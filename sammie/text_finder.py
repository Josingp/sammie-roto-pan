"""
글자로 대상 찾기 (SAM 3.1) — Sammie-Roto PAN 빌드

SAM 3.1로 현재 프레임 한 장에서 글자(영어)에 해당하는 대상을 모두 찾아 마스크를 돌려준다.
트래킹은 하지 않는다. 찾은 마스크는 SAM 2에 '시작 마스크'로 넘겨서 SAM 2가 영상 전체를 따라간다.
(SAM 3.1의 영상 트래킹은 이 PC 사양에서 너무 느리고, 점으로 지정한 대상을 놓치는 문제가 있었음)

SAM 3.1은 그래픽카드 메모리를 약 4~6GB 쓰므로, 찾을 때만 올리고 끝나면 바로 내린다.
"""

import contextlib
import gc
import io
import os
import shutil

import cv2
import numpy as np

WEIGHTS_NAME = "sam3.1_multiplex.pt"
HF_PAGE = "https://huggingface.co/facebook/sam3.1"


def app_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def weights_path():
    """checkpoints 폴더의 가중치 경로. 프로그램 폴더 바로 아래에 두었으면 checkpoints로 옮긴다."""
    root = app_root()
    target = os.path.join(root, "checkpoints", WEIGHTS_NAME)
    if os.path.exists(target):
        return target
    loose = os.path.join(root, WEIGHTS_NAME)
    if os.path.exists(loose):
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(loose, target)
            print(f"SAM 3.1 모델 파일을 checkpoints 폴더로 옮겼습니다.")
            return target
        except Exception as e:
            print(f"SAM 3.1 모델 파일을 옮기지 못해 원래 위치에서 씁니다: {e}")
            return loose
    return None


def is_available():
    """(쓸 수 있는지, 안 되는 이유)"""
    try:
        import torch
        if not torch.cuda.is_available():
            return False, "SAM 3.1은 NVIDIA 그래픽카드(CUDA)에서만 동작합니다."
    except Exception as e:
        return False, f"PyTorch를 불러오지 못했습니다: {e}"
    if weights_path() is None:
        return False, (
            f"SAM 3.1 모델 파일({WEIGHTS_NAME})이 없습니다.\n\n"
            f"1) {HF_PAGE} 에서 접근 신청 후 승인받기\n"
            f"2) Files 탭에서 {WEIGHTS_NAME} (약 3.5GB) 다운로드\n"
            f"3) 받은 파일을 Sammie-Roto PAN 폴더 안의 checkpoints 폴더에 넣기"
        )
    try:
        import timm, ftfy, regex, iopath  # noqa: F401
    except Exception as e:
        return False, (f"SAM 3.1에 필요한 패키지가 없습니다 ({e}).\n"
                       "install.bat → 1) 재설치/복구를 실행하세요.")
    return True, ""


class Sam3TextFinder:
    def __init__(self):
        self.predictor = None

    def load(self):
        if self.predictor is not None:
            return
        from sam3.model_builder import build_sam3_predictor

        bpe = os.path.join(app_root(), "sam3", "assets", "bpe_simple_vocab_16e6.txt.gz")
        buf = io.StringIO()
        # 체크포인트 키 목록이 수만 자 출력되므로 숨긴다
        with contextlib.redirect_stdout(buf):
            self.predictor = build_sam3_predictor(
                checkpoint_path=weights_path(), bpe_path=bpe, version="sam3.1",
                compile=False, warm_up=False, use_fa3=False, async_loading_frames=False,
            )

    def find(self, image_bgr, text, min_prob=0.5, work_dir=None):
        """image_bgr 한 장에서 text 대상을 찾는다. [(mask(bool HxW), prob)] 를 넓은 순서로."""
        self.load()
        work_dir = work_dir or os.path.join(app_root(), "temp", "sam3_frame")
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)
        os.makedirs(work_dir, exist_ok=True)
        cv2.imwrite(os.path.join(work_dir, "00000.jpg"), image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])

        sid = None
        try:
            r = self.predictor.handle_request(dict(type="start_session", resource_path=work_dir))
            sid = r["session_id"]
            r = self.predictor.handle_request(dict(
                type="add_prompt", session_id=sid, frame_index=0, text=text.strip(),
                output_prob_thresh=min_prob))
            out = r["outputs"]
            masks = _np(out.get("out_binary_masks"))
            probs = _np(out.get("out_probs"))
            results = []
            if masks is not None:
                for i in range(len(masks)):
                    m = masks[i].astype(bool)
                    if m.ndim == 3:
                        m = m[0]
                    if m.any():
                        results.append((m, float(probs[i]) if probs is not None and len(probs) > i else 1.0))
            results.sort(key=lambda x: int(x[0].sum()), reverse=True)
            return results
        finally:
            if sid is not None:
                try:
                    self.predictor.handle_request(dict(type="close_session", session_id=sid))
                except Exception:
                    pass
            shutil.rmtree(work_dir, ignore_errors=True)

    def unload(self):
        """그래픽카드 메모리를 비우고, SAM 3.1이 켜 둔 bf16 자동 변환을 끈다(다른 모델에 영향 없게)."""
        p = self.predictor
        self.predictor = None
        if p is not None:
            ctx = getattr(p, "bf16_context", None)
            if ctx is not None:
                try:
                    ctx.__exit__(None, None, None)
                except Exception:
                    pass
            try:
                p.shutdown()
            except Exception:
                pass
            del p
        gc.collect()
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass


def _np(x):
    if x is None:
        return None
    if hasattr(x, "detach"):
        x = x.detach().cpu().numpy()
    return np.asarray(x)


def anchor_point(mask):
    """마스크 안쪽 깊숙한 한 점 (경계에서 가장 먼 점). (x, y)"""
    m = mask.astype(np.uint8)
    dist = cv2.distanceTransform(np.pad(m, 1), cv2.DIST_L2, 5)[1:-1, 1:-1]
    y, x = np.unravel_index(int(np.argmax(dist)), dist.shape)
    return int(x), int(y)
