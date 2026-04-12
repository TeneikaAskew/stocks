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
from datetime import datetime, timedelta
from pathlib import Path

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

        # Safely extract numeric fields
        def _safe_num(val):
            if val is None or val == '':
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        records.append({
            'date': ed.strftime('%Y-%m-%d'),
            'ticker': ticker,
            'company_name': str(row.get('company', '') or ''),
            'time': str(row.get('earningsTime') or row.get('releaseTime') or ''),
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
    """Fetch and manage earnings calendar data from Unusual Whales + Earnings Whispers."""

    def __init__(self):
        self.output_dir = Path("data/earnings")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.earnings_file = self.output_dir / "earnings_calendar.json"

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

                earnings_list.append(
                    {
                        "date": earnings_date.strftime("%Y-%m-%d"),
                        "ticker": item.get("symbol", ""),
                        "company_name": item.get("full_name", ""),
                        "time": item.get("report_time", ""),  # premarket, postmarket
                        "eps_estimate": item.get("eps_mean_est"),
                        "market_cap": item.get("marketcap"),
                        "sector": item.get("sector", ""),
                        "has_options": item.get("has_options", False),
                        "expected_move": item.get("expected_move"),
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

    def save_earnings(self, earnings_df):
        """
        Save earnings data to JSON file with deduplication.
        Merges new data with existing data and removes duplicates.

        Args:
            earnings_df: DataFrame with earnings data
        """
        if earnings_df.empty:
            print("No earnings data to save")
            return

        # Load existing earnings if file exists
        if self.earnings_file.exists():
            try:
                with open(self.earnings_file, "r") as f:
                    existing_data = json.load(f)
                existing_df = pd.DataFrame(existing_data)
                print(f"Loaded {len(existing_df)} existing earnings records")

                # Combine new and existing data
                combined_df = pd.concat([existing_df, earnings_df], ignore_index=True)

                # Remove duplicates based on ticker and date
                before_dedup = len(combined_df)
                combined_df = combined_df.drop_duplicates(
                    subset=['ticker', 'date'],
                    keep='last'  # Keep the most recent fetch
                )
                after_dedup = len(combined_df)
                duplicates_removed = before_dedup - after_dedup

                print(f"Merged data: {len(existing_df)} existing + {len(earnings_df)} new = {after_dedup} total ({duplicates_removed} duplicates removed)")

                earnings_df = combined_df

            except Exception as e:
                print(f"Note: Could not load existing earnings file: {e}")
                print("Saving new data only")

        # Sort by date for easier reading
        earnings_df = earnings_df.sort_values('date').reset_index(drop=True)

        # Convert to list of dicts for JSON
        earnings_data = earnings_df.to_dict(orient="records")

        # Save to JSON file
        with open(self.earnings_file, "w") as f:
            json.dump(earnings_data, f, indent=2)

        print(f"\n{'='*80}")
        print(f"Saved {len(earnings_data)} earnings announcements to {self.earnings_file} (sorted by date)")
        print(f"{'='*80}")

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
        description="Fetch upcoming earnings calendar from Unusual Whales + Earnings Whispers"
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
        choices=["all", "uw", "ew"],
        default="all",
        help="Data source: all (default), uw (Unusual Whales only), ew (Earnings Whispers only)",
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

    # ── Unusual Whales ──
    if args.source in ("all", "uw"):
        uw_df = fetcher.fetch_unusual_whales_earnings(days_ahead=days_ahead)
        if not uw_df.empty:
            frames.append(uw_df)

    # ── Earnings Whispers ──
    if args.source in ("all", "ew"):
        ew_df = fetch_earnings_whispers()
        if not ew_df.empty:
            frames.append(ew_df)

    if not frames:
        print("\nNo earnings data fetched from any source")
        sys.exit(1)

    earnings_df = pd.concat(frames, ignore_index=True)

    # Deduplicate: prefer Earnings Whispers rows (they have strategy details)
    earnings_df = earnings_df.sort_values('source', ascending=False)  # EW before UW
    earnings_df = earnings_df.drop_duplicates(
        subset=['ticker', 'date'], keep='first'
    ).sort_values('date').reset_index(drop=True)

    # Filter by date range if specified
    if args.start_date and args.end_date:
        print(f"Filtering between {args.start_date} and {args.end_date}...")
        earnings_df = earnings_df[
            (earnings_df["date"] >= args.start_date)
            & (earnings_df["date"] <= args.end_date)
        ]
        print(f"Filtered to {len(earnings_df)} announcements")

    # Save and summarize
    fetcher.save_earnings(earnings_df)
    fetcher.print_summary(earnings_df)

    # Persist to Cloud SQL (non-fatal if not configured)
    try:
        n = persist_to_cloud_sql(earnings_df)
        if n:
            print(f"Persisted {n} rows to Cloud SQL earnings_calendar table")
    except Exception as e:
        logger.warning("Cloud SQL persist failed (non-fatal): %s", e)

    print("\n" + "=" * 80)
    print("Earnings Calendar Fetch Completed Successfully!")
    print(f"Sources: {earnings_df['source'].value_counts().to_dict()}")
    print("=" * 80)


if __name__ == "__main__":
    main()
