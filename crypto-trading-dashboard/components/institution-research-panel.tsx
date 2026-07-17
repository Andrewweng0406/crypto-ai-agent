"use client"

import { useEffect, useState } from "react"
import useSWR from "swr"
import { Building2, ExternalLink, Landmark } from "lucide-react"
import { cn } from "@/lib/utils"
import {
  adaptResearchBundles,
  type BackendResearchBundlesResponse,
  type ResearchBundleData,
} from "@/lib/signals"

const fetcher = (url: string) =>
  fetch(url).then(async (r) => {
    const body = await r.json()
    if (!r.ok) throw new Error(body?.detail ?? `Request failed (${r.status})`)
    return body
  })

// 🏦 美股多機構研究彙總：資料源自使用者本機執行的 moomoo_research_sync_local.py
// （透過moomoo/futu-api的分析師共識/機構評級明細/晨星研報三支API），涵蓋標的
// 是美股ORB關注清單跟期權分析關注清單的聯集，見後端 get_research_bundles()
// 說明。這裡顯示的是真實機構評級跟晨星研報原文，不是AI生成的摘要。
export function InstitutionResearchPanel() {
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)

  const { data: rawList, isLoading } = useSWR<BackendResearchBundlesResponse>(
    "/api/us/research-bundles",
    fetcher,
    { refreshInterval: 60000 },
  )
  const bundles = rawList ? adaptResearchBundles(rawList) : []

  useEffect(() => {
    if (bundles.length === 0) return
    const stillPresent = bundles.some((b) => b.symbol === selectedSymbol)
    if (!stillPresent) {
      const firstWithData = bundles.find((b) => b.hasData)
      setSelectedSymbol((firstWithData ?? bundles[0]).symbol)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bundles.map((b) => b.symbol).join(",")])

  const selected = bundles.find((b) => b.symbol === selectedSymbol) ?? null

  return (
    <div className="flex flex-col gap-5 rounded-2xl border border-border/60 bg-card p-5">
      <div className="flex flex-wrap items-center gap-2.5">
        <Landmark className="size-5 text-primary" aria-hidden="true" />
        <h2 className="font-mono text-base font-semibold">🏦 美股多機構研究彙總</h2>
        <span className="rounded-md bg-secondary px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
          資料源：moomoo 機構評級 / 晨星研報
        </span>
      </div>

      {bundles.length === 0 ? (
        <p className="text-sm text-muted-foreground">{isLoading ? "載入中…" : "尚無關注標的"}</p>
      ) : (
        <>
          <div className="flex flex-wrap gap-1.5">
            {bundles.map((b) => (
              <button
                key={b.symbol}
                onClick={() => setSelectedSymbol(b.symbol)}
                className={cn(
                  "rounded-md px-2.5 py-1 font-mono text-xs transition-colors",
                  b.symbol === selectedSymbol
                    ? "bg-primary text-primary-foreground"
                    : "bg-secondary text-muted-foreground hover:text-foreground",
                  !b.hasData && b.symbol !== selectedSymbol && "opacity-50",
                )}
              >
                {b.symbol}
              </button>
            ))}
          </div>

          {selected && (selected.hasData ? <ResearchCard bundle={selected} /> : <NoDataNotice symbol={selected.symbol} />)}
        </>
      )}
    </div>
  )
}

function NoDataNotice({ symbol }: { symbol: string }) {
  return (
    <p className="rounded-xl border border-dashed border-border/60 px-4 py-6 text-center text-sm text-muted-foreground">
      {symbol} 還沒有機構研究資料——本機 moomoo_research_sync_local.py
      尚未同步過這檔，或這檔沒有機構分析師覆蓋。
    </p>
  )
}

const RATING_TONE: Record<number, string> = {
  1: "bg-short/15 text-short", // 賣出
  2: "bg-short/15 text-short", // 表現不佳
  3: "bg-secondary text-muted-foreground", // 持有
  4: "bg-long/15 text-long", // 買入
  5: "bg-long/15 text-long", // 強力買入
}

function RatingBadge({ rating, label }: { rating: number | null; label: string | null }) {
  if (rating === null || label === null) {
    return <span className="rounded-md bg-secondary px-2 py-0.5 font-mono text-[11px] text-muted-foreground">N/A</span>
  }
  return (
    <span className={cn("rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold", RATING_TONE[rating] ?? "bg-secondary text-muted-foreground")}>
      {label}
    </span>
  )
}

