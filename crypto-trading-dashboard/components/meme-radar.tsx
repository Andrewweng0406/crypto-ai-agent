import { Flame, Radar } from "lucide-react"
import { cn } from "@/lib/utils"
import { type MemeAlert, type MemeWatchItem, formatPrice, formatTime } from "@/lib/signals"

const SPIKE_THRESHOLD = 3.0

function shortSymbol(symbol: string): string {
  return symbol.replace("/USDT", "")
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
  if (error) {
    return (
      <div className="rounded-2xl border border-short/30 bg-short/[0.06] p-6 text-center text-sm text-short">
        無法載入迷因幣雷達：{error}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-3">
        {watchlist.map((item) => {
          const isSpiking = item.volumeMultiple !== null && item.volumeMultiple >= SPIKE_THRESHOLD
          return (
            <div
              key={item.symbol}
              className={cn(
                "flex min-w-[180px] flex-1 flex-col gap-1.5 rounded-xl border px-4 py-3",
                isSpiking ? "border-short/60 bg-short/[0.08]" : "border-border/60 bg-card",
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
            </div>
          )
        })}
      </div>

      {alerts.length === 0 ? (
        <div className="flex min-h-[120px] flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-border/60 bg-card/40 p-8 text-center text-sm text-muted-foreground">
          <Radar className="size-6" aria-hidden="true" />
          {isLoading ? "雷達啟動中…" : "目前沒有偵測到爆量的迷因幣，雷達持續監控中。"}
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {alerts.map((alert, i) => (
            <div
              key={`${alert.symbol}-${alert.triggeredAt}-${i}`}
              className="flex items-center justify-between gap-3 rounded-xl border border-border/60 bg-card px-4 py-3.5"
            >
              <div className="flex items-center gap-3">
                <span className="inline-flex items-center gap-1 rounded-full bg-short/15 px-2.5 py-1 text-xs font-semibold uppercase text-short">
                  <Flame className="size-3.5" aria-hidden="true" />
                  爆量
                </span>
                <div className="flex flex-col">
                  <span className="font-mono text-sm font-semibold">{shortSymbol(alert.symbol)}</span>
                  <span className="text-xs text-muted-foreground">{formatTime(alert.triggeredAt)}</span>
                </div>
              </div>
              <div className="flex flex-col items-end gap-0.5">
                <span className="font-mono text-sm font-semibold text-short">{alert.volumeMultiple.toFixed(1)}x 均量</span>
                <span className="font-mono text-xs text-muted-foreground">${formatPrice(alert.price)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
