"""
美股 ORB 當沖策略回測：驗證 main.py 裡「開盤區間突破 + RVOL 過濾 + 大盤濾網」
這套策略在真實歷史數據上的表現。

直接從 main.py import 核心常數與 build_us_stock_open_signal / calculate_leverage，
確保回測跑的是「跟線上完全同一套規則」，包含這次新加的 EOD 強制平倉規則
（當沖不留倉過夜）跟 Long/Short 不對稱停損邏輯。

⚠️ 誠實聲明（範圍限制）：
  - BingX 這幾檔代幣化美股商品的歷史資料只到 2025-11-03 左右（約 246 天），
    沒有滿 360 天可測，這裡就測「資料實際存在的全部區間」，不足的部分無法
    無中生有。
  - 早期（2025-11~2026-01）資料明顯比近期稀疏（很多15分鐘沒有成交量，代表
    當時這幾個商品剛上架、流動性還很薄），RVOL 計算需要「過去5個交易日
    同一時段」都有資料才算得出來，資料稀疏的區間自然會產生較少訊號，
    這是資料本身的限制，不是程式邏輯的bug。
  - TP/SL 判定用該根K棒的 high/low（不是只看 close），同一根K棒內 TP、SL
    都被觸及時保守假設 SL 先發生。手續費採 2*FEE_PCT_PER_SIDE*槓桿（來回、
    含槓桿放大），跟 backtest_htf.py 同樣的假設。
  - 大盤濾網（NASDAQ100 代幣化指數商品）用跟 main.py 完全一樣的算法：
    MA9/MA21 交叉 或 突破前一根高低點，兩者互斥時判中性。
  - 不含滑價模擬。

用法：
  python backtest_us_stock_orb.py
"""

import asyncio
import os
from datetime import datetime, time as dt_time, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from main import (
    ORB_RANGE_END,
    ORB_RANGE_START,
    ORB_RISK_REWARD_RATIO,
    ORB_RVOL_LOOKBACK_DAYS,
    ORB_RVOL_MULT,
    US_MARKET_CLOSE,
    US_MARKET_TZ,
    US_STOCK_REGIME_SYMBOL,
    US_STOCK_SYMBOLS,
    build_us_stock_open_signal,
    calculate_leverage,
    make_exchange,
)

FEE_PCT_PER_SIDE = 0.05  # 跟 backtest_htf.py 同樣假設：BingX taker 費率概估
CANDLES_PER_FETCH = 1000
TIMEFRAME = "15m"
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_cache")


def _cache_path(symbol: str) -> str:
    safe_symbol = symbol.replace("/", "_").replace(":", "_")
    return os.path.join(CACHE_DIR, f"{safe_symbol}_{TIMEFRAME}_orb_full.csv")


async def fetch_all_available_history(exchange, symbol: str, use_cache: bool = True) -> pd.DataFrame:
    """
    往前分頁抓到抓不到為止（BingX 這幾檔代幣化商品上架沒多久，歷史本來就有限），
    不是抓固定天數——固定天數在資料不夠長時會一直原地打轉。
    """
    cache_file = _cache_path(symbol)
    if use_cache and os.path.exists(cache_file):
        return pd.read_csv(cache_file)

    all_candles: list = []
    since = None
    seen_earliest = None

    # 先抓最新一批，取得最早時間戳，再持續往前翻頁直到交易所回空為止
    latest_batch = await exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=CANDLES_PER_FETCH)
    if not latest_batch:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    all_candles.extend(latest_batch)
    seen_earliest = latest_batch[0][0]

    while True:
        since = seen_earliest - CANDLES_PER_FETCH * 15 * 60 * 1000
        batch = await exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, since=since, limit=CANDLES_PER_FETCH)
        if not batch:
            break
        all_candles.extend(batch)
        new_earliest = batch[0][0]
        if new_earliest >= seen_earliest:
            break  # 沒有再往前推進，代表已經到資料起點
        seen_earliest = new_earliest

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)

    if use_cache:
        os.makedirs(CACHE_DIR, exist_ok=True)
        df.to_csv(cache_file, index=False)

    return df


