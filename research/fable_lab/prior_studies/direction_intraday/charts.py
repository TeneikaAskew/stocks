"""Example-session charts for the direction_intraday study. Usage: python charts.py"""
import os, sys
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from analyze import bars

INK, INK2, MUTED, GRID, SURF = '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#fcfcfb'
UP, DN = '#2a78d6', '#eb6834'          # candle up / down
TRIG, OTRIG = '#6250d6', '#b9b7ae'     # call side trigger, other side trigger
STOP, T1 = '#d03b3b', '#008300'

EXAMPLES = [
    ('2025-10-31', 'SPY', 'ex1_2025-10-31_SPY_put_wrong_at_close_right_intraday.png',
     'SPY Oct 31 2025: PUT call, scored wrong at the close, right during the day'),
    ('2026-06-10', 'QQQ', 'ex2_2026-06-10_QQQ_call_right_early_then_reversed.png',
     'QQQ Jun 10 2026: CALL call, right by 09:48, then reversed and closed wrong'),
    ('2025-08-22', 'SPY', 'ex3_2025-08-22_SPY_call_clearly_right.png',
     'SPY Aug 22 2025: CALL call, clearly right'),
    ('2025-08-01', 'SPY', 'ex4_2025-08-01_SPY_call_clearly_wrong.png',
     'SPY Aug 1 2025: CALL call, clearly wrong'),
]

def candles(ax, b, width):
    for ts, r in b.iterrows():
        x = mdates.date2num(ts)
        col = UP if r.close >= r.open else DN
        ax.vlines(x, r.low, r.high, color=col, lw=0.8, zorder=2)
        lo, hi = sorted((r.open, r.close))
        ax.add_patch(Rectangle((x - width / 2, lo), width, max(hi - lo, 1e-6), facecolor=col,
                               edgecolor=col, lw=0.4, zorder=3, alpha=0.95 if ts.hour >= 9 and not (ts.hour == 9 and ts.minute < 30) else 0.45))

LABELS = []
def hline(ax, y, x0, x1, color, ls, lw, label, side_text):
    ax.hlines(y, x0, x1, colors=color, linestyles=ls, lw=lw, zorder=4)
    LABELS.append((y, f'{side_text} {y:.2f}', color))

def place_labels(ax, x, gap):
    items = sorted(LABELS)
    ys = [it[0] for it in items]
    for i in range(1, len(ys)):          # push labels apart, bottom up
        if ys[i] - ys[i - 1] < gap:
            ys[i] = ys[i - 1] + gap
    for (y0, txt, col), y in zip(items, ys):
        ax.text(x, y, ' ' + txt, va='center', ha='left', fontsize=8.5, color=INK2)
        ax.plot([x, x + 0.004], [y0, y], color=col, lw=0.8, clip_on=False)
    LABELS.clear()

