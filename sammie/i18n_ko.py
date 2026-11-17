"""
한국어 UI — Sammie-Roto PAN 빌드

원본 코드의 영어 문자열은 그대로 두고, 화면에 뜨는 위젯 텍스트만 실행 중에 한국어로 바꾼다.
(콤보박스 항목은 프로그램 내부 값으로 쓰이므로 번역하지 않는다.)
원본 업데이트를 합칠 때 충돌이 적도록 이 파일 하나에 모았다.
"""

from PySide6.QtCore import QObject, QEvent, QTimer
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QGroupBox, QLabel, QLineEdit, QMenu, QMenuBar,
    QMessageBox, QProgressDialog, QTabWidget, QTableWidget, QWidget,
)

KO = {
    # ── 탭 / 메뉴 ─────────────────────────────────────────
    "Segmentation": "세그멘테이션",
    "Matting": "매팅",
    "Object Removal": "오브젝트 제거",
    "File": "파일",
    "View": "보기",
    "Help": "도움말",
    "Load Video": "영상 불러오기",
    "Load Points": "포인트 불러오기",
    "Load Project": "프로젝트 불러오기",
    "Save Points": "포인트 저장",
    "Save Project": "프로젝트 저장",
    "Export Image": "이미지 내보내기",
    "Export Video": "영상 내보내기",
    "Settings": "설정",
    "Exit": "종료",
    "Fit to Screen": "화면에 맞추기",
    "100% Zoom": "100% 확대",
    "200% Zoom": "200% 확대",
    "400% Zoom": "400% 확대",
    "Reset Interface": "화면 배치 초기화",
    "Shortcut Keys": "단축키",
    "Open Sammie-Roto Folder": "Sammie-Roto 폴더 열기",
    "Changelog": "변경 내역",
    "About": "정보",
    "About Sammie-Roto": "Sammie-Roto 정보",

    # ── 세그멘테이션 탭 ───────────────────────────────────
    "Add Point": "포인트 추가",
    "Object:": "오브젝트:",
    "Name:": "이름:",
    "Select which object ID to assign to new points. Each object gets a unique color.":
        "새 포인트를 어느 오브젝트 번호에 넣을지 고릅니다. 오브젝트마다 색이 다릅니다.",
    "Enter object name...": "오브젝트 이름 입력...",
    "Optional: Give this object a name for easier identification": "선택 사항: 구분하기 쉽게 이름을 붙입니다",
    "Left-click: Add positive point\nCtrl+Left-click: Add negative point\nRight-click: Add negative point\nHold Shift: Live Preview":
        "좌클릭: 포함 포인트 추가\nCtrl+좌클릭: 제외 포인트 추가\n우클릭: 제외 포인트 추가\nShift 누르고 있기: 실시간 미리보기",
    "Model Selection": "모델 선택",
    "Large model is slower but slightly more accurate.\nEfficient model is faster but less accurate.":
        "Large는 느리지만 조금 더 정확합니다.\nEfficient는 빠르지만 정확도가 낮습니다.\nAnime은 애니메이션용입니다.",
    "Load Model": "모델 불러오기",
    "Clear Points": "포인트 지우기",
    "Remove Last Point": "마지막 포인트 삭제",
    "Remove the most recently added point": "가장 최근에 찍은 포인트를 지웁니다",
    "Clear Frame": "현재 프레임 지우기",
    "Remove all points from the current frame": "현재 프레임의 포인트를 모두 지웁니다",
    "Clear Object": "현재 오브젝트 지우기",
    "Remove all points for the currently selected object": "선택한 오브젝트의 포인트를 모두 지웁니다",
    "Clear All": "전체 지우기",
    "Remove all points from all frames and objects": "모든 프레임·오브젝트의 포인트를 지웁니다",
    "Tracking": "트래킹",
    "Track Objects": "전체 트래킹",
    "Propagate segmentation masks to all frames using the added points as guidance":
        "찍은 포인트를 기준으로 마스크를 모든 프레임에 퍼뜨립니다",
    "Track one frame backward from the current frame": "현재 프레임에서 한 프레임 뒤로 트래킹",
    "Track backward from the current frame to the in point (or start of video)":
        "현재 프레임에서 In 지점(또는 영상 시작)까지 뒤로 트래킹",
    "Track forward from the current frame to the out point (or end of video)":
        "현재 프레임에서 Out 지점(또는 영상 끝)까지 앞으로 트래킹",
    "Track one frame forward from the current frame": "현재 프레임에서 한 프레임 앞으로 트래킹",
    "Clear Tracking Data": "트래킹 결과 지우기",
    "Remove all propagated masks but keep the point annotations": "퍼뜨린 마스크만 지우고 포인트는 남깁니다",
    "Deduplicate Similar Masks": "비슷한 마스크 중복 제거",
    "Reduce edge chatter in animated content by repeating masks on duplicated frames (requires tracking first)":
        "애니메이션처럼 같은 그림이 반복되는 프레임에 같은 마스크를 써서 외곽 떨림을 줄입니다 (트래킹 먼저)",
    "Postprocessing": "후처리",
    "Remove Holes:": "구멍 메우기:",
    "Remove small holes inside segmented objects.": "오브젝트 안쪽의 작은 구멍을 메웁니다.",
    "Remove Dots:": "점 제거:",
    "Remove small isolated regions outside main objects.": "오브젝트 바깥의 작은 조각을 지웁니다.",
    "Border Fix:": "화면 가장자리 보정:",
    "Fix artifacts at the edge of the frame by extending masks towards the edge.":
        "마스크를 화면 끝까지 늘려서 가장자리 깨짐을 보정합니다.",
    "Shrink/Grow:": "줄이기/늘리기:",
    "Shrink (erode) or grow (dilate) the segmented regions.": "마스크 영역을 줄이거나(침식) 늘립니다(팽창).",

    # ── 매팅 탭 ──────────────────────────────────────────
    "Run Matting": "매팅 실행",
    "Clear Matting": "매팅 결과 지우기",
    "Remove all matting data": "매팅 결과를 모두 지웁니다",
    "Processing Settings": "처리 설정",
    "Model:": "모델:",
    "VideoMaMa is higher quality but slower and uses more VRAM.":
        "VideoMaMa가 품질이 가장 좋지만 느리고 VRAM을 많이 씁니다.",
    "Internal Resolution:": "내부 해상도:",
    "If your video's shortest side is larger than this, it will be\ndownsampled to this size before running matting.\nThis reduces VRAM requirements and increases processing speed.":
        "영상의 짧은 변이 이 값보다 크면 이 크기로 줄여서 매팅합니다.\nVRAM 사용량이 줄고 속도가 빨라집니다.\n머리카락 디테일이 중요하면 높게(1080 이상) 잡으세요.",
    "Crossfade overlap frames:": "배치 겹침 프레임:",
    "Number of overlapping frames between batches.\nHigher values can look smoother on slow or poorly defined subjects.":
        "배치 사이에 겹치는 프레임 수입니다.\n높을수록 배치 경계가 부드럽습니다.",
    "Frames per batch:": "배치당 프레임:",
    "The number of frames that will be processed at once.\nHigher values require more VRAM.":
        "한 번에 처리할 프레임 수입니다.\n높을수록 VRAM을 많이 씁니다.",
    "Combine All Objects": "모든 오브젝트 합치기",
    "If checked, all objects will be merged and processed as a single object.":
        "체크하면 모든 오브젝트를 하나로 합쳐서 처리합니다.",
    "Instructions": "사용법",
    "Gamma:": "감마:",
    "Values < 1.0 darken edges, values > 1.0 brighten edges.": "1.0보다 작으면 외곽이 어두워지고, 크면 밝아집니다.",
    "Shrink (erode) or grow (dilate) the matted regions.": "매트 영역을 줄이거나 늘립니다.",
    "• Matting can be used to create mattes for objects with soft or poorly defined edges.<br> • <b>Add points to at least one frame in the Segmentation tab</b>, then press Run Matting.<br> • The MatAnyone models are faster and require less VRAM than VideoMama, but may be less accurate.<br> • If you add points to multiple frames, matting will refresh at each keyframe, which may momentarily affect temporal stability.<br> • MatAnyone is free for non-commercial use, requires <a href=\"https://github.com/pq-yang/MatAnyone?tab=License-1-ov-file\">permission for commercial use</a>.<br>":
        "• 매팅은 머리카락처럼 외곽이 부드럽거나 애매한 대상의 매트를 만듭니다.<br>"
        "• <b>세그멘테이션 탭에서 최소 한 프레임에 포인트를 찍은 뒤</b> 매팅 실행을 누르세요.<br>"
        "• MatAnyone 계열은 VideoMaMa보다 빠르고 VRAM을 적게 쓰지만 정확도가 조금 낮을 수 있습니다.<br>"
        "• 여러 프레임에 포인트를 찍으면 키프레임마다 매팅이 새로 잡혀서 순간적으로 흔들릴 수 있습니다.<br>"
        "• 매팅 후 아래 <b>매트 외곽 안정화</b>를 돌리면 외곽 떨림이 줄어듭니다.<br>"
        "• MatAnyone은 비상업 용도 무료, <a href=\"https://github.com/pq-yang/MatAnyone?tab=License-1-ov-file\">상업 용도는 허가 필요</a>.<br>",
    "• Matting can be used to create mattes for objects with soft or poorly defined edges.<br> • <b>Add points and run tracking in the Segmentation tab</b> so that a mask is available on every frame, then press Run Matting.<br> • VideoMaMa processes the video frames in batches. There may be temporal instability at batch boundaries.<br> • VideoMaMa is free for non-commercial use and <a href=\"https://huggingface.co/stabilityai/stable-video-diffusion-img2vid/blob/main/LICENSE.md\">limited commercial use</a>.<br>":
        "• 매팅은 머리카락처럼 외곽이 부드럽거나 애매한 대상의 매트를 만듭니다.<br>"
        "• <b>세그멘테이션 탭에서 포인트를 찍고 전체 트래킹</b>까지 해서 모든 프레임에 마스크가 있어야 합니다. 그다음 매팅 실행.<br>"
        "• VideoMaMa는 프레임을 배치로 나눠 처리해서 배치 경계에서 살짝 흔들릴 수 있습니다 → 매트 외곽 안정화로 보정하세요.<br>"
        "• VideoMaMa는 비상업 용도 무료, <a href=\"https://huggingface.co/stabilityai/stable-video-diffusion-img2vid/blob/main/LICENSE.md\">상업 용도는 제한적 허용</a>.<br>",

    # ── 오브젝트 제거 탭 ─────────────────────────────────
    "Run Object Removal": "오브젝트 제거 실행",
    "Clear Object Removal": "오브젝트 제거 결과 지우기",
    "Remove all object removal data": "오브젝트 제거 결과를 모두 지웁니다",
    "Method": "방식",
    "Method:": "방식:",
    "MiniMax-Remover: Good quality but can only process a few seconds of video.<br>ProPainterX: Worse quality but handles longer clips more efficiently.":
        "MiniMax-Remover: 품질이 좋지만 몇 초 분량만 처리할 수 있습니다.<br>ProPainterX: 품질은 낮지만 긴 클립을 효율적으로 처리합니다.",
    "Mask Adjustment": "마스크 조정",
    "Shrink (erode) or grow (dilate) the mask before inpainting. This is additive to the same setting on the Segmentation tab.":
        "지우기 전에 마스크를 줄이거나 늘립니다. 세그멘테이션 탭의 같은 설정에 더해집니다.",
    "Parameters": "파라미터",
    "Internal processing resolution. Higher values produce better quality but are slower and use more VRAM.":
        "내부 처리 해상도입니다. 높을수록 품질이 좋지만 느리고 VRAM을 많이 씁니다.",
    "If you get an out of memory error during the VAE decode step, try enabling this option. The VAE steps will take longer but use less VRAM.":
        "VAE 디코딩 중 메모리 부족 오류가 나면 켜세요. 느려지지만 VRAM을 덜 씁니다.",
    "Use VAE Tiling:": "VAE 타일링:",
    "Steps:": "스텝:",
    "Number of diffusion steps. Larger values are better quality but slower.": "디퓨전 스텝 수입니다. 높을수록 품질이 좋지만 느립니다.",
    "• Object removal uses inpainting to fill in areas where objects have been removed.<br> • You first need to <b>run tracking in the Segmentation tab</b>, so a mask is on every frame.<br> • MiniMax-Remover gives good quality, but VRAM use grows with the number of frames in the video. Keep clips to a few seconds.<br> • MiniMax-Remover is licensed under <a href=\"https://spdx.org/licenses/CC-BY-NC-4.0\">CC-BY-NC-4.0</a>.<br>":
        "• 오브젝트 제거는 지운 자리를 인페인팅으로 채웁니다.<br>"
        "• 먼저 <b>세그멘테이션 탭에서 전체 트래킹</b>을 해서 모든 프레임에 마스크가 있어야 합니다.<br>"
        "• MiniMax-Remover는 품질이 좋지만 프레임 수만큼 VRAM이 늘어납니다. 몇 초 분량으로 끊어서 쓰세요.<br>"
        "• MiniMax-Remover 라이선스: <a href=\"https://spdx.org/licenses/CC-BY-NC-4.0\">CC-BY-NC-4.0</a> (비상업).<br>",
    "• Object removal uses inpainting to fill in areas where objects have been removed.<br> • You first need to <b>run tracking in the Segmentation tab</b>, so a mask is on every frame.<br> • ProPainterX handles longer clips more efficiently than MiniMax-Remover, but quality is usually worse.<br> • ProPainterX works best on objects that are in motion, and may produce artifacts on static objects.<br> • ProPainterX is free for non-commercial use, requires <a href=\"https://github.com/sczhou/ProPainter?tab=License-1-ov-file\">permission for commercial use</a>.<br>":
        "• 오브젝트 제거는 지운 자리를 인페인팅으로 채웁니다.<br>"
        "• 먼저 <b>세그멘테이션 탭에서 전체 트래킹</b>을 해서 모든 프레임에 마스크가 있어야 합니다.<br>"
        "• ProPainterX는 긴 클립을 효율적으로 처리하지만 보통 품질은 MiniMax-Remover보다 낮습니다.<br>"
        "• 움직이는 대상에 잘 맞고, 정지한 대상에는 깨짐이 생길 수 있습니다.<br>"
        "• ProPainterX는 비상업 용도 무료, <a href=\"https://github.com/sczhou/ProPainter?tab=License-1-ov-file\">상업 용도는 허가 필요</a>.<br>",

    # ── 하단 / 재생 / 보기 ────────────────────────────────
    "Frame:": "프레임:",
    "View:": "보기:",
    "Previous Keyframe": "이전 키프레임",
    "Previous Frame": "이전 프레임",
    "Next Frame": "다음 프레임",
    "Next Keyframe": "다음 키프레임",
    "Play/Pause": "재생/일시정지",
    "Show masks": "마스크 표시",
    "Show outlines": "외곽선 표시",
    "Show mask outline": "마스크 외곽선 표시",
    "Antialias": "안티앨리어싱",
    "Segmentation Point List": "포인트 목록",
    "Console": "콘솔",
    "Show All Frames": "전체 프레임 보기",
    "List All Frame Points": "전체 프레임 포인트 보기",
    "List Current Frame Points": "현재 프레임 포인트만 보기",
    "Toggle to show all points for all frames or just the points for the currently displayed frame":
        "전체 프레임의 포인트를 볼지, 현재 프레임 포인트만 볼지 전환합니다",
    "Click to choose background color": "클릭해서 배경색 선택",
    "Ready": "준비됨",
    "Frame": "프레임",
    "Object ID": "오브젝트",
    "Type": "종류",
    "Action": "동작",
    "Delete": "삭제",
    "Shortcut": "단축키",
    "Description": "설명",
    "Keyboard Shortcuts": "단축키",

    # ── 단축키 설명 ──────────────────────────────────────
    "Clear All Points": "포인트 전체 지우기",
    "Clear Frame Points": "현재 프레임 포인트 지우기",
    "Clear In/Out Markers": "In/Out 마커 지우기",
    "Clear Object Points": "현재 오브젝트 포인트 지우기",
    "Deduplicate Masks": "마스크 중복 제거",
    "Delete Selected Point": "선택한 포인트 삭제",
    "Go to First Frame": "첫 프레임으로",
    "Go to Last Frame": "마지막 프레임으로",
    "Matting BGcolor View": "매팅 배경색 보기",
    "Matting Matte View": "매팅 매트 보기",
    "Object Removal Edit View": "오브젝트 제거 보기",
    "Segmentation BGcolor View": "세그멘테이션 배경색 보기",
    "Segmentation Edit View": "세그멘테이션 편집 보기",
    "Segmentation Matte View": "세그멘테이션 매트 보기",
    "Set In Marker": "In 마커 설정",
    "Set Out Marker": "Out 마커 설정",
    "Show Help": "도움말 보기",
    "Show Keyboard Shortcuts": "단축키 보기",
    "Zoom In": "확대",
    "Zoom Out": "축소",

    # ── 공통 대화상자 ────────────────────────────────────
    "Loading...": "불러오는 중...",
    "Please Wait": "잠시만 기다려 주세요",
    "Confirm Delete": "삭제 확인",
    "Error": "오류",
    "VideoMaMa is not supported on CPU. Please use MatAnyone instead.": "VideoMaMa는 CPU에서 쓸 수 없습니다. MatAnyone을 쓰세요.",
    "MiniMax-Remover is not supported on CPU. Please use ProPainterX instead.": "MiniMax-Remover는 CPU에서 쓸 수 없습니다. ProPainterX를 쓰세요.",
    "Unsupported File": "지원하지 않는 파일",
    "Export Error": "내보내기 오류",
    "No video data available. Please load a video first.": "영상이 없습니다. 먼저 영상을 불러오세요.",
    "Restart Required": "재시작 필요",
    "You must restart the application for device changes to take effect.": "장치 변경은 프로그램을 다시 켜야 적용됩니다.",
    "An out of memory error occurred. Please try again with lower settings.":
        "GPU 메모리가 부족합니다. 내부 해상도나 배치당 프레임을 낮춰서 다시 시도하세요.",
    "Deduplicating...": "중복 제거 중...",
    "Progress": "진행 상황",
    "Running matting...": "매팅 중...",
    "Matting Progress": "매팅 진행",
    "Tracking...": "트래킹 중...",
    "Loading video...": "영상 불러오는 중...",
    "Loading images...": "이미지 불러오는 중...",
    "Backing up files...": "파일 백업 중...",
    "Creating Backup": "백업 만드는 중",
    "Image Sequence Detected": "이미지 시퀀스 감지",
    "Would you like to load the entire sequence or just the single image?": "시퀀스 전체를 불러올까요, 이 이미지 한 장만 불러올까요?",
    "Extracting files...": "압축 푸는 중...",
    "Extracting Backup": "백업 푸는 중",
    "Extraction completed!": "압축 풀기 완료!",
    "Loading MiniMax-Remover model...": "MiniMax-Remover 모델 불러오는 중...",
    "Object Removal Progress": "오브젝트 제거 진행",
    "Saving frames...": "프레임 저장 중...",
    "Loading ProPainterX model...": "ProPainterX 모델 불러오는 중...",
    "Preparing ProPainterX...": "ProPainterX 준비 중...",
    "Preparing…": "준비 중…",
    "Overall progress:": "전체 진행:",
    "Cancelling…": "취소하는 중…",
    "Cancel": "취소",
    "Close": "닫기",
    "OK": "확인",
    "Yes": "예",
    "No": "아니요",

    # ── 내보내기 ─────────────────────────────────────────
    "Output": "출력",
    "Select output folder...": "출력 폴더 선택...",
    "Browse...": "찾아보기...",
    "Output Folder:": "출력 폴더:",
    "Use same folder as input file": "원본 영상과 같은 폴더에 저장",
    "Filename:": "파일 이름:",
    "Preview:": "미리보기:",
    "Format & Settings": "형식 및 설정",
    "Export Format:": "내보내기 형식:",
    "Output Type:": "출력 종류:",
    "Export Object:": "내보낼 오브젝트:",
    "Export separate file for each object": "오브젝트마다 파일 따로 내보내기",
    "Lower values = higher quality, larger file size": "값이 낮을수록 고화질, 파일이 커집니다",
    "Quality (CRF):": "화질 (CRF):",
    "Antialiasing": "안티앨리어싱",
    "Antialiasing:": "안티앨리어싱:",
    "Include original frame as layer": "원본 프레임을 레이어로 포함",
    "Export only between in/out markers": "In/Out 마커 구간만 내보내기",
    "Save Settings": "설정 저장",
    "Export": "내보내기",
    "Exporting": "내보내는 중",
    "Files Exist": "파일이 이미 있음",
    "Settings Saved": "설정 저장됨",
    "Export settings have been saved as defaults.": "내보내기 설정을 기본값으로 저장했습니다.",
    "Export Complete": "내보내기 완료",
    "Export Failed": "내보내기 실패",
    "Invalid Settings": "설정 오류",
    "When exporting separate files for each object, filename must include either {object_id} or {object_name} tag.":
        "오브젝트별로 따로 내보낼 때는 파일 이름에 {object_id} 또는 {object_name} 태그가 들어가야 합니다.",
    "Input file directory is not available. Please select an output folder manually.":
        "원본 영상 폴더를 찾을 수 없습니다. 출력 폴더를 직접 선택하세요.",
    "Please select an output folder.": "출력 폴더를 선택하세요.",
    "Create Folder?": "폴더를 만들까요?",
    "No objects found": "오브젝트가 없습니다",
    "Export Settings": "내보내기 설정",
    "Save As...": "다른 이름으로 저장...",

    # ── 설정 ─────────────────────────────────────────────
    "General": "일반",
    "Defaults": "기본값",
    "View Defaults": "보기 기본값",
    "Show Masks by Default:": "마스크 기본 표시:",
    "Show Outlines by Default:": "외곽선 기본 표시:",
    "Antialias by Default:": "안티앨리어싱 기본 사용:",
    "Default Background Color:": "기본 배경색:",
    "Segmentation Defaults": "세그멘테이션 기본값",
    "Default Remove Holes:": "구멍 메우기 기본값:",
    "Default Remove Dots:": "점 제거 기본값:",
    "Default Border Fix:": "가장자리 보정 기본값:",
    "Default Shrink/Grow:": "줄이기/늘리기 기본값:",
    "Matting Defaults": "매팅 기본값",
    "Default Gamma:": "감마 기본값:",
    "Object Removal Defaults": "오브젝트 제거 기본값",
    "Hardware Settings": "하드웨어 설정",
    "Force processing to use CPU instead of GPU. Only used for debugging purposes.": "GPU 대신 CPU로 처리합니다. 디버깅용입니다.",
    "Force CPU Processing (requires restart):": "CPU로 처리 (재시작 필요):",
    "Video frame extraction": "영상 프레임 추출",
    "PNG is lossless but requires more storage space and is slower than JPG": "PNG는 무손실이지만 용량이 크고 JPG보다 느립니다",
    "File Type:": "파일 형식:",
    "Display Settings": "화면 설정",
    "How often to update the display during tracking or matting.\nLower values are more responsive but slightly slower.":
        "트래킹·매팅 중 화면을 얼마나 자주 갱신할지 정합니다.\n낮을수록 반응이 빠르지만 조금 느려집니다.",
    "Display Update Frequency:": "화면 갱신 주기:",
    "Deduplication Threshold": "중복 제거 기준",
    "Value from 0 to 1 used as a threshold for how similar masks have to be before they're considered the same and deduped.\nHigher values are more strict.":
        "마스크가 얼마나 비슷해야 같은 것으로 보고 중복 제거할지 정하는 0~1 값입니다.\n높을수록 엄격합니다.",
    "Threshold:": "기준값:",

    # ── 시작 ─────────────────────────────────────────────
    "Loading Sammie-Roto...": "Sammie-Roto 불러오는 중...",
    "Sammie-Roto Startup Error": "Sammie-Roto 시작 오류",
    "Sammie-Roto encountered an error during startup and cannot continue.": "Sammie-Roto 시작 중 오류가 나서 계속할 수 없습니다.",
    "Already Running": "이미 실행 중",
    "Sammie-Roto is already running.\nOnly one instance can run at a time.": "Sammie-Roto가 이미 실행 중입니다.\n한 번에 하나만 실행할 수 있습니다.",
    "Permission Error": "권한 오류",
    "Sammie-Roto does not have write permission in its installation directory.": "Sammie-Roto 설치 폴더에 쓰기 권한이 없습니다.",
}


