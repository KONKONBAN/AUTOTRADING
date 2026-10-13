"""Kiểm định lại chiến lược (backtest) trên dữ liệu lịch sử.

Mô phỏng cùng bộ quy tắc với Auto-Trader (bản vector hóa của điểm kỹ thuật):
- Bộ lọc thị trường: VN-Index có độ dốc xu hướng b > 0 và giá trên MA50 → được mua mới.
- Mua: điểm kỹ thuật ≥ ngưỡng, mua chia 2 lần (50% + 50% khi lãi ≥ 3%).
- Bán: cắt lỗ (ATR / tối đa 7%), trailing stop, xu hướng gãy (dưới MA50 & điểm < 40).
- Phí 0,15% mỗi chiều + thuế bán 0,1%, lô 100, nắm giữ tối thiểu T+2.

Lưu ý: điểm cơ bản/định giá dùng giá trị hiện tại (không có dữ liệu point-in-time) nên chỉ được dùng
làm bộ lọc tĩnh - kết quả backtest có thể lạc quan hơn thực tế (look-ahead bias).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..analysis import market_timing, risk, technical
from ..data import providers, universe
from . import vn_rules


def run_backtest(tickers: list[str] | None = None, initial_cash: float = 500_000_000,
                 days: int = 750, min_score: float = 60.0, max_positions: int = 8,
                 max_weight: float = 0.20, risk_per_trade: float = 0.015,
                 trailing_stop_pct: float = 0.10, max_stop_pct: float = 0.07,
                 use_market_filter: bool = True, fee_rate: float = vn_rules.DEFAULT_FEE_RATE) -> dict:
    requested = list(dict.fromkeys(t.strip().upper() for t in (tickers or [t for t in universe.VN30 if t in universe.UNIVERSE])
                                   if t.strip()))
    unknown = [t for t in requested if not universe.is_listed(t) or providers.is_index(t)]
    if unknown:
        raise ValueError(f"Mã không hợp lệ (không niêm yết / không có dữ liệu): {', '.join(unknown)}")
    mkt = providers.get_history("VNINDEX", days=days)
    if not providers.is_tradeable_source(mkt.attrs.get("source")):
        raise ValueError("Chưa có dữ liệu thật của VN-Index (đang dùng DEMO) - không backtest trên dữ liệu mô phỏng.")
    frames, scores, sources, skipped = {}, {}, {}, []
    for t in requested:
        df = providers.get_history(t, days=days)
        if not providers.is_tradeable_source(df.attrs.get("source")):
            skipped.append(t)  # giá DEMO dự phòng: kết quả trên chuỗi ngẫu nhiên vô nghĩa với đầu tư thật
            continue
        sources[t] = df.attrs.get("source")
        f = technical.compute_frame(df)
        frames[t] = f
        scores[t] = technical.vector_score(f)
    tickers = list(frames)
    if not tickers:
        raise ValueError("Không mã nào có dữ liệu giá thật để backtest - hãy kiểm tra kết nối nguồn dữ liệu.")
    tr = market_timing.rolling_trend(mkt["close"], 120)
    mkt_ok = (tr["b"] > 0) & (mkt["close"] > mkt["close"].rolling(50).mean())
    dates = sorted(set().union(*[set(f.index) for f in frames.values()]))
    dates = [d for d in dates if d in mkt.index]
    start_idx = 210  # cần đủ dữ liệu cho MA200
    if len(dates) <= start_idx + 20:
        raise ValueError("Không đủ dữ liệu lịch sử để backtest")

    cash = initial_cash
    pos: dict[str, dict] = {}
    trades, curve = [], []
    for i in range(start_idx, len(dates)):
        d = dates[i]
        prices = {t: float(frames[t].at[d, "close"]) for t in tickers if d in frames[t].index}
        # --- quản lý vị thế
        for t in list(pos):
            if t not in prices:
                continue
            p, px = pos[t], prices[t]
            p["highest"] = max(p["highest"], px)
            held_days = i - p["entry_i"]
            f = frames[t].loc[d]
            sc = scores[t].get(d, 50)
            exit_reason = None
            if px <= p["stop"]:
                exit_reason = "Cắt lỗ"
            elif p["highest"] > p["avg"] * 1.05 and px <= p["highest"] * (1 - trailing_stop_pct):
                exit_reason = "Trailing stop"
            elif not math.isnan(f["sma50"]) and px < f["sma50"] and sc < 40:
                exit_reason = "Gãy xu hướng"
            if exit_reason and held_days >= vn_rules.SETTLEMENT_DAYS:
                value = px * p["qty"]
                cost = vn_rules.trade_costs("SELL", value, fee_rate)["total"]
                cash += value - cost
                pnl = value - cost - p["cost"]
                trades.append({"ticker": t, "entry_date": p["entry_date"], "exit_date": d.strftime("%Y-%m-%d"),
                               "entry": p["avg"], "exit": px, "qty": p["qty"], "pnl": pnl,
                               "return": pnl / p["cost"], "reason": exit_reason, "days": held_days})
                del pos[t]
            elif (not p["scaled"] and px >= p["avg"] * 1.03 and sc >= min_score):
                add_qty = vn_rules.round_lot(min(p["target_qty"] - p["qty"], cash / (px * (1 + fee_rate))))
                if add_qty > 0:
                    value = px * add_qty
                    cost = vn_rules.trade_costs("BUY", value, fee_rate)["total"]
                    cash -= value + cost
                    p["cost"] += value + cost
                    p["qty"] += add_qty
                    p["avg"] = p["cost"] / p["qty"]
                    p["stop"] = max(p["stop"], p["avg"] * (1 - max_stop_pct))
                    p["scaled"] = True
        equity = cash + sum(prices.get(t, p["avg"]) * p["qty"] for t, p in pos.items())
        # --- mua mới
        market_ok = bool(mkt_ok.get(d, False)) if use_market_filter else True
        if market_ok and len(pos) < max_positions:
            ranked = sorted(((scores[t].get(d, np.nan), t) for t in prices if t not in pos),
                            key=lambda x: -(x[0] if not np.isnan(x[0]) else -1))
            for sc, t in ranked:
                if np.isnan(sc) or sc < min_score or len(pos) >= max_positions:
                    break
                px = prices[t]
                atr_v = frames[t].at[d, "atr"]
                stop = max(px - 2 * (atr_v if not math.isnan(atr_v) else px * 0.03), px * (1 - max_stop_pct))
                target_qty = min(equity * risk_per_trade / max(px - stop, px * 0.01), equity * max_weight / px)
                qty = vn_rules.round_lot(min(target_qty * 0.5, cash / (px * (1 + fee_rate))))
                if qty <= 0:
                    continue
                value = px * qty
                cost = vn_rules.trade_costs("BUY", value, fee_rate)["total"]
                cash -= value + cost
                pos[t] = {"qty": qty, "avg": (value + cost) / qty, "cost": value + cost, "stop": stop,
                          "highest": px, "entry_i": i, "entry_date": d.strftime("%Y-%m-%d"),
                          "target_qty": target_qty, "scaled": False}
        equity = cash + sum(prices.get(t, p["avg"]) * p["qty"] for t, p in pos.items())
        curve.append({"date": d.strftime("%Y-%m-%d"), "equity": equity,
                      "benchmark": float(mkt.at[d, "close"]), "exposure": 1 - cash / equity if equity else 0})

    eq = pd.Series([c["equity"] for c in curve], index=pd.to_datetime([c["date"] for c in curve]))
    bench = pd.Series([c["benchmark"] for c in curve], index=eq.index)
    m = risk.metrics(eq, bench)
    bm = risk.metrics(bench)
    base = bench.iloc[0]
    for c in curve:
        c["benchmark_equity"] = initial_cash * c["benchmark"] / base
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    return {
        "params": {"tickers": tickers, "initial_cash": initial_cash, "min_score": min_score,
                   "max_positions": max_positions, "max_weight": max_weight, "risk_per_trade": risk_per_trade,
                   "trailing_stop_pct": trailing_stop_pct, "max_stop_pct": max_stop_pct,
                   "use_market_filter": use_market_filter},
        "data_source": ", ".join(sorted(set(sources.values()) | {str(mkt.attrs.get("source"))})),
        "sources": {**sources, "VNINDEX": mkt.attrs.get("source")}, "skipped_demo": skipped,
        "metrics": {**{k: m.get(k) for k in ("total_return", "cagr", "volatility", "sharpe", "sortino",
                                              "max_drawdown", "beta", "jensen_alpha")},
                    "final_equity": float(eq.iloc[-1]), "n_trades": len(trades),
                    "win_rate": len(wins) / len(trades) if trades else None,
                    "profit_factor": gross_win / gross_loss if gross_loss else None,
                    "avg_win": float(np.mean([t["return"] for t in wins])) if wins else None,
                    "avg_loss": float(np.mean([t["return"] for t in losses])) if losses else None,
                    "avg_holding_days": float(np.mean([t["days"] for t in trades])) if trades else None},
        "benchmark": {k: bm.get(k) for k in ("total_return", "cagr", "volatility", "sharpe", "max_drawdown")},
        "equity_curve": curve, "trades": trades[-200:],
        "open_positions": [{"ticker": t, **{k: v for k, v in p.items() if k in ("qty", "avg", "stop", "entry_date")}}
                           for t, p in pos.items()],
        "disclaimer": "Kết quả quá khứ không đảm bảo lợi nhuận tương lai. Backtest có thể lạc quan do "
                      "trượt giá, thanh khoản và dữ liệu không point-in-time.",
    }
