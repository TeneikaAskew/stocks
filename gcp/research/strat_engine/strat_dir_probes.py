"""Strat Engine — DIRECTION label-reframe probes (Phase 1 of the
directionality research program).

Context
-------
The shipped DIRECTION model (target = next_close > next_open, single next
bar, unconditional) fails 0/72 walk-forward folds — see
`strat_dir_walk_forward.py` and `docs/DIRECTION_FEATURES_R&D.md`. The
literature scan (`docs/DIRECTION_LITERATURE_SCAN.md`) shows that is the
EXPECTED efficient-market result for single-bar sign on a liquid index ETF,
and that the only places a directional edge could plausibly live are
(1) a LONGER horizon, (2) a specific VOLATILITY / TIME-OF-DAY regime, and
(3) TRIGGER-conditioning. The organizing principle is therefore: change the
LABEL, not the feature set (feature families were already shown to fail 0/8).

This module runs those reuse-first probes through the EXACT production
harness the baseline used — same `load_labeled_dataset`, same `featurize`,
same 8 anchored expanding cutoffs, same LightGBM hyperparameters — so a
result here is directly comparable to the failed baseline. The ONLY
differences per experiment are the label definition and (for horizon labels)
an embargo purge that the single-bar baseline did not need.

Experiments
-----------
  e1_horizon : y = sign of SESSION-AWARE forward return over --horizon bars.
               Adds an embargo purge (drop train bars whose forward label
               window overlaps the test fold). Reports overall metrics AND a
               stratified read-out (time-of-day third, vix tercile, gamma
               regime) so a conditional pocket is visible even if the
               unconditional model is flat.
  e2_trigger : same horizon label, but RESTRICTED to bars where a Strat
               trigger fired (is_continuation OR is_reversal). Tests whether
               follow-through is predictable conditional on a setup — the
               "primary side" gate for any later meta-labeling.

Run (production path — research image, strat-engine Cloud Run Job):
  gcloud run jobs execute strat-engine --region us-east1 --wait \\
    --args="-m,gcp.research.strat_engine.strat_dir_probes,\\
            --experiment=e1_horizon,--ticker=IWM,--tf=15m,--horizon=15"

Hermetic local note: like the rest of the engine this needs Cloud SQL
(`get_engine()`), so it is NOT runnable from the web sandbox directly —
dispatch it via the strat-engine job (Rule 3.6: production replay path, no
throwaway harness).
"""
from __future__ import annotations
import argparse
import json
import logging
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# NOTE: lightgbm / scikit-learn / gcp.database and the strat_engine modules
# that pull them in are imported LAZILY inside the functions that need them,
# so the pure helpers below (session_aware_fwd_ret_bps, embargo_days_for,
# _session_third, _stratified_hit_rates) can be imported and unit-tested with
# only numpy + pandas installed (CLAUDE.md Rule 3.3 hermetic tests; same
# lazy-import discipline as strat_dataset.py).

log = logging.getLogger(__name__)

# Approximate RTH bars per day, used to convert a BAR horizon into a DAY
# embargo for the (day-granular) expanding cutoffs. Conservative (round up).
_BARS_PER_DAY = {"1m": 390, "5m": 78, "15m": 26, "30m": 13, "60m": 7,
                 "4h": 2, "1d": 1}


def session_aware_fwd_ret_bps(df: pd.DataFrame, horizon: int) -> pd.Series:
    """Forward return over `horizon` bars, SESSION-AWARE (never crosses the
    overnight gap). Matches the loader's intraday next-bar convention; the
    precomputed `fwd_ret_*bars_bps` columns use a plain cross-bar shift
    (`strat_data_builder.py:478`) that leaks overnight drift into the label.

    Returns bps; NaN for the last `horizon` bars of each session.
    """
    fwd_close = df.groupby("bar_date")["close"].shift(-horizon)
    return (fwd_close - df["close"]) / df["close"] * 10000.0


def embargo_days_for(tf: str, horizon: int) -> int:
    """Days to purge before each test fold so a forward label window cannot
    overlap the test set. ceil(horizon / bars_per_day) + 1 day of slack."""
    bpd = _BARS_PER_DAY.get(tf, 26)
    return int(math.ceil(horizon / max(1, bpd))) + 1


