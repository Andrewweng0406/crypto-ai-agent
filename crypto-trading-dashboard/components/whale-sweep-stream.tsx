import { Fish } from "lucide-react"
import { type WhaleSweepItem, formatClockTime, formatCompactUsd, formatPrice } from "@/lib/signals"

function shortSymbol(symbol: string): string {
  return symbol.replace("/USDT", "").replace(":USDT", "")
}

interface WhaleSweepStreamProps {
  items: WhaleSweepItem[]
  isLoading: boolean
  whaleSweepSupported: boolean | null
}

// 期權大單即時流：黑底終端機風格滾動牆，跟 SqueezeFeed 同一個視覺語言，但這裡
// 用買賣方向（buy=long色/sell=short色）取代擠壓燈號。whaleSweepSupported===false
// 代表這個標的在目前帳戶權限下確認不支援大單推播，要跟「還沒有大單」的
// 空狀態分開顯示，不能讓使用者誤以為系統沒在運作。
export function WhaleSweepStream({ items, isLoading, whaleSweepSupported }: WhaleSweepStreamProps) {
  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-border/60 bg-black/40 p-4">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <Fish className="size-3.5 text-primary" aria-hidden="true" />
          期權大單即時流（權利金 &gt; $500K）
        </h3>
        <span className="text-[10px] text-muted-foreground">實驗性功能</span>
      </div>

      <div className="flex max-h-64 flex-col gap-1 overflow-y-auto font-mono text-xs">
        {whaleSweepSupported === false ? (
          <p className="py-4 text-center text-muted-foreground">此帳戶權限目前不支援期權大單推播訂閱。</p>
        ) : items.length === 0 ? (
          <p className="py-4 text-center text-muted-foreground">
            {isLoading ? "連線中…" : "尚無達門檻的大單成交，系統持續監控中。"}
          </p>
        ) : (
          items.map((item, i) => {
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
                <span className="ml-auto font-bold">{formatCompactUsd(item.premiumUsd)}</span>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
