"use client"

import { useEffect, useMemo, useState } from "react"
import useSWR from "swr"
import {
  Activity,
  CandlestickChart,
  Coins,
  Flame,
  FlaskConical,
  Newspaper,
  PieChart,
  Radar,
  ScanSearch,
  Star,
  Target,
  Zap,
  type LucideIcon,
} from "lucide-react"
import {
  adaptHistory,
  adaptLiquidationWalls,
  adaptMemeAlerts,
  adaptMemeTradeHistory,
  adaptMemeTradeList,
  adaptMemeWatchlist,
  adaptNewsAgent,
  adaptOptionsGexList,
  adaptRSI2List,
  adaptSignalList,
  adaptSqueezeFeed,
  adaptUSStockHistory,
  adaptUSStockList,
  adaptWhaleSweep,
  fallbackHistory,
  formatPrice,
  formatTime,
  type BackendHistoryResponse,
  type BackendLiquidationWallsResponse,
  type BackendMemeRadarResponse,
  type BackendMemeTradeHistoryResponse,
  type BackendMemeTradeListResponse,
  type BackendNewsAgentResponse,
  type BackendOptionsGexListResponse,
  type BackendRSI2ListResponse,
  type BackendSignalListResponse,
  type BackendSqueezeFeedResponse,
  type BackendUSStockHistoryResponse,
  type BackendUSStockListResponse,
  type BackendWhaleSweepResponse,
  type NewsCategory,
  type Universe,
} from "@/lib/signals"
import { HeroSignal } from "@/components/hero-signal"
import { PriceLevels } from "@/components/price-levels"
import { PriceRangeGauge } from "@/components/price-range-gauge"
import { SignalChart } from "@/components/signal-chart"
import { RecentHistory } from "@/components/recent-history"
import { SymbolWatchlist } from "@/components/symbol-watchlist"
import { OpportunityList } from "@/components/opportunity-list"
import { MemeRadar } from "@/components/meme-radar"
import { MemeTradeWatchlist } from "@/components/meme-trade-watchlist"
import { MonitoringPanel } from "@/components/monitoring-panel"
import { USStockWatchlist } from "@/components/us-stock-watchlist"
import { USStockMonitoringPanel } from "@/components/us-stock-monitoring-panel"
import { USStockHistory } from "@/components/us-stock-history"
import { NewsRadar } from "@/components/news-radar"
import { SqueezeFeed } from "@/components/squeeze-feed"
import { OptionsAnalyticsPanel } from "@/components/options-analytics-panel"
import { BacktestSandboxPanel } from "@/components/backtest-sandbox-panel"
import { HighWinRatePanel } from "@/components/high-winrate-panel"
import { LiquidationHeatmapChart } from "@/components/liquidation-heatmap-chart"
import { TradingChatbot } from "@/components/trading-chatbot"
import { WatchlistEditor } from "@/components/watchlist-editor"
import { FavoritesOverview } from "@/components/favorites-overview"
import { ThemeToggle } from "@/components/theme-toggle"

const fetcher = (url: string) =>
  fetch(url).then(async (r) => {
    const body = await r.json()
    if (!r.ok) throw new Error(body?.detail ?? `Request failed (${r.status})`)
    return body
  })

// 迷因雷達、迷因當沖、美股ORB、AI輿情雷達、期權分析都是獨立模塊（跟主流幣
// 不同的資料形狀），tab key 因此延伸出 /api/signals 的 Universe 之外。
type TabKey =
  | Universe
  | "meme"
  | "memeTrade"
  | "usStock"
  | "newsAgent"
  | "optionsAnalytics"
  | "backtest"
  | "overview"
  | "highWinRate"

interface TabDef {
  key: TabKey
  label: string
  icon: LucideIcon
}

interface TabCategory {
  key: string
  label: string
  tabs: TabDef[]
}

// 2026-07-16 顧問備忘錄修復：原本十個分頁攤平在同一層，彼此之間沒有任何分組
// 線索。這裡收成五個大分類（總覽/加密貨幣/美股/情報/回測實驗室），分類邊界
// 直接沿用程式碼裡早就存在的 isMemeMode/isUSStockMode 這種資產類別分組方式。
// emoji 換成同一套 lucide-react 圖示，尺寸/粗細一致，不再是「有的分頁有、
// 有的沒有」的不一致標記。
const TAB_CATEGORIES: TabCategory[] = [
  {
    key: "overview",
    label: "總覽",
    tabs: [{ key: "overview", label: "我的關注", icon: Star }],
  },
  {
    key: "crypto",
    label: "加密貨幣",
    tabs: [
      { key: "major", label: "主流幣", icon: Coins },
      { key: "scan", label: "市場掃描", icon: ScanSearch },
      { key: "meme", label: "迷因雷達", icon: Radar },
      { key: "memeTrade", label: "迷因當沖", icon: Flame },
    ],
  },
  {
    key: "usStocks",
    label: "美股",
    tabs: [
      { key: "usStock", label: "美股 ORB", icon: CandlestickChart },
      { key: "optionsAnalytics", label: "期權分析", icon: PieChart },
      { key: "highWinRate", label: "高勝率策略", icon: Target },
    ],
  },
  {
    key: "intel",
    label: "情報",
    tabs: [{ key: "newsAgent", label: "新聞輿情", icon: Newspaper }],
  },
  {
    key: "backtestLab",
    label: "回測實驗室",
    tabs: [{ key: "backtest", label: "回測沙盒", icon: FlaskConical }],
  },
]

