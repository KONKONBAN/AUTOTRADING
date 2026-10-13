"""Bộ máy giao dịch tự động (Auto-Trader).

Thực thi Quy trình đầu tư cổ phiếu 4 bước (PTVĐTCK - Chương 2.1) một cách kỷ luật:
1. Lọc cổ phiếu theo điểm tổng hợp (kỹ thuật + cơ bản + định giá + rủi ro).
2. Mua khi xu hướng tăng xác nhận, CHIA NHIỀU LẦN (mua thăm dò 50% → gia tăng khi đúng hướng).
3. Bán khi: chạm cắt lỗ, trailing stop, xu hướng bị phá vỡ, thị trường chung phân phối,
   hoặc tìm được cổ phiếu tốt hơn.
4. Quản lý rủi ro: rủi ro ≤ x% vốn mỗi lệnh, tỷ trọng tối đa mỗi mã, giới hạn số mã,
   ngưng mua mới khi tài khoản sụt giảm quá ngưỡng (kill-switch).

Chế độ:
- "off":        tắt.
- "suggest":    chỉ tạo ĐỀ XUẤT lệnh, bạn duyệt trên giao diện (mặc định, an toàn).
- "auto_paper": tự động khớp lệnh trên tài khoản giao dịch giấy.
"""

from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime

from .. import services
from ..context import current_user_id
from ..data import providers, universe
from ..db import get_db
from ..utils import vn_num, vn_pct
from . import vn_rules
from .broker import OrderError, get_broker, normalize_ticker, quote

log = logging.getLogger(__name__)


@dataclass
class AutoTraderConfig:
    mode: str = "off"                     # off | suggest | auto_paper (tài khoản mới: TẮT cho tới khi bật)
    universe: str = "ALL"                 # ALL | VN30 | danh sách mã, ví dụ "FPT,HPG,MWG"
    max_positions: int = 8
    max_weight: float = 0.20              # "Không đầu tư toàn bộ vốn vào một cổ phiếu"
    risk_per_trade: float = 0.015         # rủi ro tối đa mỗi lệnh (% vốn)
    min_score: float = 65.0               # điểm tổng hợp tối thiểu để mua
    min_technical: float = 55.0           # điểm kỹ thuật tối thiểu (xác nhận xu hướng)
    stop_atr_multiple: float = 2.0
    max_stop_pct: float = 0.07            # cắt lỗ tối đa 7%
    trailing_stop_pct: float = 0.10       # bảo vệ lợi nhuận: bán khi giảm 10% từ đỉnh
    scale_in_gain: float = 0.03           # gia tăng vị thế khi lãi ≥ 3%
    max_drawdown_halt: float = 0.15       # ngưng mua mới khi tài khoản sụt ≥ 15%
    use_market_filter: bool = True        # điều chỉnh tỷ trọng theo trạng thái VN-Index
    run_time: str = "14:15"               # giờ chạy hằng ngày (trong phiên liên tục)
    sectors_excluded: list[str] = field(default_factory=list)


def load_config() -> AutoTraderConfig:
    """Cấu hình Auto-Trader của tài khoản đang đăng nhập."""
    raw = get_db().get_user_kv(current_user_id(), "autotrader_config") or {}
    cfg = AutoTraderConfig()
    for k, v in raw.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)
    return cfg


# Giới hạn hợp lệ cho tham số số (chặn NaN/vô cực/giá trị vô lý làm hỏng chu kỳ tự động)
_LIMITS = {
    "max_positions": (1, 50), "max_weight": (0.01, 1.0), "risk_per_trade": (0.001, 0.1), "min_score": (0, 100),
    "min_technical": (0, 100), "stop_atr_multiple": (0.5, 10), "max_stop_pct": (0.01, 0.5),
    "trailing_stop_pct": (0.01, 0.5), "scale_in_gain": (0, 1), "max_drawdown_halt": (0.01, 1),
}
_RUN_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def save_config(data: dict) -> AutoTraderConfig:
    cfg = load_config()
    for k, v in data.items():
        if not hasattr(cfg, k):
            continue
        cur = getattr(cfg, k)
        if isinstance(cur, bool):
            v = v if isinstance(v, bool) else str(v).lower() in {"1", "true", "yes", "on"}
        elif isinstance(cur, list):
            v = [str(x) for x in v] if isinstance(v, list) else []
        else:
            v = type(cur)(v)
        if k in _LIMITS:
            lo, hi = _LIMITS[k]
            if not math.isfinite(float(v)) or not lo <= float(v) <= hi:
                raise ValueError(f"{k} phải nằm trong khoảng {lo} - {hi}")
        setattr(cfg, k, v)
    if cfg.mode not in {"off", "suggest", "auto_paper"}:
        raise ValueError("mode phải là off | suggest | auto_paper")
    if not _RUN_TIME.match(cfg.run_time):
        raise ValueError("run_time phải có dạng HH:MM, ví dụ 14:15")
    get_db().set_user_kv(current_user_id(), "autotrader_config", asdict(cfg))
    return cfg


