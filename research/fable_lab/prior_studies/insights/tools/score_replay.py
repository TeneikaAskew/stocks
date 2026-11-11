"""Score current-code persona plans (from replay_day.py JSONs) with the same rule
as score_insights.py. The LLM's direction is held at what the stored report said.

Usage: python3 -I score_replay.py <replay_dir> <prefix> <persona_outcomes.csv> <bars_raw_dir> <out_csv>
"""
import csv
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score_insights import load_bars, simulate  # noqa: E402

rdir, prefix, orig_csv, bars_dir, out_csv = sys.argv[1:6]
orig = [r for r in csv.DictReader(open(orig_csv)) if r["canonical"] == "1" and r["persona"] == "neutral"]
llm_dir = {(r["ticker"], r["session"]): r["direction"] for r in orig}
bars = {t: load_bars(bars_dir, t) for t in ("SPY", "QQQ", "IWM")}
out = []
for f in sorted(glob.glob(os.path.join(rdir, f"{prefix}_*.json"))):
    rep = json.load(open(f))
    ses = rep["session"]
    for tk, e in rep["tickers"].items():
        days = sorted(bars[tk])
        if ses not in days:
            continue
        i = days.index(ses)
        swing = days[i:i + 5]
        for direction in ("long", "short"):
            plans = e["_plans"].get(direction)
            if not isinstance(plans, list):
                continue
            for p in plans:
                row = dict(code=prefix, session=ses, ticker=tk, direction=direction,
                           llm_direction=llm_dir.get((tk, ses)),
                           matches_llm=int(llm_dir.get((tk, ses)) == direction),
                           persona=p["persona"], regime=p["regime"],
                           trigger=e.get("calls_trigger_name" if direction == "long" else "puts_trigger_name"))
                if not p.get("entry") or p.get("stop") is None or not p.get("targets"):
                    row["outcome_day"] = "no_plan"
                    out.append(row)
                    continue
                lo, hi = p["entry"]
                stop, t1 = p["stop"], p["targets"][0]
                row.update(entry_lo=lo, entry_hi=hi, stop=stop, t1=t1)
                d = simulate([bars[tk][ses]], [ses], direction, lo, hi, stop, t1)
                s = simulate([bars[tk][x] for x in swing], swing, direction, lo, hi, stop, t1)
                row.update(outcome_day=d["outcome"], fill_time_day=d["fill_time"], r_day=d["r"],
                           mfe_r_day=d["mfe_r"], outcome_swing=s["outcome"], r_swing=s["r"],
                           exit_day_swing=s["exit_day"])
                out.append(row)
cols = []
for r in out:
    for k in r:
        if k not in cols:
            cols.append(k)
with open(out_csv, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()
    w.writerows(out)


def summ(rows, label, rule):
    fills = [r for r in rows if r.get(f"outcome_{rule}") in ("t1", "stop", "close")]
    rr = [float(r[f"r_{rule}"]) for r in fills]
    n = len(fills)
    print(f"{label} | {len(rows)} | {n} | {sum(r[f'outcome_{rule}']=='t1' for r in fills)} | "
          f"{sum(r[f'outcome_{rule}']=='stop' for r in fills)} | {sum(r[f'outcome_{rule}']=='close' for r in fills)} | "
          f"{sum(rr):+.2f} | {(sum(rr)/n if n else 0):+.2f}")


for rule in ("day", "swing"):
    print(f"\n### {prefix}: {rule} rule. group | plans | filled | t1 | stop | close | sum R | avg R")
    for per in ("aggressive", "neutral", "conservative"):
        summ([r for r in out if r["matches_llm"] == 1 and r["persona"] == per], f"LLM direction, {per}", rule)
    for per in ("aggressive", "neutral", "conservative"):
        summ([r for r in out if r["matches_llm"] == 0 and r["persona"] == per], f"opposite direction, {per}", rule)
    for per in ("neutral",):
        for d in ("long", "short"):
            summ([r for r in out if r["direction"] == d and r["persona"] == per], f"both sides, {d}, {per}", rule)
    for t in ("SPY", "QQQ", "IWM"):
        summ([r for r in out if r["matches_llm"] == 1 and r["persona"] == "neutral" and r["ticker"] == t],
             f"LLM direction, neutral, {t}", rule)
