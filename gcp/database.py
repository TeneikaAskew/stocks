#!/usr/bin/env python3
"""
Cloud SQL (PostgreSQL) connection utilities.

Environment variables required (set via Cloud Run job env or .env file):
    CLOUD_SQL_CONNECTION_NAME  e.g. my-project:us-east1:trading-db
    DB_USER                    e.g. trading_user
    DB_PASS                    (password)
    DB_NAME                    e.g. trading
    GCS_BUCKET                 e.g. gs://my-project-trading-data

Usage:
    from gcp.database import get_engine, upsert_dataframe, query_to_dataframe
"""

import os
import logging
from typing import Optional, List

import pandas as pd

logger = logging.getLogger(__name__)

# ── lazy imports so the module loads even without the cloud packages installed ──
_engine = None


def _connection_name() -> Optional[str]:
    return os.environ.get('CLOUD_SQL_CONNECTION_NAME')


def is_cloud_sql_configured() -> bool:
    """Return True when a database backend is configured.

    Recognises BOTH connection modes get_engine() can connect with:
      * Cloud SQL Connector — CLOUD_SQL_CONNECTION_NAME + DB_USER/PASS/NAME
        (production)
      * direct DB_HOST — DB_HOST + DB_USER/PASS/NAME (local dev / the CI
        integration-test Postgres). See _direct_db_url().

    Callers use this as a fail-fast guard before get_engine() (e.g.
    signal_monitor's loop/replay guards and persistence paths). It must
    return True for every mode get_engine() can actually use, or a
    DB_HOST run would be aborted before the direct engine is reached.
    """
    if not all(os.environ.get(v) for v in ('DB_USER', 'DB_PASS', 'DB_NAME')):
        return False
    return bool(
        os.environ.get('CLOUD_SQL_CONNECTION_NAME') or os.environ.get('DB_HOST')
    )


def _direct_db_url() -> Optional[str]:
    """Build a direct `postgresql+pg8000://` URL when `DB_HOST` is set.

    This path exists for local development and the CI integration-test
    job, which run against a plain Postgres container — NOT Cloud SQL.
    Production never sets `DB_HOST` (it sets `CLOUD_SQL_CONNECTION_NAME`),
    so the Cloud SQL Connector path in `get_engine()` is untouched in
    prod. If both are somehow set, the explicit host wins.

    Requires `DB_USER` / `DB_PASS` / `DB_NAME` alongside `DB_HOST`;
    `DB_PORT` defaults to 5432.
    """
    host = os.environ.get('DB_HOST')
    if not host:
        return None
    from urllib.parse import quote_plus
    user = quote_plus(os.environ.get('DB_USER', ''))
    password = quote_plus(os.environ.get('DB_PASS', ''))
    db = os.environ.get('DB_NAME', '')
    port = os.environ.get('DB_PORT', '5432')
    return f"postgresql+pg8000://{user}:{password}@{host}:{port}/{db}"


