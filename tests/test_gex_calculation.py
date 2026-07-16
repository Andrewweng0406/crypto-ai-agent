"""GEX calculation engine tests.

Uses synthetic strikes/OI/IV around a fixed spot price — this is the "拿昨天
的歷史數據進行模擬計算" requirement: we don't need a live Moomoo connection to
validate the math, only realistic option-chain-shaped inputs. Compares
black_scholes_gamma against textbook closed-form values, sanity-checks the
Net GEX formula's arithmetic directly, and exercises find_gamma_flip_point on
profiles with a known, hand-computed crossing point.
"""

import time

import numpy as np
import pytest
from scipy.stats import norm

from gex_engine import (
    OptionLeg,
    black_scholes_delta,
    black_scholes_gamma,
    compute_net_gex_by_strike,
    find_gamma_flip_point,
)


def reference_gamma(spot, strike, t, iv, r=0.045):
    """Textbook Black-Scholes gamma, computed independently of gex_engine."""
    d1 = (np.log(spot / strike) + (r + 0.5 * iv**2) * t) / (iv * np.sqrt(t))
    return norm.pdf(d1) / (spot * iv * np.sqrt(t))


def reference_delta(spot, strike, t, iv, option_type, r=0.045):
    """Textbook Black-Scholes delta, computed independently of gex_engine."""
    d1 = (np.log(spot / strike) + (r + 0.5 * iv**2) * t) / (iv * np.sqrt(t))
    call_delta = norm.cdf(d1)
    return call_delta if option_type == "call" else call_delta - 1.0


class TestBlackScholesGamma:
    def test_matches_reference_formula_atm(self):
        result = black_scholes_gamma(spot=100.0, strike=100.0, time_to_expiry_years=30 / 365, iv=0.35)
        expected = reference_gamma(100.0, 100.0, 30 / 365, 0.35)
        assert result == pytest.approx(expected, rel=1e-9)

    def test_matches_reference_formula_otm(self):
        result = black_scholes_gamma(spot=100.0, strike=120.0, time_to_expiry_years=45 / 365, iv=0.5)
        expected = reference_gamma(100.0, 120.0, 45 / 365, 0.5)
        assert result == pytest.approx(expected, rel=1e-9)

    def test_gamma_is_positive(self):
        # Gamma is always >= 0 for a vanilla option, long or short strike.
        result = black_scholes_gamma(spot=100.0, strike=95.0, time_to_expiry_years=0.1, iv=0.4)
        assert result > 0

    def test_gamma_peaks_near_the_money(self):
        atm = black_scholes_gamma(spot=100.0, strike=100.0, time_to_expiry_years=30 / 365, iv=0.3)
        deep_otm = black_scholes_gamma(spot=100.0, strike=200.0, time_to_expiry_years=30 / 365, iv=0.3)
        deep_itm = black_scholes_gamma(spot=100.0, strike=20.0, time_to_expiry_years=30 / 365, iv=0.3)
        assert atm > deep_otm
        assert atm > deep_itm

    def test_expired_contract_returns_zero_not_nan(self):
        # A stale/expired row (T<=0) must not poison a vectorized sum with NaN.
        result = black_scholes_gamma(spot=100.0, strike=100.0, time_to_expiry_years=0.0, iv=0.3)
        assert result == 0.0
        assert not np.isnan(result)

    def test_zero_iv_returns_zero_not_inf(self):
        result = black_scholes_gamma(spot=100.0, strike=100.0, time_to_expiry_years=0.1, iv=0.0)
        assert result == 0.0
        assert not np.isinf(result)

    def test_vectorized_matches_scalar_elementwise(self):
        strikes = np.array([80.0, 90.0, 100.0, 110.0, 120.0])
        ivs = np.array([0.6, 0.5, 0.4, 0.45, 0.55])
        vectorized = black_scholes_gamma(spot=100.0, strike=strikes, time_to_expiry_years=0.2, iv=ivs)
        scalar = np.array([
            black_scholes_gamma(spot=100.0, strike=k, time_to_expiry_years=0.2, iv=v)
            for k, v in zip(strikes, ivs)
        ])
        np.testing.assert_allclose(vectorized, scalar, rtol=1e-9)


