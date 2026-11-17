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
    QCheckBox, QPushButton, QSlider, QVBoxLayout,
)

from sammie import core
from sammie import temporal_stabilize as ts
from sammie.settings_manager import get_settings_manager

MASK_STAB_BACKUP = os.path.join(core.temp_dir, "masks_stab_backup")
MATTE_STAB_BACKUP = os.path.join(core.temp_dir, "matting_stab_backup")

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
    attr = "mask_dir" if kind == "mask" else "matting_dir"
    _compare_saved[kind] = getattr(core, attr)
    setattr(core, attr, backup)
    main_window._update_current_frame_display()


def compare_release(main_window, kind):
    if kind in _compare_saved:
        setattr(core, "mask_dir" if kind == "mask" else "matting_dir", _compare_saved.pop(kind))
        main_window._update_current_frame_display()


def _group_for(main_window, kind):
    try:
        tab = main_window.sidebar.segmentation_tab if kind == "mask" else main_window.sidebar.matting_tab
        return tab.stab_group
    except Exception:
        return None


def make_one_click_button():
    btn = QPushButton("원클릭 누끼\n트래킹 → 매팅 → 안정화 → 내보내기")
    btn.setToolTip(
        "점을 찍은 뒤 이 버튼 하나로 끝까지 진행합니다.\n"
        "1) 전체 트래킹  2) 마스크 외곽 안정화  3) 매팅(머리카락 등 반투명 외곽)\n"
        "4) 매트 외곽 안정화  5) 내보내기 창 열기\n"
        "매팅 모델은 GPU 메모리 12GB 이상이면 VideoMaMa, 아니면 MatAnyone2를 자동 선택합니다.")
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


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------

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
    if not sm.get_session_setting(flag, False) or not os.path.exists(backup):
        ts.make_backup(target, backup)
        sm.set_session_setting(flag, True)

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
    result = ts.stabilize_folder(
        backup, target, core.load_base_frame, start, end,
        strength=strength, radius=radius, band_px=band_px, soft=soft,
        progress_fn=on_progress, cancel_fn=progress.wasCanceled, stats=stats)
    progress.close()

    if result < 0:
        # 취소 → 반쯤 처리된 상태를 남기지 않도록 원본 복원
        ts.restore_backup(target, backup)
        print("외곽 안정화 취소됨 (원본 유지)")
        main_window._update_current_frame_display()
        return False

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


def _vram_gb():
    try:
        import torch
        dev = core.DeviceManager.get_device()
        if dev.type == "cuda":
            return torch.cuda.get_device_properties(dev).total_memory / (1024 ** 3)
    except Exception:
        pass
    return 0.0


def _pick_matting_model():
    return "VideoMaMa" if _vram_gb() >= 11.5 else "MatAnyone2"


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

    # 1) 트래킹
    print("[원클릭 1/5] 트래킹")
    main_window.track_objects()
    if not _has_output(core.mask_dir, start, end):
        print("원클릭 중단: 트래킹이 끝나지 않았습니다.")
        return

    # 2) 마스크 안정화
    print("[원클릭 2/5] 마스크 외곽 안정화")
    if not run_stabilize(main_window, "mask", quiet=True):
        print("원클릭 중단: 마스크 안정화 취소")
        return

    # 3) 매팅
    model = _pick_matting_model()
    print(f"[원클릭 3/5] 매팅 ({model})")
    sm = get_settings_manager()
    sm.set_session_setting("matany_model", model)
    mt = main_window.sidebar.matting_tab
    if mt is not None:
        mt.matany_model_combo.setCurrentText(model)
    # 머리카락 디테일: GPU 여유가 있으면 내부 해상도를 1080 이상으로
    res = sm.get_session_setting("matany_res", 1080)
    if _vram_gb() >= 8 and isinstance(res, int) and 0 < res < 1080:
        sm.set_session_setting("matany_res", 1080)
        if mt is not None:
            mt.matany_res_combo.setCurrentText("1080")
    main_window.run_matting()
    if not _has_output(core.matting_dir, start, end):
        print("원클릭 중단: 매팅이 끝나지 않았습니다.")
        return

    # 4) 매트 안정화
    print("[원클릭 4/5] 매트 외곽 안정화")
    if not run_stabilize(main_window, "matte", quiet=True):
        print("원클릭 중단: 매트 안정화 취소")
        return

    # 5) 매팅 탭 + 알파 보기 → 내보내기
    print("[원클릭 5/5] 내보내기")
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
