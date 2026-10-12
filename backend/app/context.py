"""Ngữ cảnh "người dùng hiện tại" cho từng yêu cầu / tác vụ nền.

Mọi dữ liệu riêng (tài khoản giấy, lệnh, đề xuất, Auto-Trader, hội thoại AI…) đọc user_id từ đây.
Không có ngữ cảnh thì BÁO LỖI thay vì đoán người dùng - tránh lộ hoặc ghi nhầm dữ liệu giữa các tài khoản.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_current_user: ContextVar[int | None] = ContextVar("current_user", default=None)


class NoUserContext(RuntimeError):
    pass


def current_user_id() -> int:
    uid = _current_user.get()
    if uid is None:
        raise NoUserContext("Không xác định được tài khoản đang đăng nhập.")
    return uid


def optional_user_id() -> int | None:
    return _current_user.get()


def set_current_user(user_id: int | None):
    return _current_user.set(user_id)


def reset_current_user(token) -> None:
    _current_user.reset(token)


@contextmanager
def as_user(user_id: int) -> Iterator[None]:
    token = _current_user.set(user_id)
    try:
        yield
    finally:
        _current_user.reset(token)
