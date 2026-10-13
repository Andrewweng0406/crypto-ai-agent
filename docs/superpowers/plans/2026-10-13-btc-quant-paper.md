# BTC 量化紙上交易 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 production 以紙上交易執行 B 方案（現貨趨勢組合 + 4H 逐倉合約），並先降低舊系統的風險設定。

**Architecture:** 新增獨立套件 `btc_quant/`，各檔案職責如下：
- `signals.py`：純函式
- `paper.py`：紙上帳戶
- `store.py`：Postgres / 檔案儲存
- `runner.py`：async 迴圈
- `backtest.py`：與 runner 共用同一組函式

`main.py` 只做三件事：用環境變數啟動迴圈、加上任務標籤、提供唯讀 API。

**Tech Stack:** Python 3.12、pandas、numpy、ccxt（async，BingX）、psycopg、FastAPI、pytest

**Spec:** `docs/superpowers/specs/2026-10-12-btc-quant-paper-design.md`

## Global Constraints
- 交易標的：BingX `BTC/USDT:USDT`；所有時間一律用 UTC。
- 趨勢部位：12 訊號等權；波動目標 0.40；30 日波動；曝險上限 **0.90**；現貨成本每次調整 0.1%。
- 4H 部位：唐奇安 20；ATR14；停損 1.5 ATR；停利 2R；每筆風險 2%；交易所槓桿 `min(25, floor(1/(2*stop_pct+0.005)))`；維持保證金 0.005；同時最多 1 筆。
- 市況濾網：做多需 `ens >= 0.5`；做空需 `ens == 0`。ens 取訊號 K 棒所在日期的前一日。
- 合約手續費每邊 0.05%；資金費每 8 小時依實際費率計算，做多付正費率。
- 日線計算窗口固定為最近 400 根已收盤 K 棒（`DAILY_LOOKBACK = 400`），runner 和 backtest 一致。
- 環境變數：`BTC_QUANT_ENABLED`（預設 false）、`BTC_QUANT_PAPER_EQUITY`（預設 10000）。
- 本階段**不下真實訂單**。
- 既有失敗測試 `tests/test_options_strategy_endpoint.py::test_neutral_marks_iron_condor_as_recommended` 和本計畫無關，不處理。

## Review Focus
1. **未收盤的 K 棒**：交易所回傳的最後一根 K 棒還沒收盤，不能拿來判斷訊號。→ Task 2 的 `closed_candles_df` 測試。
2. **重啟或重新部署**：不能重複調倉，同一根 4H K 棒也不能被判斷兩次。→ Task 6 的 runner 測試。
3. **價格跳空穿過停損，甚至穿過強平價**：前者用較差的價格成交，後者只損失逐倉保證金，帳戶不能出現負的現金。→ Task 3 的測試。
4. **現貨買到 0.90 時仍要留下合約保證金**：持倉中調倉不能動用保證金。→ Task 3 的測試。
5. **行情過時**（交易所斷線、資料停更）：不開新倉，但已有的持倉照樣檢查停損。→ Task 6 的測試。

---

### Task 1: 降低舊系統風險

**Files:**
- Modify: `main.py:198-200`（`FIXED_RISK_PCT`、`MAX_LEVERAGE`）
- Modify: `main.py` 的 `start_background_tasks`（約 5817、5847、5854 行）
- Modify: `tests/test_leverage.py`
- Modify: `tests/test_worker_config.py`

**Interfaces:**
- Produces: `main.legacy_strategy_flags() -> dict[str, bool]`，key 為 `us_stock_orb`、`rsi2_meanrev`、`meme_trade`

- [ ] **Step 1: 寫失敗的測試**

在 `tests/test_worker_config.py` 結尾加入：

```python
def test_legacy_strategy_loops_disabled_by_default(monkeypatch):
    for name in ("US_STOCK_ORB_ENABLED", "RSI2_MEANREV_ENABLED", "MEME_TRADE_ENABLED"):
        monkeypatch.delenv(name, raising=False)
    assert main.legacy_strategy_flags() == {
        "us_stock_orb": False,
        "rsi2_meanrev": False,
        "meme_trade": False,
    }


def test_legacy_strategy_loops_can_be_reenabled(monkeypatch):
    monkeypatch.setenv("MEME_TRADE_ENABLED", "true")
    assert main.legacy_strategy_flags()["meme_trade"] is True
```

把 `tests/test_leverage.py` 前兩個測試改成新的風險設定：

```python
def test_typical_stop_loss_distance():
    # FIXED_RISK_PCT=1：止損距離0.5% -> floor(1/0.5)=2倍
    assert calculate_leverage(0.5) == 2


def test_wider_stop_loss_gives_lower_leverage():
    # 止損距離4% -> floor(1/4)=0 -> 夾到 MIN_LEVERAGE=1
    assert calculate_leverage(4.0) == MIN_LEVERAGE


def test_risk_settings_are_conservative():
    assert FIXED_RISK_PCT == 1.0
    assert MAX_LEVERAGE == 5
```

- [ ] **Step 2: 執行，確認失敗**

Run: `./venv/bin/python -m pytest tests/test_worker_config.py tests/test_leverage.py -q`
Expected: FAIL（`legacy_strategy_flags` 不存在；風險設定仍是 15/20）

- [ ] **Step 3: 實作**

`main.py` 198–200 行改為：

```python
FIXED_RISK_PCT = 1.0         # 固定風險模型：單筆風險目標百分比（2026-10-13 由15%降為1%，見 docs/quant-review-2026-10-12.md）
MIN_LEVERAGE = 1
MAX_LEVERAGE = 5             # 2026-10-13 由20倍降為5倍，跟風險計算器預設一致
```

在 `background_job_lease_ttl` 定義之後加入：

