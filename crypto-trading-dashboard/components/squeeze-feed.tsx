import { Zap } from "lucide-react"
import { type SqueezeFeedItem, formatClockTime } from "@/lib/signals"

function shortSymbol(symbol: string): string {
  return symbol.replace(":USDT", "").replace("/USDT", "")
}

interface SqueezeFeedProps {
  items: SqueezeFeedItem[]
  isLoading: boolean
}

// 實時擠壓警報滾動牆：終端機風格的事件日誌，市場掃描跟迷因雷達
// 共用同一份 green 燈號事件（來自 /api/squeeze-feed）。⚠️ 這套判斷未經回測
// 驗證，不是高勝率保證，純粹是事件記錄。
//
// 2026-07-16修復：底色原本硬寫死 bg-black/40，在新版淺色主題下會變成一片
// 混濁的灰黑色（新版主題後來才加，這個「終端機風格」面板沒有一起更新到）。
// 改用 bg-background/40 跟卡片背景色連動，深淺色主題都會自動對。
export function SqueezeFeed({ items, isLoading }: SqueezeFeedProps) {
  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-border/60 bg-background/40 p-4">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <Zap className="size-3.5 text-long" aria-hidden="true" />
          Squeeze Feed 擠壓警報滾動牆
        </h3>
        <span className="text-[10px] text-muted-foreground">未經回測驗證</span>
      </div>

      <div className="flex max-h-48 flex-col gap-1 overflow-y-auto font-mono text-xs">
        {items.length === 0 ? (
          <p className="py-4 text-center text-muted-foreground">
            {isLoading ? "連線中…" : "尚無擠壓爆破事件，系統持續監控中。"}
          </p>
        ) : (
          items.map((item, i) => (
            <div key={`${item.symbol}-${item.triggeredAt}-${i}`} className="flex items-center gap-2 text-long">
              <span className="text-muted-foreground">[{formatClockTime(item.triggeredAt)}]</span>
              <span className="font-bold">⚡ SQUEEZE ALERT:</span>
              <span className="font-bold">${shortSymbol(item.symbol)}</span>
              <span className="text-muted-foreground">
                OI 1h {item.oiGrowth1hPct !== null ? `+${item.oiGrowth1hPct.toFixed(0)}%` : "—"} · RVOL{" "}
                {item.rvol !== null ? `${item.rvol.toFixed(1)}x` : "—"}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
