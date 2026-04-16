#!/usr/bin/env python3
"""
Test Benzinga Corporate Events API + all additional endpoints.

This tests the KEY endpoint we initially missed:
  /api/v2.1/calendar/events — Corporate Events (investor meetings, conferences, presentations)

Plus additional endpoints:
  - Government Trades
  - Insider Trades (SEC Filings)
  - Press Releases (via News API)
  - Why Is It Moving

Usage:
    export BENZINGA_API_KEY="bz.YOUR_KEY_HERE"
    python scripts/test_benzinga_corporate_events.py
    python scripts/test_benzinga_corporate_events.py --tickers BA,NVDA,ORCL,JNJ
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

import requests

BENZINGA_BASE_V2 = "https://api.benzinga.com/api/v2.1/calendar"
BENZINGA_BASE_V1 = "https://api.benzinga.com/api/v1"
BENZINGA_NEWS = "https://api.benzinga.com/api/v2/news"


def get_api_key():
    key = os.environ.get("BENZINGA_API_KEY", "")
    if not key:
        print("ERROR: BENZINGA_API_KEY not set.")
        sys.exit(1)
    return key


def test_corporate_events(api_key, date_from, date_to, tickers=None):
    """Test the Corporate Events endpoint — the key one for conferences/meetings."""
    print("=" * 70)
    print("CORPORATE EVENTS API: /api/v2.1/calendar/events")
    print("This is the endpoint for investor conferences, meetings, presentations")
    print("=" * 70)

    url = f"{BENZINGA_BASE_V2}/events"
    headers = {"Authorization": f"token {api_key}", "Accept": "application/json"}
    params = {
        "token": api_key,
        "date_from": date_from,
        "date_to": date_to,
        "pagesize": "50",
    }
    if tickers:
        params["parameters[tickers]"] = ",".join(tickers)

    try:
        r = requests.get(url, params=params, headers=headers, timeout=30)
        print(f"  Status: {r.status_code}")

        if r.status_code == 200:
            data = r.json()
            records = data if isinstance(data, list) else data.get("events", data.get("data", []))
            if not isinstance(records, list):
                print(f"  Response type: {type(data)}")
                print(f"  Keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
                print(f"  Raw (first 500 chars): {str(data)[:500]}")
                return data

            print(f"  Records: {len(records)}")

            if records:
                print(f"  Fields: {list(records[0].keys())}")

                # Analyze event types
                event_types = {}
                for rec in records:
                    et = rec.get("eventtype", rec.get("event_type", "UNKNOWN"))
                    event_types[et] = event_types.get(et, 0) + 1

                print(f"\n  EVENT TYPES FOUND:")
                for et, count in sorted(event_types.items(), key=lambda x: -x[1]):
                    print(f"    {et}: {count}")

                print(f"\n  SAMPLE EVENTS:")
                for rec in records[:10]:
                    ticker = ""
                    securities = rec.get("securities", [])
                    if securities and isinstance(securities, list):
                        ticker = securities[0].get("symbol", "") if isinstance(securities[0], dict) else ""
                    elif isinstance(rec.get("ticker"), str):
                        ticker = rec["ticker"]

                    print(f"    [{rec.get('eventtype', '?')}] {ticker:6s} "
                          f"{rec.get('eventname', rec.get('name', '?'))[:60]} "
                          f"({rec.get('datestart', rec.get('date', '?'))})")

            return records
        else:
            print(f"  Error: {r.text[:500]}")
            return None

    except Exception as e:
        print(f"  Exception: {e}")
        return None


def test_government_trades(api_key, date_from, date_to):
    """Test Government Trades endpoint."""
    print("\n" + "-" * 50)
    print("GOVERNMENT TRADES")
    print("-" * 50)

    url = f"{BENZINGA_BASE_V1}/government/trades"
    headers = {"Authorization": f"token {api_key}", "Accept": "application/json"}
    params = {"token": api_key, "date_from": date_from, "date_to": date_to, "pagesize": "5"}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            records = data if isinstance(data, list) else data.get("data", [])
            print(f"  Records: {len(records) if isinstance(records, list) else 'N/A'}")
            if isinstance(records, list) and records:
                print(f"  Fields: {list(records[0].keys())[:15]}")
                rec = records[0]
                for k in list(rec.keys())[:8]:
                    print(f"    {k}: {rec[k]}")
        else:
            print(f"  Error: {r.text[:300]}")
    except Exception as e:
        print(f"  Exception: {e}")


def test_insider_trades(api_key, date_from, date_to):
    """Test Insider Trades / SEC Filings endpoint."""
    print("\n" + "-" * 50)
    print("INSIDER TRADES (SEC Form 4)")
    print("-" * 50)

    # Try the SEC filings endpoint
    for path in ["/signal/option_activity", "/sec/filings"]:
        url = f"https://api.benzinga.com/api/v1{path}"
        headers = {"Authorization": f"token {api_key}", "Accept": "application/json"}
        params = {"token": api_key, "date_from": date_from, "date_to": date_to, "pagesize": "5"}

        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            print(f"  {path}: Status {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                records = data if isinstance(data, list) else data.get("data", [])
                if isinstance(records, list):
                    print(f"    Records: {len(records)}")
                    if records:
                        print(f"    Fields: {list(records[0].keys())[:12]}")
        except Exception as e:
            print(f"    Exception: {e}")


def test_press_releases(api_key, tickers=None):
    """Test Press Releases / News endpoint for corporate announcements."""
    print("\n" + "-" * 50)
    print("PRESS RELEASES / NEWS")
    print("-" * 50)

    url = BENZINGA_NEWS
    headers = {"Authorization": f"token {api_key}", "Accept": "application/json"}
    params = {
        "token": api_key,
        "pageSize": "5",
        "displayOutput": "full",
    }
    if tickers:
        params["tickers"] = ",".join(tickers)

    # Filter for press releases
    params["channels"] = "Press Releases"

    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            records = data if isinstance(data, list) else data.get("data", [])
            if isinstance(records, list):
                print(f"  Records: {len(records)}")
                if records:
                    print(f"  Fields: {list(records[0].keys())[:12]}")
                    for rec in records[:3]:
                        print(f"    [{rec.get('created', '?')[:10]}] "
                              f"{','.join(rec.get('stocks', [])[:3]):10s} "
                              f"{rec.get('title', '?')[:70]}")
        else:
            print(f"  Error: {r.text[:300]}")
    except Exception as e:
        print(f"  Exception: {e}")


def test_why_is_it_moving(api_key, tickers=None):
    """Test 'Why Is It Moving' endpoint."""
    print("\n" + "-" * 50)
    print("WHY IS IT MOVING")
    print("-" * 50)

    url = "https://api.benzinga.com/api/v1/signal/wiim"
    headers = {"Authorization": f"token {api_key}", "Accept": "application/json"}
    params = {"token": api_key, "pagesize": "5"}
    if tickers:
        params["tickers"] = ",".join(tickers)

    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            records = data if isinstance(data, list) else data.get("data", [])
            if isinstance(records, list):
                print(f"  Records: {len(records)}")
                if records:
                    print(f"  Fields: {list(records[0].keys())[:12]}")
        else:
            print(f"  Error: {r.text[:300]}")
    except Exception as e:
        print(f"  Exception: {e}")


def main():
    parser = argparse.ArgumentParser(description="Test Benzinga Corporate Events API")
    parser.add_argument("--tickers", default="BA,NVDA,ORCL,JNJ,GM,SCHW,BK,SMCI,TXN,TSM",
                        help="Comma-separated tickers")
    parser.add_argument("--from", dest="date_from", default=None)
    parser.add_argument("--to", dest="date_to", default=None)
    args = parser.parse_args()

    api_key = get_api_key()
    tickers = [t.strip() for t in args.tickers.split(",")]

    today = datetime.now()
    date_from = args.date_from or (today - timedelta(days=7)).strftime("%Y-%m-%d")
    date_to = args.date_to or (today + timedelta(days=30)).strftime("%Y-%m-%d")

    print(f"Benzinga Corporate Events API Test")
    print(f"  Key: {api_key[:12]}...{api_key[-4:]}")
    print(f"  Date range: {date_from} to {date_to}")
    print(f"  Tickers: {', '.join(tickers)}")
    print()

    # THE KEY TEST — Corporate Events
    events = test_corporate_events(api_key, date_from, date_to, tickers)

    # Additional endpoints
    test_government_trades(api_key, date_from, date_to)
    test_insider_trades(api_key, date_from, date_to)
    test_press_releases(api_key, tickers[:5])
    test_why_is_it_moving(api_key, tickers[:5])

    # Save results
    output_path = "data/benzinga_corporate_events_test.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "test_date": datetime.now().isoformat(),
            "date_range": {"from": date_from, "to": date_to},
            "tickers": tickers,
            "corporate_events": events if isinstance(events, list) else str(events),
        }, f, indent=2, default=str)
    print(f"\nResults saved to {output_path}")

    # Summary
    print("\n" + "=" * 70)
    print("CRITICAL FINDING")
    print("=" * 70)
    if events and isinstance(events, list) and len(events) > 0:
        print("  Corporate Events API WORKS!")
        print("  This endpoint may cover investor conferences, shareholder meetings,")
        print("  and presentations — the same types WSH has.")
        print("  Check the event types above to confirm coverage.")
    elif events is not None:
        print("  Corporate Events API returned data but in unexpected format.")
        print("  Check the raw output above.")
    else:
        print("  Corporate Events API failed or returned no data.")
        print("  This endpoint may not be included in your plan,")
        print("  or may need different parameters.")


if __name__ == "__main__":
    main()
