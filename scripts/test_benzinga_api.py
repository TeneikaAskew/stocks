#!/usr/bin/env python3
"""
Test Benzinga Calendar API endpoints to validate coverage for catalyst data.

Usage:
    # Set your API key first:
    export BENZINGA_API_KEY="bz.YOUR_KEY_HERE"

    # Run all tests:
    python scripts/test_benzinga_api.py

    # Test specific tickers from the Stratalyst screenshot:
    python scripts/test_benzinga_api.py --tickers BA,NVDA,ORCL,JNJ,GM,SCHW

    # Test a specific date range:
    python scripts/test_benzinga_api.py --from 2026-04-10 --to 2026-04-20
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

import requests

BENZINGA_BASE = "https://api.benzinga.com/api/v2.1/calendar"

# All calendar endpoint paths to test
CALENDAR_ENDPOINTS = {
    "earnings":         "/earnings",
    "economics":        "/economics",
    "dividends":        "/dividends",
    "splits":           "/splits",
    "conference-calls": "/conference-calls",
    "guidance":         "/guidance",
    "ipo":              "/ipo",
    "ma":               "/ma",
    "fda":              "/fda",
    "ratings":          "/ratings",
}

# Stratalyst screenshot event types → what Benzinga can/can't cover
WSH_EVENT_TYPES = [
    "Conference",
    "Summit",
    "Production Update",
    "Shareholder Meeting",
    "Interim Statement",
    "Business Update",
    "Sales Update",
]


def get_api_key():
    key = os.environ.get("BENZINGA_API_KEY", "")
    if not key:
        print("ERROR: BENZINGA_API_KEY not set in environment.")
        print("  export BENZINGA_API_KEY='bz.YOUR_KEY_HERE'")
        sys.exit(1)
    return key


def test_endpoint(name, path, api_key, date_from, date_to, tickers=None):
    """Test a single Benzinga calendar endpoint."""
    url = f"{BENZINGA_BASE}{path}"
    params = {
        "token": api_key,
        "date_from": date_from,
        "date_to": date_to,
        "pagesize": "10",
    }
    if tickers:
        params["parameters[tickers]"] = ",".join(tickers)

    headers = {
        "Authorization": f"token {api_key}",
        "Accept": "application/json",
    }

    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        status = r.status_code
        if status == 200:
            data = r.json()
            records = data if isinstance(data, list) else data.get(name, data.get("data", []))
            if not isinstance(records, list):
                records = []
            return {
                "status": status,
                "count": len(records),
                "fields": list(records[0].keys()) if records else [],
                "sample": records[0] if records else None,
            }
        else:
            return {"status": status, "error": r.text[:300]}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def test_conference_calls_detail(api_key, date_from, date_to, tickers=None):
    """Deep-dive into conference-calls to see if it has investor conferences or just earnings calls."""
    url = f"{BENZINGA_BASE}/conference-calls"
    params = {
        "token": api_key,
        "date_from": date_from,
        "date_to": date_to,
        "pagesize": "50",
    }
    headers = {"Authorization": f"token {api_key}", "Accept": "application/json"}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        records = data if isinstance(data, list) else data.get("conference-calls", [])
        if not isinstance(records, list):
            return None

        # Analyze: are these earnings calls or broader corporate events?
        event_names = [rec.get("name", "") for rec in records[:20]]
        return {
            "total": len(records),
            "sample_names": event_names[:10],
            "has_webcast": any(rec.get("webcast_url") for rec in records[:20]),
            "has_phone": any(rec.get("phone") for rec in records[:20]),
        }
    except Exception:
        return None


def run_gap_analysis(results):
    """Compare Benzinga coverage against WSH event types from the Stratalyst screenshot."""
    print("\n" + "=" * 70)
    print("GAP ANALYSIS: Benzinga vs Wall Street Horizon (Stratalyst screenshot)")
    print("=" * 70)

    # What Benzinga covers
    bz_has = {
        "Earnings dates & EPS/revenue": results.get("earnings", {}).get("count", 0) > 0,
        "Earnings conference calls": results.get("conference-calls", {}).get("count", 0) > 0,
        "Economic events (CPI, FOMC)": results.get("economics", {}).get("count", 0) > 0,
        "Dividends": results.get("dividends", {}).get("count", 0) > 0,
        "Stock splits": results.get("splits", {}).get("count", 0) > 0,
        "Corporate guidance": results.get("guidance", {}).get("count", 0) > 0,
        "IPOs": results.get("ipo", {}).get("count", 0) > 0,
        "M&A activity": results.get("ma", {}).get("count", 0) > 0,
        "FDA approvals": results.get("fda", {}).get("count", 0) > 0,
        "Analyst ratings": results.get("ratings", {}).get("count", 0) > 0,
    }

    print("\nBENZINGA COVERAGE:")
    for event, available in bz_has.items():
        icon = "Y" if available else "N"
        print(f"  [{icon}] {event}")

    # WSH-only events (the Stratalyst screenshot categories)
    print("\nWSH-ONLY EVENT TYPES (not in Benzinga):")
    wsh_only = {
        "Investor Conferences (EHRA, AWS Symposium)": "NO Benzinga equivalent",
        "Summits (Oracle Customer Edge Summit)": "NO Benzinga equivalent",
        "Production Updates (Boeing Deliveries)": "NO Benzinga equivalent",
        "Shareholder Meetings (Annual meetings)": "NO Benzinga equivalent",
        "Interim Statements (Activity Highlights)": "NO Benzinga equivalent",
        "Business Updates (Schwab Business Update)": "NO Benzinga equivalent",
        "Sales Updates (Revenue Reports)": "Partial via earnings/guidance",
    }
    for event, note in wsh_only.items():
        print(f"  [X] {event}")
        print(f"      -> {note}")

    print("\nSUMMARY:")
    print("  Benzinga gives you: earnings, economics, dividends, splits,")
    print("  guidance, IPOs, M&A, FDA, ratings, conference calls (earnings only)")
    print()
    print("  Benzinga CANNOT give you: investor conferences, summits,")
    print("  production updates, shareholder meetings, interim statements,")
    print("  business updates (the core Stratalyst/WSH catalyst taxonomy)")
    print()
    print("  UPGRADE PATH: Wall Street Horizon via IBKR ($49-149/mo)")
    print("  -> Adds all 40+ corporate event types including the 7 above")
    print("  -> TWS API: reqWshMetaData() + reqWshEventData()")


def main():
    parser = argparse.ArgumentParser(description="Test Benzinga Calendar API endpoints")
    parser.add_argument("--tickers", default="BA,NVDA,ORCL,JNJ,GM,SCHW,BK,SMCI,TXN,TSM",
                        help="Comma-separated tickers to test")
    parser.add_argument("--from", dest="date_from", default=None,
                        help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="date_to", default=None,
                        help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    api_key = get_api_key()
    tickers = [t.strip() for t in args.tickers.split(",")]

    today = datetime.now()
    date_from = args.date_from or (today - timedelta(days=3)).strftime("%Y-%m-%d")
    date_to = args.date_to or (today + timedelta(days=14)).strftime("%Y-%m-%d")

    print(f"Testing Benzinga Calendar API")
    print(f"  Key: {api_key[:12]}...{api_key[-4:]}")
    print(f"  Date range: {date_from} to {date_to}")
    print(f"  Tickers: {', '.join(tickers)}")
    print()

    # Test all endpoints
    results = {}
    for name, path in CALENDAR_ENDPOINTS.items():
        print(f"Testing {name}...", end=" ", flush=True)
        result = test_endpoint(name, path, api_key, date_from, date_to, tickers)
        results[name] = result

        status = result.get("status")
        count = result.get("count", 0)
        if status == 200:
            print(f"OK ({count} records)")
            if result.get("fields"):
                print(f"  Fields: {result['fields'][:12]}")
        else:
            error = result.get("error", "unknown")
            print(f"FAIL [{status}] {error[:100]}")

    # Deep-dive on conference calls
    print("\nDeep-diving conference-calls endpoint...")
    cc_detail = test_conference_calls_detail(api_key, date_from, date_to, tickers)
    if cc_detail:
        print(f"  Total calls: {cc_detail['total']}")
        print(f"  Has webcast URLs: {cc_detail['has_webcast']}")
        print(f"  Has phone numbers: {cc_detail['has_phone']}")
        print(f"  Sample names:")
        for name in cc_detail["sample_names"]:
            print(f"    - {name}")

    # Gap analysis
    run_gap_analysis(results)

    # Save raw results
    output_path = "data/benzinga_api_test_results.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        # Convert non-serializable items
        serializable = {}
        for k, v in results.items():
            serializable[k] = {sk: sv for sk, sv in v.items()}
        json.dump({
            "test_date": datetime.now().isoformat(),
            "date_range": {"from": date_from, "to": date_to},
            "tickers": tickers,
            "results": serializable,
            "conference_calls_detail": cc_detail,
        }, f, indent=2, default=str)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
