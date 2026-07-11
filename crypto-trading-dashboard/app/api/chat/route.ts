import Anthropic from "@anthropic-ai/sdk"
import type { MessageParam, Tool, ToolResultBlockParam } from "@anthropic-ai/sdk/resources/messages"

// 💬 AI 交易軍師助理：右下角常駐聊天機器人的後端。直接呼叫 Anthropic Claude
// API（不經過 FastAPI 後端做串流轉發），因為串流回應在 Next.js 這一層做
// 最直接。但要回答「真實盤面數據」的問題，光靠 system prompt 要求它「表現
// 得很專業」是不夠的——它連你的後端長怎樣都不知道。這裡用 Claude 的工具
// 呼叫（tool use）讓它能實際打你自己 FastAPI 後端既有的 API，回答時引用
// 真實數字，不會叫使用者自己去外面找資料。
//
// 模型：使用者原本指定 "claude-3-5-sonnet"，這是舊版模型代號，2026年現在
// 應該用 "claude-sonnet-5"（見系統當前可用模型列表），照舊代號打會直接
// 打不通，這裡改用新的。
const MODEL = "claude-sonnet-5"
const MAX_TOKENS = 1536
const MAX_HISTORY_MESSAGES = 20 // 只送最近N則，避免對話一長，每次呼叫的成本跟著無限膨脹
const MAX_MESSAGE_CHARS = 4000 // 單則訊息長度上限，防止異常超長輸入炸掉 token 用量
const MAX_TOOL_ROUNDS = 4 // 防止模型陷入無限工具呼叫迴圈，超過這個回合數強制收斂成文字回答

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

// ---------------------------------------------------------------------------
// IP 限流：每個 IP 每小時最多 RATE_LIMIT_MAX_REQUESTS 次，防止公開端點被刷爆
// token 額度。⚠️ 誠實聲明：這是 in-memory Map，只在單一 serverless 執行個體
// 的生命週期內有效——Vercel 可能同時起多個執行個體處理不同請求，冷啟動也會
// 讓計數歸零，所以這不是精確、跨個體一致的限流，是「多一層基本防護」而不是
// 密不透風的保證。真的要做到精確全域限流需要外部儲存（Redis/Vercel KV），
// 目前流量規模用不到那個複雜度。
// ---------------------------------------------------------------------------
const RATE_LIMIT_MAX_REQUESTS = 15
const RATE_LIMIT_WINDOW_MS = 60 * 60 * 1000 // 1小時
const RATE_LIMIT_MAX_TRACKED_IPS = 5000 // 防止長時間warm的執行個體累積過多不同IP造成記憶體無限成長

const requestLog = new Map<string, number[]>()

function getClientIp(req: Request): string {
  const forwarded = req.headers.get("x-forwarded-for")
  if (forwarded) return forwarded.split(",")[0].trim()
  return req.headers.get("x-real-ip") ?? "unknown"
}

function isRateLimited(ip: string): boolean {
  const now = Date.now()
  const timestamps = (requestLog.get(ip) ?? []).filter((t) => now - t < RATE_LIMIT_WINDOW_MS)

  if (timestamps.length >= RATE_LIMIT_MAX_REQUESTS) {
    requestLog.set(ip, timestamps)
    return true
  }

  timestamps.push(now)
  if (requestLog.size >= RATE_LIMIT_MAX_TRACKED_IPS && !requestLog.has(ip)) {
    requestLog.clear() // 簡單粗暴的防護：追蹤的IP數量失控時直接清空重來，不值得為此引入LRU
  }
  requestLog.set(ip, timestamps)
  return false
}

