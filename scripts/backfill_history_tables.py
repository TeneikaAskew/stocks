"""One-shot backfill: populate the new history tables from existing data.

Reads every row from `premarket_analysis` and `insight_reports`, copies
them into `premarket_analysis_history` and `insight_reports_history` with
`run_kind='backfill'` and `written_at` set to the row's original write
time (`analysis_ts` for the brief, `created_at` for the pipeline). This
preserves audit truth — even when the original write time is unusual
(e.g. IWM's 4/29 row was written on 4/28 at 21:56 EDT).

Idempotent — uses `ON CONFLICT DO NOTHING` on the unique constraint
`(analysis_date, ticker, written_at)` for the brief and
`(ticker, as_of, written_at)` for the pipeline. Re-running is a no-op.

Usage:
    python -m scripts.backfill_history_tables --dry-run
    python -m scripts.backfill_history_tables

The script reads DB credentials the same way the rest of the codebase
does (CLOUD_SQL_URL > DB_HOST/DB_USER/DB_PASS env vars > gcloud secrets
fallback for local-laptop runs without env vars set).

Phase 1 of docs/plans/MORNING_RUN_PROTECTION_PLAN.md.
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s - %(message)s',
)
logger = logging.getLogger('backfill-history')


_GCLOUD = r'C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
_PROJECT = 'adept-mountain-474619-d4'
_DB_HOST = '34.24.66.12'
_DB_NAME = 'trading'


def _gcloud_secret(name: str) -> str:
    return subprocess.check_output(
        [_GCLOUD, 'secrets', 'versions', 'access', 'latest',
         f'--secret={name}', f'--project={_PROJECT}'],
        text=True, timeout=15,
    ).rstrip('\n')


def _connect():
    """psycopg2 connection. Prefers env vars; falls back to gcloud secrets."""
    import psycopg2
    if os.environ.get('CLOUD_SQL_URL'):
        return psycopg2.connect(os.environ['CLOUD_SQL_URL'], connect_timeout=10)
    if os.environ.get('DB_HOST') and os.environ.get('DB_USER'):
        return psycopg2.connect(
            host=os.environ['DB_HOST'],
            port=int(os.environ.get('DB_PORT', '5432')),
            dbname=os.environ.get('DB_NAME', 'trading'),
            user=os.environ['DB_USER'],
            password=os.environ.get('DB_PASS',
                                    os.environ.get('DB_PASSWORD', '')),
            sslmode=os.environ.get('DB_SSLMODE', 'prefer'),
            connect_timeout=10,
        )
    return psycopg2.connect(
        host=_DB_HOST,
        user=_gcloud_secret('db-trading-user'),
        password=_gcloud_secret('db-trading-pass'),
        dbname=_DB_NAME, sslmode='require', connect_timeout=10,
    )


# Column list for premarket_analysis_history that mirrors premarket_analysis.
# Keep this synced with the schema.sql definition. Audit columns
# (written_at, run_kind, triggered_by, notes) are appended in the SQL.
_PMAH_MIRROR_COLS = [
    'analysis_date', 'ticker', 'price', 'rsi', 'rsi_direction',
    'consecutive_up', 'consecutive_down', 'signal_status',
    'strat_candle', 'strat_combo', 'strat_setup', 'ftfc_score',
    'ftfc_direction', 'ftfc_labels', 'prev_day_high', 'prev_day_low',
    'change_pct', 'rvol', 'sma200', 'bb_upper', 'bb_lower',
    'ema9', 'ema20', 'atr14', 'volatility_20d', 'macd_cross',
    'vol_regime', 'above_sma200', 'stoch_rsi_k', 'stoch_rsi_d',
    'recommended_orb_window', 'recommended_orb_reason', 'playbook',
]


def backfill_premarket_analysis(conn, dry_run: bool = False) -> tuple[int, int]:
    """Copy every premarket_analysis row into premarket_analysis_history.

    Returns (source_count, inserted_count). When dry_run=True, no rows
    are written but counts are still returned so the operator can
    preview the work.
    """
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM premarket_analysis")
    source_count = cur.fetchone()[0]
    logger.info("premarket_analysis: %d source rows", source_count)

    if dry_run:
        cur.execute("SELECT COUNT(*) FROM premarket_analysis_history "
                    "WHERE run_kind = 'backfill'")
        existing_backfill = cur.fetchone()[0]
        cur.close()
        logger.info("dry-run: would attempt %d inserts; %d already backfilled",
                    source_count, existing_backfill)
        return source_count, 0

    # Single SQL: INSERT...SELECT with ON CONFLICT DO NOTHING. Idempotent.
    # written_at is sourced from the original analysis_ts so the audit
    # captures when the row was actually written, not when backfill ran.
    mirror_cols_sql = ', '.join(_PMAH_MIRROR_COLS)
    cur.execute(
        f"""
        INSERT INTO premarket_analysis_history
            ({mirror_cols_sql}, written_at, run_kind, triggered_by, notes)
        SELECT
            {mirror_cols_sql}, analysis_ts, 'backfill', 'backfill-script',
            'Backfilled from premarket_analysis on Phase 1 rollout'
        FROM premarket_analysis
        ON CONFLICT (analysis_date, ticker, written_at) DO NOTHING
        """
    )
    inserted = cur.rowcount
    conn.commit()
    cur.close()
    logger.info("premarket_analysis_history: inserted %d rows "
                "(%d source rows, %d skipped as already-backfilled)",
                inserted, source_count, source_count - inserted)
    return source_count, inserted


def backfill_insight_reports(conn, dry_run: bool = False) -> tuple[int, int]:
    """Copy every insight_reports row into insight_reports_history.

    Associates each backfilled row with the most recent insight_runs row
    that produced its current content (by `report_id` FK). Multiple
    insight_runs rows can point to the same insight_reports.id (one per
    UPSERT attempt) — backfill picks the LATEST one because that's the
    one whose work matches the current report payload.

    Returns (source_count, inserted_count).
    """
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM insight_reports")
    source_count = cur.fetchone()[0]
    logger.info("insight_reports: %d source rows", source_count)

    if dry_run:
        cur.execute("SELECT COUNT(*) FROM insight_reports_history "
                    "WHERE run_kind = 'backfill'")
        existing_backfill = cur.fetchone()[0]
        cur.close()
        logger.info("dry-run: would attempt %d inserts; %d already backfilled",
                    source_count, existing_backfill)
        return source_count, 0

    cur.execute(
        """
        INSERT INTO insight_reports_history
            (insight_run_id, ticker, as_of, report, model_versions,
             cost_usd, latency_ms, written_at, run_kind, triggered_by, notes)
        SELECT
            (SELECT iruns.id
             FROM insight_runs iruns
             WHERE iruns.report_id = ir.id
             ORDER BY iruns.finished_at DESC NULLS LAST,
                      iruns.started_at DESC NULLS LAST
             LIMIT 1)            AS insight_run_id,
            ir.ticker,
            ir.as_of,
            ir.report,
            ir.model_versions,
            ir.cost_usd,
            ir.latency_ms,
            ir.created_at        AS written_at,
            'backfill'           AS run_kind,
            'backfill-script'    AS triggered_by,
            'Backfilled from insight_reports on Phase 1 rollout' AS notes
        FROM insight_reports ir
        ON CONFLICT (ticker, as_of, written_at) DO NOTHING
        """
    )
    inserted = cur.rowcount
    conn.commit()
    cur.close()
    logger.info("insight_reports_history: inserted %d rows "
                "(%d source rows, %d skipped as already-backfilled)",
                inserted, source_count, source_count - inserted)
    return source_count, inserted


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true',
                        help='Count source + already-backfilled rows; '
                             'do not insert.')
    parser.add_argument('--brief-only', action='store_true',
                        help='Only backfill premarket_analysis_history.')
    parser.add_argument('--insight-only', action='store_true',
                        help='Only backfill insight_reports_history.')
    args = parser.parse_args()

    conn = _connect()
    try:
        if not args.insight_only:
            backfill_premarket_analysis(conn, dry_run=args.dry_run)
        if not args.brief_only:
            backfill_insight_reports(conn, dry_run=args.dry_run)
    finally:
        conn.close()
    logger.info("done")


if __name__ == '__main__':
    main()
