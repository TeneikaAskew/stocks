"""Magnitude Engine — anchored walk-forward.

Same 8-cutoff schedule as strat_engine. For each fold:
  - full retrain + (optional) recalibrate from scratch
  - log-loss vs train-prior base rate
  - ECE (multiclass max-proba binning)
  - decisive-call hit rate across [0.40, 0.50, 0.60, 0.70]
  - EXPLOSIVE-bucket lift over base rate

Per-fold rows go to GCS as gs://.../research/magnitude_engine/{phase}/{ticker}_{tf}/walk_forward_{ts}.json
Per-fold rows ALSO go to a Cloud SQL `magnitude_walk_forward_results` table
(audit pattern from strat_engine) so the results doc can be SQL-assembled.

Run:
  python -m gcp.research.magnitude_engine.mag_walk_forward \\
      --phase phase0 --ticker IWM --tf 15m
  python -m gcp.research.magnitude_engine.mag_walk_forward \\
      --phase phase0 --all-cells
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

from gcp.database import get_engine, execute_sql
from gcp.research.magnitude_engine.mag_config import (
    TICKERS, TIMEFRAMES, PHASES,
    LABEL_COL, LABEL_CLASSES, LABEL_TO_IDX,
    DEFAULT_CUTOFFS, MIN_TEST_BARS,
    DEFAULT_CALIBRATION, DEFAULT_CV,
    ECE_CEILING_BY_TF, SUCCESS_BAR_EXPLOSIVE_LIFT_MIN,
    SUCCESS_BAR_CONFIDENCE_THRESHOLDS,
    SUCCESS_BAR_MIN_FOLDS_LOGLOSS, SUCCESS_BAR_MIN_FOLDS_ECE,
    SUCCESS_BAR_MIN_FOLDS_LIFT,
    GCS_BUCKET_DEFAULT, gcs_run_prefix,
)
from gcp.research.magnitude_engine.mag_dataset import load_magnitude_dataset
from gcp.research.magnitude_engine.mag_pred_train import (
    featurize, make_lgbm, expected_calibration_error,
    decisive_call_hit_rate, explosive_lift,
)
from google.cloud import storage as gcs
from lib.logging_config import setup_logging
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import log_loss

setup_logging()
log = logging.getLogger(__name__)


# ─────────────────────── DDL for the results table ───────────────────────
# Idempotent — runs once on first dispatch. Keyed by (phase, ticker, tf,
# fold, computed_at). Allows multiple re-runs to coexist; consumer
# queries pick the latest `computed_at` per cell.
RESULTS_DDL_CREATE = """
CREATE TABLE IF NOT EXISTS magnitude_walk_forward_results (
    id              BIGSERIAL PRIMARY KEY,
    phase           VARCHAR(20)  NOT NULL,
    ticker          VARCHAR(10)  NOT NULL,
    tf              VARCHAR(5)   NOT NULL,
    fold            VARCHAR(32)  NOT NULL,
    train_end       DATE,
    test_end        DATE,
    n_train         INTEGER,
    n_test          INTEGER,
    status          VARCHAR(16),
    logloss         DOUBLE PRECISION,
    base_logloss    DOUBLE PRECISION,
    beat            DOUBLE PRECISION,
    ece             DOUBLE PRECISION,
    ece_ceiling     DOUBLE PRECISION,
    ece_pass        BOOLEAN,
    accuracy        DOUBLE PRECISION,
    base_accuracy   DOUBLE PRECISION,
    accuracy_beat_pp DOUBLE PRECISION,
    explosive_base_rate    DOUBLE PRECISION,
    explosive_precision    DOUBLE PRECISION,
    explosive_lift         DOUBLE PRECISION,
    decisive_hit_json      TEXT,
    fold_seconds    INTEGER,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    run_id          VARCHAR(64),
    UNIQUE (phase, ticker, tf, fold, run_id)
)
"""
RESULTS_DDL_INDEX = """
CREATE INDEX IF NOT EXISTS ix_mwfr_cell ON
    magnitude_walk_forward_results (phase, ticker, tf, computed_at DESC)
