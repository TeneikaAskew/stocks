"""Replay each example day on QQQ 1-min bars: the trader's posted plan and the owner's 08:30 brief.
Writes example_days.csv (one row per plan side per day) and charts/<day>.png.
Usage: python3 example_days.py"""
import json
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from common import *

TK = 'QQQ'
BLUE, ORANGE, INK, MUTED, SURF = '#2a78d6', '#eb6834', '#2b2b28', '#8a897f', '#fcfcfb'
# Trader plans exactly as posted. 'from' = earliest time a follower could act (post time if after the open).
PLANS = {
 '2026-10-27': dict(calls=(713.06, [714.44, 715.43, 717.57, 719.71, 720.0]), puts=(705.58, [702.09, 701.16]),
                    note='Rule in the post: only an open BELOW 713.06 makes it the upside trigger.'),
 '2026-10-28': dict(watch=[727.95, 730.0, 713.59, 705.58, 701.16, 700.0], note='No trigger posted. Watch 727.95 / 730; else lows 713.59 705.58 701.16 700.'),
 '2026-10-29': dict(puts=('PDL', [713.59]), note='No clear read. Implied: daily 22 REV down below the prior day low, magnitude 713.59. Wait for the first hour.', implied=True),
 '2026-11-09': dict(calls=(664.52, [668.17, 671.59, 683.65]), puts=(653.99, [647.05, 642.21, 635.26])),
 '2026-11-10': dict(calls=(679.50, [681.11, 682.48, 683.65, 685.54, 687.87]), puts=(662.02, [653.99, 659.10, 656.94, 647.05]),
                    frm='09:56', note='Posted about 09:56 ET (after the open). PT "68.11" read as 681.11.'),
}
WEEK = dict(days=['2026-11-02', '2026-11-03', '2026-11-04', '2026-11-05', '2026-11-06'], puts=680.05, void=(711.62, 698.63))

def brief(day):
    return json.load(open(f'{LANE}/brief_replay/main0830_{day}.json'))['tickers'][TK]

def pt_hits(b, side, pts, t0):
    """Time each PT is first touched at or after t0 (regardless of stop)."""
    x = b[b.index >= t0]; out = {}
    for p in pts:
        hit = x[x.high >= p] if side == 'long' else x[x.low <= p]
        out[p] = hit.index[0] if len(hit) else None
    return out

def sim_side(b, side, trig, pts, opp, strat_stop, frm=None):
    x = b if frm is None else b[b.index >= frm]
    r = dict(trigger=trig, pts=pts)
    ta = trade(x, side, trig, opp, pts[0] if pts else None) if opp is not None else None
    tb = trade(x, side, trig, strat_stop, pts[0] if pts else None)
    base = tb or ta
    if not base or not base.get('fill'):
        r.update(filled=False); return r
    hits = pt_hits(x, side, pts, base['fill_t'])
    after = x[x.index >= base['fill_t']]
    mae_all = (base['px'] - after.low.min()) if side == 'long' else (after.high.max() - base['px'])
    mfe_all = (after.high.max() - base['px']) if side == 'long' else (base['px'] - after.low.min())
    r.update(filled=True, fill_t=base['fill_t'], fill_px=base['px'], thru_open=base['thru_open'],
             pts_hit={p: (t.strftime('%H:%M') if t is not None else None) for p, t in hits.items()},
             max_adverse_pts=round(float(mae_all), 2), max_favorable_pts=round(float(mfe_all), 2),
             close=float(x.close.iloc[-1]))
    for nm, tr, st in (('opp', ta, opp), ('strat', tb, strat_stop)):
        if tr and tr.get('fill'):
            r[f'stop_{nm}'] = st; r[f'R_{nm}'] = tr.get('R'); r[f'how_{nm}'] = tr.get('how')
            r[f'exit_t_{nm}'] = tr['exit_t'].strftime('%H:%M') if tr.get('exit_t') is not None else None
    return r

