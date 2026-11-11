"""Build one record per ticker-session: brief fields, every level, premarket features, RTH 1-min arrays.
Reuses the brief's own print filter (lib.indicators.calculate_premarket_context) from a clean checkout.
Usage: python3 -I build_sessions.py <stocks worktree>
Writes work/sessions.pkl and inputs/session_levels.csv."""
import glob, json, os, pickle, sys
from datetime import time as T
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); LANE = os.path.dirname(HERE)
WT = sys.argv[1]
sys.path.insert(0, WT)
from lib.indicators import calculate_premarket_context as pmctx  # the brief's own filter

B = '/mnt/project-files/stocks-scorecard/inputs/bars_raw'
D = '/mnt/project-files/strat-verify/ftfc-replay/raw'
TICKERS = ('SPY', 'QQQ', 'IWM')
CUTS = ('08:30', '09:25')


def load_bars(t):
    b = pd.concat([pd.read_csv(f, parse_dates=['timestamp']) for f in sorted(glob.glob(f'{B}/{t}_1min_*.csv'))])
    return b.drop_duplicates('timestamp').set_index('timestamp').sort_index()


def filt(x, start, end, pc, po, atr):
    """Brief's filtered high/low/vwap for bars x within [start, end) time of day."""
    if len(x) == 0:
        return None
    x = x.reset_index()
    r = pmctx(x['timestamp'], x['open'], x['high'], x['low'], x['close'], x['volume'], prev_close=pc, atr14=atr,
              prev_open=po, premarket_start=start, market_open=end)
    return r if r.get('pre_high') is not None else None


def pm_features(x, atr, pc, po, pdh, pdl):
    """x: premarket 1-min bars up to a cutoff. Returns the brief's filtered extremes plus per-side flags."""
    out = {}
    m = filt(x, T(4, 0), T(9, 30), pc, po, atr)
    if m is None:
        return None
    out['main_h'], out['main_l'], out['vwap'] = m['pre_high'], m['pre_low'], m.get('pre_vwap')
    O, H, L, C, V = (x[k].astype(float).reset_index(drop=True) for k in ('open', 'high', 'low', 'close', 'volume'))
    # the brief's stale prior-close rule (a), applied before every experimental rule, as pm_rules.py did
    pcc = int(round(pc * 100)); away = ((O + C) / 2 - pc).abs() > 0.1 * atr
    o2, h2, l2, c2 = O.copy(), H.copy(), L.copy(), C.copy()
    for s in (o2, h2, l2, c2):
        s[s.map(lambda v: v == v and int(round(v * 100)) == pcc) & away] = np.nan
    bh = pd.concat([o2, c2], axis=1).max(axis=1); bl = pd.concat([o2, c2], axis=1).min(axis=1)
    eh = h2.fillna(bh); el = l2.fillna(bl)
    out['raw_h'], out['raw_l'] = float(eh.max()), float(el.min())
    medv = float(V[V > 0].median()) if (V > 0).any() else 0.0
    p90 = float(V.quantile(0.9))
    tot = float(V.sum())
    # THIN_A: the earlier volume rule (vol:0.5:0.1): drop a wick > 0.1 ATR beyond its body when the bar's volume < 0.5 x median
    thin = V < 0.5 * medv
    dh = ((h2 - bh) > 0.1 * atr) & thin; dl = ((bl - l2) > 0.1 * atr) & thin
    va_h = float(h2.where(~dh).fillna(bh).max()); va_l = float(l2.where(~dl).fillna(bl).min())
    out['thinA_h'] = bool(va_h < out['main_h'] - 1e-9); out['thinA_l'] = bool(va_l > out['main_l'] + 1e-9)
    out['thinA_drop_h'] = min(va_h, out['main_h']); out['thinA_drop_l'] = max(va_l, out['main_l'])
    # share of premarket volume traded within 0.1 ATR of the (brief-filtered) extreme
    near_h = eh >= out['main_h'] - 0.1 * atr; near_l = el <= out['main_l'] + 0.1 * atr
    out['share_h'] = float(V[near_h].sum() / tot) if tot > 0 else np.nan
    out['share_l'] = float(V[near_l].sum() / tot) if tot > 0 else np.nan
    # ISO: iso:0.25:0.1 on the stale-filtered bars: an extreme > 0.25 ATR beyond every other bar and > 0.1 ATR beyond its own body
    for side in ('h', 'l'):
        e = (eh if side == 'h' else el).copy(); drop = pd.Series(False, index=e.index)
        flagged = False; vol_ok = False; rth_ok = False; first = True
        for _ in range(5):
            cur = e.where(~drop)
            i = cur.idxmax() if side == 'h' else cur.idxmin()
            rest = cur.drop(i)
            if len(rest.dropna()) == 0:
                break
            gap = (cur[i] - rest.max()) if side == 'h' else (rest.min() - cur[i])
            wick = (cur[i] - bh[i]) if side == 'h' else (bl[i] - cur[i])
            if gap > 0.25 * atr and wick > 0.1 * atr:
                if first:
                    flagged = True
                    vol_ok = bool(V[i] >= p90 and V[i] > 0)           # heavy-volume bar (top 10% of that morning's minutes)
                    rth_ok = bool(pdl <= cur[i] <= pdh)               # inside yesterday's regular-session range
                    out[f'iso_vol_{side}'] = float(V[i]); out[f'iso_t_{side}'] = str(x.index[i].time())[:5]
                    first = False
                drop[i] = True
            else:
                break
        out[f'iso_{side}'] = flagged; out[f'iso_volok_{side}'] = vol_ok; out[f'iso_rthok_{side}'] = rth_ok
        red = e.where(~drop)
        # reduced extreme: dropped bars fall back to their body, as the brief does
        body = bh if side == 'h' else bl
        red = red.fillna(body)
        out[f'iso_drop_{side}'] = float(red.max() if side == 'h' else red.min())
    # caught by the brief's own ATR spike filter (0.5 ATR)?
    out['main_cut_h'] = bool(out['main_h'] < out['raw_h'] - 1e-9); out['main_cut_l'] = bool(out['main_l'] > out['raw_l'] + 1e-9)
    return out