def get_engine():
    """Return a SQLAlchemy engine.

    Two connection modes, selected by environment:
      * `DB_HOST` set → a direct connection to a plain Postgres (local
        dev / CI integration-test container). See `_direct_db_url()`.
      * otherwise → Cloud SQL via the Python Connector (production).

    Uses a module-level singleton so connections are reused across calls.
    """
    global _engine
    if _engine is not None:
        return _engine

    direct_url = _direct_db_url()
    if direct_url:
        import sqlalchemy
        # Same pool config as the Cloud SQL engine below: pool_pre_ping
        # guards dropped connections on long local-dev sessions (same
        # failure mode as the 2026-05-14 Cloud SQL TLS postmortem), and
        # tests/test_database_pool_pre_ping.py pins all of these args.
        _engine = sqlalchemy.create_engine(
            direct_url,
            pool_size=5,
            max_overflow=2,
            pool_timeout=30,
            pool_recycle=1800,
            pool_pre_ping=True,
        )
        logger.info(
            "Direct DB engine created: %s:%s/%s",
            os.environ.get('DB_HOST'),
            os.environ.get('DB_PORT', '5432'),
            os.environ.get('DB_NAME'),
        )
        return _engine

    if not is_cloud_sql_configured():
        raise RuntimeError(
            "Cloud SQL not configured. Set CLOUD_SQL_CONNECTION_NAME, "
            "DB_USER, DB_PASS, DB_NAME environment variables "
            "(or DB_HOST for a direct/local Postgres connection)."
        )

    try:
        from google.cloud.sql.connector import Connector
        import sqlalchemy

        # refresh_strategy="lazy": refresh the ephemeral client cert on
        # demand at connect time rather than via a background scheduler.
        # The background refresher is unreliable on Cloud Run with
        # request-based CPU (throttled between requests), so the cert can
        # go stale and the next request hits a delayed/failed connection.
        connector = Connector(refresh_strategy="lazy")

        def _getconn():
            return connector.connect(
                _connection_name(),
                "pg8000",
                user=os.environ['DB_USER'],
                password=os.environ['DB_PASS'],
                db=os.environ['DB_NAME'],
            )

        _engine = sqlalchemy.create_engine(
            "postgresql+pg8000://",
            creator=_getconn,
            pool_size=5,
            max_overflow=2,
            pool_timeout=30,
            pool_recycle=1800,
            # pool_pre_ping issues a cheap SELECT 1 before handing out a
            # pooled connection — catches stale/dropped connections
            # (Cloud SQL TLS sessions can silently die mid-job during
            # long backfills; observed 2026-05-14 at [675/1038] in
            # fetch-market-data after ~2h 45m of continuous use).
            # Stale connection → ping fails → SQLAlchemy invalidates
            # and creates a fresh one. Net cost: one extra round-trip
            # per checkout (~5 ms on Cloud SQL).
            pool_pre_ping=True,
        )
        logger.info("Cloud SQL engine created: %s", _connection_name())
        return _engine

    except ImportError as e:
        raise ImportError(
            "Install cloud-sql-python-connector: "
            "pip install 'cloud-sql-python-connector[pg8000]' sqlalchemy"
        ) from e


def query_to_dataframe(sql: str, params: Optional[dict] = None) -> pd.DataFrame:
    """Run a SELECT query and return results as a DataFrame.

    Uses sqlalchemy.text() so named parameters (:name style) are handled
    correctly regardless of the underlying DBAPI (pg8000, psycopg2, etc.).
    Returns an empty DataFrame on error (so callers can fall back gracefully).

    WARNING — this SWALLOWS errors (CLAUDE.md Rule 3.7 "silent fallback").
    A connection failure / missing relation returns an empty DataFrame that
    callers cannot distinguish from a legitimate zero-row result. Do NOT use
    it where "query failed" must surface as an error (e.g. an API endpoint
    that should return 5xx on a real DB failure). Use
    ``query_to_dataframe_strict`` for those paths. (This function is left
    swallowing for the existing callers that depend on the behaviour; see the
    fallback-audit backlog.)
    """
    try:
        import sqlalchemy
        engine = get_engine()
        with engine.connect() as conn:
            return pd.read_sql(sqlalchemy.text(sql), conn, params=params)
    except Exception as e:
        logger.warning("Cloud SQL query failed: %s", e)
        return pd.DataFrame()


def query_to_dataframe_strict(sql: str, params: Optional[dict] = None) -> pd.DataFrame:
    """Run a SELECT and return a DataFrame — RAISES on any failure.

    The non-swallowing sibling of ``query_to_dataframe``. A connection error,
    missing relation, SQL error, etc. propagates to the caller instead of
    being masked as an empty DataFrame. This is the correct path for callers
    that must tell "query failed" apart from "query succeeded, zero rows" —
    e.g. the earnings API router, which turns a propagated exception into a
    real 5xx (CLAUDE.md Rule 3.7: INTERNAL failures fail loud, never fabricate
    an empty result).

    An empty DataFrame returned by this function therefore unambiguously means
    "the query ran and matched no rows", never "the DB was unreachable".
    """
    import sqlalchemy
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sqlalchemy.text(sql), conn, params=params)


