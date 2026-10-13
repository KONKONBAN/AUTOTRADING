#!/usr/bin/env bash
# Khởi chạy AutoTrading VN (macOS / Linux): ./run.sh  → tự mở trình duyệt
set -euo pipefail
cd "$(dirname "$0")"

PY=""
for c in python3.13 python3.12 python3.11 python3.14 python3.10 python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "[LỖI] Cần Python 3.10 trở lên. macOS: tải tại https://www.python.org/downloads/ (hoặc: brew install python@3.12)"
  exit 1
fi
"$PY" --version

if [ -x .venv/bin/python ] && ! .venv/bin/python -c 'import sys' 2>/dev/null; then rm -rf .venv; fi
if [ ! -x .venv/bin/python ]; then
  echo "[1/3] Tạo môi trường Python riêng (.venv)…"
  "$PY" -m venv .venv
fi
if ! cmp -s backend/requirements.txt .venv/requirements.installed; then
  echo "[2/3] Cài thư viện (lần đầu mất vài phút, cần Internet)…"
  .venv/bin/python -m pip install --disable-pip-version-check -q --upgrade pip
  .venv/bin/python -m pip install --disable-pip-version-check -r backend/requirements.txt
  cp backend/requirements.txt .venv/requirements.installed
fi
if [ ! -f frontend/dist/index.html ]; then
  echo "[LỖI] Thiếu giao diện frontend/dist - hãy tải lại mã nguồn đầy đủ."
  exit 1
fi
echo "[3/3] Khởi động máy chủ - trình duyệt sẽ tự mở…"
exec .venv/bin/python launcher.py
