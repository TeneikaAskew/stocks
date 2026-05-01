"""Pull AV HISTORICAL_OPTIONS around each historical earnings date for
the 5 case-study tickers, to measure typical earnings-window options
volume vs the current snapshot.

Hypothesis: FDX's 5,706 contracts on 2026-04-30 is post-earnings quiet
(last report 2026-03-19, ~6 weeks ago). Around its actual report
dates the chain is much more active.

Strategy: for each of the last 4 reported_dates per ticker, pull AV
HISTORICAL_OPTIONS for D+1 (the trading day AFTER the report) — that's
when the chain is most active.

5 tickers × 4 quarters = 20 calls @ 13s sleep ≈ 4.5 min total.
"""
import subprocess
import time
from datetime import date, timedelta

import pandas as pd
import psycopg2
import psycopg2.extras
import requests

GCLOUD = r'C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
PROJECT = 'adept-mountain-474619-d4'
DB_HOST = '34.24.66.12'
TICKERS = ['AVGO', 'GOOG', 'NVDA', 'LLY', 'FDX']
LAST_N_QUARTERS = 12  # match the 12Q reaction-profile lookback

# Today's snapshot from earlier pull (for comparison)
TODAY_SNAPSHOT = {
    'AVGO':  230123, 'GOOG':  676374, 'NVDA': 4108276,
    'LLY':    89364, 'FDX':     5706,
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
    url = 'https://www.alphavantage.co/query'
    r = requests.get(url, params={
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
          AND reported_eps IS NOT NULL AND reported_eps != 0
        ORDER BY reported_date DESC LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (ticker, n))
        return [r[0] for r in cur.fetchall()]


def next_trading_day(conn, ticker, d):
    """Find the first market_data_daily date strictly > d for this ticker."""
    sql = """SELECT date FROM market_data_daily
             WHERE ticker = %s AND date > %s ORDER BY date LIMIT 1"""
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
    for ticker in TICKERS:
        reports = fetch_recent_reports(conn, ticker)
        if not reports:
            print(f"[{ticker}] no reports; skipping")
            continue
        print(f"\n[{ticker}] {len(reports)} recent reports")
        per_ticker_volumes = []
        for reported in reports:
            d_plus_1 = next_trading_day(conn, ticker, reported)
            if d_plus_1 is None:
                continue
            d_str = d_plus_1.strftime('%Y-%m-%d')
            print(f"  pulling AV options for {ticker} D+1={d_str}...", end=' ', flush=True)
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
                    'd_plus_1': d_str, 'contracts': n_contracts,
                    'volume': vol, 'open_interest': oi,
                })
                print(f"vol={vol:>10,}  OI={oi:>12,}")
            if call_count < len(TICKERS) * LAST_N_QUARTERS:
                time.sleep(13)
        if per_ticker_volumes:
            arr = pd.Series(per_ticker_volumes)
            summary_rows.append({
                'ticker': ticker,
                'n_quarters_sampled': len(per_ticker_volumes),
                'earnings_vol_min':    int(arr.min()),
                'earnings_vol_median': int(arr.median()),
                'earnings_vol_max':    int(arr.max()),
                'earnings_vol_mean':   int(arr.mean()),
                'today_snapshot':      TODAY_SNAPSHOT.get(ticker),
            })

    conn.close()

    if detail_rows:
        ddf = pd.DataFrame(detail_rows)
        print("\n" + "=" * 90)
        print("  Per-quarter D+1 options volume")
        print("=" * 90)
        print(ddf.to_string(index=False))

    if summary_rows:
        sdf = pd.DataFrame(summary_rows)
        sdf['vs_today_x'] = sdf.apply(
            lambda r: round(r['earnings_vol_median'] / r['today_snapshot'], 1)
                      if r['today_snapshot'] else None, axis=1)
        print("\n" + "=" * 110)
        print("  Earnings-window options volume vs today's snapshot")
        print("=" * 110)
        print(sdf.to_string(index=False))


if __name__ == '__main__':
    main()
