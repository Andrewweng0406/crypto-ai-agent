"use client"

import { useEffect, useState } from "react"
import { type OptionsGexData, type WhaleSweepItem, formatPrice } from "@/lib/signals"
import { GexWallChart } from "@/components/gex-wall-chart"
import { WhaleSweepStream } from "@/components/whale-sweep-stream"

interface OptionsAnalyticsPanelProps {
  underlyings: OptionsGexData[]
  whaleSweepItems: WhaleSweepItem[]
  dataSourceOk: boolean
  isLoading: boolean
  whaleSweepLoading: boolean
}

export function OptionsAnalyticsPanel({
  underlyings,
  whaleSweepItems,
  dataSourceOk,
  isLoading,
  whaleSweepLoading,
}: OptionsAnalyticsPanelProps) {
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)

  useEffect(() => {
    if (underlyings.length === 0) {
      setSelectedSymbol(null)
      return
    }
    const stillPresent = underlyings.some((u) => u.symbol === selectedSymbol)
    if (!stillPresent) {
      setSelectedSymbol(underlyings[0].symbol)
    }
  }, [underlyings, selectedSymbol])

  const selected = underlyings.find((u) => u.symbol === selectedSymbol) ?? null

  return (
    <div className="flex flex-col gap-4">
      <div
        className={
          "flex items-center gap-2 rounded-xl border px-4 py-2.5 text-xs " +
          (dataSourceOk
            ? "border-border/60 bg-card/60 text-muted-foreground"
            : "border-short/30 bg-short/[0.06] text-short")
        }
      >
        <span className={`size-1.5 rounded-full ${dataSourceOk ? "bg-long" : "bg-short"}`} aria-hidden="true" />
        資料來源：{dataSourceOk ? "正常" : "暫無資料"}
        {!dataSourceOk && "（美股非交易時段沒有新資料，或剛啟動還在拉第一輪）"}
      </div>

      <div className="flex flex-wrap gap-3">
        {underlyings.map((u) => {
          const isSelected = u.symbol === selectedSymbol
          return (
            <button
              key={u.symbol}
              type="button"
              onClick={() => setSelectedSymbol(u.symbol)}
              className={
                "flex min-w-[140px] flex-1 flex-col gap-1 rounded-xl border px-4 py-3 text-left transition-colors " +
                (isSelected
                  ? "border-primary/60 bg-primary/[0.08]"
                  : "border-border/60 bg-card hover:bg-secondary/40")
              }
            >
              <span className="font-mono text-sm font-semibold">{u.symbol}</span>
              <span className="font-mono text-lg font-bold">
                {u.spotPrice !== null ? `$${formatPrice(u.spotPrice)}` : "—"}
              </span>
              <span className="text-[11px] text-muted-foreground">
                {u.hasData ? (u.gammaFlipStrike !== null ? `臨界點 $${formatPrice(u.gammaFlipStrike)}` : "無明顯臨界點") : "載入中…"}
              </span>
            </button>
          )
        })}
      </div>

      {selected ? (
        <GexWallChart data={selected} />
      ) : (
        <div className="flex h-64 flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-border/60 bg-card/40 p-8 text-center text-sm text-muted-foreground md:h-80">
          {isLoading ? "載入期權分析中…" : "選一檔標的查看 GEX 分佈牆"}
        </div>
      )}

      <WhaleSweepStream
        items={selected ? whaleSweepItems.filter((item) => item.symbol === selected.symbol) : whaleSweepItems}
        isLoading={whaleSweepLoading}
        whaleSweepSupported={selected?.whaleSweepSupported ?? null}
      />
    </div>
  )
}
