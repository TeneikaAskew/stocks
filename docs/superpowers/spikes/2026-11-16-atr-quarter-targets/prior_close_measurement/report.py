"""Summaries from sessions_<T>.pkl. usage: report.py <out_dir> ; prints to stdout."""
import sys, pickle
import numpy as np, pandas as pd
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 60); pd.set_option('display.max_rows', 500)
OUT = sys.argv[1]
recs = []
for t in ('SPY', 'QQQ', 'IWM'):
    d = pickle.load(open(f'{OUT}/sessions_{t}.pkl', 'rb'))
    recs += d['recs']
    m = d['meta']
    print('META', t, {k: (v if not isinstance(v, list) or len(v) < 6 else f'{len(v)} items, first {v[0]}, last {v[-1]}') for k, v in m.items()})
df = pd.DataFrame(recs)
df['year'] = df.date.str[:4]
df.drop(columns=[c for c in df.columns if c.endswith('_bar') or c == 'ship_stale_reports']).to_csv(f'{OUT}/sessions_all.csv', index=False)
print('sessions measured', df.groupby('ticker').size().to_dict(), 'dates', df.date.min(), df.date.max())
print('shipped extreme None: high', int(df.ship_high.isna().sum()), 'low', int(df.ship_low.isna().sum()), df.ship_reason.value_counts().to_dict())

TOLS = (0, 1, 2, 5, 10); XS = (0.001, 0.0025, 0.005)
print('\n==== ITEM 1: bars (volume >= 100) with open or close at the prior close, other body price more than X away ====')
print('-- totals per ticker: bars / sessions with at least one / share of sessions')
rows = []
for t, g in df.groupby('ticker'):
    for tol in TOLS:
        for X in XS:
            c = g[f'i1_t{tol}_x{X}']; b = g[f'i1both_t{tol}_x{X}']
            rows.append({'ticker': t, 'tol_cents': tol, 'X_pct': X * 100, 'bars': int(c.sum()), 'sessions_ge1': int((c > 0).sum()),
                         'share_sessions_pct': round(100 * (c > 0).mean(), 2), 'sessions': len(g),
                         'bars_bothbody_at_pc_wick_far': int(b.sum()), 'sessions_ge1_either_kind': int(((c + b) > 0).sum()),
                         'share_either_pct': round(100 * ((c + b) > 0).mean(), 2)})
i1 = pd.DataFrame(rows); print(i1.to_string(index=False)); i1.to_csv(f'{OUT}/item1_totals.csv', index=False)
print('-- by ticker and year, X = 0.25%: bars at tol 0/1/2/5 cents, sessions with >= 1 (tol 0 and tol 5), share')
rows = []
for (t, y), g in df.groupby(['ticker', 'year']):
    r = {'ticker': t, 'year': y, 'sessions': len(g)}
    for X in XS:
        for tol in (0, 1, 2, 5):
            r[f'bars_x{X*100:g}_t{tol}'] = int(g[f'i1_t{tol}_x{X}'].sum())
    for tol in (0, 5):
        c = g[f'i1_t{tol}_x0.0025']
        r[f'sess_ge1_x0.25_t{tol}'] = int((c > 0).sum()); r[f'share_x0.25_t{tol}_pct'] = round(100 * (c > 0).mean(), 1)
    r['bothbody_x0.25_t0'] = int(g['i1both_t0_x0.0025'].sum())
    rows.append(r)
i1y = pd.DataFrame(rows); print(i1y.to_string(index=False)); i1y.to_csv(f'{OUT}/item1_by_year.csv', index=False)


def changes(df, hi, lo, bh='ship_high', bl='ship_low'):
    out = []
    for side, a, b in (('high', bh, hi), ('low', bl, lo)):
        x = df[['ticker', 'date', 'pc', a, b]].copy(); x.columns = ['ticker', 'date', 'pc', 'shipped', 'cand']; x['side'] = side
        both_nan = x.shipped.isna() & x.cand.isna()
        diff = ~both_nan & ~(x.shipped == x.cand)
        x = x[diff].copy()
        x['cents'] = ((x.cand - x.shipped).abs() * 100).round(2)
        x['pct'] = ((x.cand - x.shipped).abs() / x.shipped * 100).round(4)
        out.append(x)
    return pd.concat(out)


CANDS = ['P1', 'P2', 'P2_D0.10', 'P2_tol2', 'P2_tol10', 'P3', 'P3_D0.05', 'P4', 'P2+P4', 'P5_D0.25', 'P5_D0.50', 'P2+P5_D0.50']
print('\n==== ITEM 2: candidates against the shipped rule (atr=None, stale_print_atr=None, spike_atr=None) ====')
rows = []; allch = {}
for cnd in CANDS:
    ch = changes(df, f'{cnd}_high', f'{cnd}_low'); allch[cnd] = ch
    for t in ('SPY', 'QQQ', 'IWM'):
        c = ch[ch.ticker == t]; n = int((df.ticker == t).sum())
        num = c.dropna(subset=['cents'])
        rows.append({'cand': cnd, 'ticker': t, 'sessions': n, 'high_changed': int((c.side == 'high').sum()), 'low_changed': int((c.side == 'low').sum()),
                     'sessions_either': c.date.nunique(), 'share_pct': round(100 * c.date.nunique() / n, 2),
                     'to_or_from_None': int(c.cents.isna().sum()),
                     'cents_med': num.cents.median(), 'cents_p90': num.cents.quantile(.9), 'cents_max': num.cents.max(),
                     'pct_med': num.pct.median(), 'pct_p90': num.pct.quantile(.9), 'pct_max': num.pct.max()})
