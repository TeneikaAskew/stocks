#!/usr/bin/env python3
"""
Pre-market brief -- Cloud Run Job triggered by Cloud Scheduler at 8:30 AM ET.

Loads latest daily data from Cloud SQL, computes Strat/FTFC classifications,
queries upcoming economic events, and sends a rich multi-embed Discord brief.
Also persists per-ticker analysis to the premarket_analysis table.
"""

import argparse
import os
import sys
import json
import logging
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.data_loader import DataLoader
from lib.indicators import add_all_indicators
from lib.strat import StratClassifier, compute_strat_status
from lib.strat_levels import build_level_map, format_levels_for_brief, levels_to_named_dict
from lib.signals import check_call_conditions, check_put_conditions
from lib.config import load_config

# Configure logging for the Cloud Run Job. Without this, `logger.info()`
# calls in this module (e.g. the persist_level_map success/failure log)
# are dropped because Python's default level is WARNING. Cloud Run
# captures stderr, which is where the basicConfig handler writes.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Discord embed limits
MAX_EMBED_CHARS = 6000
MAX_FIELD_VALUE = 1024


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_float(val, default=None):
    """Extract a float from a pandas value, returning default if NaN/None."""
    if val is None:
        return default
    try:
        f = float(val)
        return default if pd.isna(f) else f
    except (TypeError, ValueError):
        return default


def _delete_null_close_rows(ticker: str) -> int:
    """Delete market_data_daily rows for `ticker` that have NULL close.

    Some upstream fetchers (mystery 06:44 EDT script on 2026-04-30
    inserted 43 NULL placeholder rows — see
    docs/incidents/2026-04-30-null-rows.md) have created placeholder
    rows that crash the brief's level-map builder. The brief filters
    them out at read time AND opportunistically deletes them here so
    future runs don't re-encounter the same garbage.

    Fire-and-forget — any DB error is logged at WARNING and swallowed.
    Returns the number of rows deleted (0 on error).
    """
    try:
        from gcp.database import is_cloud_sql_configured, execute_sql
    except ImportError:
        return 0
    if not is_cloud_sql_configured():
        return 0
    try:
        execute_sql(
            "DELETE FROM market_data_daily "
            "WHERE ticker = :t AND close IS NULL",
            {'t': ticker.upper()},
        )
        # execute_sql doesn't return rowcount via the helper signature.
        # Log unconditionally — caller already gated on dropped > 0.
        logger.info(
            "[brief:%s] cleaned up NULL-close rows in market_data_daily",
            ticker,
        )
        return 1  # signal "did the cleanup attempt"
    except Exception as exc:
        logger.warning(
            "[brief:%s] NULL-row cleanup failed (non-fatal): %s",
            ticker, exc,
        )
        return 0


def _vol_regime(vol_20d):
    """Classify annualized 20-day volatility into a regime label."""
    if vol_20d is None:
        return 'N/A'
    v = vol_20d * 100 if vol_20d < 1 else vol_20d  # handle both decimal and pct
    if v < 12:
        return 'Low'
    if v < 20:
        return 'Normal'
    if v < 30:
        return 'High'
    return 'Extreme'


def _macd_cross(macd, macd_signal):
    """Return 'Bullish' or 'Bearish' based on MACD vs signal line."""
    if macd is None or macd_signal is None:
        return 'N/A'
    return 'Bullish' if macd > macd_signal else 'Bearish'


# ── Earnings Calendar ───────────────────────────────────────────────────────

def load_earnings_for_brief(today: date, weekly: bool = False, top_n: int = 25) -> dict:
    """Query earnings_calendar for the premarket brief.

    On weekdays (weekly=False): returns today's earnings only.
    On Sundays (weekly=True):   returns the upcoming Mon-Fri earnings.

    Tickers are tiered by source coverage so the most-confirmed names always
    appear first within each day (vs alphabetical order getting truncated):
        Tier 1: AV + UW + EW   (all three sources — top confirmed + strategy)
        Tier 2: AV + UW        (top market-movers per UW, no EW strategy)
        Tier 3: AV + EW        (strategy pick without UW validation)
        Tier 4: AV + (EW or UW alone without AV — edge case)
        Tier 5: EW-only or UW-only
        Tier 6: AV-only        (long-tail small caps)

    Within each tier, display row prefers EW > AV > UW so strategy details
    (strike/premium/score) surface when available.

    The result is capped at ``top_n`` rows AFTER tier-then-market-cap sort —
    so the cut keeps the most-confirmed, most-liquid names. Pass ``top_n=0``
    for legacy unbounded behaviour. Default 25 matches
    ``fetch_market_data --max-earnings-tickers`` so the morning Discord
    embed surfaces the same names the daily fetcher prioritises.
    """
    try:
        from gcp.database import is_cloud_sql_configured, query_to_dataframe
    except ImportError:
        return {'mode': 'daily', 'earnings': []}

    if not is_cloud_sql_configured():
        return {'mode': 'daily', 'earnings': []}

    if weekly:
        # Sunday → next Mon through Fri
        days_until_monday = (7 - today.weekday()) % 7 or 7
        start = today + timedelta(days=days_until_monday)
        end = start + timedelta(days=4)  # Mon..Fri
        mode = 'weekly'
    else:
        start = end = today
        mode = 'daily'

    # Pull all rows, then dedupe + tier in Python
    # Pull liquidity/quality signals too so we can break tier ties.
    # Most are UW-only; AV/EW rows leave them NULL → sort gates handle that.
    #
    # LEFT JOIN market_data_daily on (ticker, earnings_date) so the embed
    # can surface today's pre-market gap next to BMO reporters and any
    # available pre-session range for AMC names whose post-day reaction
    # is in scope. NULL when the ticker isn't in the daily fetcher
    # universe — handled downstream.
    sql = """
        SELECT ec.ticker, ec.earnings_date, ec.company_name, ec.earnings_time,
               ec.eps_estimate, ec.eps_actual, ec.eps_surprise_pct,
               ec.expected_move, ec.sector, ec.market_cap,
               ec.stock_volume, ec.options_volume, ec.open_interest,
               ec.rv_1d_last_12q,
               ec.strategy, ec.strike, ec.premium, ec.score, ec.data_source,
               ec.ew_strike_verdict, ec.ew_strike_move_pct,
               ec.ew_minutes_to_hit, ec.ew_minutes_in_zone,
               ec.ew_day_change_pct,
               md.gap_pct, md.pre_high, md.pre_low, md.pre_vwap
        FROM earnings_calendar ec
        LEFT JOIN market_data_daily md
          ON md.ticker = ec.ticker AND md.date = ec.earnings_date
        WHERE ec.earnings_date BETWEEN :start AND :end
        ORDER BY ec.ticker, ec.earnings_date
    """
    df = query_to_dataframe(sql, {'start': start, 'end': end})

    if df.empty:
        return {'mode': mode, 'start': start, 'end': end, 'earnings': []}

    # Group by (ticker, earnings_date) — collect all sources per group
    from collections import defaultdict
    groups: dict = defaultdict(lambda: {'sources': set(), 'rows': []})
    for _, row in df.iterrows():
        key = (row['ticker'], row['earnings_date'])
        groups[key]['sources'].add(row['data_source'])
        groups[key]['rows'].append(row)

    # Row priority within a group: EW carries strategy info, prefer it
    row_prio = {'earnings_whispers': 0, 'alphavantage': 1, 'unusual_whales': 2,
                'yahoo': 3}

    def _tier(sources: set) -> int:
        """Tier rows by independent date-source coverage.

        AV (SEC filings), UW (analyst-expected), and Yahoo (Yahoo Finance
        calendar) are all *date-confirming* sources — when 2+ agree on a
        date, that date is well-established. EW signals trader interest
        (a strategy was published) but isn't a date-of-truth source on
        its own.

        AV's date is sometimes wrong (~20% of SP500 names — observed
        cases: SBUX, V, STX, EA, FSLR). Yahoo was added so a UW-only
        row that Yahoo confirms gets promoted to tier 2 instead of
        being cut by the top-N cap.
        """
        has_av = 'alphavantage' in sources
        has_uw = 'unusual_whales' in sources
        has_ew = 'earnings_whispers' in sources
        has_yh = 'yahoo' in sources
        n_date_sources = int(has_av) + int(has_uw) + int(has_yh)

        if n_date_sources >= 2 and has_ew:
            return 1   # 2+ dates agree + EW strategy — strongest signal
        if n_date_sources >= 2:
            return 2   # 2+ independent date sources agree
        if (has_uw or has_yh) and has_ew:
            return 3   # UW or Yahoo + EW strategy
        if has_uw or has_yh:
            return 4   # one non-AV date source confirmed
        if has_ew:
            return 5   # EW alone (rare — strategy without confirmed date)
        return 6   # AV only (long tail; AV often has stale dates)

    def _max_non_null(rows, key):
        """Largest non-null value of `key` across a row group, or None."""
        vals = [r.get(key) for r in rows if r.get(key) is not None and not pd.isna(r.get(key))]
        return max(vals) if vals else None

    def _best_time(rows_list):
        """Pick the most-specific earnings_time across the group.

        Group-by-(ticker, date) collects rows from all data sources, but
        AV often persists earnings_time='unknown' even when UW knows the
        time. Using the lowest-priority row's time directly mis-buckets
        names like META/GOOGL into "Time Unknown" when UW had postmarket
        all along.

        Selection: any specific value beats 'unknown'; within specific
        values UW > AV > EW (UW's time-of-day is the most reliable per
        the Yahoo cross-check observations). Yahoo's calendar API never
        surfaces BMO/AMC so its time is always 'unknown' here.
        """
        src_prio = {'unusual_whales': 0, 'alphavantage': 1, 'earnings_whispers': 2}
        specific = [r for r in rows_list
                    if r.get('earnings_time')
                    and r['earnings_time'] != 'unknown']
        if specific:
            specific.sort(key=lambda r: src_prio.get(r.get('data_source'), 99))
            return specific[0]['earnings_time']
        return 'unknown'

    earnings = []
    for (ticker, earnings_date), group in groups.items():
        best = min(group['rows'], key=lambda r: row_prio.get(r['data_source'], 99))
        # Coalesce per-row signals across the (ticker, date) group. UW omits
        # market_cap on some rows; AV omits everything except the date. We
        # don't want a NULL from one source to outrank a real value from
        # another.
        rows_list = group['rows']
        mcap = _max_non_null(rows_list, 'market_cap')
        stock_vol = _max_non_null(rows_list, 'stock_volume')
        options_vol = _max_non_null(rows_list, 'options_volume')
        oi = _max_non_null(rows_list, 'open_interest')
        rv_12q = _max_non_null(rows_list, 'rv_1d_last_12q')
        # Coalesce expected_move (UW & EW provide it; AV & Yahoo don't).
        # Without this the embed would show blank EM for tier-2 names
        # whose 'best' row is the AV one (best is by EW>AV>UW priority).
        expected_move = _max_non_null(rows_list, 'expected_move')
        # Same pattern for eps_estimate — AV/UW/Yahoo all provide it,
        # but EW does not. When best is the EW row, eps_estimate would
        # render NULL even though other rows have it. Coalesce so
        # tickers with EW strategy picks still show the estimate (and
        # the "EPS X→Y" form rather than "EPS act Y" alone).
        eps_estimate = _max_non_null(rows_list, 'eps_estimate')
        # is_s_p_500 dropped: UW's flag is missing for ~half of real
        # SP500 names (WELL/WM/MDLZ/NXPI/OKE etc.) so it's noise rather
        # than signal. Tradeability ranking (options_volume × market_cap)
        # picks up SP500-grade liquidity directly.

        # Pre-market reaction signals from market_data_daily (LEFT JOIN).
        # For BMO reporters today: gap_pct = today's premarket open vs
        # yesterday's close — directly reflects the announcement reaction.
        # For AMC reporters today: NULL until tomorrow's gap. NULL also
        # when the ticker isn't in the daily fetcher universe yet.
        gap = _max_non_null(rows_list, 'gap_pct')
        pre_h = _max_non_null(rows_list, 'pre_high')
        pre_l = _max_non_null(rows_list, 'pre_low')

        # Beat/miss enrichment — Yahoo TAS rows carry these. None for
        # not-yet-reported names.
        eps_actual = _max_non_null(rows_list, 'eps_actual')
        # eps_surprise_pct can be negative (miss) so don't use _max_non_null;
        # take any non-null value (typically only Yahoo TAS supplies it).
        surprises = [r.get('eps_surprise_pct') for r in rows_list
                     if r.get('eps_surprise_pct') is not None
                     and not pd.isna(r.get('eps_surprise_pct'))]
        eps_surprise_pct = surprises[0] if surprises else None

        # EW strike verdict columns — only the EW source row carries
        # them; coalesce so the inline render works regardless of which
        # row was 'best'.
        def _first_non_null(key):
            for rr in rows_list:
                v = rr.get(key)
                if v is not None and not (isinstance(v, float) and pd.isna(v)):
                    return v
            return None
        ew_verdict = _first_non_null('ew_strike_verdict')
        ew_move_pct = _first_non_null('ew_strike_move_pct')
        ew_min_to_hit = _first_non_null('ew_minutes_to_hit')
        ew_min_in_zone = _first_non_null('ew_minutes_in_zone')
        ew_day_chg = _first_non_null('ew_day_change_pct')

        earnings.append({
            'ticker': ticker,
            'date': earnings_date,
            'company_name': best.get('company_name') or '',
            'time': _best_time(rows_list),
            'eps_estimate': eps_estimate,
            'eps_actual': eps_actual,
            'eps_surprise_pct': eps_surprise_pct,
            'expected_move': expected_move,
            'sector': best.get('sector') or '',
            'market_cap': mcap,
            'stock_volume': stock_vol,
            'options_volume': options_vol,
            'open_interest': oi,
            'rv_1d_last_12q': rv_12q,
            'strategy': best.get('strategy') or '',
            'strike': best.get('strike'),
            'premium': best.get('premium'),
            'score': best.get('score'),
            'source': best.get('data_source'),
            'sources': sorted(group['sources']),
            'tier': _tier(group['sources']),
            'gap_pct': gap,
            'pre_high': pre_h,
            'pre_low': pre_l,
            'ew_strike_verdict': ew_verdict,
            'ew_strike_move_pct': ew_move_pct,
            'ew_minutes_to_hit': ew_min_to_hit,
            'ew_minutes_in_zone': ew_min_in_zone,
            'ew_day_change_pct': ew_day_chg,
        })

    # Filter out names without options flow — earnings are only tradeable
    # via options for our use case, and a ticker with options_volume=0
    # (or NULL) means UW reported no options activity. AV-only / EW-only
    # rows often have NULL options_volume because the field is UW-derived;
    # those long-tail names rarely have meaningful options markets anyway.
    # NULL → 0 → filtered.
    earnings = [e for e in earnings if (e.get('options_volume') or 0) > 0]

    # Confirmed-only filter: keep tier 1-3 only (multi-source confirmed +
    # strategy picks). Tier 4-6 are single-source / AV-only / EW-alone —
    # the long tail. Override via BRIEF_INCLUDE_UNCONFIRMED=1 if you ever
    # want the legacy "everything" view back.
    if os.environ.get('BRIEF_INCLUDE_UNCONFIRMED', '0') != '1':
        earnings = [e for e in earnings if e.get('tier', 6) <= 3]

    # Sort by tradeability first, tier as tiebreaker.
    #
    # Tier-only sorting put EW-confirmed-but-illiquid names (WELL, WM,
    # MDLZ, NXPI, OKE — all options_volume=0) ahead of high-flow names
    # like SBUX (20K options, $112B mcap) just because EW picked a
    # strategy. From a trader's POV that's backwards: real options
    # flow + institutional weight matters more than analyst confirmation.
    #
    # Composite score (options_volume + 1) × (market_cap_B + 1):
    #   - Names with BOTH signals get multiplicative boost
    #   - Names with zero options collapse toward linear market_cap
    #     (well below names with real options flow)
    #   - Tier still matters as a tiebreaker for similar-score names
    def _rank_score(r):
        ovol = r.get('options_volume') or 0
        mcap = r.get('market_cap') or 0
        return (ovol + 1) * (mcap / 1e9 + 1)

    earnings.sort(key=lambda r: (
        r['date'],
        -_rank_score(r),     # tradeability primary (DESC)
        r['tier'],           # tier breaks ties (1 before 6)
        r['ticker'],
    ))

    # Cap at top_n AFTER the tier sort so the cut keeps the highest-quality
    # rows. ``top_n=0`` disables the cap (legacy behaviour).
    if top_n and top_n > 0:
        earnings = earnings[:top_n]

    # Enrich with the historical reaction profile + playability_score.
    # Each row gains:
    #   - playability_score (vol-normalized, options-weighted; None when
    #     no historical data available)
    #   - playability_archetype ('bullish_trend' | 'bearish_trend' |
    #     'reversal_play' | 'mixed' | 'quiet')
    #   - playability_n_q + the underlying inputs for the embed to render
    # See lib/earnings_reactions.py for the formula.
    try:
        from lib.earnings_reactions import enrich_with_playability
        enrich_with_playability(earnings)
    except Exception as e:
        # Don't fail the brief if the populator hasn't run yet — just log.
        logger.warning("playability enrichment skipped: %s", e)

    return {'mode': mode, 'start': start, 'end': end, 'earnings': earnings}


