"""Shared pieces for the weekly walk-forward review of lib/trading_analysis.py.

Research only. Imports MarketAnalyzer from a clean checkout of the stocks repo
(path in REPO below, override with env TA_REPO) so the indicator math is the
production code, unchanged.
"""
import os, sys, io, contextlib
import numpy as np
import pandas as pd

REPO = os.environ.get('TA_REPO', '/tmp/claude-0/-home-user/e21e199c-cf90-5c22-8afa-93bf6f11a73f/scratchpad/ta2_wt')
if REPO not in sys.path:
    sys.path.insert(0, REPO)
from lib.trading_analysis import MarketAnalyzer  # noqa: E402

BARS_DIR = '/mnt/project-files/stocks-scorecard/inputs/bars_raw'
DAILY_DIR = '/mnt/project-files/strat-verify/ftfc-replay/raw'
ROOT = '/mnt/project-files/stocks-scorecard/research/trading_analysis'
WORK = f'{ROOT}/work'
TICKERS = ['SPY', 'QQQ', 'IWM']

RTH_OPEN, RTH_CLOSE = 570, 960          # 09:30, 16:00 (minute of day)
EXIT_MIN, LAST_ENTRY_MIN = 955, 950     # flat by the 15:55 bar open; last entry 15:50
HOLD = 20                               # exit A: hold 20 bars (the script's default window)
STOP_ATR, TGT_ATR = 0.5, 1.0            # exit B: session bracket in daily ATR


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def load_bars(ticker):
    frames = [pd.read_csv(os.path.join(BARS_DIR, f)) for f in sorted(os.listdir(BARS_DIR))
              if f.startswith(f'{ticker}_1min_') and f.endswith('.csv')]
    df = pd.concat(frames, ignore_index=True)
    df['Time'] = pd.to_datetime(df['timestamp'])
    df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Last', 'volume': 'Volume'})
    df = df[['Time', 'Open', 'High', 'Low', 'Last', 'Volume']]
    return df.drop_duplicates('Time').sort_values('Time').reset_index(drop=True)


def daily_context(ticker, rth):
    """Daily bars: AV daily file before the intraday history, RTH-built after.
    Returns per-date ATR14 (Wilder) and regime known BEFORE that date's open."""
    D0 = pd.read_csv(f'{DAILY_DIR}/{ticker}_daily_adjusted.csv', parse_dates=['timestamp'])
    D0 = D0.sort_values('timestamp').rename(columns={'timestamp': 'Date', 'open': 'O', 'high': 'H', 'low': 'L', 'close': 'C'})
    g = rth.groupby(rth['Time'].dt.normalize())
    D1 = pd.DataFrame({'O': g['Open'].first(), 'H': g['High'].max(), 'L': g['Low'].min(), 'C': g['Last'].last()})
    D1.index.name = 'Date'
    D0 = D0[D0['Date'] < D1.index.min()].set_index('Date')[['O', 'H', 'L', 'C']]
    D = pd.concat([D0, D1]).sort_index()
    ma = MarketAnalyzer()
    D['ATR'] = ma.wilder_moving_average(ma.calculate_true_range(D['H'], D['L'], D['C'].shift(1)), 14)
    D['SMA50'] = D['C'].rolling(50).mean()
    out = pd.DataFrame(index=D.index)
    out['ATR_D'] = D['ATR'].shift(1)
    out['REGIME'] = np.where(D['C'].shift(1) > D['SMA50'].shift(1), 'up', 'down')
    out['GAP'] = (D['O'] - D['C'].shift(1)) / out['ATR_D']
    out['PDH'] = D['H'].shift(1); out['PDL'] = D['L'].shift(1)
    dn = (D['C'] < D['C'].shift(1)).astype(int); up = (D['C'] > D['C'].shift(1)).astype(int)
    out['DOWN_DAYS'] = (dn.groupby((dn != dn.shift()).cumsum()).cumsum() * dn).shift(1)
    out['UP_DAYS'] = (up.groupby((up != up.shift()).cumsum()).cumsum() * up).shift(1)
    return out


