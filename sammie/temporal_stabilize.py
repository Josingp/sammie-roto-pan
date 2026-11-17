"""
외곽 안정화 (Temporal Edge Stabilization) — Sammie-Roto PAN 전용 빌드

SAM2 세그멘테이션 마스크나 매팅 결과는 프레임마다 독립적으로 경계가 결정되기 때문에
외곽이 '발발발' 떨리는(edge chatter) 현상이 생긴다.

이 모듈은 앞뒤 프레임의 마스크를 옵티컬 플로우(DIS)로 현재 프레임에 정렬(warp)한 뒤,
'외곽 밴드' 영역에서만 시간축 가중 평균을 낸다.
 - 내부/배경(확실한 영역)은 건드리지 않으므로 형태가 뭉개지지 않는다.
 - 원본 프레임 색 차이로 플로우 신뢰도를 계산해서, 정렬이 틀린 곳(가림·빠른 움직임)은
   이웃 프레임 기여를 자동으로 줄인다 → 잔상(ghosting) 방지.
 - 세그멘테이션 마스크(이진)는 평균 후 다시 이진화 → 경계 위치를 시간축 다수결로 고정.
 - 매팅 결과(소프트 알파)는 소프트 그대로 유지 → 머리카락 디테일 보존.

원본은 백업 폴더에 보관하고, 항상 백업(원본)에서 다시 계산하므로 강도를 바꿔
여러 번 돌려도 결과가 누적되지 않는다. '원본 복원'으로 언제든 되돌릴 수 있다.
"""

import os
import shutil

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# 핵심 알고리즘 (Qt 의존성 없음 — 단위 테스트 가능)
# ---------------------------------------------------------------------------

def _to_gray_small(img_bgr, scale):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim == 3 else img_bgr
    if scale != 1.0:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return gray


def _flow_scale(h, w, max_side=960):
    s = max_side / max(h, w)
    return min(1.0, s)


class FlowCache:
    """프레임 쌍 (t -> n) 플로우를 계산·캐시. 같은 프레임을 여러 오브젝트가 공유한다."""

    def __init__(self, load_frame_fn, h, w, max_side=960):
        self.load_frame_fn = load_frame_fn
        self.h, self.w = h, w
        self.scale = _flow_scale(h, w, max_side)
        self.dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        self._gray = {}
        self._color = {}
        self._flow = {}

    def gray(self, t):
        if t not in self._gray:
            img = self.load_frame_fn(t)
            if img is None:
                return None
            self._color[t] = img
            self._gray[t] = _to_gray_small(img, self.scale)
        return self._gray[t]

    def color(self, t):
        self.gray(t)
        return self._color.get(t)

    def flow(self, t, n):
        """t 프레임의 각 픽셀이 n 프레임에서 어디에 있는지 (풀해상도 픽셀 단위)."""
        key = (t, n)
        if key not in self._flow:
            g0, g1 = self.gray(t), self.gray(n)
            if g0 is None or g1 is None:
                return None
            f = self.dis.calc(g0, g1, None)
            if self.scale != 1.0:
                f = cv2.resize(f, (self.w, self.h), interpolation=cv2.INTER_LINEAR) / self.scale
            self._flow[key] = f.astype(np.float32)
        return self._flow[key]

    def evict_before(self, t):
        for d in (self._gray, self._color):
            for k in [k for k in d if k < t]:
                del d[k]
        for k in [k for k in self._flow if k[0] < t]:
            del self._flow[k]


def edge_band(alpha_u8, band_px, soft=False):
    """외곽 밴드 마스크(float 0..1). 경계 주변 band_px 이내 + 소프트 알파 구간."""
    k = max(1, int(band_px))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
    hard = (alpha_u8 > 127).astype(np.uint8)
    grad = cv2.morphologyEx(hard, cv2.MORPH_GRADIENT, kernel)
    band = grad.astype(np.float32)
    if soft:
        semi = ((alpha_u8 > 3) & (alpha_u8 < 252)).astype(np.uint8)
        semi = cv2.dilate(semi, kernel)
        band = np.maximum(band, semi.astype(np.float32))
    # 밴드 가장자리를 부드럽게 해서 처리/비처리 경계가 티 나지 않게
    band = cv2.GaussianBlur(band, (0, 0), sigmaX=max(1.0, k / 2.0))
    return np.clip(band * 1.5, 0.0, 1.0)