# ── Yesterday-AMC reaction view (PR 3) ──────────────────────────────────────

def load_yesterday_amc_reactions(today: date, top_n: int = 5) -> list[dict]:
    """Yesterday's AMC reporters + today's pre-market gap reaction.

    The morning brief shows TODAY's earnings. But yesterday's AMC names
    (SBUX 4/28 PM, AMZN 4/29 PM, etc.) had their announcement drop AFTER
    yesterday's close — the actual market reaction lives in TODAY's
    pre-market gap. Surfacing those rows in the morning brief turns
    "what just happened?" into one glance.

    Walks back to the most recent prior weekday (skips Sat/Sun), filters
    AMC reporters with options_volume>0, JOINs today's market_data_daily
    for gap_pct, returns the top N by absolute gap. Skips rows where
    today's gap is NULL (the pre-market refresh hasn't run yet, or the
    ticker isn't in the daily fetcher universe).

    Returns a list of dicts ready for the embed builder. Each dict carries
    the same shape as load_earnings_for_brief rows so _row_line works.
    """
    try:
        from gcp.database import is_cloud_sql_configured, query_to_dataframe
    except ImportError:
        return []
    if not is_cloud_sql_configured():
        return []

    # Walk back to most recent weekday
    prior = today - timedelta(days=1)
    while prior.weekday() >= 5:  # Sat=5, Sun=6
        prior -= timedelta(days=1)

    sql = """
        SELECT ec.ticker, ec.earnings_date,
               MAX(ec.eps_estimate)      AS eps_estimate,
               MAX(ec.eps_actual)        AS eps_actual,
               MAX(ec.eps_surprise_pct)  AS eps_surprise_pct,
               MAX(ec.market_cap)        AS market_cap,
               MAX(ec.options_volume)    AS options_volume,
               MAX(ec.expected_move)     AS expected_move,
               MAX(ec.strategy)          AS strategy,
               md.gap_pct, md.pre_high, md.pre_low
          FROM earnings_calendar ec
          LEFT JOIN market_data_daily md
                 ON md.ticker = ec.ticker AND md.date = :today
         WHERE ec.earnings_date = :prior
           AND ec.earnings_time = 'postmarket'
           AND COALESCE(ec.options_volume, 0) > 0
         GROUP BY ec.ticker, ec.earnings_date, md.gap_pct, md.pre_high, md.pre_low
    """
    df = query_to_dataframe(sql, {'today': today, 'prior': prior})
    if df.empty:
        return []

    rows = []
    for _, r in df.iterrows():
        gap = r.get('gap_pct')
        if gap is None or pd.isna(gap):
            # No reaction data yet — skip rather than render a useless row
            continue
        rows.append({
            'ticker': r['ticker'],
            'date': r['earnings_date'],
            'time': 'postmarket',
            'tier': 1,            # display-only (not used for sort here)
            'eps_estimate': r.get('eps_estimate'),
            'eps_actual': r.get('eps_actual'),
            'eps_surprise_pct': r.get('eps_surprise_pct'),
            'market_cap': r.get('market_cap'),
            'options_volume': r.get('options_volume'),
            'expected_move': r.get('expected_move'),
            'strategy': r.get('strategy') or '',
            'strike': None, 'premium': None, 'score': None,
            'sources': [],
            'gap_pct': float(gap),
            'pre_high': r.get('pre_high'),
            'pre_low': r.get('pre_low'),
        })

    # Top by absolute gap (biggest movers first, regardless of direction)
    rows.sort(key=lambda x: -abs(x['gap_pct']))
    return rows[:top_n] if top_n else rows


# ── Economic Events ─────────────────────────────────────────────────────────

def load_economic_events(today: date, days_ahead: int = 5) -> dict:
    """Query economic_events from Cloud SQL for today and upcoming days."""
    try:
        from gcp.database import is_cloud_sql_configured, query_to_dataframe
    except ImportError:
        return {'today': [], 'week': []}

    if not is_cloud_sql_configured():
        return {'today': [], 'week': []}

    end_date = today + timedelta(days=days_ahead)
    # Filter at SQL level:
    #   1. Mon-Fri only (DOW 1-5) — weekend rows are FRED metadata artifacts
    #   2. High + medium impact only (ForexFactory's red + orange folders)
    sql = """
        SELECT event_date, event_time, event_name, importance, actual, forecast, previous
        FROM economic_events
        WHERE event_date BETWEEN :start AND :end
          AND importance IN ('high', 'medium')
          AND EXTRACT(DOW FROM event_date) NOT IN (0, 6)
        ORDER BY event_date, importance DESC, event_time NULLS LAST
    """
    df = query_to_dataframe(sql, {'start': today, 'end': end_date})

    # Quality filter: for each date, if any row has a release time (from
    # ForexFactory), drop all TBD rows for that date (FRED duplicates without
    # times are lower quality). Only fall through to TBD rows when FF has
    # no coverage for that day.
    dates_with_times = set(
        df[df['event_time'].notna()]['event_date'].unique()
    )
    df = df[
        df['event_time'].notna()
        | ~df['event_date'].isin(dates_with_times)
    ].reset_index(drop=True)

    today_events, week_events = [], []
    for _, row in df.iterrows():
        ev = {
            'date': row['event_date'],
            'time': str(row['event_time'])[:5] if row.get('event_time') else '',
            'name': row['event_name'],
            'importance': row['importance'],
            'forecast': row.get('forecast') or '',
            'previous': row.get('previous') or '',
        }
        if row['event_date'] == today:
            today_events.append(ev)
        else:
            week_events.append(ev)

    return {'today': today_events, 'week': week_events}


# ── Catalyst-aware ORB window selection ─────────────────────────────────────

def select_orb_window(today_events: list) -> dict:
    """Pick the ORB window based on the day's economic calendar.

    Per docs/STRAT_METHODOLOGY.md §8:
      - 8:30 ET high-impact event   -> 15m
      - 10:00 ET high-impact event  -> 30m
      - No high-impact event before 10:30 ET -> 5m

    Returns ``{'window': '5m'|'15m'|'30m', 'reason': str}``.
    """
    high_impact = [
        e for e in (today_events or [])
        if (e.get('importance') or '').lower() == 'high'
    ]
    for ev in high_impact:
        t = (ev.get('time') or '')[:5]
        name = ev.get('name') or ''
        if t == '08:30':
            return {'window': '15m', 'reason': f'15-min ORB recommended (08:30 {name})'}
        if t == '10:00':
            return {'window': '30m', 'reason': f'30-min ORB recommended (10:00 {name})'}

    return {'window': '5m', 'reason': '5-min ORB (default scalp window, no high-impact catalyst)'}