def add_common(df):
    df['Price_Change'] = df['Last'].pct_change() * 100
    df['Consecutive_Up'] = (df['Price_Change'] > 0).rolling(3).sum()
    df['Consecutive_Down'] = (df['Price_Change'] < 0).rolling(3).sum()
    df['mod'] = df['Time'].dt.hour * 60 + df['Time'].dt.minute
    df['Date'] = df['Time'].dt.normalize()
    df['Week'] = df['Time'].dt.to_period('W-SUN').dt.start_time
    return df


def build_rth(bars, ticker):
    t = bars['Time']; mod = t.dt.hour * 60 + t.dt.minute
    rth = bars[(mod >= RTH_OPEN) & (mod < RTH_CLOSE)].reset_index(drop=True)
    d = quiet(MarketAnalyzer().add_technical_indicators, rth.copy())
    d = add_common(d)
    ctx = daily_context(ticker, rth)
    for c in ctx.columns:
        d[c] = d['Date'].map(ctx[c])
    orr = d[d['mod'] < 585].groupby('Date').agg(H=('High', 'max'), L=('Low', 'min'))   # 09:30..09:44 only
    d['OR15_H'] = d['Date'].map(orr['H']); d['OR15_L'] = d['Date'].map(orr['L'])
    v5 = d.groupby('Date')['Volume'].transform(lambda s: s.rolling(5).sum())
    piv = pd.DataFrame({'Date': d['Date'], 'mod': d['mod'], 'v5': v5}).pivot_table(index='Date', columns='mod', values='v5')
    base = piv.rolling(20, min_periods=10).mean().shift(1)     # prior 20 sessions only
    bl = base.stack().rename('base').reset_index()
    d = d.merge(bl, on=['Date', 'mod'], how='left')
    d['RELVOL'] = v5.values / d['base']
    d['R15'] = d.groupby('Date')['Last'].transform(lambda s: s / s.shift(15) - 1)
    d['R60'] = d.groupby('Date')['Last'].transform(lambda s: s / s.shift(60) - 1)
    return d


def build_ext(bars):
    """Exactly how the script runs: extended-hours bars, original indicators."""
    e = quiet(MarketAnalyzer().add_technical_indicators, bars.copy())
    return add_common(e)