const SYSTEM_PROMPT_BASE = `你是「Weng Crypto」交易終端內建的 AI 交易軍師助理，服務對象是主動交易者。

【天條一：無所不知的市場百科】
只要對話涉及加密貨幣、美股、股票期權三大市場的數據（OI未平倉量、RVOL相對成交量、資金費率、爆倉單、GEX曝險等），你必須以極度專業、硬核的姿態全力解答，展現量化與盤面判讀的深度。你可以呼叫提供的工具，直接查詢本終端自己系統裡的即時數據（期權GEX、交易訊號、聰明錢、Squeeze燈號、迷因雷達、迷因當沖實盤、美股ORB、新聞情緒、爆倉密度清算牆），也可以即時執行真實歷史回測（run_backtest，僅限crypto_donchian_1h/meme_volume_spike/us_stock_orb三個策略，注意這個工具有IP限流、樣本數<15筆時務必明講不具統計意義），回答時優先引用這些真實數字，不要叫使用者自己去外部網站查。工具查不到（例如非交易時段沒資料、後端連不上）時要老實說明，不要編造數字。

【天條二：雜訊硬核攔截】
只要用戶聊到任何與加密貨幣/美股/股票期權市場資訊無關的話題（生活、旅遊、寫程式、閒聊八卦等），必須立刻切斷對話，只回覆這一句，不要加任何其他內容：
[🚨 系統拒絕]: 本終端僅提供『加密貨幣、股票與股票期權』之全方位市場資訊與量化策略分析。請專注於盤面，拒絕無效無關之雜訊。

【天條三：Scannable 排版】
拒絕長篇大論的官話與免責聲明。回答必須直擊痛點、數據說話，高度使用 Markdown 表格與重點粗體，讓使用者一眼掃過就能抓到重點。`

interface ChatMessage {
  role: "user" | "assistant"
  content: string
}

function buildSystemPrompt(contextSymbol?: string): string {
  if (!contextSymbol) return SYSTEM_PROMPT_BASE
  return `${SYSTEM_PROMPT_BASE}

【當前畫面上下文】
使用者目前正在查看標的：${contextSymbol}。若使用者的問題沒有明確指定標的，優先假設是在問這一檔。`
}

function sanitizeMessages(raw: unknown): ChatMessage[] | null {
  if (!Array.isArray(raw) || raw.length === 0) return null

  const cleaned: ChatMessage[] = []
  for (const item of raw) {
    if (
      !item ||
      typeof item !== "object" ||
      (item.role !== "user" && item.role !== "assistant") ||
      typeof item.content !== "string" ||
      item.content.trim() === ""
    ) {
      continue
    }
    cleaned.push({ role: item.role, content: item.content.slice(0, MAX_MESSAGE_CHARS) })
  }

  if (cleaned.length === 0) return null

  // Claude API 要求第一則訊息一定是 user 角色，多裁一輪不影響對話語意
  const trimmed = cleaned.slice(-MAX_HISTORY_MESSAGES)
  const firstUserIndex = trimmed.findIndex((m) => m.role === "user")
  if (firstUserIndex === -1) return null
  return trimmed.slice(firstUserIndex)
}

// ---------------------------------------------------------------------------
// 工具定義：每一個都對應後端既有的一支 API，讓 Claude 自己決定什麼時候該查
// 什麼資料，不用使用者自己講清楚要查哪支 API。
// ---------------------------------------------------------------------------

