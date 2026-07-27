"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { calculateMarketTrend, type ConfluenceTrend } from "@/lib/confluence"
import {
  adaptOptionStrategy,
  type BackendOptionStrategyResponse,
  type OptionStrategyResult,
  type OptionStrategySentiment,
  type OptionsGexData,
  type WhaleSweepItem,
} from "@/lib/signals"

interface OptionStrategyCardProps {
  gex: OptionsGexData
  recentSweeps: WhaleSweepItem[]
}

// 對齊 lib/confluence.ts 的 ConfluenceTrend——只有方向明確時才觸發策略產生，
// 「等待量能確認」「數據不足」這兩種狀態連方向都還沒確定，不該硬產生一個
// 誤導性的策略建議。
const SENTIMENT_MAP: Record<ConfluenceTrend, OptionStrategySentiment | null> = {
  強烈看多: "bullish",
  波段看多: "bullish",
  強烈看空: "bearish",
  波段看空: "bearish",
  高位震盪: "neutral",
  低位震盪: "neutral",
  等待量能確認: null,
  數據不足: null,
}

// 這個功能只在期權分析關注清單內的標的能用（後端限制，見main.py的
// get_options_strategy說明），這裡沒有ORB資料可用（OptionsAnalyticsPanel
// 不追蹤ORB），confluence engine會用gex+大單流盡量判斷、缺ORB時信心分數
// 天花板較低，這是設計上允許的行為，不是bug。
export function OptionStrategyCard({ gex, recentSweeps }: OptionStrategyCardProps) {
  const [result, setResult] = useState<OptionStrategyResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const confluence = calculateMarketTrend({
    symbol: gex.symbol,
    currentPrice: gex.spotPrice,
    orb: null,
    gex,
    recentSweeps,
  })
  const sentiment = SENTIMENT_MAP[confluence.trendStatus]

  async function handleGenerate() {
    if (!sentiment) return
    setLoading(true)
    setError(null)
    try {
      const qs = new URLSearchParams({ symbol: gex.symbol, sentiment, sentiment_label: confluence.trendStatus })
      const res = await fetch(`/api/options/strategy?${qs.toString()}`)
      const body = await res.json()
      if (!res.ok) throw new Error(body?.detail ?? `請求失敗 (${res.status})`)
      setResult(adaptOptionStrategy(body as BackendOptionStrategyResponse))
    } catch (e) {
      setError(e instanceof Error ? e.message : "產生策略失敗")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-border/60 bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm font-semibold">🎯 期權賣方價差策略建議</span>
          <span className="rounded-md bg-secondary px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
            共振判斷：{confluence.trendStatus}
          </span>
        </div>
        <button
          type="button"
          onClick={handleGenerate}
          disabled={!sentiment || loading}
          className={cn(
            "rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
            sentiment && !loading
              ? "bg-primary text-primary-foreground hover:opacity-90"
              : "cursor-not-allowed bg-secondary text-muted-foreground",
          )}
        >
          {loading ? "產生中…" : "產生策略建議"}
        </button>
      </div>

      {!sentiment && (
        <p className="text-xs text-muted-foreground">
          目前共振判斷為「{confluence.trendStatus}」，方向尚未明朗，暫不產生策略建議。
        </p>
      )}

      {error && <p className="text-xs text-short">{error}</p>}

      {result &&
        (result.strategy ? (
          <StrategyDetailView result={result} />
        ) : (
          <p className="rounded-xl border border-dashed border-border/60 px-4 py-4 text-center text-xs text-muted-foreground">
            {result.message ?? "暫無建議"}
          </p>
        ))}
    </div>
  )
}

function StrategyDetailView({ result }: { result: OptionStrategyResult }) {
  const s = result.strategy
  if (!s) return null
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-base font-semibold text-foreground">{s.name}</span>
        <span className="rounded-md bg-primary/15 px-2 py-0.5 font-mono text-[11px] font-semibold text-primary">
          理論勝率（拿到最大獲利的機率）{s.winRateEstimate}
        </span>
        <span className="text-[11px] text-muted-foreground">到期日 {s.expirationDate}</span>
      </div>

      {s.legWinRates && (
        <p className="text-[11px] text-muted-foreground">
          單腳存活率（僅供參考，不是策略勝率）：Put {s.legWinRates.put} · Call {s.legWinRates.call}
          ——要兩腳都不破才算最大獲利，所以上面的理論勝率必然比這兩個數字都低。
        </p>
      )}

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {s.legs.map((leg, i) => (
          <div
            key={`${leg.action}-${leg.optionType}-${leg.strikePrice}-${i}`}
            className={cn(
              "flex flex-col gap-1 rounded-xl border p-3",
              leg.action === "SELL" ? "border-long/30 bg-long/[0.06]" : "border-short/30 bg-short/[0.06]",
            )}
          >
            <span className="flex items-center gap-2 font-mono text-sm font-semibold">
              <span className={leg.action === "SELL" ? "text-long" : "text-short"}>{leg.action}</span>
              {leg.optionType} ${leg.strikePrice.toFixed(0)}
            </span>
            <span className="text-xs text-muted-foreground">{leg.reason}</span>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="最大獲利" value={`$${s.financials.maxProfit.toFixed(0)}`} tone="long" />
        <StatTile label="最大虧損" value={`$${s.financials.maxLoss.toFixed(0)}`} tone="short" />
        <StatTile label="所需保證金" value={`$${s.financials.maxMarginRequired.toFixed(0)}`} />
        <StatTile label="風險報酬比" value={s.financials.riskRewardRatio} />
      </div>

      <p className="rounded-xl bg-secondary/60 px-4 py-3 text-xs leading-relaxed text-foreground">{s.aiAdvice}</p>
      <p className="text-[11px] text-muted-foreground">{result.winRateDisclaimer}</p>
    </div>
  )
}

function StatTile({ label, value, tone }: { label: string; value: string; tone?: "long" | "short" }) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-border/60 px-3 py-2.5">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span
        className={cn(
          "font-mono text-base font-semibold",
          tone === "long" ? "text-long" : tone === "short" ? "text-short" : "text-foreground",
        )}
      >
        {value}
      </span>
    </div>
  )
}
