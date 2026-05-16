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
    #
    # Weekly mode (Sunday) skips this filter (#396): UW (unusual_whales)
    # only enriches options_volume for the immediate forward window — for
    # next-week earnings dates that come from yahoo/AV/EW, options_volume
    # is NULL until UW catches up Mon morning. On Sunday the brief's job
    # is informational ("here's what's coming") not tradeability ranking,
    # so dropping every row because UW hasn't refreshed produces an
    # empty list (the user sees "no earnings this week" despite ~5000
    # rows in the table for the next 5 weekdays).
    # Filter pipeline (refined 2026-05-11):
    #   1. AV ∩ UW source confirmation — both AlphaVantage AND Unusual
    #      Whales must list the (ticker, date). UW's curated daily list
    #      is the gate (~25-37 names/day); AV cross-confirms the date.
    #      EW is NOT a gate — it cuts out major institutional names
    #      (SONY, TCOM, JBS) and high-OI small-caps that don't fit EW's
    #      strategy templates but are still tradeable.
    #   2. options_volume > 0 — must have some daily flow
    #   3. open_interest > 1000 — drops tiny chains (real positions exist)
    #   4. mcap: no floor — let OI gate the micro-caps
    #
    # The Sunday weekly view relaxes (1) and (2) since UW/AV options
    # data is stale for next-week dates that haven't seen Friday's
    # close yet — see PR #398.
    # Filter is split into two layers:
    #   (a) liquidity floor — options_volume > 0 AND open_interest > 1000
    #       (always applied in daily mode; weak/illiquid chains have
    #        nothing to trade regardless of source confirmation)
    #   (b) source-confirmation gate — AV ∩ UW
    #       (bypassable via BRIEF_INCLUDE_UNCONFIRMED=1 for debug,
    #        tier-system tests, or legacy callers that want the
    #        pre-gate view)
    if mode == 'daily':
        earnings = [
            e for e in earnings
            if (e.get('options_volume') or 0) > 0
            and (e.get('open_interest') or 0) > 1000
        ]
        if os.environ.get('BRIEF_INCLUDE_UNCONFIRMED', '') != '1':
            earnings = [
                e for e in earnings
                if 'alphavantage' in (e.get('sources') or [])
                and 'unusual_whales' in (e.get('sources') or [])
            ]

    # Enrich BEFORE sorting so playability_score (move-magnitude ×
    # direction-consistency × log(options_volume)) drives the top-N
    # selection — not just after the cut. The intent is to surface
    # tickers that genuinely have high volatility AND consistent
    # post-earnings moves, which is exactly what the score captures
    # from the last 12 quarters of last_1d_reactions.
    #
    # Each row gains:
    #   - playability_score (None when no historical data available)
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

    # Two-track split (added 2026-05-14):
    #   Track A "earnings"   → nQ ≥ 12 AND not Q1-SKIP. Full archetype +
    #                          confidence label rendered. Sorted by score.
    #   Track B "watchlist"  → nQ < 12 AND high flow (OI ≥ 50k AND vol ≥ 5k).
    #                          IPO-edge names like CRCL ($30B mcap, 768k OI)
    #                          surface here instead of being silently dropped.
    #                          No archetype/score — just flow stats + nQ.
    # The two lists are mutually exclusive — a ticker is in exactly one.
    # Daily mode only; weekly preview keeps the broader pre-split view.
    watchlist: list[dict] = []
    if mode == 'daily' and os.environ.get('BRIEF_INCLUDE_UNCONFIRMED', '') != '1':
        min_nq = int(os.environ.get('BRIEF_MIN_REACTION_QUARTERS', '12'))
        wl_min_oi  = int(os.environ.get('BRIEF_WATCHLIST_MIN_OI',  '50000'))
        wl_min_vol = int(os.environ.get('BRIEF_WATCHLIST_MIN_VOL', '5000'))

        before_n = len(earnings)
        next_earnings = []
        for e in earnings:
            nq = e.get('playability_n_q') or 0
            if nq >= min_nq:
                next_earnings.append(e)
            elif ((e.get('open_interest') or 0) >= wl_min_oi
                  and (e.get('options_volume') or 0) >= wl_min_vol):
                watchlist.append(e)
        earnings = next_earnings
        logger.info(
            "Two-track split: %d → Track A=%d (nQ≥%d), Track B=%d (OI≥%d & vol≥%d)",
            before_n, len(earnings), min_nq, len(watchlist), wl_min_oi, wl_min_vol,
        )

        # Drop Q1 (SKIP) names from Track A — below-baseline conviction
        # (34.8% hit rate per backtest) doesn't deserve a row in the brief.
        try:
            from lib.earnings_reactions import score_quintile
            before_a = len(earnings)
            earnings = [e for e in earnings
                        if score_quintile(e.get('playability_score')) != 'Q1']
            if before_a != len(earnings):
                logger.info("Dropped %d Q1-SKIP names from Track A",
                            before_a - len(earnings))
        except Exception as exc:
            logger.warning("Q1 filter skipped: %s", exc)

    # Sort Track A: playability_score DESC primary; OI/vol/mcap fallback.
    earnings.sort(key=lambda r: (
        r['date'],
        -(r.get('playability_score') or 0),  # DESC: vol × consistency × log(vol)
        -(r.get('open_interest')     or 0),  # DESC: OI fallback
        -(r.get('options_volume')    or 0),  # DESC: vol fallback
        -(r.get('market_cap')        or 0),  # DESC: mcap fallback
        r['tier'],                            # ASC: tier breaks ties
        r['ticker'],                          # ASC: alphabetical
    ))

    # Sort Track B: open_interest DESC (per user-locked policy 2026-05-14).
    # Watchlist names have no score so OI is the natural priority signal.
    watchlist.sort(key=lambda r: (
        r['date'],
        -(r.get('open_interest')     or 0),
        -(r.get('options_volume')    or 0),
        -(r.get('market_cap')        or 0),
        r['ticker'],
    ))

    # Cap at top_n AFTER the playability-driven sort so the cut keeps
    # the most-tradeable rows. ``top_n=0`` disables the cap (legacy).
    if top_n and top_n > 0:
        earnings = earnings[:top_n]

    return {'mode': mode, 'start': start, 'end': end,
            'earnings': earnings, 'watchlist': watchlist}

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
    rows = rows[:top_n] if top_n else rows

    # Phase 1.6: attach event-conditional historical lean.
    # For each row, look up past quarters where this ticker had a
    # similar-shaped gap; classify as 'bullish gap play' / 'expect
    # reversal' / etc. so the renderer can surface a same-day lean.
    try:
        from lib.earnings_reactions import conditional_lean_summary
        for r in rows:
            r['conditional_lean'] = conditional_lean_summary(
                ticker=r['ticker'],
                reaction_basis='AMC',  # this loader is AMC-only
                actual_gap_pct=r['gap_pct'],
            )
    except Exception as e:
        logger.warning("conditional lean lookup skipped: %s", e)

    return rows


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
        df = loader.load_daily(ticker, on_stale='warn')
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

        # ── Data freshness gate (Track B audit G.P0.4 / G.P0.5) ─────
        # Resolve the timestamp of the last good bar and decide if
        # the brief is operating on stale data. On a stuck-fetcher
        # day (the audit's repro), `latest.name` is yesterday's
        # closed-week-ago date and we MUST surface that — silently
        # republishing 4-27 data as 5-7 is exactly what the audit
        # caught. When stale, mark status='STALE_DAILY_DATA' and
        # short-circuit the per-ticker compute so we don't pretend
        # the analysis is current. The history row still records
        # the metadata + a notes string for the audit trail; only
        # the canonical premarket_analysis row is suppressed (mirrors
        # the existing PLAYBOOK_FAILED contract).
        last_bar_ts = latest.name
        last_bar_date_obj = (
            last_bar_ts.date() if hasattr(last_bar_ts, 'date') else None
        )
        # Anchor `data_as_of` to 16:00 ET (US/Eastern market close) on
        # the bar's date, regardless of whether `latest.name` came in as
        # a tz-naive UTC midnight, a tz-aware UTC timestamp, or a plain
        # date object. The W6 v1 writer used `latest.name` directly,
        # which renders pandas DatetimeIndex's UTC midnight as
        # "20:00 EDT the prior day" in ET — confusing for validation
        # ("why am I seeing 8 PM market-close data?"). Anchoring to
        # the bar's market close makes the persisted timestamp
        # unambiguous in both UTC (e.g. 20:00 UTC for an EDT bar) and
        # ET (16:00 EDT) — readers see the bar's date AND the
        # market-close hour, exactly the semantic meaning of "this
        # daily bar's data".
        if last_bar_date_obj is not None:
            data_as_of_anchored = (
                pd.Timestamp(last_bar_date_obj)
                .tz_localize('America/New_York')
                .replace(hour=16, minute=0, second=0)
            )
        else:
            # Defensive fallback for synthetic data without a parseable
            # index — keep the original timestamp shape so persistence
            # doesn't error.
            data_as_of_anchored = last_bar_ts
        is_stale, gap_days, freshness_status = _resolve_data_freshness(
            last_bar_date_obj, analysis_date,
        )
        if is_stale:
            logger.warning(
                "[brief:%s] STALE_DAILY_DATA — last bar %s, analysis_date %s, "
                "gap=%d session(s); skipping per-ticker analysis to avoid "
                "republishing stale signals. See Track B audit G.P0.4.",
                ticker, last_bar_date_obj, analysis_date, gap_days,
            )
            brief['tickers'][ticker] = {
                'status': 'STALE_DAILY_DATA',
                'data_as_of': data_as_of_anchored,
                'data_freshness_status': freshness_status,
                'freshness_gap_days': gap_days,
            }
            continue

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
        signal_status = _resolve_signal_status(
            call_score=call_score,
            put_score=put_score,
            ftfc_direction=ftfc_dir,
            signal_threshold=signal_threshold,
            building_threshold=building_threshold,
        )

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
            # Track B audit G.P0.5 — record which OHLCV bar the
            # analysis used so freshness audits don't need joins.
            # `data_as_of_anchored` is normalized to 16:00 ET on the
            # bar's date (W11) so any reader sees an unambiguous
            # market-close-time anchor instead of pandas's default
            # UTC-midnight rendering ("20:00 EDT prior day").
            'data_as_of': data_as_of_anchored,
            'data_freshness_status': freshness_status,
            'freshness_gap_days': gap_days,
        }

    # ── Brief-level data freshness summary (Track B G.P0.5) ─────────
    # Aggregate across the per-ticker data_as_of stamps so the
    # overview embed can render a single "Based on data from X to Y"
    # line. When tickers diverge (rare but possible if one fetcher
    # was up-to-date and another wasn't) we show the spread; when
    # they converge it collapses to a single date.
    as_of_values = [
        d.get('data_as_of')
        for d in brief.get('tickers', {}).values()
        if d.get('data_as_of') is not None
    ]
    any_stale = any(
        d.get('data_freshness_status') == 'STALE_DAILY_DATA'
        for d in brief.get('tickers', {}).values()
    )
    if as_of_values:
        brief['data_freshness_summary'] = _format_data_freshness_summary(
            earliest_as_of=min(as_of_values),
            latest_as_of=max(as_of_values),
            analysis_date=analysis_date,
            any_stale=any_stale,
        )
    else:
        brief['data_freshness_summary'] = None

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
        # Track B audit (Codex P1 review on PR #336): the playbook
        # block dereferences d['price'] / d.get('atr14') etc., which
        # are not populated on STALE_DAILY_DATA rows. Pre-fix the
        # try/except below caught the resulting KeyError as a
        # PLAYBOOK_FAILED, which clobbered the intended stale notes
        # and canonical-skip behavior. Skip stale rows here so the
        # status set upstream survives all the way through to
        # persist_to_cloud_sql.
        if d.get('status') == 'STALE_DAILY_DATA':
            print(f"[brief:{ticker}] skip (STALE_DAILY_DATA)",
                  file=sys.stderr, flush=True)
            continue
        try:
            df = loader.load_daily(ticker, on_stale='warn')
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
                analysis_date=analysis_date,
            )
            # 2026-05-10 — append intraday premarket levels (PMK_H / PMK_L)
            # so they get persisted alongside the structural ones. Pre-fix
            # the trade_planner had to synthesize a trigger above pre_high
            # via ATR projection (5/6 QQQ: $695.52 = pre_high+0.20×ATR),
            # which on tight days like 5/6 was never reached during RTH.
            # With PMK_H persisted, the planner can use pre_high directly
            # as a candidate trigger AND signal_monitor sees PMK_H/L as
            # triggerable crossings live during the session.
            try:
                from lib.strat_levels import compute_premarket_levels
                latest_for_pmk = df.iloc[-1] if len(df) else None
                _pmk_h = float(latest_for_pmk.get('pre_high')) if (
                    latest_for_pmk is not None
                    and pd.notna(latest_for_pmk.get('pre_high'))
                ) else None
                _pmk_l = float(latest_for_pmk.get('pre_low')) if (
                    latest_for_pmk is not None
                    and pd.notna(latest_for_pmk.get('pre_low'))
                ) else None
                pmk_levels = compute_premarket_levels(_pmk_h, _pmk_l)
                if pmk_levels:
                    level_map.levels.extend(pmk_levels.values())
                    print(f"[brief:{ticker}] appended {len(pmk_levels)} PMK levels "
                          f"(PMK_H={_pmk_h}, PMK_L={_pmk_l})",
                          file=sys.stderr, flush=True)
            except Exception as exc:
                print(f"[brief:{ticker}] PMK levels skipped: {type(exc).__name__}: {exc}",
                      file=sys.stderr, flush=True)
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

                # `select_trigger_and_regime` returns a 5-tuple as of
                # the synthetic-trigger refactor in
                # `lib/agents/trade_planner.py` —
                # `(regime, trigger, stop_anchor, distance_atr, is_synthetic)`.
                # The brief only consumes the regime here; the rest
                # use `*_` so future renames or extensions to the
                # planner's return shape don't ripple back. Pre-fix
                # this unpacked 4 elements, which produced the
                # `regime classifier failed: ValueError: too many
                # values to unpack (expected 4)` warning observed
                # surfacing via the `regime_compute_error` defensive
                # path during the 2026-05-09 brief replays.
                regime_long, *_ = select_trigger_and_regime(_ctx('long'), 'long')
                regime_short, *_ = select_trigger_and_regime(_ctx('short'), 'short')
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

            # Persist STRUCTURED trigger/stop/target prices alongside the
            # narrative `playbook` string. The text is what the trader sees
            # in Discord; the structured columns let downstream analytics
            # (premarket_playbook_resolver — see issue tracking outcome
            # tracking, follow-up to 2026-05-11 user request) compute
            # whether the recommended setup actually played out during RTH.
            #
            # Pre-this-PR these values lived only in level_map and got lost
            # after format_levels_for_brief consumed them. Persisting them
            # is necessary to walk subsequent intraday bars and report
            # "trigger hit at HH:MM, T1 hit at HH:MM, stop never touched,
            # EOD pnl +0.97%". Without them, brief-playbook-outcome analytics
            # would have to parse the LLM prose — fragile and brittle.
            ct = level_map.calls_trigger or {}
            pt = level_map.puts_trigger or {}
            ct_targets = ct.get('targets', []) if ct else []
            pt_targets = pt.get('targets', []) if pt else []
            d['calls_trigger_price'] = ct.get('trigger_level') if ct else None
            d['calls_trigger_name']  = ct.get('trigger_name')  if ct else None
            d['calls_stop_price']    = ct.get('stop')          if ct else None
            d['calls_stop_name']     = ct.get('stop_name')     if ct else None
            d['calls_t1_price'] = ct_targets[0]['price'] if len(ct_targets) >= 1 else None
            d['calls_t2_price'] = ct_targets[1]['price'] if len(ct_targets) >= 2 else None
            d['calls_t3_price'] = ct_targets[2]['price'] if len(ct_targets) >= 3 else None
            d['puts_trigger_price'] = pt.get('trigger_level') if pt else None
            d['puts_trigger_name']  = pt.get('trigger_name')  if pt else None
            d['puts_stop_price']    = pt.get('stop')          if pt else None
            d['puts_stop_name']     = pt.get('stop_name')     if pt else None
            d['puts_t1_price'] = pt_targets[0]['price'] if len(pt_targets) >= 1 else None
            d['puts_t2_price'] = pt_targets[1]['price'] if len(pt_targets) >= 2 else None
            d['puts_t3_price'] = pt_targets[2]['price'] if len(pt_targets) >= 3 else None

            # Persist level map to Cloud SQL so the realtime signal_monitor
            # (which doesn't itself recompute) can query it for level-break
            # detection during market hours.
            #
            # 2026-05-10 freshness guard: pass `source_data_as_of` (the
            # latest market_data_daily date used to compute this level
            # map) so persist_level_map can refuse to write when the
            # underlying data is stale. Pre-fix the 5/6 brief silently
            # wrote 4/27-stale levels into rows stamped as_of=5/6;
            # every downstream reader trusted them. The data layer's
            # #322/#323/#325 guards catch the upstream freeze, but this
            # is defense-in-depth at the level-write boundary.
            try:
                from gcp.database import get_engine
                from lib.strat_levels import persist_level_map, StaleSourceDataError
                engine = get_engine()
                # df was just used to build level_map immediately above
                # (lines ~1015-1034); its index max is the latest
                # market_data_daily.date that fed the level computation.
                _src_age = None
                try:
                    if isinstance(df.index, pd.DatetimeIndex) and len(df.index):
                        _src_age = df.index.max()
                except Exception:
                    _src_age = None
                # AS-OF-aware freshness check: when this is a historical
                # replay (BRIEF_AS_OF set), the freshness comparison
                # should be "was the data fresh AS OF that date" — not
                # "is the data fresh as of right now (days/weeks
                # later)." Without this override, every historical
                # replay refuses to write because the source is now N
                # weeks behind today. analysis_date is set upstream
                # from BRIEF_AS_OF or now()-in-ET; use it as the
                # reference clock so replays are faithful to "what
                # would the brief have said on that day."
                _today_ref = None
                try:
                    _today_ref = pd.Timestamp(analysis_date)
                    if _today_ref.tz is None:
                        _today_ref = _today_ref.tz_localize('UTC')
                except Exception:
                    _today_ref = None
                with engine.connect() as conn:
                    n = persist_level_map(
                        level_map, conn.connection,
                        source_data_as_of=_src_age,
                        today=_today_ref,
                    )
                    conn.connection.commit()
                print(f"[brief:{ticker}] persisted {n} strat_levels rows "
                      f"(source_data_as_of={_src_age}, today_ref={_today_ref})",
                      file=sys.stderr, flush=True)
            except StaleSourceDataError as exc:
                # Stale-source refusal is loud + surfaceable, not a generic
                # failure. Don't traceback (the message is the message).
                # Mark the ticker for the audit trail so the row lands in
                # premarket_analysis_history with the failure cause.
                print(f"[brief:{ticker}] strat_levels persist REFUSED (stale source): {exc}",
                      file=sys.stderr, flush=True)
                d['status'] = 'STALE_DAILY_DATA'
                d['playbook_error'] = f"strat_levels persist refused: {exc}"
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


