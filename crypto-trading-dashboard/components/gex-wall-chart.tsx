"use client"

import { useEffect, useRef } from "react"
import { ChevronLeft, ChevronRight, Crosshair } from "lucide-react"
import { type OptionsGexData, type OptionsGexPoint, formatCompactUsd, formatPrice, formatTime } from "@/lib/signals"

// 2026-07-16修復：原本X軸鎖死在現價前後±15%、看不到範圍外的履約價，只能靠邊緣
// 箭頭「知道」還有更遠的臨界點，卻沒辦法真的滑過去看。現在整條履約價都畫進同一張
// 夠寬的SVG裡，外層包一個可以左右捲動/拖曳的容器——密度（每塊錢多少像素）維持
// 跟原本±15%主戰區一樣的視覺比例，只是不再把範圍外的部分裁掉，改成捲動過去看。
// 進來一律先置中在現貨價，「回到現貨」／「跳到臨界點」兩個按鈕負責快速定位。
const REFERENCE_ZOOM_PCT = 0.15
const AXIS_TICK_TARGET_PX = 110 // 大約每隔這麼多像素放一個X軸刻度
const TOP_GEX_LABEL_COUNT = 3
const SPOT_LINE_COLOR = "#ff8a00" // 亮橘色，刻意跟 long(綠)/short(紅) 區隔，代表「現在」而非方向偏多空

