"""BTC 量化紙上交易的績效統計：從事件紀錄（close / daily_equity）計算，供每日摘要和狀態 API 使用。"""

from __future__ import annotations


def _trade_stats(closes: list[dict]) -> dict:
    n = len(closes)
    wins = sum(1 for e in closes if e["net_pnl"] > 0)
    rs = [e["r_multiple"] for e in closes]
    return {
        "trades": n,
        "wins": wins,
        "win_rate_pct": wins / n * 100 if n else 0.0,
        "avg_r": sum(rs) / n if n else 0.0,
        "total_r": sum(rs),
    }


def summarize_events(events: list[dict], start_equity: float) -> dict:
    closes = [e for e in events if e.get("kind") == "close"]
    snaps = sorted((e for e in events if e.get("kind") == "daily_equity"), key=lambda e: e["ts"])

    max_dd = 0.0
    peak = None
    for snap in snaps:
        peak = snap["equity"] if peak is None else max(peak, snap["equity"])
        max_dd = min(max_dd, (snap["equity"] / peak - 1) * 100)
    latest = snaps[-1]["equity"] if snaps else start_equity

    rs = [e["r_multiple"] for e in closes]
    return {
        **_trade_stats(closes),
        "long": _trade_stats([e for e in closes if e["side"] == "Long"]),
        "short": _trade_stats([e for e in closes if e["side"] == "Short"]),
        "best_r": max(rs) if rs else 0.0,
        "worst_r": min(rs) if rs else 0.0,
        "liquidations": sum(1 for e in closes if e["reason"] == "LIQUIDATION"),
        "total_net_pnl": sum(e["net_pnl"] for e in closes),
        "days_recorded": len(snaps),
        "latest_equity": latest,
        "return_pct": (latest / start_equity - 1) * 100 if start_equity else 0.0,
        "max_drawdown_pct": max_dd,
    }