"""


def _gcs_upload(content: bytes, blob_path: str, ctype: str = "application/json"):
    bucket_name = os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT)
    gcs.Client().bucket(bucket_name).blob(blob_path).upload_from_string(
        content, content_type=ctype)
    return f"gs://{bucket_name}/{blob_path}"


def _base_rate_logloss(y_train_idx: np.ndarray, y_test_idx: np.ndarray) -> float:
    prior = np.bincount(y_train_idx, minlength=len(LABEL_CLASSES)) / len(y_train_idx)
    proba = np.tile(prior, (len(y_test_idx), 1))
    return float(log_loss(
        y_test_idx, proba, labels=list(range(len(LABEL_CLASSES)))))


def train_and_evaluate_fold(X_full: np.ndarray, y_full: np.ndarray,
                             bar_dates: np.ndarray,
                             train_end: str, test_end: str,
                             tf: str,
                             lgbm_n_jobs: int,
                             calibration: str = DEFAULT_CALIBRATION,
                             cv: int = DEFAULT_CV) -> dict:
    train_end_dt = np.datetime64(train_end)
    test_end_dt = np.datetime64(test_end)
    train_mask = bar_dates < train_end_dt
    test_mask = (bar_dates >= train_end_dt) & (bar_dates < test_end_dt)
    n_train = int(train_mask.sum())
    n_test = int(test_mask.sum())
    if n_test < MIN_TEST_BARS:
        return {"fold": f"{train_end}..{test_end}",
                "train_end": train_end, "test_end": test_end,
                "n_test": n_test, "n_train": n_train,
                "status": "SKIP_THIN"}

    X_tr = X_full[train_mask]; X_te = X_full[test_mask]
    y_tr = y_full[train_mask]; y_te = y_full[test_mask]

    if calibration == "none":
        model = make_lgbm(class_weight=None, n_jobs=-1)
        model.fit(X_tr, y_tr)
        proba = model.predict_proba(X_te)
    else:
        calibrated = CalibratedClassifierCV(
            estimator=make_lgbm(class_weight=None, n_jobs=lgbm_n_jobs),
            method=calibration, cv=cv, n_jobs=cv,
        )
        calibrated.fit(X_tr, y_tr)
        proba = calibrated.predict_proba(X_te)

    ll = float(log_loss(y_te, proba, labels=list(range(len(LABEL_CLASSES)))))
    base_ll = _base_rate_logloss(y_tr, y_te)
    pred = np.argmax(proba, axis=1)
    acc = float((pred == y_te).mean())
    train_majority = int(np.bincount(y_tr, minlength=len(LABEL_CLASSES)).argmax())
    base_acc = float((y_te == train_majority).mean())
    ece, ece_bins = expected_calibration_error(y_te, proba, n_bins=10)

    ece_ceiling = ECE_CEILING_BY_TF[tf]
    ece_pass = ece <= ece_ceiling

    decisive = decisive_call_hit_rate(y_te, proba, SUCCESS_BAR_CONFIDENCE_THRESHOLDS)
    explosive = explosive_lift(y_te, proba, explosive_idx=LABEL_TO_IDX["EXPLOSIVE"])

    return {
        "fold": f"{train_end}..{test_end}",
        "train_end": train_end, "test_end": test_end,
        "n_train": n_train, "n_test": n_test,
        "logloss": ll, "base_logloss": base_ll, "beat": base_ll - ll,
        "accuracy": acc, "base_accuracy": base_acc,
        "accuracy_beat_pp": (acc - base_acc) * 100,
        "ece": float(ece), "ece_ceiling": ece_ceiling, "ece_pass": ece_pass,
        "ece_bins": ece_bins,
        "decisive_hit": decisive,
        "explosive": explosive,
        "status": "OK",
    }


def _persist_results_table(engine, phase: str, ticker: str, tf: str,
                            folds: list[dict], run_id: str) -> None:
    """Insert per-fold rows into magnitude_walk_forward_results."""
    rows = []
    for f in folds:
        rows.append({
            "phase": phase, "ticker": ticker, "tf": tf,
            "fold": f.get("fold", "?"),
            "train_end": f.get("train_end"),
            "test_end": f.get("test_end"),
            "n_train": f.get("n_train"),
            "n_test": f.get("n_test"),
            "status": f.get("status"),
            "logloss": f.get("logloss"),
            "base_logloss": f.get("base_logloss"),
            "beat": f.get("beat"),
            "ece": f.get("ece"),
            "ece_ceiling": f.get("ece_ceiling"),
            "ece_pass": f.get("ece_pass"),
            "accuracy": f.get("accuracy"),
            "base_accuracy": f.get("base_accuracy"),
            "accuracy_beat_pp": f.get("accuracy_beat_pp"),
            "explosive_base_rate": (f.get("explosive") or {}).get("base_rate"),
            "explosive_precision": (f.get("explosive") or {}).get("precision"),
            "explosive_lift": (f.get("explosive") or {}).get("lift"),
            "decisive_hit_json": json.dumps(f.get("decisive_hit", {})),
            "fold_seconds": f.get("fold_seconds"),
            "run_id": run_id,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return
    # Use pandas-to-sql with append; the table has UNIQUE (phase,ticker,tf,fold,run_id)
    # which prevents accidental duplicate-row insertion on re-dispatch (the run_id changes per execution).
    with engine.begin() as conn:
        df.to_sql("magnitude_walk_forward_results", conn,
                   if_exists="append", index=False, method="multi")
    log.info("persisted %d folds to magnitude_walk_forward_results", len(df))


def _evaluate_phase_gate(folds: list[dict], tf: str) -> dict:
    """Apply the pre-set success bar to a phase's folds and return a verdict."""
    ok = [f for f in folds if f.get("status") == "OK"]
    n_ok = len(ok)
    n_beat = sum(1 for f in ok if f["beat"] > 0)
    n_ece_pass = sum(1 for f in ok if f["ece_pass"])
    n_lift_pass = sum(
        1 for f in ok
        if (f.get("explosive") or {}).get("lift") is not None
        and f["explosive"]["lift"] >= SUCCESS_BAR_EXPLOSIVE_LIFT_MIN
    )
    # Monotonic decisive-hit check — applied per fold; phase-level reported
    # as "fraction of folds with strictly-monotone non-decreasing hit-rate".
    def _monotone(f):
        d = f.get("decisive_hit", {})
        accs = [
            d.get(f"{t:.2f}", {}).get("accuracy")
            for t in SUCCESS_BAR_CONFIDENCE_THRESHOLDS
        ]
        clean = [a for a in accs if a is not None]
        return len(clean) >= 2 and all(b >= a for a, b in zip(clean, clean[1:]))

    n_mono = sum(1 for f in ok if _monotone(f))

    gates = {
        "n_ok_folds": n_ok,
        "g1_logloss_beat_folds": n_beat,
        "g1_pass": n_beat >= SUCCESS_BAR_MIN_FOLDS_LOGLOSS,
        "g2_ece_pass_folds": n_ece_pass,
        "g2_pass": n_ece_pass >= SUCCESS_BAR_MIN_FOLDS_ECE,
        "g3_monotone_folds": n_mono,
        # Spec gate 3 is described as "rises monotonically" — interpret
        # as "monotonic in at least the majority of folds"; gating
        # threshold mirrors the same 6/8 strictness as the others.
        "g3_pass": n_mono >= SUCCESS_BAR_MIN_FOLDS_LOGLOSS,
        "g4_lift_pass_folds": n_lift_pass,
        "g4_pass": n_lift_pass >= SUCCESS_BAR_MIN_FOLDS_LIFT,
    }
    gates["cell_pass"] = (
        gates["g1_pass"] and gates["g2_pass"]
        and gates["g3_pass"] and gates["g4_pass"]
    )
    return gates