i2 = pd.DataFrame(rows); print(i2.to_string(index=False)); i2.to_csv(f'{OUT}/item2_summary.csv', index=False)
bars = {(r['ticker'], r['date']): r for r in recs}
for cnd in ('P1', 'P2', 'P3', 'P4', 'P2+P4'):
    for t in ('SPY', 'QQQ', 'IWM'):
        c = allch[cnd]; c = c[c.ticker == t].sort_values('cents', ascending=False).head(20).copy()
        c['shipped_set_by'] = [str(bars[(t, d)][f'ship_{s}_bar']) for d, s in zip(c.date, c.side)]
        c['run3_at_shipped'] = [bars[(t, d)][f'run_ship_{s}'] for d, s in zip(c.date, c.side)]
        print(f'-- 20 largest changes, {cnd}, {t}'); print(c.drop(columns=['ticker']).to_string(index=False))
    allch[cnd].sort_values(['ticker', 'cents'], ascending=[True, False]).to_csv(f'{OUT}/item2_changes_{cnd.replace("+", "_")}.csv', index=False)

print('\n==== ITEM 3: false-positive check ====')
print('A. sessions whose shipped extreme equals the prior close to the cent, split by whether the premarket really traded there')
print('   (run_pc = longest run of consecutive non-thin bars with all four prices within 0.1% of the prior close)')
rows = []
fp_list = []
for side in ('high', 'low'):
    at = df[df[f'ship_{side}_at_pc']]
    for t in ('SPY', 'QQQ', 'IWM'):
        g = at[at.ticker == t]
        gen = g[g.run_pc >= 3]; sus = g[g.run_pc < 3]
        r = {'side': side, 'ticker': t, 'ship_at_pc': len(g), 'genuine_run>=3': len(gen), 'no_run': len(sus)}
        for cnd in ('P1', 'P2', 'P3', 'P4', 'P2+P4', 'P5_D0.50', 'P2+P5_D0.50'):
            chg = ~(gen[f'{cnd}_{side}'] == gen[f'ship_{side}'])
            r[f'{cnd}_changes_genuine'] = int(chg.sum())
            r[f'{cnd}_changes_no_run'] = int((~(sus[f'{cnd}_{side}'] == sus[f'ship_{side}'])).sum())
            x = gen[chg][['ticker', 'date', 'pc', f'ship_{side}', f'{cnd}_{side}', 'run_pc']].copy(); x.columns = ['ticker', 'date', 'pc', 'shipped', 'cand', 'run_pc']
            x['cand_name'] = cnd; x['side'] = side; fp_list.append(x)
        rows.append(r)
i3 = pd.DataFrame(rows); print(i3.to_string(index=False)); i3.to_csv(f'{OUT}/item3_at_pc.csv', index=False)
fp = pd.concat(fp_list); fp['cents'] = ((fp.cand - fp.shipped).abs() * 100).round(2)
fp.to_csv(f'{OUT}/item3_false_positives.csv', index=False)
print('-- genuine sessions (run >= 3 at the prior close) where a candidate changes the shipped extreme that sat at the prior close:')
print(fp.sort_values(['cand_name', 'cents'], ascending=[True, False]).to_string(index=False) if len(fp) else '   none')
print('B. any changed extreme whose shipped value had a run of >= 3 consecutive non-thin bars within 0.1% of it (shipped value looked real)')
rows = []
for cnd in CANDS:
    c = allch[cnd].copy()
    c['run'] = [bars[(t, d)][f'run_ship_{s}'] for t, d, s in zip(c.ticker, c.date, c.side)]
    for t in ('SPY', 'QQQ', 'IWM'):
        g = c[c.ticker == t]
        rows.append({'cand': cnd, 'ticker': t, 'changed_values': len(g), 'shipped_had_run>=3': int((g.run >= 3).sum()),
                     'of_those_change>5c': int(((g.run >= 3) & (g.cents > 5)).sum()),
                     'max_cents_of_those': g[g.run >= 3].cents.max()})