# ── Brief Generation ────────────────────────────────────────────────────────

def _resolve_analysis_date() -> date:
    """Resolve the brief's analysis date.

    Honours `BRIEF_AS_OF=YYYY-MM-DD` for historical replay (Discord
    /replay command, ad-hoc backfills) — falls back to today otherwise.
    Future-dated cutoffs are rejected so a typo doesn't silently
    produce a blank brief.
    """
    raw = os.environ.get("BRIEF_AS_OF")
    if not raw or not raw.strip():
        return date.today()
    parsed = date.fromisoformat(raw.strip())
    if parsed > date.today():
        raise ValueError(f"BRIEF_AS_OF {raw!r} is in the future")
    return parsed


def _resolve_brief_tickers(default_tickers: list[str]) -> list[str]:
    """Resolve the ticker list the brief runs against.

    Resolution order (first non-empty wins):
      1. ``BRIEF_TICKERS`` env var — one-off / replay invocations that
         focus on a specific subset. Accepts comma-, semicolon-, or
         space-separated values; semicolon needed because gcloud's
         ``--update-env-vars`` uses comma as its OWN delimiter.
      2. Cloud SQL ``watchlists`` filtered by ``in_brief = TRUE`` —
         the production source of truth for "what shows in the brief".
         Lets users add peer tickers (NVDA, AMD, …) to the watchlist
         for /similar lookups WITHOUT bloating the morning Discord
         message — only ETFs/index tickers carry ``in_brief = TRUE``.
      3. ``default_tickers`` (cfg.market.tickers) — local-dev fallback.
    """
    raw = os.environ.get("BRIEF_TICKERS")
    if raw and raw.strip():
        # Normalize all separators to whitespace, then split.
        normalized = raw.replace(',', ' ').replace(';', ' ')
        parts = [t.strip().upper() for t in normalized.split() if t.strip()]
        if parts:
            return parts

    # Cloud SQL — the in_brief column gates per-surface inclusion.
    try:
        from gcp.fetchers._watchlist import load_watchlist
        wl = load_watchlist(surface='brief')
        if wl:
            logger.info(
                "brief tickers resolved from Cloud SQL watchlists "
                "(in_brief=TRUE): %s", wl,
            )
            return wl
    except Exception as exc:
        logger.warning("brief watchlist load failed (%s); using config default", exc)

    return default_tickers


