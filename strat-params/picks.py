"""#1766 done_when 14, one side of the comparison. Runs unchanged in a #1766
worktree (per-ticker parameters) and in an origin/main worktree (#1753 as
merged), and records for SPY, QQQ and IWM, every session 2015-01-02 to
2026-11-06, what the brief's own path picks:

- per side: the trigger (name and cent), stop, T1, T2, T3 and the orb_only reason;
- per direction (long, short) and persona: the plan's entry zone, stop and targets.

The path is the brief's (gcp/premarket_brief.py): DataLoader.load_daily with
its SQL answered from the read-only export, premarket_snapshot_from_daily
for the session's own row, the cut to bars before the session, the last
completed session's ATR, build_session_levels, then
lib.agents.trade_planner.compute_persona_plans on those levels. On #1766 the
parameters are the ones in force on each session, read with
load_level_params from calib.py's history-mode rows (ticker_level_params.csv.gz).

Two premarket modes, both recorded:
- stored: the session's stored premarket row as production holds it today.
  Those rows carry no pre_filter_status, so #1766 refuses them
  (premarket_unfiltered) until the fetchers write filtered rows.
- none: no premarket snapshot on either side, so both anchor on the prior
  close and only the level code and parameters differ.

The planner context is the same on both sides: conviction medium, ftfc 0,
no catalyst, the prior close and SMA(200); only the levels differ.

Usage: PYTHONPATH=platform:<worktree> python3 picks.py <daily.csv> <out.jsonl.gz> [ticker_level_params.csv.gz]
Writes nothing anywhere else and posts nothing.
"""
from __future__ import annotations

import gzip
import inspect
import json
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

import lib.data_loader as dl  # noqa: E402
from lib import strat_levels as sl_mod  # noqa: E402
from lib.agents import trade_planner as tp  # noqa: E402

import os  # noqa: E402

START = date.fromisoformat(os.environ.get("PICKS_START", "2015-01-02"))
END = date(2026, 11, 6)
BRANCH = "params" in inspect.signature(sl_mod.build_session_levels).parameters


def install_csv_answer(export: pd.DataFrame):
    from lib.indicators import calculate_atr  # noqa: PLC0415
    frames = {}
    for t, g in export.groupby("ticker"):
        g = g.sort_values("date").reset_index(drop=True)
        g["atr_5"] = calculate_atr(g["High"], g["Low"], g["Close"], 5).to_numpy()
        frames[t] = g

    def fake_query(sql, params=None):
        if "pre_fetched_at" in sql:
            return pd.DataFrame()  # production has no provenance columns yet
        t = (params or {}).get("ticker")
        g = frames[t].drop(columns=["ticker"])
        if "atr_5" not in sql:
            g = g.drop(columns=["atr_5"])
        return g.reset_index(drop=True)
    dl._query_cloud_sql = fake_query
    dl._cloud_sql_active = lambda: True
    dl._PREMARKET_PROVENANCE_PRESENT = None
    if hasattr(dl, "_ATR5_PRESENT"):
        dl._ATR5_PRESENT = None


class ParamsSource:
    """load_level_params' one query, answered from the history-mode rows:
    the policy rows in force and, per ticker, key and basis, the row with the
    greatest effective_from on or before the session (LEVEL_PARAMS_SQL)."""

    def __init__(self, rows_csv: Path):
        df = pd.read_csv(rows_csv)
        df["eff"] = pd.to_datetime(df["effective_from"]).dt.date
        self.by_ticker = {t: g.sort_values("eff").reset_index(drop=True) for t, g in df.groupby("ticker")}
        self.policy = common.policy_rows()

    def load(self, ticker: str, session: date):
        def query(sql, p):
            day = pd.Timestamp(p["session_date"]).date()
            out = [{**r, "row_kind": "policy", "ticker": None} for r in self.policy
                   if r["effective_from"] <= day]
            g = self.by_ticker.get(ticker)
            if g is not None:
                g = g[g["eff"] <= day]
                g = g.groupby(["param_key", "atr_basis"]).tail(1)
                for r in g.to_dict("records"):
                    r = {k: (None if (isinstance(v, float) and v != v) else v) for k, v in r.items()}
                    out.append({**r, "row_kind": "ticker"})
            return pd.DataFrame(out)
        return sl_mod.load_level_params(query, [ticker], session)[ticker]


