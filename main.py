"""
AI 交易訊號後端服務
====================
使用 FastAPI + ccxt(async) 建立的加密貨幣交易訊號 API，同時監控多個標的。

監控範圍分兩組：
  1. 主流幣（MAJOR_SYMBOLS）：固定盯著 BTC/ETH/SOL，每個 tick 都會深度分析，
     即使沒有訊號也會回報「監控中」狀態，適合當作核心資產儀表板。
  2. 市場掃描（scan universe）：自動抓交易所 24 小時成交量排名前 N 名的
     USDT 永續合約，用「輪流」的方式分批深度分析（每個 tick 只分析一小部分，
     整個名單大約每 SCAN_CYCLE_TICKS 個 tick 才會被完整掃過一輪），
     避免每輪對數十檔幣都打滿 API，觸發交易所的頻率限制。
     這組只會回報「目前真的有觸發訊號」的幣，用來找機會，不是監控清單。

策略總覽（4 小時線；曾用 backtest_htf.py 在近1年+前1年兩段歷史資料上
各自驗證過扣費後期望值為正，才換成現在這版，細節見該檔案）：
  1. 唐奇安通道 (Donchian Channel) 突破：收盤價突破過去 N 根K棒（不含當根）
     的最高/最低點
  2. 成交量確認：當根成交量須高於近期均量的 VOLUME_MULT 倍，過濾無量假突破
  3. 雙均線 (MA50 / MA200) 作為趨勢過濾器，只做順勢突破，降低逆勢雜訊
  4. ATR (Average True Range) 用來衡量當下波動度，據此計算止盈(TP)/止損(SL)
  5. 依「固定風險模型」動態計算建議槓桿：
        leverage = floor(固定風險% / 止損距離%)
     例如固定風險設 15%：止損距離 1.5% -> 10 倍；止損距離 4% -> 3 倍
     這樣不論行情波動大小，單筆爆倉風險（保證金虧損比例）大致固定。

  ⚠️ 這個組合是從數百組參數/邏輯的網格搜尋中，唯二通過「近1年＋前1年、
  三個標的都要扣費後為正」門檻的結果之一，樣本數中等（每標的每段約
  20~30 筆交易），比較有可信度但不到「已證實」的程度，請持續觀察實際
  表現，不要直接投入大額資金。

聰明錢模塊（合約市場）：
  - 標的皆為 USDT 永續合約，因為槓桿/爆倉、資金費率、未平倉量、大戶多空比
    這些概念只存在於合約市場，現貨沒有對應數據。
  - 主流幣每 SMART_MONEY_REFRESH_SECONDS 秒背景刷新一次並快取；
    掃描名單的幣種平常不養這份資料，只有出現候選突破訊號時才臨時抓一次
    該幣種的即時資金費率/OI/大戶多空比來決定是否否決這次訊號。
  - 這些數據不會直接產生訊號，而是作為「否決濾網」：當技術面觸發 Long/Short，
    但聰明錢數據明顯反向時，會否決該次訊號，降低逆勢單的比例。

迷因幣雷達（MEME_SYMBOLS，完全獨立模塊）：
  - 監控 PEPE/WIF/DOGE 現貨（不是合約，單純看資金關注度，不需要槓桿概念）。
  - 1 小時線，每 MEME_SCAN_INTERVAL_SECONDS 秒檢查一次：當根成交量若達過去
    24 小時均量的 MEME_VOLUME_SPIKE_MULT 倍以上，記錄一筆「爆量警報」。
  - 這不是交易訊號，沒有方向/TP/SL/槓桿，只回答「現在哪個迷因幣資金明顯
    異常湧入」，跟上面主流幣策略的資料流、狀態、API 完全分開，互不影響。

背景任務：
  - 使用 FastAPI lifespan + asyncio.create_task 啟動一個永遠執行的背景迴圈：
      1. 批次抓取所有追蹤中標的的即時價格（一次 API 呼叫），驅動 TP/SL 監控
      2. 主流幣每個 tick 都做完整的 K 線 + 策略偵測
      3. 從掃描名單輪流取出一小批做完整的 K 線 + 策略偵測
      4. 迷因幣雷達依自己的頻率獨立掃描
  - 交易所預設使用 BingX（使用者實際下單的交易所），若讀取失敗會自動
    切換到 Binance、再切換到 OKX。

⚠️ 重要聲明：
  本程式內建策略僅為工程示範，尚未經過嚴謹回測與樣本外驗證，
  實際能否獲利取決於策略本身、風控與市場狀態，請勿直接用於實盤重倉交易。
"""

import asyncio
import json
import logging
import math
import os
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, time as dt_time, timezone
from math import floor
from typing import Deque, Dict, List, Literal, Optional
from zoneinfo import ZoneInfo

import aiohttp
import ccxt.async_support as ccxt
import feedparser
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# 1. 全域設定（可依需求調整）
# ---------------------------------------------------------------------------

MAJOR_SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]  # 固定監控的核心資產

SCAN_UNIVERSE_SIZE = 40                 # 市場掃描名單抓幾檔（依24h成交量排序取前N）
SCAN_UNIVERSE_REFRESH_SECONDS = 2700    # 掃描名單多久重新排名一次（45分鐘）
SCAN_CYCLE_TICKS = 6                    # 整份掃描名單大約每幾個 tick 完整輪過一次

# BingX 除了真的加密貨幣永續合約，還上架了一批用「NC」開頭命名的代幣化合成商品
# （NCCO=大宗商品如黃金原油、NCFX=外匯、NCSI=股票指數、NCSK=個股如 AAPL/TSLA），
# 這些不是加密貨幣，但成交量可能很高，會混進「依24h成交量排名」的掃描名單，
# 汙染掉這個功能本來要掃的東西，所以用底層代碼(base)前綴直接排除。
NON_CRYPTO_BASE_PREFIXES = ("NCCO", "NCFX", "NCSI", "NCSK")

TIMEFRAME = "4h"             # K 線週期（回測驗證用的就是 4 小時線，勿隨意改回更短週期）
CANDLE_LIMIT = 300           # 每次抓取的 K 線數量（需 > MA_SLOW_PERIOD）
TICK_INTERVAL_SECONDS = 10   # 即時報價/TP-SL監控頻率（秒）——這個不受K線週期影響，維持高頻
DEEP_SCAN_INTERVAL_SECONDS = 300  # K線+策略偵測頻率（秒）：4小時線沒必要每20秒就重算一次

DONCHIAN_PERIOD = 20         # 唐奇安通道週期（取過去N根K棒的最高/最低點，不含當根）
VOLUME_LOOKBACK = 20         # 成交量均值的計算週期
VOLUME_MULT = 2.0            # 當根成交量需 >= 均量的這個倍數，才算「帶量突破」

MA_FAST_PERIOD = 50          # 短期均線（趨勢過濾）
MA_SLOW_PERIOD = 200         # 長期均線（趨勢過濾）

ATR_PERIOD = 14              # ATR 週期
ATR_SL_MULTIPLIER = 1.5      # 止損 = ATR * 倍數
RISK_REWARD_RATIO = 2.0      # 止盈距離 = 止損距離 * 盈虧比

# 市場掃描名單裡的小幣種偶爾會出現真實的暴漲暴跌（例如短時間內腰斬），把 ATR
# 撐到跟進場價同個量級，此時止損距離會超過100%、止盈價甚至會被減成負數（一個
# 不可能達成的目標，因為真實價格不可能是負的）。這個門檻在 ATR 模型算出的止損
# 距離「本身」超過進場價的這個百分比時，直接視為這隻幣現在太不正常、不產生訊號，
# 比事後才發現止盈是負的、部位卡住永遠平不了倉安全。
MAX_SANE_STOP_LOSS_PCT = 50.0

FIXED_RISK_PCT = 15.0        # 固定風險模型：單筆爆倉風險目標百分比
MIN_LEVERAGE = 1
MAX_LEVERAGE = 20

HISTORY_MAX_LEN = 50         # /api/history 保留的歷史訊號筆數（多標的後拉高一點）

EXCHANGE_CANDIDATES = ["bingx", "binance", "okx"]  # bingx 排最前面：使用者實際在此交易所下單，
                                                    # 價格應以此為準；binance/okx 當備援。皆不需 API Key

# --- 聰明錢模塊（合約數據）設定 ---
SMART_MONEY_REFRESH_SECONDS = 300   # 主流幣資金費率/OI/大戶多空比 更新頻率（5分鐘一次）
OI_HISTORY_LEN = 6                  # 搭配上面頻率，保留最近 30 分鐘的 OI 快照

FUNDING_RATE_HIGH = 0.0005    # 資金費率 >= 0.05%：多方擁擠過熱，否決新的 Long
FUNDING_RATE_LOW = -0.0005    # 資金費率 <= -0.05%：空方擁擠過熱，否決新的 Short

TOP_TRADER_RATIO_BULLISH = 1.3   # 大戶多空比 >= 1.3：大戶明顯偏多，否決新的 Short
TOP_TRADER_RATIO_BEARISH = 1 / 1.3  # 大戶多空比 <= 0.77：大戶明顯偏空，否決新的 Long

OI_CHANGE_SIGNIFICANT_PCT = 2.0  # 未平倉量變化超過此百分比才視為有意義（僅供參考，不做否決）

# --- 迷因幣雷達（獨立模塊，不影響上面主流幣策略的邏輯與資料流） ---
# 這是純粹的「爆量警報」，不是交易訊號：沒有 TP/SL、沒有槓桿計算，只回報
# 「哪個幣現在成交量異常放大」。用現貨（不是合約），因為只是要看資金關注度，
# 不需要合約才有的槓桿/爆倉概念。
MEME_SYMBOLS = ["PEPE/USDT", "WIF/USDT", "DOGE/USDT"]
MEME_TIMEFRAME = "1h"
MEME_CANDLE_LIMIT = 50          # 24小時均量 + 緩衝，50根1小時K棒足夠
MEME_VOLUME_LOOKBACK = 24       # 過去24根（=24小時）K棒的平均成交量當基準
MEME_VOLUME_SPIKE_MULT = 3.0    # 當根成交量 >= 24小時均量的這個倍數 -> 觸發爆量警報
MEME_SCAN_INTERVAL_SECONDS = 60 # 迷因雷達多久檢查一次；比主策略頻繁，因為量能可能瞬間爆發
MEME_ALERT_HISTORY_MAX_LEN = 30 # /api/memes 保留的歷史警報筆數

# --- 美股當沖 ORB（Opening Range Breakout，獨立模塊，實驗性策略）---
# ⚠️ 這是使用者直接指定的策略邏輯（開盤區間突破 + RVOL 過濾 + 大盤濾網），
# 跟上面主流幣的 4h 唐奇安策略不同：那個經過近1年+前1年樣本外回測才上線，
# 這個目前完全沒有回測過，勝率未知，純粹照規格實作，請勿依賴其結果重倉交易。
# 標的是 BingX 的代幣化美股永續合約商品（NCSK 開頭），24 小時都能報價，
# 但 ORB 策略邏輯只在真正的美股交易時段內運作。
US_STOCK_SYMBOLS: Dict[str, str] = {
    "TSLA": "NCSKTSLA2USD/USDT:USDT",
    "NVDA": "NCSKNVDA2USD/USDT:USDT",
    "MSTR": "NCSKMSTR2USD/USDT:USDT",
    "SOXL": "NCSKSOXL2USD/USDT:USDT",
    "TQQQ": "NCSKTQQQ2USD/USDT:USDT",
}
US_STOCK_DISPLAY_BY_SYMBOL: Dict[str, str] = {v: k for k, v in US_STOCK_SYMBOLS.items()}

# 大盤濾網參考指數：那斯達克100代幣化指數商品（TQQQ/SOXL/NVDA 這幾檔跟科技股
# 大盤連動性高，用這個當代表；之後想換 SP500 只要改這個常數即可）
US_STOCK_REGIME_SYMBOL = "NCSINASDAQ1002USD/USDT:USDT"

US_STOCK_TIMEFRAME = "15m"
US_STOCK_TICKER_INTERVAL_SECONDS = 2     # 現價刷新頻率（秒）——當沖需要盯緊 TP/SL
US_STOCK_SCAN_INTERVAL_SECONDS = 60      # K線 + ORB 策略偵測頻率：15m線沒必要每2秒重算一次
US_STOCK_CLOSED_POLL_SECONDS = 300       # 非交易時段時，多久檢查一次「開盤了沒」
US_STOCK_OHLCV_LIMIT = 1000              # 約可抓到 10 天份 15m K線，供 RVOL 用「過去N個交易日同一時段」比較

US_MARKET_TZ = "America/New_York"
US_MARKET_OPEN = dt_time(9, 15)   # 背景迴圈的活動窗口（開盤前先暖機），不是正式開盤時間
US_MARKET_CLOSE = dt_time(16, 0)
ORB_RANGE_START = dt_time(9, 30)  # 開盤區間鎖定窗口：09:30-09:45（15m線的第一根收盤K棒）
ORB_RANGE_END = dt_time(9, 45)

ORB_RVOL_LOOKBACK_DAYS = 5   # RVOL 比較基準：過去幾個交易日的同一時段均量
ORB_RVOL_MULT = 3.5          # 突破當根15m成交量，需達過去N個交易日同一時段均量的這個倍數，才算量能確認
ORB_RISK_REWARD_RATIO = 2.0  # 止盈距離 = 止損距離（開盤區間寬度）* 這個倍數

US_STOCK_HISTORY_MAX_LEN = 30

# --- AI 智能投研 Agent（獨立模塊：RSS新聞 -> LLM結構化情緒分析 -> 跟現有部位比對
# 是否「技術面+情緒面共振」-> Telegram通知）---
# 資料來源用免費公開 RSS（不需註冊、不需API Key），涵蓋加密貨幣與美股新聞。
NEWS_RSS_FEEDS: Dict[str, str] = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "CoinTelegraph": "https://cointelegraph.com/rss",
    "Yahoo Finance": "https://finance.yahoo.com/news/rssindex",
    "CNBC Markets": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
}
NEWS_SCAN_INTERVAL_SECONDS = 600   # 10分鐘一次；LLM呼叫有實際費用，不需要抓太頻繁
NEWS_MAX_ITEMS_PER_SOURCE = 4      # 每個來源每輪最多送幾則新標題給LLM分析，避免單一來源（例如發文特別密集的
                                    # Yahoo Finance）洗版排擠掉其他來源，確保每輪都是四個來源雨露均霑
