"""One-shot: backfill 10 years of daily OHLCV into market_data_daily for
the Phase 0 case-study tickers.

Capped at 10 years per repo policy (older data is regime-drifted noise).
Idempotent — uses ON CONFLICT DO UPDATE on (ticker, date).
"""
import os
import subprocess
import sys
import time
from datetime import date, timedelta

import pandas as pd
import psycopg2
import psycopg2.extras
import requests

GCLOUD = r'C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
PROJECT = 'adept-mountain-474619-d4'
DB_HOST = '34.24.66.12'
TICKERS = ['GOOG', 'NVDA', 'LLY', 'FDX']  # AVGO already covered
LOOKBACK_DAYS = 365 * 10  # 10y cap


def secret(name: str) -> str:
    return subprocess.check_output(
        [GCLOUD, 'secrets', 'versions', 'access', 'latest',
         f'--secret={name}', f'--project={PROJECT}'],
        text=True, timeout=15,
    ).rstrip('\n')


def fetch_av_daily(ticker: str, api_key: str) -> pd.DataFrame:
    url = 'https://www.alphavantage.co/query'
    params = {
        'function': 'TIME_SERIES_DAILY',
        'symbol': ticker,
        'outputsize': 'full',
        'apikey': api_key,
    }
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    if 'Information' in data:
        print(f"  AV info: {data['Information']}")
        return pd.DataFrame()
    series = data.get('Time Series (Daily)') or {}
    if not series:
        print(f"  empty time series; payload keys: {list(data.keys())}")
        return pd.DataFrame()

    cutoff = date.today() - timedelta(days=LOOKBACK_DAYS)
    rows = []
    for d_str, ohlc in series.items():
        d = pd.to_datetime(d_str).date()
        if d < cutoff:
            continue
        rows.append({
            'ticker': ticker,
            'date': d,
            'open':   float(ohlc['1. open']),
            'high':   float(ohlc['2. high']),
            'low':    float(ohlc['3. low']),
            'close':  float(ohlc['4. close']),
            'volume': int(ohlc['5. volume']),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values('date').reset_index(drop=True)
    return df


def main():
    api_key = secret('av-api-key')
    conn = psycopg2.connect(
        host=DB_HOST,
        user=secret('db-trading-user'),
        password=secret('db-trading-pass'),
        dbname='trading',
        sslmode='require',
    )
    total = 0
    with conn.cursor() as cur:
        for i, ticker in enumerate(TICKERS):
            print(f"[{i+1}/{len(TICKERS)}] AV TIME_SERIES_DAILY for {ticker} (10y cap)...")
            df = fetch_av_daily(ticker, api_key)
            if df.empty:
                print(f"  no rows returned")
                continue
            print(f"  got {len(df)} bars: {df['date'].min()} .. {df['date'].max()}")
            for _, row in df.iterrows():
                cur.execute("""
                    INSERT INTO market_data_daily
                      (ticker, date, open, high, low, close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker, date) DO UPDATE
                    SET open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low  = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume
                """, (row['ticker'], row['date'],
                      row['open'], row['high'], row['low'],
                      row['close'], row['volume']))
                total += 1
            conn.commit()
            if i < len(TICKERS) - 1:
                time.sleep(13)  # AV: 5/min cap
    conn.close()
    print(f"\nBackfilled {total} OHLCV rows (10y cap)")


if __name__ == '__main__':
    main()
