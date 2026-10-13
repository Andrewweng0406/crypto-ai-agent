from fastapi.testclient import TestClient

import main
from btc_quant.paper import PaperAccount

client = TestClient(main.app)


class _Store:
    def __init__(self, state, events):
        self._state, self._events = state, events

    def load(self):
        return self._state

    def recent(self, limit=50):
        return self._events[:limit]

    def all_events(self):
        return list(self._events)


def test_status_without_state(monkeypatch):
    monkeypatch.setattr(main, "make_btc_quant_store", lambda: _Store(None, []))
    r = client.get("/api/btc-quant/status")
    assert r.status_code == 200
    assert r.json()["initialized"] is False


def test_status_with_state(monkeypatch):
    acc = PaperAccount.new(10_000)
    acc.rebalance(0.5, 100.0, "t")
    acc.mark(110.0)
    monkeypatch.setattr(main, "make_btc_quant_store", lambda: _Store(acc.to_dict(), [{"kind": "rebalance"}]))
    body = client.get("/api/btc-quant/status").json()
    assert body["initialized"] is True
    assert body["equity"] > 10_000
    assert body["trend"]["btc_qty"] == acc.btc_qty
    assert body["tactical"] is None
    assert body["recent_events"] == [{"kind": "rebalance"}]


def test_status_includes_stats(monkeypatch):
    acc = PaperAccount.new(1_000)
    acc.mark(100.0)
    events = [{"kind": "close", "side": "Long", "reason": "TAKE_PROFIT", "r_multiple": 2.0, "net_pnl": 40.0}]
    monkeypatch.setattr(main, "make_btc_quant_store", lambda: _Store(acc.to_dict(), events))
    body = client.get("/api/btc-quant/status").json()
    assert body["stats"]["trades"] == 1
    assert body["stats"]["win_rate_pct"] == 100.0
