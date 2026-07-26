import { NextRequest, NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

export async function GET(request: NextRequest) {
  const symbol = request.nextUrl.searchParams.get("symbol")
  const sentiment = request.nextUrl.searchParams.get("sentiment")
  const sentimentLabel = request.nextUrl.searchParams.get("sentiment_label")

  if (!symbol || !sentiment) {
    return NextResponse.json({ detail: "缺少 symbol 或 sentiment 參數" }, { status: 400 })
  }

  const qs = new URLSearchParams({ symbol, sentiment })
  if (sentimentLabel) qs.set("sentiment_label", sentimentLabel)

  try {
    const res = await fetch(`${BACKEND_URL}/api/options/strategy?${qs.toString()}`, { cache: "no-store" })
    const body = await res.json()
    return NextResponse.json(body, { status: res.status })
  } catch {
    return NextResponse.json(
      { detail: `無法連線到後端服務 (${BACKEND_URL})，請確認 FastAPI 是否已啟動` },
      { status: 502 },
    )
  }
}
