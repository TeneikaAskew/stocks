"""Shared helpers for the example_days lane: bars, candle building, trade rule."""
import glob, os
import numpy as np
import pandas as pd

LANE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = '/mnt/project-files/stocks-scorecard/inputs/bars_raw'
AGG = dict(open='first', high='max', low='min', close='last', volume='sum')
T = ('SPY', 'QQQ', 'IWM')

def clean(b):
    """Clip bad extended-hours prints (regular hours 09:30-15:59 untouched).
    Step 1: an isolated open or close (more than 0.5% from the 11-minute median close and more than 0.3% from
    both neighbouring closes) is replaced by that median.
    Step 2: a wick more than 0.15% beyond the highest/lowest bar body of the surrounding 11 minutes is cut
    back to the bar's own body."""
    b = b.copy()
    m = b.index.hour * 60 + b.index.minute; eth = (m < 570) | (m >= 960)
    med = b.close.rolling(11, center=True, min_periods=1).median()
    pc, nc = b.close.shift(1), b.close.shift(-1)
    for c in ('open', 'close'):   # isolated only: a real jump (news at 16:00) is followed by prices that stay there
        bad = ((b[c] - med).abs() > 0.005 * med) & ((b[c] - pc).abs() > 0.003 * med) & ((b[c] - nc).abs() > 0.003 * med) & eth
        b.loc[bad, c] = med[bad]
    bh = b[['open', 'close']].max(axis=1); bl = b[['open', 'close']].min(axis=1)
    rh = bh.rolling(11, center=True, min_periods=1).max(); rl = bl.rolling(11, center=True, min_periods=1).min()
    tol = 0.0015 * b.close
    badh = (b.high > rh + tol) & eth; badl = (b.low < rl - tol) & eth
    b.loc[badh, 'high'] = bh[badh]; b.loc[badl, 'low'] = bl[badl]
    b.loc[eth, 'high'] = b.loc[eth, ['high', 'open', 'close']].max(axis=1); b.loc[eth, 'low'] = b.loc[eth, ['low', 'open', 'close']].min(axis=1)
    return b

_bars = {}
def bars(t):
    if t not in _bars:
        raw = (pd.concat([pd.read_csv(f, parse_dates=['timestamp']) for f in sorted(glob.glob(f'{B}/{t}_1min_*.csv'))])
               .drop_duplicates('timestamp').set_index('timestamp').sort_index())
        _bars[t] = clean(raw)
    return _bars[t]

def rth(t, day):
    return bars(t).loc[f'{day} 09:30':f'{day} 15:59']

_daily = None
def daily(t):
    """Official daily bars (Alpha Vantage daily, the repo's committed fixture, through 2026-11-09),
    plus 2026-11-10 built from the 1-min regular session."""
    global _daily
    if _daily is None:
        _daily = pd.read_csv(f'{LANE}/inputs/daily_official.csv', parse_dates=['date'])
    d = _daily[_daily.ticker == t].set_index('date').drop(columns='ticker').sort_index()
    r = bars(t).between_time('09:30', '15:59')
    x = r.groupby(r.index.normalize()).agg(AGG)
    extra = x[x.index > d.index[-1]]
    return pd.concat([d, extra])

def atr14(d):
    pc = d.close.shift(1)
    tr = pd.concat([d.high - d.low, (d.high - pc).abs(), (d.low - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(14).mean().shift(1)  # known before the session

def h12(b):
    """12 hour candles as TradingView draws them on an extended-hours chart: 04:00-15:59 and 16:00-19:59 ET."""
    lab = b.index.normalize() + pd.to_timedelta((b.index.hour >= 16) * 12 + 4, unit='h')
    return b.groupby(lab).agg(AGG)

def trade(bars, side, entry, stop, t1):
    """Same rule the brief is scored with (stocks-scorecard/week_summary.trade): fill at the trigger, or at the
    bar open if already through; exit at stop, first target, or the last close; stop wins a same-bar tie.
    Extra fields: fill time, exit time, worst move against (points) while in the trade."""
    if entry is None or stop is None or pd.isna(entry) or pd.isna(stop):
        return None
    up = side == 'long'
    hi, lo, op, cl, ts = bars.high.values, bars.low.values, bars.open.values, bars.close.values, bars.index
    idx = np.where(hi >= entry)[0] if up else np.where(lo <= entry)[0]
    if len(idx) == 0:
        return {'fill': False}
    i0 = idx[0]; px = max(entry, op[i0]) if up else min(entry, op[i0])
    risk = abs(px - stop)
    out = {'fill': True, 'fill_t': ts[i0], 'px': float(px), 'thru_open': bool(i0 == 0 and ((op[0] > entry) if up else (op[0] < entry)))}
    if risk <= 0 or (up and stop >= px) or ((not up) and stop <= px):
        out.update(R=None, how='no risk'); return out
    mae = 0.0
    for i in range(i0, len(hi)):
        mae = max(mae, (px - lo[i]) if up else (hi[i] - px))
        s_hit = (lo[i] <= stop) if up else (hi[i] >= stop)
        t_hit = t1 is not None and not pd.isna(t1) and ((hi[i] >= t1) if up else (lo[i] <= t1))
        if s_hit:
            ex = min(stop, op[i]) if up else max(stop, op[i])
            out.update(R=round(((ex - px) if up else (px - ex)) / risk, 2), how='stop', exit_t=ts[i], mae=round(min(mae, risk), 2)); return out
        if t_hit:
            out.update(R=round(abs(t1 - px) / risk, 2), how='T1', exit_t=ts[i], mae=round(mae, 2)); return out
    c = cl[-1]
    out.update(R=round(((c - px) if up else (px - c)) / risk, 2), how='close', exit_t=ts[-1], mae=round(mae, 2)); return out

def boot_ci(df, col, n=2000, seed=7):
    """90% bootstrap range of the mean of `col`, resampling whole days."""
    g = df.groupby('day')[col].agg(['sum', 'count'])
    if len(g) < 5:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    s, c = g['sum'].values, g['count'].values
    ix = rng.integers(0, len(g), (n, len(g)))
    m = s[ix].sum(1) / np.maximum(c[ix].sum(1), 1)
    return (round(float(np.quantile(m, .05)), 3), round(float(np.quantile(m, .95)), 3))
