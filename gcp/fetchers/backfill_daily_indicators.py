"""
Self-healing backfill of derived indicator columns in market_data_daily.

Why this exists:
    The 2026-05-13 coverage audit showed ~98% of historical
    market_data_daily rows have raw open/high/low/close/volume but
    NULL for every derived column (atr_14, rsi_14, macd_*, ema_*,
    ma_*, bb_*, obv, rvol, stoch_*, consecutive_*, volatility_20d,
    price_vs_ema*, strat_candle/combo). Cause: the live writer in
    `fetch_market_data.compute_and_upsert_daily_indicators` only
    persisted `enriched.iloc[-1]` — the prior 249 bars in each
    250-bar compute frame were silently discarded.

Two modes, one scheduled job — no manual one-offs needed:

    --mode=daily   (default; runs nightly)
        Auto-discover tickers where ANY derived indicator column
        (atr_14, rsi_14, macd, ema_*, bb_*, obv, rvol, stoch_*,
        consecutive_*, volatility_20d, price_vs_ema*, strat_candle,
        strat_combo — every column the compute path persists) is
        NULL in the last ``--lookback-days`` (default 7). Re-compute
        their full history and upsert. Cheap when healthy.

    --mode=full
        Process every ticker in market_data_daily regardless of
        per-row coverage. Used by the weekly catch-up scheduler
        entry and on-demand recoveries. Re-computes every indicator
        for every bar — does NOT skip on per-column nulls because
        the full-mode contract is "trust nothing, recompute".

Both modes are idempotent: the per-ticker compute is a deterministic
function of the underlying OHLCV, and the upsert merges on
(ticker, date) so re-runs converge rather than duplicate. Safe to
schedule, safe to retry.

Capacity (CLAUDE.md Rule 0.2):
    Volume   : ~650k market_data_daily rows × ~28 indicator columns
    Velocity : 1 SELECT + 1 batched UPSERT per ticker
    Wall-clock per ticker: ~1-3s (select + compute + upsert)
    full mode  : ~1,200 tickers × 2s ≈ 40 min
    daily mode : ~50 affected tickers × 2s ≈ 2 min on a healthy table
    Cloud Run Job task-timeout: 3h (headroom for full mode).

Usage:
    # Scheduled nightly self-heal (default mode)
    python -m gcp.fetchers.backfill_daily_indicators

    # Weekly full sweep
    python -m gcp.fetchers.backfill_daily_indicators --mode=full

    # On-demand subset (smoke / recovery)
    python -m gcp.fetchers.backfill_daily_indicators \\
        --mode=full --tickers SPY,QQQ,IWM
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import Optional

import numpy as np
import pandas as pd

from gcp.database import (
    DAILY_INDICATOR_TO_SQL_COLUMN,
    is_cloud_sql_configured,
    query_to_dataframe,
    upsert_dataframe,
)

log = logging.getLogger(__name__)

# Columns the upsert should treat as INT (consecutive run counters).
_INT_COLS = {'consecutive_up', 'consecutive_down'}


def _all_tickers() -> list[str]:
    """Every distinct ticker with at least one row in market_data_daily."""
    sql = "SELECT DISTINCT ticker FROM market_data_daily ORDER BY ticker"
    df = query_to_dataframe(sql, {})
    if df is None or df.empty:
        return []
    return [str(t).upper() for t in df['ticker'].tolist()]


# Every SQL column produced by the indicator-compute path. Source of
# truth lives in gcp/database.DAILY_INDICATOR_TO_SQL_COLUMN; the strat
# columns (strat_candle / strat_combo) are populated by the same
# compute path and are included here so they participate in gap
# detection. NB: ftfc_score / strat_setup are intentionally excluded
# because they're populated by the live writer's per-day pass, not by
# the historical-history recompute — checking them here would force a
# re-compute on every healthy bar.
_DERIVED_COLS_FOR_GAP_CHECK: tuple[str, ...] = tuple(
    list(DAILY_INDICATOR_TO_SQL_COLUMN.values())
    + ['strat_candle', 'strat_combo']
)


def _tickers_with_gaps(lookback_days: int) -> list[str]:
    """Tickers that have at least one row in the last ``lookback_days``
    where ANY derived indicator column is NULL.

    Uses Postgres ``num_nulls()`` over every column the compute path
    persists (atr_14, rsi_14, macd_*, ema_*, ma_*, bb_*, obv, rvol,
    stoch_*, consecutive_*, volatility_20d, price_vs_ema*, plus the
    two strat string columns). A single NULL anywhere in that list
    flags the (ticker, date) row as in need of a re-compute — the
    daily mode then queues that ticker for a full-history pass.

    This replaces the prior single-column canary (atr_14) so a
    partial-write that left e.g. macd populated but rsi_14 NULL
    isn't silently ignored.
    """
    cols_sql = ", ".join(_DERIVED_COLS_FOR_GAP_CHECK)
    sql = f"""
        SELECT DISTINCT ticker
        FROM market_data_daily
        WHERE date >= CURRENT_DATE - (:d || ' days')::interval
          AND num_nulls({cols_sql}) > 0
        ORDER BY ticker
    """
    df = query_to_dataframe(sql, {'d': lookback_days})
    if df is None or df.empty:
        return []
    return [str(t).upper() for t in df['ticker'].tolist()]


def _full_history(ticker: str) -> pd.DataFrame:
    """All daily OHLCV for one ticker, oldest first."""
    sql = """
        SELECT date,
               open  AS "Open",
               high  AS "High",
               low   AS "Low",
               close AS "Close",
               volume AS "Volume"
        FROM market_data_daily
        WHERE ticker = :ticker
        ORDER BY date ASC
    """
    df = query_to_dataframe(sql, {'ticker': ticker.upper()})
    if df is None or df.empty:
        return pd.DataFrame()
    df['date'] = pd.to_datetime(df['date']).dt.date
    return df


def _build_indicator_rows(ticker: str, df: pd.DataFrame) -> list[dict]:
    """Run add_all_indicators + strat over the full history, return one
    upsert dict per bar whose row carries at least one non-NULL indicator.
    """
    if df.empty or len(df) < 2:
        return []

    from lib.indicators import add_all_indicators

    enriched = add_all_indicators(df, close_col='Close')
    # 20-day annualised historical volatility — same recipe the live
    # writer uses (not part of add_all_indicators).
    enriched['volatility_20d'] = (
        enriched['Close'].pct_change().rolling(20).std() * np.sqrt(252)
    )

    # Strat per-bar classifier output. ftfc is daily+weekly; we compute
    # it row-by-row only at the very end of the backfill since the
    # rolling-windowed ftfc result for a historical bar would itself
    # need a contemporaneous weekly resample. Keep historical ftfc
    # NULL and let the live writer fill in fresh values going forward
    # — the per-day strat_candle / strat_combo CAN be backfilled
    # deterministically since they're a function of OHLC at that bar.
    try:
        from lib.strat import StratClassifier
        clf = StratClassifier()
        labels = clf.classify_series(
            enriched[['Open', 'High', 'Low', 'Close']]
        )
        combos = clf.detect_combos(
            enriched[['Open', 'High', 'Low', 'Close']], labels
        )
        enriched['strat_candle'] = labels.astype(str).replace({'X': None})
        # combos returns a sparse frame indexed where a combo fired;
        # join back to enriched on the index so non-combo bars stay NaN.
        if not combos.empty and 'combo' in combos.columns:
            enriched['strat_combo'] = combos['combo']
        else:
            enriched['strat_combo'] = None
    except Exception as e:
        log.warning("strat backfill failed for %s: %s — skipping strat cols", ticker, e)
        enriched['strat_candle'] = None
        enriched['strat_combo'] = None

    rows: list[dict] = []
    dates = df['date'].tolist()
    for i in range(len(enriched)):
        bar = enriched.iloc[i]
        row: dict = {'ticker': ticker.upper(), 'date': dates[i]}
        for src, dst in DAILY_INDICATOR_TO_SQL_COLUMN.items():
            val = bar.get(src)
            if val is not None and pd.notna(val):
                row[dst] = int(val) if dst in _INT_COLS else float(val)
        # Strat (string columns; only write when non-null/non-X)
        strat_candle = bar.get('strat_candle')
        if strat_candle and pd.notna(strat_candle) and str(strat_candle) != 'X':
            row['strat_candle'] = str(strat_candle)
        strat_combo = bar.get('strat_combo')
        if strat_combo and pd.notna(strat_combo):
            row['strat_combo'] = str(strat_combo)[:30]
        if len(row) > 2:
            rows.append(row)
    return rows


def backfill_ticker(ticker: str) -> int:
    """Backfill all derived columns for one ticker. Returns row count."""
    t0 = time.time()
    df = _full_history(ticker)
    if df.empty:
        log.warning("  %s: no rows in market_data_daily — skipping", ticker)
        return 0
    rows = _build_indicator_rows(ticker, df)
    if not rows:
        log.warning("  %s: no indicator rows produced (only %d bars)", ticker, len(df))
        return 0
    upsert_dataframe(
        pd.DataFrame(rows), 'market_data_daily', ['ticker', 'date'],
    )
    dt = time.time() - t0
    log.info("  ✓ %s: %d rows upserted in %.1fs", ticker, len(rows), dt)
    return len(rows)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Self-healing backfill of derived indicators in "
                    "market_data_daily."
    )
    parser.add_argument(
        "--mode",
        choices=("daily", "full"),
        default=os.environ.get("BACKFILL_MODE", "daily"),
        help=(
            "daily (default): only re-compute tickers with NULL atr_14 "
            "in the last --lookback-days. full: re-compute every ticker "
            "in the table. Both modes are idempotent — re-running "
            "converges to the same state."
        ),
    )
    parser.add_argument(
        "--lookback-days", type=int,
        default=int(os.environ.get("BACKFILL_LOOKBACK_DAYS", "7")),
        help="In --mode=daily, window over which atr_14 NULL triggers "
             "a ticker re-compute (default 7).",
    )
    parser.add_argument(
        "--tickers",
        type=str,
        default=os.environ.get("BACKFILL_TICKERS", ""),
        help="Comma-separated subset — overrides --mode resolution. "
             "Used by smoke tests and targeted recoveries.",
    )
    parser.add_argument(
        "--max-tickers", type=int,
        default=int(os.environ.get("MAX_TICKERS", "0")),
        help="Cap on tickers per run (0 = no cap).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Compute but don't upsert. Logs row counts per ticker.",
    )
    args = parser.parse_args()

    if not is_cloud_sql_configured():
        log.error("Cloud SQL not configured — refusing to run")
        return 2

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        log.info("Ticker source: --tickers override (%d)", len(tickers))
    elif args.mode == "full":
        tickers = _all_tickers()
        log.info("Ticker source: mode=full (%d tickers in market_data_daily)",
                 len(tickers))
    else:  # mode == "daily"
        tickers = _tickers_with_gaps(args.lookback_days)
        log.info(
            "Ticker source: mode=daily — %d tickers with NULL atr_14 "
            "in last %dd",
            len(tickers), args.lookback_days,
        )

    if args.max_tickers and len(tickers) > args.max_tickers:
        log.warning("Truncating ticker count %d → %d (--max-tickers)",
                    len(tickers), args.max_tickers)
        tickers = tickers[: args.max_tickers]

    if not tickers:
        log.info("No tickers to process — exiting cleanly (0 gaps detected).")
        return 0

    log.info("Backfill Daily Indicators")
    log.info("  Mode    : %s", args.mode)
    log.info("  Tickers : %d", len(tickers))
    log.info("  Dry-run : %s", args.dry_run)

    total_rows = 0
    errors: list[str] = []
    for i, tk in enumerate(tickers, 1):
        try:
            if args.dry_run:
                df = _full_history(tk)
                rows = _build_indicator_rows(tk, df)
                log.info("  [%d/%d] %s: would upsert %d rows", i, len(tickers), tk, len(rows))
            else:
                n = backfill_ticker(tk)
                total_rows += n
                if i % 50 == 0:
                    log.info("  progress: %d/%d tickers · %d rows so far",
                             i, len(tickers), total_rows)
        except Exception as e:
            log.exception("  ✗ %s: %s", tk, e)
            errors.append(tk)

    log.info("Done. tickers=%d rows_upserted=%d errors=%d",
             len(tickers), total_rows, len(errors))
    if errors:
        log.warning("Errors on: %s", ", ".join(errors[:20]))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
