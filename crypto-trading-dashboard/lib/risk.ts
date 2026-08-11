import {
  type BackendBackgroundJobHealthResponse,
  type BackendDataSourceHealthItem,
  type BackendDataSourceHealthResponse,
  type Signal,
} from "@/lib/signals"

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

const trustedSourceOrder = [
  "crypto_market",
  "meme_radar",
  "meme_trade",
  "us_stock_orb",
  "options_gex",
  "whale_sweep_ingest",
  "liquidation_ingest",
  "news_agent",
  "squeeze_mode",
  "rsi2_meanrev",
  "research_ingest",
]

function trustLevelFromHealth(status: BackendDataSourceHealthItem["status"]): TrustLevel {
  if (status === "ok") return "live"
  if (status === "stale") return "delayed"
  if (status === "starting") return "experimental"
  return "offline"
}

function formatHealthDetail(item: BackendDataSourceHealthItem): string {
  if (item.status === "disabled") return "環境變數未啟用，產品不會顯示替代資料"
  if (item.status === "error") return item.last_error ? `最近失敗：${item.last_error}` : "最近一輪資料源失敗"
  if (item.status === "starting") return "服務已啟動，等待第一輪真實資料"
  if (item.status === "stale") return `最後成功已超過 ${Math.round(item.stale_after_seconds / 60)} 分鐘，請視為延遲資料`

  const latency = item.latency_ms === null ? null : `${Math.round(item.latency_ms)}ms`
  const count = item.records_seen > 0 ? `${item.records_seen} 筆` : "已同步"
  return latency ? `${count}，延遲 ${latency}` : count
}

export function buildTrustItemsFromHealth(response: BackendDataSourceHealthResponse): DataTrustItem[] {
  const ordered = [...response.sources].sort((a, b) => {
    const aIndex = trustedSourceOrder.indexOf(a.source)
    const bIndex = trustedSourceOrder.indexOf(b.source)
    return (aIndex === -1 ? 999 : aIndex) - (bIndex === -1 ? 999 : bIndex)
  })

  return ordered.map((item) => ({
    label: item.label,
    level: trustLevelFromHealth(item.status),
    detail: formatHealthDetail(item),
  }))
}

export function buildBackgroundJobTrustItem(response: BackendBackgroundJobHealthResponse): DataTrustItem {
  if (!response.database_enabled) {
    return {
      label: "背景任務",
      level: "offline",
      detail: "Postgres 未啟用，無法跨 replica 防止重複掃描",
    }
  }

  if (response.jobs.length === 0) {
    return {
      label: "背景任務",
      level: "experimental",
      detail: "租約表尚無紀錄，等待第一輪 scanner heartbeat",
    }
  }

  const expired = response.jobs.filter((job) => job.status === "expired")
  if (expired.length > 0) {
    const names = expired.slice(0, 3).map((job) => job.label).join("、")
    return {
      label: "背景任務",
      level: "offline",
      detail: `${expired.length} 個 scanner 租約過期：${names}`,
    }
  }

  const owners = new Set(response.jobs.map((job) => job.owner_fingerprint))
  return {
    label: "背景任務",
    level: "live",
    detail: `${response.jobs.length} 個 scanner 租約有效，${owners.size} 個執行實例持有`,
  }
}

export function estimatePositionRisk(input: {
  accountSize: number
  riskPct: number
  entry: number
  stop: number
  maxLeverage?: number
}) {
  const accountRisk = input.accountSize * (input.riskPct / 100)
  const stopMovePct = input.entry > 0 ? Math.abs(input.entry - input.stop) / input.entry : 0
  const rawPositionValue = stopMovePct > 0 ? accountRisk / stopMovePct : 0
  const leverageCap = input.accountSize * Math.max(input.maxLeverage ?? Number.POSITIVE_INFINITY, 1)
  const positionValue = Math.min(rawPositionValue, leverageCap)
  return {
    accountRisk,
    stopMovePct: stopMovePct * 100,
    rawPositionValue,
    positionValue,
    requiredLeverage: input.accountSize > 0 ? rawPositionValue / input.accountSize : 0,
    cappedByLeverage: rawPositionValue > leverageCap,
  }
}
