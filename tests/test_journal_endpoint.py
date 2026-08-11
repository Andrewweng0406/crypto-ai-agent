from fastapi.testclient import TestClient

import main
from main import app

client = TestClient(app)


def setup_function():
    main.state.journal_entries.clear()


def test_journal_starts_empty_without_database(monkeypatch):
    monkeypatch.setattr(main, "is_database_enabled", lambda: False)

    resp = client.get("/api/journal")

    assert resp.status_code == 200
    assert resp.json() == {"entries": []}


def test_journal_create_normalizes_symbol_and_stores_entry(monkeypatch):
    monkeypatch.setattr(main, "is_database_enabled", lambda: False)

    resp = client.post(
        "/api/journal",
        json={"symbol": " btc ", "action": "觀察", "emotion": "冷靜", "note": " wait for pullback "},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "BTC"
    assert body["note"] == "wait for pullback"
    assert body["created_at"]

    list_resp = client.get("/api/journal")
    assert list_resp.json()["entries"][0]["id"] == body["id"]


def test_journal_rejects_invalid_symbol(monkeypatch):
    monkeypatch.setattr(main, "is_database_enabled", lambda: False)

    resp = client.post("/api/journal", json={"symbol": "", "action": "觀察", "emotion": "冷靜", "note": ""})

    assert resp.status_code == 400


def test_journal_delete_removes_memory_entry(monkeypatch):
    monkeypatch.setattr(main, "is_database_enabled", lambda: False)
    created = client.post("/api/journal", json={"symbol": "ETH", "action": "模擬", "emotion": "猶豫", "note": ""})
    entry_id = created.json()["id"]

    resp = client.delete(f"/api/journal/{entry_id}")

    assert resp.status_code == 200
    assert resp.json() == {"deleted": True}
    assert client.get("/api/journal").json() == {"entries": []}
