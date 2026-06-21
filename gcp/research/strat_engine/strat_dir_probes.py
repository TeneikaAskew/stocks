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


def triple_barrier_labels(df: pd.DataFrame, horizon: int,
                          k_atr: float) -> pd.DataFrame:
    """Session-aware TRIPLE-BARRIER directional labels (López de Prado).

    For each bar t, scan forward j = 1..horizon WITHIN the same session and
    record the first bar whose HIGH touches the up-barrier
    (close[t] + k·atr20[t]) or whose LOW touches the down-barrier
    (close[t] − k·atr20[t]). The side that is touched FIRST wins; if neither
    is touched within the horizon the bar is a genuine *no-touch* (the
    vertical barrier) — this is the neutral band that filters microstructure
    noise a return-sign label is forced to label ±.

    Returns a frame aligned to ``df.index`` with:
      atr20      — t-known ATR-20 (reused from the magnitude engine; the
                   stored ``atr_20`` is NaN in source, hence local compute).
      y_long     — 1 iff the UP barrier is touched first within horizon.
      y_short    — 1 iff the DOWN barrier is touched first within horizon.
      touched    — y_long | y_short (at least one horizontal barrier hit).
      evaluable  — atr20 valid AND (touched OR the full forward window exists).

    ``y_long`` and ``y_short`` are deliberately NON-complementary: a no-touch
    bar is 0 for BOTH. That asymmetry is the whole point — it lets a separate
    long-vs-rest and short-vs-rest meta-model learn the different drivers of
    up moves (opening-range position) vs down moves (vol expansion), instead
    of a single symmetric sign model where P(short) ≡ 1 − P(long).

    A same-bar tie (one bar's range straddles both barriers, so first-touch
    order is unknowable from OHLC) is conservatively scored neutral (both 0).
    """
    # ATR-20 via continuous true-range rolling mean — byte-identical to
    # magnitude_engine.mag_dataset._compute_atr20 (the stored atr_20 is NaN in
    # source). Inlined, not imported, to keep this a pure numpy+pandas helper
    # the hermetic tests can exercise without pulling sqlalchemy/loaders.
    _h, _l, _c = df["high"], df["low"], df["close"]
    _prev_c = _c.shift(1)
    _tr = pd.concat([(_h - _l), (_h - _prev_c).abs(), (_l - _prev_c).abs()],
                    axis=1).max(axis=1, skipna=True)
    atr20 = _tr.rolling(20, min_periods=20).mean()
    close = df["close"].to_numpy(dtype=float)
    up_level = close + k_atr * atr20.to_numpy(dtype=float)
    dn_level = close - k_atr * atr20.to_numpy(dtype=float)
    g = df.groupby("bar_date")
    n = len(df)
    INF = horizon + 1
    first_up = np.full(n, INF, dtype=float)
    first_dn = np.full(n, INF, dtype=float)
    for j in range(1, horizon + 1):
        hi_j = g["high"].shift(-j).to_numpy(dtype=float)
        lo_j = g["low"].shift(-j).to_numpy(dtype=float)
        up_touch = (hi_j >= up_level) & (first_up == INF)
        dn_touch = (lo_j <= dn_level) & (first_dn == INF)
        first_up[up_touch] = j
        first_dn[dn_touch] = j
    long_out = (first_up < first_dn) & (first_up <= horizon)
    short_out = (first_dn < first_up) & (first_dn <= horizon)
    touched = long_out | short_out
    # bars after t within the session; full window exists iff >= horizon
    fwd_avail = g.cumcount(ascending=False).to_numpy()
    atr_ok = atr20.notna().to_numpy() & (atr20.to_numpy(dtype=float) > 0)
    evaluable = atr_ok & (touched | (fwd_avail >= horizon))
    return pd.DataFrame({
        "atr20": atr20.to_numpy(dtype=float),
        "y_long": long_out.astype(np.int64),
        "y_short": short_out.astype(np.int64),
        "touched": touched.astype(np.int64),
        "evaluable": evaluable,
    }, index=df.index)



def embargo_days_for(tf: str, horizon: int) -> int:
    """Days to purge before each test fold so a forward label window cannot
    overlap the test set. ceil(horizon / bars_per_day) + 1 day of slack."""
    bpd = _BARS_PER_DAY.get(tf, 26)
    return int(math.ceil(horizon / max(1, bpd))) + 1


def binary_ece(y_true: np.ndarray, p1: np.ndarray, n_bins: int = 10) -> float:
    """Expected calibration error for a BINARY positive-class probability.

    Bins bars by predicted P(positive) into n_bins equal-width [0,1] bins and
    sums |mean(p1) − mean(y)| weighted by bin population. This is the
    binary-specific ECE used for the long/short side heads — it measures
    whether the predicted long-probability VALUE matches the realized
    long-frequency, which is the quantity the flicker fails (ECE ≈ 0.10).

    Pure numpy — importable hermetically (no sklearn). Distinct from
    strat_pred_train.expected_calibration_error, which bins by the multiclass
    max-confidence and measures argmax-accuracy calibration; for a 2-column
    [1-p1, p1] stack that helper degenerates to confidence>=0.5 binning and
    cannot see miscalibration in the 0.5..0.65 region the fire thresholds use.
    """
    y_true = np.asarray(y_true, dtype=float)
    p1 = np.asarray(p1, dtype=float)
    n = len(p1)
    if n == 0:
        return float("nan")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    # digitize on the interior edges so the last bin is closed at 1.0
    idx = np.digitize(p1, edges[1:-1])
    ece = 0.0
    for b in range(n_bins):
        m = idx == b
        nb = int(m.sum())
        if nb == 0:
            continue
        ece += (nb / n) * abs(float(p1[m].mean()) - float(y_true[m].mean()))
    return float(ece)


