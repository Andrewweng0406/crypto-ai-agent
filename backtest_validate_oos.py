"""
樣本外驗證：backtest_optimize.py 在「最近 180 天」的資料上跑了 162 組參數網格搜尋，
選出來的第一名天生有過度配適風險——測了 162 種組合，難免會有純粹碰運氣表現特別好的。

這支腳本把該候選組合拿去「完全沒被拿來搜參數」的更早一段 180 天資料
（180～360 天前）上重新驗證，看看那個優勢是不是真的存在，還是只是巧合。

用法：
  python backtest_validate_oos.py
"""

import asyncio

from backtest import SYMBOLS, fetch_full_history
from backtest_optimize import ATR_PERIOD, compute_signals, simulate, summarize
from main import make_exchange

# backtest_optimize.py 網格搜尋結果排名第一的組合
CANDIDATE = {
    "bb_period": 20,
    "bb_std_mult": 2.5,
    "ma_fast": 20,
    "ma_slow": 50,
    "atr_sl_mult": 2.0,
    "risk_reward_ratio": 3.0,
}


async def main() -> None:
    exchange = make_exchange("okx")
    await exchange.load_markets()

    print("抓取樣本外資料（180～360 天前，網格搜尋完全沒用過這段資料）...")
    print(f"驗證組合：{CANDIDATE}\n")

    try:
        all_after_fee = []
        for symbol in SYMBOLS:
            df = await fetch_full_history(exchange, symbol, days=180, offset_days=180)
            start_idx = max(CANDIDATE["ma_slow"], CANDIDATE["bb_period"], ATR_PERIOD) + 2
            signals_df = compute_signals(
                df, CANDIDATE["bb_period"], CANDIDATE["bb_std_mult"], CANDIDATE["ma_fast"], CANDIDATE["ma_slow"]
            )
            trades = simulate(signals_df, CANDIDATE["atr_sl_mult"], CANDIDATE["risk_reward_ratio"], start_idx)
            stats = summarize(trades)
            all_after_fee.append(stats["total_pnl_after_fee"])

            print(
                f"{symbol:<16} {len(df):>6} 根K棒 | {stats['count']:>4} 筆交易 | "
                f"勝率 {stats['win_rate']:>5.1f}% | 扣費後平均期望值 {stats['avg_pnl_after_fee']:>7.3f}%/筆 | "
                f"累計損益 {stats['total_pnl_after_fee']:>8.1f}%"
            )
    finally:
        await exchange.close()

    print()
    if all(v > 0 for v in all_after_fee):
        print("✅ 三個標的在樣本外都還是正的，這個組合的優勢比較有可信度，但仍建議繼續用更長時間觀察。")
    else:
        print("❌ 至少一個標的在樣本外轉負，代表原本網格搜尋選出來的優勢很可能只是過度配適，不能直接拿去用。")


if __name__ == "__main__":
    asyncio.run(main())
