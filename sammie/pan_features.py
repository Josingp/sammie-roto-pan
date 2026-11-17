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
    print("[원클릭 3/5] 매팅")
    sm = get_settings_manager()
    if not run_matting_auto(main_window):
        print("원클릭 중단: 매팅이 끝나지 않았습니다.")
        return
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
