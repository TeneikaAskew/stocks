"""Mean-reversion multi-timeframe analysis (Phase 0.7 deliverable).

Mirrors scripts/_signal_multi_tf.py but uses lib.signals.evaluate_signal
(mean-reversion CALL: consec_DOWN + below_VWAP + below_EMAs + RSI oversold)
instead of MarketAnalyzer's momentum logic.

Pipeline:
  1. Load intraday bars from Cloud SQL (Apr 1 - May 1, SPY/QQQ/IWM)
  2. Enrich with indicators via MarketAnalyzer.add_technical_indicators
     (we only use the indicator calc, NOT MarketAnalyzer's signal gen)
  3. Run lib.signals.generate_signals on the enriched bars
  4. Compute per-signal returns at 5/15/30/60/90/120/240 min from raw bars
  5. Classify per timeframe + identify best_tf
  6. Write to data/signal_eval_multi_tf_mr.csv
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


def main():
    setenv()
    print("loading bars...", flush=True)
    bars = pd.read_parquet(REPO / "data/av_intraday_apr_may_2026.parquet")
    bars["ts"] = pd.to_datetime(bars["ts"], utc=True)
    bars_by_tk = {tk: g.sort_values("ts").reset_index(drop=True).copy()
                  for tk, g in bars.groupby("ticker")}

    from lib.trading_analysis import MarketAnalyzer
    from lib.signals import generate_signals
    from lib.config import IndicatorConfig

    # MarketAnalyzer outputs RSI14_W, not RSI14. Override the IndicatorConfig.
    ind_cfg = IndicatorConfig()
    ind_cfg.rsi_period = 14  # forces rsi_col = 'RSI14'

    def _derive_extra_cols(df):
        """Add columns lib.signals.evaluate_signal expects but MarketAnalyzer doesn't emit."""
        # Rename RSI14_W -> RSI14 (lib.signals expects 'RSI14')
        if 'RSI14_W' in df.columns and 'RSI14' not in df.columns:
            df['RSI14'] = df['RSI14_W']
        # Derive Price_vs_VWAP, Price_vs_EMA9, Price_vs_EMA20 as %-from-baseline
        df['Price_vs_VWAP'] = (df['Last'] - df['VWAP']) / df['VWAP'] * 100
        df['Price_vs_EMA9'] = (df['Last'] - df['EMA9']) / df['EMA9'] * 100
        df['Price_vs_EMA20'] = (df['Last'] - df['EMA20']) / df['EMA20'] * 100
        # Consecutive_Up / Consecutive_Down
        ret = df['Last'].diff()
        consec_up = (ret > 0).astype(int)
        consec_down = (ret < 0).astype(int)
        # Reset counter on direction change
        df['Consecutive_Up'] = consec_up * (consec_up.groupby((consec_up != consec_up.shift()).cumsum()).cumcount() + 1)
        df['Consecutive_Down'] = consec_down * (consec_down.groupby((consec_down != consec_down.shift()).cumsum()).cumcount() + 1)
        # 'Close' alias
        if 'Close' not in df.columns:
            df['Close'] = df['Last']
        return df

    all_signals = []
    for tk in ["SPY", "QQQ", "IWM"]:
        print(f"\n--- {tk} ---", flush=True)
        df = bars_by_tk[tk].copy()
        df_an = pd.DataFrame({
            "Time": df["ts"],
            "Open": df["open"], "High": df["high"], "Low": df["low"],
            "Last": df["close"], "Volume": df["volume"],
        })
        analyzer = MarketAnalyzer()
        analyzer.df = df_an
        enriched = analyzer.add_technical_indicators(df_an)
        enriched = _derive_extra_cols(enriched)
        enriched = enriched.set_index("Time")
        print(f"  enriched: {len(enriched):,} bars; cols added Consecutive_Up/Down/Price_vs_*", flush=True)

        sig_df = generate_signals(enriched, min_conditions=3, consecutive_periods=3,
                                  indicator_config=ind_cfg)
        print(f"  mean-reversion signals: {len(sig_df):,}", flush=True)
        if len(sig_df) == 0:
            continue
        sig_df["ticker"] = tk
        all_signals.append(sig_df)

    sigs = pd.concat(all_signals, ignore_index=True)
    print(f"\nTotal mean-reversion bar-level signals: {len(sigs):,}", flush=True)

    # Compute returns from raw bars (the per-bar enriched DF doesn't have forward-look)
    print("\ncomputing per-signal returns at 5/15/30/60/90/120/240 min...", flush=True)
    out_5, out_15, out_30, out_60, out_90, out_120, out_240 = ([] for _ in range(7))
    sigs["time"] = pd.to_datetime(sigs["time"], utc=True)
    for _, sig in sigs.iterrows():
        tk = sig["ticker"]
        bars = bars_by_tk[tk]
        sig_ts = pd.Timestamp(sig["time"]).tz_convert("UTC")
        entry = float(sig["price"])
        direction = sig["direction"]
        post = bars[bars["ts"] >= sig_ts]
        for mins, out in [(5, out_5), (15, out_15), (30, out_30), (60, out_60),
                          (90, out_90), (120, out_120), (240, out_240)]:
            window = post[post["ts"] <= sig_ts + timedelta(minutes=mins)]
            if window.empty:
                out.append(np.nan); continue
            if direction == "CALL":
                mfe_pct = (window["high"].max() - entry) / entry * 100
            else:
                mfe_pct = (entry - window["low"].min()) / entry * 100
            out.append(mfe_pct)
    sigs["return_5min"] = out_5
    sigs["return_15min"] = out_15
    sigs["return_30min"] = out_30
    sigs["return_60min"] = out_60
    sigs["return_90min"] = out_90
    sigs["return_120min"] = out_120
    sigs["return_240min"] = out_240

    # Classify each signal at every timeframe
    tf_cols = {"5m":"return_5min", "15m":"return_15min", "30m":"return_30min",
               "60m":"return_60min", "90m":"return_90min", "120m":"return_120min",
               "240m":"return_240min"}
    for tf, col in tf_cols.items():
        sigs[f"cls_{tf}"] = sigs[col].apply(lambda x: classify(x, tf))

    sigs["entry_date"] = sigs["time"].dt.date.astype(str)
    sigs.rename(columns={"direction": "trade_type"}, inplace=True)
    sigs["trade_type"] = sigs["trade_type"].str.lower()  # 'CALL' -> 'call' for parity

    sep = "=" * 90
    print(f"\n{sep}\nMEAN-REVERSION CLASSIFICATION DISTRIBUTION BY TIMEFRAME\n{sep}", flush=True)
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
        })
    print(pd.DataFrame(rows).round(2).to_string(index=False), flush=True)

    # Best timeframe per signal
    def find_best_tf(row):
        best = None; best_score = -999
        for tf in tf_cols:
            r = row[tf_cols[tf]]
            cls = row[f"cls_{tf}"]
            if pd.isna(r) or cls != "CLEAN":
                continue
            t = THRESHOLDS[tf]
            score = r / t["clean"]
            if score > best_score:
                best_score = score; best = tf
        return best
    sigs["best_tf"] = sigs.apply(find_best_tf, axis=1)
    sigs["best_tf_or_none"] = sigs["best_tf"].fillna("none_clean")

    print(f"\n{sep}\nBEST TIMEFRAME × TICKER × DIRECTION (mean-reversion)\n{sep}", flush=True)
    pivot = pd.crosstab(
        [sigs["ticker"], sigs["trade_type"]],
        sigs["best_tf_or_none"],
        normalize="index",
    ).round(3) * 100
    print(pivot.to_string(), flush=True)

    print(f"\n{sep}\nDAILY VOLUME (mean-reversion, all days)\n{sep}", flush=True)
    daily = pd.crosstab(sigs["entry_date"], sigs["best_tf_or_none"])
    daily["TOTAL"] = daily.sum(axis=1)
    print(daily.to_string(), flush=True)

    sigs.to_csv(REPO / "data/signal_eval_multi_tf_mr.csv", index=False)
    print(f"\nwrote data/signal_eval_multi_tf_mr.csv ({len(sigs):,} rows)", flush=True)


if __name__ == "__main__":
    main()
