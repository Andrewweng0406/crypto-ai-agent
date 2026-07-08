import { Flame } from "lucide-react"
import { cn } from "@/lib/utils"
import { type MemeWatchItem, formatTime } from "@/lib/signals"

const OVERHEAT_STREAK_THRESHOLD = 4 // 對應後端 ATTENTION_OVERHEAT_STREAK_THRESHOLD

const STATUS_CONFIG = {
  // 刻意不用「黃金開倉時機」這種話術——這是一個未經回測驗證的組合式判斷
  // （成交量倍數 + CoinGecko 熱門榜代理指標），不是有把握的交易訊號。
  confirmed: { dot: "🟢", label: "條件已滿足", className: "border-long/50 bg-long/[0.06]" },
  overheated: { dot: "🚨", label: "觸發過熱攔截：禁止追高接盤", className: "border-short/50 bg-short/[0.08]" },
  insufficient: { dot: "⚪", label: "觀望中 / 條件未滿足", className: "border-border/60 bg-card" },
} as const

function shortSymbol(symbol: string): string {
  return symbol.replace("/USDT", "")
}

interface MemeResonanceBoardProps {
  item: MemeWatchItem
}

// 社群共振資訊看板：點選上方某個迷因幣後顯示。跟迷因雷達其他部分一樣是純資訊
// 揭露，不是交易訊號——狀態燈用中性字眼（「條件已滿足」而非「黃金買點」），
// 因為這只是一個尚未驗證過的組合式判斷。
export function MemeResonanceBoard({ item }: MemeResonanceBoardProps) {
  const cfg = STATUS_CONFIG[item.resonanceStatus]
  const streakDisplay = Math.min(item.trendingTopStreak, OVERHEAT_STREAK_THRESHOLD)
  const isOverheating = item.resonanceStatus === "overheated"

  return (
    <div className={cn("flex flex-col gap-4 rounded-2xl border p-5", cfg.className)}>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">社群共振資訊看板</h3>
        <span className="font-mono text-sm font-semibold">{shortSymbol(item.symbol)}</span>
      </div>

      {/* 綜合狀態燈 */}
      <div
        className={cn(
          "flex items-center gap-3 rounded-xl border px-4 py-3.5",
          isOverheating ? "border-short/50 bg-short/[0.1] animate-pulse" : "border-border/60 bg-secondary/30",
        )}
      >
        <span className="text-2xl leading-none">{cfg.dot}</span>
        <span className={cn("text-base font-bold", isOverheating && "text-short")}>{cfg.label}</span>
      </div>

      {/* CoinGecko 熱門榜 */}
      <div className="flex items-center justify-between rounded-xl border border-border/60 bg-secondary/30 px-4 py-3">
        <span className="text-xs text-muted-foreground">市場注意力（CoinGecko 熱門榜）</span>
        {item.isTrending && item.trendingRank !== null ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-long/15 px-2.5 py-1 text-xs font-semibold text-long">
            <Flame className="size-3.5" aria-hidden="true" />
            CoinGecko Top {item.trendingRank + 1}
          </span>
        ) : (
          <span className="rounded-full bg-secondary px-2.5 py-1 text-xs text-muted-foreground">未上榜</span>
        )}
      </div>

      {/* 過熱風控進度條 */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">過熱風控進度</span>
          <span className={cn("font-mono font-semibold", isOverheating ? "text-short" : "text-muted-foreground")}>
            {streakDisplay}/{OVERHEAT_STREAK_THRESHOLD} 週期
          </span>
        </div>
        <div className="flex gap-1">
          {Array.from({ length: OVERHEAT_STREAK_THRESHOLD }).map((_, i) => (
            <div
              key={i}
              className={cn(
                "h-2 flex-1 rounded-full transition-colors",
                i < streakDisplay ? (isOverheating ? "bg-short animate-pulse" : "bg-long") : "bg-secondary",
              )}
            />
          ))}
        </div>
      </div>

      {/* AI 共振摘要 */}
      <div className="rounded-xl border border-border/60 bg-black/30 p-3">
        <p className="font-mono text-xs leading-relaxed text-long">
          {item.lastResonanceSummary ? (
            <>[AI Audit]: {item.lastResonanceSummary}</>
          ) : (
            <span className="text-muted-foreground">[AI Audit]: 尚無共振摘要，等待條件觸發後才會生成。</span>
          )}
        </p>
        {item.lastResonanceAt && (
          <p className="mt-1.5 text-[11px] text-muted-foreground">最後更新：{formatTime(item.lastResonanceAt)}</p>
        )}
      </div>
    </div>
  )
}