def conditions(d, cand_from=None):
    """Return dict name -> (bool ndarray, direction). The 7+7 voter conditions use the
    script's own thresholds; the GRID rows vary those thresholds; CAND rows are simple
    context conditions (computed on the RTH frame and mapped by timestamp when
    cand_from is given)."""
    last, rsi, sk = d['Last'], d['RSI14_W'], d['StochRSI_K']
    vw, e9 = d['VWAP'], d['EMA9']
    rv, ax, thr = d['RVol_Recent_20'], d['ATR_Expansion'], d['RSI_Thrust_3']
    valid = (rsi.notna() & sk.notna()).values
    C = {
        'MOM call consecutive_up': (d['Consecutive_Up'] >= 3, 1),
        'MOM call rsi_25_50': ((rsi < 50) & (rsi > 25), 1),
        'MOM call above_vwap': (last > vw, 1),
        'MOM call above_ema9': (last > e9, 1),
        'MOM call rvol>1.2': (rv > 1.2, 1),
        'MOM call atr_exp>1.15': (ax > 1.15, 1),
        'MOM call rsi_thrust>5': (thr > 5, 1),
        'MOM put consecutive_down': (d['Consecutive_Down'] >= 3, -1),
        'MOM put rsi_50_75': ((rsi > 50) & (rsi < 75), -1),
        'MOM put below_vwap': (last < vw, -1),
        'MOM put below_ema9': (last < e9, -1),
        'MOM put rvol>1.2': (rv > 1.2, -1),
        'MOM put atr_exp>1.15': (ax > 1.15, -1),
        'MOM put rsi_thrust<-5': (thr < -5, -1),
    }
    cc = sum(C[k][0].astype(int) for k in C if k.startswith('MOM call'))
    pc = sum(C[k][0].astype(int) for k in C if k.startswith('MOM put'))
    ccore = sum(C[k][0].astype(int) for k in list(C)[:4])
    pcore = sum(C[k][0].astype(int) for k in list(C)[7:11])
    ce, pe = (cc >= 5) & (ccore >= 2), (pc >= 5) & (pcore >= 2)
    C['VOTER call (as written)'] = (ce & (~pe | (cc > pc)), 1)
    C['VOTER put (as written)'] = (pe & (~ce | (pc > cc)), -1)
    for t in (3, 8):
        C[f'GRID call rsi_thrust>{t}'] = (thr > t, 1); C[f'GRID put rsi_thrust<-{t}'] = (thr < -t, -1)
    for t in (1.5, 2.0):
        C[f'GRID call rvol>{t}'] = (rv > t, 1); C[f'GRID put rvol>{t}'] = (rv > t, -1)
    for t in (1.0, 1.3):
        C[f'GRID call atr_exp>{t}'] = (ax > t, 1); C[f'GRID put atr_exp>{t}'] = (ax > t, -1)
    for t in (30, 40):
        C[f'GRID call rsi<{t}'] = (rsi < t, 1); C[f'GRID put rsi<{t}'] = (rsi < t, -1)
    for t in (60, 70):
        C[f'GRID call rsi>{t}'] = (rsi > t, 1); C[f'GRID put rsi>{t}'] = (rsi > t, -1)
    C['GRID call stochK<20'] = (sk < 20, 1); C['GRID put stochK<20'] = (sk < 20, -1)
    C['GRID call stochK>80'] = (sk > 80, 1); C['GRID put stochK>80'] = (sk > 80, -1)
    C['GRID call below_vwap'] = (last < vw, 1); C['GRID put above_vwap'] = (last > vw, -1)
    out = {k: (np.asarray(s.fillna(False) if hasattr(s, 'fillna') else s, bool) & valid, dr) for k, (s, dr) in C.items()}
    cand = cand_conditions(cand_from if cand_from is not None else d)
    if cand_from is not None:   # map RTH flags onto this frame by timestamp
        pos = pd.Series(np.arange(len(d)), index=d['Time'].values)
        for k, (s, dr) in cand.items():
            f = np.zeros(len(d), bool)
            f[pos.reindex(cand_from['Time'].values[s]).dropna().astype(int).values] = True
            out[k] = (f, dr)
    else:
        out.update(cand)
    return out


def cand_conditions(d):
    last, atr, mod = d['Last'], d['ATR_D'], d['mod']
    orh, orl = d['OR15_H'], d['OR15_L']; post = mod >= 586
    cand = {
        'OR15 above high': post & (last > orh), 'OR15 below low': post & (last < orl),
        'PDH above': last > d['PDH'], 'PDL below': last < d['PDL'],
        'PDH within 0.25 ATR below': ((d['PDH'] - last) / atr).between(0, 0.25),
        'PDL within 0.25 ATR above': ((last - d['PDL']) / atr).between(0, 0.25),
        'gap up > 0.3 ATR (before 10:30)': (d['GAP'] > 0.3) & (mod < 630),
        'gap down > 0.3 ATR (before 10:30)': (d['GAP'] < -0.3) & (mod < 630),
        'time 09:30 to 10:00': mod < 600, 'time 10:00 to 11:30': (mod >= 600) & (mod < 690),
        'time 11:30 to 14:00': (mod >= 690) & (mod < 840), 'time 14:00 to 15:50': mod >= 840,
        'relvol5 tod > 1.5': d['RELVOL'] > 1.5, 'relvol5 tod < 0.7': d['RELVOL'] < 0.7,
        'trend 15m and 60m up': (d['R15'] > 0) & (d['R60'] > 0),
        'trend 15m and 60m down': (d['R15'] < 0) & (d['R60'] < 0),
        '3+ down days': d['DOWN_DAYS'] >= 3, '3+ up days': d['UP_DAYS'] >= 3,
        'all bars (baseline)': pd.Series(True, index=d.index),
    }
    out = {}
    for k, s in cand.items():
        s = np.asarray(s.fillna(False), bool)
        out[f'CAND {k} | long'] = (s, 1); out[f'CAND {k} | short'] = (s, -1)
    return out


