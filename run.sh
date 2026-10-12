#!/usr/bin/env bash
# Khởi chạy AutoTrading VN (macOS / Linux): ./run.sh   → mở http://localhost:8000
set -e
cd "$(dirname "$0")"
[ -f .env ] || cp .env.example .env
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r backend/requirements.txt
if [ ! -f frontend/dist/index.html ]; then
  (cd frontend && npm install --no-audit --no-fund && npm run build)
fi
echo "▶ AutoTrading VN đang chạy tại http://localhost:${PORT:-8000}  (Ctrl+C để dừng)"
exec .venv/bin/uvicorn app.main:app --app-dir backend --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
