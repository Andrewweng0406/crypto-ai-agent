"""BTC 量化紙上帳戶：現貨趨勢部位 + 單一逐倉合約部位，共用同一筆本金。

保證金不從現金扣出，只在調倉時保留（reserved_margin），
所以 equity = 現金 + 現貨市值 + 合約未實現損益。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Optional

from btc_quant.signals import TacticalOrder

SPOT_COST_PCT = 0.001      # 現貨調整：手續費+滑價
FUTURES_FEE_PCT = 0.0005   # 合約每邊手續費
MIN_REBALANCE_USDT = 1.0


@dataclass
class PaperAccount:
    start_equity: float
    cash: float
    btc_qty: float = 0.0
    position: Optional[dict] = None
    peak_equity: float = 0.0
    last_price: float = 0.0
    last_daily_date: Optional[str] = None
    last_4h_bar_ts: Optional[int] = None
    last_funding_ts: Optional[int] = None
    last_tick_ms: Optional[int] = None
    dd_alerted: bool = False

    @classmethod
    def new(cls, equity: float) -> "PaperAccount":
        return cls(start_equity=equity, cash=equity, peak_equity=equity)

    def unrealized(self, price: float) -> float:
        p = self.position
        if not p:
            return 0.0
        sign = 1 if p["side"] == "Long" else -1
        return sign * p["notional"] * (price - p["entry"]) / p["entry"]

    def equity(self, price: float) -> float:
        return self.cash + self.btc_qty * price + self.unrealized(price)

    def reserved_margin(self) -> float:
        return self.position["margin"] if self.position else 0.0

    def mark(self, price: float) -> None:
        self.last_price = price
        self.peak_equity = max(self.peak_equity, self.equity(price))

    def drawdown_pct(self, price: float) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return (self.equity(price) / self.peak_equity - 1) * 100

    def rebalance(self, target: float, price: float, ts: str) -> Optional[dict]:
        eq = self.equity(price)
        delta_qty = max(0.0, target) * eq / price - self.btc_qty
        if delta_qty > 0:
            spendable = max(0.0, self.cash - self.reserved_margin())
            delta_qty = min(delta_qty, spendable / (price * (1 + SPOT_COST_PCT)))
        traded = abs(delta_qty) * price
        if traded < MIN_REBALANCE_USDT:
            self.mark(price)
            return None
        cost = traded * SPOT_COST_PCT
        self.cash -= delta_qty * price + cost
        self.btc_qty += delta_qty
        self.mark(price)
        return {
            "kind": "rebalance", "ts": ts, "target": target, "price": price,
            "delta_qty": delta_qty, "btc_qty": self.btc_qty, "cost": cost, "equity": self.equity(price),
        }

    def open(self, order: TacticalOrder, ts: str) -> Optional[dict]:
        if self.position:
            raise RuntimeError("already holding a tactical position")
        fee = order.notional * FUTURES_FEE_PCT
        free_cash = self.cash - fee
        if free_cash <= 0:
            return None
        if order.margin > free_cash:  # 交易所會拒單：依可用現金縮小部位
            scale = free_cash / order.margin
            order = replace(order, notional=order.notional * scale, margin=free_cash)
            fee = order.notional * FUTURES_FEE_PCT
        risk_amount = order.notional * order.stop_pct  # = 進場時權益的 2%
        self.cash -= fee
        self.position = {
            **asdict(order),
            "opened_at": ts,
            "open_fee": fee,
            "funding_paid": 0.0,
            "risk_amount": risk_amount,
        }
        self.mark(order.entry)
        return {"kind": "open", "ts": ts, **self.position, "equity": self.equity(order.entry)}

    def on_price(self, price: float, ts: str, gap: bool = False) -> Optional[dict]:
        """gap=False：價格連續移動，交易所停損單會在停損價成交。
        gap=True：價格跳空（新K棒開盤、報價中斷），以較差價成交；跳過強平價則只損失逐倉保證金。"""
        p = self.position
        if p:
            long = p["side"] == "Long"
            hit_stop = price <= p["stop_loss"] if long else price >= p["stop_loss"]
            hit_tp = price >= p["take_profit"] if long else price <= p["take_profit"]
            if hit_stop:
                if not gap:
                    return self._close(p["stop_loss"], "STOP", price, ts)
                beyond_liq = price <= p["liquidation"] if long else price >= p["liquidation"]
                if beyond_liq:
                    return self._close(None, "LIQUIDATION", price, ts)
                fill = min(price, p["stop_loss"]) if long else max(price, p["stop_loss"])
                return self._close(fill, "STOP", price, ts)
            if hit_tp:
                return self._close(p["take_profit"], "TAKE_PROFIT", price, ts)
        self.mark(price)
        return None

    def _close(self, fill: Optional[float], reason: str, price: float, ts: str) -> dict:
        p = self.position
        sign = 1 if p["side"] == "Long" else -1
        if fill is None:  # 逐倉：跳空穿過強平價只損失該筆保證金
            pnl = -p["margin"]
            exit_price = p["liquidation"]
        else:
            pnl = sign * p["notional"] * (fill - p["entry"]) / p["entry"] - p["notional"] * FUTURES_FEE_PCT
            exit_price = fill
        self.cash += pnl
        net = pnl - p["open_fee"] - p["funding_paid"]
        self.position = None
        self.mark(price)
        return {
            "kind": "close", "ts": ts, "reason": reason, "side": p["side"], "entry": p["entry"],
            "exit": exit_price, "pnl": pnl, "net_pnl": net, "r_multiple": net / p["risk_amount"],
            "opened_at": p["opened_at"], "equity": self.equity(price),
        }

    def accrue_funding(self, rate: float, ts: str) -> Optional[dict]:
        p = self.position
        if not p:
            return None
        sign = 1 if p["side"] == "Long" else -1
        amount = sign * p["notional"] * rate  # 正值=付出
        self.cash -= amount
        p["funding_paid"] += amount
        return {"kind": "funding", "ts": ts, "rate": rate, "amount": amount}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PaperAccount":
        return cls(**data)