def _norm(s):
    return " ".join(s.split())


_KO_NORM = {_norm(k): v for k, v in KO.items()}
_KO_VALUES = set(KO.values())


def tr(text):
    """영어 → 한국어. 없으면 None. 앞뒤 공백(아이콘 여백용)은 유지."""
    if not text or text in _KO_VALUES:
        return None
    v = KO.get(text)
    if v is None:
        n = _norm(text)
        if not n:
            return None
        v = _KO_NORM.get(n)
        if v is None and n.endswith(":"):
            base = _KO_NORM.get(n[:-1].strip())
            v = base + ":" if base else None
        if v is None:
            return None
        lead = " " if text.startswith(" ") else ""
        trail = " " if text.endswith(" ") else ""
        v = lead + v + trail
    return v


def _tr_text(get, set_):
    try:
        t = get()
    except RuntimeError:
        return
    k = tr(t)
    if k is not None and k != t:
        set_(k)


def translate_widget(w):
    """위젯 하나(자식 제외) 번역"""
    try:
        tip = w.toolTip()
        if tip:
            k = tr(tip)
            if k:
                w.setToolTip(k)
        if w.isWindow():
            _tr_text(w.windowTitle, w.setWindowTitle)
        if isinstance(w, QAbstractButton) or isinstance(w, QLabel):
            _tr_text(w.text, w.setText)
        elif isinstance(w, QGroupBox):
            _tr_text(w.title, w.setTitle)
        elif isinstance(w, QLineEdit):
            _tr_text(w.placeholderText, w.setPlaceholderText)
        elif isinstance(w, QTabWidget):
            for i in range(w.count()):
                _tr_text(lambda i=i: w.tabText(i), lambda v, i=i: w.setTabText(i, v))
        elif isinstance(w, QTableWidget):
            for c in range(w.columnCount()):
                it = w.horizontalHeaderItem(c)
                if it is not None:
                    _tr_text(it.text, it.setText)
            # 단축키 표 설명 열
            if w.columnCount() == 2:
                for r in range(w.rowCount()):
                    it = w.item(r, 1)
                    if it is not None:
                        _tr_text(it.text, it.setText)
        elif isinstance(w, QMessageBox):
            _tr_text(w.text, w.setText)
            _tr_text(w.informativeText, w.setInformativeText)
        elif isinstance(w, QProgressDialog):
            _tr_text(w.labelText, w.setLabelText)
        if isinstance(w, (QMenu, QMenuBar)) or hasattr(w, "actions"):
            for a in w.actions():
                _tr_text(a.text, a.setText)
                if a.menu() is not None:
                    _tr_text(a.menu().title, a.menu().setTitle)
    except RuntimeError:
        pass  # 이미 삭제된 위젯


def translate_tree(root):
    try:
        translate_widget(root)
        children = root.findChildren(QWidget)
    except RuntimeError:
        return
    for w in children:
        translate_widget(w)


class _Translator(QObject):
    def eventFilter(self, obj, event):
        et = event.type()
        if et == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow():
            translate_tree(obj)
        elif et == QEvent.Show and isinstance(obj, QMenu):
            translate_widget(obj)
        return False


_translator = None
_timer = None


def install(app):
    """QApplication에 한국어 번역기를 설치한다."""
    global _translator, _timer
    _translator = _Translator()
    app.installEventFilter(_translator)

    # 실행 중 동적으로 바뀌는 문구(진행창·상태줄 등) 주기적 보정
    def _sweep():
        for w in QApplication.topLevelWidgets():
            try:
                if w.isVisible():
                    translate_tree(w)
            except RuntimeError:
                pass  # 닫히는 중인 창
    _timer = QTimer()
    _timer.timeout.connect(_sweep)
    _timer.start(700)
