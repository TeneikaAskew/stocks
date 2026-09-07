#!/usr/bin/env python3
"""
Trade logger — appends trades to Cloud SQL and/or daily parquet files.

Used by the signal monitor and can also be fed manually.

When CLOUD_SQL_CONNECTION_NAME is set, trades are written to the Cloud SQL
`trades` table AND to a local Parquet file for redundancy.  Reads prefer
Cloud SQL; falls back to local Parquet files when Cloud SQL is unavailable.
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

log = logging.getLogger(__name__)


def _cloud_sql_active() -> bool:
    return bool(os.environ.get('CLOUD_SQL_CONNECTION_NAME'))


class TradeLogger:
    """Log trades to Cloud SQL (primary) and local Parquet (fallback/redundancy)."""

    def __init__(self, output_dir: str = 'data/trades'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _daily_file(self, date=None) -> Path:
        if date is None:
            date = datetime.now().date()
        return self.output_dir / f'{date}.parquet'

    def log_trade(self, trade_data: dict):
        """Append a trade record to Cloud SQL and today's Parquet file.

        trade_data should include:
            ticker, direction, entry_time, entry_price, exit_time,
            exit_price, exit_reason, signal_strength, position_size,
            return_pct, conditions_met, strat_combo, ftfc_score
        """
        # `conditions_met` lands as a Python list — SQLAlchemy + pg8000
        # adapt it to native JSONB array (the column is JSONB). PyArrow
        # also handles list columns in Parquet natively. Calling
        # `json.dumps(...)` here was the bug that produced JSONB-string-of-
        # array rows in the `trades` table; same root cause as
        # `signal_alerts.conditions_met`. See Track D audit § 6 / G.P0.6.
        serialized = dict(trade_data)

        if 'trade_date' not in serialized:
            serialized['trade_date'] = str(datetime.now().date())

        # ── Cloud SQL write ──────────────────────────────────────────────────
        if _cloud_sql_active():
            try:
                from gcp.database import upsert_dataframe
                row_df = pd.DataFrame([serialized])
                # entry_time is the natural unique key per trade
                conflict_cols = ['ticker', 'entry_time']
                if 'entry_time' in row_df.columns and row_df['entry_time'].notna().all():
                    upsert_dataframe(row_df, 'trades', conflict_cols)
                else:
                    from gcp.database import bulk_insert_dataframe
                    bulk_insert_dataframe(row_df, 'trades')
            except Exception as e:
                log.warning("Cloud SQL trade write failed: %s", e)

        # ── Local Parquet write (always, as redundant backup) ────────────────
        row = pd.DataFrame([trade_data])
        path = self._daily_file()

        if path.exists():
            existing = pd.read_parquet(path)
            combined = pd.concat([existing, row], ignore_index=True)
        else:
            combined = row

        combined.to_parquet(path, index=False)

    # trades.run_kind separates live monitor trades from the rows a deleted
    # backfill script wrote ('backfill') and tagged replays ('replay'). The
    # readers default to live so the weekend review, like the API readers,
    # never counts simulated rows (Codex on #1022); run_kind=None reads
    # every kind, matching DataLoader.load_trades.
    @staticmethod
    def _run_kind_clause(run_kind, params: dict) -> str:
        if run_kind is None:
            return ""
        params['rk'] = run_kind
        return " AND run_kind = :rk"

    def get_daily_trades(self, date=None, run_kind='live') -> pd.DataFrame:
        """Load trades for a specific date (Cloud SQL preferred, Parquet fallback)."""
        if _cloud_sql_active():
            try:
                from gcp.database import query_to_dataframe
                date_str = str(date or datetime.now().date())
                params = {'d': date_str}
                df = query_to_dataframe(
                    "SELECT * FROM trades WHERE trade_date = :d"
                    + self._run_kind_clause(run_kind, params)
                    + " ORDER BY entry_time",
                    params,
                )
                if not df.empty:
                    return df
            except Exception as e:
                # AUDIT-2026-05-13: silent fallback — a failed query falls
                # through to the Parquet files below
                log.warning("Cloud SQL daily trades query failed: %s", e)

        # Parquet fallback
        path = self._daily_file(date)
        if path.exists():
            return pd.read_parquet(path)
        return pd.DataFrame()

    def get_weekly_trades(self, week_end_date=None, run_kind='live') -> pd.DataFrame:
        """Load all trades from the past 7 days (Cloud SQL preferred)."""
        if _cloud_sql_active():
            try:
                from gcp.database import query_to_dataframe
                if week_end_date is None:
                    week_end_date = datetime.now().date()
                start = week_end_date - pd.Timedelta(days=6)
                params = {'start': str(start), 'end': str(week_end_date)}
                df = query_to_dataframe(
                    "SELECT * FROM trades WHERE trade_date BETWEEN :start AND :end"
                    + self._run_kind_clause(run_kind, params)
                    + " ORDER BY entry_time",
                    params,
                )
                if not df.empty:
                    return df
            except Exception as e:
                # AUDIT-2026-05-13: silent fallback — a failed query falls
                # through to the Parquet files below
                log.warning("Cloud SQL weekly trades query failed: %s", e)

        # Parquet fallback
        if week_end_date is None:
            week_end_date = datetime.now().date()

        frames = []
        for i in range(7):
            date = week_end_date - pd.Timedelta(days=i)
            df = self._load_parquet_for_date(date)
            if not df.empty:
                frames.append(df)

        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def get_all_trades(self, run_kind='live') -> pd.DataFrame:
        """Load all logged trades (Cloud SQL preferred, then all local Parquet files)."""
        if _cloud_sql_active():
            try:
                from gcp.database import query_to_dataframe
                params: dict = {}
                clause = self._run_kind_clause(run_kind, params)
                df = query_to_dataframe(
                    "SELECT * FROM trades"
                    + (" WHERE" + clause[len(" AND"):] if clause else "")
                    + " ORDER BY entry_time",
                    params or None,
                )
                if not df.empty:
                    return df
            except Exception as e:
                # AUDIT-2026-05-13: silent fallback — a failed query falls
                # through to the Parquet files below
                log.warning("Cloud SQL all-trades query failed: %s", e)

        # Parquet fallback
        files = sorted(self.output_dir.glob('*.parquet'))
        if not files:
            return pd.DataFrame()
        frames = [pd.read_parquet(f) for f in files]
        return pd.concat(frames, ignore_index=True)

    def _load_parquet_for_date(self, date) -> pd.DataFrame:
        path = self._daily_file(date)
        return pd.read_parquet(path) if path.exists() else pd.DataFrame()
