"""Rebuild the rule-decided half of the Insight report from local bars.

Runs the repo's own code (origin/main worktree) for every ticker and session:
  lib.indicators.calculate_premarket_context  -> premarket high / low / vwap
  lib.strat_levels.build_session_levels       -> trigger, ladder, stop anchor
  lib.strat.compute_strat_status              -> FTFC score
  lib.agents.trade_planner.compute_persona_plans -> entry / stop / targets / size
Writes one row per ticker, session and side to <out>/plans.csv and the daily
bars used to <out>/daily_{T}.csv.

Usage (cwd = worktree root):
  PYTHONPATH=platform:. python3 build_plans.py <out_dir> [cutoff HH:MM, default 08:20]
"""
import sys, glob, json, warnings, logging
from pathlib import Path
import pandas as pd

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)
from lib.indicators import calculate_atr, calculate_premarket_context
from lib.strat_levels import build_session_levels
from lib.strat import compute_strat_status
from lib.agents.trade_planner import PlanContext, compute_persona_plans

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
CUT = sys.argv[2] if len(sys.argv) > 2 else "08:20"
RAW = "/mnt/project-files/strat-verify/ftfc-replay/raw"
BARS = "/mnt/project-files/stocks-scorecard/inputs/bars_raw"
START, END = "2025-03-03", "2026-11-10"
rows = []
for t in ("SPY", "QQQ", "IWM"):
    a = pd.read_csv(f"{RAW}/{t}_daily_adjusted.csv", parse_dates=["timestamp"]).sort_values("timestamp")
    a = a.rename(columns={"timestamp": "date"}).set_index("date")[["open", "high", "low", "close"]]
    m = pd.concat([pd.read_csv(p, parse_dates=["timestamp"]) for p in sorted(glob.glob(f"{BARS}/{t}_1min_*.csv"))])
    m = m.drop_duplicates("timestamp").set_index("timestamp").sort_index()
    r = m.between_time("09:30", "15:59")
    g = r.groupby(r.index.normalize()).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                           close=("close", "last"), n=("close", "size"))
    g = g[g.n >= 200]
    # daily file through its last date, later sessions from the 1 minute regular session
    d = pd.concat([a, g.loc[g.index > a.index.max(), ["open", "high", "low", "close"]]]).sort_index()
    d.columns = ["Open", "High", "Low", "Close"]
    d["atr_14"] = calculate_atr(d.High, d.Low, d.Close, 14)
    d["sma_200"] = d.Close.rolling(200).mean()
    d[d.index >= "2024-01-01"].reset_index().rename(columns={"index": "date"}).to_csv(OUT / f"daily_{t}.csv", index=False)
    sessions = [x for x in g.index if START <= str(x.date()) <= END]
    pm_all = m.between_time("04:00", CUT, inclusive="left")
    pm_by = {k: v for k, v in pm_all.groupby(pm_all.index.normalize())}
    for ses in sessions:
        prior = d[d.index < ses]
        atr = float(prior.atr_14.iloc[-1]); pc = float(prior.Close.iloc[-1])
        sma = float(prior.sma_200.iloc[-1])
        pm = pm_by.get(ses)
        snap = None; ctx = {}
        if pm is not None and len(pm):
            p = pm.reset_index()
            ctx = calculate_premarket_context(p.timestamp, p.open, p.high, p.low, p.close, p.volume,
                                              prev_close=pc, atr14=atr, prev_open=float(prior.Open.iloc[-1]))
            snap = {"date": ses.date(), "pre_high": ctx["pre_high"], "pre_low": ctx["pre_low"],
                    "pre_vwap": ctx["pre_vwap"], "gap_pct": ctx["gap_pct"]}
        sl = build_session_levels(t, ses.date(), prior[["Open", "High", "Low", "Close"]], atr, snap)
        try:
            st = compute_strat_status(t, df=prior[["Open", "High", "Low", "Close"]].copy(), as_of=ses.date(),
                                      inclusive_today=False)
            ftfc = round(float(st.get("ftfc_score")), 2) if st.get("available") else None
        except Exception:
            ftfc = None
        for side in ("long", "short"):
            s = sl.side(side)
            row = dict(ticker=t, session=str(ses.date()), side=side, status=sl.status, atr=round(atr, 4),
                       prior_close=pc, sma_200=round(sma, 4), reference=sl.reference, ref_source=sl.reference_source,
                       pre_high=ctx.get("pre_high"), pre_low=ctx.get("pre_low"), pre_close=ctx.get("pre_close"),
                       gap_pct=ctx.get("gap_pct"), ftfc=ftfc, reason=s.reason,
                       trigger_name=s.trigger["name"] if s.trigger else None,
                       trigger=s.trigger["price"] if s.trigger else None,
                       trigger_aliases="|".join(s.trigger["aliases"]) if s.trigger else None,
                       stop_anchor=s.stop["price"] if s.stop else None,
                       stop_anchor_name=s.stop["name"] if s.stop else None,
                       rungs=json.dumps([[c["name"], c["price"]] for c in s.rungs]),
                       all_levels=json.dumps([[c["name"], c["price"], int(c["broken"]), int(c["in_window"])] for c in s.candidates]))
            plans = compute_persona_plans(PlanContext(direction=side, conviction="medium", close=pc, atr=atr,
                                                      levels=sl, sma_200=sma, ftfc_score=ftfc or 0.0))
            for p in plans:
                k = p.persona[:3]
                row[f"{k}_lo"] = p.entry_zone.low if p.entry_zone else None
                row[f"{k}_hi"] = p.entry_zone.high if p.entry_zone else None
                row[f"{k}_stop"] = p.stop
                row[f"{k}_targets"] = "|".join(str(x) for x in p.targets)
                row[f"{k}_size"] = p.position_size_pct
            rows.append(row)
    print(t, len(sessions), "sessions", flush=True)
df = pd.DataFrame(rows)
df.to_csv(OUT / "plans.csv", index=False)
print("rows", len(df), "sessions", df.session.nunique(), "cutoff", CUT)
print(df.groupby(["side"]).trigger_name.value_counts(dropna=False).to_string())
