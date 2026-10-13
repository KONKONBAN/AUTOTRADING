"""Nguồn dữ liệu giá cổ phiếu.

Thứ tự ưu tiên:
1. Dữ liệu người dùng tự nhập (CSV/Excel: Amibroker, CafeF, Vietstock, investing.com…).
2. Dữ liệu thật - khi DATA_MODE = auto | live: SSI FastConnect / DNSE OpenAPI (chính thức, nếu có khóa) →
   KBS → Vietcap → VNDirect → CafeF.
3. Dữ liệu DEMO mô phỏng (có tính tất định theo mã) - chỉ khi DATA_MODE = demo, hoặc auto mà mọi nguồn đều lỗi.

Mọi kết quả đều kèm trường `source` để giao diện hiển thị rõ đang dùng dữ liệu gì.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from datetime import date, datetime, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd

from ..config import settings
from ..db import get_db
from . import http, universe

log = logging.getLogger(__name__)


SOURCE_IMPORTED = "imported"
SOURCE_DEMO = "demo"


class DataUnavailable(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Live providers - nhiều nguồn, tự động chuyển nguồn khi lỗi
# ---------------------------------------------------------------------------
VN_TZ = "Asia/Ho_Chi_Minh"
INDEX_SYMBOLS = {"VNINDEX", "HNXINDEX", "UPCOMINDEX", "VN30", "HNX30", "VN100"}


def is_index(ticker: str) -> bool:
    return ticker.upper() in INDEX_SYMBOLS


def _epoch(d: date, end_of_day: bool = False) -> int:
    """Mốc thời gian (giây) của một NGÀY theo giờ Việt Nam (UTC+7)."""
    ts = pd.Timestamp(datetime.combine(d, datetime.max.time() if end_of_day else datetime.min.time()), tz=VN_TZ)
    return int(ts.timestamp())


def _dates_from_epoch(values) -> pd.Series:
    """Epoch giây (UTC) → ngày giao dịch theo giờ Việt Nam. Không đổi múi giờ sẽ làm lệch ngày khi nguồn đánh
    dấu nến ngày lúc 00:00 giờ VN (= 17:00 UTC hôm trước)."""
    return (pd.to_datetime(pd.Series([int(float(x)) for x in values]), unit="s", utc=True)
            .dt.tz_convert(VN_TZ).dt.tz_localize(None).dt.normalize())


def _dates_from_text(values) -> pd.Series:
    """Chuỗi ngày/giờ đa định dạng: ISO (có/không múi giờ), dd/mm/yyyy, dd-mm-yyyy.

    Xử lý theo MẢNG (một lần cho cả chuỗi giá): phân tích từng dòng một tốn ~1 giây cho mỗi mã."""
    s = pd.Series([str(v).strip() for v in values], dtype=object)
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    if s.empty:
        return out
    dmy = s.str.extract(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})")
    is_dmy = dmy[0].notna()
    if is_dmy.any():
        iso = dmy[2][is_dmy] + "-" + dmy[1][is_dmy].str.zfill(2) + "-" + dmy[0][is_dmy].str.zfill(2)
        out[is_dmy] = pd.to_datetime(iso, format="%Y-%m-%d").to_numpy("datetime64[ns]")
    has_tz = ~is_dmy & s.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True)
    if has_tz.any():
        ts = pd.to_datetime(s[has_tz], utc=True, format="ISO8601").dt.tz_convert(VN_TZ).dt.tz_localize(None)
        out[has_tz] = ts.to_numpy("datetime64[ns]")
    plain = ~is_dmy & ~has_tz
    if plain.any():
        out[plain] = pd.to_datetime(s[plain], format="ISO8601").to_numpy("datetime64[ns]")
    return out.dt.normalize().reset_index(drop=True)


def _frame(dates: pd.Series, o, h, l, c, v, ticker: str, unit: float) -> pd.DataFrame:  # noqa: E741
    """Chuẩn hóa về VND. `unit`: hệ số nhân của nguồn (1 = VND, 1000 = nghìn đồng); chỉ số giữ nguyên điểm."""
    df = pd.DataFrame({"date": dates.values, "open": pd.to_numeric(pd.Series(o), errors="coerce"),
                       "high": pd.to_numeric(pd.Series(h), errors="coerce"),
                       "low": pd.to_numeric(pd.Series(l), errors="coerce"),
                       "close": pd.to_numeric(pd.Series(c), errors="coerce"),
                       "volume": pd.to_numeric(pd.Series(v), errors="coerce").fillna(0)})
    if not is_index(ticker) and unit != 1:
        df[["open", "high", "low", "close"]] *= unit
    df = df.dropna(subset=["close"]).sort_values("date").drop_duplicates("date", keep="last")
    if df.empty:
        raise DataUnavailable(f"Không có dữ liệu cho {ticker}")
    return df


def _udf(js, ticker: str, unit: float) -> pd.DataFrame:
    """Chuẩn TradingView UDF {s,t,o,h,l,c,v} (có thể lồng trong 'data')."""
    if isinstance(js, dict) and isinstance(js.get("data"), dict) and "t" in js["data"]:
        js = js["data"]
    if not isinstance(js, dict) or js.get("s") not in (None, "ok") or not js.get("t"):
        raise DataUnavailable(f"Không có dữ liệu cho {ticker}")
    n = len(js["t"])
    return _frame(_dates_from_epoch(js["t"]), js["o"], js["h"], js["l"], js["c"], js.get("v") or [0] * n,
                  ticker, unit)


# ---- KBS (KB Securities) - không cần khóa; giá cổ phiếu tính bằng VND, chỉ số bằng điểm ---------------
KBS_BASE = "https://kbbuddywts.kbsec.com.vn/iis-server/investment"


def _fetch_kbs(ticker: str, start: date, end: date) -> pd.DataFrame:
    path = f"index/{ticker}" if is_index(ticker) else f"stocks/{ticker}"
    js = http.get_json(f"{KBS_BASE}/{path}/data_day",
                       {"sdate": start.strftime("%d-%m-%Y"), "edate": end.strftime("%d-%m-%Y")})
    rows = (js or {}).get("data_day") if isinstance(js, dict) else None
    if not rows:
        raise DataUnavailable(f"KBS không có dữ liệu cho {ticker}")
    return _frame(_dates_from_text([r["t"] for r in rows]), [r.get("o") for r in rows], [r.get("h") for r in rows],
                  [r.get("l") for r in rows], [r.get("c") for r in rows], [r.get("v") or 0 for r in rows],
                  ticker, unit=1)


# ---- Vietcap (VCI) - không cần khóa; mỗi yêu cầu MỘT mã; VND / điểm; chặn IP máy chủ đám mây ------------
VCI_HEADERS = {"Referer": "https://trading.vietcap.com.vn/", "Origin": "https://trading.vietcap.com.vn"}
_VCI_INDEX = {"VNINDEX": "VNINDEX", "HNXINDEX": "HNXIndex", "UPCOMINDEX": "HNXUpcomIndex", "VN30": "VN30",
              "HNX30": "HNX30", "VN100": "VN100"}


def _fetch_vci(ticker: str, start: date, end: date) -> pd.DataFrame:
    symbol = _VCI_INDEX.get(ticker, ticker)
    count = int(np.busday_count(start, end + timedelta(days=1))) + 5
    js = http.post_json("https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart",
                        {"timeFrame": "ONE_DAY", "symbols": [symbol], "to": _epoch(end + timedelta(days=1)),
                         "countBack": count}, headers=VCI_HEADERS)
    items = js.get("data") if isinstance(js, dict) else js
    item = next((x for x in (items or []) if isinstance(x, dict) and x.get("t")), None)
    if not item:
        raise DataUnavailable(f"Vietcap không có dữ liệu cho {ticker}")
    df = _udf({**item, "s": "ok"}, ticker, unit=1)
    return df[df["date"] >= pd.Timestamp(start)]


# ---- VNDirect dchart - không cần khóa; giá tính bằng NGHÌN đồng ---------------------------------------
def _fetch_vndirect(ticker: str, start: date, end: date) -> pd.DataFrame:
    js = http.get_json("https://dchart-api.vndirect.com.vn/dchart/history",
                       {"resolution": "D", "symbol": ticker, "from": _epoch(start), "to": _epoch(end, True)})
    return _udf(js, ticker, unit=1000)


# ---- CafeF - không cần khóa; nghìn đồng; có GIÁ ĐIỀU CHỈNH (cổ tức, chia tách) -------------------------
def _fetch_cafef(ticker: str, start: date, end: date) -> pd.DataFrame:
    rows: list[dict] = []
    for page in range(1, 11):  # phân trang - mỗi trang tối đa 1.000 phiên
        js = http.get_json("https://s.cafef.vn/Ajax/PageNew/DataHistory/PriceHistory.ashx",
                           {"Symbol": ticker, "StartDate": start.strftime("%Y-%m-%d"),
                            "EndDate": end.strftime("%Y-%m-%d"), "PageIndex": page, "PageSize": 1000})
        batch = ((js or {}).get("Data") or {}).get("Data") or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
    if not rows:
        raise DataUnavailable(f"CafeF không có dữ liệu cho {ticker}")

    def col(k):
        return pd.to_numeric(pd.Series([r.get(k) for r in rows]), errors="coerce")
    raw_close = col("GiaDongCua")
    adj_close = col("GiaDieuChinh").fillna(raw_close)
    factor = (adj_close / raw_close).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    df = _frame(_dates_from_text([r["Ngay"] for r in rows]), col("GiaMoCua") * factor, col("GiaCaoNhat") * factor,
                col("GiaThapNhat") * factor, adj_close, col("KhoiLuongKhopLenh").fillna(0), ticker, unit=1000)
    df.attrs["adjusted"] = True
    return df


# ---- SSI FastConnect v3 (CHÍNH THỨC, cần khóa) --------------------------------------------------------
SSI_BASE = "https://api.ssi.com.vn"
_ssi_token: dict = {"token": None, "exp": 0.0}


def _ssi_auth() -> str:
    if _ssi_token["token"] and _ssi_token["exp"] - 60 > time.time():
        return _ssi_token["token"]
    js = http.post_json(f"{SSI_BASE}/api/v3/auth/token",
                        {"apiKey": settings.ssi_api_key, "apiSecret": settings.ssi_api_secret})
    data = js.get("data", js) if isinstance(js, dict) else {}
    token = data.get("accessToken")
    if not token:
        raise DataUnavailable("SSI từ chối khóa API (kiểm tra SSI_API_KEY / SSI_API_SECRET)")
    exp = float(data.get("expiresAt") or 0)
    _ssi_token.update(token=token, exp=exp / 1000 if exp > 1e12 else exp or time.time() + 3000)
    return token


def _fetch_ssi(ticker: str, start: date, end: date) -> pd.DataFrame:
    if not (settings.ssi_api_key and settings.ssi_api_secret):
        raise DataUnavailable("Chưa cấu hình khóa SSI FastConnect")
    headers = {"Authorization": f"Bearer {_ssi_auth()}", "Content-Type": "application/json"}
    rows: list[dict] = []
    for page in range(1, 11):
        js = http.get_json(f"{SSI_BASE}/api/v3/data/ohlc",
                           {"symbol": ticker, "from": start.strftime("%Y/%m/%d 00:00:00"),
                            "to": end.strftime("%Y/%m/%d 23:59:59"), "timeFrame": "1d",
                            "pageIndex": page, "pageSize": 1000}, headers=headers)
        batch = (js or {}).get("data") or []
        if isinstance(batch, dict):
            batch = batch.get("items") or batch.get("data") or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
    if not rows:
        raise DataUnavailable(f"SSI không có dữ liệu cho {ticker}")

    def pick(r, *keys):
        return next((r[k] for k in keys if r.get(k) is not None), None)
    closes = pd.to_numeric(pd.Series([pick(r, "close", "Close") for r in rows]), errors="coerce")
    unit = 1000 if (not is_index(ticker) and closes.median() < 500) else 1  # tài liệu không ghi đơn vị
    return _frame(_dates_from_text([pick(r, "tradingDate", "TradingDate") for r in rows]),
                  [pick(r, "open", "Open") for r in rows], [pick(r, "high", "High") for r in rows],
                  [pick(r, "low", "Low") for r in rows], closes, [pick(r, "volume", "Volume") or 0 for r in rows],
                  ticker, unit)


# ---- DNSE OpenAPI (CHÍNH THỨC, cần khóa; yêu cầu ký HMAC; giá nghìn đồng) -----------------------------
DNSE_BASE = "https://openapi.dnse.com.vn"


def _dnse_headers(path: str) -> dict:
    import base64
    import hmac
    import uuid as _uuid
    from email.utils import formatdate
    from urllib.parse import quote
    date_hdr = formatdate(usegmt=True)
    nonce = _uuid.uuid4().hex
    to_sign = f"(request-target): get {path}\ndate: {date_hdr}\nnonce: {nonce}"
    sig = base64.b64encode(hmac.new(settings.dnse_api_secret.encode(), to_sign.encode(), "sha256").digest()).decode()
    return {"Date": date_hdr, "x-api-key": settings.dnse_api_key, "version": "2026-07-23",
            "X-Signature": (f'Signature keyId="{settings.dnse_api_key}",algorithm="hmac-sha256",'
                            f'headers="(request-target) date",signature="{quote(sig, safe="")}",nonce="{nonce}"')}


def _fetch_dnse(ticker: str, start: date, end: date) -> pd.DataFrame:
    if not (settings.dnse_api_key and settings.dnse_api_secret):
        raise DataUnavailable("Chưa cấu hình khóa DNSE OpenAPI")
    js = http.get_json(f"{DNSE_BASE}/price/ohlc",
                       {"type": "INDEX" if is_index(ticker) else "STOCK", "symbol": ticker, "resolution": "1D",
                        "from": _epoch(start), "to": _epoch(end, True)}, headers=_dnse_headers("/price/ohlc"))
    return _udf(js, ticker, unit=1000)


# Thứ tự mặc định: nguồn CHÍNH THỨC (nếu đã cấu hình khóa) → nguồn công khai đang hoạt động 2026.
# (TCBS, Vietstock, VPS, SSI iBoard đã bị loại: API công khai ngừng hoạt động hoặc yêu cầu phiên đăng nhập.)
LIVE_PROVIDERS = {
    "ssi": ("SSI FastConnect (chính thức)", _fetch_ssi),
    "dnse": ("DNSE OpenAPI (chính thức)", _fetch_dnse),
    "kbs": ("KB Securities (KBS)", _fetch_kbs),
    "vci": ("Vietcap (VCI)", _fetch_vci),
    "vndirect": ("VNDirect (dchart)", _fetch_vndirect),
    "cafef": ("CafeF", _fetch_cafef),
}
KEYED_PROVIDERS = {"ssi": ("ssi_api_key", "ssi_api_secret"), "dnse": ("dnse_api_key", "dnse_api_secret")}


def _configured(key: str) -> bool:
    need = KEYED_PROVIDERS.get(key)
    return not need or all(getattr(settings, k) for k in need)


def _provider_order() -> list[str]:
    preferred = get_db().get_kv("preferred_provider")
    order = [k for k in LIVE_PROVIDERS if _configured(k)]
    if preferred in order:
        order.remove(preferred)
        order.insert(0, preferred)
    return order


def fetch_live(ticker: str, start: date, end: date) -> tuple[pd.DataFrame, str, list[dict]]:
    """Thử lần lượt các nguồn; trả về (dữ liệu, tên nguồn, nhật ký các lần thử).
    Cả chuỗi lấy từ MỘT nguồn (không ghép nguồn: quy ước điều chỉnh giá có thể khác nhau)."""
    attempts = []
    for key in _provider_order():
        name, fn = LIVE_PROVIDERS[key]
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
            attempts.append({"provider": key, "ok": False, "error": str(exc)[:160],
                             "ms": int((time.time() - t0) * 1000)})
            log.info("Nguồn %s lỗi cho %s: %s", name, ticker, exc)
    get_db().set_kv("live_status", {"ok": False, "at": time.time(), "ticker": ticker, "attempts": attempts})
    raise DataUnavailable(f"Tất cả nguồn dữ liệu đều không truy cập được cho {ticker}")


def provider_health(ticker: str = "FPT") -> list[dict]:
    """Kiểm tra từng nguồn (trang Dữ liệu): giá đóng cửa gần nhất của các nguồn để tự đối chiếu."""
    http.reset_all()
    end = date.today()
    start = end - timedelta(days=90)
    out = []
    for key, (name, fn) in LIVE_PROVIDERS.items():
        t0 = time.time()
        if not _configured(key):
            out.append({"provider": key, "name": name, "ok": False, "skipped": True,
                        "error": "Chưa cấu hình khóa API (tùy chọn) - xem hướng dẫn trong file .env"})
            continue
        try:
            df = fn(ticker, start, end)
            out.append({"provider": key, "name": name, "ok": True, "rows": len(df),
                        "last_date": pd.Timestamp(df["date"].max()).strftime("%Y-%m-%d"),
                        "last_close": float(df.sort_values("date")["close"].iloc[-1]),
                        "adjusted": bool(df.attrs.get("adjusted")), "ms": int((time.time() - t0) * 1000)})
        except Exception as exc:  # noqa: BLE001
            out.append({"provider": key, "name": name, "ok": False, "error": str(exc)[:200],
                        "ms": int((time.time() - t0) * 1000)})
    closes = [r["last_close"] for r in out if r.get("ok")]
    if len(closes) >= 2:
        med = float(np.median(closes))
        for r in out:
            if r.get("ok"):
                r["diff_vs_median"] = r["last_close"] / med - 1  # lệch >1% → nghi ngờ đơn vị / điều chỉnh giá
    get_db().set_kv("provider_health", {"checked_at": time.time(), "results": out, "ticker": ticker})
    return out


# ---------------------------------------------------------------------------
# Demo generator (deterministic)
# ---------------------------------------------------------------------------
def _seed(text: str) -> int:
    return int(hashlib.md5(text.encode()).hexdigest()[:8], 16)


# Chuỗi DEMO được sinh một lần trên một lưới ngày cố định (2018 → 2036): mỗi phiên có một mức giá
# cố định, ngày mới chỉ nối thêm biến động mới (không "trôi" lịch sử), giá tại ngày neo = giá tham khảo.
DEMO_EPOCH = date(2018, 1, 1)
DEMO_HORIZON = date(2036, 12, 31)
DEMO_ANCHOR = pd.Timestamp(2026, 6, 30)
_DEMO_INDEX = pd.bdate_range(DEMO_EPOCH, DEMO_HORIZON)


@lru_cache(maxsize=1)
def _market_returns() -> np.ndarray:
    n = len(_DEMO_INDEX)
    rng = np.random.default_rng(_seed("VNINDEX-demo-epoch-16"))
    rets = np.empty(n)
    i = 0
    while i < n:
        length = int(rng.integers(40, 160))
        regime_drift = rng.normal(0.12, 0.22) / 252
        vol = rng.uniform(0.12, 0.24) / np.sqrt(252)
        rets[i:i + length] = rng.normal(regime_drift, vol, size=min(length, n - i))
        i += length
    return rets


def _round_ticks(prices: np.ndarray, exchange: str) -> np.ndarray:
    if exchange.upper() != "HOSE":
        step = np.full_like(prices, 100.0)
    else:
        step = np.where(prices < 10_000, 10.0, np.where(prices < 50_000, 50.0, 100.0))
    return np.round(prices / step) * step


@lru_cache(maxsize=256)
def _demo_full(ticker: str) -> pd.DataFrame:
    meta = universe.info(ticker)
    mkt = _market_returns()
    n = len(mkt)
    if ticker == "VNINDEX":
        rets = mkt.copy()
    else:
        rng = np.random.default_rng(_seed(ticker))
        beta = rng.uniform(0.6, 1.4)
        alpha = rng.normal(0.03, 0.08) / 252
        idio_vol = rng.uniform(0.12, 0.28) / np.sqrt(252)
        rets = alpha + beta * mkt + rng.normal(0, idio_vol, n)
    rets = np.clip(rets, -0.069, 0.069)  # biên độ HOSE ±7%
    path = np.exp(np.cumsum(rets))
    anchor_pos = max(int(_DEMO_INDEX.searchsorted(DEMO_ANCHOR, side="right")) - 1, 0)
    close = meta["reference_price"] * path / path[anchor_pos]
    rng = np.random.default_rng(_seed(ticker + "-ohlc"))
    prev_close = np.r_[close[0], close[:-1]]
    open_ = prev_close * (1 + rng.normal(0, 0.004, n))
    spread = np.abs(rng.normal(0, 0.006, n)) + np.abs(rets) * 0.25
    high = np.minimum(np.maximum(open_, close) * (1 + spread), prev_close * 1.069)
    low = np.maximum(np.minimum(open_, close) * (1 - spread), prev_close * 0.931)
    vol_base = 5e5 if ticker == "VNINDEX" else rng.uniform(1e6, 2e7)
    volume = (vol_base * np.exp(rng.normal(0, 0.35, n)) * (1 + 15 * np.abs(rets))).round()
    if ticker == "VNINDEX":
        open_, high, low, close = (np.round(x, 2) for x in (open_, high, low, close))
    else:
        open_, high, low, close = (_round_ticks(x, meta["exchange"]) for x in (open_, high, low, close))
        high = np.maximum.reduce([open_, high, close])
        low = np.minimum.reduce([open_, low, close])
    return pd.DataFrame({"date": _DEMO_INDEX, "open": open_, "high": high, "low": low,
                         "close": close, "volume": volume})


def _demo_history(ticker: str, n: int = 750, end: date | None = None) -> pd.DataFrame:
    end = pd.Timestamp(end or date.today())
    full = _demo_full(ticker.upper())
    return full[full["date"] <= end].tail(n).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Imported data (CSV)
# ---------------------------------------------------------------------------
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


CACHE_DAYS = 1500  # luôn lấy & cache một chuỗi dài cho mỗi mã, các cửa sổ ngắn hơn cắt đuôi từ đó
# Bộ nhớ đệm trong RAM: {khóa: (hết hạn, DataFrame)} - hợp lệ khi khớp đúng thời điểm hết hạn của bản ghi trong CSDL,
# nên mọi thao tác xóa cache trong CSDL (làm mới dữ liệu, nhập file giá…) tự động vô hiệu hóa bản trong RAM.
_frames: dict[str, tuple[float, pd.DataFrame]] = {}
_frames_lock = threading.Lock()


def _out(full: pd.DataFrame, days: int) -> pd.DataFrame:
    df = full.tail(days).copy()
    df.attrs = dict(full.attrs)
    return df


def _remember(key: str, expires: float, full: pd.DataFrame) -> None:
    with _frames_lock:
        if len(_frames) > 800:
            _frames.clear()
        _frames[key] = (expires, full)
DEMO_FALLBACK_TTL = 60  # DEMO dự phòng (khi nguồn thật lỗi) chỉ cache ngắn để nhanh chóng thử lại nguồn thật


def get_history(ticker: str, days: int = 750) -> pd.DataFrame:
    """Lịch sử giá ngày (OHLCV, đơn vị VND). `df.attrs['source']` cho biết nguồn dữ liệu."""
    ticker = ticker.upper().strip()
    db = get_db()
    fetch_days = max(days, CACHE_DAYS)
    key = f"hist:{ticker}:{fetch_days}:{settings.data_mode}"
    expires = db.cache_expiry(key)
    if expires:
        with _frames_lock:
            hit = _frames.get(key)
        if hit and hit[0] == expires:
            return _out(hit[1], days)
        entry = db.cache_entry(key)
        if entry:
            cached, expires = entry
            df = pd.DataFrame(cached["rows"])
            df["date"] = pd.to_datetime(df["date"])
            full = _finalize(df, cached["source"])
            _remember(key, expires, full)
            return _out(full, days)

    df, source = None, None
    imported = _imported_history(ticker)
    # File nhập tay được ưu tiên khi còn MỚI; file cũ (VD nhập để backtest) không được che giá thị trường hiện tại
    fresh = imported is not None and (
        settings.data_mode == "demo"
        or sessions_since(pd.Timestamp(imported["date"].iloc[-1]).date()) <= IMPORTED_FRESH_SESSIONS)
    if fresh:
        df, source = imported, SOURCE_IMPORTED
    elif settings.data_mode in {"auto", "live"}:
        end = date.today()
        start = end - timedelta(days=int(fetch_days * 1.5))
        try:
            df, source, _ = fetch_live(ticker, start, end)
        except DataUnavailable:
            if imported is not None:
                df, source = imported, SOURCE_IMPORTED  # nguồn tự động lỗi: file cũ vẫn hơn DEMO
            elif settings.data_mode == "live":
                raise
    elif imported is not None:
        df, source = imported, SOURCE_IMPORTED
    if df is None:
        df, source = _demo_history(ticker, n=fetch_days), SOURCE_DEMO

    # sắp xếp TRƯỚC khi cắt đuôi (một số nguồn trả về mới nhất trước)
    df = (df.dropna(subset=["close"]).sort_values("date").drop_duplicates("date", keep="last")
          .tail(fetch_days).reset_index(drop=True))
    if source != SOURCE_DEMO:
        ttl = settings.price_cache_ttl
    else:
        ttl = 3600 if settings.data_mode == "demo" else DEMO_FALLBACK_TTL
    records = [{**r, "date": pd.Timestamp(r["date"]).strftime("%Y-%m-%d")}
               for r in df[["date", "open", "high", "low", "close", "volume"]].to_dict("records")]
    expires = db.cache_set(key, {"source": source, "rows": records}, ttl)
    full = _finalize(df, source)
    _remember(key, expires, full)
    return _out(full, days)


def now_vn() -> datetime:
    """Giờ Việt Nam hiện tại (không kèm múi giờ) - máy chủ trên Internet thường chạy giờ UTC."""
    return pd.Timestamp.now(tz=VN_TZ).tz_localize(None).to_pydatetime()


def today_vn() -> date:
    """Ngày hiện tại theo giờ Việt Nam (máy tính có thể đặt múi giờ khác)."""
    return now_vn().date()


def sessions_since(last: date, today: date | None = None) -> int:
    """Số ngày làm việc (T2-T6) từ phiên `last` tới hôm nay - đo độ cũ của dữ liệu giá."""
    return int(np.busday_count(last, today or today_vn()))


IMPORTED_FRESH_SESSIONS = 5  # file giá nhập tay cũ hơn mức này → ưu tiên nguồn tự động (nếu có)


def is_tradeable_source(source: str | None) -> bool:
    """Chỉ cho phép đặt lệnh trên giá DEMO khi người dùng chủ động chọn DATA_MODE=demo."""
    return source != SOURCE_DEMO or settings.data_mode == "demo"


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
        "message": ("Không truy cập được các nguồn tự động (KBS, Vietcap, VNDirect, CafeF…). "
                    "Ứng dụng đang dùng dữ liệu DEMO - hãy kiểm tra kết nối Internet hoặc tải file Excel/CSV giá & BCTC."
                    if needs_manual else
                    "Đang dùng dữ liệu mô phỏng (DATA_MODE=demo)." if source == SOURCE_DEMO else
                    f"Dữ liệu tự động từ nguồn {source}."),
    }
