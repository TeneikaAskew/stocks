"""Experiment 2: ways to put the gap into the brief (H2a to H2e), scored in R on 1-min bars.
Reads days.csv, cache/sessions.pkl, brief_rows.json. Writes trades_exp2.csv and results_exp2.csv.
Usage: python3 exp2_brief_rules.py"""
import pickle, numpy as np, pandas as pd
from common import *
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 800); pd.set_option('display.max_colwidth', 90)
d = pd.read_csv(f'{LANE}/days.csv', keep_default_na=False, na_values=['', 'nan'])
cache = pickle.load(open(f'{LANE}/cache/sessions.pkl', 'rb')); rows = brief_rows()
ALLDAYS = {w: sorted(d[d.window == w].day.unique()) for w in ('primary', 'holdout')}
def call_dir(s):
    s = (s or '').upper(); return 1 if s.startswith('CALL') else -1 if s.startswith('PUT') else 0
def next_level(levels, px, sgn, atr, min_atr=0.1, min_dist=None):
    md = min_dist if min_dist is not None else min_atr * atr
    nx = [p for p in levels if (p - px) * sgn >= md]
    return (min(nx) if sgn > 0 else max(nx)) if nx else None
TR = []
def rec(strategy, variant, x, side, res, **tags):
    if res and res.get('fill') and res.get('R') is not None:
        TR.append(dict(strategy=strategy, variant=variant, day=x.day, ticker=x.ticker, window=x.window, side=side,
                       R=round(res['R'], 3), how=res['how'], entry_min=int(res['i']), **tags))
THR = (0.1, 0.25, 0.5)
for x in d.itertuples():
    s = cache[(x.day, x.ticker)]; h, l, o, c, ti, atr, pc = s['h'], s['l'], s['o'], s['c'], s['ti'], s['atr'], s['pc']
    for cut, gapcol in (('08:30', 'ind_gap_0829_atr'), ('09:20', 'ind_gap_0919_atr')):
        br = rows[(x.day, x.ticker, cut)]; call = call_dir(br['status']); ig = getattr(x, gapcol); og = x.gap_atr
        lv = sorted(set(br['levels'].values()))
        for sgn, k, side in ((1, 'calls', 'long'), (-1, 'puts', 'short')):
            trig, stop, t1 = br[f'{k}_trigger_price'], br[f'{k}_stop_price'], br[f'{k}_t1_price']
            if trig is None or stop is None: continue
            tags = dict(cutoff=cut, call=call, with_call=int(call == sgn), ind_gap=round(ig, 3) if ig == ig else None, open_gap=round(og, 3),
                        side_vs_indgap=int(np.sign(ig) * sgn) if ig == ig else 0, side_vs_opengap=int(np.sign(og) * sgn))
            base = sim(h, l, o, c, side, trig, stop, t1)
            rec('brief_trigger', 'own stop + own T1', x, side, base, **tags)
            # ladder target: next ladder level at least 1R beyond the trigger (T1 is often too close)
            risk = abs(trig - stop)
            tl = next_level(lv, trig, sgn, atr, min_dist=max(risk, 0.1 * atr)) if risk > 0 else None
            rec('brief_trigger', 'own stop + next ladder level >= 1R away', x, side, sim(h, l, o, c, side, trig, stop, tl), **tags)
            rec('brief_trigger', 'own stop + own T1, no entry after 10:00', x, side, sim(h, l, o, c, side, trig, stop, t1, last_entry=29), **tags)
            # H2c: fill-side trades, target = prior close
            if cut == '08:30' and og * sgn < 0 and base and base.get('fill'):
                px = base['px']
                if (pc - px) * sgn > 0:      # prior close still ahead of the entry
                    rec('fill_side', 'target = prior close (gap fill)', x, side, sim(h, l, o, c, side, trig, stop, pc), **tags)
                    rec('fill_side', 'target = own T1', x, side, base, **tags)
                    tt = t1 if (t1 is not None and abs(t1 - px) > abs(pc - px)) else pc
                    rec('fill_side', 'target = farther of T1 and prior close', x, side, sim(h, l, o, c, side, trig, stop, tt), **tags)
    # H2e: gap-and-go / gap-fade keyed on the first 5 or 15 minutes (decided on the 09:30 gap)
    if x.gap_dir == 0: continue
    g = int(x.gap_dir); lv = sorted(set(rows[(x.day, x.ticker, '08:30')]['levels'].values()))
    for nm, mins, hi, lo, cl in (('5', 575, x.or5_hi, x.or5_lo, x.c5), ('15', 585, x.or15_hi, x.or15_lo, x.c15)):
        st = int(np.argmax(ti >= mins)); bar = int(np.sign(cl - x.open)); e = o[st]
        tags = dict(cutoff='open', open_gap=round(x.gap_atr, 3), first_bar_vs_gap=bar * g)
        for sgn, lab in ((g, 'go'), (-g, 'fade')):
            side = 'long' if sgn > 0 else 'short'; stop = lo if sgn > 0 else hi
            if (e - stop) * sgn <= 0: continue
            risk = abs(e - stop)
            tg_ladder = next_level(lv + [pc], e, sgn, atr, min_dist=max(risk, 0.1 * atr))
            rec(f'first{nm}_{lab}', 'stop = other end of opening bar, target = next ladder level >= 1R', x, side, sim(h, l, o, c, side, None, stop, tg_ladder, start=st, market=True), **tags)
            rec(f'first{nm}_{lab}', 'stop = other end of opening bar, target = 2R', x, side, sim(h, l, o, c, side, None, stop, e + sgn * 2 * risk, start=st, market=True), **tags)
            rec(f'first{nm}_{lab}', 'stop = other end of opening bar, hold to close', x, side, sim(h, l, o, c, side, None, stop, None, start=st, market=True), **tags)
            if lab == 'fade' and (pc - e) * sgn > 0:
                rec(f'first{nm}_{lab}', 'stop = other end of opening bar, target = prior close (fill)', x, side, sim(h, l, o, c, side, None, stop, pc, start=st, market=True), **tags)