def _universe(cfg: AutoTraderConfig) -> set[str]:
    if cfg.universe.upper() == "ALL":
        tickers = set(universe.UNIVERSE)
    elif cfg.universe.upper() == "VN30":
        tickers = set(universe.VN30) & set(universe.UNIVERSE)
    else:
        tickers = {t.strip().upper() for t in cfg.universe.split(",") if t.strip()}
    return {t for t in tickers if universe.info(t)["sector"] not in cfg.sectors_excluded}


def _last_price(ticker: str) -> float:
    """Giá hiện tại để định giá đề xuất MUA giá thị trường (không có giá) khi giữ chỗ ngân sách."""
    try:
        return float(providers.latest_price(ticker))
    except Exception:  # noqa: BLE001
        return 0.0


NEUTRAL_EXPOSURE = 0.5


def _abnormal_gap(ticker: str) -> float | None:
    """Mức giảm của phiên gần nhất nếu VƯỢT biên độ sàn (không thể xảy ra khi giao dịch bình thường) → dấu hiệu
    ngày GDKHQ chia cổ tức bằng cổ phiếu / tách CP trên chuỗi giá chưa điều chỉnh."""
    try:
        close = providers.get_history(ticker, days=5)["close"]
    except Exception:  # noqa: BLE001
        return None
    if len(close) < 2 or not close.iloc[-2]:
        return None
    change = float(close.iloc[-1] / close.iloc[-2] - 1)
    band = vn_rules.PRICE_BANDS.get(universe.info(ticker)["exchange"].upper(), 0.07)
    return change if change < -(band + 0.01) else None