def run():
    rows = []; d = daily(TK)
    for day, plan in PLANS.items():
        b = rth(TK, day); prev = d[d.index < day].iloc[-1]; mid = (prev.high + prev.low) / 2
        o = float(b.open.iloc[0]); br = brief(day)
        H = h12(bars(TK)[:f'{day} 03:59']).iloc[-1]; m12 = (H.high + H.low) / 2
        ctx = dict(day=day, open=o, high=float(b.high.max()), low=float(b.low.min()), close=float(b.close.iloc[-1]),
                   prior_high=prev.high, prior_low=prev.low, prior_mid=round(mid, 2), m12=round(m12, 2), h12_high=H.high, h12_low=H.low)
        frm = f"{day} {plan['frm']}" if plan.get('frm') else None
        calls, puts = plan.get('calls'), plan.get('puts')
        if puts and puts[0] == 'PDL': puts = (float(prev.low), puts[1])
        for side, spec, opp in (('long', calls, puts), ('short', puts, calls)):
            if not spec: continue
            trig, pts = spec
            is12 = side == 'long' and day in ('2026-10-27', '2026-11-10')
            # Strat stop (stated in README): 12HR entry -> far end of that 12H candle; daily trigger -> 50% of prior day
            st = (H.low if side == 'long' else H.high) if is12 else mid
            variants = [('from 09:30', None)] + ([(f"from {plan['frm']} (post time)", frm)] if frm else [])
            for vn, f in variants:
                r = sim_side(b, side, trig, pts, opp[0] if opp else None, st, f)
                rows.append(dict(ctx, who='trader', side=side, variant=vn, strat_stop_rule='12H candle far end' if is12 else '50% of prior day', **r))
        # brief, both sides, its own stop and T1
        for side, k in (('long', 'calls'), ('short', 'puts')):
            trig, st, t1 = br.get(f'{k}_trigger_price'), br.get(f'{k}_stop_price'), br.get(f'{k}_t1_price')
            tr = trade(b, side, trig, st, t1) or {}
            pts = [x for x in (br.get(f'{k}_t1_price'), br.get(f'{k}_t2_price'), br.get(f'{k}_t3_price')) if x is not None]
            r = dict(trigger=trig, pts=pts, filled=bool(tr.get('fill')))
            if tr.get('fill'):
                hits = pt_hits(b, side, pts, tr['fill_t']); after = b[b.index >= tr['fill_t']]
                r.update(fill_t=tr['fill_t'], fill_px=tr['px'], thru_open=tr['thru_open'], stop_strat=st, R_strat=tr.get('R'), how_strat=tr.get('how'),
                         exit_t_strat=tr['exit_t'].strftime('%H:%M') if tr.get('exit_t') is not None else None,
                         pts_hit={p: (t.strftime('%H:%M') if t is not None else None) for p, t in hits.items()},
                         max_adverse_pts=round(float((tr['px'] - after.low.min()) if side == 'long' else (after.high.max() - tr['px'])), 2),
                         max_favorable_pts=round(float((after.high.max() - tr['px']) if side == 'long' else (tr['px'] - after.low.min())), 2))
            rows.append(dict(ctx, who='brief', side=side, variant=f"{br['signal_status']} | {br.get(f'{k}_trigger_name')} stop {br.get(f'{k}_stop_name')}",
                             strat_stop_rule="brief's own stop", brief_call_side=(br['signal_status'].upper().startswith('CALL') and side == 'long') or (br['signal_status'].upper().startswith('PUT') and side == 'short'), **r))
        chart(day, b, plan, calls, puts, br, [r for r in rows if r['day'] == day], ctx)
    # week of 11/02: puts below 680.05, posted Saturday; stop = 50% of the day before the trigger day
    wk = pd.concat([rth(TK, x) for x in WEEK['days']])
    hit = wk[wk.low <= WEEK['puts']]
    wr = dict(day='week 2026-11-02', who='trader', side='short', variant='week, first regular-hours trade below 680.05', trigger=WEEK['puts'], pts=[], filled=len(hit) > 0)
    if len(hit):
        t0 = hit.index[0]; dday = str(t0.date()); bd = rth(TK, dday); prev = d[d.index < dday].iloc[-1]; mid = (prev.high + prev.low) / 2
        tr = trade(bd, 'short', WEEK['puts'], mid, None)
        after = wk[wk.index >= t0]
        wr.update(fill_t=tr['fill_t'], fill_px=tr['px'], thru_open=tr['thru_open'], stop_strat=round(mid, 2), R_strat=tr['R'], how_strat=tr['how'] + ' of trigger day',
                  strat_stop_rule='50% of prior day', max_adverse_pts=tr['mae'], max_favorable_pts=round(float(tr['px'] - after.low.min()), 2),
                  close=float(bd.close.iloc[-1]), open=float(bd.open.iloc[0]), high=float(bd.high.max()), low=float(bd.low.min()))
    rows.append(wr)
    for dday in WEEK['days']:
        br = brief(dday); b = rth(TK, dday)
        for side, k in (('long', 'calls'), ('short', 'puts')):
            tr = trade(b, side, br.get(f'{k}_trigger_price'), br.get(f'{k}_stop_price'), br.get(f'{k}_t1_price')) or {}
            rows.append(dict(day=dday, who='brief', side=side, variant=f"{br['signal_status']} | {br.get(f'{k}_trigger_name')} stop {br.get(f'{k}_stop_name')}",
                             trigger=br.get(f'{k}_trigger_price'), pts=[br.get(f'{k}_t1_price')], filled=bool(tr.get('fill')), fill_t=tr.get('fill_t'), fill_px=tr.get('px'),
                             thru_open=tr.get('thru_open'), stop_strat=br.get(f'{k}_stop_price'), R_strat=tr.get('R'), how_strat=tr.get('how'),
                             open=float(b.open.iloc[0]), high=float(b.high.max()), low=float(b.low.min()), close=float(b.close.iloc[-1]),
                             brief_call_side=(br['signal_status'].upper().startswith('CALL') and side == 'long') or (br['signal_status'].upper().startswith('PUT') and side == 'short')))
    week_chart(wk, d)
    df = pd.DataFrame(rows); df.to_csv(f'{LANE}/example_days.csv', index=False)
    pd.set_option('display.width', 300); pd.set_option('display.max_colwidth', 70); pd.set_option('display.max_rows', 200); pd.set_option('display.max_columns', 40)
    print(df[['day', 'who', 'side', 'variant', 'trigger', 'filled', 'fill_t', 'fill_px', 'thru_open', 'stop_opp', 'R_opp', 'how_opp', 'stop_strat', 'R_strat', 'how_strat', 'exit_t_strat', 'max_adverse_pts', 'max_favorable_pts', 'pts_hit']].to_string())
    print(df.drop_duplicates('day')[['day', 'open', 'high', 'low', 'close', 'prior_high', 'prior_low', 'm12', 'h12_high', 'h12_low']].to_string())

