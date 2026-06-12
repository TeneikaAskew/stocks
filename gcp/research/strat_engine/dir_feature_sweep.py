#!/usr/bin/env python3
"""Direction feature-and-target sweep — the "did we REALLY exhaust direction?" test.

E-07/E-08 only ever ADDED feature families on top of the spine, kept ONE target
(unconditional next-bar body direction), and used ONE model. This script closes
those gaps by reusing the EXACT production harness pieces (no throwaway
reimplementation — Rule 3.6):

  load_labeled_dataset → [optional options-flow join] → featurize → make_direction_lgbm

and sweeping a grid of FEATURE SETS × TARGETS under the same held-out per-year
walk-forward (train strictly before each test cutoff).

FEATURE SETS (ablation / selection / replacement — never tried before):
  spine            the full ~75-col baseline (E-07 reference)
  spine_optflow    spine + options-flow (PCR / IV-skew / ATM-IV — the new family)
  optflow_only     options-flow columns alone
  topk_mi          top-K spine features by train-set mutual information (SELECTION)
  drop_gamma       spine minus gamma/GEX/VEX/king/gate/flip/dealer/vix (ablation)
  drop_categorical spine minus the one-hot strat/regime columns (ablation)

TARGETS (alternative labels — never tried before):
  uncond     next_close > next_open                       (E-07 baseline)
  highconv   same sign, but ONLY on decisive bars where
             |next_close-next_open| ≥ 0.5·atr_14          (is direction learnable
                                                           when the move is big?)
  cc1        next_close > close                           (close-to-close, 1 bar)

For each (feature_set × target) it reports pooled held-out log-loss beat,
accuracy beat (pp), and decisive-hit rate. A POSITIVE, robust log-loss beat on
any cell would be the first evidence that direction is learnable — overturning
the 24/24 fail. Anything ≤0 confirms the fail is real, not a feature/target
artifact.

    python -m gcp.research.strat_engine.dir_feature_sweep --ticker IWM --tf 15m
"""
from __future__ import annotations
import argparse
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from gcp.database import get_engine
from gcp.research.strat_engine.strat_config import TICKERS, TIMEFRAMES
from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
from gcp.research.strat_engine.strat_pred_train import featurize
from gcp.research.strat_engine.strat_walk_forward import DEFAULT_CUTOFFS, MIN_TEST_BARS
from gcp.research.strat_engine.strat_dir_walk_forward import (
    make_direction_lgbm, base_rate_logloss_binary,
)
from lib.features.experimental.options_derived import add_options_features
from lib.logging_config import setup_logging
from sklearn.metrics import log_loss
from sklearn.feature_selection import mutual_info_classif

setup_logging()
log = logging.getLogger(__name__)

TOPK = 20
_GAMMA_KEYS = ("gex", "vex", "gamma", "king", "gate", "flip", "dealer", "vix")
_CAT_KEYS = ("candle", "combo", "tercile", "regime")
_OPTFLOW_KEYS = ("pcr", "iv_skew", "atm_iv", "iv_term", "iv_atm")


def _col_has(name: str, keys) -> bool:
    n = name.lower()
    return any(k in n for k in keys)


def _feature_sets(feature_cols: list[str]) -> dict[str, list[str]]:
    spine = [c for c in feature_cols if not _col_has(c, _OPTFLOW_KEYS)]
    optflow = [c for c in feature_cols if _col_has(c, _OPTFLOW_KEYS)]
    return {
        "spine": spine,
        "spine_optflow": spine + optflow,
        "optflow_only": optflow,
        "drop_gamma": [c for c in spine if not _col_has(c, _GAMMA_KEYS)],
        "drop_categorical": [c for c in spine if not _col_has(c, _CAT_KEYS)],
        # topk_mi is resolved per-fold (depends on train data) — marker only
        "topk_mi": spine,
    }