def calibration_split(bar_dates: np.ndarray, train_mask: np.ndarray,
                      calib_frac: float = 0.2):
    """Carve a post-hoc-calibration validation slice from the TRAIN block ONLY,
    by DATE (never random) so the calibrator is fit on the most-recent train
    days and never peeks at the test/holdout fold.

    Returns (fit_mask, calib_mask): two boolean masks over the full row index
    that partition ``train_mask``. The newest ``calib_frac`` of distinct train
    DATES go to the calibration slice; the rest train the base model. Splitting
    by date (not row) prevents bars from the same day landing on both sides of
    the split — the within-day autocorrelation leak.

    If the train block has too few distinct dates to carve a slice, returns
    (train_mask, all-False) so the caller falls back to no-calibration rather
    than fitting a calibrator on a handful of bars.
    """
    if not (0.0 < calib_frac < 1.0):
        raise ValueError(f"calib_frac must be in (0,1), got {calib_frac}")
    tr_dates = np.unique(bar_dates[train_mask])
    if len(tr_dates) < 5:  # too few days to carve a meaningful calib slice
        return train_mask.copy(), np.zeros_like(train_mask)
    n_calib = max(1, int(math.ceil(len(tr_dates) * calib_frac)))
    cut_date = tr_dates[-n_calib]  # first date of the calibration slice
    calib_mask = train_mask & (bar_dates >= cut_date)
    fit_mask = train_mask & (bar_dates < cut_date)
    # Guard: both partitions must be non-empty, else fall back to no calibration.
    if int(fit_mask.sum()) == 0 or int(calib_mask.sum()) == 0:
        return train_mask.copy(), np.zeros_like(train_mask)
    return fit_mask, calib_mask


def _fit_calibrator(method: str, p_calib: np.ndarray, y_calib: np.ndarray):
    """Fit a 1-D post-hoc calibrator mapping raw P(positive) → calibrated
    P(positive). ``isotonic`` = monotone non-parametric (sklearn
    IsotonicRegression); ``platt`` = 1-feature LogisticRegression (sigmoid).

    Returns a callable ``apply(p_raw) -> p_cal``. Lazy sklearn import so the
    pure helpers above stay importable with numpy+pandas only (Rule 3.3).

    Fails loud (RuntimeError) on a degenerate single-class calibration slice
    rather than silently returning identity — a caller that can't calibrate
    must KNOW (Rule 3.7: no silent fallback / fabricated value).
    """
    y_calib = np.asarray(y_calib)
    if y_calib.min() == y_calib.max():
        raise RuntimeError(
            "calibration slice is single-class; cannot fit a calibrator")
    if method == "isotonic":
        from sklearn.isotonic import IsotonicRegression
        ir = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        ir.fit(np.asarray(p_calib, dtype=float), y_calib.astype(float))
        return lambda p: np.clip(ir.predict(np.asarray(p, dtype=float)), 0.0, 1.0)
    elif method == "platt":
        from sklearn.linear_model import LogisticRegression
        lr = LogisticRegression(C=1e6, solver="lbfgs")
        lr.fit(np.asarray(p_calib, dtype=float).reshape(-1, 1), y_calib)
        cls = list(lr.classes_)
        pos = cls.index(1) if 1 in cls else 1
        return lambda p: lr.predict_proba(
            np.asarray(p, dtype=float).reshape(-1, 1))[:, pos]
    else:
        raise ValueError(f"unknown calibration method {method!r} "
                         "(choices: isotonic, platt)")


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
              horizon: int, cutoffs=None, regime: str = "none") -> dict:
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
    log.info("DIR PROBE  exp=%s  %s %s  horizon=%dbars  embargo=%dd  regime=%s  folds=%d",
             experiment, ticker, tf, horizon, emb, regime, len(cutoffs))
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

    # E3: regime-restricted TRAINING+TEST. Faithfully tests the one directional
    # effect the literature supports — intraday momentum concentrated in specific
    # vol regimes / late session (Gao et al. 2018; Christoffersen-Diebold:
    # sign predictability rides volatility dynamics). Unlike the stratified
    # read-out (a global model sliced post-hoc), this trains a model dedicated
    # to the regime so regime-specific structure can actually be learned.
    if regime and regime != "none":
        if regime in ("vix_low", "vix_high", "vix_mid"):
            want = {"vix_low": "LOW", "vix_mid": "MID", "vix_high": "HIGH"}[regime]
            mask = df.get("vix_tercile", pd.Series(index=df.index, dtype="object")) == want
        elif regime in ("pos_gamma", "neg_gamma"):
            want = {"pos_gamma": "positive_gamma", "neg_gamma": "negative_gamma"}[regime]
            mask = df.get("gamma_regime", pd.Series(index=df.index, dtype="object")) == want
        elif regime in ("early_session", "mid_session", "late_session"):
            want = regime.split("_")[0]
            mask = _session_third(df).astype("object") == want
        else:
            raise SystemExit(f"unknown --regime={regime}")
        n_before = len(df)
        df = df[mask.values].reset_index(drop=True)
        log.info("regime=%s: restricted to %d/%d labeled rows", regime, len(df), n_before)

    if len(df) < MIN_TEST_BARS * 2:
        raise SystemExit(f"too few labeled rows ({len(df)}) for {experiment} regime={regime}")

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
        "horizon_bars": horizon, "embargo_days": emb, "regime": regime,
        "target": f"sign(session-aware fwd_ret over {horizon} bars)",
        "cutoffs": cutoffs, "calibration": "none",
        "min_test_bars": MIN_TEST_BARS, "n_features": len(feature_cols),
        "folds": folds, "computed_at": pd.Timestamp.utcnow().isoformat(),
    }
    prefix = gcs_model_prefix(ticker, tf)
    reg_tag = "" if regime == "none" else f"_{regime}"
    blob = f"{prefix}/dir_probe_{experiment}_h{horizon}{reg_tag}_{int(time.time())}.json"
    _gcs_upload(json.dumps(summary, indent=2, default=str).encode(), blob)
    log.info("saved: gs://%s/%s", os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT), blob)
    return summary


def _side_metrics(y_te, p1, base_ll):
    """Shared metric block for a side head: log-loss beat, binary ECE, and the
    decisive-fire precision ladder. ``p1`` is the (possibly calibrated)
    P(this-side-touches-first); ``base_ll`` is the train-prior null log-loss."""
    from sklearn.metrics import log_loss
    proba = np.column_stack([1 - p1, p1])
    ll = float(log_loss(y_te, proba, labels=[0, 1]))
    ece = binary_ece(y_te, p1, n_bins=10)
    fires = {}
    for t in (0.55, 0.60, 0.65):
        f = p1 >= t
        nf = int(f.sum())
        fires[t] = {"n": nf,
                    "precision": float(y_te[f].mean()) if nf > 0 else None}
    return {"base_rate": float(y_te.mean()), "logloss": ll,
            "base_logloss": base_ll, "beat": base_ll - ll,
            "ece": float(ece), "fires": fires}


