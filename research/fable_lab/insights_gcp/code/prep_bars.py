"""Build per-ticker 1-minute bar files in naive Eastern time from the db-query results, using the repo's own
reader (lib.eastern_time.stored_intraday_to_eastern) so pre-2026-09-28 rows follow the production convention check."""
import sys, json, glob
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))  # the repo root, for lib.eastern_time
import numpy as np, pandas as pd
from lib.eastern_time import stored_intraday_to_eastern, TRUE_UTC_FROM
S = sys.argv[1]
frames = []
for path in sorted(glob.glob(f'{S}/bars/bars_0*.results.json')):
    d = json.load(open(path))
    for s in d['results']:
        if s['row_count']:
            frames.append(pd.DataFrame(s['rows'], columns=s['columns']))
        print(path.split('/')[-1], s['sql'].split("ticker = '")[1][:3], s['sql'].split("ts >= TIMESTAMPTZ '")[1][:7], 'rows', s['row_count'], 'truncated', s['truncated'])
raw = pd.concat(frames, ignore_index=True)
raw['ts'] = pd.to_datetime(raw['ts'], utc=True)
print('raw rows', len(raw), raw['ts'].min(), raw['ts'].max())
out = []
for t, g in raw.groupby('ticker'):
    g = g.sort_values('ts').reset_index(drop=True)
    et, keep = stored_intraday_to_eastern(g['ts'], g['volume'])
    et = pd.DatetimeIndex(et); keep = np.asarray(keep, dtype=bool)
    rawclock = g['ts'].dt.tz_convert('UTC').dt.tz_localize(None)
    as_label = (et == pd.DatetimeIndex(rawclock))          # read as an Eastern label (legacy convention)
    gg = g.assign(et=et, keep=keep, as_label=as_label)
    gg['raw_date'] = gg['ts'].dt.tz_convert('UTC').dt.date
    cls = gg.groupby('raw_date').agg(rows=('ts', 'size'), label_rows=('as_label', 'sum'), dropped=('keep', lambda k: int((~k).sum())))
    cls['verdict'] = np.where(cls['label_rows'] > cls['rows'] / 2, 'label', 'utc')
    post = cls.index >= TRUE_UTC_FROM
    print(f"\n{t}: rows {len(gg)}, dropped {int((~keep).sum())}; raw dates {len(cls)}; read as Eastern labels: {int((cls.verdict=='label').sum())} dates (all before {TRUE_UTC_FROM}: {bool((cls[cls.verdict=='label'].index < TRUE_UTC_FROM).all())}); true UTC: {int((cls.verdict=='utc').sum())}")
    print('  label-read dates by month:', cls[cls.verdict == 'label'].groupby(pd.to_datetime(cls[cls.verdict == 'label'].index).to_period('M')).size().to_dict())
    kept = gg[gg['keep']].copy()
    kept['session'] = kept['et'].dt.date
    kept = kept[['ticker', 'et', 'session', 'open', 'high', 'low', 'close', 'volume', 'as_label']]
    kept.to_csv(f'{S}/bars/bars_{t}.csv.gz', index=False)
    rth = kept[(kept.et.dt.time >= pd.Timestamp('09:30').time()) & (kept.et.dt.time < pd.Timestamp('16:00').time())]
    per = rth.groupby('session').size()
    print(f'  sessions {per.size}; RTH bars per session: min {per.min()} median {per.median()} max {per.max()}; sessions with <380 RTH bars: {int((per<380).sum())}')
    out.append(kept)
