"""Toán tài chính & định giá (lãi đơn, lãi kép, chuỗi tiền tệ, chiết khấu thương phiếu, vay vốn,
trái phiếu, NPV/IRR/MIRR, WACC, CAPM, thuê mua tài sản).

Tài liệu: Toán tài chính Ch.1-6; PTVĐTCK Ch.3 (định giá trái phiếu); CFA - DCF & WACC;
Tài chính doanh nghiệp Ch.9 (thuê mua tài sản).
"""

from __future__ import annotations

from scipy.optimize import brentq


# ----------------------------------------------------------------- lãi đơn / lãi kép
def simple_interest(pv: float, rate: float, periods: float) -> dict:
    """Lãi đơn: I = PV·i·n ; FV = PV(1 + i·n)."""
    interest = pv * rate * periods
    return {"interest": interest, "fv": pv + interest}


def compound_interest(pv: float, rate: float, periods: float, m: int = 1) -> dict:
    """Lãi kép: FV = PV(1 + i/m)^(n·m). Lãi suất hiệu dụng = (1+i/m)^m − 1."""
    fv = pv * (1 + rate / m) ** (periods * m)
    return {"fv": fv, "interest": fv - pv, "effective_rate": (1 + rate / m) ** m - 1}


def compound_variable_rates(pv: float, rates: list[float]) -> float:
    """FQA: FV = PV·Π(1 + r_i). VD: 100 với 6%, 7%, 8% → 122,5."""
    fv = pv
    for r in rates:
        fv *= 1 + r
    return fv


def present_value(fv: float, rate: float, periods: float) -> float:
    return fv / (1 + rate) ** periods


# ----------------------------------------------------------------- chuỗi tiền tệ
def annuity(payment: float, rate: float, n: int, due: bool = False) -> dict:
    """Chuỗi tiền đều: FV = a[(1+i)^n − 1]/i ; PV = a[1 − (1+i)^−n]/i (đầu kỳ ×(1+i))."""
    if rate == 0:
        fv, pv = payment * n, payment * n
    else:
        fv = payment * ((1 + rate) ** n - 1) / rate
        pv = payment * (1 - (1 + rate) ** -n) / rate
    if due:
        fv, pv = fv * (1 + rate), pv * (1 + rate)
    return {"fv": fv, "pv": pv}


def annuity_payment(pv: float, rate: float, n: int, due: bool = False) -> float:
    """Số tiền mỗi kỳ để trả hết khoản vay PV trong n kỳ."""
    if rate == 0:
        return pv / n
    a = pv * rate / (1 - (1 + rate) ** -n)
    return a / (1 + rate) if due else a


def savings_payment(target_fv: float, rate: float, n: int) -> float:
    """Cần gửi đều bao nhiêu mỗi kỳ để đạt mục tiêu FV."""
    if rate == 0:
        return target_fv / n
    return target_fv * rate / ((1 + rate) ** n - 1)


def growing_annuity_pv(payment: float, rate: float, growth: float, n: int) -> float:
    """Chuỗi tiền biến đổi theo cấp số nhân."""
    if abs(rate - growth) < 1e-12:
        return payment * n / (1 + rate)
    return payment / (rate - growth) * (1 - ((1 + growth) / (1 + rate)) ** n)


# ----------------------------------------------------------------- vay vốn
def loan_schedule(principal: float, rate: float, n: int, method: str = "annuity") -> dict:
    """Lịch trả nợ: 'annuity' (trả góp đều) hoặc 'equal_principal' (gốc đều, lãi giảm dần)."""
    rows, balance, total_interest = [], principal, 0.0
    pay = annuity_payment(principal, rate, n) if method == "annuity" else None
    for k in range(1, n + 1):
        interest = balance * rate
        principal_part = (pay - interest) if method == "annuity" else principal / n
        payment = principal_part + interest
        balance -= principal_part
        total_interest += interest
        rows.append({"period": k, "payment": payment, "interest": interest,
                     "principal": principal_part, "balance": max(balance, 0.0)})
    return {"schedule": rows, "total_interest": total_interest, "total_paid": principal + total_interest}


