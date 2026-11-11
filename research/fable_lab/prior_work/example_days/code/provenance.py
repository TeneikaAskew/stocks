"""Where do the trader's posted QQQ levels come from? Each posted number is checked against candle levels built
only from bars before the post (post times converted to ET, see README). First matching rule in priority
order wins. exact = within 0.02, near = within 0.15 (extended-hours feeds differ by a few cents).
Usage: python3 provenance.py   -> provenance.csv"""
import pandas as pd, numpy as np
from common import *

# (post time ET, session it is for, [(level, role as posted)])
POSTS = [
 ('2026-10-26 23:25', '2026-10-27', [(713.06,'calls trigger (12HR entry, 50% of 12HR)'),(714.44,'call PT1'),(715.43,'call PT2 (chart: 22 REV 2D)'),(717.57,'call PT3'),(719.71,'call PT4'),(720.00,'call PT5'),(705.58,'puts trigger (daily 22 REV down)'),(702.09,'put PT1'),(701.16,'put PT2')]),
 ('2026-10-27 21:57', '2026-10-28', [(727.95,'critical level'),(730.00,'acceptance level'),(713.59,'low to take'),(705.58,'low to take'),(701.16,'low to take'),(700.00,'low to take')]),
 ('2026-10-29 08:15', '2026-10-29', [(713.59,'magnitude of daily 22 REV down')]),
 ('2026-10-31 08:09', '2026-11-02', [(680.05,'puts trigger (week)'),(711.62,'daily void top'),(698.63,'daily void bottom')]),
 ('2026-11-08 22:06', '2026-11-09', [(664.52,'calls trigger (daily 212 REV up)'),(668.17,'call PT1'),(671.59,'call PT2'),(683.65,'call PT3'),(653.99,'puts trigger (daily 212 CON down)'),(647.05,'put PT1'),(642.21,'put PT2'),(635.26,'put PT3')]),
 ('2026-11-10 09:56', '2026-11-10', [(679.50,'calls trigger (12HR entry; chart label 22 REV 2D)'),(681.11,'call PT1 (MAG; typed 68.11)'),(682.48,'call PT2'),(683.65,'call PT3'),(685.54,'call PT4'),(687.87,'call PT5'),(662.02,'puts trigger (daily 122 REV down)'),(653.99,'put PT (1st as posted)'),(659.10,'put PT (2nd as posted)'),(656.94,'put PT (3rd as posted)'),(647.05,'put PT (4th as posted)'),(679.35,'chart: 50% (12HR)')]),
]

def candidates(t, ts):
    """Ordered list of (price, rule) known at time ts."""
    ts = pd.Timestamp(ts); b = bars(t); b = b[b.index < ts]
    d = daily(t); d = d[d.index + pd.Timedelta(hours=16) <= ts]   # completed daily candles only
    c = []
    p = d.iloc[-1]; pd_ = d.index[-1].date()
    c += [(p.high, f'prior day high ({pd_})'), (p.low, f'prior day low ({pd_})')]
    H = h12(b)
    last = H.iloc[-1]; nm = f'{H.index[-1]:%m-%d %H:%M}'
    c += [((last.high + last.low) / 2, f'50% of latest 12H candle ({nm})'), (last.high, f'high of latest 12H candle ({nm})'),
          (last.low, f'low of latest 12H candle ({nm})'), (last.close, f'close of latest 12H candle ({nm})')]
    for k in range(2, 11):
        r = d.iloc[-k]
        c += [(r.high, f'daily high {k} sessions back ({d.index[-k].date()})'), (r.low, f'daily low {k} sessions back ({d.index[-k].date()})')]
    for k in range(2, 9):
        r = H.iloc[-k]; nm = f'{H.index[-k]:%m-%d %H:%M}'
        c += [(r.high, f'12H candle high ({nm})'), (r.low, f'12H candle low ({nm}; 04:00 candle low before the open = premarket low)'), ((r.high + r.low) / 2, f'12H candle 50% ({nm})')]
    w = d.groupby(d.index.to_period('W-FRI')).agg(dict(high='max', low='min'))
    m = d.groupby(d.index.to_period('M')).agg(dict(high='max', low='min'))
    for nm, x in (('week', w), ('month', m)):
        for k in (1, 2):
            if d.index[-1].to_period('W-FRI' if nm == 'week' else 'M') == x.index[-1] and ts.normalize() <= d.index[-1] + pd.Timedelta(days=1):
                pass
            r = x.iloc[-k - 1] if x.index[-1] == ts.to_period('W-FRI' if nm == 'week' else 'M') else x.iloc[-k]
            c += [(r.high, f'{nm} high, {k} back'), (r.low, f'{nm} low, {k} back')]
    old = d.iloc[:-10]
    for ix, r in old[::-1].iterrows():
        c += [(r.high, f'older daily high ({ix.date()})'), (r.low, f'older daily low ({ix.date()})')]
    return c

def match(L, cands):
    """Recent structures first (exact, then near); older daily highs/lows only after that; round numbers last."""
    recent = [c for c in cands if not c[1].startswith('older')]; older = [c for c in cands if c[1].startswith('older')]
    for pool, tol, grade in ((recent, 0.02, 'exact'), (recent, 0.15, 'near'), (older, 0.02, 'exact (older level)'), (older, 0.15, 'near (older level)')):
        if pool is older and abs(L - round(L / 10) * 10) < 1e-9:
            return 'round', L, 'round number'
        for p, rule in pool:
            if abs(p - L) <= tol:
                return grade, round(float(p), 2), rule
    return 'not reproduced', None, ''

def chance_rate(t='QQQ', ts='2026-11-08 22:06', span=40, tol=0.02, n=20000, seed=3):
    """How often would a random price in the recent range land within tol of some older daily high/low?"""
    older = np.array([p for p, r in candidates(t, ts) if r.startswith('older')])
    ref = daily(t).loc[:ts].close.iloc[-1]
    x = np.random.default_rng(seed).uniform(ref - span, ref + span, n)
    return float(np.mean([np.min(np.abs(older - v)) <= tol for v in x]))

if __name__ == '__main__':
    rows = []
    for ts, sess, lv in POSTS:
        c = candidates('QQQ', ts)
        for L, role in lv:
            g, p, rule = match(L, c)
            rows.append(dict(post_et=ts, session=sess, level=L, role=role, grade=g, our_value=p, rule=rule))
    df = pd.DataFrame(rows); df.to_csv(f'{LANE}/provenance.csv', index=False)
    pd.set_option('display.width', 250); pd.set_option('display.max_colwidth', 80); pd.set_option('display.max_rows', 100)
    print(df.drop(columns='post_et').to_string())
    print('chance of a random price matching an older daily high/low: within 0.02 =', round(chance_rate(), 3), '| within 0.15 =', round(chance_rate(tol=0.15), 3))
    print(df.grade.value_counts().to_dict(), 'of', len(df), '| distinct levels:', df.drop_duplicates('level').grade.value_counts().to_dict(), 'of', df.level.nunique())
