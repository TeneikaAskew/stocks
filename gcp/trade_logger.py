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


def _outage_or_raise(exc: BaseException, what: str) -> None:
    """Let an OUTAGE fall through to the Parquet backup; re-raise a defect.

    The Parquet files are a backup for a database we cannot reach, not a
    second opinion on a query we got wrong. A permanent defect — an undefined
    column after schema drift, a malformed SELECT — reaching the same handler
    is answered from local files, so `gcp/weekend_review.py` publishes a
    plausible Discord summary from stale data while the regression stays
    invisible. CLAUDE.md 3.7.1: a cross-source fallback is a silent fallback
    unless the caller can and does distinguish it, and a defect must never
    trigger one (Codex on #1022, round 24).

    These handlers only became reachable on 0dc6154c, which pointed the three
    readers at the strict query; before that the swallowing helper returned an
    empty frame and the `except` never ran.
    """
    from lib.infra_errors import is_infrastructure_error  # noqa: PLC0415

    if not is_infrastructure_error(exc):
        raise exc
    log.warning("Cloud SQL %s failed, falling back to Parquet: %s", what, exc)


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
        # Provenance is part of the write contract, not only of the one
        # caller: the readers filter on trades.run_kind, and the Parquet
        # fallback reads a null as 'live' only because the rows without it
        # predate the stamp (internal review of #1022).
        if not trade_data.get('run_kind'):
            raise ValueError("trade_data needs run_kind ('live' | 'replay' | 'backfill')")
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
                # The write half of the reader rule above. A broken INSERT --
                # a dropped column, a bad type -- was a warning and nothing
                # else, so every trade fell out of the system of record
                # silently, surviving only in Parquet where the readers now
                # (correctly) do not look unless the database is unreachable.
                #
                # Raising is safe and is what makes it visible: the one
                # caller, gcp/signal_monitor.py:1790, already wraps this in a
                # try/except that increments persist_trade_failure_count --
                # Rule 3.7's "increment a structured counter at the call site
                # instead of swallowing" -- and that counter never saw a write
                # failure, because nothing raised (Codex on #1022, round 24).
                #
                # The Parquet write below still runs for an outage, which is
                # what the backup is for.
                _outage_or_raise(e, "trade write")

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

    @staticmethod
    def _filter_run_kind(df: pd.DataFrame, run_kind) -> pd.DataFrame:
        """Apply the same run_kind restriction to a Parquet fallback frame.

        The only writer of these files is the live monitor's fire_alert,
        which stamps run_kind on every row it logs; rows written before that
        stamp existed (files with no column, or the leading rows of a file
        that was later appended to) carry a null. The rule is ROW-level and
        null reads as 'live', because every such row came from that one
        writer (internal review of #1022 round 14: a column-presence test
        dropped the pre-stamp rows of a mixed file). An empty result keeps
        the frame's columns.

        This is a closed-world assumption: it holds only while log_trade is
        the sole writer of these files and _persist_signal_alert its sole
        caller. tests/gcp/test_trade_logger_reads.py
        (test_the_trade_parquet_files_have_exactly_one_writer) fails the
        moment either gains a second, at which point a null must be read as
        unknown provenance, not as live.
        """
        if run_kind is None or df.empty:
            return df
        kinds = df['run_kind'] if 'run_kind' in df.columns else pd.Series(None, index=df.index, dtype=object)
        return df[kinds.fillna('live') == run_kind].reset_index(drop=True)

    def get_daily_trades(self, date=None, run_kind='live') -> pd.DataFrame:
        """Load trades for a specific date (Cloud SQL preferred, Parquet fallback)."""
        if _cloud_sql_active():
            try:
                from gcp.database import query_to_dataframe_strict
                date_str = str(date or datetime.now().date())
                params = {'d': date_str}
                df = query_to_dataframe_strict(
                    "SELECT * FROM trades WHERE trade_date = :d"
                    + self._run_kind_clause(run_kind, params)
                    + " ORDER BY entry_time",
                    params,
                )
                # Cloud SQL is the system of record: its answer, empty or
                # not, is the answer. Only a FAILED query reaches the files
                # (CLAUDE.md 3.7.1; internal review of #1022). That claim
                # was false while this read went through the SWALLOWING
                # query_to_dataframe, which returns an empty frame on a
                # connection failure: the except below and the Parquet
                # fallback under it were both dead code, and an outage
                # answered "no trades" while the backup held live rows
                # (Codex on #1022). The strict helper is what makes the
                # sentence true.
                return df
            except Exception as e:
                # Only an outage reaches the Parquet files; a defect raises.
                _outage_or_raise(e, "daily trades query")

        # Parquet fallback
        path = self._daily_file(date)
        if path.exists():
            return self._filter_run_kind(pd.read_parquet(path), run_kind)
        return pd.DataFrame()

    def get_weekly_trades(self, week_end_date=None, run_kind='live') -> pd.DataFrame:
        """Load all trades from the past 7 days (Cloud SQL preferred)."""
        if _cloud_sql_active():
            try:
                from gcp.database import query_to_dataframe_strict
                if week_end_date is None:
                    week_end_date = datetime.now().date()
                start = week_end_date - pd.Timedelta(days=6)
                params = {'start': str(start), 'end': str(week_end_date)}
                df = query_to_dataframe_strict(
                    "SELECT * FROM trades WHERE trade_date BETWEEN :start AND :end"
                    + self._run_kind_clause(run_kind, params)
                    + " ORDER BY entry_time",
                    params,
                )
                return df
            except Exception as e:
                # Only an outage reaches the Parquet files; a defect raises.
                _outage_or_raise(e, "weekly trades query")

        # Parquet fallback
        if week_end_date is None:
            week_end_date = datetime.now().date()

        frames = []
        for i in range(7):
            date = week_end_date - pd.Timedelta(days=i)
            df = self._filter_run_kind(self._load_parquet_for_date(date), run_kind)
            if not df.empty:
                frames.append(df)

        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def get_all_trades(self, run_kind='live') -> pd.DataFrame:
        """Load all logged trades (Cloud SQL preferred, then all local Parquet files)."""
        if _cloud_sql_active():
            try:
                from gcp.database import query_to_dataframe_strict
                params: dict = {}
                clause = self._run_kind_clause(run_kind, params)
                df = query_to_dataframe_strict(
                    "SELECT * FROM trades"
                    + (" WHERE" + clause[len(" AND"):] if clause else "")
                    + " ORDER BY entry_time",
                    params or None,
                )
                return df
            except Exception as e:
                # Only an outage reaches the Parquet files; a defect raises.
                _outage_or_raise(e, "all trades query")

        # Parquet fallback
        files = sorted(self.output_dir.glob('*.parquet'))
        if not files:
            return pd.DataFrame()
        frames = [self._filter_run_kind(pd.read_parquet(f), run_kind) for f in files]
        kept = [f for f in frames if not f.empty]
        # Nothing left: an empty frame that still carries the union of the
        # files' columns, not the first file's.
        return pd.concat(kept, ignore_index=True) if kept else pd.concat(frames).iloc[0:0]

    def _load_parquet_for_date(self, date) -> pd.DataFrame:
        path = self._daily_file(date)
        return pd.read_parquet(path) if path.exists() else pd.DataFrame()
