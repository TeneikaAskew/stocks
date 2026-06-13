"""Strat Engine — one-week prediction-vs-actual report with TYPE + DIRECTION lenses.

Trains production-config model on data STRICTLY BEFORE the test window. Predicts
on each bar in the test week. Reports both the strat-TYPE lens (does argmax
match actual next-bar type) AND the direction lens (does next bar close in the
predicted direction).

Output sections:
  Setup (leak-free assertion)
  Table 1 — Summary: type vs direction accuracy, threshold table, distribution
  Table 2 — Confident directional calls per bar (top-prob >= 0.55, pred in {2U, 2D})
  Table 3 — Every test bar (no filter)
  2x2 cross-tab — TYPE-HIT/MISS × DIR-HIT/MISS with counts, rates, avg move_$
  Magnitude — favorable vs adverse move, top 5 worst losses, loss by actual_type
  Bottom line — 3 verdict items per spec

Usage:
  python -m gcp.research.strat_engine.strat_pred_report \\
      --ticker IWM --tf 15m \\
      --test-start 2026-05-11 --test-end 2026-05-16
"""
from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from gcp.database import get_engine
from gcp.research.strat_engine.strat_config import (
    TICKERS, TIMEFRAMES, LABEL_COL, LABEL_CLASSES, LABEL_TO_IDX,
)
from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
from gcp.research.strat_engine.strat_pred_train import featurize, make_lgbm
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)


