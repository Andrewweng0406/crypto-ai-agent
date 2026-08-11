import type { Page, Route } from "@playwright/test"

const now = "2026-08-11T06:00:00+00:00"

const noSignalBase = {
  status: "NO_SIGNAL",
  side: null,
  entry_price: null,
  take_profit: null,
  stop_loss: null,
  stop_loss_pct: null,
  leverage: null,
  risk_reward_ratio: null,
  opened_at: null,
  smart_money_notes: [],
  updated_at: now,
  donchian_upper: 120,
  donchian_lower: 90,
  volume_ratio: 1.2,
  funding_rate: 0.0001,
  top_trader_long_short_ratio: 1.05,
  smart_money_bias: "Neutral",
  squeeze_tier: "none",
  squeeze_has_perp_market: true,
  squeeze_oi_growth_15m_pct: null,
  squeeze_oi_growth_1h_pct: null,
  squeeze_rvol: null,
  squeeze_funding_rate: null,
}

const mainSignals = {
  universe: "major",
  updated_at: now,
  tracked_symbols: [],
  signals: [
    { ...noSignalBase, symbol: "BTC/USDT:USDT", current_price: 113000 },
    { ...noSignalBase, symbol: "ETH/USDT:USDT", current_price: 4200 },
    { ...noSignalBase, symbol: "SOL/USDT:USDT", current_price: 185 },
  ],
}

const scanSignals = {
  universe: "scan",
  updated_at: now,
  tracked_symbols: ["BTC/USDT:USDT", "ETH/USDT:USDT"],
  signals: [],
}

const history = {
  trades: [
    {
      symbol: "BTC/USDT:USDT",
      side: "Long",
      entry_price: 100000,
      exit_price: 104000,
      take_profit: 104000,
      stop_loss: 98000,
      leverage: 2,
      result: "WIN",
      pnl_pct: 8,
      opened_at: "2026-08-10T00:00:00+00:00",
      closed_at: "2026-08-10T04:00:00+00:00",
      smart_money_notes: [],
    },
  ],
  stats: { total_trades: 1, wins: 1, losses: 0, win_rate_pct: 100 },
}

const riskSettings = {
  account_size: 1000,
  risk_pct: 1,
  max_leverage: 5,
  updated_at: now,
}

const journalEntries = {
  entries: [
    {
      id: "11111111-1111-4111-8111-111111111111",
      symbol: "BTC",
      action: "觀察",
      emotion: "冷靜",
      note: "等回踩",
      created_at: now,
    },
  ],
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  })
}

