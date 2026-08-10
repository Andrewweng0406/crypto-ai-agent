import database


def test_database_disabled_without_url(monkeypatch):
    monkeypatch.setattr(database, "DATABASE_URL", None)

    assert database.is_database_enabled() is False
    assert database.init_database() is False
    database.upsert_data_source_health([])
    database.insert_ingest_event("source", "event", {})


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
