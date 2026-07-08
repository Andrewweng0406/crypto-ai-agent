"""
美股 ORB 策略回測（真實美股現貨版）：用 Yahoo Finance（yfinance）的真實 TSLA/NVDA/
MSTR/SOXL/TQQQ 現貨分鐘級資料驗證策略概念本身在真正股票市場上站不站得住腳。

跟 backtest_us_stock_orb.py（BingX 代幣化商品版）共用同一套模擬邏輯（simulate_symbol /
compute_regime_series / build_us_stock_open_signal），差別只在資料來源，這樣兩份結果
才有辦法公平比較「同一套策略邏輯，套在真實股票 vs 合成代幣商品上表現差多少」。

⚠️ 誠實聲明：
  - Yahoo Finance 免費資料 15 分鐘級歷史只給最近 60 天，樣本數會比 BingX 那份
    （~250天）少很多，統計上更不可信，只能當初步健康檢查，不是最終驗證。
  - 大盤濾網用 QQQ（追蹤那斯達克100的真實ETF）取代 BingX 版用的代幣化指數商品，
    這才是真正有實際成交量、真正機構在交易的那斯達克100代理標的。
  - Yahoo 資料本身就只在真正的美股交易時段出現（不像 BingX 代幣化商品是24小時
    都有報價），所以完全不用另外過濾非交易時段的雜訊，這點比 BingX 資料乾淨。
  - 一樣不含滑價模擬，手續費假設沿用 backtest_us_stock_orb.py 的 FEE_PCT_PER_SIDE。

用法：
  python backtest_us_stock_orb_real.py
"""

import pandas as pd
import yfinance as yf

from backtest_us_stock_orb import (
    FEE_PCT_PER_SIDE,
    compute_regime_series,
    print_report,
    simulate_symbol,
)
from main import US_STOCK_SYMBOLS

REAL_TICKERS = list(US_STOCK_SYMBOLS.keys())  # ["TSLA", "NVDA", "MSTR", "SOXL", "TQQQ"]
REGIME_TICKER = "QQQ"  # 真實那斯達克100代理（有真實成交量的ETF），對應 main.py 的 US_STOCK_REGIME_SYMBOL
PERIOD = "60d"
INTERVAL = "15m"


def fetch_yf_ohlcv(ticker: str) -> pd.DataFrame:
    """把 yfinance 回傳的 tz-aware DataFrame 轉成跟 BingX 版一致的欄位格式（timestamp 為 UTC 毫秒）。"""
    raw = yf.Ticker(ticker).history(period=PERIOD, interval=INTERVAL)
    if raw.empty:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame({
        "timestamp": (raw.index.view("int64") // 10**6),  # tz-aware Timestamp -> UTC 毫秒，跟時區顯示無關
        "open": raw["Open"].values,
        "high": raw["High"].values,
        "low": raw["Low"].values,
        "close": raw["Close"].values,
        "volume": raw["Volume"].values,
    })
    return df.reset_index(drop=True)


def main() -> None:
    print(f"抓取 Yahoo Finance 真實股票資料中（{PERIOD} / {INTERVAL}）...")
    regime_raw = fetch_yf_ohlcv(REGIME_TICKER)
    regime_df = compute_regime_series(regime_raw)
    print(f"大盤濾網（{REGIME_TICKER}，那斯達克100真實ETF代理）：共 {len(regime_raw)} 根15m K棒")
    print()

    print("=" * 100)
    print("美股 ORB 當沖策略回測結果（真實美股現貨資料 via Yahoo Finance，60天）")
    print("=" * 100)

    for display_name in REAL_TICKERS:
        raw = fetch_yf_ohlcv(display_name)
        if raw.empty:
            print(f"{display_name:6s}｜無法取得歷史資料")
            continue
        trades = simulate_symbol(display_name, display_name, raw, regime_df)
        print_report(display_name, trades)
        print(f"       共 {len(raw)} 根15m K棒（Yahoo Finance 免費版 15m 歷史上限 60 天）")

    print("=" * 100)


if __name__ == "__main__":
    main()
