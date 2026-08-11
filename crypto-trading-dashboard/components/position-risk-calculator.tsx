"use client"

import { useEffect, useMemo, useState } from "react"
import { Calculator } from "lucide-react"
import { estimatePositionRisk } from "@/lib/risk"

const STORAGE_KEY = "weng-risk-settings"

interface BackendRiskSettings {
  account_size: number
  risk_pct: number
  max_leverage: number
  updated_at?: string | null
}

export function PositionRiskCalculator() {
  const [accountSize, setAccountSize] = useState(1000)
  const [riskPct, setRiskPct] = useState(1)
  const [maxLeverage, setMaxLeverage] = useState(5)
  const [entry, setEntry] = useState(100)
  const [stop, setStop] = useState(95)
  const [hasLoaded, setHasLoaded] = useState(false)
  const [isOffline, setIsOffline] = useState(false)

  const estimate = useMemo(
    () => estimatePositionRisk({ accountSize, riskPct, entry, stop, maxLeverage }),
    [accountSize, riskPct, entry, stop, maxLeverage],
  )

  useEffect(() => {
    let active = true
    fetch("/api/risk-settings", { cache: "no-store" })
      .then(async (response) => {
        const body = (await response.json()) as BackendRiskSettings
        if (!response.ok) throw new Error("risk settings unavailable")
        if (!active) return
        setAccountSize(body.account_size)
        setRiskPct(body.risk_pct)
        setMaxLeverage(body.max_leverage)
        setIsOffline(false)
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(body))
        setHasLoaded(true)
      })
      .catch(() => {
        if (!active) return
        try {
          const raw = window.localStorage.getItem(STORAGE_KEY)
          if (raw) {
            const cached = JSON.parse(raw) as BackendRiskSettings
            setAccountSize(cached.account_size)
            setRiskPct(cached.risk_pct)
            setMaxLeverage(cached.max_leverage)
          }
        } catch {
          // Keep defaults.
        }
        setIsOffline(true)
        setHasLoaded(true)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!hasLoaded) return
    const payload: BackendRiskSettings = {
      account_size: accountSize,
      risk_pct: riskPct,
      max_leverage: maxLeverage,
    }
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
    const timer = window.setTimeout(() => {
      fetch("/api/risk-settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        cache: "no-store",
      })
        .then((response) => {
          if (!response.ok) throw new Error("risk settings save failed")
          setIsOffline(false)
        })
        .catch(() => setIsOffline(true))
    }, 600)
    return () => window.clearTimeout(timer)
  }, [accountSize, riskPct, maxLeverage, hasLoaded])

  return (
    <section className="rounded-2xl border border-border/60 bg-card p-5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Calculator className="size-4 text-primary" aria-hidden="true" />
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">資金風控</h2>
        </div>
        <span className="text-xs text-muted-foreground">{isOffline ? "本機暫存" : "已同步"}</span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <NumberField label="帳戶資金" value={accountSize} min={0} step={100} onChange={setAccountSize} />
        <NumberField label="單筆風險 %" value={riskPct} min={0.1} max={10} step={0.1} onChange={setRiskPct} />
        <NumberField label="最大槓桿" value={maxLeverage} min={1} max={125} step={1} onChange={setMaxLeverage} />
        <NumberField label="進場價" value={entry} min={0} step={0.01} onChange={setEntry} />
        <NumberField label="停損價" value={stop} min={0} step={0.01} onChange={setStop} />
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2">
        <Result label="最多虧損" value={`$${estimate.accountRisk.toFixed(2)}`} />
        <Result label="停損距離" value={`${estimate.stopMovePct.toFixed(2)}%`} />
        <Result label="部位上限" value={`$${estimate.positionValue.toFixed(2)}`} />
        <Result label="需求槓桿" value={`${estimate.requiredLeverage.toFixed(2)}x`} />
        <Result label="槓桿限制" value={estimate.cappedByLeverage ? "已限制" : "未觸發"} />
      </div>
    </section>
  )
}

function NumberField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string
  value: number
  min: number
  max?: number
  step: number
  onChange: (value: number) => void
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-muted-foreground">
      {label}
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(Number(event.target.value))}
        className="h-10 rounded-lg border border-border/60 bg-background px-3 font-mono text-sm font-semibold text-foreground outline-none focus:border-primary"
      />
    </label>
  )
}

function Result({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border/60 bg-secondary/30 px-3 py-2">
      <span className="block text-[11px] text-muted-foreground">{label}</span>
      <span className="font-mono text-sm font-bold">{value}</span>
    </div>
  )
}
