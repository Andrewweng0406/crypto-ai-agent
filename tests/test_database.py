import database


def test_database_disabled_without_url(monkeypatch):
    monkeypatch.setattr(database, "DATABASE_URL", None)

    assert database.is_database_enabled() is False
    assert database.init_database() is False
    database.upsert_data_source_health([])
    database.insert_ingest_event("source", "event", {})
    assert database.load_watchlist("options") is None
    database.upsert_watchlist_item("options", "NVDA", "NVDA")
    database.delete_watchlist_item("options", "NVDA")
    database.seed_watchlist_if_empty("options", {"NVDA": "NVDA"})
    assert database.list_journal_entries() is None
    assert database.create_journal_entry("BTC", "觀察", "冷靜", "") is None
    assert database.delete_journal_entry("00000000-0000-0000-0000-000000000000") is False


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
