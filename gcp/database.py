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
    """Return True when all required Cloud SQL env vars are present."""
    return all(
        os.environ.get(v)
        for v in ('CLOUD_SQL_CONNECTION_NAME', 'DB_USER', 'DB_PASS', 'DB_NAME')
    )


def get_engine():
    """Return a SQLAlchemy engine connected to Cloud SQL via the Python Connector.

    Uses a module-level singleton so connections are reused across calls.
    """
    global _engine
    if _engine is not None:
        return _engine

    if not is_cloud_sql_configured():
        raise RuntimeError(
            "Cloud SQL not configured. Set CLOUD_SQL_CONNECTION_NAME, "
            "DB_USER, DB_PASS, DB_NAME environment variables."
        )

    try:
        from google.cloud.sql.connector import Connector
        import sqlalchemy

        connector = Connector()

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

    Returns an empty DataFrame on error (so callers can fall back gracefully).
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            return pd.read_sql(sql, conn, params=params)
    except Exception as e:
        logger.warning("Cloud SQL query failed: %s", e)
        return pd.DataFrame()


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

    if update_cols is None:
        update_cols = [c for c in df.columns if c not in conflict_cols]

    total = 0
    records = df.to_dict(orient='records')

    with engine.begin() as conn:
        for i in range(0, len(records), chunksize):
            batch = records[i: i + chunksize]
            stmt = pg_insert(tbl).values(batch)

            if update_cols:
                stmt = stmt.on_conflict_do_update(
                    index_elements=conflict_cols,
                    set_={col: stmt.excluded[col] for col in update_cols},
                )
            else:
                stmt = stmt.on_conflict_do_nothing(index_elements=conflict_cols)

            conn.execute(stmt)
            total += len(batch)

    logger.info("Upserted %d rows into %s", total, table)
    return total


def bulk_insert_dataframe(
    df: pd.DataFrame,
    table: str,
    chunksize: int = 5000,
) -> int:
    """Fast bulk insert using pandas to_sql (no conflict handling).

    Use for initial data loads where duplicates won't exist.
    """
    if df.empty:
        return 0
    engine = get_engine()
    rows = df.to_sql(
        table,
        engine,
        if_exists='append',
        index=False,
        chunksize=chunksize,
        method='multi',
    )
    logger.info("Bulk-inserted %s rows into %s", rows, table)
    return rows or 0


def table_exists(table: str) -> bool:
    """Return True if the table exists in the connected database."""
    try:
        engine = get_engine()
        import sqlalchemy
        return sqlalchemy.inspect(engine).has_table(table)
    except Exception:
        return False


def execute_sql(sql: str, params: Optional[dict] = None) -> None:
    """Execute a non-SELECT statement (INSERT, UPDATE, DELETE, DDL)."""
    engine = get_engine()
    import sqlalchemy
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text(sql), params or {})
