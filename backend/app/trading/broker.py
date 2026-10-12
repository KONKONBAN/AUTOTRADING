"""Môi giới: tài khoản giao dịch giấy (paper trading) và giao diện cho broker thật.

PaperBroker mô phỏng sát quy định Việt Nam:
- Lô chẵn 100 CP, giá phải nằm trong biên độ trần/sàn và đúng bước giá.
- Phí CTCK 0,15% (mua & bán), thuế TNCN 0,1% khi bán.
- Cổ phiếu mua về chỉ được bán sau T+2 ngày làm việc.
- Không cho phép mua vượt tiền mặt (không dùng margin).
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import date

import numpy as np

from ..config import settings
from ..data import providers, universe
from ..db import Database, get_db
from ..utils import vn_num
from . import vn_rules


class OrderError(ValueError):
    pass


def business_days_between(d1: date, d2: date) -> int:
    return int(np.busday_count(d1, d2))


class BrokerBase(ABC):
    name = "base"

    @abstractmethod
    def account(self) -> dict: ...

    @abstractmethod
    def place_order(self, ticker: str, side: str, quantity: int, price: float | None = None,
                    source: str = "manual", reason: str = "") -> dict: ...


class LiveBrokerAdapter(BrokerBase):
    """Khung kết nối broker thật (SSI FastConnect, DNSE, VPS...).

    Để giao dịch tiền thật, hãy cài đặt các phương thức dưới đây theo tài liệu API của công ty
    chứng khoán bạn sử dụng và đặt ALLOW_LIVE_TRADING=true. Ứng dụng KHÔNG gửi lệnh thật khi
    adapter chưa được cài đặt.
    """

    name = "live"

    def account(self) -> dict:
        raise NotImplementedError("Chưa cấu hình kết nối công ty chứng khoán (xem README - Giao dịch thật).")

    def place_order(self, ticker, side, quantity, price=None, source="manual", reason=""):
        if not settings.allow_live_trading:
            raise OrderError("Giao dịch thật đang TẮT (ALLOW_LIVE_TRADING=false).")
        raise NotImplementedError("Chưa cài đặt adapter broker thật.")


class PaperBroker(BrokerBase):
    name = "paper"

    def __init__(self, db: Database | None = None, fee_rate: float = vn_rules.DEFAULT_FEE_RATE):
        self.db = db or get_db()
        self.fee_rate = fee_rate
        if self.db.get_kv("paper_cash") is None:
            self.reset(settings.paper_initial_cash)

    # ------------------------------------------------------------------ state
    def reset(self, initial_cash: float) -> None:
        self.db.execute("DELETE FROM lots")
        self.db.execute("DELETE FROM orders WHERE broker='paper'")
        self.db.execute("DELETE FROM equity_history")
        self.db.set_kv("paper_cash", float(initial_cash))
        self.db.set_kv("paper_initial_cash", float(initial_cash))
        self.db.set_kv("paper_realized_pnl", 0.0)

    @property
    def cash(self) -> float:
        return float(self.db.get_kv("paper_cash", 0.0))

    def _set_cash(self, value: float) -> None:
        self.db.set_kv("paper_cash", float(value))

    def positions(self, prices: dict[str, float] | None = None) -> list[dict]:
        lots = self.db.query("SELECT * FROM lots ORDER BY ticker, buy_date")
        today = date.today()
        grouped: dict[str, dict] = {}
        for lot in lots:
            g = grouped.setdefault(lot["ticker"], {"ticker": lot["ticker"], "quantity": 0, "cost": 0.0,
                                                   "sellable": 0, "stop_loss": None, "take_profit": None,
                                                   "highest": None, "first_buy": lot["buy_date"]})
            g["quantity"] += lot["quantity"]
            g["cost"] += lot["quantity"] * lot["price"]
            if business_days_between(date.fromisoformat(lot["buy_date"]), today) >= vn_rules.SETTLEMENT_DAYS:
                g["sellable"] += lot["quantity"]
            g["stop_loss"] = lot["stop_loss"] if lot["stop_loss"] else g["stop_loss"]
            g["take_profit"] = lot["take_profit"] if lot["take_profit"] else g["take_profit"]
            g["highest"] = max(filter(None, [g["highest"], lot["highest"]]), default=None)
        out = []
        for g in grouped.values():
            price = (prices or {}).get(g["ticker"])
            if price is None:
                try:
                    price = providers.latest_price(g["ticker"])
                except Exception:  # noqa: BLE001
                    price = g["cost"] / g["quantity"]
            avg = g["cost"] / g["quantity"]
            value = price * g["quantity"]
            out.append({**g, "avg_price": avg, "market_price": price, "market_value": value,
                        "unrealized_pnl": value - g["cost"], "unrealized_pct": price / avg - 1,
                        "sector": universe.info(g["ticker"])["sector"]})
        return out

    def account(self, prices: dict[str, float] | None = None) -> dict:
        pos = self.positions(prices)
        mv = sum(p["market_value"] for p in pos)
        equity = self.cash + mv
        initial = float(self.db.get_kv("paper_initial_cash", settings.paper_initial_cash))
        for p in pos:
            p["weight"] = p["market_value"] / equity if equity else 0
        hist = self.db.query("SELECT date, equity, cash FROM equity_history ORDER BY date")
        peak = max([h["equity"] for h in hist] + [equity, initial])
        return {
            "broker": self.name, "cash": self.cash, "market_value": mv, "equity": equity,
            "initial_cash": initial, "total_return": equity / initial - 1 if initial else 0,
            "realized_pnl": float(self.db.get_kv("paper_realized_pnl", 0.0)),
            "unrealized_pnl": sum(p["unrealized_pnl"] for p in pos),
            "drawdown": equity / peak - 1 if peak else 0,
            "exposure": mv / equity if equity else 0, "positions": pos, "equity_history": hist,
        }

    def snapshot_equity(self) -> None:
        acc = self.account()
        self.db.execute("INSERT OR REPLACE INTO equity_history(date, equity, cash) VALUES(?,?,?)",
                        (date.today().isoformat(), acc["equity"], acc["cash"]))

    def orders(self, limit: int = 200) -> list[dict]:
        return self.db.query("SELECT * FROM orders WHERE broker='paper' ORDER BY id DESC LIMIT ?", (limit,))

    # ------------------------------------------------------------------ orders
    def _validate(self, ticker: str, side: str, quantity: int, price: float, reference: float) -> None:
        if side not in {"BUY", "SELL"}:
            raise OrderError("Loại lệnh phải là BUY hoặc SELL")
        if quantity <= 0:
            raise OrderError("Khối lượng phải lớn hơn 0")
        if quantity % vn_rules.LOT_SIZE != 0:
            raise OrderError(f"Khối lượng {quantity} không phải lô chẵn 100. Hãy tách lệnh: "
                             f"{vn_rules.split_order(quantity)}")
        ex = universe.info(ticker)["exchange"]
        lim = vn_rules.price_limits(reference, ex)
        if not (lim.floor <= price <= lim.ceiling):
            raise OrderError(f"Giá {vn_num(price)} ngoài biên độ [{vn_num(lim.floor)} - {vn_num(lim.ceiling)}]")

    def place_order(self, ticker: str, side: str, quantity: int, price: float | None = None,
                    source: str = "manual", reason: str = "", stop_loss: float | None = None,
                    take_profit: float | None = None) -> dict:
        """Khớp lệnh ngay tại giá chỉ định (hoặc giá đóng cửa gần nhất) - mô phỏng lệnh LO khớp."""
        ticker, side = ticker.upper(), side.upper()
        hist = providers.get_history(ticker, days=60)
        last_close = float(hist["close"].iloc[-1])
        reference = float(hist["close"].iloc[-2]) if len(hist) > 1 else last_close
        ex = universe.info(ticker)["exchange"]
        price = vn_rules.round_to_tick(price or last_close, ex)
        quantity = int(quantity)
        self._validate(ticker, side, quantity, price, reference)
        value = price * quantity
        costs = vn_rules.trade_costs(side, value, self.fee_rate)
        today = date.today().isoformat()
        if side == "BUY":
            need = value + costs["total"]
            if need > self.cash + 1e-6:
                raise OrderError(f"Không đủ tiền: cần {vn_num(need)}đ, có {vn_num(self.cash)}đ")
            self._set_cash(self.cash - need)
            self.db.execute(
                "INSERT INTO lots(ticker, quantity, price, buy_date, stop_loss, take_profit, highest) "
                "VALUES(?,?,?,?,?,?,?)",
                (ticker, quantity, (value + costs["total"]) / quantity, today, stop_loss, take_profit, price))
        else:
            pos = next((p for p in self.positions({ticker: price}) if p["ticker"] == ticker), None)
            if not pos or pos["sellable"] < quantity:
                raise OrderError(f"Không đủ cổ phiếu {ticker} khả dụng để bán (T+2): "
                                 f"có {pos['sellable'] if pos else 0}")
            remaining, cost_basis = quantity, 0.0
            for lot in self.db.query("SELECT * FROM lots WHERE ticker=? ORDER BY buy_date, id", (ticker,)):
                if remaining <= 0:
                    break
                if business_days_between(date.fromisoformat(lot["buy_date"]), date.today()) < vn_rules.SETTLEMENT_DAYS:
                    continue
                take = min(remaining, lot["quantity"])
                cost_basis += take * lot["price"]
                remaining -= take
                if take == lot["quantity"]:
                    self.db.execute("DELETE FROM lots WHERE id=?", (lot["id"],))
                else:
                    self.db.execute("UPDATE lots SET quantity=? WHERE id=?", (lot["quantity"] - take, lot["id"]))
            proceeds = value - costs["total"]
            self._set_cash(self.cash + proceeds)
            realized = float(self.db.get_kv("paper_realized_pnl", 0.0)) + proceeds - cost_basis
            self.db.set_kv("paper_realized_pnl", realized)
        cur = self.db.execute(
            "INSERT INTO orders(created_at, ticker, side, quantity, price, status, source, reason, fee, tax, filled_at, broker) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (time.time(), ticker, side, quantity, price, "FILLED", source, reason, costs["fee"], costs["tax"],
             time.time(), self.name))
        self.db.log_event("trade", f"{side} {quantity} {ticker} @ {vn_num(price)}", {"source": source, "reason": reason})
        return {"id": cur.lastrowid, "ticker": ticker, "side": side, "quantity": quantity, "price": price,
                "value": value, **costs, "status": "FILLED", "cash_after": self.cash}

    def update_risk_levels(self, ticker: str, stop_loss: float | None = None,
                           take_profit: float | None = None, highest: float | None = None) -> None:
        if stop_loss is not None:
            self.db.execute("UPDATE lots SET stop_loss=? WHERE ticker=?", (stop_loss, ticker))
        if take_profit is not None:
            self.db.execute("UPDATE lots SET take_profit=? WHERE ticker=?", (take_profit, ticker))
        if highest is not None:
            self.db.execute("UPDATE lots SET highest=MAX(COALESCE(highest,0), ?) WHERE ticker=?", (highest, ticker))


_broker: PaperBroker | None = None


def get_broker() -> PaperBroker:
    global _broker
    if _broker is None or _broker.db is not get_db():
        _broker = PaperBroker()
    return _broker
