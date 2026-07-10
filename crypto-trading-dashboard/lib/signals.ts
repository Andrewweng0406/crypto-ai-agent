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

export type SqueezeTier = "none" | "blue" | "yellow" | "green"

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
  squeeze_tier: SqueezeTier
  squeeze_has_perp_market: boolean
  squeeze_oi_growth_15m_pct: number | null
  squeeze_oi_growth_1h_pct: number | null
  squeeze_rvol: number | null
  squeeze_funding_rate: number | null
}

// 多空情緒擠壓爆破模式（獨立、實驗性模塊，未經回測驗證）共用的欄位形狀，
// 市場掃描（Monitoring）跟迷因雷達（MemeWatchItem）都用同一個 type。
export interface SqueezeInfo {
  tier: SqueezeTier
  hasPerpMarket: boolean
  oiGrowth15mPct: number | null
  oiGrowth1hPct: number | null
  rvol: number | null
  fundingRate: number | null
}

function adaptSqueezeInfo(raw: {
  squeeze_tier: SqueezeTier
  squeeze_has_perp_market: boolean
  squeeze_oi_growth_15m_pct: number | null
  squeeze_oi_growth_1h_pct: number | null
  squeeze_rvol: number | null
  squeeze_funding_rate: number | null
}): SqueezeInfo {
  return {
    tier: raw.squeeze_tier,
    hasPerpMarket: raw.squeeze_has_perp_market,
    oiGrowth15mPct: raw.squeeze_oi_growth_15m_pct,
    oiGrowth1hPct: raw.squeeze_oi_growth_1h_pct,
    rvol: raw.squeeze_rvol,
    fundingRate: raw.squeeze_funding_rate,
  }
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
  change_1h_pct: number | null
  change_24h_pct: number | null
  triggered_at: string
}

// Always present for the current dynamically-ranked watchlist regardless of
// alert state — this is what lets the tab show "PEPE is at 1.4x, needs 3x"
// instead of going blank the moment nothing is currently spiking.
export type MemeResonanceStatus = "confirmed" | "overheated" | "insufficient"

export interface BackendMemeWatchItem {
  symbol: string
  price: number | null
  volume_multiple: number | null
  change_1h_pct: number | null
  change_24h_pct: number | null
  is_trending: boolean
  trending_rank: number | null
  trending_top_streak: number
  resonance_status: MemeResonanceStatus
  last_resonance_summary: string | null
  last_resonance_at: string | null
  updated_at: string | null
  squeeze_tier: SqueezeTier
  squeeze_has_perp_market: boolean
  squeeze_oi_growth_15m_pct: number | null
  squeeze_oi_growth_1h_pct: number | null
  squeeze_rvol: number | null
  squeeze_funding_rate: number | null
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
  change1hPct: number | null
  change24hPct: number | null
  triggeredAt: string
}

export interface MemeWatchItem {
  symbol: string
  price: number | null
  volumeMultiple: number | null
  change1hPct: number | null
  change24hPct: number | null
  isTrending: boolean
  trendingRank: number | null
  trendingTopStreak: number
  resonanceStatus: MemeResonanceStatus
  lastResonanceSummary: string | null
  lastResonanceAt: string | null
  updatedAt: string | null
  squeeze: SqueezeInfo
}

export function adaptMemeAlerts(raw: BackendMemeRadarResponse): MemeAlert[] {
  return raw.alerts.map((a) => ({
    symbol: a.symbol,
    volumeMultiple: a.volume_multiple,
    price: a.price,
    change1hPct: a.change_1h_pct,
    change24hPct: a.change_24h_pct,
    triggeredAt: a.triggered_at,
  }))
}

