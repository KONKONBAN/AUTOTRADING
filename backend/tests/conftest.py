"""Cấu hình kiểm thử: dùng CSDL tạm và dữ liệu DEMO (không cần Internet / API key)."""
import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="autotrading-test-")
os.environ["DB_PATH"] = str(Path(_tmp) / "test.sqlite3")
os.environ["DATA_MODE"] = "demo"
os.environ["AUTOTRADER_SCHEDULER"] = "false"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
os.environ.pop("ANTHROPIC_PROFILE", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
