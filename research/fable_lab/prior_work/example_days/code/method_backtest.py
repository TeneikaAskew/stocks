"""Rule-based version of the trader's method vs the owner's brief, SPY/QQQ/IWM, same scoring.
Windows: primary 2026-05-01..2026-11-10, holdout 2025-03-03..2026-04-30.
Writes trades.csv (every trade) and results.csv (summary). Usage: python3 method_backtest.py"""
import numpy as np, pandas as pd
from common import *

K = 0.25  # ATR distance for the stop-free "which way first" measure

def path(b, side, i0, px, atr):
    """Stop-free quality of a trigger: did price go K*ATR in favour before K*ATR against; drift to close in ATR."""
    hi, lo = b.high.values[i0:], b.low.values[i0:]
    up = side == 'long'
    fav = np.where((hi >= px + K * atr) if up else (lo <= px - K * atr))[0]
    adv = np.where((lo <= px - K * atr) if up else (hi >= px + K * atr))[0]
    f = fav[0] if len(fav) else 10**9; a = adv[0] if len(adv) else 10**9
    first = 1.0 if f < a else 0.0 if a < f else np.nan     # same minute or neither = not counted
    c = b.close.values[-1]
    return first, ((c - px) if up else (px - c)) / atr

def day_rows(t, day, br, d, H):
    b = rth(t, day)
    if len(b) < 300: return []
    prev = d[d.index < day]
    if len(prev) < 16: return []
    p, pp = prev.iloc[-1], prev.iloc[-2]
    atr = br.atr14 if pd.notna(br.atr14) else np.nan
    mid = (p.high + p.low) / 2
    typ = '1' if (p.high <= pp.high and p.low >= pp.low) else '3' if (p.high > pp.high and p.low < pp.low) else '2U' if p.high > pp.high else '2D'
    look = prev.iloc[-10:-1]
    ups = sorted(x for x in look.high.values if x > p.high + 0.01); dns = sorted((x for x in look.low.values if x < p.low - 0.01), reverse=True)
    o = float(b.open.iloc[0])
    pmc = H[(H.index < pd.Timestamp(day)) & (H.index.hour == 16)]
    pm = pmc.iloc[-1] if len(pmc) and (pd.Timestamp(day) - pmc.index[-1]).days <= 5 else None
    m12 = (pm.high + pm.low) / 2 if pm is not None else None
    specs = []  # (variant, side, entry, stop, t1, setup)
    setup_up = {'2D': '2-2 reversal', '2U': '2-2 continuation', '1': 'inside-day break', '3': 'outside-day break'}[typ]
    setup_dn = {'2U': '2-2 reversal', '2D': '2-2 continuation', '1': 'inside-day break', '3': 'outside-day break'}[typ]
    for nm, k in (('T1', 0), ('T2', 1), ('close', None)):
        specs.append((f'TM_daily_{nm}', 'long', p.high, mid, (ups[k] if k is not None and len(ups) > k else None), setup_up))
        specs.append((f'TM_daily_{nm}', 'short', p.low, mid, (dns[k] if k is not None and len(dns) > k else None), setup_dn))
    if pm is not None and pm.high - pm.low > 0:
        if o < m12: specs.append(('TM_12H', 'long', m12, pm.low, pm.high, '12H 50% (open below)'))
        elif o > m12: specs.append(('TM_12H', 'short', m12, pm.high, pm.low, '12H 50% (open above)'))
    specs.append(('Brief', 'long', br.calls_trigger_price, br.calls_stop_price, br.calls_t1_price, str(br.calls_trigger_name)))
    specs.append(('Brief', 'short', br.puts_trigger_price, br.puts_stop_price, br.puts_t1_price, str(br.puts_trigger_name)))
    # brief trigger with its stop but held to the close (no target), to separate trigger quality from target distance
    specs.append(('Brief_close', 'long', br.calls_trigger_price, br.calls_stop_price, None, str(br.calls_trigger_name)))
    specs.append(('Brief_close', 'short', br.puts_trigger_price, br.puts_stop_price, None, str(br.puts_trigger_name)))
    call = 'long' if str(br.signal_status).upper().startswith('CALL') else 'short' if str(br.signal_status).upper().startswith('PUT') else None
    b1030 = b[b.index >= f'{day} 10:30']
    out = []
    for var, side, e, s, t1, setup in specs:
        for mod, bb in (('all', b), ('after_1030', b1030)):
            tr = trade(bb, side, e, s, t1)
            if not tr or not tr.get('fill') or tr.get('R') is None: continue
            i0 = bb.index.get_loc(tr['fill_t']); first, drift = path(bb, side, i0, tr['px'], atr) if atr and atr > 0 else (np.nan, np.nan)
            out.append(dict(day=day, ticker=t, variant=var, side=side, mod=mod, setup=setup, entry=round(float(e), 2), stop=round(float(s), 2), t1=t1,
                            fill_t=tr['fill_t'].strftime('%H:%M'), px=tr['px'], thru_open=tr['thru_open'], R=tr['R'], how=tr['how'],
                            risk_atr=round(abs(tr['px'] - s) / atr, 3) if atr else np.nan, t1_R=round(abs(t1 - tr['px']) / abs(tr['px'] - s), 2) if t1 is not None and pd.notna(t1) else np.nan,
                            first_fav=first, drift_atr=round(drift, 3), with_brief_call=(call == side) if call else None, brief_status=br.signal_status))
    return out

