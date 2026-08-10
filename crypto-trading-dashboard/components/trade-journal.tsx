"use client"

import { useEffect, useMemo, useState } from "react"
import { BookOpen, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"

type JournalAction = "觀察" | "模擬" | "實盤"
type JournalEmotion = "冷靜" | "猶豫" | "追高" | "恐慌"

interface JournalEntry {
  id: string
  symbol: string
  action: JournalAction
  emotion: JournalEmotion
  note: string
  createdAt: string
}

const STORAGE_KEY = "weng-trade-journal"

export function TradeJournal() {
  const [entries, setEntries] = useState<JournalEntry[]>([])
  const [symbol, setSymbol] = useState("")
  const [action, setAction] = useState<JournalAction>("觀察")
  const [emotion, setEmotion] = useState<JournalEmotion>("冷靜")
  const [note, setNote] = useState("")

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY)
      if (raw) setEntries(JSON.parse(raw))
    } catch {
      setEntries([])
    }
  }, [])

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
  }, [entries])

  const pattern = useMemo(() => {
    const fomoCount = entries.filter((entry) => entry.emotion === "追高" || entry.emotion === "恐慌").length
    if (entries.length < 3) return "累積 3 筆後開始回顧習慣。"
    return fomoCount / entries.length >= 0.4 ? "最近情緒交易偏多，先降低下單頻率。" : "紀錄穩定，繼續保持交易前檢查。"
  }, [entries])

  function addEntry() {
    const cleanSymbol = symbol.trim().toUpperCase()
    if (!cleanSymbol) return
    setEntries((current) => [
      {
        id: crypto.randomUUID(),
        symbol: cleanSymbol,
        action,
        emotion,
        note: note.trim(),
        createdAt: new Date().toISOString(),
      },
      ...current,
    ].slice(0, 20))
    setSymbol("")
    setNote("")
  }

  return (
    <section className="rounded-2xl border border-border/60 bg-card p-5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <BookOpen className="size-4 text-primary" aria-hidden="true" />
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">交易日記</h2>
        </div>
        <span className="text-xs text-muted-foreground">{entries.length} 筆</span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <input
          value={symbol}
          onChange={(event) => setSymbol(event.target.value)}
          placeholder="標的"
          className="h-10 rounded-lg border border-border/60 bg-background px-3 font-mono text-sm font-semibold outline-none focus:border-primary"
        />
        <select
          value={action}
          onChange={(event) => setAction(event.target.value as JournalAction)}
          className="h-10 rounded-lg border border-border/60 bg-background px-3 text-sm outline-none focus:border-primary"
        >
          <option>觀察</option>
          <option>模擬</option>
          <option>實盤</option>
        </select>
        <select
          value={emotion}
          onChange={(event) => setEmotion(event.target.value as JournalEmotion)}
          className="h-10 rounded-lg border border-border/60 bg-background px-3 text-sm outline-none focus:border-primary"
        >
          <option>冷靜</option>
          <option>猶豫</option>
          <option>追高</option>
          <option>恐慌</option>
        </select>
        <Button type="button" onClick={addEntry} className="h-10">
          新增
        </Button>
      </div>

      <textarea
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="進場理由"
        className="mt-3 min-h-20 w-full resize-none rounded-lg border border-border/60 bg-background px-3 py-2 text-sm outline-none focus:border-primary"
      />

      <p className="mt-3 rounded-xl border border-border/60 bg-secondary/30 px-3 py-2 text-xs text-muted-foreground">
        {pattern}
      </p>

      {entries.length > 0 && (
        <ul className="mt-3 flex max-h-56 flex-col gap-2 overflow-y-auto pr-1">
          {entries.slice(0, 6).map((entry) => (
            <li key={entry.id} className="flex items-start justify-between gap-3 rounded-xl border border-border/50 bg-background/60 px-3 py-2">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-semibold">{entry.symbol}</span>
                  <span className="text-xs text-muted-foreground">{entry.action} · {entry.emotion}</span>
                </div>
                {entry.note && <p className="mt-1 text-xs text-muted-foreground">{entry.note}</p>}
              </div>
              <button
                type="button"
                onClick={() => setEntries((current) => current.filter((item) => item.id !== entry.id))}
                className="rounded-md p-1 text-muted-foreground hover:text-short"
                aria-label="刪除紀錄"
              >
                <Trash2 className="size-3.5" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
