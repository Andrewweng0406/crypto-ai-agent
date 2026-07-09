import { type SqueezeInfo } from "@/lib/signals"

// 多空情緒擠壓爆破模式（獨立、實驗性模塊，未經回測驗證）的狀態燈，市場掃描跟
// 迷因雷達共用。刻意不用「黃金開倉點」這種話術（見 main.py 模塊說明），green
// 燈號用中性字眼「條件已滿足」。
export function SqueezeBadge({ squeeze }: { squeeze: SqueezeInfo }) {
  if (!squeeze.hasPerpMarket) {
    return (
      <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
        無合約市場
      </span>
    )
  }

  if (squeeze.tier === "green") {
    return (
      <span className="inline-flex animate-pulse items-center gap-1 rounded bg-long/20 px-1.5 py-0.5 text-[10px] font-bold text-long">
        ⚡ 觸發終極爆破：條件已滿足
      </span>
    )
  }

  if (squeeze.tier === "yellow") {
    return (
      <span className="inline-flex animate-pulse items-center gap-1 rounded bg-yellow-400/20 px-1.5 py-0.5 text-[10px] font-bold text-yellow-400">
        ⚠️ 持倉異常 {squeeze.oiGrowth1hPct !== null ? `+${squeeze.oiGrowth1hPct.toFixed(0)}%` : ""}
      </span>
    )
  }

  if (squeeze.tier === "blue") {
    return (
      <span className="inline-flex animate-pulse items-center gap-1 rounded bg-blue-400/20 px-1.5 py-0.5 text-[10px] font-bold text-blue-400">
        🔵 短線擠壓：適合極短線頭皮單
      </span>
    )
  }

  return (
    <span className="inline-flex items-center gap-1 rounded bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
      ⚪ 正常蓄力
    </span>
  )
}

export function squeezeRowHighlightClass(tier: SqueezeInfo["tier"]): string {
  // 三鐵律完全觸發時整行加強高亮，其他狀態不影響原本的邊框樣式
  return tier === "green" ? "border-long/60 bg-long/[0.06]" : ""
}
