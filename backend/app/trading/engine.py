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
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime

from .. import services
from ..data import universe
from ..db import get_db
from ..utils import vn_num, vn_pct
from . import vn_rules
from .broker import OrderError, get_broker

log = logging.getLogger(__name__)


@dataclass
class AutoTraderConfig:
    mode: str = "suggest"                 # off | suggest | auto_paper
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
    raw = get_db().get_kv("autotrader_config") or {}
    cfg = AutoTraderConfig()
    for k, v in raw.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)
    return cfg


def save_config(data: dict) -> AutoTraderConfig:
    cfg = load_config()
    for k, v in data.items():
        if not hasattr(cfg, k):
            continue
        cur = getattr(cfg, k)
        if isinstance(cur, bool):
            v = v if isinstance(v, bool) else str(v).lower() in {"1", "true", "yes", "on"}
        elif isinstance(cur, list):
            v = list(v)
        else:
            v = type(cur)(v)
        setattr(cfg, k, v)
    if cfg.mode not in {"off", "suggest", "auto_paper"}:
        raise ValueError("mode phải là off | suggest | auto_paper")
    get_db().set_kv("autotrader_config", asdict(cfg))
    return cfg


def _universe(cfg: AutoTraderConfig) -> set[str]:
    if cfg.universe.upper() == "ALL":
        tickers = set(universe.UNIVERSE)
    elif cfg.universe.upper() == "VN30":
        tickers = set(universe.VN30) & set(universe.UNIVERSE)
    else:
        tickers = {t.strip().upper() for t in cfg.universe.split(",") if t.strip()}
    return {t for t in tickers if universe.info(t)["sector"] not in cfg.sectors_excluded}


def plan_cycle(cfg: AutoTraderConfig | None = None) -> dict:
    """Lập kế hoạch lệnh cho chu kỳ hiện tại (chưa thực thi)."""
    cfg = cfg or load_config()
    broker = get_broker()
    acc = broker.account()
    equity, cash = acc["equity"], acc["cash"]
    market = services.market_overview()
    exposure_target = market["recommended_exposure"] if cfg.use_market_filter else 0.95
    actions: list[dict] = []
    notes: list[str] = [f"Thị trường: {market['regime']} → tỷ trọng cổ phiếu mục tiêu {vn_pct(exposure_target, 0)}."]

    # ---------------- 1) Quản lý vị thế đang nắm giữ (bán) ----------------
    held = {p["ticker"]: p for p in acc["positions"]}
    for t, p in held.items():
        a = services.analyze_stock(t, include_chart=False)
        price = a["technical"]["price"]
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
              and a["composite"]["score"] >= cfg.min_score and acc["drawdown"] > -cfg.max_drawdown_halt):
            add_value = min(equity * cfg.max_weight - p["market_value"], cash * 0.9)
            qty = vn_rules.round_lot(add_value / price)
            if qty > 0:
                actions.append({"ticker": t, "side": "BUY", "quantity": qty, "price": price,
                                "stop_loss": max(p["avg_price"], price * (1 - cfg.max_stop_pct)),
                                "reason": f"Gia tăng vị thế (mua lần 2): đang lãi {vn_pct(p['unrealized_pct'])}, "
                                          f"điểm {vn_num(a['composite']['score'])}"})

    # ---------------- 2) Tìm cơ hội mua mới ----------------
    if acc["drawdown"] <= -cfg.max_drawdown_halt:
        notes.append(f"KILL-SWITCH: tài khoản sụt {vn_pct(acc['drawdown'])} ≥ {vn_pct(cfg.max_drawdown_halt, 0)} - ngưng mua mới.")
    else:
        selling = {a["ticker"] for a in actions if a["side"] == "SELL"}
        n_pos = len(held) - len(selling)
        current_exposure = acc["market_value"] / equity if equity else 0
        budget = max(0.0, equity * exposure_target - acc["market_value"])
        budget = min(budget, cash - sum(a["quantity"] * a["price"] for a in actions if a["side"] == "BUY"))
        allowed = _universe(cfg)
        candidates = [r for r in services.screen()
                      if r["ticker"] in allowed and r["ticker"] not in held
                      and r["score"] >= cfg.min_score and r["parts"]["technical"] >= cfg.min_technical]
        if current_exposure >= exposure_target:
            notes.append(f"Tỷ trọng cổ phiếu hiện tại {vn_pct(current_exposure, 0)} ≥ mục tiêu - không mua mới.")
        for r in candidates:
            if n_pos >= cfg.max_positions or budget < 5_000_000:
                break
            price = r["price"]
            stop = max(r["stop_loss"], price * (1 - cfg.max_stop_pct))
            risk_ps = max(price - stop, price * 0.01)
            full_qty = min(equity * cfg.risk_per_trade / risk_ps, equity * cfg.max_weight / price)
            qty = vn_rules.round_lot(min(full_qty * 0.5, budget / price))  # mua thăm dò 50%
            if qty <= 0:
                continue
            actions.append({"ticker": r["ticker"], "side": "BUY", "quantity": qty, "price": price,
                            "stop_loss": stop,
                            "reason": f"Mua thăm dò: điểm {vn_num(r['score'])} ({r['recommendation']}), "
                                      f"kỹ thuật {vn_num(r['parts']['technical'])}, upside định giá "
                                      f"{vn_pct(r['upside'] or 0, 0, sign=True)}, cắt lỗ {vn_num(stop)}"})
            budget -= qty * price
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
    plan = plan_cycle(cfg)
    db = get_db()
    broker = get_broker()
    executed, proposed = [], []
    if mode == "off":
        plan["notes"].append("Auto-Trader đang TẮT - chỉ hiển thị kế hoạch.")
    for act in sorted(plan["actions"], key=lambda a: a["side"] != "SELL"):  # bán trước, mua sau
        if mode == "auto_paper":
            try:
                res = broker.place_order(act["ticker"], act["side"], act["quantity"], act["price"],
                                         source="autotrader", reason=act["reason"],
                                         stop_loss=act.get("stop_loss"))
                executed.append({**act, "result": res})
            except OrderError as exc:
                executed.append({**act, "error": str(exc)})
        elif mode == "suggest":
            cur = db.execute(
                "INSERT INTO proposals(created_at, ticker, side, quantity, price, stop_loss, take_profit, reason, source) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (time.time(), act["ticker"], act["side"], act["quantity"], act["price"],
                 act.get("stop_loss"), act.get("take_profit"), act["reason"], "autotrader"))
            proposed.append({**act, "proposal_id": cur.lastrowid})
    broker.snapshot_equity()
    db.set_kv("autotrader_last_run", plan["time"])
    db.log_event("autotrader", f"Chu kỳ {mode}: {len(plan['actions'])} hành động", {"notes": plan["notes"]})
    return {**plan, "mode": mode, "executed": executed, "proposed": proposed}


