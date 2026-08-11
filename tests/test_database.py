import database


def test_database_disabled_without_url(monkeypatch):
    monkeypatch.setattr(database, "DATABASE_URL", None)

    assert database.is_database_enabled() is False
    assert database.init_database() is False
    database.upsert_data_source_health([])
    assert database.list_data_source_health() is None
    database.insert_ingest_event("source", "event", {})
    assert database.load_watchlist("options") is None
    database.upsert_watchlist_item("options", "NVDA", "NVDA")
    database.delete_watchlist_item("options", "NVDA")
    database.seed_watchlist_if_empty("options", {"NVDA": "NVDA"})
    assert database.list_journal_entries() is None
    assert database.create_journal_entry("BTC", "觀察", "冷靜", "") is None
    assert database.delete_journal_entry("00000000-0000-0000-0000-000000000000") is False
    database.insert_trade_history("main_signal", {"symbol": "BTC/USDT:USDT"})
    assert database.list_trade_history("main_signal") is None
    assert database.load_risk_settings() is None
    assert database.upsert_risk_settings(1000, 1, 5) is None
    assert database.try_acquire_job_lease("price_monitor_loop", "test-owner", 30) is True


def test_first_migration_declares_core_product_tables():
    migration_sql = database.MIGRATIONS[0][1]

    for table_name in (
        "signal_snapshots",
        "trade_history",
        "watchlists",
        "journal_entries",
        "risk_settings",
        "data_source_health",
        "ingest_events",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in migration_sql


def test_second_migration_declares_job_leases_table():
    migration_sql = database.MIGRATIONS[1][1]

    assert "CREATE TABLE IF NOT EXISTS job_leases" in migration_sql
    assert "job_name TEXT PRIMARY KEY" in migration_sql
    assert "expires_at TIMESTAMPTZ NOT NULL" in migration_sql