```python
def legacy_strategy_flags() -> dict[str, bool]:
    """2026-10-13 檢討後預設關閉的舊策略；設環境變數為 true 可重新啟用。"""
    return {
        "us_stock_orb": _env_flag("US_STOCK_ORB_ENABLED", False),
        "rsi2_meanrev": _env_flag("RSI2_MEANREV_ENABLED", False),
        "meme_trade": _env_flag("MEME_TRADE_ENABLED", False),
    }
```

在 `start_background_tasks` 中，把 `us_stock_task`、`rsi2_meanrev_task`、`meme_trade_task` 三段各自包進對應旗標，例如：

```python
    flags = legacy_strategy_flags()
    if flags["us_stock_orb"]:
        us_stock_task = asyncio.create_task(us_stock_orb_loop())
        tasks.append(us_stock_task)
        logger.info(...)  # 原本的 log 不變
    else:
        logger.info("美股 ORB 已停用（US_STOCK_ORB_ENABLED=false）")
```

`rsi2_meanrev`（`RSI2_MEANREV_ENABLED`）和 `meme_trade`（`MEME_TRADE_ENABLED`）照同樣方式處理。

- [ ] **Step 4: 跑全部測試**

Run: `./venv/bin/python -m pytest -q`
Expected: 只剩既有的 options 失敗。如果有其他測試寫死 15% / 20 倍的數值，就改成依 `FIXED_RISK_PCT` / `MAX_LEVERAGE` 計算的期望值。

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_leverage.py tests/test_worker_config.py
git commit -m "Lower legacy signal risk and disable ORB/RSI2/meme loops by default"
```

---

### Task 2: `btc_quant/signals.py`

**Files:**
- Create: `btc_quant/__init__.py`（空檔）
- Create: `btc_quant/signals.py`
- Test: `tests/test_btc_quant_signals.py`

**Interfaces:**
- Produces:
  - 常數：`DAILY_LOOKBACK=400`、`FOUR_H_LOOKBACK=100`、`FOUR_H_MS=14_400_000`、`DAY_MS=86_400_000`、`TREND_MAX_EXPOSURE=0.90`、`TACTICAL_MAX_LEV=25`、`MAINT_MARGIN=0.005`
  - `closed_candles_df(rows: list[list], timeframe_ms: int, now_ms: int) -> pd.DataFrame`：index 為 UTC DatetimeIndex，欄位為 open/high/low/close/volume，只保留已收盤的 K 棒
  - `daily_ensemble(df_1d) -> pd.Series`
  - `trend_target_series(df_1d) -> pd.Series`
  - `target_as_of(df_1d, day: pd.Timestamp) -> float`：沒有 `day` 這根就回傳 nan
  - `ensemble_as_of(df_1d, day: pd.Timestamp) -> float`：同上
  - `prepare_4h(df_4h) -> pd.DataFrame`：新增 atr、up、dn 欄位
  - `signal_day_for_bar(bar_open: pd.Timestamp) -> pd.Timestamp`：回傳 bar 所在日期的前一天（00:00）
  - `tactical_signal(close, up, dn, ens) -> Optional[str]`：回傳 `"Long"`、`"Short"` 或 `None`
  - `@dataclass(frozen=True) TacticalOrder(side, entry, stop_loss, take_profit, liquidation, leverage, notional, margin, stop_pct)`
  - `size_position(side, entry, atr, equity) -> Optional[TacticalOrder]`

- [ ] **Step 1: 寫失敗的測試** `tests/test_btc_quant_signals.py`

```python
import math

import numpy as np
import pandas as pd
import pytest

from btc_quant import signals as s


def _daily(closes, start="2024-01-01"):
    idx = pd.date_range(start, periods=len(closes), freq="D", tz="UTC")
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({"open": c, "high": c * 1.001, "low": c * 0.999, "close": c, "volume": 1.0})


def test_closed_candles_df_drops_forming_bar():
    now = 3 * s.FOUR_H_MS + 1000  # 第4根(ts=3*4h)剛開始
    rows = [[i * s.FOUR_H_MS, 1, 2, 0.5, 1.5, 10] for i in range(4)]
    df = s.closed_candles_df(rows, s.FOUR_H_MS, now)
    assert len(df) == 3
    assert str(df.index.tz) == "UTC"
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_ensemble_is_one_in_steady_uptrend_and_zero_in_downtrend():
    up = _daily(np.linspace(100, 300, 400))
    down = _daily(np.linspace(300, 100, 400))
    assert s.daily_ensemble(up).iloc[-1] == 1.0
    assert s.daily_ensemble(down).iloc[-1] == 0.0


def test_ensemble_values_are_multiples_of_one_twelfth():
    rng = np.random.default_rng(1)
    df = _daily(100 * np.exp(np.cumsum(rng.normal(0, 0.03, 500))))
    ens = s.daily_ensemble(df)
    assert ((ens * 12).round(9) % 1 == 0).all()
    assert ens.between(0, 1).all()


def test_trend_target_capped_at_090():
    df = _daily(np.linspace(100, 101, 400))  # 極低波動 -> 0.4/vol 很大
    assert s.trend_target_series(df).iloc[-1] == pytest.approx(s.TREND_MAX_EXPOSURE)


def test_target_as_of_uses_window_and_missing_day_is_nan():
    df = _daily(np.linspace(100, 300, 600))
    day = df.index[500]
    expected = s.trend_target_series(df.loc[:day].tail(s.DAILY_LOOKBACK)).iloc[-1]
    assert s.target_as_of(df, day) == pytest.approx(expected)
    assert math.isnan(s.target_as_of(df, df.index[-1] + pd.Timedelta(days=5)))


def test_signal_day_for_bar_is_previous_day():
    bar = pd.Timestamp("2026-10-13 00:00", tz="UTC")
    assert s.signal_day_for_bar(bar) == pd.Timestamp("2026-10-12", tz="UTC")
    bar2 = pd.Timestamp("2026-10-13 20:00", tz="UTC")
    assert s.signal_day_for_bar(bar2) == pd.Timestamp("2026-10-12", tz="UTC")