# pg8000 packs the bind-parameter count as an unsigned 16-bit short, so
# any single statement with more than 65535 params crashes deep in
# `struct.pack('H', ...)`. The fixed `chunksize=2000` default is only
# safe when the target table has ≤ 32 columns; wider tables (e.g.
# `earnings_reactions` at 35+ cols, growing as PR #239/#240 add ATR and
# swing-window cols) silently overflow and the job exits 1.
#
# `_max_safe_chunksize` shrinks the requested chunksize so
# `chunksize × n_cols + safety_margin ≤ PG_PARAM_LIMIT`. The 5000-param
# margin reserves headroom for the ON CONFLICT … SET clause params (one
# per `update_col`, scaled per-row in pg_insert's compiled form).
PG_PARAM_LIMIT = 65535
_PG_PARAM_SAFETY_MARGIN = 5000


def _max_safe_chunksize(n_cols: int, requested_chunksize: int) -> int:
    # No artificial floor — Codex review on PR #256 caught that an earlier
    # `max(100, ...)` floor would silently overflow on pathologically wide
    # tables (n_cols=1000 → 100×1000 + 5000 = 105 000 > 65535, the exact
    # failure this helper exists to prevent). PostgreSQL caps tables at
    # 1600 columns, so (65535-5000) // n_cols is always >= 37 for any
    # legal table — the `max(1, …)` guard only activates on impossible
    # input and prevents `range(0, len, 0)` from crashing.
    if n_cols <= 0:
        return requested_chunksize
    max_safe = max(1, (PG_PARAM_LIMIT - _PG_PARAM_SAFETY_MARGIN) // n_cols)
    return min(requested_chunksize, max_safe)


def _coerce_int_columns(df: pd.DataFrame, tbl) -> pd.DataFrame:
    """Coerce DataFrame columns that map to INTEGER-family SQL columns
    back to int, returning a new DataFrame (the input is not mutated).

    Why this exists — the recurring ``22P02`` bug class:
        pandas widens an INTEGER column to ``float64`` the moment ANY
        row in it carries a NaN. pg8000 then binds the value as the
        string ``"15.0"`` / ``"-1.0"``, and Postgres rejects it with
        ``22P02 invalid input syntax for type integer``.

        This had been patched per-caller (``gcp/historical_signals.py``
        ``bulk_insert._INT_COLS``; ``scripts/run_backtest.py``
        ``persist_trades._INT_COLS``) — but every NEW writer that built
        an INT column with a possible NaN reintroduced it. Doing the
        coercion HERE, in the shared write path, keyed off the target
        table's reflected column types, kills the bug class for every
        caller, present and future.

    Coercion rule: NaN / None → None (SQL NULL); any other value → int.
    Non-INTEGER columns are left untouched. ``SmallInteger`` and
    ``BigInteger`` both subclass ``sqlalchemy.Integer`` so all three
    INT widths are covered by the single isinstance check.
    """
    import sqlalchemy

    int_cols = [
        c.name for c in tbl.columns
        if isinstance(c.type, sqlalchemy.Integer)
        and c.name in df.columns
    ]
    if not int_cols:
        return df

    df = df.copy()
    for col in int_cols:
        # Build an explicit object-dtype Series. A plain assignment of a
        # [int, None, int, ...] list lets pandas re-infer the column as
        # float64 (None → NaN) — re-widening it and defeating the whole
        # coercion. dtype=object pins it so the column holds real Python
        # ints and None, which pg8000 binds as INTEGER / NULL.
        df[col] = pd.Series(
            [None if pd.isna(v) else int(v) for v in df[col]],
            index=df.index,
            dtype=object,
        )
    return df


def _na_to_none_records(records: list[dict]) -> list[dict]:
    """Coerce pandas NA scalars (NaN / NaT) in row dicts to None so they bind as
    SQL NULL — NOT a float8 'NaN' literal. A NaN written into a float8 column is a
    valid, non-NULL value that silently breaks `WHERE col IS NULL` checks
    downstream (CLAUDE.md §3.7 — the same class of bug as the 2026-06-07 audit
    found in flip_price / distance_to_king_pct / distance_to_gate_pct, 56.7% of
    flip_price rows stored as NaN instead of NULL).

    Complements `_coerce_int_columns` (which already maps NaN→None for INT-family
    columns) by covering FLOAT / other columns, for ALL `upsert_dataframe`
    callers. The COPY fast path (`bulk_copy_upsert`) already renders NaN as the
    CSV NULL token; this closes the pg8000 bind fallback path.
    """
    def _fix(v):
        try:
            return None if pd.isna(v) else v
        except (TypeError, ValueError):
            return v  # non-scalar (list/array) — leave as-is
    return [{k: _fix(v) for k, v in r.items()} for r in records]


def upsert_dataframe(
    df: pd.DataFrame,
    table: str,
    conflict_cols: List[str],
    update_cols: Optional[List[str]] = None,
    chunksize: int = 2000,
) -> int:
    """Upsert a DataFrame into a Cloud SQL table using ON CONFLICT DO UPDATE.

    Parameters
    ----------
    df            : DataFrame to write
    table         : Target table name
    conflict_cols : Column(s) forming the UNIQUE constraint
    update_cols   : Columns to overwrite on conflict (defaults to all non-conflict cols)
    chunksize     : Rows per batch

    Returns the total number of rows upserted.
    """
    if df.empty:
        return 0

    import sqlalchemy
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    engine = get_engine()
    meta = sqlalchemy.MetaData()
    meta.reflect(bind=engine, only=[table])
    tbl = meta.tables[table]

    # Only keep DataFrame columns that actually exist in the table schema.
    # Extra columns in the DataFrame (e.g. from source files) would cause a
    # KeyError when building the ON CONFLICT SET clause.
    #
    # WARN on every dropped column so missing schema migrations don't hide
    # silently. Past pain: the premarket-brief computed `playbook` per
    # ticker but the column was missing from premarket_analysis, so the
    # rich playbook text was dropped invisibly on every run for weeks.
    # See PR #126 for the schema fix that added the column.
    table_col_names = {col.name for col in tbl.columns}
    dropped = [c for c in df.columns if c not in table_col_names]
    if dropped:
        logger.warning(
            "upsert_dataframe(%s): dropping %d DataFrame column(s) "
            "not present in table schema: %s. If these are meant to "
            "persist, add them to gcp/schema.sql.",
            table, len(dropped), dropped,
        )
    df = df[[c for c in df.columns if c in table_col_names]]

    # Coerce INTEGER-family columns back to int (pandas float-widening on
    # NaN → pg8000 binds "15.0" → Postgres 22P02). Keyed off the reflected
    # table schema so it's automatic for every caller. See _coerce_int_columns.
    df = _coerce_int_columns(df, tbl)

    if update_cols is None:
        update_cols = [c for c in df.columns if c not in conflict_cols]

    total = 0
    records = df.to_dict(orient='records')
    effective_chunksize = _max_safe_chunksize(len(df.columns), chunksize)
    if effective_chunksize < chunksize:
        logger.info(
            "upsert_dataframe(%s): table has %d columns; capping chunksize "
            "from %d to %d to stay under pg8000's 65535 bind-param limit.",
            table, len(df.columns), chunksize, effective_chunksize,
        )

    # Re-checkout the connection per chunk so pool_pre_ping fires each
    # time. Pre-fix this function held one `engine.begin()` checkout
    # across every chunk, which meant the TLS session that died mid-job
    # was never re-validated — the next `conn.execute()` hit the dead
    # pg8000 socket and surfaced SSL BAD_LENGTH. Codex P1 on PR #483
    # called this out. Each chunk is now its own committed transaction;
    # for idempotent upserts (ON CONFLICT DO UPDATE / DO NOTHING) this
    # is actually preferable — partial progress is durable on crash.
    # Cost: ~5 ms per checkout × N chunks.
    for i in range(0, len(records), effective_chunksize):
        # NaN/NaT → None PER CHUNK so they bind as SQL NULL, not a float8 'NaN'
        # (§3.7). Done per-chunk (not on the whole frame up front) so a large
        # table — e.g. strat_features_1m at ~1M rows — doesn't double its memory
        # and OOM (the bug that killed the 2026-06-08 SPY rebuild).
        batch = _na_to_none_records(records[i: i + effective_chunksize])
        stmt = pg_insert(tbl).values(batch)

        if update_cols:
            stmt = stmt.on_conflict_do_update(
                index_elements=conflict_cols,
                set_={col: stmt.excluded[col] for col in update_cols},
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=conflict_cols)

        with engine.begin() as conn:
            conn.execute(stmt)
        total += len(batch)

    logger.info("Upserted %d rows into %s", total, table)
    return total


def bulk_copy_upsert(
    df: pd.DataFrame,
    table: str,
    conflict_cols: List[str],
    update_cols: Optional[List[str]] = None,
) -> int:
    """Fast bulk upsert via psycopg2 COPY FROM STDIN → temp table → INSERT ... ON CONFLICT.

    10-30× faster than `upsert_dataframe()` (which uses pg8000 per-row binds)
    for large DataFrames. Uses the same Cloud SQL Connector but with the
    psycopg2 driver path. Falls back to `upsert_dataframe()` if psycopg2
    isn't installed or the COPY path errors.

    Implementation:
      1. Open psycopg2 connection via Cloud SQL Connector
      2. CREATE TEMPORARY TABLE matching target schema
      3. COPY FROM STDIN (CSV) into temp — single binary stream, no per-row
         binds, no parameter-count limit
      4. INSERT INTO target SELECT * FROM temp ON CONFLICT DO UPDATE
      5. Drop temp (implicit on connection close)

    Why this matters: pg8000's bind-param limit caps row throughput at
    ~890 rows per round-trip. With a ~1M row 1-min bar table that's
    1,124 round-trips × 1-2s each = 20-40 min per upsert. COPY does the
    same volume in ~30s.
    """
    if df.empty:
        return 0

    try:
        import psycopg2
    except ImportError:
        logger.warning("psycopg2 not installed — falling back to upsert_dataframe()")
        return upsert_dataframe(df, table, conflict_cols, update_cols)

    # Reflect target columns first so we drop extra DataFrame cols (same
    # safety check as upsert_dataframe) before COPY.
    import sqlalchemy
    engine = get_engine()
    meta = sqlalchemy.MetaData()
    meta.reflect(bind=engine, only=[table])
    tbl = meta.tables[table]
    table_col_names = {col.name for col in tbl.columns}
    dropped = [c for c in df.columns if c not in table_col_names]
    if dropped:
        logger.warning("bulk_copy_upsert(%s): dropping %d cols not in schema: %s",
                        table, len(dropped), dropped[:5])
    df = df[[c for c in df.columns if c in table_col_names]].copy()

    cols = list(df.columns)
    if update_cols is None:
        update_cols = [c for c in cols if c not in conflict_cols]

    # Use pg8000's native COPY support via the existing Cloud SQL engine.
    # google-cloud-sql-python-connector only supports pg8000/asyncpg drivers
    # (not psycopg2), so we route COPY through pg8000.copy_from on the raw
    # connection. Much simpler than swapping drivers.
    try:
        engine = get_engine()
        raw_conn = engine.raw_connection()
    except Exception as e:
        logger.warning("bulk_copy_upsert(%s): raw_connection failed (%s); fallback", table, e)
        return upsert_dataframe(df, table, conflict_cols, update_cols)

    try:
        import uuid, io
        temp_name = f"tmp_upsert_{table}_{uuid.uuid4().hex[:8]}"

        # pg8000 has NO psycopg2-style cur.copy_from(); its native COPY is
        # cur.execute("COPY ... FROM STDIN WITH (FORMAT CSV ...)", stream=sio).
        # Use real CSV (quoted) so embedded commas/newlines are safe; NULLs as
        # an explicit sentinel via the CSV NULL option.
        sio = io.StringIO()
        df.to_csv(sio, index=False, header=False, na_rep='\\N')
        sio.seek(0)

        # pg8000's cursor does NOT have copy_from (that is psycopg2's API — the
        # prior code silently failed every call and fell back to the slow
        # upsert_dataframe, defeating this fast path and reintroducing the
        # float8-NaN write bug). pg8000 does COPY via execute(..., stream=...).
        cur = raw_conn.cursor()
        try:
            cur.execute(
                f"CREATE TEMPORARY TABLE {temp_name} (LIKE {table} INCLUDING DEFAULTS) "
                f"ON COMMIT DROP"
            )

            col_list_copy = ", ".join(f'"{c}"' for c in cols)
            cur.execute(
                f"COPY {temp_name} ({col_list_copy}) FROM STDIN "
                f"WITH (FORMAT CSV, NULL '\\N')",
                stream=sio,
            )
            copied = cur.rowcount if cur.rowcount and cur.rowcount > 0 else len(df)
            col_list = ", ".join(f'"{c}"' for c in cols)

            conflict_clause = ", ".join(f'"{c}"' for c in conflict_cols)
            update_clause = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in update_cols)
            cur.execute(
                f"INSERT INTO {table} ({col_list}) "
                f"SELECT {col_list} FROM {temp_name} "
                f"ON CONFLICT ({conflict_clause}) DO UPDATE SET {update_clause}"
            )
            upserted = cur.rowcount if cur.rowcount and cur.rowcount > 0 else copied
        finally:
            try: cur.close()
            except Exception: pass

        raw_conn.commit()
        logger.info("bulk_copy_upsert(%s): COPY'd %d rows, upserted %d",
                     table, copied, upserted)
        return upserted
    except Exception as e:
        try: raw_conn.rollback()
        except Exception: pass
        logger.warning("bulk_copy_upsert(%s) COPY path failed (%s); fallback to upsert_dataframe",
                        table, e)
        return upsert_dataframe(df, table, conflict_cols, update_cols)
    finally:
        try: raw_conn.close()
        except Exception: pass


