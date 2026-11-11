"""Summarize persona_outcomes.csv. Usage: python3 -I summarize.py <persona_outcomes.csv>"""
import csv
import sys
from collections import defaultdict

rows = list(csv.DictReader(open(sys.argv[1])))
can = [r for r in rows if r["canonical"] == "1"]


def f(x):
    return float(x) if x not in ("", None) else None


def block(title, rs, rule):
    print(f"\n## {title} ({rule} rule)")
    print("group | plans | filled | t1 | stop | close | sum R | avg R/fill | size-wtd sum R")
    groups = defaultdict(list)
    for r in rs:
        groups[r["_g"]].append(r)
    for g in sorted(groups):
        gs = groups[g]
        fills = [r for r in gs if r[f"outcome_{rule}"] in ("t1", "stop", "close")]
        rr = [f(r[f"r_{rule}"]) for r in fills]
        sw = sum(f(r[f"r_{rule}"]) * f(r["size"]) for r in fills)
        n = len(fills)
        print(f"{g} | {len(gs)} | {n} | "
              f"{sum(r[f'outcome_{rule}']=='t1' for r in fills)} | "
              f"{sum(r[f'outcome_{rule}']=='stop' for r in fills)} | "
              f"{sum(r[f'outcome_{rule}']=='close' for r in fills)} | "
              f"{sum(rr):+.2f} | {(sum(rr)/n if n else 0):+.2f} | {sw:+.2f}")


for rule in ("day", "swing", "fill5"):
    for key, title in (("persona", "By persona"), ("ticker", "By ticker"),
                       ("direction", "By direction")):
        rs = [dict(r, _g=r[key]) for r in can]
        block(title, rs, rule)
    if rule == "day":
        rs = [dict(r, _g=r["session"]) for r in can if r["persona"] == "neutral"]
        block("By day, neutral persona only", rs, rule)

# direction-call accuracy (one per ticker-day)
neu = [r for r in can if r["persona"] == "neutral"]
print("\n## Direction call accuracy (canonical, one per ticker-day)")
for k in ("dir_correct_vs_prev_close", "dir_correct_5d"):
    v = [int(r[k]) for r in neu if r[k] != ""]
    print(f"{k}: {sum(v)}/{len(v)}")
for d in ("long", "short"):
    v = [int(r["dir_correct_vs_prev_close"]) for r in neu if r["direction"] == d]
    print(f"  {d}: {sum(v)}/{len(v)} right on the day")
v = [r for r in neu if r["outcome_day"] == "no_fill"]
print(f"no-fill ticker-days: {len(v)}/{len(neu)}; of those the call was wrong on the day: "
      f"{sum(1 for r in v if r['dir_correct_vs_prev_close']=='0')}")
d = [f(r["entry_dist_atr"]) for r in neu if r.get("entry_dist_atr")]
d.sort()
print(f"entry distance from prior close in ATR: median {d[len(d)//2]:.2f}, "
      f">1 ATR {sum(x>1 for x in d)}/{len(d)}, >3 ATR {sum(x>3 for x in d)}/{len(d)}")