t = pd.DataFrame(TR); t.to_csv(f'{LANE}/trades_exp2.csv', index=False)
print(len(t), 'simulated trades ->', 'trades_exp2.csv')

RES = []
def agg(hyp, label, sel, base=None):
    """One result line per window x ticker: n, win %, total R (range), avg R (range). base: trades to subtract (paired by day)."""
    for win in ('primary', 'holdout'):
        for tk in ('ALL',) + T:
            s = sel[(sel.window == win) & ((sel.ticker == tk) | (tk == 'ALL'))]
            if len(s) == 0: continue
            lo, hi = boot(s.R, s.day, 'sum', all_days=ALLDAYS[win]); alo, ahi = boot(s.R, s.day)
            r = dict(experiment='2', hypothesis=hyp, variant=label, window=win, ticker=tk, n=len(s), win_pct=round(100 * (s.R > 0).mean(), 1),
                     total_R=round(s.R.sum(), 2), total_lo=round(lo, 2), total_hi=round(hi, 2), avg_R=round(s.R.mean(), 3), avg_lo=round(alo, 3), avg_hi=round(ahi, 3))
            if base is not None:
                b = base[(base.window == win) & ((base.ticker == tk) | (tk == 'ALL'))]
                dlo, dhi = boot_diff(s.R, s.day, b.R, b.day, 'sum', all_days=ALLDAYS[win]); mlo, mhi = boot_diff(s.R, s.day, b.R, b.day)
                r.update(vs_base_total=round(s.R.sum() - b.R.sum(), 2), vs_lo=round(dlo, 2), vs_hi=round(dhi, 2),
                         vs_base_avg=round(s.R.mean() - b.R.mean(), 3) if len(b) else None, vsavg_lo=round(mlo, 3), vsavg_hi=round(mhi, 3))
            RES.append(r)
bt = t[t.strategy == 'brief_trigger']
for cut in ('08:30', '09:20'):
    for var in bt.variant.unique():
        b = bt[(bt.cutoff == cut) & (bt.variant == var)]; wc = b[b.with_call == 1]
        tag = f'[{cut} brief, {var}]'
        agg('baseline', f'{tag} trigger trades in the brief call direction', wc)
        agg('baseline', f'{tag} all trigger trades, both sides, every day', b)
        for gcol, gname in (('ind_gap', 'gap seen at the brief cutoff'), ('open_gap', '09:30 gap')):
            sidecol = 'side_vs_indgap' if gcol == 'ind_gap' else 'side_vs_opengap'
            for thr in THR:
                big = b[b[gcol].abs() >= thr]
                # H2a override: trade the gap side instead of the call side, on days with a call or not
                agg('H2a', f'{tag} OVERRIDE: take the trigger on the gap side when |{gname}| >= {thr} ATR', big[big[sidecol] == 1], base=wc[wc[gcol].abs() >= thr])
                agg('H2a', f'{tag} FADE override: take the trigger against the gap when |{gname}| >= {thr} ATR', big[big[sidecol] == -1], base=wc[wc[gcol].abs() >= thr])
                # H2b confidence: call-direction trades with vs against the gap
                w_ = wc[(wc[gcol].abs() >= thr) & (wc[sidecol] == 1)]; a_ = wc[(wc[gcol].abs() >= thr) & (wc[sidecol] == -1)]
                agg('H2b', f'{tag} call WITH {gname} (>= {thr} ATR)', w_, base=a_)
                agg('H2b', f'{tag} call AGAINST {gname} (>= {thr} ATR)', a_)
                # H2d skip: keep everything except call-direction trades against the gap
                keep = wc[~((wc[gcol].abs() >= thr) & (wc[sidecol] == -1))]
                agg('H2d', f'{tag} SKIP call trades against {gname} >= {thr} ATR', keep, base=wc)
