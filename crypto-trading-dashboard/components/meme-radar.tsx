"use client"

import { useEffect, useState } from "react"
import { Flame, Radar } from "lucide-react"
import { cn } from "@/lib/utils"
import { type MemeAlert, type MemeWatchItem, formatPrice, formatTime } from "@/lib/signals"
import { MemeResonanceBoard } from "@/components/meme-resonance-board"

const SPIKE_THRESHOLD = 3.0

function shortSymbol(symbol: string): string {
  return symbol.replace("/USDT", "")
}

// 同樣是爆量，拉盤跟砸盤方向完全相反，只看量能倍數看不出來，一定要標方向。
function ChangeBadge({ pct }: { pct: number | null }) {
  if (pct === null) {
    return <span className="font-mono text-xs text-muted-foreground">—</span>
  }
  const isUp = pct >= 0
  return (
    <span className={cn("font-mono text-xs font-semibold", isUp ? "text-long" : "text-short")}>
      {isUp ? "+" : ""}
      {pct.toFixed(1)}%
    </span>
  )
}

interface MemeRadarProps {
  alerts: MemeAlert[]
  watchlist: MemeWatchItem[]
  isLoading: boolean
  error?: string
}

// Pure volume-spike radar — no side/TP/SL/leverage, unlike the trading
// signals elsewhere in this dashboard. The watchlist row always shows all
// three coins' live volume-vs-24h-average ratio (mirrors the major-coin
// monitoring panel), so the tab reads as "actively computing" even when
// nothing has actually spiked; the list below is only real trigger events.
export function MemeRadar({ alerts, watchlist, isLoading, error }: MemeRadarProps) {
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)

  // 跟其他分頁同樣的選取邏輯：預設選第一個，選到的標的從清單消失時（例如輪出了
  // 動態監控名單）就重新挑一個，避免看板停留在一個已經不存在的幣上。
  useEffect(() => {
    if (watchlist.length === 0) {
      setSelectedSymbol(null)
      return
    }
    const stillPresent = watchlist.some((w) => w.symbol === selectedSymbol)
    if (!stillPresent) {
      setSelectedSymbol(watchlist[0].symbol)
    }
  }, [watchlist, selectedSymbol])

  if (error) {
    return (
      <div className="rounded-2xl border border-short/30 bg-short/[0.06] p-6 text-center text-sm text-short">
        無法載入迷因幣雷達：{error}
      </div>
    )
  }

  const selected = watchlist.find((w) => w.symbol === selectedSymbol) ?? null

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-3">
        {watchlist.map((item) => {
          const isSpiking = item.volumeMultiple !== null && item.volumeMultiple >= SPIKE_THRESHOLD
          const isSelected = item.symbol === selectedSymbol
          return (
            <button
              key={item.symbol}
              type="button"
              onClick={() => setSelectedSymbol(item.symbol)}
              className={cn(
                "flex min-w-[180px] flex-1 flex-col gap-1.5 rounded-xl border px-4 py-3 text-left transition-colors",
                isSelected
                  ? "border-primary/60 bg-primary/[0.08]"
                  : isSpiking
                    ? "border-short/60 bg-short/[0.08] hover:bg-short/[0.12]"
                    : "border-border/60 bg-card hover:bg-secondary/40",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-sm font-semibold">{shortSymbol(item.symbol)}</span>
                <span
                  className={cn("font-mono text-xs font-semibold", isSpiking ? "text-short" : "text-muted-foreground")}
                >
                  {item.volumeMultiple !== null ? `${item.volumeMultiple.toFixed(2)}x` : "—"} / {SPIKE_THRESHOLD.toFixed(2)}x
                </span>
              </div>
              <span className="font-mono text-lg font-bold">
                {item.price !== null ? `$${formatPrice(item.price)}` : "—"}
              </span>
              <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                <span className="flex items-center gap-1">
                  1h <ChangeBadge pct={item.change1hPct} />
                </span>
                <span className="flex items-center gap-1">
                  24h <ChangeBadge pct={item.change24hPct} />
                </span>
              </div>
            </button>
          )
        })}
      </div>

      {selected && <MemeResonanceBoard item={selected} />}

      {alerts.length === 0 ? (
        <div className="flex min-h-[120px] flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-border/60 bg-card/40 p-8 text-center text-sm text-muted-foreground">
          <Radar className="size-6" aria-hidden="true" />
          {isLoading ? "雷達啟動中…" : "目前沒有偵測到爆量的迷因幣，雷達持續監控中。"}
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {alerts.map((alert, i) => {
            const isPump = (alert.change1hPct ?? 0) >= 0
            return (
              <div
                key={`${alert.symbol}-${alert.triggeredAt}-${i}`}
                className="flex items-center justify-between gap-3 rounded-xl border border-border/60 bg-card px-4 py-3.5"
              >
                <div className="flex items-center gap-3">
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold uppercase",
                      isPump ? "bg-long/15 text-long" : "bg-short/15 text-short",
                    )}
                  >
                    <Flame className="size-3.5" aria-hidden="true" />
                    {isPump ? "爆量拉盤" : "爆量砸盤"}
                  </span>
                  <div className="flex flex-col">
                    <span className="font-mono text-sm font-semibold">{shortSymbol(alert.symbol)}</span>
                    <span className="text-xs text-muted-foreground">{formatTime(alert.triggeredAt)}</span>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-0.5">
                  <span className={cn("font-mono text-sm font-semibold", isPump ? "text-long" : "text-short")}>
                    {alert.volumeMultiple.toFixed(1)}x 均量
                  </span>
                  <span className="flex items-center gap-1.5 font-mono text-xs text-muted-foreground">
                    ${formatPrice(alert.price)} · <ChangeBadge pct={alert.change1hPct} /> (1h)
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
