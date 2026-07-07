import { ArrowDownRight, ArrowUpRight, Radar } from "lucide-react"
import { cn } from "@/lib/utils"
import { type SignalState, formatPrice, formatTime } from "@/lib/signals"

function shortSymbol(symbol: string): string {
  return symbol.replace(":USDT", "")
}

interface OpportunityListProps {
  signals: SignalState[]
  trackedSymbols: string[]
  selectedSymbol: string | null
  onSelect: (symbol: string) => void
  isLoading: boolean
}

// "Market Scan" tab: the backend only ever sends symbols that currently have
// a triggered signal here (see /api/signals?universe=scan), so every row is
// an actual opportunity — no No-Signal rows to filter out client-side.
export function OpportunityList({ signals, trackedSymbols, selectedSymbol, onSelect, isLoading }: OpportunityListProps) {
  // Proves the scanner is actually watching real coins even when nothing has
  // triggered — without this the "no opportunities" empty state is
  // indistinguishable from the feature being broken.
  const trackedSummary =
    trackedSymbols.length > 0 ? (
      <p className="px-1 text-xs text-muted-foreground">
        目前追蹤 {trackedSymbols.length} 檔幣：{trackedSymbols.slice(0, 6).map(shortSymbol).join(", ")}
        {trackedSymbols.length > 6 ? ` 等 +${trackedSymbols.length - 6} 檔` : ""}
      </p>
    ) : null

  if (signals.length === 0) {
    return (
      <div className="flex flex-col gap-2">
        <div className="flex min-h-[96px] flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-border/60 bg-card/40 p-6 text-center text-sm text-muted-foreground">
          <Radar className="size-5" aria-hidden="true" />
          {isLoading ? "掃描全市場中…" : "目前市場掃描沒有偵測到任何機會，引擎持續掃描全市場中。"}
        </div>
        {trackedSummary}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {trackedSummary}
      {signals.map((s) => {
        if (!s.signal) return null
        const isLong = s.signal.side === "Long"
        const isSelected = s.symbol === selectedSymbol
        const priceDelta = s.signal.current_price - s.signal.entry_price
        const priceDeltaPct = (priceDelta / s.signal.entry_price) * 100
        const roi = (isLong ? priceDeltaPct : -priceDeltaPct) * s.signal.leverage

        return (
          <button
            key={s.symbol}
            type="button"
            onClick={() => onSelect(s.symbol)}
            className={cn(
              "flex items-center justify-between gap-3 rounded-xl border px-4 py-3 text-left transition-colors",
              isSelected ? "border-primary/60 bg-primary/[0.08]" : "border-border/60 bg-card hover:bg-secondary/40",
            )}
          >
            <div className="flex items-center gap-3">
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold uppercase",
                  isLong ? "bg-long text-long-foreground" : "bg-short text-short-foreground",
                )}
              >
                {isLong ? (
                  <ArrowUpRight className="size-3.5" aria-hidden="true" />
                ) : (
                  <ArrowDownRight className="size-3.5" aria-hidden="true" />
                )}
                {s.signal.side}
              </span>
              <div className="flex flex-col">
                <span className="font-mono text-sm font-semibold">{shortSymbol(s.symbol)}</span>
                <span className="text-xs text-muted-foreground">
                  {s.signal.leverage}x · Issued {formatTime(s.signal.timestamp)}
                </span>
              </div>
            </div>
            <div className="flex flex-col items-end gap-0.5">
              <span className="font-mono text-sm font-semibold">${formatPrice(s.signal.current_price)}</span>
              <span className={cn("font-mono text-xs font-semibold", roi >= 0 ? "text-long" : "text-short")}>
                {roi >= 0 ? "+" : ""}
                {roi.toFixed(2)}% ROI
              </span>
            </div>
          </button>
        )
      })}
    </div>
  )
}