def _resolve_signal_status(
    call_score: int,
    put_score: int,
    ftfc_direction: str,
    signal_threshold: int,
    building_threshold: int,
) -> str:
    """Resolve the brief's `signal_status` string under the FTFC gate.

    The brief publishes one signal_status per (ticker, date). Pre-gate
    behaviour scored CALL and PUT independently and surfaced whichever
    crossed the threshold first — which on a bullish-FTFC row could
    produce "PUT setup (4/5)", contradicting the bullish bias. That
    contradiction is what set `signal_alerts.brief_alignment=CONFLICTED`
    on 4 of 6 (ticker, direction) buckets in the 2026-05-08 audit
    window (track-B / G.P1.5).

    The fix gates the published side by `ftfc_direction`:

      * `bullish` → CALL only (use call_score)
      * `bearish` → PUT only (use put_score)
      * anything else (mixed / None / unknown) → pick the higher score;
        ties go to CALL (a tie under mixed-FTFC carries no directional
        edge, but the brief has to pick one — CALL keeps the bias
        explicit rather than rendering "PUT" against a non-bearish
        bias).

    The trade-off is that we lose "fade the bias" plays — a 4/5 PUT
    score under a bullish FTFC will surface as 'No signal' (or as the
    weaker CALL score's status) instead of "PUT setup". Track G's
    cross-track recommendation (4.2) explicitly cautioned against
    treating fade-the-bias as a usable plan from the audit data, and
    the user-confirmed decision was to gate at source rather than
    keep the contradiction with a sidecar field. See
    `docs/audit/2026-05-08/track-B-implementation-plan.md` W1.
    """
    direction = (ftfc_direction or 'mixed').lower()
    if 'bull' in direction:
        score, side = call_score, 'CALL'
    elif 'bear' in direction:
        score, side = put_score, 'PUT'
    else:
        if call_score >= put_score:
            score, side = call_score, 'CALL'
        else:
            score, side = put_score, 'PUT'

    if score >= signal_threshold:
        return f'{side} setup ({score}/5)'
    if score >= building_threshold:
        return f'{side} building ({score}/5)'
    return 'No signal'


