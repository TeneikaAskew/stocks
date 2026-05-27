"""Strat Engine — DIRECTION-target walk-forward, EXTENDED feature set.

Track C R&D. Wraps `strat_dir_walk_forward.py`'s machinery but joins one of
four experimental feature families ON TOP of the baseline 143-col feature
matrix:

  --family=news_sentiment  → market-wide news sentiment / topic flags / volume
  --family=cross_asset     → daily VIX/VVIX/VIX3M/SPY/QQQ relative-strength
  --family=options_derived → daily PCR / IV skew / IV term slope / ATM IV
                             momentum from etf_options_snapshots
  --family=vol_regime      → daily ATR-regime / realized-vol / gap / range-z

The baseline (no family) reports 24/24 FAIL on log-loss beat. The harness
is otherwise byte-identical: same featurize() + LightGBM hyperparameters,
same 8 anchored cutoffs, same MIN_TEST_BARS=200, same ECE / hit-rate scoring,
no calibration.

Success bar per family (binary):
  1. Log-loss beat > 0 on >= 6 of 8 OK folds (per cell)
  2. ECE <= 0.05 on the SAME 6 folds
  3. Decisive-call hit rate at thresholds (0.50, 0.55, 0.60) rises
     monotonically (confidence discriminates direction)

  PASS  → all 3 hold on all 3 cells (5m, 15m, 30m)
  PARTIAL → all 3 hold on 2 of 3 cells
  FAIL  → otherwise

Run via Cloud Run Job. ONE invocation = ONE (family, tf) combination.

  gcloud run jobs execute strat-engine \\
      --update-env-vars="STRAT_RUN_ID=ext-${FAMILY}-${TF}" \\
      --args="-m,gcp.research.strat_engine.strat_dir_walk_forward_extended,--ticker=IWM,--tf=${TF},--family=${FAMILY}"
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from gcp.database import get_engine
from gcp.research.strat_engine.strat_config import (
    TICKERS, TIMEFRAMES,
    DEFAULT_ECE_CEILING,
    GCS_BUCKET_DEFAULT, gcs_model_prefix,
)
from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
from gcp.research.strat_engine.strat_pred_train import (
    featurize, expected_calibration_error,
)
from gcp.research.strat_engine.strat_walk_forward import (
    DEFAULT_CUTOFFS, MIN_TEST_BARS, _gcs_upload,
)
from gcp.research.strat_engine.strat_dir_walk_forward import (
    make_direction_lgbm, base_rate_logloss_binary,
)
from lib.features.experimental.news_sentiment import add_news_features
from lib.features.experimental.cross_asset import add_cross_asset_features
from lib.features.experimental.options_derived import add_options_features
from lib.features.experimental.vol_regime import add_vol_regime_features
from lib.logging_config import setup_logging
from sklearn.metrics import log_loss

setup_logging()
log = logging.getLogger(__name__)


FAMILY_JOINERS = {
    "news_sentiment": add_news_features,
    "cross_asset": add_cross_asset_features,
    "options_derived": add_options_features,
    "vol_regime": add_vol_regime_features,
}


def train_and_evaluate_fold_extended(X_full: np.ndarray, y_full: np.ndarray,
                                       bar_dates: np.ndarray,
                                       train_end: str, test_end: str,
                                       lgbm_n_jobs: int) -> dict:
    """Same shape as strat_dir_walk_forward.train_and_evaluate_fold, but
    extended thresh_rates to include 0.50 (the success-bar check needs
    monotonicity starting at 0.50)."""
    train_end_dt = np.datetime64(train_end)
    test_end_dt = np.datetime64(test_end)
    train_mask = bar_dates < train_end_dt
    test_mask = (bar_dates >= train_end_dt) & (bar_dates < test_end_dt)
    n_train = int(train_mask.sum())
    n_test = int(test_mask.sum())
    if n_test < MIN_TEST_BARS:
        return {"fold": f"{train_end}..{test_end}",
                "n_test": n_test, "n_train": n_train,
                "status": "SKIP_THIN"}

    X_tr = X_full[train_mask]
    X_te = X_full[test_mask]
    y_tr = y_full[train_mask]
    y_te = y_full[test_mask]

    model = make_direction_lgbm(n_jobs=lgbm_n_jobs)
    model.fit(X_tr, y_tr)

    proba = model.predict_proba(X_te)
    p_up = proba[:, 1]
    pred = (p_up >= 0.5).astype(int)

    ll = float(log_loss(y_te, proba, labels=[0, 1]))
    base_ll = base_rate_logloss_binary(y_tr, y_te)
    acc = float((pred == y_te).mean())
    base_acc = float(max(y_tr.mean(), 1 - y_tr.mean()))
    ece, _ = expected_calibration_error(y_te, proba, n_bins=10)

    thresh_rates = {}
    # Include 0.50 so monotonicity at success bar is measurable starting at
    # the natural decision threshold.
    for thresh in [0.50, 0.55, 0.60, 0.65, 0.70]:
        decisive = np.maximum(p_up, 1 - p_up) >= thresh
        n_dec = int(decisive.sum())
        if n_dec > 0:
            thresh_rates[thresh] = {
                "n": n_dec, "hit_rate": float((pred[decisive] == y_te[decisive]).mean())
            }
        else:
            thresh_rates[thresh] = {"n": 0, "hit_rate": None}

    return {
        "fold": f"{train_end}..{test_end}",
        "n_train": n_train,
        "n_test": n_test,
        "logloss": ll,
        "base_logloss": base_ll,
        "beat": base_ll - ll,
        "accuracy": acc,
        "base_accuracy": base_acc,
        "accuracy_beat_pp": (acc - base_acc) * 100,
        "ece": float(ece),
        "thresh_rates": thresh_rates,
        "up_share_train": float(y_tr.mean()),
        "up_share_test": float(y_te.mean()),
        "status": "OK",
    }


def score_family(folds: list) -> dict:
    """Apply success-bar test to a list of OK folds for one cell.

    Returns dict with:
      n_ok                : number of OK folds
      logloss_pass_count  : folds where beat > 0
      ece_pass_count      : folds where ece <= 0.05
      both_pass_count     : folds where BOTH (logloss > 0 AND ece <= 0.05)
      monotonic_thresh    : True if median hit-rate is monotone over
                            [0.50, 0.55, 0.60]
      cell_pass           : bool (binary): both_pass_count >= 6 AND
                            monotonic_thresh
    """
    ok = [f for f in folds if f.get("status") == "OK"]
    n_ok = len(ok)
    logloss_pass = sum(1 for f in ok if f["beat"] > 0)
    ece_pass = sum(1 for f in ok if f["ece"] <= DEFAULT_ECE_CEILING)
    both_pass = sum(1 for f in ok if f["beat"] > 0 and f["ece"] <= DEFAULT_ECE_CEILING)

    # Monotone hit rate across thresholds: take the median over folds at
    # each threshold and check 0.50 < 0.55 < 0.60. Tie / equal is allowed
    # (i.e. non-strictly monotonic) per the spec ("rises monotonically");
    # we use a small epsilon tolerance.
    def _median_hit(thresh: float) -> float | None:
        rates = []
        for f in ok:
            tr = f.get("thresh_rates", {}).get(thresh) or {}
            hr = tr.get("hit_rate")
            if hr is not None:
                rates.append(hr)
        return float(np.median(rates)) if rates else None

    h50 = _median_hit(0.50)
    h55 = _median_hit(0.55)
    h60 = _median_hit(0.60)
    monotonic = (h50 is not None and h55 is not None and h60 is not None
                 and h55 >= h50 - 1e-6 and h60 >= h55 - 1e-6)

    cell_pass = (both_pass >= 6 and monotonic and n_ok >= 6)

    return {
        "n_ok": n_ok,
        "logloss_pass_count": logloss_pass,
        "ece_pass_count": ece_pass,
        "both_pass_count": both_pass,
        "median_hit_0_50": h50,
        "median_hit_0_55": h55,
        "median_hit_0_60": h60,
        "monotonic_thresh": monotonic,
        "cell_pass": cell_pass,
    }


def walk_forward_extended(engine, ticker: str, tf: str, family: str,
                           cutoffs: list[str] | None = None) -> dict:
    cutoffs = cutoffs or DEFAULT_CUTOFFS
    log.info("=" * 70)
    log.info("EXTENDED WALK-FORWARD  %s %s  family=%s  %d cutoffs",
             ticker, tf, family, len(cutoffs))
    log.info("=" * 70)

    df = load_labeled_dataset(engine, ticker, tf, include_next_bar_ohlc=True)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date
    flat_mask = df["next_close"] == df["next_open"]
    n_flat = int(flat_mask.sum())
    if n_flat > 0:
        log.info("dropping %d flat-close bars", n_flat)
        df = df[~flat_mask].copy()
    log.info("loaded full dataset: %d rows (%s..%s)",
             len(df), df["bar_date"].min(), df["bar_date"].max())

    # ── join the experimental family ─────────────────────────────────
    if family == "baseline":
        joined_df = df
        log.info("family=baseline → no extension; running baseline harness verbatim")
    else:
        joiner = FAMILY_JOINERS.get(family)
        if joiner is None:
            raise RuntimeError(f"unknown family '{family}'; "
                               f"valid: {list(FAMILY_JOINERS)}")
        t_join = time.time()
        joined_df = joiner(df, ticker, engine)
        log.info("family=%s joiner ran in %.1fs (%d → %d cols)",
                 family, time.time() - t_join, df.shape[1], joined_df.shape[1])

    # ── featurize (same as baseline) ─────────────────────────────────
    t0 = time.time()
    X_df, feature_cols = featurize(joined_df)
    X_full = X_df.values.astype(np.float32, copy=False)
    y_full = (joined_df["next_close"] > joined_df["next_open"]).astype(np.int64).values
    bar_dates_arr = pd.DatetimeIndex(joined_df["bar_date"]).values.astype("datetime64[D]")
    log.info("featurize-once: %d rows × %d cols in %.1fs",
             X_full.shape[0], X_full.shape[1], time.time() - t0)
    log.info("global up-share: %.3f", float(y_full.mean()))

    cores = max(1, os.cpu_count() or 1)
    lgbm_n_jobs = cores

    folds = []
    for i, cut in enumerate(cutoffs):
        test_end = cutoffs[i + 1] if i + 1 < len(cutoffs) else \
            str(pd.Timestamp(joined_df["bar_date"].max()) + pd.Timedelta(days=1))[:10]
        log.info("─" * 70)
        log.info("fold %d/%d  train<%s  test=[%s..%s)",
                 i + 1, len(cutoffs), cut, cut, test_end)
        try:
            t1 = time.time()
            r = train_and_evaluate_fold_extended(
                X_full, y_full, bar_dates_arr, cut, test_end, lgbm_n_jobs)
            r["fold_seconds"] = round(time.time() - t1, 1)
            folds.append(r)
            if r["status"] == "OK":
                log.info("  n_train=%d  n_test=%d  up(tr/te)=%.3f/%.3f",
                         r["n_train"], r["n_test"], r["up_share_train"], r["up_share_test"])
                log.info("  logloss=%.4f  base=%.4f  beat=%+.4f",
                         r["logloss"], r["base_logloss"], r["beat"])
                log.info("  accuracy=%.3f  base=%.3f  Δ=%+.1fpp",
                         r["accuracy"], r["base_accuracy"], r["accuracy_beat_pp"])
                log.info("  ECE=%.4f  %s", r["ece"],
                         "PASS" if r["ece"] <= DEFAULT_ECE_CEILING else "FAIL")
                for thresh in [0.50, 0.55, 0.60]:
                    d = r["thresh_rates"].get(thresh, {})
                    if d.get("n", 0) > 0:
                        log.info("  dec≥%.2f: n=%d hit=%.3f",
                                 thresh, d["n"], d["hit_rate"])
            else:
                log.info("  %s (n_test=%d)", r["status"], r["n_test"])
        except Exception as e:
            log.exception("fold %s FAILED: %s", cut, e)
            folds.append({"fold": f"{cut}..{test_end}",
                          "status": "ERROR", "error": str(e)})

    # ── summary + scoring ────────────────────────────────────────────
    log.info("=" * 70)
    log.info("EXTENDED WALK-FORWARD SUMMARY  %s %s family=%s",
             ticker, tf, family)
    log.info("=" * 70)
    log.info("%-25s %8s %8s %8s %8s %8s %8s",
             "fold", "n_test", "beat", "acc_Δpp", "ece", "dec≥0.50", "dec≥0.60")
    log.info("-" * 90)
    for f in folds:
        if f.get("status") == "OK":
            d50 = f["thresh_rates"].get(0.50, {}).get("hit_rate")
            d60 = f["thresh_rates"].get(0.60, {}).get("hit_rate")
            log.info("%-25s %8d %+8.4f %+8.1f %8.4f %8s %8s",
                     f["fold"], f["n_test"], f["beat"], f["accuracy_beat_pp"],
                     f["ece"],
                     f"{d50:.3f}" if d50 is not None else "—",
                     f"{d60:.3f}" if d60 is not None else "—")
        else:
            log.info("%-25s %s", f["fold"], f.get("status", "?"))

    score = score_family(folds)
    log.info("-" * 90)
    log.info("SUCCESS-BAR SCORE  family=%s  cell=%s", family, tf)
    log.info("  n_ok folds         : %d", score["n_ok"])
    log.info("  log-loss beat > 0  : %d/%d", score["logloss_pass_count"], score["n_ok"])
    log.info("  ECE <= 0.05        : %d/%d", score["ece_pass_count"], score["n_ok"])
    log.info("  BOTH               : %d/%d", score["both_pass_count"], score["n_ok"])
    log.info("  median hit @0.50   : %s",
             f"{score['median_hit_0_50']:.3f}" if score['median_hit_0_50'] is not None else "—")
    log.info("  median hit @0.55   : %s",
             f"{score['median_hit_0_55']:.3f}" if score['median_hit_0_55'] is not None else "—")
    log.info("  median hit @0.60   : %s",
             f"{score['median_hit_0_60']:.3f}" if score['median_hit_0_60'] is not None else "—")
    log.info("  monotonic 0.50→0.60: %s", score["monotonic_thresh"])
    log.info("  CELL VERDICT       : %s", "PASS" if score["cell_pass"] else "FAIL")

    # ── persist ──────────────────────────────────────────────────────
    summary = {
        "ticker": ticker, "tf": tf, "family": family,
        "target": "direction (next_close > next_open)",
        "cutoffs": cutoffs,
        "calibration": "none",
        "min_test_bars": MIN_TEST_BARS,
        "folds": folds,
        "score": score,
        "computed_at": pd.Timestamp.utcnow().isoformat(),
    }
    prefix = gcs_model_prefix(ticker, tf)
    blob = (f"{prefix}/dir_extended_walk_forward_{family}_{int(time.time())}.json")
    _gcs_upload(json.dumps(summary, indent=2, default=str).encode(), blob)
    log.info("saved: gs://%s/%s",
             os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT), blob)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--family", required=True,
                   choices=list(FAMILY_JOINERS) + ["baseline"],
                   help="Which experimental family to test (or 'baseline' "
                        "for a sanity-check no-extension run)")
    p.add_argument("--cutoffs", default=None,
                   help="Comma-separated YYYY-MM-DD cutoffs (default: 8 regime-spanning)")
    args = p.parse_args()
    cutoffs = args.cutoffs.split(",") if args.cutoffs else None
    engine = get_engine()
    walk_forward_extended(engine, args.ticker, args.tf, args.family,
                            cutoffs=cutoffs)


if __name__ == "__main__":
    main()
