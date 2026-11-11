"""Score every indicator: base rate, precision, lift, hit rate, lead, false alarms, wrong-way rate, what was left after the fire.
  python3 -I code/evaluate.py        -> results.csv (long table), work/held.csv (the pre-registered pass/fail per indicator)
Range = 90% bootstrap interval resampling days (tickers on the same day stay together).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

HS = [15, 30, 60]; KS = [0.15, 0.25, 0.35, 0.5]; NBOOT = 1000
rng = np.random.default_rng(7)
ses = pd.read_parquet(f'{WORK}/sessions.parquet')
z = np.load(f'{WORK}/states.npz', allow_pickle=True); ST = z['states']; INTRA = list(z['names'])
OP = np.load(f'{WORK}/minute.npz')['ohlcv'][:, 0, :]
n = len(ses); atr = ses['atr'].values


def sgn(x, thr):
    return np.where(x >= thr, 1, np.where(x <= -thr, -1, 0)).astype(np.int8)

# ---- pre-open indicator states (constant through the session; known at 09:29 unless named 0830 / open) ----
PRE = {
    'gap_pm': sgn(ses.gap_pm, 0.1), 'gap_0830': sgn(ses.gap_0830, 0.1), 'gap_big': sgn(ses.gap_pm, 0.5), 'gap_open': sgn(ses.gap_open, 0.1),
    'pm_vwap': sgn(ses.pm_vwap_d, 0.05), 'pm_vwap_0830': sgn(ses.pm_vwap_d_0830, 0.05), 'pm_late': sgn(ses.pm_late, 0.05),
    'pm_pos': sgn(ses.pm_pos - 0.5, 1 / 6), 'pd_closeloc': sgn(ses.pd_closeloc - 0.5, 0.25),
    'pd_strat_2u2d': np.where(ses.pd_strat == 2, 1, np.where(ses.pd_strat == -2, -1, 0)).astype(np.int8),
    'ftfc_htf': ses.ftfc_htf.values.astype(np.int8), 'd_ema': ses.d_ema.values.astype(np.int8), 'd_macd': ses.d_macd.values.astype(np.int8),
    'd_rsi': sgn(ses.d_rsi - 50, 5), 'h_ema': ses.h_ema.values.astype(np.int8),
    'pm_beyond_pd': np.where(ses.pdc + ses.gap_pm * ses.atr > ses.pdh, 1, np.where(ses.pdc + ses.gap_pm * ses.atr < ses.pdl, -1, 0)).astype(np.int8),
    'vix_chg': (-sgn(ses.vix_chg, 1e-9)).astype(np.int8), 'vix_trend': (-sgn(ses.vix_vs10, 1e-9)).astype(np.int8),
}
ses['pm_rvol_rank'] = ses.groupby('ticker')['pm_rvol'].transform(lambda x: x.rolling(60, min_periods=20).rank(pct=True).shift(0))
# rank uses today's premarket volume against the previous 59 sessions: all known by 09:29
NONDIR_PRE = {
    'pm_range_hi': (ses.pm_range_rank >= 2 / 3).values, 'pm_rvol_hi': (ses.pm_rvol_rank >= 2 / 3).values,
    'vix_hi': (ses.vix_vs20 > 0).values, 'pd_inside': (ses.pd_strat == 1).values, 'pd_outside': (ses.pd_strat == 3).values,
    'gap_abs_big': (ses.gap_pm.abs() >= 0.5).values,
}
FAMILY = {'gap_pm': 'gap', 'gap_0830': 'gap', 'gap_big': 'gap', 'gap_open': 'gap', 'pm_vwap': 'premarket trend', 'pm_vwap_0830': 'premarket trend',
          'pm_late': 'premarket trend', 'pm_pos': 'premarket range', 'pd_closeloc': 'prior day', 'pd_strat_2u2d': 'Strat', 'ftfc_htf': 'Strat',
          'd_ema': 'daily trend', 'd_macd': 'daily trend', 'd_rsi': 'daily trend', 'h_ema': 'hourly trend', 'pm_beyond_pd': 'brief levels',
          'vix_chg': 'VIX', 'vix_trend': 'VIX', 'orb5': 'opening range', 'orb15': 'opening range', 'first5': 'opening range',
          'vwap_side': 'VWAP', 'vwap_slope': 'VWAP', 'rvol_dir': 'relative volume', 'rsi1': 'RSI', 'rsi5': 'RSI', 'ema1': 'EMA 9/21',
          'ema5': 'EMA 9/21', 'macd1': 'MACD', 'macd5': 'MACD', 'pmh_break_0830': 'brief levels', 'pmh_break_0929': 'brief levels',
          'pdh_break': 'brief levels', 'strat5': 'Strat', 'ftfc_intra': 'Strat', 'ftfc_full': 'Strat', 'voter': 'production voter',
          'half_way': 'benchmark (already moved 0.25 ATR)'}


def first_fire(state, d, H):
    """first minute index < H where state == d ; -1 if none. state [n, NB]"""
    m = state[:, :H] == d
    f = np.where(m.any(1), m.argmax(1), -1)
    return f


def fwd30(f, d, pre=False):
    """signed move over the 30 minutes after the fire, entry at the next bar's open, in ATR."""
    e = np.zeros(n, int) if pre else np.clip(f + 1, 0, OP.shape[1] - 31)
    r = (OP[np.arange(n), e + 30] - OP[np.arange(n), e]) / atr * d
    return r


