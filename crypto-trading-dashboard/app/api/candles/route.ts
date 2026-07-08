import { NextRequest, NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

export async function GET(request: NextRequest) {
  const symbol = request.nextUrl.searchParams.get("symbol")
  const limit = request.nextUrl.searchParams.get("limit") ?? "60"
  const timeframe = request.nextUrl.searchParams.get("timeframe")

  if (!symbol) {
    return NextResponse.json({ detail: "missing symbol" }, { status: 400 })
  }

  const qs = new URLSearchParams({ symbol, limit })
  if (timeframe) qs.set("timeframe", timeframe)

  try {
    const res = await fetch(`${BACKEND_URL}/api/candles?${qs.toString()}`, { cache: "no-store" })
    const body = await res.json()
    return NextResponse.json(body, { status: res.status })
  } catch {
    return NextResponse.json(
      { detail: `無法連線到後端服務 (${BACKEND_URL})，請確認 FastAPI 是否已啟動` },
      { status: 502 },
    )
  }
}
