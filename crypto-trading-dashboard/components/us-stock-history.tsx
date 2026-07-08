import { cn } from "@/lib/utils"
import { type USStockHistoryItem, type HistoryStats, formatPrice, formatTime } from "@/lib/signals"

interface USStockHistoryProps {
  trades: USStockHistoryItem[]
  stats: HistoryStats
  error?: string
}

// 實盤累積成交紀錄，不是回測——樣本數在累積起來之前（尤其剛上線那幾天）沒有
// 統計意義，所以永遠標註「實盤」而不是暗示這是驗證過的勝率。
export function USStockHistory({ trades, stats, error }: USStockHistoryProps) {
  const totalPnlPct = trades.reduce((sum, t) => sum + t.pnlPct, 0)

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-border/60 bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          實盤成交紀錄（美股 ORB）
        </h2>
        <span className="text-xs text-muted-foreground">
          非回測，樣本數少時不具統計意義
        </span>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <StatTile label="總交易筆數" value={String(stats.totalTrades)} />
        <StatTile
          label="實盤勝率"
          value={stats.totalTrades > 0 ? `${stats.winRatePct.toFixed(1)}%` : "—"}
          tone={stats.totalTrades > 0 ? (stats.winRatePct >= 50 ? "long" : "short") : "neutral"}
        />
        <StatTile
          label="累計報酬（加總%）"
          value={stats.totalTrades > 0 ? `${totalPnlPct >= 0 ? "+" : ""}${totalPnlPct.toFixed(1)}%` : "—"}
          tone={stats.totalTrades > 0 ? (totalPnlPct >= 0 ? "long" : "short") : "neutral"}
        />
      </div>

      {error && (
        <p className="rounded-lg border border-short/30 bg-short/[0.06] px-3 py-2 text-xs text-short">
          無法載入成交紀錄：{error}
        </p>
      )}

      {!error && trades.length === 0 && (
        <p className="rounded-lg border border-dashed border-border/60 px-3 py-6 text-center text-xs text-muted-foreground">
          尚無已結算的實盤成交。
        </p>
      )}

      {trades.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-xs">
            <thead>
              <tr className="text-muted-foreground">
                <th className="pb-2 font-medium">標的</th>
                <th className="pb-2 font-medium">方向</th>
                <th className="pb-2 font-medium">進場價</th>
                <th className="pb-2 font-medium">出場價</th>
                <th className="pb-2 font-medium">損益</th>
                <th className="pb-2 font-medium">結算時間</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => {
                const won = t.result === "WIN"
                return (
                  <tr key={t.id} className="border-t border-border/40">
                    <td className="py-2.5 font-mono font-semibold">{t.displayName}</td>
                    <td className="py-2.5">
                      <span
                        className={cn(
                          "rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase",
                          t.side === "Long" ? "bg-long/15 text-long" : "bg-short/15 text-short",
                        )}
                      >
                        {t.side}
                      </span>
                    </td>
                    <td className="py-2.5 font-mono">${formatPrice(t.entryPrice)}</td>
                    <td className="py-2.5 font-mono">${formatPrice(t.exitPrice)}</td>
                    <td className={cn("py-2.5 font-mono font-semibold", won ? "text-long" : "text-short")}>
                      {t.pnlPct >= 0 ? "+" : ""}
                      {t.pnlPct.toFixed(2)}%
                    </td>
                    <td className="py-2.5 text-muted-foreground">{formatTime(t.closedAt)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function StatTile({
  label,
  value,
  tone = "neutral",
}: {
  label: string
  value: string
  tone?: "long" | "short" | "neutral"
}) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-border/60 bg-secondary/30 px-4 py-3">
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <span
        className={cn(
          "font-mono text-lg font-bold",
          tone === "long" && "text-long",
          tone === "short" && "text-short",
          tone === "neutral" && "text-foreground",
        )}
      >
        {value}
      </span>
    </div>
  )
}
