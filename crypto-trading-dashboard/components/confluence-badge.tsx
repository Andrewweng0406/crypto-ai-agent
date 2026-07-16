"use client"

import { ArrowDownRight, ArrowUpRight, HelpCircle, Hourglass, Lock, TrendingDown, TrendingUp } from "lucide-react"
import { cn } from "@/lib/utils"
import type { ConfluenceResult, ConfluenceTrend } from "@/lib/confluence"

// 白話文動態標籤——把 calculateMarketTrend() 的 7 種狀態，收斂成使用者一眼就懂的
// 「助漲／助跌／主力壓制」三種直覺分類。顏色沿用既有的 --long/--short 語意色
// （多單/看漲＝綠、空單/看跌＝紅），不新造一套色碼，避免跟盤面既有的多空配色衝突。
const STYLE_MAP: Record<
  ConfluenceTrend,
  { label: string; icon: typeof TrendingUp; className: string }
> = {
  強烈看多: { label: "強力助漲", icon: TrendingUp, className: "border-long/40 bg-long/[0.12] text-long" },
  波段看多: { label: "偏多助漲", icon: ArrowUpRight, className: "border-long/30 bg-long/[0.06] text-long" },
  強烈看空: { label: "強力助跌", icon: TrendingDown, className: "border-short/40 bg-short/[0.12] text-short" },
  波段看空: { label: "偏空助跌", icon: ArrowDownRight, className: "border-short/30 bg-short/[0.06] text-short" },
  高位震盪: { label: "高位主力壓制", icon: Lock, className: "border-border/60 bg-secondary/60 text-muted-foreground" },
  低位震盪: { label: "低位主力壓制", icon: Lock, className: "border-border/60 bg-secondary/60 text-muted-foreground" },
  等待量能確認: { label: "蓄勢待發", icon: Hourglass, className: "border-amber-400/30 bg-amber-400/[0.08] text-amber-300" },
  數據不足: { label: "資料不足", icon: HelpCircle, className: "border-dashed border-border/60 bg-transparent text-muted-foreground" },
}

/** 把共振結果轉成一句白話文——跟徽章分開匯出，方便在 tooltip / 詳情面板重用。 */
export function describeConfluence(result: ConfluenceResult): string {
  return result.actionAdvice
}

export function ConfluenceBadge({ result, className }: { result: ConfluenceResult; className?: string }) {
  const style = STYLE_MAP[result.trendStatus]
  const Icon = style.icon
  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold",
        style.className,
        className,
      )}
      title={result.actionAdvice}
    >
      <Icon className="size-3.5 shrink-0" aria-hidden="true" />
      <span>{style.label}</span>
      <span className="font-mono text-[10px] font-normal opacity-70">{result.confidenceScore}%</span>
    </div>
  )
}

/** 支撐/壓力位的展開版——徽章旁邊常會需要一起顯示這兩個數字跟它們的來源。 */
export function ConfluenceSupportResistance({ result }: { result: ConfluenceResult }) {
  const { support, supportSource, resistance, resistanceSource } = result.supportResistance
  if (support === null && resistance === null) return null

  return (
    <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
      {support !== null && (
        <span>
          支撐 <span className="font-mono font-semibold text-long">${support.toFixed(2)}</span>
          {supportSource && <span className="ml-1 opacity-70">({supportSource})</span>}
        </span>
      )}
      {resistance !== null && (
        <span>
          壓力 <span className="font-mono font-semibold text-short">${resistance.toFixed(2)}</span>
          {resistanceSource && <span className="ml-1 opacity-70">({resistanceSource})</span>}
        </span>
      )}
    </div>
  )
}
