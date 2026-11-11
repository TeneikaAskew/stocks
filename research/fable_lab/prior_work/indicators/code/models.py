"""Simple models, chosen by month-by-month walk-forward INSIDE the primary window, refit on the primary window, frozen,
then scored once on the holdout.
  python3 -I code/models.py     -> model_results.csv , rule_results.csv , work/frozen_models.json
"""
import sys, os, json, itertools, warnings
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
warnings.filterwarnings('ignore')
import evaluate as E
from common import *
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, log_loss

ses, ST, INTRA, PRE = E.ses, E.ST, E.INTRA, E.PRE
rng = np.random.default_rng(11)
pri = (ses.window == 'primary').values; hol = (ses.window == 'holdout').values
month = ses.date.dt.to_period('M').astype(str).values

PRE_SETS = {
    'gap+premarket trend': ['gap_pm', 'pm_vwap_d', 'pm_late'],
    'plus prior day and higher timeframe': ['gap_pm', 'pm_vwap_d', 'pm_late', 'pm_pos', 'pd_closeloc', 'pd_ret', 'ftfc_htf', 'd_ema'],
    'everything before the open': ['gap_pm', 'pm_vwap_d', 'pm_late', 'pm_pos', 'pd_closeloc', 'pd_ret', 'ftfc_htf', 'd_ema', 'pm_range',
                                   'vix_chg', 'vix_vs10', 'h_ema', 'd_macd', 'd_rsi', 'pm_rvol'],
}
def at_sets(n):
    base = PRE_SETS['gap+premarket trend']
    return {f'first {n} min return only': [f'ret{n}'],
            f'first {n} min return, range, volume': [f'ret{n}', f'rng{n}', f'rvol{n}', f'loc{n}'],
            f'first {n} min + premarket': base + [f'ret{n}', f'rng{n}', f'rvol{n}', f'loc{n}', f'vwapd{n}', f'rsi1_{n}', f'macd1_{n}']}
CS = [0.01, 0.1, 1.0]


def fit(X, y, C):
    mu, sd = np.nanmean(X, 0), np.nanstd(X, 0) + 1e-9
    Z = np.nan_to_num((X - mu) / sd)
    m = LogisticRegression(C=C, max_iter=500).fit(Z, y)
    return dict(mu=mu.tolist(), sd=sd.tolist(), coef=m.coef_[0].tolist(), b=float(m.intercept_[0]))


def predict(f, X):
    Z = np.nan_to_num((X - np.array(f['mu'])) / np.array(f['sd']))
    return 1 / (1 + np.exp(-(Z @ np.array(f['coef']) + f['b'])))


def boot_auc(y, p, d):
    days = pd.unique(d); ix = {x: np.where(d == x)[0] for x in days}; out = []
    for _ in range(400):
        s = np.concatenate([ix[x] for x in rng.choice(days, len(days))])
        if 0 < y[s].sum() < len(s): out.append(roc_auc_score(y[s], p[s]))
    return np.percentile(out, 5), np.percentile(out, 95)


def boot_lift(top, y, d):
    df = pd.DataFrame({'d': d, 't': top.astype(float), 'ty': (top & (y == 1)).astype(float), 'y': y.astype(float), 'n': 1.0}).groupby('d').sum()
    W = rng.multinomial(len(df), np.full(len(df), 1 / len(df)), size=1000) @ df.values
    l = W[:, 1] / W[:, 0] - W[:, 2] / W[:, 3]
    return np.nanpercentile(l, 5), np.nanpercentile(l, 95)