fs = t[t.strategy == 'fill_side']
for lab, lo_, hi_ in (('all gaps', 0, 99), ('|gap| < 0.25 ATR', 0, 0.25), ('|gap| 0.25-0.50 ATR', 0.25, 0.5), ('|gap| >= 0.50 ATR', 0.5, 99)):
    k = fs[(fs.open_gap.abs() >= lo_) & (fs.open_gap.abs() < hi_)]; b0 = k[k.variant == 'target = own T1']
    for var in fs.variant.unique():
        agg('H2c', f'fill-side trigger trades, {lab}: {var}', k[k.variant == var], base=None if var == 'target = own T1' else b0)
for nm in ('5', '15'):
    for thr in (0.0,) + THR:
        for var in t[t.strategy == f'first{nm}_go'].variant.unique():
            go = t[(t.strategy == f'first{nm}_go') & (t.variant == var) & (t.open_gap.abs() >= thr)]
            fd = t[(t.strategy == f'first{nm}_fade') & (t.variant == var) & (t.open_gap.abs() >= thr)]
            pre = f'[first {nm} min, |gap| >= {thr} ATR, {var}]'
            agg('H2e', f'{pre} GO when the bar closed with the gap', go[go.first_bar_vs_gap == 1], base=go)
            agg('H2e', f'{pre} FADE when the bar closed against the gap', fd[fd.first_bar_vs_gap == -1], base=fd)
            agg('H2e', f'{pre} always GO (ignore the bar)', go)
            agg('H2e', f'{pre} always FADE (ignore the bar)', fd)
            both = pd.concat([go[go.first_bar_vs_gap == 1], fd[fd.first_bar_vs_gap == -1]])
            agg('H2e', f'{pre} FOLLOW the first bar (go or fade)', both)
            anti = pd.concat([go[go.first_bar_vs_gap == -1], fd[fd.first_bar_vs_gap == 1]])
            agg('H2e', f'{pre} OPPOSE the first bar', anti)
        var = 'stop = other end of opening bar, target = prior close (fill)'
        fd = t[(t.strategy == f'first{nm}_fade') & (t.variant == var) & (t.open_gap.abs() >= thr)]
        agg('H2e', f'[first {nm} min, |gap| >= {thr} ATR, {var}] FADE when the bar closed against the gap', fd[fd.first_bar_vs_gap == -1], base=fd)
        agg('H2e', f'[first {nm} min, |gap| >= {thr} ATR, {var}] always FADE (ignore the bar)', fd)
res = pd.DataFrame(RES); res.to_csv(f'{LANE}/results_exp2.csv', index=False)
def show(hyp, contains=None, tick='ALL', cols=('n', 'win_pct', 'total_R', 'total_lo', 'total_hi', 'avg_R', 'avg_lo', 'avg_hi', 'vs_base_total', 'vs_lo', 'vs_hi')):
    r = res[(res.hypothesis == hyp) & (res.ticker == tick)]
    if contains: r = r[r.variant.str.contains(contains, regex=False)]
    print(f'\n=== {hyp} {contains or ""} ({tick})'); print(r[['variant', 'window'] + list(cols)].to_string(index=False))
if __name__ == '__main__':
    show('baseline'); show('H2b', '[08:30 brief, own stop + own T1]'); show('H2d', '[08:30 brief, own stop + own T1]'); show('H2a', '[08:30 brief, own stop + own T1]')
    show('H2c'); show('H2e', 'target = next ladder'); show('H2e', 'target = prior close')
