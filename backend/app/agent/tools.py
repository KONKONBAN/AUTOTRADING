"""Công cụ (tools) mà AI Agent quản trị tài sản được phép sử dụng.

An toàn: Agent KHÔNG thể tự khớp lệnh. Công cụ `propose_order` chỉ tạo ĐỀ XUẤT; người dùng phải
bấm duyệt trên giao diện thì lệnh mới được đặt.
"""

from __future__ import annotations

import json
from typing import Callable

import numpy as np

from .. import services
from ..data import universe
from ..finance import calculators as calc
from ..finance import planner
from ..portfolio import optimizer
from ..trading import backtest, engine
from ..trading.broker import get_broker
from ..utils import clean
from . import knowledge


_clean = clean


def _compact_analysis(a: dict) -> dict:
    fa, val, tech, rk = a["fundamental"], a["valuation"], a["technical"], a["risk"]
    return {
        "ticker": a["ticker"], "company": a["info"]["name"], "sector": a["info"]["sector"],
        "data_sources": a["data_sources"], "as_of": a["last_date"],
        "composite": a["composite"], "summary": a["summary"],
        "technical": {k: tech[k] for k in ("score", "signal", "trend", "price", "change_pct", "atr_pct",
                                           "levels", "performance", "patterns")}
        | {"key_signals": [{"name": s["name"], "note": s["note"]} for s in tech["signals"]][:12]},
        "fundamental": {"latest": {k: fa["latest"].get(k) for k in (
            "year", "roe", "roa", "lev", "roa_op", "sd", "leverage_spread", "net_margin", "asset_turnover",
            "current_ratio", "interest_coverage", "ocf_to_ni", "revenue_growth", "ni_growth", "eps", "bvps")},
            "quality_score": fa["quality"]["score"], "revenue_cagr": fa["quality"]["revenue_cagr"],
            "ni_cagr": fa["quality"]["ni_cagr"], "piotroski": fa["piotroski"]["score"],
            "mm_model": {k: fa["mm_model"].get(k) for k in ("regression", "b_star", "bs", "verdict")}},
        "valuation": {k: val[k] for k in ("intrinsic_value", "upside", "verdict", "multiples", "assumptions")}
        | {"models": [{"model": m["model"], "value": m["value"]} for m in val["models"]]},
        "risk": {k: rk.get(k) for k in ("level", "volatility", "beta", "sharpe", "max_drawdown", "cagr",
                                        "var_95_daily", "systematic_risk_share")},
        "trade_plan": a["trade_plan"],
    }


# ------------------------------------------------------------------ executors
def t_market_overview(**_) -> dict:
    m = services.market_overview()
    return {k: v for k, v in m.items() if k != "history"}


def t_analyze_stock(ticker: str, **_) -> dict:
    return _compact_analysis(services.analyze_stock(ticker.upper(), include_chart=False))


def t_compare_stocks(tickers: list[str], **_) -> dict:
    rows = []
    for t in tickers[:8]:
        a = services.analyze_stock(t.upper(), include_chart=False)
        rows.append({"ticker": a["ticker"], "score": a["composite"]["score"],
                     "recommendation": a["composite"]["recommendation"], "parts": a["composite"]["parts"],
                     "roe": a["fundamental"]["latest"]["roe"], "pe": a["valuation"]["multiples"]["pe"],
                     "pb": a["valuation"]["multiples"]["pb"], "upside": a["valuation"]["upside"],
                     "beta": a["risk"].get("beta"), "volatility": a["risk"]["volatility"],
                     "trend": a["technical"]["trend"]})
    return {"comparison": sorted(rows, key=lambda r: -r["score"])}


def t_screen_stocks(sector: str | None = None, top_n: int = 10, min_score: float = 0, **_) -> dict:
    rows = [r for r in services.screen(sector) if r["score"] >= min_score][:max(1, min(top_n, 30))]
    return {"count": len(rows), "results": [{k: r[k] for k in (
        "ticker", "name", "sector", "price", "score", "recommendation", "signal", "trend", "roe", "pe", "pb",
        "upside", "beta", "perf_20d", "source")} for r in rows],
        "sectors_available": universe.sectors()}


