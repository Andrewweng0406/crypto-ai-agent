"use client"

import { type RSI2ChartPoint } from "@/lib/signals"

interface RSI2TechnicalChartProps {
  points: RSI2ChartPoint[]
  entryPrice: number | null
  stopLoss: number | null
}

// 交易員在RSI(2)均值回歸策略上實際會盯的那幾條線：主圖收盤價+SMA200(長期多頭濾網)+
// SMA5(動態止盈參考線)，副圖RSI(2)搭配10/90標準參考線（策略進場門檻是RSI(2)<10）。
export function RSI2TechnicalChart({ points, entryPrice, stopLoss }: RSI2TechnicalChartProps) {
  if (points.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-xl border border-dashed border-border/60 bg-card/40 text-sm text-muted-foreground">
        載入技術面圖表中…
      </div>
    )
  }

  const width = 900
  const mainHeight = 260
  const rsiHeight = 100
  const padX = 8
  const padY = 10

  const closes = points.map((p) => p.close)
  const sma200s = points.map((p) => p.sma200).filter((v): v is number => v !== null)
  const sma5s = points.map((p) => p.sma5).filter((v): v is number => v !== null)
  const allPriceValues = [...closes, ...sma200s, ...sma5s, ...(entryPrice ? [entryPrice] : []), ...(stopLoss ? [stopLoss] : [])]
  const minPrice = Math.min(...allPriceValues)
  const maxPrice = Math.max(...allPriceValues)
  const priceRange = maxPrice - minPrice || 1

  const x = (i: number) => padX + (i / Math.max(points.length - 1, 1)) * (width - padX * 2)
  const yPrice = (v: number) => padY + (1 - (v - minPrice) / priceRange) * (mainHeight - padY * 2)

  const closeLine = points.map((p, i) => `${x(i)},${yPrice(p.close)}`).join(" ")
  const sma200Points = points
    .map((p, i) => (p.sma200 !== null ? `${x(i)},${yPrice(p.sma200)}` : null))
    .filter((v): v is string => v !== null)
    .join(" ")
  const sma5Points = points
    .map((p, i) => (p.sma5 !== null ? `${x(i)},${yPrice(p.sma5)}` : null))
    .filter((v): v is string => v !== null)
    .join(" ")

  const yRsi = (v: number) => padY + (1 - v / 100) * (rsiHeight - padY * 2)
  const rsiLine = points
    .map((p, i) => (p.rsi2 !== null ? `${x(i)},${yRsi(p.rsi2)}` : null))
    .filter((v): v is string => v !== null)
    .join(" ")

  const lastPoint = points[points.length - 1]

  return (
    <div className="flex flex-col gap-1 rounded-xl border border-border/60 bg-background/40 p-3">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted-foreground">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className="inline-block h-0.5 w-3 bg-foreground" /> 收盤價
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-0.5 w-3 bg-amber-400" /> SMA200
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-0.5 w-3 bg-sky-400" /> SMA5（動態止盈參考）
          </span>
        </div>
        <span className="font-mono">
          最新收盤 ${lastPoint.close.toFixed(2)}
          {lastPoint.rsi2 !== null && ` · RSI(2) ${lastPoint.rsi2.toFixed(1)}`}
        </span>
      </div>

      <svg viewBox={`0 0 ${width} ${mainHeight}`} className="h-56 w-full md:h-64" preserveAspectRatio="none">
        {stopLoss !== null && (
          <line
            x1="0" x2={width} y1={yPrice(stopLoss)} y2={yPrice(stopLoss)}
            stroke="var(--short)" strokeWidth="1" strokeDasharray="4 4"
          />
        )}
        {entryPrice !== null && (
          <line
            x1="0" x2={width} y1={yPrice(entryPrice)} y2={yPrice(entryPrice)}
            stroke="var(--long)" strokeWidth="1" strokeDasharray="4 4"
          />
        )}
        <polyline points={sma200Points} fill="none" stroke="#fbbf24" strokeWidth="1.5" strokeLinejoin="round" />
        <polyline points={sma5Points} fill="none" stroke="#38bdf8" strokeWidth="1.5" strokeLinejoin="round" />
        <polyline points={closeLine} fill="none" stroke="var(--foreground)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      </svg>

      <div className="mt-2 flex items-center justify-between text-[11px] text-muted-foreground">
        <span>RSI(2)</span>
        <span className="font-mono">10 / 90 參考線（&lt;10=深度超賣，進場門檻）</span>
      </div>
      <svg viewBox={`0 0 ${width} ${rsiHeight}`} className="h-20 w-full" preserveAspectRatio="none">
        <rect x="0" y={yRsi(10)} width={width} height={Math.max(yRsi(0) - yRsi(10), 0)} fill="var(--long)" opacity="0.08" />
        <line x1="0" x2={width} y1={yRsi(90)} y2={yRsi(90)} stroke="var(--border)" strokeWidth="1" strokeDasharray="3 3" />
        <line x1="0" x2={width} y1={yRsi(10)} y2={yRsi(10)} stroke="var(--long)" strokeWidth="1" strokeDasharray="3 3" />
        <polyline points={rsiLine} fill="none" stroke="#a78bfa" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      </svg>
    </div>
  )
}
