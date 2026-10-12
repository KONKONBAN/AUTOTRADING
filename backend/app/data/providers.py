"""Nguồn dữ liệu giá cổ phiếu.

Thứ tự ưu tiên:
1. Dữ liệu người dùng tự nhập (CSV định dạng Amibroker/CafeF: <Ticker>,<DTYYYYMMDD>,<Open>,...).
2. Dữ liệu thật từ API công khai (VNDirect dchart, dự phòng TCBS) - khi DATA_MODE = auto | live.
3. Dữ liệu DEMO mô phỏng (có tính tất định theo mã) - khi không lấy được dữ liệu thật.

Mọi kết quả đều kèm trường `source` để giao diện hiển thị rõ đang dùng dữ liệu gì.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import time
from datetime import date, datetime, timedelta

import httpx
import numpy as np
import pandas as pd

from ..config import settings
from ..db import get_db
from ..trading.vn_rules import round_to_tick
from . import universe

log = logging.getLogger(__name__)

HTTP_TIMEOUT = httpx.Timeout(8.0, connect=3.0)
HEADERS = {"User-Agent": "Mozilla/5.0 (AutoTradingVN)", "Accept": "application/json"}

SOURCE_IMPORTED = "imported"
SOURCE_DEMO = "demo"


class DataUnavailable(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Live providers - nhiều nguồn công khai, tự động chuyển nguồn khi lỗi
# ---------------------------------------------------------------------------
def _epoch(d: date, end_of_day: bool = False) -> int:
    t = datetime.max.time() if end_of_day else datetime.min.time()
    return int(datetime.combine(d, t).timestamp())


def _udf_frame(js: dict, ticker: str) -> pd.DataFrame:
    """Chuẩn TradingView UDF {t,o,h,l,c,v} (có thể lồng trong 'data')."""
    if isinstance(js.get("data"), dict) and "t" in js["data"]:
        js = js["data"]
    if js.get("s") not in (None, "ok") or not js.get("t"):
        raise DataUnavailable(f"Không có dữ liệu cho {ticker}")
    df = pd.DataFrame({
        "date": pd.to_datetime([int(x) for x in js["t"]], unit="s").normalize(),
        "open": pd.to_numeric(js["o"]), "high": pd.to_numeric(js["h"]),
        "low": pd.to_numeric(js["l"]), "close": pd.to_numeric(js["c"]),
        "volume": pd.to_numeric(js.get("v") or [0] * len(js["t"])),
    })
    if ticker != "VNINDEX" and df["close"].median() < 1_000:
        df[["open", "high", "low", "close"]] *= 1_000  # đơn vị nghìn đồng → đồng
    return df


def _get_json(url: str, params: dict, headers: dict | None = None) -> dict:
    r = httpx.get(url, params=params, headers={**HEADERS, **(headers or {})}, timeout=HTTP_TIMEOUT,
                  follow_redirects=True)
    r.raise_for_status()
    return r.json()


def _fetch_vndirect(ticker: str, start: date, end: date) -> pd.DataFrame:
    js = _get_json("https://dchart-api.vndirect.com.vn/dchart/history",
                   {"resolution": "D", "symbol": ticker, "from": _epoch(start), "to": _epoch(end, True)})
    return _udf_frame(js, ticker)


def _fetch_ssi(ticker: str, start: date, end: date) -> pd.DataFrame:
    params = {"resolution": "1d", "symbol": ticker, "from": _epoch(start), "to": _epoch(end, True)}
    headers = {"Origin": "https://iboard.ssi.com.vn", "Referer": "https://iboard.ssi.com.vn/"}
    try:
        js = _get_json("https://iboard-api.ssi.com.vn/statistics/charts/history", params, headers)
    except Exception:  # noqa: BLE001 - endpoint cũ của iBoard
        js = _get_json("https://iboard.ssi.com.vn/dchart/api/history", {**params, "resolution": "D"}, headers)
    return _udf_frame(js, ticker)


def _fetch_tcbs(ticker: str, start: date, end: date) -> pd.DataFrame:
    js = _get_json("https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term",
                   {"ticker": ticker, "type": "index" if ticker == "VNINDEX" else "stock",
                    "resolution": "D", "to": _epoch(end, True), "countBack": max(30, (end - start).days)})
    rows = js.get("data") or []
    if not rows:
        raise DataUnavailable(f"TCBS không có dữ liệu cho {ticker}")
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["tradingDate"]).dt.tz_localize(None).dt.normalize()
    return df[["date", "open", "high", "low", "close", "volume"]]


def _fetch_vps(ticker: str, start: date, end: date) -> pd.DataFrame:
    js = _get_json("https://histdatafeed.vps.com.vn/tradingview/history",
                   {"symbol": ticker, "resolution": "D", "from": _epoch(start), "to": _epoch(end, True)})
    return _udf_frame(js, ticker)


def _fetch_vietstock(ticker: str, start: date, end: date) -> pd.DataFrame:
    headers = {"Origin": "https://stockchart.vietstock.vn", "Referer": "https://stockchart.vietstock.vn/"}
    js = _get_json("https://api.vietstock.vn/tvnew/history",
                   {"symbol": ticker, "resolution": "D", "from": _epoch(start), "to": _epoch(end, True)}, headers)
    return _udf_frame(js, ticker)


def _fetch_cafef(ticker: str, start: date, end: date) -> pd.DataFrame:
    js = _get_json("https://s.cafef.vn/Ajax/PageNew/DataHistory/PriceHistory.ashx",
                   {"Symbol": ticker, "StartDate": start.strftime("%m/%d/%Y"),
                    "EndDate": end.strftime("%m/%d/%Y"), "PageIndex": 1, "PageSize": 2000})
    rows = ((js.get("Data") or {}).get("Data")) or []
    if not rows:
        raise DataUnavailable(f"CafeF không có dữ liệu cho {ticker}")
    df = pd.DataFrame({
        "date": pd.to_datetime([r["Ngay"] for r in rows], dayfirst=True),
        "open": [r.get("GiaMoCua") for r in rows], "high": [r.get("GiaCaoNhat") for r in rows],
        "low": [r.get("GiaThapNhat") for r in rows],
        "close": [r.get("GiaDieuChinh") or r.get("GiaDongCua") for r in rows],
        "volume": [r.get("KhoiLuongKhopLenh") or 0 for r in rows],
    })
    if ticker != "VNINDEX" and df["close"].median() < 1_000:
        df[["open", "high", "low", "close"]] *= 1_000
    return df


# Thứ tự mặc định; nguồn chạy thành công gần nhất sẽ được ưu tiên ở lần sau.
LIVE_PROVIDERS = {
    "vndirect": ("VNDirect (dchart)", _fetch_vndirect),
    "ssi": ("SSI iBoard", _fetch_ssi),
    "tcbs": ("TCBS", _fetch_tcbs),
    "vps": ("VPS", _fetch_vps),
    "vietstock": ("Vietstock", _fetch_vietstock),
    "cafef": ("CafeF", _fetch_cafef),
}
PROVIDER_COOLDOWN = 300  # giây: tạm bỏ qua nguồn vừa lỗi kết nối để không làm chậm ứng dụng
_down_until: dict[str, float] = {}


def _provider_order() -> list[str]:
    preferred = get_db().get_kv("preferred_provider")
    order = list(LIVE_PROVIDERS)
    if preferred in order:
        order.remove(preferred)
        order.insert(0, preferred)
    return order


def fetch_live(ticker: str, start: date, end: date) -> tuple[pd.DataFrame, str, list[dict]]:
    """Thử lần lượt các nguồn; trả về (dữ liệu, tên nguồn, nhật ký các lần thử)."""
    attempts = []
    for key in _provider_order():
        name, fn = LIVE_PROVIDERS[key]
        if _down_until.get(key, 0) > time.time():
            attempts.append({"provider": key, "ok": False, "error": "tạm bỏ qua (vừa lỗi kết nối)"})
            continue
        t0 = time.time()
        try:
            df = fn(ticker, start, end)
            if len(df) < 30:
                raise DataUnavailable("dữ liệu quá ngắn")
            attempts.append({"provider": key, "ok": True, "ms": int((time.time() - t0) * 1000)})
            get_db().set_kv("preferred_provider", key)
            get_db().set_kv("live_status", {"ok": True, "provider": key, "at": time.time()})
            return df, key, attempts
        except Exception as exc:  # noqa: BLE001 - lỗi mạng/định dạng → thử nguồn tiếp theo
            if isinstance(exc, (httpx.TransportError, httpx.HTTPStatusError)):
                _down_until[key] = time.time() + PROVIDER_COOLDOWN
            attempts.append({"provider": key, "ok": False, "error": str(exc)[:160],
                             "ms": int((time.time() - t0) * 1000)})
            log.info("Nguồn %s lỗi cho %s: %s", name, ticker, exc)
    get_db().set_kv("live_status", {"ok": False, "at": time.time(), "ticker": ticker, "attempts": attempts})
    raise DataUnavailable(f"Tất cả nguồn dữ liệu đều không truy cập được cho {ticker}")


def provider_health(ticker: str = "FPT") -> list[dict]:
    """Kiểm tra từng nguồn dữ liệu (dùng cho trang Trạng thái dữ liệu)."""
    end = date.today()
    start = end - timedelta(days=90)
    out = []
    for key, (name, fn) in LIVE_PROVIDERS.items():
        t0 = time.time()
        try:
            df = fn(ticker, start, end)
            out.append({"provider": key, "name": name, "ok": True, "rows": len(df),
                        "last_date": pd.Timestamp(df["date"].max()).strftime("%Y-%m-%d"),
                        "last_close": float(df.sort_values("date")["close"].iloc[-1]),
                        "ms": int((time.time() - t0) * 1000)})
        except Exception as exc:  # noqa: BLE001
            out.append({"provider": key, "name": name, "ok": False, "error": str(exc)[:200],
                        "ms": int((time.time() - t0) * 1000)})
    for r in out:
        if r["ok"]:
            _down_until.pop(r["provider"], None)
    get_db().set_kv("provider_health", {"checked_at": time.time(), "results": out})
    return out


# ---------------------------------------------------------------------------
# Demo generator (deterministic)
# ---------------------------------------------------------------------------
def _seed(text: str) -> int:
    return int(hashlib.md5(text.encode()).hexdigest()[:8], 16)


def _business_days(end: date, n: int) -> pd.DatetimeIndex:
    return pd.bdate_range(end=pd.Timestamp(end), periods=n)


DEMO_DAYS = 1500  # luôn sinh cùng một chuỗi dài rồi cắt đuôi → nhất quán giữa các lần gọi


def _market_returns(n: int) -> np.ndarray:
    rng = np.random.default_rng(_seed("VNINDEX-demo-6"))
    rets = np.empty(n)
    i = 0
    while i < n:
        length = int(rng.integers(40, 160))
        regime_drift = rng.normal(0.12, 0.22) / 252
        vol = rng.uniform(0.12, 0.24) / np.sqrt(252)
        rets[i:i + length] = rng.normal(regime_drift, vol, size=min(length, n - i))
        i += length
    return rets[-n:] if len(rets) > n else rets


def _demo_history(ticker: str, n: int = 750, end: date | None = None) -> pd.DataFrame:
    end = end or date.today()
    total = max(n, DEMO_DAYS)
    idx = _business_days(end, total)
    meta = universe.info(ticker)
    mkt = _market_returns(total)
    if ticker == "VNINDEX":
        rets = mkt
        base = meta["reference_price"]
    else:
        rng = np.random.default_rng(_seed(ticker))
        beta = rng.uniform(0.6, 1.4)
        alpha = rng.normal(0.03, 0.08) / 252
        idio_vol = rng.uniform(0.12, 0.28) / np.sqrt(252)
        rets = alpha + beta * mkt + rng.normal(0, idio_vol, total)
        base = meta["reference_price"]
    n_out = n
    n = total
    rets = np.clip(rets, -0.069, 0.069)  # biên độ HOSE ±7%
    path = np.exp(np.cumsum(rets))
    close = base * path / path[-1]  # neo giá cuối ≈ giá tham khảo
    rng = np.random.default_rng(_seed(ticker + "-ohlc"))
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.004, n))
    spread = np.abs(rng.normal(0, 0.006, n)) + np.abs(rets) * 0.25
    prev_close = np.r_[close[0], close[:-1]]
    high = np.minimum(np.maximum(open_, close) * (1 + spread), prev_close * 1.069)
    low = np.maximum(np.minimum(open_, close) * (1 - spread), prev_close * 0.931)
    vol_base = 5e5 if ticker == "VNINDEX" else rng.uniform(1e6, 2e7)
    volume = vol_base * np.exp(rng.normal(0, 0.35, n)) * (1 + 15 * np.abs(rets))
    df = pd.DataFrame({"date": idx, "open": open_, "high": high, "low": low,
                       "close": close, "volume": volume.round()}).tail(n_out).reset_index(drop=True)
    if ticker != "VNINDEX":
        ex = meta["exchange"]
        for col in ("open", "high", "low", "close"):
            df[col] = [round_to_tick(p, ex) for p in df[col]]
        df["high"] = df[["open", "high", "close"]].max(axis=1)
        df["low"] = df[["open", "low", "close"]].min(axis=1)
    else:
        df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].round(2)
    return df


# ---------------------------------------------------------------------------
# Imported data (CSV)
# ---------------------------------------------------------------------------
def import_csv(text: str) -> dict:
    """Nhập dữ liệu giá từ CSV.

    Hỗ trợ định dạng Amibroker/CafeF/MetaStock:  <Ticker>,<DTYYYYMMDD>,<Open>,<High>,<Low>,<Close>,<Volume>
    và định dạng có header: ticker,date,open,high,low,close,volume (date dạng YYYY-MM-DD).
    """
    reader = csv.reader(io.StringIO(text.strip()))
    rows, counts = [], {}
    for rec in reader:
        if not rec or len(rec) < 6:
            continue
        head = rec[0].strip().strip("<>").lower()
        if head in {"ticker", "symbol", "mã"}:
            continue
        try:
            ticker = rec[0].strip().upper()
            raw_date = rec[1].strip()
            d = (datetime.strptime(raw_date, "%Y%m%d") if raw_date.isdigit()
                 else datetime.fromisoformat(raw_date[:10])).date().isoformat()
            o, h, l, c = (float(x) for x in rec[2:6])
            v = float(rec[6]) if len(rec) > 6 and rec[6].strip() else 0.0
        except (ValueError, IndexError):
            continue
        if ticker != "VNINDEX" and c < 1_000:  # dữ liệu đơn vị nghìn đồng
            o, h, l, c = (x * 1_000 for x in (o, h, l, c))
        rows.append((ticker, d, o, h, l, c, v))
        counts[ticker] = counts.get(ticker, 0) + 1
    if not rows:
        raise ValueError("Không đọc được dòng dữ liệu hợp lệ nào trong file CSV.")
    db = get_db()
    with db._lock:  # noqa: SLF001 - ghi hàng loạt trong 1 transaction
        db._conn.executemany(
            "INSERT OR REPLACE INTO imported_prices(ticker,date,open,high,low,close,volume) "
            "VALUES(?,?,?,?,?,?,?)", rows)
        db._conn.commit()
    db.execute("DELETE FROM cache WHERE key LIKE 'hist:%'")
    return {"rows": len(rows), "tickers": counts}


def _imported_history(ticker: str) -> pd.DataFrame | None:
    rows = get_db().query(
        "SELECT date, open, high, low, close, volume FROM imported_prices WHERE ticker=? ORDER BY date",
        (ticker,))
    if len(rows) < 30:
        return None
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _finalize(df: pd.DataFrame, source: str) -> pd.DataFrame:
    df = (df.dropna(subset=["close"]).drop_duplicates("date").sort_values("date")
          .set_index("date"))
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    df.attrs["source"] = source
    return df


def get_history(ticker: str, days: int = 750) -> pd.DataFrame:
    """Lịch sử giá ngày (OHLCV, đơn vị VND). `df.attrs['source']` cho biết nguồn dữ liệu."""
    ticker = ticker.upper().strip()
    db = get_db()
    key = f"hist:{ticker}:{days}:{settings.data_mode}"
    cached = db.cache_get(key)
    if cached:
        df = pd.DataFrame(cached["rows"])
        df["date"] = pd.to_datetime(df["date"])
        return _finalize(df, cached["source"])

    df, source = None, None
    imported = _imported_history(ticker)
    if imported is not None:
        df, source = imported.tail(days), SOURCE_IMPORTED
    elif settings.data_mode in {"auto", "live"}:
        end = date.today()
        start = end - timedelta(days=int(days * 1.5))
        try:
            df, source, _ = fetch_live(ticker, start, end)
        except DataUnavailable:
            if settings.data_mode == "live":
                raise
    if df is None:
        df, source = _demo_history(ticker, n=days), SOURCE_DEMO

    df = df.tail(days).reset_index(drop=True)  # mọi nguồn đều có cột "date"
    ttl = settings.price_cache_ttl if source != SOURCE_DEMO else 3600
    records = [{**r, "date": pd.Timestamp(r["date"]).strftime("%Y-%m-%d")}
               for r in df[["date", "open", "high", "low", "close", "volume"]].to_dict("records")]
    db.cache_set(key, {"source": source, "rows": records}, ttl)
    return _finalize(df, source)


def latest_price(ticker: str) -> float:
    return float(get_history(ticker, days=60)["close"].iloc[-1])


def data_status() -> dict:
    """Trạng thái dữ liệu: chế độ, nguồn đang dùng, các nguồn tự động có truy cập được không."""
    t0 = time.time()
    df = get_history("VNINDEX", days=120)
    live = get_db().get_kv("live_status") or {}
    source = df.attrs.get("source")
    needs_manual = settings.data_mode != "demo" and source == SOURCE_DEMO
    return {
        "mode": settings.data_mode, "source": source,
        "last_date": df.index[-1].strftime("%Y-%m-%d"), "latency_ms": int((time.time() - t0) * 1000),
        "live_ok": bool(live.get("ok")), "live_provider": live.get("provider"),
        "providers": [{"key": k, "name": v[0]} for k, v in LIVE_PROVIDERS.items()],
        "provider_health": get_db().get_kv("provider_health"),
        "needs_manual_input": needs_manual,
        "message": ("Không truy cập được các nguồn tự động (VNDirect, SSI, TCBS, VPS, Vietstock, CafeF). "
                    "Ứng dụng đang dùng dữ liệu DEMO - hãy tải file Excel/CSV giá & BCTC để phân tích sát thực tế."
                    if needs_manual else
                    "Đang dùng dữ liệu mô phỏng (DATA_MODE=demo)." if source == SOURCE_DEMO else
                    f"Dữ liệu tự động từ nguồn {source}."),
    }
