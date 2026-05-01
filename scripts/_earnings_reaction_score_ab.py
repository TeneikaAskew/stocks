"""Phase 0 follow-up: rank the 5 case-study tickers under three candidate
playability_score formulas. User picks the winner.

v1 — equal-weight magnitude
     score = move_magnitude * dir_consistency * log(options_volume + 1)

v2 — asymmetric (miss reactions weighted higher than beats)
     score = (0.4 * abs(avg_post_gap_when_beat) + 0.6 * abs(avg_post_gap_when_miss))
           * dir_consistency * log(options_volume + 1)

v3 — reversal-aware (credits "predictably reverses" as another form of consistency)
     score = move_magnitude
           * max(dir_consistency, 0.5 + 0.5 * reversal_rate)
           * log(options_volume + 1)

Uses the same 12Q reaction stats as _earnings_reaction_phase0.py.
options_volume is pulled from earnings_calendar (latest non-null per
ticker) as a stand-in for "current liquidity."
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
TICKERS = ['AVGO', 'GOOG', 'NVDA', 'LLY', 'FDX']
LOOKBACK_QUARTERS = 12


def secret(name: str) -> str:
    return subprocess.check_output(
        [GCLOUD, 'secrets', 'versions', 'access', 'latest',
         f'--secret={name}', f'--project={PROJECT}'],
        text=True, timeout=15,
    ).rstrip('\n')


def connect():
    return psycopg2.connect(
        host=DB_HOST, user=secret('db-trading-user'),
        password=secret('db-trading-pass'),
        dbname='trading', sslmode='require',
    )


def fetch_eps(conn, ticker):
    sql = """
        SELECT reported_date, surprise_pct, reported_eps, estimated_eps
        FROM earnings_history
        WHERE ticker = %s AND reported_date IS NOT NULL
          AND reported_eps IS NOT NULL AND reported_eps != 0
        ORDER BY reported_date DESC LIMIT %s
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (ticker, LOOKBACK_QUARTERS))
        return pd.DataFrame(cur.fetchall())


def fetch_daily(conn, ticker, reported_date):
    start = reported_date - timedelta(days=10)
    end = reported_date + timedelta(days=20)
    sql = """SELECT date, open, high, low, close, volume FROM market_data_daily
             WHERE ticker = %s AND date BETWEEN %s AND %s ORDER BY date"""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (ticker, start, end))
        rows = cur.fetchall()
    df = pd.DataFrame(rows)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date']).dt.date
        df = df.sort_values('date').reset_index(drop=True)
    return df


# Earnings-window options-volume MEDIAN over last 12 quarters, computed
# from AV HISTORICAL_OPTIONS pulls of D+1 of each historical reported_date.
# This is the right liquidity measure for the brief — it captures "what
# does this chain look like when it matters" (around earnings) rather
# than today's potentially quiet snapshot.
# (See scripts/_pull_av_options_around_earnings.py for the data pull.)
_AV_OPTIONS_VOLUME_EW_MEDIAN_12Q = {
    'AVGO':   729134,
    'GOOG':   538275,
    'NVDA':  5503629,
    'LLY':     82075,
    'FDX':    142737,
}

# Today's snapshot for diagnostic comparison only (NOT used in scores)
_AV_OPTIONS_VOLUME_TODAY_SNAPSHOT = {
    'AVGO':   230123, 'GOOG':   676374, 'NVDA':  4108276,
    'LLY':     89364, 'FDX':      5706,
}


def fetch_options_volume(conn, ticker):
    """Return earnings-window median options volume (12Q lookback)."""
    return _AV_OPTIONS_VOLUME_EW_MEDIAN_12Q.get(ticker)


def build_reactions(conn, ticker):
    eps = fetch_eps(conn, ticker)
    rows = []
    for _, e in eps.iterrows():
        daily = fetch_daily(conn, ticker, e['reported_date'])
        if daily.empty:
            continue
        on_or_after = daily[daily['date'] >= e['reported_date']]
        if on_or_after.empty:
            continue
        d_idx = on_or_after.index[0]
        if d_idx == 0 or d_idx + 1 >= len(daily):
            continue
        d_minus_1 = daily.iloc[d_idx - 1]
        d = daily.iloc[d_idx]
        d_plus_1 = daily.iloc[d_idx + 1]
        d_plus_5 = daily.iloc[d_idx + 5] if d_idx + 5 < len(daily) else None

        post_gap = (float(d_plus_1['open']) - float(d['close'])) / float(d['close']) * 100
        s5 = ((float(d_plus_5['close']) - float(d_plus_1['open'])) / float(d_plus_1['open']) * 100
              if d_plus_5 is not None else None)
        beat = (e['surprise_pct'] or 0) > 0
        rows.append({
            'beat': beat, 'post_gap_%': post_gap,
            'sus_5d_%': s5,
            'dir_consistent': (post_gap > 0) == (s5 > 0) if s5 is not None else None,
            'reversal': (
                ((post_gap > 0) != (s5 > 0)) and abs(s5) >= abs(post_gap) * 0.5
                if s5 is not None and post_gap != 0 else None
            ),
        })
    return pd.DataFrame(rows)


