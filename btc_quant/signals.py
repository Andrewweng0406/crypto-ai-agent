"""BTC 量化 B 方案的訊號計算：純函式、不連網。

規則見 docs/superpowers/specs/2026-10-12-btc-quant-paper-design.md §2；
runner.py 與 backtest.py 共用這裡的函式，確保實盤和回測邏輯一致。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

DAY_MS = 86_400_000
FOUR_H_MS = 14_400_000
DAILY_LOOKBACK = 400
FOUR_H_LOOKBACK = 100

DONCHIAN_PAIRS = [(20, 10), (55, 20), (100, 50), (55, 10), (100, 20)]
TSMOM_LOOKBACKS = [30, 90, 180]
MA_LOOKBACKS = [50, 100, 200]
TREND_VOL_TARGET = 0.40
TREND_VOL_WINDOW = 30
TREND_MAX_EXPOSURE = 0.90  # 保留至少10% USDT給合約保證金

ATR_PERIOD = 14
BREAKOUT_LOOKBACK = 20
TACTICAL_STOP_ATR = 1.5
TACTICAL_RR = 2.0
TACTICAL_RISK_PCT = 0.02
TACTICAL_MAX_LEV = 25
MAINT_MARGIN = 0.005

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def closed_candles_df(rows: list[list], timeframe_ms: int, now_ms: int) -> pd.DataFrame:
    """ccxt OHLCV -> DataFrame，丟掉還沒收盤的K棒（open_ts + timeframe > now）。"""
    closed = [r for r in rows if int(r[0]) + timeframe_ms <= now_ms]
    df = pd.DataFrame(closed, columns=["ts", *OHLCV_COLUMNS])
    df.index = pd.to_datetime(df["ts"].astype("int64"), unit="ms", utc=True)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df[OHLCV_COLUMNS].astype(float)


def _donchian_state(df: pd.DataFrame, n: int, m: int) -> pd.Series:
    hi = df["high"].rolling(n).max().shift(1).values
    lo = df["low"].rolling(m).min().shift(1).values
    out = np.zeros(len(df))
    state = 0
    for i, close in enumerate(df["close"].values):
        if state == 0 and close > hi[i]:
            state = 1
        elif state == 1 and close < lo[i]:
            state = 0
        out[i] = state
    return pd.Series(out, index=df.index)


def daily_ensemble(df_1d: pd.DataFrame) -> pd.Series:
    """12訊號等權：5組唐奇安、3個動能、動能組合、3條均線（跟 docs/btc-trend-research-2026-10-12.md 一致）。"""
    close = df_1d["close"]
    parts = [_donchian_state(df_1d, n, m) for n, m in DONCHIAN_PAIRS]
    tsmom = [(close / close.shift(lb) - 1 > 0).astype(float) for lb in TSMOM_LOOKBACKS]
    parts += tsmom
    parts.append(sum(tsmom) / len(tsmom))  # 研究版本的第12個訊號：動能組合
    parts += [(close > close.rolling(lb).mean()).astype(float) for lb in MA_LOOKBACKS]
    return sum(parts) / len(parts)


def trend_target_series(df_1d: pd.DataFrame) -> pd.Series:
    vol = df_1d["close"].pct_change().rolling(TREND_VOL_WINDOW).std() * math.sqrt(365)
    target = daily_ensemble(df_1d) * TREND_VOL_TARGET / vol
    return target.clip(lower=0.0, upper=TREND_MAX_EXPOSURE).fillna(0.0)


def _window(df_1d: pd.DataFrame, day: pd.Timestamp) -> Optional[pd.DataFrame]:
    window = df_1d.loc[:day].tail(DAILY_LOOKBACK)
    if window.empty or window.index[-1] != day:
        return None
    return window


def target_as_of(df_1d: pd.DataFrame, day: pd.Timestamp) -> float:
    window = _window(df_1d, day)
    return float("nan") if window is None else float(trend_target_series(window).iloc[-1])


def ensemble_as_of(df_1d: pd.DataFrame, day: pd.Timestamp) -> float:
    window = _window(df_1d, day)
    return float("nan") if window is None else float(daily_ensemble(window).iloc[-1])


def signal_day_for_bar(bar_open: pd.Timestamp) -> pd.Timestamp:
    return bar_open.floor("D") - pd.Timedelta(days=1)


def prepare_4h(df_4h: pd.DataFrame) -> pd.DataFrame:
    df = df_4h.copy()
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    df["atr"] = tr.rolling(ATR_PERIOD).mean()
    df["up"] = df["high"].rolling(BREAKOUT_LOOKBACK).max().shift(1)
    df["dn"] = df["low"].rolling(BREAKOUT_LOOKBACK).min().shift(1)
    return df


def tactical_signal(close: float, up: float, dn: float, ens: float) -> Optional[str]:
    if any(pd.isna(v) for v in (close, up, dn, ens)):
        return None
    if close > up and ens >= 0.5:
        return "Long"
    if close < dn and ens == 0:
        return "Short"
    return None


@dataclass(frozen=True)
class TacticalOrder:
    side: str
    entry: float
    stop_loss: float
    take_profit: float
    liquidation: float
    leverage: int
    notional: float
    margin: float
    stop_pct: float


def size_position(side: str, entry: float, atr: float, equity: float) -> Optional[TacticalOrder]:
    """依每筆風險決定部位；交易所槓桿取讓強平距離 >= 2倍停損距離的最大值（上限25）。"""
    if side not in ("Long", "Short") or entry <= 0 or equity <= 0 or not atr or atr <= 0 or pd.isna(atr):
        return None
    stop_pct = TACTICAL_STOP_ATR * atr / entry
    leverage = min(TACTICAL_MAX_LEV, math.floor(1 / (2 * stop_pct + MAINT_MARGIN)))
    if leverage < 1:
        return None
    sign = 1 if side == "Long" else -1
    notional = equity * TACTICAL_RISK_PCT / stop_pct
    liq_distance = 1 / leverage - MAINT_MARGIN
    return TacticalOrder(
        side=side,
        entry=entry,
        stop_loss=entry * (1 - sign * stop_pct),
        take_profit=entry * (1 + sign * TACTICAL_RR * stop_pct),
        liquidation=entry * (1 - sign * liq_distance),
        leverage=leverage,
        notional=notional,
        margin=notional / leverage,
        stop_pct=stop_pct,
    )
