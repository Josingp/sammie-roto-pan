"""
헤어 디테일 보정 (PAN.7)

매팅 결과(매트)는 "어디가 대상인지"는 잘 맞지만 외곽이 뭉개지는 경우가 있다.
 - VideoMaMa: 내부 압축 때문에 외곽이 몇 픽셀씩 부드럽게 번진다.
 - 내부 해상도(예: 720)보다 큰 영상: 줄여서 계산하고 다시 늘리므로 가는 머리카락이 사라진다.

여기서는 매트를 길잡이(trimap)로 삼아, 외곽의 불확실한 띠만 원본 해상도 그대로
ViTMatte(이미지 매팅 모델)로 다시 계산한다.
 - 확실한 안쪽/바깥쪽은 건드리지 않는다. (대상이 바뀌거나 엉뚱한 곳이 따지는 일이 없다)
 - 프레임마다 따로 계산하므로, 이어서 '매트 외곽 안정화'를 거치면 프레임 간 떨림이 줄어든다.

Qt 에 의존하지 않는다. (UI 연결은 pan_features.py)
"""

import os

import cv2
import numpy as np
import torch

MODEL_KEY = "vitmatte_s"
MODEL_PATH = os.path.join("checkpoints", "vitmatte_small", "model.safetensors")

# 탐색 폭 단계(1~5) → 기준 반경 배율. 기준 반경은 (전경 쪽 3px, 배경 쪽 6px)
BAND_SCALE = {1: 0.5, 2: 0.75, 3: 1.0, 4: 1.5, 5: 2.5}
BASE_R_FG = 3.0
BASE_R_BG = 6.0
LO, HI = 0.05, 0.95

_TILE_STEPS = (1536, 1280, 1024, 768, 512, 384)
_state = {"model": None, "device": None, "amp_ok": None}


# ---------------------------------------------------------------------------
# 모델
# ---------------------------------------------------------------------------

def is_downloaded():
    return os.path.exists(MODEL_PATH)


def load_model(device):
    """ViTMatte 를 device 에 올린다. 이미 올라가 있으면 그대로 쓴다."""
    if _state["model"] is not None and _state["device"] == str(device):
        return _state["model"]
    from sammie.vitmatte import load_vitmatte
    model = load_vitmatte(MODEL_PATH, device=device)
    _state["model"], _state["device"] = model, str(device)
    return model


def unload_model():
    _state["model"] = None
    _state["device"] = None
    import gc
    gc.collect()
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def default_tile(device):
    """한 번에 계산하는 타일 크기. 클수록 이음매가 줄지만 메모리를 더 쓴다. (모자라면 infer_alpha 가 알아서 줄인다)"""
    device = torch.device(device)
    if device.type == "cuda":
        try:
            gb = torch.cuda.get_device_properties(device).total_memory / (1024 ** 3)
        except Exception:
            gb = 0
        return 1536 if gb >= 10 else (1280 if gb >= 7.5 else 1024)
    return 1024


# ---------------------------------------------------------------------------
# trimap
# ---------------------------------------------------------------------------

def _ellipse(r):
    r = max(1, int(round(r)))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def make_trimap(matte_u8, r_fg, r_bg, lo=LO, hi=HI):
    """
    매트 → trimap (0 = 확실한 배경, 255 = 확실한 전경, 128 = 다시 계산할 띠).
    매트가 hi 이상인 곳을 r_fg 만큼, lo 이하인 곳을 r_bg 만큼 안쪽으로 깎아서 확실한 영역으로 삼는다.
    매트가 흐릿하게 번진 구간(lo~hi)은 전부 띠에 들어가므로, 번짐이 클수록 띠도 자동으로 넓어진다.
    """
    fg = (matte_u8 >= int(round(hi * 255))).astype(np.uint8)
    bg = (matte_u8 <= int(round(lo * 255))).astype(np.uint8)
    if r_fg >= 0.5:
        fg = cv2.erode(fg, _ellipse(r_fg))
    if r_bg >= 0.5:
        bg = cv2.erode(bg, _ellipse(r_bg))
    tri = np.full(matte_u8.shape, 128, np.uint8)
    tri[fg > 0] = 255
    tri[bg > 0] = 0
    return tri


# ---------------------------------------------------------------------------
# 추론 (타일)
# ---------------------------------------------------------------------------

def _positions(length, tile, overlap):
    if length <= tile:
        return [0]
    step = tile - overlap
    pos = list(range(0, length - tile, step))
    pos.append(length - tile)
    return pos


def _feather(h, w, overlap, top, bottom, left, right):
    """겹치는 가장자리에서 0→1 로 올라가는 가중치. (top/bottom/left/right: 그 변이 다른 타일과 겹치는지)"""
    wy = np.ones(h, np.float32)
    wx = np.ones(w, np.float32)
    ramp = np.linspace(0.0, 1.0, overlap + 2, dtype=np.float32)[1:-1]
    if top and overlap < h:
        wy[:overlap] = ramp
    if bottom and overlap < h:
        wy[-overlap:] = np.minimum(wy[-overlap:], ramp[::-1])
    if left and overlap < w:
        wx[:overlap] = ramp
    if right and overlap < w:
        wx[-overlap:] = np.minimum(wx[-overlap:], ramp[::-1])
    return wy[:, None] * wx[None, :]


