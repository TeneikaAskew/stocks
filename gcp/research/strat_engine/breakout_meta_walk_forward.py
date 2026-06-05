"""Strat Engine — BREAKOUT META-LABEL walk-forward (STRAT-BREAKOUT-META).

Reframings #2 + #7 from the 2026-06-04 rethink, and the flagship of the set.

The Strat is a STOP-ENTRY BREAKOUT system: when bar t+1 trades through bar t's
high you are long (a 2U); through bar t's low you are short (a 2D). The
DIRECTION is therefore DETERMINISTIC, given by the rule — which is why training
a model to predict next_close>next_open (strat_dir) failed 24/24: it was the
wrong target. Here we do López de Prado META-LABELING instead:

  PRIMARY (rule, no ML): did t+1 break bar t's range? side = break direction.
  META  (the ML model):  given the breakout fired, does it FOLLOW THROUGH —
                         hit a +k_PT·ATR profit target before a -k_SL·ATR stop
                         within N bars (triple-barrier label)? Binary.

The meta-model predicts TRADE QUALITY, not direction — a well-posed problem.
The success test (López de Prado): does taking only the model's high-confidence
breakouts beat taking EVERY breakout? Vehicle is the underlying (no IV), so we
report precision, profit factor, and per-trade expectancy in R-multiples.

Triple-barrier is labeled on the SAME-tf forward bars (v1). Single-bar
ambiguity (both barriers touched in one bar) is resolved conservatively as a
STOP (the pessimistic assumption — never inflates the edge).

Run:
  python -m gcp.research.strat_engine.breakout_meta_walk_forward \\
      --ticker IWM --tf 15m --pt 1.0 --sl 0.5 --horizon 12
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
    TICKERS, TIMEFRAMES, GCS_BUCKET_DEFAULT, gcs_model_prefix,
)
from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
from gcp.research.strat_engine.strat_pred_train import featurize
from gcp.research.strat_engine.strat_walk_forward import (
    DEFAULT_CUTOFFS, MIN_TEST_BARS, _gcs_upload,
)
from gcp.research.strat_engine.strat_dir_walk_forward import make_direction_lgbm
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

MIN_EVENTS = 150  # per fold-side; below this the fold is reported but not scored

# Round-trip breakout-chase slippage, as a fraction of ATR, swept to show how
# much friction the gross edge can absorb. 0.0 = gross; 0.04 ≈ a couple cents on
# SPY/QQQ; 0.10 = pessimistic. (1 R = sl_atr·ATR in price, so cost_R scales 1/sl.)
FRICTION_LEVELS_ATR = [0.0, 0.02, 0.04, 0.06, 0.08, 0.10]


def add_ofi_proxies(df: pd.DataFrame) -> list[str]:
    """Order-flow PROXY features from OHLCV (we have NO true order-flow/L2/tick
    data — AlphaVantage gives bars only). These are weak substitutes for OFI:

      clv         close-location-value ((C-L)-(H-C))/(H-L) ∈ [-1,1] — where in
                  the bar's range did it close (buying vs selling pressure proxy)
      body_frac   (C-O)/(H-L) signed body as a fraction of range
      upper_wick  rejection from the highs ; lower_wick  rejection from the lows
      signed_vol_z  tick-rule signed volume (clv·volume) z-scored over 20 bars
                  (rolling, session-naive — known at bar close)
      clv_sum5    5-bar rolling sum of clv (order-flow momentum proxy)

    Adds the columns in place and returns their names. NaNs/inf → 0 handled by
    featurize. Honest tag: these are PROXIES, not OFI; if they move the needle
    that justifies sourcing real quote/trade data, not a claim we have it.
    """
    o, h, l, c, v = (df["open"], df["high"], df["low"], df["close"], df["volume"])
    rng = (h - l).replace(0, np.nan)
    df["clv"] = ((c - l) - (h - c)) / rng
    df["body_frac"] = (c - o) / rng
    df["upper_wick"] = (h - np.maximum(o, c)) / rng
    df["lower_wick"] = (np.minimum(o, c) - l) / rng
    sv = df["clv"].fillna(0) * v
    mu = sv.rolling(20, min_periods=5).mean()
    sd = sv.rolling(20, min_periods=5).std().replace(0, np.nan)
    df["signed_vol_z"] = ((sv - mu) / sd)
    df["clv_sum5"] = df["clv"].fillna(0).rolling(5, min_periods=1).sum()
    return ["clv", "body_frac", "upper_wick", "lower_wick", "signed_vol_z", "clv_sum5"]


def add_iv_flow(engine, ticker: str, df: pd.DataFrame) -> list[str]:
    """Options-IV 'flow'/positioning features from the EOD chain we already have
    (etf_options_snapshots, 1 snapshot/day). The historical-options surface is
    EOD-only (no intraday IV), so these are DAILY features broadcast to intraday
    bars using the PRIOR day's EOD value (bar date D reads D-1 EOD → no lookahead):

      iv_skew      put_ATM_IV − call_ATM_IV  (demand for downside protection /
                   dealer positioning — a slow 'flow' signal)
      iv_atm       (call+put)/2 ATM IV level
      iv_chg_1d    day-over-day ΔATM_IV (vol being bid/offered)
      iv_skew_chg  day-over-day Δskew

    Scoped to near-ATM contracts (|Δ∓0.5|<0.12) + nearest expiry so the window
    query over the 92M-row table is feasible inside the job (the old unscoped
    options_derived family timed out on pg8000). Fails loud on empty (no silent
    fallback on a financial field — Rule 3.7).
    """
    from sqlalchemy import text
    sql = text("""
        WITH last AS (
          SELECT ticker, snapshot_date, MAX(snapshot_ts) AS last_ts
            FROM etf_options_snapshots WHERE ticker = :t GROUP BY 1, 2),
        atm AS (
          SELECT s.snapshot_date AS d, s.option_type, s.implied_volatility AS iv,
                 ROW_NUMBER() OVER (
                   PARTITION BY s.snapshot_date, s.option_type
                   ORDER BY ABS(s.delta - CASE WHEN s.option_type='calls' THEN 0.5 ELSE -0.5 END)
                            ASC NULLS LAST, s.expiration ASC NULLS LAST) AS rn
            FROM etf_options_snapshots s
            JOIN last l ON s.ticker=l.ticker AND s.snapshot_date=l.snapshot_date
                       AND s.snapshot_ts=l.last_ts
           WHERE s.implied_volatility > 0
             AND ((s.option_type='calls' AND ABS(s.delta-0.5) < 0.12)
               OR (s.option_type='puts'  AND ABS(s.delta+0.5) < 0.12)))
        SELECT d,
               MAX(iv) FILTER (WHERE option_type='calls' AND rn=1) AS call_iv,
               MAX(iv) FILTER (WHERE option_type='puts'  AND rn=1) AS put_iv
          FROM atm GROUP BY d ORDER BY d
    """)
    with engine.connect() as conn:
        iv = pd.read_sql(sql, conn, params={"t": ticker})
    iv = iv.dropna(subset=["call_iv", "put_iv"])
    if iv.empty:
        raise SystemExit(f"add_iv_flow: no ATM IV rows for {ticker} — cannot build IV-flow features")
    iv["d"] = pd.to_datetime(iv["d"]).dt.date
    iv["iv_skew"] = iv["put_iv"] - iv["call_iv"]
    iv["iv_atm"] = (iv["put_iv"] + iv["call_iv"]) / 2
    iv["iv_chg_1d"] = iv["iv_atm"].diff()
    iv["iv_skew_chg"] = iv["iv_skew"].diff()
    # shift one trading day → bar date D uses D-1 EOD (strictly prior info)
    feats = ["iv_skew", "iv_atm", "iv_chg_1d", "iv_skew_chg"]
    iv_prior = iv[["d"] + feats].copy()
    iv_prior["join_date"] = iv_prior["d"].shift(-1)   # this row's values apply to the NEXT trading day
    m = iv_prior.dropna(subset=["join_date"]).set_index("join_date")[feats]
    for f in feats:
        df[f] = df["bar_date"].map(m[f])
    cov = float(df[feats[0]].notna().mean())
    log.info("IV-flow features added (EOD options, D-1 shifted): %s  coverage=%.1f%%",
             feats, 100 * cov)
    return feats


def _friction_sweep(fold_takes: list, sl_atr: float, cost_bps: float,
                    levels: list, entry_mode: str = "market") -> list:
    """For each ONE-WAY slippage level, per fold compute NET expectancy of the
    taken trades = mean(gross_R − cost_R).

    Realistic stop-limit modelling of which legs actually pay slippage:
      - entry: 'market' (stop order chasing the break) pays one-way slippage;
        'limit' (resting limit/stop-limit at the trigger) pays ZERO entry slip.
      - exit: a winner exits at the profit-target = a LIMIT fill → no slip;
        a loser exits at the stop = a STOP fill → pays one-way slip.
    So per trade: slip_legs = (entry_mode=='market') + (gross_R < 0).
    cost_price = entry·cost_bps/1e4 + slip_legs·oneway_atr·ATR;
    cost_R = cost_price / (sl_atr·ATR).
    """
    entry_legs = 1.0 if entry_mode == "market" else 0.0
    out = []
    for oneway in levels:
        net_exps, net_pos, scored = [], 0, 0
        for ft in fold_takes:
            atr = ft["atr"]; entry = ft["entry"]; r = ft["rmult"]
            exit_slip_atr = (r < 0).astype(float) * oneway        # only stop-outs pay
            if entry_mode == "realistic":
                # entry slip is the ACTUAL gap past the trigger (1-min measured),
                # not a swept assumption; exits still use the swept one-way.
                entry_slip_atr = ft["entry_slip"]
            else:
                entry_slip_atr = entry_legs * oneway              # market=1·oneway, limit=0
            slip_atr = entry_slip_atr + exit_slip_atr
            cost_price = entry * cost_bps / 1e4 + slip_atr * atr
            cost_R = cost_price / (sl_atr * atr)
            net = r - cost_R
            scored += 1
            ne = float(net.mean()); net_exps.append(ne)
            if ne > 0:
                net_pos += 1
        out.append({
            "oneway_slip_atr": oneway, "entry_mode": entry_mode,
            "scored_folds": scored, "net_positive_folds": net_pos,
            "median_net_exp_R": float(np.median(net_exps)) if net_exps else None,
        })
    return out


def _label_1min(side, entry, pt, sl, sl_atr, pt_atr, atr_t, start_ns, end_ns, sess_date,
                om_ts, om_open, om_high, om_low, om_date):
    """Resolve the triple barrier on 1-MINUTE bars + compute the REALISTIC entry
    slippage (the actual gap past the trigger on the breakout minute).

    Returns (label, r_multiple, entry_slip_atr):
      - finds the breakout minute = first 1-min bar that crosses the trigger
        (long: high≥entry; short: low≤entry);
      - entry_slip_atr = how far the breakout bar OPENED beyond the trigger,
        in ATR (0 if it opened at/inside the trigger — a resting limit fills with
        no slip; >0 if it gapped through — even a limit pays that gap);
      - scans PT/SL from the cross bar onward (true intra-bar order); same-minute
        double-touch → conservative stop. None if no 1-min coverage / no cross
        (caller falls back to the same-tf scan).
    """
    lo = np.searchsorted(om_ts, start_ns, "left")
    hi = np.searchsorted(om_ts, end_ns, "right")
    if hi <= lo:
        return None
    same = om_date[lo:hi] == np.datetime64(sess_date, "D")
    if not same.any():
        return None
    O = om_open[lo:hi][same]; H = om_high[lo:hi][same]; L = om_low[lo:hi][same]
    cross = (H >= entry) if side == 1 else (L <= entry)
    if not cross.any():
        return None                                   # never crossed → no entry
    ci = int(np.argmax(cross))                        # breakout minute
    # realistic entry slippage = gap of the breakout bar's open past the trigger
    if side == 1:
        entry_slip = max(0.0, float(O[ci] - entry))
    else:
        entry_slip = max(0.0, float(entry - O[ci]))
    entry_slip_atr = entry_slip / atr_t if atr_t > 0 else 0.0
    Hc = H[ci:]; Lc = L[ci:]
    if side == 1:
        pt_hit = Hc >= pt; sl_hit = Lc <= sl
    else:
        pt_hit = Lc <= pt; sl_hit = Hc >= sl
    i_pt = int(np.argmax(pt_hit)) if pt_hit.any() else len(Hc)
    i_sl = int(np.argmax(sl_hit)) if sl_hit.any() else len(Hc)
    if i_pt == len(Hc) and i_sl == len(Hc):
        return (0, 0.0, entry_slip_atr)               # timeout
    if i_sl <= i_pt:
        return (0, -sl_atr, entry_slip_atr)           # stop first (ties→stop)
    return (1, pt_atr, entry_slip_atr)                # profit target first


def build_breakout_events(df: pd.DataFrame, pt_atr: float, sl_atr: float,
                           horizon: int, tf_minutes: int = 15,
                           onemin: dict | None = None) -> pd.DataFrame:
    """Detect primary breakout events and triple-barrier label them.

    For each bar t (decision at close of t), the trigger levels for t+1 are bar
    t's own high/low. LONG event = high[t+1] > high[t]; SHORT = low[t+1] <
    low[t]. Outside bars on t+1 (both broke) are ambiguous and skipped.

    Labeling: if `onemin` is given (sorted arrays ts/high/low/date), barriers
    are resolved on 1-MINUTE bars over [start of t+1, +horizon·tf_minutes) —
    the corrected path. Otherwise (or where 1-min coverage is missing) it falls
    back to the conservative same-tf forward scan.

    Returns a per-event frame: decision_pos (= bar t, features align here),
    side (+1/-1), entry, label (1=PT first, 0 otherwise), r_multiple,
    label_source ('1min'|'same_tf'), event_date.
    """
    g = df.reset_index(drop=True)
    n = len(g)
    high = g["high"].values; low = g["low"].values
    close = g["close"].values
    atr = g["atr_20"].values
    bar_date = g["bar_date"].values
    ts_ns = pd.to_datetime(g["ts"], utc=True).values.astype("datetime64[ns]").astype(np.int64)
    horizon_ns = int(horizon * tf_minutes * 60 * 1_000_000_000)
    om = onemin or {}
    om_ts = om.get("ts_ns"); om_open = om.get("open"); om_high = om.get("high")
    om_low = om.get("low"); om_date = om.get("date")

    pos_idx, side_a, entry_a, label_a, rmult_a, src_a, atr_a, slip_a = \
        [], [], [], [], [], [], [], []

    for t in range(n - 1):
        if not (np.isfinite(atr[t]) and atr[t] > 0):
            continue
        if bar_date[t + 1] != bar_date[t]:
            continue
        up_break = high[t + 1] > high[t]
        dn_break = low[t + 1] < low[t]
        if up_break == dn_break:
            continue
        side = 1 if up_break else -1
        entry = high[t] if side == 1 else low[t]
        pt = entry + side * pt_atr * atr[t]
        sl = entry - side * sl_atr * atr[t]

        res, src, eslip = None, None, 0.0
        if om_ts is not None:
            res = _label_1min(side, entry, pt, sl, sl_atr, pt_atr, atr[t],
                              ts_ns[t + 1], ts_ns[t + 1] + horizon_ns, bar_date[t],
                              om_ts, om_open, om_high, om_low, om_date)
            if res is not None:
                src = "1min"; eslip = res[2]
        if res is None:  # fallback: conservative same-tf scan
            src = "same_tf"
            label, rmult = 0, None
            for j in range(t + 1, min(t + horizon, n - 1) + 1):
                if bar_date[j] != bar_date[t]:
                    break
                hi, lo = high[j], low[j]
                hit_pt = (hi >= pt) if side == 1 else (lo <= pt)
                hit_sl = (lo <= sl) if side == 1 else (hi >= sl)
                if hit_sl and hit_pt:
                    label, rmult = 0, -sl_atr; break
                if hit_pt:
                    label, rmult = 1, pt_atr; break
                if hit_sl:
                    label, rmult = 0, -sl_atr; break
            if rmult is None:
                realized = side * (close[j] - entry) / atr[t]
                rmult = float(realized); label = 1 if realized >= pt_atr else 0
            res = (label, rmult, 0.0)

        pos_idx.append(t); side_a.append(side); entry_a.append(entry)
        label_a.append(res[0]); rmult_a.append(res[1]); src_a.append(src)
        atr_a.append(float(atr[t])); slip_a.append(float(eslip))

    ev = pd.DataFrame({
        "decision_pos": pos_idx, "side": side_a, "entry": entry_a,
        "label": label_a, "r_multiple": rmult_a, "label_source": src_a,
        "atr_at_entry": atr_a, "entry_slip_atr": slip_a,
    })
    ev["event_date"] = bar_date[ev["decision_pos"].values]
    return ev


def _load_1min(engine, ticker: str) -> dict | None:
    """Load all 1-min bars for the ticker as sorted numpy arrays for the barrier
    resolver. Returns None if the table has no rows (→ same-tf fallback)."""
    from sqlalchemy import text
    sql = text("SELECT ts, open, high, low FROM market_data_intraday "
               "WHERE ticker = :t AND interval = '1min' ORDER BY ts")
    with engine.connect() as conn:
        m = pd.read_sql(sql, conn, params={"t": ticker})
    if m.empty:
        return None
    ts = pd.to_datetime(m["ts"], utc=True)
    return {
        "ts_ns": ts.values.astype("datetime64[ns]").astype(np.int64),
        "open": m["open"].astype(float).values,
        "high": m["high"].astype(float).values,
        "low": m["low"].astype(float).values,
        "date": ts.dt.tz_convert("America/New_York").dt.normalize().dt.tz_localize(None)
                  .values.astype("datetime64[D]"),
    }


_TF_MINUTES = {"5m": 5, "15m": 15, "30m": 30}


def walk_forward_meta(engine, ticker, tf, pt_atr, sl_atr, horizon,
                      cutoffs=None, barrier_tf="1m", take_thresh=0.55,
                      cost_bps=1.0, entry_mode="market", ofi_proxies=False,
                      iv_flow=False) -> dict:
    cutoffs = cutoffs or DEFAULT_CUTOFFS
    log.info("=" * 72)
    log.info("BREAKOUT-META  %s %s  PT=%.2f SL=%.2f H=%d  barrier=%s take≥%.2f",
             ticker, tf, pt_atr, sl_atr, horizon, barrier_tf, take_thresh)
    log.info("=" * 72)

    df = load_labeled_dataset(engine, ticker, tf, include_next_bar_ohlc=False)
    df = df.sort_values(["bar_date", "ts"]).reset_index(drop=True)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date

    if ofi_proxies:
        added = add_ofi_proxies(df)
        log.info("OFI proxies added (OHLCV-derived, NOT true order flow): %s", added)
    if iv_flow:
        add_iv_flow(engine, ticker, df)

    onemin = None
    if barrier_tf == "1m":
        onemin = _load_1min(engine, ticker)
        log.info("1-min bars for barrier labeling: %s",
                 "loaded" if onemin else "NONE — falling back to same-tf scan")

    ev = build_breakout_events(df, pt_atr, sl_atr, horizon,
                               tf_minutes=_TF_MINUTES.get(tf, 15), onemin=onemin)
    if ev.empty:
        log.warning("no breakout events — aborting"); return {"status": "NO_EVENTS"}
    base_precision = float(ev["label"].mean())
    src_counts = ev["label_source"].value_counts().to_dict()
    log.info("primary breakouts: %d  (base follow-through rate=%.3f, long=%d short=%d) "
             "label_source=%s", len(ev), base_precision,
             int((ev.side == 1).sum()), int((ev.side == -1).sum()), src_counts)

    # Features at the DECISION bar (align by integer position).
    X_df, feat_cols = featurize(df)
    X_all = X_df.values.astype(np.float32, copy=False)
    Xev = X_all[ev["decision_pos"].values]
    # add side as a feature (long vs short breakouts behave differently)
    Xev = np.hstack([Xev, ev["side"].values.reshape(-1, 1).astype(np.float32)])
    y = ev["label"].values.astype(np.int64)
    rmult = ev["r_multiple"].values.astype(np.float64)
    atr_ev = ev["atr_at_entry"].values.astype(np.float64)
    entry_ev = ev["entry"].values.astype(np.float64)
    eslip_ev = ev["entry_slip_atr"].values.astype(np.float64)
    edates = pd.DatetimeIndex(ev["event_date"]).values.astype("datetime64[D]")
    tt = round(take_thresh, 2)
    fold_takes = []   # per-fold taken-trade arrays for the friction sweep

    folds = []
    for i, cut in enumerate(cutoffs):
        test_end = cutoffs[i + 1] if i + 1 < len(cutoffs) else \
            str(pd.Timestamp(df["bar_date"].max()) + pd.Timedelta(days=1))[:10]
        tr = edates < np.datetime64(cut)
        te = (edates >= np.datetime64(cut)) & (edates < np.datetime64(test_end))
        n_tr, n_te = int(tr.sum()), int(te.sum())
        if n_te < MIN_EVENTS or n_tr < MIN_EVENTS:
            folds.append({"fold": f"{cut}..{test_end}", "n_test": n_te, "status": "SKIP_THIN"})
            continue
        model = make_direction_lgbm()
        model.fit(Xev[tr], y[tr])
        p = model.predict_proba(Xev[te])[:, 1]

        base_pf = _profit_factor(rmult[te], np.ones(n_te, bool))
        base_exp = float(rmult[te].mean())
        row = {"fold": f"{cut}..{test_end}", "n_train": n_tr, "n_test": n_te,
               "base_precision": float(y[te].mean()),
               "base_expectancy_R": base_exp, "base_profit_factor": base_pf,
               "by_threshold": {}, "status": "OK"}
        for thr in sorted({0.50, 0.55, 0.60, tt}):
            take = p >= thr
            n_take = int(take.sum())
            if n_take < 20:
                row["by_threshold"][thr] = {"n": n_take, "status": "thin"}
                continue
            prec = float(y[te][take].mean())
            exp = float(rmult[te][take].mean())
            pf = _profit_factor(rmult[te], take)
            row["by_threshold"][thr] = {
                "n": n_take, "precision": prec, "expectancy_R": exp,
                "profit_factor": pf,
                "precision_lift_pp": (prec - row["base_precision"]) * 100,
            }
        # capture the take_thresh trades for the net-of-cost sweep
        take_tt = p >= tt
        if int(take_tt.sum()) >= 20:
            sub = np.where(te)[0][take_tt]
            fold_takes.append({"fold": row["fold"], "rmult": rmult[sub],
                               "atr": atr_ev[sub], "entry": entry_ev[sub],
                               "entry_slip": eslip_ev[sub]})
        folds.append(row)
        bt = row["by_threshold"].get(tt, {})
        log.info("  %s n_te=%d base[prec=%.3f exp=%+.3fR pf=%.2f] | take≥%.2f n=%s prec=%s exp=%s",
                 row["fold"], n_te, row["base_precision"], base_exp, base_pf, take_thresh,
                 bt.get("n"), _f(bt.get("precision")), _f(bt.get("expectancy_R"), "+.3f"))

    # ── NET-OF-COST gate: does the gross edge survive friction? ──────────────
    # Per-trade round-trip cost = spread (bps of notional) + breakout-chase
    # slippage (a fraction of ATR, since you cross the spread chasing the break).
    # Converted to R via 1 R = sl_atr·ATR in price. We SWEEP the slippage to show
    # how much friction the edge absorbs before dying.
    med_atr = float(np.median(atr_ev)) if len(atr_ev) else float("nan")
    med_entry = float(np.median(entry_ev)) if len(entry_ev) else float("nan")
    sweep = _friction_sweep(fold_takes, sl_atr, cost_bps, FRICTION_LEVELS_ATR, entry_mode)
    log.info("─" * 72)
    log.info("NET-OF-COST SWEEP  entry=%s  (spread=%.1fbps + ONE-WAY slippage·ATR; "
             "median ATR=%.3f, median px=%.1f → 0.04·ATR≈%.1f¢)",
             entry_mode, cost_bps, med_atr, med_entry, 0.04 * med_atr * 100)
    log.info("  %-12s %-12s %-10s", "oneway_slip", "net+folds", "med_net_R")
    for s in sweep:
        log.info("  %-12.3f %-12s %-10s",
                 s["oneway_slip_atr"],
                 f"{s['net_positive_folds']}/{s['scored_folds']}",
                 _f(s["median_net_exp_R"], "+.3f"))
    # net verdict at the realistic mid level (0.02 ATR ONE-WAY slippage ≈ 1-1.5¢)
    mid = next((s for s in sweep if abs(s["oneway_slip_atr"] - 0.02) < 1e-9), sweep[len(sweep) // 2])
    net_verdict = "NET_PASS" if (mid["scored_folds"] >= 4 and
                                 mid["net_positive_folds"] >= 5) else "NET_FAIL"
    log.info("NET verdict @ oneway_slip=%.3f ATR, entry=%s: %s (%d/%d folds net-positive)",
             mid["oneway_slip_atr"], entry_mode, net_verdict,
             mid["net_positive_folds"], mid["scored_folds"])

    # ── GROSS verdict (unchanged) ──
    oks = [f for f in folds if f.get("status") == "OK"]
    lift_folds = sum(1 for f in oks
                     if f["by_threshold"].get(tt, {}).get("precision_lift_pp", -1) > 0
                     and f["by_threshold"].get(tt, {}).get("expectancy_R", -9) >
                         f["base_expectancy_R"])
    verdict = "PASS" if (len(oks) >= 4 and lift_folds >= 5) else (
        "INSUFFICIENT_DATA" if len(oks) < 4 else "FAIL")
    log.info("META verdict: %s (take≥%.2f beat base in %d of %d OK folds)",
             verdict, take_thresh, lift_folds, len(oks))

    summary = {
        "ticker": ticker, "tf": tf, "model": "STRAT-BREAKOUT-META",
        "params": {"pt_atr": pt_atr, "sl_atr": sl_atr, "horizon": horizon,
                   "barrier_tf": barrier_tf, "take_thresh": take_thresh,
                   "cost_bps": cost_bps, "entry_mode": entry_mode},
        "n_events": int(len(ev)), "overall_base_precision": base_precision,
        "label_source_counts": src_counts,
        "gross_verdict": verdict, "lift_folds": lift_folds,
        "net_verdict": net_verdict, "friction_sweep": sweep,
        "median_atr": med_atr, "median_entry_px": med_entry,
        "folds": folds,
        "computed_at": pd.Timestamp.utcnow().isoformat(),
    }
    blob = f"{gcs_model_prefix(ticker, tf)}/breakout_meta_wf_pt{pt_atr}_sl{sl_atr}_h{horizon}_{int(time.time())}.json"
    _gcs_upload(json.dumps(summary, indent=2, default=str).encode(), blob)
    log.info("saved gs://%s/%s", os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT), blob)
    return summary


def _profit_factor(rmult: np.ndarray, take: np.ndarray) -> float:
    r = rmult[take]
    gains = r[r > 0].sum()
    losses = -r[r < 0].sum()
    return float(gains / losses) if losses > 0 else float("inf")


def _f(v, fmt=".3f"):
    return format(v, fmt) if isinstance(v, (int, float)) else "—"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--pt", type=float, default=1.0, help="profit target in ATR")
    p.add_argument("--sl", type=float, default=0.5, help="stop in ATR")
    p.add_argument("--horizon", type=int, default=12, help="vertical barrier in bars")
    p.add_argument("--barrier-tf", default="1m", choices=["1m", "same"],
                   help="1m=resolve triple barrier on 1-min bars (corrected, "
                        "true intra-bar order); same=conservative same-tf scan.")
    p.add_argument("--take-thresh", type=float, default=0.55,
                   help="meta-model confidence to 'take' a breakout (base rate "
                        "is low, so 0.60 is rarely reached — 0.55 default).")
    p.add_argument("--cost-bps", type=float, default=1.0,
                   help="round-trip spread/commission in bps of notional (the "
                        "one-way slippage·ATR term is added per slipping leg).")
    p.add_argument("--entry-mode", default="market",
                   choices=["market", "limit", "realistic"],
                   help="market=stop chasing the break (pays full one-way entry "
                        "slip); limit=resting stop-limit (zero entry slip); "
                        "realistic=ACTUAL gap past the trigger on the breakout "
                        "minute, measured from 1-min bars (the honest fill model "
                        "between market and limit). Stop-out exits always pay slip.")
    p.add_argument("--ofi-proxies", action="store_true",
                   help="add OHLCV-derived order-flow PROXY features (CLV, signed "
                        "volume z, wicks). NOT true OFI — we have no L2/tick data.")
    p.add_argument("--iv-flow", action="store_true",
                   help="add options-IV positioning/flow features (ATM put-call "
                        "skew, IV level/changes) from the EOD chain, D-1 shifted.")
    p.add_argument("--cutoffs", default=None)
    args = p.parse_args()
    cutoffs = args.cutoffs.split(",") if args.cutoffs else None
    walk_forward_meta(get_engine(), args.ticker, args.tf,
                      args.pt, args.sl, args.horizon, cutoffs=cutoffs,
                      barrier_tf=args.barrier_tf, take_thresh=args.take_thresh,
                      cost_bps=args.cost_bps, entry_mode=args.entry_mode,
                      ofi_proxies=args.ofi_proxies, iv_flow=args.iv_flow)


if __name__ == "__main__":
    main()