def t_get_portfolio(**_) -> dict:
    acc = get_broker().account()
    acc.pop("equity_history", None)
    acc["pending_proposals"] = engine.list_proposals("pending")
    return acc


def t_optimize_portfolio(tickers: list[str], objective: str = "max_sharpe", max_weight: float = 0.25,
                         capital: float | None = None, keep_frontier: bool = False, **_) -> dict:
    expected = {}
    for t in tickers:
        a = services.analyze_stock(t.upper(), include_chart=False)
        up = a["valuation"].get("upside")
        if up is not None:
            expected[t.upper()] = float(np.clip(up / 2, -0.3, 0.4)) + 0.03  # kỳ vọng 2 năm → năm, cộng rf
    res = optimizer.optimize(tickers, objective=objective, max_weight=max_weight, expected=expected)
    if not keep_frontier:
        res.pop("frontier", None)
    if capital:
        prices = {w["ticker"]: services.analyze_stock(w["ticker"], include_chart=False)["technical"]["price"]
                  for w in res["weights"]}
        res["allocation"] = optimizer.allocate(res["weights"], capital, prices)
    return res


def t_propose_order(ticker: str, side: str, quantity: int, reason: str, price: float | None = None,
                    stop_loss: float | None = None, take_profit: float | None = None, **_) -> dict:
    if int(quantity) % 100 != 0 or int(quantity) <= 0:
        return {"error": "Khối lượng phải là bội số của 100 (lô chẵn)."}
    return engine.create_proposal(ticker, side, int(quantity), price, reason, "agent", stop_loss, take_profit)


def t_autotrader_plan(**_) -> dict:
    return engine.plan_cycle()


def t_backtest(tickers: list[str] | None = None, min_score: float = 60, max_positions: int = 8,
               use_market_filter: bool = True, **_) -> dict:
    r = backtest.run_backtest(tickers=tickers, min_score=min_score, max_positions=max_positions,
                              use_market_filter=use_market_filter)
    return {"metrics": r["metrics"], "benchmark": r["benchmark"], "params": r["params"],
            "data_source": r["data_source"], "skipped_demo": r.get("skipped_demo"), "last_trades": r["trades"][-10:], "disclaimer": r["disclaimer"]}


CALCULATORS: dict[str, Callable] = {
    "simple_interest": calc.simple_interest, "compound_interest": calc.compound_interest,
    "annuity": calc.annuity, "annuity_payment": calc.annuity_payment, "savings_payment": calc.savings_payment,
    "loan_schedule": calc.loan_schedule, "discount_bill": calc.discount_bill,
    "project_appraisal": calc.project_appraisal, "capm": calc.capm, "wacc": calc.wacc,
    "bond_price": calc.bond_price, "bond_ytm": calc.bond_ytm, "convertible_bond": calc.convertible_bond,
    "lease_vs_buy": calc.lease_vs_buy,
}


def t_financial_calculator(calculator: str, params: dict, **_) -> dict:
    fn = CALCULATORS.get(calculator)
    if not fn:
        return {"error": f"Không có công cụ '{calculator}'. Có: {sorted(CALCULATORS)}"}
    res = fn(**params)
    if calculator == "loan_schedule" and len(res["schedule"]) > 24:
        res["schedule"] = res["schedule"][:12] + res["schedule"][-3:]
    return {"calculator": calculator, "result": res}


def t_personal_finance_plan(**kwargs) -> dict:
    return planner.plan(**kwargs)


def t_sector_analysis(sector: str, **_) -> dict:
    return services.sector_analysis(sector)


def t_search_knowledge(query: str, **_) -> dict:
    return {"knowledge": knowledge.search(query)}


EXECUTORS: dict[str, Callable[..., dict]] = {
    "get_market_overview": t_market_overview, "analyze_stock": t_analyze_stock,
    "compare_stocks": t_compare_stocks, "screen_stocks": t_screen_stocks, "get_portfolio": t_get_portfolio,
    "optimize_portfolio": t_optimize_portfolio, "propose_order": t_propose_order,
    "get_autotrader_plan": t_autotrader_plan, "run_backtest": t_backtest,
    "financial_calculator": t_financial_calculator, "personal_finance_plan": t_personal_finance_plan,
    "sector_analysis": t_sector_analysis, "search_knowledge": t_search_knowledge,
}

