"""Score every persona plan in exported insight_reports rows against 1-min bars.

Read-only research. Usage:
  python3 -I score_insights.py <insight_reports.csv> <bars_raw_dir> <out_dir>

Rule (identical for every persona, ticker and day):
  * Session = regular hours 09:30 to 15:59 ET bars (bar start stamps).
  * Fill: the first RTH bar on the report's session whose range touches the
    entry zone [low, high]. Fill price: the bar open if the open is inside the
    zone, else the zone edge price crossed into (entry low when coming from
    below, entry high when coming from above). No fill = no trade.
  * Risk R = |fill - stop|. A stop on the wrong side of the fill = invalid.
  * After the fill (the fill bar included), each bar is checked for the stop
    and for T1. If one bar touches both, the stop is counted first.
    Stop exits at the stop price, or at the bar open when the bar gapped past it.
  * Day rule (primary): exit at the 15:59 bar close if neither hit. R at close.
  * Swing rule (secondary, the reports say time_horizon=swing): same fill on
    day 1, stop or T1 checked across up to 5 sessions (day 1 plus 4), exit at
    the last available close. Truncated when bars end (Nov 10).
  * MFE in R (best excursion before stop or end) tells how far toward T2/T3
    price went.
  * position_size_pct is reported, and a size-weighted R is computed; a size 0
    plan (conservative standing aside) is still scored as a shadow trade.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

csv.field_size_limit(10**9)


def load_reports(path):
    rows = [json.loads(r["row"]) for r in csv.DictReader(open(path))]
    out = []
    for r in rows:
        rep = r["report"] if isinstance(r["report"], dict) else json.loads(r["report"])
        asof = datetime.fromisoformat(r["as_of"])
        # Report is written premarket; ET offset: EDT until 2026-11-01, EST after.
        et_off = -4 if asof.date() < datetime(2026, 11, 1).date() else -5
        et = asof + timedelta(hours=et_off)
        out.append(dict(id=r["id"], ticker=r["ticker"], as_of=r["as_of"],
                        session=et.date().isoformat(), et_time=et.strftime("%H:%M"),
                        rep=rep, models=r.get("model_versions"), cost=r.get("cost_usd")))
    return out


def load_bars(bars_dir, ticker):
    days = defaultdict(list)
    for fn in sorted(os.listdir(bars_dir)):
        if not fn.startswith(ticker + "_1min_2026-1"):
            continue
        for row in csv.DictReader(open(os.path.join(bars_dir, fn))):
            ts = row["timestamp"]
            d, t = ts[:10], ts[11:16]
            if "09:30" <= t <= "15:59":
                days[d].append((t, float(row["open"]), float(row["high"]),
                                float(row["low"]), float(row["close"])))
    return {d: sorted(v) for d, v in days.items()}


def simulate(bars_by_day, sessions, direction, lo, hi, stop, t1, fill_days=1):
    """bars_by_day: list of bar lists, first is the report session.
    fill_days: how many sessions the entry zone stays live (1 = report day only)."""
    sign = 1 if direction == "long" else -1
    res = dict(filled=False, fill_time=None, fill_px=None, outcome="no_fill",
               exit_px=None, r=None, mfe_r=None, exit_day=None, fill_day=None)
    fd = 0
    for fd in range(min(fill_days, len(bars_by_day))):
        if any(l <= hi and h >= lo for (_, _, h, l, _) in bars_by_day[fd]):
            break
    else:
        return res
    bars_by_day, sessions = bars_by_day[fd:], sessions[fd:]
    res["fill_day"] = sessions[0]
    day1 = bars_by_day[0]
    fill_i = None
    for i, (t, o, h, l, c) in enumerate(day1):
        if l <= hi and h >= lo:
            if lo <= o <= hi:
                px = o
            elif o < lo:
                px = lo
            else:
                px = hi
            res.update(filled=True, fill_time=t, fill_px=round(px, 4))
            fill_i = i
            break
    if fill_i is None:
        return res
    fill = res["fill_px"]
    risk = (fill - stop) * sign
    if risk <= 0:
        res["outcome"] = "invalid_stop"
        return res
    mfe = 0.0
    seq = [(0, b) for b in day1[fill_i:]]
    for k, day in enumerate(bars_by_day[1:], start=1):
        seq += [(k, b) for b in day]
    last = None
    for k, (t, o, h, l, c) in seq:
        fav = (h - fill) if sign > 0 else (fill - l)
        adv_hit = (l <= stop) if sign > 0 else (h >= stop)
        tgt_hit = (h >= t1) if sign > 0 else (l <= t1)
        if adv_hit:
            gap = (o < stop) if sign > 0 else (o > stop)
            px = o if gap else stop
            res.update(outcome="stop", exit_px=px, r=round((px - fill) * sign / risk, 3),
                       mfe_r=round(max(mfe, 0) / risk, 3), exit_day=sessions[k])
            return res
        mfe = max(mfe, fav)
        if tgt_hit:
            gap = (o > t1) if sign > 0 else (o < t1)
            px = o if gap else t1
            res.update(outcome="t1", exit_px=px, r=round((px - fill) * sign / risk, 3),
                       mfe_r=round(mfe / risk, 3), exit_day=sessions[k])
            return res
        last = (k, c)
    k, c = last
    res.update(outcome="close", exit_px=c, r=round((c - fill) * sign / risk, 3),
               mfe_r=round(mfe / risk, 3), exit_day=sessions[k])
    return res


def load_atr_prev(mdd_path):
    """ATR(14) of the session before each date, from market_data_daily rows."""
    by_t = defaultdict(dict)
    for x in csv.DictReader(open(mdd_path)):
        r = json.loads(x["row"])
        if r.get("ticker") in ("SPY", "QQQ", "IWM") and r.get("atr_14"):
            by_t[r["ticker"]][r["date"]] = float(r["atr_14"])
    out = {}
    for t, m in by_t.items():
        ds = sorted(m)
        for i in range(1, len(ds)):
            out[(t, ds[i])] = m[ds[i - 1]]
        # a session after the last stored date uses the last stored ATR
        out[(t, "next:" + ds[-1])] = m[ds[-1]]
    return out


def main(rep_path, bars_dir, out_dir, mdd_path=None):
    reports = load_reports(rep_path)
    atr_prev = load_atr_prev(mdd_path) if mdd_path else {}
    bars = {t: load_bars(bars_dir, t) for t in ("SPY", "QQQ", "IWM")}
    # canonical = latest premarket row per (ticker, session); duplicates kept, flagged
    latest = {}
    for r in reports:
        key = (r["ticker"], r["session"])
        if key not in latest or r["as_of"] > latest[key]["as_of"]:
            latest[key] = r
    out = []
    for r in sorted(reports, key=lambda x: (x["session"], x["ticker"], x["as_of"])):
        tk, ses, rep = r["ticker"], r["session"], r["rep"]
        all_days = sorted(bars[tk])
        if ses not in bars[tk]:
            continue
        i = all_days.index(ses)
        d1 = bars[tk][ses]
        prev_close = bars[tk][all_days[i - 1]][-1][4] if i > 0 else None
        day_open, day_close = d1[0][1], d1[-1][4]
        swing_days = all_days[i:i + 5]
        swing_close = bars[tk][swing_days[-1]][-1][4]
        canonical = latest[(tk, ses)]["id"] == r["id"]
        for p in rep.get("persona_plans", []):
            base = dict(report_id=r["id"], canonical=int(canonical), session=ses,
                        report_et=r["et_time"], ticker=tk, direction=rep["direction"],
                        conviction=rep["conviction"], report_regime=rep["regime"],
                        persona=p["persona"], plan_regime=p["regime"],
                        size=p["position_size_pct"], prev_close=prev_close,
                        day_open=day_open, day_close=day_close,
                        dir_correct_vs_prev_close=None, dir_correct_5d=None)
            sign = 1 if rep["direction"] == "long" else -1
            if prev_close:
                base["dir_correct_vs_prev_close"] = int((day_close - prev_close) * sign > 0)
                base["dir_correct_5d"] = int((swing_close - prev_close) * sign > 0)
            ez = p.get("entry_zone")
            if not ez or p.get("stop") is None or not p.get("targets"):
                base.update(outcome_day="no_plan", outcome_swing="no_plan")
                out.append(base)
                continue
            lo, hi, stop, t1 = ez["low"], ez["high"], p["stop"], p["targets"][0]
            ref = prev_close or day_open
            base.update(entry_lo=lo, entry_hi=hi, stop=stop, t1=t1,
                        targets="|".join(str(x) for x in p["targets"]),
                        entry_dist_atr_note=p.get("rationale", "")[:80],
                        entry_vs_prevclose_pct=round((((lo + hi) / 2) / ref - 1) * 100, 2))
            dres = simulate([d1], [ses], rep["direction"], lo, hi, stop, t1)
            sres = simulate([bars[tk][d] for d in swing_days], swing_days,
                            rep["direction"], lo, hi, stop, t1)
            fres = simulate([bars[tk][d] for d in swing_days], swing_days,
                            rep["direction"], lo, hi, stop, t1, fill_days=5)
            for k in ("outcome", "r", "fill_day", "exit_day"):
                base[f"{k}_fill5"] = fres[k]
            atr = atr_prev.get((tk, ses))
            if atr:
                base["atr14_prev"] = round(atr, 3)
                base["entry_dist_atr"] = round(abs((lo + hi) / 2 - ref) / atr, 2)
                base["stop_dist_atr"] = round(abs((lo + hi) / 2 - stop) / atr, 2)
            for k, v in dres.items():
                base[f"{k}_day"] = v
            for k in ("outcome", "exit_px", "r", "mfe_r", "exit_day"):
                base[f"{k}_swing"] = sres[k]
            base["swing_sessions"] = len(swing_days)
            base["size_weighted_r_day"] = (round(dres["r"] * p["position_size_pct"], 3)
                                           if dres["r"] is not None else None)
            out.append(base)
    os.makedirs(out_dir, exist_ok=True)
    cols = []
    for row in out:
        for k in row:
            if k not in cols:
                cols.append(k)
    with open(os.path.join(out_dir, "persona_outcomes.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out)
    print(f"wrote {len(out)} persona rows")


if __name__ == "__main__":
    main(*sys.argv[1:5])