def bulk_copy_update(
    df: pd.DataFrame,
    table: str,
    key_cols: List[str],
    update_cols: List[str],
) -> int:
    """Bulk UPDATE-only of `update_cols` on existing rows, keyed by `key_cols`.

    Unlike bulk_copy_upsert this NEVER inserts: it COPYs (keys + update_cols)
    into a temp table, then `UPDATE target SET col=t.col FROM temp WHERE keys
    match`. Use when you are backfilling a column SUBSET on rows that already
    exist and the target has NOT-NULL columns you are deliberately not touching
    (an INSERT...ON CONFLICT would still validate NOT-NULL on the insert attempt
    and fail). Rows present in `df` but absent in `target` are silently ignored
    (no insert). Idempotent. Falls back to a pg8000 per-row UPDATE on COPY error.
    """
    df = df[[c for c in df.columns if c in (set(key_cols) | set(update_cols))]].copy()
    cols = list(df.columns)
    try:
        engine = get_engine()
        raw_conn = engine.raw_connection()
    except Exception as e:
        logger.warning("bulk_copy_update(%s): raw_connection failed (%s)", table, e)
        raise

    try:
        import uuid, io
        temp_name = f"tmp_update_{table}_{uuid.uuid4().hex[:8]}"
        sio = io.StringIO()
        df.to_csv(sio, index=False, header=False, na_rep='\\N')
        sio.seek(0)
        col_defs = ", ".join(f'"{c}" DOUBLE PRECISION' if c not in key_cols
                             else (f'"{c}" TIMESTAMPTZ' if 'ts' in c else f'"{c}" TEXT')
                             for c in cols)
        cur = raw_conn.cursor()
        try:
            cur.execute(f"CREATE TEMPORARY TABLE {temp_name} ({col_defs}) ON COMMIT DROP")
            col_list = ", ".join(f'"{c}"' for c in cols)
            cur.execute(
                f"COPY {temp_name} ({col_list}) FROM STDIN WITH (FORMAT CSV, NULL '\\N')",
                stream=sio,
            )
            set_clause = ", ".join(f'"{c}" = t."{c}"' for c in update_cols)
            where = " AND ".join(f'{table}."{k}" = t."{k}"' for k in key_cols)
            cur.execute(
                f"UPDATE {table} SET {set_clause} FROM {temp_name} t WHERE {where}"
            )
            updated = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        finally:
            try: cur.close()
            except Exception: pass
        raw_conn.commit()
        logger.info("bulk_copy_update(%s): updated %d rows (%d cols)",
                     table, updated, len(update_cols))
        return updated
    except Exception as e:
        try: raw_conn.rollback()
        except Exception: pass
        logger.warning("bulk_copy_update(%s) COPY path failed (%s)", table, e)
        raise
    finally:
        try: raw_conn.close()
        except Exception: pass


