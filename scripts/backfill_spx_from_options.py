#!/usr/bin/env python3
"""
Backfill SPX daily OHLC into market_data_daily using put-call parity on the
existing SPX options snapshots in etf_options_snapshots.

Background:
    AlphaVantage does NOT provide TIME_SERIES_DAILY_ADJUSTED for the SPX index
    (none of the variants SPX, ^SPX, ^GSPC, SPX.X work). Because the existing
    fetch_market_data.py also fails on TIME_SERIES_INTRADAY for SPX, and its
    build_daily_row() function requires a non-empty minute_df, SPX has never
    been written to market_data_daily since the Yahoo Finance cutover.

    But we DO have 11.8M SPX option rows in etf_options_snapshots (from the
    daily HISTORICAL_OPTIONS backfill job), and put-call parity lets us
    derive the underlying price exactly:

        spot = strike + call_mark - put_mark   (call and put at same K, same expiration)

    This is a well-known European option identity. SPX is European-style
    (settles in cash on expiration), so put-call parity holds tightly —
    verified to ~5 cents across 5 ATM strikes on 2026-04-13.

Usage:
    python scripts/backfill_spx_from_options.py               # Backfill missing dates
    python scripts/backfill_spx_from_options.py --dry-run     # Print what would be written
    python scripts/backfill_spx_from_options.py --since 2025-12-18 --until 2026-04-13

We can't get true intraday OHLC from a single daily EOD snapshot (we only
have one underlying price per day). So the derived row has:
    open   = close = high = low = <parity-derived spot>
    volume = 0 (SPX index has no volume; volume belongs to ETFs)
    data_source = 'derived_put_call_parity'

Indicators (RSI, EMA, SMA, etc.) are left for the existing
`compute_and_upsert_daily_indicators()` helper in
`gcp.fetchers.fetch_market_data` to compute on the next daily run.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gcp.database import is_cloud_sql_configured, query_to_dataframe, execute_sql  # noqa: E402

log = logging.getLogger(__name__)


_PARITY_SQL = """
    WITH nearest_expiry AS (
      SELECT MIN(expiration) AS exp
      FROM etf_options_snapshots
      WHERE ticker = 'SPX'
        AND data_source = 'alphavantage'
        AND snapshot_date = :dt
        AND expiration > :dt
    ),
    calls AS (
      SELECT strike, mark AS call_mark
      FROM etf_options_snapshots
      WHERE ticker = 'SPX'
        AND data_source = 'alphavantage'
        AND snapshot_date = :dt
        AND option_type = 'calls'
        AND expiration = (SELECT exp FROM nearest_expiry)
        AND mark IS NOT NULL
    ),
    puts AS (
      SELECT strike, mark AS put_mark
      FROM etf_options_snapshots
      WHERE ticker = 'SPX'
        AND data_source = 'alphavantage'
        AND snapshot_date = :dt
        AND option_type = 'puts'
        AND expiration = (SELECT exp FROM nearest_expiry)
        AND mark IS NOT NULL
    )
    SELECT c.strike + c.call_mark - p.put_mark AS pcp_spot
    FROM calls c
    JOIN puts p USING (strike)
    ORDER BY ABS(c.call_mark - p.put_mark)
    LIMIT 5
"""


def derive_spx_spot_for_date(snapshot_date: str) -> Optional[float]:
    """Compute SPX spot for a given date using put-call parity on ATM SPX options.

    Returns the median parity spot across the top-5 closest strikes, or None
    if no viable option pairs exist.

    Reused by `gcp.fetchers.fetch_market_data.process_ticker` to keep SPX fresh
    in `market_data_daily` going forward — AV has no TIME_SERIES for SPX.
    """
    df = query_to_dataframe(_PARITY_SQL, {"dt": snapshot_date})
    if df.empty:
        return None
    spots = df["pcp_spot"].astype(float).dropna().tolist()
    if not spots:
        return None
    spots.sort()
    return float(spots[len(spots) // 2])


def list_missing_spx_dates(since: date, until: date) -> list[date]:
    """Return the dates in [since, until] where market_data_daily has SPX option
    data but no SPX market_data_daily row yet.
    """
    df = query_to_dataframe(
        """
        SELECT DISTINCT snapshot_date
        FROM etf_options_snapshots
        WHERE ticker = 'SPX'
          AND data_source = 'alphavantage'
          AND snapshot_date BETWEEN :since AND :until
          AND NOT EXISTS (
            SELECT 1 FROM market_data_daily md
            WHERE md.ticker = 'SPX' AND md.date = etf_options_snapshots.snapshot_date
          )
        ORDER BY snapshot_date
        """,
        {"since": since, "until": until},
    )
    return [row["snapshot_date"] for _, row in df.iterrows()]


def upsert_spx_daily(snapshot_date: date, spot: float) -> None:
    """Insert a derived SPX row into market_data_daily via upsert."""
    execute_sql(
        """
        INSERT INTO market_data_daily (ticker, date, open, high, low, close, adjusted_close, volume, data_source)
        VALUES ('SPX', :dt, :spot, :spot, :spot, :spot, :spot, 0, 'derived_put_call_parity')
        ON CONFLICT (ticker, date) DO UPDATE
          SET open           = EXCLUDED.open,
              high           = EXCLUDED.high,
              low            = EXCLUDED.low,
              close          = EXCLUDED.close,
              adjusted_close = EXCLUDED.adjusted_close,
              volume         = EXCLUDED.volume,
              data_source    = EXCLUDED.data_source
        """,
        {"dt": snapshot_date, "spot": spot},
    )


def main():
    parser = argparse.ArgumentParser(description="Backfill SPX daily via put-call parity")
    parser.add_argument("--since", default=None, help="Start date YYYY-MM-DD (default: day after latest SPX row)")
    parser.add_argument("--until", default=None, help="End date YYYY-MM-DD (default: latest SPX options snapshot)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written without upserting")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")

    if not is_cloud_sql_configured():
        log.error("Cloud SQL not configured")
        sys.exit(2)

    # Resolve date range
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d").date()
    else:
        df = query_to_dataframe("SELECT MAX(date) AS d FROM market_data_daily WHERE ticker='SPX'")
        last_spx = df.iloc[0]["d"]
        since = (last_spx + timedelta(days=1)) if last_spx else date(2025, 12, 18)

    if args.until:
        until = datetime.strptime(args.until, "%Y-%m-%d").date()
    else:
        df = query_to_dataframe(
            "SELECT MAX(snapshot_date) AS d FROM etf_options_snapshots WHERE ticker='SPX' AND data_source='alphavantage'"
        )
        until = df.iloc[0]["d"]

    log.info("Backfilling SPX market_data_daily from %s to %s (dry_run=%s)", since, until, args.dry_run)
    missing = list_missing_spx_dates(since, until)
    log.info("%d missing dates", len(missing))

    written = 0
    failed = 0
    for dt in missing:
        spot = derive_spx_spot_for_date(dt.isoformat())
        if spot is None:
            log.warning("  %s: no viable put-call parity pair (skipping)", dt)
            failed += 1
            continue
        if args.dry_run:
            log.info("  %s: would write spot=%.2f", dt, spot)
        else:
            try:
                upsert_spx_daily(dt, spot)
                log.info("  %s: wrote spot=%.2f", dt, spot)
                written += 1
            except Exception as e:
                log.error("  %s: upsert failed — %s", dt, e)
                failed += 1

    log.info("Done. wrote=%d  failed=%d  skipped=%d", written, failed, len(missing) - written - failed)


if __name__ == "__main__":
    main()
