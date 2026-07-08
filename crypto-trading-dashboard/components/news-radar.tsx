import { Newspaper, Radar } from "lucide-react"
import { cn } from "@/lib/utils"
import { type NewsItem, formatTime } from "@/lib/signals"

const RESONANCE_THRESHOLD = 7 // 對應後端 NEWS_RESONANCE_SCORE_THRESHOLD，用來標示「強烈」情緒

function sentimentTone(score: number): "long" | "short" | "neutral" {
  if (score > 0) return "long"
  if (score < 0) return "short"
  return "neutral"
}

function sentimentLabel(score: number): string {
  if (score >= RESONANCE_THRESHOLD) return "強烈利多"
  if (score > 0) return "偏多"
  if (score <= -RESONANCE_THRESHOLD) return "強烈利空"
  if (score < 0) return "偏空"
  return "中性"
}

interface NewsRadarProps {
  items: NewsItem[]
  isLoading: boolean
  error?: string
}

// AI 智能投研 Agent 面板：純資訊時間流，沒有方向/TP/SL/槓桿——這是新聞情緒監控，
// 不是交易訊號。跟迷因雷達同樣的「獨立模塊」定位，只是資料形狀完全不同。
export function NewsRadar({ items, isLoading, error }: NewsRadarProps) {
  if (error) {
    return (
      <div className="rounded-2xl border border-short/30 bg-short/[0.06] p-6 text-center text-sm text-short">
        無法載入 AI 智能輿情雷達：{error}
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="flex min-h-[160px] flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-border/60 bg-card/40 p-8 text-center text-sm text-muted-foreground">
        <Radar className="size-6" aria-hidden="true" />
        {isLoading ? "雷達啟動中…" : "尚未有 AI 分析出的新聞，背景每 10 分鐘掃描一次。"}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2.5">
      {items.map((item, i) => {
        const tone = sentimentTone(item.sentimentScore)
        const isStrong = Math.abs(item.sentimentScore) >= RESONANCE_THRESHOLD

        return (
          <a
            key={`${item.url}-${i}`}
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className={cn(
              "flex flex-col gap-2 rounded-xl border bg-card px-4 py-3.5 transition-colors hover:bg-secondary/40",
              isStrong
                ? tone === "long"
                  ? "border-long/40"
                  : tone === "short"
                    ? "border-short/40"
                    : "border-border/60"
                : "border-border/60",
            )}
          >
            <div className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Newspaper className="size-3.5" aria-hidden="true" />
                {item.source}
              </span>
              <span className="text-xs text-muted-foreground">{formatTime(item.processedAt)}</span>
            </div>

            <p className="text-sm font-medium leading-snug text-foreground">{item.title}</p>
            <p className="text-xs text-muted-foreground">{item.summary}</p>

            <div className="flex flex-wrap items-center justify-between gap-2 pt-0.5">
              <div className="flex flex-wrap gap-1.5">
                {item.symbols.length > 0 ? (
                  item.symbols.map((s) => (
                    <span
                      key={s}
                      className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px] font-semibold text-muted-foreground"
                    >
                      {s}
                    </span>
                  ))
                ) : (
                  <span className="text-[11px] text-muted-foreground">未提及明確標的</span>
                )}
              </div>

              <span
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold",
                  tone === "long" && "bg-long/15 text-long",
                  tone === "short" && "bg-short/15 text-short",
                  tone === "neutral" && "bg-secondary text-muted-foreground",
                )}
              >
                {sentimentLabel(item.sentimentScore)}
                <span className="font-mono tabular-nums">
                  {item.sentimentScore > 0 ? "+" : ""}
                  {item.sentimentScore}
                </span>
              </span>
            </div>
          </a>
        )
      })}
    </div>
  )
}
