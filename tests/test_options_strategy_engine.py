"""
2026-07-26新增：期權賣方價差策略引擎。驗證：(1) 短腿在安全墊範圍內選離現價
最近的履約價，(2) 長腿是實際掛牌的下一檔而非憑空加減固定金額，(3) 財務數字
（credit/max_profit/max_loss/margin）計算正確，(4) risk_reward_ratio的方向
正確（max_loss:max_profit，不是反過來），(5) 找不到合適履約價或無流動性時
乾脆回傳None、不硬湊，(6) Iron Condor正確合併兩側、任一側失敗就整個失敗。
"""

from yfinance_client import OptionLegRaw

from options_strategy_engine import (
    build_credit_spread,
    build_iron_condor,
    estimate_win_rate_bucket,
    select_credit_spread_strikes,
)

SPOT = 100.0
# 履約價間距5一檔，涵蓋現價上下各25塊
STRIKES = [75, 80, 85, 90, 95, 100, 105, 110, 115, 120, 125]


def _make_legs(*, put_quotes: dict | None = None, call_quotes: dict | None = None) -> list[OptionLegRaw]:
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


def test_select_put_spread_picks_strike_closest_to_spot_within_band():
    # 現價100，安全墊8%~15% -> 履約價落在[85,92]之間；85(15% OTM)跟90(10% OTM)都在範圍內，
    # 應該選離現價最近的90當短腿（權利金較高），85則是往外一檔的長腿。
    legs = _make_legs()
    picked = select_credit_spread_strikes(legs, SPOT, "put")
    assert picked is not None
    short_leg, long_leg = picked
    assert short_leg.strike == 90.0
    assert long_leg.strike == 85.0


def test_select_call_spread_picks_strike_closest_to_spot_within_band():
    legs = _make_legs()
    picked = select_credit_spread_strikes(legs, SPOT, "call")
    assert picked is not None
    short_leg, long_leg = picked
    assert short_leg.strike == 110.0
    assert long_leg.strike == 115.0


def test_select_returns_none_when_no_strike_in_safety_band():
    # 履約價間距拉大到20一檔，8%~15%這個窄範圍(92~85之間)剛好卡不到任何履約價
    legs = [
        OptionLegRaw(strike=s, call_oi=0, call_iv=0, put_oi=0, put_iv=0)
        for s in [60, 80, 100, 120, 140]
    ]
    assert select_credit_spread_strikes(legs, SPOT, "put") is None


def test_select_returns_none_when_short_leg_is_most_extreme_strike():
    # 只給到90這一檔以上的履約價，90符合put安全墊條件但已經是最下面一檔，沒有更遠的長腿可選
    legs = [OptionLegRaw(strike=s, call_oi=0, call_iv=0, put_oi=0, put_iv=0) for s in [90, 95, 100, 105, 110]]
    assert select_credit_spread_strikes(legs, SPOT, "put") is None


def test_build_put_credit_spread_financials():
    legs = _make_legs(put_quotes={90: (2.0, 2.2, 0.4), 85: (1.0, 1.2, 0.45)})
    result = build_credit_spread(legs, SPOT, "put", time_to_expiry_years=30 / 365)
    assert result is not None
    assert result.spread_type == "put_credit"
    assert result.legs[0].action == "SELL" and result.legs[0].strike_price == 90.0
    assert result.legs[1].action == "BUY" and result.legs[1].strike_price == 85.0

    # credit = short_bid(2.0) - long_ask(1.2) = 0.8；max_profit = 0.8*100 = 80
    assert result.max_profit == 80.0
    # width=5, max_loss = (5-0.8)*100 = 420
    assert result.max_loss == 420.0
    assert result.margin_required == 420.0
    # risk_reward_ratio = max_loss:max_profit = 420/80 = 5.25 -> "1 : 5.2"（Python .1f 四捨五入）
    assert result.risk_reward_ratio == "1 : 5.2"


def test_risk_reward_ratio_matches_user_provided_example():
    # 使用者原始範例：max_profit=115, max_loss=385 -> "1 : 3.3"（385/115≈3.348）
    # 反推所需的 credit/width：width=5, credit=1.15 -> max_profit=115, max_loss=(5-1.15)*100=385
    # 短腿bid=2.15、長腿ask=1.0 的組合：credit=1.15（長腿bid隨便給一個>0的值，不影響這裡算的credit）
    legs = _make_legs(put_quotes={90: (2.15, 2.3, 0.4), 85: (0.9, 1.0, 0.4)})
    result = build_credit_spread(legs, SPOT, "put", time_to_expiry_years=30 / 365)
    assert result is not None
    assert result.max_profit == 115.0
    assert result.max_loss == 385.0
    assert result.risk_reward_ratio == "1 : 3.3"


def test_build_credit_spread_returns_none_when_no_liquidity():
    # 短腿完全沒有報價（bid=0），代表沒人掛單，這種價差實際上下不了單
    legs = _make_legs(put_quotes={90: (0.0, 0.5, 0.4), 85: (0.0, 0.2, 0.4)})
    assert build_credit_spread(legs, SPOT, "put", time_to_expiry_years=30 / 365) is None


def test_build_credit_spread_returns_none_when_credit_is_negative():
    # 報價異常：短腿bid反而比長腿ask低，算出負credit
    legs = _make_legs(put_quotes={90: (0.5, 0.6, 0.4), 85: (1.0, 1.2, 0.4)})
    assert build_credit_spread(legs, SPOT, "put", time_to_expiry_years=30 / 365) is None


def test_build_credit_spread_win_rate_na_when_iv_missing():
    legs = _make_legs(put_quotes={90: (2.0, 2.2, 0.0), 85: (1.0, 1.2, 0.0)})
    result = build_credit_spread(legs, SPOT, "put", time_to_expiry_years=30 / 365)
    assert result is not None
    assert result.win_rate_bucket == "N/A"


def test_estimate_win_rate_bucket_buckets_into_10pct_ranges():
    assert estimate_win_rate_bucket(-0.20) == "80-90%"  # POP = 1-0.20 = 0.80
    assert estimate_win_rate_bucket(-0.25) == "70-80%"  # POP = 0.75
    assert estimate_win_rate_bucket(0.0) == "90-100%"


def test_build_iron_condor_combines_both_sides():
    legs = _make_legs(
        put_quotes={90: (2.0, 2.2, 0.4), 85: (1.0, 1.2, 0.4)},
        call_quotes={110: (1.5, 1.7, 0.35), 115: (0.6, 0.8, 0.35)},
    )
    result = build_iron_condor(legs, SPOT, time_to_expiry_years=30 / 365)
    assert result is not None
    assert result.spread_type == "iron_condor"
    assert len(result.legs) == 4
    put_profit = (2.0 - 1.2) * 100
    call_profit = (1.5 - 0.8) * 100
    assert result.max_profit == round(put_profit + call_profit, 2)
    put_loss = (5 - 0.8) * 100
    call_loss = (5 - 0.7) * 100
    assert result.max_loss == round(max(put_loss, call_loss), 2)


def test_build_iron_condor_returns_none_if_either_side_fails():
    # 只給put側報價，call側完全沒流動性 -> 整個Iron Condor應該失敗，不湊殘缺的
    legs = _make_legs(put_quotes={90: (2.0, 2.2, 0.4), 85: (1.0, 1.2, 0.4)})
    assert build_iron_condor(legs, SPOT, time_to_expiry_years=30 / 365) is None
