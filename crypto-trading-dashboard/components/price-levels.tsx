import { cn } from "@/lib/utils"
import { type Signal, formatPrice } from "@/lib/signals"
import { CopyValue } from "@/components/copy-value"

interface LevelRowProps {
  label: string
  value: number
  accent: "entry" | "tp" | "sl"
}

const accentStyles: Record<LevelRowProps["accent"], string> = {
  entry: "text-foreground",
  tp: "text-long",
  sl: "text-short",
}

const dotStyles: Record<LevelRowProps["accent"], string> = {
  entry: "bg-muted-foreground",
  tp: "bg-long",
  sl: "bg-short",
}

function LevelRow({ label, value, accent }: LevelRowProps) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-border/60 bg-secondary/30 px-4 py-3.5">
      <div className="flex items-center gap-2.5">
        <span className={cn("size-2 rounded-full", dotStyles[accent])} aria-hidden="true" />
        <span className="text-sm font-medium text-muted-foreground">{label}</span>
      </div>
      <div className="flex items-center gap-3">
        <span className={cn("font-mono text-lg font-semibold tabular-nums", accentStyles[accent])}>
          ${formatPrice(value)}
        </span>
        <CopyValue value={value} label={label} />
      </div>
    </div>
  )
}

export function PriceLevels({ signal }: { signal: Signal }) {
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-border/60 bg-card p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Order Levels</h2>
        <span className="text-xs text-muted-foreground">Tap to copy</span>
      </div>
      <div className="flex flex-col gap-2.5">
        <LevelRow label="Entry" value={signal.entry_price} accent="entry" />
        <LevelRow label="Take Profit" value={signal.tp} accent="tp" />
        <LevelRow label="Stop Loss" value={signal.sl} accent="sl" />
      </div>
    </div>
  )
}