def walk_forward(engine, phase: str, ticker: str, tf: str,
                  cutoffs: list[str] | None = None,
                  calibration: str = DEFAULT_CALIBRATION,
                  cv: int = DEFAULT_CV) -> dict:
    cutoffs = cutoffs or list(DEFAULT_CUTOFFS)
    log.info("=" * 70)
    log.info("MAGNITUDE WALK-FORWARD  phase=%s  ticker=%s  tf=%s  cutoffs=%d",
             phase, ticker, tf, len(cutoffs))
    log.info("=" * 70)

    df = load_magnitude_dataset(engine, ticker, tf, phase)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date
    log.info("loaded: %d rows  (%s..%s)",
             len(df), df["bar_date"].min(), df["bar_date"].max())

    t0 = time.time()
    X_df, feature_cols = featurize(df)
    X_full = X_df.values.astype(np.float32, copy=False)
    y_full = df[LABEL_COL].map(LABEL_TO_IDX).values.astype(np.int64)
    bar_dates_arr = pd.DatetimeIndex(df["bar_date"]).values.astype("datetime64[D]")
    log.info("featurize-once: %d × %d in %.1fs", X_full.shape[0], X_full.shape[1], time.time() - t0)

    cores = max(1, os.cpu_count() or 1)
    lgbm_n_jobs = max(1, cores // cv) if calibration != "none" else -1

    folds: list[dict] = []
    for i, cut in enumerate(cutoffs):
        if i + 1 < len(cutoffs):
            test_end = cutoffs[i + 1]
        else:
            test_end = str(pd.Timestamp(df["bar_date"].max()) + pd.Timedelta(days=1))[:10]
        log.info("─" * 70)
        log.info("fold %d/%d  train<%s  test=[%s..%s)",
                 i + 1, len(cutoffs), cut, cut, test_end)
        try:
            fold_t0 = time.time()
            r = train_and_evaluate_fold(
                X_full, y_full, bar_dates_arr,
                cut, test_end, tf, lgbm_n_jobs,
                calibration=calibration, cv=cv,
            )
            r["fold_seconds"] = int(round(time.time() - fold_t0))
            folds.append(r)
            if r["status"] == "OK":
                exp = r["explosive"]
                log.info("  n_train=%d n_test=%d", r["n_train"], r["n_test"])
                log.info("  logloss=%.4f base=%.4f beat=%+.4f",
                         r["logloss"], r["base_logloss"], r["beat"])
                log.info("  acc=%.3f base=%.3f Δ=%+.1fpp",
                         r["accuracy"], r["base_accuracy"], r["accuracy_beat_pp"])
                log.info("  ECE=%.4f ceiling=%.3f %s",
                         r["ece"], r["ece_ceiling"], "PASS" if r["ece_pass"] else "FAIL")
                log.info("  EXPLOSIVE base=%.3f prec=%s lift=%s",
                         exp["base_rate"],
                         f"{exp['precision']:.3f}" if exp["precision"] is not None else "—",
                         f"{exp['lift']:.2f}" if exp["lift"] is not None else "—")
                d = r["decisive_hit"]
                log.info("  decisive: " + "  ".join(
                    f"{t}:n={d[t]['n']},acc={d[t]['accuracy']:.3f}" if d[t]['accuracy'] is not None else f"{t}:n=0"
                    for t in d
                ))
            else:
                log.info("  %s (n_test=%d < %d)", r["status"], r["n_test"], MIN_TEST_BARS)
        except Exception as e:
            log.exception("fold %s FAILED: %s", cut, e)
            folds.append({"fold": f"{cut}..{test_end}",
                          "train_end": cut, "test_end": test_end,
                          "status": "ERROR", "error": str(e)})

    gates = _evaluate_phase_gate(folds, tf)
    log.info("=" * 70)
    log.info("CELL VERDICT  phase=%s  ticker=%s  tf=%s  →  %s",
             phase, ticker, tf, "PASS" if gates["cell_pass"] else "FAIL")
    log.info("  g1 log-loss beat ≥ %d/8 folds: %d  →  %s",
             SUCCESS_BAR_MIN_FOLDS_LOGLOSS, gates["g1_logloss_beat_folds"],
             "PASS" if gates["g1_pass"] else "FAIL")
    log.info("  g2 ECE ≤ %.3f in ≥ %d/8 folds: %d  →  %s",
             ECE_CEILING_BY_TF[tf], SUCCESS_BAR_MIN_FOLDS_ECE,
             gates["g2_ece_pass_folds"], "PASS" if gates["g2_pass"] else "FAIL")
    log.info("  g3 monotone decisive-hit folds: %d  →  %s",
             gates["g3_monotone_folds"], "PASS" if gates["g3_pass"] else "FAIL")
    log.info("  g4 EXPLOSIVE lift ≥ %.1f in ≥ %d/8 folds: %d  →  %s",
             SUCCESS_BAR_EXPLOSIVE_LIFT_MIN, SUCCESS_BAR_MIN_FOLDS_LIFT,
             gates["g4_lift_pass_folds"], "PASS" if gates["g4_pass"] else "FAIL")
    log.info("=" * 70)

    summary = {
        "phase": phase, "ticker": ticker, "tf": tf,
        "cutoffs": cutoffs,
        "min_test_bars": MIN_TEST_BARS,
        "calibration": calibration, "cv": cv,
        "n_features": int(X_full.shape[1]),
        "feature_cols": feature_cols,
        "folds": folds,
        "gates": gates,
        "computed_at": pd.Timestamp.utcnow().isoformat(),
    }
    run_id = (os.environ.get("CLOUD_RUN_EXECUTION")
              or os.environ.get("MAG_RUN_ID")
              or f"run_{int(time.time())}")
    summary["run_id"] = run_id

    # DDL is idempotent (CREATE IF NOT EXISTS) but concurrent dispatches
    # of 27 parallel tasks can race on the initial creation. Split DDL +
    # persist try/except so a DDL race doesn't drop the per-fold rows.
    try:
        execute_sql(RESULTS_DDL_CREATE)
        execute_sql(RESULTS_DDL_INDEX)
    except Exception as e:
        # Race on CREATE/INDEX — fine, table will already exist by the
        # time we try to insert.
        log.info("DDL race or no-op (%s): %s", type(e).__name__, e)
    try:
        _persist_results_table(engine, phase, ticker, tf, folds, run_id)
    except Exception as e:
        # Hard failure — log loud, but DON'T fail the task because GCS
        # persistence is the canonical output anyway.
        log.error("Cloud SQL persist FAILED (%s): %s", type(e).__name__, e)

    # Always persist to GCS.
    prefix = gcs_run_prefix(phase, ticker, tf)
    blob = f"{prefix}/walk_forward_{run_id}.json"
    _gcs_upload(json.dumps(summary, indent=2, default=str).encode(), blob)
    log.info("saved gs://%s/%s",
             os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT), blob)
    return summary


