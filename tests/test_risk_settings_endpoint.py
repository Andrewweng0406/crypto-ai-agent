from fastapi.testclient import TestClient

import main
from main import app

client = TestClient(app)


def setup_function():
    main.state.risk_settings = dict(main.DEFAULT_RISK_SETTINGS)


def test_risk_settings_default_without_database(monkeypatch):
    monkeypatch.setattr(main, "is_database_enabled", lambda: False)

    resp = client.get("/api/risk-settings")

    assert resp.status_code == 200
    assert resp.json()["account_size"] == 1000.0
    assert resp.json()["risk_pct"] == 1.0
    assert resp.json()["max_leverage"] == 5


def test_risk_settings_update_memory_fallback(monkeypatch):
    monkeypatch.setattr(main, "is_database_enabled", lambda: False)
    monkeypatch.setattr(main, "save_state_snapshot", lambda: None)

    resp = client.put(
        "/api/risk-settings",
        json={"account_size": 25000, "risk_pct": 1.5, "max_leverage": 3},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["account_size"] == 25000.0
    assert body["risk_pct"] == 1.5
    assert body["max_leverage"] == 3
    assert main.state.risk_settings["account_size"] == 25000.0


def test_risk_settings_rejects_invalid_values(monkeypatch):
    monkeypatch.setattr(main, "is_database_enabled", lambda: False)

    resp = client.put(
        "/api/risk-settings",
        json={"account_size": 1000, "risk_pct": 25, "max_leverage": 5},
    )

    assert resp.status_code == 400


def test_risk_settings_reads_database_when_enabled(monkeypatch):
    monkeypatch.setattr(main, "is_database_enabled", lambda: True)
    monkeypatch.setattr(
        main,
        "load_risk_settings",
        lambda: {
            "account_size": 50000.0,
            "risk_pct": 0.75,
            "max_leverage": 2,
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
    )

    resp = client.get("/api/risk-settings")

    assert resp.status_code == 200
    assert resp.json()["account_size"] == 50000.0
    assert main.state.risk_settings["max_leverage"] == 2


def test_risk_settings_writes_database_when_enabled(monkeypatch):
    saved = {}
    monkeypatch.setattr(main, "is_database_enabled", lambda: True)
    monkeypatch.setattr(main, "save_state_snapshot", lambda: None)

    def fake_upsert(account_size, risk_pct, max_leverage):
        saved.update(
            {
                "account_size": account_size,
                "risk_pct": risk_pct,
                "max_leverage": max_leverage,
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        )
        return dict(saved)

    monkeypatch.setattr(main, "upsert_risk_settings", fake_upsert)

    resp = client.put(
        "/api/risk-settings",
        json={"account_size": 12000, "risk_pct": 2, "max_leverage": 4},
    )

    assert resp.status_code == 200
    assert saved == {
        "account_size": 12000.0,
        "risk_pct": 2.0,
        "max_leverage": 4,
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
