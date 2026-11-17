"""
Sammie-Roto PAN 전용 빌드 추가 기능
 - 외곽 안정화 그룹(세그멘테이션 마스크 / 매팅 매트)
 - 원클릭 누끼: 트래킹 → 마스크 안정화 → 매팅 → 매트 안정화 → 내보내기
"""

import os
import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QGroupBox, QGridLayout, QHBoxLayout, QLabel, QProgressDialog,
    QCheckBox, QComboBox, QLineEdit, QPushButton, QSlider, QVBoxLayout,
)

from sammie import core
from sammie import temporal_stabilize as ts
from sammie.settings_manager import get_settings_manager

MASK_STAB_BACKUP = os.path.join(core.temp_dir, "masks_stab_backup")
MATTE_STAB_BACKUP = os.path.join(core.temp_dir, "matting_stab_backup")
MATTE_DETAIL_BACKUP = os.path.join(core.temp_dir, "matting_detail_backup")   # 헤어 디테일 보정 전 매트

KINDS = {
    # kind: (대상 폴더, 백업 폴더, 강도 키, 범위 키, 활성 플래그 키, 소프트 여부, 밴드 px)
    "mask": (core.mask_dir, MASK_STAB_BACKUP, "stab_strength", "stab_radius", "mask_stab_active", False, 6),
    "matte": (core.matting_dir, MATTE_STAB_BACKUP, "matte_stab_strength", "matte_stab_radius", "matte_stab_active", True, 8),
}


# ---------------------------------------------------------------------------
# UI 그룹
# ---------------------------------------------------------------------------

class StabilizeGroup(QGroupBox):
    """외곽 안정화 설정 + 실행/복원 버튼"""

    def __init__(self, kind, parent=None):
        super().__init__("외곽 안정화 (떨림 제거)", parent)
        self.kind = kind
        _, _, strength_key, radius_key, _, _, _ = KINDS[kind]
        settings_mgr = get_settings_manager()

        layout = QVBoxLayout(self)
        grid = QGridLayout()

        self.strength_slider, self.strength_value = self._make_slider(
            grid, 0, "강도:", 0, 100, settings_mgr.get_session_setting(strength_key, 70), strength_key,
            "외곽을 앞뒤 프레임과 얼마나 맞출지 정합니다.\n"
            "높을수록 떨림이 줄지만, 너무 높으면 빠른 동작에서 외곽이 살짝 늦게 따라올 수 있습니다.")
        self.radius_slider, self.radius_value = self._make_slider(
            grid, 1, "참조 프레임(앞뒤):", 1, 4, settings_mgr.get_session_setting(radius_key, 2), radius_key,
            "앞뒤 몇 프레임을 참고할지 정합니다. 2가 기본, 떨림이 심하면 3~4.")
        layout.addLayout(grid)

        row = QHBoxLayout()
        label = "마스크 외곽 안정화" if kind == "mask" else "매트 외곽 안정화"
        self.run_btn = QPushButton(label)
        self.run_btn.setToolTip(
            "옵티컬 플로우로 앞뒤 프레임 외곽을 맞춰서 경계 떨림을 줄입니다.\n"
            "외곽 부분만 처리하고 안쪽은 그대로 둡니다. 원본은 백업되며 여러 번 돌려도 누적되지 않습니다."
            + ("\n(트래킹을 먼저 실행하세요)" if kind == "mask" else "\n(매팅을 먼저 실행하세요)"))
        self.restore_btn = QPushButton("원본 복원")
        self.restore_btn.setToolTip("안정화 전 원본으로 되돌립니다.")
        row.addWidget(self.run_btn, 3)
        row.addWidget(self.restore_btn, 1)
        layout.addLayout(row)

        self.compare_btn = QPushButton("누르고 있으면 안정화 전 보기")
        self.compare_btn.setToolTip("버튼을 누르고 있는 동안 안정화 전 원본을 보여줍니다. 떼면 안정화 결과로 돌아옵니다.\n재생하면서 비교하려면 '원본 복원' 후 다시 안정화하세요.")
        layout.addWidget(self.compare_btn)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setToolTip("외곽 떨림 지수: 움직임을 보정한 뒤에도 프레임 사이에 남는 외곽 차이입니다. 낮을수록 안정적입니다.")
        layout.addWidget(self.result_label)

    def _make_slider(self, grid, row, text, lo, hi, val, key, tip):
        lbl = QLabel(text)
        lbl.setToolTip(tip)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(int(val))
        slider.setToolTip(tip)
        value = QLabel(str(int(val)))
        value.setMinimumWidth(30)
        value.setAlignment(Qt.AlignCenter)
        slider.valueChanged.connect(lambda v, l=value: l.setText(str(v)))
        slider.valueChanged.connect(lambda v, k=key: get_settings_manager().set_session_setting(k, int(v)))
        grid.addWidget(lbl, row, 0)
        grid.addWidget(slider, row, 1)
        grid.addWidget(value, row, 2)
        return slider, value

    def load_values_from_settings(self):
        _, _, strength_key, radius_key, _, _, _ = KINDS[self.kind]
        sm = get_settings_manager()
        self.strength_slider.setValue(int(sm.get_session_setting(strength_key, 70)))
        self.radius_slider.setValue(int(sm.get_session_setting(radius_key, 2)))