def test_tactical_signal_rules():
    assert s.tactical_signal(105, 104, 90, 0.5) == "Long"
    assert s.tactical_signal(105, 104, 90, 5 / 12) is None
    assert s.tactical_signal(89, 104, 90, 0.0) == "Short"
    assert s.tactical_signal(89, 104, 90, 1 / 12) is None
    assert s.tactical_signal(100, float("nan"), 90, 1.0) is None


def test_size_position_long():
    o = s.size_position("Long", entry=100.0, atr=1.0, equity=10_000.0)
    assert o.stop_pct == pytest.approx(0.015)
    assert math.floor(1 / (2 * 0.015 + 0.005)) == 28
    assert o.leverage == 25  # 被上限夾住
    assert o.notional == pytest.approx(10_000 * 0.02 / 0.015)
    assert o.margin == pytest.approx(o.notional / 25)
    assert o.stop_loss == pytest.approx(98.5)
    assert o.take_profit == pytest.approx(103.0)
    assert (o.entry - o.liquidation) / o.entry >= 2 * o.stop_pct


def test_size_position_short_and_liquidation_distance():
    o = s.size_position("Short", entry=100.0, atr=3.0, equity=10_000.0)
    assert o.stop_loss == pytest.approx(104.5)
    assert o.take_profit == pytest.approx(91.0)
    assert o.leverage == math.floor(1 / (2 * 0.045 + 0.005))
    assert (o.liquidation - o.entry) / o.entry >= 2 * o.stop_pct


def test_size_position_rejects_bad_input():
    assert s.size_position("Long", 100.0, 0.0, 10_000) is None
    assert s.size_position("Long", 100.0, 40.0, 10_000) is None  # stop 60% -> lev<1
    assert s.size_position("Sideways", 100.0, 1.0, 10_000) is None


def test_prepare_4h_columns():
    idx = pd.date_range("2026-01-01", periods=30, freq="4h", tz="UTC")
    c = pd.Series(np.arange(30, dtype=float) + 100, index=idx)
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 1.0})
    p = s.prepare_4h(df)
    assert p["atr"].iloc[-1] == pytest.approx(2.0)
    assert p["up"].iloc[-1] == pytest.approx(c.iloc[-21:-1].max() + 1)
```

- [ ] **Step 2: 執行，確認失敗**

Run: `./venv/bin/python -m pytest tests/test_btc_quant_signals.py -q`
Expected: FAIL（`ModuleNotFoundError: btc_quant`）

- [ ] **Step 3: 實作** `btc_quant/__init__.py`（空檔）以及 `btc_quant/signals.py`：

```python
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
    close = df_1d["close"]
    parts = [_donchian_state(df_1d, n, m) for n, m in DONCHIAN_PAIRS]
    parts += [(close / close.shift(lb) - 1 > 0).astype(float) for lb in TSMOM_LOOKBACKS]
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
```

- [ ] **Step 4: 執行，確認通過**

Run: `./venv/bin/python -m pytest tests/test_btc_quant_signals.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add btc_quant/__init__.py btc_quant/signals.py tests/test_btc_quant_signals.py
git commit -m "Add BTC quant signal functions"
```

---

### Task 3: `btc_quant/paper.py`

**Files:**
- Create: `btc_quant/paper.py`
- Test: `tests/test_btc_quant_paper.py`

**Interfaces:**
- Consumes: `signals.TacticalOrder`
- Produces: `PaperAccount`（dataclass）
  - 方法：`new(equity)`、`equity(price)`、`unrealized(price)`、`reserved_margin()`、`mark(price)`、`drawdown_pct(price)`、`rebalance(target, price, ts) -> Optional[dict]`、`open(order, ts) -> dict`、`on_price(price, ts) -> Optional[dict]`、`accrue_funding(rate, ts) -> Optional[dict]`、`to_dict()`、`from_dict(d)`
  - 欄位：`last_daily_date: Optional[str]`、`last_4h_bar_ts: Optional[int]`、`last_funding_ts: Optional[int]`、`dd_alerted: bool`
  - 事件 dict 一律包含 `kind` 和 `ts`

- [ ] **Step 1: 寫失敗的測試** `tests/test_btc_quant_paper.py`

```python
import pytest

from btc_quant.paper import FUTURES_FEE_PCT, SPOT_COST_PCT, PaperAccount
from btc_quant.signals import size_position

TS = "2026-10-13T00:00:00+00:00"


def _long(acc, entry=100.0, atr=1.0):
    order = size_position("Long", entry, atr, acc.equity(entry))
    acc.open(order, TS)
    return order


def test_rebalance_buys_to_target_with_cost():
    acc = PaperAccount.new(10_000)
    ev = acc.rebalance(0.5, 100.0, TS)
    assert ev["kind"] == "rebalance"
    assert acc.btc_qty == pytest.approx(50.0)
    assert acc.cash == pytest.approx(10_000 - 5_000 - 5_000 * SPOT_COST_PCT)


def test_rebalance_keeps_margin_reserved():
    acc = PaperAccount.new(10_000)
    order = _long(acc)
    acc.rebalance(1.0, 100.0, TS)
    assert acc.cash >= order.margin - 1e-9


def test_rebalance_ignores_tiny_change():
    acc = PaperAccount.new(10_000)
    acc.rebalance(0.5, 100.0, TS)
    assert acc.rebalance(0.5, 100.0, TS) is None


def test_stop_fills_at_stop_when_price_touches():
    acc = PaperAccount.new(10_000)
    o = _long(acc)
    ev = acc.on_price(o.stop_loss, TS)
    assert ev["reason"] == "STOP"
    assert ev["exit"] == pytest.approx(o.stop_loss)
    assert acc.position is None
    assert ev["r_multiple"] == pytest.approx(-1.0, abs=0.1)


