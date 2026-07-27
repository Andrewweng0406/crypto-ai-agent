"""
2026-07-27新增：美股ORB當沖的資料源從BingX代幣化股票永續合約（ccxt）改接
yfinance。驗證：(1) scan_us_stock_orb 正確吃 yfinance_client.get_intraday_
ohlcv 回傳的資料、算出開盤區間與RVOL、在大盤濾網+量能雙重確認下開出訊號，
(2) refresh_us_market_regime 改吃 QQQ 的yfinance資料算出多空濾網，
(3) 舊快照裡的BingX格式watchlist會在載入時自動遷移成yfinance格式。

不重複測試 build_us_stock_open_signal 的停損/停利公式本身
（tests/test_us_stock_orb.py 已經覆蓋），這裡只測「資料源換了之後整條管線
還接得起來」。
"""

from zoneinfo import ZoneInfo

import pandas as pd
import pytest

import main

SYMBOL = "TSLA"
TZ = ZoneInfo(main.US_MARKET_TZ)


def _make_15m_bars(days: int, bars_per_day: int = 26) -> pd.DataFrame:
    """
    產生 days 個交易日 x bars_per_day 根15分鐘K棒（09:30起，一天6.5小時共26根），
    最後一天固定是「今天」（scan_us_stock_orb 用 datetime.now(tz) 判斷哪些資料
    算今天，測試資料必須真的以今天收尾，不能寫死過去某個日期），每天同一時段
    的量都是基準量100，方便測試用「今天量能暴增」蓋過去驗證RVOL。
    """
    today = main.datetime.now(TZ).date()
    trading_days = []
    d = today
    while len(trading_days) < days:
        if d.weekday() < 5:
            trading_days.append(d)
        d -= pd.Timedelta(days=1)
    trading_days.reverse()

    rows = []
    for day in trading_days:
        day_start = pd.Timestamp(f"{day} 09:30", tz="America/New_York")
        for b in range(bars_per_day):
            ts = day_start + pd.Timedelta(minutes=15 * b)
            rows.append({"ts": ts, "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 100})
    df = pd.DataFrame(rows)
    df["timestamp"] = df["ts"].astype("int64") // 1_000_000
    return df[["timestamp", "open", "high", "low", "close", "volume"]]


@pytest.fixture(autouse=True)
def _reset_state():
    main.state.us_stock_states = {}
    main.state.us_market_regime = "Neutral"
    yield


async def test_scan_detects_long_breakout_with_volume_and_bullish_regime(monkeypatch):
    df = _make_15m_bars(days=7)
    # 鎖定今天(最後一天)的開盤區間K棒(09:30)為 high=105/low=95
    today_mask = df["timestamp"] >= df["timestamp"].iloc[-26]
    today_idx = df[today_mask].index
    df.loc[today_idx[0], ["high", "low", "close"]] = [105.0, 95.0, 102.0]
    # 今天第三根(10:00，嚴格晚於09:45)突破區間高點105，且量能是基準的5倍(觸發RVOL_MULT=3.5)。
    # scan_us_stock_orb 只看「今天目前最後一根」判斷突破，所以把今天的資料截到
    # 這一根為止，模擬「現在剛好掃到這個時間點」，不留下之後又跌回基準量的假象。
    df.loc[today_idx[2], ["close", "volume"]] = [110.0, 500]
    df = df.drop(index=today_idx[3:])

    async def fake_intraday(ticker_symbol, interval, period):
        return df

    monkeypatch.setattr(main.yfinance_client, "get_intraday_ohlcv", fake_intraday)
    main.state.us_market_regime = "Bullish"

    await main.scan_us_stock_orb(SYMBOL, SYMBOL)

    st = main.state.get_us_stock_state(SYMBOL)
    assert st.open_signal is not None
    assert st.open_signal["side"] == "Long"
    assert st.opening_high == 105.0
    assert st.opening_low == 95.0
    assert st.rvol is not None and st.rvol >= 3.5


async def test_scan_does_not_open_when_regime_disagrees(monkeypatch):
    df = _make_15m_bars(days=7)
    today_mask = df["timestamp"] >= df["timestamp"].iloc[-26]
    today_idx = df[today_mask].index
    df.loc[today_idx[0], ["high", "low", "close"]] = [105.0, 95.0, 102.0]
    df.loc[today_idx[2], ["close", "volume"]] = [110.0, 500]  # 一樣是有效的多頭突破+爆量
    df = df.drop(index=today_idx[3:])

    async def fake_intraday(ticker_symbol, interval, period):
        return df

    monkeypatch.setattr(main.yfinance_client, "get_intraday_ohlcv", fake_intraday)
    main.state.us_market_regime = "Bearish"  # 大盤濾網跟突破方向矛盾

    await main.scan_us_stock_orb(SYMBOL, SYMBOL)

    st = main.state.get_us_stock_state(SYMBOL)
    assert st.open_signal is None


async def test_scan_returns_early_when_fetch_fails(monkeypatch):
    async def fake_intraday(ticker_symbol, interval, period):
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    monkeypatch.setattr(main.yfinance_client, "get_intraday_ohlcv", fake_intraday)

    await main.scan_us_stock_orb(SYMBOL, SYMBOL)  # 不該拋例外
    st = main.state.get_us_stock_state(SYMBOL)
    assert st.open_signal is None


async def test_refresh_regime_uses_qqq_and_sets_bullish_on_ma_crossover(monkeypatch):
    rows = []
    ts0 = pd.Timestamp("2026-07-20 09:30", tz="America/New_York")
    closes = [100.0] * 20 + [101.0, 102.0, 108.0]  # 尾段急拉，快線上穿慢線+突破前高
    for i, c in enumerate(closes):
        ts = ts0 + pd.Timedelta(minutes=15 * i)
        rows.append({
            "timestamp": ts.value // 1_000_000, "open": c, "high": c + 0.5, "low": c - 0.5,
            "close": c, "volume": 100,
        })
    df = pd.DataFrame(rows)

    captured = {}

    async def fake_intraday(ticker_symbol, interval, period):
        captured["symbol"] = ticker_symbol
        return df

    monkeypatch.setattr(main.yfinance_client, "get_intraday_ohlcv", fake_intraday)

    await main.refresh_us_market_regime()

    assert captured["symbol"] == "QQQ"
    assert main.state.us_market_regime == "Bullish"


def test_snapshot_load_migrates_old_bingx_format_watchlist(tmp_path, monkeypatch):
    old_snapshot = {
        "us_stock_watchlist": {
            "TSLA": "NCSKTSLA2USD/USDT:USDT",  # 舊格式
            "NVDA": "NVDA",  # 假設已經是新格式的也要保持不變
        },
    }
    snapshot_path = tmp_path / "state_snapshot.json"
    import json
    snapshot_path.write_text(json.dumps(old_snapshot), encoding="utf-8")
    monkeypatch.setattr(main, "STATE_SNAPSHOT_PATH", str(snapshot_path))

    main.load_state_snapshot()

    assert main.state.us_stock_watchlist["TSLA"] == "TSLA"
    assert main.state.us_stock_watchlist["NVDA"] == "NVDA"
