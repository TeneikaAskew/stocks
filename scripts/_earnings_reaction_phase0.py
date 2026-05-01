"""Phase 0 case-study driver — earnings reaction profile (revised).

Pulls last 12 quarters per ticker, filters out placeholder rows
(reported_eps NULL or 0 = AV pre-report row), computes per-quarter
gap/run/sustain stats with explicit directional bias vs magnitude
columns, plus reversal detection. Reports both 8Q and 12Q summaries
side-by-side so we can A/B the lookback length.
"""
import os
import subprocess
import sys
from datetime import timedelta

import pandas as pd
import psycopg2
import psycopg2.extras

GCLOUD = r'C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
PROJECT = 'adept-mountain-474619-d4'
DB_HOST = '34.24.66.12'
TICKERS = ['AVGO', 'GOOG', 'NVDA', 'LLY', 'FDX']
LOOKBACK_QUARTERS = 12  # pull 12, summarize at 8 and 12


def secret(name: str) -> str:
    return subprocess.check_output(
        [GCLOUD, 'secrets', 'versions', 'access', 'latest',
         f'--secret={name}', f'--project={PROJECT}'],
        text=True, timeout=15,
    ).rstrip('\n')


def connect():
    return psycopg2.connect(
        host=DB_HOST,
        user=secret('db-trading-user'),
        password=secret('db-trading-pass'),
        dbname='trading',
        sslmode='require',
    )


def fetch_earnings(conn, ticker: str) -> pd.DataFrame:
    sql = """
        SELECT ticker, fiscal_date_ending, reported_date,
               reported_eps, estimated_eps, surprise, surprise_pct
        FROM earnings_history
        WHERE ticker = %s
          AND reported_date IS NOT NULL
          AND reported_eps IS NOT NULL
          AND reported_eps != 0
        ORDER BY reported_date DESC
        LIMIT %s
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (ticker, LOOKBACK_QUARTERS))
        return pd.DataFrame(cur.fetchall())


def fetch_daily_window(conn, ticker: str, reported_date) -> pd.DataFrame:
    start = reported_date - timedelta(days=10)
    end = reported_date + timedelta(days=20)
    sql = """
        SELECT date, open, high, low, close, volume
        FROM market_data_daily
        WHERE ticker = %s AND date BETWEEN %s AND %s
        ORDER BY date
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (ticker, start, end))
        rows = cur.fetchall()
    df = pd.DataFrame(rows)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date']).dt.date
        df = df.sort_values('date').reset_index(drop=True)
    return df


def compute_reaction(eps_row: dict, daily: pd.DataFrame) -> dict | None:
    reported = eps_row['reported_date']
    if daily.empty:
        return None
    on_or_after = daily[daily['date'] >= reported]
    if on_or_after.empty:
        return None
    d_idx = on_or_after.index[0]
    if d_idx == 0:
        return None

    def safe(idx):
        return daily.iloc[idx] if 0 <= idx < len(daily) else None

    d_minus_1 = safe(d_idx - 1)
    d = safe(d_idx)
    d_plus_1 = safe(d_idx + 1)
    d_plus_3 = safe(d_idx + 3)
    d_plus_5 = safe(d_idx + 5)
    d_plus_10 = safe(d_idx + 10)
    if any(x is None for x in (d_minus_1, d, d_plus_1)):
        return None

    pre_gap = (float(d['open']) - float(d_minus_1['close'])) / float(d_minus_1['close']) * 100
    post_gap = (float(d_plus_1['open']) - float(d['close'])) / float(d['close']) * 100
    d1_high = (float(d_plus_1['high']) - float(d_plus_1['open'])) / float(d_plus_1['open']) * 100
    d1_low = (float(d_plus_1['low']) - float(d_plus_1['open'])) / float(d_plus_1['open']) * 100

    def sustain(later):
        if later is None:
            return None
        return (float(later['close']) - float(d_plus_1['open'])) / float(d_plus_1['open']) * 100

    s3 = sustain(d_plus_3)
    s5 = sustain(d_plus_5)
    s10 = sustain(d_plus_10)

    # Reversal: sign flip from post-gap to 5d sustain AND magnitude exceeds 0.5x the gap
    is_reversal_5d = None
    if s5 is not None and post_gap != 0:
        sign_flipped = (post_gap > 0) != (s5 > 0)
        magnitude_meaningful = abs(s5) >= abs(post_gap) * 0.5
        is_reversal_5d = sign_flipped and magnitude_meaningful

    direction_consistent_5d = None
    if s5 is not None and post_gap != 0:
        direction_consistent_5d = (post_gap > 0) == (s5 > 0)

    return {
        'fiscal_q': eps_row['fiscal_date_ending'],
        'reported': reported,
        'eps_act': eps_row['reported_eps'],
        'eps_est': eps_row['estimated_eps'],
        'surp_%': eps_row['surprise_pct'],
        'beat': (eps_row['surprise_pct'] or 0) > 0,
        'pre_gap_%': round(pre_gap, 2),
        'post_gap_%': round(post_gap, 2),
        'D+1_hi_%': round(d1_high, 2),
        'D+1_lo_%': round(d1_low, 2),
        'sus_3d_%': round(s3, 2) if s3 is not None else None,
        'sus_5d_%': round(s5, 2) if s5 is not None else None,
        'sus_10d_%': round(s10, 2) if s10 is not None else None,
        'dir_5d': direction_consistent_5d,
        'reversal_5d': is_reversal_5d,
    }


