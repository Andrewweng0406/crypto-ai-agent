"""
回測腳本：驗證 main.py 裡「布林通道突破 + 雙均線趨勢過濾」策略在真實歷史數據上的表現。

直接從 main.py import 核心邏輯（add_indicators / detect_new_signal 的判斷條件 /
build_open_signal / calculate_leverage），確保回測跑的是「跟線上完全同一套規則」，
不是另外重寫一份容易漂移、對不上的邏輯。

⚠️ 範圍限制（誠實講清楚，不要誤會這是完整驗證）：
  這份回測只測試「技術面策略」本身，*不包含*聰明錢否決濾網（資金費率 / 大戶
  多空比）。原因：歷史資金費率、未平倉量需要額外抓取且要跟K線時間點對齊，
  複雜度高一截，先把最核心的問題回答掉——這個技術面策略本身有沒有用。
  因此這裡算出來的勝率，理論上會比實盤（多一層濾網過濾掉部分逆勢單）更保守，
  也可能有落差，之後可以再疊加聰明錢數據做第二階段回測。

  另外，TP/SL 判定用該根K棒的 high/low（而非只看 close），且「同一根K棒內
  TP、SL 都被觸及」時保守假設 SL 先發生 —— 這是業界常見的保守做法，避免
  高估勝率。實際盤中價格走的路徑不會知道，只能用這個假設去逼近。

用法：
  python backtest.py                  # 預設回測 BTC/ETH/SOL 過去 180 天
  python backtest.py --days 365       # 改成回測 365 天
"""

import argparse
import asyncio
import os
from datetime import datetime, timezone

import ccxt.async_support as ccxt
import pandas as pd

from main import (
    ATR_PERIOD,
    BB_PERIOD,
    MA_SLOW_PERIOD,
    TIMEFRAME,
    add_indicators,
    build_open_signal,
    make_exchange,
)

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
CANDLES_PER_FETCH = 300

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_cache")


def _cache_path(symbol: str, days: int, offset_days: int = 0, timeframe: str = TIMEFRAME) -> str:
    safe_symbol = symbol.replace("/", "_").replace(":", "_")
    suffix = f"_offset{offset_days}" if offset_days else ""
    return os.path.join(CACHE_DIR, f"{safe_symbol}_{timeframe}_{days}d{suffix}.csv")


async def fetch_full_history(
    exchange, symbol: str, days: int, use_cache: bool = True, offset_days: int = 0, timeframe: str = TIMEFRAME
) -> pd.DataFrame:
    """
    分頁抓取指定天數的歷史 K 線，從最舊的資料開始往現在補到完整。
    預設會存本地 CSV 快取（data_cache/），之後重跑（例如參數優化要跑很多組合）
    不用每次都重新打 API，直接讀快取即可。

    offset_days > 0 時，抓的視窗會整個往過去平移（例如 days=180, offset_days=180
    代表抓「180~360 天前」那一段），用來切出網格搜尋完全沒碰過的樣本外資料。

    timeframe 預設沿用 main.py 的 15m，也可以傳 "4h" / "1d" 等其他週期。
    """
    cache_file = _cache_path(symbol, days, offset_days, timeframe)
    if use_cache and os.path.exists(cache_file):
        return pd.read_csv(cache_file)

    now_ms = exchange.milliseconds()
    until_ms = now_ms - offset_days * 24 * 60 * 60 * 1000
    since = until_ms - days * 24 * 60 * 60 * 1000

    all_candles: list = []
    while True:
        batch = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=CANDLES_PER_FETCH)
        if not batch:
            break
        in_window = [c for c in batch if c[0] < until_ms]  # 只保留視窗內的K棒
        all_candles.extend(in_window)

        last_ts = batch[-1][0]
        if last_ts >= until_ms or last_ts <= since:
            break  # 已經到視窗終點，或交易所回傳資料沒有前進
        since = last_ts + 1
        if len(batch) < CANDLES_PER_FETCH:
            break  # 已經追到最新的K棒

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)

    if use_cache:
        os.makedirs(CACHE_DIR, exist_ok=True)
        df.to_csv(cache_file, index=False)

    return df


