"""Strat Engine — INTRADAY MOMENTUM (INTRADAY-MOM).

Reframing #6 from the 2026-06-04 rethink. Gao, Han, Li & Zhou (2018, JFE,
"Market Intraday Momentum"): the FIRST half-hour return predicts the LAST
half-hour return on SPY/ETFs (R²≈1.6–2.6%), stronger on high-vol / high-volume /
news days — exactly the EXPLOSIVE regime. Direction is not a property of every
bar; it concentrates in time windows. So reframe per-BAR → per-DAY.

This script:
  1. REPLICATION (go/no-go): OLS of last-30min return on first-30min return.
     Report R² and t-stat per ticker over 2019–2026. If we can't reproduce the
     published ~1.6% R² + significance, STOP — it's a data/timezone bug, not a
     null. (No point ML-ing a signal we can't even replicate.)
  2. WALK-FORWARD direction model: predict sign(last-30) from first-30 (+ the
     12th half-hour, VIX, overnight gap, morning RVOL). Metric = OOS directional
     accuracy + per-trade expectancy of the underlying last-30-min trade (no IV
     to beat — clean MOC-style vehicle).

Half-hour bars come straight from strat_features_30m (the 30m bar IS a
half-hour). RTH = 13 half-hours; bar 1 = 09:30–10:00 ET (first), bar 12 =
15:00–15:30 (the paper's penultimate predictor), bar 13 = 15:30–16:00 (last,
the target).

Run:
  python -m gcp.research.strat_engine.intraday_momentum --ticker SPY
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
    TICKERS, GCS_BUCKET_DEFAULT, gcs_model_prefix,
)
from gcp.research.strat_engine.strat_walk_forward import DEFAULT_CUTOFFS, _gcs_upload
from lib.logging_config import setup_logging
from sklearn.linear_model import LogisticRegression

setup_logging()
log = logging.getLogger(__name__)

OPEN_MIN = 9 * 60 + 30     # 09:30 ET
LAST_MIN = 15 * 60 + 30    # 15:30 ET (last half hour)
PEN_MIN = 15 * 60          # 15:00 ET (12th half hour)
MIN_TRAIN_DAYS = 120


def _load_halfhour(engine, ticker: str) -> pd.DataFrame:
    """One row per (date, half-hour bar) from strat_features_30m, ET minute-of-
    day tagged. Carries open/close (for the bar return) + vix_close + volume."""
    from sqlalchemy import text
    sql = text("SELECT ts, bar_date, open, close, volume, vix_close, rvol "
               "FROM strat_features_30m WHERE ticker = :t ORDER BY ts")
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"t": ticker})
    if df.empty:
        return df
    ts_et = pd.to_datetime(df["ts"], utc=True).dt.tz_convert("America/New_York")
    df["minute_of_day"] = ts_et.dt.hour * 60 + ts_et.dt.minute
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date
    df["ret"] = (df["close"] - df["open"]) / df["open"]
    return df


def build_day_panel(hh: pd.DataFrame) -> pd.DataFrame:
    """Pivot half-hour bars to one row per day with first/penultimate/last
    returns + day-level conditioning features. Days missing the open or close
    half-hour are dropped (can't form the pair)."""
    rows = []
    for d, g in hh.groupby("bar_date"):
        g = g.set_index("minute_of_day")
        if OPEN_MIN not in g.index or LAST_MIN not in g.index:
            continue
        first = g.loc[OPEN_MIN]
        last = g.loc[LAST_MIN]
        pen = g.loc[PEN_MIN] if PEN_MIN in g.index else None
        # morning RVOL / VIX as the conditioning context, known by 10:00.
        rows.append({
            "bar_date": d,
            "first_ret": float(first["ret"]),
            "pen_ret": float(pen["ret"]) if pen is not None else np.nan,
            "last_ret": float(last["ret"]),
            "morning_vix": float(first.get("vix_close")) if pd.notna(first.get("vix_close")) else np.nan,
            "morning_rvol": float(first.get("rvol")) if pd.notna(first.get("rvol")) else np.nan,
        })
    panel = pd.DataFrame(rows).dropna(subset=["first_ret", "last_ret"]).reset_index(drop=True)
    return panel


def replicate_ols(panel: pd.DataFrame) -> dict:
    """OLS last_ret ~ first_ret. Return slope, R², t-stat (the published test)."""
    x = panel["first_ret"].values
    y = panel["last_ret"].values
    n = len(x)
    xm, ym = x.mean(), y.mean()
    sxx = float(((x - xm) ** 2).sum())
    beta = float(((x - xm) * (y - ym)).sum() / sxx) if sxx > 0 else 0.0
    alpha = float(ym - beta * xm)
    resid = y - (alpha + beta * x)
    ss_res = float((resid ** 2).sum())
    ss_tot = float(((y - ym) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    # OLS t-stat on beta
    sigma2 = ss_res / (n - 2) if n > 2 else np.nan
    se_beta = float(np.sqrt(sigma2 / sxx)) if sxx > 0 else np.nan
    t_stat = beta / se_beta if se_beta and se_beta > 0 else np.nan
    # sign-agreement: fraction of days where sign(last)==sign(first)
    sign_agree = float((np.sign(x) == np.sign(y)).mean())
    return {"n_days": n, "beta": beta, "alpha": alpha, "r2": float(r2),
            "t_stat": float(t_stat), "sign_agreement": sign_agree}


def walk_forward_direction(panel: pd.DataFrame, cutoffs) -> list[dict]:
    """Per-fold logistic: P(last_ret>0 | first_ret, pen_ret, vix, rvol). Report
    OOS accuracy + expectancy of trading the last half-hour in the predicted
    direction (P&L = side * last_ret)."""
    feats = ["first_ret", "pen_ret", "morning_vix", "morning_rvol"]
    p = panel.copy()
    p["pen_ret"] = p["pen_ret"].fillna(0.0)
    p["morning_vix"] = p["morning_vix"].fillna(p["morning_vix"].median())
    p["morning_rvol"] = p["morning_rvol"].fillna(p["morning_rvol"].median())
    p["y"] = (p["last_ret"] > 0).astype(int)
    dates = pd.to_datetime(p["bar_date"]).values.astype("datetime64[D]")
    folds = []
    for i, cut in enumerate(cutoffs):
        test_end = cutoffs[i + 1] if i + 1 < len(cutoffs) else \
            str(pd.Timestamp(p["bar_date"].max()) + pd.Timedelta(days=1))[:10]
        tr = dates < np.datetime64(cut)
        te = (dates >= np.datetime64(cut)) & (dates < np.datetime64(test_end))
        if int(tr.sum()) < MIN_TRAIN_DAYS or int(te.sum()) < 30:
            folds.append({"fold": f"{cut}..{test_end}", "n_test": int(te.sum()),
                          "status": "SKIP_THIN"})
            continue
        Xtr, Xte = p.loc[tr, feats].values, p.loc[te, feats].values
        ytr, yte = p.loc[tr, "y"].values, p.loc[te, "y"].values
        # standardize (logistic is scale-sensitive)
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        clf = LogisticRegression(max_iter=1000, C=1.0)
        clf.fit((Xtr - mu) / sd, ytr)
        pe = clf.predict_proba((Xte - mu) / sd)[:, 1]
        pred = (pe >= 0.5).astype(int)
        acc = float((pred == yte).mean())
        base_acc = float(max(ytr.mean(), 1 - ytr.mean()))
        side = np.where(pred == 1, 1.0, -1.0)
        last_ret_te = p.loc[te, "last_ret"].values
        exp_bps = float(np.mean(side * last_ret_te) * 1e4)
        folds.append({"fold": f"{cut}..{test_end}", "n_test": int(te.sum()),
                      "accuracy": acc, "base_accuracy": base_acc,
                      "acc_beat_pp": (acc - base_acc) * 100,
                      "expectancy_bps": exp_bps, "status": "OK"})
        log.info("  %s n_te=%d acc=%.3f base=%.3f Δ=%+.1fpp exp=%+.1fbps",
                 folds[-1]["fold"], folds[-1]["n_test"], acc, base_acc,
                 folds[-1]["acc_beat_pp"], exp_bps)
    return folds


def run(engine, ticker: str, cutoffs=None) -> dict:
    cutoffs = cutoffs or DEFAULT_CUTOFFS
    log.info("=" * 72)
    log.info("INTRADAY-MOM  %s", ticker)
    log.info("=" * 72)
    hh = _load_halfhour(engine, ticker)
    if hh.empty:
        log.warning("no 30m bars for %s", ticker); return {"status": "NO_DATA"}
    panel = build_day_panel(hh)
    log.info("day panel: %d days (%s..%s)", len(panel),
             panel["bar_date"].min(), panel["bar_date"].max())

    rep = replicate_ols(panel)
    log.info("REPLICATION (OLS last~first): beta=%+.3f  R²=%.4f  t=%.2f  sign_agree=%.3f  n=%d",
             rep["beta"], rep["r2"], rep["t_stat"], rep["sign_agreement"], rep["n_days"])
    repro = "REPRODUCED" if (rep["r2"] >= 0.005 and abs(rep["t_stat"]) >= 2.0) else "NOT_REPRODUCED"
    log.info("replication verdict: %s (published ≈ R²0.016, t>3; floor here R²≥0.005,|t|≥2)", repro)

    log.info("─" * 72)
    log.info("WALK-FORWARD direction model")
    folds = walk_forward_direction(panel, cutoffs)
    oks = [f for f in folds if f.get("status") == "OK"]
    acc_pos = sum(1 for f in oks if f["acc_beat_pp"] > 0)
    exp_pos = sum(1 for f in oks if f["expectancy_bps"] > 0)
    verdict = "PASS" if (len(oks) >= 4 and acc_pos >= 5 and exp_pos >= 5) else (
        "INSUFFICIENT_DATA" if len(oks) < 4 else "FAIL")
    log.info("WF verdict: %s (acc>base in %d, exp>0 in %d, of %d OK folds)",
             verdict, acc_pos, exp_pos, len(oks))

    summary = {
        "ticker": ticker, "model": "INTRADAY-MOM",
        "replication": rep, "replication_verdict": repro,
        "wf_verdict": verdict, "folds": folds,
        "computed_at": pd.Timestamp.utcnow().isoformat(),
    }
    blob = f"{gcs_model_prefix(ticker, '30m')}/intraday_mom_{int(time.time())}.json"
    _gcs_upload(json.dumps(summary, indent=2, default=str).encode(), blob)
    log.info("saved gs://%s/%s", os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT), blob)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="SPY", choices=list(TICKERS))
    p.add_argument("--cutoffs", default=None)
    args = p.parse_args()
    cutoffs = args.cutoffs.split(",") if args.cutoffs else None
    run(get_engine(), args.ticker, cutoffs=cutoffs)


if __name__ == "__main__":
    main()
