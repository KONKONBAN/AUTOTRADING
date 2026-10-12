"""Định giá cổ phiếu (Module 1 - Phân tích và định giá cổ phiếu; CFA - DCF & WACC).

- DCF/FCFF chiết khấu bằng WACC (trọng số theo giá trị thị trường, chi phí nợ sau thuế).
- Mô hình chiết khấu cổ tức Gordon (DDM): P0 = D1/(re − g).
- P/B hợp lý theo ROE (dùng cho ngân hàng/bảo hiểm/chứng khoán): P/B = (ROE − g)/(re − g).
- P/E hợp lý: P/E = payout·(1+g)/(re − g); so sánh P/E ngành.
- Chỉ số Graham: √(22,5 × EPS × BVPS).
"""

from __future__ import annotations

import math

import numpy as np

from ..finance.calculators import capm, wacc
from ..utils import vn_num, vn_pct
from .fundamental import FINANCIAL_SECTORS, TAX_RATE

RISK_FREE = 0.03          # lợi suất TPCP 10 năm tham chiếu
MARKET_RISK_PREMIUM = 0.08  # phần bù rủi ro thị trường VN
TERMINAL_GROWTH = 0.04


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def dcf_fcff(rows: list[dict], price: float, beta: float, years: int = 5,
             terminal_growth: float = TERMINAL_GROWTH) -> dict | None:
    last = rows[-1]
    shares = last.get("shares")
    if not shares:
        return None
    # FCFF = NOPAT + Khấu hao − Capex − ΔVLĐ ≈ OCF + Lãi vay·(1−t) − Capex
    fcffs = [(r.get("operating_cf") or 0) + (r.get("interest_expense") or 0) * (1 - TAX_RATE)
             - (r.get("capex") or 0) for r in rows]
    base = float(np.mean(fcffs[-3:]))
    if base <= 0:
        return {"valid": False, "reason": "FCFF bình quân ≤ 0, mô hình DCF không phù hợp."}
    ni = [r["net_income"] for r in rows if r["net_income"] > 0]
    g_hist = (ni[-1] / ni[0]) ** (1 / max(len(ni) - 1, 1)) - 1 if len(ni) >= 2 else 0.05
    g = _clip(g_hist, 0.0, 0.18)
    re = capm(RISK_FREE, _clip(beta, 0.5, 2.0), mrp=MARKET_RISK_PREMIUM)
    debt = last.get("total_debt") or 0.0
    rd = (last.get("interest_expense") or 0) / debt if debt else 0.08
    rd = _clip(rd, 0.04, 0.15)
    market_cap = price * shares * 1e6 / 1e9  # tỷ đồng
    w = wacc(market_cap, debt, re, rd, TAX_RATE)
    k = w["wacc"]
    if k <= terminal_growth + 0.01:
        k = terminal_growth + 0.01
    flows, pv_sum, fc = [], 0.0, base
    for t in range(1, years + 1):
        growth = g + (terminal_growth - g) * (t - 1) / max(years - 1, 1)  # giảm dần về g dài hạn
        fc *= 1 + growth
        pv = fc / (1 + k) ** t
        pv_sum += pv
        flows.append({"year": t, "fcff": fc, "growth": growth, "pv": pv})
    tv = fc * (1 + terminal_growth) / (k - terminal_growth)
    pv_tv = tv / (1 + k) ** years
    ev = pv_sum + pv_tv
    net_debt = debt - (last.get("cash") or 0)
    equity_value = ev - net_debt
    per_share = equity_value * 1e9 / (shares * 1e6)
    return {
        "valid": per_share > 0, "value_per_share": per_share, "enterprise_value": ev,
        "equity_value": equity_value, "pv_terminal": pv_tv, "terminal_share": pv_tv / ev if ev else None,
        "wacc": k, "cost_equity": re, "cost_debt_after_tax": rd * (1 - TAX_RATE),
        "weights": {"equity": w["we"], "debt": w["wd"]}, "growth": g,
        "terminal_growth": terminal_growth, "base_fcff": base, "flows": flows,
    }


def ddm(dps: float, re: float, g: float) -> float | None:
    if not dps or dps <= 0 or re <= g:
        return None
    return dps * (1 + g) / (re - g)


def justified_pb(roe: float, re: float, g: float) -> float | None:
    if roe is None or re <= g:
        return None
    return max((roe - g) / (re - g), 0)


def graham_number(eps: float, bvps: float) -> float | None:
    if not eps or not bvps or eps <= 0 or bvps <= 0:
        return None
    return math.sqrt(22.5 * eps * bvps)


