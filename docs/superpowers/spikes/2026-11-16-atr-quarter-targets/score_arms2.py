"""Follow-up arms B1, B2, B3, Q2 beside A, Q, Q3, from the saved replay (premarket_analysis_v1.csv.gz) and the
local copy of the bucket bars. No database. Every trade is scored by production resolve_plan on plan_inputs of
the stored level_basis; only `targets` and `legs` of the PlanInputs change per arm. An unpriced leg that is not
the last is passed as the trigger price: resolve_plan holds a leg whose target is at or behind the fill."""
import sys, json, dataclasses, datetime as dt
sys.path.insert(0, "/tmp/spike-atr-targets")
import pandas as pd
from gcp.premarket_playbook_resolver import resolve_plan, plan_inputs
from gcp.fetchers.export_intraday_bars import read_bars
from lib.strat_levels import parse_level_basis, SessionLevels
from lib.eastern_time import session_close
EXTRACT, BARS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
LEFT_OUT = {("SPY", "2025-04-09"), ("IWM", "2026-06-26")}
rows_all = pd.read_csv(EXTRACT)
def no_policy(): raise RuntimeError("v3 basis only")
out = []
for t in ("SPY", "QQQ", "IWM"):
    bars, _ = read_bars(BARS, t, "2022-01", "2026-11")
    et = bars["ts"].dt.tz_convert("America/New_York")
    # the resolver's RTH filter: Eastern time >= 09:30 and < 16:00
    keep = (et.dt.time >= dt.time(9, 30)) & (et.dt.time < dt.time(16, 0))
    b = bars.loc[keep, ["ts", "open", "high", "low", "close"]].rename(columns={"ts": "time"})
    b["d"] = et[keep].dt.strftime("%Y-%m-%d")
    by_day = {d: g.drop(columns="d").reset_index(drop=True) for d, g in b.groupby("d")}
    for _, row in rows_all[rows_all.ticker == t].iterrows():
        day = str(row["analysis_date"])
        if (t, day) in LEFT_OUT or day not in by_day: continue
        basis = parse_level_basis(row["level_basis"])
        pb = by_day[day]; pb = pb[pb["time"] < pd.Timestamp(session_close(pd.Timestamp(day).date()))].reset_index(drop=True)
        sl = SessionLevels.from_basis(basis)
        res = {s: (p := plan_inputs(s, row, basis, no_policy), resolve_plan(d_, p, pb)) for s, d_ in (("calls", "call"), ("puts", "put"))}
        ent = [s for s in res if res[s][1].entry_status == "entered"]
        if len(ent) == 2:
            a, c = res["calls"][1].fill_ts, res["puts"][1].fill_ts
            if a == c: continue
            pick = "calls" if a < c else "puts"
        elif len(ent) == 1: pick = ent[0]
        else: continue
        p, o = res[pick]; direction = "call" if pick == "calls" else "put"; sign = 1 if pick == "calls" else -1
        trig, atr = p.trigger_price, sl.atr
        m = [round(trig + sign * f * atr, 2) for f in (0.25, 0.50, 0.75, 1.00)]
        A = list(p.targets)
        beyond = lambda x, ref: sign * (x - ref) > 0
        HOLD = trig     # at or behind the fill: resolve_plan holds the leg
        b1_lv = [x for x in A if beyond(x, m[1])][:2]
        cand = A[1:3] if len(A) >= 3 else A[:2]         # B2: A's T2,T3 when A has three, else A's T1,T2
        b2, prev = [], m[1]
        for x in cand:
            if beyond(x, prev): b2.append(x); prev = x
            else: b2.append(HOLD)
        b3_lv = [x for x in A if beyond(x, m[0])][:1]
        arms = {"A": (A, p.legs), "Q": (m, 4), "Q3": (m[:3], 3), "Q2": (m[:3], 4),
                "B1": (m[:2] + b1_lv, 4), "B2": (m[:2] + b2, 4), "B3": ([m[0]] + b3_lv, 2)}
        rec = {"ticker": t, "date": day, "side": pick, "fill_ts": str(o.fill_ts), "trigger": trig, "stop": p.stop_price,
               "fill": o.fill_price, "atr": atr, "a_n_targets": len(A), "b1_levels": len(b1_lv),
               "b2_priced": sum(1 for x in b2 if x != HOLD), "b3_levels": len(b3_lv)}
        for name, (tg, legs) in arms.items():
            r = o if name == "A" else resolve_plan(direction, dataclasses.replace(p, targets=tuple(tg), legs=legs), pb)
            assert r.r_status == "ok" and r.fill_price == o.fill_price
            rec[f"{name}_r"], rec[f"{name}_exit"], rec[f"{name}_targets"] = r.r, r.exit, json.dumps(list(tg))
        out.append(rec)
    print(t, sum(1 for r in out if r["ticker"] == t), flush=True)
pd.DataFrame(out).to_csv(OUT, index=False)
