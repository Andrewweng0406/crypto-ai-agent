import { cn } from "@/lib/utils"
import { type USStockSignalState, formatPrice } from "@/lib/signals"

interface USStockWatchlistProps {
  stocks: USStockSignalState[]
  selectedSymbol: string | null
  onSelect: (symbol: string) => void
}

// 固定監控名單（跟主流幣的 SymbolWatchlist 同樣精神）：永遠顯示全部 5 檔，
// 不管有沒有觸發訊號，讀起來是監控板而不是機會清單。
export function USStockWatchlist({ stocks, selectedSymbol, onSelect }: USStockWatchlistProps) {
  return (
    <div className="flex flex-wrap gap-3">
      {stocks.map((s) => {
        const isSelected = s.symbol === selectedSymbol
        const isOpen = s.status === "OPEN" && s.signal
        const change = s.orbMonitoring.dayChangePct

        return (
          <button
            key={s.symbol}
            type="button"
            onClick={() => onSelect(s.symbol)}
            className={cn(
              "flex min-w-[180px] flex-1 flex-col gap-1.5 rounded-xl border px-4 py-3 text-left transition-colors",
              isSelected ? "border-primary/60 bg-primary/[0.08]" : "border-border/60 bg-card hover:bg-secondary/40",
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-sm font-semibold">{s.displayName}</span>
              {isOpen ? (
                <span
                  className={cn(
                    "rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase",
                    s.signal!.side === "Long" ? "bg-long/15 text-long" : "bg-short/15 text-short",
                  )}
                >
                  {s.signal!.side} {s.signal!.leverage}x
                </span>
              ) : (
                <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px] font-semibold uppercase text-muted-foreground">
                  No Signal
                </span>
              )}
            </div>
            <div className="flex items-baseline justify-between gap-2">
              <span className="font-mono text-lg font-bold">
                {s.currentPrice !== null ? `$${formatPrice(s.currentPrice)}` : "—"}
              </span>
              {change !== null && (
                <span className={cn("font-mono text-xs font-semibold", change >= 0 ? "text-long" : "text-short")}>
                  {change >= 0 ? "+" : ""}
                  {change.toFixed(2)}%
                </span>
              )}
            </div>
          </button>
        )
      })}
    </div>
  )
}
