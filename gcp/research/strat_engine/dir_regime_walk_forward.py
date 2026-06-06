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


def _eval_regime_fold(X, y, prev_up, pnl_signed, mask_tr, mask_te, regime_val):
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
    # Per-trade expectancy on the UNDERLYING. CORRECTED: P&L = side × SIGNED
    # move (the prior version multiplied side by |move|, which credits a long
    # with +|move| regardless of the move's actual sign — a bug that made
    # expectancy meaningless). side=+1 long / -1 short.
    side = np.where(pred == 1, 1.0, -1.0)
    exp = float(np.nanmean(side * pnl_signed[mask_te]))
    # also the model's edge over just-trade-with-the-regime (the honest control)
    naive_side = np.where(np.array([regime_val] * n_te) == "neg",
                          np.where(prev_up[mask_te] == 1, 1.0, -1.0),
                          np.where(prev_up[mask_te] == 1, -1.0, 1.0))
    naive_exp = float(np.nanmean(naive_side * pnl_signed[mask_te]))
    return {
        "regime": regime_val, "n_train": n_tr, "n_test": n_te,
        "logloss": ll, "base_logloss": base_ll, "beat": base_ll - ll,
        "accuracy": acc, "naive_regime_acc": naive_acc,
        "acc_minus_naive_pp": (acc - naive_acc) * 100,
        "expectancy": exp, "naive_expectancy": naive_exp,
        "exp_minus_naive": exp - naive_exp,
        "status": "OK",
    }


def walk_forward_regime(engine, ticker: str, tf: str, cutoffs=None,
                         target: str = "fwd", horizon_bars: int = 5) -> dict:
    cutoffs = cutoffs or DEFAULT_CUTOFFS
    log.info("=" * 72)
    log.info("DIR-REGIME WALK-FORWARD  %s %s  target=%s H=%d", ticker, tf, target, horizon_bars)
    log.info("=" * 72)

    df = load_labeled_dataset(engine, ticker, tf, include_next_bar_ohlc=True)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date
    df = df.reset_index(drop=True)

    # TARGET (corrected). The regime hypothesis is about whether a MOVE
    # continues or reverts — not the noisiest possible target (single-bar
    # close>open). 'fwd' uses the persisted N-bar forward return so the move has
    # room to develop; P&L is that SIGNED return (bps). 'body' keeps the old
    # next_close>next_open for comparison.
    if target == "fwd":
        col = f"fwd_ret_{horizon_bars}bars_bps"
        if col not in df.columns:
            raise SystemExit(f"missing {col}; available fwd cols: "
                             f"{[c for c in df.columns if c.startswith('fwd_ret')]}")
        pnl_signed = df[col].astype(float).values        # signed, bps
        valid = np.isfinite(pnl_signed) & (pnl_signed != 0)
        df = df[valid].reset_index(drop=True)
        pnl_signed = pnl_signed[valid]
        y = (pnl_signed > 0).astype(np.int64)
    else:  # body
        flat = (df["next_close"] == df["next_open"]).values
        df = df[~flat].reset_index(drop=True)
        atr = df["atr_20"].replace(0, np.nan).values
        pnl_signed = ((df["next_close"] - df["next_open"]).values) / atr  # signed, ATR
        y = (df["next_close"] > df["next_open"]).astype(np.int64).values

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
    # prior-bar realized direction (for the naive control); session-naive ok.
    prev_up = (df["close"] > df["open"]).astype(np.int64).values
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
            r = _eval_regime_fold(X, y, prev_up, pnl_signed,
                                  tr & rmask, te & rmask, rv)
            fold["per_regime"][rv] = r
            if r["status"] == "OK":
                log.info("  %s  %s  n_te=%d acc=%.3f beat_ll=%+.4f | model_exp=%+.3f "
                         "naive_exp=%+.3f Δexp=%+.3f",
                         fold["fold"], rv.upper(), r["n_test"], r["accuracy"], r["beat"],
                         r["expectancy"], r["naive_expectancy"], r["exp_minus_naive"])
        folds.append(fold)

    # Verdict (CORRECTED): the regime hypothesis is tradeable-direction, so the
    # bar is EXPECTANCY, not log-loss. A regime PASSES if the model's per-trade
    # expectancy is > 0 AND beats the naive-regime-follow expectancy in ≥5 OK
    # folds. (Log-loss beat is still recorded, but it is NOT the gate — a
    # positive-expectancy edge can coexist with no log-loss improvement on a
    # near-50/50 sign.)
    summary_verdict = {}
    for rv in ("pos", "neg"):
        oks = [f["per_regime"][rv] for f in folds
               if f.get("per_regime", {}).get(rv, {}).get("status") == "OK"]
        exp_pos = sum(1 for r in oks if r["expectancy"] > 0)
        beat_naive = sum(1 for r in oks if r["exp_minus_naive"] > 0)
        ll_beat = sum(1 for r in oks if r["beat"] > 0)
        verdict = "PASS" if (len(oks) >= 4 and exp_pos >= 5 and beat_naive >= 5) \
            else ("INSUFFICIENT_DATA" if len(oks) < 4 else "FAIL")
        summary_verdict[rv] = {
            "ok_folds": len(oks), "expectancy_positive_folds": exp_pos,
            "beat_naive_expectancy_folds": beat_naive, "logloss_beat_folds": ll_beat,
            "median_expectancy": float(np.median([r["expectancy"] for r in oks])) if oks else None,
            "verdict": verdict,
        }
        log.info("REGIME %s verdict: %s (exp>0 in %d, beat-naive-exp in %d, ll-beat in %d, of %d OK folds)",
                 rv.upper(), verdict, exp_pos, beat_naive, ll_beat, len(oks))

    summary = {
        "ticker": ticker, "tf": tf, "model": "DIR-REGIME",
        "target": f"{target} (H={horizon_bars}) move-direction, split by gamma regime, judged on expectancy",
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
    p.add_argument("--target", default="fwd", choices=["fwd", "body"],
                   help="fwd=sign of N-bar forward return (move continuation, "
                        "the corrected target); body=next_close>next_open (old).")
    p.add_argument("--horizon-bars", type=int, default=5)
    p.add_argument("--cutoffs", default=None)
    args = p.parse_args()
    cutoffs = args.cutoffs.split(",") if args.cutoffs else None
    walk_forward_regime(get_engine(), args.ticker, args.tf, cutoffs=cutoffs,
                        target=args.target, horizon_bars=args.horizon_bars)


if __name__ == "__main__":
    main()