# ----------------------------------------------------------------- chiết khấu thương phiếu
def discount_bill(face: float, rate: float, days: int, fee: float = 0.0, basis: int = 360) -> dict:
    """Chiết khấu thương phiếu: E = F·i·n/360 ; giá trị hiện tại = F − E − hoa hồng."""
    discount = face * rate * days / basis
    proceeds = face - discount - fee
    return {"discount": discount, "fee": fee, "proceeds": proceeds,
            "actual_rate": (face - proceeds) / proceeds * basis / days if proceeds else None}


# ----------------------------------------------------------------- NPV / IRR / MIRR
def npv(rate: float, cashflows: list[float]) -> float:
    """NPV = Σ CF_t/(1+r)^t, CF_0 tại t=0 (thường âm)."""
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows))


def irr(cashflows: list[float]) -> float | None:
    """IRR: lãi suất làm NPV = 0. VD (PTVĐTCK Ch.2): [-1, -0.1, -0.5, 0.8, 1.0] → ≈ 4,17%."""
    f = lambda r: npv(r, cashflows)  # noqa: E731
    grid = [-0.99, -0.5, -0.2, 0.0, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10]
    for x in grid:  # nghiệm rơi đúng vào điểm lưới
        if abs(f(x)) < 1e-10:
            return float(x)
    for lo, hi in zip(grid, grid[1:]):
        if f(lo) * f(hi) < 0:
            return float(brentq(f, lo, hi))
    return None


def mirr(cashflows: list[float], finance_rate: float, reinvest_rate: float) -> float | None:
    """MIRR: tái đầu tư dòng tiền dương theo reinvest_rate (thường = WACC)."""
    n = len(cashflows) - 1
    pv_neg = sum(cf / (1 + finance_rate) ** t for t, cf in enumerate(cashflows) if cf < 0)
    fv_pos = sum(cf * (1 + reinvest_rate) ** (n - t) for t, cf in enumerate(cashflows) if cf > 0)
    if pv_neg >= 0 or fv_pos <= 0:
        return None
    return (fv_pos / -pv_neg) ** (1 / n) - 1


def payback_period(cashflows: list[float]) -> float | None:
    cum = 0.0
    for t, cf in enumerate(cashflows):
        prev = cum
        cum += cf
        if t > 0 and prev < 0 <= cum:
            return t - 1 + (-prev / cf)
    return None


def project_appraisal(cashflows: list[float], rate: float) -> dict:
    """Thẩm định dự án: NPV, IRR, MIRR, PI, thời gian hoàn vốn + quyết định."""
    v = npv(rate, cashflows)
    i = irr(cashflows)
    pv_in = sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows) if t > 0)
    inv = -cashflows[0] if cashflows[0] < 0 else None
    return {"npv": v, "irr": i, "mirr": mirr(cashflows, rate, rate),
            "profitability_index": pv_in / inv if inv else None,
            "payback": payback_period(cashflows),
            "decision": "CHẤP NHẬN (NPV > 0)" if v > 0 else "TỪ CHỐI (NPV < 0)" if v < 0 else "Hòa vốn (NPV = 0)"}


# ----------------------------------------------------------------- chi phí vốn
def capm(rf: float, beta: float, market_return: float | None = None, mrp: float | None = None) -> float:
    """CAPM: re = rf + β(Rm − rf)."""
    premium = mrp if mrp is not None else (market_return - rf)
    return rf + beta * premium


def wacc(equity_value: float, debt_value: float, cost_equity: float, cost_debt: float,
         tax_rate: float = 0.20, pref_value: float = 0.0, cost_pref: float = 0.0) -> dict:
    """WACC = we·re + wd·rd(1−t) + wp·rp (trọng số theo GIÁ TRỊ THỊ TRƯỜNG).

    VD CFA: E 60%, re 15%; D 40%, rd 8%, thuế 20% → WACC = 11,56%.
    """
    total = equity_value + debt_value + pref_value
    we, wd, wp = equity_value / total, debt_value / total, pref_value / total
    after_tax_debt = cost_debt * (1 - tax_rate)
    return {"wacc": we * cost_equity + wd * after_tax_debt + wp * cost_pref,
            "we": we, "wd": wd, "wp": wp, "after_tax_cost_debt": after_tax_debt}