def generate_premarket_brief(cfg=None, data_dir: str = None) -> dict:
    """Generate pre-market brief for all tickers.

    Returns a dict with per-ticker analysis and economic events.

    Honours BRIEF_AS_OF (historical replay) and BRIEF_TICKERS (override
    the config ticker list) — used by the Discord /replay command and
    ad-hoc backfills.
    """
    if cfg is None:
        cfg = load_config()

    data_dir = data_dir or cfg.market.data_dir
    tickers = _resolve_brief_tickers(cfg.market.tickers)
    signal_threshold = cfg.signal.premarket_signal_threshold
    building_threshold = cfg.signal.premarket_building_threshold

    analysis_date = _resolve_analysis_date()

    loader = DataLoader(data_dir=data_dir)
    strat = StratClassifier(strat_config=cfg.strat)
    brief = {
        'date': analysis_date.strftime('%a %b %d, %Y'),
        'analysis_date': analysis_date,
        'tickers': {},
    }

    for ticker in tickers:
        df = loader.load_daily(ticker)
        if df.empty or len(df) < 2:
            brief['tickers'][ticker] = {'status': 'NO DATA'}
            continue

        # Honour BRIEF_AS_OF — historical replays must NOT see bars after
        # analysis_date or the strat classifier / level builder will read
        # future data via df.iloc[-1] / df.iloc[-2]. The brief on a real
        # morning runs at 8:30 AM ET when today's daily row doesn't exist
        # yet, so the natural "yesterday" cutoff is `< analysis_date`
        # (strict less-than). On replay, we apply the same filter so
        # df.iloc[-1] is the last trading day BEFORE the replay date —
        # matching the data the brief would have seen at run time.
        cutoff = pd.Timestamp(analysis_date)
        if isinstance(df.index, pd.DatetimeIndex):
            idx = df.index.tz_localize(None) if df.index.tz is not None else df.index
            df = df.loc[idx < cutoff]
            if df.empty or len(df) < 2:
                brief['tickers'][ticker] = {'status': 'NO DATA'}
                continue

        close_col = 'Close' if 'Close' in df.columns else 'Last'

        # Defensive: drop rows with null close. Some upstream fetchers
        # have inserted placeholder rows with NULL OHLCV (data_source
        # NULL, observed 2026-04-30 — 43 tickers got a 4/29 NULL row
        # at 06:44 EDT). Without this filter df.iloc[-1] picks the
        # null row and curr_close=None propagates to build_level_map,
        # which crashes in compute_current_levels at
        # `max(float(today['_high']), current_price)`.
        before_n = len(df)
        df = df[df[close_col].notna()]
        dropped = before_n - len(df)
        if dropped:
            logger.warning(
                "[brief:%s] dropped %d row(s) with null close "
                "(stale placeholder); falling back to last valid row",
                ticker, dropped,
            )
            # Opportunistic cleanup so future runs don't re-encounter
            # these rows. Fire-and-forget — failure here is non-fatal.
            _delete_null_close_rows(ticker)
        if df.empty or len(df) < 2:
            brief['tickers'][ticker] = {'status': 'NO DATA (all rows null)'}
            continue

        df = add_all_indicators(df, close_col=close_col)

        latest = df.iloc[-1]       # yesterday (most recent trading day)
        prior = df.iloc[-2]        # day before yesterday
        rsi = latest.get(cfg.indicator.rsi_col, 50)

        # ── Previous day context ────────────────────────────────────────
        prev_close = _safe_float(prior.get(close_col))
        curr_close = _safe_float(latest.get(close_col))
        change_pct = None
        if prev_close and curr_close and prev_close > 0:
            change_pct = (curr_close - prev_close) / prev_close * 100

        # Volume vs 20-day average
        vol_sma20 = _safe_float(df['Volume'].rolling(20).mean().iloc[-1])
        latest_vol = _safe_float(latest.get('Volume'))
        rvol = (latest_vol / vol_sma20) if (vol_sma20 and vol_sma20 > 0) else None

        # ── Key levels ──────────────────────────────────────────────────
        sma200 = _safe_float(latest.get('SMA200'))
        ema9 = _safe_float(latest.get('EMA9'))
        ema20 = _safe_float(latest.get('EMA20'))
        bb_upper = _safe_float(latest.get('BB_Upper'))
        bb_lower = _safe_float(latest.get('BB_Lower'))
        atr14 = _safe_float(latest.get('ATR14'))
        macd = _safe_float(latest.get('MACD'))
        macd_sig = _safe_float(latest.get('MACD_Signal'))
        stoch_k = _safe_float(latest.get('StochRSI_K'))
        stoch_d = _safe_float(latest.get('StochRSI_D'))
        vol_20d = _safe_float(latest.get('volatility_20d'))

        above_sma200 = (curr_close > sma200) if (curr_close and sma200) else None

        # ── Strat / FTFC ────────────────────────────────────────────────
        # Single source of truth: lib.strat.compute_strat_status is the
        # same helper the LLM analyst calls (lib/agents/summarizers.py),
        # so the brief and the AI report agree on candle / combo / FTFC.
        # PR #101 renamed timeframe keys to match RESAMPLE_RULES (1d/1w/1mo).
        strat_status = compute_strat_status(
            ticker, df=df, timeframes=['1d', '1w', '1mo'], strat_config=cfg.strat,
        )
        if strat_status.get('available'):
            daily_strat = strat_status['last_candle']
            daily_combo = strat_status.get('in_force_combo')
            daily_setup = strat_status.get('strat_setup', False)
            ftfc_score = strat_status.get('ftfc_score', 0.0)
            ftfc_dir = strat_status.get('ftfc_direction', 'mixed')
            ftfc_labels = strat_status.get('ftfc_labels', {}) or {}
        else:
            daily_strat = '1'
            daily_combo = None
            daily_setup = False
            ftfc_score = 0.0
            ftfc_dir = 'mixed'
            ftfc_labels = {}

        # ── Signal conditions ───────────────────────────────────────────
        call_score, _ = check_call_conditions(latest)
        put_score, _ = check_put_conditions(latest)

        if call_score >= signal_threshold:
            signal_status = f'CALL setup ({call_score}/5)'
        elif put_score >= signal_threshold:
            signal_status = f'PUT setup ({put_score}/5)'
        elif call_score >= building_threshold:
            signal_status = f'CALL building ({call_score}/5)'
        elif put_score >= building_threshold:
            signal_status = f'PUT building ({put_score}/5)'
        else:
            signal_status = 'No signal'

        consec_up = int(latest.get('Consecutive_Up', 0))
        consec_down = int(latest.get('Consecutive_Down', 0))

        brief['tickers'][ticker] = {
            # Price & change
            'price': curr_close,
            'change_pct': change_pct,
            'prev_day_high': _safe_float(latest.get('High')),
            'prev_day_low': _safe_float(latest.get('Low')),
            'prev_day_open': _safe_float(latest.get('Open')),
            'prev_day_close': curr_close,
            'prev_day_volume': latest_vol,
            'rvol': rvol,
            # Indicators
            'rsi': _safe_float(rsi),
            'rsi_direction': 'down' if (rsi and rsi < 50) else 'up',
            'stoch_k': stoch_k,
            'stoch_d': stoch_d,
            'macd': macd,
            'macd_signal_val': macd_sig,
            'macd_cross': _macd_cross(macd, macd_sig),
            # Key levels
            'sma200': sma200,
            'ema9': ema9,
            'ema20': ema20,
            'bb_upper': bb_upper,
            'bb_lower': bb_lower,
            'atr14': atr14,
            'above_sma200': above_sma200,
            'vol_regime': _vol_regime(vol_20d),
            'volatility_20d': vol_20d,
            # Signal / strat
            'consecutive_up': consec_up,
            'consecutive_down': consec_down,
            'signal_status': signal_status,
            'strat_candle': daily_strat,
            'strat_combo': daily_combo,
            'strat_setup': bool(daily_setup),
            'ftfc_score': float(ftfc_score),
            'ftfc_direction': ftfc_dir,
            'ftfc_labels': {k: v for k, v in ftfc_labels.items()},
        }

    # Earnings: weekday → today's; Sunday → upcoming week's. Cap aligned
    # with the daily fetch job so the brief surfaces the same names that
    # actually have intraday bars in Cloud SQL. Uses the resolved
    # analysis_date (honours BRIEF_AS_OF) so historical replays show
    # the earnings calendar as it was on that date.
    today = analysis_date
    is_sunday = today.weekday() == 6
    brief_top_n = int(os.environ.get('BRIEF_MAX_EARNINGS', '25'))
    brief['earnings'] = load_earnings_for_brief(today, weekly=is_sunday, top_n=brief_top_n)

    # Yesterday's AMC reporters with today's pre-market gap (PR 3).
    # Skipped on Sundays — the weekly view is forward-looking, no
    # yesterday-AMC angle. Disable via BRIEF_AMC_REACTIONS=0.
    if not is_sunday and os.environ.get('BRIEF_AMC_REACTIONS', '1') != '0':
        try:
            top_amc = int(os.environ.get('BRIEF_AMC_REACTIONS_TOP', '5'))
            brief['earnings']['yesterday_amc_reactions'] = load_yesterday_amc_reactions(
                today, top_n=top_amc)
        except Exception as e:
            logger.warning("yesterday-AMC-reactions load failed: %s", e)

    # Economic events: Sunday brief needs a full week lookahead, weekday needs ~5 days
    brief['events'] = load_economic_events(today, days_ahead=7 if is_sunday else 5)

    # Catalyst-aware ORB window — applies to every ticker in this brief.
    orb_choice = select_orb_window(brief['events'].get('today', []))
    brief['recommended_orb_window'] = orb_choice['window']
    brief['recommended_orb_reason'] = orb_choice['reason']

    # Per-ticker level map + playbook string. Skip silently for NO DATA tickers.
    #
    # Diagnostic: writes to stderr (unbuffered) so every step is captured
    # in Cloud Logging regardless of stdout buffering. After the loop is
    # known-good these can be reduced to a single per-ticker info log.
    print(f"[brief] entering playbook loop with {len(brief.get('tickers', {}))} tickers: "
          f"{list(brief.get('tickers', {}).keys())}",
          file=sys.stderr, flush=True)
    for ticker, d in brief.get('tickers', {}).items():
        print(f"[brief:{ticker}] status={d.get('status')} price={d.get('price')}",
              file=sys.stderr, flush=True)
        if d.get('status') == 'NO DATA':
            print(f"[brief:{ticker}] skip (NO DATA)", file=sys.stderr, flush=True)
            continue
        try:
            df = loader.load_daily(ticker)
            print(f"[brief:{ticker}] load_daily → {len(df)} rows", file=sys.stderr, flush=True)
            if df.empty:
                continue
            # Same as_of cutoff applied above for the strat block — keep
            # the level map honest on historical replays so PDH/PDL/PWH
            # / etc. don't silently leak future bars (e.g. ARM 4/20
            # replay reading 2026-04-24's high as PDH).
            cutoff = pd.Timestamp(analysis_date)
            if isinstance(df.index, pd.DatetimeIndex):
                idx = df.index.tz_localize(None) if df.index.tz is not None else df.index
                df = df.loc[idx < cutoff]
                if df.empty or len(df) < 2:
                    print(f"[brief:{ticker}] insufficient bars before {analysis_date}",
                          file=sys.stderr, flush=True)
                    continue
            close_col = 'Close' if 'Close' in df.columns else 'Last'
            from lib.indicators import calculate_historical_levels
            ts = df['Time'] if 'Time' in df.columns else pd.Series(df.index)
            levels_df = calculate_historical_levels(
                ts, df['High'], df['Low'], df['Open'], df[close_col],
            )
            for col in levels_df.columns:
                df[col] = levels_df[col].values
            # Pass atr_14 from the latest daily row so build_level_map
            # can apply the ATR + % staleness filter (drops year-old
            # crash lows like ASTX 2026-04-28 PYL=15.03 from PUT
            # trigger selection). When atr_14 is missing/NaN the filter
            # falls back to the percent-only axis.
            atr_for_filter = float(d.get('atr14') or 0.0) or None
            print(f"[brief:{ticker}] calling build_level_map "
                  f"(current_price={d.get('price')}, atr={atr_for_filter})",
                  file=sys.stderr, flush=True)
            level_map = build_level_map(
                ticker=ticker, daily_df=df, current_price=d['price'],
                atr=atr_for_filter,
            )
            print(f"[brief:{ticker}] build_level_map → {len(level_map.levels)} levels"
                  f" (calls_trigger={'yes' if level_map.calls_trigger else 'NO (filtered)'}, "
                  f"puts_trigger={'yes' if level_map.puts_trigger else 'NO (filtered)'})",
                  file=sys.stderr, flush=True)

            # Compute the gap regime so the playbook can flag orb_only /
            # extended setups instead of publishing a stale level-break
            # plan. Same algorithm the 9:15 AM insight pipeline uses
            # (lib.agents.trade_planner.select_trigger_and_regime).
            #
            # We evaluate BOTH directions (long AND short) — previously
            # only the bias direction was checked, which meant a
            # bullish-bias ticker's bias-denial PUT setup never got
            # filtered. The bias direction is treated as the "primary"
            # regime that drives the playbook formatter; the
            # opposite-side regime is logged and used downstream for
            # per-side banners (so a denied PUT on a bullish ticker can
            # still be flagged as 'extended' / 'orb_only').
            regime_long = regime_short = 'normal'
            regime_compute_error = None
            try:
                from lib.agents.trade_planner import (
                    PlanContext, select_trigger_and_regime,
                )
                level_dict = levels_to_named_dict(level_map)
                ftfc_dir = (d.get('ftfc_direction') or '').lower()
                latest_row = df.iloc[-1]
                pre_high_v = latest_row.get('pre_high')
                pre_low_v = latest_row.get('pre_low')
                pre_vwap_v = latest_row.get('pre_vwap')
                gap_pct_v = latest_row.get('gap_pct')

                def _ctx(direction: str) -> PlanContext:
                    return PlanContext(
                        direction=direction,
                        conviction='medium',
                        close=float(d['price']),
                        atr=float(d.get('atr14') or 0.0),
                        trigger_high=level_dict.get('PDH'),
                        trigger_low=level_dict.get('PDL'),
                        pwh=level_dict.get('PWH'), pwl=level_dict.get('PWL'),
                        pmh=level_dict.get('PMH'), pml=level_dict.get('PML'),
                        pqh=level_dict.get('PQH'), pql=level_dict.get('PQL'),
                        pyh=level_dict.get('PYH'), pyl=level_dict.get('PYL'),
                        effective_pdh=level_dict.get('PDH'),
                        effective_pdl=level_dict.get('PDL'),
                        pre_high=float(pre_high_v) if pd.notna(pre_high_v) else None,
                        pre_low=float(pre_low_v) if pd.notna(pre_low_v) else None,
                        pre_vwap=float(pre_vwap_v) if pd.notna(pre_vwap_v) else None,
                        gap_pct=float(gap_pct_v) if pd.notna(gap_pct_v) else None,
                    )

                regime_long, _, _, _ = select_trigger_and_regime(_ctx('long'), 'long')
                regime_short, _, _, _ = select_trigger_and_regime(_ctx('short'), 'short')
                # Bias direction = primary regime for legacy callers.
                regime = regime_short if 'bear' in ftfc_dir else regime_long
                d['regime'] = regime
                d['regime_long'] = regime_long
                d['regime_short'] = regime_short
                print(f"[brief:{ticker}] regime_long={regime_long} "
                      f"regime_short={regime_short} primary={regime}",
                      file=sys.stderr, flush=True)
            except Exception as exc:
                # Regime compute is best-effort. Fall back to 'normal'
                # so the playbook still renders. Surface the error in
                # the brief so silent failures don't mask real bugs.
                regime = 'normal'
                regime_compute_error = f"{type(exc).__name__}: {exc}"
                print(f"[brief:{ticker}] regime compute failed: "
                      f"{regime_compute_error}",
                      file=sys.stderr, flush=True)
                d['regime'] = 'normal'
                d['regime_long'] = 'normal'
                d['regime_short'] = 'normal'
                d['regime_compute_error'] = regime_compute_error

            d['playbook'] = format_levels_for_brief(
                level_map=level_map, bias=d.get('ftfc_direction', 'mixed'),
                combo=d.get('strat_combo'), daily_strat_class=d.get('strat_candle'),
                regime=regime,
                regime_long=d.get('regime_long'),
                regime_short=d.get('regime_short'),
                regime_compute_error=d.get('regime_compute_error'),
                atr=atr_for_filter,
            )
            d['recommended_orb_window'] = orb_choice['window']
            d['recommended_orb_reason'] = orb_choice['reason']

            # Persist level map to Cloud SQL so the realtime signal_monitor
            # (which doesn't itself recompute) can query it for level-break
            # detection during market hours.
            try:
                from gcp.database import get_engine
                from lib.strat_levels import persist_level_map
                engine = get_engine()
                with engine.connect() as conn:
                    n = persist_level_map(level_map, conn.connection)
                    conn.connection.commit()
                print(f"[brief:{ticker}] persisted {n} strat_levels rows",
                      file=sys.stderr, flush=True)
            except Exception as exc:
                import traceback
                print(f"[brief:{ticker}] strat_levels persist FAILED: {type(exc).__name__}: {exc}",
                      file=sys.stderr, flush=True)
                traceback.print_exc(file=sys.stderr)
                sys.stderr.flush()
        except Exception as e:
            import traceback
            print(f"[brief:{ticker}] playbook block FAILED: {type(e).__name__}: {e}",
                  file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
            # Mark the ticker as PLAYBOOK_FAILED so persist_to_cloud_sql
            # writes the row to premarket_analysis_history (audit trail)
            # but skips the canonical premarket_analysis row. Without
            # this flag the partial row would land in the canonical
            # table with NULL playbook on a fresh-day failure.
            d['status'] = 'PLAYBOOK_FAILED'
            d['playbook_error'] = f"{type(e).__name__}: {e}"

    # 🧠 LLM explanations — populate `llm_overview`, `llm_orb_explanation`,
    # and per-ticker `llm_analysis` / `llm_playbook` slots in parallel.
    # Best-effort: any failure leaves the slot blank and the embed
    # builders silently skip the field. Set BRIEF_LLM_DISABLE=1 to
    # bypass entirely (emergency mornings / cost debugging).
    try:
        import asyncio
        from gcp.brief_explanations import generate_explanations
        asyncio.run(generate_explanations(brief))
        print(f"[brief] LLM explanations populated", file=sys.stderr, flush=True)
    except Exception as exc:
        print(f"[brief] LLM explanations FAILED: {type(exc).__name__}: {exc}",
              file=sys.stderr, flush=True)

    return brief


# ── Discord Formatting (3 embeds) ───────────────────────────────────────────

def _fmt_price(val):
    return f'${val:,.2f}' if val is not None else 'N/A'


def _fmt_pct(val):
    return f'{val:+.2f}%' if val is not None else ''


def _truncate(s: str, limit: int) -> str:
    """Trim to a Discord-safe length, appending an ellipsis when cut."""
    if not s:
        return ''
    s = str(s)
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)].rstrip() + '…'


def _fmt_combo(combo: str) -> str:
    """Render a Strat combo identifier in human-readable form.

    Storage form is snake_case (e.g. ``322_bull_continuation``,
    ``failed_2u_bear_reversal``, ``clean_2u_bull``) — that's the
    canonical key the codebase uses across DB rows, signals, the
    LLM bundle, and journal entries. The render layer (this brief
    embed) converts to title-case for trader readability:

      ``322_bull_continuation``     → ``322 Bull Continuation``
      ``failed_2u_bear_reversal``   → ``Failed 2U Bear Reversal``
      ``clean_2u_bull``             → ``Clean 2U Bull``

    Numeric prefixes (``322``, ``212``) and the ``2U``/``2D`` candle
    tokens stay as-is because they're recognised lingo. Everything
    else gets ``capitalize()``-d.
    """
    if not combo or combo == 'none':
        return ''
    out = []
    for part in combo.split('_'):
        if part.upper() in ('2U', '2D'):
            out.append(part.upper())
        elif part.isdigit():
            out.append(part)
        else:
            out.append(part.capitalize())
    return ' '.join(out)


def _fmt_timeframe(tf: str) -> str:
    """Render a timeframe key in canonical uppercase short form.

    The codebase uses the lib/data_loader.RESAMPLE_RULES keys
    (``1d``, ``1w``, ``1mo``, ``4h``…) for storage and FTFC math.
    Discord readers prefer ``1D`` / ``1W`` / ``1M`` / ``4H`` — looks
    cleaner alongside ticker symbols which are also uppercase.

    ``1mo`` collapses to ``1M`` (not ``1MO``) — 'M' is unambiguous in
    a trading context.
    """
    if not tf:
        return tf
    if tf.lower() == '1mo':
        return '1M'
    return tf.upper()


