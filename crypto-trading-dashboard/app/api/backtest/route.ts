import { NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

// 純轉發：真正的IP限流邏輯在 main.py 那邊（後端才是實際打外部交易所/yfinance
// API的地方），這裡只是把請求原封不動地轉過去，不重複實作限流。
export async function POST(req: Request) {
  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ detail: "請求格式錯誤" }, { status: 400 })
  }

  try {
    const res = await fetch(`${BACKEND_URL}/api/backtest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    })
    const responseBody = await res.json()
    return NextResponse.json(responseBody, { status: res.status })
  } catch {
    return NextResponse.json(
      { detail: `無法連線到後端服務 (${BACKEND_URL})，請確認 FastAPI 是否已啟動` },
      { status: 502 },
    )
  }
}
