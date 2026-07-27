"""
2026-07-27新增：GET /api/us-stock/candles——美股ORB遷移到yfinance後，
SignalChart 原本靠 /api/candles(ccxt) 查美股K線的路徑失效了（ccxt交易所不
認得"TSLA"這種純美股代號），這支端點是修復+「個股總覽」頁K線疊圖共用的
資料源。
"""

import pandas as pd
from fastapi.testclient import TestClient

import main
from main import app

client = TestClient(app)


def _fake_df(rows: int = 65) -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": [1700000000000 + i * 86400000 for i in range(rows)],
        "open": [100.0 + i for i in range(rows)],
        "high": [101.0 + i for i in range(rows)],
        "low": [99.0 + i for i in range(rows)],
        "close": [100.5 + i for i in range(rows)],
        "volume": [1000 + i for i in range(rows)],
    })


def test_returns_candles_for_valid_symbol(monkeypatch):
    async def fake_intraday(symbol, interval, period):
        assert symbol == "TSLA"
        assert interval == "1d"
        return _fake_df()

    monkeypatch.setattr(main.yfinance_client, "get_intraday_ohlcv", fake_intraday)
    resp = client.get("/api/us-stock/candles", params={"symbol": "TSLA"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "TSLA"
    assert body["timeframe"] == "1d"
    assert len(body["candles"]) == 60  # 預設limit=60，65筆丟進去應該只拿最後60筆


def test_limit_is_clamped_between_10_and_300(monkeypatch):
    async def fake_intraday(symbol, interval, period):
        return _fake_df(rows=65)

    monkeypatch.setattr(main.yfinance_client, "get_intraday_ohlcv", fake_intraday)
    resp = client.get("/api/us-stock/candles", params={"symbol": "TSLA", "limit": 5})
    assert len(resp.json()["candles"]) == 10  # 5被夾到最低10


def test_rejects_unsupported_timeframe():
    resp = client.get("/api/us-stock/candles", params={"symbol": "TSLA", "timeframe": "3d"})
    assert resp.status_code == 400


def test_returns_502_when_symbol_has_no_data(monkeypatch):
    async def fake_intraday(symbol, interval, period):
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    monkeypatch.setattr(main.yfinance_client, "get_intraday_ohlcv", fake_intraday)
    resp = client.get("/api/us-stock/candles", params={"symbol": "BADTICKER"})
    assert resp.status_code == 502


def test_symbol_uppercased_and_stripped(monkeypatch):
    captured = {}

    async def fake_intraday(symbol, interval, period):
        captured["symbol"] = symbol
        return _fake_df()

    monkeypatch.setattr(main.yfinance_client, "get_intraday_ohlcv", fake_intraday)
    client.get("/api/us-stock/candles", params={"symbol": " tsla "})
    assert captured["symbol"] == "TSLA"


def test_15m_timeframe_uses_5d_period(monkeypatch):
    captured = {}

    async def fake_intraday(symbol, interval, period):
        captured["period"] = period
        return _fake_df()

    monkeypatch.setattr(main.yfinance_client, "get_intraday_ohlcv", fake_intraday)
    client.get("/api/us-stock/candles", params={"symbol": "TSLA", "timeframe": "15m"})
    assert captured["period"] == "5d"
