"use client"

import { useMemo, useState } from "react"
import { AlertTriangle, Rocket } from "lucide-react"
import { cn } from "@/lib/utils"
import {
  adaptBacktestResult,
  type BacktestResult,
  type BacktestStrategy,
  type BackendBacktestResponse,
} from "@/lib/signals"

// 三個策略各自對應「已知真的有真實歷史資料源」的標的清單，不開放自由輸入
// 任意代號——避免使用者打錯字/打進系統沒在追蹤的標的，白白浪費一次限流額度
// 換來一個502。這三組清單刻意跟正式站台其他分頁（主流幣/迷因當沖/期權分析）
// 已經在追蹤的標的保持一致。
const STRATEGY_SYMBOLS: Record<BacktestStrategy, string[]> = {
  crypto_donchian_1h: ["BTC", "ETH", "SOL"],
  meme_volume_spike: ["WIF", "DOGE", "PEPE", "SHIB", "BONK"],
  us_stock_orb: ["NVDA", "TSLA", "SPY", "SMCI", "SPCX"],
}

const STRATEGY_LABELS: Record<BacktestStrategy, string> = {
  crypto_donchian_1h: "1H 唐奇安突破（主流幣）",
  meme_volume_spike: "1H 爆量當沖（迷因幣）",
  us_stock_orb: "開盤區間突破（美股ORB）",
}

const STRATEGY_MAX_DAYS: Record<BacktestStrategy, number> = {
  crypto_donchian_1h: 180,
  meme_volume_spike: 180,
  us_stock_orb: 60, // yfinance 15分鐘K線真實上限，見後端 BACKTEST_YF_MAX_DAYS 說明
}

const fetcher = async (url: string, body: unknown): Promise<BackendBacktestResponse> => {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  const json = await res.json()
  if (!res.ok) throw new Error(json?.detail ?? `請求失敗（${res.status}）`)
  return json
}

// 📊 網頁端回測沙盒：把 backtest_optimizer.py 已經驗證過的邏輯搬上正式站台，
// 只支援三個有真實歷史資料源的策略。公開端點，後端有IP限流（15次/小時）
// 防止被用來刷爆外部交易所/yfinance API額度。
export function BacktestSandboxPanel() {
  const [strategy, setStrategy] = useState<BacktestStrategy>("crypto_donchian_1h")
  const [symbol, setSymbol] = useState<string>(STRATEGY_SYMBOLS.crypto_donchian_1h[0])
  const [daysRange, setDaysRange] = useState<number>(30)
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const availableSymbols = STRATEGY_SYMBOLS[strategy]
  const maxDays = STRATEGY_MAX_DAYS[strategy]

  const handleStrategyChange = (next: BacktestStrategy) => {
    setStrategy(next)
    setSymbol(STRATEGY_SYMBOLS[next][0])
    setDaysRange((prev) => Math.min(prev, STRATEGY_MAX_DAYS[next]))
    setResult(null)
    setError(null)
  }

  const runBacktest = async () => {
    setIsLoading(true)
    setError(null)
    setResult(null)
    try {
      const raw = await fetcher("/api/backtest", { symbol, strategy_name: strategy, days_range: daysRange })
      setResult(adaptBacktestResult(raw))
    } catch (err) {
      setError(err instanceof Error ? err.message : "回測請求失敗")
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-5 rounded-2xl border border-border/60 bg-card p-5">
      <div className="flex items-center gap-2.5">
        <h2 className="font-mono text-base font-semibold">🚀 策略回測沙盒</h2>
        <span className="rounded-md bg-secondary px-2 py-0.5 font-mono text-[11px] text-muted-foreground">實驗性功能</span>
      </div>

      {/* 策略選擇 */}
      <div className="flex flex-col gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">策略類型</span>
        <div className="flex flex-wrap gap-2">
          {(Object.keys(STRATEGY_LABELS) as BacktestStrategy[]).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => handleStrategyChange(s)}
              className={cn(
                "rounded-xl border px-3.5 py-2 text-left text-xs font-semibold transition-colors",
                strategy === s
                  ? "border-primary/60 bg-primary/[0.1] text-primary"
                  : "border-border/60 bg-secondary/30 text-muted-foreground hover:bg-secondary/60",
              )}
            >
              {STRATEGY_LABELS[s]}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* 標的下拉選單 */}
        <div className="flex flex-col gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">標的</span>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="rounded-xl border border-border/60 bg-background px-3 py-2 font-mono text-sm outline-none focus:border-primary/60"
          >
            {availableSymbols.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        {/* 天數滑塊 */}
        <div className="flex flex-col gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            回測天數：<span className="font-mono text-foreground">{daysRange}</span> 天
            {daysRange > maxDays && (
              <span className="ml-1 text-short">（會被夾到 {maxDays} 天，資料源真實上限）</span>
            )}
          </span>
          <input
            type="range"
            min={7}
            max={180}
            step={1}
            value={daysRange}
            onChange={(e) => setDaysRange(Number(e.target.value))}
            className="accent-primary"
          />
        </div>
      </div>

      <button
        type="button"
        onClick={runBacktest}
        disabled={isLoading}
        className="flex items-center justify-center gap-2 rounded-xl bg-primary py-3 text-sm font-bold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        <Rocket className={cn("size-4", isLoading && "animate-pulse")} aria-hidden="true" />
        {isLoading ? "回測執行中…（真實抓取歷史資料，可能需要數秒到數十秒）" : "開始優化回測"}
      </button>

      {error && (
        <div className="flex items-start gap-1.5 rounded-lg border border-short/30 bg-short/[0.06] px-3 py-2 text-xs text-short">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          {error}
        </div>
      )}

      {isLoading && <BacktestSkeleton />}

      {result && !isLoading && <BacktestResultView result={result} />}
    </div>
  )
}

function BacktestSkeleton() {
  return (
    <div className="flex flex-col gap-4 animate-pulse">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-24 rounded-xl bg-secondary/40" />
        ))}
      </div>
      <div className="h-48 rounded-xl bg-secondary/40" />
    </div>
  )
}

