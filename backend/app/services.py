"""Tầng dịch vụ: kết hợp dữ liệu + các mô hình phân tích thành kết quả cho API, Auto-Trader và AI Agent."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import wraps

import numpy as np

from .analysis import fundamental, market_timing, quant, risk, scoring, technical, valuation
from .data import fundamentals as fund_data
from .data import providers, universe
from .utils import vn_num, vn_pct

log = logging.getLogger(__name__)


def ttl_cache(seconds: int):
    def deco(fn):
        store: dict = {}
        lock = threading.Lock()

        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()
            with lock:
                hit = store.get(key)
                if hit and now - hit[0] < seconds:
                    return hit[1]
            value = fn(*args, **kwargs)
            with lock:
                store[key] = (now, value)
            return value

        wrapper.cache_clear = store.clear  # type: ignore[attr-defined]
        return wrapper
    return deco


def clear_caches() -> None:
    for fn in (market_overview, sector_multiples, analyze_stock, screen):
        fn.cache_clear()


@ttl_cache(600)
def market_overview() -> dict:
    df = providers.get_history("VNINDEX", days=750)
    out = market_timing.analyze(df)
    out["source"] = df.attrs.get("source")
    return out


MIN_PEERS = 2


@ttl_cache(1800)
def sector_multiples(sector: str, exclude: str | None = None) -> dict:
    """P/E, P/B trung vị của các DN CÙNG NGÀNH (không tính chính mã đang định giá)."""
    pes, pbs = [], []
    for t, (_, sec, _, _) in universe.UNIVERSE.items():
        if sec != sector or t == exclude:
            continue
        try:
            last = fund_data.get_financials(t)["rows"][-1]
            price = providers.latest_price(t)
        except Exception:  # noqa: BLE001
            continue
        if last.get("eps") and last["eps"] > 0:
            pe = price / last["eps"]
            if 2 < pe < 60:
                pes.append(pe)
        if last.get("bvps") and last["bvps"] > 0:
            pbs.append(price / last["bvps"])
    return {"pe": float(np.median(pes)) if len(pes) >= MIN_PEERS else None,
            "pb": float(np.median(pbs)) if len(pbs) >= MIN_PEERS else None, "n": len(pes)}


def _summary(ticker: str, tech: dict, fa: dict, val: dict, rk: dict, comp: dict, mkt: dict) -> dict:
    pros, cons = [], []
    last = fa["latest"]
    if (last.get("roe") or 0) >= 0.15:
        pros.append(f"ROE cao ({vn_pct(last['roe'])}) - sử dụng vốn chủ hiệu quả.")
    elif last.get("roe") is not None and last["roe"] < 0.08:
        cons.append(f"ROE thấp ({vn_pct(last['roe'])}).")
    spread = fa["mm_model"].get("leverage_spread")
    if spread is not None and not fa["is_financial"]:
        (pros if spread > 0 else cons).append(
            f"Chênh lệch đòn bẩy ROA_op − Sd = {vn_pct(spread)}: nợ vay {'khuếch đại' if spread > 0 else 'làm giảm'} ROE.")
    if fa["quality"].get("negative_equity"):
        cons.append("Vốn chủ sở hữu ÂM - doanh nghiệp mất cân đối tài chính, rủi ro rất cao.")
    if fa["quality"].get("ni_turned_loss"):
        cons.append("Lợi nhuận suy giảm và đã chuyển sang LỖ.")
    elif (fa["quality"].get("ni_cagr") or 0) > 0.12:
        pros.append(f"Lợi nhuận tăng trưởng {vn_pct(fa['quality']['ni_cagr'])}/năm.")
    elif fa["quality"].get("ni_cagr") is not None and fa["quality"]["ni_cagr"] < 0:
        cons.append("Lợi nhuận suy giảm trong các năm gần đây.")
    for w in fa.get("data_warnings", []):
        cons.append(f"Dữ liệu: {w}")
    if val.get("upside") is not None:
        (pros if val["upside"] > 0.1 else cons if val["upside"] < -0.1 else pros).append(
            f"Định giá: giá trị nội tại ≈ {vn_num(val['intrinsic_value'])}đ ({vn_pct(val['upside'], sign=True)} so với thị giá) - {val['verdict']}.")
    (pros if tech["score"] >= 55 else cons).append(f"Kỹ thuật: {tech['signal']} (điểm {vn_num(tech['score'])}/100), xu hướng {tech['trend'].lower()}.")
    if rk.get("beta") is not None:
        cons.append(f"Beta {vn_num(rk['beta'], 2)} - " + ("biến động mạnh hơn thị trường." if rk["beta"] > 1.2 else "rủi ro hệ thống vừa phải.")) \
            if rk["beta"] > 1.2 else pros.append(f"Beta {vn_num(rk['beta'], 2)} - biến động không vượt quá thị trường.")
    if rk.get("max_drawdown", 0) < -0.4:
        cons.append(f"Mức sụt giảm tối đa lịch sử {vn_pct(rk['max_drawdown'], 0)} - rủi ro cao.")
    if mkt["recommended_exposure"] < 0.4:
        cons.append(f"Thị trường chung: {mkt['regime']} - nên hạn chế giải ngân.")
    return {"headline": f"{ticker}: {comp['recommendation']} (điểm tổng hợp {vn_num(comp['score'])}/100)",
            "pros": pros, "cons": cons}


@ttl_cache(300)
def analyze_stock(ticker: str, equity: float = 100_000_000, include_chart: bool = True) -> dict:
    ticker = ticker.upper().strip()
    meta = universe.info(ticker)
    df = providers.get_history(ticker, days=750)
    mkt_df = providers.get_history("VNINDEX", days=750)
    tech = technical.analyze(df)
    rk = risk.metrics(df["close"].tail(500), mkt_df["close"].tail(500))
    rk["level"] = risk.risk_level(rk["volatility"], rk["max_drawdown"])
    fin = fund_data.get_financials(ticker)
    fa = fundamental.analyze(fin, meta["sector"])
    sm = sector_multiples(meta["sector"], ticker)
    val = valuation.valuation(fin["rows"], fa["ratios"], tech["price"], rk.get("beta") or 1.0,
                              meta["sector"], sm["pe"], sm["pb"])
    mkt = market_overview()
    comp = scoring.composite(tech, fa["quality"], val, rk, mkt)
    plan = scoring.trade_plan(tech["price"], tech["atr"], tech, val, equity=equity)
    result = {
        "ticker": ticker, "info": meta,
        "data_sources": {"prices": df.attrs.get("source"), "financials": fin["source"]},
        "last_date": df.index[-1].strftime("%Y-%m-%d"),
        "composite": comp, "technical": tech, "fundamental": fa, "valuation": val,
        "risk": rk, "market": {k: mkt[k] for k in ("regime", "recommended_exposure", "score")},
        "trade_plan": plan, "summary": _summary(ticker, tech, fa, val, rk, comp, mkt),
    }
    if include_chart:
        result["chart"] = technical.chart_series(df, limit=520)  # đủ cho khung 2 năm
    return result


def _screen_row(ticker: str) -> dict | None:
    try:
        a = analyze_stock(ticker, include_chart=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("Phân tích %s lỗi: %s", ticker, exc)
        return None
    return {
        "ticker": ticker, "name": a["info"]["name"], "sector": a["info"]["sector"],
        "price": a["technical"]["price"], "change_pct": a["technical"]["change_pct"],
        "score": a["composite"]["score"], "recommendation": a["composite"]["recommendation"],
        "code": a["composite"]["code"], "parts": a["composite"]["parts"],
        "signal": a["technical"]["signal"], "trend": a["technical"]["trend"],
        "roe": a["fundamental"]["latest"]["roe"], "pe": a["valuation"]["multiples"]["pe"],
        "pb": a["valuation"]["multiples"]["pb"], "upside": a["valuation"]["upside"],
        "beta": a["risk"].get("beta"), "volatility": a["risk"]["volatility"],
        "perf_20d": a["technical"]["performance"].get("20d"),
        "atr_pct": a["technical"]["atr_pct"], "stop_loss": a["trade_plan"]["stop_loss"],
        "source": a["data_sources"]["prices"],
    }


@ttl_cache(300)
def screen(sector: str | None = None) -> list[dict]:
    tickers = [t for t, v in universe.UNIVERSE.items() if not sector or v[1] == sector]
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = [r for r in pool.map(_screen_row, tickers) if r]
    return sorted(rows, key=lambda r: -r["score"])


def sector_analysis(sector: str) -> dict:
    panel = {}
    for t, v in universe.UNIVERSE.items():
        if v[1] != sector:
            continue
        ratios = fundamental.ratios_by_year(fund_data.get_financials(t)["rows"])
        panel[t] = [(r["roa"], r["roe"]) for r in ratios]
    return {"sector": sector, "mundlak": quant.mundlak(panel), "multiples": sector_multiples(sector)}
