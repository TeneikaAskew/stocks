#!/usr/bin/env python3
"""
Cloud Run Job: Fetch economic events and write to Cloud SQL.

Replaces the GitHub Actions workflow update_economic_events_calendar.yml
(the Cloud SQL write portion -- the workflow also runs analysis scripts).

Sources (all live API; no static CSV / JSON fallback):
  1. ForexFactory (preferred) -- has release times + forecast/previous values
  2. FRED API releases calendar -- US releases. The /releases/dates endpoint
     returns dates only (no times), so we apply a canonical-time lookup
     during post-processing because the underlying agencies (BLS / BEA / Fed
     / Census / ISM) publish on fixed schedules.

Scheduled by Cloud Scheduler daily at 7:00 AM ET weekdays.

Usage:
    python -m gcp.fetchers.fetch_economic_events [--source fred|forexfactory|all]
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, date, timedelta, time as dt_time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import upsert_dataframe, is_cloud_sql_configured
from lib.logging_config import setup_logging

logger = logging.getLogger(__name__)

# Known high-impact US economic events and their typical release times (ET).
# This mirrors the calendar maintained in scripts/market_events_tracker.py
# but in a format ready for Cloud SQL.
EVENT_IMPORTANCE = {
    'CPI': 'high',
    'Core CPI': 'high',
    'FOMC': 'high',
    'FOMC Minutes': 'medium',
    'NFP': 'high',
    'Non-Farm Payrolls': 'high',
    'GDP': 'high',
    'GDP Advance': 'high',
    'GDP Second': 'medium',
    'GDP Final': 'medium',
    'PCE': 'high',
    'Core PCE': 'high',
    'PPI': 'medium',
    'Retail Sales': 'medium',
    'ISM Manufacturing PMI': 'medium',
    'ISM Services PMI': 'medium',
    'Housing Starts': 'low',
    'Initial Jobless Claims': 'low',
    'Durable Goods Orders': 'medium',
    'Consumer Confidence': 'medium',
    'Michigan Consumer Sentiment': 'medium',
    'Industrial Production': 'low',
    'Existing Home Sales': 'low',
    'New Home Sales': 'low',
    'Trade Balance': 'low',
    'Treasury Auction': 'low',
}


# Canonical scheduled release times (Eastern Time). The FRED public API
# returns release dates only (release_id, release_name, date) — the time
# metadata visible on fred.stlouisfed.org isn't exposed via the REST
# endpoint. So we apply this lookup post-fetch to populate event_time.
#
# Each agency publishes on a fixed schedule decreed by the issuing body
# (BLS, BEA, Fed, Census, ISM, NAR, DOL, Conference Board). The clock
# only changes for daylight-savings transitions, which our event_time
# storage (pure time, no tz) already accommodates because the entire
# market trades on ET and downstream consumers convert as needed.
#
# Match is by case-insensitive substring on the FRED release_name. The
# first matching prefix wins, so order MORE-SPECIFIC keys before
# generic ones (e.g. "Personal Income and Outlays" before "Personal").
FRED_RELEASE_TIMES_ET: list[tuple[str, dt_time]] = [
    # Federal Reserve — afternoon
    ('FOMC',                            dt_time(14, 0)),
    ('Federal Open Market',             dt_time(14, 0)),
    ('Beige Book',                      dt_time(14, 0)),
    # 8:30 AM ET — BLS / BEA / Census / DOL releases (most common slot)
    ('Consumer Price Index',            dt_time(8, 30)),  # CPI
    ('Producer Price Index',            dt_time(8, 30)),  # PPI
    ('Employment Situation',            dt_time(8, 30)),  # NFP
    ('Gross Domestic Product',          dt_time(8, 30)),  # GDP
    ('Personal Income and Outlays',     dt_time(8, 30)),  # PCE
    ('Retail Trade',                    dt_time(8, 30)),  # Retail Sales
    ('Unemployment Insurance',          dt_time(8, 30)),  # Jobless Claims
    ('State Unemployment Insurance',    dt_time(8, 30)),
    ('Advance Economic Indicators',     dt_time(8, 30)),  # Goods trade
    ('Durable Goods',                   dt_time(8, 30)),
    ('International Trade',             dt_time(8, 30)),
    ('Housing Starts',                  dt_time(8, 30)),
    ('New Residential Construction',    dt_time(8, 30)),  # = Housing Starts
    ('Debt to Gross Domestic Product',  dt_time(8, 30)),
    # 9:15 AM ET — Fed
    ('Industrial Production',           dt_time(9, 15)),
    ('Capacity Utilization',            dt_time(9, 15)),
    # 10:00 AM ET — ISM / NAR / Census / Conference Board
    ('Manufacturing PMI',               dt_time(10, 0)),
    ('Services PMI',                    dt_time(10, 0)),
    ('ISM',                             dt_time(10, 0)),
    ('Existing Home Sales',             dt_time(10, 0)),
    ('New Home Sales',                  dt_time(10, 0)),
    ('Pending Home Sales',              dt_time(10, 0)),
    ('Construction Spending',           dt_time(10, 0)),
    ('Wholesale Trade',                 dt_time(10, 0)),
    ('Job Openings',                    dt_time(10, 0)),  # JOLTS
    ('Consumer Confidence',             dt_time(10, 0)),
    ('Consumer Sentiment',              dt_time(10, 0)),  # UMich
    # 14:00 ET — Treasury / federal budget
    ('Monthly Treasury Statement',      dt_time(14, 0)),
    ('Treasury International Capital',  dt_time(16, 0)),  # TIC, 4 PM ET
]


def lookup_canonical_release_time(release_name: str) -> 'Optional[dt_time]':
    """Map a FRED release name to its scheduled US ET publishing time.

    Returns ``None`` for unknown releases — the caller leaves
    ``event_time`` NULL and the brief renders TBD. About 25 of the most-
    watched US releases are covered; the long-tail / unknown reports
    remain NULL until someone adds them to FRED_RELEASE_TIMES_ET.
    """
    if not release_name:
        return None
    lower = release_name.lower()
    for keyword, t in FRED_RELEASE_TIMES_ET:
        if keyword.lower() in lower:
            return t
    return None


def fetch_forexfactory_events(countries: tuple = ('USD',),
                                min_impact: str = 'medium') -> pd.DataFrame:
    """Fetch this week's economic calendar from the ForexFactory feed.

    Uses the free FairEconomyMedia JSON mirror that ForexFactory itself uses.
    No authentication required.

    Unlike FRED, this source provides:
      - Release TIME (not just date)
      - Impact classification (High/Medium/Low)
      - Forecast, Previous values (analyst consensus + prior period)

    Args:
        countries: tuple of currency codes to include (default: USD only)
        min_impact: 'high' | 'medium' | 'low' — minimum impact to include
    """
    try:
        import requests as req
    except ImportError:
        logger.warning("requests not available")
        return pd.DataFrame()

    impact_rank = {'high': 3, 'medium': 2, 'low': 1}
    min_rank = impact_rank.get(min_impact.lower(), 2)

    urls = [
        'https://nfs.faireconomy.media/ff_calendar_thisweek.json',
        'https://nfs.faireconomy.media/ff_calendar_nextweek.json',
    ]

    all_events = []
    for url in urls:
        try:
            resp = req.get(
                url,
                timeout=30,
                headers={'User-Agent': 'Mozilla/5.0 (compatible; trading-system/1.0)'},
            )
            resp.raise_for_status()
            batch = resp.json()
            all_events.extend(batch)
            logger.info("ForexFactory: %d events from %s", len(batch), url.split('/')[-1])
        except Exception as e:
            logger.warning("ForexFactory fetch failed for %s: %s", url, e)

    if not all_events:
        return pd.DataFrame()

    rows = []
    for e in all_events:
        country = e.get('country', '')
        if countries and country not in countries:
            continue

        impact_raw = (e.get('impact') or '').lower()
        if impact_rank.get(impact_raw, 0) < min_rank:
            continue

        # Parse the datetime (e.g. "2026-04-14T08:30:00-04:00")
        date_str = e.get('date', '')
        if not date_str:
            continue
        try:
            dt = pd.to_datetime(date_str)
            if pd.isna(dt):
                continue
        except Exception:
            continue

        title = (e.get('title') or '').strip()
        if not title:
            continue

        # Skip weekend events — not useful for the premarket brief
        if dt.date().weekday() >= 5:
            continue

        rows.append({
            'event_date': dt.date(),
            'event_time': dt.time().replace(microsecond=0),
            'event_name': title[:200],
            'country': country[:10],
            'importance': impact_raw,
            'actual': None,
            'forecast': (e.get('forecast') or '')[:50] or None,
            'previous': (e.get('previous') or '')[:50] or None,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.drop_duplicates(subset=['event_date', 'event_name'], keep='last')
    df = df.sort_values(['event_date', 'event_time']).reset_index(drop=True)
    logger.info("ForexFactory: %d %s+ impact events after filtering",
                 len(df), min_impact)
    return df


def fetch_fred_releases(days_ahead: int = 90) -> pd.DataFrame:
    """Fetch upcoming FRED release dates via the FRED releases API.

    Requires FRED_API_KEY environment variable. Uses the FRED /releases/dates
    endpoint, paginating through all results in the date window, then filters
    to only the high-impact release types (CPI, FOMC, NFP, GDP, PCE, PPI,
    Retail Sales, ISM/PMI, Housing Starts, Jobless Claims).

    Returns a DataFrame matching the economic_events schema.
    """
    api_key = os.environ.get('FRED_API_KEY')
    if not api_key:
        logger.info("FRED_API_KEY not set -- skipping FRED releases")
        return pd.DataFrame()

    try:
        import requests as req
    except ImportError:
        logger.warning("requests not available")
        return pd.DataFrame()

    today = date.today()
    end = today + timedelta(days=days_ahead)

    # Keywords to match high/medium-impact FRED release names
    IMPACT_KEYWORDS = {
        'high': [
            'Consumer Price Index',       # CPI
            'Employment Situation',        # NFP
            'FOMC',                        # Fed decisions
            'Gross Domestic Product',      # GDP
            'Personal Income and Outlays', # PCE
            'Producer Price Index',        # PPI
        ],
        'medium': [
            'Retail Trade',                # Retail Sales
            'Industrial Production',
            'New Residential Construction',# Housing Starts
            'Unemployment Insurance',      # Jobless Claims
            'Durable Goods',
            'ISM',                         # Manufacturing / Services PMI
            'Consumer Sentiment',          # Michigan
            'Consumer Confidence',
            'New Home Sales',
            'Existing Home Sales',
            'Trade Balance',
            'Advance Monthly Sales for Retail',
            'Personal Consumption Expenditures',
            'Advance Economic Indicators',
        ],
    }

    # Paginate through all release dates in the window
    url = 'https://api.stlouisfed.org/fred/releases/dates'
    all_releases = []
    offset = 0
    limit = 1000  # FRED max

    while True:
        params = {
            'api_key': api_key,
            'file_type': 'json',
            'realtime_start': today.isoformat(),
            'realtime_end': end.isoformat(),
            'include_release_dates_with_no_data': 'true',
            'limit': limit,
            'offset': offset,
            'sort_order': 'asc',
            'order_by': 'release_date',
        }
        try:
            resp = req.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("FRED releases/dates request failed: %s", e)
            break

        batch = data.get('release_dates', [])
        if not batch:
            break
        all_releases.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    logger.info("FRED: fetched %d total release dates in window", len(all_releases))

    if not all_releases:
        return pd.DataFrame()

    def _classify(name: str):
        if not name:
            return None
        for kw in IMPACT_KEYWORDS['high']:
            if kw in name:
                return 'high'
        for kw in IMPACT_KEYWORDS['medium']:
            if kw in name:
                return 'medium'
        return None  # low/unrelated — skip

    # Skip FRED metadata entries that appear every day — they're not real events
    # (FRED tags every Federal Reserve release day as "FOMC Press Release")
    FRED_NAME_BLACKLIST = {
        'FOMC Press Release',  # appears every weekday as FRED metadata
    }

    rows = []
    for rel in all_releases:
        name = rel.get('release_name', '')
        importance = _classify(name)
        if importance is None:
            continue
        if name in FRED_NAME_BLACKLIST:
            continue
        try:
            ev_date = pd.to_datetime(rel['date']).date()
        except Exception:
            continue
        if ev_date > end:
            continue
        # Skip weekend artifacts — US economic data doesn't release on Sat/Sun
        if ev_date.weekday() >= 5:
            continue
        # FRED's /releases/dates endpoint returns no time field — apply
        # the canonical-time lookup so the brief doesn't render TBD for
        # well-known releases (CPI, NFP, FOMC, etc.). Unknown release
        # names stay NULL and render as TBD until added to the table.
        rows.append({
            'event_date': ev_date,
            'event_time': lookup_canonical_release_time(name),
            'event_name': name[:200],
            'country': 'US',
            'importance': importance,
            'actual': None,
            'forecast': None,
            'previous': None,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.drop_duplicates(subset=['event_date', 'event_name'], keep='last')
    df = df.sort_values('event_date').reset_index(drop=True)
    logger.info("FRED: %d high/medium-impact events after filtering", len(df))
    return df


def persist_to_cloud_sql(df: pd.DataFrame) -> int:
    """Write events DataFrame to the economic_events Cloud SQL table."""
    if df.empty:
        logger.info("No events to persist")
        return 0

    if not is_cloud_sql_configured():
        logger.warning("Cloud SQL not configured -- skipping persist")
        return 0

    n = upsert_dataframe(df, 'economic_events', ['event_date', 'event_name'])
    logger.info("Upserted %d rows to economic_events", n)
    return n


def main():
    setup_logging()
    parser = argparse.ArgumentParser(description='Fetch economic events → Cloud SQL')
    parser.add_argument(
        '--source', choices=['fred', 'forexfactory', 'ff', 'all'], default='all',
        help='Data source: fred, forexfactory/ff, or all (default). '
             'ForexFactory provides release times + forecast/previous values; '
             'FRED rows have times applied via the canonical-schedule lookup '
             '(FRED_RELEASE_TIMES_ET) for well-known US agency releases.',
    )
    parser.add_argument(
        '--days-ahead', type=int, default=30,
        help='Days ahead to fetch FRED releases (default: 30)',
    )
    parser.add_argument(
        '--min-impact', choices=['low', 'medium', 'high'], default='medium',
        help='Minimum impact level for ForexFactory events (default: medium)',
    )
    parser.add_argument(
        '--countries', type=str, default='USD',
        help='Comma-separated country codes for ForexFactory (default: USD)',
    )
    args = parser.parse_args()

    frames = []
    countries = tuple(c.strip() for c in args.countries.split(',') if c.strip())

    # ForexFactory is the preferred source — has times + forecasts
    if args.source in ('forexfactory', 'ff', 'all'):
        df_ff = fetch_forexfactory_events(countries=countries, min_impact=args.min_impact)
        if not df_ff.empty:
            frames.append(df_ff)

    if args.source in ('fred', 'all'):
        df_fred = fetch_fred_releases(args.days_ahead)
        if not df_fred.empty:
            frames.append(df_fred)

    if not frames:
        logger.warning("No events loaded from any source")
        return

    # Priority: ForexFactory > FRED. When the same (event_date, event_name)
    # exists in both, keep the ForexFactory row (first in concat order)
    # because it has release times + forecast/previous values directly
    # from the source rather than via the canonical-time lookup.
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(subset=['event_date', 'event_name'], keep='first')
    logger.info("Total events to persist: %d", len(combined))

    n = persist_to_cloud_sql(combined)
    print(f"Persisted {n} economic events to Cloud SQL")


if __name__ == '__main__':
    main()
