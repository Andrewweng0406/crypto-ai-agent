"""多空情緒擠壓爆破模式：OI成長率計算、RVOL/突破判斷、藍/黃/綠燈邏輯。"""

from collections import deque

import numpy as np
import pandas as pd
import pytest

from main import (
    FUNDING_RATE_HIGH,
    FUNDING_RATE_LOW,
    SQUEEZE_BREAKOUT_LOOKBACK,
    SQUEEZE_OI_GROWTH_BLUE_PCT,
    SQUEEZE_OI_GROWTH_GREEN_PCT,
    SQUEEZE_OI_HISTORY_LEN,
    SQUEEZE_OI_LOOKBACK_15M_SAMPLES,
    SQUEEZE_OI_LOOKBACK_1H_SAMPLES,
    SQUEEZE_RVOL_THRESHOLD,
    SQUEEZE_VOLUME_LOOKBACK,
    compute_oi_growth_pct,
    compute_squeeze_price_volume,
    compute_squeeze_tier,
)


def test_oi_growth_none_when_insufficient_history():
    history = deque([100.0, 105.0], maxlen=SQUEEZE_OI_HISTORY_LEN)
    assert compute_oi_growth_pct(history, SQUEEZE_OI_LOOKBACK_1H_SAMPLES) is None


def test_oi_growth_computed_correctly():
    # lookback=3：跟3筆前比較
    history = deque([100.0, 100.0, 100.0, 100.0, 130.0], maxlen=SQUEEZE_OI_HISTORY_LEN)
    growth = compute_oi_growth_pct(history, 3)
    assert growth == pytest.approx(30.0)


def test_oi_growth_none_when_old_value_is_zero():
    history = deque([0.0, 0.0, 0.0, 0.0, 100.0], maxlen=SQUEEZE_OI_HISTORY_LEN)
    assert compute_oi_growth_pct(history, 3) is None


def _make_squeeze_df(n=50, volume_spike=True, breakout=True):
    idx = np.arange(n, dtype=float)
    base = 100 + idx * 0.01
    df = pd.DataFrame({
        "timestamp": idx.astype(int),
        "open": base, "high": base + 0.1, "low": base - 0.1, "close": base,
        "volume": np.full(n, 1000.0),
    })
    if breakout:
        prior_high = df["high"].iloc[-(SQUEEZE_BREAKOUT_LOOKBACK + 1):-1].max()
        df.loc[df.index[-1], ["close", "high"]] = prior_high + 5.0
    if volume_spike:
        df.loc[df.index[-1], "volume"] = 5000.0
    return df


def test_squeeze_price_volume_detects_breakout_and_rvol():
    df = _make_squeeze_df(volume_spike=True, breakout=True)
    result = compute_squeeze_price_volume(df)
    assert result is not None
    assert result["is_breakout"] is True
    assert result["rvol"] > SQUEEZE_RVOL_THRESHOLD


def test_squeeze_price_volume_no_breakout():
    df = _make_squeeze_df(volume_spike=True, breakout=False)
    result = compute_squeeze_price_volume(df)
    assert result["is_breakout"] is False


def test_squeeze_price_volume_insufficient_data_returns_none():
    df = _make_squeeze_df(n=10)
    assert compute_squeeze_price_volume(df) is None


def test_tier_green_requires_all_three_conditions():
    tier = compute_squeeze_tier(
        oi_growth_15m_pct=20.0,
        oi_growth_1h_pct=SQUEEZE_OI_GROWTH_GREEN_PCT,
        rvol=SQUEEZE_RVOL_THRESHOLD,
        funding_rate=FUNDING_RATE_HIGH,
        is_breakout=True,
    )
    assert tier == "green"


def test_tier_yellow_when_oi_surged_but_rvol_missing():
    tier = compute_squeeze_tier(
        oi_growth_15m_pct=None,
        oi_growth_1h_pct=SQUEEZE_OI_GROWTH_GREEN_PCT,
        rvol=1.0,  # 沒到RVOL門檻
        funding_rate=FUNDING_RATE_HIGH,
        is_breakout=False,
    )
    assert tier == "yellow"


def test_tier_yellow_when_oi_surged_but_funding_not_extreme():
    tier = compute_squeeze_tier(
        oi_growth_15m_pct=None,
        oi_growth_1h_pct=SQUEEZE_OI_GROWTH_GREEN_PCT,
        rvol=SQUEEZE_RVOL_THRESHOLD,
        funding_rate=0.0,  # 中性費率，不極端
        is_breakout=False,
    )
    assert tier == "yellow"


def test_tier_blue_on_15m_surge_with_breakout():
    tier = compute_squeeze_tier(
        oi_growth_15m_pct=SQUEEZE_OI_GROWTH_BLUE_PCT,
        oi_growth_1h_pct=None,
        rvol=None,
        funding_rate=None,
        is_breakout=True,
    )
    assert tier == "blue"


def test_tier_none_when_15m_surge_without_breakout():
    tier = compute_squeeze_tier(
        oi_growth_15m_pct=SQUEEZE_OI_GROWTH_BLUE_PCT,
        oi_growth_1h_pct=None,
        rvol=None,
        funding_rate=None,
        is_breakout=False,
    )
    assert tier == "none"


def test_tier_none_when_nothing_met():
    tier = compute_squeeze_tier(None, None, None, None, False)
    assert tier == "none"


def test_tier_green_takes_priority_over_blue():
    # 兩個門檻都達到時，green優先於blue
    tier = compute_squeeze_tier(
        oi_growth_15m_pct=SQUEEZE_OI_GROWTH_BLUE_PCT,
        oi_growth_1h_pct=SQUEEZE_OI_GROWTH_GREEN_PCT,
        rvol=SQUEEZE_RVOL_THRESHOLD,
        funding_rate=FUNDING_RATE_LOW,
        is_breakout=True,
    )
    assert tier == "green"
