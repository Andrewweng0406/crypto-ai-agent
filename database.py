import json
import logging
import os
from typing import Iterable, Optional

logger = logging.getLogger("trading_signal.database")

DATABASE_URL = os.environ.get("DATABASE_URL")

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS signal_snapshots (
            id BIGSERIAL PRIMARY KEY,
            source TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT,
            status TEXT,
            entry_price NUMERIC,
            current_price NUMERIC,
            take_profit NUMERIC,
            stop_loss NUMERIC,
            leverage INTEGER,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_signal_snapshots_source_created
            ON signal_snapshots (source, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_signal_snapshots_symbol_created
            ON signal_snapshots (symbol, created_at DESC);

        CREATE TABLE IF NOT EXISTS trade_history (
            id BIGSERIAL PRIMARY KEY,
            strategy TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT,
            result TEXT,
            entry_price NUMERIC,
            exit_price NUMERIC,
            take_profit NUMERIC,
            stop_loss NUMERIC,
            leverage INTEGER,
            pnl_pct NUMERIC,
            opened_at TIMESTAMPTZ,
            closed_at TIMESTAMPTZ,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_trade_history_strategy_closed
            ON trade_history (strategy, closed_at DESC);
        CREATE INDEX IF NOT EXISTS idx_trade_history_symbol_closed
            ON trade_history (symbol, closed_at DESC);

        CREATE TABLE IF NOT EXISTS watchlists (
            id BIGSERIAL PRIMARY KEY,
            owner_key TEXT NOT NULL DEFAULT 'global',
            list_type TEXT NOT NULL,
            display_name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (owner_key, list_type, display_name)
        );

        CREATE TABLE IF NOT EXISTS journal_entries (
            id UUID PRIMARY KEY,
            owner_key TEXT NOT NULL DEFAULT 'global',
            entry_date DATE NOT NULL,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            setup TEXT NOT NULL,
            result TEXT NOT NULL,
            note TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_journal_entries_owner_date
            ON journal_entries (owner_key, entry_date DESC);

        CREATE TABLE IF NOT EXISTS risk_settings (
            owner_key TEXT PRIMARY KEY DEFAULT 'global',
            account_size NUMERIC,
            risk_pct NUMERIC,
            max_leverage INTEGER,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS data_source_health (
            source TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('starting', 'ok', 'stale', 'error', 'disabled')),
            last_success_at TIMESTAMPTZ,
            last_error_at TIMESTAMPTZ,
            last_error TEXT,
            latency_ms DOUBLE PRECISION,
            stale_after_seconds INTEGER NOT NULL,
            records_seen INTEGER NOT NULL DEFAULT 0,
            is_stale BOOLEAN NOT NULL DEFAULT false,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_data_source_health_status
            ON data_source_health (status, updated_at DESC);

        CREATE TABLE IF NOT EXISTS ingest_events (
            id BIGSERIAL PRIMARY KEY,
            source TEXT NOT NULL,
            event_type TEXT NOT NULL,
            symbol TEXT,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            received_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_ingest_events_source_received
            ON ingest_events (source, received_at DESC);
        """,
    )
]


def is_database_enabled() -> bool:
    return bool(DATABASE_URL)


def _connect():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    import psycopg

    return psycopg.connect(DATABASE_URL, autocommit=True)


def init_database() -> bool:
    if not DATABASE_URL:
        logger.info("DATABASE_URL 未設定，Postgres 持久化停用；系統會沿用記憶體/JSON快照模式")
        return False

    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                for version, sql in MIGRATIONS:
                    cur.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (version,))
                    if cur.fetchone():
                        continue
                    for statement in sql.split(";"):
                        statement = statement.strip()
                        if statement:
                            cur.execute(statement)
                    cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
                    logger.info("Postgres migration %s 已套用", version)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Postgres 初始化失敗，將暫時退回記憶體/JSON快照模式：%s", exc)
        return False


def upsert_data_source_health(items: Iterable[dict]) -> None:
    if not DATABASE_URL:
        return

    rows = list(items)
    if not rows:
        return

    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO data_source_health (
                        source, label, status, last_success_at, last_error_at, last_error,
                        latency_ms, stale_after_seconds, records_seen, is_stale, payload, updated_at
                    )
                    VALUES (
                        %(source)s, %(label)s, %(status)s, %(last_success_at)s, %(last_error_at)s,
                        %(last_error)s, %(latency_ms)s, %(stale_after_seconds)s, %(records_seen)s,
                        %(is_stale)s, %(payload)s::jsonb, now()
                    )
                    ON CONFLICT (source) DO UPDATE SET
                        label = EXCLUDED.label,
                        status = EXCLUDED.status,
                        last_success_at = EXCLUDED.last_success_at,
                        last_error_at = EXCLUDED.last_error_at,
                        last_error = EXCLUDED.last_error,
                        latency_ms = EXCLUDED.latency_ms,
                        stale_after_seconds = EXCLUDED.stale_after_seconds,
                        records_seen = EXCLUDED.records_seen,
                        is_stale = EXCLUDED.is_stale,
                        payload = EXCLUDED.payload,
                        updated_at = now()
                    """,
                    [
                        {
                            **row,
                            "payload": json.dumps(row, ensure_ascii=False, default=str),
                        }
                        for row in rows
                    ],
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("寫入 data_source_health 失敗：%s", exc)


def insert_ingest_event(source: str, event_type: str, payload: dict, *, symbol: Optional[str] = None) -> None:
    if not DATABASE_URL:
        return

    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ingest_events (source, event_type, symbol, payload)
                    VALUES (%s, %s, %s, %s::jsonb)
                    """,
                    (source, event_type, symbol, json.dumps(payload, ensure_ascii=False, default=str)),
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("寫入 ingest_events 失敗：%s", exc)
