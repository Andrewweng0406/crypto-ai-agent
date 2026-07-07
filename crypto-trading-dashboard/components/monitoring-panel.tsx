import { cn } from "@/lib/utils"
import { type Monitoring, formatPrice } from "@/lib/signals"

interface MonitoringPanelProps {
  monitoring: Monitoring
  currentPrice: number | null
}

const BIAS_CONFIG = {
  Bullish: { label: "偏多", className: "bg-long/15 text-long" },
  Bearish: { label: "偏空", className: "bg-short/15 text-short" },
  Neutral: { label: "中性", className: "bg-secondary text-muted-foreground" },
} as const

// Fills the "no active position" screen with the real numbers the engine is
// already computing every scan — distance to the Donchian breakout, current
// volume vs the required multiple, and the funding-rate / top-trader read —
// instead of leaving it blank just because no trade has triggered yet.
export function MonitoringPanel({ monitoring, currentPrice }: MonitoringPanelProps) {
  const { donchianUpper, donchianLower, volumeRatio, fundingRate, topTraderRatio, bias } = monitoring

  const hasRange =
    donchianUpper !== null && donchianLower !== null && currentPrice !== null && donchianUpper > donchianLower

  let pct = 50
  let toUpperPct: number | null = null
  let toLowerPct: number | null = null
  if (hasRange) {
    const span = donchianUpper - donchianLower
    pct = Math.min(100, Math.max(0, ((currentPrice - donchianLower) / span) * 100))
    toUpperPct = ((donchianUpper - currentPrice) / currentPrice) * 100
    toLowerPct = ((currentPrice - donchianLower) / currentPrice) * 100
  }

  const biasInfo = bias ? BIAS_CONFIG[bias] : null

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-border/60 bg-card p-5">
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">距離突破（唐奇安通道）</h3>
          {hasRange && toUpperPct !== null && (
            <span className="font-mono text-xs text-muted-foreground">還差 {toUpperPct.toFixed(2)}% 到上軌</span>
          )}
        </div>

        {hasRange ? (
          <>
            <div className="relative h-2.5 rounded-full bg-gradient-to-r from-short via-muted to-long">
              <div className="absolute -top-1 flex -translate-x-1/2 flex-col items-center" style={{ left: `${pct}%` }}>
                <span className="mb-2 whitespace-nowrap rounded-md border border-border bg-popover px-2 py-1 font-mono text-xs font-semibold shadow-lg">
                  ${formatPrice(currentPrice as number)}
                </span>
                <span className="size-4 rounded-full border-2 border-background bg-foreground shadow-[0_0_10px] shadow-foreground/40" />
              </div>
            </div>
            <div className="mt-4 flex items-center justify-between text-xs">
              <div className="flex flex-col">
                <span className="font-medium uppercase tracking-wide text-short">下軌</span>
                <span className="font-mono font-semibold text-short">${formatPrice(donchianLower as number)}</span>
              </div>
              <div className="flex flex-col text-right">
                <span className="font-medium uppercase tracking-wide text-long">上軌</span>
                <span className="font-mono font-semibold text-long">${formatPrice(donchianUpper as number)}</span>
              </div>
            </div>
            {toLowerPct !== null && (
              <p className="text-center text-xs text-muted-foreground">
                <span className="font-mono font-semibold text-foreground">{toLowerPct.toFixed(2)}%</span> 高於下軌 ·{" "}
                <span className="font-mono font-semibold text-foreground">{toUpperPct?.toFixed(2)}%</span> 低於上軌
              </p>
            )}
          </>
        ) : (
          <div className="flex h-2.5 items-center justify-center rounded-full bg-secondary text-[10px] text-muted-foreground">
            資料累積中…
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col justify-between gap-1 rounded-xl border border-border/60 bg-secondary/30 px-4 py-3">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">量能倍數</span>
          <span
            className={cn(
              "font-mono text-xl font-bold",
              volumeRatio !== null && volumeRatio >= 2 ? "text-long" : "text-foreground",
            )}
          >
            {volumeRatio !== null ? `${volumeRatio.toFixed(2)}x` : "—"}
          </span>
          <span className="text-[11px] text-muted-foreground">需 ≥ 2.00x 才視為帶量突破</span>
        </div>

        <div className="flex flex-col justify-between gap-1.5 rounded-xl border border-border/60 bg-secondary/30 px-4 py-3">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">聰明錢偏見</span>
          {biasInfo ? (
            <span className={cn("inline-flex w-fit items-center rounded-full px-2 py-0.5 text-sm font-semibold", biasInfo.className)}>
              {biasInfo.label}
            </span>
          ) : (
            <span className="font-mono text-xl font-bold text-muted-foreground">—</span>
          )}
          <span className="text-[11px] text-muted-foreground">
            資金費率 {fundingRate !== null ? `${(fundingRate * 100).toFixed(3)}%` : "—"} · 大戶多空比{" "}
            {topTraderRatio !== null ? topTraderRatio.toFixed(2) : "—"}
          </span>
        </div>
      </div>
    </div>
  )
}
