"""聰明錢否決濾網：資金費率/大戶多空比明顯逆勢時，否決對應方向的新訊號。"""

from main import (
    FUNDING_RATE_HIGH,
    FUNDING_RATE_LOW,
    TOP_TRADER_RATIO_BEARISH,
    TOP_TRADER_RATIO_BULLISH,
    evaluate_smart_money_bias,
)


def test_high_funding_rate_vetoes_long():
    result = evaluate_smart_money_bias(FUNDING_RATE_HIGH, None, None)
    assert result["veto_long"] is True
    assert result["veto_short"] is False


def test_low_funding_rate_vetoes_short():
    result = evaluate_smart_money_bias(FUNDING_RATE_LOW, None, None)
    assert result["veto_short"] is True
    assert result["veto_long"] is False


def test_neutral_funding_rate_vetoes_nothing():
    result = evaluate_smart_money_bias(0.0, None, None)
    assert result["veto_long"] is False
    assert result["veto_short"] is False


def test_bullish_top_trader_ratio_vetoes_short_and_sets_bias():
    result = evaluate_smart_money_bias(None, TOP_TRADER_RATIO_BULLISH, None)
    assert result["veto_short"] is True
    assert result["bias"] == "Bullish"


def test_bearish_top_trader_ratio_vetoes_long_and_sets_bias():
    result = evaluate_smart_money_bias(None, TOP_TRADER_RATIO_BEARISH, None)
    assert result["veto_long"] is True
    assert result["bias"] == "Bearish"


def test_all_none_inputs_veto_nothing():
    result = evaluate_smart_money_bias(None, None, None)
    assert result == {"bias": "Neutral", "notes": [], "veto_long": False, "veto_short": False}
