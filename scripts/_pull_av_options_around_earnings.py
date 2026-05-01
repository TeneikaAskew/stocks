"""Pull AV HISTORICAL_OPTIONS around historical earnings dates.

TIMING-AWARE: reads `earnings_history.report_time` to decide which
trading day's options snapshot to pull:
  - 'pre-market'  (BMO) -> pull D itself (the morning-release session)
  - 'post-market' (AMC) -> pull D+1 (the next-day reaction session)
  - NULL/unknown          -> fall back to D+1 (AMC is the safer default)

Replaces the older AMC-only path AND the BMO-only `_v2` companion
script — one script handles all timings via report_time.

Usage:
    python -m scripts._pull_av_options_around_earnings
    python -m scripts._pull_av_options_around_earnings --tickers FDX,LLY
    python -m scripts._pull_av_options_around_earnings --quarters 4
"""
import argparse
import subprocess
import sys
import time
from datetime import timedelta

import pandas as pd
import psycopg2
import psycopg2.extras
import requests

GCLOUD = r'C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
PROJECT = 'adept-mountain-474619-d4'
DB_HOST = '34.24.66.12'

# Default 9-ticker case-study set (4 AMC + 5 BMO)
DEFAULT_TICKERS = ['AVGO', 'GOOG', 'NVDA', 'FDX',
                   'LLY', 'JPM', 'JNJ', 'WMT', 'PG']


def secret(name):
    return subprocess.check_output(
        [GCLOUD, 'secrets', 'versions', 'access', 'latest',
         f'--secret={name}', f'--project={PROJECT}'],
        text=True, timeout=15).rstrip('\n')


def connect():
    return psycopg2.connect(host=DB_HOST, user=secret('db-trading-user'),
                            password=secret('db-trading-pass'),
                            dbname='trading', sslmode='require')


def fetch_av_options(symbol, fetch_date, api_key):
    r = requests.get('https://www.alphavantage.co/query', params={
        'function': 'HISTORICAL_OPTIONS',
        'symbol': symbol, 'date': fetch_date,
        'apikey': api_key, 'datatype': 'json',
    }, timeout=60)
    r.raise_for_status()
    data = r.json()
    if data.get('message') != 'success':
        return pd.DataFrame()
    return pd.DataFrame(data.get('data', []))


def fetch_recent_reports(conn, ticker, n):
    """Last N quarterly reports with their per-quarter report_time.

    Filters NaN/0/NULL placeholder rows. Returns rows in
    most-recent-first order; consumers care about recency.
    """
    sql = """
        SELECT reported_date, report_time
        FROM earnings_history
        WHERE ticker = %s AND reported_date IS NOT NULL
          AND (reported_eps > 0 OR reported_eps < 0)
        ORDER BY reported_date DESC LIMIT %s
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (ticker, n))
        return cur.fetchall()


def first_trading_day_on_or_after(conn, ticker, d):
    sql = """SELECT date FROM market_data_daily
             WHERE ticker = %s AND date >= %s ORDER BY date LIMIT 1"""
    with conn.cursor() as cur:
        cur.execute(sql, (ticker, d))
        row = cur.fetchone()
        return row[0] if row else None


def reaction_trading_day(conn, ticker, reported_date, report_time):
    """Pick the right snapshot date based on report_time.

    BMO  (pre-market)  -> D itself (first trading day on/after reported_date)
    AMC  (post-market) -> D+1     (first trading day strictly after reported_date)
    NULL/other         -> AMC default
    """
    if (report_time or '').lower() == 'pre-market':
        return first_trading_day_on_or_after(conn, ticker, reported_date)
    # AMC default: D+1
    return first_trading_day_on_or_after(conn, ticker, reported_date + timedelta(days=1))


def main():
    parser = argparse.ArgumentParser(
        description="Pull AV HISTORICAL_OPTIONS around historical earnings (timing-aware)"
    )
    parser.add_argument('--tickers', type=str, default=None,
                        help='Comma-separated tickers (default: 9-ticker case-study set)')
    parser.add_argument('--quarters', type=int, default=12,
                        help='Number of recent quarters to pull per ticker (default: 12)')
    args = parser.parse_args()

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',') if t.strip()]
    else:
        tickers = DEFAULT_TICKERS

    api_key = secret('av-api-key')
    conn = connect()

    summary_rows = []
    detail_rows = []
    call_count = 0
    total_calls_estimate = sum(args.quarters for _ in tickers)

    for ticker in tickers:
        reports = fetch_recent_reports(conn, ticker, args.quarters)
        if not reports:
            print(f"[{ticker}] no reports; skipping")
            continue
        # Determine timing distribution
        timing_counts = {}
        for r in reports:
            t = r['report_time'] or 'unknown'
            timing_counts[t] = timing_counts.get(t, 0) + 1
        primary_timing = max(timing_counts, key=timing_counts.get)
        print(f"\n[{ticker}] timing={primary_timing} ({timing_counts}), "
              f"{len(reports)} recent reports")

        per_ticker_volumes = []
        for r in reports:
            reported = r['reported_date']
            timing = r['report_time']
            target = reaction_trading_day(conn, ticker, reported, timing)
            if target is None:
                continue
            d_str = target.strftime('%Y-%m-%d')
            print(f"  pull {ticker} reported={reported} reaction-day={d_str} "
                  f"(timing={timing or 'unknown'})...", end=' ', flush=True)
            df = fetch_av_options(ticker, d_str, api_key)
            call_count += 1
            if df.empty:
                print("(no data)")
            else:
                df['volume'] = pd.to_numeric(df.get('volume', 0), errors='coerce').fillna(0)
                df['open_interest'] = pd.to_numeric(df.get('open_interest', 0), errors='coerce').fillna(0)
                vol = int(df['volume'].sum())
                oi = int(df['open_interest'].sum())
                n_contracts = len(df)
                per_ticker_volumes.append(vol)
                detail_rows.append({
                    'ticker': ticker, 'reported_date': reported,
                    'report_time': timing or 'unknown',
                    'reaction_day': d_str,
                    'contracts': n_contracts,
                    'volume': vol, 'open_interest': oi,
                })
                print(f"vol={vol:>10,}  OI={oi:>12,}")
            if call_count < total_calls_estimate:
                time.sleep(13)

        if per_ticker_volumes:
            arr = pd.Series(per_ticker_volumes)
            summary_rows.append({
                'ticker': ticker,
                'timing': primary_timing,
                'n_quarters': len(per_ticker_volumes),
                'ew_vol_min':    int(arr.min()),
                'ew_vol_median': int(arr.median()),
                'ew_vol_max':    int(arr.max()),
                'ew_vol_mean':   int(arr.mean()),
            })

    conn.close()

    if detail_rows:
        ddf = pd.DataFrame(detail_rows)
        print("\n" + "=" * 100)
        print(f"  Per-quarter reaction-day options volume ({len(ddf)} datapoints)")
        print("=" * 100)
        print(ddf.to_string(index=False))

    if summary_rows:
        sdf = pd.DataFrame(summary_rows)
        print("\n" + "=" * 110)
        print(f"  Earnings-window options volume ({args.quarters}Q lookback)")
        print("=" * 110)
        print(sdf.to_string(index=False))


if __name__ == '__main__':
    main()
