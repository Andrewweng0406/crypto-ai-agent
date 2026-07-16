"""
2026-07-16新增：期權GEX剖面的「換日快照」機制——OI本身每天盤前才更新一次，
同一天內反覆抓不會變，所以「今天新增 vs 昨天既有」的比較基準是「換日時把
當時最後一份 gex_points 捲存起來」。驗證：(1) 換日時正確把舊資料捲進
previous_day_gex_points，(2) 同一天內重複抓不會誤把「幾分鐘前」當成「昨天」，
(3) 第一次啟動（沒有舊資料）不會用空資料覆蓋。
"""

from dataclasses import dataclass

import main


@dataclass
class _FakeLeg:
    strike: float
    call_oi: float
    call_iv: float
    put_oi: float
    put_iv: float


SYMBOL = "NVDA"
FAKE_LEGS = [_FakeLeg(strike=200.0, call_oi=100.0, call_iv=0.4, put_oi=50.0, put_iv=0.4)]
OLD_SNAPSHOT = [{"strike": 200.0, "call_gex": 111.0, "put_gex": 22.0, "net_gex": 89.0}]


async def _fake_spot(_ticker):
    return 200.0


async def _fake_expiry(_ticker):
    return "2026-08-01"


async def _fake_legs(_ticker, _expiry):
    return FAKE_LEGS


def _patch_yfinance(monkeypatch):
    monkeypatch.setattr(main.yfinance_client, "get_spot_price", _fake_spot)
    monkeypatch.setattr(main.yfinance_client, "get_nearest_expiry", _fake_expiry)
    monkeypatch.setattr(main.yfinance_client, "get_option_chain_legs", _fake_legs)
    main.state.options_watchlist = {SYMBOL: SYMBOL}


async def test_rolls_previous_day_snapshot_on_date_change(monkeypatch):
    _patch_yfinance(monkeypatch)
    opt_state = main.state.get_options_state(SYMBOL)
    opt_state.gex_points = OLD_SNAPSHOT
    opt_state.previous_day_gex_points = []
    opt_state.last_snapshot_date = "2020-01-01"  # 確定跟真正的「今天」不同

    await main.scan_options_analytics()

    assert opt_state.previous_day_gex_points == OLD_SNAPSHOT
    assert opt_state.last_snapshot_date != "2020-01-01"
    assert opt_state.gex_points != OLD_SNAPSHOT  # 换成新算出來的這輪資料


async def test_does_not_reroll_within_same_day(monkeypatch):
    _patch_yfinance(monkeypatch)
    opt_state = main.state.get_options_state(SYMBOL)
    opt_state.gex_points = OLD_SNAPSHOT
    opt_state.previous_day_gex_points = []
    opt_state.last_snapshot_date = None

    await main.scan_options_analytics()
    today = opt_state.last_snapshot_date
    first_round_points = opt_state.gex_points

    # 同一天內再抓一次：previous_day_gex_points 不該被「剛剛那輪」覆蓋掉
    opt_state.gex_points = first_round_points
    await main.scan_options_analytics()

    assert opt_state.last_snapshot_date == today
    assert opt_state.previous_day_gex_points == []


async def test_first_run_does_not_populate_previous_day_with_empty_data(monkeypatch):
    _patch_yfinance(monkeypatch)
    opt_state = main.state.get_options_state(SYMBOL)
    opt_state.gex_points = []
    opt_state.previous_day_gex_points = []
    opt_state.last_snapshot_date = None  # 全新啟動，從沒抓過

    await main.scan_options_analytics()

    assert opt_state.previous_day_gex_points == []
    assert opt_state.gex_points != []