def outcomes_hold(d):
    """Exit A. Signal at bar t, entry at open[t+1], exit at open[t+1+HOLD] or the 15:55
    open, same session. Returns long bps, short bps, exit index (all per signal bar)."""
    n = len(d); L = np.full(n, np.nan); X = np.full(n, -1, np.int64)
    O = d['Open'].values; mod = d['mod'].values
    for _, idx in d.groupby('Date').indices.items():
        idx = np.sort(idx); m = mod[idx]
        ex = np.where(m >= EXIT_MIN)[0]
        if not len(ex):
            continue
        cap = ex[0]
        ent = np.arange(1, cap)
        ent = ent[m[ent] <= LAST_ENTRY_MIN]
        if not len(ent):
            continue
        xp = np.minimum(ent + HOLD, cap)
        r = (O[idx[xp]] - O[idx[ent]]) / O[idx[ent]] * 1e4
        L[idx[ent - 1]] = r; X[idx[ent - 1]] = idx[xp]
    return L, -L, X, X.copy()


def outcomes_bracket(d):
    """Exit B (earlier review's exit). Entry open[t+1]; stop 0.5 x prior-day ATR, target
    1.0 x ATR, else the 15:55 open; stop wins ties. In R (1R = 0.5 ATR)."""
    n = len(d)
    Rl = np.full(n, np.nan); Rs = np.full(n, np.nan)
    Xl = np.full(n, -1, np.int64); Xs = np.full(n, -1, np.int64)
    O, H, Lo = (d[c].values for c in ['Open', 'High', 'Low'])
    mod = d['mod'].values; atr = d['ATR_D'].values
    for _, idx in d.groupby('Date').indices.items():
        idx = np.sort(idx); m = mod[idx]
        ex = np.where(m >= EXIT_MIN)[0]
        if not len(ex) or np.isnan(atr[idx[0]]):
            continue
        exit_pos = ex[0]; exit_px = O[idx[exit_pos]]; last_bar = exit_pos - 1
        hh, ll = H[idx[:last_bar + 1]], Lo[idx[:last_bar + 1]]
        a = atr[idx[0]]; stop, tgt = STOP_ATR * a, TGT_ATR * a
        ent = np.arange(1, last_bar + 1); ent = ent[m[ent] <= LAST_ENTRY_MIN]
        if not len(ent):
            continue
        ep = O[idx[ent]]; J = np.arange(last_bar + 1); mask = J[None, :] >= ent[:, None]; big = last_bar + 10
        for sign, R, X in [(1, Rl, Xl), (-1, Rs, Xs)]:
            if sign == 1:
                hs = mask & (ll[None, :] <= (ep - stop)[:, None]); ht = mask & (hh[None, :] >= (ep + tgt)[:, None])
            else:
                hs = mask & (hh[None, :] >= (ep + stop)[:, None]); ht = mask & (ll[None, :] <= (ep - tgt)[:, None])
            fs = np.where(hs.any(1), hs.argmax(1), big); ft = np.where(ht.any(1), ht.argmax(1), big)
            r = sign * (exit_px - ep) / stop; xpos = np.full(len(ent), exit_pos)
            tw = (ft < fs) & (ft < big); sw = (fs <= ft) & (fs < big)
            r = np.where(tw, TGT_ATR / STOP_ATR, r); xpos = np.where(tw, ft, xpos)
            r = np.where(sw, -1.0, r); xpos = np.where(sw, fs, xpos)
            R[idx[ent - 1]] = r; X[idx[ent - 1]] = idx[np.minimum(xpos, len(idx) - 1)]
    return Rl, Rs, Xl, Xs


def non_overlap(fire_idx, exit_idx):
    """One position at a time: the next signal must come after the previous exit bar."""
    out = []; j = 0
    while j < len(fire_idx):
        i = fire_idx[j]; out.append(i)
        j = np.searchsorted(fire_idx, exit_idx[i], side='right')
    return np.array(out, dtype=np.int64)