def summarize(rdf: pd.DataFrame, label: str) -> None:
    """Print summary for a slice of reaction rows."""
    if rdf.empty:
        print(f"  [{label}] no rows")
        return
    n = len(rdf)
    beat_rate = rdf['beat'].mean() * 100
    dir_bias = rdf['post_gap_%'].mean()                 # signed mean
    move_mag = rdf['post_gap_%'].abs().mean()           # absolute mean
    avg_pre = rdf['pre_gap_%'].mean()
    avg_d1_hi = rdf['D+1_hi_%'].mean()
    avg_d1_lo = rdf['D+1_lo_%'].mean()
    sus5 = rdf['sus_5d_%'].dropna()
    sus10 = rdf['sus_10d_%'].dropna()
    dir_consistent = rdf['dir_5d'].dropna()
    reversals = rdf['reversal_5d'].dropna()

    print(f"  [{label}] n={n}")
    print(f"    beat_rate            : {beat_rate:.0f}%")
    print(f"    directional_bias     : {dir_bias:+.2f}%   (signed mean post-gap — bullish vs bearish lean)")
    print(f"    move_magnitude       : {move_mag:.2f}%    (abs mean post-gap — typical reaction size)")
    print(f"    avg_pre_gap_%        : {avg_pre:+.2f}%")
    print(f"    avg D+1 high/low_%   : +{avg_d1_hi:.2f}% / {avg_d1_lo:.2f}%")
    if not sus5.empty:
        print(f"    avg sustain_5d_%     : {sus5.mean():+.2f}%")
    if not sus10.empty:
        print(f"    avg sustain_10d_%    : {sus10.mean():+.2f}%")
    if not dir_consistent.empty:
        print(f"    dir_consistency_5d   : {int(dir_consistent.sum())}/{int(dir_consistent.count())} "
              f"({dir_consistent.mean()*100:.0f}%)")
    if not reversals.empty:
        rev_count = int(reversals.sum())
        rev_n = int(reversals.count())
        print(f"    reversal_5d_count    : {rev_count}/{rev_n} "
              f"({rev_count/rev_n*100:.0f}% reversed direction within 5d)")


def main():
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 240)
    pd.set_option('display.float_format', lambda x: f'{x:.2f}')

    print("Connecting to Cloud SQL...")
    with connect() as conn:
        for ticker in TICKERS:
            print(f"\n{'=' * 110}")
            print(f"  {ticker}")
            print('=' * 110)

            eps_df = fetch_earnings(conn, ticker)
            if eps_df.empty:
                print(f"  [!] no earnings_history rows for {ticker}")
                continue
            print(f"\nearnings_history rows pulled: {len(eps_df)} (after placeholder filter)")

            stats_rows = []
            for _, row in eps_df.iterrows():
                daily = fetch_daily_window(conn, ticker, row['reported_date'])
                stats = compute_reaction(row.to_dict(), daily)
                if stats is None:
                    print(f"  {row['reported_date']}: [!] insufficient daily bars")
                    continue
                stats_rows.append(stats)
            if not stats_rows:
                continue
            rdf = pd.DataFrame(stats_rows)
            print("\nPer-quarter reactions (most recent first):")
            print(rdf.to_string(index=False))

            print(f"\n  A/B comparison — 8Q vs 12Q lookback:")
            summarize(rdf.head(8), 'last  8Q')
            summarize(rdf.head(12), 'last 12Q')


if __name__ == '__main__':
    main()
