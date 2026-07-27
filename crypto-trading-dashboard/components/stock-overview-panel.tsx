"use client"

import { useEffect, useMemo, useState } from "react"
import useSWR from "swr"
import { Landmark, Target } from "lucide-react"
import { cn } from "@/lib/utils"
import { calculateMarketTrend } from "@/lib/confluence"
import { ConfluenceBadge } from "@/components/confluence-badge"
import { GexWallChart } from "@/components/gex-wall-chart"
import { OptionStrategyCard } from "@/components/option-strategy-card"
import { RSI2TechnicalChart } from "@/components/rsi2-technical-chart"
import { UsStockCandlesChart } from "@/components/us-stock-candles-chart"
import {
  adaptOptionsGexList,
  adaptRSI2Chart,
  adaptRSI2List,
  adaptResearchBundles,
  adaptUSStockList,
  adaptWhaleSweep,
  formatPrice,
  type BackendOptionsGexListResponse,
  type BackendRSI2ChartResponse,
  type BackendRSI2ListResponse,
  type BackendResearchBundlesResponse,
  type BackendUSStockListResponse,
  type BackendWhaleSweepResponse,
} from "@/lib/signals"

const fetcher = (url: string) =>
  fetch(url).then(async (r) => {
    const body = await r.json()
    if (!r.ok) throw new Error(body?.detail ?? `Request failed (${r.status})`)
    return body
  })

