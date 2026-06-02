#!/usr/bin/env python3
"""
Cloud Run Job — refresh the earnings frontend mat views + upcoming table.

Two modes:

  --mode=weekly (Sunday 8pm ET)
    Refreshes the two big mat views:
      - earnings_event_outcomes  (one row per (ticker, reported_date))
      - earnings_ticker_lean     (one row per ticker)
    These are CONCURRENTLY-safe (have UNIQUE indices) so readers don't block.

  --mode=daily (7:30am ET, before the morning brief)
    Rebuilds earnings_upcoming_with_history for the next 14 days. Joins
    earnings_calendar (deduped per ticker) with earnings_ticker_lean,
    computes per-event implied_move_pct (expected_move / prev_close),
    runs lib.earnings_reactions.recommended_structure() in BOTH
    long-only AND IC modes (user wants to see both), and emits
    last_3_events as compact JSONB.

Idempotent: re-running same-day replaces today's rows via UNIQUE on
(refresh_date, ticker, earnings_date). Weekly REFRESH is naturally
idempotent.

Usage:
    python -m gcp.refresh_earnings_views --mode=weekly
    python -m gcp.refresh_earnings_views --mode=daily
    python -m gcp.refresh_earnings_views --mode=daily --days=21
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from gcp.database import (  # noqa: E402
    execute_sql,
    is_cloud_sql_configured,
    query_to_dataframe,
    upsert_dataframe,
)
from lib.logging_config import setup_logging  # noqa: E402

setup_logging()
log = logging.getLogger("refresh-earnings-views")


# ── Weekly: REFRESH MATERIALIZED VIEW ─────────────────────────────────

def refresh_weekly() -> None:
    """REFRESH both mat views CONCURRENTLY (non-blocking on readers)."""
    log.info("refreshing earnings_event_outcomes (CONCURRENT)...")
    execute_sql("REFRESH MATERIALIZED VIEW CONCURRENTLY earnings_event_outcomes")
    log.info("  refreshed earnings_event_outcomes")

    log.info("refreshing earnings_ticker_lean (CONCURRENT)...")
    execute_sql("REFRESH MATERIALIZED VIEW CONCURRENTLY earnings_ticker_lean")
    log.info("  refreshed earnings_ticker_lean")


# ── Daily: rebuild earnings_upcoming_with_history ─────────────────────

def refresh_daily(days_ahead: int) -> None:
    """Rebuild today's row set in earnings_upcoming_with_history.

    Pulls next N days of upcoming earnings, joins lean stats, computes
    per-event implied_move + both recommendation modes, attaches the
    last-3-events JSONB summary.
    """
    today = date.today()
    log.info("refresh_daily — days_ahead=%d as_of=%s", days_ahead, today)

    # ── Pull upcoming reporters (deduped per ticker) + market_data_daily.close
    upcoming_sql = """
        SELECT u.ticker, u.earnings_date, u.earnings_time, u.company_name,
               u.market_cap, u.sector, u.eps_estimate, u.expected_move,
               u.options_volume, u.open_interest, u.score, u.strategy,
               (SELECT close FROM market_data_daily md
                 WHERE md.ticker = u.ticker
                   AND md.date < u.earnings_date
                 ORDER BY md.date DESC LIMIT 1) AS prev_close
        FROM (
            SELECT ticker,
                   MIN(earnings_date) AS earnings_date,
                   MAX(earnings_time) AS earnings_time,
                   MAX(company_name)  AS company_name,
                   MAX(market_cap)    AS market_cap,
                   MAX(sector)        AS sector,
                   MAX(eps_estimate)  AS eps_estimate,
                   MAX(expected_move) AS expected_move,
                   MAX(options_volume) AS options_volume,
                   MAX(open_interest) AS open_interest,
                   MAX(score)         AS score,
                   MAX(strategy)      AS strategy
            FROM earnings_calendar
            WHERE earnings_date BETWEEN CURRENT_DATE
                                    AND CURRENT_DATE + (:days)::int
            GROUP BY ticker
        ) u
        ORDER BY u.earnings_date, u.ticker
    """
    upcoming = query_to_dataframe(upcoming_sql, {'days': days_ahead})
    if upcoming is None or upcoming.empty:
        log.info("  no upcoming reporters in window — clearing today's rows")
        execute_sql(
            "DELETE FROM earnings_upcoming_with_history WHERE refresh_date = :d",
            {'d': today},
        )
        return
    log.info("  found %d upcoming reporters", len(upcoming))

    # ── Pull lean stats for all upcoming tickers (one shot)
    tickers = upcoming['ticker'].dropna().unique().tolist()
    placeholders = ','.join(f":t{i}" for i in range(len(tickers)))
    lean_params = {f"t{i}": t for i, t in enumerate(tickers)}
    lean_sql = (
        f"SELECT * FROM earnings_ticker_lean "
        f"WHERE ticker IN ({placeholders})"
    )
    lean = query_to_dataframe(lean_sql, lean_params)
    lean_by_ticker = (
        {row['ticker']: row.to_dict() for _, row in lean.iterrows()}
        if lean is not None and not lean.empty else {}
    )
    log.info("  lean stats available for %d / %d tickers",
             len(lean_by_ticker), len(tickers))

    # ── Pull last-3 events per ticker (JSONB summary)
    last3_sql = f"""
        SELECT ticker, reported_date, beat_meet_miss,
               reaction_gap_pct, eps_surprise_pct,
               realized_vs_implied_ratio
        FROM (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY ticker ORDER BY reported_date DESC
                   ) AS rn
            FROM earnings_event_outcomes
            WHERE ticker IN ({placeholders})
        ) ranked
        WHERE rn <= 3
        ORDER BY ticker, reported_date DESC
    """
    last3 = query_to_dataframe(last3_sql, lean_params)
    last3_by_ticker: dict[str, list[dict]] = {}
    if last3 is not None and not last3.empty:
        for ticker, group in last3.groupby('ticker'):
            last3_by_ticker[ticker] = [
                {
                    'date': str(r['reported_date']),
                    'beat_meet_miss': r['beat_meet_miss'],
                    'gap_pct': _safe_float(r['reaction_gap_pct']),
                    'eps_surprise_pct': _safe_float(r['eps_surprise_pct']),
                    'ratio': _safe_float(r['realized_vs_implied_ratio']),
                }
                for _, r in group.iterrows()
            ]

    # ── Live calibration metrics (for IC mode + long-only SKIP filter)
    from lib.earnings_reactions import (
        confidence_label, get_calibration_options_metrics,
        recommended_structure, score_quintile,
    )
    calib = get_calibration_options_metrics() or {}
    log.info("  live calibration metrics loaded: %s", list(calib.keys()) or 'EMPTY')

    # ── Build rows for upsert
    rows = []
    for _, u in upcoming.iterrows():
        ticker = u['ticker']
        expected_move = _safe_float(u.get('expected_move'))
        prev_close = _safe_float(u.get('prev_close'))
        implied_pct = None
        if expected_move is not None and prev_close is not None and prev_close > 0:
            implied_pct = expected_move / prev_close * 100.0

        score = _safe_float(u.get('score'))
        q = score_quintile(score)
        conf = confidence_label(score)
        # Archetype derivation lives on the lean stats — historical archetype
        # via dir_consistency + reversal_rate. If lean missing, default to None.
        lean_row = lean_by_ticker.get(ticker, {})
        archetype = _derive_archetype(lean_row)

        # BOTH recommendation modes
        long_only_rec = recommended_structure(
            archetype, q, calib,
            implied_move_pct=implied_pct, long_only=True,
        )
        ic_mode_rec = recommended_structure(
            archetype, q, calib,
            implied_move_pct=implied_pct, long_only=False,
        )

        rows.append({
            'refresh_date': today,
            'ticker': ticker,
            'earnings_date': u['earnings_date'],
            'earnings_time': u.get('earnings_time'),
            'company_name': u.get('company_name'),
            'market_cap': u.get('market_cap'),
            'sector': u.get('sector'),
            'eps_estimate': u.get('eps_estimate'),
            'expected_move': expected_move,
            'prev_close': prev_close,
            'implied_move_pct': implied_pct,
            'options_volume': _safe_int(u.get('options_volume')),
            'open_interest': _safe_int(u.get('open_interest')),
            'playability_score': score,
            'quintile': q,
            'archetype': archetype,
            'confidence_label': conf,
            'recommended_structure_long_only': long_only_rec,
            'recommended_structure_ic_mode': ic_mode_rec,
            'total_quarters': _safe_int(lean_row.get('total_quarters')),
            'n_beats':        _safe_int(lean_row.get('n_beats')),
            'n_meets':        _safe_int(lean_row.get('n_meets')),
            'n_misses':       _safe_int(lean_row.get('n_misses')),
            'beat_rate_pct':  _safe_float(lean_row.get('beat_rate_pct')),
            'avg_abs_gap_pct': _safe_float(lean_row.get('avg_abs_gap_pct')),
            'dir_consistency_pct': _safe_float(lean_row.get('dir_consistency_pct')),
            'reversal_rate_pct':   _safe_float(lean_row.get('reversal_rate_pct')),
            'avg_ratio':           _safe_float(lean_row.get('avg_ratio')),
            'lean_score':          _safe_float(lean_row.get('lean_score')),
            'long_winner_count':   _safe_int(lean_row.get('long_winner_count')),
            'short_winner_count':  _safe_int(lean_row.get('short_winner_count')),
            # Pass the Python list directly. SQLAlchemy + pg8000 bind
            # Python list/dict to JSONB as a proper JSON array, NOT as
            # a JSON-encoded string. (Calling json.dumps() here would
            # produce a string that Postgres stores as a JSON string
            # literal — frontend would get "[...]" instead of the
            # iterable array.) Codex review on PR #585.
            'last_3_events':       last3_by_ticker.get(ticker, []),
        })

    # ── Replace today's rows
    log.info("  deleting prior rows for refresh_date=%s", today)
    execute_sql(
        "DELETE FROM earnings_upcoming_with_history WHERE refresh_date = :d",
        {'d': today},
    )
    df = pd.DataFrame(rows)
    upsert_dataframe(
        df, 'earnings_upcoming_with_history',
        conflict_cols=['refresh_date', 'ticker', 'earnings_date'],
    )
    log.info("  inserted %d rows", len(df))


def _derive_archetype(lean_row: dict) -> Optional[str]:
    """Derive archetype from lean stats (matches lib.earnings_reactions logic).

    bullish_trend : dir_cons >= 65% AND avg_gap > +0.5%
    bearish_trend : dir_cons >= 65% AND avg_gap < -0.5%
    reversal_play : reversal_rate >= 40% AND dir_cons < 50%
    mixed         : everything else with avg_abs_gap > 1.5%
    quiet         : avg_abs_gap <= 1.5%
    """
    if not lean_row:
        return None
    mag = _safe_float(lean_row.get('avg_abs_gap_pct'))
    if mag is None or mag < 1.5:
        return 'quiet'
    dir_cons = _safe_float(lean_row.get('dir_consistency_pct'))
    rev_rate = _safe_float(lean_row.get('reversal_rate_pct'))
    bias = _safe_float(lean_row.get('avg_gap_pct')) or 0.0
    if dir_cons is not None and dir_cons >= 65:
        if bias > 0.5:
            return 'bullish_trend'
        if bias < -0.5:
            return 'bearish_trend'
    if rev_rate is not None and rev_rate >= 40 and (dir_cons or 0) < 50:
        return 'reversal_play'
    return 'mixed'


def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        if f != f or f in (float('inf'), float('-inf')):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _safe_int(v) -> Optional[int]:
    f = _safe_float(v)
    return int(f) if f is not None else None


# ── Entrypoint ────────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Refresh earnings frontend mat views + upcoming table')
    parser.add_argument('--mode', choices=['weekly', 'daily'], required=True,
                        help='weekly = REFRESH MATERIALIZED VIEW × 2; '
                             'daily = rebuild earnings_upcoming_with_history')
    parser.add_argument('--days', type=int, default=14,
                        help='Look-ahead window for --mode=daily (default 14)')
    args = parser.parse_args(argv)

    if not is_cloud_sql_configured():
        log.error('Cloud SQL not configured')
        return 1

    if args.mode == 'weekly':
        refresh_weekly()
    elif args.mode == 'daily':
        refresh_daily(args.days)
    log.info('done')
    return 0


if __name__ == '__main__':
    sys.exit(main())
