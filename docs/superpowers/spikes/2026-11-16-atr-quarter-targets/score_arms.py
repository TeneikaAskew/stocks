"""Score arm A (today's plan), arm Q (quarters at 0.25/0.50/0.75/1.00 ATR from the trigger) and arm Q3
(thirds at 0.25/0.50/0.75 ATR) on the locally replayed briefs.

Every trade is scored by the production gcp.premarket_playbook_resolver.resolve_plan on
plan_inputs(...) of the stored level_basis. This file walks no bars and computes no indicator:
it selects the bars of a session with the resolver's own SQL filter, hands PlanInputs to
resolve_plan, and for arms Q and Q3 replaces only `targets` and `legs` of the PlanInputs.
"""
import os, sys, json, dataclasses
sys.path.insert(0, "/tmp/spike-atr-targets")
assert os.environ.get("DB_HOST") == "127.0.0.1" and os.environ.get("DB_PORT") == "5544", "local database only"
import pandas as pd
from sqlalchemy import text
from gcp.database import get_engine
from gcp.premarket_playbook_resolver import resolve_plan, plan_inputs
from lib.strat_levels import parse_level_basis, SessionLevels
from lib.eastern_time import session_close, sessions_between

START, END, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
TICKERS = ("SPY", "QQQ", "IWM")
LEFT_OUT = {("SPY", "2025-04-09"), ("IWM", "2026-06-26")}
FRACS = (0.25, 0.50, 0.75, 1.00)
eng = get_engine()

# The resolver's RTH filter (gcp/premarket_playbook_resolver.py resolve_one), over the whole range.
BARS_SQL = text("""
    SELECT ts AS time, open, high, low, close,
           (ts AT TIME ZONE 'America/New_York')::date AS d
    FROM market_data_intraday
    WHERE ticker = :t
      AND (ts AT TIME ZONE 'America/New_York')::date BETWEEN :a AND :b
      AND (ts AT TIME ZONE 'America/New_York')::time >= '09:30'
      AND (ts AT TIME ZONE 'America/New_York')::time <  '16:00'
      AND interval = '1min'
    ORDER BY ts
""")
ROWS_SQL = text("""
    SELECT analysis_date, ticker, calls_trigger_price, calls_stop_price, calls_t1_price, calls_t2_price,
           calls_t3_price, puts_trigger_price, puts_stop_price, puts_t1_price, puts_t2_price, puts_t3_price,
           level_basis
    FROM premarket_analysis WHERE ticker = :t AND analysis_date BETWEEN :a AND :b ORDER BY analysis_date
""")

def no_policy():
    raise RuntimeError("a v3 basis never reads the policy tables")

def q(x):
    return None if x is None else round(float(x), 4)

