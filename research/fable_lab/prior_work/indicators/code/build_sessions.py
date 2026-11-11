"""Build, per ticker: session labels (moves in ATR units), pre-open features and minute-by-minute indicator states.
  python3 -I code/build_sessions.py           (all three tickers, about 1 min)
Writes work/sessions.parquet  one row per ticker session
       work/states.npz        int8 [session, indicator, minute] : +1 up, -1 down, 0 off (minute 0 = bar stamped 09:30)
       work/minute.npz        float arrays [session, minute] open/high/low/close/vwap on the 09:30..11:29 grid
Every value at minute i uses only bars stamped <= i (known at the close of that bar).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

NB = 120                       # minutes kept per session: 09:30 .. 11:29
HS = [15, 30, 60]; KS = [0.15, 0.25, 0.35, 0.5]
HOLD_BARS, GIVEBACK = 5, 0.2   # held 5 minutes, giving back no more than a fifth of the threshold

INTRA = ['orb5', 'orb15', 'first5', 'vwap_side', 'vwap_slope', 'rvol_dir', 'rsi1', 'rsi5', 'ema1', 'ema5', 'macd1', 'macd5',
         'pmh_break_0830', 'pmh_break_0929', 'pdh_break', 'strat5', 'ftfc_intra', 'ftfc_full', 'voter', 'half_way']


def label_moves(O, C, Lo, Hi, atr):
    """O open at 09:30; C/Lo/Hi arrays on the minute grid. Returns dict of labels for every (H, k)."""
    out = {}
    for k in KS:
        thr = k * atr
        up = C - O >= thr; dn = O - C >= thr
        # hold: the next HOLD_BARS closes stay within GIVEBACK of the threshold
        fmin = pd.Series(C[::-1]).rolling(HOLD_BARS, min_periods=HOLD_BARS).min().values[::-1]
        fmax = pd.Series(C[::-1]).rolling(HOLD_BARS, min_periods=HOLD_BARS).max().values[::-1]
        fmin = np.roll(fmin, -1); fmax = np.roll(fmax, -1); fmin[-1] = np.nan; fmax[-1] = np.nan   # closes i+1..i+5
        upc = up & (fmin - O >= (1 - GIVEBACK) * thr)
        dnc = dn & (O - fmax >= (1 - GIVEBACK) * thr)
        for H in HS:
            iu = np.argmax(upc[:H]) if upc[:H].any() else 10 ** 6
            idn = np.argmax(dnc[:H]) if dnc[:H].any() else 10 ** 6
            if iu == idn == 10 ** 6:
                lab, r, s = 0, -1, -1
            elif iu < idn:
                lab, r = 1, iu; s = int(np.argmin(Lo[:r + 1]))
            else:
                lab, r = -1, idn; s = int(np.argmax(Hi[:r + 1]))
            out[f'lab_{H}_{k}'] = lab; out[f'reach_{H}_{k}'] = r; out[f'start_{H}_{k}'] = s
    return out


def build(T):
    bars, nfiles = load_bars(T)
    D = daily_bars(T, bars)
    tr = pd.concat([D['H'] - D['L'], (D['H'] - D['C'].shift()).abs(), (D['L'] - D['C'].shift()).abs()], axis=1).max(axis=1)
    D['ATR'] = wilder(tr, 14)
    D['e9'] = ema(D['C'], 9); D['e21'] = ema(D['C'], 21); D['mh'] = macd_hist(D['C']); D['rsi'] = rsi(D['C'])
    wk = D.index.to_period('W-SUN'); mo = D.index.to_period('M')
    D['wopen'] = D.groupby(wk)['O'].transform('first'); D['mopen'] = D.groupby(mo)['O'].transform('first')
    D['first_of_week'] = ~pd.Series(wk, index=D.index).duplicated(); D['first_of_month'] = ~pd.Series(mo, index=D.index).duplicated()
    V = pd.read_csv(f'{ROOT}/inputs/VIX_daily.csv', parse_dates=['date']).dropna().sort_values('date').set_index('date')
    V['sma10'] = V['close'].rolling(10).mean(); V['sma20'] = V['close'].rolling(20).mean(); V['chg'] = V['close'].pct_change()

    b = bars.set_index('Time')
    c = b['Last']
    m1 = pd.DataFrame({'e9': ema(c, 9), 'e21': ema(c, 21), 'rsi': rsi(c), 'mh': macd_hist(c)})
    m1['rsi_sl'] = m1['rsi'] - m1['rsi'].shift(3); m1['mh_prev'] = m1['mh'].shift(1)
    f = b.resample('5min', label='left', closed='left').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Last': 'last', 'Volume': 'sum'}).dropna()
    m5 = pd.DataFrame({'e9': ema(f['Last'], 9), 'e21': ema(f['Last'], 21), 'rsi': rsi(f['Last']), 'mh': macd_hist(f['Last'])})
    m5['rsi_prev'] = m5['rsi'].shift(1); m5['mh_prev'] = m5['mh'].shift(1)
    m5.index = m5.index + pd.Timedelta(minutes=4)            # known at the close of the 1-min bar stamped label+4
    # 60-min bars on the 09:30 grid, regular hours, for the prior-close hourly EMA stack
    mod = b.index.hour * 60 + b.index.minute
    r = b[(mod >= 570) & (mod < 960)]
    h = r['Last'].resample('60min', offset='30min').last().dropna()
    hs = pd.DataFrame({'c': h, 'e9': ema(h, 9), 'e21': ema(h, 21)})
    hs['st'] = np.where((hs.c > hs.e9) & (hs.e9 > hs.e21), 1, np.where((hs.c < hs.e9) & (hs.e9 < hs.e21), -1, 0))
    h_last = hs['st'].groupby(hs.index.normalize()).last()

    try:
        vs = pd.read_parquet(f'{WORK}/{T}_voter_signals.parquet')
        vmap = pd.Series(np.where(vs['trade_type'] == 'call', 1, -1), index=pd.to_datetime(vs['entry_time']))
    except Exception as ex:
        print('no voter file', ex); vmap = pd.Series(dtype=float)

    days = [d for d in D.index if d >= pd.Timestamp('2025-03-03')]
    rows, S, MN = [], [], []
    cumvol_hist, pmvol_hist, pmrng_hist = [], [], []
    for d in days:
        i = D.index.get_loc(d)
        if i < 30: continue
        p = D.iloc[i - 1]; atr = p['ATR']
        day = b.loc[d: d + pd.Timedelta(hours=23, minutes=59)]
        grid = pd.date_range(d + pd.Timedelta(minutes=570), periods=NB, freq='1min')
        g = day.reindex(grid)
        nmiss = int(g['Last'].isna().sum())
        if g['Last'].iloc[:60].isna().sum() > 5 or pd.isna(g['Open'].iloc[0]): continue
        g['Last'] = g['Last'].ffill()
        for col in ['Open', 'High', 'Low']: g[col] = g[col].fillna(g['Last'])
        g['Volume'] = g['Volume'].fillna(0)
        O = g['Open'].iloc[0]; C = g['Last'].values; Hi = g['High'].values; Lo = g['Low'].values; Op = g['Open'].values
        pm = day.loc[: d + pd.Timedelta(minutes=569)]
        pm830 = pm.loc[: d + pd.Timedelta(minutes=509)]
        if len(pm) < 5 or len(pm830) < 3: continue
        row = dict(ticker=T, date=d, atr=atr, open=O, pdc=p['C'], pdh=p['H'], pdl=p['L'], nmiss=nmiss)
        row.update(label_moves(O, C, Lo, Hi, atr))
        # ---------- pre-open features (known by 09:29) ----------
        last = pm['Last'].iloc[-1]; last830 = pm830['Last'].iloc[-1]
        pmh, pml = pm['High'].max(), pm['Low'].min(); pmh8, pml8 = pm830['High'].max(), pm830['Low'].min()
        tp = (pm['High'] + pm['Low'] + pm['Last']) / 3
        pmv = (tp * pm['Volume']).sum() / max(pm['Volume'].sum(), 1)
        tp8 = (pm830['High'] + pm830['Low'] + pm830['Last']) / 3
        pmv8 = (tp8 * pm830['Volume']).sum() / max(pm830['Volume'].sum(), 1)
        pmvol = pm['Volume'].sum(); pmr = (pmh - pml) / atr
        pp = D.iloc[i - 2]
        row.update(
            gap_open=(O - p['C']) / atr, gap_pm=(last - p['C']) / atr, gap_0830=(last830 - p['C']) / atr,
            pm_vwap_d=(last - pmv) / atr, pm_vwap_d_0830=(last830 - pmv8) / atr, pm_late=(last - last830) / atr,
            pm_pos=(last - pml) / max(pmh - pml, 1e-9), pm_range=pmr,
            pm_rvol=pmvol / np.mean(pmvol_hist[-20:]) if len(pmvol_hist) >= 20 else np.nan,
            pm_range_rank=np.mean(np.array(pmrng_hist[-60:]) < pmr) if len(pmrng_hist) >= 20 else np.nan,
            pmh=pmh, pml=pml, pmh0830=pmh8, pml0830=pml8,
            pd_closeloc=(p['C'] - p['L']) / max(p['H'] - p['L'], 1e-9), pd_ret=(p['C'] - p['O']) / D['ATR'].iloc[i - 2],
            pd_strat=(2 if (p['H'] > pp['H'] and p['L'] >= pp['L']) else -2 if (p['L'] < pp['L'] and p['H'] <= pp['H'])
                      else 1 if (p['H'] <= pp['H'] and p['L'] >= pp['L']) else 3),
            d_ema=1 if p['C'] > p['e9'] > p['e21'] else -1 if p['C'] < p['e9'] < p['e21'] else 0,
            d_macd=1 if (p['mh'] > 0 and p['mh'] > pp['mh']) else -1 if (p['mh'] < 0 and p['mh'] < pp['mh']) else 0,
            d_rsi=p['rsi'],
            h_ema=int(h_last.get(D.index[i - 1], 0)),
        )
        # higher timeframe continuity before the open: premarket last vs week open, month open, prior close
        refs = [p['C']]
        if not D['first_of_week'].iloc[i]: refs.append(D['wopen'].iloc[i])
        if not D['first_of_month'].iloc[i]: refs.append(D['mopen'].iloc[i])
        row['ftfc_htf'] = 1 if all(last > x for x in refs) else -1 if all(last < x for x in refs) else 0
        row['n_htf_refs'] = len(refs)
        vprev = V.loc[:d - pd.Timedelta(days=1)].iloc[-1]
        row.update(vix=vprev['close'], vix_chg=vprev['chg'], vix_vs10=vprev['close'] / vprev['sma10'] - 1, vix_vs20=vprev['close'] / vprev['sma20'] - 1)
        # ---------- in-session states ----------
        st = np.zeros((len(INTRA), NB), np.int8)
        def put(name, upb, dnb):
            st[INTRA.index(name)] = np.where(upb, 1, np.where(dnb, -1, 0))
        idx = np.arange(NB)
        h5, l5 = Hi[:5].max(), Lo[:5].min(); h15, l15 = Hi[:15].max(), Lo[:15].min()
        put('orb5', (idx >= 5) & (C > h5), (idx >= 5) & (C < l5))
        put('orb15', (idx >= 15) & (C > h15), (idx >= 15) & (C < l15))
        r5 = (C[4] - O) / atr
        put('first5', (idx >= 4) & (r5 >= 0.1), (idx >= 4) & (r5 <= -0.1))
        tpx = (Hi + Lo + C) / 3; cv = np.cumsum(g['Volume'].values); vwap = np.cumsum(tpx * g['Volume'].values) / np.maximum(cv, 1)
        ab = pd.Series(C > vwap).rolling(3).sum().values == 3; be = pd.Series(C < vwap).rolling(3).sum().values == 3
        put('vwap_side', ab, be)
        vsl = vwap - np.roll(vwap, 3); vsl[:3] = 0
        put('vwap_slope', ab & (vsl > 0), be & (vsl < 0))
        if len(cumvol_hist) >= 20:
            hist = np.array(cumvol_hist[-60:]); rv = cv / hist[-20:].mean(axis=0)
            hist_rv = hist / np.array([np.array(cumvol_hist[max(0, j - 20):j]).mean(axis=0) if j >= 20 else np.full(NB, np.nan)
                                       for j in range(len(cumvol_hist) - len(hist), len(cumvol_hist))])
            q80 = np.nanquantile(hist_rv, 0.8, axis=0) if np.isfinite(hist_rv).any() else np.full(NB, np.inf)
            hot = rv >= q80
            row['rvol5'] = rv[4]; row['rvol15'] = rv[14]
        else:
            hot = np.zeros(NB, bool); row['rvol5'] = np.nan; row['rvol15'] = np.nan
        put('rvol_dir', hot & (C > O), hot & (C < O))
        a1 = m1.reindex(grid).ffill()
        put('rsi1', (a1.rsi > 60) & (a1.rsi_sl > 0), (a1.rsi < 40) & (a1.rsi_sl < 0))
        put('ema1', (C > a1.e9) & (a1.e9 > a1.e21), (C < a1.e9) & (a1.e9 < a1.e21))
        put('macd1', (a1.mh > 0) & (a1.mh > a1.mh_prev), (a1.mh < 0) & (a1.mh < a1.mh_prev))
        a5 = m5.reindex(m5.index.union(grid)).ffill().reindex(grid)
        put('rsi5', (a5.rsi > 55) & (a5.rsi > a5.rsi_prev), (a5.rsi < 45) & (a5.rsi < a5.rsi_prev))
        put('ema5', (C > a5.e9) & (a5.e9 > a5.e21), (C < a5.e9) & (a5.e9 < a5.e21))
        put('macd5', (a5.mh > 0) & (a5.mh > a5.mh_prev), (a5.mh < 0) & (a5.mh < a5.mh_prev))
        put('pmh_break_0830', C > pmh8, C < pml8)
        put('pmh_break_0929', C > pmh, C < pml)
        put('pdh_break', C > p['H'], C < p['L'])
        # 5-min Strat: last completed regular-hours 5-min bar vs the one before it
        H5 = Hi.reshape(-1, 5).max(1); L5 = Lo.reshape(-1, 5).min(1); O5 = Op.reshape(-1, 5)[:, 0]; C5 = C.reshape(-1, 5)[:, -1]
        s5u = np.zeros(NB, bool); s5d = np.zeros(NB, bool)
        for j in range(1, NB // 5):
            u = H5[j] > H5[j - 1] and L5[j] >= L5[j - 1] and C5[j] > O5[j]
            dd = L5[j] < L5[j - 1] and H5[j] <= H5[j - 1] and C5[j] < O5[j]
            a, z = j * 5 + 4, min(j * 5 + 9, NB)
            s5u[a:z] = u; s5d[a:z] = dd
        put('strat5', s5u, s5d)
        o5 = np.repeat(O5, 5); o15 = np.repeat(Op.reshape(-1, 15)[:, 0], 15); o60 = np.repeat(Op.reshape(-1, 60)[:, 0], 60)
        iu = (C > o5) & (C > o15) & (C > o60) & (C > O); idn = (C < o5) & (C < o15) & (C < o60) & (C < O)
        put('ftfc_intra', iu, idn)
        wo, mo_ = D['wopen'].iloc[i], D['mopen'].iloc[i]
        put('ftfc_full', iu & (C > wo) & (C > mo_), idn & (C < wo) & (C < mo_))
        vv = vmap.reindex(grid).fillna(0).values if len(vmap) else np.zeros(NB)
        put('voter', vv > 0, vv < 0)
        put('half_way', (C - O) >= 0.25 * atr, (O - C) >= 0.25 * atr)
        # ---------- features at 09:35 and 09:45 for the models ----------
        for n in (5, 15):
            hh, ll = Hi[:n].max(), Lo[:n].min()
            row[f'ret{n}'] = (C[n - 1] - O) / atr; row[f'rng{n}'] = (hh - ll) / atr
            row[f'loc{n}'] = (C[n - 1] - ll) / max(hh - ll, 1e-9); row[f'vwapd{n}'] = (C[n - 1] - vwap[n - 1]) / atr
            row[f'rsi1_{n}'] = a1.rsi.iloc[n - 1]; row[f'macd1_{n}'] = a1.mh.iloc[n - 1] / atr
        rows.append(row); S.append(st); MN.append(np.stack([Op, Hi, Lo, C, vwap]))
        cumvol_hist.append(cv); pmvol_hist.append(pmvol); pmrng_hist.append(pmr)
    print(T, 'files', nfiles, 'bars', len(bars), 'sessions', len(rows), flush=True)
    return pd.DataFrame(rows), np.stack(S), np.stack(MN)


if __name__ == '__main__':
    A, B, Cm = [], [], []
    for T in TICKERS:
        a, s, m = build(T); A.append(a); B.append(s); Cm.append(m)
    ses = pd.concat(A, ignore_index=True); ses['window'] = window_of(ses['date'])
    ses.to_parquet(f'{WORK}/sessions.parquet', index=False)
    np.savez_compressed(f'{WORK}/states.npz', states=np.concatenate(B), names=np.array(INTRA))
    np.savez_compressed(f'{WORK}/minute.npz', ohlcv=np.concatenate(Cm))
    print(ses.groupby(['ticker', 'window']).size())
    for H in HS:
        print('H', H, ses.groupby('ticker')[f'lab_{H}_0.5'].value_counts(normalize=True).round(3).unstack())
