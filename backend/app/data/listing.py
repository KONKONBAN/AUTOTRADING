"""Danh sách TOÀN BỘ cổ phiếu niêm yết (HOSE, HNX, UPCoM) kèm sàn và ngành.

Nguồn: KBS (stock/search/data) → Vietcap (symbols/getAll); ngành theo ICB cấp 2 của Vietcap. Lưu đệm 24 giờ và
giữ bản tốt gần nhất để dùng khi mất mạng. Danh sách 44 mã trong universe.py vẫn là "danh mục theo dõi mặc định"
(bộ lọc, Auto-Trader), còn mọi mã niêm yết khác đều phân tích / đặt lệnh được.
"""

from __future__ import annotations

import logging
import threading

from ..config import settings
from ..db import get_db
from . import http

log = logging.getLogger(__name__)

KBS_SEARCH = "https://kbbuddywts.kbsec.com.vn/iis-server/investment/stock/search/data"
VCI_ALL = "https://trading.vietcap.com.vn/api/price/symbols/getAll"
VCI_ICB = "https://iq.vietcap.com.vn/api/iq-insight-service/v2/company/search-bar"
VCI_HEADERS = {"Referer": "https://trading.vietcap.com.vn/", "Origin": "https://trading.vietcap.com.vn"}
_EXCHANGE = {"HSX": "HOSE", "HOSE": "HOSE", "XHNF": "HNX", "HNX": "HNX", "UPCOM": "UPCOM", "UPCOMINDEX": "UPCOM"}
CACHE_KEY, CACHE_TTL = "listing:v1", 24 * 3600

_mem: dict[str, dict] | None = None
_lock = threading.Lock()


def _items(js) -> list[dict]:
    if isinstance(js, dict):
        js = js.get("data") or js.get("items") or []
    return [x for x in (js or []) if isinstance(x, dict)]


def _from_kbs() -> dict[str, dict]:
    out = {}
    for x in _items(http.get_json(KBS_SEARCH)):
        sym = str(x.get("symbol") or "").upper().strip()
        if not sym or str(x.get("type") or "stock").lower() != "stock":
            continue
        out[sym] = {"name": x.get("name") or sym, "exchange": _EXCHANGE.get(str(x.get("exchange") or "").upper(), "HOSE")}
    return out


def _from_vci() -> dict[str, dict]:
    out = {}
    for x in _items(http.get_json(VCI_ALL, headers=VCI_HEADERS)):
        sym = str(x.get("symbol") or "").upper().strip()
        if not sym or str(x.get("type") or "STOCK").upper() != "STOCK":
            continue
        out[sym] = {"name": x.get("organName") or x.get("organShortName") or sym,
                    "exchange": _EXCHANGE.get(str(x.get("board") or "").upper(), "HOSE")}
    return out


def _icb_sectors() -> dict[str, str]:
    out = {}
    for x in _items(http.get_json(VCI_ICB, {"language": 1}, headers=VCI_HEADERS)):
        lv2 = x.get("icbLv2") or {}
        if x.get("code") and isinstance(lv2, dict) and lv2.get("name"):
            out[str(x["code"]).upper()] = lv2["name"]
    return out


def refresh() -> dict[str, dict]:
    """Tải lại danh sách (KBS → Vietcap) và ngành; lỗi thì giữ bản cũ."""
    global _mem
    stocks, source = {}, None
    for src, fn in (("kbs", _from_kbs), ("vci", _from_vci)):
        try:
            stocks = fn()
            if len(stocks) > 100:
                source = src
                break
        except Exception as exc:  # noqa: BLE001
            log.info("Danh sách mã từ %s lỗi: %s", src, exc)
    if not source:
        raise RuntimeError("Không tải được danh sách mã niêm yết")
    try:
        for sym, sector in _icb_sectors().items():
            if sym in stocks:
                stocks[sym]["sector"] = sector
    except Exception as exc:  # noqa: BLE001 - thiếu ngành không chặn danh sách
        log.info("Ngành ICB lỗi: %s", exc)
    db = get_db()
    payload = {"source": source, "stocks": stocks}
    db.cache_set(CACHE_KEY, payload, CACHE_TTL)
    db.set_kv("listing_last", payload)
    with _lock:
        _mem = stocks
    return stocks


def stocks(allow_fetch: bool = True) -> dict[str, dict]:
    """{mã: {name, exchange, sector?}} - rỗng ở chế độ DEMO hoặc khi chưa từng tải được."""
    global _mem
    if settings.data_mode == "demo":
        return {}
    with _lock:
        if _mem is not None:
            return _mem
    db = get_db()
    cached = db.cache_get(CACHE_KEY)
    if cached:
        with _lock:
            _mem = cached["stocks"]
        return _mem
    if allow_fetch:
        try:
            return refresh()
        except Exception:  # noqa: BLE001
            pass
    last = db.get_kv("listing_last")
    with _lock:
        _mem = (last or {}).get("stocks") or {}
    return _mem


def lookup(ticker: str) -> dict | None:
    return stocks().get(ticker.upper())


def source() -> str | None:
    cached = get_db().cache_get(CACHE_KEY) or get_db().get_kv("listing_last") or {}
    return cached.get("source")
