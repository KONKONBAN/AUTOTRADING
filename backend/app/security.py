"""Bảo vệ truy cập.

- Trên CHÍNH máy tính chạy ứng dụng (localhost): dùng ngay, không cần đăng nhập.
- Truy cập TỪ XA (điện thoại qua Wi-Fi/Internet, đường hầm Cloudflare…): bắt buộc đặt mật khẩu và đăng nhập.
  Chưa đặt mật khẩu thì mọi truy cập từ xa đều bị từ chối.

Một yêu cầu chỉ được coi là "trên máy này" khi: kết nối đến từ địa chỉ loopback, KHÔNG có header chuyển tiếp
(X-Forwarded-For, CF-Connecting-IP… - do đường hầm/proxy thêm vào) và tên máy (Host) là localhost/127.0.0.1.
Kiểm tra Host chặn kiểu tấn công DNS rebinding từ trang web lạ nhắm vào máy chủ cục bộ.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import secrets
import threading
import time

from fastapi import Request

from .config import settings
from .db import get_db

COOKIE = "at_session"
SESSION_SECONDS = 30 * 24 * 3600
MIN_PASSWORD = 6
_PBKDF2_ROUNDS = 240_000
_LOCAL_NAMES = {"localhost", "127.0.0.1", "::1", "testserver"}  # testserver: Starlette TestClient
_FORWARD_HEADERS = ("x-forwarded-for", "x-forwarded-host", "forwarded", "cf-connecting-ip", "x-real-ip")
# Đường dẫn công khai (không cần đăng nhập): giao diện tĩnh và các API phục vụ màn hình đăng nhập
PUBLIC_API = {"/api/health", "/api/auth/status", "/api/auth/login", "/api/auth/logout"}
_PROTECTED_EXTRA = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}

_fail_lock = threading.Lock()
_failures: dict[str, list[float]] = {}
MAX_FAILURES, FAIL_WINDOW = 8, 15 * 60


def _host_name(request: Request) -> str:
    host = (request.headers.get("host") or "").strip().lower()
    if host.startswith("["):  # [::1]:8000
        return host[1:host.find("]")] if "]" in host else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def is_local(request: Request) -> bool:
    client = request.client.host if request.client else ""
    if client != "testclient":
        try:
            if not ipaddress.ip_address(client).is_loopback:
                return False
        except ValueError:
            return False
    if any(h in request.headers for h in _FORWARD_HEADERS):
        return False
    return _host_name(request) in _LOCAL_NAMES


def client_ip(request: Request) -> str:
    for h in ("cf-connecting-ip", "x-real-ip"):
        if request.headers.get(h):
            return request.headers[h].strip()
    if request.headers.get("x-forwarded-for"):
        return request.headers["x-forwarded-for"].split(",")[0].strip()
    return request.client.host if request.client else "?"


# ------------------------------------------------------------------ mật khẩu
def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)


def password_from_env() -> bool:
    return bool(settings.app_password)


def password_set() -> bool:
    return password_from_env() or bool(get_db().get_kv("auth_hash"))


def check_password(password: str) -> bool:
    if password_from_env():
        return hmac.compare_digest(password.encode("utf-8"), settings.app_password.encode("utf-8"))
    stored = get_db().get_kv("auth_hash")
    if not stored:
        return False
    salt_b64, hash_b64 = stored.split("$", 1)
    return hmac.compare_digest(_hash(password, base64.b64decode(salt_b64)), base64.b64decode(hash_b64))


def set_password(new: str) -> None:
    if password_from_env():
        raise ValueError("Mật khẩu đang được đặt bằng APP_PASSWORD trong file .env - hãy sửa ở đó.")
    if len(new) < MIN_PASSWORD:
        raise ValueError(f"Mật khẩu cần ít nhất {MIN_PASSWORD} ký tự.")
    salt = secrets.token_bytes(16)
    db = get_db()
    db.set_kv("auth_hash", base64.b64encode(salt).decode() + "$" + base64.b64encode(_hash(new, salt)).decode())
    db.set_kv("auth_secret", secrets.token_hex(32))  # đổi mật khẩu → mọi phiên đăng nhập cũ hết hiệu lực


def _secret() -> bytes:
    db = get_db()
    s = db.get_kv("auth_secret")
    if not s:
        s = secrets.token_hex(32)
        db.set_kv("auth_secret", s)
    key = s.encode()
    if password_from_env():  # đổi APP_PASSWORD trong .env cũng làm phiên cũ hết hiệu lực
        key += hashlib.sha256(settings.app_password.encode("utf-8")).digest()
    return key


def make_token() -> str:
    exp = str(int(time.time()) + SESSION_SECONDS)
    return exp + "." + hmac.new(_secret(), exp.encode(), hashlib.sha256).hexdigest()


def token_valid(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    exp, sig = token.split(".", 1)
    if not exp.isdigit() or int(exp) < time.time():
        return False
    return hmac.compare_digest(sig, hmac.new(_secret(), exp.encode(), hashlib.sha256).hexdigest())


def authenticated(request: Request) -> bool:
    return password_set() and token_valid(request.cookies.get(COOKIE))


# ------------------------------------------------------------------ chống dò mật khẩu
def login_blocked(ip: str) -> int:
    """Số giây còn bị khóa (0 = được thử)."""
    now = time.time()
    with _fail_lock:
        recent = [t for t in _failures.get(ip, []) if now - t < FAIL_WINDOW]
        _failures[ip] = recent
        return int(FAIL_WINDOW - (now - recent[0])) if len(recent) >= MAX_FAILURES else 0


def record_failure(ip: str) -> None:
    with _fail_lock:
        _failures.setdefault(ip, []).append(time.time())


def clear_failures(ip: str) -> None:
    with _fail_lock:
        _failures.pop(ip, None)


def needs_guard(path: str) -> bool:
    return (path.startswith("/api/") and path not in PUBLIC_API) or path in _PROTECTED_EXTRA