def bulk_insert_dataframe(
    df: pd.DataFrame,
    table: str,
    chunksize: int = 2000,
) -> int:
    """Bulk insert a DataFrame using SQLAlchemy Core (no conflict handling).

    Uses SQLAlchemy Table.insert() rather than pandas to_sql() to avoid two
    known failure modes with the pg8000 driver:

    1. pg8000 parameter count limit (65535 max, 2-byte unsigned short).
       pandas 'multi' method sends all columns × chunksize params in one call.
       At 9 columns × 10 000 rows = 90 000 params → struct.pack('H', ...) crash.
       We cap each batch at chunksize rows (default 2 000 → 18 000 params, safe
       for tables with up to 32 columns).

    2. Partitioned tables (LIST / RANGE).
       pandas inspect().has_table() may return False for partitioned tables,
       causing to_sql(if_exists='append') to attempt CREATE TABLE and fail with
       'relation already exists'.  SQLAlchemy MetaData.reflect() handles this
       correctly.

    Use for initial data loads where duplicates won't exist.
    """
    if df.empty:
        return 0

    import sqlalchemy

    engine = get_engine()
    meta = sqlalchemy.MetaData()
    meta.reflect(bind=engine, only=[table])
    tbl = meta.tables[table]

    # Only keep DataFrame columns that exist in the table schema.
    table_col_names = {col.name for col in tbl.columns}
    df = df[[c for c in df.columns if c in table_col_names]]

    # Coerce INTEGER-family columns back to int — see _coerce_int_columns.
    df = _coerce_int_columns(df, tbl)

    records = df.to_dict(orient='records')
    total = 0
    effective_chunksize = _max_safe_chunksize(len(df.columns), chunksize)
    if effective_chunksize < chunksize:
        logger.info(
            "bulk_insert_dataframe(%s): table has %d columns; capping "
            "chunksize from %d to %d to stay under pg8000's 65535 bind-param "
            "limit.",
            table, len(df.columns), chunksize, effective_chunksize,
        )

    # Commit after every batch rather than wrapping all rows in one giant
    # transaction. A single transaction for millions of rows creates
    # excessive WAL pressure on Cloud SQL and may never commit within
    # query-timeout limits.
    #
    # Re-checkout the connection per chunk so pool_pre_ping fires each
    # time. Pre-fix this function held one `engine.connect()` checkout
    # across every chunk, which meant the TLS session that died mid-job
    # was never re-validated — the next `conn.execute()` hit the dead
    # pg8000 socket and surfaced SSL BAD_LENGTH (Codex P1 on PR #483).
    # `engine.begin()` checkouts + auto-commits per chunk.
    for i in range(0, len(records), effective_chunksize):
        batch = records[i: i + effective_chunksize]
        # Use .values(batch) to emit ONE multi-row INSERT per chunk, not
        # executemany (conn.execute(stmt, list)) which sends one INSERT
        # per row and is extremely slow for millions of rows.
        with engine.begin() as conn:
            conn.execute(tbl.insert().values(batch))
        total += len(batch)

    logger.info("Bulk-inserted %d rows into %s", total, table)
    return total


