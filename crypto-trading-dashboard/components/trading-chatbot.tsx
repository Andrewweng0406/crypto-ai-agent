"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Loader2, MessageCircle, Send, X } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { cn } from "@/lib/utils"

interface ChatMessage {
  role: "user" | "assistant"
  content: string
}

interface TradingChatbotProps {
  // 預留數據接口：之後期權分析等分頁做好「使用者目前正在看哪檔標的」的
  // 狀態後，把 symbol 傳進來，AI 軍師助理回答問題時就會知道上下文，不用
  // 使用者自己在對話裡重複打一次代號。目前沒有任何分頁在傳，undefined。
  contextSymbol?: string
}

// 右下角常駐 AI 交易軍師助理：收合成一個帶呼吸燈的圓形按鈕，展開後是暗黑
// 風格對話框，支援 Markdown（含表格），串流打字機效果。跟 FastAPI 後端
// 無關——直接打 Next.js 自己的 /api/chat，那支路由再去呼叫 Anthropic。
export function TradingChatbot({ contextSymbol }: TradingChatbotProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [messages])

  const sendMessage = useCallback(async () => {
    const trimmed = input.trim()
    if (!trimmed || isStreaming) return

    const nextMessages: ChatMessage[] = [...messages, { role: "user", content: trimmed }]
    setMessages([...nextMessages, { role: "assistant", content: "" }])
    setInput("")
    setError(null)
    setIsStreaming(true)

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: nextMessages, contextSymbol }),
      })

      if (!res.ok || !res.body) {
        const body = await res.json().catch(() => null)
        throw new Error(body?.error ?? `請求失敗（${res.status}）`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()

      // 逐塊把串流回來的文字塞進最後一則（佔位的）assistant 訊息，做出
      // 打字機效果；不重建整個陣列，只更新最後一筆，避免每個字都整個
      // messages 陣列重新配置。
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        setMessages((prev) => {
          const updated = [...prev]
          const last = updated[updated.length - 1]
          updated[updated.length - 1] = { ...last, content: last.content + chunk }
          return updated
        })
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "連線失敗"
      setError(msg)
      setMessages((prev) => prev.slice(0, -1)) // 拿掉那則沒收到任何內容的空佔位訊息
    } finally {
      setIsStreaming(false)
    }
  }, [input, isStreaming, messages, contextSymbol])

  return (
    <>
      {!isOpen && (
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          className="animate-chatbot-breathe fixed bottom-6 right-6 z-50 flex size-14 items-center justify-center rounded-full bg-primary text-primary-foreground transition-transform hover:scale-105"
          aria-label="開啟 AI 交易軍師助理"
        >
          <MessageCircle className="size-6" aria-hidden="true" />
        </button>
      )}

      {isOpen && (
        <div className="fixed bottom-6 right-6 z-50 flex h-[min(560px,calc(100vh-3rem))] w-[min(380px,calc(100vw-3rem))] flex-col overflow-hidden rounded-2xl border border-border/60 bg-popover shadow-2xl">
          <div className="flex items-center justify-between border-b border-border/60 bg-card px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="flex size-7 items-center justify-center rounded-full bg-primary/15 text-primary">
                <MessageCircle className="size-4" aria-hidden="true" />
              </span>
              <div className="flex flex-col leading-none">
                <span className="font-mono text-sm font-semibold">AI 交易軍師助理</span>
                <span className="text-[10px] text-muted-foreground">Trading Chatbot</span>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="flex size-7 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              aria-label="收合對話框"
            >
              <X className="size-4" aria-hidden="true" />
            </button>
          </div>

          <div ref={scrollRef} className="flex flex-1 flex-col gap-3 overflow-y-auto px-4 py-4">
            {messages.length === 0 && (
              <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center text-xs text-muted-foreground">
                <MessageCircle className="size-8 opacity-40" aria-hidden="true" />
                <p>
                  問我加密貨幣、美股、期權的盤面數據。
                  <br />
                  跟盤面無關的問題不受理。
                </p>
              </div>
            )}
            {messages.map((m, i) => (
              <ChatBubble
                key={i}
                message={m}
                isPending={isStreaming && i === messages.length - 1 && m.role === "assistant" && m.content === ""}
              />
            ))}
            {error && (
              <div className="rounded-lg border border-short/30 bg-short/[0.06] px-3 py-2 text-xs text-short">
                {error}
              </div>
            )}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault()
              sendMessage()
            }}
            className="flex items-center gap-2 border-t border-border/60 bg-card p-3"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="問問盤面數據…"
              disabled={isStreaming}
              className="flex-1 rounded-full border border-border/60 bg-background px-4 py-2 text-sm outline-none focus:border-primary/60 disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={isStreaming || !input.trim()}
              className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground transition-opacity disabled:opacity-40"
              aria-label="送出"
            >
              {isStreaming ? (
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              ) : (
                <Send className="size-4" aria-hidden="true" />
              )}
            </button>
          </form>
        </div>
      )}
    </>
  )
}

function ChatBubble({ message, isPending }: { message: ChatMessage; isPending: boolean }) {
  const isUser = message.role === "user"
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
          isUser ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground",
        )}
      >
        {isPending ? (
          <span className="flex gap-1 py-1" aria-label="AI 正在輸入">
            <span className="size-1.5 animate-bounce rounded-full bg-current opacity-60 [animation-delay:-0.3s]" />
            <span className="size-1.5 animate-bounce rounded-full bg-current opacity-60 [animation-delay:-0.15s]" />
            <span className="size-1.5 animate-bounce rounded-full bg-current opacity-60" />
          </span>
        ) : isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <MarkdownContent content={message.content} />
        )}
      </div>
    </div>
  )
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="flex flex-col gap-2">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="whitespace-pre-wrap">{children}</p>,
          strong: ({ children }) => <strong className="font-bold text-foreground">{children}</strong>,
          ul: ({ children }) => <ul className="list-disc space-y-1 pl-4">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal space-y-1 pl-4">{children}</ol>,
          code: ({ children }) => (
            <code className="rounded bg-background/60 px-1 py-0.5 font-mono text-xs">{children}</code>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto rounded-lg border border-border/60">
              <table className="w-full border-collapse text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-background/60">{children}</thead>,
          th: ({ children }) => (
            <th className="border-b border-border/60 px-2 py-1.5 text-left font-semibold">{children}</th>
          ),
          td: ({ children }) => <td className="border-b border-border/40 px-2 py-1.5">{children}</td>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
