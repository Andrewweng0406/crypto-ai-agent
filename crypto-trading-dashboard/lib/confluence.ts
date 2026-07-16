// 多因子共振綜合判斷引擎（Confluence Judgment Engine）
//
// 純前端運算層，不動後端——把已經各自獨立呈現的 GEX / ORB / RVOL / 大盤濾網 /
// 期權大單流，收斂成單一標的的「現在是助漲、助跌、還是主力壓制」判斷。輸入的
// orb/gex 允許各自為 null（因為期權自選清單跟美股ORB自選清單是兩份獨立管理的
// 清單，同一檔標的不一定兩邊都有追蹤），引擎會用現有的因子盡量判斷，缺得越多、
// 信心分數天花板越低。
//
// Gamma 臨界點（gammaFlipStrike）以上＝做市商淨多Gamma、避險行為傾向壓抑波動
// （偏向助漲/區間頂部有壓力）；以下＝做市商淨空Gamma、避險行為傾向放大波動
// （偏向助跌）——定義見 gex_engine.py 的 find_gamma_flip_point() 註解，這裡的
// 方向判斷跟後端算 Gamma 臨界點用的是同一套慣例。

import type { OptionsGexData, OrbMonitoring, WhaleSweepItem } from "./signals"

export type ConfluenceTrend =
  | "強烈看多"
  | "強烈看空"
  | "波段看多"
  | "波段看空"
  | "高位震盪"
  | "低位震盪"
  | "等待量能確認"
  | "數據不足"

export interface ConfluenceInput {
  symbol: string
  currentPrice: number | null
  orb: OrbMonitoring | null
  gex: OptionsGexData | null
  /** 已預先篩選成同一檔標的、時間夠新的大單流；可以是空陣列。 */
  recentSweeps: WhaleSweepItem[]
}

export interface ConfluenceResult {
  symbol: string
  trendStatus: ConfluenceTrend
  confidenceScore: number
  actionAdvice: string
  supportResistance: {
    support: number | null
    supportSource: string | null
    resistance: number | null
    resistanceSource: string | null
  }
}

// 對齊後端 main.py 的 ORB_RVOL_MULT——同一套「量能確認」門檻，不能各自訂一套。
const ORB_RVOL_CONFIRM_MULT = 3.5

// 大單流只看最近這個時間窗內觸發的——太舊的sweep不該還在影響現在的判斷。
const SWEEP_LOOKBACK_MS = 15 * 60 * 1000
const SWEEP_CONFIDENCE_ADJUST = 12
const MAX_CONFIDENCE = 95
const MIN_CONFIDENCE = 5

function findGexWalls(gex: OptionsGexData, currentPrice: number) {
  let callWall: { strike: number; netGex: number } | null = null
  let putWall: { strike: number; netGex: number } | null = null
  for (const p of gex.points) {
    if (p.strike > currentPrice) {
      if (callWall === null || p.netGex > callWall.netGex) callWall = { strike: p.strike, netGex: p.netGex }
    } else if (p.strike < currentPrice) {
      if (putWall === null || p.netGex < putWall.netGex) putWall = { strike: p.strike, netGex: p.netGex }
    }
  }
  return { callWall, putWall }
}

function resolveSupportResistance(
  currentPrice: number | null,
  orb: OrbMonitoring | null,
  gex: OptionsGexData | null,
): ConfluenceResult["supportResistance"] {
  const empty = { support: null, supportSource: null, resistance: null, resistanceSource: null }
  if (currentPrice === null) return empty

  const resistanceCandidates: { price: number; source: string }[] = []
  const supportCandidates: { price: number; source: string }[] = []

  if (orb?.openingHigh !== null && orb?.openingHigh !== undefined && orb.openingHigh > currentPrice) {
    resistanceCandidates.push({ price: orb.openingHigh, source: "ORB 高點" })
  }
  if (orb?.openingLow !== null && orb?.openingLow !== undefined && orb.openingLow < currentPrice) {
    supportCandidates.push({ price: orb.openingLow, source: "ORB 低點" })
  }

  if (gex?.hasData) {
    const { callWall, putWall } = findGexWalls(gex, currentPrice)
    if (callWall) resistanceCandidates.push({ price: callWall.strike, source: `GEX Call Wall $${callWall.strike}` })
    if (putWall) supportCandidates.push({ price: putWall.strike, source: `GEX Put Wall $${putWall.strike}` })
  }

  // 取離現價最近的那一關（第一個真的會撞到的關卡），不是最極端的那一個。
  resistanceCandidates.sort((a, b) => a.price - b.price)
  supportCandidates.sort((a, b) => b.price - a.price)

  const resistance = resistanceCandidates[0] ?? null
  const support = supportCandidates[0] ?? null

  return {
    resistance: resistance?.price ?? null,
    resistanceSource: resistance?.source ?? null,
    support: support?.price ?? null,
    supportSource: support?.source ?? null,
  }
}

