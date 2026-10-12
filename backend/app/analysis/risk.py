"""Mức sinh lời và rủi ro (PTVĐTCK - Chương 2) + các thước đo rủi ro hiện đại.

- Mức sinh lời: r = (P1 - P0 + D1) / P0 = tỷ lệ cổ tức + tỷ suất lãi vốn.
- Sinh lời lũy kế: R(t) = (1+R1)(1+R2)...(1+Rt) - 1; bình quân hình học = (1+R(t))^(1/t) - 1.
- Bình quân số học = ΣRi / t.
- Sinh lời kỳ vọng theo kịch bản: k = Σ ki·Pi; phương sai σ² = Σ (ki - k)²·Pi.
- Rủi ro hệ thống (beta, thị trường) và phi hệ thống (đặc thù doanh nghiệp).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

TRADING_DAYS = 252
RISK_FREE = 0.03  # lãi suất phi rủi ro tham chiếu (TPCP ~3%/năm)


def holding_period_return(p0: float, p1: float, dividend: float = 0.0) -> dict:
    """Ví dụ Chương 2: mua 95.000, cổ tức 15.000, bán 120.000 → r = 42,1%."""
    return {
        "dividend_yield": dividend / p0,
        "capital_gain_yield": (p1 - p0) / p0,
        "total_return": (p1 - p0 + dividend) / p0,
    }


def cumulative_return(returns: list[float]) -> float:
    return float(np.prod([1 + r for r in returns]) - 1)


def geometric_mean_return(returns: list[float]) -> float:
    """VD Chương 2: 11%, -5%, 9% → lũy kế 15%, bình quân hình học ≈ 4,7%/năm."""
    return float((1 + cumulative_return(returns)) ** (1 / len(returns)) - 1)


def arithmetic_mean_return(returns: list[float]) -> float:
    return float(np.mean(returns))


def scenario_analysis(price0: float, scenarios: list[dict]) -> dict:
    """Sinh lời kỳ vọng theo kịch bản: [{'prob':0.3,'price':40000,'dividend':6000}, ...]."""
    ks = [(s["price"] - price0 + s.get("dividend", 0)) / price0 for s in scenarios]
    ps = [s["prob"] for s in scenarios]
    if abs(sum(ps) - 1) > 1e-6:
        raise ValueError("Tổng xác suất các kịch bản phải bằng 1")
    k = sum(ki * pi for ki, pi in zip(ks, ps))
    var = sum((ki - k) ** 2 * pi for ki, pi in zip(ks, ps))
    sd = math.sqrt(var)
    return {"returns": ks, "expected_return": k, "variance": var, "std_dev": sd,
            "range": [k - sd, k + sd], "cv": sd / k if k else None}


def max_drawdown(prices: pd.Series) -> dict:
    peak = prices.cummax()
    dd = prices / peak - 1
    trough = dd.idxmin()
    peak_date = prices.loc[:trough].idxmax()
    return {"max_drawdown": float(dd.min()), "peak_date": str(peak_date.date()),
            "trough_date": str(trough.date()), "current_drawdown": float(dd.iloc[-1])}


def metrics(prices: pd.Series, market: pd.Series | None = None, rf: float = RISK_FREE) -> dict:
    """Thước đo rủi ro/lợi nhuận từ chuỗi giá đóng cửa (ngày)."""
    rets = prices.pct_change().dropna()
    n_years = max(len(rets) / TRADING_DAYS, 1e-9)
    total = float(prices.iloc[-1] / prices.iloc[0] - 1)
    cagr = (1 + total) ** (1 / n_years) - 1
    vol = float(rets.std() * math.sqrt(TRADING_DAYS))
    downside = rets[rets < 0].std() * math.sqrt(TRADING_DAYS)
    ann_mean = float(rets.mean() * TRADING_DAYS)
    var95 = float(np.percentile(rets, 5))
    cvar95 = float(rets[rets <= var95].mean()) if (rets <= var95).any() else var95
    out = {
        "period_years": round(n_years, 2),
        "total_return": total,
        "cagr": cagr,
        "annual_mean_return": ann_mean,
        "volatility": vol,
        "sharpe": (cagr - rf) / vol if vol else None,
        "sortino": (cagr - rf) / downside if downside else None,
        "var_95_daily": var95,
        "cvar_95_daily": cvar95,
        **max_drawdown(prices),
    }
    if market is not None:
        m = market.pct_change().dropna()
        joined = pd.concat([rets, m], axis=1, join="inner").dropna()
        if len(joined) > 30:
            cov = np.cov(joined.iloc[:, 0], joined.iloc[:, 1])
            beta = float(cov[0, 1] / cov[1, 1])
            corr = float(np.corrcoef(joined.iloc[:, 0], joined.iloc[:, 1])[0, 1])
            m_years = len(joined) / TRADING_DAYS
            # cùng cửa sổ thời gian với cổ phiếu
            m_cagr = float((1 + joined.iloc[:, 1]).prod() ** (1 / max(m_years, 1e-9)) - 1)
            # CAPM: E(R) = rf + β (Rm - rf); alpha Jensen = R - E(R)
            capm = rf + beta * (m_cagr - rf)
            systematic_share = corr ** 2
            out.update({
                "beta": beta, "correlation": corr, "market_cagr": m_cagr,
                "capm_expected_return": capm, "jensen_alpha": cagr - capm,
                "systematic_risk_share": systematic_share,
                "unsystematic_risk_share": 1 - systematic_share,
            })
    return out


def risk_level(vol: float, mdd: float) -> str:
    if vol < 0.22 and mdd > -0.25:
        return "Thấp"
    if vol < 0.35 and mdd > -0.40:
        return "Trung bình"
    return "Cao"
