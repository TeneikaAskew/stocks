#!/usr/bin/env python3
"""
Pre-market brief -- Cloud Run Job triggered by Cloud Scheduler at 8:30 AM ET.

Loads latest daily data from Cloud SQL, computes Strat/FTFC classifications,
queries upcoming economic events, and sends a rich multi-embed Discord brief.
Also persists per-ticker analysis to the premarket_analysis table.
"""

import os
import sys
import json
import logging
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, date, timedelta

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
    sql = """
        SELECT ticker, earnings_date, company_name, earnings_time,
               eps_estimate, expected_move, sector, market_cap,
               is_s_p_500, stock_volume, options_volume, open_interest,
               rv_1d_last_12q,
               strategy, strike, premium, score, data_source
        FROM earnings_calendar
        WHERE earnings_date BETWEEN :start AND :end
        ORDER BY ticker, earnings_date
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
    row_prio = {'earnings_whispers': 0, 'alphavantage': 1, 'unusual_whales': 2}

    def _tier(sources: set) -> int:
        has_av = 'alphavantage' in sources
        has_uw = 'unusual_whales' in sources
        has_ew = 'earnings_whispers' in sources
        if has_av and has_uw and has_ew:
            return 1
        if has_av and has_uw:
            return 2
        if has_av and has_ew:
            return 3
        if has_uw and has_ew:   # rare: both minor sources agree, no AV
            return 4
        if has_uw:
            return 5
        if has_ew:
            return 5
        return 6   # AV only (long tail)

    def _max_non_null(rows, key):
        """Largest non-null value of `key` across a row group, or None."""
        vals = [r.get(key) for r in rows if r.get(key) is not None and not pd.isna(r.get(key))]
        return max(vals) if vals else None

    def _any_true(rows, key):
        """True if any row has the key set truthy."""
        return any(bool(r.get(key)) for r in rows)

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
        sp500 = _any_true(rows_list, 'is_s_p_500')

        earnings.append({
            'ticker': ticker,
            'date': earnings_date,
            'company_name': best.get('company_name') or '',
            'time': best.get('earnings_time') or 'unknown',
            'eps_estimate': best.get('eps_estimate'),
            'expected_move': best.get('expected_move'),
            'sector': best.get('sector') or '',
            'market_cap': mcap,
            'is_s_p_500': sp500,
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
        })

    # Sort: date → tier → SP500 first → options_volume DESC → stock_volume
    # DESC → market_cap DESC → ticker. Negative-with-fallback yields NULLS
    # LAST. SP500 truthy sorts before False/None via the int cast.
    def _neg(v):
        return -(v if v is not None else float('-inf'))

    earnings.sort(key=lambda r: (
        r['date'],
        r['tier'],
        -int(bool(r.get('is_s_p_500'))),     # True (1) sorts before False (0)
        _neg(r.get('options_volume')),
        _neg(r.get('stock_volume')),
        _neg(r.get('market_cap')),
        r['ticker'],
    ))

    # Cap at top_n AFTER the tier sort so the cut keeps the highest-quality
    # rows. ``top_n=0`` disables the cap (legacy behaviour).
    if top_n and top_n > 0:
        earnings = earnings[:top_n]

    return {'mode': mode, 'start': start, 'end': end, 'earnings': earnings}


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

    Honours `BRIEF_TICKERS` env var for one-off / replay invocations
    that focus on a specific ticker subset. Accepts comma-, semicolon-,
    or space-separated values — semicolon form is needed because
    gcloud's `--update-env-vars` uses comma as its OWN delimiter, so
    `--update-env-vars=BRIEF_TICKERS=AMD;ARM` is the only shape that
    safely passes a multi-ticker list through the gcloud CLI.

    Falls back to the config default when unset / blank.
    """
    raw = os.environ.get("BRIEF_TICKERS")
    if not raw or not raw.strip():
        return default_tickers
    # Normalize all separators to whitespace, then split.
    normalized = raw.replace(',', ' ').replace(';', ' ')
    parts = [t.strip().upper() for t in normalized.split() if t.strip()]
    return parts or default_tickers


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


