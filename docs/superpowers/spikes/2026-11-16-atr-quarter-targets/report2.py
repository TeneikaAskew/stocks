import sys, numpy as np, pandas as pd
t = pd.read_csv(sys.argv[1]); t["date"] = pd.to_datetime(t["date"])
ARMS = ["A", "Q", "Q3", "Q2", "B1", "B2", "B3"]
print("trades", len(t), " A total %.4f" % t.A_r.sum(), t.groupby("ticker").A_r.agg(["count", "sum"]).round(3).to_dict())
def rng(df, a):
    v = (df[f"{a}_r"] - df["A_r"]).groupby(df["date"]).sum().to_numpy(); r = np.random.default_rng(7)
    s = v[r.integers(0, len(v), size=(2000, len(v)))].sum(axis=1); return np.percentile(s, 5), np.percentile(s, 95)
def line(name, df):
    parts = [f"{name:26s} n={len(df):5d} A {df.A_r.sum():+7.1f}"]
    for a in ARMS[1:]:
        lo, hi = rng(df, a); parts.append(f"{a} {df[a + '_r'].sum():+7.1f} [{df[a + '_r'].sum() - df.A_r.sum():+6.1f} ({lo:+.1f},{hi:+.1f})]")
    print(" | ".join(parts))
print("\n== total R; [arm minus A (90% range, whole days resampled 2,000 times, default_rng(7))] ==")
line("All", t)
for k in ("SPY", "QQQ", "IWM"): line(k, t[t.ticker == k])
for a, b in (("2022-01-03", "2025-02-28"), ("2025-03-03", "2026-04-30"), ("2026-05-01", "2026-11-10")): line(f"{a}..{b}", t[(t.date >= a) & (t.date <= b)])
e = pd.to_datetime(["2022-01-01", "2022-03-01", "2022-09-01", "2023-03-01", "2023-09-01", "2024-03-01", "2024-09-01", "2025-03-01", "2025-09-01", "2026-03-01", "2026-09-01", "2026-11-11"])
for a, b in zip(e[:-1], e[1:]): line(f"{a.date()}..{(b - pd.Timedelta(days=1)).date()}", t[(t.date >= a) & (t.date < b)])
for s in ("calls", "puts"): line(s, t[t.side == s])
print("\n== per arm ==")
o = t.sort_values(["date", "fill_ts", "ticker"])
for a in ARMS:
    r = t[f"{a}_r"]; ex = t[f"{a}_exit"].str.split(",")
    runs = {}
    for k in ("SPY", "QQQ", "IWM"):
        x = (t[t.ticker == k].sort_values("date")[f"{a}_r"] < 0).to_numpy(); best = cur = 0
        for v in x:
            cur = cur + 1 if v else 0; best = max(best, cur)
        runs[k] = best
    c = o[f"{a}_r"].cumsum().to_numpy(); peak = np.maximum.accumulate(np.concatenate([[0.0], c])); dd = (peak - np.concatenate([[0.0], c])).max()
    print(f"{a:3s} total {r.sum():+8.2f} avg {r.mean():+.4f} share R>0 {(r > 0).mean():.1%} R=0 {(r == 0).mean():.1%} worst {r.min():+.2f} best {r.max():+.2f} "
          f"all legs stopped {ex.apply(lambda v: set(v) == {'stop'}).mean():.1%} any leg stopped {ex.apply(lambda v: 'stop' in v).mean():.1%} losing runs {runs} max drawdown {dd:.1f}R")
print("\nB1 level targets beyond the 0.50 ATR mark:", t.b1_levels.value_counts().sort_index().to_dict())
print("B2 priced legs 3 and 4:", t.b2_priced.value_counts().sort_index().to_dict(), " A targets per trade:", t.a_n_targets.value_counts().sort_index().to_dict())
print("B3 trades with a level target beyond 0.25 ATR:", t.b3_levels.value_counts().sort_index().to_dict())
