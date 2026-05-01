"""Final Phase 0 scoring — all 9 tickers (5 AMC + 4 new BMO + LLY-corrected)
under the locked-in v3 formula with TWO refinements from Phase 0.5:

1. Timing-aware reaction_gap (pre_gap for BMO, post_gap for AMC)
2. Volatility-normalized magnitude:
     move_mag_norm = move_magnitude / median(|daily_return|, last 60 days)

   This credits "moves a lot relative to normal" instead of just absolute
   move size, so BMO names (banks, staples) compete fairly against AMC
   names (semis, tech) for ranking.

   playability_score = move_mag_norm
                     × max(dir_consistency, 0.5 + 0.5 × reversal_rate)
                     × log(ew_options_volume_median + 1)
"""
import math
import subprocess
from datetime import timedelta

import pandas as pd
import psycopg2
import psycopg2.extras

GCLOUD = r'C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
PROJECT = 'adept-mountain-474619-d4'
DB_HOST = '34.24.66.12'

AMC_TICKERS = ['AVGO', 'GOOG', 'NVDA', 'FDX']
BMO_TICKERS = ['LLY', 'JPM', 'JNJ', 'WMT', 'PG']
TICKERS = AMC_TICKERS + BMO_TICKERS

LOOKBACK_QUARTERS = 12

TIMING_OVERRIDES = {
    'AVGO': 'postmarket', 'NVDA': 'postmarket', 'FDX': 'postmarket',
    'GOOG': 'postmarket',  # confirmed
    'LLY': 'premarket', 'JPM': 'premarket', 'JNJ': 'premarket',
    'WMT': 'premarket', 'PG': 'premarket',
}

# 12Q earnings-window options-volume MEDIAN per ticker.
# AMC values from earlier _pull_av_options_around_earnings.py run.
# BMO values populated below from _pull_av_options_around_earnings_v2.py
# once that completes; if missing, score falls back to log(1) = 0 and
# the ticker is flagged.
# 12Q earnings-window medians:
#   AMC tickers — D+1 reaction-day (from _pull_av_options_around_earnings.py)
#   BMO tickers — D reaction-day (from _pull_av_options_around_earnings_v2.py)
EW_OPTIONS_VOLUME_MEDIAN_12Q = {
    'AVGO':   729134,   # AMC
    'GOOG':   538275,   # AMC
    'NVDA':  5503629,   # AMC
    'FDX':    142737,   # AMC
    'LLY':    119760,   # BMO (D-of-report, supersedes earlier D+1=82075)
    'JPM':    234744,   # BMO
    'JNJ':     84037,   # BMO
    'WMT':    395623,   # BMO
    'PG':      60211,   # BMO
}


def secret(n):
    return subprocess.check_output(
        [GCLOUD, 'secrets', 'versions', 'access', 'latest',
         f'--secret={n}', f'--project={PROJECT}'],
        text=True, timeout=15).rstrip('\n')


def connect():
    return psycopg2.connect(host=DB_HOST, user=secret('db-trading-user'),
                            password=secret('db-trading-pass'),
                            dbname='trading', sslmode='require')


def fetch_earnings(conn, ticker):
    sql = """
        SELECT reported_date, surprise_pct, reported_eps
        FROM earnings_history
        WHERE ticker = %s AND reported_date IS NOT NULL
          AND (reported_eps > 0 OR reported_eps < 0)
        ORDER BY reported_date DESC LIMIT %s
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (ticker, LOOKBACK_QUARTERS))
        return pd.DataFrame(cur.fetchall())


def fetch_daily(conn, ticker, reported):
    sql = """SELECT date, open, high, low, close FROM market_data_daily
             WHERE ticker = %s AND date BETWEEN %s AND %s ORDER BY date"""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (ticker, reported - timedelta(days=15),
                          reported + timedelta(days=20)))
        df = pd.DataFrame(cur.fetchall())
    if not df.empty:
        df['date'] = pd.to_datetime(df['date']).dt.date
        df = df.sort_values('date').reset_index(drop=True)
    return df


def fetch_typical_daily_return(conn, ticker, days=60):
    """Median absolute daily return over last N trading days.
    Returns None if insufficient data."""
    sql = """
        SELECT date, close FROM market_data_daily
        WHERE ticker = %s ORDER BY date DESC LIMIT %s
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (ticker, days + 5))
        df = pd.DataFrame(cur.fetchall())
    if len(df) < 10:
        return None
    df = df.sort_values('date').reset_index(drop=True)
    df['return_pct'] = df['close'].astype(float).pct_change() * 100
    return df['return_pct'].abs().median()


