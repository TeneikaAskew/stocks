"""Strat Engine — REGIME-CONDITIONAL direction walk-forward (DIR-REGIME).

Reframing #3 from the 2026-06-04 rethink. The pooled direction model
(strat_dir_walk_forward) failed 24/24 folds because the SAME bar means opposite
things in opposite dealer-gamma regimes:

  * positive gamma  → dealers sell rips / buy dips → MEAN-REVERSION
  * negative gamma  → dealers chase the move       → MOMENTUM / trend

A single model trained across both regimes averages "fade it" and "follow it"
to ≈0 — exactly the observed null. This script SPLITS train and test by gamma
regime and trains one direction model per regime, asking whether either
conditional model beats its own base rate even though the pooled one didn't.

Honest control: a regime is itself a coarse signal (neg-gamma ≈ trend day), so
we ALSO report a naive "follow-the-regime" benchmark (in neg-gamma predict the
prior bar's direction continues; in pos-gamma predict it reverses). The model
has to beat THAT, not just the unconditional base rate.

Target / features / hyperparameters are identical to strat_dir_walk_forward;
the only change is the per-regime split. Vehicle is the UNDERLYING (no IV to
beat), so we also report directional accuracy and per-trade expectancy in ATR.

Run:
  python -m gcp.research.strat_engine.dir_regime_walk_forward --ticker IWM --tf 15m
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from gcp.database import get_engine
from gcp.research.strat_engine.strat_config import (
    TICKERS, TIMEFRAMES, DEFAULT_ECE_CEILING,
    GCS_BUCKET_DEFAULT, gcs_model_prefix,
)
from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
from gcp.research.strat_engine.strat_pred_train import featurize
from gcp.research.strat_engine.strat_walk_forward import (
    DEFAULT_CUTOFFS, MIN_TEST_BARS, _gcs_upload,
)
from gcp.research.strat_engine.strat_dir_walk_forward import (
    make_direction_lgbm, base_rate_logloss_binary,
)
from lib.logging_config import setup_logging
from sklearn.metrics import log_loss

setup_logging()
log = logging.getLogger(__name__)

# A regime split needs enough bars per side to train a stable tree; below this
# the per-regime fold is reported but excluded from the pass count.
MIN_REGIME_BARS = 150


def assign_regime(df: pd.DataFrame) -> np.ndarray:
    """Per-bar dealer-gamma regime ∈ {'pos','neg', None}.

    Primary source = the persisted `gamma_regime` string. Fallback = sign of
    (close − flip_price): above the gamma flip ≈ positive-gamma (suppressive),
    below ≈ negative-gamma (amplifying). Bars with neither signal → None
    (excluded — we never fabricate a regime for a bar with no gamma data; that
    would be a silent fallback per CLAUDE.md Rule 3.7).
    """
    out = np.full(len(df), None, dtype=object)
    gr = df.get("gamma_regime")
    flip = df.get("flip_price")
    close = df.get("close")
    if gr is not None:
        s = gr.astype("string").str.lower()
        out[s.str.contains("pos", na=False).values] = "pos"
        out[s.str.contains("neg", na=False).values] = "neg"
    # Fallback only where gamma_regime gave nothing but flip_price exists.
    if flip is not None and close is not None:
        need = np.array([o is None for o in out])
        have_flip = need & flip.notna().values & close.notna().values
        diff = (close - flip).values
        out[have_flip & (diff > 0)] = "pos"
        out[have_flip & (diff <= 0)] = "neg"
    return out


def _naive_regime_follow_acc(prev_up: np.ndarray, regime: np.ndarray,
                              y: np.ndarray) -> float:
    """Control benchmark. neg-gamma → predict prior-bar direction continues;
    pos-gamma → predict it reverses. Accuracy on the given subset."""
    pred = np.where(regime == "neg", prev_up, 1 - prev_up)
    return float((pred == y).mean()) if len(y) else float("nan")


def _eval_regime_fold(X, y, prev_up, atr_norm, mask_tr, mask_te, regime_val):
    n_tr, n_te = int(mask_tr.sum()), int(mask_te.sum())
    if n_te < MIN_REGIME_BARS or n_tr < MIN_REGIME_BARS:
        return {"regime": regime_val, "n_train": n_tr, "n_test": n_te,
                "status": "SKIP_THIN"}
    model = make_direction_lgbm()
    model.fit(X[mask_tr], y[mask_tr])
    proba = model.predict_proba(X[mask_te])
    p_up = proba[:, 1]
    pred = (p_up >= 0.5).astype(int)
    ll = float(log_loss(y[mask_te], proba, labels=[0, 1]))
    base_ll = base_rate_logloss_binary(y[mask_tr], y[mask_te])
    acc = float((pred == y[mask_te]).mean())
    naive_acc = _naive_regime_follow_acc(prev_up[mask_te], np.array([regime_val] * n_te), y[mask_te])
    # Per-trade expectancy on the UNDERLYING: take the model's side, P&L in ATR
    # = signed next-bar move / atr. dir = +1 if pred up else -1.
    side = np.where(pred == 1, 1.0, -1.0)
    exp_atr = float(np.nanmean(side * atr_norm[mask_te]))
    return {
        "regime": regime_val, "n_train": n_tr, "n_test": n_te,
        "logloss": ll, "base_logloss": base_ll, "beat": base_ll - ll,
        "accuracy": acc, "naive_regime_acc": naive_acc,
        "acc_minus_naive_pp": (acc - naive_acc) * 100,
        "expectancy_atr": exp_atr,
        "status": "OK",
    }


def walk_forward_regime(engine, ticker: str, tf: str, cutoffs=None) -> dict:
    cutoffs = cutoffs or DEFAULT_CUTOFFS
    log.info("=" * 72)
    log.info("DIR-REGIME WALK-FORWARD  %s %s", ticker, tf)
    log.info("=" * 72)

    df = load_labeled_dataset(engine, ticker, tf, include_next_bar_ohlc=True)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date
    flat = df["next_close"] == df["next_open"]
    if flat.any():
        df = df[~flat].copy()
    df = df.reset_index(drop=True)

    regime = assign_regime(df)
    cov = float(np.mean([r is not None for r in regime]))
    log.info("gamma-regime coverage: %.1f%% of %d bars (pos=%d neg=%d none=%d)",
             100 * cov, len(df),
             int((regime == "pos").sum()), int((regime == "neg").sum()),
             int(np.sum([r is None for r in regime])))
    if cov < 0.25:
        log.warning("LOW gamma coverage (%.1f%%) — regime split only valid on the "
                    "covered span; early years likely lack GEX.", 100 * cov)

    X_df, feat_cols = featurize(df)
    X = X_df.values.astype(np.float32, copy=False)
    y = (df["next_close"] > df["next_open"]).astype(np.int64).values
    # prior-bar realized direction (for the naive control); session-naive ok.
    prev_up = (df["close"] > df["open"]).astype(np.int64).values
    atr = df["atr_20"].replace(0, np.nan).values
    atr_norm = ((df["next_close"] - df["next_open"]).abs().values) / atr
    bar_dates = pd.DatetimeIndex(df["bar_date"]).values.astype("datetime64[D]")

    folds = []
    for i, cut in enumerate(cutoffs):
        test_end = cutoffs[i + 1] if i + 1 < len(cutoffs) else \
            str(pd.Timestamp(df["bar_date"].max()) + pd.Timedelta(days=1))[:10]
        tr = bar_dates < np.datetime64(cut)
        te = (bar_dates >= np.datetime64(cut)) & (bar_dates < np.datetime64(test_end))
        if int(te.sum()) < MIN_TEST_BARS:
            folds.append({"fold": f"{cut}..{test_end}", "status": "SKIP_THIN",
                          "n_test": int(te.sum())})
            continue
        fold = {"fold": f"{cut}..{test_end}", "per_regime": {}}
        for rv in ("pos", "neg"):
            rmask = (regime == rv)
            r = _eval_regime_fold(X, y, prev_up, atr_norm,
                                  tr & rmask, te & rmask, rv)
            fold["per_regime"][rv] = r
            if r["status"] == "OK":
                log.info("  %s  %s  n_te=%d beat=%+.4f acc=%.3f naive=%.3f Δ=%+.1fpp exp=%+.3fATR",
                         fold["fold"], rv.upper(), r["n_test"], r["beat"],
                         r["accuracy"], r["naive_regime_acc"],
                         r["acc_minus_naive_pp"], r["expectancy_atr"])
        folds.append(fold)

    # Verdict: a regime PASSES if it beats base-rate log-loss AND beats the
    # naive-regime control in ≥5 of its OK folds.
    summary_verdict = {}
    for rv in ("pos", "neg"):
        oks = [f["per_regime"][rv] for f in folds
               if f.get("per_regime", {}).get(rv, {}).get("status") == "OK"]
        beat_folds = sum(1 for r in oks if r["beat"] > 0)
        edge_folds = sum(1 for r in oks if r["acc_minus_naive_pp"] > 0)
        verdict = "PASS" if (len(oks) >= 4 and beat_folds >= 5 and edge_folds >= 5) \
            else ("INSUFFICIENT_DATA" if len(oks) < 4 else "FAIL")
        summary_verdict[rv] = {
            "ok_folds": len(oks), "logloss_beat_folds": beat_folds,
            "beat_naive_folds": edge_folds,
            "median_expectancy_atr": float(np.median([r["expectancy_atr"] for r in oks])) if oks else None,
            "verdict": verdict,
        }
        log.info("REGIME %s verdict: %s (beat base %d, beat naive %d, of %d OK folds)",
                 rv.upper(), verdict, beat_folds, edge_folds, len(oks))

    summary = {
        "ticker": ticker, "tf": tf, "model": "DIR-REGIME",
        "target": "direction (next_close>next_open), split by gamma regime",
        "gamma_coverage": cov, "cutoffs": cutoffs,
        "verdict": summary_verdict, "folds": folds,
        "computed_at": pd.Timestamp.utcnow().isoformat(),
    }
    blob = f"{gcs_model_prefix(ticker, tf)}/dir_regime_wf_{int(time.time())}.json"
    _gcs_upload(json.dumps(summary, indent=2, default=str).encode(), blob)
    log.info("saved gs://%s/%s", os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT), blob)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--cutoffs", default=None)
    args = p.parse_args()
    cutoffs = args.cutoffs.split(",") if args.cutoffs else None
    walk_forward_regime(get_engine(), args.ticker, args.tf, cutoffs=cutoffs)


if __name__ == "__main__":
    main()
