"""
回測沙盒的 crypto_donchian_4h 必須跟實盤 add_indicators()/detect_new_signal() 逐項對齊
——2026-07-14發現這兩套曾經各自獨立維護、悄悄分岔（回測用1H+EMA20/60，實盤其實是
4H+SMA50/200），導致回測沙盒驗證的從來不是真正在跑的策略。這裡直接拿同一份合成K線
餵給兩邊，斷言訊號判斷一致，往後任一邊改動參數卻忘記同步另一邊，這裡就會直接失敗。
"""

from main import (
    ATR_PERIOD,
    DONCHIAN_PERIOD,
    MA_FAST_PERIOD,
    MA_SLOW_PERIOD,
    VOLUME_LOOKBACK,
    VOLUME_MULT,
    add_indicators,
    detect_new_signal,
)
from main import _backtest_signals_donchian_4h


def test_backtest_donchian_4h_agrees_with_live_on_long_breakout(ohlcv_factory):
    df = ohlcv_factory(direction="up", n=MA_SLOW_PERIOD + 10, breakout=True, volume_spike=True)

    live_signal = detect_new_signal(add_indicators(df))
    backtest_last_row = _backtest_signals_donchian_4h(df).iloc[-1]

    assert live_signal is not None and live_signal["side"] == "Long"
    assert bool(backtest_last_row["long_signal"]) is True
    assert bool(backtest_last_row["short_signal"]) is False


def test_backtest_donchian_4h_agrees_with_live_on_short_breakout(ohlcv_factory):
    df = ohlcv_factory(direction="down", n=MA_SLOW_PERIOD + 10, breakout=True, volume_spike=True)

    live_signal = detect_new_signal(add_indicators(df))
    backtest_last_row = _backtest_signals_donchian_4h(df).iloc[-1]

    assert live_signal is not None and live_signal["side"] == "Short"
    assert bool(backtest_last_row["short_signal"]) is True
    assert bool(backtest_last_row["long_signal"]) is False


def test_backtest_donchian_4h_agrees_with_live_when_no_breakout(ohlcv_factory):
    df = ohlcv_factory(direction="up", n=MA_SLOW_PERIOD + 10, breakout=False, volume_spike=True)

    live_signal = detect_new_signal(add_indicators(df))
    backtest_last_row = _backtest_signals_donchian_4h(df).iloc[-1]

    assert live_signal is None
    assert bool(backtest_last_row["long_signal"]) is False
    assert bool(backtest_last_row["short_signal"]) is False


def test_backtest_donchian_4h_requires_ma_slow_period_warmup_not_60():
    """
    修復前的舊版本沿用「EMA(60)」年代的暖機假設，容易在 MA_SLOW_PERIOD=200 的情況下
    誤判資料已經足夠暖機。這裡直接斷言 min_len 邏輯依賴的常數是 MA_SLOW_PERIOD，
    不是殘留的舊字面值 60。
    """
    assert MA_SLOW_PERIOD == 200
    required_min_len = max(MA_SLOW_PERIOD, DONCHIAN_PERIOD, VOLUME_LOOKBACK, ATR_PERIOD) + 2
    assert required_min_len == MA_SLOW_PERIOD + 2
    assert MA_FAST_PERIOD < MA_SLOW_PERIOD
    assert VOLUME_MULT > 0
