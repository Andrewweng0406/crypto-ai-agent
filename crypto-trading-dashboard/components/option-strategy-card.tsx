"use client"

import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"
import { calculateMarketTrend, type ConfluenceTrend } from "@/lib/confluence"
import {
  adaptOptionStrategy,
  formatPrice,
  type BackendOptionStrategyResponse,
  type OptionStrategyDetail,
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

const TYPE_TONE: Record<OptionStrategyDetail["type"], "long" | "short" | "primary"> = {
  put_credit: "long",
  call_credit: "short",
  iron_condor: "primary",
}

// 這個功能只在期權分析關注清單內的標的能用（後端限制，見main.py的
// get_options_strategy說明），這裡沒有ORB資料可用（OptionsAnalyticsPanel
// 不追蹤ORB），confluence engine會用gex+大單流盡量判斷、缺ORB時信心分數
// 天花板較低，這是設計上允許的行為，不是bug。
export function OptionStrategyCard({ gex, recentSweeps }: OptionStrategyCardProps) {
  const [result, setResult] = useState<OptionStrategyResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedType, setSelectedType] = useState<OptionStrategyDetail["type"] | null>(null)

  const confluence = calculateMarketTrend({
    symbol: gex.symbol,
    currentPrice: gex.spotPrice,
    orb: null,
    gex,
    recentSweeps,
  })
  const sentiment = SENTIMENT_MAP[confluence.trendStatus]

  useEffect(() => {
    if (!result || result.strategies.length === 0) return
    const stillPresent = result.strategies.some((s) => s.type === selectedType)
    if (!stillPresent) {
      const recommended = result.strategies.find((s) => s.isRecommended)
      setSelectedType((recommended ?? result.strategies[0]).type)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result])

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

  const selectedStrategy = result?.strategies.find((s) => s.type === selectedType) ?? null

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
        (result.strategies.length > 0 ? (
          <>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              {result.strategies.map((s) => (
                <StrategySummaryCard
                  key={s.type}
                  strategy={s}
                  selected={s.type === selectedType}
                  onSelect={() => setSelectedType(s.type)}
                />
              ))}
            </div>

            {selectedStrategy && (
              <>
                <StrategyDetailView strategy={selectedStrategy} disclaimer={result.winRateDisclaimer} />
                <PayoffDiagram strategy={selectedStrategy} currentPrice={result.currentPrice} />
              </>
            )}
          </>
        ) : (
          <p className="rounded-xl border border-dashed border-border/60 px-4 py-4 text-center text-xs text-muted-foreground">
            {result.message ?? "暫無建議"}
          </p>
        ))}
    </div>
  )
}

// Tailwind的JIT掃描器只認得完整、字面量的class字串，不能用樣板字串動態拼
// `border-${tone}/50` 這種——那樣production build會掃不到、樣式整個消失，
// 所以這裡改用完整字面量的三條分支，不是可以再精簡的重複。
const SELECTED_TONE_CLASSES: Record<"long" | "short" | "primary", string> = {
  long: "border-long/50 bg-long/[0.07]",
  short: "border-short/50 bg-short/[0.07]",
  primary: "border-primary/50 bg-primary/[0.07]",
}

function StrategySummaryCard({
  strategy, selected, onSelect,
}: { strategy: OptionStrategyDetail; selected: boolean; onSelect: () => void }) {
  const tone = TYPE_TONE[strategy.type]
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex flex-col gap-2 rounded-xl border p-3 text-left transition-colors",
        selected ? SELECTED_TONE_CLASSES[tone] : "border-border/60 bg-secondary/30 hover:bg-secondary/50",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs font-semibold text-foreground">{strategy.name}</span>
        {strategy.isRecommended && (
          <span
            className={cn(
              "rounded-md px-1.5 py-0.5 text-[10px] font-semibold",
              tone === "long" ? "bg-long/15 text-long" : tone === "short" ? "bg-short/15 text-short" : "bg-primary/15 text-primary",
            )}
          >
            目前建議
          </span>
        )}
      </div>
      <span className="text-[11px] text-muted-foreground">理論勝率 {strategy.winRateEstimate}</span>
      <div className="flex items-center gap-3 text-[11px]">
        <span className="text-long">獲利 ${strategy.financials.maxProfit.toFixed(0)}</span>
        <span className="text-short">虧損 ${strategy.financials.maxLoss.toFixed(0)}</span>
      </div>
    </button>
  )
}

