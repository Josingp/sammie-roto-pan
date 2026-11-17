#!/bin/bash
# 사용: patch_tools/make_patch.sh <기준 커밋> [출력 폴더]
# 기준 커밋 이후 바뀐 파일만 담은 패치 zip을 만든다. (기준 = 사용자가 처음 설치한 버전)
set -e
BASE=${1:?기준 커밋을 주세요}
OUT=${2:-.}
ROOT=$(git rev-parse --show-toplevel); cd "$ROOT"
VER=$(grep '^__version__' sammie_main.py | cut -d'"' -f2)
WORK=$(mktemp -d); P="$WORK/Sammie-Roto-PAN-patch-$VER"
mkdir -p "$P/files"
git diff --name-only --diff-filter=AMR "$BASE" HEAD -- . ':!patch_tools' > "$WORK/files.txt"
git diff --name-only --diff-filter=D "$BASE" HEAD -- . ':!patch_tools' > "$WORK/deleted.txt"
while read -r f; do mkdir -p "$P/files/$(dirname "$f")"; git show "HEAD:$f" > "$P/files/$f"; done < "$WORK/files.txt"
cp patch_tools/pan_patch.py patch_tools/apply_patch.bat "$P/"
python3 - "$WORK" "$P" "$VER" "$BASE" <<'PY'
import json, sys
w, p, ver, base = sys.argv[1:]
files = [l for l in open(f"{w}/files.txt").read().split("\n") if l]
deleted = [l for l in open(f"{w}/deleted.txt").read().split("\n") if l]
json.dump({"version": ver, "base": base, "files": files, "deleted": deleted}, open(f"{p}/manifest.json", "w"), ensure_ascii=False, indent=1)
PY
OUT_ABS=$(cd "$OUT" && pwd)/$(basename "$P")
(cd "$WORK" && python3 -c "import shutil,sys; shutil.make_archive(sys.argv[1],'zip','.',sys.argv[2])" "$OUT_ABS" "$(basename "$P")")
echo "$OUT_ABS.zip"; cat "$P/manifest.json"
rm -rf "$WORK"