class DetailGroup(QGroupBox):
    """헤어 디테일 보정 설정 + 실행/복원 버튼 (매팅 탭)"""

    QUALITIES = ["표준", "고정밀(2배)"]

    def __init__(self, parent=None):
        super().__init__("헤어 디테일 보정 (머리카락·잔털)", parent)
        sm = get_settings_manager()
        layout = QVBoxLayout(self)
        grid = QGridLayout()

        tip_band = ("매트 외곽에서 얼마나 넓게 다시 살펴볼지 정합니다.\n"
                    "넓히면 매팅이 놓친 바깥쪽 잔머리까지 찾지만, 배경이 머리색과 비슷하면 배경이 묻어 들어올 수 있습니다.\n"
                    "3이 기본, 잔머리가 덜 따지면 4~5, 배경이 묻으면 1~2.")
        lbl = QLabel("탐색 폭:")
        lbl.setToolTip(tip_band)
        self.band_slider = QSlider(Qt.Horizontal)
        self.band_slider.setRange(1, 5)
        self.band_slider.setValue(int(sm.get_session_setting("detail_band", 3)))
        self.band_slider.setToolTip(tip_band)
        self.band_value = QLabel(str(self.band_slider.value()))
        self.band_value.setMinimumWidth(30)
        self.band_value.setAlignment(Qt.AlignCenter)
        self.band_slider.valueChanged.connect(lambda v: self.band_value.setText(str(v)))
        self.band_slider.valueChanged.connect(lambda v: get_settings_manager().set_session_setting("detail_band", int(v)))
        grid.addWidget(lbl, 0, 0)
        grid.addWidget(self.band_slider, 0, 1)
        grid.addWidget(self.band_value, 0, 2)

        tip_q = ("표준: 원본 해상도 그대로 계산합니다. (기본)\n"
                 "고정밀(2배): 두 배로 키워서 계산합니다. 4배쯤 느리고, 영상에 따라 더 좋아지기도 나빠지기도 하니\n"
                 "표준 결과가 아쉬울 때 비교해 보고 쓰세요.")
        qlbl = QLabel("정밀도:")
        qlbl.setToolTip(tip_q)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(self.QUALITIES)
        self.quality_combo.setToolTip(tip_q)
        q = str(sm.get_session_setting("detail_quality", "표준"))
        self.quality_combo.setCurrentText(q if q in self.QUALITIES else "표준")
        self.quality_combo.currentTextChanged.connect(
            lambda v: get_settings_manager().set_session_setting("detail_quality", v))
        grid.addWidget(qlbl, 1, 0)
        grid.addWidget(self.quality_combo, 1, 1, 1, 2)
        layout.addLayout(grid)

        row = QHBoxLayout()
        self.run_btn = QPushButton("헤어 디테일 보정")
        self.run_btn.setToolTip(
            "매팅 결과를 길잡이로 삼아, 외곽의 불확실한 띠만 원본 해상도에서 다시 계산합니다 (ViTMatte).\n"
            "VideoMaMa 처럼 외곽이 부드럽게 번지는 매트, 내부 해상도보다 큰 영상(4K 등)에서 효과가 큽니다.\n"
            "안쪽·바깥쪽 확실한 부분은 건드리지 않고, 원본은 백업됩니다. (매팅을 먼저 실행하세요)")
        self.restore_btn = QPushButton("원본 복원")
        self.restore_btn.setToolTip("보정 전 매트로 되돌립니다.")
        row.addWidget(self.run_btn, 3)
        row.addWidget(self.restore_btn, 1)
        layout.addLayout(row)

        self.compare_btn = QPushButton("누르고 있으면 보정 전 보기")
        self.compare_btn.setToolTip("버튼을 누르고 있는 동안 보정 전 매트를 보여줍니다. 떼면 보정 결과로 돌아옵니다.")
        layout.addWidget(self.compare_btn)

        self.one_click_cb = QCheckBox("원클릭 누끼에 포함")
        self.one_click_cb.setToolTip("켜 두면 원클릭 누끼가 매팅 다음에 헤어 디테일 보정까지 자동으로 합니다.")
        self.one_click_cb.setChecked(bool(sm.get_session_setting("detail_one_click", True)))
        self.one_click_cb.stateChanged.connect(
            lambda _: get_settings_manager().set_session_setting("detail_one_click", self.one_click_cb.isChecked()))
        layout.addWidget(self.one_click_cb)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

    def load_values_from_settings(self):
        sm = get_settings_manager()
        self.band_slider.setValue(int(sm.get_session_setting("detail_band", 3)))
        q = str(sm.get_session_setting("detail_quality", "표준"))
        self.quality_combo.setCurrentText(q if q in self.QUALITIES else "표준")
        self.one_click_cb.setChecked(bool(sm.get_session_setting("detail_one_click", True)))


def make_decontam_checkbox():
    cb = QCheckBox("외곽 색 번짐 제거 (배경색 빼기)")
    cb.setToolTip(
        "머리카락 같은 반투명 외곽에 섞여 있는 원래 배경색을 빼냅니다.\n"
        "다른 배경에 합성했을 때 외곽에 예전 배경색 테두리가 남지 않습니다.\n"
        "Alpha·BGcolor 보기와 내보내기에 적용되고, 흑백 매트는 바뀌지 않습니다.")
    cb.setChecked(bool(get_settings_manager().get_session_setting("matte_decontam", True)))
    cb.stateChanged.connect(
        lambda _: get_settings_manager().set_session_setting("matte_decontam", cb.isChecked()))
    return cb


_compare_saved = {}


def compare_press(main_window, kind):
    """누르는 동안 안정화 전 원본(백업)을 화면에 보여준다."""
    target, backup, _, _, _, _, _ = KINDS[kind]
    if not os.path.exists(backup):
        print("비교할 원본이 없습니다 (아직 안정화하지 않았습니다).")
        return
    if kind in _compare_saved or (kind == "matte" and "detail" in _compare_saved):
        return
    attr = "mask_dir" if kind == "mask" else "matting_dir"
    _compare_saved[kind] = getattr(core, attr)
    setattr(core, attr, backup)
    main_window._update_current_frame_display()


def compare_release(main_window, kind):
    if kind in _compare_saved:
        setattr(core, "mask_dir" if kind == "mask" else "matting_dir", _compare_saved.pop(kind))
        main_window._update_current_frame_display()


def detail_compare_press(main_window):
    """누르는 동안 헤어 디테일 보정 전 매트를 보여준다."""
    if not os.path.exists(MATTE_DETAIL_BACKUP):
        print("비교할 원본이 없습니다 (아직 헤어 디테일 보정을 하지 않았습니다).")
        return
    if "detail" in _compare_saved or "matte" in _compare_saved:
        return
    _compare_saved["detail"] = core.matting_dir
    core.matting_dir = MATTE_DETAIL_BACKUP
    main_window._update_current_frame_display()


def detail_compare_release(main_window):
    if "detail" in _compare_saved:
        core.matting_dir = _compare_saved.pop("detail")
        main_window._update_current_frame_display()


def _group_for(main_window, kind):
    try:
        tab = main_window.sidebar.segmentation_tab if kind == "mask" else main_window.sidebar.matting_tab
        return tab.stab_group
    except Exception:
        return None