def _build_earnings_embed(earnings_data: dict) -> dict:
    """Embed 4: Earnings calendar — today (weekday) or week ahead (Sunday).

    Prefers EW rows (which carry strategy, strike, premium) and falls back
    to AV/UW. Truncates to stay under Discord's 4096-char description limit.
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

    def _row_line(r):
        t_icon = time_icon.get(r.get('time'), '\u2754')
        ticker = r['ticker']
        # Tier badge: green dot for confirmed (tier 1-3), no badge for long tail
        tier = r.get('tier', 6)
        if tier == 1:
            badge = '\U0001f7e2 '   # green circle: all 3 sources
        elif tier == 2:
            badge = '\U0001f535 '   # blue circle: AV + UW (top market-movers)
        elif tier == 3:
            badge = '\U0001f7e1 '   # yellow circle: AV + EW (strategy pick)
        else:
            badge = ''
        extras = []
        if r.get('strategy'):
            extras.append(r['strategy'])
        strike = _valid_num(r.get('strike'))
        if strike is not None:
            extras.append(f'K=${strike:.0f}')
        score = _valid_num(r.get('score'))
        if score is not None:
            extras.append(f'\u2605{score:.0f}')
        # Expected move for UW-flagged tickers (tier 1 or 2)
        em = _valid_num(r.get('expected_move'))
        if em is not None and tier in (1, 2):
            extras.append(f'EM ${em:.2f}')
        if not extras:
            eps = _valid_num(r.get('eps_estimate'))
            if eps is not None:
                extras.append(f'EPS {eps:.2f}')
        if not extras and r.get('sector'):
            extras.append(str(r['sector'])[:20])
        extra_str = f' — {" | ".join(extras)}' if extras else ''
        return f'{badge}{t_icon} **{ticker}**{extra_str}'

    def _confirmed_count(day_rows):
        return sum(1 for r in day_rows if r.get('tier', 6) <= 3)

    if mode == 'weekly':
        from collections import OrderedDict
        by_date = OrderedDict()
        for r in rows:
            by_date.setdefault(r['date'], []).append(r)

        sections = []
        total_chars = 0
        PER_DAY = 10          # show top 10 per day
        for d, day_rows in by_date.items():
            day_str = d.strftime('%a %m/%d') if hasattr(d, 'strftime') else str(d)
            conf = _confirmed_count(day_rows)
            # Already sorted by (date, tier, ticker) from the loader
            header = f'\n**{day_str}** — {conf} confirmed / {len(day_rows)} total'
            lines = [header]
            for r in day_rows[:PER_DAY]:
                lines.append(_row_line(r))
            if len(day_rows) > PER_DAY:
                hidden_conf = max(0, conf - sum(1 for r in day_rows[:PER_DAY] if r.get('tier', 6) <= 3))
                if hidden_conf > 0:
                    lines.append(f'_+{len(day_rows) - PER_DAY} more ({hidden_conf} confirmed)_')
                else:
                    lines.append(f'_+{len(day_rows) - PER_DAY} more_')
            section = '\n'.join(lines)
            if total_chars + len(section) > 3800:
                sections.append('\n_... truncated_')
                break
            sections.append(section)
            total_chars += len(section)

        total = sum(len(v) for v in by_date.values())
        total_confirmed = sum(_confirmed_count(v) for v in by_date.values())
        title = f'Earnings Week Ahead — {total_confirmed} confirmed / {total} total'
        description = '\n'.join(sections).strip()
    else:
        confirmed = _confirmed_count(rows)
        title = f'Earnings Today — {confirmed} confirmed / {len(rows)} total'
        # Daily: show top 20 (already tier-sorted)
        lines = [_row_line(r) for r in rows[:20]]
        if len(rows) > 20:
            hidden_conf = max(0, confirmed - sum(1 for r in rows[:20] if r.get('tier', 6) <= 3))
            if hidden_conf > 0:
                lines.append(f'_+{len(rows) - 20} more ({hidden_conf} confirmed)_')
            else:
                lines.append(f'_+{len(rows) - 20} more_')
        description = '\n'.join(lines)

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


def format_discord_message(brief: dict) -> dict:
    """Format brief as a Discord webhook payload with up to 5 embeds."""
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

    embeds = [overview, ticker_embed, playbook, earnings, calendar]
    # Drop empty playbook embed if no tickers produced one
    if not playbook.get('fields'):
        embeds.remove(playbook)

    # Safety: drop lower-priority embeds if over Discord's 6000-char limit
    while embeds and sum(len(json.dumps(e)) for e in embeds) > MAX_EMBED_CHARS:
        logger.warning("Discord payload over %d chars, dropping %s",
                        MAX_EMBED_CHARS, embeds[-1].get('title'))
        embeds.pop()

    return {'embeds': embeds}


# ── Cloud SQL Persistence ───────────────────────────────────────────────────

def persist_to_cloud_sql(brief: dict) -> int:
    """Write premarket analysis rows to Cloud SQL premarket_analysis table."""
    try:
        from gcp.database import is_cloud_sql_configured, upsert_dataframe
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
    for ticker, data in brief.get('tickers', {}).items():
        if data.get('status') == 'NO DATA':
            continue
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

    df = pd.DataFrame(rows)
    n = upsert_dataframe(df, 'premarket_analysis', ['analysis_date', 'ticker'])
    logger.info("Upserted %d rows to premarket_analysis", n)
    return n


def send_to_discord(message: dict, webhook_url: str, timeout: int = 10):
    """Send formatted message to Discord webhook."""
    response = requests.post(webhook_url, json=message, timeout=timeout)
    response.raise_for_status()
    print(f"Discord message sent successfully (status {response.status_code})")


def main():
    webhook_url = os.environ.get('DISCORD_WEBHOOK_URL')

    cfg = load_config()
    data_dir = os.environ.get('DATA_DIR', cfg.market.data_dir)

    print("Generating pre-market brief...")
    brief = generate_premarket_brief(cfg=cfg, data_dir=data_dir)
    print(json.dumps(brief, indent=2, default=str))

    # Persist to Cloud SQL
    n = persist_to_cloud_sql(brief)
    print(f"Persisted {n} rows to premarket_analysis")

    if webhook_url:
        message = format_discord_message(brief)
        send_to_discord(message, webhook_url, timeout=cfg.monitor.discord_timeout)
    else:
        print("\nDISCORD_WEBHOOK_URL not set -- printing message only")
        message = format_discord_message(brief)
        print(json.dumps(message, indent=2))


if __name__ == '__main__':
    main()