def _run_tile(model, x, device, use_amp):
    """x: (4, h, w) float32 numpy. 32의 배수로 채워서 넣고 원래 크기로 잘라 돌려준다."""
    h, w = x.shape[1:]
    ph, pw = (32 - h % 32) % 32, (32 - w % 32) % 32
    if ph or pw:
        mode = "reflect" if (ph < h and pw < w) else "edge"
        x = np.pad(x, ((0, 0), (0, ph), (0, pw)), mode=mode)
    t = torch.from_numpy(np.ascontiguousarray(x))[None].to(device)
    if use_amp and _state.get("amp_ok") is not False:
        with torch.autocast(device_type="cuda", dtype=torch.float16):
            out = model(t)
        if _state.get("amp_ok") is None:
            # 이 GPU에서 반정밀도(fp16) 결과가 fp32 와 같은지 첫 타일에서 한 번 확인한다. 다르면 fp32 만 쓴다.
            ref = model(t)
            ok = bool(torch.isfinite(out).all()) and float((out.float() - ref).abs().mean()) < 0.004
            _state["amp_ok"] = ok
            if not ok:
                print("헤어 디테일 보정: 이 GPU에서는 반정밀도 계산이 맞지 않아 일반 정밀도(fp32)로 계산합니다.")
                out = ref
        elif not bool(torch.isfinite(out).all()):
            out = model(t)
    else:
        out = model(t)
    return torch.nan_to_num(out[0, 0, :h, :w].float(), nan=0.0).clamp_(0, 1).cpu().numpy()


