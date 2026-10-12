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
    ticker TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    buy_date TEXT NOT NULL,
    stop_loss REAL,
    take_profit REAL,
    highest REAL
);
CREATE TABLE IF NOT EXISTS equity_history (
    date TEXT PRIMARY KEY,
    equity REAL NOT NULL,
    cash REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_sessions (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    title TEXT,
    messages TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    created_at REAL NOT NULL,
    ticker TEXT,
    timeframe TEXT,
    result TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    data TEXT
);
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
            self._conn.executescript(_SCHEMA)
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

    # ---- cache -----------------------------------------------------------
    def cache_get(self, key: str) -> Any:
        row = self.query_one("SELECT value, expires_at FROM cache WHERE key = ?", (key,))
        if not row or row["expires_at"] < time.time():
            return None
        return json.loads(row["value"])

    def cache_set(self, key: str, value: Any, ttl: float) -> None:
        self.execute(
            "INSERT INTO cache(key, value, expires_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, expires_at=excluded.expires_at",
            (key, json.dumps(value, ensure_ascii=False), time.time() + ttl),
        )

    # ---- events / audit log ---------------------------------------------
    def log_event(self, level: str, message: str, data: Any = None) -> None:
        self.execute(
            "INSERT INTO events(created_at, level, message, data) VALUES(?,?,?,?)",
            (time.time(), level, message, json.dumps(data, ensure_ascii=False) if data else None),
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
