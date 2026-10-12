"""Bảo vệ truy cập từ xa: máy này dùng tự do, điện thoại/Internet phải có mật khẩu + đăng nhập."""
import pytest
from fastapi.testclient import TestClient

from app import security
from app.db import get_db
from app.main import app

REMOTE = {"X-Forwarded-For": "113.161.1.2", "CF-Connecting-IP": "113.161.1.2"}


@pytest.fixture()
def client():
    db = get_db()
    db.execute("DELETE FROM kv WHERE key IN ('auth_hash', 'auth_secret')")
    security._failures.clear()
    with TestClient(app) as c:
        yield c
    db.execute("DELETE FROM kv WHERE key IN ('auth_hash', 'auth_secret')")
    security._failures.clear()


def test_local_is_free_remote_blocked_without_password(client):
    assert client.get("/api/portfolio").status_code == 200
    r = client.get("/api/portfolio", headers=REMOTE)
    assert r.status_code == 403 and r.json()["code"] == "password_not_set"
    assert client.get("/api/health", headers=REMOTE).status_code == 200      # công khai
    assert client.get("/", headers=REMOTE).status_code in (200, 404)         # giao diện tĩnh
    assert client.get("/openapi.json", headers=REMOTE).status_code == 403


def test_dns_rebinding_host_is_not_local(client):
    r = client.get("/api/portfolio", headers={"Host": "evil.example.com"})
    assert r.status_code == 403


def test_login_flow(client):
    assert client.post("/api/auth/password", json={"new_password": "123"}).status_code == 400  # quá ngắn
    assert client.post("/api/auth/password", json={"new_password": "mat-khau-1"}).status_code == 200
    assert client.get("/api/portfolio", headers=REMOTE).status_code == 401
    assert client.post("/api/auth/login", json={"password": "sai"}, headers=REMOTE).status_code == 401
    r = client.post("/api/auth/login", json={"password": "mat-khau-1"}, headers=REMOTE)
    assert r.status_code == 200 and security.COOKIE in r.cookies
    assert client.get("/api/portfolio", headers=REMOTE).status_code == 200
    st = client.get("/api/auth/status", headers=REMOTE).json()
    assert st == {"local": False, "password_set": True, "password_from_env": False, "authenticated": True}
    client.post("/api/auth/logout", headers=REMOTE)
    assert client.get("/api/portfolio", headers=REMOTE).status_code == 401


def test_password_change_invalidates_sessions_and_remote_needs_current(client):
    client.post("/api/auth/password", json={"new_password": "mat-khau-1"})
    client.post("/api/auth/login", json={"password": "mat-khau-1"}, headers=REMOTE)
    assert client.post("/api/auth/password", json={"new_password": "mat-khau-2"}, headers=REMOTE).status_code == 403
    client.cookies.clear()
    client.post("/api/auth/login", json={"password": "mat-khau-1"}, headers=REMOTE)
    old_cookie = client.cookies.get(security.COOKIE)
    assert client.post("/api/auth/password", json={"new_password": "mat-khau-2"}).status_code == 200  # đổi trên máy
    client.cookies.set(security.COOKIE, old_cookie)
    assert client.get("/api/portfolio", headers=REMOTE).status_code == 401


def test_bruteforce_lockout(client):
    client.post("/api/auth/password", json={"new_password": "mat-khau-1"})
    for _ in range(security.MAX_FAILURES):
        assert client.post("/api/auth/login", json={"password": "x"}, headers=REMOTE).status_code == 401
    assert client.post("/api/auth/login", json={"password": "mat-khau-1"}, headers=REMOTE).status_code == 429


def test_forged_or_expired_token_rejected(client):
    client.post("/api/auth/password", json={"new_password": "mat-khau-1"})
    client.cookies.set(security.COOKIE, "9999999999.deadbeef")
    assert client.get("/api/portfolio", headers=REMOTE).status_code == 401
    assert not security.token_valid("1." + "0" * 64)


def test_tunnel_requires_local_and_password(client):
    assert client.post("/api/remote/tunnel/start").status_code == 400            # chưa có mật khẩu
    client.post("/api/auth/password", json={"new_password": "mat-khau-1"})
    client.post("/api/auth/login", json={"password": "mat-khau-1"}, headers=REMOTE)
    assert client.post("/api/remote/tunnel/start", headers=REMOTE).status_code == 403  # không mở từ xa
    info = client.get("/api/remote/info").json()
    assert "lan_urls" in info and info["tunnel"]["running"] is False


def test_no_wildcard_cors(client):
    r = client.options("/api/portfolio", headers={"Origin": "https://evil.example.com",
                                                  "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


@pytest.mark.skipif(__import__("os").name == "nt", reason="dùng shell script giả lập cloudflared")
def test_tunnel_start_stop_with_fake_cloudflared(client, tmp_path, monkeypatch):
    from app import remote
    fake = tmp_path / "cloudflared"
    fake.write_text("#!/bin/sh\necho 'INF Requesting new quick Tunnel'\n"
                    "echo 'INF |  https://abc-def-ghi.trycloudflare.com  |'\nexec sleep 30\n")
    fake.chmod(0o755)
    monkeypatch.setattr(remote, "cloudflared_path", lambda: fake)
    client.post("/api/auth/password", json={"new_password": "mat-khau-1"})
    st = client.post("/api/remote/tunnel/start").json()
    try:
        assert st["running"] and st["url"] == "https://abc-def-ghi.trycloudflare.com"
    finally:
        assert client.post("/api/remote/tunnel/stop").json()["running"] is False
