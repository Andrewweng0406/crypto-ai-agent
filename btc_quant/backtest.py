"""用跟 runner 完全相同的 signals/paper 函式，對歷史K棒逐根模擬 B 方案。

每根4H K棒的處理順序（和 runner 在K棒開盤時的 tick 完全相同）：
  1) 用開盤價檢查停損/停利
  2) 00/08/16 點：計入資金費
  3) 00:00 那根：用前一日收盤的目標曝險，在開盤價調整現貨
  4) 沒有持倉：用上一根已收盤K棒判斷訊號，在開盤價進場
  5) 再依 不利極值 -> 有利極值 的順序檢查停損/停利（相當於 runner 盤中的 tick）
"""

from __future__ import annotations

import argparse
import math
from typing import Optional

import pandas as pd

from btc_quant.paper import PaperAccount
from btc_quant.signals import (
    ensemble_as_of,
    months_since_halving,
    prepare_4h,
    signal_day_for_bar,
    size_position,
    tactical_signal,
    target_as_of,
)

FUNDING_HOURS = (0, 8, 16)


class DailyCache:
    def __init__(self, df_1d: pd.DataFrame):
        self.df_1d = df_1d
        self._target: dict = {}
        self._ens: dict = {}

    def target(self, day: pd.Timestamp) -> float:
        if day not in self._target:
            self._target[day] = target_as_of(self.df_1d, day)
        return self._target[day]

    def ens(self, day: pd.Timestamp) -> float:
        if day not in self._ens:
            self._ens[day] = ensemble_as_of(self.df_1d, day)
        return self._ens[day]


def bar_price_path(open_: float, high: float, low: float, side: Optional[str]) -> list[float]:
    if side == "Long":
        return [open_, low, high]
    return [open_, high, low]


def run_backtest(
    df_1d: pd.DataFrame,
    df_4h: pd.DataFrame,
    start_equity: float = 10_000.0,
    funding: Optional[pd.Series] = None,
    start: Optional[pd.Timestamp] = None,
) -> tuple[PaperAccount, list[dict]]:
    cache = DailyCache(df_1d)
    bars = prepare_4h(df_4h)
    acc = PaperAccount.new(start_equity)
    events: list[dict] = []
    rows = list(bars.itertuples())
    for i in range(1, len(rows)):
        bar, prev = rows[i], rows[i - 1]
        t = bar.Index
        if start is not None and t < start:
            continue
        ts = t.isoformat()
        day = t.floor("D")

        def emit(ev):
            if ev:
                events.append(ev)
            return ev

        emit(acc.on_price(bar.open, ts, gap=True))  # 開盤相對上一根收盤可能跳空

        if funding is not None and t.hour in FUNDING_HOURS and t.minute == 0:
            rate = funding.get(t)
            if rate is not None and not pd.isna(rate):
                emit(acc.accrue_funding(float(rate), ts))

        if t == day:
            target = cache.target(day - pd.Timedelta(days=1))
            if not math.isnan(target):
                emit(acc.rebalance(target, bar.open, ts))

        if acc.position is None:
            side = tactical_signal(prev.close, prev.up, prev.dn, cache.ens(signal_day_for_bar(prev.Index)))
            if side:
                order = size_position(side, bar.open, prev.atr, acc.equity(bar.open), months_since_halving(t))
                if order:
                    emit(acc.open(order, ts))

        side = acc.position["side"] if acc.position else None
        for px in bar_price_path(bar.open, bar.high, bar.low, side)[1:]:
            if emit(acc.on_price(px, ts)):
                break

        acc.mark(bar.close)
    return acc, events


def summarize(acc: PaperAccount, events: list[dict], last_price: float, days: float) -> dict:
    closes = [e for e in events if e["kind"] == "close"]
    eq = acc.equity(last_price)
    years = max(days / 365, 1e-9)
    return {
        "final_equity": eq,
        "cagr_pct": ((eq / acc.start_equity) ** (1 / years) - 1) * 100,
        "trades": len(closes),
        "win_rate_pct": (sum(1 for e in closes if e["net_pnl"] > 0) / len(closes) * 100) if closes else 0.0,
        "avg_r": (sum(e["r_multiple"] for e in closes) / len(closes)) if closes else 0.0,
        "liquidations": sum(1 for e in closes if e["reason"] == "LIQUIDATION"),
    }


async def _fetch_bingx(days: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    import ccxt.async_support as ccxt

    from btc_quant.signals import DAY_MS, FOUR_H_MS, closed_candles_df

    ex = ccxt.bingx({"enableRateLimit": True})
    try:
        now = ex.milliseconds()
        out = {}
        for tf, ms in (("1d", DAY_MS), ("4h", FOUR_H_MS)):
            since = now - (days + 420) * DAY_MS
            rows: list = []
            while since < now:
                batch = await ex.fetch_ohlcv("BTC/USDT:USDT", tf, since=since, limit=1000)
                if not batch:
                    break
                rows += batch
                if batch[-1][0] <= since:
                    break
                since = batch[-1][0] + ms
            out[tf] = closed_candles_df(rows, ms, now)
        return out["1d"], out["4h"]
    finally:
        await ex.close()


def main() -> None:
    import asyncio

    parser = argparse.ArgumentParser(description="BTC 量化 B 方案回測（BingX 資料）")
    parser.add_argument("--days", type=int, default=365)
    args = parser.parse_args()
    df_1d, df_4h = asyncio.run(_fetch_bingx(args.days))
    start = df_4h.index[-1] - pd.Timedelta(days=args.days)
    acc, events = run_backtest(df_1d, df_4h, start=start)
    print(summarize(acc, events, float(df_4h["close"].iloc[-1]), args.days))


if __name__ == "__main__":
    main()
