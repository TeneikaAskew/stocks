"""Validation: re-derive Phase 0 numbers from raw OHLCV for the most
recent valid report per ticker, then check against what the Phase 0
script said.

Two things we're checking:
1. Math correctness — does my pre_gap / post_gap formula match a manual
   computation from raw bars?
2. Timing semantics — for premarket (BMO) reporters like LLY, is the
   actual "earnings reaction" gap the D-open gap (not the D+1-open gap)?

For each ticker's most recent earnings (filtering pre-report
placeholders), prints:
  - Raw OHLCV: D-1, D, D+1, D+2, D+5, D+10 (bars exactly as in DB)
  - My pre_gap_pct  = (D open  - D-1 close) / D-1 close × 100
  - My post_gap_pct = (D+1 open - D close)   / D close   × 100
  - Earnings_time from earnings_calendar (postmarket / premarket / unknown)
  - REACTION_GAP based on timing:
      premarket (BMO) -> reaction = pre_gap (D open vs D-1 close)
      postmarket (AMC) -> reaction = post_gap (D+1 open vs D close)
  - Sustain: where the price ended up 5d / 10d after the reaction
"""
import subprocess
from datetime import timedelta

import pandas as pd
import psycopg2
import psycopg2.extras

GCLOUD = r'C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
PROJECT = 'adept-mountain-474619-d4'
DB_HOST = '34.24.66.12'
TICKERS = ['AVGO', 'GOOG', 'NVDA', 'LLY', 'FDX']


def s(n):
    return subprocess.check_output(
        [GCLOUD, 'secrets', 'versions', 'access', 'latest',
         f'--secret={n}', f'--project={PROJECT}'],
        text=True, timeout=15).rstrip('\n')


def connect():
    return psycopg2.connect(host=DB_HOST, user=s('db-trading-user'),
                            password=s('db-trading-pass'),
                            dbname='trading', sslmode='require')


def latest_report(conn, ticker):
    """Most recent valid (non-placeholder) report."""
    sql = """
        SELECT reported_date, fiscal_date_ending,
               reported_eps, estimated_eps, surprise_pct
        FROM earnings_history
        WHERE ticker = %s AND reported_date IS NOT NULL
          AND reported_eps IS NOT NULL AND reported_eps != 0
        ORDER BY reported_date DESC LIMIT 1
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (ticker,))
        return cur.fetchone()


def daily_window(conn, ticker, reported):
    sql = """
        SELECT date, open, high, low, close, volume FROM market_data_daily
        WHERE ticker = %s AND date BETWEEN %s AND %s ORDER BY date
    """
    start = reported - timedelta(days=15)
    end = reported + timedelta(days=20)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (ticker, start, end))
        df = pd.DataFrame(cur.fetchall())
    if not df.empty:
        df['date'] = pd.to_datetime(df['date']).dt.date
        df = df.sort_values('date').reset_index(drop=True)
    return df


def earnings_time(conn, ticker):
    """Get the consensus timing across data sources."""
    sql = """
        SELECT earnings_time, COUNT(*) c FROM earnings_calendar
        WHERE ticker = %s AND earnings_time IS NOT NULL
        GROUP BY earnings_time ORDER BY c DESC LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(sql, (ticker,))
        row = cur.fetchone()
        return row[0] if row else 'unknown'


