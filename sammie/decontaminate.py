"""
외곽 색 번짐 제거 (color decontamination) — Sammie-Roto PAN 빌드

머리카락처럼 반투명한 외곽 픽셀에는 원래 배경색이 섞여 있다.
그대로 알파만 붙여서 다른 배경에 올리면 외곽에 예전 배경색 테두리(프린지)가 남는다.

합성식 C = a*F + (1-a)*B 에서
 - B(배경색)는 확실한 배경 영역의 색을 외곽 쪽으로 퍼뜨려 추정하고
 - F(전경색) = (C - (1-a)*B) / a 로 풀어낸다.
 - 알파가 낮아 계산이 불안정한 곳은 확실한 전경 영역에서 퍼뜨린 색으로 대신한다.
알파(매트) 자체는 바꾸지 않는다. 반투명 픽셀의 RGB만 바뀐다.
"""

import cv2
import numpy as np

_SIGMAS = (1.5, 3.0, 7.0, 16.0)


def _propagate(img_f, weight):
    """weight>0 인 영역의 색을 주변으로 퍼뜨린다 (가까운 색 우선)."""
    out = np.zeros_like(img_f)
    filled = np.zeros(weight.shape, np.float32)
    wimg = img_f * weight[..., None]
    for sigma in _SIGMAS:
        bw = cv2.GaussianBlur(weight, (0, 0), sigma)
        bc = cv2.GaussianBlur(wimg, (0, 0), sigma)
        est = bc / np.maximum(bw, 1e-6)[..., None]
        take = np.clip(bw * 20.0, 0.0, 1.0) * (1.0 - filled)
        out += est * take[..., None]
        filled += take
    # 끝까지 못 채운 곳은 마지막(가장 넓은) 추정으로
    rest = 1.0 - filled
    out += est * rest[..., None]
    return out


def decontaminate(image, alpha_u8, margin=64):
    """image: HxWx3 uint8, alpha_u8: HxW uint8. 반투명 픽셀의 색에서 배경색을 뺀 이미지를 돌려준다."""
    semi = (alpha_u8 > 2) & (alpha_u8 < 253)
    ys, xs = np.nonzero(semi)
    if len(ys) == 0:
        return image
    H, W = alpha_u8.shape
    y0, y1 = max(0, int(ys.min()) - margin), min(H, int(ys.max()) + 1 + margin)
    x0, x1 = max(0, int(xs.min()) - margin), min(W, int(xs.max()) + 1 + margin)

    img = image[y0:y1, x0:x1].astype(np.float32)
    a = alpha_u8[y0:y1, x0:x1].astype(np.float32) / 255.0
    semi_c = semi[y0:y1, x0:x1]

    # 큰 영역은 축소해서 색을 퍼뜨린 뒤 다시 키운다 (색 추정은 저주파라 충분)
    h, w = a.shape
    sc = min(1.0, 400.0 / max(h, w))
    if sc < 1.0:
        small = cv2.resize(img, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
        a_s = cv2.resize(a, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_AREA)
    else:
        small, a_s = img, a
    fg_prop = _propagate(small, (a_s >= 0.97).astype(np.float32))
    bg_prop = _propagate(small, (a_s <= 0.03).astype(np.float32))
    if sc < 1.0:
        fg_prop = cv2.resize(fg_prop, (w, h), interpolation=cv2.INTER_LINEAR)
        bg_prop = cv2.resize(bg_prop, (w, h), interpolation=cv2.INTER_LINEAR)

    a3 = a[..., None]
    f_solve = (img - (1.0 - a3) * bg_prop) / np.maximum(a3, 0.05)
    f_solve = np.clip(f_solve, 0.0, 255.0)
    # 알파가 낮으면 풀이가 불안정 → 퍼뜨린 전경색 쪽으로
    trust = np.clip((a - 0.08) / 0.35, 0.0, 1.0)[..., None]
    fg = f_solve * trust + fg_prop * (1.0 - trust)

    out = image.copy()
    roi = out[y0:y1, x0:x1]
    roi[semi_c] = np.clip(fg[semi_c] + 0.5, 0, 255).astype(np.uint8)
    return out
