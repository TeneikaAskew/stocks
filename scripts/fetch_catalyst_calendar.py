#!/usr/bin/env python3
"""
Fetch catalyst calendar data from Benzinga Calendar API.

Covers: earnings, conference calls, guidance, dividends, splits, IPOs,
        M&A, FDA, ratings, and economics.

NOTE: Benzinga does NOT cover investor conferences, summits, production
updates, shareholder meetings, interim statements, or business updates.
Those require Wall Street Horizon (WSH) via IBKR TWS API.
See: https://www.wallstreethorizon.com/ibkr-wsh

Usage:
    python scripts/fetch_catalyst_calendar.py
    python scripts/fetch_catalyst_calendar.py --days 30
    python scripts/fetch_catalyst_calendar.py --tickers AAPL,MSFT,NVDA
    python scripts/fetch_catalyst_calendar.py --types earnings,guidance,fda
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# ── Benzinga API config ─────────────────────────────────────────────────────

BENZINGA_BASE = "https://api.benzinga.com/api/v2.1/calendar"
BENZINGA_NEWS_BASE = "https://api.benzinga.com/api/v2/news"
BENZINGA_GOV_BASE = "https://api.benzinga.com/api/v1/government"

# Calendar types → endpoint paths and how to classify them
CALENDAR_TYPES = {
    "events": {
        "path": "/events",
        "catalyst_type": "CORPORATE_EVENT",
        "impact": "High",
    },
    "earnings": {
        "path": "/earnings",
        "catalyst_type": "EARNINGS",
        "impact": "High",
    },
    "conference-calls": {
        "path": "/conference-calls",
        "catalyst_type": "CONFERENCE_CALL",
        "impact": "Medium",
    },
    "guidance": {
        "path": "/guidance",
        "catalyst_type": "GUIDANCE",
        "impact": "High",
    },
    "dividends": {
        "path": "/dividends",
        "catalyst_type": "DIVIDEND",
        "impact": "Low",
    },
    "splits": {
        "path": "/splits",
        "catalyst_type": "SPLIT",
        "impact": "Medium",
    },
    "ipo": {
        "path": "/ipo",
        "catalyst_type": "IPO",
        "impact": "High",
    },
    "ma": {
        "path": "/ma",
        "catalyst_type": "MERGER_ACQUISITION",
        "impact": "Very High",
    },
    "fda": {
        "path": "/fda",
        "catalyst_type": "FDA",
        "impact": "Very High",
    },
    "ratings": {
        "path": "/ratings",
        "catalyst_type": "ANALYST_RATING",
        "impact": "Medium",
    },
    "economics": {
        "path": "/economics",
        "catalyst_type": "ECONOMIC",
        "impact": "Variable",
    },
}

# WSH event types that MAY require upgrade — Benzinga Corporate Events API
# may cover some of these.
WSH_ONLY_TYPES = [
    "PRODUCTION_UPDATE",
    "INTERIM_STATEMENT",
    "SALES_UPDATE",
    "ROAD_SHOW",
]

OUTPUT_DIR = Path("data/catalysts")
OUTPUT_FILE = OUTPUT_DIR / "catalyst_calendar.json"


def get_api_key():
    key = os.environ.get("BENZINGA_API_KEY", "")
    if not key:
        logger.error("BENZINGA_API_KEY not set in environment")
        return None
    return key


def fetch_calendar(calendar_type, api_key, date_from, date_to, tickers=None, pagesize=1000):
    """Fetch a single Benzinga calendar endpoint with pagination."""
    config = CALENDAR_TYPES[calendar_type]
    url = f"{BENZINGA_BASE}{config['path']}"

    headers = {
        "Authorization": f"token {api_key}",
        "Accept": "application/json",
    }
    params = {
        "token": api_key,
        "date_from": date_from,
        "date_to": date_to,
        "pagesize": str(pagesize),
        "page": "0",
    }
    if tickers:
        params["parameters[tickers]"] = ",".join(tickers)

    all_records = []
    page = 0

    while True:
        params["page"] = str(page)
        try:
            r = requests.get(url, params=params, headers=headers, timeout=30)
            if r.status_code == 401:
                logger.error("Benzinga API: Unauthorized (401) — check your API key")
                return []
            if r.status_code == 403:
                logger.warning("Benzinga API: Forbidden (403) for %s — may not be in your plan", calendar_type)
                return []
            r.raise_for_status()

            data = r.json()
            records = data if isinstance(data, list) else data.get(calendar_type, data.get("data", []))
            if not isinstance(records, list):
                records = []

            if not records:
                break

            all_records.extend(records)

            # Benzinga caps at 10000 per query
            if len(records) < pagesize or len(all_records) >= 10000:
                break

            page += 1

        except requests.exceptions.RequestException as e:
            logger.error("Benzinga API error for %s: %s", calendar_type, e)
            break

    return all_records


def normalize_earnings(records):
    """Normalize earnings records to catalyst format."""
    events = []
    for rec in records:
        ticker = rec.get("ticker", "")
        if not ticker:
            continue
        events.append({
            "date": rec.get("date", ""),
            "ticker": ticker,
            "company_name": rec.get("name", ""),
            "catalyst_type": "EARNINGS",
            "event": f"{ticker} Earnings",
            "expected_impact": "High",
            "details": {
                "time": rec.get("time", ""),
                "eps_estimate": rec.get("eps_estimate", None),
                "eps_actual": rec.get("eps_actual", None),
                "revenue_estimate": rec.get("revenue_estimate", None),
                "revenue_actual": rec.get("revenue_actual", None),
                "eps_surprise": rec.get("eps_surprise", None),
                "revenue_surprise": rec.get("revenue_surprise", None),
            },
            "confirmed": True,
            "source": "Benzinga",
        })
    return events


def normalize_conference_calls(records):
    """Normalize conference call records."""
    events = []
    for rec in records:
        ticker = rec.get("ticker", "")
        if not ticker:
            continue
        events.append({
            "date": rec.get("date", ""),
            "ticker": ticker,
            "company_name": rec.get("name", ""),
            "catalyst_type": "CONFERENCE_CALL",
            "event": rec.get("name", f"{ticker} Conference Call"),
            "expected_impact": "Medium",
            "details": {
                "time": rec.get("time", ""),
                "phone": rec.get("phone", ""),
                "webcast_url": rec.get("webcast_url", ""),
            },
            "confirmed": True,
            "source": "Benzinga",
        })
    return events


def normalize_guidance(records):
    """Normalize guidance records."""
    events = []
    for rec in records:
        ticker = rec.get("ticker", "")
        if not ticker:
            continue
        events.append({
            "date": rec.get("date", ""),
            "ticker": ticker,
            "company_name": rec.get("name", ""),
            "catalyst_type": "GUIDANCE",
            "event": f"{ticker} Guidance Update",
            "expected_impact": "High",
            "details": {
                "eps_guidance_est": rec.get("eps_guidance_est", None),
                "eps_guidance_max": rec.get("eps_guidance_max", None),
                "eps_guidance_min": rec.get("eps_guidance_min", None),
                "revenue_guidance_est": rec.get("revenue_guidance_est", None),
                "revenue_guidance_max": rec.get("revenue_guidance_max", None),
                "revenue_guidance_min": rec.get("revenue_guidance_min", None),
            },
            "confirmed": True,
            "source": "Benzinga",
        })
    return events


def normalize_dividends(records):
    """Normalize dividend records."""
    events = []
    for rec in records:
        ticker = rec.get("ticker", "")
        if not ticker:
            continue
        events.append({
            "date": rec.get("date", rec.get("ex_date", "")),
            "ticker": ticker,
            "company_name": rec.get("name", ""),
            "catalyst_type": "DIVIDEND",
            "event": f"{ticker} Dividend",
            "expected_impact": "Low",
            "details": {
                "dividend": rec.get("dividend", None),
                "dividend_yield": rec.get("dividend_yield", None),
                "ex_date": rec.get("ex_date", ""),
                "payable_date": rec.get("payable_date", ""),
                "record_date": rec.get("record_date", ""),
            },
            "confirmed": True,
            "source": "Benzinga",
        })
    return events


def normalize_fda(records):
    """Normalize FDA approval records."""
    events = []
    for rec in records:
        ticker = rec.get("ticker", "")
        if not ticker:
            continue
        events.append({
            "date": rec.get("date", ""),
            "ticker": ticker,
            "company_name": rec.get("name", ""),
            "catalyst_type": "FDA",
            "event": rec.get("drug_name", f"{ticker} FDA Decision"),
            "expected_impact": "Very High",
            "details": {
                "drug_name": rec.get("drug_name", ""),
                "indication": rec.get("indication", ""),
                "status": rec.get("status", ""),
            },
            "confirmed": True,
            "source": "Benzinga",
        })
    return events


def normalize_ratings(records):
    """Normalize analyst rating records."""
    events = []
    for rec in records:
        ticker = rec.get("ticker", "")
        if not ticker:
            continue
        events.append({
            "date": rec.get("date", ""),
            "ticker": ticker,
            "company_name": rec.get("name", ""),
            "catalyst_type": "ANALYST_RATING",
            "event": f"{ticker} Rating: {rec.get('rating_current', '')}",
            "expected_impact": "Medium",
            "details": {
                "analyst": rec.get("analyst", ""),
                "analyst_name": rec.get("analyst_name", ""),
                "rating_prior": rec.get("rating_prior", ""),
                "rating_current": rec.get("rating_current", ""),
                "pt_prior": rec.get("pt_prior", None),
                "pt_current": rec.get("pt_current", None),
                "action_company": rec.get("action_company", ""),
            },
            "confirmed": True,
            "source": "Benzinga",
        })
    return events


def normalize_ma(records):
    """Normalize M&A records."""
    events = []
    for rec in records:
        ticker = rec.get("acquirer_ticker", "") or rec.get("target_ticker", "")
        if not ticker:
            continue
        events.append({
            "date": rec.get("date", rec.get("date_expected", "")),
            "ticker": ticker,
            "company_name": rec.get("acquirer_name", rec.get("target_name", "")),
            "catalyst_type": "MERGER_ACQUISITION",
            "event": f"M&A: {rec.get('acquirer_name', '?')} / {rec.get('target_name', '?')}",
            "expected_impact": "Very High",
            "details": {
                "acquirer": rec.get("acquirer_name", ""),
                "target": rec.get("target_name", ""),
                "deal_value": rec.get("deal_value", None),
                "deal_type": rec.get("deal_type", ""),
            },
            "confirmed": True,
            "source": "Benzinga",
        })
    return events


def normalize_generic(records, catalyst_type, impact):
    """Generic normalizer for simpler calendar types (splits, IPOs, economics)."""
    events = []
    for rec in records:
        ticker = rec.get("ticker", rec.get("symbol", ""))
        event_name = rec.get("name", rec.get("event_name", rec.get("company", "")))
        date = rec.get("date", rec.get("date_expected", ""))
        if not date:
            continue
        events.append({
            "date": date,
            "ticker": ticker or "",
            "company_name": rec.get("name", rec.get("company", "")),
            "catalyst_type": catalyst_type,
            "event": event_name or f"{ticker} {catalyst_type}",
            "expected_impact": impact,
            "details": {k: v for k, v in rec.items() if k not in ("id", "updated")},
            "confirmed": True,
            "source": "Benzinga",
        })
    return events


def normalize_corporate_events(records):
    """Normalize Corporate Events API records (investor conferences, meetings, presentations).

    This is the key endpoint that may cover WSH-type events:
    conferences, summits, shareholder meetings, investor days, etc.
    """
    events = []
    for rec in records:
        # Securities array contains ticker info
        ticker = ""
        securities = rec.get("securities", [])
        if securities and isinstance(securities, list):
            first = securities[0]
            if isinstance(first, dict):
                ticker = first.get("symbol", "")
            elif isinstance(first, str):
                ticker = first

        event_name = rec.get("eventname", rec.get("name", ""))
        event_type_raw = rec.get("eventtype", rec.get("event_type", ""))

        # Classify the event type based on eventtype field
        catalyst_type = _classify_corporate_event(event_type_raw, event_name)

        events.append({
            "date": rec.get("datestart", rec.get("date", "")),
            "ticker": ticker,
            "company_name": "",
            "catalyst_type": catalyst_type,
            "event": event_name,
            "expected_impact": "High",
            "details": {
                "event_type_raw": event_type_raw,
                "location": rec.get("location", ""),
                "webcast_link": rec.get("webcast_link", ""),
                "date_end": rec.get("dateend", ""),
                "start_time": rec.get("starttime", ""),
                "importance": rec.get("importance", ""),
                "source_link": rec.get("sourcelink", ""),
                "tags": rec.get("tags", []),
            },
            "confirmed": True,
            "source": "Benzinga",
        })
    return events


def _classify_corporate_event(event_type_raw, event_name):
    """Classify a Benzinga corporate event into our catalyst taxonomy."""
    et = (event_type_raw or "").lower()
    en = (event_name or "").lower()

    if "conference" in et or "conference" in en:
        return "INVESTOR_CONFERENCE"
    if "summit" in et or "summit" in en:
        return "SUMMIT"
    if "shareholder" in et or "shareholder" in en or "annual meeting" in en:
        return "SHAREHOLDER_MEETING"
    if "analyst day" in et or "analyst day" in en or "capital markets" in en:
        return "ANALYST_DAY"
    if "investor day" in et or "investor day" in en:
        return "INVESTOR_DAY"
    if "presentation" in et or "presentation" in en:
        return "PRESENTATION"
    if "business update" in et or "business update" in en:
        return "BUSINESS_UPDATE"
    if "webcast" in et or "webinar" in en:
        return "WEBCAST"
    return "CORPORATE_EVENT"


# Map calendar types to their normalizer functions
NORMALIZERS = {
    "events": normalize_corporate_events,
    "earnings": normalize_earnings,
    "conference-calls": normalize_conference_calls,
    "guidance": normalize_guidance,
    "dividends": normalize_dividends,
    "fda": normalize_fda,
    "ratings": normalize_ratings,
    "ma": normalize_ma,
}


def fetch_all_catalysts(api_key, date_from, date_to, tickers=None, calendar_types=None):
    """Fetch and normalize all catalyst events from Benzinga."""
    if calendar_types is None:
        calendar_types = list(CALENDAR_TYPES.keys())

    all_events = []

    for cal_type in calendar_types:
        if cal_type not in CALENDAR_TYPES:
            logger.warning("Unknown calendar type: %s", cal_type)
            continue

        config = CALENDAR_TYPES[cal_type]
        logger.info("Fetching %s events...", cal_type)
        records = fetch_calendar(cal_type, api_key, date_from, date_to, tickers)
        logger.info("  -> %d raw records from %s", len(records), cal_type)

        if not records:
            continue

        normalizer = NORMALIZERS.get(cal_type)
        if normalizer:
            events = normalizer(records)
        else:
            events = normalize_generic(records, config["catalyst_type"], config["impact"])

        all_events.extend(events)

    # Sort by date
    all_events.sort(key=lambda e: e.get("date", ""))
    return all_events


def save_catalysts(events, output_path=None):
    """Save catalyst events to JSON."""
    if output_path is None:
        output_path = OUTPUT_FILE

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Merge with existing data if present
    existing = []
    if output_path.exists():
        try:
            with open(output_path) as f:
                data = json.load(f)
                existing = data.get("events", []) if isinstance(data, dict) else data
        except (json.JSONDecodeError, KeyError):
            pass

    # Deduplicate by (date, ticker, catalyst_type)
    seen = set()
    merged = []
    for event in events + existing:
        key = (event.get("date"), event.get("ticker"), event.get("catalyst_type"))
        if key not in seen:
            seen.add(key)
            merged.append(event)

    merged.sort(key=lambda e: e.get("date", ""))

    output = {
        "last_updated": datetime.now().isoformat(),
        "source": "Benzinga",
        "upgrade_note": (
            "Benzinga covers earnings, conference calls, guidance, dividends, "
            "splits, IPOs, M&A, FDA, ratings, and economics. For investor "
            "conferences, summits, production updates, shareholder meetings, "
            "interim statements, and business updates, upgrade to Wall Street "
            "Horizon via IBKR TWS API ($49-149/mo)."
        ),
        "wsh_missing_types": WSH_ONLY_TYPES,
        "event_count": len(merged),
        "events": merged,
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    logger.info("Saved %d catalyst events to %s", len(merged), output_path)
    return merged


def main():
    parser = argparse.ArgumentParser(description="Fetch catalyst calendar from Benzinga")
    parser.add_argument("--days", type=int, default=14,
                        help="Number of days ahead to fetch (default: 14)")
    parser.add_argument("--days-back", type=int, default=3,
                        help="Number of days back to fetch (default: 3)")
    parser.add_argument("--tickers", default=None,
                        help="Comma-separated tickers (default: all)")
    parser.add_argument("--types", default=None,
                        help="Comma-separated calendar types (default: all)")
    parser.add_argument("--output", default=None,
                        help="Output file path (default: data/catalysts/catalyst_calendar.json)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    api_key = get_api_key()
    if not api_key:
        sys.exit(1)

    today = datetime.now()
    date_from = (today - timedelta(days=args.days_back)).strftime("%Y-%m-%d")
    date_to = (today + timedelta(days=args.days)).strftime("%Y-%m-%d")

    tickers = [t.strip().upper() for t in args.tickers.split(",")] if args.tickers else None
    cal_types = [t.strip() for t in args.types.split(",")] if args.types else None

    logger.info("Fetching Benzinga catalysts from %s to %s", date_from, date_to)
    if tickers:
        logger.info("  Tickers: %s", ", ".join(tickers))

    events = fetch_all_catalysts(api_key, date_from, date_to, tickers, cal_types)
    logger.info("Total: %d catalyst events fetched", len(events))

    saved = save_catalysts(events, args.output)

    # Summary by type
    type_counts = {}
    for e in saved:
        ct = e.get("catalyst_type", "UNKNOWN")
        type_counts[ct] = type_counts.get(ct, 0) + 1

    logger.info("Events by type:")
    for ct, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        logger.info("  %s: %d", ct, count)


if __name__ == "__main__":
    main()
