"""Quản trị tài chính cá nhân: ngân sách, quỹ dự phòng, nợ, mục tiêu và phân bổ tài sản.

Nguyên tắc:
- Ngân sách 50/30/20 (nhu cầu thiết yếu / mong muốn / tiết kiệm-đầu tư).
- Quỹ dự phòng khẩn cấp 3-6 tháng chi tiêu, giữ ở tài sản thanh khoản cao.
- Trả nợ lãi suất cao trước (phương pháp "avalanche").
- Phân bổ tài sản theo khẩu vị rủi ro và tuổi; "Đừng bỏ trứng vào một giỏ".
- Mục tiêu tài chính tính bằng giá trị thời gian của tiền (chuỗi tiền tệ đều).
"""

from __future__ import annotations

from ..utils import vn_num, vn_pct
from .calculators import annuity, savings_payment

# Lợi suất kỳ vọng dài hạn (danh nghĩa, năm) - giả định thận trọng
ASSET_RETURNS = {"Cổ phiếu": 0.11, "Trái phiếu/Quỹ trái phiếu": 0.065, "Tiết kiệm ngân hàng": 0.05,
                 "Vàng": 0.05, "Tiền mặt": 0.0}

RISK_PROFILES = {
    "than_trong": {"label": "Thận trọng", "Cổ phiếu": 0.20, "Trái phiếu/Quỹ trái phiếu": 0.35,
                   "Tiết kiệm ngân hàng": 0.30, "Vàng": 0.10, "Tiền mặt": 0.05},
    "can_bang": {"label": "Cân bằng", "Cổ phiếu": 0.45, "Trái phiếu/Quỹ trái phiếu": 0.25,
                 "Tiết kiệm ngân hàng": 0.15, "Vàng": 0.10, "Tiền mặt": 0.05},
    "tang_truong": {"label": "Tăng trưởng", "Cổ phiếu": 0.70, "Trái phiếu/Quỹ trái phiếu": 0.12,
                    "Tiết kiệm ngân hàng": 0.08, "Vàng": 0.07, "Tiền mặt": 0.03},
}

RISK_QUESTIONS = [
    {"id": "horizon", "q": "Thời gian bạn dự định đầu tư?", "options": [("< 1 năm", 0), ("1-3 năm", 1), ("3-7 năm", 2), ("> 7 năm", 3)]},
    {"id": "drop", "q": "Nếu danh mục giảm 20% trong 1 tháng, bạn sẽ?", "options": [("Bán hết", 0), ("Bán bớt", 1), ("Giữ nguyên", 2), ("Mua thêm", 3)]},
    {"id": "goal", "q": "Mục tiêu chính của bạn?", "options": [("Bảo toàn vốn", 0), ("Thu nhập ổn định", 1), ("Cân bằng", 2), ("Tăng trưởng cao", 3)]},
    {"id": "experience", "q": "Kinh nghiệm đầu tư chứng khoán?", "options": [("Chưa có", 0), ("< 1 năm", 1), ("1-3 năm", 2), ("> 3 năm", 3)]},
    {"id": "income", "q": "Thu nhập của bạn ổn định thế nào?", "options": [("Không ổn định", 0), ("Tương đối", 1), ("Ổn định", 2), ("Rất ổn định, có nhiều nguồn", 3)]},
]


def risk_profile_from_answers(answers: dict[str, int]) -> dict:
    score = sum(int(v) for v in answers.values())
    key = "than_trong" if score <= 5 else "can_bang" if score <= 10 else "tang_truong"
    return {"score": score, "max": 15, "profile": key, "label": RISK_PROFILES[key]["label"]}


def allocation(profile: str, age: int | None = None) -> dict[str, float]:
    base = {k: v for k, v in RISK_PROFILES.get(profile, RISK_PROFILES["can_bang"]).items() if k != "label"}
    if age:
        # Quy tắc tuổi: tỷ trọng cổ phiếu tối đa ≈ 110 − tuổi (%)
        cap = max(0.1, min(0.8, (110 - age) / 100))
        if base["Cổ phiếu"] > cap:
            excess = base["Cổ phiếu"] - cap
            base["Cổ phiếu"] = cap
            base["Trái phiếu/Quỹ trái phiếu"] += excess * 0.6
            base["Tiết kiệm ngân hàng"] += excess * 0.4
    return base


