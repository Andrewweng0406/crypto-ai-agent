"""Pure Gamma Exposure (GEX) calculation engine.

No I/O, no Moomoo/Futu dependency — everything here takes plain numbers or
numpy arrays in and returns numbers out, so it can be unit tested with
synthetic data and reused unchanged regardless of which broker API feeds it.

Net GEX convention follows the standard "dealer is long calls / short puts"
assumption (same convention used by SqueezeMetrics/SpotGamma-style trackers):
  Net GEX = (Call_OI * Call_Gamma - Put_OI * Put_Gamma) * S^2 * 100

This is dollar gamma exposure per $1 move in the underlying (not per 1% move
— there is no extra 0.01 scaling), matching the formula as specified for this
project. Open interest is a daily snapshot (exchanges only publish OI once,
pre-market) — that is a market-data fact, not a broker limitation. The
intended refresh pattern is: OI held fixed intraday, gamma recomputed every
poll against the live spot price, so the GEX curve still moves in real time
even though OI itself does not.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

import numpy as np
from scipy.stats import norm

OptionType = Literal["call", "put"]

SECONDS_PER_YEAR = 365.25 * 24 * 3600
CONTRACT_MULTIPLIER = 100


def _d1(spot: np.ndarray, strike: np.ndarray, time_to_expiry: np.ndarray, risk_free_rate: float, iv: np.ndarray) -> np.ndarray:
    # Standard Black-Scholes d1; callers must have already filtered out
    # time_to_expiry <= 0 or iv <= 0 (both make d1 undefined/infinite).
    return (
        np.log(spot / strike) + (risk_free_rate + 0.5 * iv**2) * time_to_expiry
    ) / (iv * np.sqrt(time_to_expiry))


def black_scholes_gamma(
    spot: float | np.ndarray,
    strike: float | np.ndarray,
    time_to_expiry_years: float | np.ndarray,
    iv: float | np.ndarray,
    risk_free_rate: float = 0.045,
) -> np.ndarray:
    """Black-Scholes Gamma. Identical formula for calls and puts.

    Vectorized: pass numpy arrays for strike/time/iv to price an entire
    option chain in one call instead of looping per contract — this is what
    keeps a 5-underlying x multi-expiry GEX recompute cheap enough to run
    every minute.
    """
    spot = np.asarray(spot, dtype=float)
    strike = np.asarray(strike, dtype=float)
    time_to_expiry = np.asarray(time_to_expiry_years, dtype=float)
    iv = np.asarray(iv, dtype=float)

    # Expired or zero/negative-vol contracts have no defined gamma — return
    # 0 rather than NaN/inf so a stale row can't poison a vectorized sum.
    safe = (time_to_expiry > 0) & (iv > 0) & (spot > 0) & (strike > 0)
    time_safe = np.where(safe, time_to_expiry, 1.0)
    iv_safe = np.where(safe, iv, 1.0)

    d1 = _d1(spot, strike, time_safe, risk_free_rate, iv_safe)
    gamma = norm.pdf(d1) / (spot * iv_safe * np.sqrt(time_safe))
    return np.where(safe, gamma, 0.0)


@dataclass
class OptionLeg:
    strike: float
    call_oi: float
    call_iv: float
    put_oi: float
    put_iv: float


def compute_net_gex_by_strike(
    legs: Sequence[OptionLeg],
    spot: float,
    time_to_expiry_years: float,
    risk_free_rate: float = 0.045,
) -> list[dict]:
    """Net GEX per strike for one expiry.

    Returns a list of dicts (strike, call_gex, put_gex, net_gex), sorted by
    strike ascending, ready to feed a bar/area chart directly.
    """
    if not legs:
        return []

    strikes = np.array([leg.strike for leg in legs], dtype=float)
    call_oi = np.array([leg.call_oi for leg in legs], dtype=float)
    call_iv = np.array([leg.call_iv for leg in legs], dtype=float)
    put_oi = np.array([leg.put_oi for leg in legs], dtype=float)
    put_iv = np.array([leg.put_iv for leg in legs], dtype=float)

    time_arr = np.full_like(strikes, time_to_expiry_years)
    call_gamma = black_scholes_gamma(spot, strikes, time_arr, call_iv, risk_free_rate)
    put_gamma = black_scholes_gamma(spot, strikes, time_arr, put_iv, risk_free_rate)

    scale = spot**2 * CONTRACT_MULTIPLIER
    call_gex = call_oi * call_gamma * scale
    put_gex = put_oi * put_gamma * scale
    net_gex = call_gex - put_gex

    order = np.argsort(strikes)
    return [
        {
            "strike": float(strikes[i]),
            "call_gex": float(call_gex[i]),
            "put_gex": float(put_gex[i]),
            "net_gex": float(net_gex[i]),
        }
        for i in order
    ]


def find_gamma_flip_point(gex_by_strike: Sequence[dict]) -> float | None:
    """The strike where cumulative Net GEX crosses zero — the "Gamma 擠壓臨界點".

    Cumulative (not per-strike) sign change is the standard definition: sum
    Net GEX from the lowest strike upward and find where that running total
    flips sign. Below the flip, dealers are net short gamma (their hedging
    amplifies moves); above it, they're net long gamma (hedging dampens
    moves). Linearly interpolates between the two straddling strikes for a
    more precise level than "just pick the nearest strike".

    Returns None if there's no sign change in the profile (e.g. it's
    entirely one-sided, or there's fewer than 2 strikes).
    """
    if len(gex_by_strike) < 2:
        return None

    strikes = [row["strike"] for row in gex_by_strike]
    cumulative = np.cumsum([row["net_gex"] for row in gex_by_strike])

    for i in range(1, len(cumulative)):
        prev, curr = cumulative[i - 1], cumulative[i]
        if prev == 0:
            return float(strikes[i - 1])
        if (prev < 0) != (curr < 0):
            # Linear interpolation between strikes[i-1] and strikes[i].
            frac = -prev / (curr - prev)
            return float(strikes[i - 1] + frac * (strikes[i] - strikes[i - 1]))

    return None