def per_session(name, d, H, k):
    lab = ses[f'lab_{H}_{k}'].values; reach = ses[f'reach_{H}_{k}'].values; start = ses[f'start_{H}_{k}'].values
    if name in PRE:
        fire = PRE[name] == d; f = np.full(n, -1); fw = fwd30(f, d, pre=True)
    else:
        f = first_fire(ST[:, INTRA.index(name), :], d, H); fire = f >= 0; fw = fwd30(f, d)
    moved = lab == d
    succ = fire & moved & (f < reach)
    late = fire & moved & (f >= reach)
    wrong = fire & (lab == -d)
    lead = np.where(succ, reach - f, np.nan)            # minutes from knowing the fire (bar close) to the reach close
    early = succ & (f < start)                          # fired before the move's launch point
    return dict(fire=fire, succ=succ, moved=moved, wrong=wrong, late=late, lead=lead, early=early, fw=np.where(fire, fw, np.nan),
                ftime=np.where(fire, f + 1, np.nan))


def boot_stats(P, mask, dates):
    """P: dict of per-session arrays for one direction or a list of two (both directions)."""
    Ps = P if isinstance(P, list) else [P]
    df = pd.DataFrame({'date': dates[mask]})
    cols = {}
    for j, p in enumerate(Ps):
        for c in ['fire', 'succ', 'moved', 'wrong', 'late', 'early']:
            cols[f'{c}{j}'] = p[c][mask].astype(float)
        cols[f'fwn{j}'] = np.isfinite(p['fw'][mask]).astype(float); cols[f'fws{j}'] = np.nan_to_num(p['fw'][mask])
        cols[f'fww{j}'] = (np.nan_to_num(p['fw'][mask]) > 0).astype(float)
    df = pd.concat([df, pd.DataFrame(cols)], axis=1); df['n'] = 1.0
    g = df.groupby('date').sum(); A = g.values; names = list(g.columns)
    W = rng.multinomial(len(g), np.full(len(g), 1 / len(g)), size=NBOOT).astype(float)
    Bt = np.vstack([A.sum(0)[None, :], W @ A])          # row 0 = actual
    col = lambda c: Bt[:, names.index(c)]
    nn = col('n'); fires = sum(col(f'fire{j}') for j in range(len(Ps))); succ = sum(col(f'succ{j}') for j in range(len(Ps)))
    exp = sum(col(f'fire{j}') * col(f'moved{j}') / nn for j in range(len(Ps)))
    with np.errstate(all='ignore'):
        prec = succ / fires; base = exp / fires; lift = prec - base
        fw = sum(col(f'fws{j}') for j in range(len(Ps))) / sum(col(f'fwn{j}') for j in range(len(Ps)))
        fww = sum(col(f'fww{j}') for j in range(len(Ps))) / sum(col(f'fwn{j}') for j in range(len(Ps)))
        moved = sum(col(f'moved{j}') for j in range(len(Ps)))
        recall = succ / moved
        wrong = sum(col(f'wrong{j}') for j in range(len(Ps))) / fires
        late = sum(col(f'late{j}') for j in range(len(Ps))) / moved
        early = sum(col(f'early{j}') for j in range(len(Ps))) / succ
    q = lambda x: (np.nanpercentile(x[1:], 5), np.nanpercentile(x[1:], 95)) if np.isfinite(x[1:]).sum() > 50 else (np.nan, np.nan)
    lo, hi = q(lift); flo, fhi = q(fw)
    leads = np.concatenate([p['lead'][mask] for p in Ps]); ft = np.concatenate([p['ftime'][mask] for p in Ps])
    return dict(sessions=int(nn[0]), fires=int(fires[0]), moves=int(moved[0]), base_rate=base[0], precision=prec[0], lift_pts=lift[0],
                lift_lo=lo, lift_hi=hi, lift_ratio=prec[0] / base[0] if base[0] > 0 else np.nan, hit_rate=recall[0],
                late_share=late[0], false_alarm=1 - prec[0], wrong_way=wrong[0],
                lead_min_median=np.nanmedian(leads) if np.isfinite(leads).any() else np.nan,
                fired_before_move_start=early[0], fire_min_median=np.nanmedian(ft) if np.isfinite(ft).any() else np.nan,
                after30_atr=fw[0], after30_lo=flo, after30_hi=fhi, after30_win=fww[0])


