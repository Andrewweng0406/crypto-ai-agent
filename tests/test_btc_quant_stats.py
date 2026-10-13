import pytest

from btc_quant.stats import summarize_events


def _close(r, side="Long", reason="STOP", pnl=None):
    return {"kind": "close", "side": side, "reason": reason, "r_multiple": r, "net_pnl": pnl if pnl is not None else r * 20}


def test_summary_of_closed_trades():
    events = [
        _close(2.0, reason="TAKE_PROFIT"),
        _close(-1.0),
        _close(-1.1, side="Short"),
        _close(-2.3, reason="LIQUIDATION"),
        {"kind": "rebalance"},
    ]
    s = summarize_events(events, start_equity=1000.0)
    assert s["trades"] == 4
    assert s["wins"] == 1
    assert s["win_rate_pct"] == pytest.approx(25.0)
    assert s["avg_r"] == pytest.approx((2.0 - 1.0 - 1.1 - 2.3) / 4)
    assert s["best_r"] == pytest.approx(2.0)
    assert s["worst_r"] == pytest.approx(-2.3)
    assert s["liquidations"] == 1
    assert s["long"]["trades"] == 3
    assert s["short"]["trades"] == 1
    assert s["total_net_pnl"] == pytest.approx(sum(e["net_pnl"] for e in events if e["kind"] == "close"))


def test_max_drawdown_from_daily_equity_in_time_order():
    events = [
        {"kind": "daily_equity", "ts": "2026-10-03", "equity": 900.0},
        {"kind": "daily_equity", "ts": "2026-10-01", "equity": 1000.0},
        {"kind": "daily_equity", "ts": "2026-10-02", "equity": 1200.0},
        {"kind": "daily_equity", "ts": "2026-10-04", "equity": 1100.0},
    ]
    s = summarize_events(events, start_equity=1000.0)
    assert s["days_recorded"] == 4
    assert s["max_drawdown_pct"] == pytest.approx(-25.0)  # 1200 -> 900
    assert s["latest_equity"] == pytest.approx(1100.0)
    assert s["return_pct"] == pytest.approx(10.0)


def test_empty_events():
    s = summarize_events([], start_equity=1000.0)
    assert s["trades"] == 0
    assert s["win_rate_pct"] == 0.0
    assert s["avg_r"] == 0.0
    assert s["max_drawdown_pct"] == 0.0