def _resolve_data_freshness(
    last_bar_date: Optional[date], analysis_date: date,
) -> tuple[bool, int, str]:
    """Decide whether the brief is operating on stale daily data.

    Track B audit (G.P0.4) found that on 2026-05-04 → 05-07 the brief
    happily republished the 2026-04-27 daily bar four mornings in a
    row because the daily fetcher had been frozen since 4-28. The
    null-close filter at premarket_brief.py:724 swallows the warning
    by silently falling back to `df.iloc[-1]` of the last good bar.
    The audit's headline recommendation is "fail loud" — detect the
    staleness and make it visible instead of letting the brief look
    healthy on a stuck-thermostat input.

    Returns a 3-tuple (is_stale, gap_days, status). Definitions:

      * ``gap_days``     — calendar-day gap between ``last_bar_date``
                           and ``analysis_date``. None-input maps to
                           sentinel ``-1`` (status='unknown').
      * ``is_stale``     — True if the gap > 1 calendar day AND the
                           weekend-exemption doesn't apply. The
                           weekend exemption: a Monday brief that
                           reads Friday's bar (gap=3) is fresh, NOT
                           stale. Implemented as
                           ``analysis_date.weekday() == 0 and gap == 3``.
                           Tuesday-after-holiday-Monday with gap=4
                           still flags as stale; that's a deliberate
                           bias toward false-positives on holiday
                           weeks (overflagging is recoverable; under-
                           flagging is the audit's failure mode).
      * ``status``       — string written to
                           ``premarket_analysis.data_freshness_status``:
                             'fresh' | 'STALE_DAILY_DATA' | 'unknown'.

    Pure function for unit-testability — does not touch globals or
    DataFrames. The caller (``generate_premarket_brief``) handles
    resolving ``last_bar_date`` from ``df.iloc[-1].name`` and
    propagating the verdict into the per-ticker dict.
    """
    if last_bar_date is None:
        return False, -1, 'unknown'
    gap = (analysis_date - last_bar_date).days
    if gap <= 1:
        return False, gap, 'fresh'
    # Weekend bridges where Friday's bar IS the most recent close
    # the market has produced:
    #   * Monday brief reading Friday → weekday=0, gap=3.
    #   * Sunday weekly brief reading Friday → weekday=6, gap=2.
    #     Codex P2 review on PR #336 caught the original exemption
    #     only handling the Monday case; the Sunday weekly brief flow
    #     at premarket_brief.py:893 is the legitimate
    #     Sunday-with-Friday-data path that needs the same exemption.
    # Saturday briefs are unsupported in production scheduling.
    weekday = analysis_date.weekday()
    weekend_exempt = (
        (weekday == 0 and gap == 3)     # Monday → Friday
        or (weekday == 6 and gap == 2)  # Sunday weekly brief → Friday
    )
    if weekend_exempt:
        return False, gap, 'fresh'
    return True, gap, 'STALE_DAILY_DATA'


