export type Side = "Long" | "Short"

export interface Signal {
  symbol: string
  side: Side
  current_price: number
  entry_price: number
  leverage: number
  tp: number
  sl: number
  timestamp: string
  smartMoneyNotes: string[]
}

export type HistoryOutcome = "Hit TP" | "Hit SL"

export interface HistorySignal {
  id: string
  symbol: string
  side: Side
  outcome: HistoryOutcome
  pnl: number
  closedAt: string
}

export interface HistoryStats {
  totalTrades: number
  wins: number
  losses: number
  winRatePct: number
}

// ---------------------------------------------------------------------------
// Raw shapes returned by the FastAPI backend (see main.py Pydantic models).
// ---------------------------------------------------------------------------

export interface BackendSignalResponse {
  symbol: string
  status: "OPEN" | "NO_SIGNAL"
  side: Side | null
  entry_price: number | null
  current_price: number | null
  take_profit: number | null
  stop_loss: number | null
  stop_loss_pct: number | null
  leverage: number | null
  risk_reward_ratio: number | null
  opened_at: string | null
  smart_money_notes: string[]
  updated_at: string
  donchian_upper: number | null
  donchian_lower: number | null
  volume_ratio: number | null
  funding_rate: number | null
  top_trader_long_short_ratio: number | null
  smart_money_bias: "Bullish" | "Bearish" | "Neutral" | null
}

export interface BackendHistoryItem {
  symbol: string
  side: Side
  entry_price: number
  exit_price: number
  take_profit: number
  stop_loss: number
  leverage: number
  result: "WIN" | "LOSS"
  pnl_pct: number
  opened_at: string
  closed_at: string
  smart_money_notes: string[]
}

export interface BackendHistoryResponse {
  trades: BackendHistoryItem[]
  stats: {
    total_trades: number
    wins: number
    losses: number
    win_rate_pct: number
  }
}

export type Universe = "major" | "scan"

export interface BackendSignalListResponse {
  universe: Universe
  signals: BackendSignalResponse[]
  updated_at: string | null
  tracked_symbols: string[]
}

// Meme radar is a separate feature from the trading signals above: it has no
// side/TP/SL/leverage, just "this coin's volume just spiked" alerts.
export interface BackendMemeAlert {
  symbol: string
  volume_multiple: number
  price: number
  triggered_at: string
}

// Always present for all MEME_SYMBOLS regardless of alert state — this is
// what lets the tab show "PEPE is at 1.4x, needs 3x" instead of going blank
// the moment nothing is currently spiking.
export interface BackendMemeWatchItem {
  symbol: string
  price: number | null
  volume_multiple: number | null
  updated_at: string | null
}

export interface BackendMemeRadarResponse {
  alerts: BackendMemeAlert[]
  watchlist: BackendMemeWatchItem[]
  updated_at: string | null
}

export interface MemeAlert {
  symbol: string
  volumeMultiple: number
  price: number
  triggeredAt: string
}

export interface MemeWatchItem {
  symbol: string
  price: number | null
  volumeMultiple: number | null
  updatedAt: string | null
}

export function adaptMemeAlerts(raw: BackendMemeRadarResponse): MemeAlert[] {
  return raw.alerts.map((a) => ({
    symbol: a.symbol,
    volumeMultiple: a.volume_multiple,
    price: a.price,
    triggeredAt: a.triggered_at,
  }))
}

export function adaptMemeWatchlist(raw: BackendMemeRadarResponse): MemeWatchItem[] {
  return raw.watchlist.map((w) => ({
    symbol: w.symbol,
    price: w.price,
    volumeMultiple: w.volume_multiple,
    updatedAt: w.updated_at,
  }))
}

