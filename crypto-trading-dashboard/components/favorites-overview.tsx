"use client"

import { Star } from "lucide-react"
import { cn } from "@/lib/utils"
import { type OptionsGexData, type USStockSignalState, formatPrice } from "@/lib/signals"

interface FavoritesOverviewProps {
  optionsUnderlyings: OptionsGexData[]
  optionsLoading: boolean
  usStocks: USStockSignalState[]
  usStocksLoading: boolean
  onSelectOptions: (symbol: string) => void
  onSelectUSStock: (symbol: string) => void
}

// ⭐ 我的關注：把期權分析＋美股ORB兩個模塊各自的自選清單彙整在一起的總覽頁，
// 純粹是「一眼掃過去」的快照卡片，不是完整功能——點卡片會跳去對應分頁看細節
// （GEX剖面圖、開盤區間監控等）。兩邊自選清單的增刪都在各自分頁內完成，這裡
// 只讀不編輯，維持這頁單純。
export function FavoritesOverview({
  optionsUnderlyings,
  optionsLoading,
  usStocks,
  usStocksLoading,
  onSelectOptions,
  onSelectUSStock,
}: FavoritesOverviewProps) {
  const isEmpty = optionsUnderlyings.length === 0 && usStocks.length === 0 && !optionsLoading && !usStocksLoading

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Star className="size-4 text-amber-400" aria-hidden="true" />
        彙整「📊 期權分析」與「美股 ORB」兩個模塊目前的自選清單，點卡片可跳去該分頁看完整細節；
        新增／移除標的請到各自分頁的搜尋框操作。
      </div>

      {isEmpty && (
        <div className="rounded-2xl border border-dashed border-border/60 bg-card/40 p-8 text-center text-sm text-muted-foreground">
          目前兩個模塊的自選清單都是空的，去「📊 期權分析」或「美股 ORB」分頁加幾檔標的吧。
        </div>
      )}

      {(optionsUnderlyings.length > 0 || optionsLoading) && (
        <section className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">📊 期權分析</h3>
          <div className="flex flex-wrap gap-3">
            {optionsUnderlyings.map((u) => (
              <button
                key={u.symbol}
                type="button"
                onClick={() => onSelectOptions(u.symbol)}
                className="flex min-w-[160px] flex-1 flex-col gap-1 rounded-xl border border-border/60 bg-card px-4 py-3 text-left transition-colors hover:border-primary/60 hover:bg-primary/[0.06]"
              >
                <span className="font-mono text-sm font-semibold">{u.symbol}</span>
                <span className="font-mono text-lg font-bold">
                  {u.spotPrice !== null ? `$${formatPrice(u.spotPrice)}` : "—"}
                </span>
                <span className="text-[11px] text-muted-foreground">
                  {u.hasData
                    ? u.gammaFlipStrike !== null
                      ? `臨界點 $${formatPrice(u.gammaFlipStrike)}`
                      : "無明顯臨界點"
                    : "載入中…"}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      {(usStocks.length > 0 || usStocksLoading) && (
        <section className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">美股 ORB</h3>
          <div className="flex flex-wrap gap-3">
            {usStocks.map((s) => {
              const isOpen = s.status === "OPEN" && s.signal
              const change = s.orbMonitoring.dayChangePct
              return (
                <button
                  key={s.symbol}
                  type="button"
                  onClick={() => onSelectUSStock(s.symbol)}
                  className="flex min-w-[160px] flex-1 flex-col gap-1.5 rounded-xl border border-border/60 bg-card px-4 py-3 text-left transition-colors hover:border-primary/60 hover:bg-primary/[0.06]"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-sm font-semibold">{s.displayName}</span>
                    {isOpen ? (
                      <span
                        className={cn(
                          "rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase",
                          s.signal!.side === "Long" ? "bg-long/15 text-long" : "bg-short/15 text-short",
                        )}
                      >
                        {s.signal!.side} {s.signal!.leverage}x
                      </span>
                    ) : (
                      <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px] font-semibold uppercase text-muted-foreground">
                        No Signal
                      </span>
                    )}
                  </div>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-mono text-lg font-bold">
                      {s.currentPrice !== null ? `$${formatPrice(s.currentPrice)}` : "—"}
                    </span>
                    {change !== null && (
                      <span className={cn("font-mono text-xs font-semibold", change >= 0 ? "text-long" : "text-short")}>
                        {change >= 0 ? "+" : ""}
                        {change.toFixed(2)}%
                      </span>
                    )}
                  </div>
                </button>
              )
            })}
          </div>
        </section>
      )}
    </div>
  )
}
