import { NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

export async function DELETE(_req: Request, context: { params: Promise<{ displayName: string }> }) {
  const { displayName } = await context.params
  try {
    const res = await fetch(`${BACKEND_URL}/api/options/watchlist/${encodeURIComponent(displayName)}`, {
      method: "DELETE",
      cache: "no-store",
    })
    const body = await res.json()
    return NextResponse.json(body, { status: res.status })
  } catch {
    return NextResponse.json(
      { detail: `無法連線到後端服務 (${BACKEND_URL})，請確認 FastAPI 是否已啟動` },
      { status: 502 },
    )
  }
}
