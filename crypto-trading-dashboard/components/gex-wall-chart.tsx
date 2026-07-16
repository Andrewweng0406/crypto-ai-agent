import { AlertTriangle } from "lucide-react"
import { type OptionsGexData, type OptionsGexPoint, formatCompactUsd, formatPrice, formatTime } from "@/lib/signals"

// 主戰區縮放範圍：現價前後 ±15%。這個組件套用在期權分析頁全部5檔標的
// （NVDA/TSLA/SPY/SMCI/SPCX），不是針對單一標的的特例——選哪一檔都走同一份邏輯。
const ZOOM_PCT = 0.15
const AXIS_TICK_COUNT = 6
const TOP_GEX_LABEL_COUNT = 3
const SPOT_LINE_COLOR = "#ff8a00" // 亮橘色，刻意跟 long(綠)/short(紅) 區隔，代表「現在」而非方向偏多空

// GEX 剖面圖：x軸用「真實履約價數值」連續分佈（不是均分格子），這樣履約價
// 間距本身（近價平密、遠價外疏）就是圖上看得出來的資訊，跟專業 GEX 圖表
// 的慣例一致。正 Net GEX（call主導，理論上壓抑波動）畫在零線上方用long色，
// 負 Net GEX（put主導，理論上放大波動）畫在零線下方用short色。
//
// 主戰區縮放：X軸嚴格聚焦在現價±15%範圍內的履約價，這才是實際會被摸到、
// 值得盯的密集交易區——臨界點如果落在這個範圍外，不會被硬塞進主圖拉爆版面，
// 改用邊緣箭頭指標標示方向與距離。
export function GexWallChart({ data }: { data: OptionsGexData }) {
  if (!data.hasData || data.points.length === 0 || data.spotPrice === null) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-2 rounded-2xl border border-border/60 bg-card p-5 text-center text-sm text-muted-foreground md:h-80">
        {data.hasData ? "此標的目前沒有可用的期權鏈資料" : "尚未拉到資料，可能是剛啟動還在拉第一輪，或美股非交易時段"}
      </div>
    )
  }

  const { points, spotPrice, gammaFlipStrike } = data

  const width = 800
  const height = 320
  const padTop = 36 // 留給正GEX前三大柱的加粗履約價標籤
  const padBottom = 50 // 留給X軸履約價刻度
  const padLeft = 8
  const padRight = 8
  const plotH = height - padTop - padBottom
  const yZero = padTop + plotH / 2

  // 主戰區縮放：現價前後15%，取得到的履約價太少時（冷門標的、履約價間距本來
  // 就很寬）退回全部履約價，避免圖表直接開天窗。
  const zoomMin = spotPrice * (1 - ZOOM_PCT)
  const zoomMax = spotPrice * (1 + ZOOM_PCT)
  const zoomedPoints = points.filter((p) => p.strike >= zoomMin && p.strike <= zoomMax)
  const visiblePoints: OptionsGexPoint[] = zoomedPoints.length >= 2 ? zoomedPoints : points
  const isZoomed = zoomedPoints.length >= 2

  const visibleStrikes = visiblePoints.map((p) => p.strike)
  const domainMin = isZoomed ? zoomMin : Math.min(...visibleStrikes, spotPrice)
  const domainMax = isZoomed ? zoomMax : Math.max(...visibleStrikes, spotPrice)
  const domainRange = domainMax - domainMin || 1
  const xPad = domainRange * 0.04

  const x = (strike: number) =>
    padLeft + ((strike - (domainMin - xPad)) / (domainRange + xPad * 2)) * (width - padLeft - padRight)

  // 縮放後的柱狀高度用「目前看得到的這批履約價」自己的最大值來定比例尺，
  // 而不是全部履約價的最大值——這樣主戰區的柱子才會被撐好撐滿，不會因為
  // 遠處某根極端值把整組柱子都壓扁。
  const maxAbsGex = Math.max(...visiblePoints.map((p) => Math.abs(p.netGex)), 1)
  const barScale = (plotH / 2) / maxAbsGex
  const barY = (netGex: number) => (netGex >= 0 ? yZero - netGex * barScale : yZero)
  const barH = (netGex: number) => Math.max(1, Math.abs(netGex) * barScale)

  const barWidth = (i: number) => {
    const leftGap = i > 0 ? visibleStrikes[i] - visibleStrikes[i - 1] : visibleStrikes[i + 1] - visibleStrikes[i]
    const rightGap =
      i < visibleStrikes.length - 1 ? visibleStrikes[i + 1] - visibleStrikes[i] : visibleStrikes[i] - visibleStrikes[i - 1]
    const gap = Math.min(leftGap, rightGap) || domainRange / visiblePoints.length
    return Math.max(2, (gap / (domainRange + xPad * 2)) * (width - padLeft - padRight) * 0.72)
  }

  // 全場（縮放後可見範圍內）Net GEX 絕對值前三大的柱子，強行加粗標註履約價，
  // 不用再盲猜哪根柱子對應哪個履約價。
  const topGexStrikes = new Set(
    [...visiblePoints]
      .sort((a, b) => Math.abs(b.netGex) - Math.abs(a.netGex))
      .slice(0, TOP_GEX_LABEL_COUNT)
      .map((p) => p.strike),
  )

  // X軸履約價刻度：均勻切6個點，不是硬對齊到真實履約價——履約價分佈本來就
  // 疏密不均，均勻切點才能穩定標出「現在畫面涵蓋的價格範圍」。
  const axisTicks = Array.from(
    { length: AXIS_TICK_COUNT },
    (_, i) => domainMin + ((domainMax - domainMin) * i) / (AXIS_TICK_COUNT - 1),
  )

  const spotX = x(spotPrice)
  const flipInRange = gammaFlipStrike !== null && gammaFlipStrike >= domainMin && gammaFlipStrike <= domainMax
  const flipX = flipInRange ? x(gammaFlipStrike as number) : null
  const flipOutOfRange = gammaFlipStrike !== null && !flipInRange
  const flipEdgeSide: "left" | "right" | null = flipOutOfRange
    ? (gammaFlipStrike as number) < domainMin
      ? "left"
      : "right"
    : null

  const glowFilterId = `gex-spot-glow-${data.symbol}`

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-border/60 bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <h2 className="font-mono text-base font-semibold">{data.symbol} GEX 分佈牆</h2>
          {data.expiry && (
            <span className="rounded-md bg-secondary px-2 py-0.5 font-mono text-xs text-muted-foreground">
              到期 {data.expiry}
            </span>
          )}
          {isZoomed && (
            <span className="rounded-md bg-secondary px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
              主戰區 ±{Math.round(ZOOM_PCT * 100)}%
            </span>
          )}
        </div>
        <div className="flex items-center gap-4 text-xs">
          <span className="flex items-center gap-1.5 text-chart-bull">
            <span className="size-2.5 rounded-sm bg-chart-bull" aria-hidden="true" /> 正 GEX（call主導）
          </span>
          <span className="flex items-center gap-1.5 text-chart-bear">
            <span className="size-2.5 rounded-sm bg-chart-bear" aria-hidden="true" /> 負 GEX（put主導）
          </span>
        </div>
      </div>

      <div className="relative w-full overflow-hidden rounded-xl bg-background/40">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="h-64 w-full md:h-80"
          preserveAspectRatio="none"
          role="img"
          aria-label={`${data.symbol} Net GEX distribution by strike price`}
        >
          <defs>
            <filter id={glowFilterId} x="-200%" y="-20%" width="500%" height="140%">
              <feGaussianBlur stdDeviation="4" result="blur" />
            </filter>
          </defs>

          {/* 零線 */}
          <line x1="0" x2={width} y1={yZero} y2={yZero} stroke="var(--border)" strokeWidth="1" />

          {/* GEX 柱狀 */}
          {visiblePoints.map((p, i) => {
            const isTop = topGexStrikes.has(p.strike)
            const top = barY(p.netGex)
            const bottom = top + barH(p.netGex)
            const cx = x(p.strike)
            const labelY = p.netGex >= 0 ? Math.max(top - 8, padTop - 12) : Math.min(bottom + 16, height - padBottom - 4)
            const labelText = `$${formatPrice(p.strike)}`
            const labelBoxWidth = labelText.length * 6.6 + 10

            return (
              <g key={p.strike}>
                <rect
                  x={cx - barWidth(i) / 2}
                  y={top}
                  width={barWidth(i)}
                  height={barH(p.netGex)}
                  fill={p.netGex >= 0 ? "var(--chart-bull)" : "var(--chart-bear)"}
                  opacity={isTop ? 1 : 0.78}
                  stroke={isTop ? (p.netGex >= 0 ? "var(--chart-bull)" : "var(--chart-bear)") : "none"}
                  strokeWidth={isTop ? 1.5 : 0}
                  rx="1"
                >
                  <title>{`Strike $${formatPrice(p.strike)} · Net GEX ${formatCompactUsd(p.netGex)}`}</title>
                </rect>

                {isTop && (
                  <g>
                    <rect
                      x={cx - labelBoxWidth / 2}
                      y={labelY - 13}
                      width={labelBoxWidth}
                      height="16"
                      rx="3"
                      fill="var(--popover)"
                      stroke={p.netGex >= 0 ? "var(--chart-bull)" : "var(--chart-bear)"}
                      strokeWidth="1"
                    />
                    <text
                      x={cx}
                      y={labelY - 2}
                      textAnchor="middle"
                      className="font-mono"
                      fontSize="11"
                      fontWeight="700"
                      fill={p.netGex >= 0 ? "var(--chart-bull)" : "var(--chart-bear)"}
                    >
                      {labelText}
                    </text>
                  </g>
                )}
              </g>
            )
          })}

          {/* X軸履約價刻度 */}
          {axisTicks.map((strike, i) => (
            <text
              key={i}
              x={x(strike)}
              y={height - padBottom + 20}
              // 頭尾兩個刻度往內對齊，避免寬數字用置中錨點時被容器的
              // overflow-hidden切掉左/右半邊文字（見清算牆同一段註解）。
              textAnchor={i === 0 ? "start" : i === axisTicks.length - 1 ? "end" : "middle"}
              className="font-mono"
              fontSize="10"
              fill="var(--muted-foreground)"
            >
              ${formatPrice(strike)}
            </text>
          ))}

          {/* Gamma 擠壓臨界點（只在主戰區範圍內才畫進主圖，範圍外改用邊緣箭頭） */}
          {flipX !== null && (
            <line x1={flipX} x2={flipX} y1={padTop} y2={height - padBottom} stroke="#60a5fa" strokeWidth="1.5" strokeDasharray="5 4" />
          )}

          {/* 現貨價：亮橘色發光核心線 + 模糊暈染層做呼吸脈衝 */}
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

        {flipX !== null && (
          <ChartTag x={flipX} width={width} label={`⚡ 臨界點 $${formatPrice(gammaFlipStrike as number)}`} tone="flip" />
        )}
        {flipEdgeSide !== null && (
          <EdgeTag side={flipEdgeSide} label={`臨界點 $${formatPrice(gammaFlipStrike as number)}`} />
        )}
        <ChartTag x={spotX} width={width} label={`現貨 $${formatPrice(spotPrice)}`} tone="spot" bottom />
      </div>

      {gammaFlipStrike === null && (
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          此履約價區間內，累積 Net GEX 沒有出現正負轉折，目前抓不到明確的 Gamma 擠壓臨界點。
        </p>
      )}

      {flipOutOfRange && (
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          Gamma 臨界點距離現價超過 {Math.round(ZOOM_PCT * 100)}%，已移出主戰區顯示範圍，改用邊緣箭頭標示方向。
        </p>
      )}

      <p className="text-xs text-muted-foreground">
        現貨 ${formatPrice(spotPrice)}
        {gammaFlipStrike !== null && ` · Gamma 臨界點 $${formatPrice(gammaFlipStrike)}`}
        {data.updatedAt && ` · 更新於 ${formatTime(data.updatedAt)}`}
      </p>
    </div>
  )
}

