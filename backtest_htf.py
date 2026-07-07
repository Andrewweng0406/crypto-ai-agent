"""
大週期回測：把先前測過的四種策略（布林突破、布林均值回歸、ATR擠壓突破、
唐奇安+成交量）原封不動搬到 4 小時線、日線上重新驗證。

動機：15 分鐘線的問題是交易頻率太高，槓桿後的手續費把本來就很薄的優勢吃光，
且容易被高頻套利機器人洗掉。拉長週期後交易次數會大幅減少，手續費佔比降低，
理論上比較有機會抓到真正的趨勢/波動。

方法論跟先前一致：抓 2 年歷史資料，切成「近1年（樣本內）」與
「前1年（樣本外）」，一開始就要求兩段、三個標的都要扣費後為正才算數。

⚠️ 誠實聲明：
  - 大週期資料點數少很多（1年日線只有 365 根，4小時線約 2190 根），最低
    交易數門檻從 15 筆降到 8 筆，代表通過門檻的統計可信度本來就比 15 分鐘
    線的測試低，結果要更保守看待。
  - 不含聰明錢否決濾網，一樣是純技術面 + 手續費。

用法：
  python backtest_htf.py
"""

import asyncio

import pandas as pd

from backtest import SYMBOLS, fetch_full_history
from main import calculate_leverage, make_exchange

WINDOW_DAYS = 365
MIN_TRADES_PER_WINDOW = 8   # 大週期資料點少，門檻比 15 分鐘線測試（15筆）降低
FEE_PCT_PER_SIDE = 0.05
ATR_PERIOD = 14
MA_FAST, MA_SLOW = 50, 200


# ---------------------------------------------------------------------------
# 共用：ATR / 趨勢 / 模擬 / 統計（跟先前幾支回測腳本邏輯一致）
# ---------------------------------------------------------------------------

