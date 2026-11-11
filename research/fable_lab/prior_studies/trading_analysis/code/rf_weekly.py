"""The script's own feature-importance step (analyze_feature_importance), rerun weekly.

  python -I code/rf_weekly.py

For each ticker and eval week W: fit on the voter signals of weeks W-4..W-1 exactly as
analyze_feature_importance does (same feature list incl. exit_*, median fill, scaler,
RandomForest 100 trees depth 10, score = 0.4 |corr| + 0.6 RF importance). Record the
top 10 features, in-sample R2 (what the script prints) and the R2 on week W (out of sample).
A check at the start confirms this replica returns the same ranking as the script's function.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from common2 import TICKERS, WORK, ROOT, MarketAnalyzer, quiet

FIRST_EVAL = pd.Timestamp('2025-05-26')
EXCL = ['entry_time', 'exit_time', 'trade_type', 'entry_price', 'exit_price', 'return_pct', 'best_return',
        'best_window_minutes', 'duration_minutes', 'signal_strength', 'conditions_met', 'week']


def feats(S):
    ex = EXCL + [c for c in S.columns if c.startswith('return_') and 'min' in c]
    cols = [c for c in S.columns if c not in ex and S[c].dtype in ['int64', 'float64', 'int32', 'float32']]
    return [c for c in cols if S[c].isna().mean() * 100 < 50]


def rank(S):
    cols = feats(S)
    X = S[cols].copy(); y = S['return_pct']
    med = X.median(); X = X.fillna(med)
    corr = {c: abs(X[c].corr(y)) for c in cols}
    sc = StandardScaler().fit(X)
    rf = RandomForestRegressor(n_estimators=100, max_depth=10, min_samples_split=10, min_samples_leaf=5,
                               random_state=42, n_jobs=-1).fit(sc.transform(X), y)
    imp = dict(zip(cols, rf.feature_importances_))
    mc = max(v for v in corr.values() if np.isfinite(v)); mr = max(imp.values())
    score = {c: 0.4 * (np.nan_to_num(corr[c]) / mc) + 0.6 * imp[c] / mr for c in cols}
    order = sorted(cols, key=lambda c: -score[c])
    return order, rf, sc, cols, med, rf.score(sc.transform(X), y)


rows = []
for T in TICKERS:
    SG = pd.read_parquet(f'{WORK}/{T}_orig_signals.parquet')
    weeks = np.sort(SG['week'].unique())
    if T == TICKERS[0]:   # replica check against the script's own function
        S = SG[SG['week'].isin(weeks[10:14])].drop(columns=['week']).reset_index(drop=True)
        mine = rank(S)[0][:10]
        theirs = quiet(MarketAnalyzer().analyze_feature_importance, S, 20)['feature'].tolist()[:10]
        print('replica matches script top10:', mine == theirs, flush=True)
    prev = None
    for W in [w for w in weeks if w >= FIRST_EVAL]:
        i = int(np.searchsorted(weeks, W))
        S = SG[SG['week'].isin(weeks[i - 4:i])].reset_index(drop=True)
        Wt = SG[SG['week'] == W]
        if len(S) < 100 or len(Wt) < 20:
            continue
        order, rf, sc, cols, med, r2_in = rank(S)
        r2_out = rf.score(sc.transform(Wt[cols].fillna(med)), Wt['return_pct'])
        top10 = order[:10]
        jac = len(set(top10) & set(prev)) / len(set(top10) | set(prev)) if prev else np.nan
        rows.append(dict(ticker=T, week=pd.Timestamp(W).date(), n_fit=len(S), n_week=len(Wt),
                         r2_in_sample=r2_in, r2_next_week=r2_out, top1=order[0], top5=' ; '.join(order[:5]),
                         exit_feats_in_top5=sum(f.startswith('exit_') for f in order[:5]),
                         exit_rank_best=min((k + 1 for k, f in enumerate(order) if f.startswith('exit_')), default=np.nan),
                         jaccard_top10_vs_prev_week=jac))
        prev = top10
    print(T, 'rf done', flush=True)
pd.DataFrame(rows).to_csv(f'{ROOT}/weekly_rf_feature_importance.csv', index=False)
