"""Tài khoản: đăng nhập, phân quyền, tách biệt dữ liệu giữa các tài khoản."""
import uuid

import pytest
from conftest import TEST_USER, login
from fastapi.testclient import TestClient

from app import auth
from app.context import as_user
from app.db import Database, get_db
from app.main import app

REMOTE = {"X-Forwarded-For": "113.161.1.2", "CF-Connecting-IP": "113.161.1.2"}


def _new_user(role: str = "user") -> tuple[dict, str]:
    pw = "matkhau-" + uuid.uuid4().hex[:6]
    return auth.create_user("u" + uuid.uuid4().hex[:8], pw, role=role), pw


@pytest.fixture()
def anon():
    auth._failures.clear()
    with TestClient(app) as c:
        yield c
    auth._failures.clear()


def _client(username: str, password: str) -> TestClient:
    c = TestClient(app)
    c.__enter__()
    login(c, username, password)
    return c


def test_api_requires_login(anon):
    r = anon.get("/api/portfolio")
    assert r.status_code == 401 and r.json()["code"] == "login_required"
    assert anon.get("/api/health").status_code == 200
    assert anon.get("/openapi.json").status_code == 401
    st = anon.get("/api/auth/status").json()
    assert st["user"] is None and st["setup_required"] is False


def test_setup_only_once(anon):
    r = anon.post("/api/auth/setup", json={"username": "khac", "password": "matkhau-999"})
    assert r.status_code == 400  # đã có quản trị viên


def test_login_logout_and_wrong_password(anon):
    assert anon.post("/api/auth/login", json={"username": TEST_USER[0], "password": "sai-mat-khau"}).status_code == 401
    assert anon.post("/api/auth/login", json={"username": "khong-ton-tai", "password": "x"}).status_code == 401
    login(anon)
    me = anon.get("/api/auth/status").json()["user"]
    assert me["username"] == TEST_USER[0] and me["role"] == "admin"
    assert anon.get("/api/portfolio").status_code == 200
    anon.post("/api/auth/logout")
    assert anon.get("/api/portfolio").status_code == 401


def test_bruteforce_lockout(anon):
    user, pw = _new_user()
    for _ in range(auth.MAX_FAILURES):
        anon.post("/api/auth/login", json={"username": user["username"], "password": "sai"}, headers=REMOTE)
    r = anon.post("/api/auth/login", json={"username": user["username"], "password": pw}, headers=REMOTE)
    assert r.status_code == 429


def test_data_isolation_between_accounts():
    a, pa = _new_user()
    b, pb = _new_user()
    ca, cb = _client(a["username"], pa), _client(b["username"], pb)
    try:
        ca.post("/api/portfolio/reset", json={"initial_cash": 300_000_000})
        cb.post("/api/portfolio/reset", json={"initial_cash": 700_000_000})
        assert ca.post("/api/orders", json={"ticker": "FPT", "side": "BUY", "quantity": 100}).status_code == 200
        pa_ = ca.get("/api/portfolio").json()
        pb_ = cb.get("/api/portfolio").json()
        assert len(pa_["positions"]) == 1 and pb_["positions"] == []
        assert pb_["cash"] == 700_000_000 and pa_["initial_cash"] == 300_000_000
        assert cb.get("/api/orders").json() == []
        # đề xuất của A: B không thấy, không duyệt được
        with as_user(a["id"]):
            from app.trading import engine
            pid = engine.create_proposal("HPG", "BUY", 100, None, "test")["proposal_id"]
        assert cb.get("/api/proposals").json() == []
        assert cb.post(f"/api/proposals/{pid}/approve").status_code == 400
        assert len(ca.get("/api/proposals").json()) == 1
        # cấu hình Auto-Trader riêng
        ca.put("/api/autotrader/config", json={"mode": "suggest", "max_positions": 3})
        assert cb.get("/api/autotrader/config").json()["mode"] == "off"
        assert ca.get("/api/autotrader/config").json()["max_positions"] == 3
        # hội thoại AI riêng; B không ghi đè được phiên của A dù biết mã phiên
        sa = ca.post("/api/agent/chat", data={"message": "FPT thế nào?"}).json()["session_id"]
        sb = cb.post("/api/agent/chat", data={"message": "Xin chào", "session_id": sa}).json()["session_id"]
        assert sb != sa
        assert [s["id"] for s in cb.get("/api/agent/sessions").json()] == [sb]
        assert cb.get(f"/api/agent/sessions/{sa}").json()["messages"] == []
        assert ca.get(f"/api/agent/sessions/{sa}").json()["messages"]
        cb.delete(f"/api/agent/sessions/{sa}")
        assert ca.get(f"/api/agent/sessions/{sa}").json()["messages"]
    finally:
        ca.__exit__(None, None, None)
        cb.__exit__(None, None, None)


def test_admin_only_endpoints_and_registration(anon):
    user, pw = _new_user()
    c = _client(user["username"], pw)
    try:
        assert c.get("/api/admin/users").status_code == 403
        assert c.put("/api/admin/settings", json={"allow_registration": True}).status_code == 403
        assert c.post("/api/remote/tunnel/start").status_code == 403
    finally:
        c.__exit__(None, None, None)
    # đăng ký mặc định TẮT
    body = {"username": "moi" + uuid.uuid4().hex[:6], "password": "matkhau-777", "display_name": "Mới"}
    assert anon.post("/api/auth/register", json=body).status_code == 403
    admin = _client(*TEST_USER[:2])
    try:
        assert admin.put("/api/admin/settings", json={"allow_registration": True}).json()["allow_registration"]
        assert anon.post("/api/auth/register", json=body).status_code == 200
        assert anon.get("/api/portfolio").status_code == 200  # đăng ký xong là đăng nhập luôn
        users = admin.get("/api/admin/users").json()["users"]
        new = next(u for u in users if u["username"] == body["username"])
        assert new["role"] == "user"
        # khóa tài khoản → phiên bị hủy ngay
        assert admin.patch(f"/api/admin/users/{new['id']}", json={"disabled": True}).status_code == 200
        assert anon.get("/api/portfolio").status_code == 401
        assert admin.delete(f"/api/admin/users/{new['id']}").status_code == 200
    finally:
        admin.put("/api/admin/settings", json={"allow_registration": False})
        admin.__exit__(None, None, None)