def _lines(ax, levels, color, ls, x1, side_lab):
    for p, lab in levels:
        ax.axhline(p, color=color, ls=ls, lw=1.2, alpha=.9, zorder=2)
        ax.annotate(f'{lab} {p:.2f}', xy=(1.005, p), xycoords=('axes fraction', 'data'), fontsize=7.5, color=INK, va='center',
                    bbox=dict(boxstyle='square,pad=0.1', fc=SURF, ec=color, lw=.8))

def _spread(levels, ylo, yhi):
    m = {}
    for p, l in levels:
        if ylo <= p <= yhi: m.setdefault(round(p, 2), []).append(l)
    return [(p, ' / '.join(ls)) for p, ls in m.items()]
BB = dict(boxstyle='square,pad=0.15', fc=SURF, ec='none')

def chart(day, b, plan, calls, puts, br, rows, ctx):
    pm = bars(TK).loc[f'{day} 08:00':f'{day} 09:29']
    fig, ax = plt.subplots(figsize=(13, 7), facecolor=SURF); ax.set_facecolor(SURF)
    ax.plot(pm.index, pm.close, color=MUTED, lw=1, zorder=3); ax.plot(b.index, b.close, color=INK, lw=1.4, zorder=3)
    ax.axvline(pd.Timestamp(f'{day} 09:30'), color=MUTED, lw=.6, ls=':')
    lo, hi = min(b.low.min(), pm.low.min()), max(b.high.max(), pm.high.max()); pad = (hi - lo) * .35
    ylo, yhi = lo - pad, hi + pad
    tl = []
    if calls: tl += [(calls[0], 'T calls >')] + [(p, f'T PT{i+1}') for i, p in enumerate(calls[1])]
    if puts: tl += [(puts[0], 'T puts <')] + [(p, f'T PT{i+1}') for i, p in enumerate(puts[1])]
    tl += [(p, 'T watch') for p in plan.get('watch', [])]
    bl = [(br['calls_trigger_price'], 'B calls >'), (br['calls_stop_price'], 'B call stop'), (br['calls_t1_price'], 'B call T1'),
          (br['puts_trigger_price'], 'B puts <'), (br['puts_stop_price'], 'B put stop'), (br['puts_t1_price'], 'B put T1')]
    bl = [(p, l) for p, l in bl if p is not None]
    for p, l in _spread(tl, ylo, yhi):
        ax.axhline(p, color=BLUE, lw=1.3, zorder=2); ax.text(b.index[-1] + pd.Timedelta(minutes=4), p, f'{l} {p:.2f}', fontsize=7.5, color=INK, va='center', bbox=BB, zorder=5)
    for p, l in _spread(bl, ylo, yhi):
        ax.axhline(p, color=ORANGE, lw=1.3, ls=(0, (5, 3)), zorder=2); ax.text(pm.index[0] - pd.Timedelta(minutes=4), p, f'{l} {p:.2f}', fontsize=7.5, color=INK, va='center', ha='right', bbox=BB, zorder=5)
    for r in rows:
        if not r.get('filled') or (r['who'] == 'trader' and r['variant'] != 'from 09:30' and 'post time' not in r['variant']): continue
        if r['who'] == 'trader' and plan.get('frm') and r['variant'] == 'from 09:30': continue
        c = BLUE if r['who'] == 'trader' else ORANGE
        ax.scatter([r['fill_t']], [r['fill_px']], marker='^' if r['side'] == 'long' else 'v', s=110, color=c, edgecolor=SURF, lw=1.5, zorder=6)
        for p, t in (r.get('pts_hit') or {}).items():
            if t: ax.scatter([pd.Timestamp(f'{day} {t}')], [p], marker='o', s=45, color=c, edgecolor=SURF, lw=1.5, zorder=6)
    ax.set_ylim(ylo, yhi); ax.set_xlim(pm.index[0] - pd.Timedelta(minutes=110), b.index[-1] + pd.Timedelta(minutes=75))
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%H:%M')); ax.grid(axis='y', color='#e6e5df', lw=.5); ax.tick_params(colors=MUTED, labelsize=8)
    for s in ax.spines.values(): s.set_visible(False)
    h = [plt.Line2D([], [], color=BLUE, lw=1.3, label="Trader's posted levels (T), labels right"), plt.Line2D([], [], color=ORANGE, lw=1.3, ls=(0, (5, 3)), label="Owner's 08:30 brief levels (B), labels left"),
         plt.Line2D([], [], color=INK, lw=1.4, label='QQQ 1-min close (grey = premarket from 08:00)'),
         plt.Line2D([], [], color=MUTED, marker='^', ls='', ms=9, label='entry (triangle up = calls, down = puts)'), plt.Line2D([], [], color=MUTED, marker='o', ls='', ms=6, label='target touched after entry')]
    ax.legend(handles=h, loc='upper center', bbox_to_anchor=(0.5, -0.05), fontsize=8, frameon=False, ncol=3)
    ax.set_title(f"QQQ {day}: trader's plan vs the 08:30 brief ({br['signal_status']})\n{plan.get('note', '')}", fontsize=11, color=INK, loc='left')
    fig.tight_layout(); fig.savefig(f'{LANE}/charts/{day}.png', dpi=130); plt.close(fig)