def test_gap_through_stop_fills_at_worse_price():
    acc = PaperAccount.new(10_000)
    o = _long(acc)
    gap = (o.stop_loss + o.liquidation) / 2
    ev = acc.on_price(gap, TS)
    assert ev["reason"] == "STOP"
    assert ev["exit"] == pytest.approx(gap)


def test_gap_through_liquidation_loses_only_margin():
    acc = PaperAccount.new(10_000)
    o = _long(acc)
    cash_before = acc.cash
    ev = acc.on_price(o.liquidation * 0.5, TS)
    assert ev["reason"] == "LIQUIDATION"
    assert acc.cash == pytest.approx(cash_before - o.margin)
    assert acc.cash > 0


def test_take_profit_and_short_side():
    acc = PaperAccount.new(10_000)
    o = size_position("Short", 100.0, 1.0, 10_000)
    acc.open(o, TS)
    assert acc.on_price(99.0, TS) is None
    ev = acc.on_price(o.take_profit, TS)
    assert ev["reason"] == "TAKE_PROFIT"
    assert ev["pnl"] > 0


def test_funding_direction():
    acc = PaperAccount.new(10_000)
    o = _long(acc)
    cash = acc.cash
    acc.accrue_funding(0.0001, TS)
    assert acc.cash == pytest.approx(cash - o.notional * 0.0001)
    acc2 = PaperAccount.new(10_000)
    o2 = size_position("Short", 100.0, 1.0, 10_000)
    acc2.open(o2, TS)
    cash2 = acc2.cash
    acc2.accrue_funding(0.0001, TS)
    assert acc2.cash == pytest.approx(cash2 + o2.notional * 0.0001)
    assert PaperAccount.new(1).accrue_funding(0.01, TS) is None


def test_open_charges_fee_and_rejects_second_position():
    acc = PaperAccount.new(10_000)
    o = _long(acc)
    assert acc.cash == pytest.approx(10_000 - o.notional * FUTURES_FEE_PCT)
    with pytest.raises(RuntimeError):
        acc.open(o, TS)


def test_roundtrip_serialization():
    acc = PaperAccount.new(10_000)
    _long(acc)
    acc.rebalance(0.3, 100.0, TS)
    acc.last_daily_date = "2026-10-13"
    clone = PaperAccount.from_dict(acc.to_dict())
    assert clone == acc


def test_drawdown_tracks_peak():
    acc = PaperAccount.new(10_000)
    acc.rebalance(0.9, 100.0, TS)
    acc.mark(110.0)
    assert acc.drawdown_pct(110.0) == pytest.approx(0.0)
    assert acc.drawdown_pct(90.0) < 0
```

- [ ] **Step 2: 執行，確認失敗**

Run: `./venv/bin/python -m pytest tests/test_btc_quant_paper.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 實作** `btc_quant/paper.py`

```python
"""BTC 量化紙上帳戶：現貨趨勢部位 + 單一逐倉合約部位，共用同一筆本金。

保證金不從現金扣出，只在調倉時保留（reserved_margin），
所以 equity = 現金 + 現貨市值 + 合約未實現損益。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

from btc_quant.signals import TacticalOrder

SPOT_COST_PCT = 0.001      # 現貨調整：手續費+滑價
FUTURES_FEE_PCT = 0.0005   # 合約每邊手續費
MIN_REBALANCE_USDT = 1.0


@dataclass
class PaperAccount:
    start_equity: float
    cash: float
    btc_qty: float = 0.0
    position: Optional[dict] = None
    peak_equity: float = 0.0
    last_price: float = 0.0
    last_daily_date: Optional[str] = None
    last_4h_bar_ts: Optional[int] = None
    last_funding_ts: Optional[int] = None
    dd_alerted: bool = False

    @classmethod
    def new(cls, equity: float) -> "PaperAccount":
        return cls(start_equity=equity, cash=equity, peak_equity=equity)

    def unrealized(self, price: float) -> float:
        p = self.position
        if not p:
            return 0.0
        sign = 1 if p["side"] == "Long" else -1
        return sign * p["notional"] * (price - p["entry"]) / p["entry"]

    def equity(self, price: float) -> float:
        return self.cash + self.btc_qty * price + self.unrealized(price)

    def reserved_margin(self) -> float:
        return self.position["margin"] if self.position else 0.0

    def mark(self, price: float) -> None:
        self.last_price = price
        self.peak_equity = max(self.peak_equity, self.equity(price))

    def drawdown_pct(self, price: float) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return (self.equity(price) / self.peak_equity - 1) * 100

    def rebalance(self, target: float, price: float, ts: str) -> Optional[dict]:
        eq = self.equity(price)
        delta_qty = max(0.0, target) * eq / price - self.btc_qty
        if delta_qty > 0:
            spendable = max(0.0, self.cash - self.reserved_margin())
            delta_qty = min(delta_qty, spendable / (price * (1 + SPOT_COST_PCT)))
        traded = abs(delta_qty) * price
        if traded < MIN_REBALANCE_USDT:
            self.mark(price)
            return None
        cost = traded * SPOT_COST_PCT
        self.cash -= delta_qty * price + cost
        self.btc_qty += delta_qty
        self.mark(price)
        return {
            "kind": "rebalance", "ts": ts, "target": target, "price": price,
            "delta_qty": delta_qty, "btc_qty": self.btc_qty, "cost": cost, "equity": self.equity(price),
        }

    def open(self, order: TacticalOrder, ts: str) -> dict:
        if self.position:
            raise RuntimeError("already holding a tactical position")
        fee = order.notional * FUTURES_FEE_PCT
        risk_amount = order.notional * order.stop_pct  # = 進場時權益的 2%
        self.cash -= fee
        self.position = {
            **asdict(order),
            "opened_at": ts,
            "open_fee": fee,
            "funding_paid": 0.0,
            "risk_amount": risk_amount,
        }
        self.mark(order.entry)
        return {"kind": "open", "ts": ts, **self.position, "equity": self.equity(order.entry)}

    def on_price(self, price: float, ts: str) -> Optional[dict]:
        p = self.position
        if p:
            long = p["side"] == "Long"
            hit_stop = price <= p["stop_loss"] if long else price >= p["stop_loss"]
            hit_tp = price >= p["take_profit"] if long else price <= p["take_profit"]
            if hit_stop:
                beyond_liq = price <= p["liquidation"] if long else price >= p["liquidation"]
                if beyond_liq:
                    return self._close(None, "LIQUIDATION", price, ts)
                fill = min(price, p["stop_loss"]) if long else max(price, p["stop_loss"])
                return self._close(fill, "STOP", price, ts)
            if hit_tp:
                return self._close(p["take_profit"], "TAKE_PROFIT", price, ts)
        self.mark(price)
        return None

    def _close(self, fill: Optional[float], reason: str, price: float, ts: str) -> dict:
        p = self.position
        sign = 1 if p["side"] == "Long" else -1
        if fill is None:  # 逐倉：跳空穿過強平價只損失該筆保證金
            pnl = -p["margin"]
            exit_price = p["liquidation"]
        else:
            pnl = sign * p["notional"] * (fill - p["entry"]) / p["entry"] - p["notional"] * FUTURES_FEE_PCT
            exit_price = fill
        self.cash += pnl
        net = pnl - p["open_fee"] - p["funding_paid"]
        self.position = None
        self.mark(price)
        return {
            "kind": "close", "ts": ts, "reason": reason, "side": p["side"], "entry": p["entry"],
            "exit": exit_price, "pnl": pnl, "net_pnl": net, "r_multiple": net / p["risk_amount"],
            "opened_at": p["opened_at"], "equity": self.equity(price),
        }

    def accrue_funding(self, rate: float, ts: str) -> Optional[dict]:
        p = self.position
        if not p:
            return None
        sign = 1 if p["side"] == "Long" else -1
        amount = sign * p["notional"] * rate  # 正值=付出
        self.cash -= amount
        p["funding_paid"] += amount
        return {"kind": "funding", "ts": ts, "rate": rate, "amount": amount}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PaperAccount":
        return cls(**data)
```

