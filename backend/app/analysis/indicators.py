"""Các chỉ báo phân tích kỹ thuật (Module 2 - Phân tích kỹ thuật).

Tất cả hàm nhận pandas Series/DataFrame (OHLCV) và trả về Series/DataFrame cùng index.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rma(s: pd.Series, n: int) -> pd.Series:
    """Wilder's moving average (dùng cho RSI, ATR, ADX)."""
    return s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = rma(delta.clip(lower=0), n)
    loss = rma(-delta.clip(upper=0), n)
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.fillna(100.0).where(loss.notna())


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid = sma(close, n)
    std = close.rolling(n, min_periods=n).std(ddof=0)
    upper, lower = mid + k * std, mid - k * std
    return pd.DataFrame({"mid": mid, "upper": upper, "lower": lower,
                         "pct_b": (close - lower) / (upper - lower),
                         "bandwidth": (upper - lower) / mid})


def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["close"].shift(1)
    return pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(),
                      (df["low"] - prev).abs()], axis=1).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return rma(true_range(df), n)


def stochastic(df: pd.DataFrame, n: int = 14, d: int = 3) -> pd.DataFrame:
    low_n = df["low"].rolling(n, min_periods=n).min()
    high_n = df["high"].rolling(n, min_periods=n).max()
    k = 100 * (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan)
    return pd.DataFrame({"k": k, "d": k.rolling(d, min_periods=d).mean()})


def adx(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    tr = rma(true_range(df), n)
    plus_di = 100 * rma(plus_dm, n) / tr
    minus_di = 100 * rma(minus_dm, n) / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return pd.DataFrame({"adx": rma(dx, n), "plus_di": plus_di, "minus_di": minus_di})


def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff()).fillna(0)
    return (direction * df["volume"]).cumsum()


def mfi(df: pd.DataFrame, n: int = 14) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    flow = tp * df["volume"]
    pos = flow.where(tp > tp.shift(1), 0.0).rolling(n, min_periods=n).sum()
    neg = flow.where(tp < tp.shift(1), 0.0).rolling(n, min_periods=n).sum()
    return 100 - 100 / (1 + pos / neg.replace(0, np.nan))


def ichimoku(df: pd.DataFrame, t: int = 9, k: int = 26, s: int = 52) -> pd.DataFrame:
    def mid(n: int) -> pd.Series:
        return (df["high"].rolling(n).max() + df["low"].rolling(n).min()) / 2
    tenkan, kijun = mid(t), mid(k)
    return pd.DataFrame({"tenkan": tenkan, "kijun": kijun,
                         "span_a": ((tenkan + kijun) / 2).shift(k),
                         "span_b": mid(s).shift(k)})


def support_resistance(df: pd.DataFrame, lookback: int = 120, window: int = 5,
                       tolerance: float = 0.015) -> dict:
    """Tìm vùng hỗ trợ/kháng cự từ các đỉnh/đáy cục bộ (gom cụm theo % sai lệch)."""
    d = df.tail(lookback)
    highs, lows = d["high"].values, d["low"].values
    pivots = []
    for i in range(window, len(d) - window):
        if highs[i] == highs[i - window:i + window + 1].max():
            pivots.append(highs[i])
        if lows[i] == lows[i - window:i + window + 1].min():
            pivots.append(lows[i])
    pivots.sort()
    clusters: list[list[float]] = []
    for p in pivots:
        if clusters and abs(p - np.mean(clusters[-1])) / p <= tolerance:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    levels = sorted(((float(np.mean(c)), len(c)) for c in clusters), key=lambda x: -x[1])[:8]
    price = float(df["close"].iloc[-1])
    supports = sorted([lv for lv, _ in levels if lv < price], reverse=True)[:3]
    resistances = sorted([lv for lv, _ in levels if lv > price])[:3]
    return {"supports": supports, "resistances": resistances}


def candlestick_patterns(df: pd.DataFrame) -> list[dict]:
    """Nhận diện một số mô hình nến phổ biến ở phiên gần nhất."""
    if len(df) < 3:
        return []
    o, h, l, c = (df[k].values for k in ("open", "high", "low", "close"))
    i = len(df) - 1
    body = abs(c[i] - o[i])
    rng = max(h[i] - l[i], 1e-9)
    upper = h[i] - max(o[i], c[i])
    lower = min(o[i], c[i]) - l[i]
    trend_down = c[i - 1] < df["close"].iloc[-10:-1].mean() if len(df) > 10 else False
    trend_up = c[i - 1] > df["close"].iloc[-10:-1].mean() if len(df) > 10 else False
    out = []
    if body / rng < 0.1:
        out.append({"name": "Doji", "bias": "neutral", "note": "Thị trường lưỡng lự, chờ xác nhận."})
    if lower > 2 * body and upper < body and trend_down:
        out.append({"name": "Búa (Hammer)", "bias": "bullish", "note": "Tín hiệu đảo chiều tăng sau nhịp giảm."})
    if upper > 2 * body and lower < body and trend_up:
        out.append({"name": "Sao băng (Shooting Star)", "bias": "bearish", "note": "Cảnh báo đảo chiều giảm."})
    prev_body = abs(c[i - 1] - o[i - 1])
    if c[i] > o[i] and c[i - 1] < o[i - 1] and c[i] >= o[i - 1] and o[i] <= c[i - 1] and body > prev_body:
        out.append({"name": "Nhấn chìm tăng (Bullish Engulfing)", "bias": "bullish", "note": "Lực cầu áp đảo."})
    if c[i] < o[i] and c[i - 1] > o[i - 1] and o[i] >= c[i - 1] and c[i] <= o[i - 1] and body > prev_body:
        out.append({"name": "Nhấn chìm giảm (Bearish Engulfing)", "bias": "bearish", "note": "Lực cung áp đảo."})
    if len(df) >= 3 and all(c[j] > o[j] for j in (i - 2, i - 1, i)) and c[i] > c[i - 1] > c[i - 2]:
        out.append({"name": "Ba chàng lính trắng", "bias": "bullish", "note": "Xu hướng tăng được củng cố."})
    if len(df) >= 3 and all(c[j] < o[j] for j in (i - 2, i - 1, i)) and c[i] < c[i - 1] < c[i - 2]:
        out.append({"name": "Ba con quạ đen", "bias": "bearish", "note": "Xu hướng giảm được củng cố."})
    return out