function ResearchCard({ bundle }: { bundle: ResearchBundleData }) {
  const hasConsensus = bundle.consensusAverage !== null
  const buyPct = bundle.consensusBuyPct ?? 0
  const holdPct = bundle.consensusHoldPct ?? 0
  const sellPct = bundle.consensusSellPct ?? 0

  // 「神仙打架」：機構評級明細裡目標價最高 vs 最低的兩家，天然就是多空分歧最大的兩方，
  // 不需要另外用LLM生成，直接從真實資料算出來。
  const withPrice = bundle.institutionRatings.filter((r) => r.targetPrice !== null)
  const bullView = withPrice.length > 0 ? withPrice.reduce((a, b) => ((a.targetPrice ?? 0) > (b.targetPrice ?? 0) ? a : b)) : null
  const bearView = withPrice.length > 0 ? withPrice.reduce((a, b) => ((a.targetPrice ?? 0) < (b.targetPrice ?? 0) ? a : b)) : null

  return (
    <div className="flex flex-col gap-5">
      {hasConsensus && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="最高目標價" value={`$${bundle.consensusHigh?.toFixed(0)}`} />
          <StatTile label="共識平均目標價" value={`$${bundle.consensusAverage?.toFixed(0)}`} emphasize />
          <StatTile label="最低目標價" value={`$${bundle.consensusLow?.toFixed(0)}`} />
          <StatTile label="分析師人數" value={`${bundle.consensusTotal ?? "--"} 位`} />
        </div>
      )}

      {hasConsensus && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              華爾街共識：<RatingBadge rating={bundle.consensusRating} label={bundle.consensusRatingLabel} />
            </span>
            <span className="font-mono">
              買入 {buyPct.toFixed(0)}% · 持有 {holdPct.toFixed(0)}% · 賣出 {sellPct.toFixed(0)}%
            </span>
          </div>
          <div className="flex h-2 overflow-hidden rounded-full bg-secondary">
            <div className="bg-long" style={{ width: `${buyPct}%` }} />
            <div className="bg-muted-foreground/40" style={{ width: `${holdPct}%` }} />
            <div className="bg-short" style={{ width: `${sellPct}%` }} />
          </div>
        </div>
      )}

      {bullView && bearView && bullView.institutionName !== bearView.institutionName && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <ClashTile tone="long" title="最看多" rating={bullView} />
          <ClashTile tone="short" title="最看空/保守" rating={bearView} />
        </div>
      )}

      {bundle.morningstarFairValue !== null && (
        <div className="flex flex-col gap-2 rounded-xl border border-border/60 p-4">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-mono font-semibold text-foreground">晨星研報</span>
            {bundle.morningstarStarRating !== null && <span className="text-muted-foreground">{"★".repeat(bundle.morningstarStarRating)}{"☆".repeat(Math.max(0, 5 - bundle.morningstarStarRating))}</span>}
            <span className="text-muted-foreground">
              公允價值 <span className="font-mono font-semibold text-foreground">${bundle.morningstarFairValue.toFixed(0)}</span>
            </span>
            {bundle.morningstarMoatLabel && (
              <span className="rounded-md bg-secondary px-2 py-0.5 text-[11px] text-muted-foreground">護城河：{bundle.morningstarMoatLabel}</span>
            )}
            {bundle.morningstarUncertaintyLabel && (
              <span className="rounded-md bg-secondary px-2 py-0.5 text-[11px] text-muted-foreground">不確定性：{bundle.morningstarUncertaintyLabel}</span>
            )}
            {bundle.morningstarFinancialHealthLabel && (
              <span className="rounded-md bg-secondary px-2 py-0.5 text-[11px] text-muted-foreground">財務健康：{bundle.morningstarFinancialHealthLabel}</span>
            )}
          </div>
          {bundle.morningstarFairValueContext && (
            <p className="whitespace-pre-line text-xs leading-relaxed text-muted-foreground">{bundle.morningstarFairValueContext}</p>
          )}
        </div>
      )}

      {bundle.institutionRatings.length > 0 && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
            <Building2 className="size-3.5" aria-hidden="true" />
            機構評級明細（{bundle.institutionRatings.length}）
          </div>
          <div className="flex max-h-72 flex-col gap-1 overflow-y-auto">
            {bundle.institutionRatings.map((r, i) => (
              <a
                key={`${r.institutionName}-${i}`}
                href={r.ratingUrl ?? undefined}
                target="_blank"
                rel="noreferrer"
                className={cn(
                  "flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-xs",
                  r.ratingUrl ? "hover:bg-secondary" : "pointer-events-none",
                )}
              >
                <span className="flex items-center gap-2">
                  <RatingBadge rating={r.rating} label={r.rating !== null ? RATING_LABEL_MAP[r.rating] ?? null : null} />
                  <span className="font-medium text-foreground">{r.institutionName}</span>
                </span>
                <span className="flex items-center gap-2 font-mono text-muted-foreground">
                  {r.targetPrice !== null && <span>${r.targetPrice.toFixed(0)}</span>}
                  <span>{r.recommendationDateStr ?? ""}</span>
                  {r.ratingUrl && <ExternalLink className="size-3" aria-hidden="true" />}
                </span>
              </a>
            ))}
          </div>
        </div>
      )}

      {bundle.updatedAt && (
        <p className="text-right text-[11px] text-muted-foreground">最後同步：{new Date(bundle.updatedAt).toLocaleString("zh-TW")}</p>
      )}
    </div>
  )
}

const RATING_LABEL_MAP: Record<number, string> = {
  1: "賣出",
  2: "表現不佳",
  3: "持有",
  4: "買入",
  5: "強力買入",
}

function StatTile({ label, value, emphasize }: { label: string; value: string; emphasize?: boolean }) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-border/60 px-3 py-2.5">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className={cn("font-mono text-base font-semibold", emphasize ? "text-primary" : "text-foreground")}>{value}</span>
    </div>
  )
}

function ClashTile({
  tone,
  title,
  rating,
}: {
  tone: "long" | "short"
  title: string
  rating: { institutionName: string; targetPrice: number | null; recommendationDateStr: string | null }
}) {
  return (
    <div className={cn("flex flex-col gap-1 rounded-xl border p-3", tone === "long" ? "border-long/30 bg-long/[0.06]" : "border-short/30 bg-short/[0.06]")}>
      <span className={cn("text-[11px] font-semibold", tone === "long" ? "text-long" : "text-short")}>{title}</span>
      <span className="font-medium text-foreground">{rating.institutionName}</span>
      <span className="font-mono text-sm text-muted-foreground">
        目標價 ${rating.targetPrice?.toFixed(0)} · {rating.recommendationDateStr}
      </span>
    </div>
  )
}
