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
        Auto-discover tickers with a *healable* gap — any derived
        indicator column (atr_14, rsi_14, macd, ema_*, bb_*, obv,
        rvol, stoch_*, consecutive_*, volatility_20d, price_vs_ema*,
        strat_candle, strat_combo — every column the compute path
        persists) NULL in the last ``--lookback-days`` (default 7) on
        a completed trading day with full raw OHLCV, gated by the
        ticker's warmup (see "Gap-detection convergence" below).
        Re-compute over the full history but write back only the
        recent window (lookback + 5d). Cheap when healthy.

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

Gap-detection convergence (issue #751, 2026-08):
    The original gap check flagged any recent row with ANY null derived
    column. Three structural null classes made that non-convergent, so
    the same tickers were re-processed every night forever:
      1. Warmup nulls — sma_200 needs 200 bars, ema_50/ma_50 need 50;
         a ticker listed 6 months ago can NEVER fill sma_200, so every
         fresh bar re-flagged it (≈50 young tickers/day, permanently).
      2. Uncomputable rows — bars with NULL raw OHLCV are dropped by the
         compute path, so their derived nulls can never be healed;
         same-day partial rows (written intraday by the top-movers
         snapshots) haven't been through the nightly enrich yet.
      3. Formula-domain nulls — quotient indicators (bb_pct, bb_squeeze,
         rvol, stoch_rsi, the RSI family, ATR-normalized features) are
         legitimately NaN when their denominator is zero on flat-price /
         zero-volume stretches; recompute reproduces the same NaN.
    The check now joins per-ticker USABLE-bar counts (complete raw
    OHLCV only) and only counts a null as a *healable gap* when the
    ticker has enough history for that column class, the column is a
    total function of valid input (_FORMULA_DOMAIN_COLS are exempt),
    the row's raw OHLCV is complete, and the row is a completed
    trading day (date < CURRENT_DATE).

Capacity (CLAUDE.md Rule 0.2 — re-measured 2026-08-24, issue #751):
    Volume   : ~2,580 tickers × ~2,500 bars ≈ 6.5M market_data_daily rows,
               ~40 indicator columns
    Velocity : 1 SELECT + 1 batched UPSERT per ticker (+1 gap query/run)
    Wall-clock per ticker (measured from the 2026-08-22 production run):
      old: ~5.5s  (full-history SELECT + compute + FULL-history upsert
                   ~2,500 rows + per-call schema reflection)
      new: ~2.2s daily (full SELECT + compute + recent-window upsert of
                   ~10 rows; reflection cached), ~5s full mode
    Worst case (every ticker flagged — happens whenever an upstream bulk
    writer lands a day of raw bars without enrichment):
      daily mode : 2,580 × ~2.2s / 4 workers (I/O overlap ≈ 1.5×–3×)
                   ≈ 35–95 min   (was: 3.9h > 3h timeout → daily death)
      full mode  : 2,580 × ~5s   / workers ≈ 1.5–2.5h
    Healthy day  : ≲100 tickers ≈ 2–4 min
    Cloud Run Job task-timeout: 36000s (10h) ≈ 4× the full-mode estimate
    (Rule 0.5 — Cloud Run charges runtime, not the cap).

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

import pandas as pd

from gcp.database import (
    DAILY_INDICATOR_TO_SQL_COLUMN,
    is_cloud_sql_configured,
    query_to_dataframe,
    record_job_run,
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


# Every SQL column produced by the indicator-compute path whose NULL
# values mean "this bar wasn't computed" — i.e. checking them for NULL
# is a reliable gap signal. Source of truth lives in
# gcp.database.DAILY_INDICATOR_TO_SQL_COLUMN; strat_candle is added
# because it's deterministic from OHLC (every bar should have it).
#
# Excluded:
#   - strat_combo:  legitimately NULL on ~21% of bars (early bars
#                   without enough lookback, or bars that don't match
#                   any combo's precondition). Including it as a gap
#                   signal would force a re-compute on every ticker
#                   every day. Empirical: 78.8% covered post-backfill
#                   on the 656k-row corpus.
#   - ftfc_score / strat_setup: populated only by the live writer's
#                   per-day pass, not by the historical backfill.
_DERIVED_COLS_FOR_GAP_CHECK: tuple[str, ...] = tuple(
    list(DAILY_INDICATOR_TO_SQL_COLUMN.values())
    + ['strat_candle']
)

# Warmup classes for the convergent gap check (issue #751). A NULL in one
# of these columns is only a *healable* gap when the ticker has at least
# the class's bar count — otherwise the null is structural (the indicator
# formula itself can't produce a value yet) and flagging it re-queues the
# ticker every night forever. Thresholds = pandas min_periods of the
# formula (lib/indicators.py) + margin for the lookback window.
_WARMUP_200_COLS: tuple[str, ...] = ('sma_200',)          # rolling(200)
_WARMUP_50_COLS: tuple[str, ...] = ('ema_50', 'ma_50')     # min_periods=50

# Columns that are PARTIAL functions of valid OHLCV — their formulas
# divide by a data-dependent quantity that is legitimately zero on
# flat-price / zero-volume stretches: bb_pct & bb_squeeze (Bollinger
# bandwidth), rvol (rolling volume), the RSI family incl. stoch_rsi
# and rsi_divergence (zero net movement → 0/0), and the ATR-normalized
# features (ATR = 0 on a flat run). Recompute reproduces the same NaN,
# so a NULL here is NOT a healable gap and must never drive the daily
# flag. Verified live 2026-08-24: after warmup gating, the entire
# non-convergent residue was exactly {bb_pct, rvol, bb_squeeze} on 5
# flat/illiquid tickers. The enrichment-didn't-run failure mode nulls
# EVERY column, so the guaranteed set below still catches it.
_FORMULA_DOMAIN_COLS: tuple[str, ...] = (
    'rsi_9', 'rsi_14', 'rsi_30', 'rsi_divergence',
    'stoch_rsi_k', 'stoch_rsi_d',
    'bb_pct', 'bb_squeeze', 'rvol',
    'price_vs_ema9_atr', 'price_vs_ema20_atr', 'ema_spread_atr',
    'ema9_slope',
)

_WARMUP_SHORT_COLS: tuple[str, ...] = tuple(
    c for c in _DERIVED_COLS_FOR_GAP_CHECK
    if c not in _WARMUP_200_COLS + _WARMUP_50_COLS + _FORMULA_DOMAIN_COLS
)  # total functions of valid OHLCV needing ≤ ~35 bars (macd_signal)
_WARMUP_200_MIN_BARS = 215
_WARMUP_50_MIN_BARS = 65
_WARMUP_SHORT_MIN_BARS = 50


def _tickers_with_gaps(lookback_days: int) -> list[str]:
    """Tickers with at least one *healable* gap in the last
    ``lookback_days``: a NULL derived column on a completed trading day
    whose raw OHLCV is present, in a column the ticker has enough
    history to actually compute.

    Uses Postgres ``num_nulls()`` over every column the compute path
    persists, split into warmup classes (see the module docstring's
    "Gap-detection convergence" section). Excluded — these nulls are
    structural and flagging them makes the nightly self-heal
    re-process the same tickers forever (the 2026-08 issue #751
    timeout loop):

      - rows dated today (partial intraday bars not yet enriched)
      - rows with NULL raw open/high/low/close/volume (the compute
        path drops them — see _build_indicator_rows)
      - warmup nulls on tickers too young for that column's window
    """
    short_sql = ", ".join(_WARMUP_SHORT_COLS)
    w50_sql = ", ".join(_WARMUP_50_COLS)
    w200_sql = ", ".join(_WARMUP_200_COLS)
    sql = f"""
        WITH bar_counts AS (
            -- Only bars the compute path can actually use: rows with
            -- NULL raw OHLCV are dropped by _build_indicator_rows, so
            -- counting them would let a ticker cross a warmup threshold
            -- it can't actually satisfy (non-convergent re-flag).
            -- Bounded to the last 450 calendar days (~310 trading bars,
            -- comfortably above the largest threshold of 215) so the
            -- null-check heap scan stays on an index range instead of
            -- the full ~6.5M-row table — unbounded, this CTE alone
            -- blew a 120s statement timeout. Undercounting a ticker's
            -- history is convergence-safe: it can only suppress a
            -- flag (weekly full mode still heals it), never re-queue.
            SELECT ticker, count(*) AS n_bars
            FROM market_data_daily
            WHERE date >= CURRENT_DATE - INTERVAL '450 days'
              AND num_nulls(open, high, low, close, volume) = 0
            GROUP BY ticker
        )
        SELECT DISTINCT m.ticker
        FROM market_data_daily m
        JOIN bar_counts c ON c.ticker = m.ticker
        WHERE m.date >= CURRENT_DATE - (:d || ' days')::interval
          AND m.date < CURRENT_DATE
          AND num_nulls(m.open, m.high, m.low, m.close, m.volume) = 0
          AND (
                (c.n_bars >= {_WARMUP_SHORT_MIN_BARS}
                    AND num_nulls({short_sql}) > 0)
             OR (c.n_bars >= {_WARMUP_50_MIN_BARS}
                    AND num_nulls({w50_sql}) > 0)
             OR (c.n_bars >= {_WARMUP_200_MIN_BARS}
                    AND num_nulls({w200_sql}) > 0)
          )
        ORDER BY m.ticker
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

    Pre-filter: rows with any None/NaN in OHLCV are dropped before the
    compute step. add_all_indicators does arithmetic on these columns
    that propagates None through to subtractions ('NoneType' - 'NoneType'
    TypeError seen on RIVN / SPX during the initial backfill, 2026-05-13).
    Indices like SPX have no volume in some sources; new tickers like
    RIVN have None for early bars. Skip them rather than crash the
    whole ticker.
    """
    if df.empty or len(df) < 2:
        return []

    # Drop bars with any null OHLCV. The compute path assumes float math
    # (add_all_indicators does subtractions that crash on None operands —
    # seen on RIVN/SPX in the initial backfill). Log every dropped
    # (ticker, date) so operators can see exactly which bars were lost
    # and trace them back to the upstream daily fetcher if needed.
    n_in = len(df)
    null_mask = df[['Open', 'High', 'Low', 'Close', 'Volume']].isna().any(axis=1)
    n_dropped = int(null_mask.sum())
    if n_dropped > 0:
        dropped_dates = df.loc[null_mask, 'date'].tolist()
        # Cap the per-bar log to first 20 to avoid drowning a many-NULL
        # ticker's output; summary line always carries the total count.
        sample = ", ".join(str(d) for d in dropped_dates[:20])
        ellipsis = f" (+{n_dropped - 20} more)" if n_dropped > 20 else ""
        log.warning(
            "  %s: dropping %d/%d bars with NULL OHLCV. dates: %s%s",
            ticker, n_dropped, n_in, sample, ellipsis,
        )
    df = df.loc[~null_mask].reset_index(drop=True)
    if df.empty or len(df) < 2:
        log.warning(
            "  %s: all %d bars had NULL OHLCV — skipping (no rows to compute on)",
            ticker, n_in,
        )
        return []

    from lib.indicators import add_all_indicators

    enriched = add_all_indicators(df, close_col='Close')
    # volatility_{5,20}d, high_low_spread{,_pct}, ATR20, RSI30 all come
    # from add_all_indicators now (single source of truth — see
    # lib/config.py IndicatorConfig.{volatility_periods,atr_extra_periods,
    # rsi_extra_periods}).

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
        # detect_combos() returns a DataFrame ALIGNED to the input index
        # with columns 'strat_candle', 'strat_combo', 'strat_setup',
        # 'trigger_high', 'trigger_low', 'consecutive_1s'. Bars where no
        # combo fired carry strat_combo == 'none' (string), NOT NaN.
        # Pull the column straight off the returned frame.
        if not combos.empty and 'strat_combo' in combos.columns:
            sc = combos['strat_combo']
            # 'none' is the sentinel for "no combo on this bar" — surface
            # it as NULL so the column reflects "combo here" vs "no combo".
            enriched['strat_combo'] = sc.where(sc != 'none', None)
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
        # Strat (string columns; only write when value carries actual
        # information). Filter every sentinel that means "no value here":
        #   - None / NaN (proper nulls)
        #   - 'X' (strat_candle sentinel for unclassifiable bar)
        #   - 'none' (strat_combo sentinel for "no combo fired")
        #   - 'nan' (string-coerced NaN — happens when an object-dtype
        #     pandas Series serialises NaN values to string via str(), seen
        #     in the 2026-05-13 backfill where ~17% of SPY bars landed
        #     as the literal string 'nan' before this guard.)
        _STRAT_NULL_SENTINELS = ('', 'X', 'nan', 'none', 'None', 'NaN')
        strat_candle = bar.get('strat_candle')
        if (strat_candle is not None and pd.notna(strat_candle)
                and str(strat_candle) not in _STRAT_NULL_SENTINELS):
            row['strat_candle'] = str(strat_candle)
        strat_combo = bar.get('strat_combo')
        if (strat_combo is not None and pd.notna(strat_combo)
                and str(strat_combo) not in _STRAT_NULL_SENTINELS):
            row['strat_combo'] = str(strat_combo)[:30]
        if len(row) > 2:
            rows.append(row)
    return rows


def _filter_recent_rows(rows: list[dict],
                        recent_days: Optional[int]) -> list[dict]:
    """Keep only rows dated within the last ``recent_days`` (None = all).

    Shared by the real upsert path and --dry-run so the dry run
    previews exactly the rows the live run would write.
    """
    if recent_days is None or not rows:
        return rows
    from datetime import date as _date, timedelta as _timedelta
    cutoff = _date.today() - _timedelta(days=recent_days)
    return [r for r in rows if r['date'] >= cutoff]


def backfill_ticker(ticker: str, recent_days: Optional[int] = None) -> int:
    """Backfill derived columns for one ticker. Returns row count.

    The compute always runs over the FULL history (cumulative
    indicators like OBV and warmup-sensitive EMAs must be derived from
    inception to stay consistent with previously stored values), but
    when ``recent_days`` is set only rows dated within that window are
    written back. Daily mode uses this: the full-history heal already
    ran (2026-05 backfill), so the nightly self-heal only needs to fix
    the recent window — cutting the upsert from ~2,500 rows/ticker to
    ~10 and the per-ticker wall-clock by more than half (issue #751).
    Full mode passes ``None`` and re-writes the whole history.
    """
    t0 = time.time()
    df = _full_history(ticker)
    if df.empty:
        log.warning("  %s: no rows in market_data_daily — skipping", ticker)
        return 0
    rows = _filter_recent_rows(_build_indicator_rows(ticker, df), recent_days)
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
        "--workers", type=int,
        default=int(os.environ.get("BACKFILL_WORKERS", "4")),
        help="Concurrent ticker workers (threads; default 4). The work "
             "is dominated by pg8000 round-trips, so a small pool "
             "overlaps I/O with compute. Keep <= the SQLAlchemy pool "
             "size (5) so workers never block on connection checkout.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Compute but don't upsert. Logs row counts per ticker.",
    )
    args = parser.parse_args()

    if not is_cloud_sql_configured():
        log.error("Cloud SQL not configured — refusing to run")
        return 2

    from datetime import datetime as _datetime, timezone as _timezone
    run_started = _datetime.now(_timezone.utc)

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
            "Ticker source: mode=daily — %d tickers with healable "
            "derived-column gaps in last %dd",
            len(tickers), args.lookback_days,
        )

    if args.max_tickers and len(tickers) > args.max_tickers:
        log.warning("Truncating ticker count %d → %d (--max-tickers)",
                    len(tickers), args.max_tickers)
        tickers = tickers[: args.max_tickers]

    if not tickers:
        log.info("No tickers to process — exiting cleanly (0 gaps detected).")
        record_job_run('backfill-daily-indicators', run_started, 'success',
                       items_total=0, items_processed=0, items_failed=0,
                       rows_written=0, note=f"mode={args.mode} (no gaps)")
        return 0

    # Daily mode writes back only the recent window (gap window + margin
    # for weekends/holidays); full mode and explicit --tickers recoveries
    # re-write the whole history. See backfill_ticker's docstring.
    recent_days: Optional[int] = None
    if args.mode == "daily" and not args.tickers:
        recent_days = args.lookback_days + 5

    workers = max(1, min(args.workers, len(tickers)))

    log.info("Backfill Daily Indicators")
    log.info("  Mode    : %s", args.mode)
    log.info("  Tickers : %d", len(tickers))
    log.info("  Workers : %d", workers)
    log.info("  Upsert  : %s",
             "full history" if recent_days is None
             else f"last {recent_days}d only")
    log.info("  Dry-run : %s", args.dry_run)

    def _process_one(tk: str) -> int:
        if args.dry_run:
            df = _full_history(tk)
            rows = _filter_recent_rows(
                _build_indicator_rows(tk, df), recent_days)
            log.info("  %s: would upsert %d rows", tk, len(rows))
            return 0
        return backfill_ticker(tk, recent_days=recent_days)

    total_rows = 0
    errors: list[str] = []
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_process_one, tk): tk for tk in tickers}
        for i, fut in enumerate(as_completed(futures), 1):
            tk = futures[fut]
            try:
                total_rows += fut.result()
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
    # Job-level disposition: exit 1 only if more than half the tickers
    # failed. A single ticker with a delisted symbol or a one-off AV
    # 'Invalid API call' should NOT page on a job that processed 1,678/
    # 1,679 successfully. Closes F6 (CLAUDE.md §3.7 — single-ticker errors
    # are surfaced via the per-ticker WARNING log + the Errors-on summary,
    # not the job-level exit code). The failure-notifier still opens an
    # issue if the threshold trips. Pattern matches run_historical_signals.
    n_failed = len(errors)
    n_total = len(tickers)
    too_many = bool(n_total and n_failed / n_total > 0.5)
    # Telemetry for the freshness-watchdog's duration-regression check —
    # capacity drift (the #751 pattern: 19 silent near-misses of the
    # task-timeout) becomes a queryable trend instead of a cliff.
    record_job_run('backfill-daily-indicators', run_started,
                   'error' if too_many else 'success',
                   items_total=n_total,
                   items_processed=n_total - n_failed,
                   items_failed=n_failed,
                   rows_written=total_rows,
                   note=f"mode={args.mode} workers={workers}")
    if too_many:
        log.error("TOO-MANY-FAILURES — %d/%d tickers (%.0f%%) failed",
                  n_failed, n_total, 100 * n_failed / n_total)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
