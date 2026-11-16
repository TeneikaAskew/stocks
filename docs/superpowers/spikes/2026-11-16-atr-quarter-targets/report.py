"""Tables for the ATR quarter-target spike from the per-day CSV score_arms.py writes."""
import sys, json
import numpy as np, pandas as pd
src, variant = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "side")
d = pd.read_csv(src)
t = d[d["pick"].notna()].copy()
if variant == "day":       # a day on which EITHER side opened past its trigger is no trade
    t = t[~t["any_opened_through"]]
t["date"] = pd.to_datetime(t["date"])
print(f"variant={variant}  ticker-days scored {len(d)}  trades {len(t)}")
print("arm A r_status:", t["a_status"].value_counts(dropna=False).to_dict(), " target_status:", t["a_target_status"].value_counts(dropna=False).to_dict())
print("arm Q r_status:", t["q_status"].value_counts(dropna=False).to_dict())
for c in ("a_r", "q_r", "q3_r"):
    t[c] = t[c].astype(float)
print("trades with a NULL R: A", int(t.a_r.isna().sum()), "Q", int(t.q_r.isna().sum()), "Q3", int(t.q3_r.isna().sum()))

def rng_range(df, col):
    by = df.assign(x=df[col] - df["a_r"]).groupby("date")["x"].sum()
    v = by.to_numpy(); r = np.random.default_rng(7)
    sums = v[r.integers(0, len(v), size=(2000, len(v)))].sum(axis=1)
    return np.percentile(sums, 5), np.percentile(sums, 95)

def line(name, df):
    if not len(df): return
    a, q, q3 = df.a_r.sum(), df.q_r.sum(), df.q3_r.sum()
    ql, qh = rng_range(df, "q_r"); l3, h3 = rng_range(df, "q3_r")
    print(f"{name:34s} n={len(df):5d}  A {a:+8.1f}  Q {q:+8.1f}  Q-A {q-a:+7.1f} ({ql:+.1f}, {qh:+.1f})  Q3 {q3:+8.1f}  Q3-A {q3-a:+7.1f} ({l3:+.1f}, {h3:+.1f})")

print("\n== totals (R; range = 90%, whole days resampled 2,000 times, numpy default_rng(7)) ==")
line("All", t)
for k in ("SPY", "QQQ", "IWM"): line(k, t[t.ticker == k])
print("-- the gap-edges spec's three windows")
for a, b in (("2022-01-03", "2025-02-28"), ("2025-03-03", "2026-04-30"), ("2026-05-01", "2026-11-10")):
    line(f"{a} to {b}", t[(t.date >= a) & (t.date <= b)])
print("-- six-month blocks (Mar to Aug, Sep to Feb; first and last partial)")
edges = pd.to_datetime(["2022-01-01", "2022-03-01", "2022-09-01", "2023-03-01", "2023-09-01", "2024-03-01", "2024-09-01",
                        "2025-03-01", "2025-09-01", "2026-03-01", "2026-09-01", "2026-11-11"])
for a, b in zip(edges[:-1], edges[1:]):
    line(f"{a.date()} to {(b - pd.Timedelta(days=1)).date()}", t[(t.date >= a) & (t.date < b)])
print("-- by side"); [line(s, t[t.side == s]) for s in ("calls", "puts")]

print("\n== reach before the stop (share of entered trades whose leg sold at the target) ==")
def has(col, k): return t[col].fillna("").str.split(",").apply(lambda x: f"t{k}" in x)
print("arm A:", {f"T{k}": f"{has('a_exit', k).mean():.1%}" for k in (1, 2, 3)}, " stop on every leg:", f"{(t.a_exit.str.split(',').apply(lambda x: set(x) == {'stop'})).mean():.1%}",
      " any leg stopped:", f"{t.a_exit.str.contains('stop').mean():.1%}")
print("arm Q (0.25, 0.50, 0.75, 1.00 ATR):", {f"T{k}": f"{has('q_exit', k).mean():.1%}" for k in (1, 2, 3, 4)},
      " any leg stopped:", f"{t.q_exit.str.contains('stop').mean():.1%}", " all four stopped:", f"{(t.q_exit == 'stop,stop,stop,stop').mean():.1%}")
print("arm Q3 (0.25, 0.50, 0.75 ATR):", {f"T{k}": f"{has('q3_exit', k).mean():.1%}" for k in (1, 2, 3)})
for k in ("SPY", "QQQ", "IWM"):
    m = t.ticker == k
    print(f"  {k} arm Q:", {f"T{j}": f"{has('q_exit', j)[m].mean():.1%}" for j in (1, 2, 3, 4)}, " arm A:", {f"T{j}": f"{has('a_exit', j)[m].mean():.1%}" for j in (1, 2, 3)})
print("arm A exit patterns:", t.a_exit.value_counts().head(8).to_dict())
print("arm Q exit patterns:", t.q_exit.value_counts().head(10).to_dict())
print("arm A targets published per traded side:", t.a_targets.apply(lambda s: len(json.loads(s))).value_counts().sort_index().to_dict())

print("\n== T1 at 0.25 ATR against the plan's stop ==")
risk_fill = (t.fill - t.stop).abs(); risk_trig = (t.trigger - t.stop).abs()
t1r_fill = (pd.Series([json.loads(s)[0] for s in t.q_targets], index=t.index) - t.fill).abs() / risk_fill
t1r_trig = 0.25 * t.atr / risk_trig
for name, s in (("from the fill, risk = fill to stop", t1r_fill), ("from the trigger, risk = trigger to stop", t1r_trig)):
    print(f"{name}: under 1.5R on {(s < 1.5).mean():.1%} of {len(s)} trades; under 1.0R on {(s < 1.0).mean():.1%}; median {s.median():.2f}R; quartiles {s.quantile(.25):.2f} / {s.quantile(.75):.2f}")
print("stop distance in ATR (trigger to stop): median %.2f, quartiles %.2f / %.2f" % ((risk_trig / t.atr).median(), (risk_trig / t.atr).quantile(.25), (risk_trig / t.atr).quantile(.75)))
print("trades filled at the open beyond the trigger:", int((t.fill != t.trigger).sum()), " of them with fill at or past T1:", int(((t.fill - pd.Series([json.loads(s)[0] for s in t.q_targets], index=t.index)) * np.where(t.side == 'calls', 1, -1) >= 0).sum()))

print("\n== ATR target within 5 cents past a named level (0 < target - level <= 0.05 in the trade's direction) ==")
near = t.q_near_levels.apply(json.loads)
tot_n = tot_hit = rest_n = rest_hit = 0
for k in (1, 2, 3, 4):
    flag = near.apply(lambda x: len(x[k - 1]) > 0); hit = has("q_exit", k)
    print(f"T{k}: {int(flag.sum())} of {len(t)} ({flag.mean():.1%}) sit just past a level; reached {hit[flag].mean():.1%} of those against {hit[~flag].mean():.1%} of the rest")
    tot_n += flag.sum(); tot_hit += hit[flag].sum(); rest_n += (~flag).sum(); rest_hit += hit[~flag].sum()
print(f"all four targets pooled: {tot_n} of {tot_n + rest_n} ({tot_n / (tot_n + rest_n):.1%}); reached {tot_hit / tot_n:.1%} against {rest_hit / rest_n:.1%}")
print(f"trades with at least one such target: {near.apply(lambda x: any(len(y) for y in x)).mean():.1%}")
names = pd.Series([lv.split('@')[0] for x in near for y in x for lv in y]).value_counts().head(12)
print("levels involved:", names.to_dict())
