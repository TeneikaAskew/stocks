"""Multi-timeframe signal evaluation.

For every historical_signals row, evaluate clean/wrong/noise across
5m / 15m / 30m / 60m / 90m / 120m / 240m windows.
- 5m..60m come from columns already in historical_signals.
- 90m..240m are computed from market_data_intraday.

Then identify the OPTIMAL TIMEFRAME for each signal and aggregate
patterns (which conditions/strength map to which best timeframe).

GET ALL DATA. No regime filtering. No dead-day exclusion.
"""
from __future__ import annotations

import os, sys, pathlib, json
from datetime import timedelta

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def setenv():
    base = REPO / ".creds_tmp"
    os.environ["DB_USER"] = (base / "u").read_text().strip()
    os.environ["DB_PASS"] = (base / "p").read_text().strip()
    os.environ["CLOUD_SQL_CONNECTION_NAME"] = (base / "c").read_text().strip()
    os.environ["DB_NAME"] = "trading"


# Thresholds in PERCENT. Tuned per-timeframe so we don't penalize
# short windows for not having time to move.
THRESHOLDS = {
    "5m":   {"clean": 0.15, "wrong": -0.20, "noise": 0.10},
    "15m":  {"clean": 0.30, "wrong": -0.30, "noise": 0.20},
    "30m":  {"clean": 0.40, "wrong": -0.40, "noise": 0.25},
    "60m":  {"clean": 0.50, "wrong": -0.50, "noise": 0.30},
    "90m":  {"clean": 0.60, "wrong": -0.60, "noise": 0.35},
    "120m": {"clean": 0.70, "wrong": -0.70, "noise": 0.40},
    "240m": {"clean": 1.00, "wrong": -1.00, "noise": 0.50},
}

def classify(r, tf):
    if pd.isna(r):
        return "ND"
    t = THRESHOLDS[tf]
    if r >= t["clean"]:  return "CLEAN"
    if r <= t["wrong"]:  return "WRONG"
    if abs(r) < t["noise"]: return "NOISE"
    return "MIXED"


def compute_extended_returns(sigs, bars_by_tk):
    """For each signal, compute return_90min/120min/240min using intraday bars."""
    out_90, out_120, out_240 = [], [], []
    for _, sig in sigs.iterrows():
        tk = sig["ticker"]
        if tk not in bars_by_tk:
            out_90.append(np.nan); out_120.append(np.nan); out_240.append(np.nan); continue
        sig_ts = pd.Timestamp(sig["entry_time"]).tz_convert("UTC")
        entry = float(sig["entry_price"])
        direction = sig["trade_type"]
        bars = bars_by_tk[tk]
        post = bars[bars["ts"] >= sig_ts]
        for mins, out in [(90, out_90), (120, out_120), (240, out_240)]:
            window = post[post["ts"] <= sig_ts + timedelta(minutes=mins)]
            if window.empty:
                out.append(np.nan); continue
            if direction == "call":
                mfe_pct = (window["high"].max() - entry) / entry * 100
            else:
                mfe_pct = (entry - window["low"].min()) / entry * 100
            out.append(mfe_pct)
    return out_90, out_120, out_240


