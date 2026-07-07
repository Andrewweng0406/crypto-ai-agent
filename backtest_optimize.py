"""
參數優化腳本：在同一份歷史資料上，掃過一組不同的策略參數組合，
找出「扣掉真實手續費後」期望值最高、且在三個幣上都相對穩健的組合。

跟 backtest.py 的關係：
  backtest.py 驗證的是 main.py 目前寫死的那組參數（BB 20期/2倍標準差、
  MA 50/200、ATR 1.5倍、盈虧比 2:1），結果是勝率 34.5%，理論打平線
  33.3%，幾乎沒有優勢，而且沒扣手續費。
  這支腳本把「策略參數」跟「手續費」都當變數，看看有沒有其他組合真的
  站得住腳，而不是繼續憑感覺調一組數字。

⚠️ 誠實聲明：
  - 一樣不含聰明錢否決濾網、不含資金費率成本，只看技術面 + 手續費。
  - 用同一份歷史資料重複測試很多組合，本質上就有「資料窺探 / 過度配適」
    的風險——測出來最好的那組，很可能只是剛好最貼合這半年的走勢，換一段
    時間不一定重現。這裡用「三個幣都要有一定樣本數、且個別都不能太爛」
    做一點點穩健性篩選，但這不能取代之後用「樣本外」（例如再抓近一個月
    的新資料）驗證。

用法：
  python backtest_optimize.py              # 用預設 180 天快取資料跑網格搜尋
  python backtest_optimize.py --days 365   # 改用 365 天資料（若無快取會先抓取）
"""

import argparse
import asyncio
import itertools

import pandas as pd

from backtest import SYMBOLS, fetch_full_history
from main import calculate_leverage, make_exchange

MIN_TRADES_PER_SYMBOL = 15  # 樣本數太少的組合直接排除，避免用個位數交易數的偶然結果誤判
FEE_PCT_PER_SIDE = 0.05     # 假設單邊 taker 手續費 0.05%（一般交易所無 VIP 折扣的常見水準）

# 網格搜尋範圍：刻意只挑常見、有解釋意義的數值，避免無意義的過度細分
GRID = {
    "bb_period": [14, 20, 30],
    "bb_std_mult": [1.5, 2.0, 2.5],
    "ma_pair": [(20, 50), (50, 200)],
    "atr_sl_mult": [1.0, 1.5, 2.0],
    "risk_reward_ratio": [1.5, 2.0, 3.0],
}
ATR_PERIOD = 14


def compute_signals(df: pd.DataFrame, bb_period: int, bb_std_mult: float, ma_fast: int, ma_slow: int) -> pd.DataFrame:
    df = df.copy()

    mid = df["close"].rolling(bb_period).mean()
    std = df["close"].rolling(bb_period).std()
    df["bb_upper"] = mid + bb_std_mult * std
    df["bb_lower"] = mid - bb_std_mult * std

    df["ma_fast"] = df["close"].rolling(ma_fast).mean()
    df["ma_slow"] = df["close"].rolling(ma_slow).mean()

    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1
    ).max(axis=1)
    df["atr"] = tr.rolling(ATR_PERIOD).mean()

    uptrend = df["ma_fast"] > df["ma_slow"]
    downtrend = df["ma_fast"] < df["ma_slow"]
    prev_bb_upper = df["bb_upper"].shift(1)
    prev_bb_lower = df["bb_lower"].shift(1)

    long_breakout = (prev_close <= prev_bb_upper) & (df["close"] > df["bb_upper"])
    short_breakout = (prev_close >= prev_bb_lower) & (df["close"] < df["bb_lower"])

    df["long_signal"] = long_breakout & uptrend
    df["short_signal"] = short_breakout & downtrend
    return df


def simulate(df: pd.DataFrame, atr_sl_mult: float, risk_reward_ratio: float, start_idx: int) -> list[dict]:
    trades: list[dict] = []
    open_position: dict | None = None

    for i in range(start_idx, len(df)):
        candle = df.iloc[i]

        if open_position is not None:
            side = open_position["side"]
            tp, sl = open_position["take_profit"], open_position["stop_loss"]
            hit_tp = candle["high"] >= tp if side == "Long" else candle["low"] <= tp
            hit_sl = candle["low"] <= sl if side == "Long" else candle["high"] >= sl

            if hit_tp or hit_sl:
                result = "LOSS" if hit_sl else "WIN"  # 同根K棒都觸及時保守假設 SL 先發生
                exit_price = sl if hit_sl else tp
                raw_pnl_pct = (exit_price - open_position["entry_price"]) / open_position["entry_price"] * 100
                if side == "Short":
                    raw_pnl_pct = -raw_pnl_pct
                pnl_pct = raw_pnl_pct * open_position["leverage"]
                fee_cost_pct = 2 * FEE_PCT_PER_SIDE * open_position["leverage"]  # 進場+出場，皆按槓桿後名目計費
                trades.append({"result": result, "pnl_pct": pnl_pct, "pnl_pct_after_fee": pnl_pct - fee_cost_pct})
                open_position = None
            continue

        if bool(candle["long_signal"]) or bool(candle["short_signal"]):
            side = "Long" if candle["long_signal"] else "Short"
            entry_price = float(candle["close"])
            atr = float(candle["atr"])
            sl_distance = atr * atr_sl_mult
            tp_distance = sl_distance * risk_reward_ratio

            if side == "Long":
                stop_loss = entry_price - sl_distance
                take_profit = entry_price + tp_distance
            else:
                stop_loss = entry_price + sl_distance
                take_profit = entry_price - tp_distance

            stop_loss_pct = abs(entry_price - stop_loss) / entry_price * 100
            leverage = calculate_leverage(stop_loss_pct)

            open_position = {
                "side": side,
                "entry_price": entry_price,
                "take_profit": take_profit,
                "stop_loss": stop_loss,
                "leverage": leverage,
            }

    return trades