def compute_breakout_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    跟 main.py 的 detect_new_signal 條件完全等價，只是改成向量化算法，
    這樣掃過去一年、數萬根K棒才不會是 O(n^2) 慢到不能用。
    """
    df = add_indicators(df)

    uptrend = df["ma_fast"] > df["ma_slow"]
    downtrend = df["ma_fast"] < df["ma_slow"]

    prev_close = df["close"].shift(1)
    prev_bb_upper = df["bb_upper"].shift(1)
    prev_bb_lower = df["bb_lower"].shift(1)

    long_breakout = (prev_close <= prev_bb_upper) & (df["close"] > df["bb_upper"])
    short_breakout = (prev_close >= prev_bb_lower) & (df["close"] < df["bb_lower"])

    df["long_signal"] = long_breakout & uptrend
    df["short_signal"] = short_breakout & downtrend
    return df


def simulate(df: pd.DataFrame, symbol: str) -> list[dict]:
    """依時間順序走一遍歷史資料：沒部位時偵測新訊號，有部位時檢查是否觸及 TP/SL。"""
    df = compute_breakout_signals(df)
    start_idx = max(MA_SLOW_PERIOD, BB_PERIOD, ATR_PERIOD) + 2

    trades: list[dict] = []
    open_position: dict | None = None

    for i in range(start_idx, len(df)):
        candle = df.iloc[i]

        if open_position is not None:
            side = open_position["side"]
            tp = open_position["take_profit"]
            sl = open_position["stop_loss"]

            hit_tp = candle["high"] >= tp if side == "Long" else candle["low"] <= tp
            hit_sl = candle["low"] <= sl if side == "Long" else candle["high"] >= sl

            if hit_tp or hit_sl:
                # 保守假設：同一根K棒內兩者都觸及時，優先算 SL（避免高估勝率）
                result = "LOSS" if hit_sl else "WIN"
                exit_price = sl if hit_sl else tp
                raw_pnl_pct = (exit_price - open_position["entry_price"]) / open_position["entry_price"] * 100
                if side == "Short":
                    raw_pnl_pct = -raw_pnl_pct
                pnl_pct = raw_pnl_pct * open_position["leverage"]

                trades.append(
                    {
                        "symbol": symbol,
                        "side": side,
                        "result": result,
                        "pnl_pct": pnl_pct,
                        "opened_at": open_position["opened_at"],
                        "closed_at": candle["timestamp"],
                    }
                )
                open_position = None
            continue

        if candle["long_signal"] or candle["short_signal"]:
            side = "Long" if candle["long_signal"] else "Short"
            candidate = {"side": side, "entry_price": float(candle["close"]), "atr": float(candle["atr"])}
            open_position = build_open_signal(symbol, candidate)
            open_position["opened_at"] = candle["timestamp"]

    return trades


def print_report(all_trades: list[dict]) -> None:
    print("\n" + "=" * 72)
    print(f"{'標的':<16}{'交易數':>6}{'勝率':>8}{'W/L':>10}{'平均獲利':>10}{'平均虧損':>10}{'累計損益(名目%)':>16}")
    print("-" * 72)

    for symbol in SYMBOLS + ["ALL"]:
        subset = all_trades if symbol == "ALL" else [t for t in all_trades if t["symbol"] == symbol]
        if not subset:
            print(f"{symbol:<16}{'0':>6}{'--':>8}")
            continue

        wins = sum(1 for t in subset if t["result"] == "WIN")
        losses = len(subset) - wins
        win_rate = wins / len(subset) * 100
        avg_win = (sum(t["pnl_pct"] for t in subset if t["result"] == "WIN") / wins) if wins else 0.0
        avg_loss = (sum(t["pnl_pct"] for t in subset if t["result"] == "LOSS") / losses) if losses else 0.0
        total_pnl = sum(t["pnl_pct"] for t in subset)

        print(
            f"{symbol:<16}{len(subset):>6}{win_rate:>7.1f}%{f'{wins}W {losses}L':>10}"
            f"{avg_win:>9.2f}%{avg_loss:>9.2f}%{total_pnl:>15.1f}%"
        )

    print("=" * 72)
    print(
        "⚠️  以上為純技術面策略（不含聰明錢否決濾網）在歷史資料上的回測結果，"
        "\n    僅供評估策略本身是否有效，過去表現不代表未來實際結果。"
    )


async def main(days: int) -> None:
    exchange = make_exchange("okx")
    await exchange.load_markets()

    all_trades: list[dict] = []
    try:
        for symbol in SYMBOLS:
            print(f"抓取 {symbol} 過去 {days} 天的 {TIMEFRAME} 歷史K線...")
            df = await fetch_full_history(exchange, symbol, days)
            print(f"  取得 {len(df)} 根K棒，開始模擬...")
            trades = simulate(df, symbol)
            all_trades.extend(trades)
            print(f"  {symbol}：{len(trades)} 筆已結算交易")
    finally:
        await exchange.close()

    print_report(all_trades)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="回測 main.py 的布林突破策略")
    parser.add_argument("--days", type=int, default=180, help="回測天數（預設 180 天）")
    args = parser.parse_args()

    asyncio.run(main(args.days))