def run_all_cells(engine, phase: str,
                   cutoffs: list[str] | None = None,
                   calibration: str = DEFAULT_CALIBRATION) -> dict:
    """Dispatch all 9 (ticker × tf) cells for one phase sequentially in-process."""
    all_summaries = []
    for ticker in TICKERS:
        for tf in TIMEFRAMES:
            try:
                s = walk_forward(engine, phase, ticker, tf,
                                 cutoffs=cutoffs, calibration=calibration)
                all_summaries.append(s)
            except Exception as e:
                log.exception("cell %s %s FAILED: %s", ticker, tf, e)
                all_summaries.append({
                    "phase": phase, "ticker": ticker, "tf": tf,
                    "status": "ERROR", "error": str(e),
                })

    # Phase-level verdict: passes if ≥ 2 of 3 tickers per TF passed
    pass_count_by_tf = {tf: 0 for tf in TIMEFRAMES}
    for s in all_summaries:
        if s.get("gates", {}).get("cell_pass"):
            pass_count_by_tf[s["tf"]] += 1
    phase_pass_tfs = [tf for tf, n in pass_count_by_tf.items() if n >= 2]
    phase_verdict = "PASS" if len(phase_pass_tfs) >= 2 else "FAIL"

    log.info("=" * 70)
    log.info("PHASE %s VERDICT: %s  (passing TFs: %s)", phase, phase_verdict,
             ", ".join(phase_pass_tfs) or "none")
    log.info("=" * 70)

    return {
        "phase": phase, "verdict": phase_verdict,
        "pass_count_by_tf": pass_count_by_tf,
        "pass_tfs": phase_pass_tfs,
        "cells": all_summaries,
    }


