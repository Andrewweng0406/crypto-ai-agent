"use client"

import { useMemo, useState } from "react"
import { Rocket, RefreshCw } from "lucide-react"
import { cn } from "@/lib/utils"
import {
  adaptBacktestResult,
  adaptStockWalkForwardResult,
  adaptWalkForwardResult,
  type BacktestResult,
  type BacktestStrategy,
  type BackendBacktestResponse,
  type BackendStockWalkForwardResponse,
  type BackendWalkForwardResponse,
  type StockWalkForwardResult,
  type WalkForwardResult,
} from "@/lib/signals"

// 四個策略各自對應「已知真的有真實歷史資料源、也真的驗證過」的標的清單，不開放
// 自由輸入任意代號——避免使用者打錯字/打進系統沒在追蹤的標的，白白浪費一次限流
// 額度換來一個502。supertrend_btc_long 只有BTC一檔，見後端SUPERTREND_CAVEAT說明：
// 2026-07-11完整調查只有「只做多、僅BTCUSDT」版本通過樣本外驗證。
const STRATEGY_SYMBOLS: Record<BacktestStrategy, string[]> = {
  crypto_donchian_4h: ["BTC", "ETH", "SOL"],
  meme_volume_spike: ["WIF", "DOGE", "PEPE", "SHIB", "BONK"],
  us_stock_orb: ["NVDA", "TSLA", "SPY", "SMCI", "SPCX"],
  supertrend_btc_long: ["BTC"],
  stock_rsi2_meanrev: ["NVDA", "GOOGL", "META", "AAPL"], // MSFT已於2026-07-12移除（樣本外最新一季勝率崩到16.7%），見後端 STOCK_MEANREV_SYMBOLS 說明
}

const STRATEGY_LABELS: Record<BacktestStrategy, string> = {
  crypto_donchian_4h: "4H 唐奇安突破（主流幣）",
  meme_volume_spike: "1H 爆量當沖（迷因幣）",
  us_stock_orb: "開盤區間突破（美股ORB）",
  supertrend_btc_long: "SuperTrend 爆量狙擊手（只做多，僅BTC）",
  stock_rsi2_meanrev: "RSI(2) 均值回歸（高勝率，僅美股）",
}

const STRATEGY_MAX_DAYS: Record<BacktestStrategy, number> = {
  crypto_donchian_4h: 180,
  meme_volume_spike: 180,
  us_stock_orb: 60, // yfinance 15分鐘K線真實上限，見後端 BACKTEST_YF_MAX_DAYS 說明
  supertrend_btc_long: 180,
  stock_rsi2_meanrev: 365 * 7, // 日線策略需要好幾年歷史，見後端 STOCK_MEANREV_MAX_DAYS_RANGE 說明
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

const walkForwardFetcher = async (): Promise<BackendWalkForwardResponse> => {
  const res = await fetch("/api/backtest/walk-forward", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  })
  const json = await res.json()
  if (!res.ok) throw new Error(json?.detail ?? `請求失敗（${res.status}）`)
  return json
}

const stockWalkForwardFetcher = async (symbol: string): Promise<BackendStockWalkForwardResponse> => {
  const res = await fetch(`/api/backtest/stock-walk-forward?symbol=${encodeURIComponent(symbol)}`, {
    method: "POST",
  })
  const json = await res.json()
  if (!res.ok) throw new Error(json?.detail ?? `請求失敗（${res.status}）`)
  return json
}