/** 淨大單方向：正值＝偏多資金（買Call），負值＝偏空資金（買Put）。只計入主動買方
 *  （side==="buy"）——賣方報價的sweep方向性不明確，不適合拿來當方向指標。 */
function netSweepBiasUsd(sweeps: WhaleSweepItem[], now: number): number {
  let bias = 0
  for (const s of sweeps) {
    const age = now - new Date(s.triggeredAt).getTime()
    if (age > SWEEP_LOOKBACK_MS || age < 0) continue
    if (s.side !== "buy") continue
    bias += s.optionType === "call" ? s.premiumUsd : -s.premiumUsd
  }
  return bias
}

export function calculateMarketTrend(input: ConfluenceInput): ConfluenceResult {
  const { symbol, currentPrice, orb, gex, recentSweeps } = input
  const supportResistance = resolveSupportResistance(currentPrice, orb, gex)

  if (currentPrice === null || (orb === null && gex === null)) {
    const missing = [
      currentPrice === null && "現價",
      orb === null && "ORB監控",
      gex === null && "GEX資料",
    ]
      .filter(Boolean)
      .join("、")
    return {
      symbol,
      trendStatus: "數據不足",
      confidenceScore: 0,
      actionAdvice: `${symbol} 缺少關鍵資料（${missing}），無法產生共振判斷。`,
      supportResistance,
    }
  }

  const hasOrb = orb !== null
  const hasGex = gex !== null && gex.hasData && gex.gammaFlipStrike !== null

  const brokeAbove = hasOrb && orb.openingHigh !== null && currentPrice > orb.openingHigh
  const brokeBelow = hasOrb && orb.openingLow !== null && currentPrice < orb.openingLow
  const aboveGexFlip = hasGex && currentPrice > gex!.gammaFlipStrike!
  const belowGexFlip = hasGex && currentPrice < gex!.gammaFlipStrike!
  const regimeBullish = hasOrb && orb.marketRegime === "Bullish"
  const regimeBearish = hasOrb && orb.marketRegime === "Bearish"
  const volConfirmed = hasOrb && orb.rvol !== null && orb.rvol >= ORB_RVOL_CONFIRM_MULT

  let trendStatus: ConfluenceTrend
  let confidenceScore: number
  let actionAdvice: string

  if ((brokeAbove || brokeBelow) && !volConfirmed) {
    // 使用者明確要求的最高優先權規則：只要價格已破位但量能沒跟上，一律先標成
    // 「等待量能確認」，不管其他因子看起來多共振，避免使用者被沒有量能背書的
    // 假突破騙進場。
    trendStatus = "等待量能確認"
    confidenceScore = 40
    const dir = brokeAbove ? "突破開盤高點" : "跌破開盤低點"
    const rvolText = orb?.rvol !== null && orb?.rvol !== undefined ? `${orb.rvol.toFixed(1)}x` : "N/A"
    actionAdvice = `${symbol} 已${dir}，但成交量僅 ${rvolText}（未達 ${ORB_RVOL_CONFIRM_MULT}x 確認門檻），建議先觀察量能是否跟上，不建議在此追價進場。`
  } else {
    // 三個共振因子各自獨立判斷方向：大盤濾網、ORB突破、GEX臨界點位置。
    const bullCount = [regimeBullish, brokeAbove, aboveGexFlip].filter(Boolean).length
    const bearCount = [regimeBearish, brokeBelow, belowGexFlip].filter(Boolean).length

    if (bullCount === 3) {
      trendStatus = "強烈看多"
      confidenceScore = 75
      actionAdvice = `${symbol} 大盤偏多＋站上開盤高點＋處於正Gamma區＋量能確認（RVOL ${orb!.rvol!.toFixed(1)}x），三因子完全共振，屬於助漲格局。`
    } else if (bearCount === 3) {
      trendStatus = "強烈看空"
      confidenceScore = 75
      actionAdvice = `${symbol} 大盤偏空＋跌破開盤低點＋處於負Gamma區＋量能確認（RVOL ${orb!.rvol!.toFixed(1)}x），三因子完全共振，屬於助跌格局。`
    } else if (bullCount === 2) {
      trendStatus = "波段看多"
      confidenceScore = brokeAbove ? 55 : 40
      actionAdvice = brokeAbove
        ? `${symbol} 站上開盤高點且量能確認，但${!regimeBullish ? "大盤濾網未偏多" : "尚未進入正Gamma區"}，共振不完整，可小倉位順勢、嚴設停損。`
        : `${symbol} 大盤偏多且處於正Gamma區，但尚未突破開盤高點，屬於醞釀階段、還沒真正發動。`
    } else if (bearCount === 2) {
      trendStatus = "波段看空"
      confidenceScore = brokeBelow ? 55 : 40
      actionAdvice = brokeBelow
        ? `${symbol} 跌破開盤低點且量能確認，但${!regimeBearish ? "大盤濾網未偏空" : "尚未進入負Gamma區"}，共振不完整，可小倉位順勢、嚴設停損。`
        : `${symbol} 大盤偏空且處於負Gamma區，但尚未跌破開盤低點，屬於醞釀階段、還沒真正發動。`
    } else if (hasGex && aboveGexFlip) {
      trendStatus = "高位震盪"
      confidenceScore = 30
      actionAdvice = `${symbol} 現價在Gamma臨界點之上但尚未突破開盤區間，做市商避險行為容易壓抑波動，注意區間震盪、追高風險較高。`
    } else if (hasGex && belowGexFlip) {
      trendStatus = "低位震盪"
      confidenceScore = 30
      actionAdvice = `${symbol} 現價在Gamma臨界點之下但尚未跌破開盤區間，波動可能被放大，觀察是否醞釀進一步破位。`
    } else if (hasOrb && orb.openingHigh !== null && orb.openingLow !== null) {
      const mid = (orb.openingHigh + orb.openingLow) / 2
      trendStatus = currentPrice >= mid ? "高位震盪" : "低位震盪"
      confidenceScore = 20
      actionAdvice = `${symbol} 目前在開盤區間內整理，尚未形成明確共振，建議觀望。`
    } else {
      trendStatus = "數據不足"
      confidenceScore = 10
      actionAdvice = `${symbol} 可用資料不足以判斷方向（缺少開盤區間或GEX資料），僅供參考。`
    }
  }

  // 大單流信心加權（使用者確認：只調整信心分數，不獨立決定方向）——只在已經有
  // 明確多空方向時才生效，「震盪」「數據不足」狀態此時連方向都還沒確定，大單
  // 流不該替它們決定方向。
  const isBullishState = trendStatus === "強烈看多" || trendStatus === "波段看多"
  const isBearishState = trendStatus === "強烈看空" || trendStatus === "波段看空"
  if (isBullishState || isBearishState) {
    const bias = netSweepBiasUsd(recentSweeps, Date.now())
    if (bias !== 0) {
      const sweepIsBullish = bias > 0
      const agrees = (isBullishState && sweepIsBullish) || (isBearishState && !sweepIsBullish)
      if (agrees) {
        confidenceScore = Math.min(MAX_CONFIDENCE, confidenceScore + SWEEP_CONFIDENCE_ADJUST)
        actionAdvice += " 近期大額期權單方向一致，訊號可信度提升。"
      } else {
        confidenceScore = Math.max(MIN_CONFIDENCE, confidenceScore - SWEEP_CONFIDENCE_ADJUST)
        actionAdvice += " ⚠️ 大單方向與訊號相反，留意主力對作。"
      }
    }
  }

  return { symbol, trendStatus, confidenceScore, actionAdvice, supportResistance }
}
