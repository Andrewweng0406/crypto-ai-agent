import { AlertTriangle } from "lucide-react"
import { type LiquidationWallData, formatCompactUsd, formatPrice, formatTime } from "@/lib/signals"

const AXIS_TICK_COUNT = 6
const SPOT_LINE_COLOR = "#ff8a00" // 跟GEX分佈牆同一套亮橘色，維持整站「現在」這個概念的視覺一致性

// 💥 幣圈爆倉密度清算牆：仿照 GEX 分佈牆的視覺規格——X軸是價格區間，Y軸是
// 該區間累積的爆倉淨額（綠=空頭爆倉燃料區，通常在現價上方，價格若衝上去
// 會觸發更多空單被強平、形成助漲燃料；紅=多頭強平真空區，通常在現價下方，
// 價格若跌下去會觸發更多多單被強平）。現貨價用同一套亮橘色呼吸發光線標示。
export function LiquidationHeatmapChart({ data }: { data: LiquidationWallData }) {
  if (!data.hasData || data.points.length === 0 || data.spotPrice === null) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-2 rounded-2xl border border-border/60 bg-card p-5 text-center text-sm text-muted-foreground md:h-80">
        尚未收到本機清算監聽回傳的資料，可能是 liquidation_listener.py 還沒開啟雲端回傳，或本機還在累積中
      </div>
    )
  }

  const { points, spotPrice } = data

  const width = 800
  const height = 320
  const padTop = 20
  const padBottom = 44
  const padLeft = 8
  const padRight = 8
  const plotH = height - padTop - padBottom
  const yZero = padTop + plotH / 2

  const buckets = points.map((p) => p.priceBucket)
  const allX = [...buckets, spotPrice]
  const minBucket = Math.min(...allX)
  const maxBucket = Math.max(...allX)
  const bucketRange = maxBucket - minBucket || 1
  const xPad = bucketRange * 0.04

  const x = (bucket: number) =>
    padLeft + ((bucket - (minBucket - xPad)) / (bucketRange + xPad * 2)) * (width - padLeft - padRight)

  const maxAbsNet = Math.max(...points.map((p) => Math.abs(p.netLiquidationUsd)), 1)
  const barScale = (plotH / 2) / maxAbsNet
  const barY = (net: number) => (net >= 0 ? yZero - net * barScale : yZero)
  const barH = (net: number) => Math.max(1, Math.abs(net) * barScale)

  const barWidth = (i: number) => {
    const leftGap = i > 0 ? buckets[i] - buckets[i - 1] : buckets[i + 1] - buckets[i]
    const rightGap = i < buckets.length - 1 ? buckets[i + 1] - buckets[i] : buckets[i] - buckets[i - 1]
    const gap = Math.min(leftGap, rightGap) || bucketRange / points.length
    return Math.max(2, (gap / (bucketRange + xPad * 2)) * (width - padLeft - padRight) * 0.72)
  }

  const axisTicks = Array.from(
    { length: AXIS_TICK_COUNT },
    (_, i) => (minBucket - xPad) + ((maxBucket + xPad - (minBucket - xPad)) * i) / (AXIS_TICK_COUNT - 1),
  )

  const spotX = x(spotPrice)
  const glowFilterId = `liq-spot-glow-${data.symbol}`

  const totalShort = points.filter((p) => p.netLiquidationUsd > 0).reduce((sum, p) => sum + p.netLiquidationUsd, 0)
  const totalLong = points.filter((p) => p.netLiquidationUsd < 0).reduce((sum, p) => sum + Math.abs(p.netLiquidationUsd), 0)

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-border/60 bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <h2 className="font-mono text-base font-semibold">{data.symbol} 爆倉密度清算牆</h2>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <span className="flex items-center gap-1.5 text-long">
            <span className="size-2.5 rounded-sm bg-long" aria-hidden="true" /> 空頭爆倉燃料區（上方阻力）
          </span>
          <span className="flex items-center gap-1.5 text-short">
            <span className="size-2.5 rounded-sm bg-short" aria-hidden="true" /> 多頭強平真空區（下方支撐）
          </span>
        </div>
      </div>

      <div className="relative w-full overflow-hidden rounded-xl bg-background/40">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="h-64 w-full md:h-80"
          preserveAspectRatio="none"
          role="img"
          aria-label={`${data.symbol} liquidation density by price bucket`}
        >
          <defs>
            <filter id={glowFilterId} x="-200%" y="-20%" width="500%" height="140%">
              <feGaussianBlur stdDeviation="4" result="blur" />
            </filter>
          </defs>

          <line x1="0" x2={width} y1={yZero} y2={yZero} stroke="var(--border)" strokeWidth="1" />

          {points.map((p, i) => (
            <rect
              key={p.priceBucket}
              x={x(p.priceBucket) - barWidth(i) / 2}
              y={barY(p.netLiquidationUsd)}
              width={barWidth(i)}
              height={barH(p.netLiquidationUsd)}
              fill={p.netLiquidationUsd >= 0 ? "var(--long)" : "var(--short)"}
              opacity="0.85"
              rx="1"
            >
              <title>{`$${formatPrice(p.priceBucket)} · 淨爆倉 ${formatCompactUsd(p.netLiquidationUsd)}`}</title>
            </rect>
          ))}

          {axisTicks.map((bucket, i) => (
            <text
              key={i}
              x={x(bucket)}
              y={height - padBottom + 20}
              // 頭尾兩個刻度改成往內對齊，避免寬數字（例如BTC的$63,184.51）
              // 用置中錨點時，文字有一半被畫到容器外面、被 overflow-hidden 切掉
              // （這個問題數字位數越多越明顯，短代號如GEX圖的$179.15不容易看出來，
              // 但邏輯上是同一個bug，這裡兩張圖一起修）。
              textAnchor={i === 0 ? "start" : i === axisTicks.length - 1 ? "end" : "middle"}
              className="font-mono"
              fontSize="10"
              fill="var(--muted-foreground)"
            >
              ${formatPrice(bucket)}
            </text>
          ))}

          {/* 現貨價：亮橘色發光核心線 + 模糊暈染層做呼吸脈衝，跟GEX分佈牆同一套視覺語言 */}
          <line
            x1={spotX}
            x2={spotX}
            y1={padTop}
            y2={height - padBottom}
            stroke={SPOT_LINE_COLOR}
            strokeWidth="6"
            opacity="0.45"
            filter={`url(#${glowFilterId})`}
            className="animate-gex-spot-pulse"
          />
          <line x1={spotX} x2={spotX} y1={padTop} y2={height - padBottom} stroke={SPOT_LINE_COLOR} strokeWidth="2" />
        </svg>

        <div
          className="pointer-events-none absolute -translate-x-1/2 whitespace-nowrap rounded-md border border-[#ff8a00]/50 bg-[#ff8a00]/15 px-2 py-0.5 font-mono text-[11px] font-semibold text-[#ff8a00] shadow-sm"
          style={{ left: `${(spotX / width) * 100}%`, top: 6 }}
        >
          現貨 ${formatPrice(spotPrice)}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1 rounded-xl border border-long/30 bg-long/[0.06] px-4 py-3">
          <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">空頭爆倉燃料（上方）</span>
          <span className="font-mono text-lg font-bold text-long">{formatCompactUsd(totalShort)}</span>
        </div>
        <div className="flex flex-col gap-1 rounded-xl border border-short/30 bg-short/[0.06] px-4 py-3">
          <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">多頭爆倉真空（下方）</span>
          <span className="font-mono text-lg font-bold text-short">{formatCompactUsd(totalLong)}</span>
        </div>
      </div>

      <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        資料是本機監聽開始運作後才累積的真實強平單，不是回推未平倉部位的理論清算價位——累積時間越長，密度圖越有參考價值。
        {data.updatedAt && ` 更新於 ${formatTime(data.updatedAt)}。`}
      </p>
    </div>
  )
}