def compute_atr(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(ATR_PERIOD).mean()


def add_trend(df: pd.DataFrame) -> pd.DataFrame:
    df["ma_fast"] = df["close"].rolling(MA_FAST).mean()
    df["ma_slow"] = df["close"].rolling(MA_SLOW).mean()
    return df


def simulate(df: pd.DataFrame, atr_sl_mult: float, rr: float, start_idx: int) -> list[dict]:
    trades = []
    open_position = None

    for i in range(start_idx, len(df)):
        candle = df.iloc[i]

        if open_position is not None:
            side = open_position["side"]
            tp, sl = open_position["take_profit"], open_position["stop_loss"]
            hit_tp = candle["high"] >= tp if side == "Long" else candle["low"] <= tp
            hit_sl = candle["low"] <= sl if side == "Long" else candle["high"] >= sl

            if hit_tp or hit_sl:
                result = "LOSS" if hit_sl else "WIN"
                exit_price = sl if hit_sl else tp
                raw_pnl_pct = (exit_price - open_position["entry_price"]) / open_position["entry_price"] * 100
                if side == "Short":
                    raw_pnl_pct = -raw_pnl_pct
                pnl_pct = raw_pnl_pct * open_position["leverage"]
                fee_cost_pct = 2 * FEE_PCT_PER_SIDE * open_position["leverage"]
                trades.append({"result": result, "pnl_pct_after_fee": pnl_pct - fee_cost_pct})
                open_position = None
            continue

        if bool(candle["long_signal"]) or bool(candle["short_signal"]):
            side = "Long" if candle["long_signal"] else "Short"
            entry_price = float(candle["close"])
            atr = float(candle["atr"])
            sl_distance = atr * atr_sl_mult
            tp_distance = sl_distance * rr

            if side == "Long":
                stop_loss, take_profit = entry_price - sl_distance, entry_price + tp_distance
            else:
                stop_loss, take_profit = entry_price + sl_distance, entry_price - tp_distance

            stop_loss_pct = abs(entry_price - stop_loss) / entry_price * 100
            leverage = calculate_leverage(stop_loss_pct)
            open_position = {"side": side, "entry_price": entry_price, "take_profit": take_profit,
                              "stop_loss": stop_loss, "leverage": leverage}

    return trades


def summarize(trades: list[dict]) -> dict:
    if not trades:
        return {"count": 0, "win_rate": 0.0, "avg_pnl_after_fee": 0.0}
    wins = sum(1 for t in trades if t["result"] == "WIN")
    total = sum(t["pnl_pct_after_fee"] for t in trades)
    return {"count": len(trades), "win_rate": wins / len(trades) * 100, "avg_pnl_after_fee": total / len(trades)}


def passes_bar(result: dict) -> bool:
    for window in ("in_sample", "out_of_sample"):
        for symbol in SYMBOLS:
            s = result[window][symbol]
            if s["count"] < MIN_TRADES_PER_WINDOW or s["avg_pnl_after_fee"] <= 0:
                return False
    return True


def combo_score(result: dict) -> float:
    values = [result[w][s]["avg_pnl_after_fee"] for w in ("in_sample", "out_of_sample") for s in SYMBOLS]
    return sum(values) / len(values)


def print_result(label: str, params: dict, result: dict) -> None:
    print(f"\n[{label}] 組合：{params}")
    for window_label, key in (("樣本內(近1年)", "in_sample"), ("樣本外(前1年)", "out_of_sample")):
        line = f"  {window_label:<16}"
        for symbol in SYMBOLS:
            s = result[key][symbol]
            line += f"{symbol.split('/')[0]}:{s['win_rate']:.0f}%赢({s['count']}筆,期望值{s['avg_pnl_after_fee']:+.2f}%) "
        print(line)


# ---------------------------------------------------------------------------
# 四種策略的訊號邏輯
# ---------------------------------------------------------------------------

def signals_breakout(df, bb_period, bb_std_mult, trend_filter):
    df = df.copy()
    df["atr"] = compute_atr(df)
    df = add_trend(df)
    mid = df["close"].rolling(bb_period).mean()
    std = df["close"].rolling(bb_period).std()
    df["bb_upper"], df["bb_lower"] = mid + bb_std_mult * std, mid - bb_std_mult * std
    prev_close, prev_up, prev_lo = df["close"].shift(1), df["bb_upper"].shift(1), df["bb_lower"].shift(1)
    long_raw = (prev_close <= prev_up) & (df["close"] > df["bb_upper"])
    short_raw = (prev_close >= prev_lo) & (df["close"] < df["bb_lower"])
    if trend_filter == "trend_aligned":
        long_raw &= df["ma_fast"] > df["ma_slow"]
        short_raw &= df["ma_fast"] < df["ma_slow"]
    df["long_signal"], df["short_signal"] = long_raw, short_raw
    return df


def signals_mean_reversion(df, bb_period, bb_std_mult, trend_filter):
    df = df.copy()
    df["atr"] = compute_atr(df)
    df = add_trend(df)
    mid = df["close"].rolling(bb_period).mean()
    std = df["close"].rolling(bb_period).std()
    df["bb_upper"], df["bb_lower"] = mid + bb_std_mult * std, mid - bb_std_mult * std
    prev_close, prev_up, prev_lo = df["close"].shift(1), df["bb_upper"].shift(1), df["bb_lower"].shift(1)
    long_raw = (prev_close >= prev_lo) & (df["close"] < df["bb_lower"])   # 跌破下軌 -> 逆勢做多
    short_raw = (prev_close <= prev_up) & (df["close"] > df["bb_upper"])  # 衝破上軌 -> 逆勢做空
    if trend_filter == "counter_trend_block":
        long_raw &= ~(df["ma_fast"] < df["ma_slow"])
        short_raw &= ~(df["ma_fast"] > df["ma_slow"])
    df["long_signal"], df["short_signal"] = long_raw, short_raw
    return df


def signals_squeeze_breakout(df, bb_period, bb_std_mult, squeeze_percentile, atr_expand_mult, trend_filter):
    df = df.copy()
    df["atr"] = compute_atr(df)
    df = add_trend(df)
    mid = df["close"].rolling(bb_period).mean()
    std = df["close"].rolling(bb_period).std()
    df["bb_upper"], df["bb_lower"] = mid + bb_std_mult * std, mid - bb_std_mult * std
    bb_width = (df["bb_upper"] - df["bb_lower"]) / mid
    lookback = 60  # 樣本點少，擠壓判斷窗口跟著縮短（原15m版用100根）
    squeeze_threshold = bb_width.rolling(lookback).quantile(squeeze_percentile)
    was_squeezed = (bb_width <= squeeze_threshold).rolling(4).max().fillna(0).astype(bool).shift(1).fillna(False)
    prev_close, prev_up, prev_lo = df["close"].shift(1), df["bb_upper"].shift(1), df["bb_lower"].shift(1)
    long_break = (prev_close <= prev_up) & (df["close"] > df["bb_upper"])
    short_break = (prev_close >= prev_lo) & (df["close"] < df["bb_lower"])
    strong_candle = (df["high"] - df["low"]) >= df["atr"] * atr_expand_mult
    long_raw = long_break & was_squeezed & strong_candle
    short_raw = short_break & was_squeezed & strong_candle
    if trend_filter == "trend_aligned":
        long_raw &= df["ma_fast"] > df["ma_slow"]
        short_raw &= df["ma_fast"] < df["ma_slow"]
    df["long_signal"], df["short_signal"] = long_raw, short_raw
    return df


def signals_donchian_volume(df, donchian_period, volume_mult, trend_filter):
    df = df.copy()
    df["atr"] = compute_atr(df)
    df = add_trend(df)
    donchian_upper = df["high"].rolling(donchian_period).max().shift(1)
    donchian_lower = df["low"].rolling(donchian_period).min().shift(1)
    avg_volume = df["volume"].rolling(20).mean()
    long_raw = (df["close"] > donchian_upper) & (df["volume"] > avg_volume * volume_mult)
    short_raw = (df["close"] < donchian_lower) & (df["volume"] > avg_volume * volume_mult)
    if trend_filter == "trend_aligned":
        long_raw &= df["ma_fast"] > df["ma_slow"]
        short_raw &= df["ma_fast"] < df["ma_slow"]
    df["long_signal"], df["short_signal"] = long_raw, short_raw
    return df


# ---------------------------------------------------------------------------
# 網格與執行
# ---------------------------------------------------------------------------

async def load_windows(timeframe: str) -> dict:
    exchange = make_exchange("okx")
    await exchange.load_markets()
    data = {"in_sample": {}, "out_of_sample": {}}
    try:
        for symbol in SYMBOLS:
            data["in_sample"][symbol] = await fetch_full_history(exchange, symbol, WINDOW_DAYS, timeframe=timeframe)
            data["out_of_sample"][symbol] = await fetch_full_history(
                exchange, symbol, WINDOW_DAYS, offset_days=WINDOW_DAYS, timeframe=timeframe
            )
    finally:
        await exchange.close()
    return data


def evaluate(data: dict, signal_fn, start_idx: int, atr_sl_mult: float, rr: float) -> dict:
    result = {"in_sample": {}, "out_of_sample": {}}
    for window in ("in_sample", "out_of_sample"):
        for symbol, df in data[window].items():
            trades = simulate(signal_fn(df), atr_sl_mult, rr, start_idx)
            result[window][symbol] = summarize(trades)
    return result


def run_grid(label: str, data: dict, combos: list, build_signal_fn, start_idx_fn) -> list:
    print(f"\n{'#'*72}\n{label}：共 {len(combos)} 組參數\n{'#'*72}")
    passed, all_results = [], []
    for params in combos:
        result = evaluate(data, build_signal_fn(params), start_idx_fn(params), params["atr_sl_mult"], params["risk_reward_ratio"])
        score = combo_score(result)
        all_results.append((params, result, score))
        if passes_bar(result):
            passed.append((params, result, score))

    print(f"通過「樣本內+樣本外、三標的皆為正」門檻：{len(passed)} / {len(combos)}")
    if not passed:
        all_results.sort(key=lambda x: x[2], reverse=True)
        print("最高分前 3 組（雖未達標）：")
        for params, result, _ in all_results[:3]:
            print_result(label, params, result)
    else:
        passed.sort(key=lambda x: x[2], reverse=True)
        print("通過門檻的組合：")
        for params, result, _ in passed:
            print_result(label, params, result)
    return passed


async def main() -> None:
    for timeframe in ("4h", "1d"):
        print("\n" + "=" * 90)
        print(f"時間週期：{timeframe}（近{WINDOW_DAYS}天=樣本內，前{WINDOW_DAYS}天=樣本外）")
        print("=" * 90)

        data = await load_windows(timeframe)
        for symbol in SYMBOLS:
            print(f"  {symbol}: 樣本內 {len(data['in_sample'][symbol])} 根 / 樣本外 {len(data['out_of_sample'][symbol])} 根")

        # 策略一：布林突破
        breakout_combos = [
            {"bb_period": p, "bb_std_mult": s, "atr_sl_mult": a, "risk_reward_ratio": r, "trend_filter": t}
            for p in (20, 30) for s in (2.0, 2.5) for a in (1.5, 2.0) for r in (1.5, 2.0, 3.0)
            for t in ("none", "trend_aligned")
        ]
        run_grid(
            f"[{timeframe}] 布林突破", data, breakout_combos,
            lambda p: (lambda df: signals_breakout(df, p["bb_period"], p["bb_std_mult"], p["trend_filter"])),
            lambda p: max(MA_SLOW, p["bb_period"], ATR_PERIOD) + 5,
        )

        # 策略二：布林均值回歸
        mr_combos = [
            {"bb_period": p, "bb_std_mult": s, "atr_sl_mult": a, "risk_reward_ratio": r, "trend_filter": t}
            for p in (14, 20, 30) for s in (2.0, 2.5) for a in (1.0, 1.5) for r in (1.0, 1.5, 2.0)
            for t in ("none", "counter_trend_block")
        ]
        run_grid(
            f"[{timeframe}] 布林均值回歸", data, mr_combos,
            lambda p: (lambda df: signals_mean_reversion(df, p["bb_period"], p["bb_std_mult"], p["trend_filter"])),
            lambda p: max(MA_SLOW, p["bb_period"], ATR_PERIOD) + 5,
        )

        # 策略三：ATR擠壓突破
        squeeze_combos = [
            {"bb_period": p, "bb_std_mult": s, "squeeze_percentile": sq, "atr_expand_mult": e,
             "atr_sl_mult": a, "risk_reward_ratio": r, "trend_filter": t}
            for p in (20, 30) for s in (1.5, 2.0) for sq in (0.15, 0.25) for e in (1.0, 1.3)
            for a in (1.5, 2.0) for r in (2.0, 3.0) for t in ("none", "trend_aligned")
        ]
        run_grid(
            f"[{timeframe}] ATR擠壓突破", data, squeeze_combos,
            lambda p: (lambda df: signals_squeeze_breakout(
                df, p["bb_period"], p["bb_std_mult"], p["squeeze_percentile"], p["atr_expand_mult"], p["trend_filter"]
            )),
            lambda p: max(MA_SLOW, p["bb_period"], ATR_PERIOD, 60) + 5,
        )

        # 策略四：唐奇安+成交量
        donchian_combos = [
            {"donchian_period": p, "volume_mult": v, "atr_sl_mult": a, "risk_reward_ratio": r, "trend_filter": t}
            for p in (20, 50) for v in (1.3, 1.5, 2.0) for a in (1.5, 2.0) for r in (1.5, 2.0, 3.0)
            for t in ("none", "trend_aligned")
        ]
        run_grid(
            f"[{timeframe}] 唐奇安+成交量", data, donchian_combos,
            lambda p: (lambda df: signals_donchian_volume(df, p["donchian_period"], p["volume_mult"], p["trend_filter"])),
            lambda p: max(MA_SLOW, p["donchian_period"], ATR_PERIOD, 20) + 5,
        )


if __name__ == "__main__":
    asyncio.run(main())
