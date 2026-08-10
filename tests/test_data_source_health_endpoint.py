from copy import deepcopy

from fastapi.testclient import TestClient

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