def main():
    pd.set_option('display.float_format', lambda x: f'{x:.2f}')
    print("Connecting to Cloud SQL...\n")

    with connect() as conn:
        for ticker in TICKERS:
            print('=' * 100)
            print(f'  {ticker}')
            print('=' * 100)

            r = latest_report(conn, ticker)
            if r is None:
                print('  no recent report')
                continue

            reported = r['reported_date']
            timing = earnings_time(conn, ticker)
            print(f"\n  Most recent report: {reported}  (fiscal Q ending {r['fiscal_date_ending']})")
            print(f"  EPS: actual {r['reported_eps']}  vs est {r['estimated_eps']}  "
                  f"(surprise {r['surprise_pct']}%)")
            print(f"  earnings_time:  {timing}")

            df = daily_window(conn, ticker, reported)
            on_after = df[df['date'] >= reported]
            if df.empty or on_after.empty:
                print('  no daily bars')
                continue
            d_idx = on_after.index[0]
            if d_idx == 0 or d_idx + 1 >= len(df):
                print('  insufficient surrounding bars')
                continue

            # Print the raw window for visual inspection
            relevant_idx = list(range(max(0, d_idx - 1),
                                     min(len(df), d_idx + 11)))
            print(f"\n  Raw OHLCV (D = {df.iloc[d_idx]['date']}):")
            for i in relevant_idx:
                row = df.iloc[i]
                tag = ''
                if i == d_idx - 1: tag = ' <- D-1'
                elif i == d_idx:   tag = ' <- D (reported_date)'
                elif i == d_idx + 1: tag = ' <- D+1'
                elif i == d_idx + 5: tag = ' <- D+5'
                elif i == d_idx + 10: tag = ' <- D+10'
                print(f"    {row['date']}  o={float(row['open']):>9.2f}  "
                      f"h={float(row['high']):>9.2f}  l={float(row['low']):>9.2f}  "
                      f"c={float(row['close']):>9.2f}  v={int(row['volume']):>14,}{tag}")

            # Manual gap math
            d_minus_1 = df.iloc[d_idx - 1]
            d = df.iloc[d_idx]
            d_plus_1 = df.iloc[d_idx + 1]
            d_plus_5 = df.iloc[d_idx + 5] if d_idx + 5 < len(df) else None
            d_plus_10 = df.iloc[d_idx + 10] if d_idx + 10 < len(df) else None

            pre_gap = (float(d['open']) - float(d_minus_1['close'])) / float(d_minus_1['close']) * 100
            post_gap = (float(d_plus_1['open']) - float(d['close'])) / float(d['close']) * 100

            print(f"\n  Manual gap math (verifying the formulas):")
            print(f"    pre_gap   = (D open {d['open']:.2f} - D-1 close {d_minus_1['close']:.2f})"
                  f" / D-1 close = {pre_gap:+.2f}%")
            print(f"    post_gap  = (D+1 open {d_plus_1['open']:.2f} - D close {d['close']:.2f})"
                  f" / D close   = {post_gap:+.2f}%")

            # The CORRECT reaction gap depends on timing
            if timing == 'premarket':
                reaction_pct = pre_gap
                reaction_label = 'pre_gap (BMO -> reaction at D open)'
                # Sustain anchored at D close (post-reaction-day close)
                sustain_anchor = float(d['close'])
                anchor_label = 'D close'
            elif timing == 'postmarket':
                reaction_pct = post_gap
                reaction_label = 'post_gap (AMC -> reaction at D+1 open)'
                sustain_anchor = float(d_plus_1['open'])
                anchor_label = 'D+1 open'
            else:
                reaction_pct = post_gap
                reaction_label = 'post_gap (AMC ASSUMED — earnings_time unknown)'
                sustain_anchor = float(d_plus_1['open'])
                anchor_label = 'D+1 open'

            print(f"\n  TIMING-CORRECT reaction:")
            print(f"    earnings_time  = {timing}")
            print(f"    reaction_gap   = {reaction_pct:+.2f}%   ({reaction_label})")

            if d_plus_5 is not None:
                sustain_5d = (float(d_plus_5['close']) - sustain_anchor) / sustain_anchor * 100
                print(f"    sustain_5d     = (D+5 close {d_plus_5['close']:.2f} - {anchor_label} {sustain_anchor:.2f})"
                      f" / {anchor_label} = {sustain_5d:+.2f}%")
            if d_plus_10 is not None:
                sustain_10d = (float(d_plus_10['close']) - sustain_anchor) / sustain_anchor * 100
                print(f"    sustain_10d    = {sustain_10d:+.2f}%")

            # What Phase 0 reported (from script output)
            print(f"\n  What Phase 0 reported earlier:")
            # Look up from earlier output (best-effort hardcoded for known recent rows)
            phase0_known = {
                ('AVGO', '2026-03-04'): {'pre_gap': 0.59, 'post_gap': 3.98, 'sus_5d': 3.45, 'sus_10d': -4.31},
                ('GOOG', '2026-02-04'): {'pre_gap': 0.90, 'post_gap': -6.04, 'sus_5d': -0.60, 'sus_10d': -3.08},
                ('NVDA', '2026-02-25'): {'pre_gap': 0.83, 'post_gap': -0.66, 'sus_5d': -5.78, 'sus_10d': -4.24},
                ('LLY',  '2026-02-04'): {'pre_gap': 7.14, 'post_gap': -3.76, 'sus_5d': -4.72, 'sus_10d': -3.97},
                ('FDX',  '2026-03-19'): {'pre_gap': -1.20, 'post_gap': 6.94, 'sus_5d': -8.21, 'sus_10d': -5.04},
            }
            key = (ticker, reported.strftime('%Y-%m-%d'))
            phase0 = phase0_known.get(key)
            if phase0:
                for k in ('pre_gap', 'post_gap', 'sus_5d', 'sus_10d'):
                    print(f"    {k:10s} : {phase0[k]:+.2f}%")
                # Mismatch check
                tol = 0.01
                mismatch = []
                if abs(phase0['pre_gap'] - pre_gap) > tol:
                    mismatch.append(f"pre_gap manual {pre_gap:+.2f}% vs phase0 {phase0['pre_gap']:+.2f}%")
                if abs(phase0['post_gap'] - post_gap) > tol:
                    mismatch.append(f"post_gap manual {post_gap:+.2f}% vs phase0 {phase0['post_gap']:+.2f}%")
                if mismatch:
                    print(f"  [!] MATH MISMATCH: {'; '.join(mismatch)}")
                else:
                    print(f"  [OK] manual math matches phase0 numbers")

            # Critical-finding flag
            if timing == 'premarket':
                print(f"\n  [!] BMO timing — Phase 0's 'pre_gap' field IS the actual earnings reaction.")
                print(f"      Phase 0's 'post_gap' field is next-day drift after the reaction had a session to digest.")
                print(f"      Production schema needs to compute reaction_gap based on earnings_time.")
            elif timing == 'unknown':
                print(f"\n  [?] earnings_time = unknown. Phase 0 assumed AMC. AVGO/NVDA/FDX always report AMC")
                print(f"      so the assumption holds, but earnings_calendar should be enriched with timing.")


if __name__ == '__main__':
    main()