def main():
    rows = json.load(open(f'{LANE}/inputs/brief_rows.json'))
    by = {}
    for r in rows:
        by.setdefault(r['ticker'], []).append(r)
    sessions = []; flat = []
    for t in TICKERS:
        b = load_bars(t)
        days = sorted(set(b.index.strftime('%Y-%m-%d')))
        prev_of = dict(zip(days[1:], days[:-1]))
        d = pd.read_csv(f'{D}/{t}_daily_adjusted.csv', parse_dates=['timestamp']).sort_values('timestamp').set_index('timestamp')
        bd = {k: g for k, g in b.groupby(b.index.strftime('%Y-%m-%d'))}
        share_hist = {'h': [], 'l': []}
        for r in sorted(by[t], key=lambda r: r['day']):
            day = r['day']; g = bd.get(day)
            if g is None or r['atr'] is None:
                continue
            rth = g.between_time('09:30', '15:59')
            if len(rth) < 300:
                continue
            atr = float(r['atr']); pc = float(r['prior_close']); po = r.get('prev_open')
            lv = {}
            for n, p in r['levels']:
                if n.startswith('GAP_') or p is None:
                    continue
                lv[n] = float(p)
            pdh, pdl = lv.get('PDH', np.inf), lv.get('PDL', -np.inf)
            # 2-day candle: the last two completed regular sessions (1-min RTH bars; daily CSV only before the 1-min history)
            p = prev_of.get(day); pp = prev_of.get(p) if p else None
            two = [bd[q].between_time('09:30', '15:59') for q in (pp, p) if q and q in bd]
            two = [q for q in two if len(q)]
            if len(two) == 2:
                lv['2D_H'] = float(max(q.high.max() for q in two)); lv['2D_L'] = float(min(q.low.min() for q in two))
            else:
                dd = d[d.index < pd.Timestamp(day)].tail(2)
                lv['2D_H'] = float(dd.high.max()); lv['2D_L'] = float(dd.low.min())
            lv['2D_50'] = (lv['2D_H'] + lv['2D_L']) / 2
            # 12-hour candle on a 04:00/16:00 grid: the last completed one at 08:30 is the prior day's 16:00 to 20:00.
            # After-hours bars carry late-reported prints far from the market, sometimes several in a row (the brief's
            # neighbour-based filter keeps those). Any open/high/low/close further than 0.25 x ATR from the 15-minute
            # centred median close is ignored.
            pg = bd.get(p) if p else None
            if pg is not None:
                ah = pg.between_time('16:00', '19:59')
                if len(ah) >= 30:
                    med = ah.close.rolling(15, center=True, min_periods=5).median()
                    vals = pd.concat([ah[k].where((ah[k] - med).abs() <= 0.25 * atr) for k in ('open', 'high', 'low', 'close')], axis=1)
                    if vals.notna().any().any():
                        lv['12N_H'], lv['12N_L'] = float(vals.max().max()), float(vals.min().min())
                        lv['12N_50'] = (lv['12N_H'] + lv['12N_L']) / 2
            for k in (0.5, 1.0):
                lv[f'ATR{k}_U'] = pc + k * atr; lv[f'ATR{k}_D'] = pc - k * atr
            pm = {}
            for cut in CUTS:
                x = g.between_time('04:00', cut, inclusive='left')
                pm[cut] = pm_features(x, atr, pc, po, pdh, pdl) if len(x) else None
            f0 = pm['08:30']
            # THIN_B: volume share near the extreme below the ticker's own 25th percentile of the prior 60 sessions (no lookahead)
            for cut in CUTS:
                f = pm[cut]
                if f is None:
                    continue
                for side in ('h', 'l'):
                    hist = share_hist[side][-60:]
                    f[f'thinB_{side}'] = bool(len(hist) >= 20 and f[f'share_{side}'] < np.percentile(hist, 25))
            if f0 is not None:
                for side in ('h', 'l'):
                    if f0[f'share_{side}'] == f0[f'share_{side}']:
                        share_hist[side].append(f0[f'share_{side}'])
            orb = rth.iloc[:15]
            eth = g.between_time('04:00', '15:59')
            tp = (eth.high + eth.low + eth.close) / 3
            cv = eth.volume.cumsum().replace(0, np.nan)
            vwap = ((tp * eth.volume).cumsum() / cv).ffill().reindex(rth.index).values
            s = dict(day=day, ticker=t, status=r['status'] or '', atr=atr, pc=pc, levels=lv, pm=pm,
                     brief={k: r[k] for k in r if k.startswith(('calls_', 'puts_'))},
                     orh=float(orb.high.max()), orl=float(orb.low.min()),
                     o=rth.open.values.astype(float), h=rth.high.values.astype(float), l=rth.low.values.astype(float),
                     c=rth.close.values.astype(float), v=rth.volume.values.astype(float), vwap=vwap,
                     tmin=(rth.index.hour * 60 + rth.index.minute).values, brief_pm=r.get('premarket'))
            sessions.append(s)
            fr = dict(day=day, ticker=t, status=s['status'], atr=round(atr, 4), prior_close=pc, open=s['o'][0], orb15_high=s['orh'], orb15_low=s['orl'])
            fr.update({k: round(v, 4) for k, v in sorted(lv.items())})
            for cut in CUTS:
                if pm[cut]:
                    fr.update({f'pm{cut.replace(":", "")}_{k}': v for k, v in pm[cut].items()})
            for k, v in s['brief'].items():
                fr[f'brief_{k}'] = v
            flat.append(fr)
    os.makedirs(f'{LANE}/work', exist_ok=True)
    pickle.dump(sessions, open(f'{LANE}/work/sessions.pkl', 'wb'))
    pd.DataFrame(flat).sort_values(['day', 'ticker']).to_csv(f'{LANE}/inputs/session_levels.csv', index=False)
    print(len(sessions), 'ticker-sessions', len({s['day'] for s in sessions}), 'days')


if __name__ == '__main__':
    main()