def plan(monthly_income: float, monthly_expenses: float, current_savings: float = 0.0,
         debts: list[dict] | None = None, goals: list[dict] | None = None, age: int | None = None,
         risk_profile: str = "can_bang", essential_expenses: float | None = None,
         emergency_months: int = 6) -> dict:
    """Lập kế hoạch tài chính cá nhân. Đơn vị: đồng/tháng."""
    debts = debts or []
    goals = goals or []
    surplus = monthly_income - monthly_expenses
    savings_rate = surplus / monthly_income if monthly_income else 0
    essential = essential_expenses if essential_expenses is not None else monthly_expenses * 0.7
    budget = {
        "needs": {"target": monthly_income * 0.5, "actual": essential},
        "wants": {"target": monthly_income * 0.3, "actual": monthly_expenses - essential},
        "savings": {"target": monthly_income * 0.2, "actual": surplus},
    }
    emergency_target = monthly_expenses * emergency_months
    emergency_gap = max(0.0, emergency_target - current_savings)
    debt_plan = sorted(debts, key=lambda d: -float(d.get("rate", 0)))
    high_interest = [d for d in debt_plan if float(d.get("rate", 0)) >= 0.12]
    alloc = allocation(risk_profile, age)
    exp_return = sum(w * ASSET_RETURNS[k] for k, w in alloc.items())

    goal_plans = []
    for g in goals:
        years = max(float(g.get("years", 1)), 0.1)
        n = int(round(years * 12))
        r_m = exp_return / 12
        fv_current = 0.0  # tiền hiện có ưu tiên cho quỹ dự phòng
        need = max(float(g["amount"]) - fv_current, 0)
        monthly = savings_payment(need, r_m, n)
        goal_plans.append({**g, "monthly_saving": monthly, "expected_return": exp_return,
                           "feasible": monthly <= max(surplus, 0),
                           "share_of_surplus": monthly / surplus if surplus > 0 else None})

    investable_monthly = max(surplus - (emergency_gap / 12 if emergency_gap else 0), 0)
    projection = []
    for years in (1, 3, 5, 10, 15, 20):
        fv = annuity(investable_monthly, exp_return / 12, years * 12)["fv"] + \
            current_savings * (1 + exp_return) ** years
        projection.append({"years": years, "value": fv})

    advice = []
    if surplus <= 0:
        advice.append("Chi tiêu đang vượt/hết thu nhập - cần cắt giảm chi tiêu 'mong muốn' trước khi đầu tư.")
    elif savings_rate < 0.2:
        advice.append(f"Tỷ lệ tiết kiệm {vn_pct(savings_rate, 0)} < 20%: hãy tự động trích tiết kiệm ngay khi nhận lương.")
    else:
        advice.append(f"Tỷ lệ tiết kiệm {vn_pct(savings_rate, 0)} - rất tốt, duy trì kỷ luật đầu tư định kỳ.")
    if emergency_gap > 0:
        advice.append(f"Ưu tiên xây quỹ dự phòng {emergency_months} tháng chi tiêu ({vn_num(emergency_target)}đ), "
                      f"còn thiếu {vn_num(emergency_gap)}đ - giữ ở tiết kiệm/CCQ thị trường tiền tệ.")
    if high_interest:
        advice.append("Trả trước các khoản nợ lãi suất ≥ 12%/năm (thẻ tín dụng, vay tiêu dùng) trước khi đầu tư "
                      "chứng khoán - đây là khoản 'lợi nhuận chắc chắn' bằng lãi suất tiết kiệm được.")
    advice.append("Không dùng margin khi chưa có kinh nghiệm; chỉ dùng ở mức phù hợp khi thị trường uptrend.")
    advice.append("Đầu tư cổ phiếu: phân tán 5-10 mã thuộc nhiều ngành, mỗi mã ≤ 20% danh mục, luôn đặt điểm cắt lỗ.")

    return {
        "summary": {"monthly_income": monthly_income, "monthly_expenses": monthly_expenses,
                    "surplus": surplus, "savings_rate": savings_rate,
                    "fire_number": monthly_expenses * 12 * 25},
        "budget_50_30_20": budget,
        "emergency_fund": {"months": emergency_months, "target": emergency_target,
                           "current": current_savings, "gap": emergency_gap},
        "debts_priority": debt_plan,
        "risk_profile": {"key": risk_profile, "label": RISK_PROFILES.get(risk_profile, RISK_PROFILES["can_bang"])["label"]},
        "allocation": [{"asset": k, "weight": w, "expected_return": ASSET_RETURNS[k],
                        "monthly_amount": investable_monthly * w} for k, w in alloc.items()],
        "portfolio_expected_return": exp_return,
        "investable_monthly": investable_monthly,
        "goals": goal_plans, "projection": projection, "advice": advice,
    }
