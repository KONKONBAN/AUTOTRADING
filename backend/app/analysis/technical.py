"""Tổng hợp phân tích kỹ thuật → điểm kỹ thuật (0-100) và tín hiệu."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import indicators as ind


def _f(x) -> float | None:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def compute_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Tính toàn bộ chỉ báo trên khung OHLCV."""
    out = df.copy()
    c = df["close"]
    for n in (10, 20, 50, 100, 200):
        out[f"sma{n}"] = ind.sma(c, n)
    out["ema12"], out["ema26"] = ind.ema(c, 12), ind.ema(c, 26)
    out = out.join(ind.macd(c))
    out["rsi"] = ind.rsi(c)
    out = out.join(ind.bollinger(c).add_prefix("bb_"))
    out["atr"] = ind.atr(df)
    out = out.join(ind.stochastic(df).add_prefix("stoch_"))
    out = out.join(ind.adx(df))
    out["obv"] = ind.obv(df)
    out["mfi"] = ind.mfi(df)
    out = out.join(ind.ichimoku(df))
    out["vol_ma20"] = ind.sma(df["volume"], 20)
    return out


SIGNAL_LABELS = [
    (75, "MUA MẠNH", "strong_buy"),
    (60, "MUA", "buy"),
    (45, "THEO DÕI / NẮM GIỮ", "hold"),
    (30, "BÁN", "sell"),
    (0, "BÁN MẠNH", "strong_sell"),
]


def label_for(score: float) -> tuple[str, str]:
    for threshold, label, code in SIGNAL_LABELS:
        if score >= threshold:
            return label, code
    return SIGNAL_LABELS[-1][1], SIGNAL_LABELS[-1][2]