def _targets(joined: pd.DataFrame) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Return {name: (y, row_mask)}. row_mask selects which rows are scorable for
    that target (e.g. highconv keeps only decisive-move bars)."""
    no, nc = joined["next_open"].values, joined["next_close"].values
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    full = np.ones(len(joined), dtype=bool)
    out["uncond"] = ((nc > no).astype(np.int64), full)
    # high-conviction: only bars whose body move clears 0.5*ATR
    atr = joined["atr_14"].values if "atr_14" in joined.columns else np.full(len(joined), np.nan)
    body = np.abs(nc - no)
    hc_mask = np.isfinite(atr) & (atr > 0) & (body >= 0.5 * atr)
    out["highconv"] = ((nc > no).astype(np.int64), hc_mask)
    # close-to-close 1-bar (needs current close)
    if "close" in joined.columns:
        c = joined["close"].values
        out["cc1"] = ((nc > c).astype(np.int64), full)
    return out


def _pooled_eval(X: np.ndarray, y: np.ndarray, bar_dates: np.ndarray,
                 row_mask: np.ndarray, cols_idx: np.ndarray,
                 cutoffs: list[str], topk: bool) -> dict | None:
    """Held-out per-year LightGBM over the masked rows; pooled stats."""
    accs = bases = beats = abeats = ntot = 0.0
    for i, cut in enumerate(cutoffs):
        end = cutoffs[i + 1] if i + 1 < len(cutoffs) else \
            str(np.datetime64(bar_dates.max()) + np.timedelta64(1, "D"))
        cut64, end64 = np.datetime64(cut), np.datetime64(end)
        tr = (bar_dates < cut64) & row_mask
        te = (bar_dates >= cut64) & (bar_dates < end64) & row_mask
        ntr, nte = int(tr.sum()), int(te.sum())
        if nte < MIN_TEST_BARS or ntr < 400:
            continue
        Xtr, Xte = X[tr][:, cols_idx], X[te][:, cols_idx]
        ytr, yte = y[tr], y[te]
        if len(np.unique(ytr)) < 2:
            continue
        idx = cols_idx
        if topk and Xtr.shape[1] > TOPK:
            mi = mutual_info_classif(Xtr, ytr, random_state=42)
            keep = np.argsort(mi)[::-1][:TOPK]
            Xtr, Xte = Xtr[:, keep], Xte[:, keep]
        model = make_direction_lgbm(n_jobs=-1)
        model.fit(Xtr, ytr)
        p = model.predict_proba(Xte)[:, 1]
        ll = log_loss(yte, p, labels=[0, 1])
        base_ll = base_rate_logloss_binary(ytr, yte)
        acc = ((p >= 0.5).astype(int) == yte).mean()
        base_acc = max(yte.mean(), 1 - yte.mean())
        beats += (base_ll - ll) * nte
        abeats += (acc - base_acc) * nte
        accs += acc * nte
        bases += base_acc * nte
        ntot += nte
    if ntot == 0:
        return None
    return {"n": int(ntot), "acc": accs / ntot, "base": bases / ntot,
            "beat": beats / ntot, "acc_beat_pp": 100 * abeats / ntot}


def run(engine, ticker: str, tf: str, cutoffs: list[str]) -> None:
    log.info("=" * 78)
    log.info("DIRECTION FEATURE+TARGET SWEEP  %s %s", ticker, tf)
    log.info("=" * 78)
    df = load_labeled_dataset(engine, ticker, tf, include_next_bar_ohlc=True)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date
    df = df[df["next_close"] != df["next_open"]].copy()
    t0 = time.time()
    joined = add_options_features(df, ticker, engine)
    log.info("options-flow join: %d→%d cols in %.1fs", df.shape[1],
             joined.shape[1], time.time() - t0)
    X_df, feature_cols = featurize(joined)
    X = X_df.values.astype(np.float32, copy=False)
    bar_dates = pd.DatetimeIndex(joined["bar_date"]).values.astype("datetime64[D]")
    sets = _feature_sets(feature_cols)
    targets = _targets(joined)
    name_to_idx = {c: i for i, c in enumerate(feature_cols)}
    log.info("rows=%d  features=%d  optflow_cols=%d", len(X), len(feature_cols),
             len(sets["optflow_only"]))

    for tname, (y, rmask) in targets.items():
        log.info("─" * 78)
        log.info("TARGET=%s  scorable_rows=%d  up_share=%.3f", tname,
                 int(rmask.sum()), float(y[rmask].mean()) if rmask.sum() else float("nan"))
        log.info("  %-16s %7s %7s %7s %9s %10s", "feature_set", "n", "acc",
                 "base", "beat_LL", "acc_Δpp")
        for sname, cols in sets.items():
            idx = np.array([name_to_idx[c] for c in cols if c in name_to_idx], dtype=int)
            if idx.size == 0:
                log.info("  %-16s (no cols)", sname); continue
            r = _pooled_eval(X, y, bar_dates, rmask, idx, cutoffs,
                             topk=(sname == "topk_mi"))
            if r is None:
                log.info("  %-16s (thin)", sname); continue
            flag = "  <== POSITIVE" if r["beat"] > 0 else ""
            log.info("  %-16s %7d %6.1f%% %6.1f%% %+9.4f %+9.1f%s", sname, r["n"],
                     100 * r["acc"], 100 * r["base"], r["beat"], r["acc_beat_pp"], flag)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--cutoffs", default=None)
    args = p.parse_args()
    cutoffs = args.cutoffs.split(",") if args.cutoffs else list(DEFAULT_CUTOFFS)
    engine = get_engine()
    run(engine, args.ticker, args.tf, cutoffs)


if __name__ == "__main__":
    main()
