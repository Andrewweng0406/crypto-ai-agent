import { cn } from "@/lib/utils"
import { type OrbMonitoring, formatPrice } from "@/lib/signals"

interface USStockMonitoringPanelProps {
  monitoring: OrbMonitoring
  currentPrice: number | null
}

const REGIME_CONFIG = {
  Bullish: { label: "偏多", className: "bg-long/15 text-long" },
  Bearish: { label: "偏空", className: "bg-short/15 text-short" },
  Neutral: { label: "中性", className: "bg-secondary text-muted-foreground" },
} as const

// 沒有部位時顯示：現價在「今天開盤區間」（09:30-09:45 ET 第一根15m K棒的高低點）
// 中的位置，加上 RVOL、大盤濾網兩張數字卡 —— 跟主流幣的 MonitoringPanel 同樣精神，
// 只是把「唐奇安通道」換成「開盤區間」。
export function USStockMonitoringPanel({ monitoring, currentPrice }: USStockMonitoringPanelProps) {
  const { openingHigh, openingLow, rvol, marketRegime } = monitoring

  const hasRange =
    openingHigh !== null && openingLow !== null && currentPrice !== null && openingHigh > openingLow

  let pct = 50
  let toUpperPct: number | null = null
  let toLowerPct: number | null = null
  if (hasRange) {
    const span = openingHigh - openingLow
    pct = Math.min(100, Math.max(0, ((currentPrice - openingLow) / span) * 100))
    toUpperPct = ((openingHigh - currentPrice) / currentPrice) * 100
    toLowerPct = ((currentPrice - openingLow) / currentPrice) * 100
  }

  const regimeInfo = REGIME_CONFIG[marketRegime]

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-border/60 bg-card p-5">
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">開盤區間位置（ORB）</h3>
          {hasRange && toUpperPct !== null && (
            <span className="font-mono text-xs text-muted-foreground">還差 {toUpperPct.toFixed(2)}% 到區間高點</span>
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
                <span className="font-medium uppercase tracking-wide text-short">區間低點</span>
                <span className="font-mono font-semibold text-short">${formatPrice(openingLow as number)}</span>
              </div>
              <div className="flex flex-col text-right">
                <span className="font-medium uppercase tracking-wide text-long">區間高點</span>
                <span className="font-mono font-semibold text-long">${formatPrice(openingHigh as number)}</span>
              </div>
            </div>
            {toLowerPct !== null && (
              <p className="text-center text-xs text-muted-foreground">
                <span className="font-mono font-semibold text-foreground">{toLowerPct.toFixed(2)}%</span> 高於區間低點 ·{" "}
                <span className="font-mono font-semibold text-foreground">{toUpperPct?.toFixed(2)}%</span> 低於區間高點
              </p>
            )}
          </>
        ) : (
          <div className="flex h-2.5 items-center justify-center rounded-full bg-secondary text-[10px] text-muted-foreground">
            等待開盤區間鎖定（美東 09:30-09:45）…
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col justify-between gap-1 rounded-xl border border-border/60 bg-secondary/30 px-4 py-3">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">RVOL 相對成交量</span>
          <span
            className={cn(
              "font-mono text-xl font-bold",
              rvol !== null && rvol >= 3.5 ? "text-long" : "text-foreground",
            )}
          >
            {rvol !== null ? `${rvol.toFixed(2)}x` : "—"}
          </span>
          <span className="text-[11px] text-muted-foreground">需 ≥ 3.50x（過去5個交易日同時段均量）</span>
        </div>

        <div className="flex flex-col justify-between gap-1.5 rounded-xl border border-border/60 bg-secondary/30 px-4 py-3">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">大盤濾網</span>
          <span className={cn("inline-flex w-fit items-center rounded-full px-2 py-0.5 text-sm font-semibold", regimeInfo.className)}>
            {regimeInfo.label}
          </span>
          <span className="text-[11px] text-muted-foreground">需與大盤（NASDAQ100）同向才會觸發訊號</span>
        </div>
      </div>
    </div>
  )
}
