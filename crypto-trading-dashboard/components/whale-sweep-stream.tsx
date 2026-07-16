"use client"

import { useMemo, useState } from "react"
import { Fish } from "lucide-react"
import { type WhaleSweepItem, formatClockTime, formatCompactUsd, formatPrice } from "@/lib/signals"

function shortSymbol(symbol: string): string {
  return symbol.replace("/USDT", "").replace(":USDT", "")
}

// Gemini建議④：深價內/深價外的大單（|delta|接近1或接近0）多半是避險/套利盤或
// 極端下注，不太代表方向性看法；|delta|落在這個範圍內才比較接近「真的在賭
// 方向」的標準單。門檻本身沒有標準答案，先用建議值，之後想調再說。
const DIRECTIONAL_DELTA_MIN = 0.15
const DIRECTIONAL_DELTA_MAX = 0.85

function isDirectional(delta: number | null): boolean {
  if (delta === null) return false
  const abs = Math.abs(delta)
  return abs >= DIRECTIONAL_DELTA_MIN && abs <= DIRECTIONAL_DELTA_MAX
}

interface WhaleSweepStreamProps {
  items: WhaleSweepItem[]
  isLoading: boolean
  whaleSweepSupported: boolean | null
}

// 期權大單即時流：終端機風格滾動牆，跟 SqueezeFeed 同一個視覺語言，但這裡
// 用買賣方向（buy=long色/sell=short色）取代擠壓燈號。whaleSweepSupported===false
// 代表這個標的在目前帳戶權限下確認不支援大單推播，要跟「還沒有大單」的
// 空狀態分開顯示，不能讓使用者誤以為系統沒在運作。
//
// 2026-07-16修復：底色原本硬寫死 bg-black/40，在新版淺色主題下會變成一片
// 混濁的灰黑色、文字幾乎看不清楚（新版主題是後來才加的，這幾個「終端機風格」
// 面板沒有一起更新到）。改用 bg-background/40 跟卡片背景色連動，深淺色主題
// 都會自動對。
//
// 同一批修復：delta由後端用最近一次GEX剖面重算帶出的IV估算（不是這筆交易
// 當下即時算的隱含波動率），估不出來時是null、顯示「Δ--」而不是假裝算得出來。
// 「只顯示方向性大單」開關純前端過濾，不影響原始資料，關掉隨時能看回全部。
export function WhaleSweepStream({ items, isLoading, whaleSweepSupported }: WhaleSweepStreamProps) {
  const [directionalOnly, setDirectionalOnly] = useState(false)

  const visibleItems = useMemo(
    () => (directionalOnly ? items.filter((item) => isDirectional(item.delta)) : items),
    [items, directionalOnly],
  )

  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-border/60 bg-background/40 p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <Fish className="size-3.5 text-primary" aria-hidden="true" />
          期權大單即時流（權利金 &gt; $500K）
        </h3>
        <div className="flex items-center gap-2">
          <label className="flex cursor-pointer items-center gap-1.5 text-[10px] text-muted-foreground">
            <input
              type="checkbox"
              checked={directionalOnly}
              onChange={(e) => setDirectionalOnly(e.target.checked)}
              className="size-3 accent-foreground"
            />
            只顯示方向性大單（|Δ| {DIRECTIONAL_DELTA_MIN}~{DIRECTIONAL_DELTA_MAX}）
          </label>
          <span className="text-[10px] text-muted-foreground">實驗性功能</span>
        </div>
      </div>

      <div className="flex max-h-64 flex-col gap-1 overflow-y-auto font-mono text-xs">
        {whaleSweepSupported === false ? (
          <p className="py-4 text-center text-muted-foreground">此帳戶權限目前不支援期權大單推播訂閱。</p>
        ) : items.length === 0 ? (
          <p className="py-4 text-center text-muted-foreground">
            {isLoading ? "連線中…" : "尚無達門檻的大單成交，系統持續監控中。"}
          </p>
        ) : visibleItems.length === 0 ? (
          <p className="py-4 text-center text-muted-foreground">目前沒有符合方向性篩選條件的大單，關掉篩選可看回全部。</p>
        ) : (
          visibleItems.map((item, i) => {
            const tone = item.side === "buy" ? "text-long" : item.side === "sell" ? "text-short" : "text-muted-foreground"
            const label = item.side === "buy" ? "🟢 BUY" : item.side === "sell" ? "🔴 SELL" : "⚪ 方向不明"
            return (
              <div key={`${item.symbol}-${item.triggeredAt}-${i}`} className={`flex items-center gap-2 ${tone}`}>
                <span className="text-muted-foreground">[{formatClockTime(item.triggeredAt)}]</span>
                <span className="font-bold">{label}</span>
                <span className="font-bold">${shortSymbol(item.symbol)}</span>
                <span className="text-muted-foreground">
                  {item.optionType === "call" ? "Call" : "Put"} ${formatPrice(item.strike)} · {item.expiry}
                </span>
                <span className="text-muted-foreground">
                  Δ{item.delta === null ? "--" : item.delta.toFixed(2)}
                </span>
                <span className="ml-auto font-bold">{formatCompactUsd(item.premiumUsd)}</span>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
