"""
2026-07-15修復：RSI(2)均值回歸實盤監控的止盈判斷曾經拿「今天還在跳動的估算收盤價」
跟「同一根還沒收盤K棒算出來的SMA5」比較，兩者在盤中會自然地上下交錯震盪，導致同一天
內反覆觸發「止盈→(進場條件不變)立即重開倉→再次止盈」，實際觀察到GOOGL一天內灌出
30筆連續WIN、entry/stop_loss完全相同的假交易。這裡驗證：(1)止盈只能在收盤確認後才會
觸發，盤中即使股價瞬間站上SMA5也不該結算；(2)同一天內已經開過倉的標的，不會再被
重複開倉（不管今天稍早是用SL還是TP結算的）。
"""

import pandas as pd
import pytest

import main


SYMBOL = "GOOGL"


def _make_raw(n=210):
    return pd.DataFrame({
        "timestamp": range(n),
        "open": [100.0] * n,
        "high": [101.0] * n,
        "low": [99.0] * n,
        "close": [100.0] * n,
        "volume": [1000.0] * n,
    })


def _make_signals_with_open_position():
    """today收盤(估算值)剛好站上sma5，模擬「盤中瞬間站上SMA5」這個會誤觸發止盈的情境。"""
    return pd.DataFrame({
        "timestamp": [0, 1],
        "open": [100.0, 105.0],
        "high": [101.0, 108.0],
        "low": [99.0, 104.0],
        "close": [100.0, 106.0],
        "sma200": [95.0, 95.0],
        "sma5": [104.0, 105.5],  # today(index=1)的close(106.0) > sma5(105.5)
        "rsi2": [5.0, 5.0],
        "entry_signal": [False, False],
        "sl_price": [90.0, 90.0],
    })


def _make_signals_with_fresh_entry_signal():
    return pd.DataFrame({
        "timestamp": [0, 1],
        "open": [100.0, 105.0],
        "high": [101.0, 108.0],
        "low": [99.0, 104.0],
        "close": [100.0, 106.0],
        "sma200": [95.0, 95.0],
        "sma5": [104.0, 105.5],
        "rsi2": [5.0, 5.0],
        "entry_signal": [True, False],  # yesterday(index=0)訊號成立
        "sl_price": [90.0, 90.0],
    })


@pytest.fixture(autouse=True)
def _reset_rsi2_state():
    main.state.rsi2_states.pop(SYMBOL, None)
    yield
    main.state.rsi2_states.pop(SYMBOL, None)


async def test_tp_does_not_fire_intraday_before_close_confirmed(monkeypatch):
    monkeypatch.setattr(main, "_backtest_fetch_yf_daily", lambda *a, **k: _make_raw())
    monkeypatch.setattr(main, "_backtest_signals_rsi2_mean_reversion", lambda raw: _make_signals_with_open_position())
    monkeypatch.setattr(main, "_is_us_market_active", lambda now_et: True)  # 盤中，尚未收盤確認

    st = main.state.get_rsi2_state(SYMBOL)
    st.open_signal = {"entry_price": 100.0, "stop_loss": 90.0, "opened_at": "2026-07-15T14:00:00+00:00"}

    await main.scan_rsi2_stock(SYMBOL)

    assert st.open_signal is not None, "盤中即使即時價格瞬間站上SMA5，也不該結算止盈"


async def test_tp_fires_once_close_is_confirmed(monkeypatch):
    monkeypatch.setattr(main, "_backtest_fetch_yf_daily", lambda *a, **k: _make_raw())
    monkeypatch.setattr(main, "_backtest_signals_rsi2_mean_reversion", lambda raw: _make_signals_with_open_position())
    monkeypatch.setattr(main, "_is_us_market_active", lambda now_et: False)  # 收盤後，confirmed

    st = main.state.get_rsi2_state(SYMBOL)
    st.open_signal = {"entry_price": 100.0, "stop_loss": 90.0, "opened_at": "2026-07-15T14:00:00+00:00"}

    await main.scan_rsi2_stock(SYMBOL)

    assert st.open_signal is None, "收盤確認後站上SMA5，應該正常結算止盈"


async def test_no_same_day_reentry_after_already_traded(monkeypatch):
    monkeypatch.setattr(main, "_backtest_fetch_yf_daily", lambda *a, **k: _make_raw())
    monkeypatch.setattr(main, "_backtest_signals_rsi2_mean_reversion", lambda raw: _make_signals_with_fresh_entry_signal())
    monkeypatch.setattr(main, "_is_us_market_active", lambda now_et: True)

    st = main.state.get_rsi2_state(SYMBOL)
    st.open_signal = None
    today_et = __import__("datetime").datetime.now(__import__("zoneinfo").ZoneInfo(main.US_MARKET_TZ)).date()
    st.triggered_date = today_et.isoformat()  # 模擬今天稍早已經開平倉過一次

    await main.scan_rsi2_stock(SYMBOL)

    assert st.open_signal is None, "同一天內已經交易過，不該再被重新開倉"


async def test_opens_and_records_triggered_date_when_fresh(monkeypatch):
    monkeypatch.setattr(main, "_backtest_fetch_yf_daily", lambda *a, **k: _make_raw())
    monkeypatch.setattr(main, "_backtest_signals_rsi2_mean_reversion", lambda raw: _make_signals_with_fresh_entry_signal())
    monkeypatch.setattr(main, "_is_us_market_active", lambda now_et: True)

    st = main.state.get_rsi2_state(SYMBOL)
    st.open_signal = None
    st.triggered_date = None

    await main.scan_rsi2_stock(SYMBOL)

    assert st.open_signal is not None
    assert st.open_signal["entry_price"] == 105.0  # today's open
    assert st.triggered_date is not None


def _record(symbol, entry_price, stop_loss, closed_at):
    return {
        "symbol": symbol, "display_name": symbol, "side": "Long",
        "entry_price": entry_price, "exit_price": entry_price * 1.03, "stop_loss": stop_loss,
        "result": "WIN", "pnl_pct": 3.0, "opened_at": closed_at, "closed_at": closed_at,
        "exit_reason": "TP",
    }


def test_purge_drops_entire_group_sharing_entry_and_stop():
    history = [
        _record("GOOGL", 358.15, 331.36, "2026-07-15T15:27:07+00:00"),
        _record("GOOGL", 358.15, 331.36, "2026-07-15T15:26:06+00:00"),
        _record("GOOGL", 358.15, 331.36, "2026-07-15T15:25:05+00:00"),
        _record("NVDA", 200.0, 190.0, "2026-07-15T15:10:00+00:00"),  # 唯一一筆，真實交易，應保留
    ]
    cleaned = main._purge_duplicate_rsi2_history(history)
    assert [r["symbol"] for r in cleaned] == ["NVDA"]


def test_purge_is_noop_on_already_clean_history():
    history = [
        _record("NVDA", 200.0, 190.0, "2026-07-15T15:10:00+00:00"),
        _record("META", 500.0, 480.0, "2026-07-14T15:10:00+00:00"),
    ]
    cleaned = main._purge_duplicate_rsi2_history(history)
    assert len(cleaned) == 2
