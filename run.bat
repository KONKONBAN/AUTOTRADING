@echo off
REM Khởi chạy AutoTrading VN (Windows): bấm đúp run.bat  -> mở http://localhost:8000
cd /d "%~dp0"
if not exist .env copy .env.example .env
if not exist .venv python -m venv .venv
.venv\Scripts\pip install -q -r backend\requirements.txt
if not exist frontend\dist\index.html (
  pushd frontend
  call npm install --no-audit --no-fund
  call npm run build
  popd
)
echo AutoTrading VN dang chay tai http://localhost:8000  (Ctrl+C de dung)
.venv\Scripts\uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
