"""Điểm tổng hợp & khuyến nghị đầu tư cho một mã cổ phiếu.

Quy trình đầu tư cổ phiếu (PTVĐTCK - Chương 2.1):
1. Lựa chọn cổ phiếu theo tiêu chí (cơ bản + định giá)  →  điểm chất lượng & định giá
2. Lựa chọn thời điểm mua (xu hướng, động lượng)        →  điểm kỹ thuật + trạng thái thị trường
3. Lựa chọn thời điểm bán (chốt lời / cắt lỗ)           →  mục tiêu giá, điểm cắt lỗ
4. Quản lý rủi ro danh mục                               →  khối lượng đề xuất, tỷ trọng tối đa
"""

from __future__ import annotations

from ..utils import vn_num, vn_pct

WEIGHTS = {"technical": 0.35, "quality": 0.30, "valuation": 0.20, "risk": 0.15}


def risk_score(risk: dict) -> float:
    vol = risk.get("volatility") or 0.3
    mdd = risk.get("max_drawdown") or -0.3
    sharpe = risk.get("sharpe") or 0
    s = 100 - (vol - 0.15) * 150 + mdd * 60 + sharpe * 10
    return float(max(0, min(100, s)))


def composite(tech: dict, quality: dict, val: dict, risk: dict, market: dict | None) -> dict:
    parts = {
        "technical": tech["score"],
        "quality": quality["score"],
        "valuation": val["score"],
        "risk": risk_score(risk),
    }
    # Thành phần thiếu dữ liệu (chưa có BCTC → chất lượng/định giá = None) bị loại, trọng số chia lại
    avail = {k: w for k, w in WEIGHTS.items() if parts[k] is not None}
    score = sum(parts[k] * w for k, w in avail.items()) / sum(avail.values())
    # Điều chỉnh theo thị trường chung (rủi ro hệ thống)
    if market:
        exposure = market["recommended_exposure"]
        score += (exposure - 0.5) * 10
    score = round(max(0, min(100, score)), 1)
    if score >= 72:
        rec, code = "MUA", "buy"
    elif score >= 60:
        rec, code = "TÍCH LŨY", "accumulate"
    elif score >= 45:
        rec, code = "NẮM GIỮ / THEO DÕI", "hold"
    elif score >= 35:
        rec, code = "GIẢM TỶ TRỌNG", "reduce"
    else:
        rec, code = "BÁN / TRÁNH", "sell"
    missing = [k for k in WEIGHTS if parts[k] is None]
    return {"score": score, "parts": {k: (round(v, 1) if v is not None else None) for k, v in parts.items()},
            "weights": {k: round(w / sum(avail.values()), 3) for k, w in avail.items()}, "recommendation": rec,
            "code": code, "missing_parts": missing,
            "note": ("Chưa có BCTC thật: điểm chỉ dựa trên kỹ thuật và rủi ro - thận trọng, hãy bổ sung BCTC."
                     if missing else None)}


def trade_plan(price: float, atr: float, tech: dict, val: dict, equity: float = 100_000_000,
               risk_per_trade: float = 0.02, max_weight: float = 0.20) -> dict:
    """Kế hoạch giao dịch: điểm mua, cắt lỗ, chốt lời, khối lượng theo rủi ro."""
    supports = tech["levels"].get("supports") or []
    resistances = tech["levels"].get("resistances") or []
    stop = max(price - 2 * atr, price * 0.93)  # cắt lỗ tối đa ~7%
    if supports and supports[0] < price and supports[0] > price * 0.88:
        stop = min(stop, supports[0] * 0.99)
    risk_per_share = max(price - stop, price * 0.01)
    target1 = resistances[0] if resistances else price + 2 * risk_per_share
    target1 = max(target1, price + 1.5 * risk_per_share)
    target2 = val.get("intrinsic_value") or price + 3 * risk_per_share
    target2 = max(target2, target1 * 1.05)
    qty_risk = equity * risk_per_trade / risk_per_share
    qty_cap = equity * max_weight / price
    qty = int(min(qty_risk, qty_cap) // 100 * 100)
    lower = price * 0.98
    if supports and supports[0] < price:
        lower = max(supports[0] * 1.01, price * 0.95)
    lower = min(lower, price * 0.995)
    return {
        "entry_zone": [round(lower, 0), round(price, 0)],
        "stop_loss": round(stop, 0), "stop_loss_pct": stop / price - 1,
        "take_profit_1": round(target1, 0), "take_profit_2": round(target2, 0),
        "reward_risk": (target1 - price) / risk_per_share,
        "suggested_quantity": qty, "position_value": qty * price,
        "assumptions": f"Rủi ro tối đa {vn_pct(risk_per_trade, 0)} vốn/lệnh, tỷ trọng ≤ {vn_pct(max_weight, 0)}, vốn {vn_num(equity)}đ",
        "rules": [
            "Mua chia 2-3 lần để phân tán rủi ro điểm vào (không mua toàn bộ một lần).",
            f"Cắt lỗ bắt buộc khi giá đóng cửa dưới {vn_num(stop)}đ.",
            "Chốt lời một phần ở mục tiêu 1, dời điểm cắt lỗ lên giá vốn.",
            "Bán khi xu hướng bị phá vỡ (đóng cửa dưới MA50) hoặc thị trường chung phân phối.",
        ],
    }
