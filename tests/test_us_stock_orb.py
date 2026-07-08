"""美股 ORB 當沖策略核心邏輯：Long/Short 不對稱停損、市場時段判定。"""

from datetime import datetime
from zoneinfo import ZoneInfo

from main import (
    ORB_RISK_REWARD_RATIO,
    US_MARKET_TZ,
    _is_us_market_active,
    build_us_stock_open_signal,
)

TZ = ZoneInfo(US_MARKET_TZ)


def test_long_stop_loss_is_opening_range_low():
    candidate = {"side": "Long", "entry_price": 410.0, "opening_high": 420.0, "opening_low": 400.0}
    opened = build_us_stock_open_signal("TSLA", "NCSKTSLA2USD/USDT:USDT", candidate)
    assert opened["stop_loss"] == 400.0
    sl_distance = opened["entry_price"] - opened["stop_loss"]
    assert opened["take_profit"] == opened["entry_price"] + sl_distance * ORB_RISK_REWARD_RATIO


def test_short_stop_loss_uses_day_high_when_higher_than_range_mid():
    # 區間中點 = (420+400)/2 = 410；當日最高點 425 比中點高，應該用 425
    candidate = {
        "side": "Short", "entry_price": 395.0, "opening_high": 420.0, "opening_low": 400.0,
        "day_high_so_far": 425.0,
    }
    opened = build_us_stock_open_signal("TSLA", "NCSKTSLA2USD/USDT:USDT", candidate)
    assert opened["stop_loss"] == 425.0


def test_short_stop_loss_uses_range_mid_when_day_high_lower():
    # 當日最高點 405 比中點 410 低，應該用中點 410（不會比中點更緊）
    candidate = {
        "side": "Short", "entry_price": 395.0, "opening_high": 420.0, "opening_low": 400.0,
        "day_high_so_far": 405.0,
    }
    opened = build_us_stock_open_signal("TSLA", "NCSKTSLA2USD/USDT:USDT", candidate)
    assert opened["stop_loss"] == 410.0


def test_short_without_day_high_so_far_falls_back_to_opening_high():
    candidate = {"side": "Short", "entry_price": 395.0, "opening_high": 420.0, "opening_low": 400.0}
    opened = build_us_stock_open_signal("TSLA", "NCSKTSLA2USD/USDT:USDT", candidate)
    assert opened["stop_loss"] == 420.0


def test_market_active_during_trading_window_on_weekday():
    # 2026-07-08 是週三
    now = datetime(2026, 7, 8, 12, 0, tzinfo=TZ)
    assert _is_us_market_active(now) is True


def test_market_inactive_before_open():
    now = datetime(2026, 7, 8, 8, 0, tzinfo=TZ)
    assert _is_us_market_active(now) is False


def test_market_inactive_after_close():
    now = datetime(2026, 7, 8, 17, 0, tzinfo=TZ)
    assert _is_us_market_active(now) is False


def test_market_inactive_on_weekend():
    # 2026-07-11 是週六
    now = datetime(2026, 7, 11, 12, 0, tzinfo=TZ)
    assert _is_us_market_active(now) is False


def test_market_active_at_exact_boundaries():
    assert _is_us_market_active(datetime(2026, 7, 8, 9, 15, tzinfo=TZ)) is True
    assert _is_us_market_active(datetime(2026, 7, 8, 16, 0, tzinfo=TZ)) is True