class TestBlackScholesDelta:
    """2026-07-16新增：Gemini建議④（用delta過濾大單流裡的非方向性噪音）需要
    先有delta可以算——這裡驗證公式本身跟教科書closed-form一致，供main.py
    估算whale sweep大單delta時使用。"""

    def test_call_matches_reference_formula(self):
        result = black_scholes_delta(spot=100.0, strike=100.0, time_to_expiry_years=30 / 365, iv=0.35, option_type="call")
        expected = reference_delta(100.0, 100.0, 30 / 365, 0.35, "call")
        assert result == pytest.approx(expected, rel=1e-9)

    def test_put_matches_reference_formula(self):
        result = black_scholes_delta(spot=100.0, strike=110.0, time_to_expiry_years=45 / 365, iv=0.5, option_type="put")
        expected = reference_delta(100.0, 110.0, 45 / 365, 0.5, "put")
        assert result == pytest.approx(expected, rel=1e-9)

    def test_call_delta_between_zero_and_one(self):
        for strike in [50.0, 90.0, 100.0, 110.0, 200.0]:
            d = black_scholes_delta(spot=100.0, strike=strike, time_to_expiry_years=0.25, iv=0.4, option_type="call")
            assert 0.0 <= d <= 1.0

    def test_put_delta_between_negative_one_and_zero(self):
        for strike in [50.0, 90.0, 100.0, 110.0, 200.0]:
            d = black_scholes_delta(spot=100.0, strike=strike, time_to_expiry_years=0.25, iv=0.4, option_type="put")
            assert -1.0 <= d <= 0.0

    def test_atm_call_delta_near_half(self):
        # 高度價平、時間夠長時，call delta理論上接近0.5（不是恰好0.5，drift項會讓它偏一點）。
        d = black_scholes_delta(spot=100.0, strike=100.0, time_to_expiry_years=30 / 365, iv=0.3, option_type="call")
        assert 0.4 < d < 0.6

    def test_deep_itm_call_delta_near_one(self):
        d = black_scholes_delta(spot=200.0, strike=50.0, time_to_expiry_years=30 / 365, iv=0.3, option_type="call")
        assert d > 0.95

    def test_deep_otm_call_delta_near_zero(self):
        d = black_scholes_delta(spot=50.0, strike=200.0, time_to_expiry_years=30 / 365, iv=0.3, option_type="call")
        assert d < 0.05

    def test_expired_or_zero_iv_returns_nan_not_crash(self):
        assert np.isnan(black_scholes_delta(spot=100.0, strike=100.0, time_to_expiry_years=0.0, iv=0.3, option_type="call"))
        assert np.isnan(black_scholes_delta(spot=100.0, strike=100.0, time_to_expiry_years=0.1, iv=0.0, option_type="put"))

    def test_vectorized_option_type_array_matches_scalar(self):
        strikes = np.array([90.0, 100.0, 110.0])
        types = np.array(["call", "put", "call"])
        vectorized = black_scholes_delta(spot=100.0, strike=strikes, time_to_expiry_years=0.2, iv=0.4, option_type=types)
        scalar = np.array([
            black_scholes_delta(spot=100.0, strike=k, time_to_expiry_years=0.2, iv=0.4, option_type=t)
            for k, t in zip(strikes, types)
        ])
        np.testing.assert_allclose(vectorized, scalar, rtol=1e-9)


class TestNetGexByStrike:
    def test_single_strike_matches_hand_computed_formula(self):
        spot = 100.0
        leg = OptionLeg(strike=100.0, call_oi=1000, call_iv=0.3, put_oi=500, put_iv=0.3)
        [row] = compute_net_gex_by_strike([leg], spot=spot, time_to_expiry_years=30 / 365)

        gamma = reference_gamma(spot, 100.0, 30 / 365, 0.3)
        expected_call_gex = 1000 * gamma * spot**2 * 100
        expected_put_gex = 500 * gamma * spot**2 * 100

        assert row["call_gex"] == pytest.approx(expected_call_gex, rel=1e-9)
        assert row["put_gex"] == pytest.approx(expected_put_gex, rel=1e-9)
        assert row["net_gex"] == pytest.approx(expected_call_gex - expected_put_gex, rel=1e-9)

    def test_more_call_oi_than_put_oi_gives_positive_net_gex(self):
        leg = OptionLeg(strike=100.0, call_oi=5000, call_iv=0.3, put_oi=100, put_iv=0.3)
        [row] = compute_net_gex_by_strike([leg], spot=100.0, time_to_expiry_years=0.1)
        assert row["net_gex"] > 0

    def test_more_put_oi_than_call_oi_gives_negative_net_gex(self):
        leg = OptionLeg(strike=100.0, call_oi=100, call_iv=0.3, put_oi=5000, put_iv=0.3)
        [row] = compute_net_gex_by_strike([leg], spot=100.0, time_to_expiry_years=0.1)
        assert row["net_gex"] < 0

    def test_results_sorted_by_strike_ascending(self):
        legs = [
            OptionLeg(strike=110.0, call_oi=100, call_iv=0.3, put_oi=100, put_iv=0.3),
            OptionLeg(strike=90.0, call_oi=100, call_iv=0.3, put_oi=100, put_iv=0.3),
            OptionLeg(strike=100.0, call_oi=100, call_iv=0.3, put_oi=100, put_iv=0.3),
        ]
        rows = compute_net_gex_by_strike(legs, spot=100.0, time_to_expiry_years=0.1)
        assert [r["strike"] for r in rows] == [90.0, 100.0, 110.0]

    def test_empty_legs_returns_empty_list(self):
        assert compute_net_gex_by_strike([], spot=100.0, time_to_expiry_years=0.1) == []