def _side_fold(X_full, y, bar_dates, train_end, test_end, embargo_days,
               cond_tr, cond_te, evaluable, n_jobs, side, train_lower=None,
               calibrate: str = "none", holdout_mask=None) -> dict:
    """One walk-forward fold for ONE side's meta-model (long-vs-rest or
    short-vs-rest), conditioned on the magnitude model's predicted-EXPLOSIVE
    mask. cond_tr is the IN-SAMPLE mag prediction (selects the train subset);
    cond_te is the OOF mag prediction (mag model never saw the test fold).
    train_lower (optional) caps how far back training reaches (rolling window).

    calibrate ∈ {none, isotonic, platt}: when not "none", a post-hoc
    calibrator is fit on a date-carved validation slice of THIS fold's TRAIN
    block (never the test/holdout) and applied to the test probabilities
    before metrics. A fresh calibrator per fold — never reused across folds
    (the classic walk-forward harness leak; see strat_walk_forward.py).

    holdout_mask (optional): a boolean row mask of bars reserved as a LOCKED
    holdout. These bars are force-excluded from the train block here too (they
    are also excluded globally upstream, but this is a defensive second guard)
    so a fold's training set can never touch a holdout bar.
    """
    from gcp.research.strat_engine.strat_dir_walk_forward import (
        make_direction_lgbm, base_rate_logloss_binary,
    )
    from gcp.research.strat_engine.strat_walk_forward import MIN_TEST_BARS

    train_end_dt = np.datetime64(train_end)
    test_end_dt = np.datetime64(test_end)
    embargo_cut = train_end_dt - np.timedelta64(embargo_days, "D")
    tr = (bar_dates < embargo_cut) & cond_tr & evaluable
    if train_lower is not None:
        tr &= (bar_dates >= train_lower)
    if holdout_mask is not None:
        tr &= ~holdout_mask
    te = (bar_dates >= train_end_dt) & (bar_dates < test_end_dt) & cond_te & evaluable
    if holdout_mask is not None:
        te &= ~holdout_mask
    n_tr, n_te = int(tr.sum()), int(te.sum())
    out = {"side": side, "fold": f"{train_end}..{test_end}",
           "n_train": n_tr, "n_test": n_te, "calibrate": calibrate}
    if n_te < MIN_TEST_BARS or n_tr < MIN_TEST_BARS:
        out["status"] = "SKIP_THIN"
        return out
    y_tr, y_te = y[tr], y[te]
    if y_tr.min() == y_tr.max():  # single-class train subset — undefined model
        out["status"] = "SKIP_DEGEN"
        return out
    base_ll = base_rate_logloss_binary(y_tr, y_te)

    if calibrate == "none":
        model = make_direction_lgbm(n_jobs=n_jobs)
        model.fit(X_full[tr], y_tr)
        proba = model.predict_proba(X_full[te])
        p1 = proba[:, list(model.classes_).index(1)] \
            if 1 in model.classes_ else np.zeros(n_te)
        cal_status = "raw"
    else:
        # Carve the calibration slice from THIS fold's train block by date.
        fit_mask, calib_mask = calibration_split(bar_dates, tr, calib_frac=0.2)
        y_fit = y[fit_mask]
        if int(calib_mask.sum()) == 0 or y_fit.min() == y_fit.max():
            # Cannot calibrate honestly (thin / single-class slice). Fail loud
            # by recording the reason; the fold still reports RAW metrics so
            # the run isn't silently dropped, but the calibrate flag is marked
            # not-applied so the verdict can't be over-read (Rule 3.7).
            model = make_direction_lgbm(n_jobs=n_jobs)
            model.fit(X_full[tr], y_tr)
            proba = model.predict_proba(X_full[te])
            p1 = proba[:, list(model.classes_).index(1)] \
                if 1 in model.classes_ else np.zeros(n_te)
            cal_status = "RAW_calib_unavailable"
        else:
            model = make_direction_lgbm(n_jobs=n_jobs)
            model.fit(X_full[fit_mask], y_fit)
            cls = list(model.classes_)
            pos = cls.index(1) if 1 in cls else 1
            p_calib = model.predict_proba(X_full[calib_mask])[:, pos]
            p_te_raw = model.predict_proba(X_full[te])[:, pos]
            if len(p_calib) == 0:
                # Degenerate: predict_proba returned empty for the calib slice
                # even though calib_mask.sum() > 0 — can happen in newer
                # sklearn/LightGBM when the fitted model sees no split on this
                # subset.  Fail loud with a recorded reason (Rule 3.7).
                log.warning(
                    "fold=%s..%s calibrate=%s: predict_proba returned 0 "
                    "predictions for calib slice (calib_mask.sum=%d) — "
                    "degenerate; falling back to raw probabilities",
                    train_end, test_end, calibrate, int(calib_mask.sum()),
                )
                p1 = p_te_raw
                cal_status = "RAW_calib_empty_predictions"
            else:
                try:
                    apply = _fit_calibrator(calibrate, p_calib, y[calib_mask])
                    p1 = np.asarray(apply(p_te_raw), dtype=float)
                    cal_status = calibrate
                except RuntimeError as e:
                    # single-class calib slice slipped past the guard above
                    p1 = p_te_raw
                    cal_status = f"RAW_calib_failed:{e}"

    out["calib_status"] = cal_status
    return {**out, "status": "OK", **_side_metrics(y_te, p1, base_ll)}


