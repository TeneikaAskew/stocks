#!/usr/bin/env python3
"""
Pre-market refresh fetcher — runs at 8:20 AM ET (premarket-refresh-daily), before the 8:30 brief.

Targets a small set of tickers (today's earnings reporters + watchlist),
fetches today's pre-market bars from AlphaVantage, and UPSERTs the
``pre_high / pre_low / pre_vwap / pre_volume / gap_pct / pre_range_atr``
columns into ``market_data_daily`` for today's date.

Why a separate job from ``fetch_market_data.py``:
  - The nightly 11 PM fetcher captures the full session (including
    pre-market), but that's after the brief has fired.
  - At 8:30 AM brief render time, today's market_data_daily row doesn't
    yet exist, so the brief's LEFT JOIN to gap_pct returns NULL.
  - A targeted ~30-50 ticker refresh at 8:20 AM costs <1 minute of AV
    budget and populates today's gap_pct in time for the 8:30 brief.

Usage:
    python -m gcp.fetchers.fetch_premarket_refresh
    python -m gcp.fetchers.fetch_premarket_refresh --tickers AAPL MSFT
    python -m gcp.fetchers.fetch_premarket_refresh --max-tickers 25

Required env vars:
    ALPHA_VANTAGE_API_KEY
    CLOUD_SQL_CONNECTION_NAME / DB_USER / DB_PASS / DB_NAME
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.earnings_reactions import EARNINGS_NOT_RETIRED_SQL

log = logging.getLogger(__name__)


# ── Universe selection ──────────────────────────────────────────────────────

def resolve_universe(target_date: date, max_tickers: int = 50) -> list[str]:
    """Build the priority ticker set for pre-market refresh.

    Priority order:
      1. Watchlist tickers (always included)
      2. Today's earnings reporters with options flow (UW-confirmed) —
         filtered by ``options_volume > 0`` so we don't waste AV budget
         on long-tail names without tradeable options.

    Capped at ``max_tickers`` to keep the AV call count bounded — the
    AV premium tier allows 1200/day and ~150/min so 50 tickers leaves
    plenty of headroom for the rest of the daily pipeline.
    """
    try:
        from gcp.database import is_cloud_sql_configured, query_to_dataframe
    except ImportError:
        log.warning("gcp.database unavailable — cannot resolve universe")
        return []
    if not is_cloud_sql_configured():
        log.warning("Cloud SQL not configured — cannot resolve universe")
        return []

    universe: dict[str, int] = {}  # ticker → priority bucket (0=watchlist)

    # Watchlist (priority 0)
    try:
        from gcp.fetchers._watchlist import load_watchlist
        for t in load_watchlist():
            universe[t.upper()] = 0
    except Exception as e:
        log.warning("Watchlist load failed: %s", e)

    # Today's earnings tickers with options flow (priority 1)
    try:
        sql = f"""
            SELECT ticker, MAX(options_volume) AS opt_vol,
                   MAX(market_cap)            AS mcap
              FROM earnings_calendar
             WHERE {EARNINGS_NOT_RETIRED_SQL} AND earnings_date = :d
               AND COALESCE(options_volume, 0) > 0
             GROUP BY ticker
             ORDER BY (COALESCE(MAX(options_volume), 0) + 1)
                      * (COALESCE(MAX(market_cap), 0) / 1e9 + 1) DESC
             LIMIT :lim
        """
        df = query_to_dataframe(sql, {'d': target_date,
                                       'lim': max_tickers})
        for tk in df['ticker'].tolist():
            tk = str(tk).upper()
            if tk not in universe:
                universe[tk] = 1
    except Exception as e:
        log.warning("Earnings universe lookup failed: %s", e)

    # Yesterday's AMC reporters (priority 2) — their reaction shows in
    # today's pre-market, so we need today's bars for them too.
    try:
        prior = target_date - timedelta(days=1)
        # Walk back over weekends/holidays — find most recent weekday
        while prior.weekday() >= 5:
            prior -= timedelta(days=1)
        sql_amc = f"""
            SELECT DISTINCT ticker FROM earnings_calendar
             WHERE {EARNINGS_NOT_RETIRED_SQL} AND earnings_date = :d
               AND earnings_time = 'postmarket'
               AND COALESCE(options_volume, 0) > 0
        """
        df_amc = query_to_dataframe(sql_amc, {'d': prior})
        for tk in df_amc['ticker'].tolist():
            tk = str(tk).upper()
            if tk not in universe:
                universe[tk] = 2
    except Exception as e:
        log.warning("Yesterday-AMC universe lookup failed: %s", e)

    # Cap (watchlist always included; trim earnings tail)
    if len(universe) > max_tickers:
        sorted_tk = sorted(universe.items(), key=lambda kv: kv[1])
        universe = dict(sorted_tk[:max_tickers])

    return sorted(universe.keys())


# ── Pre-market computation ──────────────────────────────────────────────────

def _prior_session_from_db(ticker: str, fetch_date: date) -> dict:
    """The last completed session before ``fetch_date``: close, open, atr_14,
    atr_5.

    The 11pm-yesterday market_data_daily row has yesterday's close and ATRs
    already, so one backward lookup is enough. The premarket print filter
    needs the prior session's ATR in the policy's basis (FEAT-STRAT-001),
    never the fetch date's own row, which at 08:30 holds only premarket
    columns. Returns an empty dict when the query succeeds and finds no row;
    a failed query raises, so a lookup error is never read as "no prior
    session".
    """
    from gcp.database import query_to_dataframe
    sql = """
        SELECT close, open, atr_14, atr_5
          FROM market_data_daily
         WHERE ticker = :tk
           AND date < :d
           AND close IS NOT NULL
         ORDER BY date DESC
         LIMIT 1
    """
    df = query_to_dataframe(sql, {'tk': ticker, 'd': fetch_date})
    if df.empty:
        return {}
    row = df.iloc[0]
    out = {}
    for key in ('close', 'open', 'atr_14', 'atr_5'):
        v = row.get(key)
        out[key] = float(v) if v is not None and pd.notna(v) else None
    return out


def _prev_close_from_db(ticker: str, fetch_date: date) -> float | None:
    """Most recent regular-session close prior to ``fetch_date``."""
    return _prior_session_from_db(ticker, fetch_date).get('close')


def read_level_params_for_run(tickers, session_date):
    """The level parameters in force on `session_date` for the whole
    universe, in one query (FEAT-STRAT-001). Raises LevelParamsUnavailable
    when the tables cannot be read."""
    from gcp.database import query_to_dataframe_strict
    from lib.strat_levels import load_level_params
    return load_level_params(query_to_dataframe_strict, list(tickers), session_date)


def compute_premarket_for_ticker(ticker: str, fetch_date: date,
                                  api_key: str, *, level_params=None) -> dict | None:
    """Fetch today's intraday bars from AV and return pre-market metrics.

    Returns a dict with keys ``pre_high pre_low pre_vwap pre_volume
    gap_pct pre_range_atr`` (any of which may be None) plus ``ticker``
    and ``date``. Returns None if the AV fetch fails or no bars are in
    the pre-market window.

    `level_params` is the ticker's LevelParams in force on fetch_date
    (read once per run, read_level_params_for_run). The print filter runs
    with its calibrated thresholds only when both are ok; otherwise the
    snapshot carries pre_filter_status naming why and NULL excluded counts.
    """
    from gcp.fetchers.fetch_market_data import fetch_minute_data
    from lib.indicators import calculate_premarket_context

    iso_date = fetch_date.strftime('%Y-%m-%d')
    df = fetch_minute_data(ticker, iso_date, api_key)
    # When the bars behind this snapshot were fetched (a UTC instant).
    fetched_at = datetime.now(timezone.utc)
    if df.empty:
        log.info("  %s: no AV intraday bars for %s", ticker, iso_date)
        return None

    try:
        prior = _prior_session_from_db(ticker, fetch_date)
    except Exception as e:  # noqa: BLE001 withheld: a failed lookup is never "no prior session"
        log.error("  %s: premarket withheld for %s: prior-session lookup failed: %s",
                  ticker, iso_date, e)
        return None
    prev_close = prior.get('close')
    if level_params is None:
        pm_filter = {'status': 'level_params_unavailable', 'atr': None,
                     'stale_print_atr': None, 'spike_atr': None, 'params': None}
    else:
        from lib.strat_levels import premarket_filter_inputs
        pm_filter = premarket_filter_inputs(
            level_params, {'atr_14': prior.get('atr_14'), 'atr_5': prior.get('atr_5')})

    # `times` must be a Series so calculate_premarket_context's tz-aware
    # path runs (DatetimeIndex falls to a per-row Python loop that builds
    # a default-int-index Series, which then fails to align with OHLCV).
    times_series = df.index.to_series().reset_index(drop=True)
    pm = calculate_premarket_context(
        times=times_series,
        open_=df['Open'].reset_index(drop=True),
        high=df['High'].reset_index(drop=True),
        low=df['Low'].reset_index(drop=True),
        close=df['Close'].reset_index(drop=True),
        volume=df['Volume'].reset_index(drop=True),
        prev_close=prev_close,
        atr=pm_filter['atr'],
        prev_open=prior.get('open'),
        stale_print_atr=pm_filter['stale_print_atr'],
        spike_atr=pm_filter['spike_atr'],
    )
    if pm.get('bar_count', 0) <= 0:
        log.info("  %s: 0 pre-market bars for %s (early run, weekend, or holiday)",
                 ticker, iso_date)
        return None

    return {
        'ticker': ticker,
        'date': fetch_date,
        'pre_high': pm.get('pre_high'),
        'pre_low': pm.get('pre_low'),
        'pre_vwap': pm.get('pre_vwap'),
        'pre_volume': pm.get('pre_volume'),
        'gap_pct': pm.get('gap_pct'),
        'excluded_prior_close_prints': pm.get('excluded_prior_close_prints'),
        'excluded_spike_prints': pm.get('excluded_spike_prints'),
        # The provenance columns (FEAT-STRAT-001), written when the table
        # has them (see upsert_premarket). The counts are None when the
        # filter did not run.
        'pre_fetched_at': fetched_at,
        'pre_excluded_stale_prints': pm.get('excluded_prior_close_prints'),
        'pre_excluded_spikes': pm.get('excluded_spike_prints'),
        # Whether the prints were filtered with the ticker's own thresholds,
        # and which (Design 8). Not ok: the builder refuses the snapshot.
        'pre_filter_status': 'ok' if pm.get('filtered') else (
            pm_filter['status'] if pm_filter['status'] != 'ok' else 'atr_unavailable'),
        'pre_filter_params': (json.dumps(pm_filter['params'], sort_keys=True)
                              if pm_filter['params'] is not None else None),
    }


# ── Persist (UPSERT only the pre_* columns) ─────────────────────────────────

def upsert_premarket(rows: list[dict]) -> int:
    """UPSERT today's pre-market columns into market_data_daily.

    Filters out rows where every pre_* field is NULL — AV had nothing
    useful for that ticker, so an INSERT would create a row with all
    OHLC + all pre_* NULL. That broke the morning brief
    (compute_current_levels crashed on max(NULL, current_price)) until
    the strat_levels NULL-handling fix landed; this guard prevents the
    underlying bad rows from being written in the first place.

    For rows that DO have at least one pre_* signal:
    - If today's row exists (rare at 8:30am), UPDATE pre_* only.
    - If it doesn't, INSERT pre_* fields; full OHLC fills tonight at 11pm.

    Returns the number of rows touched.
    """
    if not rows:
        return 0
    # Skip rows with no useful pre-market data — AV gave us nothing.
    PRE_KEYS = ('pre_high', 'pre_low', 'pre_vwap', 'pre_volume', 'gap_pct')
    useful = [r for r in rows
              if any(r.get(k) is not None for k in PRE_KEYS)]
    skipped = len(rows) - len(useful)
    if skipped:
        log.info("skipped %d ticker(s) with no AV pre-market data", skipped)
    if not useful:
        return 0

    try:
        from gcp.database import get_engine
    except ImportError:
        log.warning("gcp.database unavailable — cannot persist")
        return 0

    import sqlalchemy
    eng = get_engine()
    sql = sqlalchemy.text(_upsert_premarket_sql(_has_provenance_columns(eng)))
    n = 0
    with eng.begin() as conn:
        for r in useful:
            conn.execute(sql, {k: r.get(k) for k in _UPSERT_KEYS})
            n += 1
    return n


_PROVENANCE_COLUMNS = ('pre_fetched_at', 'pre_excluded_stale_prints', 'pre_excluded_spikes',
                       'pre_filter_status', 'pre_filter_params')
_UPSERT_KEYS = ('ticker', 'date', 'pre_high', 'pre_low', 'pre_vwap', 'pre_volume',
                'gap_pct') + _PROVENANCE_COLUMNS


def _has_provenance_columns(eng) -> bool:
    """True when market_data_daily has the premarket provenance columns
    (FEAT-STRAT-001). They wait on the owner's schema apply, so the writer
    checks rather than assumes; any failure reads as absent."""
    import sqlalchemy
    try:
        with eng.connect() as conn:
            found = conn.execute(sqlalchemy.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'market_data_daily' "
                "AND column_name IN ('pre_fetched_at', 'pre_excluded_stale_prints', "
                "'pre_excluded_spikes', 'pre_filter_status', 'pre_filter_params')"
            )).fetchall()
    except Exception:  # noqa: BLE001 absent is the safe reading
        return False
    return {row[0] for row in found} >= set(_PROVENANCE_COLUMNS)


def _upsert_premarket_sql(with_provenance: bool) -> str:
    cols = ['pre_high', 'pre_low', 'pre_vwap', 'pre_volume', 'gap_pct']
    if with_provenance:
        cols += list(_PROVENANCE_COLUMNS)
    # The filter status and its counts describe this snapshot only: they are
    # overwritten, never COALESCEd with an earlier run's, so an unfiltered
    # rerun cannot leave an earlier run's 'ok' beside its unfiltered prices.
    overwrite = {'pre_excluded_stale_prints', 'pre_excluded_spikes',
                 'pre_filter_status', 'pre_filter_params'}
    sets = ',\n            '.join(
        f"{c} = EXCLUDED.{c}" if c in overwrite
        else f"{c} = COALESCE(EXCLUDED.{c}, market_data_daily.{c})" for c in cols)
    values = [f"CAST(:{c} AS JSONB)" if c == 'pre_filter_params' else f":{c}" for c in cols]
    return (
        "INSERT INTO market_data_daily\n"
        f"    (ticker, date, {', '.join(cols)})\n"
        "VALUES\n"
        f"    (:ticker, :date, {', '.join(values)})\n"
        "ON CONFLICT (ticker, date) DO UPDATE SET\n"
        f"            {sets}"
    )


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(levelname)-8s %(message)s',
        datefmt='%H:%M:%S',
    )

    parser = argparse.ArgumentParser(
        description="Pre-market refresh: fetch today's pre-market bars "
                    "for earnings + watchlist tickers, write gap_pct.")
    parser.add_argument('--tickers', nargs='*', default=None,
                        help='Override universe with explicit tickers')
    parser.add_argument('--max-tickers', type=int,
                        default=int(os.environ.get('PREMARKET_MAX_TICKERS', '50')),
                        help='Cap on universe size (default 50)')
    parser.add_argument('--date', default=None,
                        help='Date to refresh (YYYY-MM-DD). Default: today.')
    args = parser.parse_args()

    target = (datetime.strptime(args.date, '%Y-%m-%d').date()
              if args.date else date.today())

    api_key = os.environ.get('ALPHA_VANTAGE_API_KEY', '')
    if not api_key:
        log.error("ALPHA_VANTAGE_API_KEY not set — cannot fetch")
        sys.exit(1)

    if args.tickers:
        universe = [t.upper() for t in args.tickers]
        log.info("Override universe: %d tickers", len(universe))
    else:
        universe = resolve_universe(target, max_tickers=args.max_tickers)
        log.info("Resolved universe: %d tickers (target_date=%s)",
                 len(universe), target)

    if not universe:
        log.warning("No tickers to refresh — exiting cleanly")
        return

    # FEAT-STRAT-001: the print thresholds for the whole universe, read
    # once. Unreadable tables: every snapshot is written unfiltered
    # (pre_filter_status level_params_unavailable) and the run exits non-zero.
    from lib.strat_levels import LevelParamsUnavailable
    params_failed = False
    try:
        run_params = read_level_params_for_run(universe, target)
    except LevelParamsUnavailable as e:
        log.error("level_params_unavailable: %s (premarket snapshots written unfiltered)", e)
        run_params, params_failed = {}, True

    rows = []
    for tk in universe:
        result = compute_premarket_for_ticker(tk, target, api_key,
                                              level_params=run_params.get(tk.upper()))
        if result:
            rows.append(result)

    log.info("Computed pre-market for %d/%d tickers", len(rows), len(universe))

    n = upsert_premarket(rows)
    log.info("Upserted %d rows into market_data_daily for %s", n, target)
    if params_failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
