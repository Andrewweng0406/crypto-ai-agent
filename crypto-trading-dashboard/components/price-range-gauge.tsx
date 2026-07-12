import { cn } from "@/lib/utils"
import { type Signal, formatPrice } from "@/lib/signals"

export function PriceRangeGauge({ signal }: { signal: Signal }) {
  const { sl, tp, current_price: current } = signal
  const span = tp - sl
  const rawPct = ((current - sl) / span) * 100
  const pct = Math.min(100, Math.max(0, rawPct))

  // Distance to each boundary as a percentage of the full range.
  const toTp = (((tp - current) / span) * 100).toFixed(1)
  const toSl = (((current - sl) / span) * 100).toFixed(1)

  return (
    <div className="flex flex-col gap-5 rounded-2xl border border-border/60 bg-card p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Position Range</h2>
        <span className="font-mono text-xs text-muted-foreground">
          {toTp}% to TP left
        </span>
      </div>

      <div className="px-1 pt-6 pb-2">
        <div className="relative h-2.5 rounded-full bg-gradient-to-r from-short via-muted to-long">
          {/* Current price marker */}
          <div
            className="absolute -top-1 flex -translate-x-1/2 flex-col items-center"
            style={{ left: `${pct}%` }}
          >
            <span className="mb-2 whitespace-nowrap rounded-md border border-border bg-popover px-2 py-1 font-mono text-xs font-semibold shadow-lg">
              ${formatPrice(current)}
            </span>
            <span className="size-4 rounded-full border-2 border-background bg-foreground shadow-[0_0_10px] shadow-foreground/40" />
          </div>
        </div>

        <div className="mt-4 flex items-center justify-between">
          <div className="flex flex-col">
            <span className="text-xs font-medium uppercase tracking-wide text-short">Stop Loss</span>
            <span className="font-mono text-sm font-semibold text-short">${formatPrice(sl)}</span>
          </div>
          <div className="flex flex-col text-right">
            <span className="text-xs font-medium uppercase tracking-wide text-long">Take Profit</span>
            <span className="font-mono text-sm font-semibold text-long">${formatPrice(tp)}</span>
          </div>
        </div>
      </div>

      <p className={cn("text-center text-xs text-muted-foreground")}>
        <span className="font-mono font-semibold text-foreground">{toTp}%</span> of range remaining before target ·{" "}
        <span className="font-mono font-semibold text-foreground">{toSl}%</span> cushion above stop
      </p>
    </div>
  )
}