def summarize(tr):
    rows = []
    tr = tr.copy(); tr['window'] = np.where(tr.day <= '2026-04-30', 'holdout', 'primary')
    mods = {'all': tr[tr['mod'] == 'all'], 'skip_open_through': tr[(tr['mod'] == 'all') & (~tr.thru_open)],
            'before_1000': tr[(tr['mod'] == 'all') & (tr.fill_t < '10:00')], 'before_1000_skip_through': tr[(tr['mod'] == 'all') & (tr.fill_t < '10:00') & (~tr.thru_open)],
            'after_1030_first_hour_wait': tr[(tr['mod'] == 'after_1030') & (~tr.thru_open)]}
    for mn, x in mods.items():
        for (w, v), g in x.groupby(['window', 'variant']):
            for tk, gg in [('ALL', g)] + list(g.groupby('ticker')):
                lo, hi = boot_ci(gg, 'R'); dl, dh = boot_ci(gg.dropna(subset=['drift_atr']), 'drift_atr'); ff = gg.dropna(subset=['first_fav'])
                fl, fh = boot_ci(ff, 'first_fav')
                wins, losses = gg[gg.R > 0].R, gg[gg.R <= 0].R
                rows.append(dict(window=w, variant=v, modifier=mn, ticker=tk, trades=len(gg), days=gg.day.nunique(), win_pct=round(100 * (gg.R > 0).mean(), 1),
                                 total_R=round(gg.R.sum(), 2), avg_R=round(gg.R.mean(), 3), avg_R_lo90=lo, avg_R_hi90=hi,
                                 avg_win_R=round(wins.mean(), 2) if len(wins) else np.nan, avg_loss_R=round(losses.mean(), 2) if len(losses) else np.nan,
                                 median_risk_atr=round(gg.risk_atr.median(), 2), median_t1_R=round(gg.t1_R.median(), 2),
                                 fav_first_pct=round(100 * ff.first_fav.mean(), 1) if len(ff) else np.nan, fav_first_lo90=round(100 * fl, 1) if fl == fl else np.nan, fav_first_hi90=round(100 * fh, 1) if fh == fh else np.nan,
                                 drift_atr=round(gg.drift_atr.mean(), 3), drift_lo90=dl, drift_hi90=dh))
    return pd.DataFrame(rows)

if __name__ == '__main__':
    br = pd.read_csv(f'{LANE}/inputs/brief_rows_main0830.csv')
    allr = []
    for t in T:
        d = daily(t); H = h12(bars(t))
        for r in br[br.ticker == t].itertuples():
            allr += day_rows(t, r.day, r, d, H)
    tr = pd.DataFrame(allr); tr.to_csv(f'{LANE}/trades.csv', index=False)
    res = summarize(tr); res.to_csv(f'{LANE}/results.csv', index=False)
    # by setup, daily trigger held to T1, and whether the trigger side agrees with the brief's call
    x = tr[(tr['mod'] == 'all')].copy(); x['window'] = np.where(x.day <= '2026-04-30', 'holdout', 'primary')
    by = []
    for (w, v, s), g in x[x.variant.isin(['TM_daily_T1', 'TM_daily_close', 'TM_12H'])].groupby(['window', 'variant', 'setup']):
        lo, hi = boot_ci(g, 'R'); dl, dh = boot_ci(g.dropna(subset=['drift_atr']), 'drift_atr')
        by.append(dict(window=w, variant=v, setup=s, trades=len(g), win_pct=round(100 * (g.R > 0).mean(), 1), avg_R=round(g.R.mean(), 3), lo90=lo, hi90=hi, drift_atr=round(g.drift_atr.mean(), 3), drift_lo90=dl, drift_hi90=dh))
    for (w, v, s), g in x[x.variant.isin(['TM_daily_T1', 'TM_daily_close', 'TM_12H', 'Brief']) & x.with_brief_call.notna()].groupby(['window', 'variant', 'with_brief_call']):
        lo, hi = boot_ci(g, 'R'); dl, dh = boot_ci(g.dropna(subset=['drift_atr']), 'drift_atr')
        by.append(dict(window=w, variant=v, setup='agrees with brief call' if s else 'against brief call', trades=len(g), win_pct=round(100 * (g.R > 0).mean(), 1), avg_R=round(g.R.mean(), 3), lo90=lo, hi90=hi, drift_atr=round(g.drift_atr.mean(), 3), drift_lo90=dl, drift_hi90=dh))
    pd.DataFrame(by).to_csv(f'{LANE}/results_by_setup.csv', index=False)
    pd.set_option('display.width', 320); pd.set_option('display.max_rows', 500); pd.set_option('display.max_columns', 40)
    print('ticker-days', br.groupby('ticker').day.nunique().to_dict(), 'trade rows', len(tr))
    print(res[(res.ticker == 'ALL')].sort_values(['modifier', 'window', 'variant']).to_string(index=False))
    print(res[(res.ticker != 'ALL') & (res.modifier == 'all')].sort_values(['window', 'variant', 'ticker'])[['window', 'variant', 'ticker', 'trades', 'win_pct', 'total_R', 'avg_R', 'avg_R_lo90', 'avg_R_hi90', 'fav_first_pct', 'drift_atr', 'drift_lo90', 'drift_hi90']].to_string(index=False))
    print(pd.DataFrame(by).to_string(index=False))
