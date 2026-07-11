"use client"

import { useEffect, useState } from "react"
import useSWR from "swr"
import { AlertTriangle, Target } from "lucide-react"
import { cn } from "@/lib/utils"
import {
  adaptRSI2Chart,
  adaptRSI2History,
  adaptRSI2List,
  type BackendRSI2ChartResponse,
  type BackendRSI2HistoryResponse,
  type BackendRSI2ListResponse,
  type RSI2StockState,
} from "@/lib/signals"
import { RSI2TechnicalChart } from "@/components/rsi2-technical-chart"

const fetcher = (url: string) =>
  fetch(url).then(async (r) => {
    const body = await r.json()
    if (!r.ok) throw new Error(body?.detail ?? `Request failed (${r.status})`)
    return body
  })

// 🎯 高勝率股票策略：RSI(2)均值回歸實盤監控——2026-07-11從回測沙盒驗證過的
// stock_rsi2_meanrev 策略移植成正式實盤監控頁面。這是「監控+通知」，不是自動
// 下單；單次回測/滾動式Walk-Forward驗證維持在「🚀 回測沙盒」那邊，不重複。
export function HighWinRatePanel() {
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)

  const { data: rawList, isLoading: listLoading } = useSWR<BackendRSI2ListResponse>(
    "/api/rsi2-meanrev",
    fetcher,
    { refreshInterval: 20000 },
  )
  const { data: rawHistory } = useSWR<BackendRSI2HistoryResponse>("/api/rsi2-meanrev/history", fetcher, {
    refreshInterval: 30000,
  })

  const listData = rawList ? adaptRSI2List(rawList) : null
  const historyData = rawHistory ? adaptRSI2History(rawHistory) : null

  useEffect(() => {
    if (!listData || listData.stocks.length === 0) return
    const stillPresent = listData.stocks.some((s) => s.symbol === selectedSymbol)
    if (!stillPresent) {
      const firstOpen = listData.stocks.find((s) => s.status === "OPEN")
      setSelectedSymbol((firstOpen ?? listData.stocks[0]).symbol)
    }
  }, [listData, selectedSymbol])

  const { data: rawChart, isLoading: chartLoading } = useSWR<BackendRSI2ChartResponse>(
    selectedSymbol ? `/api/rsi2-meanrev/chart?symbol=${selectedSymbol}` : null,
    fetcher,
    { refreshInterval: 60000 },
  )
  const chartPoints = rawChart ? adaptRSI2Chart(rawChart) : []

  const selected = listData?.stocks.find((s) => s.symbol === selectedSymbol) ?? null

  return (
    <div className="flex flex-col gap-5 rounded-2xl border border-border/60 bg-card p-5">
      <div className="flex flex-wrap items-center gap-2.5">
        <Target className="size-5 text-primary" aria-hidden="true" />
        <h2 className="font-mono text-base font-semibold">🎯 高勝率策略：RSI(2) 均值回歸 實盤監控</h2>
        <span className="rounded-md bg-secondary px-2 py-0.5 font-mono text-[11px] text-muted-foreground">僅美股</span>
        {listData && (
          <span
            className={cn(
              "flex items-center gap-1.5 rounded-md px-2 py-0.5 font-mono text-[11px]",
              listData.marketSession === "OPEN" ? "bg-long/15 text-long" : "bg-secondary text-muted-foreground",
            )}
          >
            <span className={cn("size-1.5 rounded-full", listData.marketSession === "OPEN" ? "bg-long animate-pulse" : "bg-muted-foreground")} />
            {listData.marketSession === "OPEN" ? "盤中監控" : "休市中"}
          </span>
        )}
      </div>

      {listData && (
        <div className="flex items-start gap-1.5 rounded-lg border border-amber-400/30 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-200">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          {listData.caveat}
        </div>
      )}

      {/* 標的監控卡片 */}
      <div className="flex flex-wrap gap-3">
        {listLoading && !listData && (
          <div className="flex h-20 flex-1 items-center justify-center rounded-xl border border-dashed border-border/60 text-sm text-muted-foreground">
            載入監控名單中…
          </div>
        )}
        {listData?.stocks.map((s) => (
          <StockTile key={s.symbol} stock={s} isSelected={s.symbol === selectedSymbol} onSelect={() => setSelectedSymbol(s.symbol)} />
        ))}
      </div>

      {/* 選中標的詳情：技術面圖表 */}
      {selected && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <DetailTile label="現價" value={selected.currentPrice !== null ? `$${selected.currentPrice.toFixed(2)}` : "—"} />
            <DetailTile
              label="SMA200 濾網"
              value={selected.sma200 !== null ? `$${selected.sma200.toFixed(2)}` : "—"}
              tone={
                selected.currentPrice !== null && selected.sma200 !== null
                  ? selected.currentPrice > selected.sma200
                    ? "long"
                    : "short"
                  : "neutral"
              }
            />
            <DetailTile
              label={`RSI(2)${selected.rsi2IsConfirmed ? "（已確認）" : "（盤中估算）"}`}
              value={selected.rsi2 !== null ? selected.rsi2.toFixed(1) : "—"}
              tone={selected.rsi2 !== null && selected.rsi2 < 10 ? "long" : "neutral"}
            />
            <DetailTile
              label="訊號狀態"
              value={selected.status === "OPEN" ? "🎯 持倉中" : "無訊號"}
              tone={selected.status === "OPEN" ? "long" : "neutral"}
            />
          </div>

          {selected.status === "OPEN" && (
            <div className="flex flex-wrap gap-4 rounded-xl border border-long/30 bg-long/[0.06] px-4 py-3 text-xs">
              <span>
                進場：<span className="font-mono font-semibold text-long">${selected.entryPrice?.toFixed(2)}</span>
              </span>
              <span>
                停損：<span className="font-mono font-semibold text-short">${selected.stopLoss?.toFixed(2)}</span>
              </span>
              <span className="text-muted-foreground">止盈：收盤收復SMA5（動態，見下方圖表藍線）</span>
              {selected.openedAt && (
                <span className="text-muted-foreground">進場時間：{new Date(selected.openedAt).toLocaleString("zh-TW")}</span>
              )}
            </div>
          )}

          {chartLoading && chartPoints.length === 0 ? (
            <div className="flex h-64 items-center justify-center rounded-xl border border-dashed border-border/60 bg-card/40 text-sm text-muted-foreground">
              載入技術面圖表中…
            </div>
          ) : (
            <RSI2TechnicalChart points={chartPoints} entryPrice={selected.entryPrice} stopLoss={selected.stopLoss} />
          )}
        </>
      )}

      {/* 實盤成交紀錄 */}
      {historyData && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">實盤成交紀錄（RSI2均值回歸）</h3>
            <span className="text-xs text-muted-foreground">
              {historyData.stats.totalTrades} 筆 · 勝率 {historyData.stats.winRatePct.toFixed(1)}%
            </span>
          </div>
          {historyData.trades.length === 0 ? (
            <p className="rounded-xl border border-dashed border-border/60 bg-card/40 px-4 py-6 text-center text-xs text-muted-foreground">
              尚無已結算的實盤成交。
            </p>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-border/60">
              <table className="w-full min-w-[560px] font-mono text-xs">
                <thead>
                  <tr className="border-b border-border/60 bg-secondary/30 text-left text-muted-foreground">
                    <th className="px-3 py-2 font-medium">標的</th>
                    <th className="px-3 py-2 font-medium">結果</th>
                    <th className="px-3 py-2 text-right font-medium">進場</th>
                    <th className="px-3 py-2 text-right font-medium">出場</th>
                    <th className="px-3 py-2 text-right font-medium">損益</th>
                    <th className="px-3 py-2 font-medium">出場原因</th>
                  </tr>
                </thead>
                <tbody>
                  {historyData.trades.map((t, i) => (
                    <tr key={`${t.symbol}-${t.closedAt}-${i}`} className="border-b border-border/40 last:border-0">
                      <td className="px-3 py-2 font-semibold">{t.displayName}</td>
                      <td className={cn("px-3 py-2", t.result === "WIN" ? "text-long" : "text-short")}>{t.result}</td>
                      <td className="px-3 py-2 text-right text-muted-foreground">${t.entryPrice.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right text-muted-foreground">${t.exitPrice.toFixed(2)}</td>
                      <td className={cn("px-3 py-2 text-right font-semibold", t.pnlPct >= 0 ? "text-long" : "text-short")}>
                        {t.pnlPct >= 0 ? "+" : ""}
                        {t.pnlPct.toFixed(2)}%
                      </td>
                      <td className="px-3 py-2 text-muted-foreground">{t.exitReason === "SL" ? "停損" : "止盈(SMA5)"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function StockTile({ stock, isSelected, onSelect }: { stock: RSI2StockState; isSelected: boolean; onSelect: () => void }) {
  const isOpen = stock.status === "OPEN"
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex min-w-[160px] flex-1 flex-col gap-1.5 rounded-xl border px-4 py-3 text-left transition-colors",
        isSelected ? "border-primary/60 bg-primary/[0.08]" : "border-border/60 bg-card hover:bg-secondary/40",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-sm font-semibold">{stock.displayName}</span>
        {isOpen ? (
          <span className="rounded bg-long/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-long">Long</span>
        ) : (
          <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px] font-semibold uppercase text-muted-foreground">No Signal</span>
        )}
      </div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-lg font-bold">{stock.currentPrice !== null ? `$${stock.currentPrice.toFixed(2)}` : "—"}</span>
        {stock.dayChangePct !== null && (
          <span className={cn("font-mono text-xs font-semibold", stock.dayChangePct >= 0 ? "text-long" : "text-short")}>
            {stock.dayChangePct >= 0 ? "+" : ""}
            {stock.dayChangePct.toFixed(2)}%
          </span>
        )}
      </div>
      {stock.rsi2 !== null && (
        <span className={cn("text-[11px]", stock.rsi2 < 10 ? "text-long font-semibold" : "text-muted-foreground")}>
          RSI(2) {stock.rsi2.toFixed(1)}
        </span>
      )}
    </button>
  )
}

function DetailTile({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "long" | "short" | "neutral" }) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-border/60 bg-secondary/30 px-4 py-3">
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <span
        className={cn(
          "font-mono text-lg font-bold",
          tone === "long" && "text-long",
          tone === "short" && "text-short",
          tone === "neutral" && "text-foreground",
        )}
      >
        {value}
      </span>
    </div>
  )
}