def _format_data_freshness_summary(
    earliest_as_of: Optional[datetime],
    latest_as_of: Optional[datetime],
    analysis_date: date,
    any_stale: bool,
) -> Optional[str]:
    """Render the brief-level "Based on data from X to Y" line.

    Track B audit (G.P0.5): the 8:30 AM Discord brief is the first
    thing a phone-only trader sees in the morning, and it has no
    indication of which underlying data window produced the bias /
    levels / RSI. This helper produces a one-liner the overview
    embed appends, so freshness becomes visible at-a-glance instead
    of requiring a SQL query to discover.

    Examples:

      "Based on data from 2026-05-07 → 2026-05-07 (1 trading day)"
        → healthy day, single-bar window. The X==Y form is the
        common case (yesterday's close).

      "Based on data from 2026-04-27 → 2026-04-27 (1 trading day, "
      "stale by 6 sessions) ⚠"
        → stuck-fetcher day. Adds a gap-in-sessions descriptor and
        a warning emoji so the staleness is unmistakable.

    Returns None if both inputs are None (no tickers had usable
    data; the embed builder skips the line entirely). Single-bar
    windows are rendered as ``X → X (1 trading day)``.
    """
    if earliest_as_of is None or latest_as_of is None:
        return None
    earliest_d = earliest_as_of.date() if hasattr(earliest_as_of, 'date') else earliest_as_of
    latest_d = latest_as_of.date() if hasattr(latest_as_of, 'date') else latest_as_of
    span_days = (latest_d - earliest_d).days + 1
    span_label = '1 trading day' if span_days == 1 else f'{span_days} trading days'
    line = f'Based on data from {earliest_d} → {latest_d} ({span_label}'
    if any_stale:
        gap = (analysis_date - latest_d).days
        line += f', stale by {gap} session{"s" if gap != 1 else ""}'
    line += ')'
    if any_stale:
        line += ' ⚠'
    return line


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
        # STALE_DAILY_DATA rows have no price/rsi/change_pct
        # populated (the per-ticker analysis was skipped upstream).
        # Render a degraded line that still names the ticker but
        # flags staleness explicitly, mirroring the NO DATA pattern.
        # The brief-level `data_freshness_summary` line below carries
        # the full session-gap descriptor for context. Codex P1
        # review on PR #336 caught the missing skip path that
        # would have caused KeyError on d['price'] downstream.
        if d.get('status') == 'STALE_DAILY_DATA':
            gap = d.get('freshness_gap_days', '?')
            suffix = 's' if gap != 1 else ''
            lines.append(
                f'**{ticker}** — STALE (data {gap} session{suffix} old) ⚠'
            )
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
        # STALE_DAILY_DATA tickers have no ftfc_direction populated;
        # skip them rather than crashing on the missing key.
        if d.get('ftfc_direction') is None:
            continue
        ftfc_parts.append(f'{ticker}: {d["ftfc_direction"]} ({d["ftfc_score"]:+.1f})')
    if ftfc_parts:
        lines.append('')
        lines.append('**FTFC:** ' + ' | '.join(ftfc_parts))

    # \ud83d\udcca Data freshness summary (Track B audit G.P0.5). Single
    # description-suffix line so phone-only readers see the
    # underlying-data window at-a-glance. On a stale day this carries
    # the warning emoji + "stale by N sessions" text \u2014 making the
    # bug the audit caught visible the moment the brief lands in
    # Discord, instead of requiring a database query to discover.
    freshness_summary = brief.get('data_freshness_summary')
    if freshness_summary:
        lines.append('')
        lines.append('\U0001F4CA ' + freshness_summary)

    # \ud83e\udde0 LLM "Today's setup" explanation (PR \u03b2 fills brief['llm_overview'];
    # PR \u03b1 reserves the slot). Renders as a description-suffix paragraph
    # so it sits naturally below the FTFC line without adding a field.
    overview_text = brief.get('llm_overview')
    if overview_text:
        lines.append('')
        lines.append('\U0001F9E0 **Today\'s setup:** ' + str(overview_text))

    # Determine overall color. Exclude both NO DATA and STALE_DAILY_DATA
    # statuses from the denominator — neither has a populated ftfc_direction
    # so they'd skew the bull/bear ratio toward "neutral".
    _excluded_statuses = {'NO DATA', 'STALE_DAILY_DATA'}
    bullish_count = sum(
        1 for d in brief.get('tickers', {}).values()
        if d.get('ftfc_direction') == 'bullish'
    )
    total = sum(
        1 for d in brief.get('tickers', {}).values()
        if d.get('status') not in _excluded_statuses
    )
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
        # Track B audit (Codex P1 review on PR #336): STALE_DAILY_DATA
        # rows have no level/indicator data populated upstream — the
        # per-ticker analysis was skipped. Mirror the NO DATA pattern
        # with a single degraded field rather than risking KeyError on
        # d['prev_day_high'] / d['rsi'] / etc. downstream.
        if d.get('status') == 'STALE_DAILY_DATA':
            gap = d.get('freshness_gap_days', '?')
            suffix = 's' if gap != 1 else ''
            fields.append({
                'name': f'{ticker}',
                'value': f'STALE — data {gap} session{suffix} old',
                'inline': False,
            })
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

    # Pull the lookback target from lib so the embed header label
    # matches whatever BRIEF_REACTION_LOOKBACK_QUARTERS is set to.
    try:
        from lib.earnings_reactions import DEFAULT_LOOKBACK_QUARTERS
        lookback = DEFAULT_LOOKBACK_QUARTERS
    except ImportError:
        lookback = 12
    lines = [f'  🎯 _Playability — top {len(playable)} ({lookback}Q profile)_']
    for i, r in enumerate(playable, 1):
        score = r.get('playability_score') or 0
        arch = r.get('playability_archetype') or 'quiet'
        mag = r.get('playability_move_mag_pct') or 0
        cons = (r.get('playability_dir_consistency') or 0) * 100
        rev = (r.get('playability_reversal_rate') or 0) * 100
        nq = r.get('playability_n_q', 0)
        hint = action_hint_for_archetype(arch)
        # Show n=X only when the ticker has fewer than the lookback
        # target quarters (insufficient daily bars for some reports).
        # When n matches the target, the section header already conveys it.
        n_suffix = '' if nq >= lookback else f' _(n={nq})_'
        lines.append(
            f'  {i}. **{r["ticker"]}** '
            f'`{score:.0f}` {arch} | '
            f'gap {mag:.1f}% · cons dir {cons:.0f}% · rev {rev:.0f}% '
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
        # Playability archetype → action (revised 2026-05-14 post-backtest).
        # Every row gets a tradeable action; confidence label below
        # tells you how to size it.
        #   bullish_trend  → CALL   (directional)
        #   bearish_trend  → PUT    (directional)
        #   mixed          → STRDL  (vol-only — no direction)
        #   reversal_play  → STRDL  (anti-predictive direction per
        #                            backtest — vol still happens,
        #                            don't bet a side)
        #   quiet          → (filtered upstream)
        archetype = r.get('playability_archetype')
        action_map = {
            'bullish_trend': 'CALL',
            'bearish_trend': 'PUT',
            'reversal_play': 'STRDL',
            'mixed':         'STRDL',
        }
        action = action_map.get(archetype)
        if action:
            extras.append(action)
        # Confidence label — tells the reader how much to size this trade.
        # Replaces academic Q1-Q5 with plain English:
        #   🔥 HIGH   (Q5, 58.9% hit) — size up
        #   ✅ SOLID  (Q4, 51.7%)     — standard sizing
        #   🟡 OK     (Q3, 46.5%)     — small position only
        #   ❓ WEAK   (Q2, 42.9%)     — paper / watch
        # Q1 (SKIP, 34.8% — below baseline) is filtered upstream so
        # never rendered.
        try:
            from lib.earnings_reactions import confidence_label
            conf = confidence_label(r.get('playability_score'))
            if conf:
                extras.append(conf)
        except Exception:
            pass
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
        # Phase 1.6: each row also carries a conditional lean from the
        # past 12Q earnings_reactions, rendered as a sub-line.
        amc_reactions = earnings_data.get('yesterday_amc_reactions') or []
        if amc_reactions:
            r_lines = [
                f'\n**\U0001f4ca Reactions to Last Night’s AMC** '
                f'(top {len(amc_reactions)} by |gap|)'
            ]
            for r in amc_reactions:
                r_lines.append(_row_line(r, show_tier_badge=False))
                lean = r.get('conditional_lean') or {}
                sentence = lean.get('sentence') or ''
                lean_phrase = lean.get('lean')
                if sentence and lean_phrase and lean_phrase != 'skip':
                    r_lines.append(
                        f'  → {sentence} · lean: **{lean_phrase}**'
                    )
                elif sentence:
                    # Sample too small / no clear pattern — surface
                    # the count but no directional verb.
                    r_lines.append(f'  → {sentence}')
            sections.append('\n'.join(r_lines))

        # 3. Tonight's AMC — reports after today's close
        amc = _build_bucket_section('\U0001f319 Reporting After Close',
                                     buckets['amc'], SECTION_CAP['amc'])
        if amc:
            sections.append(amc)

        # 4. High-Flow Watchlist (Track B) — IPO-edge names with huge
        # institutional flow but < 12Q earnings history. No archetype/
        # score (sample too small) — just flow stats + nQ. Sorted by
        # OI DESC per user policy 2026-05-14.
        watchlist = earnings_data.get('watchlist') or []
        if watchlist:
            def _compact(n):
                """Format 768421 → '768k', 1_530_000 → '1.5M'."""
                v = _valid_num(n)
                if v is None or v <= 0:
                    return None
                if v >= 1_000_000_000:
                    return f'{v/1_000_000_000:.1f}B'
                if v >= 1_000_000:
                    return f'{v/1_000_000:.1f}M'
                if v >= 1_000:
                    return f'{v/1_000:.0f}k'
                return f'{v:.0f}'

            w_lines = [
                f'\n**\U0001f4ca High-Flow Watchlist** ({len(watchlist)})',
                '_Huge flow but < 12Q history — no score/archetype. DYOR._'
            ]
            for r in watchlist:
                parts = []
                em = _valid_num(r.get('expected_move'))
                if em is not None:
                    parts.append(f'EM ${em:.2f}')
                oi = _compact(r.get('open_interest'))
                if oi:
                    parts.append(f'OI {oi}')
                vol = _compact(r.get('options_volume'))
                if vol:
                    parts.append(f'Vol {vol}')
                mcap = _compact(r.get('market_cap'))
                if mcap:
                    parts.append(f'{mcap} mcap')
                nq = r.get('playability_n_q') or 0
                if nq:
                    parts.append(f'nQ={nq}')
                extra = f' — {" | ".join(parts)}' if parts else ''
                w_lines.append(f"**{r['ticker']}**{extra}")
            sections.append('\n'.join(w_lines))

        # 5. Whispers — separated from the BMO/AMC rows so EW's strategy
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


def format_discord_messages_routed(brief: dict) -> list[tuple[str, dict]]:
    """Format brief as a list of (channel_kind, payload) tuples.

    Returns 1-3 messages, each tagged with the webhook channel it
    should post to:

      ('main', overview + ticker_analysis + playbook)   — analytics
      ('earnings', earnings)                            — company earnings
      ('main', economic calendar)                       — macro events

    The caller maps `channel_kind` to a webhook URL. If the earnings
    webhook isn't configured, the caller falls back to the main
    webhook so behaviour stays compatible.

    Per-message truncation still applies — if a single message would
    exceed 6000 chars on its own, lower-priority embeds drop within
    that message until it fits. The OTHER messages are unaffected.
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

    # ── Main channel — analytics ────────────────────────────────────
    main_msg = [overview, ticker_embed]
    if playbook.get('fields'):
        main_msg.append(playbook)

    # ── Earnings channel — company earnings ─────────────────────────
    earnings_msg = []
    if earnings.get('fields') or earnings.get('description'):
        earnings_msg.append(earnings)

    # ── Main channel — macro calendar (separate message so it doesn't
    # eat the analytics char budget) ────────────────────────────────
    calendar_msg = []
    if calendar.get('fields') or calendar.get('description'):
        calendar_msg.append(calendar)

    output: list[tuple[str, dict]] = []
    for kind, embeds in [('main', main_msg),
                         ('earnings', earnings_msg),
                         ('main', calendar_msg)]:
        # Per-message truncation
        while embeds and sum(len(json.dumps(e)) for e in embeds) > MAX_EMBED_CHARS:
            logger.warning(
                "Discord payload over %d chars, dropping %s",
                MAX_EMBED_CHARS, embeds[-1].get('title'),
            )
            embeds.pop()
        if embeds:
            output.append((kind, {'embeds': embeds}))
    return output


def format_discord_messages(brief: dict) -> list[dict]:
    """Backward-compatible API. Returns just the payloads (drops the
    channel-kind tag). Tests + legacy callers keep working unchanged;
    new callers should prefer format_discord_messages_routed to honour
    the earnings channel split.
    """
    return [msg for _kind, msg in format_discord_messages_routed(brief)]


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
    # Same contract for STALE_DAILY_DATA tickers (Track B audit
    # G.P0.4): the stale-warn path skipped the per-ticker analysis,
    # so the row has no signal_status / strat_candle / playbook. We
    # still want a history row for the audit trail (with a populated
    # `notes` column explaining why), but the canonical row would
    # contain NULL signals across the board — exactly the audit's
    # "republish stale data as fresh" failure mode. Skip canonical;
    # keep history.
    stale_data = set()
    for ticker, data in brief.get('tickers', {}).items():
        if data.get('status') == 'NO DATA':
            continue
        if data.get('status') == 'PLAYBOOK_FAILED':
            playbook_failed.add(ticker)
        if data.get('status') == 'STALE_DAILY_DATA':
            stale_data.add(ticker)
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
            # Track B audit G.P0.4 + G.P0.5 — freshness telemetry
            'data_as_of': data.get('data_as_of'),
            'data_freshness_status': data.get('data_freshness_status'),

            # Structured playbook fields (foundation for premarket_playbook_resolver
            # outcome tracking — added 2026-05-11). The narrative `playbook`
            # text is what the trader reads; these columns are what the EOD
            # resolver walks intraday bars against to compute trigger-hit /
            # target-hit / stop-hit / EOD-pnl per recommended setup.
            'calls_trigger_price': data.get('calls_trigger_price'),
            'calls_trigger_name':  data.get('calls_trigger_name'),
            'calls_stop_price':    data.get('calls_stop_price'),
            'calls_stop_name':     data.get('calls_stop_name'),
            'calls_t1_price':      data.get('calls_t1_price'),
            'calls_t2_price':      data.get('calls_t2_price'),
            'calls_t3_price':      data.get('calls_t3_price'),
            'puts_trigger_price':  data.get('puts_trigger_price'),
            'puts_trigger_name':   data.get('puts_trigger_name'),
            'puts_stop_price':     data.get('puts_stop_price'),
            'puts_stop_name':      data.get('puts_stop_name'),
            'puts_t1_price':       data.get('puts_t1_price'),
            'puts_t2_price':       data.get('puts_t2_price'),
            'puts_t3_price':       data.get('puts_t3_price'),
            # Track B audit G.P2.11 — persist LLM-generated brief
            # commentary for audit trail. The four strings are
            # non-deterministic Gemini-Flash outputs (gcp/brief_explanations.py)
            # rendered live to Discord; pre-W7 they were discarded
            # post-render so no audit could grade what users actually
            # saw on a given morning. Persisting them locks the
            # original morning's text — replays will produce different
            # text but the original is preserved for back-audit.
            #
            # `llm_overview` and `llm_orb_explanation` are top-level on
            # `brief` (one-per-morning); `llm_analysis` and
            # `llm_playbook` are per-ticker on `data`.
            'llm_overview': brief.get('llm_overview'),
            'llm_orb_explanation': brief.get('llm_orb_explanation'),
            'llm_analysis': data.get('llm_analysis'),
            'llm_playbook': data.get('llm_playbook'),
        })

    if not rows:
        return 0

    # Step 1 — always insert into history (append-only).
    # When a ticker is stale, populate the `notes` column with a
    # human-readable explanation so a SELECT on history rows can
    # immediately distinguish "the brief ran healthy" from "the
    # brief detected staleness and skipped". Pre-W6 rows have NULL
    # notes; future stale rows will carry the gap-in-sessions
    # descriptor.
    def _row_notes(row):
        ticker = row['ticker']
        if ticker in stale_data:
            data = brief['tickers'][ticker]
            gap = data.get('freshness_gap_days')
            return (
                f"STALE_DAILY_DATA: data_as_of={data.get('data_as_of')}; "
                f"gap={gap} session(s); analysis skipped to avoid "
                f"republishing stale signals (Track B audit G.P0.4)."
            )
        if ticker in playbook_failed:
            return f"PLAYBOOK_FAILED: {brief['tickers'][ticker].get('playbook_error')}"
        return None

    history_rows = [
        {**row, 'run_kind': run_kind, 'triggered_by': triggered_by,
         'notes': _row_notes(row)}
        for row in rows
    ]
    history_df = pd.DataFrame(history_rows)
    n_hist = bulk_insert_dataframe(history_df, 'premarket_analysis_history')
    logger.info("Inserted %d rows into premarket_analysis_history (run_kind=%s)",
                n_hist, run_kind)

    # Step 2 — write to current table. Per-ticker conditional UPSERT
    # protects the canonical morning row when allow_update=False.
    # Drop PLAYBOOK_FAILED and STALE_DAILY_DATA tickers before either
    # write path; both kinds of rows have NULL signal data and would
    # corrupt the canonical row by overwriting it with stale or
    # empty values.
    skip_canonical = playbook_failed | stale_data
    canonical_rows = [r for r in rows if r['ticker'] not in skip_canonical]
    if playbook_failed:
        logger.warning(
            "Skipped premarket_analysis write for %d PLAYBOOK_FAILED "
            "ticker(s); history rows are still recorded. Failed: %s",
            len(playbook_failed), ', '.join(sorted(playbook_failed)))
    if stale_data:
        logger.warning(
            "Skipped premarket_analysis write for %d STALE_DAILY_DATA "
            "ticker(s); history rows are still recorded with notes. "
            "Stale: %s",
            len(stale_data), ', '.join(sorted(stale_data)))
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
    parser.add_argument(
        '--no-discord', action='store_true',
        help="Skip the Discord webhook POST at the end of the run. "
             "Brief still persists to premarket_analysis + "
             "premarket_analysis_history. Used by backfills and "
             "historical replays to avoid spamming the Discord channel "
             "with re-posted content. Equivalent env var: "
             "BRIEF_POST_TO_DISCORD=false. Default: post to Discord (live "
             "behavior unchanged). Implied when BRIEF_AS_OF is set "
             "(replay) — historical replays would post stale content "
             "to a real-time Discord channel.",
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

    # Resolve whether this run posts to Discord.
    #
    # BRIEF_POST_TO_DISCORD is a 3-state override env var:
    #   - `true`  → FORCE posting on; wins over everything, including
    #               the BRIEF_AS_OF replay auto-suppress. This is the
    #               "show me a historical date's brief in Discord even
    #               though it's a replay" case (used by /replay).
    #   - `false` → FORCE posting off.
    #   - unset   → no override; fall through to the rules below.
    #
    # When unset, posting is suppressed if ANY of these hold:
    #   - `--no-discord` CLI flag
    #   - `BRIEF_AS_OF` is set (historical replay — default safety, so
    #     a backtest doesn't post stale content to a live channel)
    # Otherwise (a normal live run) the brief posts.
    #
    # The persistence path (persist_to_cloud_sql) is unaffected by any
    # of this — premarket_analysis + premarket_analysis_history rows
    # are always written regardless of the Discord policy.
    post_to_discord_env = os.environ.get('BRIEF_POST_TO_DISCORD', '').lower()
    if post_to_discord_env == 'true':
        no_discord = False  # explicit force-on; wins over AS_OF auto-suppress
    else:
        no_discord = (
            args.no_discord
            or post_to_discord_env == 'false'
            or bool(os.environ.get('BRIEF_AS_OF'))
        )
    webhook_url = '' if no_discord else os.environ.get('DISCORD_WEBHOOK_URL')
    # Earnings-specific channel. The Earnings embed routes here so
    # company earnings don't drown out analytics in the main feed.
    # Falls back to the main webhook when not configured, so existing
    # deployments behave identically.
    earnings_webhook_url = (
        '' if no_discord
        else (os.environ.get('DISCORD_WEBHOOK_EARNINGS_URL') or webhook_url)
    )

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

    routed = format_discord_messages_routed(brief)
    if webhook_url:
        for i, (kind, message) in enumerate(routed, start=1):
            target = earnings_webhook_url if kind == 'earnings' else webhook_url
            try:
                send_to_discord(message, target,
                                timeout=cfg.monitor.discord_timeout)
                logger.info("sent message %d/%d to %s channel (%d embeds)",
                            i, len(routed), kind,
                            len(message.get('embeds', [])))
            except Exception:
                logger.exception("Discord post failed for message %d/%d (%s)",
                                 i, len(routed), kind)
    else:
        print("\nDISCORD_WEBHOOK_URL not set -- printing payloads only")
        for i, (kind, message) in enumerate(routed, start=1):
            print(f"\n--- payload {i}/{len(routed)} (channel={kind}) ---")
            print(json.dumps(message, indent=2))


if __name__ == '__main__':
    main()
