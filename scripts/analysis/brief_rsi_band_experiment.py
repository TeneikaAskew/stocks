"""Offline experiment (FEAT-SIGNAL-001, 2026-11-11 spec): the premarket
brief's CALL/PUT selection with the hard-coded RSI bands versus per-ticker
bands. Read only; touches no database.

Usage:
  python scripts/analysis/brief_rsi_band_experiment.py \
    --daily-dir /mnt/project-files/strat-verify/ftfc-replay/raw \
    --minute-dir /mnt/project-files/stocks-scorecard/inputs/bars_raw \
    --out /tmp/rsi_exp

Inputs:
  <daily-dir>/{T}_daily_adjusted.csv   Alpha Vantage TIME_SERIES_DAILY_ADJUSTED
                                        (the unadjusted OHLCV columns are used)
  <minute-dir>/{T}_1min_YYYY-MM.csv    Alpha Vantage 1-minute bars, extended hours

The brief on session D reads the daily frame strictly before D, runs
add_brief_indicators, scores check_call_conditions / check_put_conditions on
the last row, takes the FTFC direction from compute_strat_status at the
08:30 ET clock on D, and publishes _resolve_signal_status. Only the RSI band
passed to the two scorers differs between variants:

  H  hard-coded: CALL (25, 50), PUT (50, 75)  (lib/signals.py defaults)
  A  ticker_calibration Tier A, rebuilt point in time the way
     scripts/calibrate_thresholds.py writes it: Wilder RSI(14) over the 1-min
     closes of the 60 calendar days ending on the quarterly run date
     (Jan/Apr/Jul/Oct 1), CALL (p10, p50), PUT (p50, p90); the brief on D uses
     the latest run dated on or before D and no more than 180 days old, else
     Tier B (equal to H). Read via the same rule as lib/strategies/calibration.
  D  daily-RSI percentiles: the same (p10, p50) / (p50, p90) rule over the
     ticker's own daily RSI(14) for the 252 sessions before D.
"""
from __future__ import annotations

import argparse
import glob
import inspect
import json
import os
import sys
from datetime import date, timedelta

import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from gcp.premarket_brief import _resolve_signal_status  # noqa: E402
from lib.config import load_config  # noqa: E402
from lib.indicators import add_brief_indicators  # noqa: E402
from lib.signals import check_call_conditions, check_put_conditions  # noqa: E402
from lib.strat import compute_strat_status  # noqa: E402
from lib.strategies.calibration import _STALE_DAYS  # noqa: E402
from scripts.calibrate_thresholds import compute_rsi  # noqa: E402

DAILY = "{d}/{t}_daily_adjusted.csv"
MINUTE = "{d}/{t}_1min_*.csv"
LOOKBACK_DAYS = 60     # calibrate_thresholds.py --lookback-days default
DAILY_LOOKBACK = 252   # variant D: sessions of daily RSI before D
# origin/main's hard-coded bands: the scorers' own defaults
HARD_CALL = inspect.signature(check_call_conditions).parameters["rsi_range"].default
HARD_PUT = inspect.signature(check_put_conditions).parameters["rsi_range"].default
TICKERS = ["SPY", "QQQ", "IWM"]
WINDOWS = {
    "primary_2026-05_to_2026-11": (date(2026, 5, 1), date(2026, 11, 4)),
    "holdout_2025-03_to_2026-04": (date(2025, 3, 1), date(2026, 4, 30)),
}
QUARTER_RUNS = [date(y, m, 1) for y in (2025, 2026) for m in (1, 4, 7, 10)]


