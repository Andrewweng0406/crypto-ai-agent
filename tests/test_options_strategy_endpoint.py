"""
2026-07-26新增、2026-07-27改版：GET /api/options/strategy 端點層測試（跟
tests/test_options_strategy_engine.py 的純計算層測試分開——這裡驗證的是
main.py怎麼把yfinance資料接進策略引擎、以及路由/邊界條件，不重複算
credit/margin這些純數學）。2026-07-27起端點一次回傳三種策略（put_credit/
call_credit/iron_condor都算），is_recommended標記sentiment對應的那一種，
不再是「只回傳一種」的單一strategy欄位。
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


# 同時提供put跟call兩側流動性，讓三種策略都算得出來，方便測試is_recommended切換
BOTH_SIDES_LEGS = _fake_legs(
    put_quotes={90: (2.0, 2.2, 0.4), 85: (1.0, 1.2, 0.4)},
    call_quotes={110: (1.5, 1.7, 0.35), 115: (0.6, 0.8, 0.35)},
)


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


def _by_type(strategies, type_):
    return next((s for s in strategies if s["type"] == type_), None)


def test_rejects_symbol_not_in_watchlist(monkeypatch):
    _patch_common(monkeypatch)
    resp = client.get("/api/options/strategy", params={"symbol": "AAPL", "sentiment": "bullish"})
    assert resp.status_code == 400


def test_returns_all_three_strategies_when_computable(monkeypatch):
    _patch_common(monkeypatch, legs=BOTH_SIDES_LEGS)

    resp = client.get("/api/options/strategy", params={"symbol": SYMBOL, "sentiment": "bullish"})
    assert resp.status_code == 200
    body = resp.json()
    types = {s["type"] for s in body["strategies"]}
    assert types == {"put_credit", "call_credit", "iron_condor"}


def test_bullish_marks_put_credit_as_recommended(monkeypatch):
    _patch_common(monkeypatch, legs=BOTH_SIDES_LEGS)
    resp = client.get("/api/options/strategy", params={"symbol": SYMBOL, "sentiment": "bullish"})
    body = resp.json()

    put_credit = _by_type(body["strategies"], "put_credit")
    call_credit = _by_type(body["strategies"], "call_credit")
    condor = _by_type(body["strategies"], "iron_condor")
    assert put_credit["is_recommended"] is True
    assert call_credit["is_recommended"] is False
    assert condor["is_recommended"] is False
    assert put_credit["legs"][0]["action"] == "SELL"
    assert put_credit["legs"][0]["option_type"] == "PUT"
    assert put_credit["financials"]["max_profit"] == 80.0
    assert body["current_price"] == SPOT
    assert "Delta" in body["win_rate_disclaimer"]


def test_bearish_marks_call_credit_as_recommended(monkeypatch):
    _patch_common(monkeypatch, legs=BOTH_SIDES_LEGS)
    resp = client.get("/api/options/strategy", params={"symbol": SYMBOL, "sentiment": "bearish"})
    body = resp.json()

    call_credit = _by_type(body["strategies"], "call_credit")
    assert call_credit["is_recommended"] is True
    assert call_credit["legs"][0]["option_type"] == "CALL"
    assert _by_type(body["strategies"], "put_credit")["is_recommended"] is False


def test_neutral_marks_iron_condor_as_recommended(monkeypatch):
    _patch_common(monkeypatch, legs=BOTH_SIDES_LEGS)
    resp = client.get("/api/options/strategy", params={"symbol": SYMBOL, "sentiment": "neutral"})
    body = resp.json()

    condor = _by_type(body["strategies"], "iron_condor")
    assert condor["is_recommended"] is True
    assert len(condor["legs"]) == 4
    # 2026-07-26修正：win_rate_estimate必須是「兩腳都不破」的聯合機率，比leg_win_rates
    # 裡任一腳單獨的存活機率都低，不能讓使用者誤把單腳存活率看成整個策略的勝率
    leg_rates = condor["leg_win_rates"]
    assert leg_rates is not None and "put" in leg_rates and "call" in leg_rates
    combined_lower_bound = int(condor["win_rate_estimate"].split("-")[0])
    put_lower_bound = int(leg_rates["put"].split("-")[0])
    call_lower_bound = int(leg_rates["call"].split("-")[0])
    assert combined_lower_bound <= min(put_lower_bound, call_lower_bound)


def test_only_computable_strategies_are_returned(monkeypatch):
    # 只給put側流動性：call側/iron condor都算不出來，應該只回傳put_credit一種
    legs = _fake_legs(put_quotes={90: (2.0, 2.2, 0.4), 85: (1.0, 1.2, 0.4)})
    _patch_common(monkeypatch, legs=legs)

    resp = client.get("/api/options/strategy", params={"symbol": SYMBOL, "sentiment": "bearish"})
    body = resp.json()
    types = {s["type"] for s in body["strategies"]}
    assert types == {"put_credit"}
    # sentiment是bearish但只有put_credit算得出來，這種情況下沒有任何策略會被標記推薦
    assert all(not s["is_recommended"] for s in body["strategies"])


def test_uses_sentiment_label_for_display_when_provided(monkeypatch):
    _patch_common(monkeypatch, legs=BOTH_SIDES_LEGS)

    resp = client.get(
        "/api/options/strategy",
        params={"symbol": SYMBOL, "sentiment": "bullish", "sentiment_label": "強烈看多"},
    )
    assert resp.json()["market_sentiment"] == "強烈看多"


def test_falls_back_to_default_label_when_not_provided(monkeypatch):
    _patch_common(monkeypatch, legs=BOTH_SIDES_LEGS)

    resp = client.get("/api/options/strategy", params={"symbol": SYMBOL, "sentiment": "bullish"})
    assert resp.json()["market_sentiment"] == "看漲"


def test_returns_message_when_no_valid_strikes_found(monkeypatch):
    # 沒有任何履約價落在安全墊範圍內
    legs = [OptionLegRaw(strike=float(s), call_oi=0, call_iv=0, put_oi=0, put_iv=0) for s in [50, 150]]
    _patch_common(monkeypatch, legs=legs)
    monkeypatch.setattr(main, "_is_us_market_active", lambda _now: True)

    resp = client.get("/api/options/strategy", params={"symbol": SYMBOL, "sentiment": "bullish"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["strategies"] == []
    assert body["message"] is not None
    assert body["market_open"] is True


def test_market_closed_message_distinguishes_from_low_liquidity(monkeypatch):
    # 2026-07-27新增：休市時bid/ask普遍是0，這個情境不該跟「真的流動性不足」共用
    # 同一句話，容易讓使用者誤以為系統壞了或這檔真的沒人要交易。
    legs = _fake_legs()  # 全部bid/ask=0，模擬休市時yfinance回傳的樣子
    _patch_common(monkeypatch, legs=legs)
    monkeypatch.setattr(main, "_is_us_market_active", lambda _now: False)

    resp = client.get("/api/options/strategy", params={"symbol": SYMBOL, "sentiment": "bullish"})
    body = resp.json()
    assert body["market_open"] is False
    assert body["strategies"] == []
    assert "休市" in body["message"] or "非美股交易時段" in body["message"]


def test_market_open_field_true_during_market_hours_with_strategies(monkeypatch):
    _patch_common(monkeypatch, legs=BOTH_SIDES_LEGS)
    monkeypatch.setattr(main, "_is_us_market_active", lambda _now: True)

    resp = client.get("/api/options/strategy", params={"symbol": SYMBOL, "sentiment": "bullish"})
    assert resp.json()["market_open"] is True


def test_returns_message_when_spot_price_unavailable(monkeypatch):
    _patch_common(monkeypatch, spot=None, legs=[])
    resp = client.get("/api/options/strategy", params={"symbol": SYMBOL, "sentiment": "bullish"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["strategies"] == []
    assert body["current_price"] == 0.0
