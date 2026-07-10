import { cn } from "@/lib/utils"
import { type MemeTradeState, formatPrice } from "@/lib/signals"

interface MemeTradeWatchlistProps {
  coins: MemeTradeState[]
  selectedSymbol: string | null
  onSelect: (symbol: string) => void
}

// 只有兩檔（WIF/DOGE）——180天回測裡唯二樣本數跨過統計門檻的迷因幣，永遠
// 顯示兩檔，不管有沒有觸發訊號，跟美股 ORB Watchlist 同樣的「監控板」精神。
export function MemeTradeWatchlist({ coins, selectedSymbol, onSelect }: MemeTradeWatchlistProps) {
  return (
    <div className="flex flex-wrap gap-3">
      {coins.map((c) => {
        const isSelected = c.symbol === selectedSymbol
        const isOpen = c.status === "OPEN" && c.signal

        return (
          <button
            key={c.symbol}
            type="button"
            onClick={() => onSelect(c.symbol)}
            className={cn(
              "flex min-w-[180px] flex-1 flex-col gap-1.5 rounded-xl border px-4 py-3 text-left transition-colors",
              isSelected ? "border-primary/60 bg-primary/[0.08]" : "border-border/60 bg-card hover:bg-secondary/40",
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-sm font-semibold">{c.displayName}</span>
              {isOpen ? (
                <span
                  className={cn(
                    "rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase",
                    c.signal!.side === "Long" ? "bg-long/15 text-long" : "bg-short/15 text-short",
                  )}
                >
                  {c.signal!.side} {c.signal!.leverage}x
                </span>
              ) : (
                <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px] font-semibold uppercase text-muted-foreground">
                  No Signal
                </span>
              )}
            </div>
            <span className="font-mono text-lg font-bold">
              {c.currentPrice !== null ? `$${formatPrice(c.currentPrice)}` : "—"}
            </span>
          </button>
        )
      })}
    </div>
  )
}