def plan_cycle(cfg: AutoTraderConfig | None = None) -> dict:
    """Lập kế hoạch lệnh cho chu kỳ hiện tại (chưa thực thi)."""
    cfg = cfg or load_config()
    broker = get_broker()
    acc = broker.account()
    equity, cash = acc["equity"], acc["cash"]
    market = services.market_overview()
    market_real = providers.is_tradeable_source(market.get("source"))
    if not cfg.use_market_filter:
        exposure_target = 0.95
    elif market_real:
        exposure_target = market["recommended_exposure"]
    else:
        exposure_target = NEUTRAL_EXPOSURE  # VN-Index đang là DEMO: không suy trạng thái thị trường từ dữ liệu giả
    actions: list[dict] = []
    notes: list[str] = [f"Thị trường: {market['regime']} → tỷ trọng cổ phiếu mục tiêu {vn_pct(exposure_target, 0)}."
                        if market_real or not cfg.use_market_filter else
                        "Chưa có dữ liệu thật của VN-Index → bỏ qua bộ lọc thị trường, tỷ trọng mục tiêu trung tính "
                        f"{vn_pct(exposure_target, 0)} và không bán vì lý do thị trường chung."]
    fee = vn_rules.DEFAULT_FEE_RATE
    # Đề xuất MUA đang chờ duyệt từ nguồn khác (AI Agent) có thể được duyệt → giữ chỗ ngân sách cho chúng.
    # Đề xuất cũ của chính Auto-Trader sẽ bị thay thế ở chu kỳ này nên không tính.
    pending_other = [p for p in list_proposals("pending") if p["source"] != "autotrader" and p["side"] == "BUY"]
    pending_tickers = {p["ticker"] for p in pending_other}
    pending_value = sum(p["quantity"] * (p["price"] or _last_price(p["ticker"])) for p in pending_other)
    cash_left = max(cash - pending_value, 0.0)
    # Ngân sách giải ngân dùng CHUNG cho cả mua gia tăng lẫn mua mới, không vượt tỷ trọng mục tiêu
    budget = max(0.0, equity * exposure_target - acc["market_value"] - pending_value)
    halted = acc["drawdown"] <= -cfg.max_drawdown_halt

    # ---------------- 1) Quản lý vị thế đang nắm giữ (bán) ----------------
    held = {p["ticker"]: p for p in acc["positions"]}
    for t, p in held.items():
        a = services.analyze_stock(t, include_chart=False)
        if not providers.is_tradeable_source(a["data_sources"]["prices"]) or not p.get("price_ok", True):
            # giá DEMO dự phòng (mất kết nối) không được ghi vào đỉnh giá / dùng để quyết định bán
            notes.append(f"{t}: chưa có giá thật (nguồn dữ liệu đang lỗi) - giữ nguyên vị thế, không xét mua/bán.")
            continue
        price = a["technical"]["price"]
        gap = _abnormal_gap(t)
        if gap is not None:
            notes.append(f"{t}: giá giảm {vn_pct(gap)} trong một phiên - vượt biên độ sàn, nhiều khả năng do chia cổ tức "
                         "bằng cổ phiếu / tách cổ phiếu (giá chưa điều chỉnh). Không tự động cắt lỗ phiên này - hãy kiểm tra.")
            continue
        broker.update_risk_levels(t, highest=price)
        highest = max(p.get("highest") or price, price)
        stop = p.get("stop_loss") or p["avg_price"] * (1 - cfg.max_stop_pct)
        reason = None
        if price <= stop:
            reason = f"Cắt lỗ: giá {vn_num(price)} ≤ điểm cắt lỗ {vn_num(stop)}"
        elif highest > p["avg_price"] * 1.05 and price <= highest * (1 - cfg.trailing_stop_pct):
            reason = f"Trailing stop: giảm {vn_pct(price / highest - 1)} từ đỉnh {vn_num(highest)} - bảo vệ lợi nhuận"
        elif a["technical"]["trend"] == "Giảm" and a["technical"]["score"] < 40:
            reason = "Xu hướng của cổ phiếu bị phá vỡ (dưới MA50, điểm kỹ thuật < 40)"
        elif a["composite"]["score"] < 35:
            reason = f"Điểm tổng hợp suy giảm còn {vn_num(a['composite']['score'])}"
        elif exposure_target <= 0.25 and p["unrealized_pct"] < 0:
            reason = "Thị trường chung phân phối/giảm - hạ tỷ trọng vị thế đang lỗ"
        if reason:
            qty = vn_rules.round_lot(p["sellable"])
            if qty > 0:
                actions.append({"ticker": t, "side": "SELL", "quantity": qty, "price": price, "reason": reason})
            else:
                notes.append(f"{t}: cần bán ({reason}) nhưng cổ phiếu chưa về tài khoản (T+2).")
        elif (p["unrealized_pct"] >= cfg.scale_in_gain and p["weight"] < cfg.max_weight * 0.6
              and a["composite"]["score"] >= cfg.min_score and not halted and budget > 0
              and t not in pending_tickers and providers.is_tradeable_source(a["data_sources"]["prices"])):
            add_value = min(equity * cfg.max_weight - p["market_value"], budget, cash_left * 0.9)
            qty = vn_rules.round_lot(add_value / (price * (1 + fee)))
            if qty > 0:
                actions.append({"ticker": t, "side": "BUY", "quantity": qty, "price": price,
                                "stop_loss": max(p["avg_price"], price * (1 - cfg.max_stop_pct)),
                                "reason": f"Gia tăng vị thế (mua lần 2): đang lãi {vn_pct(p['unrealized_pct'])}, "
                                          f"điểm {vn_num(a['composite']['score'])}"})
                spent = qty * price * (1 + fee)
                budget -= spent
                cash_left -= spent

    # ---------------- 2) Tìm cơ hội mua mới ----------------
    if halted:
        notes.append(f"KILL-SWITCH: tài khoản sụt {vn_pct(acc['drawdown'])} ≥ {vn_pct(cfg.max_drawdown_halt, 0)} - ngưng mua mới.")
    else:
        selling = {a["ticker"] for a in actions if a["side"] == "SELL"}
        n_pos = len(held) - len(selling) + len(pending_tickers - set(held))
        current_exposure = acc["market_value"] / equity if equity else 0
        allowed = _universe(cfg)
        screened = services.screen()
        demo_skipped = [r["ticker"] for r in screened if not providers.is_tradeable_source(r["source"])]
        if demo_skipped:
            notes.append(f"Bỏ qua {len(demo_skipped)} mã chưa có giá thật (đang dùng DEMO) - không giao dịch trên dữ liệu mô phỏng.")
        candidates = [r for r in screened
                      if r["ticker"] in allowed and r["ticker"] not in held and r["ticker"] not in pending_tickers
                      and providers.is_tradeable_source(r["source"])
                      and r["score"] >= cfg.min_score and r["parts"]["technical"] >= cfg.min_technical]
        if current_exposure >= exposure_target:
            notes.append(f"Tỷ trọng cổ phiếu hiện tại {vn_pct(current_exposure, 0)} ≥ mục tiêu - không mua mới.")
        for r in candidates:
            if n_pos >= cfg.max_positions or min(budget, cash_left) < 5_000_000:
                break
            price = r["price"]
            stop = max(r["stop_loss"], price * (1 - cfg.max_stop_pct))
            risk_ps = max(price - stop, price * 0.01)
            full_qty = min(equity * cfg.risk_per_trade / risk_ps, equity * cfg.max_weight / price)
            # mua thăm dò 50%
            qty = vn_rules.round_lot(min(full_qty * 0.5, min(budget, cash_left) / (price * (1 + fee))))
            if qty <= 0:
                continue
            actions.append({"ticker": r["ticker"], "side": "BUY", "quantity": qty, "price": price,
                            "stop_loss": stop,
                            "reason": f"Mua thăm dò: điểm {vn_num(r['score'])} ({r['recommendation']}), "
                                      f"kỹ thuật {vn_num(r['parts']['technical'])}, upside định giá "
                                      f"{vn_pct(r['upside'] or 0, 0, sign=True)}, cắt lỗ {vn_num(stop)}"})
            spent = qty * price * (1 + fee)
            budget -= spent
            cash_left -= spent
            n_pos += 1
        if not candidates:
            notes.append("Không có cổ phiếu đạt đủ tiêu chí mua trong chu kỳ này.")
    return {"time": datetime.now().isoformat(timespec="seconds"), "mode": cfg.mode,
            "market": {"regime": market["regime"], "exposure_target": exposure_target},
            "account": {k: acc[k] for k in ("equity", "cash", "exposure", "drawdown")},
            "actions": actions, "notes": notes}