export function GexWallChart({ data }: { data: OptionsGexData }) {
  const scrollRef = useRef<HTMLDivElement>(null)

  if (!data.hasData || data.points.length === 0 || data.spotPrice === null) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-2 rounded-2xl border border-border/60 bg-card p-5 text-center text-sm text-muted-foreground md:h-80">
        {data.hasData ? "此標的目前沒有可用的期權鏈資料" : "尚未拉到資料，可能是剛啟動還在拉第一輪，或美股非交易時段"}
      </div>
    )
  }

  const { points, spotPrice, gammaFlipStrike } = data

  const viewportWidth = 800
  const height = 320
  const padTop = 36 // 留給正GEX前三大柱的加粗履約價標籤
  const padBottom = 50 // 留給X軸履約價刻度
  const padSide = 24 // 兩端各留一點空間，捲到底時最外側那根柱子不會貼死邊緣
  const plotH = height - padTop - padBottom
  const yZero = padTop + plotH / 2

  const strikes = points.map((p) => p.strike)
  const domainMin = Math.min(...strikes, spotPrice)
  const domainMax = Math.max(...strikes, spotPrice)
  const domainRange = domainMax - domainMin || 1

  // 密度基準：沿用原本「現價±15%塞進一個800px主戰區」的視覺比例，整條履約價
  // 都用同一個比例畫，只是現在畫布本身會依範圍變寬，超出主戰區的部分用捲動看到。
  const pxPerUnit = (viewportWidth - padSide * 2) / (spotPrice * REFERENCE_ZOOM_PCT * 2)
  const svgWidth = Math.max(viewportWidth, pxPerUnit * domainRange + padSide * 2)

  const x = (strike: number) => padSide + (strike - domainMin) * pxPerUnit

  const maxAbsGex = Math.max(...points.map((p) => Math.abs(p.netGex)), 1)
  const barScale = plotH / 2 / maxAbsGex
  const barY = (netGex: number) => (netGex >= 0 ? yZero - netGex * barScale : yZero)
  const barH = (netGex: number) => Math.max(1, Math.abs(netGex) * barScale)

  const barWidth = (i: number) => {
    const leftGap = i > 0 ? strikes[i] - strikes[i - 1] : strikes[i + 1] - strikes[i]
    const rightGap = i < strikes.length - 1 ? strikes[i + 1] - strikes[i] : strikes[i] - strikes[i - 1]
    const gap = Math.min(leftGap, rightGap) || domainRange / points.length
    return Math.max(2, gap * pxPerUnit * 0.72)
  }

  // 全部履約價裡 Net GEX 絕對值前三大的柱子，強行加粗標註履約價，不用再盲猜
  // 哪根柱子對應哪個履約價（捲動範圍變大之後，這個提示更重要，能引導使用者
  // 往哪個方向捲）。
  const topGexStrikes = new Set(
    [...points]
      .sort((a, b) => Math.abs(b.netGex) - Math.abs(a.netGex))
      .slice(0, TOP_GEX_LABEL_COUNT)
      .map((p) => p.strike),
  )

  const tickCount = Math.max(2, Math.round(svgWidth / AXIS_TICK_TARGET_PX))
  const axisTicks = Array.from({ length: tickCount }, (_, i) => domainMin + (domainRange * i) / (tickCount - 1))

  const spotX = x(spotPrice)
  const flipX = gammaFlipStrike !== null ? x(gammaFlipStrike) : null

  const scrollToCenter = (centerX: number) => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTo({ left: Math.max(0, centerX - el.clientWidth / 2), behavior: "smooth" })
  }

  // 選標的/資料更新時，預設一律先把畫面對齊到現貨價（等同原本±15%主戰區的
  // 預設視角），使用者之後自己捲/拖曳到其他履約價再看。
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTo({ left: Math.max(0, spotX - el.clientWidth / 2), behavior: "auto" })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.symbol, data.spotPrice])

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
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => scrollToCenter(spotX)}
            className="flex items-center gap-1 rounded-md border border-border/60 bg-secondary/40 px-2 py-1 font-mono text-[11px] font-semibold text-muted-foreground transition-colors hover:text-foreground"
          >
            <Crosshair className="size-3" aria-hidden="true" />
            回到現貨
          </button>
          {flipX !== null && (
            <button
              type="button"
              onClick={() => scrollToCenter(flipX)}
              className="flex items-center gap-1 rounded-md border border-blue-400/40 bg-blue-400/10 px-2 py-1 font-mono text-[11px] font-semibold text-blue-400 transition-colors hover:bg-blue-400/20"
            >
              跳到臨界點
            </button>
          )}
          <div className="flex items-center gap-4 pl-2 text-xs">
            <span className="flex items-center gap-1.5 text-chart-bull">
              <span className="size-2.5 rounded-sm bg-chart-bull" aria-hidden="true" /> 正 GEX（call主導）
            </span>
            <span className="flex items-center gap-1.5 text-chart-bear">
              <span className="size-2.5 rounded-sm bg-chart-bear" aria-hidden="true" /> 負 GEX（put主導）
            </span>
          </div>
        </div>
      </div>

      <div className="relative">
        <div
          ref={scrollRef}
          className="scroll-smooth overflow-x-auto overscroll-x-contain rounded-xl bg-background/40"
          style={{ scrollbarWidth: "thin" }}
        >
          <svg
            viewBox={`0 0 ${svgWidth} ${height}`}
            width={svgWidth}
            height={height}
            className="block h-64 md:h-80"
            role="img"
            aria-label={`${data.symbol} Net GEX distribution by strike price，可左右捲動查看完整履約價範圍`}
          >
            <defs>
              <filter id={glowFilterId} x="-200%" y="-20%" width="500%" height="140%">
                <feGaussianBlur stdDeviation="4" result="blur" />
              </filter>
            </defs>

            {/* 零線 */}
            <line x1="0" x2={svgWidth} y1={yZero} y2={yZero} stroke="var(--border)" strokeWidth="1" />

            {/* GEX 柱狀 */}
            {points.map((p, i) => {
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
                textAnchor={i === 0 ? "start" : i === axisTicks.length - 1 ? "end" : "middle"}
                className="font-mono"
                fontSize="10"
                fill="var(--muted-foreground)"
              >
                ${formatPrice(strike)}
              </text>
            ))}

            {/* Gamma 擠壓臨界點 */}
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
        </div>

        {/* 左右提示箭頭：純粹視覺提示「這裡可以捲動」，不是互動元件本身
           （捲動容器本身才是，滑鼠拖曳/觸控滑動/shift+滾輪都能用）。 */}
        <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center rounded-l-xl bg-gradient-to-r from-card to-transparent pl-1 pr-4">
          <ChevronLeft className="size-4 text-muted-foreground/60" aria-hidden="true" />
        </div>
        <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center rounded-r-xl bg-gradient-to-l from-card to-transparent pr-1 pl-4">
          <ChevronRight className="size-4 text-muted-foreground/60" aria-hidden="true" />
        </div>
      </div>

      {gammaFlipStrike === null && (
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          此履約價區間內，累積 Net GEX 沒有出現正負轉折，目前抓不到明確的 Gamma 擠壓臨界點。
        </p>
      )}

      <p className="text-xs text-muted-foreground">
        現貨 ${formatPrice(spotPrice)}
        {gammaFlipStrike !== null && ` · Gamma 臨界點 $${formatPrice(gammaFlipStrike)}`}
        {data.updatedAt && ` · 更新於 ${formatTime(data.updatedAt)}`}
        {" · 可左右捲動／拖曳查看完整履約價範圍"}
      </p>
    </div>
  )
}
