"""#1766 done_when 14: compares picks.py's output from the #1766 worktree
with the origin/main (#1753 as merged) output, session by session.

Usage: python3 diff.py <main.jsonl.gz> <branch.jsonl.gz> <out_dir>
Writes out_dir/pick_changes.md and pick_changes.json.
"""
from __future__ import annotations

import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

SIDES = ("long", "short")
PERSONAS = ("aggressive", "neutral", "conservative")
TICKERS = ("SPY", "QQQ", "IWM")


def load(path: Path) -> dict:
    with gzip.open(path, "rt") as f:
        return {(r["ticker"], r["session"], r["mode"]): r for r in map(json.loads, f)}


def nth(xs, i):
    return xs[i] if xs and len(xs) > i else None


def side_changes(a: dict, b: dict) -> dict:
    return {"trigger": a["trigger"] != b["trigger"], "stop": a["stop"] != b["stop"],
            "t1": nth(a["targets"], 0) != nth(b["targets"], 0),
            "t2": nth(a["targets"], 1) != nth(b["targets"], 1),
            "t3": nth(a["targets"], 2) != nth(b["targets"], 2),
            "orb_only": (a["trigger"] is None) != (b["trigger"] is None)}


def plan_changes(a: dict, b: dict) -> dict:
    if "error" in a or "error" in b:
        return {"error": True}
    out = {}
    for p in PERSONAS:
        x, y = a.get(p) or {}, b.get(p) or {}
        out[p] = {"entry": x.get("entry") != y.get("entry"), "stop": x.get("stop") != y.get("stop"),
                  "targets": x.get("targets") != y.get("targets")}
    return out


def side_text(s: dict) -> str:
    if s["trigger"] is None:
        return f"orb_only ({s['reason']})"
    t = ", ".join(f"{x:.2f}" for x in s["targets"]) or "none"
    stop = "none" if s["stop"] is None else f"{s['stop']:.2f}"
    return f"{s['trigger']}, stop {stop}, T {t}"


def main(main_path: Path, branch_path: Path, out_dir: Path) -> None:
    old, new = load(main_path), load(branch_path)
    keys = sorted(set(old) & set(new))
    missing = sorted(set(old) ^ set(new))
    counts = defaultdict(lambda: defaultdict(int))
    plans = defaultdict(lambda: defaultdict(int))
    for k in keys:
        t, s, mode = k
        a, b = old[k], new[k]
        for side in SIDES:
            c = side_changes(a[side], b[side])
            row = counts[(mode, t, side)]
            row["sessions"] += 1
            for f, v in c.items():
                row[f] += int(v)
            row["any"] += int(any(c[f] for f in ("trigger", "stop", "t1", "t2", "t3", "orb_only")))
            row["orb_only_main"] += int(a[side]["trigger"] is None)
            row["orb_only_branch"] += int(b[side]["trigger"] is None)
        for direction in SIDES:
            pc = plan_changes(a["plans"][direction], b["plans"][direction])
            if "error" in pc:
                plans[(mode, t, direction, "all")]["error"] += 1
                continue
            for p, c in pc.items():
                row = plans[(mode, t, direction, p)]
                row["plans"] += 1
                for f, v in c.items():
                    row[f] += int(v)
                row["any"] += int(any(c.values()))
        if a["premarket"] != b["premarket"]:
            counts[(mode, t, "premarket")][f"{a['premarket']} -> {b['premarket']}"] += 1

    md = ["# #1766 pick changes against #1753 (origin/main), 2015-01-02 to 2026-11-06", ""]
    if missing:
        md += [f"{len(missing)} session keys are in one run only (first: {missing[0]})", ""]
    for mode, title in (("stored", "Stored premarket rows (production today; #1766 refuses unfiltered rows)"),
                        ("none", "No premarket snapshot on either side (level code and parameters only)")):
        md += [f"## {title}", "", "Sessions whose pick changed, per ticker and side:", "",
               "| ticker | side | sessions | trigger | stop | T1 | T2 | T3 | any | orb_only state | orb_only #1753 | orb_only #1766 |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for t in TICKERS:
            for side in SIDES:
                r = counts[(mode, t, side)]
                md.append(f"| {t} | {side} | {r['sessions']} | {r['trigger']} | {r['stop']} | {r['t1']} | {r['t2']} | "
                          f"{r['t3']} | {r['any']} | {r['orb_only']} | {r['orb_only_main']} | {r['orb_only_branch']} |")
        pm = {t: dict(counts[(mode, t, "premarket")]) for t in TICKERS if counts[(mode, t, "premarket")]}
        if pm:
            md += ["", "Premarket status changes: " + "; ".join(
                f"{t} " + ", ".join(f"{k} {v}" for k, v in d.items()) for t, d in pm.items())]
        md += ["", "Persona plans that changed, per ticker, direction and persona:", "",
               "| ticker | direction | persona | plans | entry zone | stop | targets | any |", "|---|---|---|---|---|---|---|---|"]
        for t in TICKERS:
            for direction in SIDES:
                err = plans[(mode, t, direction, "all")]["error"]
                for p in PERSONAS:
                    r = plans[(mode, t, direction, p)]
                    md.append(f"| {t} | {direction} | {p} | {r['plans']} | {r['entry']} | {r['stop']} | "
                              f"{r['targets']} | {r['any']} |")
                if err:
                    md.append(f"| {t} | {direction} | (planner raised on either side) | {err} | | | | |")
        md += ["", "The 20 sessions through 2026-11-06, before (#1753) and after (#1766):", "",
               "| ticker | session | side | #1753 | #1766 |", "|---|---|---|---|---|"]
        for t in TICKERS:
            for k in [k for k in keys if k[0] == t and k[2] == mode][-20:]:
                for side in SIDES:
                    a, b = old[k][side], new[k][side]
                    md.append(f"| {t} | {k[1]} | {side} | {side_text(a)} | {side_text(b)} |")
        md.append("")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pick_changes.md").write_text("\n".join(md) + "\n")
    (out_dir / "pick_changes.json").write_text(json.dumps({
        "sides": {"|".join(k): v for k, v in counts.items()},
        "plans": {"|".join(k): v for k, v in plans.items()},
        "last_20": {f"{t}|{mode}": [{"session": k[1], "main": {s: old[k][s] for s in SIDES},
                                      "branch": {s: new[k][s] for s in SIDES}}
                                     for k in [k for k in keys if k[0] == t and k[2] == mode][-20:]]
                    for t in TICKERS for mode in ("stored", "none")}}, indent=1))
    print("\n".join(md[:60]))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
