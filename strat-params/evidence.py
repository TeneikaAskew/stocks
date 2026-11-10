"""#1766 done_when 4: for SPY, QQQ and IWM as of 2026-11-06, every
parameter's calibrated value, sample and input range beside the #1753
constant it replaces, and the evidence row Design 2 names for it:
- trigger windows: per year, the share of sessions whose excursion passed the window;
- premarket thresholds: every bar each threshold drops on the 20 sessions through 2026-11-06;
- break-derived values: break counts per side and year.

Usage (from a #1766 worktree, after calib.py):
  PYTHONPATH=platform:. python3 <this dir>/evidence.py <daily.csv> <minutes_dir> <calib_out_dir>
Writes calib_out_dir/evidence.md and evidence.json. Reads exports only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

from gcp import calibrate_level_params as job  # noqa: E402
from lib import level_calibration as lc  # noqa: E402

LEGACY_1753 = {  # tests/lib/level_params_fixtures.py LEGACY_1753_VALUES
    "trigger_window_long_atr": 3.0, "trigger_window_short_atr": 3.0, "pm_spike_atr": 0.5,
    "pm_stale_print_atr": 0.1, "level_cluster_atr": 0.15,
    "entry_buffer_aggressive_lo_atr": 0.0, "entry_buffer_aggressive_hi_atr": 0.5,
    "entry_buffer_neutral_lo_atr": 0.0, "entry_buffer_neutral_hi_atr": 0.25,
    "entry_buffer_conservative_lo_atr": 0.1, "entry_buffer_conservative_hi_atr": 0.4,
    "stop_aggressive_atr": 2.0, "stop_neutral_atr": 1.0, "stop_conservative_atr": 0.7,
    "min_stop_atr": 0.5, "target_aggressive_1_r": 2.0, "target_aggressive_2_r": 3.5,
    "target_aggressive_3_r": 5.0, "target_neutral_1_r": 1.0, "target_neutral_2_r": 2.0,
    "target_neutral_3_r": 3.0, "target_conservative_1_r": 1.0, "target_conservative_2_r": 1.75,
}


def fmt(v, nd=4):
    return "" if v is None or (isinstance(v, float) and v != v) else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def main(daily_csv: Path, minutes_dir: Path, calib_dir: Path) -> None:
    inforce = json.loads((calib_dir / f"in_force_{common.AS_OF}.json").read_text())
    export = common.load_daily_export(daily_csv)
    daily = {t: common.daily_for_job(export, t) for t in common.TICKERS}
    minutes_raw = {t: common.load_minutes(minutes_dir / f"{t.lower()}.csv") for t in common.TICKERS}
    query = common.make_query(daily, minutes_raw)
    as_of = pd.Timestamp(common.AS_OF)
    policy = job.policy_on(common.policy_rows(), as_of)
    basis = lc.policy_atr_basis(policy)
    md, js = [f"# #1766 calibrated evidence as of {common.AS_OF} (run {inforce['run_id']})", ""], {}
    for t in common.TICKERS:
        p = inforce["tickers"][t]
        d_raw = job.read_daily(query, t, "2014-01-01", (as_of + pd.Timedelta(days=1)).date())
        m_et = job.read_minutes(query, t, "2014-10-01", (as_of + pd.Timedelta(days=1)).date())
        md += [f"## {t}", "", "| key | calibrated | status | sample | input | #1753 |", "|---|---|---|---|---|---|"]
        for k in LEGACY_1753:
            r = p.get(k, {})
            md.append(f"| {k} | {fmt(r.get('value'))} | {r.get('status')} | {r.get('sample_n')} | "
                      f"{r.get('input_from')} to {r.get('input_to')} | {LEGACY_1753[k]} |")
        js[t] = {"params": p}
        # trigger windows
        for side in lc.SIDES:
            key = f"trigger_window_{side}_atr"
            w = p.get(key, {}).get("value")
            if w is None:
                continue
            ex = lc.window_exceedance_by_year(d_raw, basis, as_of, side, float(w))
            legacy = lc.window_exceedance_by_year(d_raw, basis, as_of, side, LEGACY_1753[key])
            ex = ex.merge(legacy[["year", "share"]].rename(columns={"share": "share_at_1753"}), on="year")
            js[t][f"window_{side}"] = ex.to_dict("records")
            md += ["", f"{side} window {float(w):.3f} x ATR: share of sessions whose excursion passed it, per year "
                   f"(and at the #1753 3.0):", "", "| year | sessions | passed | share | share at 3.0 |", "|---|---|---|---|---|"]
            md += [f"| {r['year']} | {r['sessions']} | {r['passed']} | {r['share']:.3f} | {r['share_at_1753']:.3f} |"
                   for r in ex.to_dict("records")]
        # premarket thresholds on the 20 sessions through AS_OF
        sessions = [pd.Timestamp(s) for s in sorted(set(pd.to_datetime(d_raw["date"])))
                    if pd.Timestamp(s) <= as_of][-20:]
        stale = p.get("pm_stale_print_atr", {}).get("value")
        spike = p.get("pm_spike_atr", {}).get("value")
        for label, sv, kv in (("calibrated", stale, spike), ("#1753", LEGACY_1753["pm_stale_print_atr"],
                                                             LEGACY_1753["pm_spike_atr"])):
            if sv is None or kv is None:
                md += ["", f"premarket drops ({label}): threshold not ok, no filter"]
                continue
            dr = lc.premarket_drops(d_raw, m_et, basis, sessions, stale_print_atr=float(sv), spike_atr=float(kv))
            js[t][f"premarket_drops_{label}"] = dr.astype(str).to_dict("records")
            md += ["", f"premarket drops, 20 sessions through {common.AS_OF}, {label} (stale {float(sv):.4f}, "
                   f"spike {float(kv):.4f} x ATR): {len(dr)} prints", "", "| session | time ET | field | price | rule |",
                   "|---|---|---|---|---|"]
            md += [f"| {r['session']} | {pd.Timestamp(r['timestamp']).strftime('%H:%M')} | {r['field']} | "
                   f"{r['price']:.4f} | {r['rule']} |" for r in dr.to_dict("records")]
        # break counts per side and year, under the policy in force on AS_OF
        dn = lc.normalize_daily(d_raw, basis, as_of)
        mn = lc.normalize_minutes(m_et, as_of)
        msess = set(mn["session"].unique()) if len(mn) else set()
        sess = [s for s in dn.index if s in msess]
        trig = lc.replay_triggers(t, lc.daily_before(d_raw, as_of), dn, policy, sess, basis)
        bc = lc.break_counts_by_year(lc.find_breaks(dn, mn, trig))
        js[t]["break_counts"] = bc.to_dict("records")
        md += ["", "breaks per side and year (sessions with one-minute bars):", "",
               "| side | year | breaks | held |", "|---|---|---|---|"]
        md += [f"| {r['side']} | {r['year']} | {r['breaks']} | {r['held']} |" for r in bc.to_dict("records")]
        md.append("")
        print(t, "done", file=sys.stderr, flush=True)
    (calib_dir / "evidence.md").write_text("\n".join(md) + "\n")
    (calib_dir / "evidence.json").write_text(json.dumps(js, indent=1, default=str))
    print("\n".join(md))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