def table_exists(table: str) -> bool:
    """Return True if the table exists in the connected database."""
    try:
        engine = get_engine()
        import sqlalchemy
        return sqlalchemy.inspect(engine).has_table(table)
    except Exception:
        return False


def row_exists(table: str, where: dict) -> bool:
    """Return True if at least one row matches the where-dict.

    Used by the brief/pipeline jobs to decide whether to UPSERT or
    skip a current-table write when the canonical morning row is
    being protected (Phase 2 of MORNING_RUN_PROTECTION_PLAN).

    Returns False on Cloud SQL unreachable (callers fall back to
    INSERT, which will then raise on unique-constraint violation —
    surfacing the connection issue instead of silently skipping).
    """
    if not where:
        raise ValueError("row_exists requires a non-empty where-dict")
    if not is_cloud_sql_configured():
        return False
    where_clause = ' AND '.join(f"{k} = :{k}" for k in where)
    sql = f"SELECT 1 FROM {table} WHERE {where_clause} LIMIT 1"
    try:
        df = query_to_dataframe(sql, where)
        return not df.empty
    except Exception as e:
        logger.warning("row_exists(%s, %s) failed: %s", table, where, e)
        return False


def execute_sql(sql: str, params: Optional[dict] = None) -> None:
    """Execute a non-SELECT statement (INSERT, UPDATE, DELETE, DDL)."""
    engine = get_engine()
    import sqlalchemy
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text(sql), params or {})


