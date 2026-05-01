"""One-shot: backfill earnings_history + 10y market_data_daily for the
BMO validation tickers (JPM, JNJ, WMT, PG).

Takes ~5 min wall clock (8 AV calls @ 13s spacing).
Capped at 10 years per repo policy.
"""
import subprocess
import time
from datetime import date, timedelta

import pandas as pd
import psycopg2
import requests

GCLOUD = r'C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
PROJECT = 'adept-mountain-474619-d4'
DB_HOST = '34.24.66.12'
TICKERS = ['JPM', 'JNJ', 'WMT', 'PG']
LOOKBACK_DAYS = 365 * 10


def secret(name):
    return subprocess.check_output(
        [GCLOUD, 'secrets', 'versions', 'access', 'latest',
         f'--secret={name}', f'--project={PROJECT}'],
        text=True, timeout=15).rstrip('\n')


def conn():
    return psycopg2.connect(host=DB_HOST, user=secret('db-trading-user'),
                            password=secret('db-trading-pass'),
                            dbname='trading', sslmode='require')


def safe_float(v):
    if v is None or v in ('None', '', 'null'):
        return None
    try:
        x = float(v)
        if x != x:  # NaN check
            return None
        return x
    except (TypeError, ValueError):
        return None


def fetch_av_earnings(ticker, api_key):
    r = requests.get('https://www.alphavantage.co/query', params={
        'function': 'EARNINGS', 'symbol': ticker, 'apikey': api_key,
    }, timeout=30)
    r.raise_for_status()
    data = r.json()
    if 'Information' in data:
        print(f"  AV info: {data['Information']}")
        return pd.DataFrame()
    quarterly = data.get('quarterlyEarnings') or []
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


def fetch_av_daily(ticker, api_key):
    r = requests.get('https://www.alphavantage.co/query', params={
        'function': 'TIME_SERIES_DAILY', 'symbol': ticker,
        'outputsize': 'full', 'apikey': api_key,
    }, timeout=60)
    r.raise_for_status()
    data = r.json()
    if 'Information' in data:
        print(f"  AV info: {data['Information']}")
        return pd.DataFrame()
    series = data.get('Time Series (Daily)') or {}
    cutoff = date.today() - timedelta(days=LOOKBACK_DAYS)
    rows = []
    for d_str, ohlc in series.items():
        d = pd.to_datetime(d_str).date()
        if d < cutoff:
            continue
        rows.append({
            'ticker': ticker, 'date': d,
            'open':   float(ohlc['1. open']),
            'high':   float(ohlc['2. high']),
            'low':    float(ohlc['3. low']),
            'close':  float(ohlc['4. close']),
            'volume': int(ohlc['5. volume']),
        })
    return pd.DataFrame(rows).sort_values('date').reset_index(drop=True) if rows else pd.DataFrame()


def main():
    api_key = secret('av-api-key')
    db = conn()
    eh_total = mdd_total = 0
    calls = 0
    with db.cursor() as cur:
        for i, ticker in enumerate(TICKERS):
            # 1. earnings_history
            print(f"[{i+1}/{len(TICKERS)}] {ticker}: AV EARNINGS...")
            eh = fetch_av_earnings(ticker, api_key)
            calls += 1
            if not eh.empty:
                # Filter NaN reported_eps in Python (also enforce 10y cap on backfill — though earnings is per-quarter so that's max 40 rows anyway)
                eh = eh[eh['reported_eps'].notna() | eh['estimated_eps'].notna()]
                # Keep only last 10 years of fiscal_date_ending
                cutoff = date.today() - timedelta(days=LOOKBACK_DAYS)
                eh = eh[eh['fiscal_date_ending'] >= cutoff]
                print(f"  {len(eh)} quarterly rows (10y capped)")
                for _, row in eh.iterrows():
                    cur.execute("""
                        INSERT INTO earnings_history
                          (ticker, fiscal_date_ending, reported_date,
                           reported_eps, estimated_eps, surprise, surprise_pct)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (ticker, fiscal_date_ending) DO UPDATE
                        SET reported_date = EXCLUDED.reported_date,
                            reported_eps = EXCLUDED.reported_eps,
                            estimated_eps = EXCLUDED.estimated_eps,
                            surprise = EXCLUDED.surprise,
                            surprise_pct = EXCLUDED.surprise_pct
                    """, (row['ticker'], row['fiscal_date_ending'], row['reported_date'],
                          row['reported_eps'], row['estimated_eps'],
                          row['surprise'], row['surprise_pct']))
                    eh_total += 1
                db.commit()
            time.sleep(13)

            # 2. market_data_daily
            print(f"  {ticker}: AV TIME_SERIES_DAILY (10y)...")
            mdd = fetch_av_daily(ticker, api_key)
            calls += 1
            if not mdd.empty:
                print(f"  {len(mdd)} bars: {mdd['date'].min()} .. {mdd['date'].max()}")
                for _, row in mdd.iterrows():
                    cur.execute("""
                        INSERT INTO market_data_daily
                          (ticker, date, open, high, low, close, volume)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (ticker, date) DO UPDATE
                        SET open = EXCLUDED.open,
                            high = EXCLUDED.high,
                            low  = EXCLUDED.low,
                            close = EXCLUDED.close,
                            volume = EXCLUDED.volume
                    """, (row['ticker'], row['date'], row['open'], row['high'],
                          row['low'], row['close'], row['volume']))
                    mdd_total += 1
                db.commit()
            if i < len(TICKERS) - 1:
                time.sleep(13)
    db.close()
    print(f"\nDone. {eh_total} earnings_history rows, {mdd_total} market_data_daily rows ({calls} AV calls).")


if __name__ == '__main__':
    main()