def _session_third(df: pd.DataFrame) -> pd.Series:
    """Bucket each bar into early / mid / late session by its position within
    the day (robust to TZ; matches Gao et al.'s first-vs-last framing)."""
    pos = df.groupby("bar_date").cumcount()
    cnt = df.groupby("bar_date")["close"].transform("size")
    frac = (pos + 0.5) / cnt
    return pd.cut(frac, [0, 1 / 3, 2 / 3, 1.0],
                 labels=["early", "mid", "late"], include_lowest=True)


def _stratified_hit_rates(y_true: np.ndarray, p_up: np.ndarray,
                          strata: dict[str, pd.Series]) -> dict:
    """For each stratum column, decisive-call (≥0.55) hit rate per level.
    A pocket with n≥200 and hit_rate>0.55 is what we are hunting for."""
    pred = (p_up >= 0.5).astype(int)
    decisive = np.maximum(p_up, 1 - p_up) >= 0.55
    out: dict[str, dict] = {}
    for name, col in strata.items():
        vals = col.values if hasattr(col, "values") else np.asarray(col)
        levels: dict[str, dict] = {}
        for lvl in pd.unique(vals[~pd.isna(vals)]):
            m = (vals == lvl) & decisive
            n = int(m.sum())
            levels[str(lvl)] = {
                "n": n,
                "hit_rate": float((pred[m] == y_true[m]).mean()) if n > 0 else None,
            }
        out[name] = levels
    return out


def evaluate_fold(X_full, y_full, bar_dates, strata_full,
                  train_end, test_end, embargo_days, lgbm_n_jobs) -> dict:
    from sklearn.metrics import log_loss
    from gcp.research.strat_engine.strat_pred_train import expected_calibration_error
    from gcp.research.strat_engine.strat_dir_walk_forward import (
        make_direction_lgbm, base_rate_logloss_binary,
    )
    from gcp.research.strat_engine.strat_walk_forward import MIN_TEST_BARS

    train_end_dt = np.datetime64(train_end)
    test_end_dt = np.datetime64(test_end)
    embargo_cut = train_end_dt - np.timedelta64(embargo_days, "D")

    train_mask = bar_dates < embargo_cut
    test_mask = (bar_dates >= train_end_dt) & (bar_dates < test_end_dt)
    n_train, n_test = int(train_mask.sum()), int(test_mask.sum())
    if n_test < MIN_TEST_BARS:
        return {"fold": f"{train_end}..{test_end}", "n_test": n_test,
                "n_train": n_train, "embargo_days": embargo_days,
                "status": "SKIP_THIN"}

    X_tr, X_te = X_full[train_mask], X_full[test_mask]
    y_tr, y_te = y_full[train_mask], y_full[test_mask]

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
    for t in (0.55, 0.60, 0.65):
        dec = np.maximum(p_up, 1 - p_up) >= t
        n_dec = int(dec.sum())
        thresh_rates[t] = {"n": n_dec,
                           "hit_rate": float((pred[dec] == y_te[dec]).mean())
                           if n_dec > 0 else None}

    strata_te = {k: v[test_mask] for k, v in strata_full.items()}
    return {
        "fold": f"{train_end}..{test_end}",
        "n_train": n_train, "n_test": n_test, "embargo_days": embargo_days,
        "logloss": ll, "base_logloss": base_ll, "beat": base_ll - ll,
        "accuracy": acc, "base_accuracy": base_acc,
        "accuracy_beat_pp": (acc - base_acc) * 100,
        "ece": float(ece), "thresh_rates": thresh_rates,
        "up_share_train": float(y_tr.mean()), "up_share_test": float(y_te.mean()),
        "stratified": _stratified_hit_rates(y_te, p_up, strata_te),
        "status": "OK",
    }


