"""One-shot: pull AV HISTORICAL_OPTIONS for the 5 case-study tickers
to populate options_volume so the playability_score can be computed
properly.

We pull the most recent available date and aggregate per-ticker total
options volume (sum across all contracts). This gives us a current
liquidity measure for ALL 5 tickers regardless of whether they're in
earnings_calendar.

The AV endpoint is per-ticker, per-date. We pull yesterday's date
(today's options data isn't yet final). 5 tickers × 1 date = 5 calls,
under the 5-rpm cap with sleep.
"""
import subprocess
import time
from datetime import date, timedelta

import pandas as pd
import requests

GCLOUD = r'C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
PROJECT = 'adept-mountain-474619-d4'
TICKERS = ['AVGO', 'GOOG', 'NVDA', 'LLY', 'FDX']


def secret(name: str) -> str:
    return subprocess.check_output(
        [GCLOUD, 'secrets', 'versions', 'access', 'latest',
         f'--secret={name}', f'--project={PROJECT}'],
        text=True, timeout=15,
    ).rstrip('\n')


def fetch_av_options(symbol: str, fetch_date: str, api_key: str) -> pd.DataFrame:
    url = 'https://www.alphavantage.co/query'
    params = {
        'function': 'HISTORICAL_OPTIONS',
        'symbol':   symbol,
        'date':     fetch_date,
        'apikey':   api_key,
        'datatype': 'json',
    }
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    if data.get('message') != 'success':
        msg = data.get('message') or data.get('Information') or list(data.keys())
        print(f"  {symbol} {fetch_date}: {msg}")
        return pd.DataFrame()
    records = data.get('data', [])
    return pd.DataFrame(records) if records else pd.DataFrame()


def main():
    api_key = secret('av-api-key')
    # Step back to last weekday with data — try today, then today-1, etc.
    candidates = [date.today() - timedelta(days=i) for i in range(0, 5)]

    print(f"Pulling AV HISTORICAL_OPTIONS for {len(TICKERS)} tickers...")
    summaries = []
    for i, ticker in enumerate(TICKERS):
        print(f"\n[{i+1}/{len(TICKERS)}] {ticker}")
        df = pd.DataFrame()
        used_date = None
        for d in candidates:
            d_str = d.strftime('%Y-%m-%d')
            df = fetch_av_options(ticker, d_str, api_key)
            if not df.empty:
                used_date = d_str
                break
            time.sleep(13)
        if df.empty:
            print(f"  no data for any of {len(candidates)} dates")
            continue
        # Aggregate
        df['volume'] = pd.to_numeric(df.get('volume', 0), errors='coerce').fillna(0)
        df['open_interest'] = pd.to_numeric(df.get('open_interest', 0), errors='coerce').fillna(0)
        total_vol = int(df['volume'].sum())
        total_oi = int(df['open_interest'].sum())
        n_contracts = len(df)
        summaries.append({
            'ticker': ticker,
            'date': used_date,
            'contracts': n_contracts,
            'total_options_volume': total_vol,
            'total_open_interest': total_oi,
        })
        print(f"  date={used_date}  contracts={n_contracts:>5}  volume={total_vol:>10,}  OI={total_oi:>12,}")
        if i < len(TICKERS) - 1:
            time.sleep(13)

    if summaries:
        sdf = pd.DataFrame(summaries)
        print("\n" + "=" * 80)
        print("  Per-ticker options liquidity")
        print("=" * 80)
        print(sdf.to_string(index=False))


if __name__ == '__main__':
    main()