export async function mockDashboardApis(page: Page) {
  await page.route("**/api/**", async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname

    if (path === "/api/signals") {
      return json(route, url.searchParams.get("universe") === "scan" ? scanSignals : mainSignals)
    }
    if (path === "/api/history") return json(route, history)
    if (path === "/api/data-sources/health") {
      return json(route, {
        updated_at: now,
        sources: [
          {
            source: "crypto_market",
            label: "主流幣/市場掃描",
            status: "ok",
            last_success_at: now,
            last_error_at: null,
            last_error: null,
            latency_ms: 120,
            stale_after_seconds: 180,
            records_seen: 40,
            is_stale: false,
          },
          {
            source: "us_stock_orb",
            label: "美股 ORB",
            status: "ok",
            last_success_at: now,
            last_error_at: null,
            last_error: null,
            latency_ms: 180,
            stale_after_seconds: 900,
            records_seen: 6,
            is_stale: false,
          },
        ],
      })
    }
    if (path === "/api/background-jobs/health") {
      return json(route, {
        updated_at: now,
        database_enabled: true,
        jobs: [
          {
            job_name: "price_monitor_loop",
            label: "主流幣/市場掃描",
            status: "active",
            owner_fingerprint: "abc123def0",
            acquired_at: now,
            heartbeat_at: now,
            expires_at: now,
          },
          {
            job_name: "us_stock_orb_loop",
            label: "美股 ORB",
            status: "active",
            owner_fingerprint: "abc123def0",
            acquired_at: now,
            heartbeat_at: now,
            expires_at: now,
          },
        ],
      })
    }
    if (path === "/api/risk-settings") {
      if (request.method() === "PUT") {
        const payload = request.postDataJSON()
        return json(route, { ...payload, updated_at: now })
      }
      return json(route, riskSettings)
    }
    if (path === "/api/journal") {
      if (request.method() === "POST") {
        const payload = request.postDataJSON()
        return json(route, {
          id: "22222222-2222-4222-8222-222222222222",
          symbol: payload.symbol,
          action: payload.action,
          emotion: payload.emotion,
          note: payload.note,
          created_at: now,
        })
      }
      return json(route, journalEntries)
    }
    if (path.startsWith("/api/journal/")) return json(route, { deleted: true })
    if (path === "/api/options/gex") {
      return json(route, {
        underlyings: [
          {
            symbol: "NVDA",
            has_data: true,
            spot_price: 182.25,
            expiry: "2026-08-21",
            gamma_flip_strike: 180,
            points: [],
            previous_day_points: [],
            whale_sweep_supported: true,
            updated_at: now,
          },
        ],
        data_source_ok: true,
        moomoo_online: false,
        updated_at: now,
      })
    }
    if (path === "/api/options/whale-sweep") return json(route, { items: [], updated_at: now })
    if (path === "/api/us-stock-orb") {
      return json(route, {
        market_session: "CLOSED",
        market_regime: "Neutral",
        updated_at: now,
        stocks: [
          {
            symbol: "TSLA",
            display_name: "TSLA",
            status: "NO_SIGNAL",
            side: null,
            entry_price: null,
            current_price: 245.12,
            take_profit: null,
            stop_loss: null,
            stop_loss_pct: null,
            leverage: null,
            risk_reward_ratio: null,
            opened_at: null,
            day_change_pct: 1.2,
            updated_at: now,
            opening_high: 248,
            opening_low: 240,
            rvol: 1.4,
            market_regime: "Neutral",
          },
        ],
      })
    }
    if (path === "/api/us-stock-orb/history") {
      return json(route, {
        trades: [],
        stats: { total_trades: 0, wins: 0, losses: 0, win_rate_pct: 0 },
      })
    }
    if (path === "/api/memes") {
      return json(route, {
        alerts: [],
        watchlist: [
          {
            symbol: "DOGE/USDT",
            price: 0.23,
            volume_multiple: 1.8,
            change_1h_pct: 0.5,
            change_24h_pct: 2.1,
            is_trending: true,
            trending_rank: 1,
            trending_top_streak: 2,
            resonance_status: "confirmed",
            last_resonance_summary: "watching",
            last_resonance_at: now,
            updated_at: now,
            squeeze_tier: "none",
            squeeze_has_perp_market: true,
            squeeze_oi_growth_15m_pct: null,
            squeeze_oi_growth_1h_pct: null,
            squeeze_rvol: null,
            squeeze_funding_rate: null,
          },
        ],
        updated_at: now,
      })
    }
    if (path === "/api/meme-trade") {
      return json(route, {
        coins: [
          {
            symbol: "DOGE/USDT:USDT",
            display_name: "DOGE",
            status: "NO_SIGNAL",
            side: null,
            entry_price: null,
            current_price: 0.23,
            take_profit: null,
            stop_loss: null,
            stop_loss_pct: null,
            leverage: null,
            risk_reward_ratio: null,
            opened_at: null,
            updated_at: now,
          },
        ],
        updated_at: now,
      })
    }
    if (path === "/api/meme-trade/history") {
      return json(route, {
        trades: [],
        stats: { total_trades: 0, wins: 0, losses: 0, win_rate_pct: 0 },
      })
    }
    if (path === "/api/ai-agent/news") return json(route, { items: [], updated_at: now })
    if (path === "/api/ai-agent/broadcast") return json(route, { items: [], updated_at: now })
    if (path === "/api/squeeze-feed") return json(route, { items: [], updated_at: now })
    if (path === "/api/rsi2-meanrev") {
      return json(route, {
        market_session: "CLOSED",
        caveat: "sample-size warning",
        updated_at: now,
        stocks: [],
      })
    }
    if (path === "/api/market/liquidation-walls") {
      return json(route, { underlyings: [], updated_at: now })
    }

    return json(route, { detail: `Unhandled test API route: ${path}` }, 501)
  })
}
