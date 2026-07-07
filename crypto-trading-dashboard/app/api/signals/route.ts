import { NextRequest, NextResponse } from "next/server"

// Server-side proxy to the FastAPI backend. Keeping this as a same-origin
// route means the browser never needs to know the backend's address (no
// CORS round-trip from the client), and the address stays configurable
// per-environment via BACKEND_URL.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

export async function GET(request: NextRequest) {
  const universe = request.nextUrl.searchParams.get("universe") ?? "major"
  try {
    const res = await fetch(`${BACKEND_URL}/api/signals?universe=${universe}`, { cache: "no-store" })
    const body = await res.json()
    return NextResponse.json(body, { status: res.status })
  } catch {
    return NextResponse.json(
      { detail: `無法連線到後端服務 (${BACKEND_URL})，請確認 FastAPI 是否已啟動` },
      { status: 502 },
    )
  }
}