def run_cycle(cfg: AutoTraderConfig | None = None, force_mode: str | None = None) -> dict:
    cfg = cfg or load_config()
    mode = force_mode or cfg.mode
    db = get_db()
    if mode in {"suggest", "auto_paper"}:
        # đề xuất cũ của Auto-Trader được thay bằng kế hoạch mới (tránh trùng lặp, mua gấp đôi)
        db.execute("UPDATE proposals SET status='expired' WHERE status='pending' AND source='autotrader' "
                   "AND user_id=?", (current_user_id(),))
    plan = plan_cycle(cfg)
    broker = get_broker()
    executed, proposed = [], []
    if mode == "off":
        plan["notes"].append("Auto-Trader đang TẮT - chỉ hiển thị kế hoạch.")
    for act in sorted(plan["actions"], key=lambda a: a["side"] != "SELL"):  # bán trước, mua sau
        if mode == "auto_paper":
            try:
                # lệnh thị trường: khớp tại giá hiện tại
                res = broker.place_order(act["ticker"], act["side"], act["quantity"], None,
                                         source="autotrader", reason=act["reason"],
                                         stop_loss=act.get("stop_loss"))
                executed.append({**act, "result": res})
            except Exception as exc:  # noqa: BLE001 - một lệnh lỗi (thiếu dữ liệu, sai luật) không dừng cả chu kỳ
                executed.append({**act, "error": str(exc)})
        elif mode == "suggest":
            cur = db.execute(
                "INSERT INTO proposals(user_id, created_at, ticker, side, quantity, price, stop_loss, take_profit, "
                "reason, source) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (current_user_id(), time.time(), act["ticker"], act["side"], act["quantity"], act["price"],
                 act.get("stop_loss"), act.get("take_profit"), act["reason"], "autotrader"))
            proposed.append({**act, "proposal_id": cur.lastrowid})
    broker.snapshot_equity()
    db.set_user_kv(current_user_id(), "autotrader_last_run", plan["time"])
    db.log_event("autotrader", f"Chu kỳ {mode}: {len(plan['actions'])} hành động", {"notes": plan["notes"]})
    return {**plan, "mode": mode, "executed": executed, "proposed": proposed}


