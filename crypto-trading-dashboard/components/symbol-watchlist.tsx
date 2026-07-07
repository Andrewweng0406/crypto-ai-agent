import { cn } from "@/lib/utils"
import { type SignalState, formatPrice } from "@/lib/signals"

function shortSymbol(symbol: string): string {
  return symbol.replace(":USDT", "")
}

interface SymbolWatchlistProps {
  signals: SignalState[]
  selectedSymbol: string | null
  onSelect: (symbol: string) => void
}

// Fixed watchlist for the "Major Coins" tab: always shows every tracked
// symbol (even with no active signal), so it reads as a monitoring board
// rather than an opportunity feed.
export function SymbolWatchlist({ signals, selectedSymbol, onSelect }: SymbolWatchlistProps) {
  return (
    <div className="flex flex-wrap gap-3">
      {signals.map((s) => {
        const isSelected = s.symbol === selectedSymbol
        const isOpen = s.status === "OPEN" && s.signal

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
              <span className="font-mono text-sm font-semibold">{shortSymbol(s.symbol)}</span>
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
            <span className="font-mono text-lg font-bold">
              {s.currentPrice !== null ? `$${formatPrice(s.currentPrice)}` : "—"}
            </span>
          </button>
        )
      })}
    </div>
  )
}
