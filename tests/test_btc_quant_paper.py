import pytest

from btc_quant.paper import FUTURES_FEE_PCT, SPOT_COST_PCT, PaperAccount
from btc_quant.signals import size_position

TS = "2026-10-13T00:00:00+00:00"


def _long(acc, entry=100.0, atr=1.0):
    order = size_position("Long", entry, atr, acc.equity(entry))
    acc.open(order, TS)
    return order


def test_rebalance_buys_to_target_with_cost():
    acc = PaperAccount.new(10_000)
    ev = acc.rebalance(0.5, 100.0, TS)
    assert ev["kind"] == "rebalance"
    assert acc.btc_qty == pytest.approx(50.0)
    assert acc.cash == pytest.approx(10_000 - 5_000 - 5_000 * SPOT_COST_PCT)


def test_rebalance_keeps_margin_reserved():
    acc = PaperAccount.new(10_000)
    order = _long(acc)
    acc.rebalance(1.0, 100.0, TS)
    assert acc.cash >= order.margin - 1e-9


def test_rebalance_ignores_tiny_change():
    acc = PaperAccount.new(10_000)
    acc.rebalance(0.5, 100.0, TS)
    current = acc.btc_qty * 100.0 / acc.equity(100.0)
    assert acc.rebalance(current + 0.00005, 100.0, TS) is None  # 差額約0.5 USDT < 1 USDT門檻
    assert acc.rebalance(current + 0.01, 100.0, TS) is not None


def test_stop_fills_at_stop_when_price_touches():
    acc = PaperAccount.new(10_000)
    o = _long(acc)
    ev = acc.on_price(o.stop_loss, TS)
    assert ev["reason"] == "STOP"
    assert ev["exit"] == pytest.approx(o.stop_loss)
    assert acc.position is None
    assert ev["r_multiple"] == pytest.approx(-1.0, abs=0.1)


def test_gap_through_stop_fills_at_worse_price():
    acc = PaperAccount.new(10_000)
    o = _long(acc)
    gap = (o.stop_loss + o.liquidation) / 2
    ev = acc.on_price(gap, TS, gap=True)
    assert ev["reason"] == "STOP"
    assert ev["exit"] == pytest.approx(gap)


def test_gap_through_liquidation_loses_only_margin():
    acc = PaperAccount.new(10_000)
    o = _long(acc)
    cash_before = acc.cash
    ev = acc.on_price(o.liquidation * 0.5, TS, gap=True)
    assert ev["reason"] == "LIQUIDATION"
    assert acc.cash == pytest.approx(cash_before - o.margin)
    assert acc.cash > 0


def test_take_profit_and_short_side():
    acc = PaperAccount.new(10_000)
    o = size_position("Short", 100.0, 1.0, 10_000)
    acc.open(o, TS)
    assert acc.on_price(99.0, TS) is None
    ev = acc.on_price(o.take_profit, TS)
    assert ev["reason"] == "TAKE_PROFIT"
    assert ev["pnl"] > 0


def test_funding_direction():
    acc = PaperAccount.new(10_000)
    o = _long(acc)
    cash = acc.cash
    acc.accrue_funding(0.0001, TS)
    assert acc.cash == pytest.approx(cash - o.notional * 0.0001)
    acc2 = PaperAccount.new(10_000)
    o2 = size_position("Short", 100.0, 1.0, 10_000)
    acc2.open(o2, TS)
    cash2 = acc2.cash
    acc2.accrue_funding(0.0001, TS)
    assert acc2.cash == pytest.approx(cash2 + o2.notional * 0.0001)
    assert PaperAccount.new(1).accrue_funding(0.01, TS) is None


def test_open_charges_fee_and_rejects_second_position():
    acc = PaperAccount.new(10_000)
    o = _long(acc)
    assert acc.cash == pytest.approx(10_000 - o.notional * FUTURES_FEE_PCT)
    with pytest.raises(RuntimeError):
        acc.open(o, TS)


def test_roundtrip_serialization():
    acc = PaperAccount.new(10_000)
    _long(acc)
    acc.rebalance(0.3, 100.0, TS)
    acc.last_daily_date = "2026-10-13"
    clone = PaperAccount.from_dict(acc.to_dict())
    assert clone == acc


def test_drawdown_tracks_peak():
    acc = PaperAccount.new(10_000)
    acc.rebalance(0.9, 100.0, TS)
    acc.mark(110.0)
    assert acc.drawdown_pct(110.0) == pytest.approx(0.0)
    assert acc.drawdown_pct(90.0) < 0


def test_continuous_cross_fills_at_resting_stop():
    # 價格連續移動時，交易所上的停損單會先在停損價成交，不會用之後看到的更差價格
    acc = PaperAccount.new(10_000)
    o = _long(acc)
    ev = acc.on_price((o.stop_loss + o.liquidation) / 2, TS)
    assert ev["reason"] == "STOP"
    assert ev["exit"] == pytest.approx(o.stop_loss)


def test_continuous_move_beyond_liquidation_is_still_a_stop():
    acc = PaperAccount.new(10_000)
    o = _long(acc)
    ev = acc.on_price(o.liquidation * 0.5, TS)
    assert ev["reason"] == "STOP"
    assert ev["r_multiple"] == pytest.approx(-1.0, abs=0.1)
