"""One-shot: backfill earnings_history (with Yahoo timing) + 10y OHLCV
for the 22 tickers that reported on Tue 2026-04-28, then run
compute_earnings_reactions for them.

This is the demo-data backfill so we can render the playability section
of the 4/28 replay brief with real numbers.

Estimated ~12 min wall clock:
  22 × 2 AV calls (EARNINGS + TIME_SERIES_DAILY) = 44 calls @ 13s = ~10 min
  + 22 yfinance timing calls (fast, no rate limit)
  + compute_earnings_reactions (~30s on 22 tickers)
"""
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import psycopg2
import requests
import time

GCLOUD = r'C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
PROJECT = 'adept-mountain-474619-d4'
DB_HOST = '34.24.66.12'
LOOKBACK_DAYS = 365 * 10

# 22 tickers from Tue 4/28: 12 BMO + 10 AMC
TICKERS = [
    # BMO
    'KO', 'GLW', 'GM', 'UPS', 'BP', 'SPOT', 'EPD', 'GLXY',
    'CNC', 'JBLU', 'PHM', 'ROK',
    # AMC
    'V', 'HOOD', 'BE', 'SBUX', 'STX', 'BKNG', 'TMUS', 'EXE',
    'ENPH', 'CZR',
]


def secret(n):
    return subprocess.check_output(
        [GCLOUD, 'secrets', 'versions', 'access', 'latest',
         f'--secret={n}', f'--project={PROJECT}'],
        text=True, timeout=15).rstrip('\n')


def conn():
    return psycopg2.connect(
        host=DB_HOST, user=secret('db-trading-user'),
        password=secret('db-trading-pass'),
        dbname='trading', sslmode='require',
    )


def safe_float(v):
    if v is None or v in ('None', '', 'null'):
        return None
    try:
        x = float(v)
        if x != x:
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
        print(f"  AV info: {data['Information'][:80]}")
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
            'report_time': (q.get('reportTime') or '').strip() or None,
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


def fetch_yahoo_timing(ticker):
    """Last 40 reports' timing per yfinance Ticker.get_earnings_dates."""
    try:
        import yfinance as yf
        df = yf.Ticker(ticker).get_earnings_dates(limit=40)
    except Exception:
        return {}
    if df is None or df.empty:
        return {}
    out = {}
    for ts, _ in df.iterrows():
        if ts is None or pd.isna(ts):
            continue
        ts = pd.Timestamp(ts)
        if ts.tzinfo is not None:
            try:
                ts = ts.tz_convert('US/Eastern')
            except Exception:
                ts = ts.tz_convert('UTC').tz_convert('US/Eastern')
        minutes = ts.hour * 60 + ts.minute
        if minutes >= 16 * 60:
            timing = 'post-market'
        elif minutes <= 9 * 60 + 30:
            timing = 'pre-market'
        else:
            continue
        out[ts.date()] = timing
    return out


def main():
    api_key = secret('av-api-key')
    db = conn()
    eh_total = mdd_total = 0
    calls = 0
    n = len(TICKERS)
    with db.cursor() as cur:
        for i, ticker in enumerate(TICKERS):
            print(f"[{i+1}/{n}] {ticker}: AV EARNINGS...")
            eh = fetch_av_earnings(ticker, api_key)
            calls += 1
            yt = fetch_yahoo_timing(ticker)
            print(f"  Yahoo timing: {len(yt)} reports")
            if not eh.empty:
                cutoff = date.today() - timedelta(days=LOOKBACK_DAYS)
                eh = eh[eh['fiscal_date_ending'] >= cutoff]
                # Merge Yahoo timing
                eh['yahoo_report_time'] = eh['reported_date'].map(
                    lambda d: yt.get(d) if d else None
                )
                disagreements = ((eh['report_time'].notna())
                                 & (eh['yahoo_report_time'].notna())
                                 & (eh['report_time'] != eh['yahoo_report_time'])).sum()
                print(f"  {len(eh)} rows, {disagreements} AV/Yahoo disagreements")
                for _, row in eh.iterrows():
                    cur.execute("""
                        INSERT INTO earnings_history
                          (ticker, fiscal_date_ending, reported_date,
                           reported_eps, estimated_eps, surprise, surprise_pct,
                           report_time, yahoo_report_time)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (ticker, fiscal_date_ending) DO UPDATE
                        SET reported_date     = EXCLUDED.reported_date,
                            reported_eps      = EXCLUDED.reported_eps,
                            estimated_eps     = EXCLUDED.estimated_eps,
                            surprise          = EXCLUDED.surprise,
                            surprise_pct      = EXCLUDED.surprise_pct,
                            report_time       = EXCLUDED.report_time,
                            yahoo_report_time = EXCLUDED.yahoo_report_time
                    """, (row['ticker'], row['fiscal_date_ending'], row['reported_date'],
                          row['reported_eps'], row['estimated_eps'],
                          row['surprise'], row['surprise_pct'],
                          row['report_time'], row['yahoo_report_time']))
                    eh_total += 1
                db.commit()
            time.sleep(13)

            print(f"  {ticker}: AV TIME_SERIES_DAILY...")
            mdd = fetch_av_daily(ticker, api_key)
            calls += 1
            if not mdd.empty:
                print(f"  {len(mdd)} bars")
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
            if i < n - 1:
                time.sleep(13)
    db.close()
    print(f"\nDone. {eh_total} earnings_history, {mdd_total} OHLCV bars ({calls} AV calls).")


if __name__ == '__main__':
    main()