def make_one_click_button():
    btn = QPushButton("원클릭 누끼\n트래킹 → 매팅 → 헤어 디테일 → 안정화 → 내보내기")
    btn.setToolTip(
        "점을 찍은 뒤 이 버튼 하나로 끝까지 진행합니다.\n"
        "1) 전체 트래킹  2) 마스크 외곽 안정화  3) 매팅(머리카락 등 반투명 외곽)\n"
        "4) 헤어 디테일 보정  5) 매트 외곽 안정화  6) 내보내기 창 열기\n"
        "매팅 모델과 해상도는 이 PC의 그래픽카드 메모리에 맞춰 자동으로 정하고,\n메모리가 모자라면 설정을 낮춰 다시 시도합니다.")
    btn.setMinimumHeight(46)
    btn.setStyleSheet("QPushButton { font-weight: bold; }")
    return btn


# ---------------------------------------------------------------------------
# 무효화 (원본이 바뀌면 백업을 다시 떠야 함)
# ---------------------------------------------------------------------------

def invalidate(kind):
    _, backup, _, _, flag, _, _ = KINDS[kind]
    get_settings_manager().set_session_setting(flag, False)
    if os.path.exists(backup):
        shutil.rmtree(backup, ignore_errors=True)
    if kind == "matte":
        # 매트가 새로 만들어지면 헤어 디테일 보정도 처음부터
        get_settings_manager().set_session_setting("detail_active", False)
        if os.path.exists(MATTE_DETAIL_BACKUP):
            shutil.rmtree(MATTE_DETAIL_BACKUP, ignore_errors=True)


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------

def _merge_tree(src_dir, dst_dir):
    """src_dir 의 파일들을 같은 경로로 dst_dir 에 덮어쓴다 (dst 에만 있는 파일은 그대로 둔다)."""
    for root, _, files in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        out = dst_dir if rel == "." else os.path.join(dst_dir, rel)
        os.makedirs(out, exist_ok=True)
        for name in files:
            shutil.copyfile(os.path.join(root, name), os.path.join(out, name))


def _has_output(folder, start, end):
    if not os.path.isdir(folder):
        return False
    for f in (start, end):
        d = os.path.join(folder, f"{f:05d}")
        if not (os.path.isdir(d) and any(n.endswith(".png") for n in os.listdir(d))):
            return False
    return True


def run_stabilize(main_window, kind, quiet=False):
    """반환: True(완료) / False(취소·불가)"""
    target, backup, strength_key, radius_key, flag, soft, band_px = KINDS[kind]
    sm = get_settings_manager()
    start, end, total = core.get_frame_range()

    if not _has_output(target, start, end):
        if not quiet:
            from sammie.gui_widgets import show_message_dialog
            msg = ("먼저 트래킹을 실행해서 모든 프레임에 마스크를 만들어 주세요." if kind == "mask"
                   else "먼저 매팅을 실행해 주세요.")
            show_message_dialog(main_window, title="외곽 안정화", message=msg, type="warning")
        return False

    # 원본 백업: 이미 안정화된 상태가 아니면 현재 결과를 원본으로 저장
    had_backup = bool(sm.get_session_setting(flag, False)) and os.path.exists(backup)
    if not had_backup:
        ts.make_backup(target, backup)

    strength = sm.get_session_setting(strength_key, 70) / 100.0
    radius = int(sm.get_session_setting(radius_key, 2))

    progress = QProgressDialog("외곽 안정화 중...", "취소", 0, total, main_window)
    progress.setWindowTitle("외곽 안정화")
    progress.setWindowModality(Qt.WindowModal)
    progress.setMinimumDuration(0)
    progress.setValue(0)

    def on_progress(done, tot):
        progress.setValue(done)
        QApplication.processEvents()

    print(f"외곽 안정화 시작 ({'마스크' if kind == 'mask' else '매트'}, 강도 {int(strength*100)}, 참조 ±{radius}프레임)")
    stats = {}
    # 작업 폴더에 먼저 쓰고, 끝까지 됐을 때만 결과 폴더에 반영한다.
    # (도중에 취소해도 이전 상태 — 원본이든 이전 안정화 결과든 — 가 그대로 남는다)
    work = target + "_stab_work"
    shutil.rmtree(work, ignore_errors=True)
    try:
        result = ts.stabilize_folder(
            backup, work, core.load_base_frame, start, end,
            strength=strength, radius=radius, band_px=band_px, soft=soft,
            progress_fn=on_progress, cancel_fn=progress.wasCanceled, stats=stats)
    except Exception as e:
        print(f"외곽 안정화 중 오류: {e}")
        result = -1
    progress.close()

    if result <= 0:
        shutil.rmtree(work, ignore_errors=True)
        if not had_backup:
            shutil.rmtree(backup, ignore_errors=True)
        print("외곽 안정화 취소됨 (이전 상태 그대로)")
        main_window._update_current_frame_display()
        return False

    _merge_tree(work, target)
    shutil.rmtree(work, ignore_errors=True)
    sm.set_session_setting(flag, True)

    print(f"외곽 안정화 완료: {result}프레임")
    before, after = stats.get("before", 0.0), stats.get("after", 0.0)
    if before > 0:
        msg = f"외곽 떨림 지수 {before:.1f} → {after:.1f} ({(after / before - 1) * 100:+.0f}%)"
        print(msg)
        grp = _group_for(main_window, kind)
        if grp is not None:
            grp.result_label.setText(msg)
    sm.save_session_settings()
    main_window._update_current_frame_display()
    return True


def restore_stabilize(main_window, kind):
    target, backup, _, _, flag, _, _ = KINDS[kind]
    if ts.restore_backup(target, backup):
        print("안정화 전 원본으로 복원했습니다.")
    else:
        print("복원할 원본이 없습니다 (아직 안정화하지 않았습니다).")
    get_settings_manager().set_session_setting(flag, False)
    if os.path.exists(backup):
        shutil.rmtree(backup, ignore_errors=True)
    grp = _group_for(main_window, kind)
    if grp is not None:
        grp.result_label.setText("")
    main_window._update_current_frame_display()


# ---------------------------------------------------------------------------
# 헤어 디테일 보정 (ViTMatte)
#   매팅 원본(R) → 디테일 보정 D(R) → 외곽 안정화 S(·) 순서로 쌓인다.
#   matting_detail_backup = R (보정이 켜져 있을 때만 존재)
#   matting_stab_backup   = 안정화의 입력 (R 또는 D(R))
# ---------------------------------------------------------------------------

def _detail_group(main_window):
    try:
        return main_window.sidebar.matting_tab.detail_group
    except Exception:
        return None