// 📊 網頁端回測沙盒：把 backtest_optimizer.py 已經驗證過的邏輯搬上正式站台，
// 只支援三個有真實歷史資料源的策略。公開端點，後端有IP限流（15次/小時）
// 防止被用來刷爆外部交易所/yfinance API額度。
export function BacktestSandboxPanel() {
  const [strategy, setStrategy] = useState<BacktestStrategy>("crypto_donchian_4h")
  const [symbol, setSymbol] = useState<string>(STRATEGY_SYMBOLS.crypto_donchian_4h[0])
  const [daysRange, setDaysRange] = useState<number>(30)
  const [stLength, setStLength] = useState<number>(10)
  const [stMultiplier, setStMultiplier] = useState<number>(3.0)
  const [stRiskReward, setStRiskReward] = useState<number>(4.0)
  const [mode, setMode] = useState<"single" | "walk_forward">("single")
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [wfResult, setWfResult] = useState<WalkForwardResult | null>(null)
  const [stockWfResult, setStockWfResult] = useState<StockWalkForwardResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const availableSymbols = STRATEGY_SYMBOLS[strategy]
  const maxDays = STRATEGY_MAX_DAYS[strategy]
  const isSupertrend = strategy === "supertrend_btc_long"
  const isStockMeanrev = strategy === "stock_rsi2_meanrev"
  const hasWalkForward = isSupertrend || isStockMeanrev

  const handleStrategyChange = (next: BacktestStrategy) => {
    setStrategy(next)
    setSymbol(STRATEGY_SYMBOLS[next][0])
    setDaysRange((prev) => Math.min(prev, STRATEGY_MAX_DAYS[next]))
    setMode("single")
    setResult(null)
    setWfResult(null)
    setStockWfResult(null)
    setError(null)
  }

  const runBacktest = async () => {
    setIsLoading(true)
    setError(null)
    setResult(null)
    setWfResult(null)
    try {
      const raw = await fetcher("/api/backtest", {
        symbol,
        strategy_name: strategy,
        days_range: daysRange,
        ...(isSupertrend
          ? { st_length: stLength, st_multiplier: stMultiplier, st_risk_reward: stRiskReward }
          : {}),
      })
      setResult(adaptBacktestResult(raw))
    } catch (err) {
      setError(err instanceof Error ? err.message : "回測請求失敗")
    } finally {
      setIsLoading(false)
    }
  }

  const runWalkForward = async () => {
    setIsLoading(true)
    setError(null)
    setResult(null)
    setWfResult(null)
    setStockWfResult(null)
    try {
      if (isStockMeanrev) {
        const raw = await stockWalkForwardFetcher(symbol)
        setStockWfResult(adaptStockWalkForwardResult(raw))
      } else {
        const raw = await walkForwardFetcher()
        setWfResult(adaptWalkForwardResult(raw))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "滾動式驗證請求失敗")
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

      {/* 單次回測 vs 滾動式Walk-Forward驗證模式切換（SuperTrend/RSI2均值回歸專屬） */}
      {hasWalkForward && (
        <div className="flex flex-col gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">驗證模式</span>
          <div className="flex w-fit gap-1 rounded-full border border-border/60 bg-secondary/30 p-1">
            {(
              [
                { key: "single" as const, label: "單次回測" },
                { key: "walk_forward" as const, label: "🔁 滾動式Walk-Forward" },
              ]
            ).map((m) => (
              <button
                key={m.key}
                type="button"
                onClick={() => {
                  setMode(m.key)
                  setResult(null)
                  setWfResult(null)
                  setError(null)
                }}
                className={cn(
                  "rounded-full px-3.5 py-1.5 text-xs font-semibold transition-colors",
                  mode === m.key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {mode === "single" ? (
        <>
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

          {isSupertrend && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="flex flex-col gap-2">
                <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  SuperTrend Length
                </span>
                <input
                  type="number" min={3} max={50} value={stLength}
                  onChange={(e) => setStLength(Number(e.target.value))}
                  className="rounded-xl border border-border/60 bg-background px-3 py-2 font-mono text-sm outline-none focus:border-primary/60"
                />
              </div>
              <div className="flex flex-col gap-2">
                <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Multiplier</span>
                <input
                  type="number" min={1} max={6} step={0.5} value={stMultiplier}
                  onChange={(e) => setStMultiplier(Number(e.target.value))}
                  className="rounded-xl border border-border/60 bg-background px-3 py-2 font-mono text-sm outline-none focus:border-primary/60"
                />
              </div>
              <div className="flex flex-col gap-2">
                <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Risk:Reward</span>
                <input
                  type="number" min={1.5} max={6} step={0.5} value={stRiskReward}
                  onChange={(e) => setStRiskReward(Number(e.target.value))}
                  className="rounded-xl border border-border/60 bg-background px-3 py-2 font-mono text-sm outline-none focus:border-primary/60"
                />
              </div>
            </div>
          )}

          <button
            type="button"
            onClick={runBacktest}
            disabled={isLoading}
            className="flex items-center justify-center gap-2 rounded-xl bg-primary py-3 text-sm font-bold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            <Rocket className={cn("size-4", isLoading && "animate-pulse")} aria-hidden="true" />
            {isLoading ? "回測執行中…（真實抓取歷史資料，可能需要數秒到數十秒）" : "開始優化回測"}
          </button>
        </>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            {isStockMeanrev
              ? "把整段~7年日線資料切成全期間/前50%/後50%/Q1-Q4四季，用同一組固定邏輯跑（沒有重新搜參數），檢查勝率是否每個時間切片都撐得住，不能自訂天數。"
              : "固定跑同一套方法論：12個月訓練窗+4個月測試窗一起往前滑動，每一折都只在該折訓練窗上重新網格搜尋最佳參數，套進該折測試窗（全新起始資金）算出樣本外表現——跟單次回測是完全不同層次的驗證，不能自訂參數/天數。"}
            {" "}單次請求約需15-25秒。
          </p>
          <button
            type="button"
            onClick={runWalkForward}
            disabled={isLoading}
            className="flex items-center justify-center gap-2 rounded-xl bg-primary py-3 text-sm font-bold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            <RefreshCw className={cn("size-4", isLoading && "animate-spin")} aria-hidden="true" />
            {isLoading ? "滾動式驗證執行中…（約15-25秒，請耐心等候）" : "執行滾動式驗證"}
          </button>
        </>
      )}

      {error && (
        <div className="flex items-start gap-1.5 rounded-lg border border-short/30 bg-short/[0.06] px-3 py-2 text-xs text-short">
          {error}
        </div>
      )}

      {isLoading && <BacktestSkeleton />}

      {result && !isLoading && <BacktestResultView result={result} />}
      {wfResult && !isLoading && <WalkForwardResultView result={wfResult} />}
      {stockWfResult && !isLoading && <StockWalkForwardResultView result={stockWfResult} />}
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
          樣本數僅 {result.totalTrades} 筆（門檻15筆），這組數字統計上不具意義，不能拿來下結論。
        </div>
      )}
      {result.daysRangeUsed < result.daysRangeRequested && (
        <p className="text-xs text-muted-foreground">
          ⚠️ 你要求 {result.daysRangeRequested} 天，但 {result.dataSource} 真實上限只到 {result.daysRangeUsed}{" "}
          天，已自動夾住（不是模擬資料）。
        </p>
      )}
      {result.strategyCaveat && (
        <div className="flex items-start gap-1.5 rounded-lg border border-amber-400/30 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-200">
          {result.strategyCaveat}
        </div>
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

function WalkForwardResultView({ result }: { result: WalkForwardResult }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start gap-1.5 rounded-lg border border-amber-400/30 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-200">
        {result.caveat}
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatTile
          label="樣本外獲利折數"
          value={`${result.oosProfitableFolds}/${result.oosTotalFolds}`}
          tone={result.oosProfitableFolds / result.oosTotalFolds >= 0.5 ? "long" : "short"}
        />
        <StatTile
          label="平均樣本外報酬"
          value={`${result.oosAvgReturnPct >= 0 ? "+" : ""}${result.oosAvgReturnPct.toFixed(2)}%`}
          tone={result.oosAvgReturnPct >= 0 ? "long" : "short"}
        />
        <StatTile
          label="複利串接報酬（整段期間）"
          value={`${result.oosCompoundedReturnPct >= 0 ? "+" : ""}${result.oosCompoundedReturnPct.toFixed(2)}%`}
          tone={result.oosCompoundedReturnPct >= 0 ? "long" : "short"}
        />
        <StatTile label="總折數" value={String(result.oosTotalFolds)} />
      </div>

      <div className="overflow-x-auto rounded-xl border border-border/60">
        <table className="w-full min-w-[640px] font-mono text-xs">
          <thead>
            <tr className="border-b border-border/60 bg-secondary/30 text-left text-muted-foreground">
              <th className="px-3 py-2 font-medium">Fold</th>
              <th className="px-3 py-2 font-medium">測試期間</th>
              <th className="px-3 py-2 font-medium">參數 (L/M/RR)</th>
              <th className="px-3 py-2 text-right font-medium">策略報酬</th>
              <th className="px-3 py-2 text-right font-medium">買入持有</th>
              <th className="px-3 py-2 text-right font-medium">交易數</th>
            </tr>
          </thead>
          <tbody>
            {result.folds.map((f) => (
              <tr key={f.fold} className="border-b border-border/40 last:border-0">
                <td className="px-3 py-2">{f.fold}</td>
                <td className="px-3 py-2 text-muted-foreground">{f.testRange}</td>
                <td className="px-3 py-2 text-muted-foreground">
                  {f.stLength}/{f.stMultiplier}/{f.stRiskReward}
                </td>
                <td className={cn("px-3 py-2 text-right font-semibold", f.testReturnPct >= 0 ? "text-long" : "text-short")}>
                  {f.testReturnPct >= 0 ? "+" : ""}
                  {f.testReturnPct.toFixed(2)}%
                </td>
                <td className="px-3 py-2 text-right text-muted-foreground">
                  {f.testBuyHoldPct >= 0 ? "+" : ""}
                  {f.testBuyHoldPct.toFixed(2)}%
                </td>
                <td className="px-3 py-2 text-right text-muted-foreground">{f.testNTrades}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {result.folds.some((f) => f.testNTrades < 15) && (
        <p className="text-xs text-muted-foreground">
          ⚠️ 部分折的交易數低於15筆統計門檻，單一折的數字本身統計力道不足，真正有意義的是「多折方向是否一致」，
          不是任何一折的精確數字。
        </p>
      )}
    </div>
  )
}

function StockWalkForwardResultView({ result }: { result: StockWalkForwardResult }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start gap-1.5 rounded-lg border border-amber-400/30 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-200">
        {result.caveat}
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-2">
        <StatTile
          label="四季度是否全數過關（勝率≥50%）"
          value={result.allQuartersPass50Pct ? "✅ 全數通過" : "⚠️ 有季度不過關"}
          tone={result.allQuartersPass50Pct ? "long" : "short"}
        />
        <StatTile
          label="最低單季勝率"
          value={`${result.minQuarterWinRate.toFixed(1)}%`}
          tone={result.minQuarterWinRate >= 50 ? "long" : "short"}
        />
      </div>

      <div className="overflow-x-auto rounded-xl border border-border/60">
        <table className="w-full min-w-[600px] font-mono text-xs">
          <thead>
            <tr className="border-b border-border/60 bg-secondary/30 text-left text-muted-foreground">
              <th className="px-3 py-2 font-medium">切片</th>
              <th className="px-3 py-2 font-medium">期間</th>
              <th className="px-3 py-2 text-right font-medium">交易數</th>
              <th className="px-3 py-2 text-right font-medium">勝率</th>
              <th className="px-3 py-2 text-right font-medium">總報酬</th>
              <th className="px-3 py-2 text-right font-medium">獲利因子</th>
            </tr>
          </thead>
          <tbody>
            {result.folds.map((f) => (
              <tr key={f.fold} className="border-b border-border/40 last:border-0">
                <td className="px-3 py-2 font-semibold">{f.fold}</td>
                <td className="px-3 py-2 text-muted-foreground">
                  {f.start} ~ {f.end}
                </td>
                <td className="px-3 py-2 text-right text-muted-foreground">{f.totalTrades}</td>
                <td className={cn("px-3 py-2 text-right font-semibold", f.winRate >= 50 ? "text-long" : "text-short")}>
                  {f.winRate.toFixed(1)}%
                </td>
                <td className={cn("px-3 py-2 text-right", f.totalReturnPct >= 0 ? "text-long" : "text-short")}>
                  {f.totalReturnPct >= 0 ? "+" : ""}
                  {f.totalReturnPct.toFixed(2)}%
                </td>
                <td className="px-3 py-2 text-right text-muted-foreground">{f.profitFactor.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function StatTile({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "long" | "short" | "neutral" }) {
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

export function WinRateRing({ winRate }: { winRate: number }) {
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

export function EquityCurveChart({ equityCurve, isProfitable }: { equityCurve: number[]; isProfitable: boolean }) {
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