function StrategyDetailView({ strategy: s, disclaimer }: { strategy: OptionStrategyDetail; disclaimer: string }) {
  return (
    <div className="flex flex-col gap-4 border-t border-border/60 pt-4">
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
      <p className="text-[11px] text-muted-foreground">{disclaimer}</p>
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

// ---------------------------------------------------------------------------
// 到期損益圖：兩腳價差（put_credit/call_credit）用履約價+財務數字直接畫出
// 標準的「賣方對沖」形狀；Iron Condor（4腳）近似成兩側各自的斜坡＋中間平台，
// 用整體 max_profit/max_loss 等比例畫，不是逐檔精算（跟財務欄位本身一樣，
// 保證金/最大虧損是兩側取較大值，不是各自獨立算的），示意圖用途。
// ---------------------------------------------------------------------------

function payoffAt(s: OptionStrategyDetail, price: number): number {
  const { maxProfit, maxLoss } = s.financials
  const strikes = [...s.legs.map((l) => l.strikePrice)].sort((a, b) => a - b)

  if (s.type === "iron_condor" && strikes.length === 4) {
    const [k1, k2, k3, k4] = strikes
    if (price <= k1 || price >= k4) return -maxLoss
    if (price >= k2 && price <= k3) return maxProfit
    if (price < k2) {
      const frac = (price - k1) / (k2 - k1)
      return -maxLoss + frac * (maxProfit + maxLoss)
    }
    const frac = (k4 - price) / (k4 - k3)
    return -maxLoss + frac * (maxProfit + maxLoss)
  }

  const sell = s.legs.find((l) => l.action === "SELL")
  const buy = s.legs.find((l) => l.action === "BUY")
  if (!sell || !buy) return 0

  if (sell.optionType === "PUT") {
    if (price >= sell.strikePrice) return maxProfit
    if (price <= buy.strikePrice) return -maxLoss
    const frac = (price - buy.strikePrice) / (sell.strikePrice - buy.strikePrice)
    return -maxLoss + frac * (maxProfit + maxLoss)
  }
  if (price <= sell.strikePrice) return maxProfit
  if (price >= buy.strikePrice) return -maxLoss
  const frac = (buy.strikePrice - price) / (buy.strikePrice - sell.strikePrice)
  return -maxLoss + frac * (maxProfit + maxLoss)
}

function PayoffDiagram({ strategy, currentPrice }: { strategy: OptionStrategyDetail; currentPrice: number }) {
  const strikes = [...strategy.legs.map((l) => l.strikePrice)].sort((a, b) => a - b)
  const padPct = 0.08
  const rangeLo = strikes[0] * (1 - padPct)
  const rangeHi = strikes[strikes.length - 1] * (1 + padPct)

  const W = 720, H = 220, padL = 56, padR = 20, padTop = 16, padBottom = 28
  const plotW = W - padL - padR, plotH = H - padTop - padBottom
  const { maxProfit, maxLoss } = strategy.financials
  const yMax = maxProfit * 1.2 || 1
  const yMin = -maxLoss * 1.2 || -1

  const xAt = (p: number) => padL + ((p - rangeLo) / (rangeHi - rangeLo)) * plotW
  const yAt = (v: number) => padTop + ((yMax - v) / (yMax - yMin)) * plotH
  const zeroY = yAt(0)

  const steps = 60
  const points: [number, number][] = []
  for (let i = 0; i <= steps; i++) {
    const price = rangeLo + ((rangeHi - rangeLo) * i) / steps
    points.push([price, payoffAt(strategy, price)])
  }
  const linePath = points.map(([p, v], i) => `${i === 0 ? "M" : "L"} ${xAt(p).toFixed(1)} ${yAt(v).toFixed(1)}`).join(" ")
  const aboveArea =
    `M ${xAt(rangeLo).toFixed(1)} ${zeroY.toFixed(1)} ` +
    points.map(([p, v]) => `L ${xAt(p).toFixed(1)} ${yAt(Math.max(0, v)).toFixed(1)}`).join(" ") +
    ` L ${xAt(rangeHi).toFixed(1)} ${zeroY.toFixed(1)} Z`
  const belowArea =
    `M ${xAt(rangeLo).toFixed(1)} ${zeroY.toFixed(1)} ` +
    points.map(([p, v]) => `L ${xAt(p).toFixed(1)} ${yAt(Math.min(0, v)).toFixed(1)}`).join(" ") +
    ` L ${xAt(rangeHi).toFixed(1)} ${zeroY.toFixed(1)} Z`

  const showCurrentPrice = currentPrice >= rangeLo && currentPrice <= rangeHi
  const yTicks = [yMin, yMin / 2, 0, yMax / 2, yMax]

  return (
    <div className="flex flex-col gap-2 border-t border-border/60 pt-4">
      <div className="flex items-center justify-between text-xs">
        <span className="font-semibold text-foreground">到期損益模擬（示意圖，非逐檔精算）</span>
        <span className="text-muted-foreground">現價 ${formatPrice(currentPrice)}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-48 w-full rounded-xl bg-background/40" role="img" aria-label={`${strategy.name} 到期損益曲線`}>
        {yTicks.map((v, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={yAt(v)} y2={yAt(v)} stroke="var(--border)" strokeWidth={1} />
            <text x={padL - 6} y={yAt(v) + 3} textAnchor="end" fontSize={9} fontFamily="var(--font-mono)" fill="var(--muted-foreground)">
              {v >= 0 ? "+" : "-"}${Math.abs(Math.round(v))}
            </text>
          </g>
        ))}
        <path d={aboveArea} fill="var(--chart-bull)" opacity={0.12} />
        <path d={belowArea} fill="var(--chart-bear)" opacity={0.12} />
        <path d={linePath} fill="none" stroke={TYPE_TONE[strategy.type] === "short" ? "var(--chart-bear)" : "var(--chart-bull)"} strokeWidth={2} />
        {strikes.map((k, i) => (
          <g key={i}>
            <line x1={xAt(k)} x2={xAt(k)} y1={padTop} y2={H - padBottom} stroke="var(--border)" strokeWidth={1} strokeDasharray="2 3" />
            <text x={xAt(k)} y={H - padBottom + 14} textAnchor="middle" fontSize={9} fontFamily="var(--font-mono)" fill="var(--muted-foreground)">
              ${k.toFixed(0)}
            </text>
          </g>
        ))}
        {showCurrentPrice && (
          <line x1={xAt(currentPrice)} x2={xAt(currentPrice)} y1={padTop} y2={H - padBottom} stroke="#38bdf8" strokeWidth={1.5} strokeDasharray="4 3" />
        )}
      </svg>
    </div>
  )
}