rows, frozen = [], {}
targets = [(0.15, 15), (0.25, 30), (0.5, 60), (0.25, 60)]
for when, sets, nmin in [('before the open (09:29)', PRE_SETS, 0), ('09:35', at_sets(5), 5), ('09:45', at_sets(15), 15)]:
    for (k, H) in targets:
        if nmin and H <= nmin + 10: continue
        lab = ses[f'lab_{H}_{k}'].values; reach = ses[f'reach_{H}_{k}'].values
        elig = np.ones(len(ses), bool) if nmin == 0 else ~((lab != 0) & (reach < nmin))     # not already reached at decision time
        for dname, d in (('up', 1), ('down', -1)):
            y = (lab == d).astype(int)
            months = sorted(set(month[pri])); best = None
            for sname, cols in sets.items():
                X = ses[cols].values.astype(float)
                for C in CS:
                    ll, n = 0.0, 0; pp, yy = [], []
                    for mth in months[2:]:
                        tr = pri & elig & (month < mth); te = pri & elig & (month == mth)
                        if y[tr].sum() < 5 or te.sum() == 0: continue
                        p = predict(fit(X[tr], y[tr], C), X[te]); pp.append(p); yy.append(y[te])
                    if not pp: continue
                    pp, yy = np.concatenate(pp), np.concatenate(yy)
                    sc = log_loss(yy, np.clip(pp, 1e-4, 1 - 1e-4), labels=[0, 1])
                    wf_auc = roc_auc_score(yy, pp) if 0 < yy.sum() < len(yy) else np.nan
                    if best is None or sc < best[0]: best = (sc, sname, cols, C, wf_auc)
            if best is None: continue
            sc, sname, cols, C, wf_auc = best
            X = ses[cols].values.astype(float)
            m = fit(X[pri & elig], y[pri & elig], C)
            p = predict(m, X)
            thr = float(np.quantile(p[pri & elig], 0.8))                                   # frozen: top fifth of primary scores
            key = f'{when}|{k}|{H}|{dname}'
            frozen[key] = dict(features=cols, C=C, threshold=thr, **m)
            for T in ['ALL'] + TICKERS:
                hm = hol & elig & ((ses.ticker == T).values if T != 'ALL' else True)
                pm_ = pri & elig & ((ses.ticker == T).values if T != 'ALL' else True)
                yh, ph, dh = y[hm], p[hm], ses.date.values[hm]
                if yh.sum() < 3: continue
                auc = roc_auc_score(yh, ph); alo, ahi = boot_auc(yh, ph, dh)
                top = ph >= thr; llo, lhi = boot_lift(top, yh, dh)
                # what was left: 30 minutes after the decision, in the model's direction, for the top group
                e0 = nmin
                fw = (E.OP[:, e0 + 30] - E.OP[:, e0]) / E.atr * d
                rows.append(dict(decision_time=when, k_atr=k, horizon_min=H, direction=dname, ticker=T, chosen_features=sname, C=C,
                                 walkforward_auc_primary=wf_auc, insample_auc_primary=roc_auc_score(y[pm_], p[pm_]) if 0 < y[pm_].sum() < pm_.sum() else np.nan,
                                 holdout_sessions=int(hm.sum()), holdout_moves=int(yh.sum()), holdout_auc=auc, auc_lo=alo, auc_hi=ahi,
                                 top_group_n=int(top.sum()), holdout_base_rate=yh.mean(), top_group_precision=yh[top].mean() if top.any() else np.nan,
                                 top_group_lift_pts=(yh[top].mean() - yh.mean()) if top.any() else np.nan, lift_lo=llo, lift_hi=lhi,
                                 top_group_after30_atr=np.nanmean(fw[hm][top]) if top.any() else np.nan,
                                 held=bool(alo > 0.5 and llo > 0)))
M = pd.DataFrame(rows); num = M.select_dtypes(float).columns; M[num] = M[num].round(4)
M.to_csv(f'{ROOT}/model_results.csv', index=False)
json.dump(frozen, open(f'{WORK}/frozen_models.json', 'w'), indent=1)
print(M[M.ticker == 'ALL'][['decision_time', 'k_atr', 'horizon_min', 'direction', 'chosen_features', 'walkforward_auc_primary', 'insample_auc_primary',
                            'holdout_auc', 'auc_lo', 'auc_hi', 'holdout_base_rate', 'top_group_n', 'top_group_precision', 'lift_lo', 'lift_hi', 'top_group_after30_atr', 'held']].to_string())

