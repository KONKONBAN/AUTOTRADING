"""HTTP dùng chung cho các nguồn dữ liệu thị trường.

- Header trình duyệt cố định (các API công khai của CTCK từ chối client lạ).
- Ngắt mạch theo từng máy chủ: máy chủ vừa lỗi kết nối / chặn (403, 429, 5xx) bị tạm bỏ qua một lúc để ứng
  dụng không bị chậm khi một nguồn ngừng hoạt động.
"""

from __future__ import annotations

import threading
import time
from urllib.parse import urlparse

import httpx

TIMEOUT = httpx.Timeout(15.0, connect=5.0)
BROWSER_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/140.0.0.0 Safari/537.36"),
}
COOLDOWN_ERROR = 300      # giây: lỗi kết nối / bị chặn
COOLDOWN_RATE_LIMIT = 60  # giây: HTTP 429

_lock = threading.Lock()
_down_until: dict[str, float] = {}


class SourceDown(RuntimeError):
    """Máy chủ đang trong thời gian tạm bỏ qua."""


def _host(url: str) -> str:
    return urlparse(url).hostname or url


def host_down(url: str) -> float:
    with _lock:
        return max(0.0, _down_until.get(_host(url), 0.0) - time.time())


def reset_host(url: str) -> None:
    with _lock:
        _down_until.pop(_host(url), None)


def reset_all() -> None:
    with _lock:
        _down_until.clear()


def _trip(url: str, seconds: float) -> None:
    with _lock:
        _down_until[_host(url)] = time.time() + seconds


def request_json(method: str, url: str, *, params: dict | None = None, json: dict | list | None = None,
                 headers: dict | None = None, timeout: httpx.Timeout | float = TIMEOUT):
    wait = host_down(url)
    if wait:
        raise SourceDown(f"{_host(url)} tạm bỏ qua {int(wait)} giây (vừa lỗi)")
    try:
        r = httpx.request(method, url, params=params, json=json, headers={**BROWSER_HEADERS, **(headers or {})},
                          timeout=timeout, follow_redirects=True)
    except httpx.TransportError:
        _trip(url, COOLDOWN_ERROR)
        raise
    if r.status_code == 429:
        _trip(url, COOLDOWN_RATE_LIMIT)
    elif r.status_code in (401, 403, 451) or r.status_code >= 500:
        _trip(url, COOLDOWN_ERROR)
    r.raise_for_status()
    try:
        return r.json()
    except ValueError as exc:  # trang HTML (chặn bot / bảo trì) thay vì JSON
        _trip(url, COOLDOWN_ERROR)
        raise ValueError(f"{_host(url)} không trả về JSON (có thể bị chặn)") from exc


def get_json(url: str, params: dict | None = None, headers: dict | None = None):
    return request_json("GET", url, params=params, headers=headers)


def post_json(url: str, body: dict | list, headers: dict | None = None, params: dict | None = None):
    return request_json("POST", url, json=body, headers=headers, params=params)
