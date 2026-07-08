"""calculate_leverage：固定風險模型，leverage = floor(FIXED_RISK_PCT / 止損距離%)，夾在 [MIN,MAX] 之間。"""

from main import FIXED_RISK_PCT, MAX_LEVERAGE, MIN_LEVERAGE, calculate_leverage


def test_typical_stop_loss_distance():
    # FIXED_RISK_PCT=15：止損距離1.5% -> floor(15/1.5)=10倍
    assert calculate_leverage(1.5) == 10


def test_wider_stop_loss_gives_lower_leverage():
    # 止損距離4% -> floor(15/4)=3倍
    assert calculate_leverage(4.0) == 3


def test_zero_or_negative_stop_loss_pct_falls_back_to_min():
    assert calculate_leverage(0.0) == MIN_LEVERAGE
    assert calculate_leverage(-1.0) == MIN_LEVERAGE


def test_tiny_stop_loss_distance_clamped_to_max_leverage():
    # 止損距離極小(0.01%)，理論上算出來槓桿會超大，要被夾到 MAX_LEVERAGE
    assert calculate_leverage(0.01) == MAX_LEVERAGE


def test_result_is_always_within_bounds():
    for pct in [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0]:
        lev = calculate_leverage(pct)
        assert MIN_LEVERAGE <= lev <= MAX_LEVERAGE


def test_matches_hand_computed_formula():
    import math
    pct = 2.3
    expected = max(MIN_LEVERAGE, min(MAX_LEVERAGE, math.floor(FIXED_RISK_PCT / pct)))
    assert calculate_leverage(pct) == expected
