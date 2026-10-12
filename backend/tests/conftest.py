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

import pytest  # noqa: E402

TEST_USER = ("tester", "matkhau-123", "Người kiểm thử")


@pytest.fixture(autouse=True, scope="session")
def _test_user():
    """Tài khoản kiểm thử + ngữ cảnh người dùng cho các test gọi trực tiếp broker/engine/agent."""
    from app import auth
    from app.context import set_current_user
    if auth.user_count() == 0:
        user = auth.setup_admin(*TEST_USER)
    else:
        user = next(u for u in auth.list_users() if u["username"] == TEST_USER[0])
    set_current_user(user["id"])
    yield user


def login(client, username: str = TEST_USER[0], password: str = TEST_USER[1]):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return client
