import { AlertTriangle } from "lucide-react"
import { type OptionsGexData, formatCompactUsd, formatPrice, formatTime } from "@/lib/signals"

// GEX 剖面圖：x軸用「真實履約價數值」連續分佈（不是均分格子），這樣履約價
// 間距本身（近價平密、遠價外疏）就是圖上看得出來的資訊，跟專業 GEX 圖表
// 的慣例一致。正 Net GEX（call主導，理論上壓抑波動）畫在零線上方用long色，
// 負 Net GEX（put主導，理論上放大波動）畫在零線下方用short色。
export function GexWallChart({ data }: { data: OptionsGexData }) {
  if (!data.hasData || data.points.length === 0 || data.spotPrice === null) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-2 rounded-2xl border border-border/60 bg-card p-5 text-center text-sm text-muted-foreground md:h-80">
        {data.hasData ? "此標的目前沒有可用的期權鏈資料" : "尚未連線 Moomoo OpenD 或還沒拉到資料"}
      </div>
    )
  }

  const { points, spotPrice, gammaFlipStrike } = data

  const width = 800
  const height = 320
  const padTop = 20
  const padBottom = 28
  const padLeft = 8
  const padRight = 8
  const plotH = height - padTop - padBottom

  const strikes = points.map((p) => p.strike)
  const allX = [...strikes, spotPrice, ...(gammaFlipStrike !== null ? [gammaFlipStrike] : [])]
  const minStrike = Math.min(...allX)
  const maxStrike = Math.max(...allX)
  const strikeRange = maxStrike - minStrike || 1
  const xPad = strikeRange * 0.04

  const x = (strike: number) =>
    padLeft + ((strike - (minStrike - xPad)) / (strikeRange + xPad * 2)) * (width - padLeft - padRight)

  const maxAbsGex = Math.max(...points.map((p) => Math.abs(p.netGex)), 1)
  const yZero = padTop + plotH / 2
  const barScale = (plotH / 2) / maxAbsGex
  const barY = (netGex: number) => (netGex >= 0 ? yZero - netGex * barScale : yZero)
  const barH = (netGex: number) => Math.max(1, Math.abs(netGex) * barScale)

  // 每根柱子的寬度取「跟左右鄰居距離的較小值」的一部分，避免柱子互相重疊，
  // 邊界的第一根/最後一根沒有對應方向的鄰居時，就退回用另一側的間距。
  const barWidth = (i: number) => {
    const leftGap = i > 0 ? strikes[i] - strikes[i - 1] : strikes[i + 1] - strikes[i]
    const rightGap = i < strikes.length - 1 ? strikes[i + 1] - strikes[i] : strikes[i] - strikes[i - 1]
    const gap = Math.min(leftGap, rightGap) || strikeRange / points.length
    return Math.max(2, (gap / (strikeRange + xPad * 2)) * (width - padLeft - padRight) * 0.72)
  }

  const spotX = x(spotPrice)
  const flipX = gammaFlipStrike !== null ? x(gammaFlipStrike) : null

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
        <div className="flex items-center gap-4 text-xs">
          <span className="flex items-center gap-1.5 text-long">
            <span className="size-2.5 rounded-sm bg-long" aria-hidden="true" /> 正 GEX（call主導）
          </span>
          <span className="flex items-center gap-1.5 text-short">
            <span className="size-2.5 rounded-sm bg-short" aria-hidden="true" /> 負 GEX（put主導）
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
          {/* 零線 */}
          <line x1="0" x2={width} y1={yZero} y2={yZero} stroke="var(--border)" strokeWidth="1" />

          {/* GEX 柱狀 */}
          {points.map((p, i) => (
            <rect
              key={p.strike}
              x={x(p.strike) - barWidth(i) / 2}
              y={barY(p.netGex)}
              width={barWidth(i)}
              height={barH(p.netGex)}
              fill={p.netGex >= 0 ? "var(--long)" : "var(--short)"}
              opacity="0.88"
              rx="1"
            >
              <title>{`Strike $${formatPrice(p.strike)} · Net GEX ${formatCompactUsd(p.netGex)}`}</title>
            </rect>
          ))}

          {/* Gamma 擠壓臨界點 */}
          {flipX !== null && (
            <line x1={flipX} x2={flipX} y1={padTop} y2={height - padBottom} stroke="#60a5fa" strokeWidth="1.5" strokeDasharray="5 4" />
          )}

          {/* 現貨價 */}
          <line x1={spotX} x2={spotX} y1={padTop} y2={height - padBottom} stroke="var(--foreground)" strokeWidth="1.5" strokeDasharray="2 3" opacity="0.7" />
        </svg>

        {flipX !== null && (
          <ChartTag x={flipX} width={width} label={`⚡ 臨界點 $${formatPrice(gammaFlipStrike as number)}`} tone="flip" />
        )}
        <ChartTag x={spotX} width={width} label={`現貨 $${formatPrice(spotPrice)}`} tone="spot" bottom />
      </div>

      {gammaFlipStrike === null && (
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          此履約價區間內，累積 Net GEX 沒有出現正負轉折，目前抓不到明確的 Gamma 擠壓臨界點。
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
          : "border-border bg-popover text-foreground")
      }
      style={{ left: `${leftPct}%`, [bottom ? "bottom" : "top"]: 6 }}
    >
      {label}
    </div>
  )
}