# ─────────────────────── Task plans for Cloud Run parallel dispatch ────────
# Each plan maps a task-index N to ONE (phase, ticker, tf) cell. Cloud Run
# Job is dispatched with --tasks=len(plan) --parallelism=len(plan) so all
# cells run on independent workers simultaneously. Wall-clock = slowest
# single cell (~30-60 min) instead of sum (~5-9 hours sequential).
TASK_PLANS: dict[str, list[tuple[str, str, str]]] = {
    # Phase 0 only (9 cells) — smallest dispatch; use when you want a
    # cheap, fast read on whether the baseline carries any signal.
    "phase0": [
        (phase, ticker, tf)
        for phase in ("phase0",)
        for ticker in TICKERS
        for tf in TIMEFRAMES
    ],
    # All three phases that don't need backfills (27 cells) — preferred
    # default. Same ~30-60 min wall-clock, ~3x compute cost, gives 3
    # phase verdicts in one shot. Phase 2 + 4 deferred until backfills.
    "no_backfill": [
        (phase, ticker, tf)
        for phase in ("phase0", "phase1", "phase3")
        for ticker in TICKERS
        for tf in TIMEFRAMES
    ],
    # Phase 1 only (9 cells)
    "phase1": [
        ("phase1", ticker, tf)
        for ticker in TICKERS
        for tf in TIMEFRAMES
    ],
    # Phase 3 only (9 cells)
    "phase3": [
        ("phase3", ticker, tf)
        for ticker in TICKERS
        for tf in TIMEFRAMES
    ],
    # Phase 2 only (9 cells) — REQUIRES market_data_indicators backfill
    "phase2": [
        ("phase2", ticker, tf)
        for ticker in TICKERS
        for tf in TIMEFRAMES
    ],
    # Phase 4 only (9 cells) — REQUIRES market_data_cross_asset backfill
    "phase4": [
        ("phase4", ticker, tf)
        for ticker in TICKERS
        for tf in TIMEFRAMES
    ],
}


