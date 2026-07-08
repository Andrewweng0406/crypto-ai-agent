"""主流幣/市場掃描策略核心邏輯：唐奇安通道突破 + 成交量確認 + 雙均線趨勢過濾。"""

from main import add_indicators, build_open_signal, detect_new_signal


def test_long_signal_on_uptrend_breakout_with_volume(ohlcv_factory):
    df = add_indicators(ohlcv_factory(direction="up", breakout=True, volume_spike=True))
    signal = detect_new_signal(df)
    assert signal is not None
    assert signal["side"] == "Long"


def test_short_signal_on_downtrend_breakout_with_volume(ohlcv_factory):
    df = add_indicators(ohlcv_factory(direction="down", breakout=True, volume_spike=True))
    signal = detect_new_signal(df)
    assert signal is not None
    assert signal["side"] == "Short"


def test_no_signal_without_breakout(ohlcv_factory):
    df = add_indicators(ohlcv_factory(direction="up", breakout=False, volume_spike=True))
    assert detect_new_signal(df) is None


def test_no_signal_without_volume_confirmation(ohlcv_factory):
    df = add_indicators(ohlcv_factory(direction="up", breakout=True, volume_spike=False))
    assert detect_new_signal(df) is None


def test_no_signal_with_insufficient_history(ohlcv_factory):
    # MA_SLOW_PERIOD=200，資料不足時指標會是 NaN，必須回傳 None 而不是誤判
    df = add_indicators(ohlcv_factory(direction="up", n=100, breakout=True, volume_spike=True))
    assert detect_new_signal(df) is None


def test_build_open_signal_long_tp_above_sl_below_entry():
    signal = {"side": "Long", "entry_price": 100.0, "atr": 2.0}
    opened = build_open_signal("BTC/USDT:USDT", signal)
    assert opened["stop_loss"] < opened["entry_price"] < opened["take_profit"]
    assert opened["leverage"] >= 1


def test_build_open_signal_short_tp_below_sl_above_entry():
    signal = {"side": "Short", "entry_price": 100.0, "atr": 2.0}
    opened = build_open_signal("BTC/USDT:USDT", signal)
    assert opened["take_profit"] < opened["entry_price"] < opened["stop_loss"]


def test_build_open_signal_risk_reward_ratio_applied():
    from main import ATR_SL_MULTIPLIER, RISK_REWARD_RATIO

    signal = {"side": "Long", "entry_price": 100.0, "atr": 2.0}
    opened = build_open_signal("BTC/USDT:USDT", signal)
    sl_distance = opened["entry_price"] - opened["stop_loss"]
    tp_distance = opened["take_profit"] - opened["entry_price"]
    assert sl_distance == 2.0 * ATR_SL_MULTIPLIER
    assert tp_distance == sl_distance * RISK_REWARD_RATIO