# ------------------------------------------------------------------ proposals
def list_proposals(status: str | None = "pending") -> list[dict]:
    if status:
        return get_db().query("SELECT * FROM proposals WHERE status=? ORDER BY id DESC", (status,))
    return get_db().query("SELECT * FROM proposals ORDER BY id DESC LIMIT 200")


def decide_proposal(pid: int, approve: bool) -> dict:
    db = get_db()
    p = db.query_one("SELECT * FROM proposals WHERE id=?", (pid,))
    if not p or p["status"] != "pending":
        raise ValueError("Đề xuất không tồn tại hoặc đã được xử lý")
    if not approve:
        db.execute("UPDATE proposals SET status='rejected' WHERE id=?", (pid,))
        return {"id": pid, "status": "rejected"}
    try:
        res = get_broker().place_order(p["ticker"], p["side"], p["quantity"], p["price"],
                                       source=p["source"], reason=p["reason"] or "", stop_loss=p["stop_loss"],
                                       take_profit=p["take_profit"])
        db.execute("UPDATE proposals SET status='executed', result=? WHERE id=?", (str(res["id"]), pid))
        return {"id": pid, "status": "executed", "order": res}
    except OrderError as exc:
        db.execute("UPDATE proposals SET status='failed', result=? WHERE id=?", (str(exc), pid))
        return {"id": pid, "status": "failed", "error": str(exc)}


def create_proposal(ticker: str, side: str, quantity: int, price: float | None, reason: str,
                    source: str = "agent", stop_loss: float | None = None,
                    take_profit: float | None = None) -> dict:
    cur = get_db().execute(
        "INSERT INTO proposals(created_at, ticker, side, quantity, price, stop_loss, take_profit, reason, source) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (time.time(), ticker.upper(), side.upper(), int(quantity), price, stop_loss, take_profit, reason, source))
    return {"proposal_id": cur.lastrowid, "status": "pending",
            "message": "Đã tạo đề xuất lệnh - cần người dùng duyệt trên tab Giao dịch."}