def _stoch_regime_tag(stoch_k, stoch_d) -> str:
    """Translate the larger of K and D into the standard 0-100 regime tag.

    StochRSI is RSI applied to RSI itself — measures where current
    RSI sits within its recent range. The two lines (K and D) almost
    always agree on which band they're in, so we tag based on the
    larger value (the more extreme reading) which is the one a
    trader would react to. Bands follow the common 20/80 thresholds:

      * ``oversold``    — both lines ≤ 20 (RSI is at the LOW end of
                          its lookback range; mean-reversion up
                          favoured short-term)
      * ``overbought``  — either line ≥ 80 (RSI at the HIGH end;
                          mean-reversion down favoured)
      * ``neutral``     — anywhere between (no momentum-exhaustion
                          signal either way)

    The IWM 100/99 reading from the 2026-04-28 brief is the
    canonical "fully pegged at the top" overbought call this tag
    surfaces — combined with regular RSI 73, it argues for a
    pullback to EMA9 / BB mid-band rather than further breakout.
    """
    if stoch_k is None or stoch_d is None:
        return ''
    try:
        hi = max(float(stoch_k), float(stoch_d))
        lo = min(float(stoch_k), float(stoch_d))
    except (TypeError, ValueError):
        return ''
    if hi >= 80:
        return 'overbought'
    if lo <= 20:
        return 'oversold'
    return 'neutral'


def _build_overview_embed(brief: dict) -> dict:
    """Embed 1: Market overview — previous day recap + regime context."""
    lines = []
    for ticker, d in brief.get('tickers', {}).items():
        if d.get('status') == 'NO DATA':
            lines.append(f'**{ticker}** — No data')
            continue

        chg = _fmt_pct(d.get('change_pct'))
        rsi_arrow = '\u2193' if d.get('rsi_direction') == 'down' else '\u2191'
        sma_pos = ''
        if d.get('above_sma200') is not None:
            sma_pos = 'Above' if d['above_sma200'] else 'Below'
            sma_pos = f' | {sma_pos} SMA200'

        rvol_str = f' | RVOL {d["rvol"]:.1f}x' if d.get('rvol') else ''
        vol_str = f' | Vol: {d["vol_regime"]}' if d.get('vol_regime') != 'N/A' else ''

        lines.append(
            f'**{ticker}** {_fmt_price(d["price"])} ({chg})'
            f' | RSI {d["rsi"]:.0f}{rsi_arrow}'
            f'{sma_pos}{rvol_str}{vol_str}'
        )

    # FTFC summary line
    ftfc_parts = []
    for ticker, d in brief.get('tickers', {}).items():
        if d.get('status') == 'NO DATA':
            continue
        ftfc_parts.append(f'{ticker}: {d["ftfc_direction"]} ({d["ftfc_score"]:+.1f})')
    if ftfc_parts:
        lines.append('')
        lines.append('**FTFC:** ' + ' | '.join(ftfc_parts))

    # \ud83e\udde0 LLM "Today's setup" explanation (PR \u03b2 fills brief['llm_overview'];
    # PR \u03b1 reserves the slot). Renders as a description-suffix paragraph
    # so it sits naturally below the FTFC line without adding a field.
    overview_text = brief.get('llm_overview')
    if overview_text:
        lines.append('')
        lines.append('\U0001F9E0 **Today\'s setup:** ' + str(overview_text))

    # Determine overall color
    bullish_count = sum(
        1 for d in brief.get('tickers', {}).values()
        if d.get('ftfc_direction') == 'bullish'
    )
    total = sum(1 for d in brief.get('tickers', {}).values() if d.get('status') != 'NO DATA')
    if bullish_count > total / 2:
        color = 0x2ecc71  # green
    elif bullish_count < total / 2:
        color = 0xe74c3c  # red
    else:
        color = 0x3498db  # blue

    return {
        'title': f'PRE-MARKET BRIEF \u2014 {brief["date"]}',
        'description': '\n'.join(lines),
        'color': color,
    }


def _build_ticker_fields(brief: dict) -> list:
    """Build per-ticker analysis fields (3 inline columns + 1 full-width
    LLM explanation per ticker).

    Field-pair splits land paired values on their own lines for mobile
    readability \u2014 ``Prev H/L`` becomes ``Prev H`` + ``Prev L``,
    ``EMA 9/20`` becomes ``EMA9`` + ``EMA20``, the inline
    ``RSI | StochRSI`` mash-up becomes two separate lines.

    The 4th field per ticker (``inline: False``) is reserved for the
    LLM-generated analysis. PR \u03b2 fills it from
    ``brief['tickers'][ticker]['llm_analysis']``; if that's empty
    (LLM disabled, timed out, or errored) the field is skipped so the
    embed doesn't render an empty box.
    """
    fields = []
    for ticker, d in brief.get('tickers', {}).items():
        if d.get('status') == 'NO DATA':
            fields.append({'name': f'{ticker}', 'value': 'No data', 'inline': False})
            continue

        # Field 1: Key Levels (split paired values onto their own lines)
        level_lines = []
        if d.get('prev_day_high'):
            level_lines.append(f'Prev H: {_fmt_price(d["prev_day_high"])}')
        if d.get('prev_day_low'):
            level_lines.append(f'Prev L: {_fmt_price(d["prev_day_low"])}')
        if d.get('sma200'):
            level_lines.append(f'SMA200: {_fmt_price(d["sma200"])}')
        if d.get('bb_upper') and d.get('bb_lower'):
            level_lines.append(f'BB: {_fmt_price(d["bb_upper"])} / {_fmt_price(d["bb_lower"])}')
        if d.get('ema9'):
            level_lines.append(f'EMA9: {_fmt_price(d["ema9"])}')
        if d.get('ema20'):
            level_lines.append(f'EMA20: {_fmt_price(d["ema20"])}')
        if d.get('atr14'):
            level_lines.append(f'ATR14: {_fmt_price(d["atr14"])}')

        fields.append({
            'name': f'{ticker} Levels',
            'value': '\n'.join(level_lines) or 'N/A',
            'inline': True,
        })

        # Field 2: Momentum (RSI and StochRSI on separate lines)
        rsi_arrow = '\u2193' if d.get('rsi_direction') == 'down' else '\u2191'
        mom_lines = [f'RSI: {d["rsi"]:.0f} {rsi_arrow}']
        if d.get('stoch_k') is not None:
            tag = _stoch_regime_tag(d['stoch_k'], d['stoch_d'])
            tag_suffix = f' ({tag})' if tag else ''
            mom_lines.append(
                f'StochRSI: {d["stoch_k"]:.0f}/{d["stoch_d"]:.0f}{tag_suffix}'
            )
        mom_lines.append(f'MACD: {d.get("macd_cross", "N/A")}')

        consec = ''
        if d['consecutive_down'] >= 2:
            consec = f'{d["consecutive_down"]} consecutive down'
        elif d['consecutive_up'] >= 2:
            consec = f'{d["consecutive_up"]} consecutive up'
        if consec:
            mom_lines.append(consec)
        mom_lines.append(d['signal_status'])

        fields.append({
            'name': f'{ticker} Momentum',
            'value': '\n'.join(mom_lines),
            'inline': True,
        })

        # Field 3: Strat / FTFC
        # Combo names are stored snake_case in the DB / LLM bundle
        # (`322_bull_continuation`) but rendered title-case here for
        # readability (`322 Bull Continuation`). Timeframe keys use
        # the `lib/data_loader.RESAMPLE_RULES` lowercase form for
        # storage (`1d`, `1w`, `1mo`) but render uppercase here
        # (`1D`, `1W`, `1M`) so they read like ticker symbols.
        # Daily / Combo land on their own lines (rather than the
        # previous `Daily: 2U | Combo: ...` mash-up) — the long
        # title-cased combo names overflowed visually when piped onto
        # the Daily line on mobile.
        strat_lines = [f'Daily: {d["strat_candle"]}']
        if d['strat_combo'] != 'none':
            strat_lines.append(f'Combo: {_fmt_combo(d["strat_combo"])}')
        strat_lines.append(
            f'FTFC: {d["ftfc_score"]:+.1f} ({d["ftfc_direction"]})'
        )
        tf_parts = ' '.join(
            f'{_fmt_timeframe(k)}:{v}'
            for k, v in d.get('ftfc_labels', {}).items()
        )
        if tf_parts:
            strat_lines.append(tf_parts)
        if d['strat_setup']:
            strat_lines.append('**SETUP FORMING**')

        fields.append({
            'name': f'{ticker} Strat',
            'value': '\n'.join(strat_lines),
            'inline': True,
        })

        # Field 4: \ud83e\udde0 Analysis (full-width, fills the gap that previously
        # appeared from column-height misalignment). Skipped when no
        # LLM text is available so the embed doesn't render an empty box.
        analysis = d.get('llm_analysis')
        if analysis:
            fields.append({
                'name': f'\U0001F9E0 {ticker} Analysis',
                'value': _truncate(str(analysis), MAX_FIELD_VALUE),
                'inline': False,
            })

    return fields


def _playability_lines(bucket: list[dict], top_n: int = 5) -> list[str]:
    """Build the indented 'Playability — top N' sub-section for a bucket.

    Returns a list of lines (no leading newline; caller joins with \\n).
    Returns [] when no row in the bucket has a playability_score — the
    section is hidden in that case rather than showing 'no data'.
    """
    playable = [r for r in bucket if r.get('playability_score') is not None]
    if not playable:
        return []
    playable = sorted(playable, key=lambda r: -r['playability_score'])[:top_n]

    try:
        from lib.earnings_reactions import action_hint_for_archetype
    except ImportError:
        def action_hint_for_archetype(_a):
            return ''

    LOOKBACK_TARGET = 12  # matches enrich_with_playability default
    lines = [f'  🎯 _Playability — top {len(playable)} ({LOOKBACK_TARGET}Q profile)_']
    for i, r in enumerate(playable, 1):
        score = r.get('playability_score') or 0
        arch = r.get('playability_archetype') or 'quiet'
        mag = r.get('playability_move_mag_pct') or 0
        cons = (r.get('playability_dir_consistency') or 0) * 100
        rev = (r.get('playability_reversal_rate') or 0) * 100
        nq = r.get('playability_n_q', 0)
        hint = action_hint_for_archetype(arch)
        # Show n=X only when the ticker has fewer than LOOKBACK_TARGET
        # quarters (insufficient daily bars for some reports). When n
        # matches the target, the section header already conveys it.
        n_suffix = '' if nq >= LOOKBACK_TARGET else f' _(n={nq})_'
        lines.append(
            f'  {i}. **{r["ticker"]}** '
            f'`{score:.0f}` {arch} | '
            f'gap {mag:.1f}% · cons {cons:.0f}% · rev {rev:.0f}% '
            f'· {hint}{n_suffix}'
        )
    return lines


