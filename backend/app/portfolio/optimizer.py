"""Xây dựng danh mục đầu tư tối ưu (Module 4) - lý thuyết danh mục Markowitz.

- Lợi nhuận kỳ vọng danh mục: E(Rp) = Σ wi·E(Ri)
- Phương sai danh mục: σp² = wᵀ Σ w  (đa dạng hóa giảm rủi ro phi hệ thống)
- Mục tiêu: tối đa hệ số Sharpe, hoặc tối thiểu phương sai, với ràng buộc tỷ trọng tối đa mỗi mã
  ("Đừng bao giờ đặt trứng vào một giỏ").
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from ..data import providers

TRADING_DAYS = 252


def _returns(tickers: list[str], days: int = 500) -> pd.DataFrame:
    closes = {t: providers.get_history(t, days=days)["close"] for t in tickers}
    return pd.DataFrame(closes).dropna().pct_change().dropna()


def _shrink_cov(rets: pd.DataFrame, delta: float = 0.2) -> np.ndarray:
    """Hiệp phương sai co rút (Ledoit-Wolf đơn giản) để ổn định nghiệm."""
    s = rets.cov().values * TRADING_DAYS
    target = np.diag(np.diag(s))
    return (1 - delta) * s + delta * target


def optimize(tickers: list[str], objective: str = "max_sharpe", max_weight: float = 0.25,
             min_weight: float = 0.0, rf: float = 0.03, expected: dict[str, float] | None = None,
             days: int = 500) -> dict:
    tickers = [t.upper() for t in dict.fromkeys(tickers)]
    if len(tickers) < 2:
        raise ValueError("Cần ít nhất 2 mã để tối ưu danh mục")
    max_weight = max(max_weight, 1 / len(tickers))
    rets = _returns(tickers, days)
    hist_mu = rets.mean().values * TRADING_DAYS
    # Kết hợp kỳ vọng từ mô hình định giá/điểm số (nếu có) với lịch sử để tránh "đuổi theo quá khứ"
    if expected:
        prior = np.array([expected.get(t, m) for t, m in zip(tickers, hist_mu)])
        mu = 0.6 * prior + 0.4 * hist_mu
    else:
        mu = hist_mu
    cov = _shrink_cov(rets)
    n = len(tickers)
    bounds = [(min_weight, max_weight)] * n
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1}]

    def port(w):
        r = float(w @ mu)
        v = float(np.sqrt(w @ cov @ w))
        return r, v

    if objective == "min_variance":
        fun = lambda w: w @ cov @ w  # noqa: E731
    else:
        fun = lambda w: -(port(w)[0] - rf) / max(port(w)[1], 1e-9)  # noqa: E731
    w0 = np.full(n, 1 / n)
    res = minimize(fun, w0, method="SLSQP", bounds=bounds, constraints=cons,
                   options={"maxiter": 500, "ftol": 1e-10})
    w = np.clip(res.x if res.success else w0, 0, 1)
    w = w / w.sum()
    r, v = port(w)
    eq_r, eq_v = port(w0)

    # Đường biên hiệu quả
    frontier = []
    for target in np.linspace(mu.min(), mu.max(), 15):
        c2 = cons + [{"type": "eq", "fun": lambda w, t=target: w @ mu - t}]
        rr = minimize(lambda w: w @ cov @ w, w0, method="SLSQP", bounds=bounds, constraints=c2)
        if rr.success:
            frontier.append({"return": float(target), "volatility": float(np.sqrt(rr.x @ cov @ rr.x))})

    corr = rets.corr().round(3)
    return {
        "objective": objective,
        "weights": [{"ticker": t, "weight": float(wi), "expected_return": float(m),
                     "volatility": float(np.sqrt(cov[i, i]))}
                    for i, (t, wi, m) in enumerate(zip(tickers, w, mu))],
        "expected_return": r, "volatility": v, "sharpe": (r - rf) / v if v else None,
        "equal_weight": {"expected_return": eq_r, "volatility": eq_v,
                         "sharpe": (eq_r - rf) / eq_v if eq_v else None},
        "diversification_ratio": float((w @ np.sqrt(np.diag(cov))) / v) if v else None,
        "frontier": frontier,
        "correlation": {"tickers": tickers, "matrix": corr.values.tolist()},
        "constraints": {"max_weight": max_weight, "min_weight": min_weight},
    }


def allocate(weights: list[dict], capital: float, prices: dict[str, float]) -> list[dict]:
    """Phân bổ vốn thành số cổ phiếu (lô 100)."""
    out = []
    for w in weights:
        price = prices[w["ticker"]]
        qty = int(capital * w["weight"] / price // 100 * 100)
        out.append({**w, "price": price, "quantity": qty, "value": qty * price})
    return out