def _side_holdout_eval(X_full, y, bar_dates, holdout_mask, last_train_end,
                       embargo_days, cond_full, evaluable, n_jobs, side,
                       calibrate: str, train_lower=None) -> dict:
    """ONE locked-holdout evaluation for a side head. Train on EVERYTHING dated
    before the holdout (minus the embargo gap), optionally calibrate on a
    date-carved slice of that train block, then evaluate ONCE on the locked
    holdout bars. The holdout never enters training or the calibration slice.

    ``cond_full`` is the magnitude conditioner mask computed with a model
    trained ONLY on the pre-holdout block (so the holdout's conditioning is
    OOF, same leak-discipline as the per-fold OOF conditioner)."""
    from gcp.research.strat_engine.strat_dir_walk_forward import (
        make_direction_lgbm, base_rate_logloss_binary,
    )
    from gcp.research.strat_engine.strat_walk_forward import MIN_TEST_BARS

    embargo_cut = np.datetime64(last_train_end) - np.timedelta64(embargo_days, "D")
    tr = (bar_dates < embargo_cut) & ~holdout_mask & cond_full & evaluable
    if train_lower is not None:
        tr &= (bar_dates >= train_lower)
    te = holdout_mask & cond_full & evaluable
    n_tr, n_te = int(tr.sum()), int(te.sum())
    out = {"side": side, "block": "LOCKED_HOLDOUT", "n_train": n_tr,
           "n_test": n_te, "calibrate": calibrate}
    if n_te < MIN_TEST_BARS or n_tr < MIN_TEST_BARS:
        out["status"] = "SKIP_THIN"
        return out
    y_tr, y_te = y[tr], y[te]
    if y_tr.min() == y_tr.max():
        out["status"] = "SKIP_DEGEN"
        return out
    base_ll = base_rate_logloss_binary(y_tr, y_te)
    if calibrate == "none":
        model = make_direction_lgbm(n_jobs=n_jobs)
        model.fit(X_full[tr], y_tr)
        cls = list(model.classes_)
        pos = cls.index(1) if 1 in cls else 1
        p1 = model.predict_proba(X_full[te])[:, pos]
        out["calib_status"] = "raw"
    else:
        fit_mask, calib_mask = calibration_split(bar_dates, tr, calib_frac=0.2)
        y_fit = y[fit_mask]
        if int(calib_mask.sum()) == 0 or y_fit.min() == y_fit.max():
            out["status"] = "SKIP_CALIB_UNAVAILABLE"
            return out
        model = make_direction_lgbm(n_jobs=n_jobs)
        model.fit(X_full[fit_mask], y_fit)
        cls = list(model.classes_)
        pos = cls.index(1) if 1 in cls else 1
        p_calib = model.predict_proba(X_full[calib_mask])[:, pos]
        p_te_raw = model.predict_proba(X_full[te])[:, pos]
        if len(p_calib) == 0:
            # Degenerate: predict_proba returned empty for the calib slice even
            # though calib_mask.sum() > 0 (newer sklearn/LightGBM, no split on
            # this subset). Fail loud with a recorded reason; still report the
            # raw locked-holdout verdict rather than aborting the probe so the
            # settle-test always writes an outcome (Rule 3.7). Mirrors _side_fold.
            log.warning(
                "holdout calibrate=%s: predict_proba returned 0 predictions "
                "for calib slice (calib_mask.sum=%d) — degenerate; falling "
                "back to raw probabilities", calibrate, int(calib_mask.sum()),
            )
            p1 = p_te_raw
            out["calib_status"] = "RAW_calib_empty_predictions"
        else:
            try:
                apply = _fit_calibrator(calibrate, p_calib, y[calib_mask])
                p1 = np.asarray(apply(p_te_raw), dtype=float)
                out["calib_status"] = calibrate
            except RuntimeError as e:
                # Single-class calib slice (e.g. after the magnitude conditioner
                # in a thin window) slipped past the fit-side guard above — report
                # the raw holdout verdict instead of aborting the whole probe.
                p1 = p_te_raw
                out["calib_status"] = f"RAW_calib_failed:{e}"
    return {**out, "status": "OK", **_side_metrics(y_te, p1, base_ll)}


def _symmetric_fold(X_full, y3, bar_dates, train_end, test_end, embargo_days,
                    cond_tr, cond_te, evaluable, n_jobs, train_lower=None,
                    holdout_mask=None) -> dict:
    """One walk-forward fold for the SYMMETRIC 3-class first-touch primary
    model (0=down, 1=neutral, 2=up). This is the canonical López-de-Prado
    triple-barrier target: predict which barrier is touched first, with an
    explicit neutral class for timeouts. Metrics: 3-class log-loss vs the
    train-prior constant predictor (strong-form null), and the tradeable
    DIRECTIONAL precision — of bars the model decisively calls up/down (not
    neutral), how often that side's barrier really comes first.

    holdout_mask (optional): locked-holdout bars force-excluded from train+test."""
    import lightgbm as lgb
    from sklearn.metrics import log_loss
    from gcp.research.strat_engine.strat_walk_forward import MIN_TEST_BARS

    train_end_dt = np.datetime64(train_end)
    test_end_dt = np.datetime64(test_end)
    embargo_cut = train_end_dt - np.timedelta64(embargo_days, "D")
    tr = (bar_dates < embargo_cut) & cond_tr & evaluable
    if train_lower is not None:
        tr &= (bar_dates >= train_lower)
    if holdout_mask is not None:
        tr &= ~holdout_mask
    te = (bar_dates >= train_end_dt) & (bar_dates < test_end_dt) & cond_te & evaluable
    if holdout_mask is not None:
        te &= ~holdout_mask
    n_tr, n_te = int(tr.sum()), int(te.sum())
    out = {"side": "symmetric", "fold": f"{train_end}..{test_end}",
           "n_train": n_tr, "n_test": n_te}
    if n_te < MIN_TEST_BARS or n_tr < MIN_TEST_BARS:
        out["status"] = "SKIP_THIN"
        return out
    y_tr, y_te = y3[tr], y3[te]
    if len(np.unique(y_tr)) < 3:  # need all of down/neutral/up to train a 3-class
        out["status"] = "SKIP_DEGEN"
        return out
    model = lgb.LGBMClassifier(
        objective="multiclass", num_class=3, n_estimators=300,
        learning_rate=0.05, max_depth=6, num_leaves=31, min_child_samples=100,
        random_state=42, verbose=-1, n_jobs=n_jobs)
    model.fit(X_full[tr], y_tr)
    classes = list(model.classes_)
    proba = model.predict_proba(X_full[te])
    ll = float(log_loss(y_te, proba, labels=classes))
    # Strong-form null: constant predictor = train class priors.
    prior = np.array([(y_tr == c).mean() for c in classes])
    base_ll = float(log_loss(y_te, np.tile(prior, (n_te, 1)), labels=classes))
    pred = np.array(classes)[proba.argmax(1)]
    pmax = proba.max(1)
    down_i, up_i = classes.index(0) if 0 in classes else None, \
        classes.index(2) if 2 in classes else None
    dirn = {}
    for t in (0.50, 0.55, 0.60):
        # decisive directional call = argmax is up or down (not neutral) ≥ t
        fire = (pred != 1) & (pmax >= t)
        nf = int(fire.sum())
        dirn[t] = {"n": nf,
                   "precision": float((pred[fire] == y_te[fire]).mean())
                   if nf > 0 else None}
    return {**out, "status": "OK", "logloss": ll, "base_logloss": base_ll,
            "beat": base_ll - ll,
            "class_share_test": {int(c): float((y_te == c).mean()) for c in classes},
            "directional": dirn}


