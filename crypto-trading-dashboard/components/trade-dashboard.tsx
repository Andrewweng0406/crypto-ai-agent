"use client"

import { useEffect, useMemo, useState } from "react"
import useSWR from "swr"
import { Activity, AlertTriangle, Radar, Zap } from "lucide-react"
import {
  adaptHistory,
  adaptMemeAlerts,
  adaptMemeWatchlist,
  adaptSignalList,
  fallbackHistory,
  formatPrice,
  formatTime,
  type BackendHistoryResponse,
  type BackendMemeRadarResponse,
  type BackendSignalListResponse,
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

const fetcher = (url: string) =>
  fetch(url).then(async (r) => {
    const body = await r.json()
    if (!r.ok) throw new Error(body?.detail ?? `Request failed (${r.status})`)
    return body
  })

// Meme radar is a separate feature (pure volume-spike alerts, no trading
// signal shape), so the tab key extends beyond the /api/signals `Universe`.
type TabKey = Universe | "meme"

const TABS: { key: TabKey; label: string }[] = [
  { key: "major", label: "主流幣" },
  { key: "scan", label: "市場掃描" },
  { key: "meme", label: "迷因雷達" },
]

export function TradeDashboard() {
  const [mode, setMode] = useState<TabKey>("major")
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)

  const isMemeMode = mode === "meme"

  const {
    data: rawSignals,
    error: signalsError,
    isLoading: signalsLoading,
  } = useSWR<BackendSignalListResponse>(isMemeMode ? null : `/api/signals?universe=${mode}`, fetcher, {
    refreshInterval: mode === "major" ? 5000 : 12000,
  })

  const {
    data: rawMemes,
    error: memesError,
    isLoading: memesLoading,
  } = useSWR<BackendMemeRadarResponse>(isMemeMode ? "/api/memes" : null, fetcher, {
    refreshInterval: 15000,
  })

  const { data: rawHistory, error: historyError } = useSWR<BackendHistoryResponse>("/api/history", fetcher, {
    refreshInterval: 15000,
  })

  const signals = useMemo(() => (rawSignals ? adaptSignalList(rawSignals) : []), [rawSignals])
  const memeAlerts = useMemo(() => (rawMemes ? adaptMemeAlerts(rawMemes) : []), [rawMemes])
  const memeWatchlist = useMemo(() => (rawMemes ? adaptMemeWatchlist(rawMemes) : []), [rawMemes])
  const { trades: history, stats } = rawHistory ? adaptHistory(rawHistory) : fallbackHistory

  // Keep the selection sane across tab switches and data refreshes: default
  // to the first open opportunity, and re-pick if the current selection
  // disappears (its signal closed, or it dropped out of the scan ranking).
  useEffect(() => {
    if (signals.length === 0) {
      setSelectedSymbol(null)
      return
    }
    const stillPresent = signals.some((s) => s.symbol === selectedSymbol)
    if (!stillPresent) {
      const firstOpen = signals.find((s) => s.status === "OPEN")
      setSelectedSymbol((firstOpen ?? signals[0]).symbol)
    }
  }, [signals, selectedSymbol])

  const selected = signals.find((s) => s.symbol === selectedSymbol) ?? null

  const activeError = isMemeMode ? memesError : signalsError
  const activeLoading = isMemeMode ? memesLoading : signalsLoading
  const isConnected = isMemeMode ? !memesError && !!rawMemes : !signalsError && !!rawSignals
  const statusLabel = activeError ? "Backend offline" : activeLoading ? "Syncing…" : "Connected"

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-5 px-4 py-6 md:px-8 md:py-10">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Zap className="size-5" aria-hidden="true" />
          </span>
          <div className="flex flex-col leading-none">
            <span className="font-mono text-lg font-bold tracking-tight">Cipher</span>
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
          <p className="text-center text-xs text-muted-foreground">
            迷因幣雷達為獨立功能：純粹偵測 PEPE / WIF / DOGE 現貨的成交量異常放大，不是交易訊號，沒有方向、槓桿或
            TP/SL。
          </p>
        </>
      ) : (
        <>
          {mode === "major" ? (
            <SymbolWatchlist signals={signals} selectedSymbol={selectedSymbol} onSelect={setSelectedSymbol} />
          ) : (
            <OpportunityList
              signals={signals}
              trackedSymbols={rawSignals?.tracked_symbols ?? []}
              selectedSymbol={selectedSymbol}
              onSelect={setSelectedSymbol}
              isLoading={signalsLoading}
            />
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
          <p className="text-xs text-muted-foreground">Last checked {formatTime(updatedAt)} · Cipher AI Engine</p>
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
