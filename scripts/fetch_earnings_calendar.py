#!/usr/bin/env python3
"""
Fetch upcoming earnings calendar from Unusual Whales + Earnings Whispers.

Sources:
  1. Unusual Whales — free upcoming earnings calendar (dates, tickers, EPS)
  2. Earnings Whispers — options strategy picks across 9 strategies
     (requires EW_USER / EW_PASS credentials)

The Earnings Whispers flow mirrors the Google Apps Script in
google-apps-script/src/04_Code.js: login with cookie/CSRF, then
GET each /api/get* endpoint with the session cookies.

Usage:
    python scripts/fetch_earnings_calendar.py
    python scripts/fetch_earnings_calendar.py --days 30
    python scripts/fetch_earnings_calendar.py --source all
    python scripts/fetch_earnings_calendar.py --source ew   # Earnings Whispers only
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# ── Earnings Whispers constants ──────────────────────────────────────────────

EW_BASE = 'https://www.earningswhispers.com'
EW_LOGIN_URL = f'{EW_BASE}/login'
EW_REFERRER = f'{EW_BASE}/optiontrades'

EW_STRATEGY_ENDPOINTS = {
    'Long Calls':    '/api/getlongcalls',
    'Long Puts':     '/api/getlongput',
    'Short Puts':    '/api/getshortput',
    'Bull Spreads':  '/api/getbullcallspread',
    'Strangles':     '/api/getshortstrangle',
    'Covered Calls': '/api/getcoveredcall',
    'Straddles':     '/api/getstraddle',
    'Short Calls':   '/api/getshortcalls',
    'Bear Spreads':  '/api/getbearputspread',
}

EW_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'


# ── Shared normalization ────────────────────────────────────────────────────

def normalize_earnings_time(val) -> str:
    """Normalize earnings release time to a consistent vocabulary.

    Earnings Whispers uses numeric codes (1=before open, 2=intraday, 3=after close).
    Unusual Whales uses lowercase strings ('premarket', 'postmarket').
    GAS `15_SuccessReport.js` lines 1560-1561 confirm: releaseTime 1→beforeOpen,
    3→afterClose. Value 2 is rare and unmapped in GAS — we treat it as 'intraday'.

    Returns one of: 'premarket', 'intraday', 'postmarket', 'unknown'
    """
    if val is None:
        return 'unknown'
    s = str(val).strip().lower()
    if s in ('', 'none', 'null', 'nan', 'unknown'):
        return 'unknown'
    # EW numeric codes
    if s == '1' or s == '1.0':
        return 'premarket'
    if s == '2' or s == '2.0':
        return 'intraday'
    if s == '3' or s == '3.0':
        return 'postmarket'
    # UW / already-normalized strings
    if s in ('premarket', 'pre-market', 'bmo', 'before open', 'beforeopen'):
        return 'premarket'
    if s in ('postmarket', 'post-market', 'amc', 'after close', 'afterclose'):
        return 'postmarket'
    if s in ('intraday', 'during', 'duringmarket'):
        return 'intraday'
    return 'unknown'


# ── Shared numeric helper ───────────────────────────────────────────────────

def _safe_num(val):
    """Return float(val) or None if conversion fails / empty."""
    if val is None or val == '' or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        f = float(val)
        return None if pd.isna(f) else f
    except (ValueError, TypeError):
        return None


def _safe_int(val):
    """Return int(val) or None — tolerates UW's numeric-string fields
    ("281404632") and floats with trailing zeros."""
    f = _safe_num(val)
    if f is None:
        return None
    try:
        return int(f)
    except (ValueError, TypeError, OverflowError):
        return None


# ── AV date attach helper ───────────────────────────────────────────────────

def _attach_av_date(df: pd.DataFrame, av_dates: dict) -> int:
    """Attach AV's date-of-truth as a separate column without mutating the
    source-reported earnings_date.

    Adds an `av_earnings_date` column populated only for tickers that also
    appear in the AV fetch. EW/UW keep their own dates for traceability —
    consumers can compare the two and flag discrepancies downstream.

    Returns the number of rows that got an AV date attached.
    """
    if df.empty:
        df['av_earnings_date'] = None
        return 0

    count = 0
    av_col = []
    for idx in df.index:
        ticker = df.at[idx, 'ticker']
        if ticker in av_dates:
            av_col.append(av_dates[ticker][0])
            count += 1
        else:
            av_col.append(None)
    df['av_earnings_date'] = av_col
    return count


# ── AlphaVantage earnings calendar (source of truth for dates) ──────────────

def fetch_alphavantage_earnings(horizon: str = '3month') -> pd.DataFrame:
    """Fetch AlphaVantage EARNINGS_CALENDAR (CSV) as the date-of-truth source.

    AV pulls from SEC filings so its reportDate is authoritative. We use this
    to override EW and UW dates when they disagree. Returns a DataFrame with
    the common earnings_calendar schema.
    """
    api_key = os.environ.get('AV_API_KEY') or os.environ.get('ALPHA_VANTAGE_API_KEY', '')
    if not api_key:
        logger.info("AV_API_KEY / ALPHA_VANTAGE_API_KEY not set — skipping AV earnings")
        return pd.DataFrame()

    url = 'https://www.alphavantage.co/query'
    params = {'function': 'EARNINGS_CALENDAR', 'horizon': horizon, 'apikey': api_key}
    logger.info("Fetching AV earnings calendar (horizon=%s)...", horizon)

    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
    except requests.RequestException as e:
        logger.warning("AV request failed: %s", e)
        return pd.DataFrame()

    text = (r.text or '').strip()
    if not text:
        logger.warning("AV earnings returned empty body")
        return pd.DataFrame()

    # AV returns JSON error envelopes or "Information"/"Error Message" strings
    # when rate-limited or key invalid, instead of CSV
    lower_head = text[:200].lower()
    if text.startswith('{') or 'error message' in lower_head or 'information' in lower_head or 'rate limit' in lower_head:
        logger.warning("AV earnings returned non-CSV response: %s", text[:200])
        return pd.DataFrame()

    from io import StringIO
    try:
        df = pd.read_csv(StringIO(text))
    except Exception as e:
        logger.warning("AV CSV parse failed: %s", e)
        return pd.DataFrame()

    if df.empty or 'symbol' not in df.columns or 'reportDate' not in df.columns:
        logger.warning("AV CSV missing expected columns, got: %s", list(df.columns))
        return pd.DataFrame()

    logger.info("AV returned %d earnings announcements", len(df))

    records = []
    for _, row in df.iterrows():
        try:
            rd = pd.to_datetime(row['reportDate'], errors='coerce')
            if pd.isna(rd):
                continue
            ticker = str(row.get('symbol', '')).upper().strip()
            if not ticker or len(ticker) > 10:
                continue
            records.append({
                'date': rd.strftime('%Y-%m-%d'),
                'ticker': ticker,
                'company_name': str(row.get('name', '') or ''),
                'time': normalize_earnings_time(row.get('timeOfTheDay')),
                'eps_estimate': _safe_num(row.get('estimate')),
                'market_cap': None,
                'sector': '',
                'has_options': None,
                'expected_move': None,
                'source': 'AlphaVantage',
                'strategy': '',
                'fetched_at': datetime.now().isoformat(),
            })
        except Exception as e:
            logger.debug("Skipping AV row: %s", e)
            continue

    result = pd.DataFrame(records)
    if not result.empty:
        result = result.drop_duplicates(subset=['ticker', 'date'], keep='last')
        result = result.sort_values('date').reset_index(drop=True)
        logger.info("AV total: %d records across %d unique tickers",
                     len(result), result['ticker'].nunique())
    return result


# ── AV HISTORICAL_OPTIONS enrichment ────────────────────────────────────────
# Sums daily option chain volume + OI per ticker so the brief's
# options_volume filter has signal for ALL earnings tickers — not only
# the ~30/day UnusualWhales covers.

def _previous_trading_weekday(d: date) -> date:
    """Most recent weekday strictly before d (ignores market holidays —
    AV returns 'No data' for those, which the caller handles)."""
    d = d - timedelta(days=1)
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return d


def _resolve_target_dates_for_av_options(scope: str) -> list:
    """Resolve the dates whose AV ∩ UW reporters should get an AV options
    refresh on this run.

    scope='weekly'  (Sunday 7 PM ET run): the upcoming Mon-Fri (5 dates).
        Snapshot date will be the previous weekday close (Friday).
    scope='daily'   (Mon-Thu 7 PM ET evening run): the next calendar
        day, only when it's a weekday AND the gap is exactly 1 day.
        Returns [] on Friday (tomorrow=Sat → no earnings) — Friday
        evening just does post-close history+reactions for today's
        reporters; Monday is handled by Sunday's weekly run.

    Returns a list of date objects (may be empty).
    """
    today = datetime.now().date()
    if scope == 'weekly':
        # Find next Monday (or today if already Monday/weekday … but the
        # weekly scope is invoked on Sunday by the scheduler).
        d = today + timedelta(days=1)
        while d.weekday() != 0:  # 0=Mon
            d += timedelta(days=1)
        return [d + timedelta(days=i) for i in range(5)]  # Mon-Fri
    # daily: only tomorrow, only if it's a weekday and gap is 1 day
    tomorrow = today + timedelta(days=1)
    if tomorrow.weekday() >= 5:
        return []
    return [tomorrow]


def _resolve_scope(cli_scope: Optional[str] = None) -> str:
    """Scope = 'weekly' on Sundays (or when overridden), else 'daily'."""
    if cli_scope in ('daily', 'weekly'):
        return cli_scope
    env = os.environ.get('PIPELINE_SCOPE', '').strip().lower()
    if env in ('daily', 'weekly'):
        return env
    return 'weekly' if datetime.now().weekday() == 6 else 'daily'
    """Most recent weekday strictly before d. Ignores market holidays —
    AV returns 'No data' for those, which the caller handles."""
    d = d - timedelta(days=1)
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return d


def fetch_av_options_summary(ticker: str, snapshot_date: str, api_key: str,
                             timeout: int = 60) -> tuple:
    """One AV HISTORICAL_OPTIONS call → (volume, open_interest, status).

    Returns
    -------
    (vol, oi, status) where status is one of:
        'has_options'   — chain returned; vol/oi are summed across contracts
        'no_options'    — AV "No data for symbol" (ticker has no listed options)
        'error:<msg>'   — rate limit, transient API failure; vol/oi are None
    """
    params = {
        'function': 'HISTORICAL_OPTIONS',
        'symbol':   ticker,
        'date':     snapshot_date,
        'apikey':   api_key,
        'datatype': 'json',
    }
    try:
        r = requests.get('https://www.alphavantage.co/query',
                         params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return (None, None, f'error:{type(e).__name__}')

    msg = data.get('message', '') or data.get('Information', '') or data.get('Note', '')
    chain = data.get('data', []) or []

    if msg == 'success' and chain:
        vol = sum(int(float(r.get('volume') or 0)) for r in chain)
        oi = sum(int(float(r.get('open_interest') or 0)) for r in chain)
        return (vol, oi, 'has_options')

    if isinstance(msg, str) and msg.startswith('No data for symbol'):
        # Positive signal: ticker exists but has no listed options.
        # Persist 0 so the brief filter drops it without re-querying.
        return (0, 0, 'no_options')

    # Rate limit, malformed key, etc. — leave NULL so next run retries.
    return (None, None, f'error:{(msg or "unknown")[:60]}')


def _load_existing_options_from_db(date_keys: set) -> dict:
    """Load existing (options_volume, open_interest) from earnings_calendar
    for the given (ticker, earnings_date) pairs.

    Returns {(ticker, earnings_date): (vol, oi)} where at least one of
    vol/oi is non-null. Pairs absent from the result either don't exist
    in the table or have both columns NULL.

    Used by enrich_with_av_options to (a) skip AV calls for already-
    populated (ticker, date) pairs and (b) hydrate today's fresh df so
    the upsert doesn't NULL-out yesterday's good values.
    """
    if not date_keys:
        return {}
    try:
        _root = str(Path(__file__).resolve().parent.parent)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from gcp.database import query_to_dataframe, is_cloud_sql_configured
    except ImportError:
        return {}
    if not is_cloud_sql_configured():
        return {}

    dates = sorted({d for _, d in date_keys})
    sql = """
        SELECT ticker, earnings_date,
               MAX(options_volume) AS options_volume,
               MAX(open_interest)  AS open_interest
        FROM earnings_calendar
        WHERE earnings_date = ANY(:dates)
          AND (options_volume IS NOT NULL OR open_interest IS NOT NULL)
        GROUP BY ticker, earnings_date
    """
    try:
        df = query_to_dataframe(sql, {'dates': dates})
    except Exception as e:
        logger.warning("DB load for AV-options skip-check failed: %s", e)
        return {}
    if df.empty:
        return {}
    out: dict = {}
    for _, r in df.iterrows():
        ed = r['earnings_date']
        if hasattr(ed, 'date'):
            ed = ed.date()
        key = (r['ticker'], ed)
        vol = int(r['options_volume']) if pd.notna(r.get('options_volume')) else None
        oi = int(r['open_interest']) if pd.notna(r.get('open_interest')) else None
        if vol is None and oi is None:
            continue
        out[key] = (vol, oi)
    return out


def enrich_with_av_options(df: pd.DataFrame, snapshot_date: str,
                           api_key: str, rpm: int = 150,
                           scope: str = 'daily',
                           target_dates_override: Optional[list] = None) -> pd.DataFrame:
    """Per-ticker AV HISTORICAL_OPTIONS enrichment.

    Pipeline:
      1. Hydrate df with existing DB (ticker, earnings_date) options
         values so the upsert later doesn't NULL-out yesterday's data.
      2. Compute the set of tickers that STILL have at least one
         (ticker, earnings_date) without options_volume in df.
      3. Call AV once per ticker in that needs-AV set (each ticker
         hits AV at most once even with many source/strategy rows).
      4. Broadcast AV results into NULL columns only — preserving
         UnusualWhales' real per-row values and the DB-hydrated values.

    Tickers whose AV call returns 'error:...' are left NULL so the
    next scheduled run can retry.
    """
    if df.empty or 'ticker' not in df.columns:
        return df

    df = df.copy()
    if 'options_volume' not in df.columns:
        df['options_volume'] = None
    if 'open_interest' not in df.columns:
        df['open_interest'] = None

    # 1) Hydrate from DB for every (ticker, earnings_date) in df.
    date_col = 'date' if 'date' in df.columns else 'earnings_date'

    def _to_date(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        if hasattr(v, 'date'):
            return v.date()
        if isinstance(v, str):
            try:
                return datetime.strptime(v[:10], '%Y-%m-%d').date()
            except ValueError:
                return None
        return v

    pairs_in_df = {
        (r['ticker'], _to_date(r[date_col]))
        for _, r in df.iterrows()
        if r.get('ticker') and r.get(date_col) is not None
    }
    db_existing = _load_existing_options_from_db(pairs_in_df)
    if db_existing:
        logger.info("AV options enrichment: hydrated %d (ticker,date) pairs from DB",
                    len(db_existing))

        # Overwrite every row's options_volume/open_interest with the
        # canonical (DB-stored, AV-chain-sum) value for that (ticker,
        # date). This replaces UW's per-strategy contract counts and
        # EW's NULL placeholders with the chain-wide aggregate so every
        # row in the DB carries the same per-(ticker, date) value.
        def _hydrate(row, key, idx):
            v = db_existing.get((row['ticker'], _to_date(row[date_col])))
            if v is not None and v[idx] is not None:
                return v[idx]
            return row[key]

        df['options_volume'] = df.apply(lambda r: _hydrate(r, 'options_volume', 0), axis=1)
        df['open_interest']  = df.apply(lambda r: _hydrate(r, 'open_interest', 1), axis=1)

    # 2) Narrow the enrichment universe to AV ∩ UW tickers reporting
    #    on the target date(s) for this run's scope:
    #      - 'daily' (Mon-Thu 7 PM ET): tomorrow only (so the next-day
    #        brief reads tomorrow's reporters with TODAY's close snapshot).
    #        Friday returns [] (Sat doesn't trade; Mon prep is Sunday's job).
    #      - 'weekly' (Sun 7 PM ET): the full upcoming Mon-Fri.
    #
    # Tickers outside AV ∩ UW are dropped entirely — the brief filter
    # wouldn't surface them anyway, so calling AV is wasted work.
    target_dates = set(target_dates_override or _resolve_target_dates_for_av_options(scope))
    src_col = 'source' if 'source' in df.columns else 'data_source'
    av_aliases = {'alphavantage', 'AlphaVantage'}
    uw_aliases = {'unusual_whales', 'UnusualWhales'}
    needs_av: set = set()
    av_uw_in_target: set = set()
    for ticker, grp in df.groupby('ticker'):
        sources = set(grp[src_col].dropna().astype(str).unique())
        if not (sources & av_aliases and sources & uw_aliases):
            continue
        # Reports in target window?
        ticker_dates = {_to_date(ed) for ed in grp[date_col].dropna().unique()}
        if ticker_dates & target_dates:
            av_uw_in_target.add(ticker)
            needs_av.add(ticker)

    total_tickers = df['ticker'].nunique()
    tickers = sorted(needs_av)
    non_av_uw = total_tickers - sum(
        1 for t, g in df.groupby('ticker')
        if (set(g[src_col].dropna().astype(str).unique()) & av_aliases) and
           (set(g[src_col].dropna().astype(str).unique()) & uw_aliases)
    )
    logger.info(
        "AV options enrichment [scope=%s]: %d AV∩UW tickers reporting in "
        "target_dates=%s on snapshot=%s (rpm=%d); dropped %d non-AV∩UW, "
        "%d AV∩UW outside target window",
        scope, len(tickers),
        sorted(d.isoformat() for d in target_dates),
        snapshot_date, rpm, non_av_uw,
        total_tickers - non_av_uw - len(av_uw_in_target),
    )
    if not tickers:
        return df

    # 3) One AV call per ticker.
    delay_s = 60.0 / max(rpm, 1)
    results: dict = {}
    counters = {'has_options': 0, 'no_options': 0, 'error': 0}
    for i, t in enumerate(tickers, 1):
        vol, oi, status = fetch_av_options_summary(t, snapshot_date, api_key)
        results[t] = (vol, oi, status)
        bucket = 'has_options' if status == 'has_options' else (
                 'no_options' if status == 'no_options' else 'error')
        counters[bucket] += 1
        if i % 50 == 0 or i == len(tickers):
            logger.info("  AV options: %d/%d  has=%d no=%d err=%d",
                        i, len(tickers),
                        counters['has_options'], counters['no_options'],
                        counters['error'])
        time.sleep(delay_s)

    # 4) Broadcast AV chain sum onto every row for the ticker —
    #    overwrites UW per-strategy contract counts and EW NULLs.
    #    Only AV "error:..." responses (None, None) are left as-is so a
    #    transient rate-limit doesn't blow away an existing value.
    def _fill(row, key, idx):
        new = results.get(row['ticker'], (None, None, ''))[idx]
        if new is not None:
            return new
        return row[key]

    df['options_volume'] = df.apply(lambda r: _fill(r, 'options_volume', 0), axis=1)
    df['open_interest']  = df.apply(lambda r: _fill(r, 'open_interest', 1), axis=1)

    logger.info("AV options enrichment complete: has=%d no=%d err=%d "
                "(dropped %d non-AV∩UW, skipped %d already-populated)",
                counters['has_options'], counters['no_options'],
                counters['error'], non_av_uw, skipped_future)
    return df


# ── Earnings Whispers auth + fetch ───────────────────────────────────────────

def _ew_extract_csrf(html: str) -> str:
    """Extract CSRF token from the login page HTML (mirrors GAS EW_extractCsrf)."""
    patterns = [
        r'<meta\s+name=["\']?csrf-token["\']?\s+content=["\']?([^"\'\s>]+)',
        r'<input[^>]+name=["\']?_token["\']?[^>]+value=["\']?([^"\'\s>]+)',
        r'<input[^>]+name=["\']?__RequestVerificationToken["\']?[^>]+value=["\']?([^"\'\s>]+)',
        r'name=["\']?_token["\']?[^>]+value=["\']?([^"\'\s>]+)',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            return m.group(1)
    return ''


def ew_login(user: str, password: str) -> requests.Session:
    """Authenticate to Earnings Whispers and return a requests.Session.

    Mirrors the 3-step flow in google-apps-script/src/04_Code.js EW_login():
      1. GET /login → collect cookies + CSRF token
      2. POST /login with Email/Password → collect session cookies
      3. Follow redirect if present → collect final cookies
    """
    session = requests.Session()
    session.headers.update({'User-Agent': EW_USER_AGENT})

    # Step 1: GET login page
    r1 = session.get(EW_LOGIN_URL, allow_redirects=False, timeout=15)
    if r1.status_code >= 400:
        raise RuntimeError(f"EW login page returned HTTP {r1.status_code}")
    csrf = _ew_extract_csrf(r1.text)
    logger.info("EW login step 1: status=%d, csrf=%s", r1.status_code,
                'found' if csrf else 'none')

    # Step 2: POST credentials
    payload = {'Email': user, 'Password': password}
    if csrf:
        payload['__RequestVerificationToken'] = csrf

    r2 = session.post(
        EW_LOGIN_URL,
        data=payload,
        allow_redirects=False,
        timeout=15,
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': EW_BASE,
            'Referer': EW_LOGIN_URL,
        },
    )
    logger.info("EW login step 2: status=%d", r2.status_code)

    # 500 is common — EW sometimes returns 500 but the antiforgery cookie
    # is still valid enough for the API endpoints to work.  Only fail hard
    # on explicit auth-failure redirects.

    # Step 3: follow redirect if 3xx
    if 300 <= r2.status_code < 400:
        loc = r2.headers.get('Location', '')
        if loc and ('doh' in loc or 'error' in loc or 'failed' in loc):
            raise RuntimeError(f"EW login failed, redirect to {loc}")
        if loc:
            redir_url = loc if loc.startswith('http') else f'{EW_BASE}{loc}'
            r3 = session.get(redir_url, timeout=15)
            logger.info("EW login step 3: redirect to %s, status=%d",
                        redir_url, r3.status_code)

    # Validate: check for auth-ish cookies
    cookie_names = [c.name for c in session.cookies]
    has_auth = any(
        kw in name.lower()
        for name in cookie_names
        for kw in ('auth', 'session', 'login', 'token')
    )
    if not has_auth and len(cookie_names) < 2:
        logger.warning("EW login may have failed — no auth cookies found: %s",
                        cookie_names)

    logger.info("EW login complete, %d cookies", len(cookie_names))
    return session


def ew_fetch_strategy(session: requests.Session, path: str) -> list[dict]:
    """Fetch one strategy endpoint and return list of row dicts.

    Mirrors GAS EW_fetchJson + EW_jsonToRows.  Returns [] on any error
    or empty response so the caller can continue with other strategies.
    """
    url = f'{EW_BASE}{path}'
    try:
        r = session.get(url, timeout=20, headers={
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': EW_REFERRER,
        })
    except requests.RequestException as e:
        logger.warning("EW %s request failed: %s", path, e)
        return []

    if r.status_code >= 400:
        logger.warning("EW %s returned HTTP %d", path, r.status_code)
        return []

    text = (r.text or '').strip()
    if not text:
        logger.info("EW %s returned empty body", path)
        return []

    if text.startswith('<!DOCTYPE') or text.startswith('<html'):
        logger.warning("EW %s returned HTML (auth issue or no data)", path)
        return []

    try:
        data = r.json()
    except ValueError:
        logger.warning("EW %s JSON parse error, body starts: %s",
                        path, text[:120])
        return []

    # Endpoint returned valid JSON but it could be null, empty, or unexpected
    if data is None:
        return []

    # Normalize — same logic as GAS EW_jsonToRows
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        if 'data' in data and isinstance(data['data'], list):
            return [row for row in data['data'] if isinstance(row, dict)]
        if 'rows' in data and 'headers' in data:
            headers = data['headers']
            return [dict(zip(headers, row)) for row in data['rows']
                    if isinstance(row, (list, tuple))]
        return [data]
    return []


def fetch_earnings_whispers(user: str = None, password: str = None) -> pd.DataFrame:
    """Fetch all 9 EW strategy endpoints and return a unified DataFrame.

    Each row represents one options trade recommendation with earnings context.
    """
    user = user or os.environ.get('EW_USER', '')
    password = password or os.environ.get('EW_PASS', '')

    if not user or not password:
        logger.info("EW_USER/EW_PASS not set — skipping Earnings Whispers")
        return pd.DataFrame()

    try:
        session = ew_login(user, password)
    except Exception as e:
        logger.error("EW login failed: %s", e)
        return pd.DataFrame()

    all_rows = []
    for strategy_name, path in EW_STRATEGY_ENDPOINTS.items():
        try:
            rows = ew_fetch_strategy(session, path)
            logger.info("EW %s: %d rows", strategy_name, len(rows))
            for row in rows:
                row['_strategy'] = strategy_name
            all_rows.extend(rows)
        except Exception as e:
            logger.warning("EW %s failed: %s", strategy_name, e)
        # Small delay between endpoints (mirrors GAS Utilities.sleep(300))
        import time as _time
        _time.sleep(0.3)

    if not all_rows:
        logger.warning("EW returned 0 total rows across all strategies")
        return pd.DataFrame()

    # Normalize to earnings calendar format
    records = []
    for row in all_rows:
        if not isinstance(row, dict):
            continue

        # Extract earnings date — EW uses multiple field names across strategies
        earnings_date = (
            row.get('earningsDate') or row.get('nextEPSDate')
            or row.get('date') or ''
        )
        # Some endpoints return empty string or None
        if not earnings_date or str(earnings_date).strip() in ('', 'None', 'null'):
            continue

        # Parse date — handle YYYY-MM-DD, datetime strings, timestamps
        try:
            ed_str = str(earnings_date).strip()
            if 'T' in ed_str or ' ' in ed_str:
                ed = pd.to_datetime(ed_str, errors='coerce')
                if pd.isna(ed):
                    continue
                ed = ed.date()
            else:
                ed = datetime.strptime(ed_str[:10], '%Y-%m-%d').date()
        except (ValueError, TypeError, IndexError):
            continue

        ticker = row.get('ticker') or row.get('symbol') or ''
        ticker = str(ticker).upper().strip()
        if not ticker or len(ticker) > 10:
            continue

        records.append({
            'date': ed.strftime('%Y-%m-%d'),
            'ticker': ticker,
            'company_name': str(row.get('company', '') or ''),
            'time': normalize_earnings_time(
                row.get('earningsTime') or row.get('releaseTime')
            ),
            'eps_estimate': None,
            'market_cap': None,
            'sector': '',
            'has_options': True,
            'expected_move': _safe_num(row.get('avgEPSMove')),
            'source': 'EarningsWhispers',
            'strategy': row.get('_strategy', ''),
            'strike': _safe_num(row.get('strike')),
            'expiration': str(row.get('expiration') or row.get('expDate') or ''),
            'premium': _safe_num(row.get('premium') or row.get('lastTrade')),
            'score': _safe_num(row.get('score')),
            'fetched_at': datetime.now().isoformat(),
        })

    if not records:
        logger.warning("EW: no parseable records from %d raw rows", len(all_rows))
        return pd.DataFrame()

    result = pd.DataFrame(records)
    result = result.drop_duplicates(subset=['ticker', 'date', 'strategy'], keep='last')
    result = result.sort_values('date').reset_index(drop=True)
    logger.info("EW total: %d records across %d unique tickers",
                 len(result), result['ticker'].nunique())
    return result


# ── Yahoo Finance (independent date source via yfinance) ────────────────────

# Yahoo's Timing column comes from the bulk Calendars API. Map to our vocab:
#   BMO = Before Market Open       → premarket
#   AMC = After Market Close       → postmarket
#   TAS = Time As Stated (reported)→ derived from the timestamp hour
#   TNS = Time Not Supplied        → unknown
_YH_TIMING = {'BMO': 'premarket', 'AMC': 'postmarket', 'TNS': 'unknown'}


def _yahoo_time_from_ts(ts) -> str:
    """Map a yfinance timestamp to our earnings_time vocab.

    yfinance returns a tz-aware Timestamp. Convert to ET first since
    Yahoo's bulk API returns UTC timestamps; the per-ticker
    get_earnings_dates already returns ET. Then bucket by hour:
        hour < 9   → premarket  (Yahoo BMO is typically 06:00–08:00 ET)
        hour >= 16 → postmarket (Yahoo AMC is typically 16:00–17:00 ET)
        else       → intraday   (TNS shows as 12:00 noon)
    """
    try:
        if ts.tz is not None and str(ts.tz).upper() != 'US/EASTERN':
            ts = ts.tz_convert('US/Eastern')
        h = ts.hour
    except AttributeError:
        return 'unknown'
    if h < 9:
        return 'premarket'
    if h >= 16:
        return 'postmarket'
    return 'intraday'


def _yahoo_time_from_row(timing: str, ts) -> str:
    """Map (Timing, Event Start Date) from the bulk Calendars row.

    Yahoo's `Timing` column carries the BMO/AMC/TNS/TAS marker. For TAS
    rows ("Time As Stated" — already reported), the marker is just a
    label, not a time bucket — fall through to hour-based inference.
    """
    if timing in _YH_TIMING:
        return _YH_TIMING[timing]
    return _yahoo_time_from_ts(ts)


def _fetch_yahoo_bulk(start_date, end_date, page_size: int = 100,
                     max_pages: int = 30) -> pd.DataFrame:
    """Fetch the entire Yahoo earnings calendar across [start, end] in one
    paginated call set, returning a DataFrame in our common schema.

    Uses ``yfinance.Calendars.get_earnings_calendar`` (added in yfinance
    1.2+) which calls Yahoo's bulk earnings endpoint — one HTTP request
    per page of 100 tickers, no rate-limiting risk vs the per-ticker path.

    Limitations: Yahoo's bulk API doesn't surface "today's after-close
    events that haven't happened yet" — those need the per-ticker
    ``Ticker.calendar`` fallback. ~3000 tickers/day across all reports
    so 30 pages is enough headroom for a 2-3 week window.
    """
    try:
        from yfinance import Calendars
    except ImportError:
        logger.info("yfinance.Calendars not available (need yfinance >= 1.2); "
                    "skipping bulk Yahoo earnings")
        return pd.DataFrame()

    from datetime import date as _date
    sd = (datetime.strptime(start_date, '%Y-%m-%d').date()
          if isinstance(start_date, str) else start_date)
    ed = (datetime.strptime(end_date, '%Y-%m-%d').date()
          if isinstance(end_date, str) else end_date)
    if not isinstance(sd, _date) or not isinstance(ed, _date):
        logger.warning("_fetch_yahoo_bulk: invalid date args sd=%s ed=%s", sd, ed)
        return pd.DataFrame()

    # Yahoo's bulk API returns 0 rows on single-day calls (observed behavior).
    # Force at least a 2-day window — duplicates are filtered downstream.
    if sd == ed:
        ed = sd + timedelta(days=1)

    logger.info("Fetching Yahoo bulk earnings calendar %s..%s...", sd, ed)
    pages = []
    try:
        cal = Calendars(start=sd.strftime('%Y-%m-%d'),
                        end=ed.strftime('%Y-%m-%d'))
        for offset in range(0, max_pages * page_size, page_size):
            page = cal.get_earnings_calendar(
                filter_most_active=False,
                limit=page_size,
                offset=offset,
                force=True,
            )
            if page is None or page.empty:
                break
            pages.append(page)
            if len(page) < page_size:
                break
    except Exception as e:
        logger.warning("Yahoo bulk fetch failed at offset=%s: %s",
                       offset if 'offset' in locals() else 0,
                       type(e).__name__)
        if not pages:
            return pd.DataFrame()

    if not pages:
        logger.warning("Yahoo bulk: 0 pages returned for %s..%s", sd, ed)
        return pd.DataFrame()

    combined = pd.concat(pages)
    # Yahoo schema flips between releases — normalize column names.
    cap_col = next((c for c in ('Marketcap', 'Market Cap (Intraday)',
                                'Market Cap', 'Marketcap (Intraday)')
                    if c in combined.columns), None)
    company_col = next((c for c in ('Company', 'Company Name')
                        if c in combined.columns), None)
    surprise_col = next((c for c in ('Surprise(%)', 'Surprise (%)',
                                     'EPS Surprise(%)')
                         if c in combined.columns), None)

    records = []
    for sym, row in combined.iterrows():
        try:
            esd = row.get('Event Start Date')
            if esd is None or pd.isna(esd):
                continue
            ts = pd.Timestamp(esd)
            d = ts.date()
        except Exception:
            continue
        if d < sd or d > ed:
            continue
        # Beat/miss enrichment: Yahoo's TAS rows have Reported EPS +
        # Surprise(%); upcoming/scheduled rows leave them None.
        records.append({
            'date': d.strftime('%Y-%m-%d'),
            'ticker': str(sym).upper(),
            'company_name': str(row.get(company_col, '') or '') if company_col else '',
            'time': _yahoo_time_from_row(row.get('Timing', ''), ts),
            'eps_estimate': _safe_num(row.get('EPS Estimate')),
            'eps_actual': _safe_num(row.get('Reported EPS')),
            'eps_surprise_pct': (_safe_num(row.get(surprise_col))
                                 if surprise_col else None),
            'market_cap': _safe_num(row.get(cap_col)) if cap_col else None,
            'sector': '',
            'has_options': None,
            'expected_move': None,
            'source': 'Yahoo',
            'strategy': '',
            'fetched_at': datetime.now().isoformat(),
        })

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df = df.drop_duplicates(subset=['ticker', 'date'], keep='last')
    df = df.sort_values('date').reset_index(drop=True)
    logger.info("Yahoo bulk total: %d records / %d unique tickers across "
                "%s..%s", len(df), df['ticker'].nunique(), sd, ed)
    return df


def _fetch_yahoo_one(ticker: str, start_date, end_date, limit: int = 8):
    """Fetch one ticker's earnings dates from Yahoo via yfinance.

    Returns a list of normalized record dicts (may be empty). Catches all
    exceptions because yfinance raises noisy KeyErrors on tickers Yahoo
    doesn't have data for, which is normal at the long tail.

    Uses TWO yfinance APIs because they cover different windows:
      - ``get_earnings_dates()`` returns *past + as-of* earnings (last 25
        rows). It picks up names that reported within the current day
        (e.g. SBUX AMC yesterday) but NOT future-but-scheduled events.
      - ``calendar`` returns the SINGLE next upcoming earnings date. This
        is what we need for tonight's AMC names (AMZN, MSFT, GOOG, etc.)
        before the report drops — the very case Yahoo cross-confirmation
        was added to fix.

    One retry with backoff on transient errors — Yahoo throttles aggressive
    parallel fetching, returning 429s or empty bodies that bubble up as
    KeyError. A single 1.5s pause is enough for the cookie/crumb cycle to
    recover most of the time.
    """
    try:
        import yfinance as yf
    except ImportError:
        return []

    import time as _time
    yf_ticker = None
    for attempt in (0, 1):
        try:
            yf_ticker = yf.Ticker(ticker)
            break
        except Exception:
            if attempt == 0:
                _time.sleep(1.5)
                continue
            return []
    if yf_ticker is None:
        return []

    records = []
    seen_dates: set = set()  # avoid double-emitting if calendar agrees with get_earnings_dates

    # ── Path 1: past + current-day reports ───────────────────────────────
    try:
        ed = yf_ticker.get_earnings_dates(limit=limit)
    except Exception as e:
        logger.debug("Yahoo %s get_earnings_dates: %s", ticker, type(e).__name__)
        ed = None

    if ed is not None and not ed.empty:
        for ts, row in ed.iterrows():
            try:
                d = ts.date() if hasattr(ts, 'date') else None
            except Exception:
                continue
            if d is None or d < start_date or d > end_date:
                continue
            seen_dates.add(d)
            eps = row.get('EPS Estimate')
            # Per-ticker get_earnings_dates returns 'Reported EPS' +
            # 'Surprise(%)' for past rows (already-reported names).
            actual = row.get('Reported EPS')
            surprise = row.get('Surprise(%)')
            records.append({
                'date': d.strftime('%Y-%m-%d'),
                'ticker': ticker,
                'company_name': '',
                'time': _yahoo_time_from_ts(ts),
                'eps_estimate': _safe_num(eps),
                'eps_actual': _safe_num(actual),
                'eps_surprise_pct': _safe_num(surprise),
                'market_cap': None,
                'sector': '',
                'has_options': None,
                'expected_move': None,
                'source': 'Yahoo',
                'strategy': '',
                'fetched_at': datetime.now().isoformat(),
            })

    # ── Path 2: upcoming-not-yet-reported via Ticker.calendar ────────────
    # The reason Yahoo cross-confirmation matters: tonight's mega-cap AMC
    # reporters are scheduled but not yet "as-of," so get_earnings_dates
    # omits them. calendar fills the gap. We accept time='unknown' here
    # because calendar doesn't surface BMO/AMC — UW provides that.
    try:
        cal = yf_ticker.calendar
    except Exception:
        cal = None

    if isinstance(cal, dict):
        cal_dates = cal.get('Earnings Date') or cal.get('earningsDate') or []
        if not isinstance(cal_dates, (list, tuple)):
            cal_dates = [cal_dates]
        eps_avg = cal.get('Earnings Average')
        for cd in cal_dates:
            try:
                if hasattr(cd, 'date'):
                    d = cd.date()
                elif isinstance(cd, datetime):
                    d = cd.date()
                else:
                    d = cd  # assume already a date
            except Exception:
                continue
            if d is None or d < start_date or d > end_date:
                continue
            if d in seen_dates:
                continue
            records.append({
                'date': d.strftime('%Y-%m-%d'),
                'ticker': ticker,
                'company_name': '',
                'time': 'unknown',  # calendar doesn't carry BMO/AMC
                'eps_estimate': _safe_num(eps_avg),
                'market_cap': None,
                'sector': '',
                'has_options': None,
                'expected_move': None,
                'source': 'Yahoo',
                'strategy': '',
                'fetched_at': datetime.now().isoformat(),
            })

    return records


def fetch_yahoo_earnings(start_date, end_date) -> pd.DataFrame:
    """Fetch Yahoo Finance's earnings calendar for [start, end].

    Uses Yahoo's bulk earnings endpoint via ``yfinance.Calendars`` — one
    paginated API call set covers the entire window. The bulk response
    already carries Reported EPS + Surprise(%) for filed rows, so the
    previous per-ticker fill path was redundant for our 7-day window
    and the OOM cause when iterating thousands of long-tail names.

    Yahoo is the third independent date source (alongside AV and UW).
    AV's date is wrong for ~20% of SP500 names (SBUX, V, STX, EA, FSLR).
    Yahoo confirmation promotes those rows from tier 5 (UW alone) to
    tier 2 in the brief.

    Returns:
        DataFrame matching the common earnings_calendar schema with
        ``source='Yahoo'``. Empty if yfinance is unavailable.
    """
    try:
        import yfinance  # noqa: F401  (probe)
    except ImportError:
        logger.info("yfinance not installed — skipping Yahoo earnings")
        return pd.DataFrame()

    bulk = _fetch_yahoo_bulk(start_date, end_date)
    if not bulk.empty:
        logger.info("Yahoo total: %d records / %d unique tickers",
                    len(bulk), bulk['ticker'].nunique())
    return bulk


def persist_to_cloud_sql(df: pd.DataFrame) -> int:
    """Write earnings calendar DataFrame to Cloud SQL earnings_calendar table.

    Returns the number of rows upserted, or 0 if Cloud SQL is not configured.
    """
    if df.empty:
        return 0

    try:
        _root = str(Path(__file__).resolve().parent.parent)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from gcp.database import upsert_dataframe, is_cloud_sql_configured
    except ImportError:
        logger.info("gcp.database not available — skipping Cloud SQL persist")
        return 0

    if not is_cloud_sql_configured():
        logger.info("Cloud SQL not configured — skipping persist")
        return 0

    # Map JSON column names → DB column names
    db_df = df.copy()
    db_df = db_df.rename(columns={
        'date': 'earnings_date',
        'time': 'earnings_time',
    })

    # Normalize data_source values
    source_map = {
        'UnusualWhales': 'unusual_whales',
        'EarningsWhispers': 'earnings_whispers',
        'AlphaVantage': 'alphavantage',
        'Yahoo': 'yahoo',
    }
    if 'source' in db_df.columns:
        db_df['data_source'] = db_df['source'].map(source_map).fillna(db_df['source'])
        db_df = db_df.drop(columns=['source'], errors='ignore')
    elif 'data_source' not in db_df.columns:
        db_df['data_source'] = 'unknown'

    # Fill missing strategy with empty string (required for unique constraint)
    db_df['strategy'] = db_df['strategy'].fillna('').astype(str) if 'strategy' in db_df.columns else ''

    # Convert fetched_at to timestamp
    if 'fetched_at' in db_df.columns:
        db_df['fetched_at'] = pd.to_datetime(db_df['fetched_at'], errors='coerce')

    # Convert earnings_date to date type, drop rows with invalid dates
    if 'earnings_date' in db_df.columns:
        db_df['earnings_date'] = pd.to_datetime(db_df['earnings_date'], errors='coerce')
        db_df = db_df.dropna(subset=['earnings_date'])
        db_df['earnings_date'] = db_df['earnings_date'].dt.date

    # Convert expiration to date if present, replace NaT with None
    if 'expiration' in db_df.columns:
        db_df['expiration'] = pd.to_datetime(db_df['expiration'], errors='coerce')
        db_df['expiration'] = db_df['expiration'].where(db_df['expiration'].notna(), None)
        db_df['expiration'] = db_df['expiration'].apply(
            lambda x: x.date() if pd.notna(x) else None
        )

    # Convert av_earnings_date to date type (NULL-safe)
    if 'av_earnings_date' in db_df.columns:
        db_df['av_earnings_date'] = pd.to_datetime(db_df['av_earnings_date'], errors='coerce')
        db_df['av_earnings_date'] = db_df['av_earnings_date'].apply(
            lambda x: x.date() if pd.notna(x) else None
        )

    # JSONB columns need JSON strings, not Python lists/dicts — pg8000
    # rejects raw lists when the column is JSONB. Convert before NaN scrub
    # (json.dumps(None) is the literal string "null", which we don't want;
    # do it conditionally).
    import json as _json
    if 'last_1d_reactions' in db_df.columns:
        db_df['last_1d_reactions'] = db_df['last_1d_reactions'].apply(
            lambda v: _json.dumps(v) if isinstance(v, (list, dict)) else v
        )

    # BIGINT columns: pandas widens to float64 when one source provides
    # ints (UW: stock_volume) and another provides NULL (Yahoo: no
    # stock_volume) and the two are concat'd. The float values then
    # serialize as "31193563.0" — Postgres rejects that for BIGINT with
    # 22P02 (invalid input syntax). Coerce to plain Python int (None
    # passthrough) so pg8000 sees an integer literal.
    #
    # Important: build via list comprehension and re-wrap as an
    # object-dtype Series. A bare `.apply(lambda)` returns ints+None
    # but pandas infers the original float64 dtype back on the
    # assignment, undoing the coercion.
    for col in ('stock_volume', 'options_volume', 'open_interest'):
        if col in db_df.columns:
            coerced = [
                int(v) if (v is not None and pd.notna(v)) else None
                for v in db_df[col]
            ]
            db_df[col] = pd.Series(coerced, dtype=object, index=db_df.index)

    # Replace NaN/NaT with None across all columns so PostgreSQL gets NULL
    import numpy as np
    db_df = db_df.replace({np.nan: None, float('nan'): None})
    db_df = db_df.where(db_df.notna(), None)

    n = upsert_dataframe(
        db_df,
        'earnings_calendar',
        conflict_cols=['ticker', 'earnings_date', 'strategy', 'data_source'],
    )
    logger.info("Upserted %d rows to earnings_calendar", n)
    return n


class EarningsCalendarFetcher:
    """Fetch and manage earnings calendar data from Unusual Whales + Earnings Whispers.

    Cloud SQL (`earnings_calendar` table, written via persist_to_cloud_sql) is
    the canonical store. The legacy `data/earnings/earnings_calendar.json`
    cache was removed 2026-05-01 — no Python code in the repo read it, the
    workflow file-existence check that flagged its absence wasn't consumed
    downstream, and double-writing created drift risk between sources.
    """

    def __init__(self):
        # Intentionally no JSON output path — the canonical write is Cloud SQL.
        pass

    def fetch_unusual_whales_earnings(self, days_ahead=90):
        """
        Fetch upcoming earnings from Unusual Whales API.

        Args:
            days_ahead: Number of days ahead to fetch earnings (default: 90)

        Returns:
            pd.DataFrame: Earnings data
        """
        try:
            # Unusual Whales upcoming earnings endpoint
            # Using formats=table to get all available earnings data
            url = "https://phx.unusualwhales.com/api/companies_earnings/upcoming_earnings_v2?formats=table"

            print(f"Fetching earnings calendar from Unusual Whales...")
            print(f"URL: {url}")

            # Add headers to avoid being blocked
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json',
            }

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            if not data or "data" not in data:
                print("Warning: No earnings data found in API response")
                return pd.DataFrame()

            earnings_data = data["data"]

            if not earnings_data:
                print(f"Note: API returned 0 earnings announcements")
                print("This may be due to rate limiting or time of day.")
                print("The API typically returns data during market hours or with proper auth.")
                return pd.DataFrame()

            print(f"Fetched {len(earnings_data)} earnings announcements")

            # Parse and structure the data
            earnings_list = []
            today = datetime.now().date()
            cutoff_date = today + timedelta(days=days_ahead)

            for item in earnings_data:
                # Parse earnings date - field is 'report_date'
                earnings_date_str = item.get("report_date")
                if not earnings_date_str:
                    continue

                try:
                    # Try parsing different date formats
                    if "T" in earnings_date_str:
                        earnings_date = datetime.fromisoformat(
                            earnings_date_str.replace("Z", "+00:00")
                        ).date()
                    else:
                        earnings_date = datetime.strptime(
                            earnings_date_str, "%Y-%m-%d"
                        ).date()
                except (ValueError, AttributeError):
                    continue

                # Filter by date range
                if earnings_date > cutoff_date:
                    continue

                # UW returns numeric strings for several fields ("82.73",
                # "414846040000"); coerce to native ints/floats so downstream
                # SQL casts (BIGINT/DOUBLE PRECISION) don't choke. Helpers
                # already exist for safe numeric casting.
                call_vol = _safe_int(item.get("call_vol"))
                put_vol = _safe_int(item.get("put_vol"))
                options_vol = (call_vol + put_vol) if (call_vol is not None and put_vol is not None) else None

                earnings_list.append(
                    {
                        "date": earnings_date.strftime("%Y-%m-%d"),
                        "ticker": item.get("symbol", ""),
                        "company_name": item.get("full_name", ""),
                        "time": normalize_earnings_time(item.get("report_time")),
                        "eps_estimate": item.get("eps_mean_est"),
                        "market_cap": item.get("marketcap"),
                        "sector": item.get("sector", ""),
                        "has_options": item.get("has_options", False),
                        "expected_move": item.get("expected_move"),
                        # ── UW liquidity / quality enrichments ──────────────
                        # Map straight to the new earnings_calendar columns.
                        # Fields are 100% filled in the UW response except
                        # eps_mean_est / sector (~98%); we tolerate None.
                        "is_s_p_500": item.get("is_s_p_500"),
                        "stock_volume": _safe_int(item.get("stock_volume")),
                        "options_volume": options_vol,
                        "open_interest": _safe_int(item.get("oi")),
                        "rv_1d_last_12q": _safe_num(item.get("rv_1d_last_12q")),
                        "last_1d_reactions": item.get("last_1d_reactions"),
                        "source": "UnusualWhales",
                        "fetched_at": datetime.now().isoformat(),
                    }
                )

            df = pd.DataFrame(earnings_list)

            if not df.empty:
                df = df.sort_values("date").reset_index(drop=True)
                print(f"Processed {len(df)} earnings announcements")
                print(f"Date range: {df['date'].min()} to {df['date'].max()}")
            else:
                print("No earnings data after processing")

            return df

        except requests.exceptions.RequestException as e:
            print(f"Error fetching from Unusual Whales API: {e}")
            return pd.DataFrame()
        except Exception as e:
            print(f"Error processing earnings data: {e}")
            import traceback

            traceback.print_exc()
            return pd.DataFrame()

    def print_summary(self, earnings_df):
        """Print summary statistics of earnings data."""
        if earnings_df.empty:
            print("\nNo earnings data available")
            return

        print(f"\n{'='*80}")
        print("EARNINGS CALENDAR SUMMARY")
        print(f"{'='*80}")

        print(f"\nTotal Earnings: {len(earnings_df)}")

        # Group by date
        by_date = earnings_df.groupby("date").size()
        print(f"\nEarnings by Date:")
        for date, count in by_date.head(10).items():
            print(f"  {date}: {count} companies")

        if len(by_date) > 10:
            print(f"  ... and {len(by_date) - 10} more dates")

        # Group by sector
        if "sector" in earnings_df.columns and earnings_df["sector"].notna().any():
            by_sector = earnings_df.groupby("sector").size().sort_values(ascending=False)
            print(f"\nTop Sectors:")
            for sector, count in by_sector.head(5).items():
                if sector:
                    print(f"  {sector}: {count}")

        # Time of day breakdown
        if "time" in earnings_df.columns and earnings_df["time"].notna().any():
            by_time = earnings_df.groupby("time").size()
            print(f"\nEarnings Time:")
            for time, count in by_time.items():
                if time:
                    print(f"  {time}: {count}")

        # Upcoming earnings (next 7 days)
        today = datetime.now().date()
        next_week = today + timedelta(days=7)
        upcoming = earnings_df[
            earnings_df["date"].apply(
                lambda x: today
                <= datetime.strptime(x, "%Y-%m-%d").date()
                <= next_week
            )
        ]

        if not upcoming.empty:
            print(f"\nUpcoming Earnings (Next 7 Days): {len(upcoming)}")
            for _, row in upcoming.head(10).iterrows():
                print(
                    f"  {row['date']} ({row.get('time', 'N/A')}): {row['ticker']} - {row.get('company_name', 'N/A')}"
                )


def main():
    """Main function to fetch earnings calendar."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(levelname)-8s %(message)s',
        datefmt='%H:%M:%S',
    )

    parser = argparse.ArgumentParser(
        description="Fetch upcoming earnings calendar from AlphaVantage + Unusual Whales + Earnings Whispers"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Number of days ahead to fetch earnings (default: 90)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date for filtering (YYYY-MM-DD) - overrides --days",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date for filtering (YYYY-MM-DD) - overrides --days",
    )
    parser.add_argument(
        "--source",
        choices=["all", "uw", "ew", "av", "yh"],
        default="all",
        help="Data source: all (default), uw (Unusual Whales), ew (Earnings Whispers), av (AlphaVantage — date truth), yh (Yahoo — independent date cross-check via yfinance)",
    )
    parser.add_argument(
        "--av-horizon",
        choices=["3month", "6month", "12month"],
        default="3month",
        help="AlphaVantage earnings horizon (default: 3month)",
    )
    parser.add_argument(
        "--no-av-options-enrich",
        action="store_true",
        help="Skip AV HISTORICAL_OPTIONS enrichment (default: enabled — "
             "populates options_volume + open_interest for every earnings "
             "ticker via 1 AV call/ticker on the most recent trading day)",
    )
    parser.add_argument(
        "--av-options-snapshot-date",
        type=str,
        default="",
        help="Override snapshot date for AV options enrichment (YYYY-MM-DD). "
             "Default: previous weekday.",
    )
    parser.add_argument(
        "--scope",
        choices=["daily", "weekly"],
        default=None,
        help="Pipeline scope (overrides auto-detection from day-of-week / "
             "PIPELINE_SCOPE env var). 'daily' targets tomorrow's AV ∩ UW "
             "reporters; 'weekly' targets the next Mon-Fri (Sunday setup).",
    )

    args = parser.parse_args()

    fetcher = EarningsCalendarFetcher()
    frames = []

    # Determine days ahead
    if args.start_date and args.end_date:
        start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
        end = datetime.strptime(args.end_date, "%Y-%m-%d").date()
        days_ahead = max((end - datetime.now().date()).days, 90)
        print(f"Fetching earnings for date range: {args.start_date} to {args.end_date}")
    else:
        days_ahead = args.days
        print(f"Fetching earnings for next {days_ahead} days")

    # ── AlphaVantage (FIRST — used as date-of-truth reference, NOT override) ──
    av_dates: dict = {}  # ticker → (date, time)
    if args.source in ("all", "av"):
        av_df = fetch_alphavantage_earnings(horizon=args.av_horizon)
        if not av_df.empty:
            # AV rows: their av_earnings_date equals their own earnings_date
            av_df['av_earnings_date'] = av_df['date']
            frames.append(av_df)
            # Build lookup for attaching AV dates to EW/UW rows
            for _, row in av_df.iterrows():
                av_dates[row['ticker']] = (row['date'], row['time'])
            print(f"AV date-truth lookup built: {len(av_dates)} tickers")

    # ── Unusual Whales ──
    if args.source in ("all", "uw"):
        uw_df = fetcher.fetch_unusual_whales_earnings(days_ahead=days_ahead)
        if not uw_df.empty:
            attached = _attach_av_date(uw_df, av_dates)
            print(f"UW: tagged {attached} rows with av_earnings_date (dates preserved)")
            frames.append(uw_df)

    # ── Earnings Whispers ──
    if args.source in ("all", "ew"):
        ew_df = fetch_earnings_whispers()
        if not ew_df.empty:
            attached = _attach_av_date(ew_df, av_dates)
            print(f"EW: tagged {attached} rows with av_earnings_date (dates preserved)")
            frames.append(ew_df)

    # ── Yahoo Finance (independent date cross-check) ──
    # Bulk-only fetch via Calendars.get_earnings_calendar. Yesterday +
    # next 7 days is all the brief consumes; pulling further out
    # multiplies memory cost without adding value (the per-ticker fill
    # was the OOM cause for the daily Cloud Run Job).
    if args.source in ("all", "yh"):
        if args.start_date and args.end_date:
            yh_start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
            yh_end = datetime.strptime(args.end_date, "%Y-%m-%d").date()
        else:
            yh_start = datetime.now().date() - timedelta(days=1)
            yh_end = datetime.now().date() + timedelta(days=7)

        yh_df = fetch_yahoo_earnings(yh_start, yh_end)
        if not yh_df.empty:
            attached = _attach_av_date(yh_df, av_dates)
            print(f"Yahoo: tagged {attached} rows with av_earnings_date (dates preserved)")
            frames.append(yh_df)

    if not frames:
        print("\nNo earnings data fetched from any source")
        sys.exit(1)

    # Un-deduped frame goes to Cloud SQL — the unique key
    # (ticker, earnings_date, strategy, data_source) lets every source's row
    # coexist, which is what the brief's tier-by-source-coverage logic needs.
    all_rows_df = pd.concat(frames, ignore_index=True)

    # Filter by date range first (applies to both DB persist and JSON cache).
    # When no explicit window is given, clamp to today-1 .. today+7 — that's
    # the only window the brief reads, and it caps the per-run memory
    # footprint regardless of how many rows AV's 3-month horizon returns.
    if args.start_date and args.end_date:
        clamp_start, clamp_end = args.start_date, args.end_date
    else:
        today = datetime.now().date()
        clamp_start = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        clamp_end = (today + timedelta(days=7)).strftime("%Y-%m-%d")
    print(f"Filtering between {clamp_start} and {clamp_end}...")
    before_n = len(all_rows_df)
    all_rows_df = all_rows_df[
        (all_rows_df["date"] >= clamp_start)
        & (all_rows_df["date"] <= clamp_end)
    ]
    print(f"Filtered: {before_n} → {len(all_rows_df)} announcements (across all sources)")

    # AV HISTORICAL_OPTIONS enrichment — populates options_volume + open_interest
    # per ticker so the brief's options filter has signal for ALL earnings names,
    # not only the small subset UW covers. One AV call per unique ticker (dedup'd
    # across sources/strategies) on the most recent trading day.
    if not args.no_av_options_enrich:
        av_key = os.environ.get('ALPHA_VANTAGE_API_KEY') or os.environ.get('AV_API_KEY')
        if not av_key:
            logger.warning("ALPHA_VANTAGE_API_KEY / AV_API_KEY not set — "
                           "skipping AV options enrichment")
        else:
            scope = _resolve_scope(getattr(args, 'scope', None))
            snapshot_date = (args.av_options_snapshot_date
                             or _previous_trading_weekday(datetime.now().date())
                                 .strftime('%Y-%m-%d'))
            all_rows_df = enrich_with_av_options(
                all_rows_df, snapshot_date, av_key, scope=scope,
            )

    # Deduplicate for JSON cache: prefer EW (carries strategy) > AV > UW > Yahoo.
    # The JSON file is a human-readable summary — one row per (ticker, date)
    # is the right shape there. Cloud SQL gets the full multi-source view.
    source_priority = {'EarningsWhispers': 0, 'AlphaVantage': 1, 'UnusualWhales': 2, 'Yahoo': 3}
    earnings_df = all_rows_df.copy()
    earnings_df['_priority'] = earnings_df['source'].map(source_priority).fillna(99)
    earnings_df = earnings_df.sort_values('_priority')
    earnings_df = earnings_df.drop_duplicates(
        subset=['ticker', 'date'], keep='first'
    ).drop(columns=['_priority']).sort_values('date').reset_index(drop=True)

    # Print summary — Cloud SQL is the canonical store; the legacy JSON
    # cache was removed (no consumers, drift risk).
    fetcher.print_summary(earnings_df)

    # Persist un-deduped frame to Cloud SQL so each source lands as its own
    # row — required for the brief's per-source tier scoring.
    try:
        n = persist_to_cloud_sql(all_rows_df)
        if n:
            print(f"Persisted {n} rows to Cloud SQL earnings_calendar table")
        else:
            # 0 rows persisted is a real signal — either the input frame
            # was empty (caught by persist_to_cloud_sql's df.empty guard
            # and logged at INFO) or the upsert returned 0 (unusual).
            # Surface at WARNING so monitoring catches stale-source bugs
            # earlier than the 18-day silent-failure window observed in
            # 2026-04-12..04-30 for AV / EW persists.
            try:
                src_breakdown = all_rows_df['source'].value_counts().to_dict()
            except Exception:
                src_breakdown = {}
            logger.warning(
                "persist_to_cloud_sql returned 0 rows for input "
                "frame of %d (source breakdown=%s) — table may now "
                "be stale for one or more sources",
                len(all_rows_df), src_breakdown,
            )
    except Exception as e:
        # Don't just log the message — log the type, length of input
        # frame, and re-raise type info so 22P02 / 23505 / etc. show up
        # distinctly in Cloud Logging filters.
        try:
            src_breakdown = all_rows_df['source'].value_counts().to_dict()
        except Exception:
            src_breakdown = {}
        logger.error(
            "Cloud SQL persist failed (non-fatal): %s: %s | "
            "input rows=%d sources=%s",
            type(e).__name__, e, len(all_rows_df), src_breakdown,
        )

    print("\n" + "=" * 80)
    print("Earnings Calendar Fetch Completed Successfully!")
    print(f"Sources: {earnings_df['source'].value_counts().to_dict()}")
    print("=" * 80)


if __name__ == "__main__":
    main()