def _detail_cap_factor(object_id):
    """매팅이 원본보다 줄여서 계산된 배율(>=1). 매트 위치 오차가 그만큼 커지므로 탐색 띠를 넓히는 데 쓴다."""
    sm = get_settings_manager()
    try:
        res = int(sm.get_session_setting("matany_res", 0) or 0)
    except Exception:
        res = 0
    if res <= 0:
        return 1.0
    short = min(core.VideoInfo.width or 0, core.VideoInfo.height or 0)
    if short <= 0:
        return 1.0
    if sm.get_session_setting("matany_model", "MatAnyone2") == "VideoMaMa" and not sm.get_session_setting("matany_combined", False):
        # VideoMaMa 는 오브젝트 주변만 잘라서 계산한다 → 잘린 영역의 짧은 변이 기준
        try:
            start, end, total = core.get_frame_range()
            step = max(1, total // 40)
            rect = core.compute_mask_bounding_box(range(start, end + 1, step), [object_id])
            if rect:
                short = max(8, min(rect[2] - rect[0], rect[3] - rect[1]))
        except Exception:
            pass
    return max(1.0, min(4.0, short / float(res)))


def _detail_scale(quality):
    """계산 배율: 표준 1배 / 고정밀 2배"""
    return 2.0 if str(quality).startswith("고정밀") else 1.0


def _detail_mix(cap):
    """보정 결과를 얼마나 쓸지(0~1). 나머지는 매팅 원본.
    - VideoMaMa(외곽이 번짐)나 줄여서 계산된 매트: 보정 결과를 그대로 쓴다.
    - MatAnyone 이 원본 해상도로 계산한 매트: 이미 세밀하므로 반반 섞는 쪽이 오차가 가장 작았다."""
    sm = get_settings_manager()
    if sm.get_session_setting("matany_model", "MatAnyone2") == "VideoMaMa" or cap >= 1.3:
        return 1.0
    return 0.5


_detail_status = {"last": ""}        # "ok" / "cancel" / "error" — 원클릭이 취소와 오류를 구분하는 데 쓴다


def run_detail(main_window, quiet=False):
    """헤어 디테일 보정. 반환: True(완료) / False(취소·불가). 이유는 _detail_status["last"]"""
    _detail_status["last"] = "error"
    from sammie import hair_detail as hd
    from sammie.gui_widgets import show_message_dialog
    from sammie.model_downloader import ensure_models

    sm = get_settings_manager()
    start, end, total = core.get_frame_range()
    target = KINDS["matte"][0]

    if not _has_output(target, start, end):
        if not quiet:
            show_message_dialog(main_window, title="헤어 디테일 보정", message="먼저 매팅을 실행해 주세요.", type="warning")
        return False
    if not ensure_models([hd.MODEL_KEY], parent=main_window):
        print("헤어 디테일 보정: 모델(ViTMatte)을 받지 못했습니다. 인터넷 연결을 확인하고 다시 시도해 주세요.")
        return False

    stab_on = bool(sm.get_session_setting("matte_stab_active", False)) and os.path.exists(MATTE_STAB_BACKUP)
    detail_on = bool(sm.get_session_setting("detail_active", False)) and os.path.exists(MATTE_DETAIL_BACKUP)
    # 보정의 입력은 항상 매팅 원본
    if detail_on:
        raw = MATTE_DETAIL_BACKUP
    elif stab_on:
        raw = MATTE_STAB_BACKUP
    else:
        raw = target

    band_level = int(sm.get_session_setting("detail_band", 3))
    quality = str(sm.get_session_setting("detail_quality", "표준"))
    band = hd.BAND_SCALE.get(band_level, 1.0)

    progress = QProgressDialog("헤어 디테일 보정 중...", "취소", 0, total, main_window)
    progress.setWindowTitle("헤어 디테일 보정")
    progress.setWindowModality(Qt.WindowModal)
    progress.setMinimumDuration(0)
    progress.setValue(0)
    QApplication.processEvents()

    def on_progress(done, tot):
        progress.setValue(done)
        QApplication.processEvents()

    device = core.DeviceManager.get_device()
    print(f"헤어 디테일 보정 시작 (탐색 폭 {band_level}, 정밀도 {quality}, {str(device).upper()})")
    work = target + "_detail_work"
    shutil.rmtree(work, ignore_errors=True)
    stats = {}
    result, error = -1, None
    sam = getattr(main_window, "sam_manager", None)
    try:
        if sam is not None:
            sam.offload_model_to_cpu()          # GPU 메모리 확보
        result = hd.refine_folder(
            raw, work, core.load_base_frame, start, end, device,
            band=band, cap_fn=_detail_cap_factor, scale=_detail_scale(quality), mix_fn=_detail_mix,
            progress_fn=on_progress, cancel_fn=progress.wasCanceled, stats=stats)
    except Exception as e:
        error = e
    finally:
        hd.unload_model()
        try:
            if sam is not None:
                sam.load_model_to_device()
        except Exception as e:
            print(f"SAM 모델을 다시 올리지 못했습니다: {e}")
        progress.close()

    if error is not None or result <= 0:
        shutil.rmtree(work, ignore_errors=True)
        if error is not None:
            oom = "out of memory" in str(error).lower()
            msg = ("GPU 메모리가 부족해서 헤어 디테일 보정을 끝내지 못했습니다.\n정밀도를 '표준'으로 바꾸거나 In/Out 마커로 구간을 나눠 다시 시도해 보세요."
                   if oom else f"헤어 디테일 보정 중 오류가 났습니다.\n{error}")
            print(msg.replace("\n", " "))
            if not quiet:
                show_message_dialog(main_window, title="헤어 디테일 보정", message=msg, type="warning")
        else:
            _detail_status["last"] = "cancel"
            print("헤어 디테일 보정 취소됨 (이전 상태 그대로)")
        main_window._update_current_frame_display()
        return False

    if not detail_on:
        ts.make_backup(raw, MATTE_DETAIL_BACKUP)        # 보정 전 원본 보관
    _merge_tree(work, MATTE_STAB_BACKUP if stab_on else target)
    shutil.rmtree(work, ignore_errors=True)
    sm.set_session_setting("detail_active", True)

    n = stats.get("objects", 0)
    msg = (f"헤어 디테일 보정 완료: {result}프레임 · 매트 {n}장"
           + (f" (장당 외곽 띠 약 {int(round(stats['band_px'] / n, -2)):,}픽셀 재계산)" if n else ""))
    print(msg)
    grp = _detail_group(main_window)
    if grp is not None:
        grp.result_label.setText(msg + "\n'누르고 있으면 보정 전 보기'로 비교해 보세요.")

    if stab_on:
        # 안정화가 켜져 있었으면 보정된 매트로 다시 안정화
        print("보정된 매트로 외곽 안정화를 다시 적용합니다.")
        if not run_stabilize(main_window, "matte", quiet=True):
            # 다시 안정화하지 못하면 화면의 매트가 보정 전 것으로 남으므로, 안정화를 풀어 보정된 매트를 그대로 보여준다
            restore_stabilize(main_window, "matte")
            print("안정화를 다시 적용하지 못해 해제했습니다. 보정된 매트는 적용돼 있습니다. 필요하면 '매트 외곽 안정화'를 다시 눌러 주세요.")
    sm.save_session_settings()
    main_window._update_current_frame_display()
    _detail_status["last"] = "ok"
    return True


def restore_detail(main_window):
    sm = get_settings_manager()
    target = KINDS["matte"][0]
    grp = _detail_group(main_window)
    if grp is not None:
        grp.result_label.setText("")
    if not (bool(sm.get_session_setting("detail_active", False)) and os.path.exists(MATTE_DETAIL_BACKUP)):
        print("복원할 원본이 없습니다 (아직 헤어 디테일 보정을 하지 않았습니다).")
        sm.set_session_setting("detail_active", False)
        return
    stab_on = bool(sm.get_session_setting("matte_stab_active", False)) and os.path.exists(MATTE_STAB_BACKUP)
    ts.restore_backup(MATTE_STAB_BACKUP if stab_on else target, MATTE_DETAIL_BACKUP)
    shutil.rmtree(MATTE_DETAIL_BACKUP, ignore_errors=True)
    sm.set_session_setting("detail_active", False)
    print("헤어 디테일 보정 전 매트로 복원했습니다.")
    if stab_on:
        print("복원한 매트로 외곽 안정화를 다시 적용합니다.")
        if not run_stabilize(main_window, "matte", quiet=True):
            restore_stabilize(main_window, "matte")
            print("안정화를 다시 적용하지 못해 해제했습니다. 필요하면 '매트 외곽 안정화'를 다시 눌러 주세요.")
    sm.save_session_settings()
    main_window._update_current_frame_display()


def _vram_gb():
    try:
        import torch
        dev = core.DeviceManager.get_device()
        if dev.type == "cuda":
            return torch.cuda.get_device_properties(dev).total_memory / (1024 ** 3)
    except Exception:
        pass
    return 0.0


def _gpu_name():
    try:
        import torch
        dev = core.DeviceManager.get_device()
        if dev.type == "cuda":
            return torch.cuda.get_device_name(dev)
        return dev.type.upper()
    except Exception:
        return "알 수 없음"


def auto_profile():
    """그래픽카드 메모리에 맞는 매팅 설정. (모델, 내부 해상도, 배치당 프레임)
    기준값은 보수적으로 잡았고, 그래도 메모리가 모자라면 원클릭이 한 단계씩 낮춰 다시 시도한다."""
    v = _vram_gb()
    if v >= 20:
        return "VideoMaMa", 1080, 16
    if v >= 11.5:
        return "VideoMaMa", 720, 16
    if v >= 6:
        return "MatAnyone2", 1080, 16
    return "MatAnyone2", 720, 16


def _set_matting(main_window, model, res, chunk=None):
    sm = get_settings_manager()
    sm.set_session_setting("matany_model", model)
    sm.set_session_setting("matany_res", res)
    if chunk:
        sm.set_session_setting("matany_chunk", chunk)
    mt = main_window.sidebar.matting_tab
    if mt is not None:
        mt.matany_model_combo.setCurrentText(model)
        mt.matany_res_combo.setCurrentText(str(res))
        if chunk:
            mt.chunk_combo.setCurrentText(str(chunk))


def apply_auto_profile(main_window):
    model, res, chunk = auto_profile()
    _set_matting(main_window, model, res, chunk)
    v = _vram_gb()
    spec = f"{_gpu_name()}" + (f" (VRAM {v:.0f}GB)" if v > 0 else "")
    print(f"[자동 설정] {spec} → 매팅 모델 {model}, 내부 해상도 {res}")
    return model, res


_RES_STEPS = [1080, 720, 576, 480]


def _lower_setting(model, res):
    """메모리 부족 시 다음에 시도할 설정. 더 낮출 수 없으면 None."""
    lower = [r for r in _RES_STEPS if r < res]
    if model == "VideoMaMa":
        if res > 720 and lower:
            return "VideoMaMa", lower[0]
        return "MatAnyone2", 720          # VideoMaMa가 720에서도 안 되면 가벼운 모델로
    if lower:
        return model, lower[0]
    return None


def run_matting_auto(main_window):
    """사양에 맞춘 설정으로 매팅. 메모리가 모자라면 한 단계씩 낮춰 최대 4번 시도. 성공하면 True."""
    start, end, _ = core.get_frame_range()
    model, res = apply_auto_profile(main_window)
    main_window._pan_auto_retry = True
    try:
        for _ in range(4):
            main_window._pan_oom = False
            main_window.run_matting()
            if not main_window._pan_oom:
                return _has_output(core.matting_dir, start, end)
            nxt = _lower_setting(model, res)
            if nxt is None:
                break
            model, res = nxt
            print(f"[자동 설정] 다시 시도: 매팅 모델 {model}, 내부 해상도 {res}")
            _set_matting(main_window, model, res)
        from sammie.gui_widgets import show_message_dialog
        show_message_dialog(main_window, title="원클릭 누끼",
                            message="GPU 메모리가 부족해서 매팅을 끝내지 못했습니다.\nIn/Out 마커로 구간을 나눠서 다시 시도해 보세요.",
                            type="warning")
        return False
    finally:
        main_window._pan_auto_retry = False


def run_one_click(main_window):
    from sammie.gui_widgets import show_message_dialog

    if core.VideoInfo.total_frames == 0:
        show_message_dialog(main_window, title="원클릭 누끼", message="먼저 영상을 불러와 주세요.", type="warning")
        return
    if len(main_window.point_manager.points) == 0:
        show_message_dialog(main_window, title="원클릭 누끼",
                            message="먼저 따낼 대상 위를 클릭해서 점을 찍어 주세요.\n(좌클릭: 포함 / 우클릭: 제외)",
                            type="warning")
        return

    start, end, _ = core.get_frame_range()

    sm = get_settings_manager()
    use_detail = bool(sm.get_session_setting("detail_one_click", True))
    steps = 6 if use_detail else 5
    step = [0]

    def announce(name):
        step[0] += 1
        print(f"[원클릭 {step[0]}/{steps}] {name}")

    # 1) 트래킹
    announce("트래킹")
    main_window.track_objects()
    if not _has_output(core.mask_dir, start, end):
        print("원클릭 중단: 트래킹이 끝나지 않았습니다.")
        return

    # 2) 마스크 안정화
    announce("마스크 외곽 안정화")
    if not run_stabilize(main_window, "mask", quiet=True):
        print("원클릭 중단: 마스크 안정화 취소")
        return

    # 3) 매팅
    announce("매팅")
    if not run_matting_auto(main_window):
        print("원클릭 중단: 매팅이 끝나지 않았습니다.")
        return
    if not _has_output(core.matting_dir, start, end):
        print("원클릭 중단: 매팅이 끝나지 않았습니다.")
        return

    # 4) 헤어 디테일 보정 (끌 수 있음). 실패해도 매팅 결과는 그대로이므로 계속 진행한다.
    if use_detail:
        announce("헤어 디테일 보정")
        if not run_detail(main_window, quiet=True):
            if _detail_status["last"] == "cancel":
                print("원클릭 중단: 헤어 디테일 보정 취소")
                return
            print("헤어 디테일 보정을 건너뜁니다 (매팅 결과 그대로 진행).")

    # 5) 매트 안정화
    announce("매트 외곽 안정화")
    if not run_stabilize(main_window, "matte", quiet=True):
        print("원클릭 중단: 매트 안정화 취소")
        return

    announce("내보내기")
    # 매팅 탭 + 알파 보기 → 내보내기
    try:
        main_window.sidebar.tab_widget.setCurrentIndex(1)
        idx = main_window.view_combo.findText("Matting-BGcolor")
        if idx >= 0:
            main_window.view_combo.setCurrentIndex(idx)
    except Exception:
        pass
    # 내보내기 창이 매팅 결과로 열리도록 (세그멘테이션 매트가 기본값이면 바꿔 둠)
    if not str(sm.app_settings.export_output_type).startswith("Matting"):
        sm.set_app_setting("export_output_type", "Matting-Matte")
    main_window.export_video()


# ---------------------------------------------------------------------------
# 글자로 대상 찾기 (SAM 3.1 → SAM 2)
# ---------------------------------------------------------------------------

class TextFindGroup(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("글자로 대상 찾기 (SAM 3.1)", parent)
        layout = QVBoxLayout(self)
        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText("영어로 입력: person, woman, dog, car ...")
        self.text_edit.setToolTip(
            "찾을 대상을 영어 단어나 짧은 문장으로 입력합니다.\n"
            "예) person / woman with long hair / man in black suit / dog / car")
        layout.addWidget(self.text_edit)
        row = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["찾은 대상 전부", "가장 큰 1개만"])
        self.mode_combo.setToolTip("찾은 대상을 모두 오브젝트로 만들지, 화면에서 가장 큰 하나만 쓸지 고릅니다.")
        self.find_btn = QPushButton("현재 프레임에서 찾기")
        self.find_btn.setToolTip(
            "현재 프레임에서 SAM 3.1로 대상을 찾아 오브젝트로 만듭니다.\n"
            "그다음 '전체 트래킹'(또는 원클릭 누끼)을 누르면 SAM 2가 영상 전체를 따라갑니다.\n"
            "찾은 프레임에 점을 더 찍으면 그 프레임은 점 기준으로 다시 잡힙니다.\n"
            "처음 찾을 때는 모델을 불러오느라 30초~1분 걸립니다.")
        row.addWidget(self.mode_combo, 2)
        row.addWidget(self.find_btn, 3)
        layout.addLayout(row)
        self.text_edit.returnPressed.connect(self.find_btn.click)


def _free_object_ids(main_window, count):
    used = {p['object_id'] for p in main_window.point_manager.points}
    max_id = 20
    try:
        max_id = main_window.sidebar.segmentation_tab.object_spinbox.maximum()
    except Exception:
        pass
    return [i for i in range(0, max_id + 1) if i not in used][:count]


def run_text_find(main_window):
    from sammie.gui_widgets import show_message_dialog
    from sammie import text_finder

    grp = main_window.sidebar.segmentation_tab.text_find_group
    text = grp.text_edit.text().strip()
    if core.VideoInfo.total_frames == 0:
        show_message_dialog(main_window, title="글자로 대상 찾기", message="먼저 영상을 불러와 주세요.", type="warning")
        return
    if not text:
        show_message_dialog(main_window, title="글자로 대상 찾기",
                            message="찾을 대상을 영어로 입력해 주세요. (예: person)", type="warning")
        return
    if any("\uac00" <= ch <= "\ud7a3" for ch in text):
        show_message_dialog(main_window, title="글자로 대상 찾기",
                            message="SAM 3.1은 영어만 알아듣습니다. 영어로 입력해 주세요.\n예) 사람 → person, 여자 → woman, 강아지 → dog",
                            type="warning")
        return
    ok, why = text_finder.is_available()
    if not ok:
        show_message_dialog(main_window, title="글자로 대상 찾기", message=why, type="warning")
        return

    frame = main_window.frame_slider.value()
    image = core.load_base_frame(frame)  # RGB
    if image is None:
        return
    import cv2
    image_bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    progress = QProgressDialog("SAM 3.1로 찾는 중... (처음엔 모델을 불러오느라 30초~1분)", None, 0, 0, main_window)
    progress.setWindowTitle("글자로 대상 찾기")
    progress.setWindowModality(Qt.WindowModal)
    progress.setMinimumDuration(0)
    progress.show()
    QApplication.processEvents()

    finder = text_finder.Sam3TextFinder()
    results = []
    error = None
    main_window.sam_manager.offload_model_to_cpu()   # SAM 2를 잠시 내려서 메모리 확보
    try:
        print(f"[글자 찾기] '{text}' — 프레임 {frame}")
        finder.load()
        QApplication.processEvents()
        results = finder.find(image_bgr, text)
    except Exception as e:
        import traceback
        traceback.print_exc()
        error = e
    finally:
        finder.unload()
        main_window.sam_manager.load_model_to_device()
        progress.close()

    if error is not None:
        msg = str(error)
        if "out of memory" in msg.lower():
            msg = "GPU 메모리가 부족합니다. 다른 프로그램을 닫고 다시 시도해 주세요."
        show_message_dialog(main_window, title="글자로 대상 찾기", message=f"찾는 중 오류가 났습니다.\n{msg}", type="warning")
        return
    if not results:
        show_message_dialog(main_window, title="글자로 대상 찾기",
                            message=f"'{text}'에 해당하는 대상을 이 프레임에서 찾지 못했습니다.\n다른 단어로 바꾸거나, 대상이 잘 보이는 프레임에서 다시 해 보세요.",
                            type="info")
        return

    if grp.mode_combo.currentIndex() == 1:
        results = results[:1]
    ids = _free_object_ids(main_window, len(results))
    if len(ids) < len(results):
        print(f"[글자 찾기] 오브젝트 번호가 모자라 {len(ids)}개만 추가합니다.")
        results = results[:len(ids)]

    from sammie.settings_manager import get_settings_manager
    sm = get_settings_manager()
    names = dict(sm.get_session_setting("object_names", {}) or {})
    for (mask, prob), oid in zip(results, ids):
        x, y = text_finder.anchor_point(mask)
        main_window.point_manager.add_point(frame, oid, True, x, y)
        main_window.sam_manager.add_text_object(frame, oid, mask, (x, y), label=text)
        names.setdefault(str(oid), f"{text} {oid}")
        print(f"[글자 찾기] 오브젝트 {oid}: 확률 {prob:.2f}, 넓이 {int(mask.sum())}px")
    sm.set_session_setting("object_names", names)
    sm.save_session_settings()

    main_window._refresh_table()
    main_window._update_current_frame_display()
    made = ", ".join(str(i) for i in ids[:len(results)])
    print(f"[글자 찾기] {len(results)}개를 오브젝트 {made}번으로 만들었습니다. "
          "이제 '전체 트래킹'이나 '원클릭 누끼'를 누르세요.")
    try:
        main_window.sidebar.segmentation_tab._update_name_display(
            main_window.sidebar.segmentation_tab.get_selected_object_id())
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 외곽 그려서 지정: 다각형/자유곡선으로 대략 그리면 SAM 2가 다듬고 따라간다
# ---------------------------------------------------------------------------

from PySide6.QtCore import QEvent, QObject, QPointF
from PySide6.QtGui import QColor, QPainterPath, QPen, QBrush


class OutlineGroup(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("외곽 그려서 지정", parent)
        layout = QVBoxLayout(self)
        self.draw_btn = QPushButton("외곽 그리기 시작")
        self.draw_btn.setCheckable(True)
        self.draw_btn.setToolTip(
            "선택한 오브젝트 번호로, 현재 프레임에서 대상의 외곽을 대략 그립니다.\n"
            "그린 모양을 시작 마스크로 SAM 2가 외곽을 다듬고, 트래킹하면 영상 전체를 따라갑니다.\n"
            "카메라가 크게 움직이면 처음·중간·끝 프레임에 한 번씩 그려 주면 더 정확합니다.")
        layout.addWidget(self.draw_btn)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["그린 영역 안에서 SAM이 외곽 다듬기", "그린 모양 그대로"])
        self.mode_combo.setToolTip(
            "다듬기: 대략 그린 영역 안에서 SAM 2가 실제 경계를 찾아 붙입니다. 그린 선 밖은 잘라냅니다.\n"
            "그대로: 그린 다각형을 그대로 시작 마스크로 씁니다. 경계가 애매해서 SAM이 엉뚱하게 잡을 때 쓰세요.")
        layout.addWidget(self.mode_combo)
        help_lbl = QLabel(
            "좌클릭: 꼭짓점 추가 · 누른 채 끌기: 자유곡선\n"
            "우클릭/Backspace: 되돌리기 · 더블클릭/Enter/첫 점 클릭: 완료\n"
            "Esc: 취소 · 휠/가운데 버튼: 확대·이동")
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("QLabel { color: palette(mid); font-size: 11px; }")
        layout.addWidget(help_lbl)


class OutlineDrawer(QObject):
    """ImageViewer 위에 다각형을 그리는 도구. 뷰어 코드를 고치지 않고 이벤트 필터로 동작한다."""

    def __init__(self, viewer, on_finish, on_cancel):
        super().__init__(viewer)
        self.viewer = viewer
        self.on_finish = on_finish
        self.on_cancel = on_cancel
        self.active = False
        self.pts = []
        self.cursor_pt = None
        self.dragging = False
        self.item = None
        self.dots = None
        viewer.viewport().installEventFilter(self)
        viewer.installEventFilter(self)

    # -- 상태 ---------------------------------------------------------------
    def start(self):
        self.active = True
        self.pts = []
        self.cursor_pt = None
        scene = self.viewer.graphics_scene
        if self.item is None:
            self.item = scene.addPath(QPainterPath())
            self.item.setZValue(1000)
            self.dots = scene.addPath(QPainterPath())
            self.dots.setZValue(1001)
        pen = QPen(QColor(255, 220, 0), 2)
        pen.setCosmetic(True)
        self.item.setPen(pen)
        self.dots.setPen(QPen(Qt.NoPen))
        self.dots.setBrush(QBrush(QColor(255, 220, 0)))
        self.item.setVisible(True)
        self.dots.setVisible(True)
        self.viewer.viewport().setCursor(Qt.CrossCursor)
        self.viewer.setFocus()
        self._redraw()

    def stop(self):
        self.active = False
        self.dragging = False
        self.pts = []
        if self.item is not None:
            self.item.setVisible(False)
            self.dots.setVisible(False)
        self.viewer.viewport().setCursor(Qt.ArrowCursor)

    def _finish(self):
        pts = list(self.pts)
        self.stop()
        if len(pts) >= 3:
            self.on_finish(pts)
        else:
            self.on_cancel()

    def _cancel(self):
        self.stop()
        self.on_cancel()

    # -- 좌표 ---------------------------------------------------------------
    def _scene_pt(self, pos):
        p = self.viewer.mapToScene(pos.toPoint())
        pm = self.viewer.original_pixmap
        x, y = p.x(), p.y()
        if pm is not None:
            x = min(max(x, 0), pm.width() - 1)
            y = min(max(y, 0), pm.height() - 1)
        return QPointF(x, y)

    def _scale(self):
        return max(1e-3, float(getattr(self.viewer, "current_scale", 1.0) or 1.0))

    def _near_first(self, p):
        if len(self.pts) < 3:
            return False
        q = self.pts[0]
        return ((p.x() - q.x()) ** 2 + (p.y() - q.y()) ** 2) ** 0.5 * self._scale() < 10

    def _redraw(self):
        path = QPainterPath()
        if self.pts:
            path.moveTo(self.pts[0])
            for p in self.pts[1:]:
                path.lineTo(p)
            if self.cursor_pt is not None:
                path.lineTo(self.cursor_pt)
                if len(self.pts) >= 2:
                    path.lineTo(self.pts[0])
        self.item.setPath(path)
        dots = QPainterPath()
        r = 3.5 / self._scale()
        for i, p in enumerate(self.pts):
            rr = r * (1.8 if i == 0 else 1.0)
            dots.addEllipse(p, rr, rr)
        self.dots.setPath(dots)

    # -- 이벤트 -------------------------------------------------------------
    def eventFilter(self, obj, ev):
        if not self.active:
            return False
        t = ev.type()
        if obj is self.viewer.viewport():
            if t == QEvent.MouseButtonPress:
                if ev.button() == Qt.LeftButton:
                    p = self._scene_pt(ev.position())
                    if self._near_first(p):
                        self._finish()
                        return True
                    self.pts.append(p)
                    self.dragging = True
                    self._redraw()
                    return True
                if ev.button() == Qt.RightButton:
                    if self.pts:
                        self.pts.pop()
                        self._redraw()
                    return True
                return False  # 가운데 버튼 이동은 원래대로
            if t == QEvent.MouseButtonDblClick and ev.button() == Qt.LeftButton:
                self._finish()
                return True
            if t == QEvent.MouseButtonRelease and ev.button() == Qt.LeftButton:
                self.dragging = False
                return True
            if t == QEvent.MouseMove:
                p = self._scene_pt(ev.position())
                self.cursor_pt = p
                if self.dragging and (ev.buttons() & Qt.LeftButton) and self.pts:
                    q = self.pts[-1]
                    if ((p.x() - q.x()) ** 2 + (p.y() - q.y()) ** 2) ** 0.5 * self._scale() > 6:
                        self.pts.append(p)
                self._redraw()
                return False  # 좌표 표시·이동은 원래대로
            return False
        if obj is self.viewer and t == QEvent.KeyPress:
            k = ev.key()
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self._finish(); return True
            if k == Qt.Key_Escape:
                self._cancel(); return True
            if k == Qt.Key_Backspace:
                if self.pts:
                    self.pts.pop(); self._redraw()
                return True
            if k in (Qt.Key_Shift, Qt.Key_Control):
                return True  # 그리는 중에는 점 미리보기 끔
        return False


def start_outline(main_window):
    from sammie.gui_widgets import show_message_dialog
    grp = main_window.sidebar.segmentation_tab.outline_group
    if core.VideoInfo.total_frames == 0:
        grp.draw_btn.setChecked(False)
        show_message_dialog(main_window, title="외곽 그려서 지정", message="먼저 영상을 불러와 주세요.", type="warning")
        return
    if not hasattr(main_window, "_outline_drawer"):
        main_window._outline_drawer = OutlineDrawer(
            main_window.viewer,
            on_finish=lambda pts: apply_outline(main_window, pts),
            on_cancel=lambda: _outline_done(main_window, None))
    oid = main_window.sidebar.segmentation_tab.get_selected_object_id()
    grp.draw_btn.setText(f"그리는 중... (오브젝트 {oid}) — Esc로 취소")
    main_window._outline_drawer.start()
    print(f"[외곽 그리기] 오브젝트 {oid}, 프레임 {main_window.frame_slider.value()} — 대상 외곽을 따라 클릭하세요.")


def stop_outline(main_window):
    d = getattr(main_window, "_outline_drawer", None)
    if d is not None and d.active:
        d.stop()
    _outline_done(main_window, None)


def _outline_done(main_window, msg):
    grp = main_window.sidebar.segmentation_tab.outline_group
    grp.draw_btn.blockSignals(True)
    grp.draw_btn.setChecked(False)
    grp.draw_btn.blockSignals(False)
    grp.draw_btn.setText("외곽 그리기 시작")
    if msg:
        print(msg)


def apply_outline(main_window, pts):
    import cv2
    import numpy as np
    from sammie import text_finder
    from sammie.settings_manager import get_settings_manager

    frame = main_window.frame_slider.value()
    oid = main_window.sidebar.segmentation_tab.get_selected_object_id()
    h, w = core.VideoInfo.height, core.VideoInfo.width
    poly = np.array([[int(round(p.x())), int(round(p.y()))] for p in pts], np.int32)
    mask = np.zeros((h, w), np.uint8)
    cv2.fillPoly(mask, [poly], 1)
    mask = mask.astype(bool)
    if mask.sum() < 50:
        _outline_done(main_window, "[외곽 그리기] 그린 영역이 너무 작아서 취소했습니다.")
        return

    # 이 오브젝트가 이 프레임에 갖고 있던 점은 외곽으로 대체
    pm = main_window.point_manager
    before = len(pm.points)
    pm.points = [p for p in pm.points if not (p['frame'] == frame and p['object_id'] == oid)]
    removed = before - len(pm.points)
    get_settings_manager().save_points(pm.points)

    x, y = text_finder.anchor_point(mask)
    refined_note = ""
    if main_window.sidebar.segmentation_tab.outline_group.mode_combo.currentIndex() == 0:
        refined = main_window.sam_manager.refine_in_region(frame, oid, mask, (x, y))
        if refined is not None:
            mask = refined
            x, y = text_finder.anchor_point(mask)
            refined_note = " SAM이 외곽을 다듬었습니다."
    pm.add_point(frame, oid, True, x, y)
    main_window.sam_manager.add_text_object(frame, oid, mask, (x, y), label="외곽")

    sm = get_settings_manager()
    names = dict(sm.get_session_setting("object_names", {}) or {})
    if str(oid) not in names:
        names[str(oid)] = f"외곽 {oid}"
        sm.set_session_setting("object_names", names)
    sm.save_session_settings()

    main_window._refresh_table()
    main_window._update_current_frame_display()
    note = f" (이 프레임에 있던 점 {removed}개는 외곽으로 바꿨습니다)" if removed else ""
    _outline_done(main_window,
                  f"[외곽 그리기] 오브젝트 {oid}, 프레임 {frame}에 외곽을 지정했습니다{note}.{refined_note} "
                  "다른 프레임에도 그리거나 '전체 트래킹'을 누르세요.")