i3b = pd.DataFrame(rows); print(i3b.to_string(index=False)); i3b.to_csv(f'{OUT}/item3_supported_changes.csv', index=False)
print('C. dropped bars (non-thin) that had continuity: the bar before closed, or the bar after opened, within 0.1% of the prior close')
print(df.groupby('ticker')[[c for c in df.columns if c.endswith('_bars_dropped') or c.endswith('_dropped_supported')]].sum().to_string())
print('D. what is left: sessions where the result still sits within 5 cents of the prior close with no run of 3 bars there')
rows = []
for cnd in ['ship'] + CANDS:
    for t in ('SPY', 'QQQ', 'IWM'):
        g = df[(df.ticker == t) & (df.run_pc < 3)]
        r = {'cand': cnd, 'ticker': t}
        for side in ('high', 'low'):
            dist = ((g[f'{cnd}_{side}'] - g.pc).abs() * 100).round(2)
            r[f'{side}_within5c_no_run'] = int((dist <= 5).sum())
            r[f'{side}_exact_no_run'] = int((dist == 0).sum())
        rows.append(r)
print(pd.DataFrame(rows).to_string(index=False)); pd.DataFrame(rows).to_csv(f'{OUT}/item3_residual.csv', index=False)

print('\n==== ITEM 4: Task 12 Step 2, PM_MIN_EXTREME_VOLUME 100 against 0 (shipped function, atr=None) ====')
rows = []; thin = []
for t in ('SPY', 'QQQ', 'IWM'):
    g = df[df.ticker == t]
    r = {'ticker': t, 'sessions': len(g)}
    for side in ('high', 'low'):
        a, b = g[f'ship_{side}'], g[f'vol0_{side}']
        diff = ~(a.isna() & b.isna()) & ~(a == b)
        r[f'pre_{side}_changed'] = int(diff.sum()); r[f'pre_{side}_None_at_100'] = int((a.isna() & b.notna()).sum())
        x = g[diff][['ticker', 'date', f'vol0_{side}', f'ship_{side}', f'vol0_{side}_bar']].copy(); x.columns = ['ticker', 'date', 'at_0', 'at_100', 'bar_setting_value_at_0']
        x['side'] = side; x['cents'] = ((x.at_0 - x.at_100).abs() * 100).round(2); x['pct'] = ((x.at_0 - x.at_100).abs() / x.at_100 * 100).round(4)
        thin.append(x)
    rows.append(r)
print(pd.DataFrame(rows).to_string(index=False)); pd.DataFrame(rows).to_csv(f'{OUT}/item4_thin_counts.csv', index=False)
thin = pd.concat(thin); thin.to_csv(f'{OUT}/item4_thin_changes.csv', index=False)
for t in ('SPY', 'QQQ', 'IWM'):
    x = thin[thin.ticker == t]
    print(f'-- {t}: change size cents median {x.cents.median()} p90 {x.cents.quantile(.9)} max {x.cents.max()}; ten largest:')
    print(x.sort_values('cents', ascending=False).head(10).drop(columns=['ticker']).to_string(index=False))
print('-- ten largest over the three tickers:'); print(thin.sort_values('cents', ascending=False).head(10).to_string(index=False))
print('-- by year, sessions with pre_high or pre_low changed:')
th = thin.assign(year=thin.date.str[:4]).groupby(['ticker', 'year']).date.nunique().unstack(0); print(th.to_string())

print('\n==== SECONDARY: 2026 sessions with the recorded calibrated filter (ATR and both thresholds from pre_filter_params) ====')
f = df[df.get('F_ship_high').notna() | df.get('F_ship_low').notna()] if 'F_ship_high' in df else df.iloc[:0]
print('sessions', f.groupby('ticker').size().to_dict(), f.date.min(), f.date.max())
rows = []
for cnd in ('P1', 'P2', 'P3', 'P4', 'P2+P4'):
    ch = changes(f, f'F_{cnd}_high', f'F_{cnd}_low', 'F_ship_high', 'F_ship_low')
    ch['run'] = [bars[(t, d)][f'F_run_ship_{s}'] for t, d, s in zip(ch.ticker, ch.date, ch.side)]
    for t in ('SPY', 'QQQ', 'IWM'):
        c = ch[ch.ticker == t]
        rows.append({'cand': cnd, 'ticker': t, 'high_changed': int((c.side == 'high').sum()), 'low_changed': int((c.side == 'low').sum()),
                     'sessions_either': c.date.nunique(), 'cents_med': c.cents.median(), 'cents_p90': c.cents.quantile(.9), 'cents_max': c.cents.max(),
                     'shipped_had_run>=3': int((c.run >= 3).sum())})
    ch.sort_values(['ticker', 'cents'], ascending=[True, False]).to_csv(f'{OUT}/filtered2026_changes_{cnd.replace("+", "_")}.csv', index=False)
    if cnd in ('P2', 'P4'):
        print(f'-- {cnd}, ten largest with the filter on'); print(ch.sort_values('cents', ascending=False).head(10).to_string(index=False))
print(pd.DataFrame(rows).to_string(index=False)); pd.DataFrame(rows).to_csv(f'{OUT}/filtered2026_summary.csv', index=False)
print('filter on vs off, shipped rule, 2026: sessions where pre_high differs', int((~(f.F_ship_high == f.ship_high)).sum()), 'pre_low differs', int((~(f.F_ship_low == f.ship_low)).sum()))
