"""Tài khoản người dùng: đăng ký, đăng nhập, phiên làm việc, phân quyền.

- Lần chạy đầu: tạo tài khoản QUẢN TRỊ (chỉ làm được trên chính máy tính chạy ứng dụng). Dữ liệu của bản
  một-người-dùng trước đây được giao cho tài khoản này.
- Người khác: quản trị viên tạo tài khoản, hoặc bật "cho phép tự đăng ký".
- Mỗi tài khoản có tài khoản giao dịch giấy, lệnh, đề xuất, Auto-Trader và hội thoại AI RIÊNG.
- Mật khẩu băm PBKDF2-SHA256 (muối riêng); phiên đăng nhập = mã ngẫu nhiên trong cookie HttpOnly,
  CSDL chỉ lưu bản băm SHA-256 của mã. Khóa tạm sau nhiều lần sai.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import re
import secrets
import threading
import time

from fastapi import Request

from .config import settings
from .db import get_db

COOKIE = "at_session"
REMEMBER_SECONDS = 30 * 24 * 3600
SHORT_SECONDS = 12 * 3600
MIN_PASSWORD = 8
_PBKDF2_ROUNDS = 240_000
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")

_LOCAL_NAMES = {"localhost", "127.0.0.1", "::1", "testserver"}  # testserver: Starlette TestClient
_FORWARD_HEADERS = ("x-forwarded-for", "x-forwarded-host", "forwarded", "cf-connecting-ip", "x-real-ip")
PUBLIC_API = {"/api/health", "/api/auth/status", "/api/auth/login", "/api/auth/logout", "/api/auth/setup",
              "/api/auth/register"}
_PROTECTED_EXTRA = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}

_fail_lock = threading.Lock()
_failures: dict[str, list[float]] = {}
MAX_FAILURES, FAIL_WINDOW = 8, 15 * 60


class AuthError(ValueError):
    pass


# ------------------------------------------------------------------ yêu cầu từ đâu
def _host_name(request: Request) -> str:
    host = (request.headers.get("host") or "").strip().lower()
    if host.startswith("["):  # [::1]:8000
        return host[1:host.find("]")] if "]" in host else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def is_local(request: Request) -> bool:
    """Yêu cầu đến từ CHÍNH máy tính chạy ứng dụng: IP loopback, không qua proxy/đường hầm, Host = localhost
    (kiểm tra Host chặn tấn công DNS rebinding từ trang web lạ)."""
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
    """IP thật của người dùng. Chỉ tin header chuyển tiếp khi kết nối đến từ CHÍNH máy này (đường hầm cloudflared
    hoặc proxy cục bộ); máy khác trong mạng LAN tự gắn header X-Real-IP sẽ không né được giới hạn theo IP."""
    peer = request.client.host if request.client else "?"
    hops = settings.proxy_hops
    xff = [p.strip() for p in (request.headers.get("x-forwarded-for") or "").split(",") if p.strip()]
    if hops > 0 and xff:
        # máy chủ Internet: proxy của nhà cung cấp NỐI THÊM IP người dùng vào cuối danh sách → lấy theo số bước
        # proxy tin cậy (phần đầu danh sách do trình duyệt tự gửi, giả mạo được)
        return xff[-hops] if len(xff) >= hops else xff[0]
    try:
        trusted = peer == "testclient" or ipaddress.ip_address(peer).is_loopback
    except ValueError:
        trusted = False
    if not trusted:
        return peer
    for h in ("cf-connecting-ip", "x-real-ip"):
        if request.headers.get(h):
            return request.headers[h].strip()
    if request.headers.get("x-forwarded-for"):
        return request.headers["x-forwarded-for"].split(",")[0].strip()
    return peer


def needs_login(path: str) -> bool:
    return (path.startswith("/api/") and path not in PUBLIC_API) or path in _PROTECTED_EXTRA


# ------------------------------------------------------------------ mật khẩu
def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2${_PBKDF2_ROUNDS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt_b64, hash_b64 = stored.split("$", 3)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt_b64), int(rounds))
        return hmac.compare_digest(digest, base64.b64decode(hash_b64))
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = _hash_password("không-dùng")  # so khớp giả khi sai tên đăng nhập → thời gian phản hồi như nhau


def _check_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise AuthError(f"Mật khẩu cần ít nhất {MIN_PASSWORD} ký tự.")
    if password.isdigit() or password.isalpha():
        raise AuthError("Mật khẩu nên có cả chữ và số.")


def normalize_username(username: str) -> str:
    u = (username or "").strip().lower()
    if not USERNAME_RE.match(u):
        raise AuthError("Tên đăng nhập 3-32 ký tự, chỉ gồm chữ thường không dấu, số và . _ - (bắt đầu bằng chữ/số).")
    return u


# ------------------------------------------------------------------ người dùng
def _public(u: dict | None) -> dict | None:
    if not u:
        return None
    return {"id": u["id"], "username": u["username"], "display_name": u["display_name"], "role": u["role"],
            "disabled": bool(u["disabled"]), "created_at": u["created_at"], "last_login_at": u["last_login_at"]}


def user_count() -> int:
    return get_db().query_one("SELECT COUNT(*) AS n FROM users")["n"]


def get_user(user_id: int) -> dict | None:
    return _public(get_db().query_one("SELECT * FROM users WHERE id=?", (user_id,)))


def list_users() -> list[dict]:
    return [_public(u) for u in get_db().query("SELECT * FROM users ORDER BY id")]


def create_user(username: str, password: str, display_name: str | None = None, role: str = "user") -> dict:
    username = normalize_username(username)
    _check_new_password(password)
    if role not in {"admin", "user"}:
        raise AuthError("Vai trò không hợp lệ.")
    name = (display_name or "").strip()[:60] or username
    db = get_db()
    if db.query_one("SELECT id FROM users WHERE username=?", (username,)):
        raise AuthError("Tên đăng nhập đã tồn tại.")
    cur = db.execute("INSERT INTO users(username, display_name, password_hash, role, created_at) VALUES(?,?,?,?,?)",
                     (username, name, _hash_password(password), role, time.time()))
    return get_user(cur.lastrowid)


def check_setup_code(code: str | None, ip: str) -> None:
    """Mã thiết lập (SETUP_CODE) để tạo quản trị viên đầu tiên trên máy chủ Internet. Giới hạn đoán chung cho
    mọi địa chỉ: 8 lần sai / 15 phút."""
    if not settings.setup_code:
        raise AuthError("Tài khoản quản trị đầu tiên chỉ tạo được trên chính máy tính chạy ứng dụng "
                        "(hoặc đặt biến SETUP_CODE trên máy chủ).")
    _reserve_attempt(["setup:any", f"setup:{ip}"])
    if not code or not hmac.compare_digest(code.strip().encode(), settings.setup_code.encode()):
        raise AuthError("Mã thiết lập không đúng.")
    with _fail_lock:
        _failures.pop("setup:any", None)
        _failures.pop(f"setup:{ip}", None)


def setup_admin(username: str, password: str, display_name: str | None = None) -> dict:
    """Tạo tài khoản quản trị đầu tiên và nhận dữ liệu cũ (chỉ khi CSDL chưa có tài khoản nào)."""
    db = get_db()
    with db._lock:  # noqa: SLF001 - tránh hai yêu cầu cùng tạo quản trị
        if user_count() > 0:
            raise AuthError("Ứng dụng đã có tài khoản quản trị.")
        user = create_user(username, password, display_name, role="admin")
        db.adopt_legacy_data(user["id"])
    return user


def registration_open() -> bool:
    return bool(get_db().get_kv("allow_registration", False))


def set_registration(open_: bool) -> None:
    get_db().set_kv("allow_registration", bool(open_))


def update_user(user_id: int, *, display_name: str | None = None, role: str | None = None,
                disabled: bool | None = None, password: str | None = None, acting_user_id: int | None = None) -> dict:
    db = get_db()
    user = db.query_one("SELECT * FROM users WHERE id=?", (user_id,))
    if not user:
        raise AuthError("Không tìm thấy tài khoản.")
    if role is not None or disabled:
        # luôn phải còn ít nhất một quản trị viên đang hoạt động
        admins = db.query("SELECT id FROM users WHERE role='admin' AND disabled=0 AND id<>?", (user_id,))
        losing_admin = user["role"] == "admin" and (role == "user" or disabled)
        if losing_admin and not admins:
            raise AuthError("Phải còn ít nhất một quản trị viên đang hoạt động.")
    if role is not None:
        if role not in {"admin", "user"}:
            raise AuthError("Vai trò không hợp lệ.")
        db.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
    if display_name is not None:
        db.execute("UPDATE users SET display_name=? WHERE id=?", (display_name.strip()[:60] or user["username"], user_id))
    if disabled is not None:
        if disabled and acting_user_id == user_id:
            raise AuthError("Không thể tự khóa tài khoản của mình.")
        db.execute("UPDATE users SET disabled=? WHERE id=?", (1 if disabled else 0, user_id))
        if disabled:
            db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    if password is not None:
        _check_new_password(password)
        db.execute("UPDATE users SET password_hash=? WHERE id=?", (_hash_password(password), user_id))
        db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))  # đăng xuất mọi thiết bị
    return get_user(user_id)


def delete_user(user_id: int, acting_user_id: int) -> None:
    if user_id == acting_user_id:
        raise AuthError("Không thể tự xóa tài khoản của mình.")
    db = get_db()
    user = db.query_one("SELECT * FROM users WHERE id=?", (user_id,))
    if not user:
        raise AuthError("Không tìm thấy tài khoản.")
    if user["role"] == "admin" and not db.query("SELECT id FROM users WHERE role='admin' AND disabled=0 AND id<>?",
                                                (user_id,)):
        raise AuthError("Phải còn ít nhất một quản trị viên.")
    for table in ("orders", "lots", "agent_sessions", "proposals", "chart_analyses", "events", "sessions"):
        db.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM equity_history WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM user_kv WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM users WHERE id=?", (user_id,))


def change_password(user_id: int, current: str, new: str, keep_token: str | None = None) -> None:
    db = get_db()
    user = db.query_one("SELECT * FROM users WHERE id=?", (user_id,))
    if not user or not _verify_password(current, user["password_hash"]):
        raise AuthError("Mật khẩu hiện tại không đúng.")
    _check_new_password(new)
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (_hash_password(new), user_id))
    # đăng xuất các thiết bị KHÁC, giữ phiên hiện tại
    keep = _token_hash(keep_token) if keep_token else ""
    db.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (user_id, keep))


# ------------------------------------------------------------------ đăng nhập & phiên
def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def login_blocked(key: str) -> int:
    now = time.time()
    with _fail_lock:
        recent = [t for t in _failures.get(key, []) if now - t < FAIL_WINDOW]
        _failures[key] = recent
        return int(FAIL_WINDOW - (now - recent[0])) if len(recent) >= MAX_FAILURES else 0


def _record_failure(key: str) -> None:
    with _fail_lock:
        _failures.setdefault(key, []).append(time.time())


def _reserve_attempt(keys: list[str]) -> float:
    """Kiểm tra + ghi nhận lượt thử TRONG CÙNG một khóa: nhiều yêu cầu song song không vượt được giới hạn."""
    now = time.time()
    with _fail_lock:
        waits = []
        for k in keys:
            recent = [t for t in _failures.get(k, []) if now - t < FAIL_WINDOW]
            _failures[k] = recent
            if len(recent) >= MAX_FAILURES:
                waits.append(int(FAIL_WINDOW - (now - recent[0])))
        if waits:
            raise AuthError(f"Sai mật khẩu quá nhiều lần - thử lại sau {max(waits) // 60 + 1} phút.")
        for k in keys:
            _failures[k].append(now)  # tính là một lần sai cho tới khi mật khẩu được xác nhận đúng
    return now


def authenticate(username: str, password: str, ip: str) -> dict:
    keys = [f"ip:{ip}", f"user:{(username or '').strip().lower()}"]
    _reserve_attempt(keys)
    row = get_db().query_one("SELECT * FROM users WHERE username=?", ((username or "").strip().lower(),))
    ok = _verify_password(password, row["password_hash"] if row else _DUMMY_HASH)
    if not row or not ok:
        raise AuthError("Sai tên đăng nhập hoặc mật khẩu.")
    if row["disabled"]:
        raise AuthError("Tài khoản đã bị khóa - liên hệ quản trị viên.")
    with _fail_lock:
        for k in keys:
            _failures.pop(k, None)
    return _public(row)


def create_session(user_id: int, remember: bool, user_agent: str | None, ip: str) -> tuple[str, int]:
    token = secrets.token_urlsafe(32)
    ttl = REMEMBER_SECONDS if remember else SHORT_SECONDS
    now = time.time()
    db = get_db()
    db.execute("INSERT INTO sessions(token_hash, user_id, created_at, expires_at, last_seen_at, user_agent, ip) "
               "VALUES(?,?,?,?,?,?,?)", (_token_hash(token), user_id, now, now + ttl, now, (user_agent or "")[:200], ip))
    db.execute("UPDATE users SET last_login_at=? WHERE id=?", (now, user_id))
    db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
    return token, ttl


def session_user(token: str | None) -> dict | None:
    if not token:
        return None
    db = get_db()
    row = db.query_one("SELECT s.token_hash, s.expires_at, s.last_seen_at, u.* FROM sessions s "
                       "JOIN users u ON u.id = s.user_id WHERE s.token_hash=?", (_token_hash(token),))
    now = time.time()
    if not row or row["expires_at"] < now or row["disabled"]:
        return None
    if now - row["last_seen_at"] > 300:
        db.execute("UPDATE sessions SET last_seen_at=? WHERE token_hash=?", (now, row["token_hash"]))
    return _public(row)


def end_session(token: str | None) -> None:
    if token:
        get_db().execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))


def list_sessions(user_id: int, current_token: str | None) -> list[dict]:
    cur = _token_hash(current_token) if current_token else ""
    rows = get_db().query("SELECT token_hash, created_at, last_seen_at, expires_at, user_agent, ip FROM sessions "
                          "WHERE user_id=? AND expires_at>? ORDER BY last_seen_at DESC", (user_id, time.time()))
    return [{"id": r["token_hash"][:16], "created_at": r["created_at"], "last_seen_at": r["last_seen_at"],
             "expires_at": r["expires_at"], "user_agent": r["user_agent"], "ip": r["ip"],
             "current": r["token_hash"] == cur} for r in rows]


def revoke_session(user_id: int, session_id: str) -> None:
    if len(session_id) < 16:
        raise AuthError("Mã phiên không hợp lệ.")
    get_db().execute("DELETE FROM sessions WHERE user_id=? AND substr(token_hash, 1, 16)=?", (user_id, session_id))