# ---------------- rules: best single indicator and best pair, picked on the primary window only ----------------
n = len(ses); NBm = ST.shape[2]
def state_of(name):
    return np.repeat(PRE[name][:, None], NBm, 1) if name in PRE else ST[:, INTRA.index(name), :]
names = [x for x in list(PRE) + INTRA if x not in ('half_way', 'gap_open')]
fam = E.FAMILY
def rule_stats(state, k, H, mask):
    lab = ses[f'lab_{H}_{k}'].values; reach = ses[f'reach_{H}_{k}'].values
    P = []
    for d in (1, -1):
        f = E.first_fire(state, d, H); fire = f >= 0; moved = lab == d
        if (state[:, 0] == state[:, -1]).all() and (state == state[:, :1]).all(): f = np.where(fire, -1, f)   # pre-open only
        P.append(dict(fire=fire, succ=fire & moved & (f < reach), moved=moved, wrong=fire & (lab == -d), late=fire & moved & (f >= reach),
                      early=np.zeros(n, bool), lead=np.where(fire & moved & (f < reach), reach - f, np.nan),
                      fw=np.where(fire, E.fwd30(f, d, pre=False) if (f >= 0).any() else E.fwd30(f, d, pre=True), np.nan), ftime=np.where(fire, f + 1, np.nan)))
    return P
def quick(P, mask):
    fires = sum(p['fire'][mask].sum() for p in P); succ = sum(p['succ'][mask].sum() for p in P)
    exp = sum(p['fire'][mask].sum() * p['moved'][mask].mean() for p in P)
    if fires < 40: return None
    base = exp / fires; prec = succ / fires
    return (prec - base) / np.sqrt(base * (1 - base) / fires + 1e-12), fires, prec, base
rr = []
for (k, H) in targets:
    cand = {}
    for a in names:
        cand[a] = state_of(a)
    for a, b in itertools.combinations(names, 2):
        if fam[a] == fam[b]: continue
        sa, sb = state_of(a), state_of(b)
        cand[f'{a} AND {b}'] = np.where(sa == sb, sa, 0).astype(np.int8)
    sc = []
    for nm, stt in cand.items():
        P = rule_stats(stt, k, H, pri); q = quick(P, pri)
        if q: sc.append((q[0], nm))
    sc.sort(reverse=True)
    singles = [x for x in sc if ' AND ' not in x[1]][:3]; pairs = [x for x in sc if ' AND ' in x[1]][:3]
    for rank, (zs, nm) in enumerate(singles + pairs):
        P = rule_stats(cand[nm], k, H, pri)
        for w, mk in (('primary', pri), ('holdout', hol)):
            for T in ['ALL'] + TICKERS:
                mm = mk & ((ses.ticker == T).values if T != 'ALL' else True)
                r = E.boot_stats(P, mm, ses.date.values)
                rr.append(dict(k_atr=k, horizon_min=H, rule=nm, kind='pair' if ' AND ' in nm else 'single', rank_on_primary=rank % 3 + 1,
                               primary_z=zs, window=w, ticker=T, **r))
    print('rules', k, H, 'candidates', len(sc), flush=True)
RR = pd.DataFrame(rr); num = RR.select_dtypes(float).columns; RR[num] = RR[num].round(4)
RR.to_csv(f'{ROOT}/rule_results.csv', index=False)
print(RR[RR.ticker == 'ALL'][['k_atr', 'horizon_min', 'rule', 'window', 'fires', 'base_rate', 'precision', 'lift_pts', 'lift_lo', 'lift_hi', 'wrong_way', 'lead_min_median', 'after30_atr', 'after30_lo', 'after30_hi']].to_string())