// 🔭 個股總覽：不是新的資料源，是把GEX/美股ORB/高勝率策略(RSI2)/機構研究/期權
// 策略這幾個本來分散在四個獨立分頁的既有資料，依「使用者選的這一檔標的」重新
// 組裝在同一頁——2026-07-27新增，直接回應「想要一個能快速讀懂市場的頁面」
// 這個需求。刻意不把RSI2（均值回歸，賭超賣反彈）跟confluence engine（GEX+ORB+
// 大單流，判斷趨勢延續）的方向判斷混在同一個分數裡：兩者是哲學上不同的策略
// （均值回歸 vs 順勢），硬湊成一個綜合分數會讓判斷失真，所以RSI2狀態改成
// 獨立區塊呈現，不餵進 calculateMarketTrend()。
export function StockOverviewPanel() {
  const [selected, setSelected] = useState<string | null>(null)

  const { data: rawGex } = useSWR<BackendOptionsGexListResponse>("/api/options/gex", fetcher, { refreshInterval: 30000 })
  const { data: rawWhaleSweep } = useSWR<BackendWhaleSweepResponse>("/api/options/whale-sweep", fetcher, { refreshInterval: 15000 })
  const { data: rawUsStock } = useSWR<BackendUSStockListResponse>("/api/us-stock-orb", fetcher, { refreshInterval: 15000 })
  const { data: rawRsi2 } = useSWR<BackendRSI2ListResponse>("/api/rsi2-meanrev", fetcher, { refreshInterval: 20000 })
  const { data: rawResearch } = useSWR<BackendResearchBundlesResponse>("/api/us/research-bundles", fetcher, { refreshInterval: 60000 })

  const gexList = useMemo(() => (rawGex ? adaptOptionsGexList(rawGex).underlyings : []), [rawGex])
  const whaleSweepItems = useMemo(() => (rawWhaleSweep ? adaptWhaleSweep(rawWhaleSweep) : []), [rawWhaleSweep])
  const usStockData = useMemo(
    () => (rawUsStock ? adaptUSStockList(rawUsStock) : { marketSession: "CLOSED" as const, marketRegime: "Neutral" as const, stocks: [] }),
    [rawUsStock],
  )
  const rsi2Data = useMemo(() => (rawRsi2 ? adaptRSI2List(rawRsi2) : null), [rawRsi2])
  const researchList = useMemo(() => (rawResearch ? adaptResearchBundles(rawResearch) : []), [rawResearch])

  // 這一頁的標的清單 = 四個既有資料源各自關注清單的聯集，不是另外維護一份——
  // 選單裡看到的就是「目前系統至少對這檔標的知道一些什麼」的真實情況。
  const allSymbols = useMemo(() => {
    const set = new Set<string>()
    gexList.forEach((g) => set.add(g.symbol))
    usStockData.stocks.forEach((s) => set.add(s.symbol))
    rsi2Data?.stocks.forEach((s) => set.add(s.symbol))
    researchList.forEach((r) => set.add(r.symbol))
    return Array.from(set).sort()
  }, [gexList, usStockData, rsi2Data, researchList])

  useEffect(() => {
    if (allSymbols.length === 0) return
    if (!selected || !allSymbols.includes(selected)) setSelected(allSymbols[0])
  }, [allSymbols, selected])

  const gex = gexList.find((g) => g.symbol === selected) ?? null
  const orb = usStockData.stocks.find((s) => s.symbol === selected) ?? null
  const rsi2 = rsi2Data?.stocks.find((s) => s.symbol === selected) ?? null
  const research = researchList.find((r) => r.symbol === selected && r.hasData) ?? null
  const relevantSweeps = useMemo(
    () => whaleSweepItems.filter((item) => item.symbol === selected),
    [whaleSweepItems, selected],
  )

  const confluence = selected
    ? calculateMarketTrend({
        symbol: selected,
        currentPrice: orb?.currentPrice ?? gex?.spotPrice ?? null,
        orb: orb?.orbMonitoring ?? null,
        gex,
        recentSweeps: relevantSweeps,
      })
    : null

  const { data: rawRsi2Chart } = useSWR<BackendRSI2ChartResponse>(
    rsi2 ? `/api/rsi2-meanrev/chart?symbol=${selected}` : null,
    fetcher,
    { refreshInterval: 60000 },
  )
  const rsi2ChartPoints = rawRsi2Chart ? adaptRSI2Chart(rawRsi2Chart) : []

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-1.5 rounded-2xl border border-border/60 bg-card p-4">
        {allSymbols.length === 0 && <span className="text-sm text-muted-foreground">載入關注標的中…</span>}
        {allSymbols.map((sym) => (
          <button
            key={sym}
            type="button"
            onClick={() => setSelected(sym)}
            className={cn(
              "rounded-md px-3 py-1.5 font-mono text-sm transition-colors",
              sym === selected ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground hover:text-foreground",
            )}
          >
            {sym}
          </button>
        ))}
      </div>

      {selected && confluence && (
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-border/60 bg-card p-5">
          <span className="font-mono text-xl font-bold">{selected}</span>
          {(orb?.currentPrice ?? gex?.spotPrice) !== null && (orb?.currentPrice ?? gex?.spotPrice) !== undefined && (
            <span className="font-mono text-lg text-foreground">${formatPrice((orb?.currentPrice ?? gex?.spotPrice) as number)}</span>
          )}
          <ConfluenceBadge result={confluence} />
          <span className="text-xs text-muted-foreground">{confluence.actionAdvice}</span>
        </div>
      )}

      {selected && <UsStockCandlesChart symbol={selected} />}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {orb && (
          <div className="flex flex-col gap-3 rounded-2xl border border-border/60 bg-card p-5">
            <div className="flex items-center gap-2">
              <Target className="size-4 text-primary" aria-hidden="true" />
              <span className="font-mono text-sm font-semibold">美股 ORB 當沖狀態</span>
            </div>
            {orb.status === "OPEN" && orb.signal ? (
              <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                <StatTile label="方向" value={orb.signal.side} tone={orb.signal.side === "Long" ? "long" : "short"} />
                <StatTile label="進場價" value={`$${formatPrice(orb.signal.entry_price)}`} />
                <StatTile label="停利" value={`$${formatPrice(orb.signal.tp)}`} tone="long" />
                <StatTile label="停損" value={`$${formatPrice(orb.signal.sl)}`} tone="short" />
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">目前無持倉訊號</p>
            )}
            <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
              <StatTile label="開盤區間高" value={orb.orbMonitoring.openingHigh !== null ? `$${formatPrice(orb.orbMonitoring.openingHigh)}` : "—"} />
              <StatTile label="開盤區間低" value={orb.orbMonitoring.openingLow !== null ? `$${formatPrice(orb.orbMonitoring.openingLow)}` : "—"} />
              <StatTile label="RVOL" value={orb.orbMonitoring.rvol !== null ? `${orb.orbMonitoring.rvol.toFixed(1)}x` : "—"} />
              <StatTile label="大盤濾網" value={orb.orbMonitoring.marketRegime} />
            </div>
          </div>
        )}

        {rsi2 && (
          <div className="flex flex-col gap-3 rounded-2xl border border-border/60 bg-card p-5">
            <div className="flex items-center gap-2">
              <Target className="size-4 text-primary" aria-hidden="true" />
              <span className="font-mono text-sm font-semibold">高勝率策略（RSI2均值回歸）</span>
              <span className="rounded-md bg-secondary px-2 py-0.5 text-[10px] text-muted-foreground">
                跟上方共振判斷是不同哲學（賭超賣反彈，非順勢），故不合併計分
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
              <StatTile label="RSI(2)" value={rsi2.rsi2 !== null ? rsi2.rsi2.toFixed(1) : "—"} tone={rsi2.rsi2 !== null && rsi2.rsi2 < 10 ? "long" : undefined} />
              <StatTile label="狀態" value={rsi2.status === "OPEN" ? "持倉中" : "無訊號"} tone={rsi2.status === "OPEN" ? "long" : undefined} />
              <StatTile label="SMA200" value={rsi2.sma200 !== null ? `$${formatPrice(rsi2.sma200)}` : "—"} />
              <StatTile label="SMA5" value={rsi2.sma5 !== null ? `$${formatPrice(rsi2.sma5)}` : "—"} />
            </div>
            <RSI2TechnicalChart points={rsi2ChartPoints} entryPrice={rsi2.entryPrice} stopLoss={rsi2.stopLoss} />
          </div>
        )}
      </div>

      {gex && gex.hasData && <GexWallChart data={gex} />}

      {gex && gex.hasData && <OptionStrategyCard gex={gex} recentSweeps={relevantSweeps} />}

      {research && (
        <div className="flex flex-col gap-3 rounded-2xl border border-border/60 bg-card p-5">
          <div className="flex items-center gap-2">
            <Landmark className="size-4 text-primary" aria-hidden="true" />
            <span className="font-mono text-sm font-semibold">機構研究共識</span>
            {research.consensusRatingLabel && (
              <span className="rounded-md bg-primary/15 px-2 py-0.5 text-[11px] font-semibold text-primary">
                {research.consensusRatingLabel}
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
            <StatTile label="最高目標價" value={research.consensusHigh !== null ? `$${research.consensusHigh.toFixed(0)}` : "—"} />
            <StatTile label="共識平均目標價" value={research.consensusAverage !== null ? `$${research.consensusAverage.toFixed(0)}` : "—"} tone="primary" />
            <StatTile label="最低目標價" value={research.consensusLow !== null ? `$${research.consensusLow.toFixed(0)}` : "—"} />
            <StatTile label="分析師人數" value={research.consensusTotal !== null ? `${research.consensusTotal} 位` : "—"} />
          </div>
          <p className="text-[11px] text-muted-foreground">完整機構評級明細與晨星研報請至「機構研究」分頁查看。</p>
        </div>
      )}

      {selected && !orb && !gex && !rsi2 && !research && (
        <p className="rounded-xl border border-dashed border-border/60 px-4 py-6 text-center text-sm text-muted-foreground">
          {selected} 目前沒有任何模塊的資料。
        </p>
      )}
    </div>
  )
}

function StatTile({ label, value, tone }: { label: string; value: string; tone?: "long" | "short" | "primary" }) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-border/60 bg-secondary/30 px-3 py-2">
      <span className="text-[10px] text-muted-foreground">{label}</span>
      <span
        className={cn(
          "font-mono text-sm font-semibold",
          tone === "long" ? "text-long" : tone === "short" ? "text-short" : tone === "primary" ? "text-primary" : "text-foreground",
        )}
      >
        {value}
      </span>
    </div>
  )
}
