"use client"

import { useEffect, useMemo, useState } from "react"
import useSWR from "swr"
import { Activity, AlertTriangle, Radar, Zap } from "lucide-react"
import {
  adaptHistory,
  adaptMemeAlerts,
  adaptMemeWatchlist,
  adaptNewsAgent,
  adaptOptionsGexList,
  adaptSignalList,
  adaptSqueezeFeed,
  adaptUSStockHistory,
  adaptUSStockList,
  adaptWhaleSweep,
  fallbackHistory,
  formatPrice,
  formatTime,
  type BackendHistoryResponse,
  type BackendMemeRadarResponse,
  type BackendNewsAgentResponse,
  type BackendOptionsGexListResponse,
  type BackendSignalListResponse,
  type BackendSqueezeFeedResponse,
  type BackendUSStockHistoryResponse,
  type BackendUSStockListResponse,
  type BackendWhaleSweepResponse,
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
import { MonitoringPanel } from "@/components/monitoring-panel"
import { USStockWatchlist } from "@/components/us-stock-watchlist"
import { USStockMonitoringPanel } from "@/components/us-stock-monitoring-panel"
import { USStockHistory } from "@/components/us-stock-history"
import { NewsRadar } from "@/components/news-radar"
import { SqueezeFeed } from "@/components/squeeze-feed"
import { OptionsAnalyticsPanel } from "@/components/options-analytics-panel"
import { TradingChatbot } from "@/components/trading-chatbot"

const fetcher = (url: string) =>
  fetch(url).then(async (r) => {
    const body = await r.json()
    if (!r.ok) throw new Error(body?.detail ?? `Request failed (${r.status})`)
    return body
  })

// 迷因雷達、美股ORB、AI輿情雷達、期權分析都是獨立模塊（跟主流幣不同的資料
// 形狀），tab key 因此延伸出 /api/signals 的 Universe 之外。
type TabKey = Universe | "meme" | "usStock" | "newsAgent" | "optionsAnalytics"

const TABS: { key: TabKey; label: string }[] = [
  { key: "major", label: "主流幣" },
  { key: "scan", label: "市場掃描" },
  { key: "meme", label: "迷因雷達" },
  { key: "usStock", label: "美股 ORB" },
  { key: "newsAgent", label: "AI 智能輿情雷達" },
  { key: "optionsAnalytics", label: "📊 期權分析" },
]

export function TradeDashboard() {
  const [mode, setMode] = useState<TabKey>("major")
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)

  const isMemeMode = mode === "meme"
  const isUSStockMode = mode === "usStock"
  const isNewsAgentMode = mode === "newsAgent"
  const isOptionsMode = mode === "optionsAnalytics"

  const {
    data: rawSignals,
    error: signalsError,
    isLoading: signalsLoading,
  } = useSWR<BackendSignalListResponse>(
    isMemeMode || isUSStockMode || isNewsAgentMode || isOptionsMode ? null : `/api/signals?universe=${mode}`,
    fetcher,
    { refreshInterval: mode === "major" ? 5000 : 12000 },
  )

  // 📊 期權分析：美股盤中 GEX 剖面每分鐘才會重算一次，不需要跟加密貨幣一樣
  // 秒級輪詢；大單流稍微快一點，才不會漏掉盤中即時的大單事件。
  const {
    data: rawOptionsGex,
    error: optionsGexError,
    isLoading: optionsGexLoading,
  } = useSWR<BackendOptionsGexListResponse>(isOptionsMode ? "/api/options/gex" : null, fetcher, {
    refreshInterval: 30000,
  })

  const {
    data: rawWhaleSweep,
    isLoading: whaleSweepLoading,
  } = useSWR<BackendWhaleSweepResponse>(isOptionsMode ? "/api/options/whale-sweep" : null, fetcher, {
    refreshInterval: 15000,
  })

  const {
    data: rawMemes,
    error: memesError,
    isLoading: memesLoading,
  } = useSWR<BackendMemeRadarResponse>(isMemeMode ? "/api/memes" : null, fetcher, {
    refreshInterval: 15000,
  })

  const {
    data: rawUSStocks,
    error: usStocksError,
    isLoading: usStocksLoading,
  } = useSWR<BackendUSStockListResponse>(isUSStockMode ? "/api/us-stock-orb" : null, fetcher, {
    refreshInterval: 3000,
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
  } = useSWR<BackendNewsAgentResponse>(isNewsAgentMode ? "/api/ai-agent/news" : null, fetcher, {
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
  } = useSWR<BackendSqueezeFeedResponse>(isSqueezeFeedMode ? "/api/squeeze-feed" : null, fetcher, {
    refreshInterval: 20000,
  })

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
  const optionsGexData = useMemo(
    () => (rawOptionsGex ? adaptOptionsGexList(rawOptionsGex) : { underlyings: [], dataSourceOk: false }),
    [rawOptionsGex],
  )
  const whaleSweepItems = useMemo(() => (rawWhaleSweep ? adaptWhaleSweep(rawWhaleSweep) : []), [rawWhaleSweep])
  const { trades: history, stats } = rawHistory ? adaptHistory(rawHistory) : fallbackHistory

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

    if (signals.length === 0) {
      setSelectedSymbol(null)
      return
    }
    const stillPresent = signals.some((s) => s.symbol === selectedSymbol)
    if (!stillPresent) {
      const firstOpen = signals.find((s) => s.status === "OPEN")
      setSelectedSymbol((firstOpen ?? signals[0]).symbol)
    }
  }, [signals, usStockData, isUSStockMode, selectedSymbol])

  const selected = signals.find((s) => s.symbol === selectedSymbol) ?? null
  const selectedUSStock = usStockData.stocks.find((s) => s.symbol === selectedSymbol) ?? null

  const activeError = isMemeMode
    ? memesError
    : isUSStockMode
      ? usStocksError
      : isNewsAgentMode
        ? newsError
        : isOptionsMode
          ? optionsGexError
          : signalsError
  const activeLoading = isMemeMode
    ? memesLoading
    : isUSStockMode
      ? usStocksLoading
      : isNewsAgentMode
        ? newsLoading
        : isOptionsMode
          ? optionsGexLoading
          : signalsLoading
  const isConnected = isMemeMode
    ? !memesError && !!rawMemes
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
        <div
          className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs ${
            activeError ? "border-short/40 bg-short/10 text-short" : "border-border/60 bg-card text-muted-foreground"
          }`}
        >
          <Activity className={`size-3.5 ${isConnected ? "text-long" : ""}`} aria-hidden="true" />
          {statusLabel}
        </div>
      </header>

      <div className="flex w-fit gap-1 rounded-full border border-border/60 bg-card p-1">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setMode(tab.key)}
            className={`rounded-full px-4 py-1.5 text-sm font-semibold transition-colors ${
              mode === tab.key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeError && (
        <div className="rounded-xl border border-short/30 bg-short/[0.06] px-4 py-3 text-sm text-short">
          無法連線到後端 API：{activeError.message}。請確認 FastAPI 服務是否已在本機啟動（
          <code className="font-mono">uvicorn main:app --reload --port 8000</code>）。
        </div>
      )}

      {isMemeMode ? (
        <>
          <MemeRadar alerts={memeAlerts} watchlist={memeWatchlist} isLoading={memesLoading} error={undefined} />
          <SqueezeFeed items={squeezeFeedItems} isLoading={squeezeFeedLoading} />
          <p className="text-center text-xs text-muted-foreground">
            迷因幣雷達為獨立功能：從迷因幣候選池依 24h 成交量動態排名監控前 10 大，純粹偵測現貨的成交量異常放大
            （同時標示是拉盤還是砸盤），不是交易訊號，沒有方向、槓桿或 TP/SL。⚡ 爆破狀態燈號（Squeeze
            Mode）是額外疊加的實驗性判斷，未經回測驗證。
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
            ，標的為 BingX 代幣化美股商品（TSLA/NVDA/MSTR/SOXL/TQQQ），僅在美東交易時段運作。
          </p>
        </>
      ) : isNewsAgentMode ? (
        <>
          <NewsRadar items={newsItems} isLoading={newsLoading} error={undefined} />
          <p className="text-center text-xs text-muted-foreground">
            AI 智能輿情雷達為獨立功能：背景每 10 分鐘掃描 CoinDesk / CoinTelegraph / Yahoo Finance / CNBC
            等公開新聞來源，交給 AI 判斷相關標的與情緒分數（-10~+10），純粹是資訊監控，
            <strong className="text-foreground">不是交易訊號</strong>，沒有方向、槓桿或 TP/SL。
          </p>
        </>
      ) : isOptionsMode ? (
        <>
          <OptionsAnalyticsPanel
            underlyings={optionsGexData.underlyings}
            whaleSweepItems={whaleSweepItems}
            dataSourceOk={optionsGexData.dataSourceOk}
            isLoading={optionsGexLoading}
            whaleSweepLoading={whaleSweepLoading}
          />
          <p className="text-center text-xs text-muted-foreground">
            期權分析為獨立功能：串接 yfinance 期權鏈，自行用 Black-Scholes 模型計算 Gamma
            曝險（GEX）分佈與擠壓臨界點，<strong className="text-foreground">純粹是造市商部位結構的參考資訊，不是交易訊號</strong>
            ，沒有方向、槓桿或 TP/SL。首批監控標的：NVDA / TSLA / SPY / SMCI / SPCX，僅在美股交易時段更新。期權大單即時流
            目前資料源無法提供逐筆成交數據，暫不支援。
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
        </>
      )}

      <footer className="mt-2 flex items-start gap-2 rounded-xl border border-border/60 bg-card/60 p-4 text-xs leading-relaxed text-muted-foreground">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
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
