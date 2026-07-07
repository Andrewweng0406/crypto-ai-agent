import { cn } from "@/lib/utils"
import { type HistorySignal, type HistoryStats, formatTime } from "@/lib/signals"

interface RecentHistoryProps {
  history: HistorySignal[]
  stats?: HistoryStats
  error?: string
}

export function RecentHistory({ history, stats, error }: RecentHistoryProps) {
  return (
    <div className="flex h-full flex-col gap-3 rounded-2xl border border-border/60 bg-card p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Recent Signals</h2>
        {stats && stats.totalTrades > 0 ? (
          <span className="rounded-full bg-secondary px-2 py-0.5 font-mono text-xs font-semibold text-foreground">
            {stats.winRatePct.toFixed(1)}% win rate · {stats.wins}W {stats.losses}L
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">Last {history.length}</span>
        )}
      </div>

      {error && (
        <p className="rounded-lg border border-short/30 bg-short/[0.06] px-3 py-2 text-xs text-short">
          無法載入歷史紀錄：{error}
        </p>
      )}

      {!error && history.length === 0 && (
        <p className="rounded-lg border border-dashed border-border/60 px-3 py-6 text-center text-xs text-muted-foreground">
          尚無已結算的歷史訊號。
        </p>
      )}

      <ul className="flex flex-col gap-2 overflow-y-auto pr-1">
        {history.map((h) => {
          const won = h.outcome === "Hit TP"
          return (
            <li
              key={h.id}
              className="flex items-center justify-between gap-3 rounded-xl border border-border/50 bg-secondary/30 px-3.5 py-3"
            >
              <div className="flex flex-col gap-0.5">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-semibold">{h.symbol}</span>
                  <span
                    className={cn(
                      "rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase",
                      h.side === "Long" ? "bg-long/15 text-long" : "bg-short/15 text-short",
                    )}
                  >
                    {h.side}
                  </span>
                </div>
                <span className="text-xs text-muted-foreground">{formatTime(h.closedAt)}</span>
              </div>

              <div className="flex flex-col items-end gap-0.5">
                <span
                  className={cn(
                    "rounded-full px-2.5 py-0.5 text-xs font-semibold",
                    won ? "bg-long/15 text-long" : "bg-short/15 text-short",
                  )}
                >
                  {h.outcome}
                </span>
                <span className={cn("font-mono text-xs font-semibold", won ? "text-long" : "text-short")}>
                  {h.pnl >= 0 ? "+" : ""}
                  {h.pnl.toFixed(1)}%
                </span>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
