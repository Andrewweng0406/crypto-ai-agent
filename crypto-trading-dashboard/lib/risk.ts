import { type Signal } from "@/lib/signals"

export type RiskLevel = "low" | "medium" | "high" | "critical"
export type TrustLevel = "live" | "delayed" | "experimental" | "offline"

export interface SignalRiskAssessment {
  level: RiskLevel
  label: string
  decision: string
  stopMovePct: number
  leveragedLossPct: number
  rewardMovePct: number
  leveragedRewardPct: number
  riskRewardRatio: number
  notes: string[]
}

export interface DataTrustItem {
  label: string
  level: TrustLevel
  detail: string
}

export function assessSignalRisk(signal: Signal): SignalRiskAssessment {
  const stopMovePct = Math.abs((signal.entry_price - signal.sl) / signal.entry_price) * 100
  const rewardMovePct = Math.abs((signal.tp - signal.entry_price) / signal.entry_price) * 100
  const leveragedLossPct = stopMovePct * signal.leverage
  const leveragedRewardPct = rewardMovePct * signal.leverage
  const riskRewardRatio = rewardMovePct > 0 && stopMovePct > 0 ? rewardMovePct / stopMovePct : 0
  const notes: string[] = []

  if (signal.leverage >= 10) notes.push("槓桿偏高，新手不應直接照單放大部位。")
  if (leveragedLossPct >= 15) notes.push("打到停損時，倉位損失幅度很大。")
  if (riskRewardRatio < 1.5) notes.push("盈虧比不足，沒有明顯補償停損風險。")
  if (signal.smartMoneyNotes.length > 0) notes.push(signal.smartMoneyNotes[0])

  if (leveragedLossPct >= 20 || signal.leverage >= 20) {
    return {
      level: "critical",
      label: "極高風險",
      decision: "不適合新手跟單",
      stopMovePct,
      leveragedLossPct,
      rewardMovePct,
      leveragedRewardPct,
      riskRewardRatio,
      notes,
    }
  }

  if (leveragedLossPct >= 12 || signal.leverage >= 10) {
    return {
      level: "high",
      label: "高風險",
      decision: "只適合小倉位觀察",
      stopMovePct,
      leveragedLossPct,
      rewardMovePct,
      leveragedRewardPct,
      riskRewardRatio,
      notes,
    }
  }

  if (leveragedLossPct >= 6 || signal.leverage >= 5) {
    return {
      level: "medium",
      label: "中等風險",
      decision: "先用風控計算倉位",
      stopMovePct,
      leveragedLossPct,
      rewardMovePct,
      leveragedRewardPct,
      riskRewardRatio,
      notes,
    }
  }

  return {
    level: "low",
    label: "低槓桿風險",
    decision: "仍需設定停損",
    stopMovePct,
    leveragedLossPct,
    rewardMovePct,
    leveragedRewardPct,
    riskRewardRatio,
    notes,
  }
}

export function buildDefaultTrustItems(input: {
  backendConnected: boolean
  hasHistory: boolean
  hasOptionsData: boolean
  hasUSStockData: boolean
}): DataTrustItem[] {
  return [
    {
      label: "交易訊號",
      level: input.backendConnected ? "live" : "offline",
      detail: input.backendConnected ? "後端即時同步" : "後端離線，不顯示替代訊號",
    },
    {
      label: "歷史勝率",
      level: input.hasHistory ? "delayed" : "experimental",
      detail: input.hasHistory ? "使用已結算紀錄統計" : "尚無足夠實盤紀錄",
    },
    {
      label: "期權/GEX",
      level: input.hasOptionsData ? "delayed" : "offline",
      detail: input.hasOptionsData ? "期權鏈每日 OI，加盤中價格重算" : "目前沒有可用期權資料",
    },
    {
      label: "美股 ORB",
      level: input.hasUSStockData ? "experimental" : "offline",
      detail: input.hasUSStockData ? "真實 K 線，但樣本數仍需累積" : "目前沒有可用美股資料",
    },
  ]
}

export function estimatePositionRisk(input: {
  accountSize: number
  riskPct: number
  entry: number
  stop: number
}) {
  const accountRisk = input.accountSize * (input.riskPct / 100)
  const stopMovePct = input.entry > 0 ? Math.abs(input.entry - input.stop) / input.entry : 0
  const positionValue = stopMovePct > 0 ? accountRisk / stopMovePct : 0
  return {
    accountRisk,
    stopMovePct: stopMovePct * 100,
    positionValue,
  }
}