NEWS_SEEN_URL_MAX_LEN = 500        # 記住最近幾則新聞網址，避免重複分析、重複通知
NEWS_HISTORY_MAX_LEN = 60          # /api/ai-agent/news 保留的筆數
NEWS_RESONANCE_SCORE_THRESHOLD = 7 # 情緒分數 |score| >= 這個值，才算「強烈共振」

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip() or None
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()

# --- X（Twitter）自動發文：預留接口，目前未啟用 ---
# 之後申請到 X Developer 帳號、把這四個環境變數設好，post_to_x() 才會真的動作；
# 現在沒設定的話直接跳過，不影響任何其他功能。目前沒有任何呼叫端在用它。
X_API_KEY = os.environ.get("X_API_KEY", "").strip() or None
X_API_SECRET = os.environ.get("X_API_SECRET", "").strip() or None
X_ACCESS_TOKEN = os.environ.get("X_ACCESS_TOKEN", "").strip() or None
X_ACCESS_TOKEN_SECRET = os.environ.get("X_ACCESS_TOKEN_SECRET", "").strip() or None

# --- 落地紀錄（供之後統計用，跟 state.history / state.meme_alerts 這種
# 「只留最近N筆」的記憶體佇列不同，這裡是永久追加、不會被覆蓋掉的紀錄檔） ---
# 部署到雲端平台時，容器本身的檔案系統通常是「暫時性」的——重新部署、重啟
# 都可能被清空，一定要掛載一個持久化的硬碟（volume）並用 DATA_DIR 指到那個
# 路徑，不然狀態快照/紀錄檔案每次部署都會消失，等於persistence機制形同虛設。
# 本機開發不用設這個環境變數，預設沿用專案資料夾底下的 logs/。
LOG_DIR = os.environ.get("DATA_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
TRADE_LOG_PATH = os.path.join(LOG_DIR, "trade_log.jsonl")
MEME_ALERT_LOG_PATH = os.path.join(LOG_DIR, "meme_alert_log.jsonl")
US_STOCK_TRADE_LOG_PATH = os.path.join(LOG_DIR, "us_stock_trade_log.jsonl")
NEWS_LOG_PATH = os.path.join(LOG_DIR, "news_agent_log.jsonl")

# --- 狀態快照（讓伺服器重啟不會弄丟正在追蹤中的部位/歷史紀錄） ---
# 這是「快照」不是逐筆交易資料庫：定期把整個記憶體狀態的重點欄位存成一份
# JSON，啟動時讀回來。夠這個專案的規模用，不需要真的上資料庫。
STATE_SNAPSHOT_PATH = os.path.join(LOG_DIR, "state_snapshot.json")

# --- Telegram 推播（新訊號產生、訊號結算、迷因幣爆量時主動通知） ---
# 兩個環境變數都沒設時，推播功能整個跳過（不影響其他功能），本機開發預設
# 不用管這個。設定方式：跟 @BotFather 聊天建立一個 bot 拿到 TOKEN，
# 用該 bot 傳一句話給自己後查 getUpdates 拿到 CHAT_ID。
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() or None
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip() or None

# --- 測試用途 ---
# 設定環境變數 DEBUG_FORCE_SIGNAL=long（或 short）可以跳過策略偵測，
# 直接用當下即時價格生成一筆假訊號，方便在本地測試前端畫面，
# 不需要等布林通道真的突破。預設作用在 DEBUG_FORCE_SYMBOL（預設為第一個主流幣）。
# 正式環境請勿設定這個變數。
DEBUG_FORCE_SIGNAL = os.environ.get("DEBUG_FORCE_SIGNAL", "").strip().lower() or None
DEBUG_FORCE_SYMBOL = os.environ.get("DEBUG_FORCE_SYMBOL", "").strip() or MAJOR_SYMBOLS[0]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("trading_signal")


def append_jsonl(path: str, record: dict) -> None:
    """
    把一筆紀錄追加寫進本地 JSONL 檔（每行一筆 JSON），供之後離線統計勝率/
    爆量警報準確度用。純粹是稽核用的落地紀錄，跟記憶體裡的 state.history /
    state.meme_alerts（只留最近N筆、伺服器重啟就消失）是分開的兩件事。
    寫檔失敗只記警告、不拋例外，不能因為寫檔問題把背景迴圈搞掛。
    """
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.warning("寫入紀錄檔失敗（%s）：%s", path, exc)


async def send_telegram_message(text: str) -> None:
    """
    推播一則訊息到 Telegram。沒設定 TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID 時直接
    跳過。刻意設計成呼叫端絕對不能在持有 state.lock 時呼叫這個函式——它是一次
    真正的網路請求，扣著鎖去等外部服務回應，會卡住其他正在等鎖的 API 讀取請求。
    送失敗只記警告，不影響背景迴圈繼續運作。
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(
                url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning("Telegram 推播失敗（狀態碼 %s）：%s", resp.status, body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telegram 推播失敗：%s", exc)


# --- 背景迴圈連續失敗告警 ---
# 三支背景迴圈（主流幣/美股ORB/AI新聞）各自的例外處理都只會寫進 log，log 沒人在
# 半夜盯著看。這裡加一層「連續失敗達到門檻才推播一次告警」，而不是每次失敗都推播
# （偶發性的單次網路錯誤很常見，會洗版沒有意義）；失敗後只要成功一次就重置計數，
# 如果先前告警過，也會補推一則「已恢復」，這樣使用者才知道問題有沒有解決。
# 純粹是進程內的計數器，不碰 state.lock，也不需要跨重啟保留。
LOOP_FAILURE_ALERT_THRESHOLD = 3
_loop_failure_counts: Dict[str, int] = {}
_loop_alerted: Dict[str, bool] = {}


def _record_loop_outcome(loop_name: str, success: bool) -> Optional[str]:
    if success:
        was_alerted = _loop_alerted.get(loop_name, False)
        _loop_failure_counts[loop_name] = 0
        if was_alerted:
            _loop_alerted[loop_name] = False
            return f"✅ <b>背景迴圈已恢復</b>\n{loop_name} 重新開始正常運作"
        return None

    count = _loop_failure_counts.get(loop_name, 0) + 1
    _loop_failure_counts[loop_name] = count
    if count == LOOP_FAILURE_ALERT_THRESHOLD and not _loop_alerted.get(loop_name, False):
        _loop_alerted[loop_name] = True
        return (
            f"🚨 <b>背景迴圈連續失敗</b>\n{loop_name} 已連續失敗 {count} 次，"
            f"請檢查 Railway log 確認問題"
        )
    return None


# ---------------------------------------------------------------------------
# 2. Pydantic 回應模型
# ---------------------------------------------------------------------------

class SignalResponse(BaseModel):
    symbol: str
    status: Literal["OPEN", "NO_SIGNAL"]
    side: Optional[Literal["Long", "Short"]] = None
    entry_price: Optional[float] = None
    current_price: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    leverage: Optional[int] = None
    risk_reward_ratio: Optional[float] = None
    opened_at: Optional[str] = None
    smart_money_notes: List[str] = []
    updated_at: str

    # 監控用欄位：即使 status=NO_SIGNAL 也會填，讓前端在「沒有部位」時
    # 仍能顯示引擎目前實際算出來的東西（離突破多遠、量能倍數、聰明錢偏見），
    # 而不是一片空白。這些數值本來就是背景掃描的副產品，只是之前沒有暴露出來。
    donchian_upper: Optional[float] = None
    donchian_lower: Optional[float] = None
    volume_ratio: Optional[float] = None  # 當根成交量 / 近期均量
    funding_rate: Optional[float] = None
    top_trader_long_short_ratio: Optional[float] = None
    smart_money_bias: Optional[Literal["Bullish", "Bearish", "Neutral"]] = None


class SignalListResponse(BaseModel):
    universe: Literal["major", "scan"]
    signals: List[SignalResponse]
    updated_at: Optional[str] = None
    tracked_symbols: List[str] = []  # universe=scan 時回傳目前的掃描名單，證明引擎真的在追蹤這些幣


class HistoryItem(BaseModel):
    symbol: str
    side: Literal["Long", "Short"]
    entry_price: float
    exit_price: float
    take_profit: float
    stop_loss: float
    leverage: int
    result: Literal["WIN", "LOSS"]
    pnl_pct: float
    opened_at: str
    closed_at: str
    smart_money_notes: List[str] = []


class HistoryStats(BaseModel):
    total_trades: int
    wins: int
    losses: int
    win_rate_pct: float


class HistoryResponse(BaseModel):
    trades: List[HistoryItem]
    stats: HistoryStats


class SmartMoneyResponse(BaseModel):
    symbol: str
    funding_rate: Optional[float] = None
    open_interest_value: Optional[float] = None
    oi_change_pct: Optional[float] = None
    top_trader_long_short_ratio: Optional[float] = None
    bias: Literal["Bullish", "Bearish", "Neutral"]
    notes: List[str]
    updated_at: Optional[str] = None


class MemeAlertResponse(BaseModel):
    symbol: str
    volume_multiple: float   # 當根成交量是過去24小時均量的幾倍
    price: float
    triggered_at: str


class MemeWatchItem(BaseModel):
    """就算沒有爆量，也持續回報的即時監控快照——跟主流幣的 NO_SIGNAL 監控欄位同樣道理。"""

    symbol: str
    price: Optional[float] = None
    volume_multiple: Optional[float] = None
    updated_at: Optional[str] = None


class MemeRadarResponse(BaseModel):
    alerts: List[MemeAlertResponse]  # 依觸發時間新到舊排序
    watchlist: List[MemeWatchItem]   # 固定回傳 MEME_SYMBOLS 全部，不管有沒有警報
    updated_at: Optional[str] = None


class CandleResponse(BaseModel):
    timestamp: int  # unix 毫秒
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandlesListResponse(BaseModel):
    symbol: str
    timeframe: str
    candles: List[CandleResponse]


class USStockResponse(BaseModel):
    """美股 ORB 當沖：跟主流幣 SignalResponse 同樣的 OPEN/NO_SIGNAL 形狀，多了開盤區間/RVOL/大盤濾網欄位。"""

    symbol: str          # BingX 代幣化商品符號，如 NCSKTSLA2USD/USDT:USDT
    display_name: str    # 給前端顯示用的乾淨代號，如 TSLA
    status: Literal["OPEN", "NO_SIGNAL"]
    side: Optional[Literal["Long", "Short"]] = None
    entry_price: Optional[float] = None
    current_price: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    leverage: Optional[int] = None
    risk_reward_ratio: Optional[float] = None
    opened_at: Optional[str] = None
    day_change_pct: Optional[float] = None
    updated_at: str

    # ORB 監控用欄位：不管有沒有觸發訊號都會填，讓前端在「沒有部位」時也能畫
    # 開盤區間進度條、RVOL 數字卡、大盤偏向卡。
    opening_high: Optional[float] = None
    opening_low: Optional[float] = None
    rvol: Optional[float] = None
    market_regime: Literal["Bullish", "Bearish", "Neutral"] = "Neutral"


class USStockListResponse(BaseModel):
    market_session: Literal["OPEN", "CLOSED"]  # 現在是否在美股交易時段內（美東 09:15-16:00、週一到週五）
    market_regime: Literal["Bullish", "Bearish", "Neutral"]
    stocks: List[USStockResponse]
    updated_at: Optional[str] = None


class USStockHistoryItem(BaseModel):
    symbol: str
    display_name: str
    side: Literal["Long", "Short"]
    entry_price: float
    exit_price: float
    take_profit: float
    stop_loss: float
    leverage: int
    result: Literal["WIN", "LOSS"]
    pnl_pct: float
    opened_at: str
    closed_at: str


class USStockHistoryStats(BaseModel):
    total_trades: int
    wins: int
    losses: int
    win_rate_pct: float


class USStockHistoryResponse(BaseModel):
    # ⚠️ 這是「實盤累積結果」，不是回測——樣本數在累積起來之前很小，數字沒有
    # 統計意義，前端請務必標註清楚，不要讓人誤以為這是驗證過的勝率。
    trades: List[USStockHistoryItem]
    stats: USStockHistoryStats


class NewsItemResponse(BaseModel):
    title: str
    url: str
    source: str
    published_at: str
    symbols: List[str]       # LLM 從新聞內容判斷出的可交易標的代號，如 ["TSLA","BTC"]
    summary: str              # LLM 產生的一句話摘要
    sentiment_score: int      # -10（極度利空）~ +10（極度利多）
    processed_at: str


class NewsAgentResponse(BaseModel):
    items: List[NewsItemResponse]  # 依處理時間新到舊排序
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# 3. 全域狀態（背景任務寫入，API 讀取）
# ---------------------------------------------------------------------------

class SymbolState:
    """單一標的的即時狀態：目前部位、即時價格、聰明錢快取。"""

    def __init__(self) -> None:
        self.open_signal: Optional[dict] = None
        self.current_price: Optional[float] = None
        self.smart_money: Optional[dict] = None
        self.oi_history: Deque[float] = deque(maxlen=OI_HISTORY_LEN)
        self.last_smart_money_fetch: float = 0.0  # time.monotonic() 時間戳
        self.last_updated: Optional[str] = None

        # 監控快照：每次深度掃描（不論有沒有觸發訊號）都會更新，
        # 讓「沒有部位」時前端也能顯示離突破多遠、量能倍數。
        self.donchian_upper: Optional[float] = None
        self.donchian_lower: Optional[float] = None
        self.volume_ratio: Optional[float] = None


class MemeAlertState:
    """單一迷因幣的雷達狀態：只追蹤成交量是否異常放大，跟交易部位無關。"""

    def __init__(self) -> None:
        self.current_price: Optional[float] = None
        self.volume_multiple: Optional[float] = None
        self.alert_active: bool = False  # 目前是否處於「爆量中」，避免同一次爆量重複記錄警報
        self.last_updated: Optional[str] = None


class USStockState:
    """單一美股代幣化商品的 ORB 當沖狀態：開盤區間、RVOL、部位，跟主流幣的 symbols 完全分開。"""

    def __init__(self) -> None:
        self.current_price: Optional[float] = None
        self.day_change_pct: Optional[float] = None
        self.opening_high: Optional[float] = None
        self.opening_low: Optional[float] = None
        self.rvol: Optional[float] = None
        self.market_regime: Literal["Bullish", "Bearish", "Neutral"] = "Neutral"
        self.open_signal: Optional[dict] = None
        self.triggered_date: Optional[str] = None  # 今天（美東時區日期）是否已觸發過訊號，避免同一天反覆進出
        self.last_updated: Optional[str] = None


class AppState:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.symbols: Dict[str, SymbolState] = {}
        self.history: Deque[dict] = deque(maxlen=HISTORY_MAX_LEN)
        self.active_exchange_name: str = EXCHANGE_CANDIDATES[0]

        self.scan_universe: List[str] = []
        self.last_scan_universe_refresh: float = 0.0
        self.scan_cursor: int = 0

        self.last_tick_at: Optional[str] = None
        self.last_deep_scan_at: float = 0.0  # time.monotonic() 時間戳

        # 迷因幣雷達（獨立狀態，跟主流幣的 symbols/history 完全分開）
        self.meme_states: Dict[str, MemeAlertState] = {}
        self.meme_alerts: Deque[dict] = deque(maxlen=MEME_ALERT_HISTORY_MAX_LEN)
        self.last_meme_scan_at: float = 0.0  # time.monotonic() 時間戳

        # 美股 ORB 當沖（獨立狀態，跟上面兩組完全分開；市場濾網是全域共用一份，
        # 不是逐檔各自算，因為所有標的都拿同一個大盤指數當濾網）
        self.us_stock_states: Dict[str, USStockState] = {}
        self.us_stock_history: Deque[dict] = deque(maxlen=US_STOCK_HISTORY_MAX_LEN)
        self.us_market_regime: Literal["Bullish", "Bearish", "Neutral"] = "Neutral"

        # AI 智能投研 Agent（獨立狀態，跟上面所有模塊完全分開，只在偵測到共振時
        # 才會去「讀」其他模塊的 open_signal，不會反過來被其他模塊碰）
        self.news_items: Deque[dict] = deque(maxlen=NEWS_HISTORY_MAX_LEN)
        self.seen_news_urls: Deque[str] = deque(maxlen=NEWS_SEEN_URL_MAX_LEN)
        self.last_news_scan_at: float = 0.0  # time.monotonic() 時間戳

    def get_meme_state(self, symbol: str) -> MemeAlertState:
        if symbol not in self.meme_states:
            self.meme_states[symbol] = MemeAlertState()
        return self.meme_states[symbol]

    def get_symbol_state(self, symbol: str) -> SymbolState:
        if symbol not in self.symbols:
            self.symbols[symbol] = SymbolState()
        return self.symbols[symbol]

    def get_us_stock_state(self, symbol: str) -> USStockState:
        if symbol not in self.us_stock_states:
            self.us_stock_states[symbol] = USStockState()
        return self.us_stock_states[symbol]


state = AppState()

# 給 /api/candles 這種「按需查詢」的路由用：背景迴圈的 exchange_pool 是在
# lifespan() 裡建立的區域變數，路由處理函式碰不到，所以在 lifespan 啟動時
# 把參照存一份到這裡。
exchange_pool_ref: Dict[str, object] = {}


# ---------------------------------------------------------------------------
# 4. 技術指標計算（純 pandas 實作，避免額外依賴 ta-lib）
# ---------------------------------------------------------------------------

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """在 K 線 DataFrame 上計算唐奇安通道、成交量均值、雙均線、ATR，回傳新增欄位後的 df。"""
    df = df.copy()

    # 唐奇安通道：過去 N 根K棒的最高/最低點，shift(1) 是為了不含當根，避免用到未來資訊
    df["donchian_upper"] = df["high"].rolling(DONCHIAN_PERIOD).max().shift(1)
    df["donchian_lower"] = df["low"].rolling(DONCHIAN_PERIOD).min().shift(1)

    # 成交量均值：用來判斷當根是否「帶量」
    df["avg_volume"] = df["volume"].rolling(VOLUME_LOOKBACK).mean()

    # 雙均線（趨勢過濾）
    df["ma_fast"] = df["close"].rolling(MA_FAST_PERIOD).mean()
    df["ma_slow"] = df["close"].rolling(MA_SLOW_PERIOD).mean()

    # ATR（真實波幅）
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr"] = tr.rolling(ATR_PERIOD).mean()

    return df


def calculate_leverage(stop_loss_pct: float) -> int:
    """
    固定風險模型：leverage = floor(固定風險% / 止損距離%)，並限制在 [MIN, MAX] 之間。
    止損距離 1.5% -> floor(15/1.5)=10 倍
    止損距離 4%   -> floor(15/4)=3 倍
    """
    if stop_loss_pct <= 0:
        return MIN_LEVERAGE
    raw_leverage = floor(FIXED_RISK_PCT / stop_loss_pct)
    return max(MIN_LEVERAGE, min(MAX_LEVERAGE, raw_leverage))


def detect_new_signal(df: pd.DataFrame) -> Optional[dict]:
    """
    唐奇安通道突破 + 成交量確認：最新已收盤K棒的收盤價突破過去 N 根的高/低點，
    且當根成交量需放大到均量的 VOLUME_MULT 倍以上，方向還要跟雙均線趨勢一致，
    才視為有效訊號（跟 backtest_htf.py 驗證過的邏輯完全一致）。
    回傳 dict：{side, entry_price, atr} 或 None。
    """
    min_len = max(MA_SLOW_PERIOD, DONCHIAN_PERIOD, VOLUME_LOOKBACK, ATR_PERIOD) + 2
    if len(df) < min_len:
        return None  # 資料不足以計算指標

    last = df.iloc[-1]

    if last[["donchian_upper", "donchian_lower", "avg_volume", "ma_fast", "ma_slow", "atr"]].isna().any():
        return None

    uptrend = last["ma_fast"] > last["ma_slow"]
    downtrend = last["ma_fast"] < last["ma_slow"]
    volume_confirmed = last["volume"] > last["avg_volume"] * VOLUME_MULT

    long_breakout = last["close"] > last["donchian_upper"] and volume_confirmed
    short_breakout = last["close"] < last["donchian_lower"] and volume_confirmed

    entry_price = float(last["close"])
    atr = float(last["atr"])

    # 防呆：ATR 算出來的止損距離本身就先超過進場價的 MAX_SANE_STOP_LOSS_PCT，
    # 代表這隻幣現在處於不正常的暴漲暴跌，不適合套用這套風險模型，直接不產生訊號
    # （細節見 MAX_SANE_STOP_LOSS_PCT 定義處的說明）。
    projected_sl_pct = (atr * ATR_SL_MULTIPLIER) / entry_price * 100 if entry_price > 0 else float("inf")
    if projected_sl_pct > MAX_SANE_STOP_LOSS_PCT:
        return None

    if long_breakout and uptrend:
        return {"side": "Long", "entry_price": entry_price, "atr": atr}
    if short_breakout and downtrend:
        return {"side": "Short", "entry_price": entry_price, "atr": atr}
    return None


def build_open_signal(symbol: str, signal: dict, smart_money_notes: Optional[List[str]] = None) -> dict:
    """依訊號方向與 ATR 計算 TP / SL / 槓桿，組成完整的 open_signal 物件。"""
    side = signal["side"]
    entry_price = signal["entry_price"]
    atr = signal["atr"]

    sl_distance = atr * ATR_SL_MULTIPLIER
    tp_distance = sl_distance * RISK_REWARD_RATIO

    if side == "Long":
        stop_loss = entry_price - sl_distance
        take_profit = entry_price + tp_distance
    else:  # Short
        stop_loss = entry_price + sl_distance
        take_profit = entry_price - tp_distance

    stop_loss_pct = abs(entry_price - stop_loss) / entry_price * 100
    leverage = calculate_leverage(stop_loss_pct)

    return {
        "symbol": symbol,
        "side": side,
        "entry_price": entry_price,
        "take_profit": take_profit,
        "stop_loss": stop_loss,
        "stop_loss_pct": stop_loss_pct,
        "leverage": leverage,
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "smart_money_notes": smart_money_notes or [],
    }


# ---------------------------------------------------------------------------
# 5. 交易所存取（含 Binance -> OKX 自動備援）
# ---------------------------------------------------------------------------

def make_exchange(name: str):
    exchange_class = getattr(ccxt, name)
    return exchange_class(
        {
            "enableRateLimit": True,
            "timeout": 20000,
            # 只載入合約(swap)市場：OKX 預設會一次載入 SPOT/SWAP/FUTURES/OPTION
            # 全部市場資料，資料量大且較慢，容易在 load_markets() 階段逾時；
            # 而我們的策略與聰明錢數據本來就都是合約市場，只載入 swap 剛好。
            "options": {"defaultType": "swap"},
        }
    )


def get_market_id(exchange, symbol: str) -> str:
    """將 ccxt 統一符號（如 BTC/USDT:USDT）轉成該交易所原生的市場代碼。"""
    return exchange.market(symbol)["id"]


def _exchange_order() -> List[str]:
    """目前 active 交易所優先，其餘候補交易所排在後面，用於備援重試。"""
    return [state.active_exchange_name] + [
        n for n in EXCHANGE_CANDIDATES if n != state.active_exchange_name
    ]


async def fetch_ohlcv_for_symbol(
    exchange_pool: dict, symbol: str, timeframe: str = TIMEFRAME, limit: int = CANDLE_LIMIT
) -> pd.DataFrame:
    """
    抓取單一標的的已收盤 K 線，依序嘗試各交易所，成功後切換為 active。
    timeframe/limit 預設沿用主流幣策略的設定，迷因幣雷達等其他模塊可以自行傳入。
    """
    last_error: Optional[Exception] = None
    for name in _exchange_order():
        exchange = exchange_pool[name]
        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            # 最後一根通常是尚未收盤的「進行中」K棒，訊號判斷只採用已收盤資料
            closed_df = df.iloc[:-1].reset_index(drop=True)

            if name != state.active_exchange_name:
                logger.warning("交易所 %s 失敗，已切換至 %s", state.active_exchange_name, name)
                state.active_exchange_name = name

            return closed_df
        except Exception as exc:  # noqa: BLE001 - 交易所來源錯誤型別眾多，統一捕捉後續嘗試備援
            last_error = exc
            continue

    raise RuntimeError(f"所有交易所皆抓取失敗（{symbol}）：{last_error}")


async def fetch_tickers_batch(exchange_pool: dict, symbols: List[str]) -> Dict[str, float]:
    """
    一次批次抓取多個標的的即時價格（單一 API 呼叫），依序嘗試各交易所備援。
    不是每個交易所都上架追蹤名單裡的每一檔（例如某些代幣化商品只有單一交易所
    才有），所以查詢前先篩掉該交易所沒有的標的，避免一檔查不到就讓整批連帶失敗。
    """
    if not symbols:
        return {}

    last_error: Optional[Exception] = None
    for name in _exchange_order():
        exchange = exchange_pool[name]
        if not exchange.markets:
            continue  # 該交易所市場資料尚未載入成功（例如地區限制），跳過改用備援

        available_symbols = [s for s in symbols if s in exchange.markets]
        missing_symbols = set(symbols) - set(available_symbols)
        if missing_symbols:
            logger.warning("交易所 %s 沒有以下追蹤標的，本輪跳過：%s", name, missing_symbols)
        if not available_symbols:
            continue

        try:
            tickers = await exchange.fetch_tickers(available_symbols)
            prices = {
                sym: float(ticker["last"])
                for sym, ticker in tickers.items()
                if ticker.get("last") is not None
            }

            if name != state.active_exchange_name:
                logger.warning("交易所 %s 失敗，已切換至 %s", state.active_exchange_name, name)
                state.active_exchange_name = name

            return prices
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue

    raise RuntimeError(f"所有交易所批次報價皆抓取失敗：{last_error}")


# ---------------------------------------------------------------------------
# 6. 聰明錢模塊（合約：資金費率 / 未平倉量 / 大戶多空比）
# ---------------------------------------------------------------------------

async def fetch_top_trader_ratio(exchange, exchange_name: str, market_id: str) -> Optional[float]:
    """
    大戶持倉多空比並非 ccxt 統一 API，需呼叫各交易所的底層 implicit endpoint
    （皆為「依持倉量加權」版本，而非單純帳戶數量，較能反映真實資金方向）：
      - Binance USDT本位合約：fapiData GET topLongShortPositionRatio
      - OKX：rubik/stat/contracts/long-short-position-ratio-contract-top-trader
    需要 ccxt >= 4.5.0（舊版 OKX 底層尚未提供這組 implicit endpoint）。
    任一交易所回傳格式若未來調整，這裡會直接拋例外，由呼叫端 try/except 吞掉並記錄。
    """
    if exchange_name == "binance":
        raw = await exchange.fapiDataGetTopLongShortPositionRatio(
            {"symbol": market_id, "period": "15m", "limit": 1}
        )
        return float(raw[-1]["longShortRatio"])

    if exchange_name == "okx":
        raw = await exchange.publicGetRubikStatContractsLongShortPositionRatioContractTopTrader(
            {"instId": market_id, "period": "5m"}
        )
        data = raw.get("data") or []
        return float(data[0][1])

    return None


async def fetch_smart_money_snapshot(exchange, exchange_name: str, symbol: str) -> dict:
    """
    抓取資金費率 / 未平倉量 / 大戶多空比。三者互相獨立 try/except，
    任一個失敗都不影響其他兩個，缺值時對應欄位維持 None。
    """
    snapshot = {
        "funding_rate": None,
        "open_interest_value": None,
        "top_trader_long_short_ratio": None,
    }

    try:
        funding = await exchange.fetch_funding_rate(symbol)
        snapshot["funding_rate"] = funding.get("fundingRate")
    except Exception as exc:  # noqa: BLE001
        logger.warning("抓取資金費率失敗（%s / %s）：%s", symbol, exchange_name, exc)

    try:
        oi = await exchange.fetch_open_interest(symbol)
        snapshot["open_interest_value"] = oi.get("openInterestValue") or oi.get("openInterestAmount")
    except Exception as exc:  # noqa: BLE001
        logger.warning("抓取未平倉量失敗（%s / %s）：%s", symbol, exchange_name, exc)

    try:
        market_id = get_market_id(exchange, symbol)
        snapshot["top_trader_long_short_ratio"] = await fetch_top_trader_ratio(
            exchange, exchange_name, market_id
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("抓取大戶多空比失敗（%s / %s）：%s", symbol, exchange_name, exc)

    return snapshot


def compute_oi_change_pct(oi_history: Deque[float]) -> Optional[float]:
    """比較目前 OI 與 OI_HISTORY_LEN 筆之前（約 30 分鐘前）的 OI，回傳變化百分比。"""
    if len(oi_history) < 2 or oi_history[0] in (None, 0):
        return None
    oldest, latest = oi_history[0], oi_history[-1]
    if oldest is None or latest is None:
        return None
    return (latest - oldest) / oldest * 100


def evaluate_smart_money_bias(
    funding_rate: Optional[float],
    top_trader_ratio: Optional[float],
    oi_change_pct: Optional[float],
) -> dict:
    """
    將三項合約數據整合成方向偏見與否決旗標：
      - veto_long / veto_short：技術面觸發訊號時，是否要被聰明錢數據否決
      - bias：僅供顯示參考的整體偏多/偏空/中性標籤
    否決條件刻意設得保守（只在明顯衝突時否決），避免過度濾掉本來就不多的訊號。
    """
    notes: List[str] = []
    veto_long = False
    veto_short = False
    bias: Literal["Bullish", "Bearish", "Neutral"] = "Neutral"

    if funding_rate is not None:
        if funding_rate >= FUNDING_RATE_HIGH:
            notes.append(f"資金費率偏高（{funding_rate * 100:.3f}%），多方擁擠過熱，不追多")
            veto_long = True
        elif funding_rate <= FUNDING_RATE_LOW:
            notes.append(f"資金費率偏低（{funding_rate * 100:.3f}%），空方擁擠過熱，不追空")
            veto_short = True

    if top_trader_ratio is not None:
        if top_trader_ratio >= TOP_TRADER_RATIO_BULLISH:
            notes.append(f"大戶多空比 {top_trader_ratio:.2f}，大戶明顯偏多")
            veto_short = True
            bias = "Bullish"
        elif top_trader_ratio <= TOP_TRADER_RATIO_BEARISH:
            notes.append(f"大戶多空比 {top_trader_ratio:.2f}，大戶明顯偏空")
            veto_long = True
            bias = "Bearish"

    if oi_change_pct is not None:
        if oi_change_pct >= OI_CHANGE_SIGNIFICANT_PCT:
            notes.append(f"未平倉量上升 {oi_change_pct:.2f}%，資金持續進場")
        elif oi_change_pct <= -OI_CHANGE_SIGNIFICANT_PCT:
            notes.append(f"未平倉量下降 {oi_change_pct:.2f}%，可能是平倉/回補而非新趨勢")

    return {"bias": bias, "notes": notes, "veto_long": veto_long, "veto_short": veto_short}


# ---------------------------------------------------------------------------
# 6.5 迷因幣雷達模塊（獨立於上面的主流幣策略，不共用訊號/部位邏輯）
# ---------------------------------------------------------------------------

def compute_volume_snapshot(df: pd.DataFrame) -> Optional[dict]:
    """
    計算最新已收盤K棒的成交量，是過去 MEME_VOLUME_LOOKBACK 根（不含當根）
    平均成交量的幾倍。不論有沒有達到爆量門檻都會回傳，這樣前端才能顯示
    「現在幾倍、離門檻還差多少」，而不是只有爆量當下才有數字。
    """
    if len(df) < MEME_VOLUME_LOOKBACK + 2:
        return None  # 資料不足

    last = df.iloc[-1]
    baseline_window = df["volume"].iloc[-(MEME_VOLUME_LOOKBACK + 1):-1]  # 不含當根，避免自己墊高自己的基準
    avg_volume_24h = baseline_window.mean()

    if pd.isna(avg_volume_24h) or avg_volume_24h <= 0:
        return None

    volume_multiple = last["volume"] / avg_volume_24h
    return {"volume_multiple": float(volume_multiple), "price": float(last["close"])}


async def scan_meme_radar(exchange_pool: dict) -> None:
    """
    對每個迷因幣抓取 1 小時 K 線，檢查成交量是否爆量。用「邊緣觸發」邏輯：
    只有從「未警報」變成「警報中」的那一刻才會記錄一筆新警報，避免同一次
    爆量在還沒消退前，每次掃描都重複記錄。
    """
    for symbol in MEME_SYMBOLS:
        try:
            closed_df = await fetch_ohlcv_for_symbol(
                exchange_pool, symbol, timeframe=MEME_TIMEFRAME, limit=MEME_CANDLE_LIMIT
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("迷因幣K線抓取失敗（%s）：%s", symbol, exc)
            continue

        snapshot = compute_volume_snapshot(closed_df)
        is_spike = snapshot is not None and snapshot["volume_multiple"] >= MEME_VOLUME_SPIKE_MULT

        new_alert: Optional[dict] = None
        async with state.lock:
            meme_state = state.get_meme_state(symbol)
            if snapshot is not None:
                meme_state.current_price = snapshot["price"]
                meme_state.volume_multiple = snapshot["volume_multiple"]
            meme_state.last_updated = datetime.now(timezone.utc).isoformat()

            if is_spike:
                if not meme_state.alert_active:
                    meme_state.alert_active = True
                    triggered_at = datetime.now(timezone.utc).isoformat()
                    alert_record = {
                        "symbol": symbol,
                        "volume_multiple": snapshot["volume_multiple"],
                        "price": snapshot["price"],
                        "triggered_at": triggered_at,
                    }
                    state.meme_alerts.appendleft(alert_record)
                    append_jsonl(MEME_ALERT_LOG_PATH, alert_record)
                    logger.warning(
                        "🚨 迷因幣爆量警報：%s 成交量達24h均量 %.1f 倍 @ %.8f",
                        symbol,
                        snapshot["volume_multiple"],
                        snapshot["price"],
                    )
                    new_alert = alert_record
            else:
                meme_state.alert_active = False  # 量能回落，重置狀態，下次再爆量才會算新警報

        # 推播放在鎖外面，理由同 run_tick
        if new_alert is not None:
            await send_telegram_message(
                f"🚨 <b>迷因幣爆量</b>\n{new_alert['symbol']}\n"
                f"成交量達24h均量 {new_alert['volume_multiple']:.1f} 倍\n"
                f"價格：{new_alert['price']:.8f}"
            )


# ---------------------------------------------------------------------------
# 6.6 美股 ORB 當沖模塊（獨立模塊，實驗性策略，未經回測驗證）
# ---------------------------------------------------------------------------

def _is_us_market_active(now_et: datetime) -> bool:
    """判斷現在（美東時間）是否落在背景迴圈的活動窗口內：週一到週五、09:15-16:00。"""
    if now_et.weekday() >= 5:  # 5=Sat, 6=Sun
        return False
    return US_MARKET_OPEN <= now_et.time() <= US_MARKET_CLOSE


async def refresh_us_market_regime(exchange_pool: dict) -> None:
    """
    大盤濾網：抓大盤指數（預設那斯達克100代幣化商品）的 15m K 線，用短/長均線
    交叉判斷趨勢，或用「是否突破前一根K棒高低點」當輔助訊號，兩者任一成立即可
    判定方向；兩者矛盾時視為中性。這是策略濾網用的簡化定義，不是嚴謹的大盤
    強弱指標，跟主流幣策略的雙均線濾網是同樣的簡化精神。
    """
    try:
        df = await fetch_ohlcv_for_symbol(
            exchange_pool, US_STOCK_REGIME_SYMBOL, timeframe=US_STOCK_TIMEFRAME, limit=60
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("大盤濾網K線抓取失敗：%s", exc)
        return

    if len(df) < 22:
        return

    ma_fast = df["close"].rolling(9).mean().iloc[-1]
    ma_slow = df["close"].rolling(21).mean().iloc[-1]
    last = df.iloc[-1]
    prev = df.iloc[-2]

    bullish = bool(ma_fast > ma_slow or last["close"] > prev["high"])
    bearish = bool(ma_fast < ma_slow or last["close"] < prev["low"])

    if bullish and not bearish:
        regime: Literal["Bullish", "Bearish", "Neutral"] = "Bullish"
    elif bearish and not bullish:
        regime = "Bearish"
    else:
        regime = "Neutral"

    async with state.lock:
        state.us_market_regime = regime


def build_us_stock_open_signal(display_name: str, ticker_symbol: str, candidate: dict) -> dict:
    """
    ORB 的 TP/SL 邏輯跟主流幣的 ATR 模型不同，是這個策略的標準做法，且 Long/Short
    的停損邏輯不對稱（使用者指定）：
      - Long 停損 = 開盤區間低點（區間另一側整個寬度）。
      - Short 停損 = max(開盤區間半線 50%, 當日最高點)：預設用區間中點當作比較
        緊的停損，但如果當天稍早已經衝到比中點更高的價位，代表那個高點才是
        真正該防守的失效位置，改用那個當日最高點，停損不會比它更緊。
    停利距離 = 停損距離 * ORB_RISK_REWARD_RATIO。槓桿沿用主流幣同一套固定風險模型。
    """
    side = candidate["side"]
    entry_price = candidate["entry_price"]
    opening_high = candidate["opening_high"]
    opening_low = candidate["opening_low"]

    if side == "Long":
        stop_loss = opening_low
        sl_distance = entry_price - stop_loss
        take_profit = entry_price + sl_distance * ORB_RISK_REWARD_RATIO
    else:  # Short
        range_mid = (opening_high + opening_low) / 2
        day_high_so_far = candidate.get("day_high_so_far", opening_high)
        stop_loss = max(range_mid, day_high_so_far)
        sl_distance = stop_loss - entry_price
        take_profit = entry_price - sl_distance * ORB_RISK_REWARD_RATIO

    stop_loss_pct = abs(entry_price - stop_loss) / entry_price * 100
    leverage = calculate_leverage(stop_loss_pct)

    return {
        "symbol": ticker_symbol,
        "display_name": display_name,
        "side": side,
        "entry_price": entry_price,
        "take_profit": take_profit,
        "stop_loss": stop_loss,
        "stop_loss_pct": stop_loss_pct,
        "leverage": leverage,
        "opened_at": datetime.now(timezone.utc).isoformat(),
    }


async def scan_us_stock_orb(exchange_pool: dict, display_name: str, ticker_symbol: str) -> None:
    """
    單一美股代幣化商品的 ORB（Opening Range Breakout）偵測：
      1. 鎖定當天開盤區間（美東 09:30-09:45，15m線的第一根收盤K棒）的高/低點。
      2. 區間鎖定後，後續每根15m K棒收盤若突破區間高/低點，且該根成交量達
         「過去 ORB_RVOL_LOOKBACK_DAYS 個交易日同一時段均量」的 ORB_RVOL_MULT
         倍以上（RVOL 過濾），且大盤濾網方向一致，才視為有效訊號。
      3. 同一天（美東時區）只觸發一次，避免區間邊緣反覆插針造成連續進出。

    ⚠️ 使用者直接指定的實驗性策略，沒有經過回測驗證，勝率未知。
    """
    async with state.lock:
        st = state.get_us_stock_state(ticker_symbol)
        if st.open_signal is not None:
            return  # 已有部位，TP/SL 由 ticker 迴圈另外監控，這裡不重複偵測新訊號

    try:
        df = await fetch_ohlcv_for_symbol(
            exchange_pool, ticker_symbol, timeframe=US_STOCK_TIMEFRAME, limit=US_STOCK_OHLCV_LIMIT
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("美股K線抓取失敗（%s）：%s", display_name, exc)
        return

    if df.empty:
        return

    tz = ZoneInfo(US_MARKET_TZ)
    df = df.copy()
    df["et_time"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_convert(tz)
    df["et_date"] = df["et_time"].dt.date
    df["et_hm"] = df["et_time"].dt.strftime("%H:%M")

    now_et = datetime.now(tz)
    today_et = now_et.date()
    today_df = df[df["et_date"] == today_et]

    last_row = df.iloc[-1]
    first_today_close = today_df.iloc[0]["close"] if not today_df.empty else None
    day_change_pct = (
        float((last_row["close"] - first_today_close) / first_today_close * 100)
        if first_today_close
        else None
    )

    range_candle = today_df[today_df["et_hm"] == ORB_RANGE_START.strftime("%H:%M")]

    if range_candle.empty:
        # 今天的開盤區間K棒還沒收盤（例如剛開盤還不到09:45），先只更新現價相關欄位
        async with state.lock:
            s = state.get_us_stock_state(ticker_symbol)
            s.day_change_pct = day_change_pct
            s.last_updated = datetime.now(timezone.utc).isoformat()
        return

    opening_high = float(range_candle.iloc[0]["high"])
    opening_low = float(range_candle.iloc[0]["low"])
    if opening_high <= opening_low:
        return  # 開盤區間寬度異常（理論上不會發生），跳過這輪

    breakout_candidates = today_df[today_df["et_time"].dt.time > ORB_RANGE_END]
    if breakout_candidates.empty:
        async with state.lock:
            s = state.get_us_stock_state(ticker_symbol)
            s.opening_high = opening_high
            s.opening_low = opening_low
            s.day_change_pct = day_change_pct
            s.last_updated = datetime.now(timezone.utc).isoformat()
        return

    last_candle = breakout_candidates.iloc[-1]

    # RVOL：過去 N 個「平日」同一時段（同樣的 et_hm，排除今天、排除週末雜訊資料）的均量
    same_slot = df[(df["et_hm"] == last_candle["et_hm"]) & (df["et_date"] != today_et)]
    same_slot = same_slot[pd.to_datetime(same_slot["et_date"]).dt.dayofweek < 5]
    recent_slot_volumes = same_slot.sort_values("et_date").tail(ORB_RVOL_LOOKBACK_DAYS)["volume"]
    avg_slot_volume = float(recent_slot_volumes.mean()) if len(recent_slot_volumes) > 0 else None
    rvol = (
        float(last_candle["volume"]) / avg_slot_volume
        if avg_slot_volume and avg_slot_volume > 0
        else None
    )

    async with state.lock:
        regime = state.us_market_regime

    volume_confirmed = rvol is not None and rvol >= ORB_RVOL_MULT
    long_breakout = last_candle["close"] > opening_high
    short_breakout = last_candle["close"] < opening_low

    candidate: Optional[dict] = None
    if long_breakout and volume_confirmed and regime == "Bullish":
        candidate = {
            "side": "Long",
            "entry_price": float(last_candle["close"]),
            "opening_high": opening_high,
            "opening_low": opening_low,
        }
    elif short_breakout and volume_confirmed and regime == "Bearish":
        candidate = {
            "side": "Short",
            "entry_price": float(last_candle["close"]),
            "opening_high": opening_high,
            "opening_low": opening_low,
            "day_high_so_far": float(today_df["high"].max()),
        }

    opened_signal: Optional[dict] = None
    async with state.lock:
        s = state.get_us_stock_state(ticker_symbol)
        s.opening_high = opening_high
        s.opening_low = opening_low
        s.rvol = rvol
        s.market_regime = regime
        s.day_change_pct = day_change_pct
        s.last_updated = datetime.now(timezone.utc).isoformat()

        if s.open_signal is not None or candidate is None:
            pass  # 已有部位，或這輪沒有候選訊號
        elif s.triggered_date == today_et.isoformat():
            pass  # 今天已經觸發過一次，避免在區間邊緣反覆進出
        else:
            s.open_signal = build_us_stock_open_signal(display_name, ticker_symbol, candidate)
            s.triggered_date = today_et.isoformat()
            opened_signal = s.open_signal

    if opened_signal is not None:
        logger.info(
            "美股 ORB 新訊號：%s %s @ %.2f（RVOL=%.2f，大盤=%s）",
            display_name, candidate["side"], candidate["entry_price"], rvol or 0.0, regime,
        )
        emoji = "🟢" if candidate["side"] == "Long" else "🔴"
        await send_telegram_message(
            f"{emoji} <b>美股 ORB 新訊號</b>\n{display_name} {candidate['side']}\n"
            f"進場：{opened_signal['entry_price']:.4f}\n"
            f"停利：{opened_signal['take_profit']:.4f} ／ 停損：{opened_signal['stop_loss']:.4f}\n"
            f"槓桿：{opened_signal['leverage']}x\nRVOL：{(rvol or 0.0):.2f} 倍 ／ 大盤：{regime}"
        )


async def evaluate_us_stock_open_signal(ticker_symbol: str, current_price: float) -> Optional[str]:
    """
    跟主流幣的 evaluate_open_signal 邏輯完全相同，只是作用在美股 ORB 的部位上。
    呼叫端須持有 state.lock；回傳值是「這次有結算的話，要推播的通知文字」或 None。
    """
    st = state.get_us_stock_state(ticker_symbol)
    signal = st.open_signal
    if signal is None:
        return None

    side = signal["side"]
    take_profit = signal["take_profit"]
    stop_loss = signal["stop_loss"]

    hit_tp = current_price >= take_profit if side == "Long" else current_price <= take_profit
    hit_sl = current_price <= stop_loss if side == "Long" else current_price >= stop_loss
    if not (hit_tp or hit_sl):
        return None

    result: Literal["WIN", "LOSS"] = "WIN" if hit_tp else "LOSS"
    exit_price = take_profit if hit_tp else stop_loss

    raw_pnl_pct = (exit_price - signal["entry_price"]) / signal["entry_price"] * 100
    if side == "Short":
        raw_pnl_pct = -raw_pnl_pct
    pnl_pct = raw_pnl_pct * signal["leverage"]

    closed_record = {
        **signal,
        "exit_price": exit_price,
        "result": result,
        "pnl_pct": pnl_pct,
        "closed_at": datetime.now(timezone.utc).isoformat(),
    }
    state.us_stock_history.appendleft(closed_record)
    st.open_signal = None
    append_jsonl(US_STOCK_TRADE_LOG_PATH, closed_record)
    logger.info("美股 ORB 訊號結算：%s %s，結果=%s，損益=%.2f%%", signal["display_name"], side, result, pnl_pct)

    emoji = "✅" if result == "WIN" else "❌"
    return (
        f"{emoji} <b>美股 ORB 訊號結算</b>\n{signal['display_name']} {side}\n"
        f"結果：{result}\n進場：{signal['entry_price']:.4f} → 出場：{exit_price:.4f}\n"
        f"損益：{pnl_pct:+.2f}%（{signal['leverage']}x 槓桿）"
    )


async def force_close_us_stock_signal(ticker_symbol: str, current_price: float) -> Optional[str]:
    """
    當沖規則：收盤前如果部位還沒碰到 TP/SL，用收盤前最後報價強制平倉，不留倉過夜。
    背景迴圈在非交易時段整個睡眠、完全不會監控價格，留倉會變成沒人管的曝險，
    這支函式就是避免那種情況。呼叫端須持有 state.lock。
    """
    st = state.get_us_stock_state(ticker_symbol)
    signal = st.open_signal
    if signal is None:
        return None

    side = signal["side"]
    exit_price = current_price

    raw_pnl_pct = (exit_price - signal["entry_price"]) / signal["entry_price"] * 100
    if side == "Short":
        raw_pnl_pct = -raw_pnl_pct
    pnl_pct = raw_pnl_pct * signal["leverage"]
    result: Literal["WIN", "LOSS"] = "WIN" if pnl_pct >= 0 else "LOSS"

    closed_record = {
        **signal,
        "exit_price": exit_price,
        "result": result,
        "pnl_pct": pnl_pct,
        "closed_at": datetime.now(timezone.utc).isoformat(),
    }
    state.us_stock_history.appendleft(closed_record)
    st.open_signal = None
    append_jsonl(US_STOCK_TRADE_LOG_PATH, closed_record)
    logger.info("美股 ORB 收盤強制平倉：%s %s，結果=%s，損益=%.2f%%", signal["display_name"], side, result, pnl_pct)

    return (
        f"🌙 <b>美股 ORB 收盤強制平倉</b>\n{signal['display_name']} {side}\n"
        f"結果：{result}（當沖規則：收盤前未觸及TP/SL，以收盤前報價平倉）\n"
        f"進場：{signal['entry_price']:.4f} → 出場：{exit_price:.4f}\n"
        f"損益：{pnl_pct:+.2f}%（{signal['leverage']}x 槓桿）"
    )


async def flatten_all_us_stock_positions(exchange_pool: dict) -> None:
    """收盤瞬間對所有還有部位的標的做一次批次強制平倉，見 force_close_us_stock_signal。"""
    async with state.lock:
        open_symbols = [
            sym for sym in US_STOCK_SYMBOLS.values() if state.get_us_stock_state(sym).open_signal is not None
        ]
    if not open_symbols:
        return

    try:
        prices = await fetch_tickers_batch(exchange_pool, open_symbols)
    except Exception as exc:  # noqa: BLE001
        logger.error("收盤強制平倉時抓取價格失敗，這些部位將留到下次抓得到報價才平倉：%s", exc)
        return

    notifications: List[str] = []
    async with state.lock:
        for ticker_symbol, price in prices.items():
            notification = await force_close_us_stock_signal(ticker_symbol, price)
            if notification:
                notifications.append(notification)

    for notification in notifications:
        await send_telegram_message(notification)


async def us_stock_orb_loop(exchange_pool: dict) -> None:
    """
    美股 ORB 背景迴圈：獨立於主流幣/迷因幣共用的 price_monitor_loop，只在美股交易
    時段（美東 09:15-16:00、週一到週五）才運作，其餘時間睡眠、不打任何 API。
    現價每 US_STOCK_TICKER_INTERVAL_SECONDS 秒刷新一次（驅動 TP/SL 監控），
    K線+ORB策略偵測每 US_STOCK_SCAN_INTERVAL_SECONDS 秒才跑一次（15m線沒必要
    每2秒重算），任何例外都會被記錄下來但不中斷這支迴圈。

    當沖規則：休市時這支迴圈整個睡眠、完全不會監控價格，所以一旦偵測到「剛從
    開盤轉成休市」，會先強制平倉所有還沒結算的部位（見 flatten_all_us_stock_
    positions），不留倉過夜曝險。
    """
    last_scan_at = 0.0
    tz = ZoneInfo(US_MARKET_TZ)
    # 初始值刻意設 True：如果伺服器是在休市時段重啟、又剛好從快照讀回一筆
    # 沒平倉的舊部位（例如上次收盤前平倉失敗），第一輪就會觸發一次平倉檢查，
    # 而不是要等到「真的觀察到一次開盤轉休市」才處理；沒有殘留部位時是無害的
    # no-op（flatten_all_us_stock_positions 內部沒有部位就直接返回）。
    was_active = True

    while True:
        failure_notification: Optional[str] = None
        try:
            now_et = datetime.now(tz)
            is_active = _is_us_market_active(now_et)

            if not is_active:
                if was_active:
                    await flatten_all_us_stock_positions(exchange_pool)
                was_active = False
                await asyncio.sleep(US_STOCK_CLOSED_POLL_SECONDS)
                continue

            was_active = True
            symbols = list(US_STOCK_SYMBOLS.values())
            try:
                prices = await fetch_tickers_batch(exchange_pool, symbols)
            except Exception as exc:  # noqa: BLE001
                logger.error("美股批次抓取即時價格失敗：%s", exc)
                prices = {}

            now_iso = datetime.now(timezone.utc).isoformat()
            settlement_notifications: List[str] = []
            async with state.lock:
                for ticker_symbol, price in prices.items():
                    s = state.get_us_stock_state(ticker_symbol)
                    s.current_price = price
                    notification = await evaluate_us_stock_open_signal(ticker_symbol, price)
                    if notification:
                        settlement_notifications.append(notification)
                    s.last_updated = now_iso

            for notification in settlement_notifications:
                await send_telegram_message(notification)

            now_monotonic = time.monotonic()
            if now_monotonic - last_scan_at >= US_STOCK_SCAN_INTERVAL_SECONDS:
                await refresh_us_market_regime(exchange_pool)
                for display_name, ticker_symbol in US_STOCK_SYMBOLS.items():
                    await scan_us_stock_orb(exchange_pool, display_name, ticker_symbol)
                last_scan_at = now_monotonic

            failure_notification = _record_loop_outcome("美股 ORB 迴圈", success=True)
        except Exception as exc:  # noqa: BLE001 - 背景迴圈需持續存活，統一捕捉並記錄錯誤
            logger.error("美股 ORB 背景迴圈發生錯誤：%s", exc)
            failure_notification = _record_loop_outcome("美股 ORB 迴圈", success=False)

        if failure_notification:
            await send_telegram_message(failure_notification)

        await asyncio.sleep(US_STOCK_TICKER_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# 6.7 AI 智能投研 Agent（獨立模塊：RSS新聞 -> LLM情緒分析 -> 技術面共振通知）
# ---------------------------------------------------------------------------

SENTIMENT_PROMPT_TEMPLATE = """你是專業的美股與加密貨幣市場新聞分析師。請閱讀以下這則新聞的標題與摘要，判斷：
1. 這則新聞明確提到哪些「可交易標的」的代號（美股代號如 TSLA、NVDA，或加密貨幣代號如 BTC、ETH）。
   只列出新聞內容有明確指名道姓的標的，不要自己聯想擴充；如果沒有明確提到任何可交易標的，回傳空陣列。
2. 用一句話（繁體中文，30字以內）摘要這則新聞的核心重點。
3. 給這則新聞對這些標的的市場情緒評分，範圍是 -10（極度利空）到 +10（極度利多），0 代表中性無明顯方向。

新聞標題：{title}
新聞摘要：{summary}

請「只」回傳一個 JSON 物件，不要加任何其他文字、不要用 markdown 標記包起來，格式如下：
{{"symbols": ["TSLA", "BTC"], "summary": "一句話摘要", "sentiment_score": 5}}

如果這則新聞跟金融市場無關、或沒有提到任何明確標的，回傳：
{{"symbols": [], "summary": "一句話摘要", "sentiment_score": 0}}
"""


def build_sentiment_prompt(title: str, summary: str) -> str:
    return SENTIMENT_PROMPT_TEMPLATE.format(title=title, summary=summary or "（無摘要，僅有標題）")


async def analyze_news_sentiment(
    openai_client: Optional[AsyncOpenAI], title: str, summary: str
) -> Optional[dict]:
    """
    呼叫 LLM 把一則新聞標題/摘要結構化：提取可交易標的代號、一句話摘要、情緒評分(-10~+10)。
    openai_client 為 None（未設定 OPENAI_API_KEY）時直接跳過，回傳 None，不影響其他功能——
    這支模塊在沒有金鑰時仍然會抓新聞、去重複，只是不會有情緒分析結果。
    """
    if openai_client is None:
        return None

    try:
        response = await openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": build_sentiment_prompt(title, summary)}],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=300,
        )
        parsed = json.loads(response.choices[0].message.content)
        symbols = [str(s).strip().upper() for s in parsed.get("symbols", []) if s]
        raw_score = int(parsed.get("sentiment_score", 0))
        score = max(-10, min(10, raw_score))  # 保險起見再夾一次範圍，避免 LLM 沒照格式回傳
        return {
            "symbols": symbols,
            "summary": str(parsed.get("summary", "")).strip(),
            "sentiment_score": score,
        }
    except Exception as exc:  # noqa: BLE001 - LLM回傳格式不保證、網路也可能失敗，統一捕捉不中斷迴圈
        logger.warning("新聞情緒分析失敗（%s）：%s", title[:40], exc)
        return None


async def fetch_news_entries() -> List[dict]:
    """
    非同步抓取所有設定好的 RSS 來源。feedparser 本身是同步、會阻塞的網路呼叫，
    用 asyncio.to_thread 丟到執行緒池跑，避免卡住事件迴圈裡其他協程。
    """
    entries: List[dict] = []
    for source_name, feed_url in NEWS_RSS_FEEDS.items():
        try:
            parsed = await asyncio.to_thread(feedparser.parse, feed_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RSS 抓取失敗（%s）：%s", source_name, exc)
            continue

        for entry in parsed.entries:
            link = entry.get("link")
            title = entry.get("title")
            if not link or not title:
                continue
            published_struct = entry.get("published_parsed")
            published_at = (
                datetime(*published_struct[:6], tzinfo=timezone.utc).isoformat()
                if published_struct
                else datetime.now(timezone.utc).isoformat()
            )
            entries.append({
                "source": source_name,
                "title": title,
                "url": link,
                "summary_raw": entry.get("summary", ""),
                "published_at": published_at,
            })
    return entries


def _match_open_signals_for_symbol(ticker: str) -> List[dict]:
    """
    找出目前「有開倉部位」且跟這個新聞標的代號相符的訊號——同時查主流幣/掃描名單
    跟美股 ORB 兩組獨立狀態，回傳 [{"kind", "display", "side", "symbol"}, ...]。
    呼叫端須持有 state.lock。
    """
    matches: List[dict] = []

    for symbol, sym_state in state.symbols.items():
        if sym_state.open_signal is None:
            continue
        base = symbol.split("/")[0].upper()
        if base == ticker:
            matches.append({"kind": "crypto", "display": symbol, "side": sym_state.open_signal["side"], "symbol": symbol})

    for display_name, ticker_symbol in US_STOCK_SYMBOLS.items():
        if display_name.upper() != ticker:
            continue
        us_state = state.us_stock_states.get(ticker_symbol)
        if us_state and us_state.open_signal is not None:
            matches.append(
                {"kind": "us_stock", "display": display_name, "side": us_state.open_signal["side"], "symbol": ticker_symbol}
            )

    return matches


async def scan_news_agent(openai_client: Optional[AsyncOpenAI]) -> None:
    """
    抓新聞 -> 去重複 -> LLM結構化情緒分析 -> 只留「有價值」的（明確標的 + 非中性
    情緒分數）-> 跟現有開倉部位比對是否「技術面+情緒面共振」（部位方向與情緒方向
    一致，且 |分數| 達到 NEWS_RESONANCE_SCORE_THRESHOLD）-> 共振時推播 Telegram。

    候選新聞用「每個來源各自留名額」（NEWS_MAX_ITEMS_PER_SOURCE）而不是全部來源
    混在一起比誰最新，避免發文密度高的來源（例如 Yahoo Finance）每輪把配額全部
    吃光，擠壓掉其他來源，確保每輪都有機會分析到不同來源的新聞。
    """
    entries = await fetch_news_entries()

    async with state.lock:
        seen = set(state.seen_news_urls)

    entries_by_source: Dict[str, List[dict]] = {}
    for e in entries:
        if e["url"] in seen:
            continue
        entries_by_source.setdefault(e["source"], []).append(e)

    new_entries: List[dict] = []
    for source_entries in entries_by_source.values():
        source_entries.sort(key=lambda e: e["published_at"], reverse=True)  # 該來源內優先分析最新的
        new_entries.extend(source_entries[:NEWS_MAX_ITEMS_PER_SOURCE])

    if not new_entries:
        return

    resonance_notifications: List[str] = []
    for entry in new_entries:
        analysis = await analyze_news_sentiment(openai_client, entry["title"], entry["summary_raw"])

        async with state.lock:
            state.seen_news_urls.append(entry["url"])

        if analysis is None:
            continue

        # 「有價值」的定義：LLM 判斷出至少一個明確標的，而且情緒不是中性(0分)——
        # 沒有標的或中性的新聞對交易判斷沒有實質幫助，不存、不顯示，但上面那行
        # 已經把網址記進 seen_news_urls，不會浪費 LLM 額度重複分析同一則。
        if not analysis["symbols"] or analysis["sentiment_score"] == 0:
            continue

        record = {
            "title": entry["title"],
            "url": entry["url"],
            "source": entry["source"],
            "published_at": entry["published_at"],
            "symbols": analysis["symbols"],
            "summary": analysis["summary"],
            "sentiment_score": analysis["sentiment_score"],
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        async with state.lock:
            state.news_items.appendleft(record)
        append_jsonl(NEWS_LOG_PATH, record)

        if abs(analysis["sentiment_score"]) < NEWS_RESONANCE_SCORE_THRESHOLD:
            continue

        async with state.lock:
            for ticker in analysis["symbols"]:
                for match in _match_open_signals_for_symbol(ticker):
                    side_aligned = (
                        (match["side"] == "Long" and analysis["sentiment_score"] > 0)
                        or (match["side"] == "Short" and analysis["sentiment_score"] < 0)
                    )
                    if not side_aligned:
                        continue
                    resonance_notifications.append(
                        f"🎯 <b>技術面 + 新聞情緒共振</b>\n"
                        f"{match['display']}（{match['side']}）\n"
                        f"情緒評分：{analysis['sentiment_score']:+d}\n"
                        f"新聞：{analysis['summary']}\n"
                        f"來源：{entry['source']} － {entry['url']}"
                    )

    # 推播刻意放在鎖外面，理由同 run_tick
    for notification in resonance_notifications:
        await send_telegram_message(notification)


async def post_to_x(content: str) -> None:
    """
    【預留接口，目前未啟用、也還沒有任何呼叫端在用它】自動發文到 X (Twitter)。
    標準 HTTP POST 呼叫 X API v2 的 /2/tweets 端點，不引入 tweepy 這個額外依賴，
    維持跟 send_telegram_message 一樣「直接打 REST API」的風格。

    四個 X_* 環境變數都沒設定時直接跳過，不影響任何其他功能。之後申請到 X
    Developer 帳號、填好這四個環境變數後，還需要補上 OAuth 1.0a User Context
    簽名邏輯（X API v2 發文必須簽名，不能只憑 API Key 裸打）才能真的動作——
    這裡先留 TODO，等實際申請到帳號、確認簽名方式後再補完整實作。

    ⚠️ 啟用前必看：這是會公開發文的函式，呼叫端要自己決定「什麼情況才該發」，
    這裡不做任何內容審查或發文頻率限制，濫用可能導致帳號被 X 停權。
    """
    if not all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET]):
        logger.debug("X_* 環境變數未設定，跳過發文：%s", content[:40])
        return

    raise NotImplementedError(
        "post_to_x() 目前只是預留骨架：X_* 環境變數都設定好之後，"
        "還需要補上 OAuth 1.0a 簽名邏輯才能真的呼叫 X API v2 /2/tweets"
    )


async def news_agent_loop() -> None:
    """
    AI 智能投研 Agent 背景迴圈：獨立於其他所有模塊，每 NEWS_SCAN_INTERVAL_SECONDS
    秒跑一次 scan_news_agent。沒設定 OPENAI_API_KEY 時，client 是 None，迴圈照樣會
    跑（抓新聞、去重複），只是不會有情緒分析結果——不會因為沒設金鑰就整支掛掉。
    """
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
    if openai_client is None:
        logger.warning("未設定 OPENAI_API_KEY，AI 新聞情緒分析模塊將只抓新聞、不做情緒分析")

    while True:
        failure_notification: Optional[str] = None
        try:
            await scan_news_agent(openai_client)
            failure_notification = _record_loop_outcome("AI新聞Agent迴圈", success=True)
        except Exception as exc:  # noqa: BLE001 - 背景迴圈需持續存活，統一捕捉並記錄錯誤
            logger.error("AI新聞Agent背景迴圈發生錯誤：%s", exc)
            failure_notification = _record_loop_outcome("AI新聞Agent迴圈", success=False)

        if failure_notification:
            await send_telegram_message(failure_notification)

        await asyncio.sleep(NEWS_SCAN_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# 7. 多標的追蹤名單管理
# ---------------------------------------------------------------------------

async def refresh_scan_universe(exchange_pool: dict) -> None:
    """每 SCAN_UNIVERSE_REFRESH_SECONDS 秒重新依 24h 成交量排名一次市場掃描名單。"""
    now = time.monotonic()
    if state.scan_universe and now - state.last_scan_universe_refresh < SCAN_UNIVERSE_REFRESH_SECONDS:
        return

    last_error: Optional[Exception] = None
    for name in _exchange_order():
        exchange = exchange_pool[name]
        if not exchange.markets:
            continue  # 該交易所 load_markets() 尚未成功（例如地區限制），跳過改用備援
        try:
            candidates = [
                symbol
                for symbol, market in exchange.markets.items()
                if market.get("swap")
                and market.get("linear")
                and market.get("quote") == "USDT"
                and not str(market.get("base", "")).startswith(NON_CRYPTO_BASE_PREFIXES)
            ]
            tickers = await exchange.fetch_tickers(candidates)
            ranked = sorted(tickers.values(), key=lambda t: t.get("quoteVolume") or 0, reverse=True)
            top_symbols = [t["symbol"] for t in ranked if t["symbol"] not in MAJOR_SYMBOLS][:SCAN_UNIVERSE_SIZE]

            if name != state.active_exchange_name:
                logger.warning("交易所 %s 失敗，已切換至 %s", state.active_exchange_name, name)
                state.active_exchange_name = name

            async with state.lock:
                state.scan_universe = top_symbols
                state.last_scan_universe_refresh = now
            logger.info("市場掃描名單已更新（依24h成交量排序，來源 %s），共 %d 檔", name, len(top_symbols))
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue

    logger.warning("更新市場掃描名單失敗：%s", last_error)


def pick_scan_universe_chunk() -> List[str]:
    """輪流從掃描名單取出一小批，讓整份名單大約每 SCAN_CYCLE_TICKS 個 tick 掃過一輪。"""
    universe = state.scan_universe
    if not universe:
        return []

    chunk_size = max(1, math.ceil(len(universe) / SCAN_CYCLE_TICKS))
    start = state.scan_cursor
    chunk = [universe[(start + i) % len(universe)] for i in range(min(chunk_size, len(universe)))]
    state.scan_cursor = (start + chunk_size) % len(universe)
    return chunk


async def build_tracked_symbols() -> List[str]:
    """目前需要即時報價的標的：主流幣 + 掃描名單 + 任何目前持有部位的幣（即使已跌出排名）。"""
    async with state.lock:
        open_symbols = [s for s, sym_state in state.symbols.items() if sym_state.open_signal is not None]
        scan_universe = list(state.scan_universe)
    return list(dict.fromkeys(MAJOR_SYMBOLS + scan_universe + open_symbols))


# ---------------------------------------------------------------------------
# 8. 背景監控迴圈
# ---------------------------------------------------------------------------

async def evaluate_open_signal(symbol: str, current_price: float) -> Optional[str]:
    """
    檢查該標的目前持有中的訊號是否已觸及止盈/止損，若是則結算並寫入歷史。
    呼叫端須持有 state.lock。回傳值是「這次有結算的話，要推播的通知文字」或
    None——刻意用回傳值而不是在這裡直接送 Telegram，因為這個函式是在鎖裡面
    跑的，網路請求不能卡在鎖裡面。
    """
    sym_state = state.get_symbol_state(symbol)
    signal = sym_state.open_signal
    if signal is None:
        return None

    side = signal["side"]
    take_profit = signal["take_profit"]
    stop_loss = signal["stop_loss"]

    hit_tp = current_price >= take_profit if side == "Long" else current_price <= take_profit
    hit_sl = current_price <= stop_loss if side == "Long" else current_price >= stop_loss

    if not (hit_tp or hit_sl):
        return None

    result: Literal["WIN", "LOSS"] = "WIN" if hit_tp else "LOSS"
    exit_price = take_profit if hit_tp else stop_loss

    raw_pnl_pct = (exit_price - signal["entry_price"]) / signal["entry_price"] * 100
    if side == "Short":
        raw_pnl_pct = -raw_pnl_pct
    pnl_pct = raw_pnl_pct * signal["leverage"]

    closed_record = {
        **signal,
        "exit_price": exit_price,
        "result": result,
        "pnl_pct": pnl_pct,
        "closed_at": datetime.now(timezone.utc).isoformat(),
    }
    state.history.appendleft(closed_record)
    sym_state.open_signal = None
    append_jsonl(TRADE_LOG_PATH, closed_record)
    logger.info("訊號結算：%s %s，結果=%s，損益=%.2f%%", symbol, side, result, pnl_pct)

    emoji = "✅" if result == "WIN" else "❌"
    return (
        f"{emoji} <b>訊號結算</b>\n{symbol} {side}\n"
        f"結果：{result}\n進場：{signal['entry_price']:.4f} → 出場：{exit_price:.4f}\n"
        f"損益：{pnl_pct:+.2f}%（{signal['leverage']}x 槓桿）"
    )


async def refresh_major_smart_money(exchange_pool: dict) -> None:
    """主流幣專屬：每 SMART_MONEY_REFRESH_SECONDS 秒刷新一次並快取聰明錢數據。"""
    for symbol in MAJOR_SYMBOLS:
        sym_state = state.get_symbol_state(symbol)
        now = time.monotonic()
        if now - sym_state.last_smart_money_fetch < SMART_MONEY_REFRESH_SECONDS:
            continue

        exchange = exchange_pool[state.active_exchange_name]
        snapshot = await fetch_smart_money_snapshot(exchange, state.active_exchange_name, symbol)

        async with state.lock:
            sym_state = state.get_symbol_state(symbol)
            if snapshot["open_interest_value"] is not None:
                sym_state.oi_history.append(snapshot["open_interest_value"])
            oi_change_pct = compute_oi_change_pct(sym_state.oi_history)
            bias_eval = evaluate_smart_money_bias(
                snapshot["funding_rate"], snapshot["top_trader_long_short_ratio"], oi_change_pct
            )
            sym_state.smart_money = {
                **snapshot,
                "oi_change_pct": oi_change_pct,
                **bias_eval,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            sym_state.last_smart_money_fetch = now

        logger.info(
            "聰明錢數據更新：%s funding=%s, OI變化=%s%%, 大戶多空比=%s, bias=%s",
            symbol,
            snapshot["funding_rate"],
            oi_change_pct,
            snapshot["top_trader_long_short_ratio"],
            bias_eval["bias"],
        )


async def deep_scan_symbol(exchange_pool: dict, symbol: str) -> None:
    """對單一標的做完整的 K 線 + 策略偵測，並在觸發候選訊號時套用聰明錢否決濾網。"""
    async with state.lock:
        sym_state = state.get_symbol_state(symbol)
        if sym_state.open_signal is not None:
            return  # 已有部位，TP/SL 監控已在批次報價階段處理，這裡不重複偵測新訊號

    try:
        closed_df = await fetch_ohlcv_for_symbol(exchange_pool, symbol)
    except Exception as exc:  # noqa: BLE001
        logger.warning("K線抓取失敗（%s）：%s", symbol, exc)
        return

    df_with_indicators = add_indicators(closed_df)

    # 監控快照：不論這根K棒有沒有觸發訊號都更新，讓「沒有部位」時前端也能顯示
    # 離突破多遠、量能倍數，而不是完全沒東西可看。
    if len(df_with_indicators) > 0:
        last_row = df_with_indicators.iloc[-1]
        async with state.lock:
            sym_state = state.get_symbol_state(symbol)
            sym_state.donchian_upper = (
                float(last_row["donchian_upper"]) if pd.notna(last_row["donchian_upper"]) else None
            )
            sym_state.donchian_lower = (
                float(last_row["donchian_lower"]) if pd.notna(last_row["donchian_lower"]) else None
            )
            if pd.notna(last_row["avg_volume"]) and last_row["avg_volume"] > 0:
                sym_state.volume_ratio = float(last_row["volume"] / last_row["avg_volume"])
            else:
                sym_state.volume_ratio = None

    is_debug_target = symbol == DEBUG_FORCE_SYMBOL and DEBUG_FORCE_SIGNAL in ("long", "short")

    if is_debug_target:
        async with state.lock:
            price = state.get_symbol_state(symbol).current_price
        fallback_price = price or float(closed_df["close"].iloc[-1])
        candidate = {
            "side": "Long" if DEBUG_FORCE_SIGNAL == "long" else "Short",
            "entry_price": fallback_price,
            "atr": fallback_price * 0.005,  # 假設 0.5% 波動，純供 UI 測試使用
        }
        forced_notes: Optional[List[str]] = ["⚠️ DEBUG_FORCE_SIGNAL 測試模式，非真實策略觸發的訊號"]
    else:
        candidate = detect_new_signal(df_with_indicators)
        forced_notes = None

    if candidate is None:
        return

    # 主流幣有背景定期刷新的聰明錢快取可直接用；掃描名單的幣種平常不養這份資料，
    # 只有真的出現候選訊號時才臨時抓一次，避免每輪對數十檔都打資金費率/OI API。
    if symbol in MAJOR_SYMBOLS:
        async with state.lock:
            cached = state.get_symbol_state(symbol).smart_money
        bias_eval = cached or {"veto_long": False, "veto_short": False, "notes": []}
    elif not is_debug_target:
        exchange = exchange_pool[state.active_exchange_name]
        snapshot = await fetch_smart_money_snapshot(exchange, state.active_exchange_name, symbol)
        bias_eval = evaluate_smart_money_bias(
            snapshot["funding_rate"], snapshot["top_trader_long_short_ratio"], None
        )
        async with state.lock:
            sym_state = state.get_symbol_state(symbol)
            sym_state.smart_money = {
                **snapshot,
                "oi_change_pct": None,
                **bias_eval,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
    else:
        bias_eval = {"veto_long": False, "veto_short": False, "notes": []}

    vetoed = (candidate["side"] == "Long" and bias_eval.get("veto_long")) or (
        candidate["side"] == "Short" and bias_eval.get("veto_short")
    )

    async with state.lock:
        sym_state = state.get_symbol_state(symbol)
        if sym_state.open_signal is not None:
            return  # 這段期間可能已經有其他路徑產生訊號，避免重複建立

        if vetoed and not is_debug_target:
            logger.info(
                "訊號被聰明錢模塊否決：%s %s @ %.2f，原因：%s",
                symbol,
                candidate["side"],
                candidate["entry_price"],
                bias_eval.get("notes"),
            )
            return

        notes = forced_notes if forced_notes is not None else bias_eval.get("notes")
        sym_state.open_signal = build_open_signal(symbol, candidate, smart_money_notes=notes)

    if is_debug_target:
        logger.warning(
            "⚠️ DEBUG_FORCE_SIGNAL=%s 已啟用，強制產生測試訊號：%s @ %.2f（非真實策略觸發）",
            DEBUG_FORCE_SIGNAL,
            symbol,
            candidate["entry_price"],
        )
    else:
        logger.info("新訊號產生：%s %s @ %.2f", symbol, candidate["side"], candidate["entry_price"])
        opened = sym_state.open_signal
        emoji = "🟢" if candidate["side"] == "Long" else "🔴"
        await send_telegram_message(
            f"{emoji} <b>新訊號</b>\n{symbol} {candidate['side']}\n"
            f"進場：{opened['entry_price']:.4f}\n"
            f"停利：{opened['take_profit']:.4f} ／ 停損：{opened['stop_loss']:.4f}\n"
            f"槓桿：{opened['leverage']}x"
        )


async def run_tick(exchange_pool: dict) -> None:
    """
    背景迴圈的單次迭代：
      1. 視需要重新排名市場掃描名單
      2. 批次抓取所有追蹤中標的的即時價格，驅動 TP/SL 監控與結算（每 tick 都做，
         因為價格隨時可能觸及 TP/SL，跟K線週期無關）
      3. 每 DEEP_SCAN_INTERVAL_SECONDS 秒才做一次完整的 K 線 + 策略偵測——
         現在策略跑在 4 小時線上，沒必要每 20 秒就重算一次指標、浪費 API 額度
    """
    await refresh_scan_universe(exchange_pool)

    tracked_symbols = await build_tracked_symbols()

    try:
        prices = await fetch_tickers_batch(exchange_pool, tracked_symbols)
    except Exception as exc:  # noqa: BLE001
        logger.error("批次抓取即時價格失敗：%s", exc)
        prices = {}

    now_iso = datetime.now(timezone.utc).isoformat()
    settlement_notifications: List[str] = []
    async with state.lock:
        for symbol, price in prices.items():
            sym_state = state.get_symbol_state(symbol)
            sym_state.current_price = price
            notification = await evaluate_open_signal(symbol, price)
            if notification:
                settlement_notifications.append(notification)
            sym_state.last_updated = now_iso
        state.last_tick_at = now_iso

    # 推播刻意放在鎖外面，避免等 Telegram 回應時卡住其他正在等鎖的請求
    for notification in settlement_notifications:
        await send_telegram_message(notification)

    await refresh_major_smart_money(exchange_pool)

    now_monotonic = time.monotonic()
    if now_monotonic - state.last_deep_scan_at >= DEEP_SCAN_INTERVAL_SECONDS:
        scan_chunk = pick_scan_universe_chunk()
        for symbol in MAJOR_SYMBOLS + scan_chunk:
            await deep_scan_symbol(exchange_pool, symbol)
        state.last_deep_scan_at = now_monotonic

    # 迷因幣雷達：完全獨立的一支，跟上面主流幣策略的資料/邏輯互不影響
    if now_monotonic - state.last_meme_scan_at >= MEME_SCAN_INTERVAL_SECONDS:
        await scan_meme_radar(exchange_pool)
        state.last_meme_scan_at = now_monotonic

    save_state_snapshot()  # 資料量很小，每個 tick 都存一次，盡量縮短重啟遺失資料的時間窗


async def price_monitor_loop(exchange_pool: dict) -> None:
    """背景永久迴圈：每 TICK_INTERVAL_SECONDS 秒跑一次 run_tick，任何例外都會被記錄下來但不中斷服務。"""
    while True:
        failure_notification: Optional[str] = None
        try:
            await run_tick(exchange_pool)
            failure_notification = _record_loop_outcome("主流幣監控迴圈", success=True)
        except Exception as exc:  # noqa: BLE001 - 背景迴圈需持續存活，統一捕捉並記錄錯誤
            logger.error("背景監控迴圈發生錯誤：%s", exc)
            failure_notification = _record_loop_outcome("主流幣監控迴圈", success=False)

        if failure_notification:
            await send_telegram_message(failure_notification)

        await asyncio.sleep(TICK_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# 8.5 狀態快照（存檔／讀回，讓重啟不會弄丟正在追蹤中的部位）
# ---------------------------------------------------------------------------

def save_state_snapshot() -> None:
    """
    把目前記憶體裡的關鍵狀態寫成一份 JSON 快照：持倉中的部位、歷史紀錄、
    掃描名單、迷因幣狀態。伺服器重啟時會嘗試讀回，這樣重啟（例如套用程式
    修復）不會弄丟正在追蹤中的部位跟統計數據。寫檔失敗只記警告，不影響
    背景迴圈繼續運作。
    """
    try:
        snapshot = {
            "symbols": {
                symbol: {"open_signal": sym_state.open_signal, "current_price": sym_state.current_price}
                for symbol, sym_state in state.symbols.items()
                if sym_state.open_signal is not None  # 沒有部位的標的重新掃描即可，不用救
            },
            "history": list(state.history),
            "scan_universe": state.scan_universe,
            "meme_states": {
                symbol: {
                    "current_price": meme_state.current_price,
                    "volume_multiple": meme_state.volume_multiple,
                    "alert_active": meme_state.alert_active,
                }
                for symbol, meme_state in state.meme_states.items()
            },
            "meme_alerts": list(state.meme_alerts),
            "us_stock_states": {
                symbol: {
                    "open_signal": s.open_signal,
                    "current_price": s.current_price,
                    "triggered_date": s.triggered_date,
                }
                for symbol, s in state.us_stock_states.items()
                if s.open_signal is not None or s.triggered_date is not None
            },
            "us_stock_history": list(state.us_stock_history),
            "news_items": list(state.news_items),
            "seen_news_urls": list(state.seen_news_urls),
        }
        os.makedirs(LOG_DIR, exist_ok=True)
        tmp_path = STATE_SNAPSHOT_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, default=str)
        os.replace(tmp_path, STATE_SNAPSHOT_PATH)  # 原子性覆蓋，避免寫到一半時被讀到壞檔
    except Exception as exc:  # noqa: BLE001
        logger.warning("寫入狀態快照失敗：%s", exc)


def load_state_snapshot() -> None:
    """伺服器啟動時嘗試讀回快照；沒有快照檔或讀取失敗就從全新狀態開始，不會擋住啟動。"""
    if not os.path.exists(STATE_SNAPSHOT_PATH):
        logger.info("找不到狀態快照，從全新狀態啟動")
        return

    try:
        with open(STATE_SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            snapshot = json.load(f)

        for symbol, data in snapshot.get("symbols", {}).items():
            sym_state = state.get_symbol_state(symbol)
            sym_state.open_signal = data.get("open_signal")
            sym_state.current_price = data.get("current_price")

        state.history.extend(snapshot.get("history", []))
        state.scan_universe = snapshot.get("scan_universe", [])

        for symbol, data in snapshot.get("meme_states", {}).items():
            meme_state = state.get_meme_state(symbol)
            meme_state.current_price = data.get("current_price")
            meme_state.volume_multiple = data.get("volume_multiple")
            meme_state.alert_active = data.get("alert_active", False)

        state.meme_alerts.extend(snapshot.get("meme_alerts", []))

        for symbol, data in snapshot.get("us_stock_states", {}).items():
            us_state = state.get_us_stock_state(symbol)
            us_state.open_signal = data.get("open_signal")
            us_state.current_price = data.get("current_price")
            us_state.triggered_date = data.get("triggered_date")

        state.us_stock_history.extend(snapshot.get("us_stock_history", []))
        state.news_items.extend(snapshot.get("news_items", []))
        state.seen_news_urls.extend(snapshot.get("seen_news_urls", []))

        restored_positions = sum(1 for d in snapshot.get("symbols", {}).values() if d.get("open_signal"))
        restored_us_stock_positions = sum(
            1 for d in snapshot.get("us_stock_states", {}).values() if d.get("open_signal")
        )
        logger.info(
            "已從快照恢復狀態：%d 筆持倉中部位、%d 筆歷史紀錄、%d 檔掃描名單、%d 筆迷因警報、"
            "%d 筆美股ORB部位、%d 則已分析新聞",
            restored_positions,
            len(state.history),
            len(state.scan_universe),
            len(state.meme_alerts),
            restored_us_stock_positions,
            len(state.news_items),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("讀取狀態快照失敗，將從全新狀態啟動：%s", exc)


# ---------------------------------------------------------------------------
# 9. FastAPI 應用程式（lifespan 管理背景任務與交易所連線）
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    exchange_pool = {name: make_exchange(name) for name in EXCHANGE_CANDIDATES}
    exchange_pool_ref.clear()
    exchange_pool_ref.update(exchange_pool)

    # 預先載入市場資料，讓後續 exchange.market(symbol) 查詢代碼可以直接使用；
    # 單一交易所載入失敗（例如地區限制）不影響另一個，稍後 fetch 階段仍會自動備援。
    for name, exchange in exchange_pool.items():
        try:
            await exchange.load_markets()
        except Exception as exc:  # noqa: BLE001
            logger.warning("交易所 %s 載入市場資料失敗：%s", name, exc)

    load_state_snapshot()  # 嘗試恢復重啟前的部位/歷史紀錄，須在背景迴圈開始前完成

    monitor_task = asyncio.create_task(price_monitor_loop(exchange_pool))
    logger.info(
        "背景多標的監控已啟動（主流幣：%s，掃描名單前 %d 檔，每 %s 秒更新一次）",
        ", ".join(MAJOR_SYMBOLS),
        SCAN_UNIVERSE_SIZE,
        TICK_INTERVAL_SECONDS,
    )

    us_stock_task = asyncio.create_task(us_stock_orb_loop(exchange_pool))
    logger.info(
        "美股 ORB 當沖背景迴圈已啟動（標的：%s，只在美東 %s-%s 交易時段內運作）",
        ", ".join(US_STOCK_SYMBOLS.keys()),
        US_MARKET_OPEN.strftime("%H:%M"),
        US_MARKET_CLOSE.strftime("%H:%M"),
    )

    news_agent_task = asyncio.create_task(news_agent_loop())
    logger.info(
        "AI 智能投研 Agent 背景迴圈已啟動（新聞來源：%s，每 %d 秒一輪）",
        ", ".join(NEWS_RSS_FEEDS.keys()),
        NEWS_SCAN_INTERVAL_SECONDS,
    )

    try:
        yield
    finally:
        monitor_task.cancel()
        us_stock_task.cancel()
        news_agent_task.cancel()
        for task in (monitor_task, us_stock_task, news_agent_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
        save_state_snapshot()  # 正常關機前再存一次，盡量減少關機瞬間的資料落差
        exchange_pool_ref.clear()
        for exchange in exchange_pool.values():
            await exchange.close()
        logger.info("背景監控已關閉，交易所連線已釋放")


app = FastAPI(title="AI 交易訊號 API", lifespan=lifespan)

# 允許所有來源，方便前端（v0 / Next.js）直接串接
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 10. API 路由
# ---------------------------------------------------------------------------

def _to_signal_response(symbol: str, updated_at_fallback: str) -> SignalResponse:
    """讀取單一標的目前狀態並組成 SignalResponse，呼叫端須持有 state.lock。"""
    sym_state = state.symbols.get(symbol)
    signal = sym_state.open_signal if sym_state else None
    current_price = sym_state.current_price if sym_state else None
    updated_at = (sym_state.last_updated if sym_state and sym_state.last_updated else updated_at_fallback)

    monitoring_fields = {
        "donchian_upper": sym_state.donchian_upper if sym_state else None,
        "donchian_lower": sym_state.donchian_lower if sym_state else None,
        "volume_ratio": sym_state.volume_ratio if sym_state else None,
        "funding_rate": (sym_state.smart_money or {}).get("funding_rate") if sym_state else None,
        "top_trader_long_short_ratio": (
            (sym_state.smart_money or {}).get("top_trader_long_short_ratio") if sym_state else None
        ),
        "smart_money_bias": (sym_state.smart_money or {}).get("bias") if sym_state else None,
    }

    if signal is None:
        return SignalResponse(
            symbol=symbol,
            status="NO_SIGNAL",
            current_price=current_price,
            updated_at=updated_at,
            **monitoring_fields,
        )

    return SignalResponse(
        symbol=symbol,
        status="OPEN",
        side=signal["side"],
        entry_price=signal["entry_price"],
        current_price=current_price,
        take_profit=signal["take_profit"],
        stop_loss=signal["stop_loss"],
        stop_loss_pct=signal["stop_loss_pct"],
        leverage=signal["leverage"],
        risk_reward_ratio=RISK_REWARD_RATIO,
        opened_at=signal["opened_at"],
        smart_money_notes=signal.get("smart_money_notes", []),
        updated_at=updated_at,
        **monitoring_fields,
    )


@app.get("/api/signals", response_model=SignalListResponse)
async def get_signals(universe: Literal["major", "scan"] = "major") -> SignalListResponse:
    """
    universe=major：固定回傳 BTC/ETH/SOL 三檔的狀態（不管有沒有訊號都回傳，監控用）。
    universe=scan：只回傳市場掃描名單中「目前真的有觸發訊號」的幣（找機會用）。
    """
    async with state.lock:
        if state.last_tick_at is None:
            raise HTTPException(status_code=503, detail="背景資料尚未就緒，請稍後再試")

        if universe == "major":
            candidate_symbols = list(MAJOR_SYMBOLS)
        else:
            candidate_symbols = [
                s for s in state.scan_universe
                if state.symbols.get(s) and state.symbols[s].open_signal is not None
            ]

        signals = [_to_signal_response(symbol, state.last_tick_at) for symbol in candidate_symbols]
        tracked_symbols = list(state.scan_universe) if universe == "scan" else []

        return SignalListResponse(
            universe=universe, signals=signals, updated_at=state.last_tick_at, tracked_symbols=tracked_symbols
        )


@app.get("/api/history", response_model=HistoryResponse)
async def get_history(symbol: Optional[str] = None) -> HistoryResponse:
    """回傳過去已結算訊號紀錄與勝率統計，可用 ?symbol= 篩選單一標的。"""
    async with state.lock:
        records = [r for r in state.history if symbol is None or r["symbol"] == symbol]
        trades = [
            HistoryItem(
                symbol=record["symbol"],
                side=record["side"],
                entry_price=record["entry_price"],
                exit_price=record["exit_price"],
                take_profit=record["take_profit"],
                stop_loss=record["stop_loss"],
                leverage=record["leverage"],
                result=record["result"],
                pnl_pct=record["pnl_pct"],
                opened_at=record["opened_at"],
                closed_at=record["closed_at"],
                smart_money_notes=record.get("smart_money_notes", []),
            )
            for record in records
        ]

    wins = sum(1 for t in trades if t.result == "WIN")
    losses = sum(1 for t in trades if t.result == "LOSS")
    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0.0

    return HistoryResponse(
        trades=trades,
        stats=HistoryStats(
            total_trades=total,
            wins=wins,
            losses=losses,
            win_rate_pct=round(win_rate, 2),
        ),
    )


@app.get("/api/smart-money", response_model=SmartMoneyResponse)
async def get_smart_money(symbol: str = MAJOR_SYMBOLS[0]) -> SmartMoneyResponse:
    """回傳指定標的目前的合約聰明錢數據快照與偏見判斷。"""
    async with state.lock:
        sym_state = state.symbols.get(symbol)
        snapshot = sym_state.smart_money if sym_state else None
        if snapshot is None:
            raise HTTPException(status_code=503, detail=f"{symbol} 的聰明錢數據尚未就緒，請稍後再試")

        return SmartMoneyResponse(
            symbol=symbol,
            funding_rate=snapshot.get("funding_rate"),
            open_interest_value=snapshot.get("open_interest_value"),
            oi_change_pct=snapshot.get("oi_change_pct"),
            top_trader_long_short_ratio=snapshot.get("top_trader_long_short_ratio"),
            bias=snapshot.get("bias", "Neutral"),
            notes=snapshot.get("notes", []),
            updated_at=snapshot.get("updated_at"),
        )


@app.get("/api/memes", response_model=MemeRadarResponse)
async def get_memes() -> MemeRadarResponse:
    """
    回傳最新觸發爆量警報的迷因幣清單（依觸發時間新到舊），與主流幣訊號完全獨立。
    watchlist 固定回傳 MEME_SYMBOLS 全部，不管有沒有警報，讓前端在「沒爆量」時
    也能顯示目前量能倍數，而不是整頁空白。
    """
    async with state.lock:
        alerts = [
            MemeAlertResponse(
                symbol=record["symbol"],
                volume_multiple=record["volume_multiple"],
                price=record["price"],
                triggered_at=record["triggered_at"],
            )
            for record in state.meme_alerts
        ]
        watchlist = []
        for symbol in MEME_SYMBOLS:
            meme_state = state.meme_states.get(symbol)
            watchlist.append(
                MemeWatchItem(
                    symbol=symbol,
                    price=meme_state.current_price if meme_state else None,
                    volume_multiple=meme_state.volume_multiple if meme_state else None,
                    updated_at=meme_state.last_updated if meme_state else None,
                )
            )
        updated_at = max(
            (s.last_updated for s in state.meme_states.values() if s.last_updated),
            default=None,
        )

    return MemeRadarResponse(alerts=alerts, watchlist=watchlist, updated_at=updated_at)


@app.get("/api/candles", response_model=CandlesListResponse)
async def get_candles(symbol: str, limit: int = 60, timeframe: str = TIMEFRAME) -> CandlesListResponse:
    """
    回傳指定標的最近已收盤的真實K線，供前端畫真實蠟燭圖用（取代原本 demo 用的
    假隨機漫步資料）。跟主流幣策略共用同一支 fetch_ohlcv_for_symbol，資料來源
    一致；不限定只能查 MAJOR_SYMBOLS，市場掃描/迷因幣/美股ORB的標的也能查
    （美股 ORB 前端應傳 timeframe=15m，對齊策略本身用的K線週期）。
    """
    limit = min(max(limit, 10), 300)

    if not exchange_pool_ref:
        raise HTTPException(status_code=503, detail="交易所連線尚未就緒，請稍後再試")

    try:
        df = await fetch_ohlcv_for_symbol(exchange_pool_ref, symbol, timeframe=timeframe, limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"抓取 {symbol} K線失敗：{exc}")

    candles = [
        CandleResponse(
            timestamp=int(row["timestamp"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
        )
        for _, row in df.iterrows()
    ]

    return CandlesListResponse(symbol=symbol, timeframe=timeframe, candles=candles)


def _to_us_stock_response(ticker_symbol: str) -> USStockResponse:
    """讀取單一美股標的目前狀態並組成 USStockResponse，呼叫端須持有 state.lock。"""
    st = state.us_stock_states.get(ticker_symbol)
    display_name = US_STOCK_DISPLAY_BY_SYMBOL.get(ticker_symbol, ticker_symbol)
    signal = st.open_signal if st else None
    updated_at = (st.last_updated if st and st.last_updated else datetime.now(timezone.utc).isoformat())

    monitoring_fields = {
        "current_price": st.current_price if st else None,
        "day_change_pct": st.day_change_pct if st else None,
        "opening_high": st.opening_high if st else None,
        "opening_low": st.opening_low if st else None,
        "rvol": st.rvol if st else None,
        "market_regime": st.market_regime if st else "Neutral",
    }

    if signal is None:
        return USStockResponse(
            symbol=ticker_symbol,
            display_name=display_name,
            status="NO_SIGNAL",
            updated_at=updated_at,
            **monitoring_fields,
        )

    return USStockResponse(
        symbol=ticker_symbol,
        display_name=display_name,
        status="OPEN",
        side=signal["side"],
        entry_price=signal["entry_price"],
        take_profit=signal["take_profit"],
        stop_loss=signal["stop_loss"],
        stop_loss_pct=signal["stop_loss_pct"],
        leverage=signal["leverage"],
        risk_reward_ratio=ORB_RISK_REWARD_RATIO,
        opened_at=signal["opened_at"],
        updated_at=updated_at,
        **monitoring_fields,
    )


@app.get("/api/us-stock-orb", response_model=USStockListResponse)
async def get_us_stock_orb() -> USStockListResponse:
    """
    美股 ORB 當沖（獨立模塊，實驗性策略，未經回測驗證）：固定回傳 US_STOCK_SYMBOLS
    全部標的的狀態（不管有沒有訊號都回傳，監控用），跟主流幣的 universe=major 同樣道理。
    """
    async with state.lock:
        now_et = datetime.now(ZoneInfo(US_MARKET_TZ))
        market_session: Literal["OPEN", "CLOSED"] = "OPEN" if _is_us_market_active(now_et) else "CLOSED"
        stocks = [_to_us_stock_response(sym) for sym in US_STOCK_SYMBOLS.values()]
        regime = state.us_market_regime

    return USStockListResponse(
        market_session=market_session,
        market_regime=regime,
        stocks=stocks,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/api/us-stock-orb/history", response_model=USStockHistoryResponse)
async def get_us_stock_history() -> USStockHistoryResponse:
    """
    回傳美股 ORB 已結算的實盤成交紀錄與統計。這是「真實累積結果」，不是回測——
    上線第一天樣本數會是 0 或個位數，統計上還不具意義，純粹讓實際表現隨時間
    自然累積、可被檢視，取代任何無法驗證的「回測勝率」宣稱。
    """
    async with state.lock:
        records = list(state.us_stock_history)

    trades = [
        USStockHistoryItem(
            symbol=record["symbol"],
            display_name=record["display_name"],
            side=record["side"],
            entry_price=record["entry_price"],
            exit_price=record["exit_price"],
            take_profit=record["take_profit"],
            stop_loss=record["stop_loss"],
            leverage=record["leverage"],
            result=record["result"],
            pnl_pct=record["pnl_pct"],
            opened_at=record["opened_at"],
            closed_at=record["closed_at"],
        )
        for record in records
    ]

    wins = sum(1 for t in trades if t.result == "WIN")
    losses = sum(1 for t in trades if t.result == "LOSS")
    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0.0

    return USStockHistoryResponse(
        trades=trades,
        stats=USStockHistoryStats(
            total_trades=total,
            wins=wins,
            losses=losses,
            win_rate_pct=round(win_rate, 2),
        ),
    )


@app.get("/api/ai-agent/news", response_model=NewsAgentResponse)
async def get_ai_agent_news() -> NewsAgentResponse:
    """
    AI 智能投研 Agent（獨立模塊，實驗性）：回傳最近處理過的新聞，依處理時間新到舊
    排序。未設定 OPENAI_API_KEY 時這裡會一直是空的（新聞有抓，但沒有情緒分析結果
    就不會寫進 state.news_items）。
    """
    async with state.lock:
        items = [NewsItemResponse(**item) for item in state.news_items]
    return NewsAgentResponse(items=items, updated_at=datetime.now(timezone.utc).isoformat())


# --- 【一次性維運用途，用完即刪】強制平倉一筆卡住的舊部位 ---
# LAB/USDT:USDT 因為 MAX_SANE_STOP_LOSS_PCT 防呆修復前產生了一筆止盈價格為負數
# （永遠不可能觸及）的假訊號，需要手動用當下市價結算掉。用 ADMIN_TOKEN 環境變數
# 比對，避免公開網站被任意呼叫操作；用完這次就會在下一個 commit 整段移除。
@app.post("/api/admin/force-close-signal")
async def admin_force_close_signal(symbol: str, token: str) -> dict:
    admin_token = os.environ.get("ADMIN_TOKEN", "").strip()
    if not admin_token or token != admin_token:
        raise HTTPException(status_code=403, detail="unauthorized")

    async with state.lock:
        sym_state = state.symbols.get(symbol)
        if sym_state is None or sym_state.open_signal is None:
            raise HTTPException(status_code=404, detail="no open signal for this symbol")
        current_price = sym_state.current_price
        if current_price is None:
            raise HTTPException(status_code=400, detail="no current price available")

        signal = sym_state.open_signal
        side = signal["side"]
        raw_pnl_pct = (current_price - signal["entry_price"]) / signal["entry_price"] * 100
        if side == "Short":
            raw_pnl_pct = -raw_pnl_pct
        pnl_pct = raw_pnl_pct * signal["leverage"]
        result = "WIN" if pnl_pct >= 0 else "LOSS"

        closed_record = {
            **signal,
            "exit_price": current_price,
            "result": result,
            "pnl_pct": pnl_pct,
            "closed_at": datetime.now(timezone.utc).isoformat(),
        }
        state.history.appendleft(closed_record)
        sym_state.open_signal = None
        append_jsonl(TRADE_LOG_PATH, closed_record)
        save_state_snapshot()

    return {"closed": closed_record}


@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health_check() -> dict:
    """
    簡單的健康檢查端點，方便前端或監控工具確認服務存活。同時支援 GET/HEAD——
    像 UptimeRobot 這類外部監控工具預設會送 HEAD 請求，只註冊 GET 的話每次
    健康檢查都會收到 405，被誤判成服務掛掉（實際上服務是正常的）。
    """
    return {
        "status": "ok",
        "active_exchange": state.active_exchange_name,
        "major_symbols": MAJOR_SYMBOLS,
        "scan_universe_size": len(state.scan_universe),
        "meme_symbols": MEME_SYMBOLS,
        "meme_alert_count": len(state.meme_alerts),
        "last_tick_at": state.last_tick_at,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# 11. 本地啟動入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
