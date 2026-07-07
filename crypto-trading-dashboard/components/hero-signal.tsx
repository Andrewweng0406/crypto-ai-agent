import { ArrowUpRight, ArrowDownRight } from "lucide-react"
import { cn } from "@/lib/utils"
import { type Signal, formatPrice, formatTime } from "@/lib/signals"

export function HeroSignal({ signal }: { signal: Signal }) {
  const isLong = signal.side === "Long"
  const priceDelta = signal.current_price - signal.entry_price
  const priceDeltaPct = (priceDelta / signal.entry_price) * 100
  // Unrealized move in the direction of the trade, amplified by leverage.
  const directional = isLong ? priceDeltaPct : -priceDeltaPct
  const roi = directional * signal.leverage
  const inProfit = roi >= 0

  return (
    <section
      aria-label="Active trading signal"
      className={cn(
        "relative overflow-hidden rounded-2xl border p-6 md:p-8",
        isLong
          ? "border-long/30 bg-long/[0.06] shadow-[0_0_60px_-15px] shadow-long/30"
          : "border-short/30 bg-short/[0.06] shadow-[0_0_60px_-15px] shadow-short/30",
      )}
    >
      {/* Glow accent */}
      <div
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute -right-16 -top-16 size-56 rounded-full blur-3xl",
          isLong ? "bg-long/20" : "bg-short/20",
        )}
      />

      <div className="relative flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-semibold uppercase tracking-wide",
                isLong ? "bg-long text-long-foreground" : "bg-short text-short-foreground",
              )}
            >
              {isLong ? (
                <ArrowUpRight className="size-4" aria-hidden="true" />
              ) : (
                <ArrowDownRight className="size-4" aria-hidden="true" />
              )}
              {signal.side}
            </span>
            <span className="flex items-center gap-2 text-sm text-muted-foreground">
              <span className="relative flex size-2">
                <span
                  className={cn(
                    "absolute inline-flex h-full w-full animate-ping rounded-full opacity-75",
                    isLong ? "bg-long" : "bg-short",
                  )}
                />
                <span className={cn("relative inline-flex size-2 rounded-full", isLong ? "bg-long" : "bg-short")} />
              </span>
              Live signal
            </span>
          </div>

          <div>
            <h1 className="font-mono text-5xl font-bold tracking-tight text-balance md:text-6xl">{signal.symbol}</h1>
            <p
              className={cn(
                "mt-2 font-mono text-2xl font-semibold md:text-3xl",
                isLong ? "text-long" : "text-short",
              )}
            >
              {signal.leverage}x Leverage
            </p>
          </div>

          <p className="text-xs text-muted-foreground">Issued {formatTime(signal.timestamp)} · Cipher AI Engine</p>
        </div>

        <div className="flex flex-col gap-1 rounded-xl border border-border/60 bg-card/60 p-5 md:min-w-[220px] md:text-right">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Current Price</span>
          <span className="font-mono text-3xl font-bold md:text-4xl">${formatPrice(signal.current_price)}</span>
          <span
            className={cn(
              "mt-1 font-mono text-sm font-semibold",
              inProfit ? "text-long" : "text-short",
            )}
          >
            {inProfit ? "+" : ""}
            {roi.toFixed(2)}% ROI
            <span className="ml-2 text-muted-foreground">
              ({priceDelta >= 0 ? "+" : ""}
              {formatPrice(priceDelta)})
            </span>
          </span>
        </div>
      </div>
    </section>
  )
}
