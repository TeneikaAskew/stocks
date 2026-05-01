"""Phase 0 driver v2 — timing-aware (BMO vs AMC).

Reads earnings_calendar.earnings_time to pick the correct reaction
gap and sustain anchor per ticker:

  AMC (postmarket): reaction at D+1 open, sustain anchored at D+1 open
  BMO (premarket):  reaction at D   open, sustain anchored at D   close

If earnings_time is unknown for a ticker, falls back to AMC (which is
the default for AVGO/NVDA/FDX based on industry knowledge — those names
have only AV rows in earnings_calendar without timing data).

Also fixes the NaN placeholder filter: uses
`reported_eps > 0 OR reported_eps < 0` which excludes NULL, 0, and NaN.
"""
import subprocess
from datetime import timedelta

import pandas as pd
import psycopg2
import psycopg2.extras

GCLOUD = r'C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
PROJECT = 'adept-mountain-474619-d4'
DB_HOST = '34.24.66.12'

# 9-ticker set: 5 original (AMC) + 4 new BMO + LLY now correctly classified
AMC_TICKERS = ['AVGO', 'GOOG', 'NVDA', 'FDX']  # confirmed-or-assumed AMC
BMO_TICKERS = ['LLY', 'JPM', 'JNJ', 'WMT', 'PG']  # confirmed BMO
TICKERS = AMC_TICKERS + BMO_TICKERS

LOOKBACK_QUARTERS = 12

