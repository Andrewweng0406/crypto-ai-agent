import { NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

// 純轉發：真正的IP限流邏輯在 main.py 那邊。這個端點比 /api/backtest 更吃運算資源
// （抓3年歷史K線+跑滾動式網格搜尋），單次請求可能要15-25秒，前端需設對應的等待UI。
export async function POST(req: Request) {
  let body: unknown
  try {
    body = await req.json()
  } catch {
    body = {}
  }

  try {
    const res = await fetch(`${BACKEND_URL}/api/backtest/walk-forward`, {
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
