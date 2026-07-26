"""
2026-07-26新增：GET /api/options/strategy 端點層測試（跟 tests/test_options_
strategy_engine.py 的純計算層測試分開——這裡驗證的是main.py怎麼把yfinance
資料接進策略引擎、以及路由/邊界條件，不重複算credit/margin這些純數學）。
"""

from fastapi.testclient import TestClient

import main
from main import app
from yfinance_client import OptionLegRaw

client = TestClient(app)

SYMBOL = "NVDA"
SPOT = 100.0
STRIKES = [75, 80, 85, 90, 95, 100, 105, 110, 115, 120, 125]


def _fake_legs(put_quotes=None, call_quotes=None):
    put_quotes = put_quotes or {}
    call_quotes = call_quotes or {}
    legs = []
    for strike in STRIKES:
        pb, pa, piv = put_quotes.get(strike, (0.0, 0.0, 0.0))
        cb, ca, civ = call_quotes.get(strike, (0.0, 0.0, 0.0))
        legs.append(OptionLegRaw(
            strike=float(strike), call_oi=100.0, call_iv=civ, put_oi=100.0, put_iv=piv,
            call_bid=cb, call_ask=ca, put_bid=pb, put_ask=pa,
        ))
    return legs


def _patch_common(monkeypatch, *, spot=SPOT, expiry="2026-08-30", legs=None):
    main.state.options_watchlist = {SYMBOL: SYMBOL}

    async def fake_spot(_symbol):
        return spot

    async def fake_expiry(_symbol, **_kwargs):
        return expiry

    async def fake_legs(_symbol, _expiry):
        return legs if legs is not None else []

    monkeypatch.setattr(main.yfinance_client, "get_spot_price", fake_spot)
    monkeypatch.setattr(main.yfinance_client, "get_expiry_by_dte", fake_expiry)
    monkeypatch.setattr(main.yfinance_client, "get_option_chain_legs", fake_legs)


def test_rejects_symbol_not_in_watchlist(monkeypatch):
    _patch_common(monkeypatch)
    resp = client.get("/api/options/strategy", params={"symbol": "AAPL", "sentiment": "bullish"})
    assert resp.status_code == 400


def test_bullish_returns_put_credit_spread(monkeypatch):
    legs = _fake_legs(put_quotes={90: (2.0, 2.2, 0.4), 85: (1.0, 1.2, 0.4)})
    _patch_common(monkeypatch, legs=legs)

    resp = client.get("/api/options/strategy", params={"symbol": SYMBOL, "sentiment": "bullish"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["strategy"] is not None
    assert body["strategy"]["type"] == "put_credit"
    assert body["strategy"]["legs"][0]["action"] == "SELL"
    assert body["strategy"]["legs"][0]["option_type"] == "PUT"
    assert body["strategy"]["financials"]["max_profit"] == 80.0
    assert body["current_price"] == SPOT
    assert "Delta" in body["win_rate_disclaimer"]


def test_bearish_returns_call_credit_spread(monkeypatch):
    legs = _fake_legs(call_quotes={110: (1.5, 1.7, 0.35), 115: (0.6, 0.8, 0.35)})
    _patch_common(monkeypatch, legs=legs)

    resp = client.get("/api/options/strategy", params={"symbol": SYMBOL, "sentiment": "bearish"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["strategy"]["type"] == "call_credit"
    assert body["strategy"]["legs"][0]["option_type"] == "CALL"


def test_neutral_returns_iron_condor(monkeypatch):
    legs = _fake_legs(
        put_quotes={90: (2.0, 2.2, 0.4), 85: (1.0, 1.2, 0.4)},
        call_quotes={110: (1.5, 1.7, 0.35), 115: (0.6, 0.8, 0.35)},
    )
    _patch_common(monkeypatch, legs=legs)

    resp = client.get("/api/options/strategy", params={"symbol": SYMBOL, "sentiment": "neutral"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["strategy"]["type"] == "iron_condor"
    assert len(body["strategy"]["legs"]) == 4


def test_uses_sentiment_label_for_display_when_provided(monkeypatch):
    legs = _fake_legs(put_quotes={90: (2.0, 2.2, 0.4), 85: (1.0, 1.2, 0.4)})
    _patch_common(monkeypatch, legs=legs)

    resp = client.get(
        "/api/options/strategy",
        params={"symbol": SYMBOL, "sentiment": "bullish", "sentiment_label": "強烈看多"},
    )
    assert resp.json()["market_sentiment"] == "強烈看多"


def test_falls_back_to_default_label_when_not_provided(monkeypatch):
    legs = _fake_legs(put_quotes={90: (2.0, 2.2, 0.4), 85: (1.0, 1.2, 0.4)})
    _patch_common(monkeypatch, legs=legs)

    resp = client.get("/api/options/strategy", params={"symbol": SYMBOL, "sentiment": "bullish"})
    assert resp.json()["market_sentiment"] == "看漲"


def test_returns_message_when_no_valid_strikes_found(monkeypatch):
    # 沒有任何履約價落在安全墊範圍內
    legs = [OptionLegRaw(strike=float(s), call_oi=0, call_iv=0, put_oi=0, put_iv=0) for s in [50, 150]]
    _patch_common(monkeypatch, legs=legs)

    resp = client.get("/api/options/strategy", params={"symbol": SYMBOL, "sentiment": "bullish"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["strategy"] is None
    assert body["message"] is not None


def test_returns_message_when_spot_price_unavailable(monkeypatch):
    _patch_common(monkeypatch, spot=None, legs=[])
    resp = client.get("/api/options/strategy", params={"symbol": SYMBOL, "sentiment": "bullish"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["strategy"] is None
    assert body["current_price"] == 0.0