def analyze(df: pd.DataFrame) -> dict:
    """Phân tích kỹ thuật phiên gần nhất. Trả về điểm, các tín hiệu thành phần và mức giá quan trọng."""
    f = compute_frame(df)
    last, prev = f.iloc[-1], f.iloc[-2]
    price = float(last["close"])
    signals: list[dict] = []

    def add(name: str, value, score: float, weight: float, note: str, unit: str | None = None) -> None:
        signals.append({"name": name, "value": value, "score": score, "weight": weight, "note": note, "unit": unit})

    # 1) Xu hướng - đường trung bình
    if _f(last["sma200"]) is not None:
        above200 = price > last["sma200"]
        add("Giá so với MA200", round(price / last["sma200"] - 1, 4), 1 if above200 else -1, 2.0,
            "Trên MA200: xu hướng dài hạn tăng" if above200 else "Dưới MA200: xu hướng dài hạn giảm", unit="pct")
    if _f(last["sma50"]) is not None:
        above50 = price > last["sma50"]
        add("Giá so với MA50", round(price / last["sma50"] - 1, 4), 1 if above50 else -1, 1.5,
            "Trên MA50: trung hạn tích cực" if above50 else "Dưới MA50: trung hạn tiêu cực", unit="pct")
    if _f(last["sma50"]) is not None and _f(last["sma200"]) is not None:
        golden = last["sma50"] > last["sma200"]
        crossed = (prev["sma50"] <= prev["sma200"]) != (last["sma50"] <= last["sma200"])
        note = ("Golden cross MA50/MA200" if golden else "Death cross MA50/MA200") + (" (vừa xảy ra)" if crossed else "")
        add("MA50 vs MA200", "golden" if golden else "death", 1 if golden else -1, 1.5, note)
    if _f(last["sma20"]) is not None:
        slope20 = f["sma20"].iloc[-1] / f["sma20"].iloc[-6] - 1
        add("Độ dốc MA20 (5 phiên)", round(float(slope20), 4), float(np.tanh(slope20 * 60)), 1.0,
            "MA20 hướng lên" if slope20 > 0 else "MA20 hướng xuống", unit="pct")

    # 2) Động lượng
    if _f(last["macd"]) is not None and _f(last["signal"]) is not None:
        bull = last["macd"] > last["signal"]
        cross = (prev["macd"] <= prev["signal"]) != (last["macd"] <= last["signal"])
        add("MACD (12,26,9)", round(float(last["hist"]), 2), 1 if bull else -1, 1.5,
            ("MACD cắt lên Signal" if bull else "MACD cắt xuống Signal") if cross
            else ("MACD trên Signal" if bull else "MACD dưới Signal"))
    r = _f(last["rsi"])
    if r is not None:
        if r >= 70:
            s, note = -0.5, "Quá mua (>70) - rủi ro điều chỉnh"
        elif r <= 30:
            s, note = 0.5, "Quá bán (<30) - có thể hồi phục"
        elif r >= 50:
            s, note = 0.6, "RSI > 50: động lượng tích cực"
        else:
            s, note = -0.6, "RSI < 50: động lượng yếu"
        add("RSI (14)", round(r, 1), s, 1.0, note)
    k, d = _f(last["stoch_k"]), _f(last["stoch_d"])
    if k is not None and d is not None:
        s = 0.5 if k > d else -0.5
        if k < 20 and k > d:
            s = 1.0
        if k > 80 and k < d:
            s = -1.0
        add("Stochastic (14,3)", round(k, 1), s, 0.7, "%K trên %D" if k > d else "%K dưới %D")

    # 3) Sức mạnh xu hướng
    a = _f(last["adx"])
    if a is not None:
        direction = 1 if last["plus_di"] > last["minus_di"] else -1
        strength = min(a / 40, 1.0)
        add("ADX (14)", round(a, 1), direction * strength, 1.0,
            f"{'Xu hướng mạnh' if a >= 25 else 'Xu hướng yếu/đi ngang'} - "
            f"{'+DI > -DI (bên mua)' if direction > 0 else '-DI > +DI (bên bán)'}")

    # 4) Biến động - Bollinger
    pb = _f(last["bb_pct_b"])
    if pb is not None:
        if pb > 1:
            s, note = -0.3, "Vượt dải trên Bollinger - quá nóng"
        elif pb < 0:
            s, note = 0.3, "Thủng dải dưới Bollinger - quá bán"
        else:
            s, note = (pb - 0.5), "Trong dải Bollinger"
        add("Bollinger %B", round(pb, 2), s, 0.6, note)

    # 5) Dòng tiền / khối lượng
    m = _f(last["mfi"])
    if m is not None:
        add("MFI (14)", round(m, 1), float(np.clip((m - 50) / 30, -1, 1)), 0.7,
            "Dòng tiền vào" if m > 50 else "Dòng tiền ra")
    if _f(last["vol_ma20"]):
        vr = float(last["volume"] / last["vol_ma20"])
        up_day = last["close"] >= prev["close"]
        s = float(np.tanh((vr - 1))) * (1 if up_day else -1)
        add("Khối lượng / TB20", round(vr, 2), s, 0.8,
            f"KL {'cao' if vr > 1.2 else 'thấp' if vr < 0.8 else 'bình thường'} trong phiên "
            f"{'tăng' if up_day else 'giảm'}")
    obv_slope = f["obv"].iloc[-1] - f["obv"].iloc[-20] if len(f) > 20 else 0
    add("OBV (20 phiên)", None, 0.5 if obv_slope > 0 else -0.5, 0.6,
        "OBV tăng - tích lũy" if obv_slope > 0 else "OBV giảm - phân phối")

    # 6) Ichimoku
    sa, sb = _f(last["span_a"]), _f(last["span_b"])
    if sa is not None and sb is not None:
        top, bottom = max(sa, sb), min(sa, sb)
        s = 1 if price > top else -1 if price < bottom else 0
        add("Ichimoku Cloud", None, s, 1.0,
            "Giá trên mây" if s > 0 else "Giá dưới mây" if s < 0 else "Giá trong mây (tích lũy)")

    patterns = ind.candlestick_patterns(df)
    for p in patterns:
        bias = {"bullish": 0.6, "bearish": -0.6}.get(p["bias"], 0)
        if bias:
            add(f"Mô hình nến: {p['name']}", None, bias, 0.5, p["note"])

    total_w = sum(s["weight"] for s in signals) or 1
    raw = sum(s["score"] * s["weight"] for s in signals) / total_w  # [-1, 1]
    score = round(50 + 50 * raw, 1)
    label, code = label_for(score)

    atr_v = _f(last["atr"]) or price * 0.02
    levels = ind.support_resistance(df)
    hi52 = float(df["high"].tail(250).max())
    lo52 = float(df["low"].tail(250).min())
    perf = {f"{n}d": _f(price / df["close"].iloc[-n - 1] - 1) if len(df) > n else None
            for n in (5, 20, 60, 120, 250)}
    trend = ("Tăng" if _f(last["sma50"]) and price > last["sma50"] and last["sma50"] > (last["sma200"] if _f(last["sma200"]) else 0)
             else "Giảm" if _f(last["sma50"]) and price < last["sma50"] and (not _f(last["sma200"]) or last["sma50"] < last["sma200"])
             else "Đi ngang")
    return {
        "score": score,
        "signal": label,
        "signal_code": code,
        "trend": trend,
        "price": price,
        "change_pct": _f(price / prev["close"] - 1),
        "atr": atr_v,
        "atr_pct": atr_v / price,
        "signals": signals,
        "patterns": patterns,
        "levels": {**levels, "high_52w": hi52, "low_52w": lo52},
        "performance": perf,
        "indicators": {
            k: _f(last[k]) for k in ("sma20", "sma50", "sma200", "rsi", "macd", "signal", "hist",
                                     "bb_upper", "bb_mid", "bb_lower", "atr", "adx", "mfi",
                                     "stoch_k", "stoch_d", "tenkan", "kijun")
        },
    }