def valuation(fin_rows: list[dict], ratios: list[dict], price: float, beta: float, sector: str,
              sector_pe: float | None = None, sector_pb: float | None = None) -> dict:
    last = fin_rows[-1]
    eps, bvps, dps = last.get("eps") or 0, last.get("bvps") or 0, last.get("dps") or 0
    roe = ratios[-1]["roe"] or 0
    re = capm(RISK_FREE, _clip(beta or 1.0, 0.5, 2.0), mrp=MARKET_RISK_PREMIUM)
    retention = 1 - (dps / eps) if eps > 0 else 0.5
    g_sust = _clip(roe * _clip(retention, 0, 1), 0.0, 0.12)  # tăng trưởng bền vững g = ROE × b
    pe = price / eps if eps > 0 else None
    pb = price / bvps if bvps > 0 else None
    models = []

    def add(name: str, value, weight: float, note: str):
        if value is not None and value > 0 and math.isfinite(value):
            models.append({"model": name, "value": float(value), "weight": weight, "note": note})

    financial = sector in FINANCIAL_SECTORS
    if not financial:
        d = dcf_fcff(fin_rows, price, beta or 1.0)
        if d and d.get("valid"):
            add("DCF (FCFF - WACC)", d["value_per_share"], 0.35,
                f"WACC {vn_pct(d['wacc'])}, g dài hạn {vn_pct(d['terminal_growth'], 0)}")
    else:
        d = None
    # Mô hình vĩnh viễn (P/B hợp lý, DDM) phải dùng tăng trưởng DÀI HẠN, không suy ra từ re
    g_eff = min(g_sust, TERMINAL_GROWTH)
    pb_fair = justified_pb(roe, re, g_eff)
    if pb_fair is not None:
        pb_fair = _clip(pb_fair, 0.3, 5.0)
    if pb_fair is not None and bvps > 0:
        add("P/B hợp lý theo ROE", pb_fair * bvps, 0.35 if financial else 0.15,
            f"P/B = (ROE − g)/(re − g) = {vn_num(pb_fair, 2)}x")
    if eps > 0:
        # Trạng thái dừng: tăng trưởng g cần tái đầu tư g/ROE → tỷ lệ chi trả bền vững = 1 − g/ROE
        # (nhất quán với P/B hợp lý; dùng tỷ lệ chi trả hiện tại thấp sẽ kéo P/E về sàn một cách sai lệch)
        g_pe = g_eff if roe > g_eff else 0.0
        payout_ss = 1 - g_pe / roe if roe > g_eff else 1.0
        if re > g_pe:
            pe_fair = _clip(payout_ss * (1 + g_pe) / (re - g_pe), 5, 25)
            add("P/E hợp lý (Gordon)", pe_fair * eps, 0.15,
                f"P/E hợp lý {vn_num(pe_fair, 1)}x (chi trả bền vững {vn_pct(payout_ss, 0)}, g {vn_pct(g_pe)})")
    if sector_pe and eps > 0:
        add("So sánh P/E ngành", sector_pe * eps, 0.2, f"P/E trung vị ngành {vn_num(sector_pe, 1)}x")
    if sector_pb and bvps > 0:
        add("So sánh P/B ngành", sector_pb * bvps, 0.1, f"P/B trung vị ngành {vn_num(sector_pb, 2)}x")
    add("Chiết khấu cổ tức (DDM)", ddm(dps, re, g_eff), 0.05, f"re {vn_pct(re)}, g {vn_pct(g_eff)}")
    add("Chỉ số Graham", graham_number(eps, bvps), 0.05, "√(22,5 × EPS × BVPS)")

    total_w = sum(m["weight"] for m in models)
    intrinsic = sum(m["value"] * m["weight"] for m in models) / total_w if total_w else None
    upside = intrinsic / price - 1 if intrinsic else None
    if upside is None:
        score, verdict = 50.0, "Chưa đủ dữ liệu định giá"
    else:
        score = float(np.clip(50 + upside * 125, 0, 100))
        verdict = ("RẺ - biên an toàn lớn" if upside > 0.25 else "HẤP DẪN" if upside > 0.10
                   else "HỢP LÝ" if upside > -0.10 else "ĐẮT" if upside > -0.25 else "RẤT ĐẮT")
    return {
        "price": price, "intrinsic_value": intrinsic, "upside": upside, "score": round(score, 1),
        "verdict": verdict, "models": models, "dcf": d,
        "multiples": {"pe": pe, "pb": pb, "dividend_yield": dps / price if price else None,
                      "eps": eps, "bvps": bvps, "dps": dps, "sector_pe": sector_pe, "sector_pb": sector_pb},
        "assumptions": {"risk_free": RISK_FREE, "mrp": MARKET_RISK_PREMIUM, "cost_equity": re,
                        "sustainable_growth": g_sust, "beta": beta},
    }