def _direction_of(pred_type: str) -> str:
    return "up" if pred_type == "2U" else ("down" if pred_type == "2D" else "—")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--test-start", required=True, help="YYYY-MM-DD inclusive")
    p.add_argument("--test-end", required=True, help="YYYY-MM-DD EXCLUSIVE")
    args = p.parse_args()

    log.info("=" * 70)
    log.info("STRAT-PRED REPORT (TYPE + DIRECTION lenses)  %s %s  test=[%s..%s)",
             args.ticker, args.tf, args.test_start, args.test_end)
    log.info("=" * 70)

    engine = get_engine()
    df = load_labeled_dataset(engine, args.ticker, args.tf,
                                include_next_bar_ohlc=True)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date

    test_start = pd.Timestamp(args.test_start).date()
    test_end = pd.Timestamp(args.test_end).date()

    train_df = df[df["bar_date"] < test_start].copy()
    test_df = df[(df["bar_date"] >= test_start) & (df["bar_date"] < test_end)].copy()

    log.info("─" * 70)
    log.info("TRAIN / TEST BOUNDARY")
    log.info("  train: %d bars, dates %s..%s",
             len(train_df), train_df["bar_date"].min(), train_df["bar_date"].max())
    log.info("  test:  %d bars, dates %s..%s",
             len(test_df), test_df["bar_date"].min(), test_df["bar_date"].max())
    if set(train_df["bar_date"].unique()) & set(test_df["bar_date"].unique()):
        raise RuntimeError("LEAK: train/test date overlap")
    log.info("  overlap: 0 dates (leak-free)")

    if len(test_df) == 0:
        log.error("test window is empty"); return

    # Featurize, align
    X_train, train_cols = featurize(train_df)
    X_test, test_cols = featurize(test_df)
    all_cols = sorted(set(train_cols) | set(test_cols))
    X_train = X_train.reindex(columns=all_cols, fill_value=0).astype(np.float32)
    X_test = X_test.reindex(columns=all_cols, fill_value=0).astype(np.float32)
    y_test = test_df[LABEL_COL].map(LABEL_TO_IDX).values
    y_train = train_df[LABEL_COL].map(LABEL_TO_IDX).values
    log.info("featurize: train %s, test %s", X_train.shape, X_test.shape)

    log.info("training LightGBM (no calibration) ...")
    model = make_lgbm(class_weight=None)
    model.fit(X_train.values, y_train)
    log.info("training done.")

    proba = model.predict_proba(X_test.values)
    # Align proba columns to LABEL_CLASSES ordering
    proba_aligned = np.zeros((proba.shape[0], len(LABEL_CLASSES)))
    for j, idx in enumerate(model.classes_):
        proba_aligned[:, idx] = proba[:, j]
    proba = proba_aligned

    pred_idx = np.argmax(proba, axis=1)
    top_prob = proba.max(axis=1)
    hit_type = (pred_idx == y_test).astype(int)

    # ── DIRECTION LENS ──
    # The "predicted bar" is the NEXT bar; check if it closed in the
    # predicted direction. dir is only defined when pred is 2U or 2D.
    next_open = test_df["next_open"].values
    next_close = test_df["next_close"].values
    move_dollar = next_close - next_open
    move_pct = np.where(next_open != 0, move_dollar / next_open * 100, 0)
    actual_dir_up = next_close > next_open
    actual_dir_dn = next_close < next_open
    pred_2u = pred_idx == LABEL_TO_IDX["2U"]
    pred_2d = pred_idx == LABEL_TO_IDX["2D"]
    dir_hit = np.where(pred_2u, actual_dir_up,
                        np.where(pred_2d, actual_dir_dn, False)).astype(int)

    rep = pd.DataFrame({
        "ts": test_df["ts"].values,
        "bar_date": test_df["bar_date"].values,
        "open": test_df["open"].values,
        "high": test_df["high"].values,
        "low": test_df["low"].values,
        "close": test_df["close"].values,
        "next_open": next_open,
        "next_close": next_close,
        "prev_strat": test_df["strat_candle"].values,
        "p1":  proba[:, 0],
        "p2u": proba[:, 1],
        "p2d": proba[:, 2],
        "p3":  proba[:, 3],
        "predicted": [LABEL_CLASSES[i] for i in pred_idx],
        "top_prob": top_prob,
        "actual": [LABEL_CLASSES[i] for i in y_test],
        "hit_type": hit_type,
        "dir_pred": [_direction_of(LABEL_CLASSES[i]) for i in pred_idx],
        "move_dollar": move_dollar,
        "move_pct": move_pct,
        "dir_hit": dir_hit,
    })
    rep["ts"] = pd.to_datetime(rep["ts"], utc=True).dt.tz_convert("America/New_York")

    # ── TABLE 1 — SUMMARY ──
    log.info("=" * 70)
    log.info("TABLE 1 — SUMMARY")
    log.info("=" * 70)

    n_total = len(rep)
    base_majority = int(np.bincount(y_test, minlength=len(LABEL_CLASSES)).argmax())
    base_rate = float((y_test == base_majority).mean())
    type_acc = float(hit_type.mean())

    log.info("Total test bars: %d", n_total)
    log.info("")
    log.info("**Actual next-bar-type distribution:**")
    log.info("| type | count | share |")
    log.info("|---|---|---|")
    for k, cls in enumerate(LABEL_CLASSES):
        n = int((y_test == k).sum())
        log.info(f"| {cls} | {n} | {n/n_total:.1%} |")

    log.info("")
    log.info("**TYPE lens (all bars, no confidence filter):**")
    log.info("| metric | value |")
    log.info("|---|---|")
    log.info(f"| TYPE accuracy (argmax==actual) | {type_acc:.3f} |")
    log.info(f"| base rate (majority class = {LABEL_CLASSES[base_majority]}) | {base_rate:.3f} |")
    log.info(f"| TYPE accuracy beat over base | +{(type_acc - base_rate)*100:.1f}pp |")
    dir_mask_all = pred_2u | pred_2d
    log.info(f"| directional predictions (subset) | {int(dir_mask_all.sum())}/{n_total} |")
    if dir_mask_all.sum():
        log.info(f"| TYPE accuracy on directional preds | {float(hit_type[dir_mask_all].mean()):.3f} |")

    # ── CONFIDENCE-DISCRIMINATION (TYPE) ──
    log.info("")
    log.info("**TYPE confident-call hit rate at thresholds (top-prob ≥ X):**")
    log.info("| top-prob ≥ | n calls | TYPE hit rate |")
    log.info("|---|---|---|")
    type_rates = {}
    for thresh in [0.50, 0.55, 0.60]:
        mask = top_prob >= thresh
        n = int(mask.sum())
        if n == 0:
            log.info(f"| {thresh:.2f} | 0 | — |")
            type_rates[thresh] = None
        else:
            hr = float(hit_type[mask].mean())
            type_rates[thresh] = hr
            log.info(f"| {thresh:.2f} | {n} | {hr:.3f} |")

    # ── DIRECTION LENS ──
    log.info("")
    log.info("**DIRECTION lens (confident DIRECTIONAL calls only):**")
    conf_dir_mask = (top_prob >= 0.55) & (pred_2u | pred_2d)
    n_conf = int(conf_dir_mask.sum())
    if n_conf == 0:
        log.info("(no confident directional calls)")
    else:
        dir_acc = float(dir_hit[conf_dir_mask].mean())
        type_acc_conf = float(hit_type[conf_dir_mask].mean())
        log.info("| metric | value |")
        log.info("|---|---|")
        log.info(f"| confident directional calls (top-prob ≥ 0.55, pred ∈ 2U,2D) | {n_conf} |")
        log.info(f"| TYPE accuracy (confident subset) | {type_acc_conf:.3f} |")
        log.info(f"| DIRECTION accuracy (confident subset) | {dir_acc:.3f} |")
        log.info(f"| DIRECTION beat over TYPE (same subset) | {(dir_acc - type_acc_conf)*100:+.1f}pp |")

    # ── CONFIDENCE-DISCRIMINATION (DIRECTION) ──
    log.info("")
    log.info("**DIRECTION confident-call hit rate at thresholds (directional preds only):**")
    log.info("| top-prob ≥ | n calls | DIR hit rate |")
    log.info("|---|---|---|")
    dir_rates = {}
    for thresh in [0.50, 0.55, 0.60]:
        mask = (top_prob >= thresh) & (pred_2u | pred_2d)
        n = int(mask.sum())
        if n == 0:
            log.info(f"| {thresh:.2f} | 0 | — |")
            dir_rates[thresh] = None
        else:
            hr = float(dir_hit[mask].mean())
            dir_rates[thresh] = hr
            log.info(f"| {thresh:.2f} | {n} | {hr:.3f} |")

    # Discrimination flag — does DIR rate RISE with the threshold?
    if all(dir_rates[t] is not None for t in (0.50, 0.55, 0.60)):
        if dir_rates[0.60] > dir_rates[0.55] > dir_rates[0.50]:
            disc_dir = "RISES monotonically — confidence discriminates"
        elif dir_rates[0.60] >= dir_rates[0.50] + 0.03:
            disc_dir = f"RISES (Δ={dir_rates[0.60]-dir_rates[0.50]:+.3f}) — confidence discriminates"
        elif abs(dir_rates[0.60] - dir_rates[0.50]) < 0.03:
            disc_dir = f"FLAT (Δ={dir_rates[0.60]-dir_rates[0.50]:+.3f}) — confidence uninformative on direction"
        else:
            disc_dir = f"DECLINES (Δ={dir_rates[0.60]-dir_rates[0.50]:+.3f}) — confidence anti-correlated with direction hits"
        log.info(f"DIRECTION confidence-discrimination: {disc_dir}")

    # ── 2x2 CROSS-TAB ──
    log.info("")
    log.info("=" * 70)
    log.info("2×2 CROSS-TAB — TYPE vs DIRECTION (confident calls only, top-prob ≥ 0.55, pred ∈ 2U,2D)")
    log.info("=" * 70)
    conf_rep = rep[conf_dir_mask].copy()
    if len(conf_rep) > 0:
        # Build the 4 cells
        m_th_dh = (conf_rep["hit_type"] == 1) & (conf_rep["dir_hit"] == 1)
        m_th_dm = (conf_rep["hit_type"] == 1) & (conf_rep["dir_hit"] == 0)
        m_tm_dh = (conf_rep["hit_type"] == 0) & (conf_rep["dir_hit"] == 1)
        m_tm_dm = (conf_rep["hit_type"] == 0) & (conf_rep["dir_hit"] == 0)

        log.info("| cell | n | share | avg move_$ | avg move_% |")
        log.info("|---|---|---|---|---|")
        for label, m in [("TYPE-HIT  & DIR-HIT  (right on both)", m_th_dh),
                          ("TYPE-HIT  & DIR-MISS (right structure, wrong price)", m_th_dm),
                          ("TYPE-MISS & DIR-HIT  (wrong structure, right price)", m_tm_dh),
                          ("TYPE-MISS & DIR-MISS (wrong on both)", m_tm_dm)]:
            n = int(m.sum())
            share = n / len(conf_rep) if len(conf_rep) else 0
            if n > 0:
                avg_d = float(conf_rep.loc[m, "move_dollar"].mean())
                avg_p = float(conf_rep.loc[m, "move_pct"].mean())
                log.info(f"| {label} | {n} | {share:.1%} | {avg_d:+.3f} | {avg_p:+.3f}% |")
            else:
                log.info(f"| {label} | 0 | 0.0% | — | — |")

    # ── MAGNITUDE ──
    log.info("")
    log.info("=" * 70)
    log.info("MAGNITUDE — favorable vs adverse moves (confident directional calls)")
    log.info("=" * 70)

    if n_conf > 0:
        # signed favorable move per row: + when DIR-HIT
        # For pred=2U on a DIR-HIT, move_dollar is positive; for pred=2D on a DIR-HIT, move_dollar is negative
        # The "favorable magnitude" we'd capture trading is abs(move_dollar) when DIR-HIT
        # The "adverse magnitude" we'd lose trading is abs(move_dollar) when DIR-MISS
        # (using simple signed-bar P&L as the tradeability proxy, no costs)
        dir_hit_arr = conf_rep["dir_hit"].values.astype(bool)
        moves_abs = conf_rep["move_dollar"].abs().values
        pct_abs = conf_rep["move_pct"].abs().values

        fav_dollar = moves_abs[dir_hit_arr]
        adv_dollar = moves_abs[~dir_hit_arr]
        fav_pct = pct_abs[dir_hit_arr]
        adv_pct = pct_abs[~dir_hit_arr]

        log.info("| metric | $ | % |")
        log.info("|---|---|---|")
        if len(fav_dollar):
            log.info(f"| n DIR-HIT (favorable) | {len(fav_dollar)} | |")
            log.info(f"| avg favorable move | {fav_dollar.mean():+.3f} | {fav_pct.mean():+.3f}% |")
            log.info(f"| median favorable move | {np.median(fav_dollar):+.3f} | {np.median(fav_pct):+.3f}% |")
        if len(adv_dollar):
            log.info(f"| n DIR-MISS (adverse) | {len(adv_dollar)} | |")
            log.info(f"| avg adverse move (loss size) | {adv_dollar.mean():+.3f} | {adv_pct.mean():+.3f}% |")
            log.info(f"| median adverse move | {np.median(adv_dollar):+.3f} | {np.median(adv_pct):+.3f}% |")

        # Net naive P&L per bar
        # If pred=2U: P&L per share = next_close - next_open
        # If pred=2D: P&L per share = next_open - next_close
        # So net = sign-adjusted move_dollar
        signed_pnl = np.where(conf_rep["dir_pred"].values == "up",
                                conf_rep["move_dollar"].values,
                                -conf_rep["move_dollar"].values)
        log.info("")
        log.info("**Naive per-bar P&L (entry at next_open, exit at next_close, no costs/spread/slippage):**")
        log.info(f"- total $/share across all confident directional calls: {signed_pnl.sum():+.3f}")
        log.info(f"- avg $/share per call: {signed_pnl.mean():+.4f}")
        log.info(f"- expectancy ratio (avg fav / avg adv): "
                 f"{fav_dollar.mean() / adv_dollar.mean():.3f}" if len(adv_dollar) else "—")

        # ── TOP 5 WORST LOSSES ──
        log.info("")
        log.info("**5 largest adverse moves (worst single losses, DIR-MISS rows):**")
        adv_rows = conf_rep[~dir_hit_arr].copy()
        if len(adv_rows) > 0:
            adv_rows["loss_dollar"] = adv_rows["move_dollar"].abs()
            adv_rows = adv_rows.sort_values("loss_dollar", ascending=False).head(5)
            log.info("| timestamp ET | dir_pred | top_p | actual_type | move_$ | move_% |")
            log.info("|---|---|---|---|---|---|")
            for _, r in adv_rows.iterrows():
                log.info(f"| {r['ts'].strftime('%a %m-%d %H:%M')} | {r['dir_pred']} "
                         f"| {r['top_prob']:.2f} | {r['actual']} "
                         f"| {r['move_dollar']:+.3f} | {r['move_pct']:+.3f}% |")

        # ── ADVERSE MOVES BY ACTUAL TYPE ──
        log.info("")
        log.info("**Adverse-move size by actual_type (loss concentration check):**")
        log.info("| actual_type | n DIR-MISS | avg loss $ | total loss $ | share of total loss |")
        log.info("|---|---|---|---|---|")
        total_loss = adv_dollar.sum() if len(adv_dollar) else 0
        adv_df = conf_rep[~dir_hit_arr].copy()
        adv_df["loss_dollar"] = adv_df["move_dollar"].abs()
        for cls in LABEL_CLASSES:
            sub = adv_df[adv_df["actual"] == cls]
            if len(sub) == 0:
                log.info(f"| {cls} | 0 | — | 0 | 0.0% |")
            else:
                avg_l = float(sub["loss_dollar"].mean())
                tot_l = float(sub["loss_dollar"].sum())
                share = tot_l / total_loss if total_loss > 0 else 0
                log.info(f"| {cls} | {len(sub)} | {avg_l:.3f} | {tot_l:.3f} | {share:.1%} |")

    # ── TABLE 2 — Confident directional calls (per-bar) ──
    log.info("")
    log.info("=" * 70)
    log.info("TABLE 2 — CONFIDENT DIRECTIONAL CALLS (top-prob ≥ 0.55, pred ∈ {2U, 2D})")
    log.info("=" * 70)
    if len(conf_rep) > 0:
        log.info("| timestamp ET | prev | P(1) | P(2U) | P(2D) | P(3) | pred | dir_pred | top_p | actual_type | move_$ | move_% | TYPE | DIR |")
        log.info("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for _, r in conf_rep.iterrows():
            tm = "HIT ✓" if r["hit_type"] == 1 else "MISS ✗"
            dm = "HIT ✓" if r["dir_hit"] == 1 else "MISS ✗"
            log.info(f"| {r['ts'].strftime('%a %m-%d %H:%M')} | {r['prev_strat']} "
                     f"| {r['p1']:.2f} | {r['p2u']:.2f} | {r['p2d']:.2f} | {r['p3']:.2f} "
                     f"| {r['predicted']} | {r['dir_pred']} | {r['top_prob']:.2f} "
                     f"| {r['actual']} | {r['move_dollar']:+.3f} | {r['move_pct']:+.3f}% "
                     f"| {tm} | {dm} |")

    # ── TABLE 3 — Every test bar ──
    log.info("")
    log.info("=" * 70)
    log.info("TABLE 3 — EVERY TEST BAR")
    log.info("=" * 70)
    log.info("| timestamp ET | prev | P(1) | P(2U) | P(2D) | P(3) | pred | top_p | actual_type | move_$ | move_% | TYPE | DIR |")
    log.info("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for _, r in rep.iterrows():
        tm = "HIT ✓" if r["hit_type"] == 1 else "MISS ✗"
        if r["predicted"] in ("2U", "2D"):
            dm = "HIT ✓" if r["dir_hit"] == 1 else "MISS ✗"
        else:
            dm = "—"  # no directional prediction made
        log.info(f"| {r['ts'].strftime('%a %m-%d %H:%M')} | {r['prev_strat']} "
                 f"| {r['p1']:.2f} | {r['p2u']:.2f} | {r['p2d']:.2f} | {r['p3']:.2f} "
                 f"| {r['predicted']} | {r['top_prob']:.2f} "
                 f"| {r['actual']} | {r['move_dollar']:+.3f} | {r['move_pct']:+.3f}% "
                 f"| {tm} | {dm} |")

    # ── BOTTOM LINE ──
    log.info("")
    log.info("=" * 70)
    log.info("BOTTOM LINE")
    log.info("=" * 70)
    if n_conf > 0:
        dir_acc = float(dir_hit[conf_dir_mask].mean())
        type_acc_conf = float(hit_type[conf_dir_mask].mean())
        log.info(f"1. TYPE accuracy (confident subset) = {type_acc_conf:.3f}  vs  "
                 f"DIRECTION accuracy = {dir_acc:.3f}  →  delta {(dir_acc-type_acc_conf)*100:+.1f}pp")
        if len(fav_dollar) and len(adv_dollar):
            ratio = fav_dollar.mean() / adv_dollar.mean()
            comp = "BIGGER" if ratio > 1.0 else "SMALLER"
            log.info(f"2. Avg winning move ({fav_dollar.mean():.3f}) is {comp} than avg losing move "
                     f"({adv_dollar.mean():.3f}); ratio = {ratio:.3f}")
        if all(dir_rates[t] is not None for t in (0.50, 0.55, 0.60)):
            log.info(f"3. DIRECTION confidence-discrimination: "
                     f"@0.50={dir_rates[0.50]:.3f}  @0.55={dir_rates[0.55]:.3f}  @0.60={dir_rates[0.60]:.3f}")
            log.info(f"   → {disc_dir}")

    log.info("=" * 70)
    log.info("REPORT COMPLETE")
    log.info("=" * 70)


if __name__ == "__main__":
    main()
