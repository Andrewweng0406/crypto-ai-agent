"""
2026-07-16新增：Gemini建議④（用delta過濾大單流裡的非方向性噪音）——
_estimate_whale_sweep_delta 用「這檔標的最近一次GEX剖面重算」帶出來的
call_iv/put_iv 去估算whale sweep大單的delta，不是即時算隱含波動率。
驗證：正常情況估得出來、跟gex_engine的公式對得上；資料不足時老實回傳None，
不要顯示一個可能誤導的假數字。
"""

import gex_engine
import main

SYMBOL = "NVDA"


def _seed_options_state(spot_price, gex_points):
    opt_state = main.state.get_options_state(SYMBOL)
    opt_state.spot_price = spot_price
    opt_state.gex_points = gex_points
    return opt_state


def test_estimates_delta_matching_gex_engine_formula():
    _seed_options_state(200.0, [{"strike": 200.0, "call_gex": 0, "put_gex": 0, "net_gex": 0, "call_iv": 0.4, "put_iv": 0.42}])

    result = main._estimate_whale_sweep_delta(SYMBOL, 200.0, "2026-08-01", "call")

    assert result is not None
    time_to_expiry = main._time_to_expiry_years("2026-08-01")
    expected = float(gex_engine.black_scholes_delta(spot=200.0, strike=200.0, time_to_expiry_years=time_to_expiry, iv=0.4, option_type="call"))
    assert result == round(expected, 4)


def test_put_uses_put_iv_not_call_iv():
    _seed_options_state(200.0, [{"strike": 200.0, "call_gex": 0, "put_gex": 0, "net_gex": 0, "call_iv": 0.4, "put_iv": 0.9}])

    result = main._estimate_whale_sweep_delta(SYMBOL, 200.0, "2026-08-01", "put")

    time_to_expiry = main._time_to_expiry_years("2026-08-01")
    expected = float(gex_engine.black_scholes_delta(spot=200.0, strike=200.0, time_to_expiry_years=time_to_expiry, iv=0.9, option_type="put"))
    assert result == round(expected, 4)


def test_returns_none_when_symbol_not_tracked():
    assert main._estimate_whale_sweep_delta("UNTRACKED_SYMBOL", 100.0, "2026-08-01", "call") is None


def test_returns_none_when_no_spot_price_yet():
    opt_state = main.state.get_options_state(SYMBOL)
    opt_state.spot_price = None
    opt_state.gex_points = [{"strike": 200.0, "call_gex": 0, "put_gex": 0, "net_gex": 0, "call_iv": 0.4, "put_iv": 0.4}]

    assert main._estimate_whale_sweep_delta(SYMBOL, 200.0, "2026-08-01", "call") is None


def test_returns_none_when_strike_not_in_current_gex_window():
    _seed_options_state(200.0, [{"strike": 200.0, "call_gex": 0, "put_gex": 0, "net_gex": 0, "call_iv": 0.4, "put_iv": 0.4}])

    # 750 這個履約價不在目前追蹤的GEX剖面窗口內（見OPTIONS_STRIKE_WINDOW_PCT）
    assert main._estimate_whale_sweep_delta(SYMBOL, 750.0, "2026-08-01", "call") is None


def test_returns_none_when_iv_is_zero_or_missing():
    _seed_options_state(200.0, [{"strike": 200.0, "call_gex": 0, "put_gex": 0, "net_gex": 0, "call_iv": 0.0, "put_iv": 0.4}])

    assert main._estimate_whale_sweep_delta(SYMBOL, 200.0, "2026-08-01", "call") is None
