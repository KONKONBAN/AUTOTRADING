"""Mô hình dự báo thời điểm thị trường (Market-Timing) cho VN-Index.

Theo file "Analysis of Market-Timing Forecast for VN-INDEX": mô hình xu hướng log-tuyến tính
    lnP_t = a + b·t + u_t
ước lượng trên cửa sổ trượt. Trong đó:
- b (độ dốc) = tốc độ tăng trưởng xu hướng mỗi phiên (năm hóa ≈ e^(252·b) − 1),
- u = độ lệch giá khỏi xu hướng (dương: giá cao hơn xu hướng / quá nóng; âm: dưới xu hướng),
- d(b), d(a) = thay đổi của độ dốc/hệ số chặn → tín hiệu tăng tốc hoặc suy yếu của xu hướng.

Kết hợp với "ngày phân phối" (giảm > 0,2% kèm khối lượng tăng) để nhận diện thị trường chung
đang phân phối - một trong các tình huống nên BÁN (PTVĐTCK - Chương 2.1).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import indicators as ind


def rolling_trend(close: pd.Series, window: int = 120) -> pd.DataFrame:
    lnp = np.log(close.values)
    n = len(lnp)
    a = np.full(n, np.nan)
    b = np.full(n, np.nan)
    u = np.full(n, np.nan)
    t = np.arange(window, dtype=float)
    t_mean = t.mean()
    sxx = ((t - t_mean) ** 2).sum()
    for i in range(window - 1, n):
        y = lnp[i - window + 1:i + 1]
        bi = ((t - t_mean) * (y - y.mean())).sum() / sxx
        ai = y.mean() - bi * t_mean
        a[i], b[i] = ai, bi
        u[i] = y[-1] - (ai + bi * t[-1])
    out = pd.DataFrame({"lnP": lnp, "a": a, "b": b, "u": u}, index=close.index)
    out["db"] = out["b"].diff(20)
    out["u_z"] = (out["u"] - out["u"].rolling(250, min_periods=60).mean()) / \
        out["u"].rolling(250, min_periods=60).std()
    out["trend_annual"] = np.exp(out["b"] * 252) - 1
    return out


def distribution_days(df: pd.DataFrame, lookback: int = 25) -> int:
    d = df.tail(lookback + 1)
    chg = d["close"].pct_change()
    vol_up = d["volume"] > d["volume"].shift(1)
    return int(((chg < -0.002) & vol_up).sum())


def analyze(df: pd.DataFrame, window: int = 120) -> dict:
    """Trạng thái thị trường chung + tỷ trọng cổ phiếu khuyến nghị."""
    close = df["close"]
    tr = rolling_trend(close, window)
    last = tr.iloc[-1]
    ma50, ma200 = ind.sma(close, 50).iloc[-1], ind.sma(close, 200).iloc[-1]
    price = float(close.iloc[-1])
    dist = distribution_days(df)
    rsi = float(ind.rsi(close).iloc[-1])

    # Hồi quy toàn mẫu: tăng trưởng dài hạn
    t = np.arange(len(close))
    b_full, a_full = np.polyfit(t, np.log(close.values), 1)

    score = 0.0
    score += 1.5 if last["b"] > 0 else -1.5
    score += 1.0 if (last["db"] or 0) > 0 else -1.0
    score += 1.0 if price > ma50 else -1.0
    score += 1.0 if (not np.isnan(ma200) and price > ma200) else -1.0
    score += -1.0 if dist >= 6 else (-0.5 if dist >= 4 else 0.5)
    uz = last["u_z"] if not np.isnan(last["u_z"]) else 0.0
    score += -0.5 if uz > 2 else (0.5 if uz < -2 else 0)

    if score >= 3:
        regime, exposure = "UPTREND - Xu hướng tăng xác nhận", 0.9
    elif score >= 1:
        regime, exposure = "TĂNG THẬN TRỌNG - Xu hướng tăng chịu áp lực", 0.65
    elif score > -1:
        regime, exposure = "ĐI NGANG / TÍCH LŨY", 0.45
    elif score > -3:
        regime, exposure = "PHÂN PHỐI - Rủi ro điều chỉnh", 0.25
    else:
        regime, exposure = "DOWNTREND - Ưu tiên bảo toàn vốn", 0.1

    notes = []
    if dist >= 5:
        notes.append(f"{dist} ngày phân phối trong 25 phiên: thị trường chung có dấu hiệu phân phối → hạn chế mua mới.")
    if last["b"] > 0 and (last["db"] or 0) < 0:
        notes.append("Xu hướng tăng đang chậm lại (độ dốc b giảm).")
    if last["b"] < 0 and (last["db"] or 0) > 0:
        notes.append("Xu hướng giảm đang yếu đi (độ dốc b tăng) - theo dõi điểm đảo chiều.")
    if uz > 2:
        notes.append("Giá lệch xa trên đường xu hướng (u cao) - thị trường quá nóng.")
    if uz < -2:
        notes.append("Giá lệch xa dưới đường xu hướng (u thấp) - vùng quá bán, cơ hội tích lũy dần.")

    hist = tr.tail(250)
    return {
        "price": price, "change_pct": float(close.pct_change().iloc[-1]),
        "regime": regime, "score": round(score, 2), "recommended_exposure": exposure,
        "trend_slope_b": float(last["b"]), "trend_annualized": float(last["trend_annual"]),
        "slope_change_db": float(last["db"]) if not np.isnan(last["db"]) else None,
        "deviation_u": float(last["u"]), "deviation_z": float(uz),
        "ma50": float(ma50), "ma200": float(ma200) if not np.isnan(ma200) else None,
        "rsi": rsi, "distribution_days": dist,
        "long_run": {"a": float(a_full), "b": float(b_full),
                     "cagr": float(np.exp(b_full * 252) - 1)},
        "notes": notes,
        "model": f"lnP_t = a + b·t + u_t (cửa sổ {window} phiên)",
        "history": [{"time": d.strftime("%Y-%m-%d"), "close": float(c),
                     "trend": float(np.exp(r.a + r.b * (window - 1))) if not np.isnan(r.b) else None,
                     "b_annual": float(r.trend_annual) if not np.isnan(r.trend_annual) else None}
                    for d, c, r in zip(hist.index, close.tail(250), hist.itertuples())],
    }