export function adaptMemeWatchlist(raw: BackendMemeRadarResponse): MemeWatchItem[] {
  return raw.watchlist.map((w) => ({
    symbol: w.symbol,
    price: w.price,
    volumeMultiple: w.volume_multiple,
    change1hPct: w.change_1h_pct,
    change24hPct: w.change_24h_pct,
    isTrending: w.is_trending,
    trendingRank: w.trending_rank,
    trendingTopStreak: w.trending_top_streak,
    resonanceStatus: w.resonance_status,
    lastResonanceSummary: w.last_resonance_summary,
    lastResonanceAt: w.last_resonance_at,
    updatedAt: w.updated_at,
    squeeze: adaptSqueezeInfo(w),
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
  squeeze: SqueezeInfo
}

function adaptMonitoring(raw: BackendSignalResponse): Monitoring {
  return {
    donchianUpper: raw.donchian_upper,
    donchianLower: raw.donchian_lower,
    volumeRatio: raw.volume_ratio,
    fundingRate: raw.funding_rate,
    topTraderRatio: raw.top_trader_long_short_ratio,
    bias: raw.smart_money_bias,
    squeeze: adaptSqueezeInfo(raw),
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

// 已結算的實盤成交紀錄——這是真實累積結果，不是回測，樣本數在累積起來之前
// 沒有統計意義，元件那邊要標註清楚。
export interface BackendUSStockHistoryItem {
  symbol: string
  display_name: string
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
}

export interface BackendUSStockHistoryResponse {
  trades: BackendUSStockHistoryItem[]
  stats: {
    total_trades: number
    wins: number
    losses: number
    win_rate_pct: number
  }
}

export interface USStockHistoryItem {
  id: string
  symbol: string
  displayName: string
  side: Side
  entryPrice: number
  exitPrice: number
  result: "WIN" | "LOSS"
  pnlPct: number
  closedAt: string
}

export function adaptUSStockHistory(raw: BackendUSStockHistoryResponse): {
  trades: USStockHistoryItem[]
  stats: HistoryStats
} {
  return {
    trades: raw.trades.map((t, i) => ({
      id: `${t.symbol}-${t.closed_at}-${i}`,
      symbol: t.symbol,
      displayName: t.display_name,
      side: t.side,
      entryPrice: t.entry_price,
      exitPrice: t.exit_price,
      result: t.result,
      pnlPct: t.pnl_pct,
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

// ---------------------------------------------------------------------------
// AI 智能投研 Agent（獨立模塊，實驗性）：RSS新聞經LLM結構化出標的/摘要/情緒分數，
// 純資訊面板，沒有方向/TP/SL/槓桿，跟迷因雷達同樣是「監控」而不是交易訊號。
// ---------------------------------------------------------------------------

export type NewsCategory = "crypto" | "us_stock"

export interface BackendNewsItem {
  title: string
  url: string
  source: string
  published_at: string
  symbols: string[]
  summary: string
  sentiment_score: number  // -10（極度利空）~ +10（極度利多）
  category: NewsCategory
  processed_at: string
}

export interface BackendNewsAgentResponse {
  items: BackendNewsItem[]
  updated_at: string | null
}

export interface NewsItem {
  title: string
  url: string
  source: string
  symbols: string[]
  summary: string
  sentimentScore: number
  category: NewsCategory
  processedAt: string
}

export function adaptNewsAgent(raw: BackendNewsAgentResponse): NewsItem[] {
  return raw.items.map((item) => ({
    title: item.title,
    url: item.url,
    source: item.source,
    symbols: item.symbols,
    summary: item.summary,
    sentimentScore: item.sentiment_score,
    category: item.category,
    processedAt: item.processed_at,
  }))
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

export function formatClockTime(iso: string): string {
  // HH:MM:SS，給 Squeeze Feed 那種終端機風格的滾動牆用
  return new Date(iso).toLocaleString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "Asia/Taipei",
  })
}

// ---------------------------------------------------------------------------
// 多空情緒擠壓爆破模式（Squeeze Mode，獨立、實驗性模塊）：市場掃描 + 迷因雷達
// 共用同一份 green 燈號事件滾動牆。
// ---------------------------------------------------------------------------

export interface BackendSqueezeFeedItem {
  symbol: string
  oi_growth_1h_pct: number | null
  rvol: number | null
  funding_rate: number | null
  triggered_at: string
}

export interface BackendSqueezeFeedResponse {
  items: BackendSqueezeFeedItem[]
  updated_at: string | null
}

export interface SqueezeFeedItem {
  symbol: string
  oiGrowth1hPct: number | null
  rvol: number | null
  fundingRate: number | null
  triggeredAt: string
}

export function adaptSqueezeFeed(raw: BackendSqueezeFeedResponse): SqueezeFeedItem[] {
  return raw.items.map((item) => ({
    symbol: item.symbol,
    oiGrowth1hPct: item.oi_growth_1h_pct,
    rvol: item.rvol,
    fundingRate: item.funding_rate,
    triggeredAt: item.triggered_at,
  }))
}

// ---------------------------------------------------------------------------
// 📊 期權分析（Options Analytics，獨立、實驗性模塊）：yfinance 期權鏈 ->
// Black-Scholes GEX 計算引擎，找出 Gamma 擠壓臨界點 + 期權大單即時流。
// has_data=false 代表還沒拉到資料，不是「這檔沒有擠壓」，前端要能區分這兩種
// 狀態。yfinance 沒有逐筆成交數據，whale_sweep_supported 恆為 false。
// ---------------------------------------------------------------------------

export interface BackendOptionsGexPoint {
  strike: number
  call_gex: number
  put_gex: number
  net_gex: number
}

export interface BackendOptionsGexResponse {
  symbol: string
  has_data: boolean
  spot_price: number | null
  expiry: string | null
  gamma_flip_strike: number | null
  points: BackendOptionsGexPoint[]
  whale_sweep_supported: boolean | null
  updated_at: string | null
}

export interface BackendOptionsGexListResponse {
  underlyings: BackendOptionsGexResponse[]
  data_source_ok: boolean
  moomoo_online: boolean
  updated_at: string | null
}

export interface OptionsGexPoint {
  strike: number
  callGex: number
  putGex: number
  netGex: number
}

export interface OptionsGexData {
  symbol: string
  hasData: boolean
  spotPrice: number | null
  expiry: string | null
  gammaFlipStrike: number | null
  points: OptionsGexPoint[]
  whaleSweepSupported: boolean | null
  updatedAt: string | null
}

export function adaptOptionsGexList(raw: BackendOptionsGexListResponse): {
  underlyings: OptionsGexData[]
  dataSourceOk: boolean
  moomooOnline: boolean
} {
  return {
    underlyings: raw.underlyings.map((u) => ({
      symbol: u.symbol,
      hasData: u.has_data,
      spotPrice: u.spot_price,
      expiry: u.expiry,
      gammaFlipStrike: u.gamma_flip_strike,
      points: u.points.map((p) => ({ strike: p.strike, callGex: p.call_gex, putGex: p.put_gex, netGex: p.net_gex })),
      whaleSweepSupported: u.whale_sweep_supported,
      updatedAt: u.updated_at,
    })),
    dataSourceOk: raw.data_source_ok,
    moomooOnline: raw.moomoo_online,
  }
}

export interface BackendWhaleSweepItem {
  symbol: string
  strike: number
  expiry: string
  option_type: "call" | "put"
  side: "buy" | "sell" | null
  premium_usd: number
  triggered_at: string
}

export interface BackendWhaleSweepResponse {
  items: BackendWhaleSweepItem[]
  updated_at: string | null
}

export interface WhaleSweepItem {
  symbol: string
  strike: number
  expiry: string
  optionType: "call" | "put"
  side: "buy" | "sell" | null
  premiumUsd: number
  triggeredAt: string
}

export function adaptWhaleSweep(raw: BackendWhaleSweepResponse): WhaleSweepItem[] {
  return raw.items.map((item) => ({
    symbol: item.symbol,
    strike: item.strike,
    expiry: item.expiry,
    optionType: item.option_type,
    side: item.side,
    premiumUsd: item.premium_usd,
    triggeredAt: item.triggered_at,
  }))
}

// ---------------------------------------------------------------------------
// 🔥 迷因幣1H爆量當沖（正式實盤，獨立模塊）：只有 WIF/DOGE 兩檔——180天回測裡
// 唯二樣本數跨過統計門檻的幣種。跟純警報用的迷因雷達完全不同，這裡有方向/
// TP/SL/槓桿，OPEN 狀態沿用跟主流幣一樣的 Signal type，可以直接重用
// HeroSignal/PriceLevels/PriceRangeGauge 三個既有元件。
// ---------------------------------------------------------------------------

export interface BackendMemeTradeResponse {
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
  updated_at: string | null
}

export interface BackendMemeTradeListResponse {
  coins: BackendMemeTradeResponse[]
  updated_at: string | null
}

export interface MemeTradeState {
  status: "OPEN" | "NO_SIGNAL"
  symbol: string
  displayName: string
  currentPrice: number | null
  updatedAt: string | null
  signal: Signal | null
}

export function adaptMemeTrade(raw: BackendMemeTradeResponse): MemeTradeState {
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
    }
  }

  return {
    status: "OPEN",
    symbol: raw.symbol,
    displayName: raw.display_name,
    currentPrice: raw.current_price,
    updatedAt: raw.updated_at,
    signal: {
      symbol: raw.display_name,
      side: raw.side,
      current_price: raw.current_price ?? raw.entry_price,
      entry_price: raw.entry_price,
      leverage: raw.leverage,
      tp: raw.take_profit,
      sl: raw.stop_loss,
      timestamp: raw.opened_at ?? raw.updated_at ?? new Date().toISOString(),
      smartMoneyNotes: [],
    },
  }
}

export function adaptMemeTradeList(raw: BackendMemeTradeListResponse): MemeTradeState[] {
  return raw.coins.map(adaptMemeTrade)
}

export interface BackendMemeTradeHistoryItem {
  symbol: string
  display_name: string
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
}

export interface BackendMemeTradeHistoryResponse {
  trades: BackendMemeTradeHistoryItem[]
  stats: {
    total_trades: number
    wins: number
    losses: number
    win_rate_pct: number
  }
}

export function adaptMemeTradeHistory(raw: BackendMemeTradeHistoryResponse): {
  trades: USStockHistoryItem[]
  stats: HistoryStats
} {
  return {
    trades: raw.trades.map((t, i) => ({
      id: `${t.symbol}-${t.closed_at}-${i}`,
      symbol: t.symbol,
      displayName: t.display_name,
      side: t.side,
      entryPrice: t.entry_price,
      exitPrice: t.exit_price,
      result: t.result,
      pnlPct: t.pnl_pct,
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

// ---------------------------------------------------------------------------
// 💬 AI副官0-token戰況跑馬燈：純字串模板（後端組合，不是LLM輸出），觸發源是
// 迷因當沖新訊號跟期權大單。點擊跑馬燈才會把訊息送進 /api/chat 真的觸發LLM。
// ---------------------------------------------------------------------------

export type AssistantBroadcastKind = "meme_trade" | "whale_sweep"

export interface BackendAssistantBroadcastItem {
  id: string
  message: string
  symbol: string
  kind: AssistantBroadcastKind
  triggered_at: string
}

export interface BackendAssistantBroadcastResponse {
  items: BackendAssistantBroadcastItem[]
  updated_at: string | null
}

export interface AssistantBroadcastItem {
  id: string
  message: string
  symbol: string
  kind: AssistantBroadcastKind
  triggeredAt: string
}

export function adaptAssistantBroadcasts(raw: BackendAssistantBroadcastResponse): AssistantBroadcastItem[] {
  return raw.items.map((item) => ({
    id: item.id,
    message: item.message,
    symbol: item.symbol,
    kind: item.kind,
    triggeredAt: item.triggered_at,
  }))
}

export function formatCompactUsd(value: number): string {
  // 例："$1.24M" / "$850K"，給 GEX 數值/大單權利金這種大數字用，避免顯示一長串0
  const sign = value < 0 ? "-" : ""
  const abs = Math.abs(value)
  if (abs >= 1_000_000_000) return `${sign}$${(abs / 1_000_000_000).toFixed(2)}B`
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(1)}K`
  return `${sign}$${abs.toFixed(0)}`
}