def aggregate(rdf: pd.DataFrame) -> dict:
    """Reduce per-quarter rows to the score inputs."""
    n = len(rdf)
    move_magnitude = rdf['post_gap_%'].abs().mean()

    beats = rdf[rdf['beat']]
    misses = rdf[~rdf['beat']]
    avg_gap_beat = beats['post_gap_%'].mean() if not beats.empty else 0.0
    avg_gap_miss = misses['post_gap_%'].mean() if not misses.empty else 0.0

    dir_n = rdf['dir_consistent'].dropna()
    dir_consistency = dir_n.mean() if not dir_n.empty else 0.0

    rev_n = rdf['reversal'].dropna()
    reversal_rate = rev_n.mean() if not rev_n.empty else 0.0

    return {
        'n': n,
        'move_magnitude': move_magnitude,
        'avg_gap_beat': avg_gap_beat,
        'avg_gap_miss': avg_gap_miss,
        'dir_consistency': dir_consistency,
        'reversal_rate': reversal_rate,
    }


def _liq_multiplier(opt_vol):
    """log(options_volume + 1) — caps volume's influence so a 100x more
    liquid name doesn't 100x the score."""
    return math.log((opt_vol or 1) + 1)


def score_v1(agg, opt_vol):
    """Equal-weight magnitude × direction consistency × log(liquidity)."""
    return agg['move_magnitude'] * agg['dir_consistency'] * _liq_multiplier(opt_vol)


def score_v2(agg, opt_vol):
    """Asymmetric — miss reactions weighted higher than beats × log(liquidity)."""
    asymm = 0.4 * abs(agg['avg_gap_beat']) + 0.6 * abs(agg['avg_gap_miss'])
    return asymm * agg['dir_consistency'] * _liq_multiplier(opt_vol)


def score_v3(agg, opt_vol):
    """Reversal-aware — credits 'predictably reverses' as consistency × log(liquidity)."""
    confidence = max(agg['dir_consistency'], 0.5 + 0.5 * agg['reversal_rate'])
    return agg['move_magnitude'] * confidence * _liq_multiplier(opt_vol)


# Reaction-only scores (no liquidity multiplier — for diagnostic comparison)
def score_v3_no_liq(agg):
    confidence = max(agg['dir_consistency'], 0.5 + 0.5 * agg['reversal_rate'])
    return agg['move_magnitude'] * confidence


def main():
    pd.set_option('display.float_format', lambda x: f'{x:.2f}')
    print("Connecting to Cloud SQL...")
    rows = []
    with connect() as conn:
        for t in TICKERS:
            rdf = build_reactions(conn, t)
            if rdf.empty:
                print(f"  {t}: no reaction rows")
                continue
            agg = aggregate(rdf)
            opt_vol = fetch_options_volume(conn, t)
            rows.append({
                'ticker': t,
                'n_q': agg['n'],
                'move_mag_%': round(agg['move_magnitude'], 2),
                'gap_beat_%': round(agg['avg_gap_beat'], 2),
                'gap_miss_%': round(agg['avg_gap_miss'], 2),
                'dir_cons': round(agg['dir_consistency'], 2),
                'rev_rate': round(agg['reversal_rate'], 2),
                'opt_vol': int(opt_vol) if opt_vol else None,
                'v1_score': round(score_v1(agg, opt_vol), 2),
                'v2_score': round(score_v2(agg, opt_vol), 2),
                'v3_score': round(score_v3(agg, opt_vol), 2),
                'v3_no_liq': round(score_v3_no_liq(agg), 2),
            })

    df = pd.DataFrame(rows)
    print("\n" + "=" * 110)
    print("  Per-ticker stats + three score variants (12Q lookback)")
    print("=" * 110)
    print(df.to_string(index=False))

    print("\nRanking under each formula (highest score first):")
    for v in ('v1_score', 'v2_score', 'v3_score', 'v3_no_liq'):
        ranked = df.sort_values(v, ascending=False)
        print(f"\n  {v}:")
        for i, r in enumerate(ranked.itertuples(), 1):
            ov = f"{r.opt_vol:>10,}" if r.opt_vol else "       N/A"
            print(f"    {i}. {r.ticker:6s}  score={getattr(r, v):>7.2f}  "
                  f"(mag={r._3:.2f}%  dir={r.dir_cons:.2f}  rev={r.rev_rate:.2f}  opt_vol={ov})")


if __name__ == '__main__':
    main()
