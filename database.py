import json
import logging
import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
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


def load_watchlist(list_type: str) -> Optional[dict[str, str]]:
    if not DATABASE_URL:
        return None

    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT display_name, symbol
                    FROM watchlists
                    WHERE owner_key = 'global' AND list_type = %s
                    ORDER BY display_name
                    """,
                    (list_type,),
                )
                return {display_name: symbol for display_name, symbol in cur.fetchall()}
    except Exception as exc:  # noqa: BLE001
        logger.warning("讀取 watchlists 失敗（%s）：%s", list_type, exc)
        return None


def upsert_watchlist_item(list_type: str, display_name: str, symbol: str) -> None:
    if not DATABASE_URL:
        return

    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO watchlists (owner_key, list_type, display_name, symbol, updated_at)
                    VALUES ('global', %s, %s, %s, now())
                    ON CONFLICT (owner_key, list_type, display_name) DO UPDATE SET
                        symbol = EXCLUDED.symbol,
                        updated_at = now()
                    """,
                    (list_type, display_name, symbol),
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("寫入 watchlist 失敗（%s:%s）：%s", list_type, display_name, exc)


def delete_watchlist_item(list_type: str, display_name: str) -> None:
    if not DATABASE_URL:
        return

    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM watchlists
                    WHERE owner_key = 'global' AND list_type = %s AND display_name = %s
                    """,
                    (list_type, display_name),
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("刪除 watchlist 失敗（%s:%s）：%s", list_type, display_name, exc)


def seed_watchlist_if_empty(list_type: str, items: dict[str, str]) -> None:
    if not DATABASE_URL:
        return

    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM watchlists WHERE owner_key = 'global' AND list_type = %s",
                    (list_type,),
                )
                if cur.fetchone()[0] > 0:
                    return
                cur.executemany(
                    """
                    INSERT INTO watchlists (owner_key, list_type, display_name, symbol, updated_at)
                    VALUES ('global', %(list_type)s, %(display_name)s, %(symbol)s, now())
                    ON CONFLICT (owner_key, list_type, display_name) DO NOTHING
                    """,
                    [
                        {"list_type": list_type, "display_name": display_name, "symbol": symbol}
                        for display_name, symbol in items.items()
                    ],
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("初始化 watchlist 失敗（%s）：%s", list_type, exc)


def list_journal_entries(limit: int = 50) -> Optional[list[dict]]:
    if not DATABASE_URL:
        return None

    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id::text, symbol, direction, setup, note, created_at
                    FROM journal_entries
                    WHERE owner_key = 'global'
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                return [
                    {
                        "id": entry_id,
                        "symbol": symbol,
                        "action": direction,
                        "emotion": setup,
                        "note": note,
                        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
                    }
                    for entry_id, symbol, direction, setup, note, created_at in cur.fetchall()
                ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("讀取 journal_entries 失敗：%s", exc)
        return None


def create_journal_entry(symbol: str, action: str, emotion: str, note: str) -> Optional[dict]:
    if not DATABASE_URL:
        return None

    entry_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO journal_entries (
                        id, owner_key, entry_date, symbol, direction, setup, result, note, created_at, updated_at
                    )
                    VALUES (%s, 'global', %s, %s, %s, %s, 'open', %s, %s, %s)
                    """,
                    (entry_id, date.fromisoformat(created_at.date().isoformat()), symbol, action, emotion, note, created_at, created_at),
                )
        return {
            "id": entry_id,
            "symbol": symbol,
            "action": action,
            "emotion": emotion,
            "note": note,
            "created_at": created_at.isoformat(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("寫入 journal_entries 失敗：%s", exc)
        return None


def delete_journal_entry(entry_id: str) -> bool:
    if not DATABASE_URL:
        return False

    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM journal_entries WHERE owner_key = 'global' AND id = %s",
                    (entry_id,),
                )
                return cur.rowcount > 0
    except Exception as exc:  # noqa: BLE001
        logger.warning("刪除 journal_entries 失敗（%s）：%s", entry_id, exc)
        return False


def load_risk_settings() -> Optional[dict]:
    if not DATABASE_URL:
        return None

    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT account_size, risk_pct, max_leverage, payload, updated_at
                    FROM risk_settings
                    WHERE owner_key = 'global'
                    """,
                )
                row = cur.fetchone()
                if not row:
                    return None

                account_size, risk_pct, max_leverage, payload, updated_at = row
                payload_dict = payload if isinstance(payload, dict) else {}
                return _jsonable(
                    {
                        **payload_dict,
                        "account_size": account_size,
                        "risk_pct": risk_pct,
                        "max_leverage": max_leverage,
                        "updated_at": updated_at,
                    }
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("讀取 risk_settings 失敗：%s", exc)
        return None


def upsert_risk_settings(account_size: float, risk_pct: float, max_leverage: int) -> Optional[dict]:
    if not DATABASE_URL:
        return None

    payload = {
        "account_size": account_size,
        "risk_pct": risk_pct,
        "max_leverage": max_leverage,
    }
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO risk_settings (
                        owner_key, account_size, risk_pct, max_leverage, payload, updated_at
                    )
                    VALUES ('global', %s, %s, %s, %s::jsonb, now())
                    ON CONFLICT (owner_key) DO UPDATE SET
                        account_size = EXCLUDED.account_size,
                        risk_pct = EXCLUDED.risk_pct,
                        max_leverage = EXCLUDED.max_leverage,
                        payload = EXCLUDED.payload,
                        updated_at = now()
                    RETURNING account_size, risk_pct, max_leverage, updated_at
                    """,
                    (account_size, risk_pct, max_leverage, json.dumps(payload, ensure_ascii=False)),
                )
                saved_account_size, saved_risk_pct, saved_max_leverage, updated_at = cur.fetchone()
                return _jsonable(
                    {
                        "account_size": saved_account_size,
                        "risk_pct": saved_risk_pct,
                        "max_leverage": saved_max_leverage,
                        "updated_at": updated_at,
                    }
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("寫入 risk_settings 失敗：%s", exc)
        return None


def _jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _parse_datetime(value):
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def insert_trade_history(strategy: str, record: dict) -> None:
    if not DATABASE_URL:
        return

    symbol = str(record.get("symbol") or record.get("display_name") or "").strip()
    if not symbol:
        return

    opened_at = _parse_datetime(record.get("opened_at"))
    closed_at = _parse_datetime(record.get("closed_at"))
    payload = json.dumps(record, ensure_ascii=False, default=str)

    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trade_history (
                        strategy, symbol, side, result, entry_price, exit_price, take_profit,
                        stop_loss, leverage, pnl_pct, opened_at, closed_at, payload
                    )
                    SELECT
                        %(strategy)s, %(symbol)s, %(side)s, %(result)s, %(entry_price)s, %(exit_price)s,
                        %(take_profit)s, %(stop_loss)s, %(leverage)s, %(pnl_pct)s,
                        %(opened_at)s, %(closed_at)s, %(payload)s::jsonb
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM trade_history
                        WHERE strategy = %(strategy)s
                          AND symbol = %(symbol)s
                          AND opened_at IS NOT DISTINCT FROM %(opened_at)s
                          AND closed_at IS NOT DISTINCT FROM %(closed_at)s
                    )
                    """,
                    {
                        "strategy": strategy,
                        "symbol": symbol,
                        "side": record.get("side"),
                        "result": record.get("result"),
                        "entry_price": record.get("entry_price"),
                        "exit_price": record.get("exit_price"),
                        "take_profit": record.get("take_profit"),
                        "stop_loss": record.get("stop_loss"),
                        "leverage": record.get("leverage"),
                        "pnl_pct": record.get("pnl_pct"),
                        "opened_at": opened_at,
                        "closed_at": closed_at,
                        "payload": payload,
                    },
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("寫入 trade_history 失敗（%s:%s）：%s", strategy, symbol, exc)


def list_trade_history(strategy: str, *, symbol: Optional[str] = None, limit: int = 50) -> Optional[list[dict]]:
    if not DATABASE_URL:
        return None

    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                params: list[object] = [strategy]
                symbol_clause = ""
                if symbol:
                    symbol_clause = "AND symbol = %s"
                    params.append(symbol)
                params.append(limit)
                cur.execute(
                    f"""
                    SELECT
                        symbol, side, result, entry_price, exit_price, take_profit,
                        stop_loss, leverage, pnl_pct, opened_at, closed_at, payload
                    FROM trade_history
                    WHERE strategy = %s {symbol_clause}
                    ORDER BY closed_at DESC NULLS LAST, created_at DESC
                    LIMIT %s
                    """,
                    params,
                )
                records: list[dict] = []
                for row in cur.fetchall():
                    (
                        row_symbol,
                        side,
                        result,
                        entry_price,
                        exit_price,
                        take_profit,
                        stop_loss,
                        leverage,
                        pnl_pct,
                        opened_at,
                        closed_at,
                        payload,
                    ) = row
                    payload_dict = payload if isinstance(payload, dict) else {}
                    record = dict(payload_dict)
                    record.update(
                        {
                            "symbol": row_symbol,
                            "side": side,
                            "result": result,
                            "entry_price": _jsonable(entry_price),
                            "exit_price": _jsonable(exit_price),
                            "take_profit": _jsonable(take_profit),
                            "stop_loss": _jsonable(stop_loss),
                            "leverage": leverage,
                            "pnl_pct": _jsonable(pnl_pct),
                            "opened_at": _jsonable(opened_at),
                            "closed_at": _jsonable(closed_at),
                        }
                    )
                    records.append(_jsonable(record))
                return records
    except Exception as exc:  # noqa: BLE001
        logger.warning("讀取 trade_history 失敗（%s）：%s", strategy, exc)
        return None