說明：`risk_amount` 等於 `notional × stop_pct`，也就是進場時帳戶權益的 2%。

- [ ] **Step 4: 執行，確認通過**

Run: `./venv/bin/python -m pytest tests/test_btc_quant_paper.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add btc_quant/paper.py tests/test_btc_quant_paper.py
git commit -m "Add BTC quant paper account"
```

---

### Task 4: `btc_quant/backtest.py`

**Files:**
- Create: `btc_quant/backtest.py`
- Test: `tests/test_btc_quant_backtest.py`

**Interfaces:**
- Consumes: Task 2 和 Task 3 的所有函式
- Produces:
  - `run_backtest(df_1d, df_4h, start_equity=10_000.0, funding: Optional[pd.Series]=None, start: Optional[pd.Timestamp]=None) -> tuple[PaperAccount, list[dict]]`
  - `bar_price_path(open_, high, low, side: Optional[str]) -> list[float]`
  - `class DailyCache`：`target(day)`、`ens(day)`，用來快取同一天的計算結果

- [ ] **Step 1: 寫失敗的測試** `tests/test_btc_quant_backtest.py`

```python
import numpy as np
import pandas as pd

from btc_quant.backtest import bar_price_path, run_backtest


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


def test_price_path_checks_adverse_extreme_first():
    assert bar_price_path(10, 12, 8, "Long") == [10, 8, 12]
    assert bar_price_path(10, 12, 8, "Short") == [10, 12, 8]
    assert bar_price_path(10, 12, 8, None) == [10, 12, 8]


def test_backtest_runs_and_keeps_invariants():
    df1, df4 = _synthetic()
    acc, events = run_backtest(df1, df4, start=df4.index[400 * 6])
    kinds = {e["kind"] for e in events}
    assert "rebalance" in kinds
    opens = [e for e in events if e["kind"] == "open"]
    closes = [e for e in events if e["kind"] == "close"]
    assert len(closes) in (len(opens), len(opens) - 1)
    assert all(e["leverage"] <= 25 for e in opens)
    assert acc.btc_qty * df4["close"].iloc[-1] <= 0.90 * acc.equity(df4["close"].iloc[-1]) * 1.2
    assert acc.equity(df4["close"].iloc[-1]) > 0


def test_backtest_rebalances_at_most_once_per_day():
    df1, df4 = _synthetic()
    _, events = run_backtest(df1, df4, start=df4.index[400 * 6])
    days = [e["ts"][:10] for e in events if e["kind"] == "rebalance"]
    assert len(days) == len(set(days))
```

- [ ] **Step 2: 執行，確認失敗**