def stabilize_frame(t, alphas, flows, frames_color, strength=0.7, radius=2,
                    band_px=6, soft=False, color_sigma=18.0):
    """
    한 프레임(t)의 알파를 안정화한다.

    alphas:       {frame_idx: uint8 HxW}  (t 포함, 이웃은 없을 수 있음)
    flows:        {n: flow(t->n) HxWx2}
    frames_color: {frame_idx: BGR uint8}  플로우 신뢰도 계산용
    """
    a_t = alphas[t]
    H, W = a_t.shape
    band_full = edge_band(a_t, band_px, soft=soft) * float(np.clip(strength, 0.0, 1.0))
    ys, xs = np.nonzero(band_full > 0)
    if len(ys) == 0:
        return a_t.copy()
    # 외곽 밴드가 있는 영역만 잘라서 계산 (속도)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    h, w = y1 - y0, x1 - x0
    band = band_full[y0:y1, x0:x1]
    a_c = a_t[y0:y1, x0:x1]
    grid_x, grid_y = np.meshgrid(np.arange(x0, x1, dtype=np.float32), np.arange(y0, y1, dtype=np.float32))

    acc = a_c.astype(np.float32)          # 자기 자신 가중치 1
    wsum = np.ones((h, w), np.float32)
    sigma_t = max(0.5, radius / 1.5)
    img_t = frames_color.get(t)
    img_t_f = img_t[y0:y1, x0:x1].astype(np.float32) if img_t is not None else None

    for n, flow in flows.items():
        if n == t or n not in alphas or flow is None:
            continue
        d = abs(n - t)
        w_time = float(np.exp(-0.5 * (d / sigma_t) ** 2))
        f = flow[y0:y1, x0:x1]
        mx = grid_x + f[..., 0]
        my = grid_y + f[..., 1]
        warped = cv2.remap(alphas[n], mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
        conf = np.full((h, w), w_time, np.float32)
        img_n = frames_color.get(n)
        if img_t_f is not None and img_n is not None:
            warped_img = cv2.remap(img_n, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
            diff = np.abs(warped_img - img_t_f).mean(axis=2) if warped_img.ndim == 3 else np.abs(warped_img - img_t_f)
            diff = cv2.GaussianBlur(diff, (0, 0), 1.5)
            conf *= np.exp(-(diff / color_sigma) ** 2)
        # 이미지 밖으로 나간 플로우 무시
        conf *= (mx >= 0) & (mx <= W - 1) & (my >= 0) & (my <= H - 1)
        acc += warped * conf
        wsum += conf

    smoothed = acc / wsum
    out_c = a_c.astype(np.float32) * (1.0 - band) + smoothed * band

    out = a_t.copy()
    if not soft:
        # 이진 마스크: 시간축 다수결로 경계 고정 후 다시 이진화
        res = np.where(out_c >= 127.5, 255, 0).astype(np.uint8)
        keep = band <= 0.0
        res[keep] = a_c[keep]
    else:
        res = np.clip(out_c + 0.5, 0, 255).astype(np.uint8)
    out[y0:y1, x0:x1] = res
    return out


# ---------------------------------------------------------------------------
# 폴더 단위 처리 (temp/masks, temp/matting 구조: <dir>/<frame:05d>/<obj>.png)
# ---------------------------------------------------------------------------

def _list_object_ids(folder, frames):
    ids = set()
    for f in frames:
        d = os.path.join(folder, f"{f:05d}")
        if os.path.isdir(d):
            for name in os.listdir(d):
                stem, ext = os.path.splitext(name)
                if ext.lower() == ".png" and stem.isdigit():
                    ids.add(int(stem))
    return sorted(ids)


def make_backup(target_dir, backup_dir):
    """현재 target_dir를 원본으로 백업 (기존 백업은 교체)."""
    if os.path.exists(backup_dir):
        shutil.rmtree(backup_dir)
    if os.path.exists(target_dir):
        shutil.copytree(target_dir, backup_dir)


def restore_backup(target_dir, backup_dir):
    """백업(원본)을 target_dir로 되돌린다. 백업이 없으면 False."""
    if not os.path.exists(backup_dir):
        return False
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
    shutil.copytree(backup_dir, target_dir)
    return True


def stabilize_folder(source_dir, target_dir, load_frame_fn, start_frame, end_frame,
                     strength=0.7, radius=2, band_px=6, soft=False,
                     progress_fn=None, cancel_fn=None):
    """
    source_dir(원본 백업)의 알파를 안정화해 target_dir에 쓴다.
    progress_fn(done, total) / cancel_fn() -> bool
    반환: 처리한 프레임 수 (취소 시 -1)
    """
    frames = list(range(start_frame, end_frame + 1))
    object_ids = _list_object_ids(source_dir, frames)
    if not object_ids or not frames:
        return 0

    # 해상도
    first = None
    for f in frames:
        for oid in object_ids:
            p = os.path.join(source_dir, f"{f:05d}", f"{oid}.png")
            if os.path.exists(p):
                first = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
                break
        if first is not None:
            break
    if first is None:
        return 0
    h, w = first.shape

    def load_alpha(f, oid):
        p = os.path.join(source_dir, f"{f:05d}", f"{oid}.png")
        if not os.path.exists(p):
            return None
        a = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
        if a is not None and a.shape != (h, w):
            a = cv2.resize(a, (w, h), interpolation=cv2.INTER_LINEAR)
        return a

    cache = FlowCache(load_frame_fn, h, w)
    total = len(frames)
    for i, t in enumerate(frames):
        if cancel_fn and cancel_fn():
            return -1
        lo, hi = max(start_frame, t - radius), min(end_frame, t + radius)
        neighbors = [n for n in range(lo, hi + 1) if n != t]

        frame_alphas_by_obj = {}
        for oid in object_ids:
            a_t = load_alpha(t, oid)
            if a_t is None:
                continue
            alphas = {t: a_t}
            for n in neighbors:
                a_n = load_alpha(n, oid)
                if a_n is not None:
                    alphas[n] = a_n
            frame_alphas_by_obj[oid] = alphas

        # 내용이 없는(전부 0) 프레임은 플로우 계산 생략
        need_flow = any(a[t].any() for a in frame_alphas_by_obj.values())
        flows = {}
        colors = {}
        if need_flow:
            for n in neighbors:
                flows[n] = cache.flow(t, n)
                colors[n] = cache.color(n)
            colors[t] = cache.color(t)

        out_dir = os.path.join(target_dir, f"{t:05d}")
        os.makedirs(out_dir, exist_ok=True)
        for oid, alphas in frame_alphas_by_obj.items():
            a_t = alphas[t]
            if need_flow and a_t.any():
                res = stabilize_frame(t, alphas, flows, colors, strength=strength,
                                      radius=radius, band_px=band_px, soft=soft)
            else:
                res = a_t
            cv2.imwrite(os.path.join(out_dir, f"{oid}.png"), res)

        cache.evict_before(t - radius)
        if progress_fn:
            progress_fn(i + 1, total)
    return total
