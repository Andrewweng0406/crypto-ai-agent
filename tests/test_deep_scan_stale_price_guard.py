"""
市場掃描/deep_scan_symbol 的「即時價格防過期」防護——2026-07-14修復。

detect_new_signal() 用的是最近一根已收盤K棒的收盤價當進場價，但 deep_scan_symbol
真正要開倉時可能已經是好幾分鐘後。這裡驗證：突破已經被即時價格反轉時不應該開倉，
突破仍然成立時應該用即時價格（不是過期的收盤價）當進場價。
"""

import main
from main import deep_scan_symbol


async def _run_deep_scan(monkeypatch, ohlcv_factory, symbol, current_price):
    df = ohlcv_factory(direction="up", breakout=True, volume_spike=True)

    async def fake_fetch(exchange_pool, sym):
        return df

    monkeypatch.setattr(main, "fetch_ohlcv_for_symbol", fake_fetch)

    sym_state = main.state.get_symbol_state(symbol)
    sym_state.open_signal = None
    sym_state.current_price = current_price
    sym_state.smart_money = None

    await deep_scan_symbol({}, symbol)
    return main.state.get_symbol_state(symbol)


async def test_signal_skipped_when_live_price_already_reverted_into_channel(monkeypatch, ohlcv_factory):
    """收盤價突破了，但即時報價已經跌回唐奇安通道內——不該追一個已經過期的假突破。"""
    df = ohlcv_factory(direction="up", breakout=True, volume_spike=True)
    stale_close = float(df["close"].iloc[-1])
    donchian_upper = float(df["high"].iloc[-21:-1].max())  # detect_new_signal 用同一組資料算出的上軌附近

    sym_state = await _run_deep_scan(
        monkeypatch, ohlcv_factory, "BTC/USDT:USDT", current_price=donchian_upper - 1.0
    )
    assert sym_state.open_signal is None
    assert stale_close > donchian_upper  # 前提成立：收盤價確實高於上軌，才談得上「事後失效」


async def test_signal_uses_live_price_not_stale_close_when_breakout_still_valid(monkeypatch, ohlcv_factory):
    """即時報價仍然站在突破之上時，應該用即時報價當進場價，而不是過期的收盤價。"""
    df = ohlcv_factory(direction="up", breakout=True, volume_spike=True)
    stale_close = float(df["close"].iloc[-1])
    live_price = stale_close + 5.0  # 模擬「這幾分鐘價格又漲更多」

    sym_state = await _run_deep_scan(monkeypatch, ohlcv_factory, "BTC/USDT:USDT", current_price=live_price)
    assert sym_state.open_signal is not None
    assert sym_state.open_signal["entry_price"] == live_price
    assert sym_state.open_signal["entry_price"] != stale_close
