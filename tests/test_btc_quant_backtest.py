import numpy as np
import pandas as pd

from btc_quant.backtest import bar_price_path, run_backtest


def _synthetic(days=520, seed=3):
    rng = np.random.default_rng(seed)
    idx4 = pd.date_range("2024-01-01", periods=days * 6, freq="4h", tz="UTC")
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, len(idx4))))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.006, len(idx4)))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.006, len(idx4)))
    df4 = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": 1.0}, index=idx4)
    df1 = df4.resample("D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return df1, df4


def test_price_path_checks_adverse_extreme_first():
    assert bar_price_path(10, 12, 8, "Long") == [10, 8, 12]
    assert bar_price_path(10, 12, 8, "Short") == [10, 12, 8]
    assert bar_price_path(10, 12, 8, None) == [10, 12, 8]


def test_backtest_runs_and_keeps_invariants():
    df1, df4 = _synthetic()
    acc, events = run_backtest(df1, df4, start=df4.index[400 * 6])
    kinds = {e["kind"] for e in events}
    assert "rebalance" in kinds
    opens = [e for e in events if e["kind"] == "open"]
    closes = [e for e in events if e["kind"] == "close"]
    assert len(closes) in (len(opens), len(opens) - 1)
    assert all(e["leverage"] <= 25 for e in opens)
    assert acc.btc_qty * df4["close"].iloc[-1] <= 0.90 * acc.equity(df4["close"].iloc[-1]) * 1.2
    assert acc.equity(df4["close"].iloc[-1]) > 0


def test_backtest_rebalances_at_most_once_per_day():
    df1, df4 = _synthetic()
    _, events = run_backtest(df1, df4, start=df4.index[400 * 6])
    days = [e["ts"][:10] for e in events if e["kind"] == "rebalance"]
    assert len(days) == len(set(days))


def test_intrabar_stop_fills_at_stop_not_bar_low():
    df1, df4 = _synthetic()
    _, events = run_backtest(df1, df4, start=df4.index[400 * 6])
    stops = [e for e in events if e["kind"] == "close" and e["reason"] == "STOP"]
    assert stops
    # 只有開盤跳空才可能比 -1R 差很多；盤中觸發的停損應該接近 -1R（含手續費）
    assert sum(1 for e in stops if e["r_multiple"] < -1.3) <= len(stops) * 0.2
