"""
新策略回測：測試兩種跟先前布林通道全然不同的進場邏輯。跟 backtest_mean_reversion.py
用同一套嚴謹方法——樣本內(近180天)與樣本外(180~360天前)、三個標的都要扣費後
為正才算數，一開始就雙重把關，不是搜出最佳解再回頭驗證。

策略一：ATR / 布林寬度擠壓突破 (Squeeze Breakout)
  概念：波動度縮到近期相對低點（盤整蓄勢）之後，才出現真正放量的長K棒突破，
  用來過濾掉「盤整期雜訊」造成的假突破——這是先前布林突破策略完全沒有的
  「規避盤整」機制。

策略二：唐奇安通道突破 + 成交量確認 (Donchian + Volume)
  概念：價格突破過去 N 根K棒的最高/最低點，且當根成交量明顯放大（高於近期
  均量），才視為有效突破，避免「無量假突破」——成交量確認是先前一直沒測過
  的過濾器。

用法：
  python backtest_new_strategies.py
"""

import asyncio

import pandas as pd

from backtest_mean_reversion import combo_score, load_windows, passes_bar, print_result
from backtest_optimize import ATR_PERIOD, simulate, summarize
from main import MA_FAST_PERIOD, MA_SLOW_PERIOD

MA_FAST, MA_SLOW = MA_FAST_PERIOD, MA_SLOW_PERIOD


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


def apply_trend_filter(df: pd.DataFrame, long_raw: pd.Series, short_raw: pd.Series, mode: str):
    if mode == "none":
        return long_raw, short_raw
    uptrend = df["ma_fast"] > df["ma_slow"]
    downtrend = df["ma_fast"] < df["ma_slow"]
    return long_raw & uptrend, short_raw & downtrend  # trend_aligned：只做順著主趨勢方向的突破


def compute_squeeze_breakout_signals(
    df: pd.DataFrame,
    bb_period: int,
    bb_std_mult: float,
    squeeze_percentile: float,
    atr_expand_mult: float,
    trend_filter: str,
) -> pd.DataFrame:
    df = df.copy()
    df["atr"] = compute_atr(df)
    df = add_trend(df)

    mid = df["close"].rolling(bb_period).mean()
    std = df["close"].rolling(bb_period).std()
    df["bb_upper"] = mid + bb_std_mult * std
    df["bb_lower"] = mid - bb_std_mult * std
    bb_width = (df["bb_upper"] - df["bb_lower"]) / mid

    bb_width_lookback = 100  # 固定不放進網格，避免組合數爆炸
    squeeze_threshold = bb_width.rolling(bb_width_lookback).quantile(squeeze_percentile)
    # 突破當下不用擠壓，而是「突破前最近幾根」曾經處於擠壓狀態
    was_squeezed_recently = (
        (bb_width <= squeeze_threshold).rolling(4).max().fillna(0).astype(bool).shift(1).fillna(False)
    )

    prev_close = df["close"].shift(1)
    prev_bb_upper = df["bb_upper"].shift(1)
    prev_bb_lower = df["bb_lower"].shift(1)

    long_breakout = (prev_close <= prev_bb_upper) & (df["close"] > df["bb_upper"])
    short_breakout = (prev_close >= prev_bb_lower) & (df["close"] < df["bb_lower"])

    strong_candle = (df["high"] - df["low"]) >= df["atr"] * atr_expand_mult  # 帶量的長K棒打破沉默

    long_raw = long_breakout & was_squeezed_recently & strong_candle
    short_raw = short_breakout & was_squeezed_recently & strong_candle

    df["long_signal"], df["short_signal"] = apply_trend_filter(df, long_raw, short_raw, trend_filter)
    return df


def compute_donchian_volume_signals(
    df: pd.DataFrame, donchian_period: int, volume_mult: float, trend_filter: str
) -> pd.DataFrame:
    df = df.copy()
    df["atr"] = compute_atr(df)
    df = add_trend(df)

    volume_lookback = 20  # 固定不放進網格
    donchian_upper = df["high"].rolling(donchian_period).max().shift(1)  # 不含當根，避免用到未來資訊
    donchian_lower = df["low"].rolling(donchian_period).min().shift(1)
    avg_volume = df["volume"].rolling(volume_lookback).mean()

    long_raw = (df["close"] > donchian_upper) & (df["volume"] > avg_volume * volume_mult)
    short_raw = (df["close"] < donchian_lower) & (df["volume"] > avg_volume * volume_mult)

    df["long_signal"], df["short_signal"] = apply_trend_filter(df, long_raw, short_raw, trend_filter)
    return df