const TOOLS: Tool[] = [
  {
    name: "get_options_gex",
    description:
      "查詢指定美股標的的期權 GEX（Gamma Exposure）分佈與 Gamma 擠壓臨界點。只支援本終端監控的標的：NVDA, TSLA, SPY, SMCI, SPCX。",
    input_schema: {
      type: "object",
      properties: {
        symbol: { type: "string", description: "標的代號，例如 NVDA" },
      },
      required: ["symbol"],
    },
  },
  {
    name: "get_crypto_signals",
    description:
      "查詢加密貨幣交易訊號與監控快照：唐奇安通道位置、成交量比、資金費率、聰明錢偏向、Squeeze多空擠壓燈號。major=主流幣(BTC/ETH/SOL)，scan=市場掃描全名單（有觸發訊號或擠壓燈號的標的）。",
    input_schema: {
      type: "object",
      properties: {
        universe: { type: "string", enum: ["major", "scan"] },
      },
      required: ["universe"],
    },
  },
  {
    name: "get_crypto_smart_money",
    description: "查詢指定加密貨幣合約的聰明錢數據：資金費率、未平倉量變化、大戶多空比、偏向判斷。",
    input_schema: {
      type: "object",
      properties: {
        symbol: { type: "string", description: "ccxt格式合約符號，例如 BTC/USDT:USDT" },
      },
      required: ["symbol"],
    },
  },
  {
    name: "get_squeeze_feed",
    description: "查詢最近觸發的多空情緒擠壓爆破事件（綠燈級別）滾動清單，涵蓋加密貨幣主流幣/市場掃描/迷因幣。",
    input_schema: { type: "object", properties: {} },
  },
  {
    name: "get_meme_radar",
    description: "查詢迷因幣雷達：動態監控名單、爆量警報（拉盤/砸盤方向）、社群關注度共振狀態。",
    input_schema: { type: "object", properties: {} },
  },
  {
    name: "get_us_stock_orb",
    description: "查詢美股 ORB 開盤區間突破當沖策略監控狀態，標的：TSLA, NVDA, MSTR, SOXL, TQQQ。",
    input_schema: { type: "object", properties: {} },
  },
  {
    name: "get_news_sentiment",
    description: "查詢 AI 新聞情緒分析結果：近期加密貨幣/美股相關新聞的標的判斷與情緒分數。",
    input_schema: { type: "object", properties: {} },
  },
  {
    name: "get_meme_trade",
    description:
      "查詢🔥迷因幣1H爆量當沖（正式實盤）目前狀態：僅WIF/DOGE兩檔——180天回測裡唯二樣本數跨過統計門檻的幣種（WIF 19筆PF1.36、DOGE 20筆PF1.46），有無持倉、進場價、TP/SL、槓桿。跟迷因雷達(get_meme_radar)是不同東西：雷達只是警報，這裡是有方向/TP/SL的實際策略。",
    input_schema: { type: "object", properties: {} },
  },
  {
    name: "get_liquidation_walls",
    description:
      "查詢💥幣圈爆倉密度清算牆：BTC/ETH/SOL三檔，依價格區間彙總的真實強平單淨額（正值=空頭爆倉燃料區在現價上方、負值=多頭強平真空區在現價下方）。資料源自使用者本機監聽器，只從監聽開始運作那一刻起算，不是回推理論清算價位。",
    input_schema: { type: "object", properties: {} },
  },
  {
    name: "run_backtest",
    description:
      "對指定標的即時執行一次真實歷史回測（不是查快取，是真的重新抓歷史K線模擬），回傳勝率/賺賠比/獲利因子/最大回撤/總交易筆數。三個策略可選：crypto_donchian_1h（1H唐奇安+EMA+RVOL，標的用裸代號如BTC/ETH/SOL）、meme_volume_spike（1H迷因爆量，標的如WIF/DOGE/PEPE）、us_stock_orb（美股開盤區間突破，標的如NVDA/TSLA，天數會被yfinance夾到60天上限）。這是公開端點，後端有每小時15次的IP限流，這個限流是整個網站共用（含網頁上的回測沙盒UI），不是每個使用者各自15次，用之前跟使用者說一聲比較保險，不要濫用。回傳的sample_sufficient若為false，一定要在回答裡明確講「樣本數不足15筆，這個結果不具統計意義」，不能把小樣本的漂亮數字講得像已驗證的勝率。",
    input_schema: {
      type: "object",
      properties: {
        symbol: { type: "string", description: "標的代號，例如 BTC、WIF、NVDA" },
        strategy_name: { type: "string", enum: ["crypto_donchian_1h", "meme_volume_spike", "us_stock_orb"] },
        days_range: { type: "number", description: "回測天數，預設30，最大180（美股會被夾到60）" },
      },
      required: ["symbol", "strategy_name"],
    },
  },
]

