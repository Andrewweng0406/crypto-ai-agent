"""
均值回歸策略回測：跟 main.py 現有的「突破策略」方向完全相反。

邏輯對調：
  突破策略：價格突破布林上軌 → 順著突破做多（追漲）；跌破下軌 → 做空（追跌）
  均值回歸：價格跌破布林下軌 → 逆勢做多，賭它會彈回均值；衝破上軌 → 逆勢做空

這支腳本重用 backtest_optimize.py 的 simulate() / summarize()（TP/SL、槓桿、
手續費模型完全一樣，只是換一組訊號判斷），並且直接把「樣本內（近180天）
與樣本外（180~360天前）都要賺錢」當作篩選門檻——不是像上次一樣搜出最佳解
再回頭驗證，而是一開始就要求兩段資料都撐得住，才算數，避免重蹈資料窺探
的覆轍。

用法：
  python backtest_mean_reversion.py
"""

import asyncio

import pandas as pd

from backtest import SYMBOLS, fetch_full_history
from backtest_optimize import ATR_PERIOD, simulate, summarize
from main import make_exchange

GRID_BB_PERIOD = [14, 20, 30]
GRID_BB_STD_MULT = [2.0, 2.5]
GRID_ATR_SL_MULT = [1.0, 1.5]
GRID_RISK_REWARD_RATIO = [1.0, 1.5, 2.0]
GRID_TREND_FILTER = ["none", "counter_trend_block"]  # none=不管趨勢；block=不逆著主趨勢做

MA_FAST, MA_SLOW = 50, 200  # 只拿來當趨勢過濾器參考，跟原策略同一組週期
MIN_TRADES_PER_WINDOW = 15


def compute_mr_signals(
    df: pd.DataFrame, bb_period: int, bb_std_mult: float, trend_filter: str
) -> pd.DataFrame:
    df = df.copy()

    mid = df["close"].rolling(bb_period).mean()
    std = df["close"].rolling(bb_period).std()
    df["bb_upper"] = mid + bb_std_mult * std
    df["bb_lower"] = mid - bb_std_mult * std

    df["ma_fast"] = df["close"].rolling(MA_FAST).mean()
    df["ma_slow"] = df["close"].rolling(MA_SLOW).mean()

    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1
    ).max(axis=1)
    df["atr"] = tr.rolling(ATR_PERIOD).mean()

    prev_bb_upper = df["bb_upper"].shift(1)
    prev_bb_lower = df["bb_lower"].shift(1)

    # 跟突破策略「同一組」穿越事件，只是 Long/Short 的解讀對調
    crossed_below_lower = (prev_close >= prev_bb_lower) & (df["close"] < df["bb_lower"])
    crossed_above_upper = (prev_close <= prev_bb_upper) & (df["close"] > df["bb_upper"])

    if trend_filter == "none":
        long_ok = pd.Series(True, index=df.index)
        short_ok = pd.Series(True, index=df.index)
    else:  # counter_trend_block：不逆著主趨勢方向做（下跌趨勢中不摸底、上漲趨勢中不摸頭）
        downtrend = df["ma_fast"] < df["ma_slow"]
        uptrend = df["ma_fast"] > df["ma_slow"]
        long_ok = ~downtrend
        short_ok = ~uptrend

    df["long_signal"] = crossed_below_lower & long_ok
    df["short_signal"] = crossed_above_upper & short_ok
    return df


async def load_windows() -> dict[str, dict[str, pd.DataFrame]]:
    exchange = make_exchange("okx")
    await exchange.load_markets()
    data: dict[str, dict[str, pd.DataFrame]] = {"in_sample": {}, "out_of_sample": {}}
    try:
        for symbol in SYMBOLS:
            data["in_sample"][symbol] = await fetch_full_history(exchange, symbol, days=180)
            data["out_of_sample"][symbol] = await fetch_full_history(exchange, symbol, days=180, offset_days=180)
    finally:
        await exchange.close()
    return data


def evaluate_combo(data: dict, bb_period: int, bb_std_mult: float, atr_sl_mult: float, rr: float, trend_filter: str):
    start_idx = max(MA_SLOW, bb_period, ATR_PERIOD) + 2
    result = {"in_sample": {}, "out_of_sample": {}}

    for window in ("in_sample", "out_of_sample"):
        for symbol in SYMBOLS:
            df = data[window][symbol]
            signals_df = compute_mr_signals(df, bb_period, bb_std_mult, trend_filter)
            trades = simulate(signals_df, atr_sl_mult, rr, start_idx)
            result[window][symbol] = summarize(trades)

    return result


def passes_bar(result: dict) -> bool:
    for window in ("in_sample", "out_of_sample"):
        for symbol in SYMBOLS:
            stats = result[window][symbol]
            if stats["count"] < MIN_TRADES_PER_WINDOW:
                return False
            if stats["avg_pnl_after_fee"] <= 0:
                return False
    return True


def combo_score(result: dict) -> float:
    values = [
        result[window][symbol]["avg_pnl_after_fee"]
        for window in ("in_sample", "out_of_sample")
        for symbol in SYMBOLS
    ]
    return sum(values) / len(values)


def print_result(params: dict, result: dict) -> None:
    print(f"\n組合：{params}")
    for window_label, window_key in (("樣本內(近180天)", "in_sample"), ("樣本外(180~360天前)", "out_of_sample")):
        line = f"  {window_label:<22}"
        for symbol in SYMBOLS:
            s = result[window_key][symbol]
            line += f"{symbol.split('/')[0]}:{s['win_rate']:.0f}%赢({s['count']}筆,期望值{s['avg_pnl_after_fee']:+.2f}%) "
        print(line)


async def main() -> None:
    print("載入樣本內／樣本外歷史資料（優先讀取本地快取）...")
    data = await load_windows()

    combos = [
        {"bb_period": p, "bb_std_mult": s, "atr_sl_mult": a, "risk_reward_ratio": r, "trend_filter": t}
        for p in GRID_BB_PERIOD
        for s in GRID_BB_STD_MULT
        for a in GRID_ATR_SL_MULT
        for r in GRID_RISK_REWARD_RATIO
        for t in GRID_TREND_FILTER
    ]
    print(f"共 {len(combos)} 組均值回歸參數，同時要求樣本內與樣本外、三個標的都要扣費後為正才算數...\n")

    passed = []
    all_results = []
    for params in combos:
        result = evaluate_combo(
            data, params["bb_period"], params["bb_std_mult"], params["atr_sl_mult"],
            params["risk_reward_ratio"], params["trend_filter"],
        )
        score = combo_score(result)
        all_results.append((params, result, score))
        if passes_bar(result):
            passed.append((params, result, score))

    print(f"通過「樣本內+樣本外、三標的皆為正」門檻的組合數：{len(passed)} / {len(combos)}")

    if not passed:
        print("\n沒有任何均值回歸參數組合能同時撐過樣本內與樣本外驗證。")
        all_results.sort(key=lambda x: x[2], reverse=True)
        print("\n列出綜合期望值最高的前 5 組（雖未達標，看看差多少）：")
        for params, result, score in all_results[:5]:
            print_result(params, result)
        return

    passed.sort(key=lambda x: x[2], reverse=True)
    print("\n以下為通過門檻的組合（依平均期望值排序）：")
    for params, result, score in passed:
        print_result(params, result)


if __name__ == "__main__":
    asyncio.run(main())
