"""Lưu trữ SQLite đơn giản (thread-safe) cho tài khoản, lệnh, cache và hội thoại AI."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS imported_prices (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (ticker, date)
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    created_at REAL NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    reason TEXT,
    fee REAL DEFAULT 0,
    tax REAL DEFAULT 0,
    filled_at REAL,
    broker TEXT DEFAULT 'paper'
);
CREATE TABLE IF NOT EXISTS lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    ticker TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    buy_date TEXT NOT NULL,
    stop_loss REAL,
    take_profit REAL,
    highest REAL,
    anchor_date TEXT,
    anchor_close REAL
);
CREATE TABLE IF NOT EXISTS equity_history (
    user_id INTEGER NOT NULL DEFAULT 0,
    date TEXT NOT NULL,
    equity REAL NOT NULL,
    cash REAL NOT NULL,
    PRIMARY KEY (user_id, date)
);
CREATE TABLE IF NOT EXISTS agent_sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    title TEXT,
    messages TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    created_at REAL NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL,
    stop_loss REAL,
    take_profit REAL,
    reason TEXT,
    source TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    result TEXT
);
CREATE TABLE IF NOT EXISTS manual_financials (
    ticker TEXT NOT NULL,
    year INTEGER NOT NULL,
    data TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (ticker, year)
);
CREATE TABLE IF NOT EXISTS chart_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    created_at REAL NOT NULL,
    ticker TEXT,
    timeframe TEXT,
    result TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    created_at REAL NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    data TEXT
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    disabled INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    last_login_at REAL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    last_seen_at REAL NOT NULL,
    user_agent TEXT,
    ip TEXT
);
CREATE TABLE IF NOT EXISTS user_kv (
    user_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (user_id, key)
);
"""