def run_triple_barrier_probe(engine, ticker: str, tf: str, horizon: int,
                             k_atr: float, mag_cond: str, mag_thresh: float,
                             cutoffs=None, feature_blocks: str = "",
                             window: str = "expanding",
                             rolling_years: int = 3,
                             holdout: str | None = None,
                             calibrate: str = "none") -> dict:
    """E4 — the closing experiment. Triple-barrier first-touch directional
    labels (neutral band) + SEPARATE long/short meta-models, conditioned on
    the magnitude engine's PREDICTED-EXPLOSIVE flag (leak-free: in-sample for
    train selection, OOF for the test fold). Addresses the three spec levers
    the return-sign probes (E1–E3) only approximated: barrier target, neutral
    band, magnitude-conditioning, and asymmetric model form.

    holdout (optional, YYYY-MM-DD): every bar dated >= this date is a LOCKED
    block excluded from EVERY walk-forward training fold AND every test fold.
    After the walk-forward, the long/short heads are trained once on all
    pre-holdout data and evaluated ONCE on the locked block — the true
    out-of-sample test the flicker needs (DIRECTION_RESEARCH_RESULTS §"What
    would change this verdict" #4).

    calibrate ∈ {none, isotonic, platt}: post-hoc calibration fit on a
    date-carved slice of TRAIN only (never test/holdout). E-20 found sigmoid
    HURT the sibling TYPE model; isotonic on this long head is UNTRIED — this
    flag exists to TEST it, not to assume it helps."""
    from gcp.research.strat_engine.strat_config import (
        DEFAULT_ECE_CEILING, GCS_BUCKET_DEFAULT, gcs_model_prefix,
    )
    from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
    from gcp.research.strat_engine.strat_pred_train import featurize
    from gcp.research.strat_engine.strat_walk_forward import (
        DEFAULT_CUTOFFS, MIN_TEST_BARS, _gcs_upload,
    )
    from gcp.research.magnitude_engine.mag_pred_train import make_lgbm
    from gcp.research.magnitude_engine.mag_config import LABEL_CLASSES, LABEL_TO_IDX
    from gcp.research.magnitude_engine.mag_dataset import _bucket_magnitude

    cutoffs = cutoffs or DEFAULT_CUTOFFS
    emb = embargo_days_for(tf, horizon)
    expl_idx = LABEL_TO_IDX["EXPLOSIVE"]
    exp_idx = LABEL_TO_IDX["EXPANDED"]
    log.info("=" * 72)
    log.info("DIR PROBE  exp=e4_triple_barrier  %s %s  horizon=%dbars  "
             "k_atr=%.2f  mag_cond=%s(thresh=%.2f)  embargo=%dd",
             ticker, tf, horizon, k_atr, mag_cond, mag_thresh, emb)
    log.info("=" * 72)

    # next_open/next_close needed for the magnitude target → load them, then
    # drop before featurize (the leak guard also blocks next_* by name).
    df = load_labeled_dataset(engine, ticker, tf, include_next_bar_ohlc=True)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date
    df = df.sort_values(["bar_date", "ts"]).reset_index(drop=True)

    # NEW-INFORMATION-CLASS feature blocks (the "rethink"). Injected BEFORE
    # featurize so featurize() auto-selects the new numeric columns; all are
    # d-1 leak-safe (flow) or session-aware stationary (fracdiff) and carry no
    # fwd_/next_ name, so the leak guard passes.
    blocks = [b.strip() for b in feature_blocks.split(",") if b.strip()]
    if "flow" in blocks:
        from lib.features.flow_direction import add_flow_features
        df = add_flow_features(df, ticker, engine)
        log.info("feature-block flow: added dealer-positioning columns")
    if "fracdiff" in blocks:
        from lib.features.fracdiff import add_fracdiff_features
        # fixed d=0.4 (memory-preserving, ~stationary) — avoids the ADF/
        # statsmodels search in the hot path; session-aware via bar_date.
        df = add_fracdiff_features(df, ["close"], d=0.4, prefix="fd_")
        log.info("feature-block fracdiff: added fd_close (d=0.4)")
    if "intraflow" in blocks:
        from lib.features.intraday_flow import add_intraflow_features
        # Intraday order-flow imbalance from the 1-min bars within each 15m bar.
        # CONTEMPORANEOUS (no shift): current bar's OFI is realized at its close,
        # same alignment as the baseline RSI/etc.; predicts the NEXT bar.
        df = add_intraflow_features(df, ticker, engine)
        log.info("feature-block intraflow: added intraday OFI columns")
    if "intragex" in blocks:
        from lib.features.intraday_gex import add_intragex_features
        # Reconstructed intraday dealer GEX/DEX: the T-1 EOD chain walked forward
        # to each bar's spot (delta-gamma re-curve). CONTEMPORANEOUS (no shift) —
        # uses the current bar's spot against the frozen prior-day chain.
        df = add_intragex_features(df, ticker, engine)
        log.info("feature-block intragex: added reconstructed GEX/DEX columns")
    if "realgex" in blocks:
        from lib.features.intraday_gex import add_realgex_features
        # REAL intraday dealer GEX/DEX from the av-options-realtime feed (actual
        # intraday greeks, not the EOD re-curve). Only covers dates since the feed
        # went live (2026-05-23) — for the recent-window real-intraday test once
        # enough history accrues. CONTEMPORANEOUS (no shift).
        df = add_realgex_features(df, ticker, engine)
        log.info("feature-block realgex: added REAL intraday GEX/DEX columns")

    tb = triple_barrier_labels(df, horizon, k_atr)
    # Magnitude target (forward |next_close-next_open|/atr20 bucket) — used
    # ONLY as the magnitude model's TRAINING label, never as a feature.
    move = (df["next_close"] - df["next_open"]).abs()
    mag_bucket = _bucket_magnitude(move, tb["atr20"])
    mag_y = mag_bucket.map(lambda b: LABEL_TO_IDX.get(b) if pd.notna(b) else np.nan)
    mag_ok = mag_y.notna().to_numpy()
    mag_y_int = np.where(mag_ok, mag_y.fillna(0).to_numpy(), 0).astype(np.int64)

    evaluable = tb["evaluable"].to_numpy()
    log.info("triple-barrier: %d evaluable bars  touched=%.3f  "
             "long=%.3f short=%.3f notouch=%.3f (of evaluable)",
             int(evaluable.sum()), float(tb["touched"][evaluable].mean()),
             float(tb["y_long"][evaluable].mean()),
             float(tb["y_short"][evaluable].mean()),
             float((tb["touched"][evaluable] == 0).mean()))

    drop_cols = [c for c in ("y_long", "y_short", "atr20", "next_open",
                 "next_close", "next_high", "next_low") if c in df.columns]
    X_df, feature_cols = featurize(df.drop(columns=drop_cols, errors="ignore"))
    X_full = X_df.values.astype(np.float32, copy=False)
    leak = [c for c in feature_cols
            if c.startswith(("fwd_", "next_", "_fwd")) or "fwd_ret" in c]
    if leak:
        raise SystemExit(f"LEAKAGE: forward-looking cols in matrix: {leak}")
    bar_dates = pd.DatetimeIndex(df["bar_date"]).values.astype("datetime64[D]")
    y_long = tb["y_long"].to_numpy()
    y_short = tb["y_short"].to_numpy()
    # Symmetric 3-class first-touch label: 2=up, 0=down, 1=neutral (timeout).
    y3 = np.where(y_long == 1, 2, np.where(y_short == 1, 0, 1)).astype(np.int64)
    n_jobs = max(1, os.cpu_count() or 1)

    # LOCKED HOLDOUT: bars dated >= `holdout` are reserved. They are excluded
    # from every fold (train AND test) below and evaluated exactly once at the
    # end. all-False when no holdout requested.
    if holdout:
        holdout_dt = np.datetime64(holdout)
        holdout_mask = bar_dates >= holdout_dt
        if int(holdout_mask.sum()) == 0:
            raise SystemExit(
                f"--holdout {holdout} reserves 0 bars (max bar_date="
                f"{df['bar_date'].max()}); pick an earlier holdout date")
        log.info("LOCKED HOLDOUT >= %s: %d bars reserved (%.1f%% of %d); "
                 "excluded from EVERY training fold",
                 holdout, int(holdout_mask.sum()),
                 100.0 * holdout_mask.mean(), len(bar_dates))
        # Cap the walk-forward cutoffs so no fold tests into the holdout.
        cutoffs = [c for c in cutoffs if np.datetime64(c) <= holdout_dt]
    else:
        holdout_mask = np.zeros(len(bar_dates), dtype=bool)

    if calibrate not in ("none", "isotonic", "platt"):
        raise SystemExit(f"--calibrate must be none|isotonic|platt, got {calibrate!r}")
    log.info("calibrate=%s  holdout=%s", calibrate, holdout or "none")

    folds = {"symmetric": [], "long": [], "short": []}
    for i, cut in enumerate(cutoffs):
        test_end = cutoffs[i + 1] if i + 1 < len(cutoffs) else \
            str(pd.Timestamp(df["bar_date"].max()) + pd.Timedelta(days=1))[:10]
        cut_dt = np.datetime64(cut)
        emb_cut = cut_dt - np.timedelta64(emb, "D")
        # Rolling window (C6): cap training to the last `rolling_years` before
        # the cutoff, so a stale 2019 regime can't dilute a 2025 prediction.
        train_lower = (cut_dt - np.timedelta64(int(rolling_years * 365), "D")
                       if window == "rolling" else None)
        tr_all = (bar_dates < emb_cut) & mag_ok & ~holdout_mask
        if train_lower is not None:
            tr_all &= (bar_dates >= train_lower)
        te_all = ((bar_dates >= cut_dt) & (bar_dates < np.datetime64(test_end))
                  & mag_ok & ~holdout_mask)
        if int(tr_all.sum()) < MIN_TEST_BARS or int(te_all.sum()) < MIN_TEST_BARS:
            continue
        # Magnitude model: train on fold-train, predict EXPLOSIVE prob.
        mag = make_lgbm(n_jobs=n_jobs)
        mag.fit(X_full[tr_all], mag_y_int[tr_all])
        cols = list(mag.classes_)
        def _p(idx, mask):
            return mag.predict_proba(X_full[mask])[:, cols.index(idx)] \
                if idx in cols else np.zeros(int(mask.sum()))
        # Build full-length conditioner masks (default False off-fold).
        def _cond(mask):
            p_expl = _p(expl_idx, mask)
            if mag_cond == "none":
                sel = np.ones(int(mask.sum()), dtype=bool)
            elif mag_cond == "big":
                p_exp = _p(exp_idx, mask)
                sel = (p_expl + p_exp) >= max(mag_thresh, 0.5)
            elif mag_cond == "topq":
                # Fold-relative: keep the top `mag_thresh` fraction of bars by
                # predicted P(EXPLOSIVE) — the faithful "where a big move is
                # MOST likely" conditioner that stays large enough to evaluate.
                frac = mag_thresh if 0 < mag_thresh < 1 else 0.2
                if len(p_expl) == 0:
                    sel = p_expl.astype(bool)
                else:
                    sel = p_expl >= float(np.quantile(p_expl, 1 - frac))
            else:  # "explosive"
                sel = p_expl >= mag_thresh if mag_thresh > 0 else \
                    (mag.predict(X_full[mask]) == expl_idx)
            full = np.zeros(len(bar_dates), dtype=bool)
            full[np.where(mask)[0]] = sel
            return full
        cond_tr = _cond(tr_all)
        cond_te = _cond(te_all)
        log.info("─" * 72)
        log.info("fold %d/%d test=[%s..%s)  predicted-EXPLOSIVE: train=%d test=%d",
                 i + 1, len(cutoffs), cut, test_end,
                 int(cond_tr.sum()), int(cond_te.sum()))
        rs = _symmetric_fold(X_full, y3, bar_dates, cut, test_end, emb,
                             cond_tr, cond_te, evaluable, n_jobs, train_lower,
                             holdout_mask=holdout_mask)
        folds["symmetric"].append(rs)
        if rs["status"] == "OK":
            d55 = rs["directional"][0.55]
            log.info("  sym   n_tr=%d n_te=%d beat=%+.4f  shares=%s  "
                     "dir≥.55 n=%d prec=%s", rs["n_train"], rs["n_test"],
                     rs["beat"], {k: round(v, 2) for k, v in rs["class_share_test"].items()},
                     d55["n"], f"{d55['precision']:.3f}" if d55["precision"] is not None else "—")
        else:
            log.info("  sym   %s (n_te=%d)", rs["status"], rs["n_test"])
        for side, y in (("long", y_long), ("short", y_short)):
            r = _side_fold(X_full, y, bar_dates, cut, test_end, emb,
                           cond_tr, cond_te, evaluable, n_jobs, side, train_lower,
                           calibrate=calibrate, holdout_mask=holdout_mask)
            folds[side].append(r)
            if r["status"] == "OK":
                f60 = r["fires"][0.60]
                log.info("  %-5s n_tr=%d n_te=%d base=%.3f beat=%+.4f ECE=%.4f "
                         "fire≥.60 n=%d prec=%s", side, r["n_train"], r["n_test"],
                         r["base_rate"], r["beat"], r["ece"], f60["n"],
                         f"{f60['precision']:.3f}" if f60["precision"] is not None else "—")
            else:
                log.info("  %-5s %s (n_te=%d)", side, r["status"], r["n_test"])

    # ── LOCKED-HOLDOUT EVALUATION (once) ────────────────────────────────────
    # Train the long/short heads on ALL pre-holdout data, optionally calibrate
    # on a date-carved slice of that train block, evaluate ONCE on the locked
    # block. The conditioner is computed from a magnitude model trained ONLY on
    # pre-holdout data (OOF for the holdout), same leak-discipline as the folds.
    holdout_eval = {}
    if holdout:
        holdout_dt = np.datetime64(holdout)
        emb_cut_h = holdout_dt - np.timedelta64(emb, "D")
        train_lower_h = (holdout_dt - np.timedelta64(int(rolling_years * 365), "D")
                         if window == "rolling" else None)
        tr_pre = (bar_dates < emb_cut_h) & mag_ok & ~holdout_mask
        if train_lower_h is not None:
            tr_pre &= (bar_dates >= train_lower_h)
        ho_eval_mask = holdout_mask & mag_ok
        log.info("=" * 72)
        log.info("LOCKED-HOLDOUT EVAL  train(pre-holdout)=%d  holdout=%d  "
                 "calibrate=%s", int(tr_pre.sum()), int(ho_eval_mask.sum()),
                 calibrate)
        if int(tr_pre.sum()) < MIN_TEST_BARS or int(ho_eval_mask.sum()) < MIN_TEST_BARS:
            log.warning("holdout eval skipped — thin (tr=%d ho=%d)",
                        int(tr_pre.sum()), int(ho_eval_mask.sum()))
            holdout_eval = {"status": "SKIP_THIN", "n_train": int(tr_pre.sum()),
                            "n_holdout": int(ho_eval_mask.sum())}
        else:
            mag_h = make_lgbm(n_jobs=n_jobs)
            mag_h.fit(X_full[tr_pre], mag_y_int[tr_pre])
            cols_h = list(mag_h.classes_)

            def _ph(idx, mask):
                return mag_h.predict_proba(X_full[mask])[:, cols_h.index(idx)] \
                    if idx in cols_h else np.zeros(int(mask.sum()))

            def _cond_h(mask):
                p_expl = _ph(expl_idx, mask)
                if mag_cond == "none":
                    sel = np.ones(int(mask.sum()), dtype=bool)
                elif mag_cond == "big":
                    p_exp = _ph(exp_idx, mask)
                    sel = (p_expl + p_exp) >= max(mag_thresh, 0.5)
                elif mag_cond == "topq":
                    frac = mag_thresh if 0 < mag_thresh < 1 else 0.2
                    sel = (p_expl >= float(np.quantile(p_expl, 1 - frac))
                           if len(p_expl) else p_expl.astype(bool))
                else:
                    sel = p_expl >= mag_thresh if mag_thresh > 0 else \
                        (mag_h.predict(X_full[mask]) == expl_idx)
                full = np.zeros(len(bar_dates), dtype=bool)
                full[np.where(mask)[0]] = sel
                return full

            # Conditioner over the union of pre-holdout-train and holdout bars,
            # so _side_holdout_eval can re-slice train vs holdout from one mask.
            cond_full = _cond_h(tr_pre) | _cond_h(ho_eval_mask)
            for side, y in (("long", y_long), ("short", y_short)):
                hr = _side_holdout_eval(
                    X_full, y, bar_dates, holdout_mask, holdout,
                    emb, cond_full, evaluable, n_jobs, side, calibrate,
                    train_lower_h)
                holdout_eval[side] = hr
                if hr["status"] == "OK":
                    f60 = hr["fires"][0.60]
                    log.info("  HOLDOUT %-5s n_tr=%d n_ho=%d base=%.3f beat=%+.4f "
                             "ECE=%.4f(%s) fire≥.60 n=%d prec=%s lift=%s",
                             side, hr["n_train"], hr["n_test"], hr["base_rate"],
                             hr["beat"], hr["ece"], hr.get("calib_status", "?"),
                             f60["n"],
                             f"{f60['precision']:.3f}" if f60["precision"] is not None else "—",
                             f"{f60['precision'] - hr['base_rate']:+.3f}"
                             if f60["precision"] is not None else "—")
                else:
                    log.info("  HOLDOUT %-5s %s (n_ho=%d)", side, hr["status"],
                             hr.get("n_test", 0))

    summary = {"experiment": "e4_triple_barrier", "ticker": ticker, "tf": tf,
               "horizon_bars": horizon, "k_atr": k_atr, "mag_cond": mag_cond,
               "mag_thresh": mag_thresh, "embargo_days": emb,
               "feature_blocks": blocks, "window": window,
               "rolling_years": rolling_years if window == "rolling" else None,
               "holdout": holdout, "calibrate": calibrate,
               "holdout_eval": holdout_eval,
               "target": f"first-touch sign of ±{k_atr}·ATR20 within {horizon} bars",
               "n_features": len(feature_cols), "folds": folds,
               "computed_at": pd.Timestamp.utcnow().isoformat()}
    sym_ok = [f for f in folds["symmetric"] if f.get("status") == "OK"]
    log.info("=" * 72)
    if sym_ok:
        sbeats = [f["beat"] for f in sym_ok]
        sprecs = [f["directional"][0.55]["precision"] for f in sym_ok
                  if f["directional"][0.55]["precision"] is not None]
        # directional base = P(correct side | a barrier touched) for a coin
        # flip among non-neutral truth = share(up)+share(down) split → compare
        # decisive precision against 0.5 (up-vs-down is the binary it resolves).
        log.info("SUMMARY symmetric(3-class): logloss beat median %+.4f  "
                 "positive %d/%d folds", float(np.median(sbeats)),
                 sum(b > 0 for b in sbeats), len(sym_ok))
        if sprecs:
            log.info("         directional≥.55 precision median %.3f "
                     "(coin=0.500, lift %+.3f)", float(np.median(sprecs)),
                     float(np.median(sprecs)) - 0.5)
    for side in ("long", "short"):
        ok = [f for f in folds[side] if f.get("status") == "OK"]
        log.info("=" * 72)
        if ok:
            beats = [f["beat"] for f in ok]
            eces = [f["ece"] for f in ok]
            precs = [f["fires"][0.60]["precision"] for f in ok
                     if f["fires"][0.60]["precision"] is not None]
            bases = [f["base_rate"] for f in ok]
            log.info("SUMMARY %s: logloss beat median %+.4f  positive %d/%d  "
                     "ECE median %.4f passes %d/%d", side,
                     float(np.median(beats)), sum(b > 0 for b in beats), len(ok),
                     float(np.median(eces)),
                     sum(e <= DEFAULT_ECE_CEILING for e in eces), len(ok))
            if precs:
                log.info("         fire≥.60 precision median %.3f vs base median "
                         "%.3f  (lift %+.3f)", float(np.median(precs)),
                         float(np.median(bases)),
                         float(np.median(precs)) - float(np.median(bases)))

    # Locked-holdout verdict line — the decisive read for the flicker.
    if holdout and isinstance(holdout_eval, dict) and "long" in holdout_eval:
        log.info("=" * 72)
        log.info("LOCKED-HOLDOUT VERDICT (>= %s, calibrate=%s)", holdout, calibrate)
        for side in ("long", "short"):
            hr = holdout_eval.get(side, {})
            if hr.get("status") == "OK":
                f60 = hr["fires"][0.60]
                lift = (f60["precision"] - hr["base_rate"]
                        if f60["precision"] is not None else None)
                log.info("  %-5s beat=%+.4f  ECE=%.4f (ceiling %.3f → %s)  "
                         "fire≥.60 n=%d prec=%s base=%.3f lift=%s", side,
                         hr["beat"], hr["ece"], DEFAULT_ECE_CEILING,
                         "PASS" if hr["ece"] <= DEFAULT_ECE_CEILING else "FAIL",
                         f60["n"],
                         f"{f60['precision']:.3f}" if f60["precision"] is not None else "—",
                         hr["base_rate"],
                         f"{lift:+.3f}" if lift is not None else "—")
            else:
                log.info("  %-5s %s", side, hr.get("status", "?"))

    prefix = gcs_model_prefix(ticker, tf)
    vtag = ("_" + "_".join(blocks) if blocks else "") + ("_roll" if window == "rolling" else "")
    if calibrate != "none":
        vtag += f"_cal-{calibrate}"
    if holdout:
        vtag += f"_ho{holdout.replace('-', '')}"
    blob = f"{prefix}/dir_probe_e4_tb_h{horizon}_k{k_atr}_{mag_cond}{vtag}_{int(time.time())}.json"
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
                   choices=["e1_horizon", "e2_trigger", "e4_triple_barrier"])
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--horizon", type=int, default=15,
                   help="forward-return / barrier horizon in bars (session-aware)")
    p.add_argument("--regime", default="none",
                   choices=["none", "vix_low", "vix_mid", "vix_high",
                            "pos_gamma", "neg_gamma",
                            "early_session", "mid_session", "late_session"],
                   help="E3: restrict train+test to a regime subset")
    p.add_argument("--barrier-atr", type=float, default=1.0,
                   help="E4: triple-barrier half-width in ATR-20 multiples")
    p.add_argument("--mag-cond", default="explosive",
                   choices=["none", "explosive", "big", "topq"],
                   help="E4: magnitude-model conditioner — predicted EXPLOSIVE, "
                        "EXPANDED+EXPLOSIVE='big', fold-relative top-quantile of "
                        "P(EXPLOSIVE)='topq', or none")
    p.add_argument("--mag-thresh", type=float, default=0.0,
                   help="E4: explosive/big ⇒ prob cutoff (0 ⇒ argmax==EXPLOSIVE); "
                        "topq ⇒ top fraction kept (default 0.2)")
    p.add_argument("--feature-blocks", default="",
                   help="E4: comma list of NEW feature blocks to inject "
                        "(flow, fracdiff, intraflow, intragex, realgex). Empty = "
                        "price-history surface only.")
    p.add_argument("--window", default="expanding",
                   choices=["expanding", "rolling"],
                   help="E4: training window — anchored expanding or rolling.")
    p.add_argument("--rolling-years", type=float, default=3.0,
                   help="E4: rolling-window lookback in years (window=rolling).")
    p.add_argument("--holdout", default=None,
                   help="E4: YYYY-MM-DD — bars >= this date are a LOCKED holdout "
                        "excluded from every training fold and evaluated once at "
                        "the end (the true out-of-sample test for the flicker).")
    p.add_argument("--calibrate", default="none",
                   choices=["none", "isotonic", "platt"],
                   help="E4: post-hoc calibration of the long/short head probs, "
                        "fit on a date-carved slice of TRAIN only. E-20 found "
                        "sigmoid HURT the TYPE model; isotonic here is UNTRIED — "
                        "this TESTS it, does not assume it helps.")
    p.add_argument("--cutoffs", default=None)
    args = p.parse_args()
    cutoffs = args.cutoffs.split(",") if args.cutoffs else None
    engine = get_engine()
    if args.experiment == "e4_triple_barrier":
        run_triple_barrier_probe(engine, args.ticker, args.tf, args.horizon,
                                 args.barrier_atr, args.mag_cond,
                                 args.mag_thresh, cutoffs,
                                 feature_blocks=args.feature_blocks,
                                 window=args.window,
                                 rolling_years=args.rolling_years,
                                 holdout=args.holdout,
                                 calibrate=args.calibrate)
    else:
        run_probe(engine, args.ticker, args.tf, args.experiment, args.horizon,
                  cutoffs, regime=args.regime)


if __name__ == "__main__":
    main()
