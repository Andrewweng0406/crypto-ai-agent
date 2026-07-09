import Anthropic from "@anthropic-ai/sdk"

// 💬 AI 交易軍師助理：右下角常駐聊天機器人的後端。直接呼叫 Anthropic Claude
// API（不經過 FastAPI 後端），因為串流回應在 Next.js 這一層做最直接，不用
// 另外在 FastAPI 那邊搭一套 SSE。
//
// 模型：使用者原本指定 "claude-3-5-sonnet"，這是舊版模型代號，2026年現在
// 應該用 "claude-sonnet-5"（見系統當前可用模型列表），照舊代號打會直接
// 打不通，這裡改用新的。
const MODEL = "claude-sonnet-5"
const MAX_TOKENS = 1024
const MAX_HISTORY_MESSAGES = 20 // 只送最近N則，避免對話一長，每次呼叫的成本跟著無限膨脹
const MAX_MESSAGE_CHARS = 4000 // 單則訊息長度上限，防止異常超長輸入炸掉 token 用量

const SYSTEM_PROMPT_BASE = `你是「Weng Crypto」交易終端內建的 AI 交易軍師助理，服務對象是主動交易者。

【天條一：無所不知的市場百科】
只要對話涉及加密貨幣、美股、股票期權三大市場的數據（OI未平倉量、RVOL相對成交量、資金費率、爆倉單、GEX曝險等），你必須以極度專業、硬核的姿態全力解答，展現量化與盤面判讀的深度。

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

export async function POST(req: Request) {
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

  const messages = sanitizeMessages(body.messages)
  if (!messages) {
    return new Response(JSON.stringify({ error: "對話內容不能為空" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    })
  }
  const contextSymbol = typeof body.contextSymbol === "string" ? body.contextSymbol.slice(0, 40) : undefined

  const anthropic = new Anthropic({ apiKey })

  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      try {
        const claudeStream = anthropic.messages.stream({
          model: MODEL,
          max_tokens: MAX_TOKENS,
          system: buildSystemPrompt(contextSymbol),
          messages,
        })

        claudeStream.on("text", (textDelta) => {
          controller.enqueue(encoder.encode(textDelta))
        })

        await claudeStream.finalMessage()
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
