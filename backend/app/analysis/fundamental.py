"""Phân tích cơ bản: hiệu quả tài chính, đòn bẩy, chất lượng lợi nhuận.

Dựa trên tài liệu FQA (Phân tích định lượng trong tài chính):
- ROE = NI/E, ROA = NI/TA, LEV = D/E (D = Nợ phải trả).
- Định lý Modigliani-Miller mở rộng:  ROE = (1 + LEV)·ROA_op − LEV·Sd
  với ROA_op = (NI + Int(1−T))/TA (sinh lời hoạt động), Sd = Rd(1−T) = Int(1−T)/D.
  → Đòn bẩy chỉ khuếch đại ROE khi ROA_op > Sd (chênh lệch đòn bẩy dương).
- Hồi quy chuỗi thời gian: ROE_t = a + b·ROA_t + u_t  (b: hệ số khuếch đại, a: chi phí đòn bẩy),
  so sánh b với b* = 1 + LEV (giá trị lý thuyết MM); bs = E(ROE)/E(ROA) (trạng thái ổn định).
"""

from __future__ import annotations

import math

import numpy as np

TAX_RATE = 0.20
ESTIMATED_LABELS = {"total_debt": "vay nợ (ước tính 50% nợ phải trả)", "current_liabilities": "nợ ngắn hạn",
                    "pretax_income": "lợi nhuận trước thuế", "operating_cf": "dòng tiền HĐKD (lấy bằng LNST)"}
FINANCIAL_SECTORS = {"Ngân hàng", "Bảo hiểm", "Chứng khoán"}


def _div(a, b):
    try:
        return a / b if b not in (0, None) and a is not None else None
    except TypeError:
        return None