def _build_earnings_embed(earnings_data: dict) -> dict:
    """Embed 4: Earnings calendar — today (weekday) or week ahead (Sunday).

    Daily mode partitions rows into Before Open / After Close / Intraday
    sections so traders can scan the timing-relevant bucket at a glance.
    Each section caps independently so a busy AMC day doesn't crowd out
    BMO names.

    Pre-market gap_pct (from the LEFT-joined market_data_daily) renders
    next to rows as \U0001f4c8 +X.X% / \U0001f4c9 -X.X% — the announcement
    reaction in pre-session for names that already reported.

    Truncates to stay under Discord's 4096-char description limit.
    """
    mode = earnings_data.get('mode', 'daily')
    rows = earnings_data.get('earnings', [])

    if not rows:
        return {
            'title': 'Earnings (Today)' if mode == 'daily' else 'Earnings (Week Ahead)',
            'description': 'No earnings scheduled',
            'color': 0x7f8c8d,
        }

    time_icon = {
        'premarket': '\u2600\ufe0f',
        'postmarket': '\U0001f319',
        'intraday': '\U0001f552',
    }

    def _valid_num(v):
        if v is None:
            return None
        try:
            f = float(v)
            return None if (f != f) else f  # NaN check (NaN != NaN)
        except (ValueError, TypeError):
            return None

    def _ew_verdict_str(r):
        """Render EW strike verdict from prior eval — e.g.
        'EW LC $30 HIT +18.7% in 5m, held 142m, day +1.2%'.

        Only fires when ew_strike_verdict is populated (post-eval).
        Strategy is abbreviated:
            LC=Long Calls  LP=Long Puts  CC=Covered Calls
            BS=Bull Spreads  BR=Bear Spreads
        """
        verdict = r.get('ew_strike_verdict')
        if not verdict:
            return ''
        strat = r.get('strategy') or ''
        abbrev = {
            'Long Calls': 'LC', 'Long Puts': 'LP',
            'Covered Calls': 'CC',
            'Bull Spreads': 'BS', 'Bear Spreads': 'BR',
        }.get(strat, strat[:6] if strat else '')
        strike = _valid_num(r.get('strike'))
        move = _valid_num(r.get('ew_strike_move_pct'))
        ttl = r.get('ew_minutes_to_hit')
        iz = r.get('ew_minutes_in_zone')
        day = _valid_num(r.get('ew_day_change_pct'))

        head_parts = ['EW']
        if abbrev: head_parts.append(abbrev)
        if strike is not None: head_parts.append(f'${strike:.0f}')
        head_parts.append(verdict)  # HIT / MISS / KEPT / ASSIGNED
        if move is not None:
            head_parts.append(f'{move:+.1f}%')
        head = ' '.join(head_parts)

        tail_parts = []
        if ttl is not None and verdict in ('HIT', 'ASSIGNED'):
            tail_parts.append(f'in {int(ttl)}m')
        if iz is not None:
            tail_parts.append(f'held {int(iz)}m')
        if day is not None:
            tail_parts.append(f'day {day:+.1f}%')
        return head + (', ' + ', '.join(tail_parts) if tail_parts else '')

    def _gap_str(gap):
        """Render gap_pct as up/down arrow + signed pct, or '' when no signal.

        \xb10.05% threshold so pure rounding noise doesn't clutter the line;
        real announcement reactions are typically \xb12-10% on earnings names.
        """
        g = _valid_num(gap)
        if g is None or abs(g) < 0.05:
            return ''
        if g > 0:
            return f'\U0001f4c8 +{g:.1f}%'
        return f'\U0001f4c9 {g:.1f}%'

    def _beat_miss_str(estimate, actual, surprise_pct):
        """Render expectation delta — verdict + percent FIRST, then the
        EPS detail. The leading verdict marker keeps the row scannable:
        the eye sees '✅ +6.8% EPS 3.10→3.31' and gets the read in
        the first two tokens, with the supporting numbers trailing.

        Returns '' when the company hasn't reported yet (actual is None).
        Threshold |surprise| < 1% labels as 'inline' (hit) since EPS
        rounds to 2 decimals and a 0.5% miss is typically a non-event.
        """
        e = _valid_num(estimate)
        a = _valid_num(actual)
        if a is None:
            return ''
        s = _valid_num(surprise_pct)
        # If Yahoo didn't supply surprise, derive it (avoid div-by-zero)
        if s is None and e is not None and abs(e) > 1e-6:
            s = (a - e) / abs(e) * 100.0
        # Verdict marker — ✅ beat, ❌ miss, \U0001f3af inline
        if s is None:
            verdict = ''
        elif s >= 1.0:
            verdict = '✅'   # beat
        elif s <= -1.0:
            verdict = '❌'   # miss
        else:
            verdict = '\U0001f3af'  # bullseye/inline
        if e is not None:
            eps_part = f'EPS {e:.2f}→{a:.2f}'
        else:
            eps_part = f'EPS act {a:.2f}'
        if s is not None and verdict:
            return f'{verdict} {s:+.1f}% {eps_part}'
        # No surprise pct (e.g. estimate missing & Yahoo didn't supply) —
        # render just the EPS detail, no leading verdict.
        return eps_part

    def _row_line(r, show_tier_badge: bool = True):
        ticker = r['ticker']
        # Tier badge: green dot for confirmed (tier 1-3), no badge for long tail.
        # Suppressed in the Reactions-to-Last-Night-AMC section because the
        # tier signal isn't useful there — those names already reported, so
        # the source-confirmation tier doesn't change how the gap is read.
        tier = r.get('tier', 6)
        if not show_tier_badge:
            badge = ''
        elif tier == 1:
            badge = '\U0001f7e2 '   # green circle: all 3 sources
        elif tier == 2:
            badge = '\U0001f535 '   # blue circle: AV + UW (top market-movers)
        elif tier == 3:
            badge = '\U0001f7e1 '   # yellow circle: AV + EW (strategy pick)
        else:
            badge = ''
        # Field order: EM \u2192 verdict \u2192 gap \u2192 strategy \u2192 strike.
        # EM first = "what range should I expect?" \u2014 the actionable
        # number for sizing & strike selection. Verdict next once known
        # (beat/miss replaces estimate), then gap (the actual reaction).
        # Strategy + strike last since they're recommendations, not
        # observed facts. EW's \u2605 score removed (too noisy, didn't help).
        # Strategy block (text + strike) goes at the end together \u2014 see
        # below where it's appended after the verdict + gap.
        extras = []
        em = _valid_num(r.get('expected_move'))
        if em is not None:
            extras.append(f'EM ${em:.2f}')
        if not extras:
            eps = _valid_num(r.get('eps_estimate'))
            if eps is not None:
                extras.append(f'EPS {eps:.2f}')
        if not extras and r.get('sector'):
            extras.append(str(r['sector'])[:20])
        # Beat/miss verdict — when actual EPS is known, this REPLACES the
        # generic 'EPS estimate' fallback because the actual+verdict is
        # strictly more informative.
        bm = _beat_miss_str(r.get('eps_estimate'),
                            r.get('eps_actual'),
                            r.get('eps_surprise_pct'))
        if bm:
            # Remove a plain 'EPS X.XX' fallback if we already added one;
            # the beat/miss form supersedes it.
            extras = [x for x in extras if not (
                isinstance(x, str) and x.startswith('EPS ') and '→' not in x
            )]
            extras.append(bm)
        # Pre-market gap reaction (where market_data_daily has data).
        gap_str = _gap_str(r.get('gap_pct'))
        if gap_str:
            extras.append(gap_str)
        # Strategy + strike + EW verdict deliberately NOT rendered here
        # — those move to the dedicated 🔮 Whispers section at the
        # bottom of the embed. Mixing strategy recommendations with the
        # earnings-event row was misleading: EW strategies can span
        # multiple days around the report and aren't always actionable
        # today. The Whispers section makes the recommendation context
        # explicit so traders don't read "Long Calls Strike $16" as
        # "buy this NOW".
        extra_str = f' — {" | ".join(extras)}' if extras else ''
        return f'{badge}**{ticker}**{extra_str}'

    def _whispers_row(r):
        """🔮 Whispers section row: strategy + strike + historical EW
        verdict. Lead dot reflects the verdict outcome (NOT the source
        tier — different signal in this section):
            🟢 = HIT (long calls/puts went above/below) or KEPT (CC held)
            🔴 = MISS (strike never crossed) or ASSIGNED (CC breached)
            (no dot) = verdict pending (today's pick, evaluator hasn't run)
        """
        ticker = r['ticker']
        verdict = r.get('ew_strike_verdict')
        if verdict in ('HIT', 'KEPT'):
            dot = '\U0001f7e2 '   # green
        elif verdict in ('MISS', 'ASSIGNED'):
            dot = '\U0001f534 '   # red
        else:
            dot = ''
        parts = []
        if r.get('strategy'):
            parts.append(r['strategy'])
        strike = _valid_num(r.get('strike'))
        if strike is not None:
            parts.append(f'Strike ${strike:.0f}')
        ew_v = _ew_verdict_str(r)
        if ew_v:
            parts.append(ew_v)
        extra = f' — {" | ".join(parts)}' if parts else ''
        return f'{dot}**{ticker}**{extra}'

    def _confirmed_count(day_rows):
        return sum(1 for r in day_rows if r.get('tier', 6) <= 3)

    if mode == 'weekly':
        from collections import OrderedDict
        by_date = OrderedDict()
        for r in rows:
            by_date.setdefault(r['date'], []).append(r)

        # In daily mode the loader filters to confirmed-only by default,
        # so 'X confirmed / Y total' collapses to just the count. Drop
        # the redundant denominator in headers + footers.
        sections = []
        total_chars = 0
        PER_DAY = 10          # show top 10 per day
        for d, day_rows in by_date.items():
            day_str = d.strftime('%a %m/%d') if hasattr(d, 'strftime') else str(d)
            header = f'\n**{day_str}** — {len(day_rows)}'
            lines = [header]
            for r in day_rows[:PER_DAY]:
                lines.append(_row_line(r))
            if len(day_rows) > PER_DAY:
                lines.append(f'_+{len(day_rows) - PER_DAY} more_')
            section = '\n'.join(lines)
            if total_chars + len(section) > 3800:
                sections.append('\n_... truncated_')
                break
            sections.append(section)
            total_chars += len(section)

        total = sum(len(v) for v in by_date.values())
        # Title shows the week range so the reader knows which week
        first = next(iter(by_date)) if by_date else None
        last = next(reversed(by_date)) if by_date else None
        if first and hasattr(first, 'strftime'):
            wk = f' — {first.strftime("%a %m/%d")} to {last.strftime("%a %m/%d")}'
        else:
            wk = ''
        title = f'Earnings Week Ahead{wk} — {total}'
        description = '\n'.join(sections).strip()
    else:
        # Daily mode: partition by time-of-day so traders scan the
        # relevant bucket directly. Each section caps independently —
        # a busy AMC day no longer crowds out BMO names. Loader has
        # already filtered to confirmed-only (BRIEF_INCLUDE_UNCONFIRMED
        # disabled), so headers show just the count.
        title_date = ''
        d = earnings_data.get('start') or (rows[0].get('date') if rows else None)
        if d and hasattr(d, 'strftime'):
            title_date = f' — {d.strftime("%a %m/%d")}'
        title = f'Earnings Today{title_date} — {len(rows)}'

        def _bucket(r):
            t = r.get('time')
            if t == 'premarket':  return 'bmo'
            if t == 'postmarket': return 'amc'
            return None  # intraday/unknown — dropped (mostly foreign tickers / TNS)

        buckets = {'bmo': [], 'amc': []}
        for r in rows:
            b = _bucket(r)
            if b is not None:
                buckets[b].append(r)

        # Section order is intentional — most-actionable first:
        #   1. ☀️ BMO — opens in minutes, immediate setup
        #   2. 📊 Yesterday-AMC reactions — overnight gappers tradeable today
        #   3. 🌙 AMC — reports later tonight, set up but not yet actionable
        # Per-section caps: BMO/AMC each 10. Intraday/unknown rows
        # are dropped (foreign listings / TNS placeholders).
        SECTION_CAP = {'bmo': 10, 'amc': 10}

        def _build_bucket_section(header, bucket, cap):
            if not bucket:
                return None
            kept = bucket[:cap]
            sec_lines = [f'\n**{header}** ({len(bucket)})']
            sec_lines.extend(_row_line(r) for r in kept)
            if len(bucket) > cap:
                sec_lines.append(f'_+{len(bucket) - cap} more_')
            sec_lines.extend(_playability_lines(bucket, top_n=5))
            return '\n'.join(sec_lines)

        sections = []

        # 1. BMO
        bmo = _build_bucket_section('☀️ Reporting Before Open',
                                     buckets['bmo'], SECTION_CAP['bmo'])
        if bmo:
            sections.append(bmo)

        # 2. Yesterday-AMC reactions — last night's AMC reporters with
        # today's pre-market gap. The actual market reaction to the news
        # that dropped 4-5 PM yesterday lives in today's pre-market gap.
        amc_reactions = earnings_data.get('yesterday_amc_reactions') or []
        if amc_reactions:
            r_lines = [
                f'\n**\U0001f4ca Reactions to Last Night’s AMC** '
                f'(top {len(amc_reactions)} by |gap|)'
            ]
            r_lines.extend(_row_line(r, show_tier_badge=False)
                           for r in amc_reactions)
            sections.append('\n'.join(r_lines))

        # 3. Tonight's AMC — reports after today's close
        amc = _build_bucket_section('\U0001f319 Reporting After Close',
                                     buckets['amc'], SECTION_CAP['amc'])
        if amc:
            sections.append(amc)

        # 4. Whispers — separated from the BMO/AMC rows so EW's strategy
        # picks (strike, structure, historical hit-rate) don't get read
        # as "today's actionable recommendation". An EW Long Call $16
        # might be a 3-day position around earnings, not a today-only
        # trigger. Putting it in its own section makes the context clear.
        whispers = [r for r in rows if r.get('strategy')]
        if whispers:
            w_lines = [f'\n**\U0001f52e Whispers** ({len(whispers)})']
            w_lines.extend(_whispers_row(r) for r in whispers)
            sections.append('\n'.join(w_lines))

        description = '\n'.join(sections).strip()

    return {
        'title': title,
        'description': description[:4090],
        'color': 0xf39c12,
    }