function ChartTag({
  x,
  width,
  label,
  tone,
  bottom,
}: {
  x: number
  width: number
  label: string
  tone: "spot" | "flip"
  bottom?: boolean
}) {
  const leftPct = (x / width) * 100
  return (
    <div
      className={
        "pointer-events-none absolute -translate-x-1/2 whitespace-nowrap rounded-md border px-2 py-0.5 font-mono text-[11px] font-semibold shadow-sm " +
        (tone === "flip"
          ? "border-blue-400/40 bg-blue-400/15 text-blue-400"
          : "border-[#ff8a00]/50 bg-[#ff8a00]/15 text-[#ff8a00]")
      }
      style={{ left: `${leftPct}%`, [bottom ? "bottom" : "top"]: 6 }}
    >
      {label}
    </div>
  )
}

// 臨界點離現價太遠、被移出主戰區縮放範圍時，用畫面邊緣的箭頭指標取代——
// 讓使用者知道「往哪個方向、多遠處」還有一個臨界點，但不犧牲主戰區的縮放比例。
function EdgeTag({ side, label }: { side: "left" | "right"; label: string }) {
  return (
    <div
      className={
        "pointer-events-none absolute top-1/2 -translate-y-1/2 whitespace-nowrap rounded-md border border-blue-400/40 bg-blue-400/15 px-2 py-0.5 font-mono text-[11px] font-semibold text-blue-400 shadow-sm " +
        (side === "left" ? "left-1.5" : "right-1.5")
      }
    >
      {side === "left" ? `← ${label}` : `${label} →`}
    </div>
  )
}