def main():
    setenv()
    from gcp.database import get_engine
    eng = get_engine()

    print("loading historical_signals (full month, all 3 tickers, no filtering)...", flush=True)
    sigs = pd.read_sql("""
        SELECT ticker, entry_time, trade_type, entry_price, signal_strength,
               conditions_met, entry_rsi,
               return_5min, return_15min, return_30min, return_60min,
               return_45min, return_20min, return_10min
          FROM historical_signals
         WHERE entry_time >= '2026-04-01' AND entry_time < '2026-05-02'
           AND ticker IN ('SPY', 'QQQ', 'IWM')
           AND return_60min IS NOT NULL
         ORDER BY entry_time
    """, eng)
    print(f"loaded {len(sigs):,} signals across {sigs['ticker'].nunique()} tickers", flush=True)

    print("\nloading intraday bars for 90m/120m/240m extension...", flush=True)
    bars = pd.read_parquet(REPO / "data/av_intraday_apr_may_2026.parquet")
    bars["ts"] = pd.to_datetime(bars["ts"], utc=True)
    bars_by_tk = {tk: g.sort_values("ts").copy() for tk, g in bars.groupby("ticker")}

    print("computing extended returns (90/120/240 min)...", flush=True)
    sigs["entry_time"] = pd.to_datetime(sigs["entry_time"], utc=True)
    r90, r120, r240 = compute_extended_returns(sigs, bars_by_tk)
    sigs["return_90min"] = r90
    sigs["return_120min"] = r120
    sigs["return_240min"] = r240

    # Classify each signal at every timeframe
    tf_cols = {"5m":"return_5min", "15m":"return_15min", "30m":"return_30min",
               "60m":"return_60min", "90m":"return_90min", "120m":"return_120min",
               "240m":"return_240min"}
    for tf, col in tf_cols.items():
        sigs[f"cls_{tf}"] = sigs[col].apply(lambda x: classify(x, tf))

    sigs["entry_date"] = sigs["entry_time"].dt.date.astype(str)

    sep = "=" * 90
    # ── Distribution at each timeframe (every day, all signals) ───────────
    print(f"\n{sep}\nCLASSIFICATION DISTRIBUTION BY TIMEFRAME (all 30k+ candidates, no exclusions)\n{sep}", flush=True)
    rows = []
    for tf in tf_cols:
        col = f"cls_{tf}"
        v = sigs[col].value_counts()
        n_total = (sigs[col] != "ND").sum()
        rows.append({
            "tf": tf, "n": n_total,
            "clean_pct": v.get("CLEAN", 0) / n_total * 100 if n_total else 0,
            "wrong_pct": v.get("WRONG", 0) / n_total * 100 if n_total else 0,
            "noise_pct": v.get("NOISE", 0) / n_total * 100 if n_total else 0,
            "mixed_pct": v.get("MIXED", 0) / n_total * 100 if n_total else 0,
        })
    summary = pd.DataFrame(rows)
    print(summary.round(2).to_string(index=False), flush=True)

    # ── Per-signal: identify the BEST timeframe based on actual MFE ───────
    print(f"\n{sep}\nBEST TIMEFRAME PER SIGNAL\n{sep}", flush=True)
    # For each signal, find which timeframe had highest favorable excursion
    # AND was classified CLEAN. If none clean, mark "no_clean_tf"
    def find_best_tf(row):
        best = None; best_pct = -1; best_score = -999
        for tf in tf_cols:
            r = row[tf_cols[tf]]
            cls = row[f"cls_{tf}"]
            if pd.isna(r):
                continue
            if cls == "CLEAN":
                # Score by return-over-noise-threshold ratio
                t = THRESHOLDS[tf]
                score = r / t["clean"]
                if score > best_score:
                    best_score = score; best_pct = r; best = tf
        return best
    sigs["best_tf"] = sigs.apply(find_best_tf, axis=1)
    print(f"\nDistribution of best timeframe per signal:", flush=True)
    btf = sigs["best_tf"].fillna("none_clean").value_counts()
    print((btf / len(sigs) * 100).round(1).to_string(), flush=True)
    print(f"\nTotal: {len(sigs):,}  with at least one CLEAN tf: {sigs['best_tf'].notna().sum():,} "
          f"({sigs['best_tf'].notna().mean()*100:.1f}%)", flush=True)

    # ── Per-ticker × direction × best_tf ──────────────────────────────────
    print(f"\n{sep}\nBEST TIMEFRAME × TICKER × DIRECTION\n{sep}", flush=True)
    sigs["best_tf_or_none"] = sigs["best_tf"].fillna("none_clean")
    pivot = pd.crosstab(
        [sigs["ticker"], sigs["trade_type"]],
        sigs["best_tf_or_none"],
        normalize="index",
    ).round(3) * 100
    print(pivot.to_string(), flush=True)

    # ── Daily: best-tf distribution by day (every day) ────────────────────
    print(f"\n{sep}\nDAILY: number of signals at each best_tf (all days, no skipping)\n{sep}", flush=True)
    daily = pd.crosstab(sigs["entry_date"], sigs["best_tf_or_none"])
    daily["TOTAL"] = daily.sum(axis=1)
    daily["clean_signals"] = daily.sum(axis=1) - daily["TOTAL"] / 2 - daily.get("none_clean", 0)
    print(daily.to_string(), flush=True)

    # ── Conditions analysis: which conditions favor which timeframe ───────
    print(f"\n{sep}\nWHICH CONDITIONS PREDICT WHICH TIMEFRAME?\n{sep}", flush=True)
    # Parse conditions_met (it's a JSON string like ["rsi_oversold_zone", ...])
    def parse_cm(x):
        if pd.isna(x): return []
        if isinstance(x, list): return x
        try: return json.loads(x) if isinstance(x, str) else []
        except Exception: return []
    sigs["cond_list"] = sigs["conditions_met"].apply(parse_cm)
    # Explode to one row per (signal, condition)
    exp = sigs.explode("cond_list")
    # For each condition, what's the distribution of best_tf?
    for cond in exp["cond_list"].dropna().unique():
        if cond is None or cond == "":
            continue
        sub = exp[exp["cond_list"] == cond]
        if len(sub) < 50:
            continue
        clean = sub["best_tf"].notna()
        print(f"\n{cond}  n={len(sub):,}  clean-rate={clean.mean()*100:.1f}%", flush=True)
        if clean.sum() > 0:
            tf_dist = sub.loc[clean, "best_tf"].value_counts(normalize=True).round(3) * 100
            print(f"  best_tf when clean: {tf_dist.to_dict()}", flush=True)

    # ── Mean MFE at each timeframe by best_tf ─────────────────────────────
    print(f"\n{sep}\nWHAT 'BEST_TF=X' SIGNALS LOOK LIKE — return profile across all timeframes\n{sep}", flush=True)
    for btf in ["5m","15m","30m","60m","90m","120m","240m"]:
        sub = sigs[sigs["best_tf"] == btf]
        if len(sub) < 20:
            continue
        means = {tf: sub[tf_cols[tf]].mean() for tf in tf_cols}
        print(f"\nbest_tf={btf}  n={len(sub):,}  mean MFE at each timeframe (in %):", flush=True)
        for tf, m in means.items():
            print(f"  {tf:>5}: {m:>+6.3f}%", flush=True)

    sigs.to_csv(REPO / "data/signal_eval_multi_tf.csv", index=False)
    print(f"\nwrote data/signal_eval_multi_tf.csv ({len(sigs):,} rows)", flush=True)


if __name__ == "__main__":
    main()
