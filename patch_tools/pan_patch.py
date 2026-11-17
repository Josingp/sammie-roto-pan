"""
Sammie-Roto PAN 패치 적용기

apply_patch.bat이 설치 폴더의 파이썬으로 실행한다.
  python pan_patch.py <설치 폴더> <패치 폴더>

1) 프로그램이 켜져 있으면 중단
2) 바뀔 파일을 설치 폴더\\patch_backup\\<날짜시간>\\ 에 백업
3) 새 파일 복사, 없어진 파일 삭제
4) 패키지 목록(uv.lock)이 바뀌었으면 패키지 다시 맞춤
5) 새로 필요한 모델이 있으면 받기 (인터넷이 없으면 안내만)
"""
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def app_running():
    tmp = os.environ.get("TEMP", os.environ.get("TMP", "/tmp")) if platform.system() == "Windows" else "/tmp"
    lock = os.path.join(tmp, "sammie-roto.lock")
    if not os.path.exists(lock):
        return False
    try:
        pid = int(open(lock).readline().strip())
    except Exception:
        return False
    if platform.system() == "Windows":
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
        return str(pid) in r.stdout
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def read_version(app):
    try:
        for line in open(os.path.join(app, "sammie_main.py"), encoding="utf-8"):
            if line.startswith("__version__"):
                return line.split("=", 1)[1].strip().strip('"\'')
    except Exception:
        pass
    return "알 수 없음"


def main():
    if len(sys.argv) < 3:
        print("사용법: pan_patch.py <설치 폴더> <패치 폴더>")
        return 1
    app = os.path.abspath(sys.argv[1])
    src = os.path.abspath(sys.argv[2])
    manifest = json.load(open(os.path.join(os.path.dirname(src), "manifest.json"), encoding="utf-8"))

    print("=" * 60)
    print(f" Sammie-Roto PAN 패치 {manifest['version']}")
    print("=" * 60)
    print(f"설치 폴더: {app}")
    print(f"현재 버전: {read_version(app)}")

    if not os.path.exists(os.path.join(app, "sammie_main.py")):
        print("\n[중단] Sammie-Roto PAN 설치 폴더가 아닙니다.")
        return 1
    if app_running():
        print("\n[중단] Sammie-Roto가 실행 중입니다. 프로그램을 종료한 뒤 다시 실행하세요.")
        return 1

    old_lock = os.path.join(app, "uv.lock")
    old_lock_md5 = md5(old_lock) if os.path.exists(old_lock) else None

    # 2) 백업 + 3) 복사
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = os.path.join(app, "patch_backup", stamp)
    changed = 0
    for rel in manifest["files"]:
        s = os.path.join(src, rel)
        d = os.path.join(app, rel)
        if os.path.exists(d):
            if md5(d) == md5(s):
                continue
            b = os.path.join(backup, rel)
            os.makedirs(os.path.dirname(b), exist_ok=True)
            shutil.copy2(d, b)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(s, d)
        changed += 1
        print(f"  갱신  {rel}")
    for rel in manifest.get("deleted", []):
        d = os.path.join(app, rel)
        if os.path.exists(d):
            b = os.path.join(backup, rel)
            os.makedirs(os.path.dirname(b), exist_ok=True)
            shutil.move(d, b)
            changed += 1
            print(f"  삭제  {rel}")
    print(f"\n파일 {changed}개를 바꿨습니다." + (f" 이전 파일은 patch_backup\\{stamp} 에 있습니다." if changed else " (이미 최신 상태)"))

    os.chdir(app)
    sys.path.insert(0, app)

    # 4) 패키지
    new_lock_md5 = md5(old_lock) if os.path.exists(old_lock) else None
    if old_lock_md5 != new_lock_md5:
        print("\n[패키지] 필요한 패키지가 바뀌어서 다시 맞춥니다 (인터넷 필요)...")
        # install.bat / run_sammie.bat과 같은 파이썬·캐시 위치를 써야 기존 설치를 그대로 쓴다
        if os.path.isdir(os.path.join(app, ".uv", "python")):
            os.environ["UV_PYTHON_INSTALL_DIR"] = os.path.join(app, ".uv", "python")
            os.environ["UV_CACHE_DIR"] = os.path.join(app, ".uv", "uv_cache")
        else:  # exFAT 등 링크를 못 쓰는 드라이브에 설치한 경우 (install.bat과 같은 규칙)
            la = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Sammie-Roto-2")
            os.environ["UV_PYTHON_INSTALL_DIR"] = os.path.join(la, "uv-python")
            os.environ["UV_CACHE_DIR"] = os.path.join(la, "uv-cache")
            os.environ["UV_LINK_MODE"] = "copy"
        try:
            import manage
            backend = manage.get_installed_backend() or manage.detect_backend()
            manage.sync_env(backend)
        except SystemExit:
            print("[경고] 패키지 설치에 실패했습니다. 인터넷 연결 후 install.bat → 1) 재설치/복구를 실행하세요.")
        except Exception as e:
            print(f"[경고] 패키지 설치 실패: {e}")

    # 5) 모델
    try:
        from sammie.model_downloader import MODEL_REGISTRY
        missing = [k for k, spec in MODEL_REGISTRY.items() if not spec.already_downloaded()]
    except Exception as e:
        missing = []
        print(f"[경고] 모델 목록 확인 실패: {e}")
    if missing:
        print(f"\n[모델] 새로 필요한 모델 {len(missing)}개를 받습니다: {', '.join(missing)}")
        r = subprocess.run([sys.executable, os.path.join("sammie", "model_downloader.py"), *missing])
        if r.returncode != 0:
            print("[안내] 모델을 받지 못했습니다. 인터넷이 될 때 install.bat → 2) 모델 다시 받기를 실행하세요.")
            print("       그 전까지는 해당 모델을 쓰는 기능만 안 됩니다.")

    print(f"\n패치 완료! 현재 버전: {read_version(app)}")
    print("Sammie-Roto PAN을 다시 실행하세요.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n[오류] 패치 중 문제가 생겼습니다: {e}")
        print("이 창 내용을 캡처해서 보내 주세요.")
        sys.exit(1)
