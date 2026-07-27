"use client"

import useSWR from "swr"
import { type BackendCandlesResponse, adaptCandles, formatPrice } from "@/lib/signals"

const fetcher = (url: string) =>
  fetch(url).then(async (r) => {
    const body = await r.json()
    if (!r.ok) throw new Error(body?.detail ?? `Request failed (${r.status})`)
    return body
  })

// 🕯️ 個股總覽頁的K線圖：2026-07-27新增，補上「個股總覽」原本只有數字沒有
// 價格走勢視覺化的缺口（RSI2那4檔本來就有RSI2TechnicalChart，其餘標的
// 沒有）。資料源是 /api/us-stock/candles（yfinance日線），跟GEX分佈牆分開
// 畫成兩張獨立的圖，不是疊在同一張SVG裡——GEX牆本身已經是一個複雜元件，
// 硬把K線疊進去風險較高，兩張圖並排看一樣能達到「一次看完全貌」的效果。
export function UsStockCandlesChart({ symbol }: { symbol: string }) {
  const { data: rawCandles, error, isLoading } = useSWR<BackendCandlesResponse>(
    `/api/us-stock/candles?symbol=${symbol}&timeframe=1d&limit=60`,
    fetcher,
    { refreshInterval: 60000 },
  )

  const candles = rawCandles ? adaptCandles(rawCandles) : []

  if (candles.length === 0) {
    return (
      <div className="flex h-56 flex-col items-center justify-center gap-2 rounded-2xl border border-border/60 bg-card p-5 text-center text-sm text-muted-foreground">
        {error ? `K線載入失敗：${error.message}` : isLoading ? "載入K線中…" : "暫無K線資料"}
      </div>
    )
  }

  const W = 900, H = 220, padL = 46, padR = 12, padTop = 10, padBottom = 20
  const plotW = W - padL - padR, plotH = H - padTop - padBottom

  const highs = candles.map((c) => c.h)
  const lows = candles.map((c) => c.l)
  const pMin = Math.min(...lows), pMax = Math.max(...highs)
  const pRange = pMax - pMin || 1
  const yAt = (p: number) => padTop + ((pMax - p) / pRange) * plotH

  const cw = plotW / candles.length
  const xAt = (i: number) => padL + i * cw + cw / 2

  const yTicks = [pMin, pMin + pRange * 0.5, pMax]
  const last = candles[candles.length - 1]
  const first = candles[0]
  const changePct = ((last.c - first.c) / first.c) * 100

  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-border/60 bg-card p-5">
      <div className="flex items-center justify-between text-xs">
        <span className="font-mono text-sm font-semibold text-foreground">{symbol} 日線（近{candles.length}個交易日）</span>
        <span className="font-mono text-muted-foreground">
          最新收盤 ${formatPrice(last.c)}
          <span className={changePct >= 0 ? "ml-2 text-long" : "ml-2 text-short"}>
            {changePct >= 0 ? "+" : ""}{changePct.toFixed(1)}%（區間）
          </span>
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-56 w-full" role="img" aria-label={`${symbol} 日線K線圖`}>
        {yTicks.map((p, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={yAt(p)} y2={yAt(p)} stroke="var(--border)" strokeWidth={1} />
            <text x={padL - 6} y={yAt(p) + 3} textAnchor="end" fontSize={9} fontFamily="var(--font-mono, monospace)" fill="var(--muted-foreground)">
              ${p.toFixed(0)}
            </text>
          </g>
        ))}
        {candles.map((c, i) => {
          const x = xAt(i)
          const up = c.c >= c.o
          const color = up ? "var(--long)" : "var(--short)"
          const bodyTop = yAt(Math.max(c.o, c.c))
          const bodyBottom = yAt(Math.min(c.o, c.c))
          return (
            <g key={c.timestamp}>
              <line x1={x} x2={x} y1={yAt(c.h)} y2={yAt(c.l)} stroke={color} strokeWidth={1.2} />
              <rect x={x - cw * 0.3} y={bodyTop} width={cw * 0.6} height={Math.max(1.2, bodyBottom - bodyTop)} fill={color} rx={0.5} />
            </g>
          )
        })}
      </svg>
    </div>
  )
}
