"use client"

import { useEffect, useRef, useState } from "react"
import useSWR, { mutate as globalMutate } from "swr"
import { X, Plus, Loader2 } from "lucide-react"
import {
  adaptBingxStockCatalog,
  adaptWatchlist,
  type BackendBingxStockCatalogResponse,
  type BackendWatchlistResponse,
  type BingxStockCatalogItem,
} from "@/lib/signals"

const fetcher = (url: string) =>
  fetch(url).then(async (r) => {
    const body = await r.json()
    if (!r.ok) throw new Error(body?.detail ?? `Request failed (${r.status})`)
    return body
  })

interface WatchlistEditorProps {
  watchlistUrl: string
  dataUrl: string // 新增/移除成功後，一併重新驗證的主資料端點（讓面板即時反映異動）
  catalogUrl?: string // 提供時走「搜尋既有目錄」模式（美股ORB）；不提供則是「自由輸入代號」模式（期權分析）
  placeholder: string
  maxSize: number
}

// ⭐ 自選監控清單編輯器：期權分析（自由輸入任意美股代號）跟美股ORB（只能從
// BingX目前上架的代幣化商品目錄裡選）共用同一顆元件，用 catalogUrl 是否提供
// 來切換兩種輸入模式，styling跟互動邏輯完全共用。
export function WatchlistEditor({ watchlistUrl, dataUrl, catalogUrl, placeholder, maxSize }: WatchlistEditorProps) {
  const { data, isLoading } = useSWR<BackendWatchlistResponse>(watchlistUrl, fetcher, { refreshInterval: 30000 })
  const [query, setQuery] = useState("")
  const [catalogResults, setCatalogResults] = useState<BingxStockCatalogItem[]>([])
  const [showDropdown, setShowDropdown] = useState(false)
  const [pending, setPending] = useState<string | null>(null) // 目前正在新增/移除的代號（用來個別鎖住按鈕、避免重複點擊）
  const [errorText, setErrorText] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const items = data ? adaptWatchlist(data) : []

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowDropdown(false)
      }
    }
    document.addEventListener("mousedown", onClickOutside)
    return () => document.removeEventListener("mousedown", onClickOutside)
  }, [])

  // 美股ORB模式：輸入時debounce搜尋BingX目錄（後端純記憶體篩選，很快，300ms已足夠避免每個按鍵都打一次）
  useEffect(() => {
    if (!catalogUrl) return
    if (!query.trim()) {
      setCatalogResults([])
      return
    }
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`${catalogUrl}?q=${encodeURIComponent(query.trim())}`)
        const body: BackendBingxStockCatalogResponse = await res.json()
        if (res.ok) setCatalogResults(adaptBingxStockCatalog(body).items)
      } catch {
        // 搜尋失敗不用特別提示，使用者繼續打字就會再重試
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [query, catalogUrl])

  async function revalidateAll() {
    await Promise.all([globalMutate(watchlistUrl), globalMutate(dataUrl)])
  }

  async function addSymbol(ticker: string) {
    const normalized = ticker.trim().toUpperCase()
    if (!normalized) return
    if (items.length >= maxSize) {
      setErrorText(`自選清單已達上限（${maxSize}檔），請先移除幾檔再新增`)
      return
    }
    setPending(normalized)
    setErrorText(null)
    try {
      const res = await fetch(watchlistUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: normalized }),
      })
      const body = await res.json()
      if (!res.ok) {
        setErrorText(body?.detail ?? "新增失敗")
        return
      }
      setQuery("")
      setCatalogResults([])
      setShowDropdown(false)
      await revalidateAll()
    } catch {
      setErrorText("無法連線到後端服務")
    } finally {
      setPending(null)
    }
  }

  async function removeSymbol(displayName: string) {
    setPending(displayName)
    setErrorText(null)
    try {
      const res = await fetch(`${watchlistUrl}/${encodeURIComponent(displayName)}`, { method: "DELETE" })
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        setErrorText(body?.detail ?? "移除失敗")
        return
      }
      await revalidateAll()
    } catch {
      setErrorText("無法連線到後端服務")
    } finally {
      setPending(null)
    }
  }

  return (
    <div ref={containerRef} className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        {items.map((item) => (
          <span
            key={item.displayName}
            className="flex items-center gap-1.5 rounded-full border border-border/60 bg-secondary/40 py-1 pl-3 pr-1.5 text-xs font-mono font-semibold"
          >
            {item.displayName}
            <button
              type="button"
              onClick={() => removeSymbol(item.displayName)}
              disabled={pending === item.displayName}
              aria-label={`移除 ${item.displayName}`}
              className="flex size-4 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-short/15 hover:text-short disabled:opacity-40"
            >
              {pending === item.displayName ? <Loader2 className="size-3 animate-spin" /> : <X className="size-3" />}
            </button>
          </span>
        ))}
        {isLoading && items.length === 0 && (
          <span className="text-xs text-muted-foreground">載入自選清單中…</span>
        )}
      </div>

      <div className="relative flex items-center gap-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setShowDropdown(true)
              setErrorText(null)
            }}
            onFocus={() => setShowDropdown(true)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !catalogUrl) {
                e.preventDefault()
                addSymbol(query)
              }
            }}
            placeholder={placeholder}
            maxLength={20}
            className="w-full rounded-lg border border-border/60 bg-card px-3 py-2 text-sm font-mono outline-none transition-colors focus:border-primary/60"
          />
          {catalogUrl && showDropdown && query.trim() && catalogResults.length > 0 && (
            <div className="absolute left-0 right-0 top-full z-10 mt-1 max-h-56 overflow-y-auto rounded-lg border border-border/60 bg-card shadow-lg">
              {catalogResults.map((c) => {
                const alreadyAdded = items.some((item) => item.displayName === c.displayName)
                return (
                  <button
                    key={c.displayName}
                    type="button"
                    disabled={alreadyAdded || pending !== null}
                    onClick={() => addSymbol(c.displayName)}
                    className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-mono transition-colors hover:bg-secondary/50 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <span>{c.displayName}</span>
                    {alreadyAdded && <span className="text-[10px] text-muted-foreground">已在清單中</span>}
                  </button>
                )
              })}
            </div>
          )}
        </div>
        {!catalogUrl && (
          <button
            type="button"
            onClick={() => addSymbol(query)}
            disabled={!query.trim() || pending !== null}
            className="flex items-center gap-1 rounded-lg border border-primary/50 bg-primary/10 px-3 py-2 text-xs font-semibold text-primary transition-colors hover:bg-primary/15 disabled:opacity-40"
          >
            {pending && pending === query.trim().toUpperCase() ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Plus className="size-3.5" />
            )}
            新增
          </button>
        )}
      </div>

      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
        <span>{items.length}／{maxSize} 檔</span>
        {errorText && <span className="text-short">{errorText}</span>}
      </div>
    </div>
  )
}
