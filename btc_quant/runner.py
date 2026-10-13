"""BTC 量化紙上交易的背景迴圈。每次 tick 的處理順序和 backtest.run_backtest 相同：
停損/停利檢查 -> 資金費 -> 每日現貨調整 -> 新4H K棒訊號。"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from typing import Awaitable, Callable, Optional

import pandas as pd

from btc_quant.paper import PaperAccount
from btc_quant.signals import (
    DAILY_LOOKBACK,
    DAY_MS,
    FOUR_H_LOOKBACK,
    FOUR_H_MS,
    closed_candles_df,
    ensemble_as_of,
    prepare_4h,
    signal_day_for_bar,
    size_position,
    tactical_signal,
    target_as_of,
)
from btc_quant.store import make_store

logger = logging.getLogger("trading_signal.btc_quant")

SYMBOL = "BTC/USDT:USDT"
STALE_AFTER_MS = 30 * 60 * 1000
DD_ALERT_PCT = -30.0
FUNDING_INTERVAL_MS = 8 * 3_600_000
GAP_AFTER_MS = 15 * 60 * 1000  # 距離上次報價超過這麼久，視為價格跳空（停損單可能無法在停損價成交）
JOB_NAME = "btc_quant_loop"

Notify = Callable[[str], Awaitable[None]]


def _iso(ms: int) -> str:
    return pd.Timestamp(ms, unit="ms", tz="UTC").isoformat()


class BtcQuantRunner:
    def __init__(self, exchange, store, notify: Notify, now_ms: Callable[[], int], start_equity: float):
        self.exchange = exchange
        self.store = store
        self.notify = notify
        self.now_ms = now_ms
        saved = store.load()
        self.account = PaperAccount.from_dict(saved) if saved else PaperAccount.new(start_equity)

    async def _save(self) -> None:
        await asyncio.to_thread(self.store.save, self.account.to_dict())

    async def _emit(self, events: list[dict], event: Optional[dict], message: Optional[str]) -> None:
        """帳戶一有變動就先存檔，再記錄事件、發通知：後面步驟失敗也不會遺失或重複這次變動。"""
        if not event:
            return
        await self._save()
        events.append(event)
        await asyncio.to_thread(self.store.append, event)
        if message:
            await self.notify(message)

    async def _daily_df(self, now: int) -> pd.DataFrame:
        rows = await self.exchange.fetch_ohlcv(SYMBOL, "1d", limit=DAILY_LOOKBACK + 1)
        return closed_candles_df(rows, DAY_MS, now)

    async def tick(self) -> list[dict]:
        saved = await asyncio.to_thread(self.store.load)  # 每次都重新載入：避免沿用其他 instance 已更新過的舊狀態
        if saved:
            self.account = PaperAccount.from_dict(saved)
        acc = self.account
        events: list[dict] = []
        now = self.now_ms()
        ts = _iso(now)
        price = float((await self.exchange.fetch_ticker(SYMBOL))["last"])

        # 1) 停損 / 停利 / 強平
        gap = acc.last_tick_ms is None or now - acc.last_tick_ms > GAP_AFTER_MS
        acc.last_tick_ms = now
        ev = acc.on_price(price, ts, gap=gap)
        await self._emit(events, ev, ev and _close_message(ev))

        # 2) 資金費（00/08/16 UTC 結算）
        latest_settle = now // FUNDING_INTERVAL_MS * FUNDING_INTERVAL_MS
        if acc.last_funding_ts is None:
            acc.last_funding_ts = latest_settle
        elif latest_settle > acc.last_funding_ts:
            history = await self.exchange.fetch_funding_rate_history(SYMBOL, limit=3)
            for item in history:
                t = int(item["timestamp"])
                if acc.last_funding_ts < t <= now:
                    ev = acc.accrue_funding(float(item["fundingRate"]), _iso(t))
                    acc.last_funding_ts = t
                    await self._emit(events, ev, None)
            acc.last_funding_ts = latest_settle

        # 3) 每日現貨調整（UTC 換日後第一次 tick）
        today = pd.Timestamp(now, unit="ms", tz="UTC").floor("D")
        df_1d: Optional[pd.DataFrame] = None
        if acc.last_daily_date != today.date().isoformat():
            df_1d = await self._daily_df(now)
            target = target_as_of(df_1d, today - pd.Timedelta(days=1))
            if not math.isnan(target):
                ev = acc.rebalance(target, price, ts)
                acc.last_daily_date = today.date().isoformat()
                await self._emit(events, ev, ev and _rebalance_message(ev))
                await self._save()
                await self.notify(_daily_summary(acc, price))

        # 4) 新收盤的4H K棒 -> 判斷訊號
        rows_4h = await self.exchange.fetch_ohlcv(SYMBOL, "4h", limit=FOUR_H_LOOKBACK)
        bars = prepare_4h(closed_candles_df(rows_4h, FOUR_H_MS, now))
        if not bars.empty:
            last = bars.iloc[-1]
            last_ts = int(bars.index[-1].value // 10**6)
            if acc.last_4h_bar_ts is None or last_ts > acc.last_4h_bar_ts:
                acc.last_4h_bar_ts = last_ts
                fresh = now - (last_ts + FOUR_H_MS) <= STALE_AFTER_MS
                if acc.position is None and fresh:
                    if df_1d is None:
                        df_1d = await self._daily_df(now)
                    ens = ensemble_as_of(df_1d, signal_day_for_bar(bars.index[-1]))
                    side = tactical_signal(last["close"], last["up"], last["dn"], ens)
                    if side:
                        order = size_position(side, price, last["atr"], acc.equity(price))
                        if order:
                            ev = acc.open(order, ts)
                            await self._emit(events, ev, ev and _open_message(ev))
                elif not fresh:
                    expected_close = now // FOUR_H_MS * FOUR_H_MS
                    if last_ts + FOUR_H_MS < expected_close:
                        logger.warning("BTC 量化：4H K棒資料過時（最後收盤 %s），本輪不開新倉", _iso(last_ts + FOUR_H_MS))
                    else:
                        logger.info("BTC 量化：K棒已收盤超過30分鐘（%s，可能剛啟動），不追進場", _iso(last_ts + FOUR_H_MS))

        # 5) 回撤警告（每次跌破只發一次，回升後重置）
        dd = acc.drawdown_pct(price)
        if dd <= DD_ALERT_PCT and not acc.dd_alerted:
            acc.dd_alerted = True
            await self.notify(f"⚠️ <b>BTC 量化（紙上）回撤警告</b>\n目前回撤 {dd:.1f}%（回測最大回撤約 -44%，策略不會自動停止）")
        elif dd > DD_ALERT_PCT / 2 and acc.dd_alerted:
            acc.dd_alerted = False

        await self._save()
        return events


def _open_message(ev: dict) -> str:
    side = "做多" if ev["side"] == "Long" else "做空"
    return (
        f"🟢 <b>BTC 量化（紙上）開倉：{side}</b>\n"
        f"進場 {ev['entry']:,.1f}\n停損 {ev['stop_loss']:,.1f}（{ev['stop_pct'] * 100:.2f}%）\n"
        f"停利 {ev['take_profit']:,.1f}\n交易所槓桿 {ev['leverage']} 倍（逐倉）\n"
        f"部位 {ev['notional']:,.0f} USDT／保證金 {ev['margin']:,.0f} USDT\n強平價 {ev['liquidation']:,.1f}"
    )


def _close_message(ev: dict) -> str:
    reason = {"STOP": "停損", "TAKE_PROFIT": "停利", "LIQUIDATION": "強平（只損失逐倉保證金）"}[ev["reason"]]
    return (
        f"🔴 <b>BTC 量化（紙上）平倉：{reason}</b>\n"
        f"進場 {ev['entry']:,.1f} → 出場 {ev['exit']:,.1f}\n"
        f"淨損益 {ev['net_pnl']:+,.2f} USDT（{ev['r_multiple']:+.2f}R）\n淨值 {ev['equity']:,.2f} USDT"
    )


def _rebalance_message(ev: dict) -> str:
    action = "買進" if ev["delta_qty"] > 0 else "賣出"
    return (
        f"📊 <b>BTC 量化（紙上）現貨調整</b>\n目標曝險 {ev['target'] * 100:.1f}%\n"
        f"{action} {abs(ev['delta_qty']):.5f} BTC @ {ev['price']:,.1f}\n持有 {ev['btc_qty']:.5f} BTC"
    )


def _daily_summary(acc: PaperAccount, price: float) -> str:
    eq = acc.equity(price)
    pos = acc.position
    pos_text = f"{'多' if pos['side'] == 'Long' else '空'}單 {pos['notional']:,.0f} USDT" if pos else "無"
    return (
        f"📅 <b>BTC 量化（紙上）每日摘要</b>\n淨值 {eq:,.2f} USDT（自起始 {(eq / acc.start_equity - 1) * 100:+.2f}%）\n"
        f"回撤 {acc.drawdown_pct(price):.1f}%\n現貨 {acc.btc_qty:.5f} BTC\n合約持倉 {pos_text}"
    )


async def run_btc_quant_loop(
    notify: Notify,
    acquire_lease: Callable[[str, int], Awaitable[bool]],
    record_outcome: Callable[[str, bool], Optional[str]],
    interval_seconds: int = 300,
) -> None:
    import ccxt.async_support as ccxt

    exchange = ccxt.bingx({"enableRateLimit": True})
    start_equity = float(os.environ.get("BTC_QUANT_PAPER_EQUITY", "10000"))
    runner: Optional[BtcQuantRunner] = None
    try:
        while True:
            try:
                if await acquire_lease(JOB_NAME, max(interval_seconds * 3, 120)):
                    if runner is None:
                        runner = BtcQuantRunner(
                            exchange, make_store(), notify, lambda: int(time.time() * 1000), start_equity
                        )
                    await runner.tick()
                alert = record_outcome(JOB_NAME, True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception("BTC 量化迴圈失敗：%s", exc)
                runner = None  # 下次重新從 store 載入，避免記憶體狀態和儲存不一致
                alert = record_outcome(JOB_NAME, False)
            if alert:
                await notify(alert)
            await asyncio.sleep(interval_seconds)
    finally:
        await exchange.close()