def ols(x: list[float], y: list[float]) -> dict | None:
    """Hồi quy OLS đơn biến y = a + b·x, kèm sai số chuẩn, t-stat, R²."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = len(x)
    if n < 3 or np.var(x) == 0:
        return None
    b, a = np.polyfit(x, y, 1)
    resid = y - (a + b * x)
    sse = float(resid @ resid)
    sst = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - sse / sst if sst else 0.0
    s2 = sse / (n - 2) if n > 2 else 0.0
    sxx = float(((x - x.mean()) ** 2).sum())
    se_b = math.sqrt(s2 / sxx) if sxx else None
    se_a = math.sqrt(s2 * (1 / n + x.mean() ** 2 / sxx)) if sxx else None
    return {"a": float(a), "b": float(b), "r2": r2, "n": n,
            "se_a": se_a, "se_b": se_b,
            "t_a": _div(float(a), se_a), "t_b": _div(float(b), se_b)}


def ratios_by_year(rows: list[dict]) -> list[dict]:
    out = []
    prev = None
    for r in rows:
        ni, ta, e = r["net_income"], r["total_assets"], r["equity"]
        d = r.get("total_liabilities") or (ta - e)
        interest = r.get("interest_expense") or 0.0
        sd = _div(interest * (1 - TAX_RATE), d)  # chi phí nợ sau thuế
        roa_op = _div(ni + interest * (1 - TAX_RATE), ta)
        fcf = (r.get("operating_cf") or 0) - (r.get("capex") or 0)
        neg_equity = e is None or e <= 0  # vốn chủ âm: ROE, D/E vô nghĩa (lỗ / vốn âm ra số dương)
        row = {
            "year": r["year"],
            "revenue": r["revenue"], "net_income": ni, "total_assets": ta, "equity": e,
            "negative_equity": neg_equity,
            "roe": None if neg_equity else _div(ni, e), "roa": _div(ni, ta),
            "lev": None if neg_equity else _div(d, e),
            "roa_op": roa_op, "sd": sd,
            "leverage_spread": (roa_op - sd) if roa_op is not None and sd is not None else None,
            "net_margin": _div(ni, r["revenue"]),
            "gross_margin": _div(r.get("gross_profit"), r["revenue"]),
            "asset_turnover": _div(r["revenue"], ta),
            "equity_multiplier": None if neg_equity else _div(ta, e),
            "current_ratio": _div(r.get("current_assets"), r.get("current_liabilities")),
            "quick_ratio": _div((r.get("current_assets") or 0) - (r.get("inventory") or 0),
                                r.get("current_liabilities")),
            "interest_coverage": _div(r.get("ebit"), interest) if interest else None,
            "debt_to_assets": _div(d, ta),
            "ocf_to_ni": _div(r.get("operating_cf"), ni) if ni and ni > 0 else None,
            "fcf": fcf,
            "eps": r.get("eps"), "bvps": r.get("bvps"), "dps": r.get("dps"),
        }
        if prev:
            row["revenue_growth"] = _div(r["revenue"] - prev["revenue"], abs(prev["revenue"]))
            row["ni_growth"] = _div(ni - prev["net_income"], abs(prev["net_income"]))
        out.append(row)
        prev = r
    return out


def piotroski_f_score(rows: list[dict]) -> dict:
    """Điểm F-Score Piotroski (0-9) đo sức khỏe tài chính."""
    if len(rows) < 2:
        return {"score": None, "checks": []}
    c, p = rows[-1], rows[-2]
    roa_c, roa_p = _div(c["net_income"], c["total_assets"]), _div(p["net_income"], p["total_assets"])
    lev_c = _div(c.get("total_debt"), c["total_assets"])
    lev_p = _div(p.get("total_debt"), p["total_assets"])
    cr_c = _div(c.get("current_assets"), c.get("current_liabilities"))
    cr_p = _div(p.get("current_assets"), p.get("current_liabilities"))
    gm_c, gm_p = _div(c.get("gross_profit"), c["revenue"]), _div(p.get("gross_profit"), p["revenue"])
    at_c, at_p = _div(c["revenue"], c["total_assets"]), _div(p["revenue"], p["total_assets"])
    checks = [
        ("ROA dương", roa_c is not None and roa_c > 0),
        ("Dòng tiền HĐKD dương", (c.get("operating_cf") or 0) > 0),
        ("ROA cải thiện", roa_c is not None and roa_p is not None and roa_c > roa_p),
        ("Dòng tiền HĐKD > Lợi nhuận (chất lượng LN)", (c.get("operating_cf") or 0) > c["net_income"]),
        ("Đòn bẩy nợ vay giảm", lev_c is not None and lev_p is not None and lev_c <= lev_p),
        ("Thanh khoản hiện hành tăng", cr_c is not None and cr_p is not None and cr_c > cr_p),
        ("Không pha loãng cổ phiếu", (c.get("shares") or 0) <= (p.get("shares") or 0) * 1.01),
        ("Biên lợi nhuận gộp tăng", gm_c is not None and gm_p is not None and gm_c > gm_p),
        ("Vòng quay tài sản tăng", at_c is not None and at_p is not None and at_c > at_p),
    ]
    return {"score": sum(ok for _, ok in checks),
            "checks": [{"name": n, "pass": bool(ok)} for n, ok in checks]}


def mm_leverage_model(ratios: list[dict]) -> dict:
    """Mô hình ROE–ROA theo MM mở rộng cho 1 doanh nghiệp (chuỗi thời gian)."""
    xs = [r["roa"] for r in ratios if r["roa"] is not None and r["roe"] is not None]
    ys = [r["roe"] for r in ratios if r["roa"] is not None and r["roe"] is not None]
    levs = [r["lev"] for r in ratios if r["lev"] is not None]
    reg = ols(xs, ys)
    mean_lev = float(np.mean(levs)) if levs else None
    b_star = 1 + mean_lev if mean_lev is not None else None
    e_roe, e_roa = (float(np.mean(ys)), float(np.mean(xs))) if xs else (None, None)
    last = ratios[-1] if ratios else {}
    spread = last.get("leverage_spread")
    if spread is None:
        verdict = "Không đủ dữ liệu để đánh giá đòn bẩy."
    elif spread > 0.005:
        verdict = ("Đòn bẩy CÓ LỢI: sinh lời hoạt động (ROA_op) cao hơn chi phí nợ sau thuế (Sd), "
                   "nợ vay đang khuếch đại ROE.")
    elif spread < -0.005:
        verdict = ("Đòn bẩy BẤT LỢI: ROA_op thấp hơn chi phí nợ sau thuế, vay nợ làm suy giảm ROE "
                   "và tăng rủi ro tài chính.")
    else:
        verdict = "Đòn bẩy trung tính: ROA_op xấp xỉ chi phí nợ."
    return {
        "regression": reg,
        "mean_lev": mean_lev,
        "b_star": b_star,
        "b_gap": (reg["b"] - b_star) if reg and b_star else None,
        "bs": _div(e_roe, e_roa),
        "expected_roe": e_roe, "expected_roa": e_roa,
        "leverage_spread": spread,
        "verdict": verdict,
        "equation": "ROE = (1 + LEV)·ROA_op − LEV·Rd(1−T)",
    }


def _cagr(first: float, last: float, years: int) -> float | None:
    if not first or first <= 0 or last <= 0 or years <= 0:
        return None
    return (last / first) ** (1 / years) - 1


def score_quality(ratios: list[dict], f_score: dict, sector: str) -> dict:
    """Điểm chất lượng cơ bản 0-100 (điều chỉnh theo đặc thù ngành tài chính)."""
    last = ratios[-1]
    financial = sector in FINANCIAL_SECTORS
    parts = []

    def part(name: str, value, score: float, weight: float, note: str):
        parts.append({"name": name, "value": value, "score": float(np.clip(score, 0, 1)),
                      "weight": weight, "note": note})

    neg_equity = bool(last.get("negative_equity"))
    roe = last["roe"] or 0
    part("ROE", last["roe"], 0.0 if neg_equity else (roe - 0.05) / 0.20, 2.0,
         "Vốn chủ sở hữu ÂM - mất cân đối tài chính nghiêm trọng" if neg_equity else "ROE ≥ 15% là tốt; > 25% rất tốt")
    roa = last["roa"] or 0
    roa_target = 0.02 if financial else 0.10
    part("ROA", roa, roa / roa_target, 1.2, f"Mục tiêu ngành {'tài chính' if financial else 'phi tài chính'}: ≥ {roa_target * 100:g}%")
    lev = last["lev"] or 0
    lev_ok = 12 if sector == "Ngân hàng" else 6 if financial else 2.0
    part("Đòn bẩy D/E", last["lev"], 0.0 if neg_equity else 1 - max(lev - lev_ok * 0.5, 0) / lev_ok, 1.0,
         "Không tính được D/E vì vốn chủ âm" if neg_equity else f"D/E an toàn cho ngành ≤ {lev_ok:g}")
    spread = last.get("leverage_spread")
    if spread is not None and not financial:
        part("Chênh lệch đòn bẩy (ROA_op − Sd)", spread, 0.5 + spread * 10, 1.0,
             "Dương: vay nợ khuếch đại ROE (MM mở rộng)")
    span = max(last["year"] - ratios[0]["year"], 1)  # số năm thực tế (có thể có năm bị thiếu)
    rev_cagr = _cagr(ratios[0]["revenue"], last["revenue"], span)
    ni_cagr = _cagr(ratios[0]["net_income"], last["net_income"], span)
    turned_loss = ratios[0]["net_income"] > 0 and last["net_income"] <= 0
    part("Tăng trưởng doanh thu (CAGR)", rev_cagr, ((rev_cagr or 0) + 0.02) / 0.20, 1.0, "≥ 15%/năm là tốt")
    part("Tăng trưởng LNST (CAGR)", ni_cagr,
         0.0 if turned_loss or last["net_income"] <= 0 else ((ni_cagr or 0) + 0.02) / 0.22, 1.5,
         "Doanh nghiệp đã chuyển từ lãi sang LỖ" if turned_loss else "≥ 15%/năm là tốt")
    roes = [r["roe"] for r in ratios if r["roe"] is not None]
    stability = 1 - min(float(np.std(roes)) / max(abs(float(np.mean(roes))), 0.01), 1.5) / 1.5 if roes else 0
    part("Ổn định ROE", float(np.std(roes)) if roes else None, stability, 0.8, "Độ lệch chuẩn ROE thấp = ổn định")
    if f_score.get("score") is not None:
        part("Piotroski F-Score", f_score["score"], f_score["score"] / 9, 1.2, "≥ 7 là sức khỏe tài chính tốt")
    if not financial and last.get("ocf_to_ni") is not None:
        part("Chất lượng LN (OCF/NI)", last["ocf_to_ni"], last["ocf_to_ni"] / 1.2, 0.8, "≥ 1: lợi nhuận được hiện thực hóa bằng tiền")
    if not financial and last.get("current_ratio") is not None:
        part("Thanh toán hiện hành", last["current_ratio"], (last["current_ratio"] - 0.8) / 1.0, 0.5, "≥ 1,5 là an toàn")
    total_w = sum(p["weight"] for p in parts)
    score = 100 * sum(p["score"] * p["weight"] for p in parts) / total_w
    return {"score": round(score, 1), "parts": parts, "revenue_cagr": rev_cagr, "ni_cagr": ni_cagr,
            "ni_turned_loss": turned_loss, "negative_equity": neg_equity}


def analyze(fin: dict, sector: str) -> dict:
    rows = fin["rows"]
    ratios = ratios_by_year(rows)
    f = piotroski_f_score(rows)
    mm = mm_leverage_model(ratios)
    quality = score_quality(ratios, f, sector)
    last = ratios[-1]
    dupont = {
        "net_margin": last["net_margin"], "asset_turnover": last["asset_turnover"],
        "equity_multiplier": last["equity_multiplier"], "roe": last["roe"],
        "note": "ROE = Biên LN ròng × Vòng quay tài sản × Hệ số nhân vốn chủ",
    }
    labels = {k: label for k, label in ESTIMATED_LABELS.items()}
    raw_last = rows[-1]
    warnings = []
    if not raw_last.get("shares"):
        warnings.append("Thiếu số cổ phiếu lưu hành → chưa tính được EPS, BVPS, P/E, P/B và các mô hình định giá theo cổ phiếu.")
    est = [labels.get(k, k) for k in raw_last.get("estimated_fields") or []]
    if est:
        warnings.append(f"Năm {raw_last['year']}: các chỉ tiêu được ƯỚC TÍNH do thiếu số liệu: {', '.join(est)}.")
    if raw_last.get("balance_warning"):
        warnings.append(raw_last["balance_warning"])
    return {"source": fin["source"], "ratios": ratios, "latest": last, "dupont": dupont, "data_warnings": warnings,
            "piotroski": f, "mm_model": mm, "quality": quality,
            "is_financial": sector in FINANCIAL_SECTORS}
