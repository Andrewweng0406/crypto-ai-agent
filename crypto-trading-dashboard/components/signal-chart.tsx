"use client"

import useSWR from "swr"
import { cn } from "@/lib/utils"
import { type BackendCandlesResponse, type Signal, adaptCandles, formatPrice } from "@/lib/signals"

const fetcher = (url: string) =>
  fetch(url).then(async (r) => {
    const body = await r.json()
    if (!r.ok) throw new Error(body?.detail ?? `Request failed (${r.status})`)
    return body
  })

export function SignalChart({ signal }: { signal: Signal }) {
  const isLong = signal.side === "Long"

  // Real OHLCV from the same backend the strategy itself scans — this used to
  // be a deterministic pseudo-random walk purely for decoration; TP/SL/current
  // price lines were always real, the candles behind them were not.
  const {
    data: rawCandles,
    error,
    isLoading,
  } = useSWR<BackendCandlesResponse>(`/api/candles?symbol=${encodeURIComponent(signal.symbol)}&limit=60`, fetcher, {
    refreshInterval: 60_000,
  })

  const candles = rawCandles ? adaptCandles(rawCandles) : []
  const timeframeLabel = rawCandles?.timeframe ?? ""

  if (candles.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-2 rounded-2xl border border-border/60 bg-card p-5 text-center text-sm text-muted-foreground md:h-80">
        {error ? `K線載入失敗：${error.message}` : isLoading ? "載入K線中…" : "暫無K線資料"}
      </div>
    )
  }

  const width = 800
  const height = 320
  const padTop = 16
  const padBottom = 16

  const values = candles.flatMap((c) => [c.h, c.l]).concat([signal.tp, signal.sl, signal.current_price])
  const max = Math.max(...values)
  const min = Math.min(...values)
  const range = max - min || 1
  const pad = range * 0.08

  const y = (price: number) =>
    padTop + ((max + pad - price) / (range + pad * 2)) * (height - padTop - padBottom)

  const slotW = width / candles.length
  const bodyW = slotW * 0.58

  const tpY = y(signal.tp)
  const slY = y(signal.sl)
  const curY = y(signal.current_price)

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-border/60 bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <h2 className="font-mono text-base font-semibold">{signal.symbol}</h2>
          {timeframeLabel && (
            <span className="rounded-md bg-secondary px-2 py-0.5 font-mono text-xs text-muted-foreground">
              {timeframeLabel}
            </span>
          )}
        </div>
        <div className="flex items-center gap-4 text-xs">
          <span className="flex items-center gap-1.5 text-long">
            <span className="h-0.5 w-4 border-t-2 border-dashed border-long" aria-hidden="true" /> TP
          </span>
          <span className="flex items-center gap-1.5 text-short">
            <span className="h-0.5 w-4 border-t-2 border-dashed border-short" aria-hidden="true" /> SL
          </span>
        </div>
      </div>

      <div className="relative w-full overflow-hidden rounded-xl bg-background/40">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="h-64 w-full md:h-80"
          preserveAspectRatio="none"
          role="img"
          aria-label={`Candlestick chart for ${signal.symbol} with take profit and stop loss levels`}
        >
          <defs>
            <linearGradient id="tpFill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="var(--long)" stopOpacity="0.12" />
              <stop offset="100%" stopColor="var(--long)" stopOpacity="0" />
            </linearGradient>
            <linearGradient id="slFill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="var(--short)" stopOpacity="0" />
              <stop offset="100%" stopColor="var(--short)" stopOpacity="0.12" />
            </linearGradient>
          </defs>

          {/* Target / stop shaded zones. For a Long, TP sits above SL (smaller
              y), so the "beyond target" zone is the top of the chart down to
              the TP line. For a Short, TP is the lower price (larger y), so
              the zone flips to the bottom of the chart up to the TP line —
              hence branching on which line actually has the smaller y. */}
          {tpY < slY ? (
            <>
              <rect x="0" y="0" width={width} height={tpY} fill="url(#tpFill)" />
              <rect x="0" y={slY} width={width} height={height - slY} fill="url(#slFill)" />
            </>
          ) : (
            <>
              <rect x="0" y={tpY} width={width} height={height - tpY} fill="url(#tpFill)" />
              <rect x="0" y="0" width={width} height={slY} fill="url(#slFill)" />
            </>
          )}

          {/* Candles */}
          {candles.map((c, i) => {
            const cx = i * slotW + slotW / 2
            const up = c.c >= c.o
            const color = up ? "var(--long)" : "var(--short)"
            const bodyTop = y(Math.max(c.o, c.c))
            const bodyBottom = y(Math.min(c.o, c.c))
            const bodyH = Math.max(1, bodyBottom - bodyTop)
            return (
              <g key={c.timestamp}>
                <line x1={cx} x2={cx} y1={y(c.h)} y2={y(c.l)} stroke={color} strokeWidth="1" opacity="0.85" />
                <rect
                  x={cx - bodyW / 2}
                  y={bodyTop}
                  width={bodyW}
                  height={bodyH}
                  fill={color}
                  rx="0.5"
                  opacity="0.9"
                />
              </g>
            )
          })}

          {/* TP line */}
          <line x1="0" x2={width} y1={tpY} y2={tpY} stroke="var(--long)" strokeWidth="1.5" strokeDasharray="6 5" />
          {/* SL line */}
          <line x1="0" x2={width} y1={slY} y2={slY} stroke="var(--short)" strokeWidth="1.5" strokeDasharray="6 5" />
          {/* Current price line */}
          <line
            x1="0"
            x2={width}
            y1={curY}
            y2={curY}
            stroke="var(--foreground)"
            strokeWidth="1"
            strokeDasharray="2 4"
            opacity="0.55"
          />
        </svg>

        {/* Price tags overlaid with HTML for crisp text */}
        <PriceTag y={tpY} height={height} label={`TP ${formatPrice(signal.tp)}`} tone="long" />
        <PriceTag y={slY} height={height} label={`SL ${formatPrice(signal.sl)}`} tone="short" />
        <PriceTag
          y={curY}
          height={height}
          label={formatPrice(signal.current_price)}
          tone={isLong ? "neutral" : "neutral"}
        />
      </div>
    </div>
  )
}

function PriceTag({
  y,
  height,
  label,
  tone,
}: {
  y: number
  height: number
  label: string
  tone: "long" | "short" | "neutral"
}) {
  const topPct = (y / height) * 100
  return (
    <div
      className={cn(
        "pointer-events-none absolute right-2 -translate-y-1/2 rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold shadow-sm",
        tone === "long" && "bg-long text-long-foreground",
        tone === "short" && "bg-short text-short-foreground",
        tone === "neutral" && "border border-border bg-popover text-foreground",
      )}
      style={{ top: `${topPct}%` }}
    >
      {label}
    </div>
  )
}