out, skipped = [], []
for t in TICKERS:
    rows = pd.read_sql(ROWS_SQL, eng, params={"t": t, "a": START, "b": END})
    bars_all = pd.read_sql(BARS_SQL, eng, params={"t": t, "a": START, "b": END})
    bars_all["time"] = pd.to_datetime(bars_all["time"], utc=True)
    by_day = {str(d): g.drop(columns="d").reset_index(drop=True) for d, g in bars_all.groupby("d")}
    have = {str(d) for d in rows["analysis_date"]}
    for d in sessions_between(START, END):
        if d.isoformat() not in have:
            skipped.append((t, d.isoformat(), "no_brief_row"))
    for _, row in rows.iterrows():
        day = str(row["analysis_date"])
        if (t, day) in LEFT_OUT:
            skipped.append((t, day, "left_out")); continue
        bars = by_day.get(day)
        if bars is None or bars.empty:
            skipped.append((t, day, "no_bars")); continue
        basis = parse_level_basis(row.get("level_basis"))
        if basis is None:
            skipped.append((t, day, "no_basis")); continue
        # The plan's walk ends at the exchange's close (resolve_one does the same cut).
        close_utc = pd.Timestamp(session_close(pd.Timestamp(day).date()))
        plan_bars = bars[bars["time"] < close_utc].reset_index(drop=True)
        sl = SessionLevels.from_basis(basis)
        res = {}
        for side, direction in (("calls", "call"), ("puts", "put")):
            p = plan_inputs(side, row, basis, no_policy)
            res[side] = (p, resolve_plan(direction, p, plan_bars))
        st = {s: res[s][1].entry_status for s in res}
        entered = [s for s in res if st[s] == "entered"]
        opened = [s for s in res if st[s] == "opened_through"]
        pick, why = None, None
        if len(entered) == 2:
            a, b = res["calls"][1].fill_ts, res["puts"][1].fill_ts
            if a == b: why = "same_bar_tie"
            else: pick = "calls" if a < b else "puts"
        elif len(entered) == 1:
            pick = entered[0]
        else:
            why = "no_entry"
        rec = {"ticker": t, "date": day, "calls_status": st["calls"], "puts_status": st["puts"],
               "any_opened_through": bool(opened), "pick": pick, "no_trade_reason": why,
               "atr": sl.atr, "atr_basis": sl.atr_basis, "reference": sl.reference,
               "reference_source": sl.reference_source, "prior_close": sl.prior_close,
               "premarket_status": sl.premarket_status, "open": float(plan_bars["open"].iloc[0]),
               "n_bars": len(plan_bars), "last_bar": str(plan_bars["time"].iloc[-1])}
        if pick:
            p, o = res[pick]
            direction = "call" if pick == "calls" else "put"
            sign = 1 if pick == "calls" else -1
            rec.update({"side": pick, "trigger": p.trigger_price, "stop": p.stop_price, "fill": o.fill_price,
                        "fill_ts": str(o.fill_ts), "a_status": o.r_status, "a_r": o.r, "a_exit": o.exit,
                        "a_targets": json.dumps(list(p.targets)), "a_legs": p.legs,
                        "a_target_status": p.target_status, "cutoff": p.cutoff_minutes})
            if sl.atr and p.trigger_price:
                tg = tuple(round(p.trigger_price + sign * f * sl.atr, 2) for f in FRACS)
                rec["q_targets"] = json.dumps(list(tg))
                # Arm Q and Q3: only targets and legs change; a side with no published plan gets a
                # usable target_status so the ATR targets can be scored on the same trigger and stop.
                base = dataclasses.replace(p, target_status="ok",
                                           cutoff_minutes=p.cutoff_minutes if p.cutoff_minutes is not None else 960)
                oq = resolve_plan(direction, dataclasses.replace(base, targets=tg, legs=4), plan_bars)
                o3 = resolve_plan(direction, dataclasses.replace(base, targets=tg[:3], legs=3), plan_bars)
                rec.update({"q_status": oq.r_status, "q_r": oq.r, "q_exit": oq.exit, "q_fill": oq.fill_price,
                            "q3_status": o3.r_status, "q3_r": o3.r, "q3_exit": o3.exit})
                lv = [(l.name, float(l.price), l.level_type) for l in sl.levels if l.price is not None]
                near = []
                for k, tp in enumerate(tg, 1):
                    hit = [(n, px) for n, px, _ in lv if 0 < round(sign * (tp - px), 4) <= 0.05]
                    near.append([f"{n}@{px}" for n, px in hit])
                rec["q_near_levels"] = json.dumps(near)
        out.append(rec)
    print(t, "rows", len(rows), "scored days", sum(1 for r in out if r["ticker"] == t), flush=True)
df = pd.DataFrame(out)
df.to_csv(OUT, index=False)
pd.DataFrame(skipped, columns=["ticker", "date", "why"]).to_csv(OUT.replace(".csv", "_skipped.csv"), index=False)
print("days", len(df), "picked", int(df["pick"].notna().sum()), "skipped", len(skipped))