class TestGammaFlipPoint:
    def test_finds_interpolated_crossing_between_strikes(self):
        # Cumulative net GEX: -100 at strike 95 -> +100 at strike 105.
        # Crosses zero exactly halfway.
        profile = [
            {"strike": 95.0, "net_gex": -100.0},
            {"strike": 105.0, "net_gex": 200.0},
        ]
        flip = find_gamma_flip_point(profile)
        assert flip == pytest.approx(100.0)

    def test_no_crossing_returns_none_for_all_positive(self):
        profile = [
            {"strike": 95.0, "net_gex": 50.0},
            {"strike": 100.0, "net_gex": 50.0},
            {"strike": 105.0, "net_gex": 50.0},
        ]
        assert find_gamma_flip_point(profile) is None

    def test_no_crossing_returns_none_for_all_negative(self):
        profile = [
            {"strike": 95.0, "net_gex": -50.0},
            {"strike": 100.0, "net_gex": -30.0},
            {"strike": 105.0, "net_gex": -20.0},
        ]
        assert find_gamma_flip_point(profile) is None

    def test_exact_zero_crossing_returns_that_strike(self):
        profile = [
            {"strike": 95.0, "net_gex": -100.0},
            {"strike": 100.0, "net_gex": 100.0},
            {"strike": 105.0, "net_gex": 50.0},
        ]
        # Cumulative: -100, 0, 50 -> exact zero lands on strike 100.
        assert find_gamma_flip_point(profile) == pytest.approx(100.0)

    def test_fewer_than_two_strikes_returns_none(self):
        assert find_gamma_flip_point([{"strike": 100.0, "net_gex": 50.0}]) is None
        assert find_gamma_flip_point([]) is None

    def test_realistic_multi_strike_profile(self):
        # Typical shape: negative GEX below spot (put-heavy), positive above
        # (call-heavy), crossing somewhere near spot.
        legs = [
            OptionLeg(strike=k, call_oi=200 + max(0, (k - 100)) * 20, call_iv=0.35,
                      put_oi=200 + max(0, (100 - k)) * 20, put_iv=0.35)
            for k in range(80, 121, 5)
        ]
        rows = compute_net_gex_by_strike(legs, spot=100.0, time_to_expiry_years=20 / 365)
        flip = find_gamma_flip_point(rows)
        assert flip is not None
        assert 80.0 <= flip <= 120.0


class TestPerformance:
    def test_vectorized_chain_computation_is_fast_at_realistic_scale(self):
        # 5 underlyings x ~8 expiries x ~40 strikes each ~= 1600 legs per
        # poll cycle — the "high concurrency, still efficient" requirement.
        # A pure-Python per-contract loop would be the naive alternative;
        # this asserts the vectorized path handles that volume well under
        # the 60s poll interval with large margin.
        rng = np.random.default_rng(42)
        legs = [
            OptionLeg(
                strike=float(k),
                call_oi=float(rng.integers(0, 5000)),
                call_iv=float(rng.uniform(0.15, 0.9)),
                put_oi=float(rng.integers(0, 5000)),
                put_iv=float(rng.uniform(0.15, 0.9)),
            )
            for k in range(1, 1601)
        ]
        start = time.perf_counter()
        rows = compute_net_gex_by_strike(legs, spot=500.0, time_to_expiry_years=15 / 365)
        elapsed = time.perf_counter() - start

        assert len(rows) == 1600
        assert elapsed < 1.0

    def test_no_nan_or_inf_in_output_across_wide_strike_range(self):
        # Guards against silent NaN propagation when strikes are far ITM/OTM
        # relative to spot, which a real chain will always include.
        legs = [
            OptionLeg(strike=float(k), call_oi=100, call_iv=0.4, put_oi=100, put_iv=0.4)
            for k in [1.0, 10.0, 50.0, 100.0, 500.0, 1000.0, 5000.0]
        ]
        rows = compute_net_gex_by_strike(legs, spot=100.0, time_to_expiry_years=0.05)
        for row in rows:
            assert np.isfinite(row["call_gex"])
            assert np.isfinite(row["put_gex"])
            assert np.isfinite(row["net_gex"])
