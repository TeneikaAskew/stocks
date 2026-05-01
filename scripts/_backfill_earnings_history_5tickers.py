"""One-shot: backfill AV EARNINGS into earnings_history for the Phase 0
case-study tickers.

Rationale: fetch-earnings-history runs weekly but only for tickers in the
next 90d of earnings_calendar. GOOG / NVDA / LLY / FDX aren't in that
window today, so their history is missing. We backfill once so Phase 0
can show all 5 tickers, then validate the per-ticker reaction profile.
"""
import os
import subprocess
import sys
import time

import pandas as pd
import psycopg2
import psycopg2.extras
import requests

GCLOUD = r'C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
PROJECT = 'adept-mountain-474619-d4'
DB_HOST = '34.24.66.12'
TICKERS = ['GOOG', 'NVDA', 'LLY', 'FDX']  # AVGO already has rows


def secret(name: str) -> str:
    return subprocess.check_output(
        [GCLOUD, 'secrets', 'versions', 'access', 'latest',
         f'--secret={name}', f'--project={PROJECT}'],
        text=True, timeout=15,
    ).rstrip('\n')


def fetch_av_earnings(ticker: str, api_key: str) -> pd.DataFrame:
    url = 'https://www.alphavantage.co/query'
    params = {'function': 'EARNINGS', 'symbol': ticker, 'apikey': api_key}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if 'Information' in data:
        print(f"  AV info for {ticker}: {data['Information']}")
        return pd.DataFrame()
    quarterly = data.get('quarterlyEarnings') or []
    if not quarterly:
        return pd.DataFrame()

    def safe_float(v):
        if v is None or v in ('None', '', 'null'):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    rows = []
    for q in quarterly:
        fiscal = q.get('fiscalDateEnding')
        reported = q.get('reportedDate')
        if not fiscal:
            continue
        rows.append({
            'ticker': ticker,
            'fiscal_date_ending': pd.to_datetime(fiscal).date(),
            'reported_date': pd.to_datetime(reported).date() if reported else None,
            'reported_eps': safe_float(q.get('reportedEPS')),
            'estimated_eps': safe_float(q.get('estimatedEPS')),
            'surprise': safe_float(q.get('surprise')),
            'surprise_pct': safe_float(q.get('surprisePercentage')),
        })
    return pd.DataFrame(rows)


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
            print(f"[{i+1}/{len(TICKERS)}] AV EARNINGS for {ticker}...")
            df = fetch_av_earnings(ticker, api_key)
            if df.empty:
                print(f"  no quarterly history returned")
                continue
            print(f"  got {len(df)} quarterly rows")
            for _, row in df.iterrows():
                cur.execute("""
                    INSERT INTO earnings_history
                      (ticker, fiscal_date_ending, reported_date,
                       reported_eps, estimated_eps, surprise, surprise_pct)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker, fiscal_date_ending) DO UPDATE
                    SET reported_date = EXCLUDED.reported_date,
                        reported_eps = EXCLUDED.reported_eps,
                        estimated_eps = EXCLUDED.estimated_eps,
                        surprise = EXCLUDED.surprise,
                        surprise_pct = EXCLUDED.surprise_pct
                """, (row['ticker'], row['fiscal_date_ending'], row['reported_date'],
                      row['reported_eps'], row['estimated_eps'],
                      row['surprise'], row['surprise_pct']))
                total += 1
            conn.commit()
            if i < len(TICKERS) - 1:
                time.sleep(13)  # AV: 5/min cap
    conn.close()
    print(f"\nBackfilled {total} rows into earnings_history")


if __name__ == '__main__':
    main()