def load_daily(d: str, t: str) -> pd.DataFrame:
    df = pd.read_csv(DAILY.format(d=d, t=t), parse_dates=["timestamp"])
    df = df.sort_values("timestamp").set_index("timestamp")
    df.index.name = None
    out = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                             "close": "Close", "volume": "Volume"})
    out = out[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    # lib.data_loader.load_daily carries Time, and lib.indicators adds VWAP
    # (so Price_vs_VWAP, the scorers' fifth factor) only when Time is present.
    out["Time"] = out.index
    return out


# The live calibrate-thresholds job runs at 02:00 ET on the run date
# (gcp/deploy.sh, Phase 0.6), so it can only read bars stamped before then.
RUN_CLOCK = pd.Timedelta(hours=2)


def tier_a_rows(d: str, t: str) -> dict:
    """ticker_calibration rows rebuilt as scripts/calibrate_thresholds.py
    writes them on each quarterly run date the local history covers."""
    files = sorted(glob.glob(MINUTE.format(d=d, t=t)))
    bars = pd.concat([pd.read_csv(f, parse_dates=["timestamp"]) for f in files])
    bars = bars.sort_values("timestamp").drop_duplicates("timestamp")
    first = bars["timestamp"].min().date()
    rows = {}
    for run in QUARTER_RUNS:
        start = run - timedelta(days=LOOKBACK_DAYS)
        if start < first:
            continue  # 60-day window not covered by the local 1-min history
        w = bars[(bars["timestamp"] >= pd.Timestamp(start))
                 & (bars["timestamp"] < pd.Timestamp(run) + RUN_CLOCK)]
        if w.empty:
            continue
        rsi = compute_rsi(w["close"].reset_index(drop=True)).dropna()
        rows[run] = {"p10": float(rsi.quantile(0.10)), "p50": float(rsi.quantile(0.50)),
                     "p90": float(rsi.quantile(0.90)), "n_bars": int(len(w)),
                     "from": str(w["timestamp"].min()), "to": str(w["timestamp"].max())}
    return rows


def tier_a_for(rows: dict, d: date):
    runs = [r for r in rows if r <= d and (d - r).days <= _STALE_DAYS]
    if not runs:
        return None
    r = rows[max(runs)]
    return (r["p10"], r["p50"]), (r["p50"], r["p90"]), max(runs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily-dir", required=True)
    ap.add_argument("--minute-dir", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    cfg = load_config()
    sig_t, bld_t = cfg.signal.premarket_signal_threshold, cfg.signal.premarket_building_threshold
    os.makedirs(a.out, exist_ok=True)
    rows_out = []
    calib_out = {}
    for t in TICKERS:
        raw = load_daily(a.daily_dir, t)
        ind = add_brief_indicators(raw, close_col="Close")
        drsi = ind[cfg.indicator.rsi_col]
        ta = tier_a_rows(a.minute_dir, t)
        calib_out[t] = {str(k): v for k, v in ta.items()}
        sessions = list(raw.index)
        for i in range(260, len(sessions) - 1):
            D = sessions[i].date()
            if not any(lo <= D <= hi for lo, hi in WINDOWS.values()):
                continue
            prev = ind.iloc[i - 1]
            hist = raw.iloc[max(0, i - 800):i]
            clock = pd.Timestamp(D.isoformat() + " 08:30", tz="America/New_York")
            ss = compute_strat_status(
                t, df=hist, timeframes=["1d", "1w", "1mo"], strat_config=cfg.strat,
                as_of=clock, inclusive_today=False,
                observed_price=float(prev["Close"]), observed_price_session=sessions[i - 1].date(),
                price_provenance="latest_completed_close",
                continuity_timeframes=cfg.strat.continuity_timeframes_premarket,
            )
            ftfc = ss.get("ftfc_direction") if ss.get("available") else None
            r_hist = drsi.iloc[i - DAILY_LOOKBACK:i].dropna()
            variants = {"H": (HARD_CALL, HARD_PUT, "fixed")}
            tier = tier_a_for(ta, D)
            variants["A"] = (tier[0], tier[1], f"tierA:{tier[2]}") if tier else (HARD_CALL, HARD_PUT, "tierB")
            variants["D"] = ((float(r_hist.quantile(.10)), float(r_hist.quantile(.50))),
                             (float(r_hist.quantile(.50)), float(r_hist.quantile(.90))), "daily252")
            rec = {"ticker": t, "session": D.isoformat(), "ftfc": ftfc,
                   "rsi": float(prev[cfg.indicator.rsi_col]),
                   "prev_close": float(raw["Close"].iloc[i - 1]),
                   "open": float(raw["Open"].iloc[i]), "close": float(raw["Close"].iloc[i]),
                   "next_close": float(raw["Close"].iloc[i + 1])}
            for k, (cb, pb, src) in variants.items():
                cs, _ = check_call_conditions(prev, rsi_range=cb)
                ps, _ = check_put_conditions(prev, rsi_range=pb)
                st = _resolve_signal_status(call_score=cs, put_score=ps, ftfc_direction=ftfc,
                                            signal_threshold=sig_t, building_threshold=bld_t)
                rec[f"{k}_status"], rec[f"{k}_src"] = st, src
                rec[f"{k}_call_band"], rec[f"{k}_put_band"] = list(cb), list(pb)
            rows_out.append(rec)
        print(t, "done", file=sys.stderr, flush=True)
    df = pd.DataFrame(rows_out)
    df.to_csv(os.path.join(a.out, "sessions.csv"), index=False)
    with open(os.path.join(a.out, "tier_a_calibration.json"), "w") as f:
        json.dump(calib_out, f, indent=1)

    def side(s):
        return None if s == "No signal" else s.split()[0]

    summary = []
    for wname, (lo, hi) in WINDOWS.items():
        w = df[(df.session >= lo.isoformat()) & (df.session <= hi.isoformat())]
        for t in TICKERS + ["ALL"]:
            x = w if t == "ALL" else w[w.ticker == t]
            for k in ("H", "A", "D"):
                sd = x[f"{k}_status"].map(side)
                called = sd.notna()
                up_same = x["close"] > x["prev_close"]
                up_od = x["close"] > x["open"]
                up_next = x["next_close"] > x["close"]
                def agree(up):
                    ok = ((sd == "CALL") & up) | ((sd == "PUT") & ~up)
                    n = int(called.sum())
                    return int(ok[called].sum()), (round(100 * ok[called].sum() / n, 1) if n else None)
                setups = x[f"{k}_status"].str.contains("setup")
                summary.append({
                    "window": wname, "ticker": t, "variant": k, "sessions": int(len(x)),
                    "calls": int(called.sum()), "call_side": int((sd == "CALL").sum()),
                    "put_side": int((sd == "PUT").sum()), "setups": int(setups.sum()),
                    "same_day_cc_agree": agree(up_same), "same_day_oc_agree": agree(up_od),
                    "next_day_agree": agree(up_next),
                    "status_changed_vs_H": int((x[f"{k}_status"] != x["H_status"]).sum()),
                })
    s = pd.DataFrame(summary)
    s.to_csv(os.path.join(a.out, "summary.csv"), index=False)
    with pd.option_context("display.width", 250, "display.max_rows", 200):
        print(s.to_string(index=False))


if __name__ == "__main__":
    main()