def evaluate(data: dict, signal_fn, start_idx: int, atr_sl_mult: float, rr: float) -> dict:
    result = {"in_sample": {}, "out_of_sample": {}}
    for window in ("in_sample", "out_of_sample"):
        for symbol, df in data[window].items():
            signals_df = signal_fn(df)
            trades = simulate(signals_df, atr_sl_mult, rr, start_idx)
            result[window][symbol] = summarize(trades)
    return result


async def run_squeeze_breakout(data: dict) -> list:
    print("\n" + "#" * 72)
    print("策略一：ATR / 布林寬度擠壓突破 (Squeeze Breakout)")
    print("#" * 72)

    combos = [
        {
            "bb_period": bb_period,
            "bb_std_mult": bb_std_mult,
            "squeeze_percentile": sq,
            "atr_expand_mult": expand,
            "atr_sl_mult": atr_sl_mult,
            "risk_reward_ratio": rr,
            "trend_filter": trend,
        }
        for bb_period in (20, 30)
        for bb_std_mult in (1.5, 2.0)
        for sq in (0.15, 0.25)
        for expand in (1.0, 1.3)
        for atr_sl_mult in (1.5, 2.0)
        for rr in (1.5, 2.0, 3.0)
        for trend in ("none", "trend_aligned")
    ]
    print(f"共 {len(combos)} 組參數...")

    passed, all_results = [], []
    for params in combos:
        start_idx = max(MA_SLOW, params["bb_period"], ATR_PERIOD, 100) + 5

        def signal_fn(df, p=params):
            return compute_squeeze_breakout_signals(
                df, p["bb_period"], p["bb_std_mult"], p["squeeze_percentile"], p["atr_expand_mult"], p["trend_filter"]
            )

        result = evaluate(data, signal_fn, start_idx, params["atr_sl_mult"], params["risk_reward_ratio"])
        score = combo_score(result)
        all_results.append((params, result, score))
        if passes_bar(result):
            passed.append((params, result, score))

    report(combos, passed, all_results, "擠壓突破")
    return passed


async def run_donchian_volume(data: dict) -> list:
    print("\n" + "#" * 72)
    print("策略二：唐奇安通道突破 + 成交量確認 (Donchian + Volume)")
    print("#" * 72)

    combos = [
        {
            "donchian_period": period,
            "volume_mult": vol_mult,
            "atr_sl_mult": atr_sl_mult,
            "risk_reward_ratio": rr,
            "trend_filter": trend,
        }
        for period in (50, 100)
        for vol_mult in (1.3, 1.5, 2.0)
        for atr_sl_mult in (1.5, 2.0)
        for rr in (1.5, 2.0, 3.0)
        for trend in ("none", "trend_aligned")
    ]
    print(f"共 {len(combos)} 組參數...")

    passed, all_results = [], []
    for params in combos:
        start_idx = max(MA_SLOW, params["donchian_period"], ATR_PERIOD, 20) + 5

        def signal_fn(df, p=params):
            return compute_donchian_volume_signals(df, p["donchian_period"], p["volume_mult"], p["trend_filter"])

        result = evaluate(data, signal_fn, start_idx, params["atr_sl_mult"], params["risk_reward_ratio"])
        score = combo_score(result)
        all_results.append((params, result, score))
        if passes_bar(result):
            passed.append((params, result, score))

    report(combos, passed, all_results, "唐奇安+成交量")
    return passed


def report(combos: list, passed: list, all_results: list, label: str) -> None:
    print(f"通過「樣本內+樣本外、三標的皆為正」門檻的組合數：{len(passed)} / {len(combos)}")

    if not passed:
        all_results.sort(key=lambda x: x[2], reverse=True)
        print(f"\n沒有任何{label}參數組合能同時撐過樣本內與樣本外驗證。列出最高分的前 3 組（雖未達標）：")
        for params, result, score in all_results[:3]:
            print_result(params, result)
        return

    passed.sort(key=lambda x: x[2], reverse=True)
    print(f"\n以下為通過門檻的{label}組合（依平均期望值排序）：")
    for params, result, score in passed:
        print_result(params, result)


async def main() -> None:
    print("載入樣本內／樣本外歷史資料（優先讀取本地快取）...")
    data = await load_windows()

    squeeze_passed = await run_squeeze_breakout(data)
    donchian_passed = await run_donchian_volume(data)

    print("\n" + "=" * 72)
    print(f"總結：擠壓突破通過 {len(squeeze_passed)} 組，唐奇安+成交量通過 {len(donchian_passed)} 組")


if __name__ == "__main__":
    asyncio.run(main())
