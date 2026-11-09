"""FEAT-STRAT-001 #1753 done_when 13 on production inputs.

Input: the CSV produced by export_daily.sql (production market_data_daily,
read-only). The script feeds it through the brief's own path, unchanged:
DataLoader.load_daily (its SQL call is answered from the CSV), then for each
session premarket_snapshot_from_daily, the cut to bars before the session,
the last completed session's atr_14 and build_session_levels, exactly as
gcp/premarket_brief.py does. origin/main's picks come from its level code
(tests/fixtures/legacy_strat_levels_5e1142ae.py) on the same frame, anchored
on the prior close as its brief did. Nothing is written to any database and
nothing posts. The branch planner reads the same SessionLevels (parity test),
so its picks equal the branch brief's.

Usage: PYTHONPATH=platform:<repo> python3 prod_replay.py <export.csv> <out_dir>
"""
from __future__ import annotations

import csv
import importlib.util
import sys
from datetime import date
from pathlib import Path

import pandas as pd

import lib.data_loader as dl
from lib.strat_levels import (build_session_levels, premarket_snapshot_from_daily,
                              price_cents)

REPO = Path(dl.__file__).resolve().parents[1]
START, END = date(2015, 1, 2), date(2026, 11, 6)
TICKERS = ("IWM", "SPY", "QQQ")


def legacy_module():
    p = REPO / "tests" / "fixtures" / "legacy_strat_levels_5e1142ae.py"
    spec = importlib.util.spec_from_file_location("legacy_strat_levels", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def install_csv_answer(export: pd.DataFrame):
    def fake_query(sql, params=None):
        if "pre_fetched_at" in sql:
            return pd.DataFrame()  # production has no provenance columns yet
        t = (params or {}).get("ticker")
        return export[export["ticker"] == t].drop(columns=["ticker"]).reset_index(drop=True)
    dl._query_cloud_sql = fake_query
    dl._cloud_sql_active = lambda: True
    dl._PREMARKET_PROVENANCE_PRESENT = None


def pick_legacy(trig):
    if not trig:
        return "orb_only"
    return f"{trig['trigger_name']} {price_cents(trig['trigger_level']) / 100:.2f}"


def pick_new(side):
    if side.trigger is None:
        return f"orb_only:{side.reason}"
    return f"{side.trigger['name']} {price_cents(side.trigger['price']) / 100:.2f}"


def main(export_csv: Path, out_dir: Path) -> None:
    export = pd.read_csv(export_csv)
    print("rows", len(export), "range", export["date"].min(), export["date"].max(), file=sys.stderr)
    install_csv_answer(export)
    loader = dl.DataLoader()
    legacy = legacy_module()
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, pm_seen = [], {}
    for ticker in TICKERS:
        full = loader.load_daily(ticker, on_stale="warn")
        sessions = [t for t in full.index if START <= t.date() <= END]
        pm_seen[ticker] = 0
        for s in sessions:
            d = s.date()
            session_pm = premarket_snapshot_from_daily(full, d)
            before = full[full.index < pd.Timestamp(d)]
            if len(before) < 2:
                continue
            atr = before["ATR14"].iloc[-1]
            atr = float(atr) if pd.notna(atr) and float(atr) > 0 else None
            sl = build_session_levels(ticker, d, before, atr, session_pm,
                                      daily_strat_class=(str(before["strat_candle"].iloc[-1])
                                                         if pd.notna(before["strat_candle"].iloc[-1]) else ""))
            if sl.premarket_status == "ok":
                pm_seen[ticker] += 1
            lm = legacy.build_level_map(ticker=ticker, daily_df=before.iloc[-600:],
                                        current_price=float(before["Close"].iloc[-1]),
                                        atr=atr, analysis_date=d)
            rows.append({"ticker": ticker, "session": d.isoformat(),
                         "premarket": sl.premarket_status,
                         "origin_calls": pick_legacy(lm.calls_trigger),
                         "branch_calls": pick_new(sl.long),
                         "origin_puts": pick_legacy(lm.puts_trigger),
                         "branch_puts": pick_new(sl.short)})
        print(ticker, len(sessions), "premarket ok:", pm_seen[ticker], file=sys.stderr, flush=True)

    with open(out_dir / "picks.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

    def same(a, b):
        return (a.startswith("orb_only") and b.startswith("orb_only")) or a == b

    lines = ["ticker,side,sessions,premarket_ok,trigger_changed,orb_only_origin,"
             "orb_only_branch,orb_only_state_changed"]
    for ticker in TICKERS:
        tr = [r for r in rows if r["ticker"] == ticker]
        for side in ("calls", "puts"):
            o = [r[f"origin_{side}"] for r in tr]; b = [r[f"branch_{side}"] for r in tr]
            lines.append(",".join(map(str, [
                ticker, side, len(tr), pm_seen[ticker],
                sum(not same(x, y) for x, y in zip(o, b)),
                sum(x.startswith("orb_only") for x in o),
                sum(y.startswith("orb_only") for y in b),
                sum(x.startswith("orb_only") != y.startswith("orb_only") for x, y in zip(o, b))])))
    (out_dir / "counts.csv").write_text("\n".join(lines) + "\n")
    last = []
    for ticker in TICKERS:
        last.extend([r for r in rows if r["ticker"] == ticker][-20:])
    with open(out_dir / "last_20_sessions.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(last)
    print("\n".join(lines))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