def _resolve_task() -> tuple[str, str, str] | None:
    """Resolve (phase, ticker, tf) from CLOUD_RUN_TASK_INDEX + MAG_PLAN env.

    Returns None when not running in a task-parallel Cloud Run dispatch.
    """
    plan_name = os.environ.get("MAG_PLAN", "")
    idx_str = os.environ.get("CLOUD_RUN_TASK_INDEX", "")
    if not plan_name or idx_str == "":
        return None
    if plan_name not in TASK_PLANS:
        raise SystemExit(f"MAG_PLAN={plan_name!r} not in {list(TASK_PLANS)}")
    plan = TASK_PLANS[plan_name]
    idx = int(idx_str)
    if idx >= len(plan):
        log.info("task-index %d ≥ plan size %d — no-op exit", idx, len(plan))
        return None
    return plan[idx]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", default=None, choices=list(PHASES) + [None])
    p.add_argument("--ticker", default=None, choices=list(TICKERS) + [None])
    p.add_argument("--tf", default=None, choices=list(TIMEFRAMES) + [None])
    p.add_argument("--all-cells", action="store_true",
                   help="In-process loop over 9 cells of one phase (legacy; "
                        "prefer Cloud Run --tasks parallelism via MAG_PLAN env)")
    p.add_argument("--plan", default=None, choices=list(TASK_PLANS) + [None],
                   help="Local-debug equivalent of MAG_PLAN env. With "
                        "--task-index N, run plan[N] only.")
    p.add_argument("--task-index", type=int, default=None,
                   help="Local debug: pick cell N from --plan. In Cloud Run "
                        "this is auto-resolved from CLOUD_RUN_TASK_INDEX.")
    p.add_argument("--cutoffs", default=None,
                   help="Comma-separated YYYY-MM-DD (default: regime-spanning)")
    p.add_argument("--calibration", default=DEFAULT_CALIBRATION,
                   choices=["none", "isotonic", "sigmoid"])
    args = p.parse_args()
    cutoffs = args.cutoffs.split(",") if args.cutoffs else None
    engine = get_engine()

    # Resolution priority:
    #   1. Cloud Run task-parallel env (MAG_PLAN + CLOUD_RUN_TASK_INDEX)
    #   2. --plan + --task-index (local debug for parity check)
    #   3. --all-cells with --phase (in-process loop — legacy)
    #   4. --phase --ticker --tf (single cell)
    cell = _resolve_task()
    if cell:
        phase, ticker, tf = cell
        log.info("task-parallel dispatch: plan=%s idx=%s → %s/%s/%s",
                 os.environ.get("MAG_PLAN"), os.environ.get("CLOUD_RUN_TASK_INDEX"),
                 phase, ticker, tf)
        walk_forward(engine, phase, ticker, tf,
                      cutoffs=cutoffs, calibration=args.calibration)
        return

    if args.plan and args.task_index is not None:
        plan = TASK_PLANS[args.plan]
        if args.task_index >= len(plan):
            log.info("task-index %d ≥ plan size %d — no-op", args.task_index, len(plan))
            return
        phase, ticker, tf = plan[args.task_index]
        walk_forward(engine, phase, ticker, tf,
                      cutoffs=cutoffs, calibration=args.calibration)
        return

    if args.all_cells:
        if not args.phase:
            raise SystemExit("--all-cells needs --phase")
        run_all_cells(engine, args.phase, cutoffs=cutoffs, calibration=args.calibration)
        return

    if not args.phase or not args.ticker or not args.tf:
        raise SystemExit(
            "Specify (--phase --ticker --tf) for a single cell, OR "
            "(--plan --task-index) for a single cell of a plan, OR "
            "(--phase --all-cells) for in-process 9-cell loop, OR set "
            "MAG_PLAN + CLOUD_RUN_TASK_INDEX env vars for task-parallel dispatch."
        )
    walk_forward(engine, args.phase, args.ticker, args.tf,
                  cutoffs=cutoffs, calibration=args.calibration)


if __name__ == "__main__":
    main()