def week_chart(wk, d):
    fig, ax = plt.subplots(figsize=(13, 6.5), facecolor=SURF); ax.set_facecolor(SURF)
    x = np.arange(len(wk)); ax.plot(x, wk.close.values, color=INK, lw=1.2, zorder=3)
    days = sorted(set(wk.index.date)); pos = [np.where(wk.index.date == dd)[0][0] for dd in days]
    for p in pos: ax.axvline(p, color=MUTED, lw=.6, ls=':')
    ax.set_xticks(pos); ax.set_xticklabels([str(dd) for dd in days], fontsize=8)
    ax.axhline(WEEK['puts'], color=BLUE, lw=1.3); ax.text(len(wk) + 15, WEEK['puts'], 'T puts < 680.05', fontsize=8, va='center', color=INK, bbox=BB, zorder=5)
    ax.axhspan(WEEK['void'][1], WEEK['void'][0], color=BLUE, alpha=.12, lw=0); ax.text(len(wk) + 15, 705, 'T daily void\n698.63 to 711.62', fontsize=8, va='center', color=INK)
    for dd, p in zip(days, pos):
        br = brief(str(dd)); n = int((wk.index.date == dd).sum())
        for k, lab in (('calls', 'B calls >'), ('puts', 'B puts <')):
            v = br.get(f'{k}_trigger_price')
            if v: ax.hlines(v, p, p + n - 1, color=ORANGE, lw=1.3, ls=(0, (5, 3))); ax.text(p + 5, v + (0.6 if k == 'calls' else -0.6), f'{lab} {v:.2f}', fontsize=7, color=INK, va='bottom' if k == 'calls' else 'top', bbox=BB, zorder=5)
    hit = np.where(wk.low.values <= WEEK['puts'])[0]
    if len(hit): ax.scatter([hit[0]], [min(WEEK['puts'], wk.open.values[hit[0]])], marker='v', s=120, color=BLUE, edgecolor=SURF, lw=1.5, zorder=6)
    ax.set_xlim(-10, len(wk) + 230); ax.grid(axis='y', color='#e6e5df', lw=.5); ax.tick_params(colors=MUTED, labelsize=8)
    for s in ax.spines.values(): s.set_visible(False)
    h = [plt.Line2D([], [], color=BLUE, lw=1.3, label="Trader's posted levels (T)"), plt.Line2D([], [], color=ORANGE, lw=1.3, ls=(0, (5, 3)), label="Brief's daily triggers (B), premarket high / low"),
         plt.Line2D([], [], color=INK, lw=1.2, label='QQQ 1-min close, regular hours'), plt.Line2D([], [], color=BLUE, marker='v', ls='', ms=9, label='trader puts entry')]
    ax.legend(handles=h, loc='upper center', bbox_to_anchor=(0.5, -0.06), fontsize=8, frameon=False, ncol=4)
    ax.set_title('QQQ week of 2026-11-02: "puts below 680.05, watch the daily void 711.62 to 698.63" (posted Sat 10/31)', fontsize=11, color=INK, loc='left')
    fig.tight_layout(); fig.savefig(f'{LANE}/charts/week_2026-11-02.png', dpi=130); plt.close(fig)

if __name__ == '__main__':
    run()