def run_probe(engine, ticker: str, tf: str, experiment: str,
              horizon: int, cutoffs=None) -> dict:
    from gcp.research.strat_engine.strat_config import (
        DEFAULT_ECE_CEILING, GCS_BUCKET_DEFAULT, gcs_model_prefix,
    )
    from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
    from gcp.research.strat_engine.strat_pred_train import featurize
    from gcp.research.strat_engine.strat_walk_forward import (
        DEFAULT_CUTOFFS, MIN_TEST_BARS, _gcs_upload,
    )

    cutoffs = cutoffs or DEFAULT_CUTOFFS
    emb = embargo_days_for(tf, horizon)
    log.info("=" * 72)
    log.info("DIR PROBE  exp=%s  %s %s  horizon=%dbars  embargo=%dd  folds=%d",
             experiment, ticker, tf, horizon, emb, len(cutoffs))
    log.info("=" * 72)

    df = load_labeled_dataset(engine, ticker, tf, include_next_bar_ohlc=False)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date
    df = df.sort_values(["bar_date", "ts"]).reset_index(drop=True)

    # Label: session-aware forward-return sign at the chosen horizon.
    fwd_bps = session_aware_fwd_ret_bps(df, horizon)
    df = df.assign(_fwd_bps=fwd_bps)

    if experiment == "e2_trigger":
        trig = df.get("is_continuation", pd.Series(False, index=df.index)).fillna(False) | \
               df.get("is_reversal", pd.Series(False, index=df.index)).fillna(False)
        n_before = len(df)
        df = df[trig].copy()
        log.info("e2_trigger: restricted to %d/%d bars where a trigger fired",
                 len(df), n_before)
    elif experiment != "e1_horizon":
        raise SystemExit(f"unknown --experiment={experiment} "
                         "(choices: e1_horizon, e2_trigger)")

    # Drop bars with no forward label (session tail) or flat move (ambiguous).
    valid = df["_fwd_bps"].notna() & (df["_fwd_bps"] != 0.0)
    n_drop = int((~valid).sum())
    df = df[valid].reset_index(drop=True)
    log.info("dropped %d bars (no fwd label or flat); %d labeled rows (%s..%s)",
             n_drop, len(df), df["bar_date"].min(), df["bar_date"].max())
    if len(df) < MIN_TEST_BARS * 2:
        raise SystemExit(f"too few labeled rows ({len(df)}) for {experiment}")

    t0 = time.time()
    # Compute the label BEFORE featurizing, then featurize on a frame WITHOUT
    # the label column. featurize()'s drop-list is by NAME, so it would happily
    # admit our `_fwd_bps` label as a feature — a look-ahead leak that produces
    # ~100% accuracy. Drop it explicitly.
    y_full = (df["_fwd_bps"] > 0).astype(np.int64).values
    X_df, feature_cols = featurize(df.drop(columns=["_fwd_bps"]))
    X_full = X_df.values.astype(np.float32, copy=False)

    # Leakage guard (Rule 0): no forward-looking column may enter the matrix.
    leak = [c for c in feature_cols
            if c.startswith(("fwd_", "next_", "_fwd"))
            or "fwd_ret" in c or "fwd_close" in c]
    if leak:
        raise SystemExit(f"LEAKAGE: forward-looking columns in feature matrix: {leak}")
    bar_dates = pd.DatetimeIndex(df["bar_date"]).values.astype("datetime64[D]")
    strata_full = {
        "session_third": _session_third(df).astype("object"),
        "vix_tercile": df.get("vix_tercile", pd.Series(index=df.index, dtype="object")).astype("object"),
        "gamma_regime": df.get("gamma_regime", pd.Series(index=df.index, dtype="object")).astype("object"),
    }
    log.info("featurize-once: %d rows × %d cols in %.1fs; global up-share=%.4f",
             X_full.shape[0], X_full.shape[1], time.time() - t0, float(y_full.mean()))

    lgbm_n_jobs = max(1, os.cpu_count() or 1)
    folds = []
    for i, cut in enumerate(cutoffs):
        test_end = cutoffs[i + 1] if i + 1 < len(cutoffs) else \
            str(pd.Timestamp(df["bar_date"].max()) + pd.Timedelta(days=1))[:10]
        log.info("─" * 72)
        log.info("fold %d/%d  train<%s (embargo %dd)  test=[%s..%s)",
                 i + 1, len(cutoffs), cut, emb, cut, test_end)
        try:
            ft0 = time.time()
            r = evaluate_fold(X_full, y_full, bar_dates, strata_full,
                              cut, test_end, emb, lgbm_n_jobs)
            r["fold_seconds"] = round(time.time() - ft0, 1)
            folds.append(r)
            if r["status"] == "OK":
                log.info("  n_tr=%d n_te=%d up(tr/te)=%.3f/%.3f",
                         r["n_train"], r["n_test"], r["up_share_train"], r["up_share_test"])
                log.info("  logloss=%.4f base=%.4f beat=%+.4f  acc=%.3f Δ=%+.1fpp  ECE=%.4f %s",
                         r["logloss"], r["base_logloss"], r["beat"], r["accuracy"],
                         r["accuracy_beat_pp"], r["ece"],
                         "PASS" if r["ece"] <= DEFAULT_ECE_CEILING else "FAIL")
                for t, d in r["thresh_rates"].items():
                    if d["n"] > 0:
                        log.info("  decisive ≥%.2f: n=%d hit=%.3f", t, d["n"], d["hit_rate"])
                # Surface any strong stratum pocket
                for sname, levels in r["stratified"].items():
                    for lvl, d in levels.items():
                        if d["n"] >= 200 and d["hit_rate"] is not None and d["hit_rate"] >= 0.55:
                            log.info("  POCKET %s=%s: n=%d hit=%.3f", sname, lvl, d["n"], d["hit_rate"])
            else:
                log.info("  %s (n_test=%d)", r["status"], r["n_test"])
        except Exception as e:
            log.exception("fold %s FAILED: %s", cut, e)
            folds.append({"fold": f"{cut}..{test_end}", "status": "ERROR", "error": str(e)})

    ok = [f for f in folds if f.get("status") == "OK"]
    log.info("=" * 72)
    log.info("SUMMARY  exp=%s %s %s horizon=%d", experiment, ticker, tf, horizon)
    if ok:
        beats = [f["beat"] for f in ok]
        accs = [f["accuracy_beat_pp"] for f in ok]
        eces = [f["ece"] for f in ok]
        log.info("  logloss beat: median %+.4f  positive %d/%d folds",
                 float(np.median(beats)), sum(1 for b in beats if b > 0), len(ok))
        log.info("  accuracy beat: median %+.1fpp  positive %d/%d folds",
                 float(np.median(accs)), sum(1 for a in accs if a > 0), len(ok))
        log.info("  ECE: median %.4f  passes %d/%d",
                 float(np.median(eces)), sum(1 for e in eces if e <= DEFAULT_ECE_CEILING), len(ok))

    summary = {
        "experiment": experiment, "ticker": ticker, "tf": tf,
        "horizon_bars": horizon, "embargo_days": emb,
        "target": f"sign(session-aware fwd_ret over {horizon} bars)",
        "cutoffs": cutoffs, "calibration": "none",
        "min_test_bars": MIN_TEST_BARS, "n_features": len(feature_cols),
        "folds": folds, "computed_at": pd.Timestamp.utcnow().isoformat(),
    }
    prefix = gcs_model_prefix(ticker, tf)
    blob = f"{prefix}/dir_probe_{experiment}_h{horizon}_{int(time.time())}.json"
    _gcs_upload(json.dumps(summary, indent=2, default=str).encode(), blob)
    log.info("saved: gs://%s/%s", os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT), blob)
    return summary


def main():
    from gcp.database import get_engine
    from gcp.research.strat_engine.strat_config import TICKERS, TIMEFRAMES
    from lib.logging_config import setup_logging
    setup_logging()

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--experiment", default="e1_horizon",
                   choices=["e1_horizon", "e2_trigger"])
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--horizon", type=int, default=15,
                   help="forward-return horizon in bars (session-aware)")
    p.add_argument("--cutoffs", default=None)
    args = p.parse_args()
    cutoffs = args.cutoffs.split(",") if args.cutoffs else None
    engine = get_engine()
    run_probe(engine, args.ticker, args.tf, args.experiment, args.horizon, cutoffs)


if __name__ == "__main__":
    main()
