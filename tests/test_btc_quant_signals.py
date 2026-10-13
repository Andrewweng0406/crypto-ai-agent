import math

import numpy as np
import pandas as pd
import pytest

from btc_quant import signals as s


def _daily(closes, start="2024-01-01"):
    idx = pd.date_range(start, periods=len(closes), freq="D", tz="UTC")
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({"open": c, "high": c * 1.001, "low": c * 0.999, "close": c, "volume": 1.0})


def test_closed_candles_df_drops_forming_bar():
    now = 3 * s.FOUR_H_MS + 1000  # 第4根(ts=3*4h)剛開始
    rows = [[i * s.FOUR_H_MS, 1, 2, 0.5, 1.5, 10] for i in range(4)]
    df = s.closed_candles_df(rows, s.FOUR_H_MS, now)
    assert len(df) == 3
    assert str(df.index.tz) == "UTC"
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_ensemble_is_one_in_steady_uptrend_and_zero_in_downtrend():
    up = _daily(np.linspace(100, 300, 400))
    down = _daily(np.linspace(300, 100, 400))
    assert s.daily_ensemble(up).iloc[-1] == 1.0
    assert s.daily_ensemble(down).iloc[-1] == 0.0


def test_ensemble_matches_research_twelve_signal_weights():
    # 研究版本的12個訊號 = 5唐奇安 + 3動能 + 動能組合(3動能平均) + 3均線，所以值是1/36的倍數
    rng = np.random.default_rng(1)
    df = _daily(100 * np.exp(np.cumsum(rng.normal(0, 0.03, 500))))
    ens = s.daily_ensemble(df)
    assert ((ens * 36).round(9) % 1 == 0).all()
    assert not ((ens * 11).round(9) % 1 == 0).all()
    assert ens.between(0, 1).all()


def test_trend_target_capped_at_090():
    df = _daily(np.linspace(100, 101, 400))  # 極低波動 -> 0.4/vol 很大
    assert s.trend_target_series(df).iloc[-1] == pytest.approx(s.TREND_MAX_EXPOSURE)


def test_target_as_of_uses_window_and_missing_day_is_nan():
    df = _daily(np.linspace(100, 300, 600))
    day = df.index[500]
    expected = s.trend_target_series(df.loc[:day].tail(s.DAILY_LOOKBACK)).iloc[-1]
    assert s.target_as_of(df, day) == pytest.approx(expected)
    assert math.isnan(s.target_as_of(df, df.index[-1] + pd.Timedelta(days=5)))


def test_signal_day_for_bar_is_previous_day():
    bar = pd.Timestamp("2026-10-13 00:00", tz="UTC")
    assert s.signal_day_for_bar(bar) == pd.Timestamp("2026-10-12", tz="UTC")
    bar2 = pd.Timestamp("2026-10-13 20:00", tz="UTC")
    assert s.signal_day_for_bar(bar2) == pd.Timestamp("2026-10-12", tz="UTC")


def test_tactical_signal_rules():
    assert s.tactical_signal(105, 104, 90, 0.5) == "Long"
    assert s.tactical_signal(105, 104, 90, 5 / 12) is None
    assert s.tactical_signal(89, 104, 90, 0.0) == "Short"
    assert s.tactical_signal(89, 104, 90, 1 / 12) is None
    assert s.tactical_signal(100, float("nan"), 90, 1.0) is None


def test_size_position_long():
    o = s.size_position("Long", entry=100.0, atr=1.0, equity=10_000.0)
    assert o.stop_pct == pytest.approx(0.015)
    assert math.floor(1 / (2 * 0.015 + 0.005)) == 28
    assert o.leverage == 25  # 被上限夾住
    assert o.notional == pytest.approx(10_000 * 0.02 / 0.015)
    assert o.margin == pytest.approx(o.notional / 25)
    assert o.stop_loss == pytest.approx(98.5)
    assert o.take_profit == pytest.approx(103.0)
    assert (o.entry - o.liquidation) / o.entry >= 2 * o.stop_pct


def test_size_position_short_and_liquidation_distance():
    o = s.size_position("Short", entry=100.0, atr=3.0, equity=10_000.0)
    assert o.stop_loss == pytest.approx(104.5)
    assert o.take_profit == pytest.approx(91.0)
    assert o.leverage == math.floor(1 / (2 * 0.045 + 0.005))
    assert (o.liquidation - o.entry) / o.entry >= 2 * o.stop_pct


def test_size_position_rejects_bad_input():
    assert s.size_position("Long", 100.0, 0.0, 10_000) is None
    assert s.size_position("Long", 100.0, 40.0, 10_000) is None  # stop 60% -> lev<1
    assert s.size_position("Sideways", 100.0, 1.0, 10_000) is None


def test_prepare_4h_columns():
    idx = pd.date_range("2026-01-01", periods=30, freq="4h", tz="UTC")
    c = pd.Series(np.arange(30, dtype=float) + 100, index=idx)
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 1.0})
    p = s.prepare_4h(df)
    assert p["atr"].iloc[-1] == pytest.approx(2.0)
    assert p["up"].iloc[-1] == pytest.approx(c.iloc[-21:-1].max() + 1)


def test_months_since_halving():
    assert s.months_since_halving(pd.Timestamp("2024-04-19", tz="UTC")) == pytest.approx(0.0)
    assert s.months_since_halving(pd.Timestamp("2026-10-13", tz="UTC")) == pytest.approx(29.8, abs=0.2)
    assert s.months_since_halving(pd.Timestamp("2018-01-07", tz="UTC")) == pytest.approx(18.0, abs=0.1)
    assert math.isnan(s.months_since_halving(pd.Timestamp("2011-01-01", tz="UTC")))


def test_cycle_phase_labels():
    assert s.cycle_phase(5.0) == "牛市段"
    assert s.cycle_phase(18.0) == "熊市窗口"
    assert s.cycle_phase(29.9) == "熊市窗口"
    assert s.cycle_phase(30.0) == "復甦段"
    assert s.cycle_phase(float("nan")) == "未知"


def test_trend_target_capped_in_bear_window():
    # 2018-01-07 起是 2016 輪減半後第18個月 -> 熊市窗口，持倉上限 0.30
    bear = _daily(np.linspace(100, 101, 400), start="2017-01-07")
    bull = _daily(np.linspace(100, 101, 400), start="2016-12-01")  # 結束於 2018-01-05，第17.9個月
    assert bear.index[-1] == pd.Timestamp("2018-02-10", tz="UTC")
    assert s.trend_target_series(bear).iloc[-1] == pytest.approx(s.CYCLE_BEAR_MAX_EXPOSURE)
    assert s.trend_target_series(bull).iloc[-1] == pytest.approx(s.TREND_MAX_EXPOSURE)


def test_long_risk_halved_in_bear_window():
    normal = s.size_position("Long", 100.0, 1.0, 10_000, months=10.0)
    bear_long = s.size_position("Long", 100.0, 1.0, 10_000, months=20.0)
    bear_short = s.size_position("Short", 100.0, 1.0, 10_000, months=20.0)
    assert bear_long.notional == pytest.approx(normal.notional * s.CYCLE_BEAR_LONG_RISK_MULT)
    assert bear_long.margin == pytest.approx(normal.margin * s.CYCLE_BEAR_LONG_RISK_MULT)
    assert bear_short.notional == pytest.approx(normal.notional)
    assert s.size_position("Long", 100.0, 1.0, 10_000).notional == pytest.approx(normal.notional)  # 未給月份=不調整