def summarize(trades: list[dict]) -> dict:
    if not trades:
        return {"count": 0, "win_rate": 0.0, "avg_pnl_after_fee": 0.0, "total_pnl_after_fee": 0.0}

    wins = sum(1 for t in trades if t["result"] == "WIN")
    total_after_fee = sum(t["pnl_pct_after_fee"] for t in trades)
    return {
        "count": len(trades),
        "win_rate": wins / len(trades) * 100,
        "avg_pnl_after_fee": total_after_fee / len(trades),
        "total_pnl_after_fee": total_after_fee,
    }


async def load_all_history(days: int) -> dict[str, pd.DataFrame]:
    exchange = make_exchange("okx")
    await exchange.load_markets()
    data = {}
    try:
        for symbol in SYMBOLS:
            data[symbol] = await fetch_full_history(exchange, symbol, days)
    finally:
        await exchange.close()
    return data


def run_grid_search(data: dict[str, pd.DataFrame]) -> list[dict]:
    combos = list(
        itertools.product(
            GRID["bb_period"], GRID["bb_std_mult"], GRID["ma_pair"], GRID["atr_sl_mult"], GRID["risk_reward_ratio"]
        )
    )
    print(f"共 {len(combos)} 組參數 x {len(SYMBOLS)} 個標的，開始模擬...")

    results = []
    for bb_period, bb_std_mult, (ma_fast, ma_slow), atr_sl_mult, rr in combos:
        start_idx = max(ma_slow, bb_period, ATR_PERIOD) + 2
        per_symbol = {}
        for symbol, df in data.items():
            signals_df = compute_signals(df, bb_period, bb_std_mult, ma_fast, ma_slow)
            trades = simulate(signals_df, atr_sl_mult, rr, start_idx)
            per_symbol[symbol] = summarize(trades)

        # 穩健性把關：任一標的樣本數太少就整組排除，避免被偶然的少數交易誤導
        if any(s["count"] < MIN_TRADES_PER_SYMBOL for s in per_symbol.values()):
            continue

        worst_symbol_pnl = min(s["total_pnl_after_fee"] for s in per_symbol.values())
        avg_expectancy = sum(s["avg_pnl_after_fee"] for s in per_symbol.values()) / len(per_symbol)

        results.append(
            {
                "params": {
                    "bb_period": bb_period,
                    "bb_std_mult": bb_std_mult,
                    "ma_fast": ma_fast,
                    "ma_slow": ma_slow,
                    "atr_sl_mult": atr_sl_mult,
                    "risk_reward_ratio": rr,
                },
                "per_symbol": per_symbol,
                "worst_symbol_pnl": worst_symbol_pnl,
                "avg_expectancy_after_fee": avg_expectancy,
            }
        )

    # 排序依據：每筆交易扣費後的平均期望值（不是總損益，避免偏好交易次數多的組合）
    results.sort(key=lambda r: r["avg_expectancy_after_fee"], reverse=True)
    return results


def print_top_results(results: list[dict], top_n: int = 10) -> None:
    if not results:
        print("沒有任何組合通過最低樣本數門檻，資料量可能不足。")
        return

    print("\n" + "=" * 100)
    print(f"{'排名':<4}{'BB期':>5}{'BB倍':>6}{'MA':>10}{'ATR倍':>7}{'盈虧比':>7}   {'扣費後平均期望值/筆':>18}   最差標的累計損益  各標的勝率(交易數)")
    print("-" * 100)

    for rank, r in enumerate(results[:top_n], start=1):
        p = r["params"]
        ma_label = f"{p['ma_fast']}/{p['ma_slow']}"
        per_symbol_label = " | ".join(
            f"{sym.split('/')[0]}:{s['win_rate']:.0f}%({s['count']})" for sym, s in r["per_symbol"].items()
        )
        print(
            f"{rank:<4}{p['bb_period']:>5}{p['bb_std_mult']:>6.1f}{ma_label:>10}{p['atr_sl_mult']:>7.1f}"
            f"{p['risk_reward_ratio']:>7.1f}   {r['avg_expectancy_after_fee']:>17.3f}%   "
            f"{r['worst_symbol_pnl']:>14.1f}%   {per_symbol_label}"
        )

    print("=" * 100)
    positive = [r for r in results if r["avg_expectancy_after_fee"] > 0 and r["worst_symbol_pnl"] > 0]
    print(
        f"\n扣費後平均期望值為正、且三個標的都沒有虧錢的組合數：{len(positive)} / {len(results)}"
    )
    print(
        "⚠️  這是在同一份歷史資料上跑很多組合選出來的最佳結果，天生有過度配適風險，"
        "\n    務必再用一段沒用來搜參數的新資料（樣本外）驗證，數字才可信。"
    )


async def main(days: int) -> None:
    print(f"載入 {days} 天歷史資料（若已有快取會直接讀取，不重新打 API）...")
    data = await load_all_history(days)
    for symbol, df in data.items():
        print(f"  {symbol}: {len(df)} 根K棒")

    results = run_grid_search(data)
    print_top_results(results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="策略參數網格搜尋（含手續費）")
    parser.add_argument("--days", type=int, default=180, help="使用幾天的歷史資料（預設 180 天）")
    args = parser.parse_args()

    asyncio.run(main(args.days))
