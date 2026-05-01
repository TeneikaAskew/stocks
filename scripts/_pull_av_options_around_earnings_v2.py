"""Pull AV HISTORICAL_OPTIONS around historical earnings dates with
timing-aware reaction-day selection:

  AMC: pull D+1 (intraday post-overnight-gap session)
  BMO: pull D    (intraday after the 6:30 AM release)

Operates on the 4 new BMO tickers (JPM, JNJ, WMT, PG) plus LLY (rerun
with BMO-correct date). The 4 original AMC tickers (AVGO, GOOG, NVDA,
FDX) already have 12Q D+1 data from the earlier _pull script.

12Q × 5 = 60 calls × ~13s ≈ 13 min wall clock.
"""
import subprocess
import time
from datetime import timedelta

import pandas as pd
import psycopg2
import psycopg2.extras
import requests

GCLOUD = r'C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
PROJECT = 'adept-mountain-474619-d4'
DB_HOST = '34.24.66.12'
TICKERS = ['LLY', 'JPM', 'JNJ', 'WMT', 'PG']  # all BMO
LAST_N_QUARTERS = 12

TIMING_OVERRIDES = {  # match v2 driver
    'LLY': 'premarket', 'JPM': 'premarket', 'JNJ': 'premarket',
    'WMT': 'premarket', 'PG': 'premarket',
}


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


def fetch_recent_reports(conn, ticker, n=LAST_N_QUARTERS):
    sql = """
        SELECT reported_date FROM earnings_history
        WHERE ticker = %s AND reported_date IS NOT NULL
          AND (reported_eps > 0 OR reported_eps < 0)
        ORDER BY reported_date DESC LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (ticker, n))
        return [r[0] for r in cur.fetchall()]


def first_trading_day_on_or_after(conn, ticker, d):
    """For BMO: D itself is the reaction day (assuming d is a weekday).
    Returns first trading-bar date >= d, in case d is weekend/holiday."""
    sql = """SELECT date FROM market_data_daily
             WHERE ticker = %s AND date >= %s ORDER BY date LIMIT 1"""
    with conn.cursor() as cur:
        cur.execute(sql, (ticker, d))
        row = cur.fetchone()
        return row[0] if row else None


def main():
    api_key = secret('av-api-key')
    conn = connect()

    summary_rows = []
    detail_rows = []
    call_count = 0
    total_calls = sum(LAST_N_QUARTERS for _ in TICKERS)

    for ticker in TICKERS:
        timing = TIMING_OVERRIDES.get(ticker, 'postmarket')
        reports = fetch_recent_reports(conn, ticker)
        if not reports:
            print(f"[{ticker}] no reports; skipping")
            continue
        print(f"\n[{ticker}] timing={timing}, {len(reports)} recent reports")

        per_ticker_volumes = []
        for reported in reports:
            # BMO: pull D itself. AMC: pull D+1.
            target_d = first_trading_day_on_or_after(conn, ticker, reported)
            if timing != 'premarket':
                # AMC fallback (shouldn't trigger here — this script is BMO-only)
                target_d = first_trading_day_on_or_after(conn, ticker, reported + timedelta(days=1))
            if target_d is None:
                continue
            d_str = target_d.strftime('%Y-%m-%d')
            print(f"  pull {ticker} reaction-day={d_str} (reported={reported})...", end=' ', flush=True)
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
                    'reaction_day': d_str, 'contracts': n_contracts,
                    'volume': vol, 'open_interest': oi,
                })
                print(f"vol={vol:>10,}  OI={oi:>12,}")
            if call_count < total_calls:
                time.sleep(13)

        if per_ticker_volumes:
            arr = pd.Series(per_ticker_volumes)
            summary_rows.append({
                'ticker': ticker, 'timing': timing,
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
        print("  Earnings-window options volume — BMO tickers (12Q lookback)")
        print("=" * 110)
        print(sdf.to_string(index=False))


if __name__ == '__main__':
    main()