Run: `./venv/bin/python -m pytest tests/test_btc_quant_backtest.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 實作** `btc_quant/backtest.py`

```python
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

        emit(acc.on_price(bar.open, ts))

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
                order = size_position(side, bar.open, prev.atr, acc.equity(bar.open))
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
```

- [ ] **Step 4: 執行，確認通過**

Run: `./venv/bin/python -m pytest tests/test_btc_quant_backtest.py -q`
Expected: PASS

- [ ] **Step 5: 用真實資料試跑**

Run: `./venv/bin/python -m btc_quant.backtest --days 365`
Expected: 印出 summary，`liquidations` 很少，`final_equity > 0`。把數字記到 commit 訊息中。

- [ ] **Step 6: Commit**

```bash
git add btc_quant/backtest.py tests/test_btc_quant_backtest.py
git commit -m "Add BTC quant backtest sharing live signal code"
```

---

### Task 5: 儲存層（Postgres migration 3 + `btc_quant/store.py`）

**Files:**
- Modify: `database.py`（在 `MIGRATIONS` 加入第 3 版；新增 4 個函式）
- Create: `btc_quant/store.py`
- Test: `tests/test_database.py`（新增）、`tests/test_btc_quant_store.py`

**Interfaces:**
- Produces:
  - `database.load_btc_quant_state(state_id: str) -> Optional[dict]`
  - `database.save_btc_quant_state(state_id: str, state: dict) -> None`
  - `database.insert_btc_quant_event(kind: str, payload: dict) -> None`
  - `database.list_btc_quant_events(limit: int = 50) -> Optional[list[dict]]`
  - `store.FileStore(state_path, events_path)` 和 `store.DbStore()`：都提供 `load() -> Optional[dict]`、`save(state)`、`append(event)`、`recent(limit=50) -> list[dict]`
  - `store.make_store()`：有 `DATABASE_URL` 時回傳 `DbStore`，否則回傳 `FileStore`

- [ ] **Step 1: 寫失敗的測試**

`tests/test_database.py` 結尾加入：

```python
def test_third_migration_declares_btc_quant_tables():
    version, sql = database.MIGRATIONS[2]
    assert version == 3
    assert "CREATE TABLE IF NOT EXISTS btc_quant_state" in sql
    assert "CREATE TABLE IF NOT EXISTS btc_quant_events" in sql


def test_btc_quant_db_functions_noop_without_url(monkeypatch):
    monkeypatch.setattr(database, "DATABASE_URL", None)
    assert database.load_btc_quant_state("default") is None
    database.save_btc_quant_state("default", {"cash": 1})
    database.insert_btc_quant_event("open", {"x": 1})
    assert database.list_btc_quant_events() is None
```

新增 `tests/test_btc_quant_store.py`：

```python
from btc_quant.store import FileStore


def test_file_store_roundtrip(tmp_path):
    st = FileStore(str(tmp_path / "state.json"), str(tmp_path / "events.jsonl"))
    assert st.load() is None
    st.save({"cash": 10.0})
    assert st.load() == {"cash": 10.0}
    for i in range(3):
        st.append({"kind": "open", "ts": f"t{i}"})
    recent = st.recent(2)
    assert [e["ts"] for e in recent] == ["t2", "t1"]
```

- [ ] **Step 2: 執行，確認失敗**

Run: `./venv/bin/python -m pytest tests/test_database.py tests/test_btc_quant_store.py -q`
Expected: FAIL

- [ ] **Step 3: 實作**

在 `database.py` 的 `MIGRATIONS` 加入第 3 版：

```python
    (
        3,
        """
        CREATE TABLE IF NOT EXISTS btc_quant_state (
            id TEXT PRIMARY KEY,
            state JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS btc_quant_events (
            id BIGSERIAL PRIMARY KEY,
            ts TIMESTAMPTZ NOT NULL DEFAULT now(),
            kind TEXT NOT NULL,
            payload JSONB NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_btc_quant_events_ts
            ON btc_quant_events (ts DESC);
        """,
    ),
```

在 `database.py` 檔尾加入：

```python
def load_btc_quant_state(state_id: str) -> Optional[dict]:
    if not DATABASE_URL:
        return None
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT state FROM btc_quant_state WHERE id = %s", (state_id,))
                row = cur.fetchone()
                return row[0] if row else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("讀取 btc_quant_state 失敗：%s", exc)
        return None