async function fetchBackend(path: string): Promise<unknown> {
  const res = await fetch(`${BACKEND_URL}${path}`, { cache: "no-store" })
  if (!res.ok) {
    throw new Error(`後端回應 ${res.status}`)
  }
  return res.json()
}

// run_backtest 專用：POST + JSON body。跟其他GET工具不同，這支會觸發後端真的
// 重新抓歷史K線模擬（見該工具description的限流警告），不是查快取。
async function postBackend(path: string, body: unknown): Promise<unknown> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  })
  const json = await res.json().catch(() => null)
  if (!res.ok) {
    throw new Error(json?.detail ?? `後端回應 ${res.status}`)
  }
  return json
}

// 把 GEX 剖面（可能上百個履約價）壓縮成 Claude 真正需要的重點，避免整包
// points 塞爆 context：只留現貨價/臨界點，加上依 |net_gex| 排序的前5大履約價。
function summarizeGexData(raw: any, symbol: string): unknown {
  const underlying = raw?.underlyings?.find(
    (u: any) => typeof u?.symbol === "string" && u.symbol.toUpperCase() === symbol.toUpperCase(),
  )
  if (!underlying) return { error: `找不到標的 ${symbol}，本終端只監控 NVDA/TSLA/SPY/SMCI/SPCX` }
  if (!underlying.has_data) {
    return {
      symbol,
      has_data: false,
      note: "目前沒有可用的期權鏈資料，可能是美股非交易時段，或系統剛啟動還在拉第一輪。",
    }
  }
  const points = Array.isArray(underlying.points) ? underlying.points : []
  const topStrikes = [...points]
    .sort((a, b) => Math.abs(b.net_gex) - Math.abs(a.net_gex))
    .slice(0, 5)
  return {
    symbol,
    has_data: true,
    spot_price: underlying.spot_price,
    expiry: underlying.expiry,
    gamma_flip_strike: underlying.gamma_flip_strike,
    top_gex_strikes_by_magnitude: topStrikes,
    updated_at: underlying.updated_at,
  }
}