# Override map: when earnings_calendar.earnings_time is 'unknown' or missing,
# use this to enforce timing classification (industry knowledge).
TIMING_OVERRIDES = {
    'AVGO': 'postmarket', 'NVDA': 'postmarket', 'FDX': 'postmarket',
    'JPM': 'premarket', 'JNJ': 'premarket',
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


def fetch_earnings(conn, ticker):
    """Pull last 12Q. Filter NULL / 0 / NaN reported_eps in one expression."""
    sql = """
        SELECT ticker, fiscal_date_ending, reported_date,
               reported_eps, estimated_eps, surprise_pct
        FROM earnings_history
        WHERE ticker = %s AND reported_date IS NOT NULL
          AND (reported_eps > 0 OR reported_eps < 0)
        ORDER BY reported_date DESC LIMIT %s
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (ticker, LOOKBACK_QUARTERS))
        return pd.DataFrame(cur.fetchall())


def fetch_daily(conn, ticker, reported):
    sql = """SELECT date, open, high, low, close, volume FROM market_data_daily
             WHERE ticker = %s AND date BETWEEN %s AND %s ORDER BY date"""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (ticker, reported - timedelta(days=15),
                          reported + timedelta(days=20)))
        df = pd.DataFrame(cur.fetchall())
    if not df.empty:
        df['date'] = pd.to_datetime(df['date']).dt.date
        df = df.sort_values('date').reset_index(drop=True)
    return df


def resolve_timing(conn, ticker):
    """Get consensus earnings_time. Falls back to TIMING_OVERRIDES."""
    sql = """
        SELECT earnings_time, COUNT(*) c FROM earnings_calendar
        WHERE ticker = %s
          AND earnings_time IN ('premarket', 'postmarket')
        GROUP BY earnings_time ORDER BY c DESC LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(sql, (ticker,))
        row = cur.fetchone()
    if row and row[0]:
        return row[0]
    return TIMING_OVERRIDES.get(ticker, 'postmarket')


def compute_reaction(eps, daily, timing):
    """Timing-aware reaction stats.

    AMC: reaction = D+1 open vs D close; anchor = D+1 open
    BMO: reaction = D open vs D-1 close;  anchor = D close
    """
    reported = eps['reported_date']
    if daily.empty:
        return None
    on_after = daily[daily['date'] >= reported]
    if on_after.empty:
        return None
    d_idx = on_after.index[0]
    if d_idx == 0 or d_idx + 1 >= len(daily):
        return None

    def safe(idx):
        return daily.iloc[idx] if 0 <= idx < len(daily) else None

    d_minus_1 = safe(d_idx - 1)
    d = safe(d_idx)
    d_plus_1 = safe(d_idx + 1)
    if any(x is None for x in (d_minus_1, d, d_plus_1)):
        return None

    pre_gap = (float(d['open']) - float(d_minus_1['close'])) / float(d_minus_1['close']) * 100
    post_gap = (float(d_plus_1['open']) - float(d['close'])) / float(d['close']) * 100

    if timing == 'premarket':
        reaction_gap = pre_gap
        # Reaction trading day = D itself
        reaction_day = d
        max_run = (float(d['high']) - float(d['open'])) / float(d['open']) * 100
        max_drawdown = (float(d['low']) - float(d['open'])) / float(d['open']) * 100
        anchor = float(d['close'])  # sustain measured from D close (post-reaction-day close)
        sustain_offset = 0  # D+5 means d_idx + 5 from D
    else:  # postmarket / AMC
        reaction_gap = post_gap
        reaction_day = d_plus_1
        max_run = (float(d_plus_1['high']) - float(d_plus_1['open'])) / float(d_plus_1['open']) * 100
        max_drawdown = (float(d_plus_1['low']) - float(d_plus_1['open'])) / float(d_plus_1['open']) * 100
        anchor = float(d_plus_1['open'])  # sustain measured from D+1 open
        sustain_offset = 1  # D+5 means d_idx + 1 + 4 = d_idx + 5 from D

    def sustain(n):
        # n trading days after the reaction day
        idx = d_idx + sustain_offset + n
        later = safe(idx)
        if later is None:
            return None
        return (float(later['close']) - anchor) / anchor * 100

    s3 = sustain(3)
    s5 = sustain(5)
    s10 = sustain(10)

    direction_consistent = None
    is_reversal = None
    if s5 is not None and reaction_gap != 0:
        direction_consistent = (reaction_gap > 0) == (s5 > 0)
        sign_flipped = (reaction_gap > 0) != (s5 > 0)
        is_reversal = sign_flipped and abs(s5) >= abs(reaction_gap) * 0.5

    return {
        'fiscal_q': eps['fiscal_date_ending'],
        'reported': reported,
        'eps_act': eps['reported_eps'],
        'surp_%': eps['surprise_pct'],
        'beat': (eps['surprise_pct'] or 0) > 0,
        'timing': timing,
        'pre_gap_%': round(pre_gap, 2),
        'post_gap_%': round(post_gap, 2),
        'reaction_%': round(reaction_gap, 2),
        'max_run_%': round(max_run, 2),
        'max_dd_%': round(max_drawdown, 2),
        'sus_3d_%': round(s3, 2) if s3 is not None else None,
        'sus_5d_%': round(s5, 2) if s5 is not None else None,
        'sus_10d_%': round(s10, 2) if s10 is not None else None,
        'dir_5d': direction_consistent,
        'reversal_5d': is_reversal,
    }


def summarize(rdf, label):
    if rdf.empty:
        print(f"  [{label}] no rows")
        return None
    n = len(rdf)
    move_mag = rdf['reaction_%'].abs().mean()
    dir_bias = rdf['reaction_%'].mean()
    sus5 = rdf['sus_5d_%'].dropna()
    dir_n = rdf['dir_5d'].dropna()
    rev_n = rdf['reversal_5d'].dropna()
    summary = {
        'n': n,
        'beat_rate': rdf['beat'].mean() * 100,
        'directional_bias': dir_bias,
        'move_magnitude': move_mag,
        'avg_max_run': rdf['max_run_%'].mean(),
        'avg_max_dd':  rdf['max_dd_%'].mean(),
        'avg_sustain_5d':  sus5.mean() if not sus5.empty else None,
        'dir_consistency': dir_n.mean() if not dir_n.empty else None,
        'reversal_rate':   rev_n.mean() if not rev_n.empty else None,
    }
    print(f"  [{label}] n={n}")
    print(f"    beat_rate          : {summary['beat_rate']:.0f}%")
    print(f"    directional_bias   : {summary['directional_bias']:+.2f}%   (signed mean reaction)")
    print(f"    move_magnitude     : {summary['move_magnitude']:.2f}%    (abs mean reaction)")
    print(f"    avg max_run / max_dd : +{summary['avg_max_run']:.2f}% / {summary['avg_max_dd']:.2f}%")
    if summary['avg_sustain_5d'] is not None:
        print(f"    avg sustain_5d     : {summary['avg_sustain_5d']:+.2f}%")
    if summary['dir_consistency'] is not None:
        print(f"    dir_consistency_5d : {int(dir_n.sum())}/{len(dir_n)} ({summary['dir_consistency']*100:.0f}%)")
    if summary['reversal_rate'] is not None:
        print(f"    reversal_5d_rate   : {int(rev_n.sum())}/{len(rev_n)} ({summary['reversal_rate']*100:.0f}%)")
    return summary


def main():
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 240)
    pd.set_option('display.float_format', lambda x: f'{x:.2f}')

    print("Connecting to Cloud SQL...")
    all_summaries = []
    with connect() as conn:
        for ticker in TICKERS:
            timing = resolve_timing(conn, ticker)
            print(f"\n{'=' * 110}")
            print(f"  {ticker}  ({timing})")
            print('=' * 110)

            eps = fetch_earnings(conn, ticker)
            if eps.empty:
                print(f"  no earnings_history rows")
                continue

            stats_rows = []
            for _, e in eps.iterrows():
                daily = fetch_daily(conn, ticker, e['reported_date'])
                stats = compute_reaction(e.to_dict(), daily, timing)
                if stats is None:
                    continue
                stats_rows.append(stats)

            if not stats_rows:
                continue
            rdf = pd.DataFrame(stats_rows)
            print(f"\n  Per-quarter (most recent first, n={len(rdf)}):")
            print(rdf.to_string(index=False))

            summary = summarize(rdf, f'{ticker} 12Q')
            if summary:
                summary['ticker'] = ticker
                summary['timing'] = timing
                all_summaries.append(summary)

    if all_summaries:
        print(f"\n{'=' * 130}")
        print("  9-TICKER COMPARISON — BMO vs AMC profiles")
        print('=' * 130)
        sdf = pd.DataFrame(all_summaries)
        sdf = sdf[['ticker', 'timing', 'n', 'beat_rate',
                   'directional_bias', 'move_magnitude',
                   'avg_max_run', 'avg_max_dd', 'avg_sustain_5d',
                   'dir_consistency', 'reversal_rate']]
        # Sort: AMC first then BMO, then by move_magnitude
        sdf['_t'] = sdf['timing'].map({'postmarket': 0, 'premarket': 1})
        sdf = sdf.sort_values(['_t', 'move_magnitude'], ascending=[True, False]).drop(columns=['_t'])
        print(sdf.to_string(index=False))


if __name__ == '__main__':
    main()