// Real OHLCV history for the signal chart — replaces the old deterministic
// pseudo-random walk that was only ever decorative.
export interface BackendCandle {
  timestamp: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface BackendCandlesResponse {
  symbol: string
  timeframe: string
  candles: BackendCandle[]
}

export interface Candle {
  timestamp: number
  o: number
  h: number
  l: number
  c: number
}

export function adaptCandles(raw: BackendCandlesResponse): Candle[] {
  return raw.candles.map((c) => ({
    timestamp: c.timestamp,
    o: c.open,
    h: c.high,
    l: c.low,
    c: c.close,
  }))
}

// Populated whether or not there's an active signal — this is what fills the
// "no active position" screen with something real instead of empty space:
// how close price is to the next breakout, current volume vs the required
// multiple, and the smart-money read (funding rate / top trader ratio).
export interface Monitoring {
  donchianUpper: number | null
  donchianLower: number | null
  volumeRatio: number | null
  fundingRate: number | null
  topTraderRatio: number | null
  bias: "Bullish" | "Bearish" | "Neutral" | null
}

function adaptMonitoring(raw: BackendSignalResponse): Monitoring {
  return {
    donchianUpper: raw.donchian_upper,
    donchianLower: raw.donchian_lower,
    volumeRatio: raw.volume_ratio,
    fundingRate: raw.funding_rate,
    topTraderRatio: raw.top_trader_long_short_ratio,
    bias: raw.smart_money_bias,
  }
}

// A signal API response is either an active trade, or "no active trade right
// now" — the dashboard needs to render each of those states differently, so
// the adapter keeps `status` around instead of forcing a fake Signal shape.
export interface SignalState {
  status: "OPEN" | "NO_SIGNAL"
  symbol: string
  currentPrice: number | null
  updatedAt: string
  signal: Signal | null
  monitoring: Monitoring
}

export function adaptSignal(raw: BackendSignalResponse): SignalState {
  const monitoring = adaptMonitoring(raw)

  if (
    raw.status !== "OPEN" ||
    raw.side === null ||
    raw.entry_price === null ||
    raw.take_profit === null ||
    raw.stop_loss === null ||
    raw.leverage === null
  ) {
    return {
      status: "NO_SIGNAL",
      symbol: raw.symbol,
      currentPrice: raw.current_price,
      updatedAt: raw.updated_at,
      signal: null,
      monitoring,
    }
  }

  return {
    status: "OPEN",
    symbol: raw.symbol,
    currentPrice: raw.current_price,
    updatedAt: raw.updated_at,
    monitoring,
    signal: {
      symbol: raw.symbol,
      side: raw.side,
      current_price: raw.current_price ?? raw.entry_price,
      entry_price: raw.entry_price,
      leverage: raw.leverage,
      tp: raw.take_profit,
      sl: raw.stop_loss,
      timestamp: raw.opened_at ?? raw.updated_at,
      smartMoneyNotes: raw.smart_money_notes ?? [],
    },
  }
}

export function adaptSignalList(raw: BackendSignalListResponse): SignalState[] {
  return raw.signals.map(adaptSignal)
}

export function adaptHistory(raw: BackendHistoryResponse): { trades: HistorySignal[]; stats: HistoryStats } {
  return {
    trades: raw.trades.map((t, i) => ({
      id: `${t.symbol}-${t.closed_at}-${i}`,
      symbol: t.symbol,
      side: t.side,
      outcome: t.result === "WIN" ? "Hit TP" : "Hit SL",
      pnl: t.pnl_pct,
      closedAt: t.closed_at,
    })),
    stats: {
      totalTrades: raw.stats.total_trades,
      wins: raw.stats.wins,
      losses: raw.stats.losses,
      winRatePct: raw.stats.win_rate_pct,
    },
  }
}

// Fallback data shown before the first real API response lands (SWR
// `fallbackData`), so the UI never flashes empty on first paint.
export const fallbackHistory: { trades: HistorySignal[]; stats: HistoryStats } = {
  trades: [
    { id: "h1", symbol: "ETH/USDT:USDT", side: "Long", outcome: "Hit TP", pnl: 42.8, closedAt: "2026-07-07T10:12:00Z" },
    { id: "h2", symbol: "SOL/USDT:USDT", side: "Short", outcome: "Hit SL", pnl: -18.4, closedAt: "2026-07-07T08:47:00Z" },
    { id: "h3", symbol: "BTC/USDT:USDT", side: "Long", outcome: "Hit TP", pnl: 63.1, closedAt: "2026-07-06T22:30:00Z" },
    { id: "h4", symbol: "XRP/USDT:USDT", side: "Short", outcome: "Hit TP", pnl: 27.5, closedAt: "2026-07-06T17:05:00Z" },
    { id: "h5", symbol: "AVAX/USDT:USDT", side: "Long", outcome: "Hit SL", pnl: -12.9, closedAt: "2026-07-06T13:22:00Z" },
  ],
  stats: { totalTrades: 5, wins: 3, losses: 2, winRatePct: 60 },
}

// ---------------------------------------------------------------------------
// 美股 ORB 當沖（獨立模塊，實驗性策略）：跟上面的主流幣/迷因幣完全分開，
// 有自己的開盤區間/RVOL/大盤濾網欄位，OPEN 狀態下的 signal 形狀則刻意沿用
// 跟主流幣一樣的 Signal type，這樣 HeroSignal / PriceLevels / PriceRangeGauge
// 三個既有元件可以直接重用，不用重寫一份。
// ---------------------------------------------------------------------------

export interface BackendUSStockResponse {
  symbol: string
  display_name: string
  status: "OPEN" | "NO_SIGNAL"
  side: Side | null
  entry_price: number | null
  current_price: number | null
  take_profit: number | null
  stop_loss: number | null
  stop_loss_pct: number | null
  leverage: number | null
  risk_reward_ratio: number | null
  opened_at: string | null
  day_change_pct: number | null
  updated_at: string
  opening_high: number | null
  opening_low: number | null
  rvol: number | null
  market_regime: "Bullish" | "Bearish" | "Neutral"
}

export interface BackendUSStockListResponse {
  market_session: "OPEN" | "CLOSED"
  market_regime: "Bullish" | "Bearish" | "Neutral"
  stocks: BackendUSStockResponse[]
  updated_at: string | null
}

// 沒有部位時，前端仍要能畫「離開盤區間邊界多遠」的進度條 + RVOL/大盤濾網卡片，
// 跟主流幣 Monitoring 同樣的「監控快照」精神，只是欄位換成 ORB 專屬的。
export interface OrbMonitoring {
  openingHigh: number | null
  openingLow: number | null
  rvol: number | null
  dayChangePct: number | null
  marketRegime: "Bullish" | "Bearish" | "Neutral"
}

export interface USStockSignalState {
  status: "OPEN" | "NO_SIGNAL"
  symbol: string
  displayName: string
  currentPrice: number | null
  updatedAt: string
  signal: Signal | null
  orbMonitoring: OrbMonitoring
}

function adaptOrbMonitoring(raw: BackendUSStockResponse): OrbMonitoring {
  return {
    openingHigh: raw.opening_high,
    openingLow: raw.opening_low,
    rvol: raw.rvol,
    dayChangePct: raw.day_change_pct,
    marketRegime: raw.market_regime,
  }
}

export function adaptUSStock(raw: BackendUSStockResponse): USStockSignalState {
  const orbMonitoring = adaptOrbMonitoring(raw)

  if (
    raw.status !== "OPEN" ||
    raw.side === null ||
    raw.entry_price === null ||
    raw.take_profit === null ||
    raw.stop_loss === null ||
    raw.leverage === null
  ) {
    return {
      status: "NO_SIGNAL",
      symbol: raw.symbol,
      displayName: raw.display_name,
      currentPrice: raw.current_price,
      updatedAt: raw.updated_at,
      signal: null,
      orbMonitoring,
    }
  }

  return {
    status: "OPEN",
    symbol: raw.symbol,
    displayName: raw.display_name,
    currentPrice: raw.current_price,
    updatedAt: raw.updated_at,
    orbMonitoring,
    signal: {
      symbol: raw.display_name,
      side: raw.side,
      current_price: raw.current_price ?? raw.entry_price,
      entry_price: raw.entry_price,
      leverage: raw.leverage,
      tp: raw.take_profit,
      sl: raw.stop_loss,
      timestamp: raw.opened_at ?? raw.updated_at,
      smartMoneyNotes: [],
    },
  }
}

export function adaptUSStockList(raw: BackendUSStockListResponse): {
  marketSession: "OPEN" | "CLOSED"
  marketRegime: "Bullish" | "Bearish" | "Neutral"
  stocks: USStockSignalState[]
} {
  return {
    marketSession: raw.market_session,
    marketRegime: raw.market_regime,
    stocks: raw.stocks.map(adaptUSStock),
  }
}

export function formatPrice(value: number): string {
  // Market-scan and meme-radar symbols can be sub-$1 (DOGE ~$0.075) or
  // sub-cent (PEPE ~$0.0000027) — a fixed 2-decimal format would round
  // those straight to $0.00 and hide the price entirely, so precision
  // scales with magnitude instead.
  const decimals = value >= 100 ? 2 : value >= 1 ? 4 : value >= 0.01 ? 6 : 8
  return value.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

export function formatTime(iso: string): string {
  // Pinning an explicit timeZone is required for SSR correctness: without it,
  // this resolves to the runtime's local zone, which is UTC on Vercel's
  // server-rendered/prerendered HTML but the visitor's own zone on the
  // client — the mismatched strings trigger a React hydration error.
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Taipei",
  })
}