def test_cannot_remove_last_admin():
    me = next(u for u in auth.list_users() if u["username"] == TEST_USER[0])
    with pytest.raises(auth.AuthError):
        auth.update_user(me["id"], role="user")
    with pytest.raises(auth.AuthError):
        auth.update_user(me["id"], disabled=True, acting_user_id=me["id"])


def test_password_change_logs_out_other_devices():
    user, pw = _new_user()
    c1, c2 = _client(user["username"], pw), _client(user["username"], pw)
    try:
        assert len(c1.get("/api/auth/sessions").json()) == 2
        r = c1.post("/api/auth/password", json={"current_password": "sai", "new_password": "matkhau-moi-1"})
        assert r.status_code == 400
        r = c1.post("/api/auth/password", json={"current_password": pw, "new_password": "matkhau-moi-1"})
        assert r.status_code == 200
        assert c1.get("/api/portfolio").status_code == 200   # thiết bị đang dùng vẫn đăng nhập
        assert c2.get("/api/portfolio").status_code == 401   # thiết bị khác bị đăng xuất
    finally:
        c1.__exit__(None, None, None)
        c2.__exit__(None, None, None)


def test_weak_or_invalid_credentials_rejected():
    with pytest.raises(auth.AuthError):
        auth.create_user("ab", "matkhau-123")            # tên quá ngắn
    with pytest.raises(auth.AuthError):
        auth.create_user("Hợp lệ", "matkhau-123")        # có dấu / khoảng trắng
    with pytest.raises(auth.AuthError):
        auth.create_user("hople" + uuid.uuid4().hex[:4], "12345678")  # chỉ toàn số
    with pytest.raises(auth.AuthError):
        auth.create_user(TEST_USER[0].upper(), "matkhau-123")  # trùng (không phân biệt hoa thường)


def test_cross_origin_writes_rejected():
    c = _client(*TEST_USER[:2])
    try:
        r = c.post("/api/orders", json={"ticker": "FPT", "side": "BUY", "quantity": 100},
                   headers={"Origin": "https://evil.example.com"})
        assert r.status_code == 403
    finally:
        c.__exit__(None, None, None)


def test_no_wildcard_cors(anon):
    r = anon.options("/api/portfolio", headers={"Origin": "https://evil.example.com",
                                                "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_tunnel_needs_local_admin():
    c = _client(*TEST_USER[:2])
    try:
        assert c.post("/api/remote/tunnel/start", headers=REMOTE).status_code == 403
        info = c.get("/api/remote/info").json()
        assert "lan_urls" in info and info["tunnel"]["running"] is False
    finally:
        c.__exit__(None, None, None)


@pytest.mark.skipif(__import__("os").name == "nt", reason="dùng shell script giả lập cloudflared")
def test_tunnel_start_stop_with_fake_cloudflared(tmp_path, monkeypatch):
    from app import remote
    fake = tmp_path / "cloudflared"
    fake.write_text("#!/bin/sh\necho 'INF Requesting new quick Tunnel'\n"
                    "echo 'INF |  https://abc-def-ghi.trycloudflare.com  |'\nexec sleep 30\n")
    fake.chmod(0o755)
    monkeypatch.setattr(remote, "cloudflared_path", lambda: fake)
    import dataclasses

    from app import main as app_main
    monkeypatch.setattr(app_main, "settings", dataclasses.replace(app_main.settings, enable_tunnel=True))
    c = _client(*TEST_USER[:2])
    try:
        st = c.post("/api/remote/tunnel/start").json()
        assert st["running"] and st["url"] == "https://abc-def-ghi.trycloudflare.com"
    finally:
        assert c.post("/api/remote/tunnel/stop").json()["running"] is False
        c.__exit__(None, None, None)


def test_legacy_single_user_database_is_adopted(tmp_path):
    import sqlite3
    path = tmp_path / "old.sqlite3"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE kv(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL);
        CREATE TABLE equity_history(date TEXT PRIMARY KEY, equity REAL NOT NULL, cash REAL NOT NULL);
        CREATE TABLE lots(id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL, quantity INTEGER NOT NULL,
                          price REAL NOT NULL, buy_date TEXT NOT NULL, stop_loss REAL, take_profit REAL, highest REAL);
        INSERT INTO kv VALUES('paper_cash', '123456', 0);
        INSERT INTO equity_history VALUES('2026-10-01', 1, 1);
        INSERT INTO lots(ticker, quantity, price, buy_date) VALUES('FPT', 100, 1, '2026-10-01');
    """)
    con.commit()
    con.close()
    db = Database(path)
    db.adopt_legacy_data(42)
    assert db.query("SELECT user_id FROM lots") == [{"user_id": 42}]
    assert db.query("SELECT user_id FROM equity_history") == [{"user_id": 42}]
    assert db.get_user_kv(42, "paper_cash") == 123456 and db.get_kv("paper_cash") is None
    assert get_db() is not db