function findCategoryForTab(tabKey: TabKey): TabCategory {
  return TAB_CATEGORIES.find((category) => category.tabs.some((tab) => tab.key === tabKey)) ?? TAB_CATEGORIES[0]
}

export function TradeDashboard() {
  const [mode, setMode] = useState<TabKey>("overview")
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)
  const [newsCategory, setNewsCategory] = useState<NewsCategory | "all">("all")
  const [liquidationSymbol, setLiquidationSymbol] = useState<string>("BTC")

  // 目前所在的大分類永遠直接從 mode 反推，不用額外狀態——點大分類本身時，
  // 直接把 mode 切到該分類的第一個子分頁即可，不需要記住「使用者剛點了哪個
  // 分類」這種額外狀態，減少一種可能跟 mode 不同步的情境。
  const activeCategory = findCategoryForTab(mode)

  const isMemeMode = mode === "meme"
  const isMemeTradeMode = mode === "memeTrade"
  const isUSStockMode = mode === "usStock"
  const isNewsAgentMode = mode === "newsAgent"
  const isOptionsMode = mode === "optionsAnalytics"
  const isBacktestMode = mode === "backtest"
  const isOverviewMode = mode === "overview"
  const isHighWinRateMode = mode === "highWinRate"

  const {
    data: rawSignals,
    error: signalsError,
    isLoading: signalsLoading,
  } = useSWR<BackendSignalListResponse>(
    isMemeMode ||
    isMemeTradeMode ||
    isUSStockMode ||
    isNewsAgentMode ||
    isOptionsMode ||
    isBacktestMode ||
    isOverviewMode ||
    isHighWinRateMode
      ? null
      : `/api/signals?universe=${mode}`,
    fetcher,
    { refreshInterval: mode === "major" ? 5000 : 12000 },
  )

  const {
    data: rawMemeTrade,
    error: memeTradeError,
    isLoading: memeTradeLoading,
  } = useSWR<BackendMemeTradeListResponse>(isMemeTradeMode || isOverviewMode ? "/api/meme-trade" : null, fetcher, {
    refreshInterval: 5000,
  })

  const { data: rawMemeTradeHistory, error: memeTradeHistoryError } = useSWR<BackendMemeTradeHistoryResponse>(
    isMemeTradeMode ? "/api/meme-trade/history" : null,
    fetcher,
    { refreshInterval: 15000 },
  )

  // 📊 期權分析：美股盤中 GEX 剖面每分鐘才會重算一次，不需要跟加密貨幣一樣
  // 秒級輪詢；大單流稍微快一點，才不會漏掉盤中即時的大單事件。
  const {
    data: rawOptionsGex,
    error: optionsGexError,
    isLoading: optionsGexLoading,
  } = useSWR<BackendOptionsGexListResponse>(isOptionsMode || isOverviewMode ? "/api/options/gex" : null, fetcher, {
    refreshInterval: 30000,
  })

  const {
    data: rawWhaleSweep,
    isLoading: whaleSweepLoading,
  } = useSWR<BackendWhaleSweepResponse>(isOptionsMode || isOverviewMode ? "/api/options/whale-sweep" : null, fetcher, {
    refreshInterval: 15000,
  })

  const {
    data: rawMemes,
    error: memesError,
    isLoading: memesLoading,
  } = useSWR<BackendMemeRadarResponse>(isMemeMode || isOverviewMode ? "/api/memes" : null, fetcher, {
    refreshInterval: 15000,
  })

  const {
    data: rawUSStocks,
    error: usStocksError,
    isLoading: usStocksLoading,
  } = useSWR<BackendUSStockListResponse>(isUSStockMode || isOverviewMode ? "/api/us-stock-orb" : null, fetcher, {
    refreshInterval: isOverviewMode ? 15000 : 3000,
  })

  const {
    data: rawUSStockHistory,
    error: usStockHistoryError,
  } = useSWR<BackendUSStockHistoryResponse>(isUSStockMode ? "/api/us-stock-orb/history" : null, fetcher, {
    refreshInterval: 15000,
  })

  const {
    data: rawNews,
    error: newsError,
    isLoading: newsLoading,
  } = useSWR<BackendNewsAgentResponse>(isNewsAgentMode || isOverviewMode ? "/api/ai-agent/news" : null, fetcher, {
    refreshInterval: 30000,
  })

  const { data: rawHistory, error: historyError } = useSWR<BackendHistoryResponse>("/api/history", fetcher, {
    refreshInterval: 15000,
  })

  // Squeeze Mode 的 green 燈號滾動牆：市場掃描跟迷因雷達共用同一份資料
  const isSqueezeFeedMode = mode === "scan" || isMemeMode
  const {
    data: rawSqueezeFeed,
    isLoading: squeezeFeedLoading,
  } = useSWR<BackendSqueezeFeedResponse>(isSqueezeFeedMode || isOverviewMode ? "/api/squeeze-feed" : null, fetcher, {
    refreshInterval: 20000,
  })

  // ⭐ 我的關注戰情室摘要用：主流幣/市場掃描的持倉數（rawSignals 綁定單一
  // universe 字串，總覽頁需要兩個都看，所以另外開兩支輕量的），以及RSI2
  // 均值回歸清單（高勝率策略分頁本身是獨立元件自己抓資料，這裡總覽頁需要
  // 另外抓一次算「目前幾檔有部位」）。
  const { data: rawMajorSignalsOverview } = useSWR<BackendSignalListResponse>(
    isOverviewMode ? "/api/signals?universe=major" : null,
    fetcher,
    { refreshInterval: 20000 },
  )
  const { data: rawScanSignalsOverview } = useSWR<BackendSignalListResponse>(
    isOverviewMode ? "/api/signals?universe=scan" : null,
    fetcher,
    { refreshInterval: 20000 },
  )
  const { data: rawRsi2Overview } = useSWR<BackendRSI2ListResponse>(
    isOverviewMode ? "/api/rsi2-meanrev" : null,
    fetcher,
    { refreshInterval: 20000 },
  )

  const { data: rawLiquidationWalls } = useSWR<BackendLiquidationWallsResponse>(
    mode === "major" ? "/api/market/liquidation-walls" : null,
    fetcher,
    { refreshInterval: 30000 },
  )
  const liquidationWalls = useMemo(
    () => (rawLiquidationWalls ? adaptLiquidationWalls(rawLiquidationWalls) : []),
    [rawLiquidationWalls],
  )
  const selectedLiquidationWall = liquidationWalls.find((w) => w.symbol === liquidationSymbol) ?? null

  const signals = useMemo(() => (rawSignals ? adaptSignalList(rawSignals) : []), [rawSignals])
  const memeAlerts = useMemo(() => (rawMemes ? adaptMemeAlerts(rawMemes) : []), [rawMemes])
  const memeWatchlist = useMemo(() => (rawMemes ? adaptMemeWatchlist(rawMemes) : []), [rawMemes])
  const squeezeFeedItems = useMemo(() => (rawSqueezeFeed ? adaptSqueezeFeed(rawSqueezeFeed) : []), [rawSqueezeFeed])
  const usStockData = useMemo(
    () => (rawUSStocks ? adaptUSStockList(rawUSStocks) : { marketSession: "CLOSED" as const, marketRegime: "Neutral" as const, stocks: [] }),
    [rawUSStocks],
  )
  const usStockHistoryData = useMemo(
    () =>
      rawUSStockHistory
        ? adaptUSStockHistory(rawUSStockHistory)
        : { trades: [], stats: { totalTrades: 0, wins: 0, losses: 0, winRatePct: 0 } },
    [rawUSStockHistory],
  )
  const newsItems = useMemo(() => (rawNews ? adaptNewsAgent(rawNews) : []), [rawNews])
  const filteredNewsItems = useMemo(
    () => (newsCategory === "all" ? newsItems : newsItems.filter((item) => item.category === newsCategory)),
    [newsItems, newsCategory],
  )
  const memeTradeCoins = useMemo(() => (rawMemeTrade ? adaptMemeTradeList(rawMemeTrade) : []), [rawMemeTrade])
  const memeTradeHistoryData = useMemo(
    () =>
      rawMemeTradeHistory
        ? adaptMemeTradeHistory(rawMemeTradeHistory)
        : { trades: [], stats: { totalTrades: 0, wins: 0, losses: 0, winRatePct: 0 } },
    [rawMemeTradeHistory],
  )
  const optionsGexData = useMemo(
    () =>
      rawOptionsGex
        ? adaptOptionsGexList(rawOptionsGex)
        : { underlyings: [], dataSourceOk: false, moomooOnline: false },
    [rawOptionsGex],
  )
  const whaleSweepItems = useMemo(() => (rawWhaleSweep ? adaptWhaleSweep(rawWhaleSweep) : []), [rawWhaleSweep])
  const { trades: history, stats } = rawHistory ? adaptHistory(rawHistory) : fallbackHistory

  // ⭐ 我的關注戰情室：每個模塊貢獻一行最精簡的摘要，點下去直接跳去對應
  // 分頁——這樣打開網站第一眼看到的是「整個系統現在的狀態」，不用先猜十個
  // 分頁分別代表什麼。只在總覽頁計算，其餘分頁這些 raw*Overview 都是 undefined。
  const moduleSummaries = useMemo(() => {
    if (!isOverviewMode) return []
    const majorOpen = rawMajorSignalsOverview ? adaptSignalList(rawMajorSignalsOverview).filter((s) => s.status === "OPEN").length : null
    const scanOpen = rawScanSignalsOverview ? adaptSignalList(rawScanSignalsOverview).filter((s) => s.status === "OPEN").length : null
    const memeTradeOpen = rawMemeTrade ? adaptMemeTradeList(rawMemeTrade).filter((s) => s.status === "OPEN").length : null
    const rsi2Open = rawRsi2Overview ? adaptRSI2List(rawRsi2Overview).stocks.filter((s) => s.status === "OPEN").length : null

    return [
      { key: "major" as const, icon: Coins, label: "主流幣", value: majorOpen === null ? "載入中…" : `${majorOpen} 個持倉中訊號` },
      { key: "scan" as const, icon: ScanSearch, label: "市場掃描", value: scanOpen === null ? "載入中…" : `${scanOpen} 個持倉中訊號` },
      { key: "meme" as const, icon: Radar, label: "迷因雷達", value: rawMemes ? `${memeAlerts.length} 筆爆量警報` : "載入中…" },
      { key: "memeTrade" as const, icon: Flame, label: "迷因當沖", value: memeTradeOpen === null ? "載入中…" : `${memeTradeOpen} 個持倉中訊號` },
      { key: "usStock" as const, icon: CandlestickChart, label: "美股 ORB", value: rawUSStocks ? `${usStockData.stocks.filter((s) => s.status === "OPEN").length} 個持倉中訊號` : "載入中…" },
      { key: "optionsAnalytics" as const, icon: PieChart, label: "期權分析", value: rawOptionsGex ? `${optionsGexData.underlyings.length} 檔自選標的` : "載入中…" },
      { key: "highWinRate" as const, icon: Target, label: "高勝率策略", value: rsi2Open === null ? "載入中…" : `${rsi2Open} 個持倉中訊號` },
      { key: "newsAgent" as const, icon: Newspaper, label: "新聞輿情", value: rawNews ? `${newsItems.length} 則已分析新聞` : "載入中…" },
    ]
  }, [
    isOverviewMode,
    rawMajorSignalsOverview,
    rawScanSignalsOverview,
    rawMemeTrade,
    rawRsi2Overview,
    rawMemes,
    memeAlerts.length,
    rawUSStocks,
    usStockData.stocks,
    rawOptionsGex,
    optionsGexData.underlyings.length,
    rawNews,
    newsItems.length,
  ])

  // Keep the selection sane across tab switches and data refreshes: default
  // to the first open opportunity, and re-pick if the current selection
  // disappears (its signal closed, or it dropped out of the scan ranking).
  useEffect(() => {
    if (isUSStockMode) {
      if (usStockData.stocks.length === 0) {
        setSelectedSymbol(null)
        return
      }
      const stillPresent = usStockData.stocks.some((s) => s.symbol === selectedSymbol)
      if (!stillPresent) {
        const firstOpen = usStockData.stocks.find((s) => s.status === "OPEN")
        setSelectedSymbol((firstOpen ?? usStockData.stocks[0]).symbol)
      }
      return
    }

    if (isMemeTradeMode) {
      if (memeTradeCoins.length === 0) {
        setSelectedSymbol(null)
        return
      }
      const stillPresent = memeTradeCoins.some((c) => c.symbol === selectedSymbol)
      if (!stillPresent) {
        const firstOpen = memeTradeCoins.find((c) => c.status === "OPEN")
        setSelectedSymbol((firstOpen ?? memeTradeCoins[0]).symbol)
      }
      return
    }

    if (signals.length === 0) {
      setSelectedSymbol(null)
      return
    }
    const stillPresent = signals.some((s) => s.symbol === selectedSymbol)
    if (!stillPresent) {
      const firstOpen = signals.find((s) => s.status === "OPEN")
      setSelectedSymbol((firstOpen ?? signals[0]).symbol)
    }
  }, [signals, usStockData, isUSStockMode, isMemeTradeMode, memeTradeCoins, selectedSymbol])

  const selected = signals.find((s) => s.symbol === selectedSymbol) ?? null
  const selectedUSStock = usStockData.stocks.find((s) => s.symbol === selectedSymbol) ?? null
  const selectedMemeTrade = memeTradeCoins.find((c) => c.symbol === selectedSymbol) ?? null

  const activeError = isBacktestMode || isHighWinRateMode
    ? undefined
    : isOverviewMode
      // 2026-07-12 稽核修復：原本要「兩個來源同時出錯」才顯示頂部錯誤橫幅，
      // 單一來源失敗完全不會被看到。現在任一來源出錯就標示（優先顯示期權，
      // 兩個都掛時哪個優先其實不重要），細節仍看 FavoritesOverview 內的
      // 各自區塊錯誤訊息。
      ? (optionsGexError ?? usStocksError)
      : isMemeMode
        ? memesError
        : isMemeTradeMode
          ? memeTradeError
          : isUSStockMode
            ? usStocksError
            : isNewsAgentMode
              ? newsError
              : isOptionsMode
                ? optionsGexError
                : signalsError
  const activeLoading = isBacktestMode || isHighWinRateMode
    ? false
    : isOverviewMode
      ? optionsGexLoading || usStocksLoading
      : isMemeMode
        ? memesLoading
        : isMemeTradeMode
          ? memeTradeLoading
          : isUSStockMode
            ? usStocksLoading
            : isNewsAgentMode
              ? newsLoading
              : isOptionsMode
                ? optionsGexLoading
                : signalsLoading
  const isConnected = isBacktestMode || isHighWinRateMode
    ? true
    : isOverviewMode
      ? (!optionsGexError && !!rawOptionsGex) || (!usStocksError && !!rawUSStocks)
      : isMemeMode
        ? !memesError && !!rawMemes
        : isMemeTradeMode
          ? !memeTradeError && !!rawMemeTrade
          : isUSStockMode
            ? !usStocksError && !!rawUSStocks
            : isNewsAgentMode
              ? !newsError && !!rawNews
              : isOptionsMode
                ? !optionsGexError && !!rawOptionsGex
                : !signalsError && !!rawSignals
  const statusLabel = activeError ? "Backend offline" : activeLoading ? "Syncing…" : "Connected"

  return (
    <>
    <main className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-5 px-4 py-6 md:px-8 md:py-10">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Zap className="size-5" aria-hidden="true" />
          </span>
          <div className="flex flex-col leading-none">
            <span className="font-mono text-lg font-bold tracking-tight">Weng Crypto</span>
            <span className="text-xs text-muted-foreground">AI Signal Terminal</span>
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          <div
            className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs ${
              activeError ? "border-short/40 bg-short/10 text-short" : "border-border/60 bg-card text-muted-foreground"
            }`}
          >
            <Activity className={`size-3.5 ${isConnected ? "text-long" : ""}`} aria-hidden="true" />
            {statusLabel}
          </div>
          <ThemeToggle />
        </div>
      </header>

      <div className="flex flex-col gap-2">
        <div className="flex w-fit gap-1 rounded-full border border-border/60 bg-card p-1">
          {TAB_CATEGORIES.map((category) => (
            <button
              key={category.key}
              type="button"
              onClick={() => setMode(category.tabs[0].key)}
              className={`rounded-full px-4 py-1.5 text-sm font-semibold transition-colors ${
                activeCategory.key === category.key
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {category.label}
            </button>
          ))}
        </div>

        {activeCategory.tabs.length > 1 && (
          <div className="flex w-fit gap-1 rounded-xl border border-border/60 bg-card/60 p-1">
            {activeCategory.tabs.map((tab) => {
              const Icon = tab.icon
              return (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setMode(tab.key)}
                  className={`flex items-center gap-1.5 rounded-lg px-3 py-1 text-xs font-semibold transition-colors ${
                    mode === tab.key
                      ? "bg-secondary text-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <Icon className="size-3.5" aria-hidden="true" />
                  {tab.label}
                </button>
              )
            })}
          </div>
        )}
      </div>

      {activeError && (
        <div className="rounded-xl border border-short/30 bg-short/[0.06] px-4 py-3 text-sm text-short">
          無法連線到後端 API：{activeError.message}。請確認 FastAPI 服務是否已在本機啟動（
          <code className="font-mono">uvicorn main:app --reload --port 8000</code>）。
        </div>
      )}

      {isOverviewMode ? (
        <FavoritesOverview
          optionsUnderlyings={optionsGexData.underlyings}
          optionsLoading={optionsGexLoading}
          optionsError={optionsGexError?.message}
          usStocks={usStockData.stocks}
          usStocksLoading={usStocksLoading}
          usStocksError={usStocksError?.message}
          whaleSweepItems={whaleSweepItems}
          moduleSummaries={moduleSummaries}
          onSelectModule={(key) => setMode(key as TabKey)}
          onSelectOptions={(symbol) => {
            setSelectedSymbol(symbol)
            setMode("optionsAnalytics")
          }}
          onSelectUSStock={(symbol) => {
            setSelectedSymbol(symbol)
            setMode("usStock")
          }}
        />
      ) : isMemeMode ? (
        <>
          <MemeRadar alerts={memeAlerts} watchlist={memeWatchlist} isLoading={memesLoading} error={memesError?.message} />
          <SqueezeFeed items={squeezeFeedItems} isLoading={squeezeFeedLoading} />
          <p className="text-center text-xs text-muted-foreground">
            迷因幣雷達為獨立功能：從迷因幣候選池依 24h 成交量動態排名監控前 10 大，純粹偵測現貨的成交量異常放大
            （同時標示是拉盤還是砸盤），不是交易訊號，沒有方向、槓桿或 TP/SL。⚡ 爆破狀態燈號（Squeeze
            Mode）是額外疊加的實驗性判斷，未經回測驗證。
          </p>
        </>
      ) : isMemeTradeMode ? (
        <>
          <MemeTradeWatchlist coins={memeTradeCoins} selectedSymbol={selectedSymbol} onSelect={setSelectedSymbol} />

          {selectedMemeTrade && selectedMemeTrade.status === "OPEN" && selectedMemeTrade.signal ? (
            <HeroSignal signal={selectedMemeTrade.signal} />
          ) : selectedMemeTrade ? (
            <NoActiveSignal
              symbol={selectedMemeTrade.displayName}
              currentPrice={selectedMemeTrade.currentPrice}
              updatedAt={selectedMemeTrade.updatedAt ?? new Date().toISOString()}
            />
          ) : (
            !memeTradeError && (
              <div className="rounded-2xl border border-dashed border-border/60 bg-card/40 p-6 text-center text-sm text-muted-foreground">
                資料載入中…
              </div>
            )
          )}

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
            <div className="flex flex-col gap-5 lg:col-span-2">
              {selectedMemeTrade && selectedMemeTrade.status === "OPEN" && selectedMemeTrade.signal ? (
                <>
                  <SignalChart signal={selectedMemeTrade.signal} candleSymbol={selectedMemeTrade.symbol} timeframe="1h" />
                  <PriceRangeGauge signal={selectedMemeTrade.signal} />
                </>
              ) : (
                <div className="flex min-h-[280px] flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-border/60 bg-card/40 p-8 text-center text-sm text-muted-foreground">
                  <Radar className="size-6" aria-hidden="true" />
                  目前無持倉，等待引擎偵測到 1H 爆量訊號（成交量≥24h均量3倍 + 方向確認）。
                </div>
              )}
            </div>
            <div className="flex flex-col gap-5">
              {selectedMemeTrade && selectedMemeTrade.status === "OPEN" && selectedMemeTrade.signal && (
                <PriceLevels signal={selectedMemeTrade.signal} />
              )}
            </div>
          </div>

          <USStockHistory
            title="實盤成交紀錄（迷因當沖）"
            trades={memeTradeHistoryData.trades}
            stats={memeTradeHistoryData.stats}
            error={memeTradeHistoryError?.message}
          />

          <p className="text-center text-xs text-muted-foreground">
            迷因當沖為正式實盤功能：僅 WIF / DOGE 上線——180天回測裡唯二樣本數跨過統計門檻的幣種（WIF 19筆
            PF1.36、DOGE 20筆 PF1.46），其餘迷因雷達候選幣沒有被驗證過，不會自動加入這個策略。
            <strong className="text-foreground">30天單一窗口回測不保證樣本外表現</strong>，請持續觀察上方實盤紀錄。
            訊號邏輯：1H成交量≥24h均量3倍+方向確認，ATR×1.5停損，盈虧比2:1。
          </p>
        </>
      ) : isUSStockMode ? (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border/60 bg-card/60 px-4 py-2.5 text-xs">
            <span className="flex items-center gap-1.5">
              <span
                className={`size-1.5 rounded-full ${usStockData.marketSession === "OPEN" ? "bg-long" : "bg-muted-foreground"}`}
                aria-hidden="true"
              />
              美股當沖時段：{usStockData.marketSession === "OPEN" ? "開盤中" : "休市中（美東 09:15-16:00 才運作）"}
            </span>
            <span className="text-muted-foreground">
              大盤濾網（NASDAQ100）：
              <span
                className={
                  usStockData.marketRegime === "Bullish"
                    ? "text-long"
                    : usStockData.marketRegime === "Bearish"
                      ? "text-short"
                      : "text-foreground"
                }
              >
                {" "}
                {usStockData.marketRegime === "Bullish" ? "偏多" : usStockData.marketRegime === "Bearish" ? "偏空" : "中性"}
              </span>
            </span>
          </div>

          <USStockWatchlist stocks={usStockData.stocks} selectedSymbol={selectedSymbol} onSelect={setSelectedSymbol} />

          <WatchlistEditor
            watchlistUrl="/api/us-stock/watchlist"
            dataUrl="/api/us-stock-orb"
            catalogUrl="/api/us-stock/catalog"
            placeholder="搜尋 BingX 代幣化美股/指數，例如 AAPL"
            maxSize={30}
          />

          {selectedUSStock && selectedUSStock.status === "OPEN" && selectedUSStock.signal ? (
            <HeroSignal signal={selectedUSStock.signal} />
          ) : selectedUSStock ? (
            <NoActiveSignal
              symbol={selectedUSStock.displayName}
              currentPrice={selectedUSStock.currentPrice}
              updatedAt={selectedUSStock.updatedAt}
            />
          ) : (
            !usStocksError && (
              <div className="rounded-2xl border border-dashed border-border/60 bg-card/40 p-6 text-center text-sm text-muted-foreground">
                資料載入中…
              </div>
            )
          )}

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
            <div className="flex flex-col gap-5 lg:col-span-2">
              {selectedUSStock && selectedUSStock.status === "OPEN" && selectedUSStock.signal ? (
                <>
                  <SignalChart signal={selectedUSStock.signal} candleSymbol={selectedUSStock.symbol} timeframe="15m" />
                  <PriceRangeGauge signal={selectedUSStock.signal} />
                </>
              ) : selectedUSStock ? (
                <USStockMonitoringPanel
                  monitoring={selectedUSStock.orbMonitoring}
                  currentPrice={selectedUSStock.currentPrice}
                />
              ) : (
                <div className="flex min-h-[280px] flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-border/60 bg-card/40 p-8 text-center text-sm text-muted-foreground">
                  <Radar className="size-6" aria-hidden="true" />
                  選一檔美股查看開盤區間監控，或等待引擎掃描到新的 ORB 訊號。
                </div>
              )}
            </div>
            <div className="flex flex-col gap-5">
              {selectedUSStock && selectedUSStock.status === "OPEN" && selectedUSStock.signal && (
                <PriceLevels signal={selectedUSStock.signal} />
              )}
            </div>
          </div>

          <USStockHistory
            trades={usStockHistoryData.trades}
            stats={usStockHistoryData.stats}
            error={usStockHistoryError?.message}
          />

          <p className="text-center text-xs text-muted-foreground">
            美股 ORB 當沖為獨立功能：開盤區間突破 + RVOL 過濾 + 大盤濾網，
            <strong className="text-foreground">尚未經過回測驗證，勝率未知</strong>
            ，標的為 BingX 代幣化美股商品，可在上方自選清單自由增刪（目前上架約252檔可選），僅在美東交易時段運作。
          </p>
        </>
      ) : isNewsAgentMode ? (
        <>
          <div className="flex w-fit gap-1 rounded-full border border-border/60 bg-card p-1">
            {(["all", "crypto", "us_stock"] as const).map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setNewsCategory(cat)}
                className={`rounded-full px-3.5 py-1 text-xs font-semibold transition-colors ${
                  newsCategory === cat
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {cat === "all" ? "全部" : cat === "crypto" ? "加密貨幣" : "美股"}
              </button>
            ))}
          </div>
          <NewsRadar items={filteredNewsItems} isLoading={newsLoading} error={newsError?.message} />
          <p className="text-center text-xs text-muted-foreground">
            新聞（AI 智能輿情雷達）為獨立功能：背景每 10 分鐘掃描 CoinDesk / CoinTelegraph / Yahoo Finance / CNBC
            等公開新聞來源，交給 AI 判斷相關標的與情緒分數（-10~+10），純粹是資訊監控，
            <strong className="text-foreground">不是交易訊號</strong>，沒有方向、槓桿或 TP/SL。分類依 AI
            判斷出的標的自動歸類加密貨幣／美股，沒有明確標的時預設歸美股。
          </p>
        </>
      ) : isOptionsMode ? (
        <>
          <OptionsAnalyticsPanel
            underlyings={optionsGexData.underlyings}
            whaleSweepItems={whaleSweepItems}
            dataSourceOk={optionsGexData.dataSourceOk}
            moomooOnline={optionsGexData.moomooOnline}
            isLoading={optionsGexLoading}
            whaleSweepLoading={whaleSweepLoading}
            initialSymbol={selectedSymbol}
          />
          <p className="text-center text-xs text-muted-foreground">
            期權分析為獨立功能：串接 yfinance 期權鏈，自行用 Black-Scholes 模型計算 Gamma
            曝險（GEX）分佈與擠壓臨界點，<strong className="text-foreground">純粹是造市商部位結構的參考資訊，不是交易訊號</strong>
            ，沒有方向、槓桿或 TP/SL。可在上方自選清單自由輸入任意美股代號增刪監控標的，僅在美股交易時段更新。期權大單即時流
            資料源自使用者本機執行的 Moomoo Whale Sweep 監聽工具（選擇性回傳），Live/Standby
            燈號代表本機監聽目前是否在線，離線時 GEX 主面板不受影響、只是大單清單不會有新資料。
          </p>
        </>
      ) : isHighWinRateMode ? (
        <>
          <HighWinRatePanel />
          <p className="text-center text-xs text-muted-foreground">
            高勝率策略為獨立實盤監控功能：只在美股交易時段運作，即時跟蹤現價 vs SMA200/SMA5/RSI(2)，
            <strong className="text-foreground">進場判斷永遠只認前一天已確認收盤的訊號</strong>
            ，不會被盤中估算值誤導。均值回歸策略平均持倉1-3天，設計目標是高勝率+低回撤，不是跟大盤比總報酬。
            單次回測/滾動式驗證請至「🚀 回測沙盒」分頁。
          </p>
        </>
      ) : isBacktestMode ? (
        <>
          <BacktestSandboxPanel />
          <p className="text-center text-xs text-muted-foreground">
            回測沙盒為獨立功能：真實抓取歷史K線並模擬策略進出場，
            <strong className="text-foreground">不是即時交易訊號</strong>
            ，樣本數不足15筆時請勿把結果當成已驗證的勝率。公開端點有IP限流（15次/小時）。
          </p>
        </>
      ) : (
        <>
          {mode === "major" ? (
            <SymbolWatchlist signals={signals} selectedSymbol={selectedSymbol} onSelect={setSelectedSymbol} />
          ) : (
            <>
              <OpportunityList
                signals={signals}
                trackedSymbols={rawSignals?.tracked_symbols ?? []}
                selectedSymbol={selectedSymbol}
                onSelect={setSelectedSymbol}
                isLoading={signalsLoading}
              />
              <SqueezeFeed items={squeezeFeedItems} isLoading={squeezeFeedLoading} />
            </>
          )}

          {selected && selected.status === "OPEN" && selected.signal ? (
            <HeroSignal signal={selected.signal} />
          ) : selected ? (
            <NoActiveSignal
              symbol={selected.symbol}
              currentPrice={selected.currentPrice}
              updatedAt={selected.updatedAt}
            />
          ) : (
            // In scan mode, OpportunityList above already renders the "no
            // opportunities yet" empty state — showing it again here would just
            // repeat the same sentence, so this fallback is major-mode only.
            !signalsError &&
            mode === "major" && (
              <div className="rounded-2xl border border-dashed border-border/60 bg-card/40 p-6 text-center text-sm text-muted-foreground">
                資料載入中…
              </div>
            )
          )}

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
            <div className="flex flex-col gap-5 lg:col-span-2">
              {selected && selected.status === "OPEN" && selected.signal ? (
                <>
                  <SignalChart signal={selected.signal} />
                  <PriceRangeGauge signal={selected.signal} />
                </>
              ) : mode === "major" && selected ? (
                <MonitoringPanel monitoring={selected.monitoring} currentPrice={selected.currentPrice} />
              ) : (
                <div className="flex min-h-[280px] flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-border/60 bg-card/40 p-8 text-center text-sm text-muted-foreground">
                  <Radar className="size-6" aria-hidden="true" />
                  選一筆機會查看詳細圖表，或等待引擎掃描到新的機會。
                </div>
              )}
            </div>
            <div className="flex flex-col gap-5">
              {selected && selected.status === "OPEN" && selected.signal && <PriceLevels signal={selected.signal} />}
              <RecentHistory history={history} stats={stats} error={historyError?.message} />
            </div>
          </div>

          {mode === "major" && (
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <h2 className="font-mono text-sm font-semibold text-muted-foreground">💥 幣圈爆倉密度清算牆</h2>
                <div className="flex gap-1 rounded-full border border-border/60 bg-card p-1">
                  {liquidationWalls.map((w) => (
                    <button
                      key={w.symbol}
                      type="button"
                      onClick={() => setLiquidationSymbol(w.symbol)}
                      className={`rounded-full px-3 py-1 font-mono text-xs font-semibold transition-colors ${
                        liquidationSymbol === w.symbol
                          ? "bg-primary text-primary-foreground"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {w.symbol}
                    </button>
                  ))}
                </div>
              </div>
              {selectedLiquidationWall && <LiquidationHeatmapChart data={selectedLiquidationWall} />}
            </div>
          )}
        </>
      )}

      <footer className="mt-2 flex items-start gap-2 rounded-xl border border-border/60 bg-card/60 p-4 text-xs leading-relaxed text-muted-foreground">
        <p>
          本網站顯示的訊號由自動化演算法產生，<strong className="text-foreground">僅供研究與參考，不構成任何投資建議</strong>
          ，策略本身仍在驗證階段、過去（含回測）表現不代表未來結果。加密貨幣槓桿交易風險極高，可能導致本金全部損失，請自行判斷風險並對自己的交易決策負責。
        </p>
      </footer>
    </main>
    <TradingChatbot />
    </>
  )
}

function NoActiveSignal({
  symbol,
  currentPrice,
  updatedAt,
}: {
  symbol: string
  currentPrice: number | null
  updatedAt: string
}) {
  return (
    <section className="relative overflow-hidden rounded-2xl border border-border/60 bg-card p-6 md:p-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-col gap-2">
          <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-secondary px-3 py-1 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            No Active Signal
          </span>
          <h1 className="font-mono text-3xl font-bold tracking-tight text-balance md:text-4xl">{symbol}</h1>
          <p className="text-xs text-muted-foreground">Last checked {formatTime(updatedAt)} · Weng Crypto AI Engine</p>
        </div>
        {currentPrice !== null && (
          <div className="flex flex-col gap-1 rounded-xl border border-border/60 bg-card/60 p-5 md:min-w-[220px] md:text-right">
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Current Price</span>
            <span className="font-mono text-3xl font-bold md:text-4xl">${formatPrice(currentPrice)}</span>
          </div>
        )}
      </div>
    </section>
  )
}
