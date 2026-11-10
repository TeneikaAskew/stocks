"""#1766 done_when 5 diagnostic: how one-minute wick excesses (the spike
rule's measure, lib.level_calibration.wick_excesses, divided by the prior
session's ATR(14)) are distributed in the regular session and in the
premarket, per ticker, over the 60 and 250 sessions before 2026-11-06.

Why: the calibrated pm_spike_atr (0.999 quantile of regular-session wicks)
came out near 0.07 ATR, which drops IWM's 269.13 premarket low (0.25 ATR
past its neighbours' bodies) that done_when 5 keeps. This shows where real
premarket wicks and the bad prints sit, to choose a method that separates
them. Reads only the cached exports; writes results/spike_diag.md and .json.

Usage: PYTHONPATH=platform:. python3 spike_diag.py <daily.csv> <minutes_dir> <out_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

import gcp.calibrate_level_params as job  # noqa: E402
from lib import level_calibration as lc  # noqa: E402

QS = (0.5, 0.9, 0.99, 0.995, 0.999, 0.9995, 1.0)
CUTS = (0.1, 0.25, 0.5, 0.75, 1.0, 1.5)


def excess_rows(g: pd.DataFrame, atr: float) -> pd.DataFrame:
    """Per bar and side: the wick excess / ATR with its time."""
    g = g.reset_index(drop=True)
    o, c, h, lo = g["open"], g["close"], g["high"], g["low"]
    bh, bl = np.maximum(o, c), np.minimum(o, c)
    nbh = pd.concat([bh.shift(s) for s in (-2, -1, 1, 2)], axis=1).max(axis=1)
    nbl = pd.concat([bl.shift(s) for s in (-2, -1, 1, 2)], axis=1).min(axis=1)
    up = np.minimum(h - bh, h - nbh) / atr
    dn = np.minimum(bl - lo, nbl - lo) / atr
    a = pd.DataFrame({"tod": g["tod"].astype(str), "field": "high", "x": up, "price": h})
    b = pd.DataFrame({"tod": g["tod"].astype(str), "field": "low", "x": dn, "price": lo})
    out = pd.concat([a, b])
    return out[np.isfinite(out["x"])]


def main(daily_csv: Path, minutes_dir: Path, out_dir: Path) -> None:
    export = common.load_daily_export(daily_csv)
    as_of = pd.Timestamp(common.AS_OF)
    md, js = ["# One-minute wick excess / prior ATR(14), regular session vs premarket", ""], {}
    for t in common.TICKERS:
        daily = common.daily_for_job(export, t)
        query = common.make_query({t: daily}, {t: common.load_minutes(minutes_dir / f"{t.lower()}.csv")})
        d = job.read_daily(query, t, "2014-01-01", (as_of + pd.Timedelta(days=1)).date())
        d = d.assign(session=pd.to_datetime(d["date"])).set_index("session")
        d["prior_atr"] = d["atr_14"].shift(1)
        m = lc.normalize_minutes(job.read_minutes(query, t, "2025-09-01", (as_of + pd.Timedelta(days=1)).date()),
                                 as_of.date())
        d = d[d.index < as_of]
        rth, pre = lc._rth(m), lc._premarket(m)
        js[t] = {}
        for n in (60, 250):
            sessions = d.index[-n:]
            rows = {"rth": [], "pre": []}
            per_session = []
            for s in sessions:
                atr = d.at[s, "prior_atr"]
                if not (atr == atr and atr > 0):
                    continue
                for name, src in (("rth", rth), ("pre", pre)):
                    g = src[src["session"] == s]
                    if len(g) >= 5:
                        e = excess_rows(g, float(atr)).assign(session=s.date().isoformat())
                        rows[name].append(e)
                        if name == "pre":
                            top = e.nlargest(3, "x")
                            per_session.append({"session": s.date().isoformat(), "bars": len(g),
                                                "top": [[r.tod[:5], r.field, round(float(r.price), 4), round(float(r.x), 3)]
                                                        for r in top.itertuples()]})
            res = {}
            for name in ("rth", "pre"):
                x = pd.concat(rows[name])["x"].to_numpy() if rows[name] else np.zeros(0)
                res[name] = {"wicks": int(len(x)), "q": {str(q): float(np.quantile(x, q)) if len(x) else None for q in QS},
                             "share_over": {str(c): float((x > c).mean()) if len(x) else None for c in CUTS}}
            res["pre_by_session"] = per_session
            js[t][str(n)] = res
            md += [f"## {t}, last {n} sessions before {common.AS_OF}", "",
                   "| population | wicks | " + " | ".join(f"q{q}" for q in QS) + " |",
                   "|---|---|" + "---|" * len(QS)]
            for name in ("rth", "pre"):
                r = res[name]
                md.append(f"| {name} | {r['wicks']} | " + " | ".join(
                    "" if r['q'][str(q)] is None else f"{r['q'][str(q)]:.3f}" for q in QS) + " |")
            md += ["", "Share of wicks past each multiple of ATR:", "",
                   "| population | " + " | ".join(str(c) for c in CUTS) + " |", "|---|" + "---|" * len(CUTS)]
            for name in ("rth", "pre"):
                r = res[name]
                md.append(f"| {name} | " + " | ".join(
                    "" if r['share_over'][str(c)] is None else f"{r['share_over'][str(c)]:.5f}" for c in CUTS) + " |")
            if n == 60:
                md += ["", "Largest three premarket wicks per session (time, field, price, excess ATR):", ""]
                md += [f"- {p['session']} ({p['bars']} bars): " + "; ".join(
                    f"{a} {b} {c} {x}" for a, b, c, x in p['top']) for p in per_session]
            md.append("")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "spike_diag.md").write_text("\n".join(md) + "\n")
    (out_dir / "spike_diag.json").write_text(json.dumps(js, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
