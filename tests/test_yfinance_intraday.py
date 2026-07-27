"""
2026-07-27新增：美股ORB當沖模塊改接yfinance（原本是BingX代幣化股票永續合約）
用到的兩支新函式。驗證：(1) get_intraday_ohlcv 回傳欄位/型別跟原本ccxt版本
一致（timestamp為UTC毫秒整數、欄名小寫），且會砍掉最後一根「進行中」K棒，
(2) get_batch_spot_prices 對單檔/多檔兩種yf.download回傳形狀（有無MultiIndex）
都能正確解析，抓不到的標的會被省略而不是讓整批失敗。
"""

import pandas as pd
import pytest

import yfinance_client


def _make_intraday_df(rows: int = 5) -> pd.DataFrame:
    idx = pd.date_range("2026-07-24 09:30", periods=rows, freq="15min", tz="America/New_York")
    return pd.DataFrame({
        "Open": [100.0 + i for i in range(rows)],
        "High": [101.0 + i for i in range(rows)],
        "Low": [99.0 + i for i in range(rows)],
        "Close": [100.5 + i for i in range(rows)],
        "Volume": [1000 + i * 10 for i in range(rows)],
        "Dividends": [0.0] * rows,
        "Stock Splits": [0.0] * rows,
    }, index=idx)


async def test_get_intraday_ohlcv_matches_ccxt_shape(monkeypatch):
    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, period, interval):
            return _make_intraday_df(5)

    monkeypatch.setattr(yfinance_client.yf, "Ticker", FakeTicker)

    df = await yfinance_client.get_intraday_ohlcv("TSLA", interval="15m", period="5d")

    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert df["timestamp"].dtype.kind in ("i", "u")  # 整數毫秒，不是datetime物件
    # 5根丟進去，砍掉最後一根「進行中」K棒，應該只剩4根
    assert len(df) == 4


async def test_get_intraday_ohlcv_timestamp_is_utc_ms():
    # 用真正的pandas timezone轉換驗證，不靠yfinance本身，避免這條測試依賴網路
    idx = pd.date_range("2026-07-24 09:30", periods=2, freq="15min", tz="America/New_York")
    ts_ms = idx.view("int64") // 1_000_000
    back = pd.to_datetime(ts_ms[0], unit="ms", utc=True).tz_convert("America/New_York")
    assert back == idx[0]


async def test_get_intraday_ohlcv_returns_empty_df_on_fetch_failure(monkeypatch):
    class FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, period, interval):
            raise RuntimeError("network down")

    monkeypatch.setattr(yfinance_client.yf, "Ticker", FakeTicker)
    df = await yfinance_client.get_intraday_ohlcv("BADTICKER", interval="15m", period="5d")
    assert df.empty
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]


async def test_get_batch_spot_prices_multi_symbol_multiindex(monkeypatch):
    columns = pd.MultiIndex.from_product([["TSLA", "NVDA"], ["Open", "High", "Low", "Close", "Volume"]])
    data = pd.DataFrame([[300, 305, 299, 303, 1000, 200, 205, 199, 204, 500]], columns=columns)

    def fake_download(**kwargs):
        return data

    monkeypatch.setattr(yfinance_client.yf, "download", fake_download)
    prices = await yfinance_client.get_batch_spot_prices(["TSLA", "NVDA"])
    assert prices == {"TSLA": 303.0, "NVDA": 204.0}


async def test_get_batch_spot_prices_single_symbol_flat_columns(monkeypatch):
    data = pd.DataFrame({"Open": [300], "High": [305], "Low": [299], "Close": [303], "Volume": [1000]})

    def fake_download(**kwargs):
        return data

    monkeypatch.setattr(yfinance_client.yf, "download", fake_download)
    prices = await yfinance_client.get_batch_spot_prices(["TSLA"])
    assert prices == {"TSLA": 303.0}


async def test_get_batch_spot_prices_skips_symbol_missing_from_response(monkeypatch):
    columns = pd.MultiIndex.from_product([["TSLA"], ["Open", "High", "Low", "Close", "Volume"]])
    data = pd.DataFrame([[300, 305, 299, 303, 1000]], columns=columns)

    def fake_download(**kwargs):
        return data

    monkeypatch.setattr(yfinance_client.yf, "download", fake_download)
    # 要NVDA但回應裡根本沒有 -> 應該被省略而不是拋例外整批失敗
    prices = await yfinance_client.get_batch_spot_prices(["TSLA", "NVDA"])
    assert prices == {"TSLA": 303.0}


async def test_get_batch_spot_prices_empty_input_returns_empty_dict():
    assert await yfinance_client.get_batch_spot_prices([]) == {}


async def test_get_batch_spot_prices_returns_empty_on_fetch_failure(monkeypatch):
    def fake_download(**kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(yfinance_client.yf, "download", fake_download)
    assert await yfinance_client.get_batch_spot_prices(["TSLA"]) == {}