def _build_calendar_embed(events: dict, mode: str = 'daily') -> dict:
    """Embed 3: Economic calendar.

    In daily mode: today's events in description, rest-of-week in a field.
    In weekly mode (Sunday brief): week-ahead events grouped by day in
    the description (no "today" section since today is Sunday).
    """
    today_evts = events.get('today', [])
    week_evts = events.get('week', [])

    def _ev_line(ev, with_day=False):
        # Red = high impact, orange = medium (matches ForexFactory's folder colors)
        icon = '\U0001f534' if ev['importance'] == 'high' else '\U0001f7e0'
        time_str = ev['time'] or 'TBD'
        if with_day:
            d = ev['date']
            day_str = d.strftime('%a %m/%d') if hasattr(d, 'strftime') else str(d)
            prefix = f'{day_str} {time_str}'.strip()
        else:
            prefix = time_str
        line = f'{icon} **{prefix}** {ev["name"]}'
        # Surface forecast + previous (ForexFactory provides these).
        # Labels use Exp/Prev for clarity (vs FF's terse F/P).
        parts = []
        if ev.get('forecast'):
            parts.append(f'Exp={ev["forecast"]}')
        if ev.get('previous'):
            parts.append(f'Prev={ev["previous"]}')
        if parts:
            line += f' ({", ".join(parts)})'
        return line

    if mode == 'weekly':
        # Group week events by day
        if not week_evts and not today_evts:
            description = 'No major events this week'
        else:
            from collections import OrderedDict
            by_date = OrderedDict()
            for ev in week_evts:
                by_date.setdefault(ev['date'], []).append(ev)

            sections = []
            total_chars = 0
            for d, day_evts in by_date.items():
                day_str = d.strftime('%a %m/%d') if hasattr(d, 'strftime') else str(d)
                header = f'\n**{day_str}** ({len(day_evts)})'
                lines = [header]
                for ev in day_evts[:6]:
                    lines.append(_ev_line(ev, with_day=False))
                if len(day_evts) > 6:
                    lines.append(f'_+{len(day_evts) - 6} more_')
                section = '\n'.join(lines)
                if total_chars + len(section) > 3800:
                    sections.append('\n_... truncated_')
                    break
                sections.append(section)
                total_chars += len(section)
            description = '\n'.join(sections).strip()

        total = len(week_evts)
        return {
            'title': f'Economic Calendar — Week Ahead ({total})',
            'description': description,
            'color': 0x95a5a6,
        }

    # Daily mode
    if today_evts:
        today_text = '\n'.join(_ev_line(ev) for ev in today_evts[:8])
    else:
        today_text = 'No major events today'

    embed = {
        'title': 'Economic Calendar',
        'description': today_text,
        'color': 0x95a5a6,
    }

    # Week ahead compact field (up to 6 entries)
    if week_evts:
        week_lines = [_ev_line(ev, with_day=True) for ev in week_evts[:6]]
        embed['fields'] = [{
            'name': 'This Week',
            'value': '\n'.join(week_lines),
            'inline': False,
        }]

    return embed


def _build_playbook_embed(brief: dict) -> dict:
    """Embed: per-ticker Strat playbook with trigger, stop, T1/T2 + R:R.

    Each ticker gets one field with the multiline format produced by
    lib.strat_levels.format_levels_for_brief, optionally followed by a
    full-width LLM "Why this trigger" field. The catalyst-aware ORB
    recommendation goes in the description, with an optional LLM
    explanation ("which window was picked, what the alternatives are")
    appended underneath.
    """
    fields = []
    orb_window = brief.get('recommended_orb_window') or '5m'
    orb_reason = brief.get('recommended_orb_reason') or ''

    # 🧠 LLM playbook header — explains why this ORB window vs the 5/15/30
    # alternatives. PR β fills brief['llm_orb_explanation']; PR α
    # reserves the slot.
    description_parts = [orb_reason] if orb_reason else []
    orb_text = brief.get('llm_orb_explanation')
    if orb_text:
        description_parts.append('')
        description_parts.append('\U0001F9E0 ' + str(orb_text))
    description = '\n'.join(description_parts) if description_parts else ''

    for ticker, d in brief.get('tickers', {}).items():
        if not d.get('playbook'):
            continue
        value = d['playbook']
        if len(value) > MAX_FIELD_VALUE:
            value = value[:MAX_FIELD_VALUE - 3] + '...'
        fields.append({
            'name': f'{ticker} Playbook',
            'value': f'```\n{value}\n```',
            'inline': False,
        })

        # 🧠 Per-ticker playbook explanation — explains why this trigger /
        # what the trader should watch. Sits directly under the playbook
        # code-block so it reads as commentary on the levels above.
        playbook_text = d.get('llm_playbook')
        if playbook_text:
            fields.append({
                'name': f'\U0001F9E0 {ticker} — Why this trigger',
                'value': _truncate(str(playbook_text), MAX_FIELD_VALUE),
                'inline': False,
            })

    return {
        'title': f'Strat Playbook — {orb_window} ORB',
        'description': description,
        'fields': fields,
        'color': 0x9b59b6,
    }


def format_discord_messages(brief: dict) -> list[dict]:
    """Format brief as a LIST of Discord webhook payloads.

    Discord caps each webhook payload at 6000 chars across all embeds.
    Once the earnings embed gained BMO/AMC sections + tradeability
    ranking + options-flow filter (commit 80ebf9f3), the combined
    overview+tickers+playbook+earnings+calendar payload exceeds 6000
    on busy mornings — so the legacy single-message format silently
    dropped earnings and calendar.

    Split into two messages so each section has its own size budget:
      Message 1: overview + ticker_analysis + playbook  (analytics)
      Message 2: earnings + calendar                    (events)

    Per-message truncation still applies — if a single message would
    exceed 6000 chars on its own, lower-priority embeds drop within
    that message until it fits. The OTHER message is unaffected.
    """
    overview = _build_overview_embed(brief)
    ticker_fields = _build_ticker_fields(brief)
    mode = brief.get('earnings', {}).get('mode', 'daily')
    calendar = _build_calendar_embed(brief.get('events', {}), mode=mode)
    earnings = _build_earnings_embed(brief.get('earnings', {}))
    playbook = _build_playbook_embed(brief)

    ticker_embed = {
        'title': 'Ticker Analysis',
        'fields': ticker_fields,
        'color': overview.get('color', 0x3498db),
    }

    # ── Message 1: analytics ────────────────────────────────────────
    msg1 = [overview, ticker_embed, playbook]
    if not playbook.get('fields'):
        msg1.remove(playbook)

    # ── Message 2: events ───────────────────────────────────────────
    msg2 = []
    if earnings.get('fields') or earnings.get('description'):
        msg2.append(earnings)
    if calendar.get('fields') or calendar.get('description'):
        msg2.append(calendar)

    messages = []
    for embeds in (msg1, msg2):
        # Per-message truncation
        while embeds and sum(len(json.dumps(e)) for e in embeds) > MAX_EMBED_CHARS:
            logger.warning(
                "Discord payload over %d chars, dropping %s",
                MAX_EMBED_CHARS, embeds[-1].get('title'),
            )
            embeds.pop()
        if embeds:
            messages.append({'embeds': embeds})
    return messages


def format_discord_message(brief: dict) -> dict:
    """Legacy single-payload API kept for back-compat with tests + any
    direct callers. Returns the FIRST message from format_discord_messages,
    which is overview + tickers + playbook (the analytics half). Earnings
    and calendar move to a second message — callers using this legacy
    function will silently lose them. New code should prefer
    format_discord_messages.
    """
    msgs = format_discord_messages(brief)
    return msgs[0] if msgs else {'embeds': []}


# ── Cloud SQL Persistence ───────────────────────────────────────────────────

def _resolve_run_kind_and_update(allow_update_arg: bool) -> tuple[bool, str]:
    """Resolve allow_update + run_kind from CLI flag and env vars.

    Precedence (highest first):
      1. CLI --update flag → allow_update=True, run_kind='manual_update'
      2. BRIEF_UPDATE=true env → allow_update=True, run_kind='manual_update'
      3. BRIEF_AS_OF set (historical replay) → allow_update=True,
         run_kind='replay_refresh'
      4. otherwise → allow_update=False, run_kind='scheduled' if
         BRIEF_TRIGGERED_BY starts with 'cloud-scheduler', else
         'manual_replay'
    """
    if allow_update_arg or os.environ.get('BRIEF_UPDATE') == 'true':
        return True, 'manual_update'
    if os.environ.get('BRIEF_AS_OF'):
        return True, 'replay_refresh'
    triggered_by = os.environ.get('BRIEF_TRIGGERED_BY', '')
    if triggered_by.startswith('cloud-scheduler'):
        return False, 'scheduled'
    return False, 'manual_replay'