function BacktestResultView({ result }: { result: BacktestResult }) {
  const isProfitable = result.equityCurve[result.equityCurve.length - 1] >= result.equityCurve[0]

  return (
    <div className="flex flex-col gap-4">
      {!result.sampleSufficient && (
        <div className="flex items-start gap-1.5 rounded-lg border border-short/30 bg-short/[0.06] px-3 py-2 text-xs text-short">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          樣本數僅 {result.totalTrades} 筆（門檻15筆），這組數字統計上不具意義，不能拿來下結論。
        </div>
      )}
      {result.daysRangeUsed < result.daysRangeRequested && (
        <p className="text-xs text-muted-foreground">
          ⚠️ 你要求 {result.daysRangeRequested} 天，但 {result.dataSource} 真實上限只到 {result.daysRangeUsed}{" "}
          天，已自動夾住（不是模擬資料）。
        </p>
      )}

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <WinRateRing winRate={result.winRate} />
        <StatTile label="賺賠比" value={result.profitLossRatio.toFixed(2)} />
        <StatTile
          label="最大回撤 MDD"
          value={`${result.mdd.toFixed(1)}%`}
          tone={result.mdd < -20 ? "short" : "neutral"}
        />
        <StatTile label="總交易筆數" value={String(result.totalTrades)} />
      </div>

      <EquityCurveChart equityCurve={result.equityCurve} isProfitable={isProfitable} />

      <p className="text-xs text-muted-foreground">
        {result.symbol} · {STRATEGY_LABELS[result.strategyName as BacktestStrategy] ?? result.strategyName} ·
        資料源 {result.dataSource} · 獲利因子 {result.profitFactor.toFixed(2)}
      </p>
    </div>
  )
}

function StatTile({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "long" | "short" | "neutral" }) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-border/60 bg-secondary/30 px-4 py-3">
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <span
        className={cn(
          "font-mono text-xl font-bold",
          tone === "long" && "text-long",
          tone === "short" && "text-short",
          tone === "neutral" && "text-foreground",
        )}
      >
        {value}
      </span>
    </div>
  )
}

function WinRateRing({ winRate }: { winRate: number }) {
  const size = 96
  const strokeWidth = 8
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - Math.min(Math.max(winRate, 0), 100) / 100)
  const tone = winRate >= 50 ? "var(--long)" : "var(--short)"

  return (
    <div className="flex flex-col items-center justify-center gap-1 rounded-xl border border-border/60 bg-secondary/30 px-4 py-3">
      <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--border)" strokeWidth={strokeWidth} />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={tone}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
          />
        </svg>
        <span className="absolute font-mono text-lg font-extrabold" style={{ color: tone }}>
          {winRate.toFixed(1)}%
        </span>
      </div>
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">勝率</span>
    </div>
  )
}

function EquityCurveChart({ equityCurve, isProfitable }: { equityCurve: number[]; isProfitable: boolean }) {
  const width = 800
  const height = 180
  const padX = 8
  const padY = 12

  const values = equityCurve.length > 0 ? equityCurve : [100]
  const minV = Math.min(...values)
  const maxV = Math.max(...values)
  const range = maxV - minV || 1

  const x = (i: number) => padX + (i / Math.max(values.length - 1, 1)) * (width - padX * 2)
  const y = (v: number) => padY + (1 - (v - minV) / range) * (height - padY * 2)

  const points = values.map((v, i) => `${x(i)},${y(v)}`).join(" ")
  const baselineY = y(values[0])
  const tone = isProfitable ? "var(--long)" : "var(--short)"

  return (
    <div className="rounded-xl border border-border/60 bg-background/40 p-3">
      <div className="mb-1 flex items-center justify-between text-[11px] text-muted-foreground">
        <span>權益曲線（起始基準 100，未複利、單筆%直接加總）</span>
        <span className="font-mono" style={{ color: tone }}>
          {values[values.length - 1] >= values[0] ? "+" : ""}
          {(values[values.length - 1] - values[0]).toFixed(1)}%
        </span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-32 w-full md:h-40" preserveAspectRatio="none">
        <line x1="0" x2={width} y1={baselineY} y2={baselineY} stroke="var(--border)" strokeWidth="1" strokeDasharray="4 4" />
        <polyline points={points} fill="none" stroke={tone} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      </svg>
    </div>
  )
}