@torch.inference_mode()
def infer_alpha(model, rgb_u8, tri_u8, device, tile=1024, overlap=128):
    """
    rgb_u8: (H, W, 3) RGB, tri_u8: (H, W) 0/128/255. 반환: (H, W) float32 알파.
    큰 이미지는 겹치는 타일로 나눠 계산하고, 띠(128)가 없는 타일은 건너뛴다.
    GPU 메모리가 모자라면 타일을 줄여 다시 시도한다.
    """
    H, W = tri_u8.shape
    device = torch.device(device)
    use_amp = device.type == "cuda"
    x = np.empty((4, H, W), np.float32)
    x[:3] = (rgb_u8.transpose(2, 0, 1).astype(np.float32) / 255.0 - 0.5) / 0.5
    x[3] = tri_u8.astype(np.float32) / 255.0
    unknown = tri_u8 == 128

    tiles = [t for t in _TILE_STEPS if t <= tile] or [_TILE_STEPS[-1]]
    last_error = None
    for tsize in tiles:
        ov = min(overlap, tsize // 4)
        try:
            acc = np.zeros((H, W), np.float32)
            wsum = np.zeros((H, W), np.float32)
            ys, xs = _positions(H, tsize, ov), _positions(W, tsize, ov)
            for yi, y0 in enumerate(ys):
                y1 = min(H, y0 + tsize)
                for xi, x0 in enumerate(xs):
                    x1 = min(W, x0 + tsize)
                    if not unknown[y0:y1, x0:x1].any():
                        continue
                    pred = _run_tile(model, x[:, y0:y1, x0:x1], device, use_amp)
                    wgt = _feather(y1 - y0, x1 - x0, ov, yi > 0, yi < len(ys) - 1, xi > 0, xi < len(xs) - 1)
                    acc[y0:y1, x0:x1] += pred * wgt
                    wsum[y0:y1, x0:x1] += wgt
            out = np.where(wsum > 0, acc / np.maximum(wsum, 1e-6), tri_u8.astype(np.float32) / 255.0)
            return out.astype(np.float32)
        except RuntimeError as e:                       # torch.OutOfMemoryError 포함
            if "out of memory" not in str(e).lower():
                raise
            last_error = e
            if device.type == "cuda":
                torch.cuda.empty_cache()
    raise last_error


# ---------------------------------------------------------------------------
# 매트 한 장 보정
# ---------------------------------------------------------------------------

def refine_matte(model, device, rgb_u8, matte_u8, band=1.0, cap=1.0, scale=1.0, mix=1.0, tile=1024, info=None):
    """
    rgb_u8: (H, W, 3) RGB 원본 프레임, matte_u8: (H, W) 매트.
    band : 탐색 폭 배율(BAND_SCALE 값)
    cap  : 매팅이 줄여서 계산된 배율(원본 짧은 변 / 내부 해상도, 1 이상). 클수록 매트 위치 오차가 커서 띠를 넓힌다.
    scale: 계산 배율(1 = 원본 그대로, 2 = 두 배로 키워서 계산)
    mix  : 띠 안에서 보정 결과를 쓰는 비율(1 = 전부, 0.5 = 매팅 원본과 반반)
    info : dict 를 주면 다시 계산한 띠의 픽셀 수를 info["band_px"] 에 더한다.
    반환: 보정된 매트 (uint8). 띠가 없으면 입력을 그대로 돌려준다.
    """
    H, W = matte_u8.shape
    lo_v = int(round(LO * 255))
    ys, xs = np.nonzero(matte_u8 > lo_v)
    if len(ys) == 0:
        return matte_u8
    r_fg = BASE_R_FG * band * cap
    r_bg = BASE_R_BG * band * cap

    # 대상 주변만 잘라서 계산 (띠 + 주변 문맥)
    pad = int(round(r_bg)) + 48
    x0, x1 = max(0, int(xs.min()) - pad), min(W, int(xs.max()) + 1 + pad)
    y0, y1 = max(0, int(ys.min()) - pad), min(H, int(ys.max()) + 1 + pad)
    crop_m = matte_u8[y0:y1, x0:x1]
    crop_rgb = rgb_u8[y0:y1, x0:x1]

    tri = make_trimap(crop_m, r_fg, r_bg)
    n_band = int((tri == 128).sum())
    if n_band == 0:
        return matte_u8
    if info is not None:
        info["band_px"] = info.get("band_px", 0) + n_band
        info["objects"] = info.get("objects", 0) + 1

    if scale > 1.0:
        ch, cw = crop_m.shape
        sh, sw = int(round(ch * scale)), int(round(cw * scale))
        big_rgb = cv2.resize(crop_rgb, (sw, sh), interpolation=cv2.INTER_CUBIC)
        big_tri = cv2.resize(tri, (sw, sh), interpolation=cv2.INTER_NEAREST)
        alpha = infer_alpha(model, big_rgb, big_tri, device, tile=tile)
        alpha = cv2.resize(alpha, (cw, ch), interpolation=cv2.INTER_AREA)
    else:
        alpha = infer_alpha(model, crop_rgb, tri, device, tile=tile)

    band_val = alpha * 255.0
    if mix < 1.0:
        band_val = crop_m.astype(np.float32) * (1.0 - mix) + band_val * mix
    refined = np.where(tri == 255, 255, np.where(tri == 0, 0, np.clip(band_val + 0.5, 0, 255))).astype(np.uint8)
    out = matte_u8.copy()
    out[y0:y1, x0:x1] = refined
    return out


# ---------------------------------------------------------------------------
# 폴더 단위 처리
# ---------------------------------------------------------------------------

def _object_ids(folder, frames):
    ids = set()
    for f in frames:
        d = os.path.join(folder, f"{f:05d}")
        if os.path.isdir(d):
            for name in os.listdir(d):
                stem, ext = os.path.splitext(name)
                if ext.lower() == ".png" and stem.isdigit():
                    ids.add(int(stem))
    return sorted(ids)


def refine_folder(source_dir, target_dir, load_frame_fn, start_frame, end_frame, device,
                  band=1.0, cap_fn=None, scale=1.0, mix_fn=None, tile=None,
                  progress_fn=None, cancel_fn=None, stats=None):
    """
    source_dir(보정 전 매트)를 읽어 보정한 결과를 target_dir 에 쓴다. 폴더 구조: {프레임:05d}/{오브젝트}.png
    load_frame_fn(frame) -> RGB uint8
    cap_fn(object_id) -> 매팅 축소 배율(>=1), mix_fn(cap) -> 보정 결과를 쓰는 비율, scale: 계산 배율
    progress_fn(done, total), cancel_fn() -> bool
    stats: dict 를 주면 "objects"(보정한 매트 수), "band_px"(다시 계산한 띠 픽셀 합)를 채운다.
    반환: 처리한 프레임 수 (취소 시 -1)
    """
    frames = list(range(start_frame, end_frame + 1))
    ids = _object_ids(source_dir, frames)
    if not ids or not frames:
        return 0
    model = load_model(device)
    caps = {oid: (cap_fn(oid) if cap_fn else 1.0) for oid in ids}
    mixes = {oid: (mix_fn(caps[oid]) if mix_fn else 1.0) for oid in ids}
    if tile is None:
        tile = default_tile(device)
    info = stats if stats is not None else {}
    for i, f in enumerate(frames):
        if cancel_fn and cancel_fn():
            return -1
        rgb = None
        out_dir = os.path.join(target_dir, f"{f:05d}")
        os.makedirs(out_dir, exist_ok=True)
        for oid in ids:
            src = os.path.join(source_dir, f"{f:05d}", f"{oid}.png")
            if not os.path.exists(src):
                continue
            matte = cv2.imread(src, cv2.IMREAD_GRAYSCALE)
            if matte is None:
                continue
            res = matte
            if matte.any():
                if rgb is None:
                    rgb = load_frame_fn(f)
                if rgb is not None:
                    if rgb.shape[:2] != matte.shape:
                        rgb = cv2.resize(rgb, (matte.shape[1], matte.shape[0]), interpolation=cv2.INTER_AREA)
                    res = refine_matte(model, device, rgb, matte, band=band, cap=caps[oid], scale=scale,
                                       mix=mixes[oid], tile=tile, info=info)
            cv2.imwrite(os.path.join(out_dir, f"{oid}.png"), res)
        if progress_fn:
            progress_fn(i + 1, len(frames))
    return len(frames)