_TICKER = {"type": "string", "description": "Mã cổ phiếu, ví dụ FPT, HPG, VCB"}

TOOLS: list[dict] = [
    {"name": "get_market_overview",
     "description": "Trạng thái thị trường chung VN-Index theo mô hình market-timing lnP = a + b·t (xu hướng, độ lệch, "
                    "ngày phân phối) và tỷ trọng cổ phiếu khuyến nghị. Dùng trước khi khuyến nghị giải ngân.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "analyze_stock",
     "description": "Phân tích toàn diện 1 mã: kỹ thuật (MA, MACD, RSI, ADX, Ichimoku, Bollinger, mô hình nến, hỗ trợ/kháng cự), "
                    "cơ bản (ROE, ROA, đòn bẩy MM, DuPont, F-Score), định giá (DCF-WACC, P/B, P/E, DDM, Graham), rủi ro "
                    "(beta, biến động, drawdown) và kế hoạch giao dịch (điểm mua, cắt lỗ, chốt lời, khối lượng).",
     "input_schema": {"type": "object", "properties": {"ticker": _TICKER}, "required": ["ticker"],
                      "additionalProperties": False}},
    {"name": "compare_stocks",
     "description": "So sánh nhanh nhiều mã (tối đa 8) theo điểm tổng hợp, ROE, P/E, P/B, upside, beta.",
     "input_schema": {"type": "object", "properties": {"tickers": {"type": "array", "items": {"type": "string"}}},
                      "required": ["tickers"], "additionalProperties": False}},
    {"name": "screen_stocks",
     "description": "Lọc & xếp hạng cổ phiếu trong danh sách theo dõi theo điểm tổng hợp. Có thể lọc theo ngành.",
     "input_schema": {"type": "object", "properties": {
         "sector": {"type": "string", "description": "Tên ngành, ví dụ 'Ngân hàng', 'Công nghệ'"},
         "top_n": {"type": "integer", "description": "Số mã trả về (mặc định 10)"},
         "min_score": {"type": "number", "description": "Điểm tối thiểu 0-100"}}, "additionalProperties": False}},
    {"name": "get_portfolio",
     "description": "Tài khoản & danh mục hiện tại: tiền mặt, vị thế, lãi/lỗ, tỷ trọng, drawdown, đề xuất lệnh đang chờ duyệt.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "optimize_portfolio",
     "description": "Tối ưu tỷ trọng danh mục Markowitz (max Sharpe hoặc min variance) với giới hạn tỷ trọng mỗi mã; "
                    "có thể phân bổ số cổ phiếu theo số vốn.",
     "input_schema": {"type": "object", "properties": {
         "tickers": {"type": "array", "items": {"type": "string"}},
         "objective": {"type": "string", "enum": ["max_sharpe", "min_variance"]},
         "max_weight": {"type": "number", "description": "Tỷ trọng tối đa mỗi mã, ví dụ 0.25"},
         "capital": {"type": "number", "description": "Số vốn (đồng) để phân bổ thành số cổ phiếu"}},
         "required": ["tickers"], "additionalProperties": False}},
    {"name": "propose_order",
     "description": "Tạo ĐỀ XUẤT lệnh mua/bán trên tài khoản. Lệnh KHÔNG được khớp ngay - người dùng phải duyệt trên giao "
                    "diện. Chỉ dùng khi người dùng muốn giao dịch; luôn kèm lý do, điểm cắt lỗ khi mua. Khối lượng là bội số 100.",
     "input_schema": {"type": "object", "properties": {
         "ticker": _TICKER, "side": {"type": "string", "enum": ["BUY", "SELL"]},
         "quantity": {"type": "integer", "description": "Số cổ phiếu (bội số của 100)"},
         "price": {"type": "number", "description": "Giá đặt (đồng); bỏ trống = giá thị trường gần nhất"},
         "stop_loss": {"type": "number"}, "take_profit": {"type": "number"},
         "reason": {"type": "string"}}, "required": ["ticker", "side", "quantity", "reason"],
         "additionalProperties": False}},
    {"name": "get_autotrader_plan",
     "description": "Xem kế hoạch lệnh mà Auto-Trader sẽ thực hiện ở chu kỳ hiện tại (chưa thực thi).",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "run_backtest",
     "description": "Kiểm định lại chiến lược tự động trên dữ liệu lịch sử, so với VN-Index.",
     "input_schema": {"type": "object", "properties": {
         "tickers": {"type": "array", "items": {"type": "string"}},
         "min_score": {"type": "number"}, "max_positions": {"type": "integer"},
         "use_market_filter": {"type": "boolean"}}, "additionalProperties": False}},
    {"name": "financial_calculator",
     "description": "Máy tính tài chính. calculator ∈ {simple_interest(pv,rate,periods), compound_interest(pv,rate,periods,m), "
                    "annuity(payment,rate,n,due), annuity_payment(pv,rate,n), savings_payment(target_fv,rate,n), "
                    "loan_schedule(principal,rate,n,method='annuity'|'equal_principal'), discount_bill(face,rate,days,fee), "
                    "project_appraisal(cashflows,rate), capm(rf,beta,market_return|mrp), "
                    "wacc(equity_value,debt_value,cost_equity,cost_debt,tax_rate), bond_price(face,coupon_rate,market_rate,years,freq), "
                    "bond_ytm(price,face,coupon_rate,years,freq), convertible_bond(face,conversion_price,stock_price), "
                    "lease_vs_buy(asset_cost,lease_payment,years,pre_tax_debt_rate,tax_rate,salvage)}. Lãi suất dạng thập phân (0.1 = 10%).",
     "input_schema": {"type": "object", "properties": {
         "calculator": {"type": "string", "enum": sorted(CALCULATORS)},
         "params": {"type": "object", "description": "Tham số của công cụ"}},
         "required": ["calculator", "params"], "additionalProperties": False}},
    {"name": "personal_finance_plan",
     "description": "Lập kế hoạch tài chính cá nhân: ngân sách 50/30/20, quỹ dự phòng, ưu tiên trả nợ, phân bổ tài sản theo "
                    "khẩu vị rủi ro, số tiền cần tiết kiệm cho từng mục tiêu, dự phóng tài sản. Đơn vị: đồng/tháng.",
     "input_schema": {"type": "object", "properties": {
         "monthly_income": {"type": "number"}, "monthly_expenses": {"type": "number"},
         "current_savings": {"type": "number"}, "age": {"type": "integer"},
         "risk_profile": {"type": "string", "enum": ["than_trong", "can_bang", "tang_truong"]},
         "debts": {"type": "array", "items": {"type": "object", "properties": {
             "name": {"type": "string"}, "amount": {"type": "number"}, "rate": {"type": "number"}}}},
         "goals": {"type": "array", "items": {"type": "object", "properties": {
             "name": {"type": "string"}, "amount": {"type": "number"}, "years": {"type": "number"}}}}},
         "required": ["monthly_income", "monthly_expenses"], "additionalProperties": False}},
    {"name": "sector_analysis",
     "description": "Phân tích ngành: phân rã Mundlak ROE–ROA (quan hệ trạng thái vs động lực), P/E, P/B trung vị ngành.",
     "input_schema": {"type": "object", "properties": {"sector": {"type": "string"}}, "required": ["sector"],
                      "additionalProperties": False}},
    {"name": "search_knowledge",
     "description": "Tra cứu kiến thức nền tảng (giáo trình chứng khoán, tài chính, kế toán của người dùng) theo chủ đề.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"],
                      "additionalProperties": False}},
]


def execute(name: str, args: dict) -> tuple[str, bool]:
    """Thực thi tool → (chuỗi JSON kết quả, is_error)."""
    fn = EXECUTORS.get(name)
    if not fn:
        return json.dumps({"error": f"Công cụ không tồn tại: {name}"}, ensure_ascii=False), True
    try:
        out = _clean(fn(**(args or {})))
        text = json.dumps(out, ensure_ascii=False, default=str)
        if len(text) > 30_000:
            text = text[:30_000] + '..."(đã rút gọn)"'
        return text, False
    except Exception as exc:  # noqa: BLE001 - trả lỗi cho model tự xử lý
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), True