# Single source of truth for `lib.indicators.add_all_indicators()` output
# column names → `market_data_daily` SQL column names. Imported by both
# `gcp/fetchers/fetch_market_data.py` (live writer) and `gcp/migrate_to_gcp.py`
# (one-shot migrator) so the two paths can't drift on rename.
DAILY_INDICATOR_TO_SQL_COLUMN: dict[str, str] = {
    'RSI14':          'rsi_14',
    'RSI9':           'rsi_9',
    'RSI30':          'rsi_30',
    'ATR14':          'atr_14',
    'ATR20':          'atr_20',
    'EMA9':           'ema_9',
    'EMA20':          'ema_20',
    'EMA50':          'ema_50',
    'SMA5':           'ma_5',
    'SMA10':          'ma_10',
    'SMA20':          'ma_20',
    'SMA50':          'ma_50',
    'SMA200':         'sma_200',
    'MACD':           'macd',
    'MACD_Signal':    'macd_signal',
    'MACD_Histogram': 'macd_histogram',
    'BB_Upper':       'bb_upper',
    'BB_Lower':       'bb_lower',
    'BB_Width':       'bb_width',
    'BB_Pct':         'bb_pct',
    'StochRSI_K':     'stoch_rsi_k',
    'StochRSI_D':     'stoch_rsi_d',
    'OBV':            'obv',
    'RVOL':           'rvol',
    'Consecutive_Up':   'consecutive_up',
    'Consecutive_Down': 'consecutive_down',
    'Price_vs_EMA9':    'price_vs_ema9',
    'Price_vs_EMA20':   'price_vs_ema20',
    # Sourced from `add_all_indicators` (snake_case keys match SQL cols).
    'volatility_20d':   'volatility_20d',
    'volatility_5d':    'volatility_5d',
    'high_low_spread':     'high_low_spread',
    'high_low_spread_pct': 'high_low_spread_pct',
    # Promoted 2026-05-31 (daily-meaningful subset; Mins_Since_Open and
    # Price_vs_VWAP_ATR omitted — no intraday clock / degenerate daily VWAP).
    'Realized_Vol_Short': 'realized_vol_short',
    'Price_vs_EMA9_ATR':  'price_vs_ema9_atr',
    'Price_vs_EMA20_ATR': 'price_vs_ema20_atr',
    'EMA_Spread_ATR':     'ema_spread_atr',
    'EMA9_Slope':         'ema9_slope',
    'BB_Squeeze':         'bb_squeeze',
    'RSI_Divergence':     'rsi_divergence',
}