def reaction_for_quarter(eps, daily, timing):
    """Returns dict with reaction_pct, sus5_pct, dir_consistent, is_reversal."""
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

    if timing == 'premarket':
        reaction_pct = (float(d['open']) - float(d_minus_1['close'])) / float(d_minus_1['close']) * 100
        anchor = float(d['close'])
        sustain_offset = 0
    else:  # AMC
        reaction_pct = (float(d_plus_1['open']) - float(d['close'])) / float(d['close']) * 100
        anchor = float(d_plus_1['open'])
        sustain_offset = 1

    later = safe(d_idx + sustain_offset + 5)
    if later is None:
        return None
    sus5 = (float(later['close']) - anchor) / anchor * 100

    dir_consistent = (reaction_pct > 0) == (sus5 > 0) if reaction_pct != 0 else None
    is_reversal = (
        ((reaction_pct > 0) != (sus5 > 0)) and abs(sus5) >= abs(reaction_pct) * 0.5
        if reaction_pct != 0 else None
    )
    return {
        'reaction_pct': reaction_pct,
        'sus5_pct': sus5,
        'dir_consistent': dir_consistent,
        'is_reversal': is_reversal,
        'beat': (eps.get('surprise_pct') or 0) > 0,
    }


def main():
    pd.set_option('display.float_format', lambda x: f'{x:.3f}')
    print("Connecting to Cloud SQL...")
    rows = []
    with connect() as conn:
        for ticker in TICKERS:
            timing = TIMING_OVERRIDES.get(ticker, 'postmarket')
            eps = fetch_earnings(conn, ticker)
            if eps.empty:
                continue
            stats = []
            for _, e in eps.iterrows():
                daily = fetch_daily(conn, ticker, e['reported_date'])
                r = reaction_for_quarter(e.to_dict(), daily, timing)
                if r:
                    stats.append(r)
            if not stats:
                continue
            sdf = pd.DataFrame(stats)
            move_mag = sdf['reaction_pct'].abs().mean()
            dir_n = sdf['dir_consistent'].dropna()
            rev_n = sdf['is_reversal'].dropna()
            dir_cons = dir_n.mean() if not dir_n.empty else 0.5
            rev_rate = rev_n.mean() if not rev_n.empty else 0.0

            typical = fetch_typical_daily_return(conn, ticker, days=60)
            move_mag_norm = move_mag / typical if typical and typical > 0 else None

            ew_vol = EW_OPTIONS_VOLUME_MEDIAN_12Q.get(ticker)
            confidence = max(dir_cons, 0.5 + 0.5 * rev_rate)
            log_liq = math.log((ew_vol or 1) + 1)

            score_raw = move_mag * confidence * log_liq
            score_norm = (move_mag_norm * confidence * log_liq) if move_mag_norm else None

            rows.append({
                'ticker': ticker,
                'timing': timing,
                'n_q': len(sdf),
                'move_mag_%': round(move_mag, 2),
                'typical_daily_%': round(typical, 2) if typical else None,
                'move_mag_norm': round(move_mag_norm, 2) if move_mag_norm else None,
                'dir_cons': round(dir_cons, 2),
                'rev_rate': round(rev_rate, 2),
                'confidence': round(confidence, 2),
                'ew_vol': ew_vol,
                'score_raw': round(score_raw, 2),
                'score_norm': round(score_norm, 2) if score_norm else None,
            })

    df = pd.DataFrame(rows)
    print("\n" + "=" * 130)
    print("  9-TICKER FINAL SCORE — raw vs vol-normalized magnitude")
    print("=" * 130)
    print(df.to_string(index=False))

    print("\nRanking (raw move_magnitude × confidence × log_liq) — biases toward AMC names:")
    for i, r in enumerate(df.sort_values('score_raw', ascending=False).itertuples(), 1):
        print(f"  {i}. {r.ticker:6s} {r.timing:>10s}  score={r.score_raw:>7.2f}  "
              f"(mag={r._4:.2f}%  typ={r._5:.2f}%)")

    print("\nRanking (VOL-NORMALIZED magnitude × confidence × log_liq):")
    if df['score_norm'].notna().any():
        for i, r in enumerate(df.sort_values('score_norm', ascending=False).itertuples(), 1):
            score = r.score_norm
            if score is None or pd.isna(score):
                continue
            print(f"  {i}. {r.ticker:6s} {r.timing:>10s}  score={score:>6.2f}  "
                  f"(mag_norm={r.move_mag_norm:.2f}× typical, mag={r._4:.2f}%, dir={r.dir_cons:.2f}, rev={r.rev_rate:.2f})")


if __name__ == '__main__':
    main()