dates = ses['date'].values; tick = ses['ticker'].values; win = ses['window'].values

if __name__ == '__main__':
    out = []
    names = list(PRE) + INTRA
    for k in KS:
        for H in HS:
            for name in names:
                P = {d: per_session(name, d, H, k) for d in (1, -1)}
                for w in ('primary', 'holdout'):
                    for T in ['ALL'] + TICKERS:
                        mask = (win == w) & ((tick == T) if T != 'ALL' else True)
                        for dn, pp in (('up', P[1]), ('down', P[-1]), ('both', [P[1], P[-1]])):
                            r = boot_stats(pp, mask, dates)
                            out.append(dict(indicator=name, family=FAMILY[name], when='pre-open' if name in PRE else 'in-session',
                                            k_atr=k, horizon_min=H, window=w, ticker=T, direction=dn, **r))
            # non-directional: does a move (either way) come?
            lab = ses[f'lab_{H}_{k}'].values
            nd = dict(NONDIR_PRE); nd['rvol_hot_by_0935'] = (ST[:, INTRA.index('rvol_dir'), :5] != 0).any(1)
            for name, on in nd.items():
                p = dict(fire=on, succ=on & (lab != 0), moved=lab != 0, wrong=np.zeros(n, bool), late=np.zeros(n, bool), early=np.zeros(n, bool),
                         lead=np.full(n, np.nan), fw=np.full(n, np.nan), ftime=np.full(n, np.nan))
                for w in ('primary', 'holdout'):
                    for T in ['ALL'] + TICKERS:
                        mask = (win == w) & ((tick == T) if T != 'ALL' else True)
                        r = boot_stats(p, mask, dates)
                        out.append(dict(indicator=name, family='is a move coming (either way)', when='pre-open' if name in NONDIR_PRE else 'in-session',
                                        k_atr=k, horizon_min=H, window=w, ticker=T, direction='any', **r))
        print('k', k, 'done', flush=True)
    R = pd.DataFrame(out)
    num = R.select_dtypes(float).columns; R[num] = R[num].round(4)
    R.to_csv(f'{ROOT}/results.csv', index=False)

    # ---- pre-registered pass / fail: direction 'both' (or 'any'), per (k, H) ----
    rows = []
    key = R[R.direction.isin(['both', 'any'])]
    for (name, k, H), g in key.groupby(['indicator', 'k_atr', 'horizon_min']):
        a = g.set_index(['window', 'ticker'])
        pr, ho = a.loc[('primary', 'ALL')], a.loc[('holdout', 'ALL')]
        signs = [np.sign(a.loc[('holdout', T), 'lift_pts']) for T in TICKERS]
        same = len(set(signs)) == 1 and signs[0] != 0
        held = bool(pr.lift_lo > 0 and ho.lift_lo > 0 and same and signs[0] > 0)
        held_neg = bool(pr.lift_hi < 0 and ho.lift_hi < 0 and same and signs[0] < 0)
        trad = bool(held and ho.after30_lo > 0)
        rows.append(dict(indicator=name, family=g.family.iloc[0], when=g.when.iloc[0], k_atr=k, horizon_min=H,
                         primary_fires=pr.fires, primary_lift=pr.lift_pts, primary_lo=pr.lift_lo, primary_hi=pr.lift_hi,
                         holdout_fires=ho.fires, holdout_base=ho.base_rate, holdout_precision=ho.precision, holdout_lift=ho.lift_pts,
                         holdout_lo=ho.lift_lo, holdout_hi=ho.lift_hi, holdout_hit_rate=ho.hit_rate, holdout_lead=ho.lead_min_median,
                         holdout_wrong_way=ho.wrong_way, holdout_after30=ho.after30_atr, holdout_after30_lo=ho.after30_lo, holdout_after30_hi=ho.after30_hi,
                         same_sign_3_tickers=same, held=held, held_as_fade=held_neg, tradable_after_fire=trad))
    Hd = pd.DataFrame(rows); Hd.to_csv(f'{WORK}/held.csv', index=False)
    print('rows', len(R)); print(Hd[(Hd.k_atr == 0.5) & (Hd.horizon_min == 60)].sort_values('holdout_lift', ascending=False)
          [['indicator', 'primary_lift', 'primary_lo', 'holdout_fires', 'holdout_base', 'holdout_precision', 'holdout_lift', 'holdout_lo', 'holdout_hi', 'holdout_after30', 'holdout_after30_lo', 'held', 'tradable_after_fire']].to_string())