# Bảng chứa dữ liệu RIÊNG của từng tài khoản (thêm cột user_id khi nâng cấp CSDL cũ)
USER_TABLES = ("orders", "lots", "agent_sessions", "proposals", "chart_analyses", "events")
_INDEXES = """
CREATE INDEX IF NOT EXISTS ix_orders_user ON orders(user_id, id);
CREATE INDEX IF NOT EXISTS ix_lots_user ON lots(user_id, ticker);
CREATE INDEX IF NOT EXISTS ix_proposals_user ON proposals(user_id, status);
CREATE INDEX IF NOT EXISTS ix_agent_sessions_user ON agent_sessions(user_id, updated_at);
CREATE INDEX IF NOT EXISTS ix_chart_user ON chart_analyses(user_id, id);
CREATE INDEX IF NOT EXISTS ix_events_user ON events(user_id, id);
CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(user_id);
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.executescript(_SCHEMA)
            self._migrate()
            self._conn.executescript(_INDEXES)
            self._conn.commit()

    def _columns(self, table: str) -> set[str]:
        return {r[1] for r in self._conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def _migrate(self) -> None:
        """Nâng cấp CSDL của phiên bản một-người-dùng: thêm cột user_id (dữ liệu cũ = NULL, sẽ giao cho
        tài khoản quản trị đầu tiên khi tạo) và đổi khóa chính equity_history thành (user_id, date)."""
        for table in USER_TABLES:
            if "user_id" not in self._columns(table):
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")
        # mốc giá để nhận biết chia cổ tức bằng cổ phiếu / tách cổ phiếu sau ngày mua
        for col, typ in (("anchor_date", "TEXT"), ("anchor_close", "REAL")):
            if col not in self._columns("lots"):
                self._conn.execute(f"ALTER TABLE lots ADD COLUMN {col} {typ}")
        if "user_id" not in self._columns("equity_history"):
            self._conn.executescript("""
                ALTER TABLE equity_history RENAME TO equity_history_v1;
                CREATE TABLE equity_history (user_id INTEGER NOT NULL DEFAULT 0, date TEXT NOT NULL,
                    equity REAL NOT NULL, cash REAL NOT NULL, PRIMARY KEY (user_id, date));
                INSERT INTO equity_history(user_id, date, equity, cash) SELECT 0, date, equity, cash FROM equity_history_v1;
                DROP TABLE equity_history_v1;
            """)

    def adopt_legacy_data(self, user_id: int) -> None:
        """Giao toàn bộ dữ liệu của bản một-người-dùng (chưa có chủ) cho tài khoản quản trị đầu tiên."""
        with self._lock:
            for table in USER_TABLES:
                self._conn.execute(f"UPDATE {table} SET user_id=? WHERE user_id IS NULL", (user_id,))
            self._conn.execute("UPDATE equity_history SET user_id=? WHERE user_id=0", (user_id,))
            for key in ("paper_cash", "paper_initial_cash", "paper_realized_pnl", "autotrader_config",
                        "autotrader_last_run"):
                row = self._conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
                if row is not None:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO user_kv(user_id, key, value, updated_at) VALUES(?,?,?,?)",
                        (user_id, key, row[0], time.time()))
                    self._conn.execute("DELETE FROM kv WHERE key=?", (key,))
            self._conn.commit()

    # ---- generic helpers -------------------------------------------------
    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def query(self, sql: str, params: tuple | list = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def query_one(self, sql: str, params: tuple | list = ()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # ---- key/value -------------------------------------------------------
    def get_kv(self, key: str, default: Any = None) -> Any:
        row = self.query_one("SELECT value FROM kv WHERE key = ?", (key,))
        return json.loads(row["value"]) if row else default

    def set_kv(self, key: str, value: Any) -> None:
        self.execute(
            "INSERT INTO kv(key, value, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False), time.time()),
        )

    # ---- key/value riêng của từng tài khoản ---------------------------------
    def get_user_kv(self, user_id: int, key: str, default: Any = None) -> Any:
        row = self.query_one("SELECT value FROM user_kv WHERE user_id=? AND key=?", (user_id, key))
        return json.loads(row["value"]) if row else default

    def set_user_kv(self, user_id: int, key: str, value: Any) -> None:
        self.execute(
            "INSERT INTO user_kv(user_id, key, value, updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (user_id, key, json.dumps(value, ensure_ascii=False), time.time()),
        )

    # ---- cache -----------------------------------------------------------
    def cache_get(self, key: str) -> Any:
        row = self.query_one("SELECT value, expires_at FROM cache WHERE key = ?", (key,))
        if not row or row["expires_at"] < time.time():
            return None
        return json.loads(row["value"])

    def cache_entry(self, key: str) -> tuple[Any, float] | None:
        """(giá trị, thời điểm hết hạn) - None nếu không có / đã hết hạn."""
        row = self.query_one("SELECT value, expires_at FROM cache WHERE key = ?", (key,))
        if not row or row["expires_at"] < time.time():
            return None
        return json.loads(row["value"]), row["expires_at"]

    def cache_expiry(self, key: str) -> float | None:
        """Chỉ đọc thời điểm hết hạn (rẻ) - dùng để kiểm tra bộ nhớ đệm trong RAM còn hợp lệ."""
        row = self.query_one("SELECT expires_at FROM cache WHERE key = ?", (key,))
        return row["expires_at"] if row and row["expires_at"] >= time.time() else None

    def cache_set(self, key: str, value: Any, ttl: float) -> float:
        expires = time.time() + ttl
        self.execute(
            "INSERT INTO cache(key, value, expires_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, expires_at=excluded.expires_at",
            (key, json.dumps(value, ensure_ascii=False), expires),
        )
        return expires

    # ---- events / audit log ---------------------------------------------
    def log_event(self, level: str, message: str, data: Any = None, user_id: int | None = None) -> None:
        if user_id is None:
            from .context import optional_user_id
            user_id = optional_user_id()
        self.execute(
            "INSERT INTO events(created_at, user_id, level, message, data) VALUES(?,?,?,?,?)",
            (time.time(), user_id, level, message, json.dumps(data, ensure_ascii=False) if data else None),
        )


_db: Database | None = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database(settings.db_path)
    return _db


def set_db(db: Database) -> None:
    """Dùng trong test để thay DB bằng ':memory:'."""
    global _db
    _db = db
