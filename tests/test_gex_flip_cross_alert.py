"""
2026-07-16新增：現貨價穿越Gamma臨界點的「黃金交叉/死亡交叉」推播。驗證：
(1) 第一次啟動（沒有基準可比較）只建立基準，不誤判成交叉、不推播；
(2) 真的從臨界點下方穿越到上方時，正確判定成黃金交叉並記進broadcast；
(3) 沒有穿越（維持在同一側）不會誤觸發；
(4) 這輪算不出臨界點（None）時不更新基準、不推播，避免用不完整資料誤判。
"""

from dataclasses import dataclass

import main

SYMBOL = "NVDA"


@dataclass
class _FakeLeg:
    strike: float
    call_oi: float
    call_iv: float
    put_oi: float
    put_iv: float


def _patch_yfinance(monkeypatch, spot, legs, expiry="2026-08-01"):
    async def fake_spot(_ticker):
        return spot

    async def fake_expiry(_ticker):
        return expiry

    async def fake_legs(_ticker, _expiry):
        return legs

    monkeypatch.setattr(main.yfinance_client, "get_spot_price", fake_spot)
    monkeypatch.setattr(main.yfinance_client, "get_nearest_expiry", fake_expiry)
    monkeypatch.setattr(main.yfinance_client, "get_option_chain_legs", fake_legs)
    main.state.options_watchlist = {SYMBOL: SYMBOL}


def _reset_state():
    opt_state = main.state.get_options_state(SYMBOL)
    opt_state.was_above_flip = None
    opt_state.gex_points = []
    opt_state.gamma_flip_strike = None
    main.state.assistant_broadcasts.clear()
    return opt_state


# 兩檔合約組成一個乾淨的正負轉折剖面：低履約價put主導（負GEX），高履約價call
# 主導（正GEX）。實測過這組固定的legs在spot=100時算出flip=104.16（現價在臨界點
# 下方），spot=103時算出flip=102.31（現價在臨界點上方）——用真正跑過
# gex_engine算出來的值，不是憑感覺猜的數字（見開發過程中的手動驗證）。
BELOW_FLIP_SPOT = 100.0
ABOVE_FLIP_SPOT = 103.0
LEGS = [
    _FakeLeg(strike=95.0, call_oi=1.0, call_iv=0.01, put_oi=100.0, put_iv=0.4),
    _FakeLeg(strike=105.0, call_oi=100.0, call_iv=0.4, put_oi=1.0, put_iv=0.01),
]


async def test_first_run_establishes_baseline_without_alerting(monkeypatch):
    _patch_yfinance(monkeypatch, BELOW_FLIP_SPOT, LEGS)
    opt_state = _reset_state()

    await main.scan_options_analytics()

    assert opt_state.was_above_flip is False
    assert len(main.state.assistant_broadcasts) == 0


async def test_genuine_cross_triggers_golden_cross_alert(monkeypatch):
    _patch_yfinance(monkeypatch, BELOW_FLIP_SPOT, LEGS)
    opt_state = _reset_state()
    await main.scan_options_analytics()  # 建立基準：was_above_flip=False
    assert opt_state.was_above_flip is False

    _patch_yfinance(monkeypatch, ABOVE_FLIP_SPOT, LEGS)
    await main.scan_options_analytics()  # 這輪現價站上臨界點 -> 應該觸發黃金交叉

    assert opt_state.was_above_flip is True
    broadcasts = list(main.state.assistant_broadcasts)
    assert len(broadcasts) == 1
    assert broadcasts[0]["kind"] == "gex_flip_cross"
    assert broadcasts[0]["symbol"] == SYMBOL


async def test_no_cross_when_staying_on_same_side(monkeypatch):
    _patch_yfinance(monkeypatch, BELOW_FLIP_SPOT, LEGS)
    opt_state = _reset_state()
    await main.scan_options_analytics()
    await main.scan_options_analytics()  # 還是同一邊，不該觸發

    assert opt_state.was_above_flip is False
    assert len(main.state.assistant_broadcasts) == 0


async def test_undefined_flip_point_does_not_update_baseline_or_alert(monkeypatch):
    # 全部call主導、完全沒有正負轉折 -> find_gamma_flip_point 回傳 None
    one_sided_legs = [
        _FakeLeg(strike=100.0, call_oi=100.0, call_iv=0.4, put_oi=0.0, put_iv=0.01),
        _FakeLeg(strike=200.0, call_oi=100.0, call_iv=0.4, put_oi=0.0, put_iv=0.01),
    ]
    _patch_yfinance(monkeypatch, ABOVE_FLIP_SPOT, LEGS)
    opt_state = _reset_state()
    await main.scan_options_analytics()  # 先建立基準 was_above_flip=True
    assert opt_state.was_above_flip is True

    _patch_yfinance(monkeypatch, ABOVE_FLIP_SPOT, one_sided_legs)
    await main.scan_options_analytics()  # 這輪算不出臨界點

    assert opt_state.gamma_flip_strike is None
    assert opt_state.was_above_flip is True  # 維持上一輪的基準，不被清掉
    assert len(main.state.assistant_broadcasts) == 0