def add_et_columns(df: pd.DataFrame) -> pd.DataFrame:
    tz = ZoneInfo(US_MARKET_TZ)
    df = df.copy()
    df["et_time"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_convert(tz)
    df["et_date"] = df["et_time"].dt.date
    df["et_hm"] = df["et_time"].dt.strftime("%H:%M")
    return df


def compute_regime_series(regime_df: pd.DataFrame) -> pd.DataFrame:
    """跟 main.py 的 refresh_us_market_regime 完全同樣的算法，逐根計算。"""
    df = regime_df.copy()
    ma_fast = df["close"].rolling(9).mean()
    ma_slow = df["close"].rolling(21).mean()
    prev_high = df["high"].shift(1)
    prev_low = df["low"].shift(1)

    bullish = (ma_fast > ma_slow) | (df["close"] > prev_high)
    bearish = (ma_fast < ma_slow) | (df["close"] < prev_low)

    regime = pd.Series("Neutral", index=df.index)
    regime[bullish & ~bearish] = "Bullish"
    regime[bearish & ~bullish] = "Bearish"
    df["regime"] = regime
    return df[["timestamp", "regime"]]


def simulate_symbol(display_name: str, ticker_symbol: str, df: pd.DataFrame, regime_df: pd.DataFrame) -> list[dict]:
    df = add_et_columns(df)
    df = df.merge(regime_df, on="timestamp", how="left")
    df["regime"] = df["regime"].fillna("Neutral")

    # 依 et_hm 分組，供 RVOL 查詢「過去N個交易日同一時段」用
    volume_by_slot: dict[str, list[tuple]] = {}
    for _, row in df.iterrows():
        volume_by_slot.setdefault(row["et_hm"], []).append((row["et_date"], row["volume"]))

    trades: list[dict] = []
    dates = sorted(df["et_date"].unique())
    range_start_hm = ORB_RANGE_START.strftime("%H:%M")

    for d in dates:
        if d.weekday() >= 5:
            continue

        day_df = df[df["et_date"] == d].reset_index(drop=True)
        range_rows = day_df[day_df["et_hm"] == range_start_hm]
        if range_rows.empty:
            continue

        opening_high = float(range_rows.iloc[0]["high"])
        opening_low = float(range_rows.iloc[0]["low"])
        if opening_high <= opening_low:
            continue

        breakout_rows = day_df[day_df["et_time"].dt.time > ORB_RANGE_END]
        if breakout_rows.empty:
            continue

        position: dict | None = None
        day_high_so_far = float(range_rows.iloc[0]["high"])

        for _, row in breakout_rows.iterrows():
            day_high_so_far = max(day_high_so_far, float(row["high"]))

            if position is None:
                # --- 尋找當天第一個有效突破 ---
                slot_history = volume_by_slot.get(row["et_hm"], [])
                past_volumes = sorted(
                    [(dd, vv) for dd, vv in slot_history if dd < d and pd.Timestamp(dd).dayofweek < 5],
                    key=lambda x: x[0],
                )
                recent = [v for _, v in past_volumes[-ORB_RVOL_LOOKBACK_DAYS:]]
                avg_slot_volume = (sum(recent) / len(recent)) if recent else None
                rvol = (row["volume"] / avg_slot_volume) if avg_slot_volume and avg_slot_volume > 0 else None
                volume_confirmed = rvol is not None and rvol >= ORB_RVOL_MULT

                long_breakout = row["close"] > opening_high
                short_breakout = row["close"] < opening_low
                regime = row["regime"]

                candidate = None
                if long_breakout and volume_confirmed and regime == "Bullish":
                    candidate = {
                        "side": "Long", "entry_price": float(row["close"]),
                        "opening_high": opening_high, "opening_low": opening_low,
                    }
                elif short_breakout and volume_confirmed and regime == "Bearish":
                    candidate = {
                        "side": "Short", "entry_price": float(row["close"]),
                        "opening_high": opening_high, "opening_low": opening_low,
                        "day_high_so_far": day_high_so_far,
                    }

                if candidate is not None:
                    opened = build_us_stock_open_signal(display_name, ticker_symbol, candidate)
                    position = {**opened, "rvol": rvol, "regime_at_entry": regime}
                continue

            # --- 已有部位，檢查這根K棒是否觸及 TP/SL（保守假設同根內SL先發生）---
            side = position["side"]
            tp, sl = position["take_profit"], position["stop_loss"]
            hit_tp = row["high"] >= tp if side == "Long" else row["low"] <= tp
            hit_sl = row["low"] <= sl if side == "Long" else row["high"] >= sl

            if hit_sl:
                trades.append(_close_trade(position, sl, "LOSS"))
                position = None
            elif hit_tp:
                trades.append(_close_trade(position, tp, "WIN"))
                position = None

        if position is not None:
            # 當沖規則：收盤前沒觸及 TP/SL，用當天最後一根收盤價強制平倉
            last_close = float(day_df.iloc[-1]["close"])
            raw_pnl = (last_close - position["entry_price"]) / position["entry_price"] * 100
            if position["side"] == "Short":
                raw_pnl = -raw_pnl
            result = "WIN" if raw_pnl >= 0 else "LOSS"
            trades.append(_close_trade(position, last_close, result))

    return trades


def _close_trade(position: dict, exit_price: float, result: str) -> dict:
    side = position["side"]
    raw_pnl_pct = (exit_price - position["entry_price"]) / position["entry_price"] * 100
    if side == "Short":
        raw_pnl_pct = -raw_pnl_pct
    pnl_pct = raw_pnl_pct * position["leverage"]
    fee_cost_pct = 2 * FEE_PCT_PER_SIDE * position["leverage"]
    return {
        "side": side,
        "result": result,
        "pnl_pct": pnl_pct,
        "pnl_pct_after_fee": pnl_pct - fee_cost_pct,
        "rvol": position["rvol"],
        "regime_at_entry": position["regime_at_entry"],
    }


def print_report(display_name: str, trades: list[dict]) -> None:
    if not trades:
        print(f"{display_name:6s}｜0 筆交易（資料期間內沒有同時滿足 突破+RVOL+大盤濾網 的訊號）")
        return

    wins = sum(1 for t in trades if t["result"] == "WIN")
    losses = len(trades) - wins
    win_rate = wins / len(trades) * 100

    gross_total = sum(t["pnl_pct"] for t in trades)
    net_total = sum(t["pnl_pct_after_fee"] for t in trades)
    avg_net = net_total / len(trades)

    win_pnls = [t["pnl_pct_after_fee"] for t in trades if t["pnl_pct_after_fee"] > 0]
    loss_pnls = [t["pnl_pct_after_fee"] for t in trades if t["pnl_pct_after_fee"] <= 0]
    gross_win = sum(win_pnls)
    gross_loss = abs(sum(loss_pnls))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

    print(
        f"{display_name:6s}｜{len(trades):4d} 筆｜勝率 {win_rate:5.1f}%（{wins}W {losses}L）｜"
        f"扣費後期望值 {avg_net:+6.2f}%/筆｜扣費後總報酬 {net_total:+8.1f}%｜"
        f"Profit Factor {profit_factor:.2f}（扣費前總報酬 {gross_total:+8.1f}%）"
    )


async def main() -> None:
    exchange = make_exchange("bingx")
    await exchange.load_markets()

    print("抓取歷史K線中（首次執行會存快取到 data_cache/，之後重跑會直接讀快取）...")
    regime_raw = await fetch_all_available_history(exchange, US_STOCK_REGIME_SYMBOL)
    regime_df = compute_regime_series(regime_raw)
    print(
        f"大盤濾網（{US_STOCK_REGIME_SYMBOL}）資料範圍："
        f"{datetime.fromtimestamp(regime_raw['timestamp'].min()/1000, tz=timezone.utc).date()} ~ "
        f"{datetime.fromtimestamp(regime_raw['timestamp'].max()/1000, tz=timezone.utc).date()}"
        f"（共 {len(regime_raw)} 根15m K棒）"
    )
    print()

    print("=" * 100)
    print("美股 ORB 當沖策略回測結果（開盤區間突破 + RVOL>=%.1fx + 大盤濾網，%dx風報比，含手續費）" % (
        ORB_RVOL_MULT, ORB_RISK_REWARD_RATIO
    ))
    print("=" * 100)

    for display_name, ticker_symbol in US_STOCK_SYMBOLS.items():
        raw = await fetch_all_available_history(exchange, ticker_symbol)
        if raw.empty:
            print(f"{display_name:6s}｜無法取得歷史資料")
            continue
        date_min = datetime.fromtimestamp(raw["timestamp"].min() / 1000, tz=timezone.utc).date()
        date_max = datetime.fromtimestamp(raw["timestamp"].max() / 1000, tz=timezone.utc).date()
        trades = simulate_symbol(display_name, ticker_symbol, raw, regime_df)
        print_report(display_name, trades)
        print(f"       資料範圍：{date_min} ~ {date_max}（共 {len(raw)} 根15m K棒，約 {(date_max-date_min).days} 天）")

    print("=" * 100)
    await exchange.close()


if __name__ == "__main__":
    asyncio.run(main())