def chart(day, t, fname, title, stats):
    r = stats[(stats.day == day) & (stats.ticker == t)].iloc[0]
    s = r.call; a = 'down' if s == 'up' else 'up'
    b1 = bars(t).loc[f'{day} 04:00':f'{day} 15:59'].copy()
    # premarket only: clip isolated 1 minute bad prints (stale or odd lot) to within 0.3 ATR of the rolling median close
    pm = b1.index < pd.Timestamp(f'{day} 09:30')
    med = b1.close.rolling(15, center=True, min_periods=3).median()
    cap = 0.3 * r.atr
    for c in ('open', 'high', 'low', 'close'):
        b1.loc[pm, c] = b1.loc[pm, c].clip(lower=med[pm] - cap, upper=med[pm] + cap)
    b = b1.resample('5min', label='left', closed='left').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    atr, o, pc = r.atr, r.open, r.prev_close
    fig, ax = plt.subplots(figsize=(13, 7.6), dpi=130)
    fig.patch.set_facecolor(SURF); ax.set_facecolor(SURF)
    x0 = mdates.date2num(pd.Timestamp(f'{day} 04:00')); x1 = mdates.date2num(pd.Timestamp(f'{day} 16:00'))
    xo = mdates.date2num(pd.Timestamp(f'{day} 09:30')); xb = mdates.date2num(pd.Timestamp(f'{day} 08:30'))
    ax.axvspan(x0, xo, color='#f0efec', zorder=0)
    ax.text(x0 + 0.002, 1.0, 'premarket', transform=ax.get_xaxis_transform(), va='top', fontsize=8.5, color=MUTED)
    ax.axvline(xb, color=MUTED, lw=1, ls=(0, (2, 2)), zorder=1)
    ax.text(xb, 1.0, ' brief runs 08:30', transform=ax.get_xaxis_transform(), va='top', fontsize=8.5, color=INK2)
    candles(ax, b, 4 / (24 * 60))
    # reference lines
    hline(ax, pc, x0, x1, INK, (0, (6, 3)), 1.2, '', 'prior close')
    hline(ax, o, xo, x1, MUTED, '-', 0.9, '', 'open')
    sgn = 1 if s == 'up' else -1
    for k, txt in ((0.5, '0.5 ATR for call'), (-0.5, '0.5 ATR against')):
        y = o + sgn * k * atr
        ax.hlines(y, xo, x1, colors='#1baf7a' if k > 0 else STOP, linestyles=(0, (1, 2)), lw=1.1, zorder=4)
        LABELS.append((y, f'{txt} {y:.2f}', '#1baf7a' if k > 0 else STOP))
    trig = r[f'{s}_trig']; otrig = r[f'{a}_trig']
    if pd.notna(trig):
        hline(ax, trig, x0, x1, TRIG, '-', 1.6, '', f'{"calls" if s == "up" else "puts"} trigger')
        if pd.notna(r[f'{s}_stop']): hline(ax, r[f'{s}_stop'], xo, x1, STOP, '-', 1.1, '', 'stop')
        if pd.notna(r[f'{s}_t1']): hline(ax, r[f'{s}_t1'], xo, x1, T1, '-', 1.1, '', 'T1')
    if pd.notna(otrig):
        hline(ax, otrig, x0, x1, OTRIG, '-', 1.1, '', f'{"puts" if s == "up" else "calls"} trigger (other side)')
    # first 0.5 ATR hit markers
    rth = bars(t).loc[f'{day} 09:30':f'{day} 15:59']
    for side, mk, col, lab in ((s, '^' if s == 'up' else 'v', '#1baf7a', 'first 0.5 ATR move for the call'),
                               (a, 'X', STOP, 'first 0.5 ATR move against')):
        tt = r[f'{side}_hit0.5_t']
        if isinstance(tt, str) and tt:
            ts = pd.Timestamp(f'{day} {tt}')
            y = o + (0.5 * atr if side == 'up' else -0.5 * atr)
            ax.scatter([mdates.date2num(ts)], [y], marker=mk, s=110, color=col, edgecolor='white', lw=1.2, zorder=6, label=f'{lab} ({tt})')
    if isinstance(r[f'{s}_trig_t'], str) and r[f'{s}_trig_t']:
        ts = pd.Timestamp(f'{day} {r[f"{s}_trig_t"]}')
        ax.scatter([mdates.date2num(ts)], [trig], marker='o', s=70, facecolor='none', edgecolor=TRIG, lw=1.8, zorder=6,
                   label=f'trigger touched ({r[f"{s}_trig_t"]})')
    rt = b.loc[f'{day} 09:30':]
    lv = [y for y, _, _ in LABELS]
    lo = min(rt.low.min(), b.open.min(), b.close.min(), *lv); hi = max(rt.high.max(), b.open.max(), b.close.max(), *lv)
    pad = (hi - lo) * 0.06
    ax.set_ylim(lo - pad, hi + pad)
    place_labels(ax, x1 + 0.004, (hi - lo + 2 * pad) * 0.032)
    ax.set_xlim(x0, x1 + 0.10)
    ax.set_xticks([mdates.date2num(pd.Timestamp(f'{day} {h:02d}:00')) for h in range(4, 17)])
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.grid(axis='y', color=GRID, lw=0.6); ax.set_axisbelow(True)
    for sp in ('top', 'right'): ax.spines[sp].set_visible(False)
    for sp in ('left', 'bottom'): ax.spines[sp].set_color('#c3c2b7')
    ax.tick_params(colors=INK2, labelsize=9)
    ax.set_ylabel(f'{t} price (5 minute candles, ET)', color=INK2, fontsize=9.5)
    ax.set_title(title, loc='left', fontsize=13, color=INK, pad=24)
    ax.text(0, 1.035, f'Brief at 08:30: {r.status}. ATR {atr:.2f}. Shaded area is premarket (isolated bad print wicks clipped); 5 minute candles, 04:00 to 16:00 ET.',
            transform=ax.transAxes, fontsize=9, color=INK2)
    clo = 'right' if r.call_close_right else 'wrong'
    sc = (r.close - pc) / atr * sgn; oc = (r.close - o) / atr * sgn
    rR = r[f'{s}_trig_R']
    box = (f'Best move for the call: {r.call_mfe:.2f} ATR (at {r[f"{s}_mfe_t"]})\n'
           f'Worst move against: {r.call_mae:.2f} ATR (at {r[f"{a}_mfe_t"]})\n'
           f'Close vs prior close: {sc:+.2f} ATR in call direction ({clo})\n'
           f'Close vs 09:30 open: {oc:+.2f} ATR in call direction\n'
           f'Trigger trade: {"no fill" if pd.isna(rR) else f"{rR:+.2f} R ({r[s + "_trig_how"]})"}')
    ax.text(0.0, -0.10, box, transform=ax.transAxes, fontsize=9, color=INK, va='top', ha='left', family='monospace',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='white', edgecolor=GRID))
    leg = ax.legend(loc='upper left', bbox_to_anchor=(0.42, -0.10), fontsize=8.5, frameon=True, facecolor='white', edgecolor=GRID)
    for txt in leg.get_texts(): txt.set_color(INK2)
    fig.subplots_adjust(left=0.06, right=0.97, top=0.89, bottom=0.25)
    fig.savefig(f'{HERE}/{fname}', facecolor=SURF)
    plt.close(fig)

if __name__ == '__main__':
    st = pd.read_csv(f'{HERE}/session_stats.csv', keep_default_na=True)
    for day, t, fn, title in EXAMPLES:
        chart(day, t, fn, title, st)
        print('wrote', fn)