def save_btc_quant_state(state_id: str, state: dict) -> None:
    if not DATABASE_URL:
        return
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO btc_quant_state (id, state, updated_at)
                    VALUES (%s, %s::jsonb, now())
                    ON CONFLICT (id) DO UPDATE SET state = EXCLUDED.state, updated_at = now()
                    """,
                    (state_id, json.dumps(_jsonable(state))),
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("寫入 btc_quant_state 失敗：%s", exc)


def insert_btc_quant_event(kind: str, payload: dict) -> None:
    if not DATABASE_URL:
        return
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO btc_quant_events (kind, payload) VALUES (%s, %s::jsonb)",
                    (kind, json.dumps(_jsonable(payload))),
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("寫入 btc_quant_events 失敗：%s", exc)


def list_btc_quant_events(limit: int = 50) -> Optional[list[dict]]:
    if not DATABASE_URL:
        return None
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM btc_quant_events ORDER BY id DESC LIMIT %s", (limit,))
                return [row[0] for row in cur.fetchall()]
    except Exception as exc:  # noqa: BLE001
        logger.warning("讀取 btc_quant_events 失敗：%s", exc)
        return None
```

新增 `btc_quant/store.py`：

```python
"""BTC 量化狀態/事件的儲存：production 用 Postgres，本機沒有 DATABASE_URL 時用 logs/ 下的檔案。"""

from __future__ import annotations

import json
import os
from typing import Optional

import database

STATE_ID = "default"
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")


class FileStore:
    def __init__(self, state_path: str, events_path: str):
        self.state_path = state_path
        self.events_path = events_path

    def load(self) -> Optional[dict]:
        if not os.path.exists(self.state_path):
            return None
        with open(self.state_path, encoding="utf-8") as fh:
            return json.load(fh)

    def save(self, state: dict) -> None:
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)
        os.replace(tmp, self.state_path)

    def append(self, event: dict) -> None:
        os.makedirs(os.path.dirname(self.events_path), exist_ok=True)
        with open(self.events_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def recent(self, limit: int = 50) -> list[dict]:
        if not os.path.exists(self.events_path):
            return []
        with open(self.events_path, encoding="utf-8") as fh:
            lines = fh.readlines()[-limit:]
        return [json.loads(line) for line in reversed(lines)]


class DbStore:
    def load(self) -> Optional[dict]:
        return database.load_btc_quant_state(STATE_ID)

    def save(self, state: dict) -> None:
        database.save_btc_quant_state(STATE_ID, state)

    def append(self, event: dict) -> None:
        database.insert_btc_quant_event(event.get("kind", "unknown"), event)

    def recent(self, limit: int = 50) -> list[dict]:
        return database.list_btc_quant_events(limit) or []


def make_store():
    if database.is_database_enabled():
        return DbStore()
    return FileStore(os.path.join(_LOG_DIR, "btc_quant_state.json"), os.path.join(_LOG_DIR, "btc_quant_events.jsonl"))
```

- [ ] **Step 4: 執行，確認通過**

Run: `./venv/bin/python -m pytest tests/test_database.py tests/test_btc_quant_store.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add database.py btc_quant/store.py tests/test_database.py tests/test_btc_quant_store.py
git commit -m "Add BTC quant persistence (migration 3, file/db store)"
```

---

### Task 6: `btc_quant/runner.py`（含一致性測試）

**Files:**
- Create: `btc_quant/runner.py`
- Test: `tests/test_btc_quant_runner.py`

**Interfaces:**
- Consumes: Task 2–5
- Produces:
  - `class BtcQuantRunner(exchange, store, notify, now_ms: Callable[[], int], start_equity: float)`
    - `async tick() -> list[dict]`：回傳這次產生的事件
    - 屬性 `account: PaperAccount`
  - `async run_btc_quant_loop(notify, acquire_lease, interval_seconds=300) -> None`
  - 常數：`SYMBOL = "BTC/USDT:USDT"`、`STALE_AFTER_MS = 30*60*1000`、`DD_ALERT_PCT = -30.0`
  - exchange 需要提供的介面（ccxt async 相容）：`fetch_ticker(symbol)`、`fetch_ohlcv(symbol, timeframe, limit=)`、`fetch_funding_rate_history(symbol, limit=)`

- [ ] **Step 1: 寫失敗的測試** `tests/test_btc_quant_runner.py`

```python
import asyncio

import numpy as np
import pandas as pd
import pytest

from btc_quant.backtest import bar_price_path, run_backtest
from btc_quant.runner import BtcQuantRunner
from btc_quant.signals import FOUR_H_MS


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
            ex.now = t.value // 10**6 + k * 3_600_000
            ex.price = float(px)
            await runner.tick()


def test_parity_with_backtest_entries():
    df1, df4 = _synthetic()
    start_i = 420 * 6
    end_i = start_i + 60 * 6
    _, bt_events = run_backtest(df1, df4.iloc[: end_i], start=df4.index[start_i])
    ex = FakeExchange(df1, df4)
    runner, _ = _runner(ex)
    asyncio.run(_drive(runner, ex, df4, start_i, end_i))
    live = [e for e in runner.store.events if e["kind"] == "open"]
    bt = [e for e in bt_events if e["kind"] == "open"]
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
    r.account.peak_equity = r.account.equity(ex.price) * 2  # 人為製造 -50% 回撤
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
```

- [ ] **Step 2: 執行，確認失敗**

Run: `./venv/bin/python -m pytest tests/test_btc_quant_runner.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 實作** `btc_quant/runner.py`

```python
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

    async def _emit(self, events: list[dict], event: Optional[dict], message: Optional[str]) -> None:
        if not event:
            return
        events.append(event)
        await asyncio.to_thread(self.store.append, event)
        if message:
            await self.notify(message)

    async def _daily_df(self, now: int) -> pd.DataFrame:
        rows = await self.exchange.fetch_ohlcv(SYMBOL, "1d", limit=DAILY_LOOKBACK + 1)
        return closed_candles_df(rows, DAY_MS, now)

    async def tick(self) -> list[dict]:
        acc = self.account
        events: list[dict] = []
        now = self.now_ms()
        ts = _iso(now)
        price = float((await self.exchange.fetch_ticker(SYMBOL))["last"])

        # 1) 停損 / 停利 / 強平
        ev = acc.on_price(price, ts)
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
                    await self._emit(events, acc.accrue_funding(float(item["fundingRate"]), _iso(t)), None)
            acc.last_funding_ts = latest_settle

        # 3) 每日現貨調整（UTC 換日後第一次 tick）
        today = pd.Timestamp(now, unit="ms", tz="UTC").floor("D")
        df_1d: Optional[pd.DataFrame] = None
        if acc.last_daily_date != today.date().isoformat():
            df_1d = await self._daily_df(now)
            target = target_as_of(df_1d, today - pd.Timedelta(days=1))
            if not math.isnan(target):
                ev = acc.rebalance(target, price, ts)
                await self._emit(events, ev, ev and _rebalance_message(ev))
                acc.last_daily_date = today.date().isoformat()
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
                            await self._emit(events, ev, _open_message(ev))
                elif not fresh:
                    logger.warning("BTC 量化：4H K棒資料過時（最後收盤 %s），本輪不開新倉", _iso(last_ts + FOUR_H_MS))

        # 5) 回撤警告（每次跌破只發一次，回升後重置）
        dd = acc.drawdown_pct(price)
        if dd <= DD_ALERT_PCT and not acc.dd_alerted:
            acc.dd_alerted = True
            await self.notify(f"⚠️ <b>BTC 量化（紙上）回撤警告</b>\n目前回撤 {dd:.1f}%（回測最大回撤約 -44%，策略不會自動停止）")
        elif dd > DD_ALERT_PCT / 2 and acc.dd_alerted:
            acc.dd_alerted = False

        await asyncio.to_thread(self.store.save, acc.to_dict())
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
```

- [ ] **Step 4: 執行，確認通過**

Run: `./venv/bin/python -m pytest tests/test_btc_quant_runner.py -q`
Expected: PASS。如果一致性測試失敗，要找出 runner 和 backtest 處理順序的差異並修正，**不能放寬斷言**。

- [ ] **Step 5: Commit**

```bash
git add btc_quant/runner.py tests/test_btc_quant_runner.py
git commit -m "Add BTC quant paper runner with backtest parity test"
```

---

### Task 7: 整合到 `main.py`（啟動、任務標籤、API）

**Files:**
- Modify: `main.py`（`BACKGROUND_JOB_LABELS`、`start_background_tasks`、新增 endpoint）
- Test: `tests/test_btc_quant_endpoint.py`

**Interfaces:**
- Consumes: `btc_quant.runner.run_btc_quant_loop`、`btc_quant.store.make_store`、`PaperAccount`
- Produces: `GET /api/btc-quant/status`

- [ ] **Step 1: 寫失敗的測試** `tests/test_btc_quant_endpoint.py`

```python
from fastapi.testclient import TestClient

import main
from btc_quant.paper import PaperAccount

client = TestClient(main.app)


class _Store:
    def __init__(self, state, events):
        self._state, self._events = state, events

    def load(self):
        return self._state

    def recent(self, limit=50):
        return self._events[:limit]


def test_status_without_state(monkeypatch):
    monkeypatch.setattr(main, "make_btc_quant_store", lambda: _Store(None, []))
    r = client.get("/api/btc-quant/status")
    assert r.status_code == 200
    assert r.json()["initialized"] is False


def test_status_with_state(monkeypatch):
    acc = PaperAccount.new(10_000)
    acc.rebalance(0.5, 100.0, "t")
    acc.mark(110.0)
    monkeypatch.setattr(main, "make_btc_quant_store", lambda: _Store(acc.to_dict(), [{"kind": "rebalance"}]))
    body = client.get("/api/btc-quant/status").json()
    assert body["initialized"] is True
    assert body["equity"] > 10_000
    assert body["trend"]["btc_qty"] == acc.btc_qty
    assert body["tactical"] is None
    assert body["recent_events"] == [{"kind": "rebalance"}]
```

- [ ] **Step 2: 執行，確認失敗**

Run: `./venv/bin/python -m pytest tests/test_btc_quant_endpoint.py -q`
Expected: FAIL（404）

- [ ] **Step 3: 實作**

在 `main.py` 的 import 區加入：

```python
from btc_quant.paper import PaperAccount
from btc_quant.runner import run_btc_quant_loop
from btc_quant.store import make_store as make_btc_quant_store
```

`BACKGROUND_JOB_LABELS` 加入：`"btc_quant_loop": "BTC 量化（紙上）",`

在 `start_background_tasks` 的 `return tasks` 之前加入：

```python
    if _env_flag("BTC_QUANT_ENABLED", False):
        tasks.append(
            asyncio.create_task(
                run_btc_quant_loop(send_telegram_message, acquire_background_job_lease, _record_loop_outcome)
            )
        )
        logger.info("BTC 量化紙上交易迴圈已啟動（每 300 秒一次）")
```

在 `/api/history` 之前加入 endpoint：

```python
@app.get("/api/btc-quant/status")
async def get_btc_quant_status() -> dict:
    """BTC 量化 B 方案紙上帳戶狀態（唯讀）。"""
    store = make_btc_quant_store()
    saved = await asyncio.to_thread(store.load)
    events = await asyncio.to_thread(store.recent, 50)
    if not saved:
        return {"initialized": False, "enabled": _env_flag("BTC_QUANT_ENABLED", False), "recent_events": events}
    acc = PaperAccount.from_dict(saved)
    price = acc.last_price or 0.0
    equity = acc.equity(price) if price else acc.cash
    return {
        "initialized": True,
        "enabled": _env_flag("BTC_QUANT_ENABLED", False),
        "start_equity": acc.start_equity,
        "equity": equity,
        "return_pct": (equity / acc.start_equity - 1) * 100,
        "drawdown_pct": acc.drawdown_pct(price) if price else 0.0,
        "last_price": price,
        "trend": {"btc_qty": acc.btc_qty, "value": acc.btc_qty * price},
        "tactical": acc.position,
        "recent_events": events,
    }
```

- [ ] **Step 4: 跑全部測試**

Run: `./venv/bin/python -m pytest -q`
Expected: 只剩既有的 options 失敗。

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_btc_quant_endpoint.py
git commit -m "Wire BTC quant paper loop and status endpoint into main"
```

---

### Task 8: 驗證與部署準備

- [ ] **Step 1：** 跑 `./venv/bin/python -m btc_quant.backtest --days 365` 和 `--days 700`，把結果和研究報告比對（要考慮 0.90 上限和 BingX 資料的差異），寫進 `docs/btc-trend-research-2026-10-12.md` 的「附錄三」。
- [ ] **Step 2：** 本機實際跑一次 tick（不需要 DB）：

  `./venv/bin/python -c "import asyncio,time,ccxt.async_support as c;from btc_quant.runner import BtcQuantRunner;from btc_quant.store import FileStore
async def n(t):print(t)
async def m():
  ex=c.bingx();r=BtcQuantRunner(ex,FileStore('/tmp/bq/s.json','/tmp/bq/e.jsonl'),n,lambda:int(time.time()*1000),10000);print(await r.tick());await ex.close()
asyncio.run(m())"`

  Expected: 印出今天的調倉事件和每日摘要，沒有錯誤。
- [ ] **Step 3：** 由 reviewer 檢查整個分支。
- [ ] **Step 4：** 部署步驟（每一步都要**先經使用者同意**）：
  1. 合併到 main 並 push（Railway 會自動部署）
  2. 在 Railway `web` 設定 `BTC_QUANT_ENABLED=true`
  3. 確認收到第一則 Telegram，以及 `/api/btc-quant/status` 有回應
