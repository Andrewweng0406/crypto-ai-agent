from fastapi.testclient import TestClient

import main
from main import app

client = TestClient(app)


def setup_function():
    main.state.history.clear()
    main.state.us_stock_history.clear()
    main.state.rsi2_history.clear()
    main.state.meme_trade_history.clear()


def test_history_prefers_database_records_when_enabled(monkeypatch):
    main.state.history.appendleft(
        {
            "symbol": "MEMORY/USDT:USDT",
            "side": "Long",
            "entry_price": 1.0,
            "exit_price": 2.0,
            "take_profit": 2.0,
            "stop_loss": 0.5,
            "leverage": 1,
            "result": "WIN",
            "pnl_pct": 100.0,
            "opened_at": "2026-01-01T00:00:00+00:00",
            "closed_at": "2026-01-02T00:00:00+00:00",
            "smart_money_notes": [],
        }
    )

    monkeypatch.setattr(main, "is_database_enabled", lambda: True)
    monkeypatch.setattr(
        main,
        "list_trade_history",
        lambda strategy, **kwargs: [
            {
                "symbol": "BTC/USDT:USDT",
                "side": "Short",
                "entry_price": 100.0,
                "exit_price": 90.0,
                "take_profit": 90.0,
                "stop_loss": 105.0,
                "leverage": 2,
                "result": "WIN",
                "pnl_pct": 20.0,
                "opened_at": "2026-01-03T00:00:00+00:00",
                "closed_at": "2026-01-04T00:00:00+00:00",
                "smart_money_notes": ["db"],
            }
        ],
    )

    resp = client.get("/api/history")

    assert resp.status_code == 200
    body = resp.json()
    assert body["trades"][0]["symbol"] == "BTC/USDT:USDT"
    assert body["trades"][0]["smart_money_notes"] == ["db"]
    assert body["stats"]["total_trades"] == 1


def test_history_falls_back_to_memory_when_database_read_fails(monkeypatch):
    main.state.history.appendleft(
        {
            "symbol": "ETH/USDT:USDT",
            "side": "Long",
            "entry_price": 10.0,
            "exit_price": 8.0,
            "take_profit": 12.0,
            "stop_loss": 8.0,
            "leverage": 3,
            "result": "LOSS",
            "pnl_pct": -60.0,
            "opened_at": "2026-01-01T00:00:00+00:00",
            "closed_at": "2026-01-02T00:00:00+00:00",
            "smart_money_notes": [],
        }
    )

    monkeypatch.setattr(main, "is_database_enabled", lambda: True)
    monkeypatch.setattr(main, "list_trade_history", lambda strategy, **kwargs: None)

    resp = client.get("/api/history")

    assert resp.status_code == 200
    body = resp.json()
    assert body["trades"][0]["symbol"] == "ETH/USDT:USDT"
    assert body["stats"]["losses"] == 1