async function executeTool(name: string, input: Record<string, unknown>): Promise<unknown> {
  try {
    switch (name) {
      case "get_options_gex": {
        const symbol = typeof input.symbol === "string" ? input.symbol : ""
        const raw = await fetchBackend("/api/options/gex")
        return summarizeGexData(raw, symbol)
      }
      case "get_crypto_signals": {
        const universe = input.universe === "scan" ? "scan" : "major"
        return await fetchBackend(`/api/signals?universe=${universe}`)
      }
      case "get_crypto_smart_money": {
        const symbol = typeof input.symbol === "string" ? input.symbol : "BTC/USDT:USDT"
        return await fetchBackend(`/api/smart-money?symbol=${encodeURIComponent(symbol)}`)
      }
      case "get_squeeze_feed":
        return await fetchBackend("/api/squeeze-feed")
      case "get_meme_radar":
        return await fetchBackend("/api/memes")
      case "get_us_stock_orb":
        return await fetchBackend("/api/us-stock-orb")
      case "get_news_sentiment":
        return await fetchBackend("/api/ai-agent/news")
      case "get_meme_trade":
        return await fetchBackend("/api/meme-trade")
      case "get_liquidation_walls":
        return await fetchBackend("/api/market/liquidation-walls")
      case "run_backtest": {
        const symbol = typeof input.symbol === "string" ? input.symbol : ""
        const strategyName = typeof input.strategy_name === "string" ? input.strategy_name : ""
        const daysRange = typeof input.days_range === "number" ? input.days_range : 30
        if (!symbol || !strategyName) {
          return { error: "缺少 symbol 或 strategy_name 參數" }
        }
        return await postBackend("/api/backtest", { symbol, strategy_name: strategyName, days_range: daysRange })
      }
      default:
        return { error: `未知的工具：${name}` }
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : "查詢失敗"
    return { error: `無法連線到後端服務 (${BACKEND_URL})：${message}` }
  }
}

export async function POST(req: Request) {
  const clientIp = getClientIp(req)
  if (isRateLimited(clientIp)) {
    return new Response(
      JSON.stringify({ error: `請求過於頻繁，每小時最多 ${RATE_LIMIT_MAX_REQUESTS} 次，請稍後再試。` }),
      { status: 429, headers: { "Content-Type": "application/json" } },
    )
  }

  const apiKey = process.env.ANTHROPIC_API_KEY

  if (!apiKey) {
    return new Response(
      JSON.stringify({ error: "ANTHROPIC_API_KEY 尚未設定，AI 軍師助理暫時無法使用" }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    )
  }

  let body: { messages?: unknown; contextSymbol?: unknown }
  try {
    body = await req.json()
  } catch {
    return new Response(JSON.stringify({ error: "請求格式錯誤" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    })
  }

  const sanitized = sanitizeMessages(body.messages)
  if (!sanitized) {
    return new Response(JSON.stringify({ error: "對話內容不能為空" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    })
  }
  const contextSymbol = typeof body.contextSymbol === "string" ? body.contextSymbol.slice(0, 40) : undefined

  const anthropic = new Anthropic({ apiKey })
  const systemPrompt = buildSystemPrompt(contextSymbol)

  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      // Claude 的訊息型別跟我們前端存的 ChatMessage 形狀相容，但工具呼叫
      // 往返會需要塞 assistant 的 content blocks 跟 tool_result，所以這裡
      // 用 SDK 自己的 MessageParam[] 型別，不是原本簡化過的 ChatMessage[]。
      let messages: MessageParam[] = sanitized.map((m) => ({ role: m.role, content: m.content }))

      try {
        for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
          const claudeStream = anthropic.messages.stream({
            model: MODEL,
            max_tokens: MAX_TOKENS,
            system: systemPrompt,
            messages,
            tools: TOOLS,
          })

          claudeStream.on("text", (textDelta) => {
            controller.enqueue(encoder.encode(textDelta))
          })

          const finalMessage = await claudeStream.finalMessage()

          if (finalMessage.stop_reason !== "tool_use") {
            controller.close()
            return
          }

          const toolUseBlocks = finalMessage.content.filter(
            (block): block is Extract<typeof block, { type: "tool_use" }> => block.type === "tool_use",
          )

          // 讓使用者知道現在在等真實數據，不是卡住了
          controller.enqueue(encoder.encode(round === 0 ? "\n\n_🔍 查詢即時數據中…_\n\n" : ""))

          const toolResults: ToolResultBlockParam[] = await Promise.all(
            toolUseBlocks.map(async (block) => ({
              type: "tool_result" as const,
              tool_use_id: block.id,
              content: JSON.stringify(await executeTool(block.name, block.input as Record<string, unknown>)),
            })),
          )

          messages = [
            ...messages,
            { role: "assistant", content: finalMessage.content },
            { role: "user", content: toolResults },
          ]
        }

        // 超過 MAX_TOOL_ROUNDS 還沒收斂成文字回答，強制關閉串流避免無限迴圈
        controller.enqueue(encoder.encode("\n\n[⚠️ 查詢輪數過多，已中止。請換個方式提問。]"))
        controller.close()
      } catch (err) {
        // 串流已經開始的話，前端會收到不完整的回應；這裡至少把錯誤原因
        // 附加上去，不要讓畫面停在打字打一半又不明不白地卡住。
        const message = err instanceof Error ? err.message : "AI 軍師助理發生未知錯誤"
        controller.enqueue(encoder.encode(`\n\n[⚠️ 連線中斷：${message}]`))
        controller.close()
      }
    },
  })

  return new Response(stream, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-cache",
    },
  })
}