# ----------------------------------------------------------------- trái phiếu (PTVĐTCK Ch.3)
def bond_price(face: float, coupon_rate: float, market_rate: float, years: float, freq: int = 1) -> dict:
    """P = C·[1 − (1+r)^−n]/r + F/(1+r)^n (lãi trả m lần/năm: C/m, r/m, n·m)."""
    c = face * coupon_rate / freq
    r = market_rate / freq
    n = int(round(years * freq))
    pv_coupons = c * (1 - (1 + r) ** -n) / r if r else c * n
    pv_face = face / (1 + r) ** n
    price = pv_coupons + pv_face
    status = "bằng mệnh giá" if abs(coupon_rate - market_rate) < 1e-9 else (
        "cao hơn mệnh giá (premium)" if coupon_rate > market_rate else "thấp hơn mệnh giá (discount)")
    return {"price": price, "pv_coupons": pv_coupons, "pv_face": pv_face,
            "current_yield": face * coupon_rate / price, "status": status,
            "duration": bond_duration(face, coupon_rate, market_rate, years, freq)}


def bond_duration(face: float, coupon_rate: float, market_rate: float, years: float, freq: int = 1) -> dict:
    c = face * coupon_rate / freq
    r = market_rate / freq
    n = int(round(years * freq))
    cfs = [(t, c + (face if t == n else 0)) for t in range(1, n + 1)]
    price = sum(cf / (1 + r) ** t for t, cf in cfs)
    mac = sum(t * cf / (1 + r) ** t for t, cf in cfs) / price / freq
    return {"macaulay": mac, "modified": mac / (1 + r)}


def zero_coupon_price(face: float, market_rate: float, years: float) -> float:
    return face / (1 + market_rate) ** years


def perpetual_bond_price(coupon: float, market_rate: float) -> float:
    return coupon / market_rate


def bond_ytm(price: float, face: float, coupon_rate: float, years: float, freq: int = 1) -> float | None:
    """Lợi suất đáo hạn. VD Ch.3: giá 1.035.000, coupon 10%, 2 năm → YTM ≈ 8,04%."""
    f = lambda y: bond_price(face, coupon_rate, y, years, freq)["price"] - price  # noqa: E731
    try:
        return float(brentq(f, -0.5, 2.0))
    except ValueError:
        return None


def convertible_bond(face: float, conversion_price: float, stock_price: float) -> dict:
    """VD Ch.3: mệnh giá 1.000.000, giá chuyển đổi 40.000, thị giá 50.000 → tỷ lệ 25, giá trị 1.250.000."""
    ratio = face / conversion_price
    value = ratio * stock_price
    return {"conversion_ratio": ratio, "conversion_value": value, "premium": value - face,
            "should_convert": value > face}


# ----------------------------------------------------------------- thuê mua tài sản (TCDN Ch.9)
def lease_vs_buy(asset_cost: float, lease_payment: float, years: int, pre_tax_debt_rate: float,
                 tax_rate: float = 0.20, salvage: float = 0.0, lease_in_advance: bool = True) -> dict:
    """Lợi ích ròng của thuê tài chính (NAL) so với vay mua - chiết khấu theo rd(1−t).

    Thuê: chi phí thuê sau thuế L(1−t). Mua: bỏ vốn đầu tư, hưởng lá chắn thuế khấu hao, thu thanh lý.
    NAL > 0 → nên THUÊ; NAL < 0 → nên VAY MUA.
    """
    r = pre_tax_debt_rate * (1 - tax_rate)
    dep = (asset_cost - salvage) / years
    cf_lease_vs_buy = [asset_cost]  # t=0: tiết kiệm được chi phí mua tài sản
    for t in range(years + 1):
        cf = 0.0
        pay_t = (t < years) if lease_in_advance else (t >= 1)
        if pay_t:
            cf -= lease_payment * (1 - tax_rate)
        if t >= 1:
            cf -= dep * tax_rate  # mất lá chắn thuế khấu hao
        if t == years:
            # mất giá trị thanh lý; tài sản đã khấu hao về đúng giá trị thanh lý nên thuế trên lãi thanh lý = 0
            book_end = asset_cost - dep * years
            cf -= salvage - tax_rate * (salvage - book_end)
        if t == 0:
            cf_lease_vs_buy[0] += cf
        else:
            cf_lease_vs_buy.append(cf)
    nal = npv(r, cf_lease_vs_buy)
    return {"nal": nal, "discount_rate": r, "cashflows": cf_lease_vs_buy,
            "decision": "NÊN THUÊ TÀI CHÍNH" if nal > 0 else "NÊN VAY ĐỂ MUA"}
