"""Strat Engine — one-week DIRECTION-target report.

Binary classifier target: did next_close > next_open?
Same features, no calibration. Same train/test split logic as the TYPE
one-week report (production config, leak-free).

Output:
  Setup (leak-free assertion + flat-bar drop count)
  Table 1 — Summary (overall accuracy, base rate, threshold table)
  2x2 confusion matrix (predicted-direction vs actual-direction)
  Magnitude — favorable vs adverse move, top losses, loss by actual_type
  Table 2 — Confident calls (decisive ≥ 0.60)
  Table 3 — Every test bar
  Bottom line

Usage:
  python -m gcp.research.strat_engine.strat_dir_report \\
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
    TICKERS, TIMEFRAMES, LABEL_CLASSES, LABEL_COL, LABEL_TO_IDX,
)
from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
from gcp.research.strat_engine.strat_pred_train import featurize
from gcp.research.strat_engine.strat_dir_walk_forward import make_direction_lgbm
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--test-start", required=True)
    p.add_argument("--test-end", required=True)
    args = p.parse_args()

    log.info("=" * 70)
    log.info("STRAT-DIR REPORT (direction target: next_close > next_open)  %s %s  test=[%s..%s)",
             args.ticker, args.tf, args.test_start, args.test_end)
    log.info("=" * 70)

    engine = get_engine()
    df = load_labeled_dataset(engine, args.ticker, args.tf,
                                include_next_bar_ohlc=True)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date

    test_start = pd.Timestamp(args.test_start).date()
    test_end = pd.Timestamp(args.test_end).date()

    # Drop flat-direction bars (ambiguous label)
    flat_mask = df["next_close"] == df["next_open"]
    n_flat = int(flat_mask.sum())
    if n_flat > 0:
        log.info("dropping %d flat bars (next_close == next_open, ambiguous)", n_flat)
        df = df[~flat_mask].copy()

    train_df = df[df["bar_date"] < test_start].copy()
    test_df = df[(df["bar_date"] >= test_start) & (df["bar_date"] < test_end)].copy()

    log.info("─" * 70)
    log.info("TRAIN / TEST BOUNDARY")
    log.info("  train: %d bars (%s..%s)",
             len(train_df), train_df["bar_date"].min(), train_df["bar_date"].max())
    log.info("  test:  %d bars (%s..%s)",
             len(test_df), test_df["bar_date"].min(), test_df["bar_date"].max())
    if set(train_df["bar_date"].unique()) & set(test_df["bar_date"].unique()):
        raise RuntimeError("LEAK")
    log.info("  overlap: 0 dates (leak-free)")

    if len(test_df) == 0:
        log.error("test empty"); return

    X_train, train_cols = featurize(train_df)
    X_test, test_cols = featurize(test_df)
    all_cols = sorted(set(train_cols) | set(test_cols))
    X_train = X_train.reindex(columns=all_cols, fill_value=0).astype(np.float32)
    X_test = X_test.reindex(columns=all_cols, fill_value=0).astype(np.float32)
    y_train = (train_df["next_close"] > train_df["next_open"]).astype(int).values
    y_test = (test_df["next_close"] > test_df["next_open"]).astype(int).values
    log.info("featurize: train %s, test %s", X_train.shape, X_test.shape)
    log.info("train up-share: %.3f, test up-share: %.3f",
             float(y_train.mean()), float(y_test.mean()))

    log.info("training direction LightGBM (binary, no calibration) ...")
    model = make_direction_lgbm()
    model.fit(X_train.values, y_train)
    log.info("training done.")

    proba = model.predict_proba(X_test.values)
    p_up = proba[:, 1]
    pred = (p_up >= 0.5).astype(int)
    decisiveness = np.maximum(p_up, 1 - p_up)
    hit = (pred == y_test).astype(int)

    # Move details
    next_open = test_df["next_open"].values
    next_close = test_df["next_close"].values
    move_dollar = next_close - next_open
    move_pct = np.where(next_open != 0, move_dollar / next_open * 100, 0)

    rep = pd.DataFrame({
        "ts": test_df["ts"].values,
        "bar_date": test_df["bar_date"].values,
        "open": test_df["open"].values,
        "close": test_df["close"].values,
        "next_open": next_open,
        "next_close": next_close,
        "p_up": p_up,
        "p_down": 1 - p_up,
        "decisiveness": decisiveness,
        "pred_dir": np.where(pred == 1, "up", "down"),
        "actual_dir": np.where(y_test == 1, "up", "down"),
        "actual_type": [LABEL_CLASSES[i] for i in test_df[LABEL_COL].map(LABEL_TO_IDX).values],
        "move_dollar": move_dollar,
        "move_pct": move_pct,
        "hit": hit,
    })
    rep["ts"] = pd.to_datetime(rep["ts"], utc=True).dt.tz_convert("America/New_York")

    n_total = len(rep)
    test_base = float(max(y_test.mean(), 1 - y_test.mean()))
    overall_acc = float(hit.mean())

    # ── TABLE 1 — SUMMARY ──
    log.info("=" * 70)
    log.info("TABLE 1 — SUMMARY")
    log.info("=" * 70)
    log.info("**Direction (all bars, no confidence filter):**")
    log.info("| metric | value |")
    log.info("|---|---|")
    log.info(f"| total test bars | {n_total} |")
    log.info(f"| up-share in test | {float(y_test.mean()):.3f} |")
    log.info(f"| base rate (majority direction) | {test_base:.3f} |")
    log.info(f"| accuracy | {overall_acc:.3f} |")
    log.info(f"| accuracy beat over base | +{(overall_acc - test_base)*100:.1f}pp |")

    # Decisive-call hit rate at multiple thresholds
    log.info("")
    log.info("**Decisive-call hit rate (decisiveness = max(p_up, p_down) ≥ X):**")
    log.info("| decisive ≥ | n calls | hit rate | avg decisiveness |")
    log.info("|---|---|---|---|")
    rates = {}
    for thresh in [0.50, 0.55, 0.60, 0.65, 0.70]:
        m = decisiveness >= thresh
        n = int(m.sum())
        if n == 0:
            log.info(f"| {thresh:.2f} | 0 | — | — |")
            rates[thresh] = None
        else:
            hr = float(hit[m].mean())
            avg_d = float(decisiveness[m].mean())
            rates[thresh] = hr
            log.info(f"| {thresh:.2f} | {n} | {hr:.3f} | {avg_d:.3f} |")

    # Discrimination flag
    if all(rates[t] is not None for t in (0.50, 0.55, 0.60, 0.65, 0.70)):
        delta = rates[0.70] - rates[0.50] if rates[0.70] is not None else 0
        if delta >= 0.03 and rates[0.70] > rates[0.50]:
            disc = f"RISES (Δ={delta:+.3f}, 0.50→0.70) — confidence discriminates"
        elif abs(delta) < 0.03:
            disc = f"FLAT (Δ={delta:+.3f}) — confidence uninformative"
        else:
            disc = f"DECLINES (Δ={delta:+.3f}) — confidence anti-correlates"
        log.info(f"discrimination: {disc}")

    # Actual-type distribution
    log.info("")
    log.info("**Actual next-bar type distribution (informational):**")
    log.info("| type | count | share |")
    log.info("|---|---|---|")
    for cls in LABEL_CLASSES:
        n = int((rep["actual_type"] == cls).sum())
        log.info(f"| {cls} | {n} | {n/n_total:.1%} |")

    # ── 2x2 CONFUSION MATRIX ──
    log.info("")
    log.info("=" * 70)
    log.info("2×2 CONFUSION — pred vs actual direction (all bars)")
    log.info("=" * 70)
    pp_aa = int(((pred == 1) & (y_test == 1)).sum())
    pp_aa_pct = pp_aa / n_total
    pp_an = int(((pred == 1) & (y_test == 0)).sum())
    pp_an_pct = pp_an / n_total
    pn_aa = int(((pred == 0) & (y_test == 1)).sum())
    pn_aa_pct = pn_aa / n_total
    pn_an = int(((pred == 0) & (y_test == 0)).sum())
    pn_an_pct = pn_an / n_total
    log.info("| | actual=UP | actual=DOWN |")
    log.info("|---|---|---|")
    log.info(f"| **pred=UP**   | {pp_aa} ({pp_aa_pct:.1%}) HIT | {pp_an} ({pp_an_pct:.1%}) MISS |")
    log.info(f"| **pred=DOWN** | {pn_aa} ({pn_aa_pct:.1%}) MISS | {pn_an} ({pn_an_pct:.1%}) HIT |")
    # Per-direction accuracy
    n_pred_up = int((pred == 1).sum())
    n_pred_dn = int((pred == 0).sum())
    if n_pred_up > 0:
        log.info(f"precision @ pred=UP:   {pp_aa/n_pred_up:.3f}  (of {n_pred_up} up-calls, {pp_aa} were right)")
    if n_pred_dn > 0:
        log.info(f"precision @ pred=DOWN: {pn_an/n_pred_dn:.3f}  (of {n_pred_dn} down-calls, {pn_an} were right)")

    # ── MAGNITUDE ──
    log.info("")
    log.info("=" * 70)
    log.info("MAGNITUDE — favorable vs adverse move (all bars; signed by direction call)")
    log.info("=" * 70)
    # Signed P&L: if pred=up, P&L = next_close - next_open; if pred=down, P&L = next_open - next_close
    signed_pnl = np.where(pred == 1, move_dollar, -move_dollar)
    fav_mask = signed_pnl > 0
    adv_mask = signed_pnl < 0
    fav_pnl = signed_pnl[fav_mask]
    adv_pnl = signed_pnl[adv_mask]
    log.info("| metric | $ | % |")
    log.info("|---|---|---|")
    if len(fav_pnl):
        fav_pct = (np.where(pred == 1, move_pct, -move_pct))[fav_mask]
        log.info(f"| n favorable (signed P&L > 0) | {len(fav_pnl)} | |")
        log.info(f"| avg favorable | {fav_pnl.mean():+.3f} | {fav_pct.mean():+.3f}% |")
        log.info(f"| median favorable | {np.median(fav_pnl):+.3f} | {np.median(fav_pct):+.3f}% |")
    if len(adv_pnl):
        adv_pct = (np.where(pred == 1, move_pct, -move_pct))[adv_mask]
        log.info(f"| n adverse | {len(adv_pnl)} | |")
        log.info(f"| avg adverse (loss size) | {abs(adv_pnl.mean()):.3f} | {abs(adv_pct.mean()):.3f}% |")
        log.info(f"| median adverse | {abs(np.median(adv_pnl)):.3f} | {abs(np.median(adv_pct)):.3f}% |")

    log.info("")
    log.info("**Naive per-bar P&L (entry next_open, exit next_close, no costs):**")
    log.info(f"- total $/share across all {n_total} bars: {signed_pnl.sum():+.3f}")
    log.info(f"- avg $/share per bar: {signed_pnl.mean():+.4f}")
    if len(adv_pnl):
        exp_ratio = fav_pnl.mean() / abs(adv_pnl.mean())
        log.info(f"- expectancy ratio (avg fav / avg adv): {exp_ratio:.3f}")

    # Top 5 worst losses
    log.info("")
    log.info("**5 largest adverse moves (worst single losses):**")
    rep["signed_pnl"] = signed_pnl
    losers = rep[rep["signed_pnl"] < 0].copy()
    if len(losers) > 0:
        losers = losers.sort_values("signed_pnl").head(5)
        log.info("| timestamp ET | pred | p_up | actual_dir | actual_type | move_$ | signed_pnl |")
        log.info("|---|---|---|---|---|---|---|")
        for _, r in losers.iterrows():
            log.info(f"| {r['ts'].strftime('%a %m-%d %H:%M')} | {r['pred_dir']} "
                     f"| {r['p_up']:.2f} | {r['actual_dir']} | {r['actual_type']} "
                     f"| {r['move_dollar']:+.3f} | {r['signed_pnl']:+.3f} |")

    # Adverse moves by actual_type
    log.info("")
    log.info("**Adverse-move size by actual_type (loss concentration check):**")
    log.info("| actual_type | n losers | avg loss $ | total loss $ | share of total loss |")
    log.info("|---|---|---|---|---|")
    adv_df = rep[rep["signed_pnl"] < 0].copy()
    adv_df["loss_dollar"] = adv_df["signed_pnl"].abs()
    total_loss = float(adv_df["loss_dollar"].sum()) if len(adv_df) else 0
    for cls in LABEL_CLASSES:
        sub = adv_df[adv_df["actual_type"] == cls]
        if len(sub) == 0:
            log.info(f"| {cls} | 0 | — | 0 | 0.0% |")
        else:
            tot_l = float(sub["loss_dollar"].sum())
            share = tot_l / total_loss if total_loss > 0 else 0
            log.info(f"| {cls} | {len(sub)} | {float(sub['loss_dollar'].mean()):.3f} "
                     f"| {tot_l:.3f} | {share:.1%} |")

    # ── TABLE 2 — Decisive calls (≥ 0.60) ──
    log.info("")
    log.info("=" * 70)
    log.info("TABLE 2 — DECISIVE CALLS (decisiveness ≥ 0.60)")
    log.info("=" * 70)
    conf = rep[rep["decisiveness"] >= 0.60].copy()
    if len(conf) > 0:
        log.info("| timestamp ET | p_up | p_down | pred | dec | actual_dir | actual_type | move_$ | move_% | signed_pnl | result |")
        log.info("|---|---|---|---|---|---|---|---|---|---|---|")
        for _, r in conf.iterrows():
            mark = "HIT ✓" if r["hit"] == 1 else "MISS ✗"
            log.info(f"| {r['ts'].strftime('%a %m-%d %H:%M')} | {r['p_up']:.2f} | {r['p_down']:.2f} "
                     f"| {r['pred_dir']} | {r['decisiveness']:.2f} | {r['actual_dir']} | {r['actual_type']} "
                     f"| {r['move_dollar']:+.3f} | {r['move_pct']:+.3f}% "
                     f"| {r['signed_pnl']:+.3f} | {mark} |")
        n_hits = int(conf["hit"].sum())
        log.info("")
        log.info(f"Decisive subset: {len(conf)} calls, {n_hits} hits → {n_hits/len(conf):.3f} hit rate")
        log.info(f"Decisive subset P&L: total {conf['signed_pnl'].sum():+.3f}  avg {conf['signed_pnl'].mean():+.4f}")

    # ── TABLE 3 — every bar ──
    log.info("")
    log.info("=" * 70)
    log.info("TABLE 3 — EVERY TEST BAR")
    log.info("=" * 70)
    log.info("| timestamp ET | p_up | p_down | pred | dec | actual_dir | actual_type | move_$ | signed_pnl | result |")
    log.info("|---|---|---|---|---|---|---|---|---|---|")
    for _, r in rep.iterrows():
        mark = "HIT ✓" if r["hit"] == 1 else "MISS ✗"
        log.info(f"| {r['ts'].strftime('%a %m-%d %H:%M')} | {r['p_up']:.2f} | {r['p_down']:.2f} "
                 f"| {r['pred_dir']} | {r['decisiveness']:.2f} | {r['actual_dir']} | {r['actual_type']} "
                 f"| {r['move_dollar']:+.3f} | {r['signed_pnl']:+.3f} | {mark} |")

    # ── BOTTOM LINE ──
    log.info("")
    log.info("=" * 70)
    log.info("BOTTOM LINE")
    log.info("=" * 70)
    log.info(f"1. Direction accuracy: {overall_acc:.3f}  base rate: {test_base:.3f}  beat: {(overall_acc-test_base)*100:+.1f}pp")
    if len(fav_pnl) and len(adv_pnl):
        ratio = fav_pnl.mean() / abs(adv_pnl.mean())
        log.info(f"2. Avg win {fav_pnl.mean():.3f}  vs  avg loss {abs(adv_pnl.mean()):.3f}  ratio={ratio:.3f}")
        log.info(f"3. Naive P&L: total {signed_pnl.sum():+.3f}  avg/bar {signed_pnl.mean():+.4f}")
    if all(rates[t] is not None for t in (0.50, 0.60, 0.70)):
        log.info(f"4. Confidence discrimination @0.50={rates[0.50]:.3f} @0.60={rates[0.60]:.3f} @0.70={rates[0.70]:.3f}")
    log.info("=" * 70)
    log.info("REPORT COMPLETE")
    log.info("=" * 70)


if __name__ == "__main__":
    main()