def persist_to_cloud_sql(brief: dict, allow_update: bool = False,
                         run_kind: str = 'scheduled',
                         triggered_by: Optional[str] = None) -> int:
    """Write premarket analysis rows to Cloud SQL.

    Always INSERTs a row into `premarket_analysis_history` (audit
    trail; append-only). Then, per-ticker:
      - If a row already exists in `premarket_analysis` for
        (analysis_date, ticker) and `allow_update` is False:
        SKIP the current-table write; log a warning. Protects the
        canonical morning row.
      - Otherwise: UPSERT (INSERT, or UPDATE on conflict). Used for
        the first run of the day and for explicit --update overrides.

    See docs/plans/MORNING_RUN_PROTECTION_PLAN.md for the rationale.
    """
    try:
        from gcp.database import (
            is_cloud_sql_configured, upsert_dataframe, bulk_insert_dataframe,
            row_exists,
        )
    except ImportError:
        logger.warning("gcp.database not available -- skipping DB persist")
        return 0

    if not is_cloud_sql_configured():
        logger.info("Cloud SQL not configured -- skipping DB persist")
        return 0

    # Honour the brief's resolved analysis_date (BRIEF_AS_OF) so
    # historical replays write to the correct date row, not today's.
    # Falls back to today when the brief was generated without an
    # explicit override.
    analysis_date = brief.get('analysis_date') or date.today()
    rows = []
    # Tickers whose per-ticker playbook block raised. They still go to
    # premarket_analysis_history (audit trail records the failure), but
    # they MUST NOT land in the canonical premarket_analysis row — a
    # partial row with NULL playbook would silently corrupt the morning
    # snapshot on a fresh-day failure.
    playbook_failed = set()
    for ticker, data in brief.get('tickers', {}).items():
        if data.get('status') == 'NO DATA':
            continue
        if data.get('status') == 'PLAYBOOK_FAILED':
            playbook_failed.add(ticker)
        rows.append({
            'analysis_date': analysis_date,
            'ticker': ticker,
            'price': data.get('price'),
            'rsi': data.get('rsi'),
            'rsi_direction': data.get('rsi_direction'),
            'consecutive_up': data.get('consecutive_up'),
            'consecutive_down': data.get('consecutive_down'),
            'signal_status': data.get('signal_status'),
            'strat_candle': str(data.get('strat_candle', '')),
            'strat_combo': str(data.get('strat_combo', '')),
            'recommended_orb_window': str(data.get('recommended_orb_window', '')),
            'recommended_orb_reason': str(data.get('recommended_orb_reason', '')),
            # The full Strat playbook string rendered by
            # lib.strat_levels.format_levels_for_brief — entry triggers,
            # stops, T1/T2, R:R per ticker. PR #129 added the column;
            # this row-builder was the second half of the fix
            # (without it, the column would still get NULL on upsert).
            'playbook': data.get('playbook'),
            'strat_setup': data.get('strat_setup', False),
            'ftfc_score': data.get('ftfc_score'),
            'ftfc_direction': data.get('ftfc_direction'),
            'ftfc_labels': json.dumps(data.get('ftfc_labels', {})),
            'prev_day_high': data.get('prev_day_high'),
            'prev_day_low': data.get('prev_day_low'),
            # New enriched fields (silently dropped if columns don't exist yet)
            'change_pct': data.get('change_pct'),
            'rvol': data.get('rvol'),
            'sma200': data.get('sma200'),
            'bb_upper': data.get('bb_upper'),
            'bb_lower': data.get('bb_lower'),
            'ema9': data.get('ema9'),
            'ema20': data.get('ema20'),
            'atr14': data.get('atr14'),
            'volatility_20d': data.get('volatility_20d'),
            'macd_cross': data.get('macd_cross'),
            'vol_regime': data.get('vol_regime'),
            'above_sma200': data.get('above_sma200'),
            'stoch_rsi_k': data.get('stoch_k'),
            'stoch_rsi_d': data.get('stoch_d'),
        })

    if not rows:
        return 0

    # Step 1 — always insert into history (append-only).
    history_rows = [
        {**row, 'run_kind': run_kind, 'triggered_by': triggered_by}
        for row in rows
    ]
    history_df = pd.DataFrame(history_rows)
    n_hist = bulk_insert_dataframe(history_df, 'premarket_analysis_history')
    logger.info("Inserted %d rows into premarket_analysis_history (run_kind=%s)",
                n_hist, run_kind)

    # Step 2 — write to current table. Per-ticker conditional UPSERT
    # protects the canonical morning row when allow_update=False.
    # Drop PLAYBOOK_FAILED tickers before either write path; those rows
    # have no playbook + level data and would corrupt the canonical row.
    canonical_rows = [r for r in rows if r['ticker'] not in playbook_failed]
    if playbook_failed:
        logger.warning(
            "Skipped premarket_analysis write for %d PLAYBOOK_FAILED "
            "ticker(s); history rows are still recorded. Failed: %s",
            len(playbook_failed), ', '.join(sorted(playbook_failed)))
    if not canonical_rows:
        return 0
    if allow_update:
        df = pd.DataFrame(canonical_rows)
        n = upsert_dataframe(df, 'premarket_analysis', ['analysis_date', 'ticker'])
        logger.info("UPSERTED %d rows to premarket_analysis (allow_update=True)", n)
        return n

    # Default path — INSERT only the rows that don't already exist.
    rows_to_write = []
    skipped = []
    for row in canonical_rows:
        if row_exists('premarket_analysis',
                      {'analysis_date': row['analysis_date'],
                       'ticker': row['ticker']}):
            skipped.append(row['ticker'])
        else:
            rows_to_write.append(row)
    if rows_to_write:
        df = pd.DataFrame(rows_to_write)
        n = upsert_dataframe(df, 'premarket_analysis',
                             ['analysis_date', 'ticker'])
        logger.info("Inserted %d new rows to premarket_analysis", n)
    else:
        n = 0
    if skipped:
        logger.warning(
            "Skipped premarket_analysis write for %d ticker(s) "
            "(row already exists; pass --update or set BRIEF_UPDATE=true to "
            "overwrite). Skipped: %s",
            len(skipped), ', '.join(skipped))
    return n


def send_to_discord(message: dict, webhook_url: str, timeout: int = 10):
    """Send formatted message to Discord webhook."""
    response = requests.post(webhook_url, json=message, timeout=timeout)
    response.raise_for_status()
    print(f"Discord message sent successfully (status {response.status_code})")


def fetch_premarket_analysis_row(ticker: str, analysis_date) -> Optional[dict]:
    """Pull one premarket_analysis row as a dict (None if missing).

    Returns the row in the same dict shape that the in-memory brief
    uses (with keys like prev_day_high, atr14, ftfc_direction, etc.)
    so it can be fed back into the embed builders for /replay
    cache-hits.
    """
    try:
        from gcp.database import is_cloud_sql_configured, query_to_dataframe
    except ImportError:
        return None
    if not is_cloud_sql_configured():
        return None

    df = query_to_dataframe(
        "SELECT * FROM premarket_analysis "
        "WHERE analysis_date = :d AND ticker = :t LIMIT 1",
        {'d': str(analysis_date), 't': ticker.upper()},
    )
    if df.empty:
        return None
    row = df.iloc[0].to_dict()
    # ftfc_labels stored as JSONB → comes back as dict already; coerce to dict
    # to be safe (some drivers return str).
    if isinstance(row.get('ftfc_labels'), str):
        try:
            row['ftfc_labels'] = json.loads(row['ftfc_labels'])
        except (json.JSONDecodeError, TypeError):
            row['ftfc_labels'] = {}
    return row


def render_existing_brief_to_discord(
    ticker: str, analysis_date, webhook_url: Optional[str] = None,
) -> bool:
    """Pull the existing premarket_analysis row and post a Discord
    embed for it. Used by /replay's cache-hit path to re-deliver the
    canonical morning brief without re-running compute.

    Returns True on success. Returns False (and logs) if the row is
    missing or the webhook call fails.
    """
    webhook_url = webhook_url or os.environ.get('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        logger.warning("render_existing_brief: no DISCORD_WEBHOOK_URL set")
        return False

    row = fetch_premarket_analysis_row(ticker, analysis_date)
    if row is None:
        logger.warning("render_existing_brief: no row for %s on %s",
                       ticker, analysis_date)
        return False

    # Reconstruct a minimal brief dict so the existing embed builders
    # can render it. We render ONLY the ticker-fields embed (the
    # focused /replay output) — events/earnings are separate concerns
    # and would require re-fetching for the historical date.
    brief = {
        'analysis_date': analysis_date,
        'tickers': {row['ticker']: row},
        'events': {},
        'earnings': {'mode': 'daily', 'earnings': []},
    }
    fields = _build_ticker_fields(brief)
    embed = {
        'title': f'Replay: {ticker.upper()} on {analysis_date}',
        'description': f"Cached premarket analysis from "
                       f"{row.get('analysis_ts', 'unknown time')}.",
        'fields': fields,
        'color': 0x95a5a6,  # gray — distinguishes from a live brief
    }

    # Drop fields if over the per-embed char budget
    while fields and len(json.dumps(embed)) > MAX_EMBED_CHARS:
        fields.pop()
        embed['fields'] = fields

    try:
        send_to_discord({'embeds': [embed]}, webhook_url)
        return True
    except Exception as exc:
        logger.warning("render_existing_brief: webhook post failed: %s", exc)
        return False


def main(argv: Optional[list[str]] = None):
    # Cloud Run Jobs pass overrides via env vars, not CLI flags. Translate
    # the env-var equivalent of --post-existing into argv when the caller
    # didn't pass argv explicitly. This lets /replay dispatch the
    # cache-hit job by setting BRIEF_POST_EXISTING_{TICKER,DATE}.
    if argv is None:
        env_t = os.environ.get('BRIEF_POST_EXISTING_TICKER')
        env_d = os.environ.get('BRIEF_POST_EXISTING_DATE')
        if env_t and env_d:
            argv = ['--post-existing', env_t, env_d]

    parser = argparse.ArgumentParser(
        description='Run the pre-market brief and persist + post to Discord.')
    parser.add_argument(
        '--update', action='store_true',
        help="Allow overwriting today's canonical premarket_analysis "
             "row. Without this, re-runs only append to "
             "premarket_analysis_history; the current row is "
             "protected. Equivalent to BRIEF_UPDATE=true env var. "
             "Implied when BRIEF_AS_OF is set (replay).",
    )
    parser.add_argument(
        '--post-existing', nargs=2, metavar=('TICKER', 'DATE'),
        help="Skip compute. Pull the existing premarket_analysis row "
             "for (TICKER, DATE) and post it to Discord. Used by "
             "/replay's cache-hit path. DATE format: YYYY-MM-DD. "
             "Equivalent env vars: BRIEF_POST_EXISTING_TICKER, "
             "BRIEF_POST_EXISTING_DATE.",
    )
    args = parser.parse_args(argv)

    if args.post_existing:
        ticker, date_str = args.post_existing
        try:
            analysis_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            print(f"ERROR: --post-existing DATE must be YYYY-MM-DD; "
                  f"got {date_str!r}", file=sys.stderr)
            sys.exit(2)
        ok = render_existing_brief_to_discord(ticker, analysis_date)
        sys.exit(0 if ok else 1)

    allow_update, run_kind = _resolve_run_kind_and_update(args.update)
    triggered_by = (
        os.environ.get('BRIEF_TRIGGERED_BY')
        or ('cli' if sys.stdin.isatty() else 'cloud-run-job')
    )

    webhook_url = os.environ.get('DISCORD_WEBHOOK_URL')

    cfg = load_config()
    data_dir = os.environ.get('DATA_DIR', cfg.market.data_dir)

    print(f"Generating pre-market brief... (allow_update={allow_update}, "
          f"run_kind={run_kind}, triggered_by={triggered_by})")
    brief = generate_premarket_brief(cfg=cfg, data_dir=data_dir)
    print(json.dumps(brief, indent=2, default=str))

    # Persist to Cloud SQL — always writes history; current-table
    # write is conditional on allow_update + per-ticker existence.
    n = persist_to_cloud_sql(
        brief, allow_update=allow_update,
        run_kind=run_kind, triggered_by=triggered_by,
    )
    print(f"Persisted {n} rows to premarket_analysis "
          f"(history rows always written)")

    messages = format_discord_messages(brief)
    if webhook_url:
        for i, message in enumerate(messages, start=1):
            try:
                send_to_discord(message, webhook_url,
                                timeout=cfg.monitor.discord_timeout)
                logger.info("sent message %d/%d (%d embeds)",
                            i, len(messages),
                            len(message.get('embeds', [])))
            except Exception:
                logger.exception("Discord post failed for message %d/%d",
                                 i, len(messages))
    else:
        print("\nDISCORD_WEBHOOK_URL not set -- printing payloads only")
        for i, message in enumerate(messages, start=1):
            print(f"\n--- payload {i}/{len(messages)} ---")
            print(json.dumps(message, indent=2))


if __name__ == '__main__':
    main()