# ------------------------------------------------------------------ proposals
def list_proposals(status: str | None = "pending") -> list[dict]:
    uid = current_user_id()
    if status:
        return get_db().query("SELECT * FROM proposals WHERE user_id=? AND status=? ORDER BY id DESC", (uid, status))
    return get_db().query("SELECT * FROM proposals WHERE user_id=? ORDER BY id DESC LIMIT 200", (uid,))


def last_run() -> str | None:
    return get_db().get_user_kv(current_user_id(), "autotrader_last_run")


def last_attempt() -> str | None:
    """Lần gần nhất bộ lập lịch BẮT ĐẦU chạy (kể cả khi lỗi) - để lỗi không bị thử lại mỗi phút."""
    return get_db().get_user_kv(current_user_id(), "autotrader_last_attempt") or last_run()


def mark_attempt(when: str) -> None:
    get_db().set_user_kv(current_user_id(), "autotrader_last_attempt", when)


SLIPPAGE = 0.02  # khi duyệt: chấp nhận giá hiện tại xấu hơn giá đề xuất tối đa 2%


def _approval_limit(p: dict) -> float | None:
    """Giá giới hạn khi thực thi đề xuất đã duyệt.

    - BÁN của Auto-Trader (cắt lỗ / trailing / thoát vị thế): lệnh thị trường - phải thực hiện được.
    - MUA: giá đề xuất + 2% (không mua đuổi), không vượt giá trần của phiên.
    - BÁN có giá (VD: AI Agent đề xuất chốt lời 139.000): giá đề xuất − 2%, không thấp hơn giá sàn;
      thị trường thấp hơn mức này thì lệnh không khớp thay vì bán rẻ hơn giá người dùng đã duyệt.
    """
    if not p["price"] or (p["side"] == "SELL" and p["source"] == "autotrader"):
        return None
    lim = quote(p["ticker"])["limits"]
    if p["side"] == "BUY":
        return min(p["price"] * (1 + SLIPPAGE), lim.ceiling)
    return max(p["price"] * (1 - SLIPPAGE), lim.floor)


def decide_proposal(pid: int, approve: bool) -> dict:
    db = get_db()
    # Giành quyền xử lý NGUYÊN TỬ: chỉ một yêu cầu chuyển được trạng thái pending → executing/rejected
    cur = db.execute("UPDATE proposals SET status=? WHERE id=? AND user_id=? AND status='pending'",
                     ("executing" if approve else "rejected", pid, current_user_id()))
    if cur.rowcount == 0:
        raise ValueError("Đề xuất không tồn tại hoặc đã được xử lý")
    if not approve:
        return {"id": pid, "status": "rejected"}
    p = db.query_one("SELECT * FROM proposals WHERE id=?", (pid,))
    try:
        limit = _approval_limit(p)
        res = get_broker().place_order(p["ticker"], p["side"], p["quantity"], limit,
                                       source=p["source"], reason=p["reason"] or "", stop_loss=p["stop_loss"],
                                       take_profit=p["take_profit"])
        db.execute("UPDATE proposals SET status='executed', result=? WHERE id=?", (str(res["id"]), pid))
        return {"id": pid, "status": "executed", "order": res}
    except Exception as exc:  # noqa: BLE001 - mọi lỗi đều phải giải phóng trạng thái 'executing'
        msg = str(exc) if isinstance(exc, OrderError) else f"Lỗi khi đặt lệnh: {exc}"
        db.execute("UPDATE proposals SET status='failed', result=? WHERE id=?", (msg, pid))
        return {"id": pid, "status": "failed", "error": msg}


def create_proposal(ticker: str, side: str, quantity: int, price: float | None, reason: str,
                    source: str = "agent", stop_loss: float | None = None,
                    take_profit: float | None = None) -> dict:
    ticker, side = normalize_ticker(ticker), side.strip().upper()
    if side not in {"BUY", "SELL"}:
        raise ValueError("side phải là BUY hoặc SELL")
    if not universe.is_listed(ticker) or providers.is_index(ticker):
        raise ValueError(f"Mã {ticker} không có trong danh sách cổ phiếu niêm yết (có thể gõ nhầm)")
    cur = get_db().execute(
        "INSERT INTO proposals(user_id, created_at, ticker, side, quantity, price, stop_loss, take_profit, reason, "
        "source) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (current_user_id(), time.time(), ticker, side, int(quantity), price, stop_loss, take_profit, reason, source))
    return {"proposal_id": cur.lastrowid, "status": "pending",
            "message": "Đã tạo đề xuất lệnh - cần người dùng duyệt trên tab Giao dịch."}
