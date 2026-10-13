import asyncio

import numpy as np
import pandas as pd
import pytest

from btc_quant.backtest import bar_price_path, run_backtest
from btc_quant.runner import BtcQuantRunner
from btc_quant.signals import FOUR_H_MS, size_position


class MemStore:
    def __init__(self):
        self.state = None
        self.events = []

    def load(self):
        return self.state

    def save(self, state):
        self.state = state

    def append(self, event):
        self.events.append(event)

    def recent(self, limit=50):
        return list(reversed(self.events))[:limit]


class FakeExchange:
    """依 self.now 逐步揭露歷史：只回傳 open_ts <= now 的K棒（含正在形成的那根）。"""

    def __init__(self, df1, df4):
        self.df1, self.df4 = df1, df4
        self.now = 0
        self.price = 0.0
        self.fail = False

    def _rows(self, df, limit):
        ms = df.index.asi8 // 10**6
        sel = df[ms <= self.now].tail(limit)
        return [[int(t.value // 10**6), r.open, r.high, r.low, r.close, r.volume] for t, r in zip(sel.index, sel.itertuples())]

    async def fetch_ticker(self, symbol):
        if self.fail:
            raise RuntimeError("down")
        return {"last": self.price}

    async def fetch_ohlcv(self, symbol, timeframe, limit=100):
        return self._rows(self.df1 if timeframe == "1d" else self.df4, limit)

    async def fetch_funding_rate_history(self, symbol, limit=3):
        return []


def _synthetic(days=520, seed=3):
    rng = np.random.default_rng(seed)
    idx4 = pd.date_range("2024-01-01", periods=days * 6, freq="4h", tz="UTC")
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, len(idx4))))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.006, len(idx4)))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.006, len(idx4)))
    df4 = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": 1.0}, index=idx4)
    df1 = df4.resample("D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return df1, df4


def _runner(ex, store=None):
    sent = []

    async def notify(text):
        sent.append(text)

    r = BtcQuantRunner(ex, store or MemStore(), notify, now_ms=lambda: ex.now, start_equity=10_000.0)
    return r, sent


async def _drive(runner, ex, df4, start_i, end_i):
    """在每根4H開盤時 tick 一次，再依不利/有利極值各 tick 一次（模擬盤中價格）。"""
    for i in range(start_i, end_i):
        t = df4.index[i]
        bar = df4.iloc[i]
        ex.now = t.value // 10**6
        ex.price = float(bar.open)
        await runner.tick()
        side = runner.account.position["side"] if runner.account.position else None
        for k, px in enumerate(bar_price_path(bar.open, bar.high, bar.low, side)[1:], start=1):
            ex.now = t.value // 10**6 + k * 300_000  # 每5分鐘一次輪詢：價格連續移動
            ex.price = float(px)
            await runner.tick()


def test_parity_with_backtest_entries():
    df1, df4 = _synthetic(seed=11)  # 這段合成行情有約30筆合約交易
    start_i = 420 * 6
    end_i = start_i + 90 * 6
    _, bt_events = run_backtest(df1, df4.iloc[: end_i], start=df4.index[start_i])
    ex = FakeExchange(df1, df4)
    runner, _ = _runner(ex)
    asyncio.run(_drive(runner, ex, df4, start_i, end_i))
    live = [e for e in runner.store.events if e["kind"] == "open"]
    bt = [e for e in bt_events if e["kind"] == "open"]
    assert len(bt) >= 5, "一致性測試需要足夠的交易才有意義"
    assert [(e["ts"], e["side"]) for e in live] == [(e["ts"], e["side"]) for e in bt]
    for a, b in zip(live, bt):
        assert a["notional"] == pytest.approx(b["notional"], rel=1e-6)
    live_rb = [e["ts"][:10] for e in runner.store.events if e["kind"] == "rebalance"]
    bt_rb = [e["ts"][:10] for e in bt_events if e["kind"] == "rebalance"]
    assert live_rb == bt_rb


def test_restart_does_not_repeat_daily_or_4h_processing():
    df1, df4 = _synthetic()
    i = 450 * 6
    ex = FakeExchange(df1, df4)
    store = MemStore()
    r1, _ = _runner(ex, store)
    ex.now = df4.index[i].value // 10**6
    ex.price = float(df4.iloc[i].open)
    asyncio.run(r1.tick())
    n = len(store.events)
    r2, _ = _runner(ex, store)  # 模擬重啟：從 store 載入狀態
    asyncio.run(r2.tick())
    assert [e for e in store.events[n:] if e["kind"] in ("rebalance", "open")] == []


def test_stale_data_blocks_new_entries_but_checks_stops(monkeypatch):
    df1, df4 = _synthetic()
    i = 450 * 6
    ex = FakeExchange(df1, df4)
    r, _ = _runner(ex)
    ex.now = df4.index[i].value // 10**6 + 2 * FOUR_H_MS  # K棒資料落後超過30分鐘
    ex.df4 = df4.iloc[: i + 1]
    ex.price = float(df4.iloc[i].open)
    import btc_quant.runner as runner_mod
    monkeypatch.setattr(runner_mod, "tactical_signal", lambda *a: "Long")
    asyncio.run(r.tick())
    assert r.account.position is None


def test_drawdown_alert_sent_once():
    df1, df4 = _synthetic()
    i = 450 * 6
    ex = FakeExchange(df1, df4)
    r, sent = _runner(ex)
    ex.now = df4.index[i].value // 10**6
    ex.price = float(df4.iloc[i].open)
    asyncio.run(r.tick())
    r.store.state["peak_equity"] = r.account.equity(ex.price) * 2  # 人為製造 -50% 回撤（tick 會從 store 重新載入）
    ex.now += 60_000
    asyncio.run(r.tick())
    ex.now += 60_000
    asyncio.run(r.tick())
    assert sum("回撤警告" in m for m in sent) == 1


def test_fetch_failure_raises_for_loop_accounting():
    df1, df4 = _synthetic()
    ex = FakeExchange(df1, df4)
    ex.fail = True
    r, _ = _runner(ex)
    with pytest.raises(RuntimeError):
        asyncio.run(r.tick())


def _with_position(minutes_later):
    df1, df4 = _synthetic()
    i = 450 * 6
    ex = FakeExchange(df1, df4)
    r, _ = _runner(ex)
    ex.now = df4.index[i].value // 10**6
    ex.price = float(df4.iloc[i].open)
    asyncio.run(r.tick())
    if r.account.position is None:
        r.account.open(size_position("Long", ex.price, ex.price * 0.01, r.account.equity(ex.price)), "t")
        r.store.save(r.account.to_dict())
    liq = r.account.position["liquidation"]
    ex.now += minutes_later * 60_000
    ex.price = liq * 0.9
    return r, ex


def test_continuous_ticks_fill_at_resting_stop():
    r, ex = _with_position(5)
    events = asyncio.run(r.tick())
    close = [e for e in events if e["kind"] == "close"][0]
    assert close["reason"] == "STOP"


def test_tick_after_outage_is_treated_as_gap():
    r, ex = _with_position(20)
    events = asyncio.run(r.tick())
    close = [e for e in events if e["kind"] == "close"][0]
    assert close["reason"] == "LIQUIDATION"


class FlakyOhlcvExchange(FakeExchange):
    def __init__(self, *a):
        super().__init__(*a)
        self.ohlcv_fail = False

    async def fetch_ohlcv(self, symbol, timeframe, limit=100):
        if self.ohlcv_fail:
            raise RuntimeError("ohlcv down")
        return await super().fetch_ohlcv(symbol, timeframe, limit)


def test_stop_is_kept_when_later_step_fails():
    df1, df4 = _synthetic()
    i = 450 * 6
    ex = FlakyOhlcvExchange(df1, df4)
    r, sent = _runner(ex)
    ex.now = df4.index[i].value // 10**6
    ex.price = float(df4.iloc[i].open)
    asyncio.run(r.tick())
    r.account.open(size_position("Long", ex.price, ex.price * 0.01, r.account.equity(ex.price)), "t")
    r.store.save(r.account.to_dict())
    stop = r.account.position["stop_loss"]
    ex.now = df4.index[i + 1].value // 10**6 + 60_000  # 新的4H K棒 -> 會去抓 OHLCV
    ex.price = stop * 0.999
    ex.ohlcv_fail = True
    with pytest.raises(RuntimeError):
        asyncio.run(r.tick())
    r, sent = _runner(ex, r.store)  # 背景迴圈出錯後會重建 runner、從 store 載入
    ex.ohlcv_fail = False
    ex.price = stop * 1.05  # 價格回升
    ex.now += 300_000
    asyncio.run(r.tick())
    closes = [e for e in r.store.events if e["kind"] == "close"]
    assert len(closes) == 1
    assert r.store.state["position"] is None


def test_tick_reloads_state_written_by_another_instance():
    df1, df4 = _synthetic()
    i = 450 * 6
    ex = FakeExchange(df1, df4)
    store = MemStore()
    a, _ = _runner(ex, store)
    b, _ = _runner(ex, store)
    ex.now = df4.index[i].value // 10**6
    ex.price = float(df4.iloc[i].open)
    asyncio.run(a.tick())  # A 做了當日調倉
    ex.now += 300_000
    asyncio.run(b.tick())  # B 接手：必須看到 A 的狀態，不能再調倉一次
    assert sum(1 for e in store.events if e["kind"] == "rebalance") == 1
