"""Môi giới: tài khoản giao dịch giấy (paper trading) và giao diện cho broker thật.

PaperBroker mô phỏng sát quy định Việt Nam:
- Lô chẵn 100 CP, giá phải nằm trong biên độ trần/sàn và đúng bước giá.
- Phí CTCK 0,15% (mua & bán), thuế TNCN 0,1% khi bán.
- Cổ phiếu mua về chỉ được bán sau T+2 ngày làm việc.
- Không cho phép mua vượt tiền mặt (không dùng margin).
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from datetime import date

import numpy as np

from ..config import settings
from ..context import current_user_id
from ..data import providers, universe
from ..db import Database, get_db
from ..utils import vn_num
from . import vn_rules


class OrderError(ValueError):
    pass


# Mọi thao tác đọc-ghi tiền mặt/lô cổ phiếu đi qua một khóa để hai lệnh đồng thời không ghi đè nhau
_ORDER_LOCK = threading.RLock()


PRICE_EPS = 0.005  # giá nhập file ×1000 có thể lệch dấu phẩy động (32199.9999…) - không coi là khác giá


def quote(ticker: str) -> dict:
    """Giá khớp gần nhất, giá tham chiếu và biên độ trần/sàn của phiên (từ nguồn giá giao dịch được)."""
    ticker = normalize_ticker(ticker)
    hist = providers.get_history(ticker, days=60)
    if not providers.is_tradeable_source(hist.attrs.get("source")):
        raise OrderError(f"Chưa có giá thật cho {ticker} (đang dùng dữ liệu DEMO) - không thể đặt lệnh. "
                         "Hãy kiểm tra kết nối nguồn dữ liệu hoặc tải file giá lên.")
    last = round(float(hist["close"].iloc[-1]), 2)
    reference = round(float(hist["close"].iloc[-2]), 2) if len(hist) > 1 else last
    ex = universe.info(ticker)["exchange"]
    return {"last": last, "reference": reference, "exchange": ex, "limits": vn_rules.price_limits(reference, ex)}


def normalize_ticker(ticker: str) -> str:
    return (ticker or "").strip().upper()


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

    """Tài khoản giao dịch giấy của NGƯỜI DÙNG HIỆN TẠI (lấy từ ngữ cảnh đăng nhập)."""

    def __init__(self, db: Database | None = None, fee_rate: float = vn_rules.DEFAULT_FEE_RATE):
        self.db = db or get_db()
        self.fee_rate = fee_rate

    # ------------------------------------------------------------------ state
    @property
    def uid(self) -> int:
        return current_user_id()

    def _kv(self, key: str, default=None):
        return self.db.get_user_kv(self.uid, key, default)

    def _set_kv(self, key: str, value) -> None:
        self.db.set_user_kv(self.uid, key, value)

    def _ensure(self) -> None:
        """Tài khoản mới: khởi tạo vốn ban đầu."""
        if self._kv("paper_cash") is None:
            self.reset(settings.paper_initial_cash)

    def reset(self, initial_cash: float) -> None:
        uid = self.uid
        with _ORDER_LOCK:
            self.db.execute("DELETE FROM lots WHERE user_id=?", (uid,))
            self.db.execute("DELETE FROM orders WHERE broker='paper' AND user_id=?", (uid,))
            self.db.execute("DELETE FROM equity_history WHERE user_id=?", (uid,))
            self.db.execute("UPDATE proposals SET status='expired' WHERE status IN ('pending', 'executing') "
                            "AND user_id=?", (uid,))
            self._set_kv("paper_cash", float(initial_cash))
            self._set_kv("paper_initial_cash", float(initial_cash))
            self._set_kv("paper_realized_pnl", 0.0)

    @property
    def cash(self) -> float:
        self._ensure()
        return float(self._kv("paper_cash", 0.0))

    def _set_cash(self, value: float) -> None:
        self._set_kv("paper_cash", float(value))

    def positions(self, prices: dict[str, float] | None = None) -> list[dict]:
        lots = self.db.query("SELECT * FROM lots WHERE user_id=? ORDER BY ticker, buy_date", (self.uid,))
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
        initial = float(self._kv("paper_initial_cash", settings.paper_initial_cash))
        for p in pos:
            p["weight"] = p["market_value"] / equity if equity else 0
        hist = self.db.query("SELECT date, equity, cash FROM equity_history WHERE user_id=? ORDER BY date", (self.uid,))
        peak = max([h["equity"] for h in hist] + [equity, initial])
        return {
            "broker": self.name, "cash": self.cash, "market_value": mv, "equity": equity,
            "initial_cash": initial, "total_return": equity / initial - 1 if initial else 0,
            "realized_pnl": float(self._kv("paper_realized_pnl", 0.0)),
            "unrealized_pnl": sum(p["unrealized_pnl"] for p in pos),
            "drawdown": equity / peak - 1 if peak else 0,
            "exposure": mv / equity if equity else 0, "positions": pos, "equity_history": hist,
        }

    def snapshot_equity(self) -> None:
        acc = self.account()
        self.db.execute("INSERT OR REPLACE INTO equity_history(user_id, date, equity, cash) VALUES(?,?,?,?)",
                        (self.uid, date.today().isoformat(), acc["equity"], acc["cash"]))

    def orders(self, limit: int = 200) -> list[dict]:
        return self.db.query("SELECT * FROM orders WHERE broker='paper' AND user_id=? ORDER BY id DESC LIMIT ?",
                             (self.uid, limit))

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
        with _ORDER_LOCK:
            return self._place_order(ticker, side, quantity, price, source, reason, stop_loss, take_profit)

    def _place_order(self, ticker: str, side: str, quantity: int, price: float | None, source: str,
                     reason: str, stop_loss: float | None, take_profit: float | None) -> dict:
        """Mô phỏng lệnh LO: `price` là GIÁ GIỚI HẠN (bỏ trống = lệnh thị trường).

        Lệnh chỉ khớp khi thị trường cho phép (mua: giới hạn ≥ giá hiện tại; bán: giới hạn ≤ giá hiện tại)
        và luôn khớp tại GIÁ THỊ TRƯỜNG hiện tại - không bao giờ khớp ở mức giá thị trường chưa từng đạt.
        """
        ticker, side = normalize_ticker(ticker), side.upper().strip()
        if not ticker:
            raise OrderError("Thiếu mã cổ phiếu")
        if not universe.is_listed(ticker) or providers.is_index(ticker):
            raise OrderError(f"Mã {ticker} không có trong danh sách cổ phiếu niêm yết và chưa có dữ liệu giá nhập - "
                             "kiểm tra lại mã (có thể gõ nhầm).")
        q = quote(ticker)
        last_close, reference, ex = q["last"], q["reference"], q["exchange"]
        quantity = int(quantity)
        if price is not None:
            limit = vn_rules.round_to_tick(float(price), ex)
            self._validate(ticker, side, quantity, limit, reference)
            if side == "BUY" and limit < last_close - PRICE_EPS:
                raise OrderError(f"Giá mua {vn_num(limit)} thấp hơn giá thị trường {vn_num(last_close)} - lệnh LO "
                                 "sẽ chưa khớp. Hãy đặt giá ≥ giá thị trường hoặc chờ giá về vùng mua.")
            if side == "SELL" and limit > last_close + PRICE_EPS:
                raise OrderError(f"Giá bán {vn_num(limit)} cao hơn giá thị trường {vn_num(last_close)} - lệnh LO "
                                 "sẽ chưa khớp.")
        price = last_close
        self._validate(ticker, side, quantity, price, price)  # khớp tại giá thị trường (luôn trong biên độ)
        value = price * quantity
        costs = vn_rules.trade_costs(side, value, self.fee_rate)
        today = date.today().isoformat()
        if side == "BUY":
            need = value + costs["total"]
            if need > self.cash + 1e-6:
                raise OrderError(f"Không đủ tiền: cần {vn_num(need)}đ, có {vn_num(self.cash)}đ")
            self._set_cash(self.cash - need)
            self.db.execute(
                "INSERT INTO lots(user_id, ticker, quantity, price, buy_date, stop_loss, take_profit, highest) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (self.uid, ticker, quantity, (value + costs["total"]) / quantity, today, stop_loss, take_profit, price))
        else:
            pos = next((p for p in self.positions({ticker: price}) if p["ticker"] == ticker), None)
            if not pos or pos["sellable"] < quantity:
                raise OrderError(f"Không đủ cổ phiếu {ticker} khả dụng để bán (T+2): "
                                 f"có {pos['sellable'] if pos else 0}")
            remaining, cost_basis = quantity, 0.0
            for lot in self.db.query("SELECT * FROM lots WHERE user_id=? AND ticker=? ORDER BY buy_date, id",
                                     (self.uid, ticker)):
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
            realized = float(self._kv("paper_realized_pnl", 0.0)) + proceeds - cost_basis
            self._set_kv("paper_realized_pnl", realized)
        cur = self.db.execute(
            "INSERT INTO orders(user_id, created_at, ticker, side, quantity, price, status, source, reason, fee, tax, "
            "filled_at, broker) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.uid, time.time(), ticker, side, quantity, price, "FILLED", source, reason, costs["fee"], costs["tax"],
             time.time(), self.name))
        self.db.log_event("trade", f"{side} {quantity} {ticker} @ {vn_num(price)}", {"source": source, "reason": reason})
        return {"id": cur.lastrowid, "ticker": ticker, "side": side, "quantity": quantity, "price": price,
                "value": value, **costs, "status": "FILLED", "cash_after": self.cash}

    def update_risk_levels(self, ticker: str, stop_loss: float | None = None,
                           take_profit: float | None = None, highest: float | None = None) -> None:
        if stop_loss is not None:
            self.db.execute("UPDATE lots SET stop_loss=? WHERE user_id=? AND ticker=?", (stop_loss, self.uid, ticker))
        if take_profit is not None:
            self.db.execute("UPDATE lots SET take_profit=? WHERE user_id=? AND ticker=?", (take_profit, self.uid, ticker))
        if highest is not None:
            self.db.execute("UPDATE lots SET highest=MAX(COALESCE(highest,0), ?) WHERE user_id=? AND ticker=?",
                            (highest, self.uid, ticker))


_broker: PaperBroker | None = None


def get_broker() -> PaperBroker:
    global _broker
    if _broker is None or _broker.db is not get_db():
        _broker = PaperBroker()
    return _broker
