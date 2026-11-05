"""Read-only: recompute the 2026-11-05 premarket brief's STRAT fields with
current main and compare them with what this morning's production run stored.

Run from a checkout of TeneikaAskew/stocks at main (c5e39ea1 or later), with
Cloud SQL configured the way the brief job is (CLOUD_SQL_CONNECTION_NAME etc.):

    python -I -W ignore compare_brief_2026_11_05.py /path/to/stocks

It only SELECTs (premarket_analysis, premarket_analysis_history and
market_data_daily via DataLoader.load_daily). It writes nothing, posts
nothing, deletes no NULL-close rows and calls no Cloud Run job.
"""
import json, sys
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else '.')
import pandas as pd
from gcp.database import query_to_dataframe
from lib.config import load_config
from lib.data_loader import DataLoader
from lib.indicators import add_brief_indicators
from lib.strat import compute_strat_status
from gcp import premarket_brief as pb

import subprocess
print('stocks rev', subprocess.run(['git','-C',sys.argv[1] if len(sys.argv)>1 else '.','rev-parse','--short','HEAD'],capture_output=True,text=True).stdout.strip())
DAY = '2026-11-05'
CLOCK = pd.Timestamp(DAY + ' 08:30', tz='America/New_York')   # the live run's clock
cfg = load_config()

hist = query_to_dataframe(
    "SELECT ticker, strat_candle, strat_combo, strat_setup, ftfc_score, ftfc_direction, "
    "ftfc_labels, signal_status, run_kind, triggered_by, written_at "
    "FROM premarket_analysis_history WHERE analysis_date = :d ORDER BY written_at", {'d': DAY})
print(f"history rows today: {len(hist)}")
print(hist.groupby(['run_kind', 'triggered_by'], dropna=False).size().to_string())
# This morning's production run: the first scheduled row per ticker.
sched = hist[hist['run_kind'] == 'scheduled']
stored = (sched if len(sched) else hist).drop_duplicates('ticker', keep='first').sort_values('ticker')
print(f"compared against {len(stored)} rows, written {stored['written_at'].min()} to {stored['written_at'].max()}")

loader = DataLoader(data_dir=cfg.market.data_dir)
out = []
for row in stored.itertuples():
    t = row.ticker
    df = loader.load_daily(t, on_stale='warn')
    idx = df.index.tz_localize(None) if df.index.tz is not None else df.index
    df = df.loc[idx < pd.Timestamp(DAY)]
    close_col = 'Close' if 'Close' in df.columns else 'Last'
    df = df[df[close_col].notna()]           # same filter, no delete
    df = add_brief_indicators(df, close_col=close_col)
    st = compute_strat_status(t, df=df, timeframes=['1d', '1w', '1mo'],
                              strat_config=cfg.strat, as_of=CLOCK, inclusive_today=True)
    avail = bool(st.get('available'))
    ftfc_dir = st.get('ftfc_direction') if avail else None
    latest = df.iloc[-1]
    call_s, _ = pb.check_call_conditions(latest)
    put_s, _ = pb.check_put_conditions(latest)
    sig = pb._resolve_signal_status(call_score=call_s, put_score=put_s, ftfc_direction=ftfc_dir,
                                    signal_threshold=cfg.signal.premarket_signal_threshold,
                                    building_threshold=cfg.signal.premarket_building_threshold)
    new = {
        'strat_candle': st['last_candle'] if avail else 'X',
        'strat_combo': st.get('in_force_combo') if avail else None,
        'strat_setup': bool(st.get('strat_setup', False)) if avail else False,
        'ftfc_score': st.get('ftfc_score') if avail else None,
        'ftfc_direction': ftfc_dir,
        'ftfc_labels': st.get('ftfc_labels', {}) if avail else {},
        'signal_status': sig,
    }
    old = {k: getattr(row, k) for k in new}
    if isinstance(old['ftfc_labels'], str):
        old['ftfc_labels'] = json.loads(old['ftfc_labels'] or '{}')
    norm = lambda v: 'none' if v is None or str(v) in ('None', 'none', '', 'nan') else str(v)
    diffs = {k: (old[k], new[k]) for k in new
             if norm(old[k]) != norm(new[k]) and not (k == 'ftfc_score' and old[k] is not None
             and new[k] is not None and abs(float(old[k]) - float(new[k])) < 1e-9)}
    conf = st.get('confirmed_setups') or {}
    out.append({'ticker': t, 'last_bar': str(df.index[-1].date()), 'diffs': diffs,
                'strat_available': avail, 'strat_reason': None if avail else st.get('reason'),
                'strat_observation_ts': st.get('observation_ts'),
                'data_as_of': st.get('data_as_of'),
                'confirmed_1w': (conf.get('timeframes') or conf).get('1w') if isinstance(conf, dict) else None})
for r in out:
    print(json.dumps(r, default=str))
print(f"SUMMARY tickers={len(out)} changed={sum(1 for r in out if r['diffs'])} "
      f"unavailable={sum(1 for r in out if not r['strat_available'])}")
