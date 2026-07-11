import { type SqueezeInfo } from "@/lib/signals"

// 多空情緒擠壓爆破模式（獨立、實驗性模塊，未經回測驗證）的狀態燈，市場掃描跟
// 迷因雷達共用。刻意不用「黃金開倉點」這種話術（見 main.py 模塊說明）。
export function SqueezeBadge({ squeeze }: { squeeze: SqueezeInfo }) {
  if (!squeeze.hasPerpMarket) {
    return (
      <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
        無合約市場
      </span>
    )
  }

  if (squeeze.tier === "green") {
    // 警告黃外框+呼吸環效果，不用long(綠)語意色——Squeeze可能是軋空頭也可能是
    // 殺多頭，不是單純看多訊號，用中性的警戒色比較不會誤導方向。
    return (
      <span className="relative inline-flex items-center gap-1 rounded bg-amber-400/20 px-1.5 py-0.5 text-[10px] font-bold text-amber-400 ring-1 ring-amber-400/60">
        <span className="absolute inset-0 animate-ping rounded bg-amber-400/30" aria-hidden="true" />
        <span className="relative">🔥 軋空擠壓中</span>
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
  return tier === "green" ? "border-amber-400/60 bg-amber-400/[0.06]" : ""
}
