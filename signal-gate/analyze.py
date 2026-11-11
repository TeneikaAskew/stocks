"""Score pre-registered gate candidates on live signal_alerts rows.
Usage: python3 analyze.py alerts.csv
Blocked fire = one the rule would have suppressed. Its live exit_return_pct is
the loss (or win) the rule removes. Day-clustered bootstrap over alert_date."""
import csv, sys, random
from collections import defaultdict

SPLIT = "2026-10-16"
PAST_T1 = ("post_t1", "post_t1_open")
RULES = {
    "C1 brief opposed": lambda r: r["brief_alignment"] == "opposed",
    "C2 fades a leg past T1": lambda r: r["opp_level_state"] in PAST_T1,
    "C2n same, brief neutral/none": lambda r: r["opp_level_state"] in PAST_T1 and r["brief_bias"] not in ("CALL", "PUT"),
    "C3 own leg past T1/invalid": lambda r: r["level_state"] in PAST_T1 + ("invalidated",),
    "C4 RVOL below": lambda r: r["rvol_gate"] == "below",
    "C5 C1 or C2": lambda r: r["brief_alignment"] == "opposed" or r["opp_level_state"] in PAST_T1,
}

def load(path):
    rows = []
    for r in csv.DictReader(open(path)):
        if r.get("exit_return_pct") in ("", None):
            continue
        r["ret"] = float(r["exit_return_pct"])
        rows.append(r)
    return rows

def boot_mean(rows, n=4000, seed=7):
    by = defaultdict(list)
    for r in rows:
        by[r["alert_date"][:10]].append(r["ret"])
    days = list(by)
    if len(days) < 3:
        return (float("nan"), float("nan"))
    rnd = random.Random(seed); out = []
    for _ in range(n):
        s = [x for d in (rnd.choice(days) for _ in days) for x in by[d]]
        out.append(sum(s) / len(s))
    out.sort()
    return out[int(.025 * n)], out[int(.975 * n)]

def stats(rows):
    if not rows:
        return "n=0"
    m = sum(r["ret"] for r in rows) / len(rows)
    w = sum(r["ret"] > 0 for r in rows) / len(rows)
    lo, hi = boot_mean(rows)
    return f"n={len(rows):4d} days={len({r['alert_date'][:10] for r in rows}):3d} mean={m:+.3f}% [{lo:+.3f},{hi:+.3f}] win={w:.0%} sum={sum(r['ret'] for r in rows):+.2f}%"

def main(path):
    rows = load(path)
    tagged = [r for r in rows if r.get("opp_level_state") not in ("", None)]
    first = min(r["alert_date"] for r in tagged)[:10] if tagged else None
    print("rows with exits", len(rows), "| level-tagged since", first)
    for label, lo, hi in (("explore", first, SPLIT), ("holdout", SPLIT, "9999")):
        part = [r for r in rows if r["alert_date"][:10] >= (first or "") and lo <= r["alert_date"][:10] < hi]
        print(f"\n== {label} {lo} to {hi}: all fires {stats(part)}")
        for name, f in RULES.items():
            blk = [r for r in part if f(r)]
            keep = [r for r in part if not f(r)]
            print(f"  {name:30s} blocked {stats(blk)}")
            print(f"  {'':30s} kept    {stats(keep)}")

if __name__ == "__main__":
    main(sys.argv[1])
