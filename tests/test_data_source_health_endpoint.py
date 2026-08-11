from copy import deepcopy
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import main
from main import app, state

client = TestClient(app)


def test_data_source_health_returns_core_sources():
    resp = client.get("/api/data-sources/health")

    assert resp.status_code == 200
    body = resp.json()
    sources = {item["source"]: item for item in body["sources"]}

    assert "updated_at" in body
    assert sources["crypto_market"]["status"] in {"starting", "ok", "stale", "error"}
    assert sources["meme_radar"]["label"] == "迷因雷達"
    assert sources["us_stock_orb"]["stale_after_seconds"] > 0
    assert sources["options_gex"]["status"] in {"starting", "ok", "stale", "error", "disabled"}


def test_data_source_health_reflects_success_and_error_states():
    source = "crypto_market"
    original = deepcopy(state.data_source_health[source])

    try:
        state.mark_data_source_success(source, latency_ms=12.345, records_seen=7)
        ok_resp = client.get("/api/data-sources/health")
        ok_item = next(item for item in ok_resp.json()["sources"] if item["source"] == source)
        assert ok_item["status"] == "ok"
        assert ok_item["latency_ms"] == 12.35
        assert ok_item["records_seen"] == 7

        state.mark_data_source_error(source, "upstream timeout", latency_ms=50)
        error_resp = client.get("/api/data-sources/health")
        error_item = next(item for item in error_resp.json()["sources"] if item["source"] == source)
        assert error_item["status"] == "error"
        assert error_item["last_error"] == "upstream timeout"
        assert error_item["latency_ms"] == 50
    finally:
        state.data_source_health[source] = original


def test_data_source_health_marks_ok_source_stale_after_threshold():
    source = "meme_radar"
    original = deepcopy(state.data_source_health[source])

    try:
        state.mark_data_source_success(source, records_seen=3)
        state.data_source_health[source].last_success_monotonic -= (
            state.data_source_health[source].stale_after_seconds + 1
        )

        resp = client.get("/api/data-sources/health")
        item = next(item for item in resp.json()["sources"] if item["source"] == source)

        assert item["status"] == "stale"
        assert item["is_stale"] is True
    finally:
        state.data_source_health[source] = original


def test_data_source_health_hydrates_stale_database_record():
    source = "crypto_market"
    original = deepcopy(state.data_source_health[source])
    old_success_at = (datetime.now(timezone.utc) - timedelta(
        seconds=state.data_source_health[source].stale_after_seconds + 30
    )).isoformat()

    try:
        state.data_source_health[source].hydrate_from_record({
            "source": source,
            "label": "主流幣/市場掃描",
            "status": "ok",
            "last_success_at": old_success_at,
            "last_error_at": None,
            "last_error": None,
            "latency_ms": 12.345,
            "stale_after_seconds": state.data_source_health[source].stale_after_seconds,
            "records_seen": 9,
            "is_stale": False,
        })

        resp = client.get("/api/data-sources/health")
        item = next(item for item in resp.json()["sources"] if item["source"] == source)

        assert item["status"] == "stale"
        assert item["is_stale"] is True
        assert item["records_seen"] == 9
        assert item["latency_ms"] == 12.35
    finally:
        state.data_source_health[source] = original


def test_data_source_health_endpoint_prefers_database_records(monkeypatch):
    old_success_at = datetime.now(timezone.utc).isoformat()

    monkeypatch.setattr(main, "is_database_enabled", lambda: True)
    monkeypatch.setattr(main, "list_data_source_health", lambda: [{
        "source": "crypto_market",
        "label": "主流幣/市場掃描",
        "status": "ok",
        "last_success_at": old_success_at,
        "last_error_at": None,
        "last_error": None,
        "latency_ms": 42.424,
        "stale_after_seconds": 180,
        "records_seen": 123,
        "is_stale": False,
    }])

    resp = client.get("/api/data-sources/health")
    body = resp.json()
    sources = {item["source"]: item for item in body["sources"]}

    assert sources["crypto_market"]["records_seen"] == 123
    assert sources["crypto_market"]["latency_ms"] == 42.42
    assert "meme_radar" in sources


def test_background_jobs_health_reports_lease_status(monkeypatch):
    monkeypatch.setattr(main, "is_database_enabled", lambda: True)
    monkeypatch.setattr(main, "list_job_leases", lambda: [
        {
            "job_name": "price_monitor_loop",
            "owner_id": "deployment:web:abc",
            "acquired_at": "2026-08-11T18:00:00+00:00",
            "heartbeat_at": "2026-08-11T18:01:00+00:00",
            "expires_at": "2026-08-11T18:03:00+00:00",
            "is_active": True,
        },
        {
            "job_name": "news_agent_loop",
            "owner_id": "deployment:web:abc",
            "acquired_at": "2026-08-11T17:00:00+00:00",
            "heartbeat_at": "2026-08-11T17:01:00+00:00",
            "expires_at": "2026-08-11T17:20:00+00:00",
            "is_active": False,
        },
    ])

    resp = client.get("/api/background-jobs/health")
    body = resp.json()
    jobs = {item["job_name"]: item for item in body["jobs"]}

    assert resp.status_code == 200
    assert body["database_enabled"] is True
    assert jobs["price_monitor_loop"]["label"] == "主流幣/市場掃描"
    assert jobs["price_monitor_loop"]["status"] == "active"
    assert len(jobs["price_monitor_loop"]["owner_fingerprint"]) == 10
    assert jobs["news_agent_loop"]["status"] == "expired"