def cents(x):
    return None if x is None else sl_mod.price_cents(x) / 100


def side_record(side) -> dict:
    trig = side.trigger
    return {
        "trigger": None if trig is None else f"{trig['name']} {cents(trig['price']):.2f}",
        "reason": None if trig is not None else side.reason,
        "stop": None if not side.stop else cents(side.stop["price"]),
        "targets": [cents(t["price"]) for t in (side.targets or [])][:3],
    }


def plan_records(levels, close, atr, sma) -> dict:
    out = {}
    for direction in ("long", "short"):
        try:
            ctx = tp.PlanContext(direction=direction, conviction="medium", close=float(close),
                                 atr=atr, levels=levels, sma_200=sma)
            plans = tp.compute_persona_plans(ctx)
        except Exception as exc:  # recorded, counted by diff.py
            out[direction] = {"error": type(exc).__name__}
            continue
        out[direction] = {p.persona: {
            "entry": None if p.entry_zone is None else [round(p.entry_zone.low, 2), round(p.entry_zone.high, 2)],
            "stop": None if p.stop is None else round(p.stop, 2),
            "targets": [round(x, 2) for x in p.targets], "regime": p.regime} for p in plans}
    return out


def fnum(v):
    return float(v) if v is not None and pd.notna(v) and float(v) > 0 else None


def main(export_csv: Path, out_path: Path, params_csv: Path | None = None) -> None:
    if BRANCH and params_csv is None:
        raise SystemExit("the #1766 worktree needs ticker_level_params.csv.gz from calib.py")
    export = pd.read_csv(export_csv)
    install_csv_answer(export)
    loader = dl.DataLoader()
    params = ParamsSource(params_csv) if BRANCH else None
    print("version", "#1766" if BRANCH else "#1753", "rows", len(export), file=sys.stderr, flush=True)
    t0, n = time.time(), 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out_path, "wt") as f:
        for ticker in common.TICKERS:
            full = loader.load_daily(ticker, on_stale="warn")
            for s in [t for t in full.index if START <= t.date() <= END]:
                d = s.date()
                before = full[full.index < pd.Timestamp(d)]
                if len(before) < 2:
                    continue
                last = before.iloc[-1]
                strat = str(last["strat_candle"]) if pd.notna(last["strat_candle"]) else ""
                close, sma = float(last["Close"]), fnum(last.get("SMA200"))
                atr14 = fnum(last.get("ATR14"))
                lp = params.load(ticker, d) if BRANCH else None
                for mode in ("stored", "none"):
                    pm = sl_mod.premarket_snapshot_from_daily(full, d) if mode == "stored" else None
                    if BRANCH:
                        atrs = {"atr_14": atr14, "atr_5": fnum(last.get("ATR5"))}
                        lv = sl_mod.build_session_levels(ticker, d, before, atrs, pm, lp,
                                                         daily_strat_class=strat)
                        plan_atr = lv.atr
                    else:
                        lv = sl_mod.build_session_levels(ticker, d, before, atr14, pm,
                                                         daily_strat_class=strat)
                        plan_atr = atr14
                    rec = {"ticker": ticker, "session": d.isoformat(), "mode": mode,
                           "premarket": lv.premarket_status, "atr": plan_atr,
                           "long": side_record(lv.long), "short": side_record(lv.short),
                           "plans": plan_records(lv, close, plan_atr, sma)}
                    f.write(json.dumps(rec) + "\n")
                n += 1
            print(ticker, "done", n, f"{time.time() - t0:.0f} s", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]) if len(sys.argv) > 3 else None)