def chart_series(df: pd.DataFrame, limit: int = 400) -> dict:
    """Chuỗi dữ liệu cho biểu đồ nến + chỉ báo trên giao diện."""
    f = compute_frame(df).tail(limit)
    t = [d.strftime("%Y-%m-%d") for d in f.index]

    def series(col: str) -> list:
        return [{"time": ti, "value": round(float(v), 4)} for ti, v in zip(t, f[col]) if pd.notna(v)]

    candles = [{"time": ti, "open": float(r.open), "high": float(r.high), "low": float(r.low),
                "close": float(r.close)} for ti, r in zip(t, f.itertuples())]
    volume = [{"time": ti, "value": float(r.volume),
               "up": bool(r.close >= r.open)} for ti, r in zip(t, f.itertuples())]
    return {
        "candles": candles, "volume": volume,
        "sma20": series("sma20"), "sma50": series("sma50"), "sma200": series("sma200"),
        "bb_upper": series("bb_upper"), "bb_lower": series("bb_lower"),
        "rsi": series("rsi"), "macd": series("macd"), "macd_signal": series("signal"),
        "macd_hist": series("hist"),
    }


def vector_score(f: pd.DataFrame) -> pd.Series:
    """Điểm kỹ thuật dạng vector (0-100) cho backtest - xấp xỉ nhanh của `analyze`."""
    c = f["close"]
    parts = [
        (np.where(c > f["sma200"], 1, -1), 2.0),
        (np.where(c > f["sma50"], 1, -1), 1.5),
        (np.where(f["sma50"] > f["sma200"], 1, -1), 1.5),
        (np.tanh((f["sma20"] / f["sma20"].shift(5) - 1) * 60), 1.0),
        (np.where(f["macd"] > f["signal"], 1, -1), 1.5),
        (np.select([f["rsi"] >= 70, f["rsi"] <= 30, f["rsi"] >= 50], [-0.5, 0.5, 0.6], -0.6), 1.0),
        (np.where(f["plus_di"] > f["minus_di"], 1, -1) * np.clip(f["adx"] / 40, 0, 1), 1.0),
        (np.clip((f["mfi"] - 50) / 30, -1, 1), 0.7),
    ]
    total_w = sum(w for _, w in parts)
    raw = sum(np.nan_to_num(np.asarray(v, dtype=float)) * w for v, w in parts) / total_w
    score = pd.Series(50 + 50 * raw, index=f.index)
    return score.where(f["sma200"].notna())
