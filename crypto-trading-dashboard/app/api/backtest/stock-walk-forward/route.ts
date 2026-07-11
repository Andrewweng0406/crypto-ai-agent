import { NextRequest, NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

// 純轉發：真正的IP限流邏輯在 main.py 那邊。
export async function POST(req: NextRequest) {
  const symbol = req.nextUrl.searchParams.get("symbol") ?? "NVDA"

  try {
    const res = await fetch(`${BACKEND_URL}/api/backtest/stock-walk-forward?symbol=${encodeURIComponent(symbol)}`, {
      method: "POST",
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
