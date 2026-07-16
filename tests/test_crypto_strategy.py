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


def test_no_signal_when_atr_implies_absurd_stop_loss(ohlcv_factory):
    # 真實發生過的案例：LAB/USDT:USDT 暴漲暴跌把 ATR 撐到接近進場價本身，導致
    # ATR模型算出的止損距離超過100%、止盈甚至被減成負數（不可能觸及的價格）。
    # high_low_range 調大來模擬這種「相對價格而言波動異常劇烈」的K棒。
    df = add_indicators(
        ohlcv_factory(direction="up", breakout=True, volume_spike=True, high_low_range=80.0)
    )
    assert detect_new_signal(df) is None


def test_no_signal_when_volatility_too_low_for_leverage_model(ohlcv_factory):
    # 2026-07-15真實發生過的案例：XAUT/USDT:USDT（黃金錨定代幣，非真正加密貨幣）
    # 波動率長期只有0.1%-3%，ATR算出的停損距離窄到讓固定風險槓桿模型直接拉滿20倍
    # 槓桿去賭雜訊等級的波動，單筆虧損13%。high_low_range 調小模擬這種「這隻標的
    # 天生就不太會動」的K棒。
    df = add_indicators(
        ohlcv_factory(direction="up", breakout=True, volume_spike=True, high_low_range=0.05)
    )
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
