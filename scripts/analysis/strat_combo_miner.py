"""Effort B — Strat next-candle combination miner (ticker / TF-parameterised).

Finds the indicator-value COMBINATIONS that best predict, out-of-sample, the
NEXT Strat candle type (1 / 2U / 2D / 3) — the thing the existing strat engine
ranks only one feature at a time (single-feature MI, Stage 3). This is the
combo layer (the sandbox-runnable sibling of strat-engine "Stage 3b").

Reuses the shared math core (`lib.combo_mining`), the production indicator
engine (`add_all_indicators`), the one true Strat classifier
(`lib.strat.StratClassifier`), and the one true label
(`strat_dataset.label_next_bar_type`) — no logic re-implemented (Rule 3.6).

Timeframes: 5m, 15m (resampled from local 1-min) and D (daily, from AV).
1m is allowed for data-gathering but has near-zero predictive value per the
strat engine, so it is not a default.

Usage:
    python -m scripts.analysis.strat_combo_miner --ticker IWM --tf 5m,15m,D
    python -m scripts.analysis.strat_combo_miner --ticker SPY,QQQ
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib import combo_mining as cm  # noqa: E402
from lib.config import IndicatorConfig  # noqa: E402
from lib.indicators import add_all_indicators  # noqa: E402
from lib.strat import StratClassifier  # noqa: E402
from gcp.research.strat_engine.strat_dataset import label_next_bar_type  # noqa: E402
from scripts.analysis.shared_utils import (  # noqa: E402
    load_ticker_1m, resample_to_timeframe, md_header, md_table, save_report,
    timestamp_str, progress,
)

STRAT_CLASSES = ["1", "2U", "2D", "3"]
# TF label → strat_dataset TF key (controls session-aware vs cross-bar shift).
_TF_KEY = {"5m": "5m", "15m": "15m", "30m": "30m", "60m": "60m", "D": "4h"}


def _daily_bars(ticker: str) -> pd.DataFrame:
    """Daily OHLCV from AlphaVantage (HTTPS/443 — sandbox-safe)."""
    import os
    import requests
    key = os.environ.get("AV_KEY") or os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    if not key:
        raise RuntimeError("AV_KEY / ALPHA_VANTAGE_API_KEY not set for daily fetch.")
    r = requests.get("https://www.alphavantage.co/query", params={
        "function": "TIME_SERIES_DAILY", "symbol": ticker, "outputsize": "full",
        "apikey": key, "datatype": "json",
    }, timeout=60)
    r.raise_for_status()
    d = r.json()
    k = next((x for x in d if "Time Series" in x), None)
    if not k:
        raise RuntimeError(f"AV daily: no series for {ticker}: {list(d)[:3]}")
    df = pd.DataFrame.from_dict(d[k], orient="index").astype(float)
    df.index = pd.to_datetime(df.index)
    df = df.rename(columns={"1. open": "Open", "2. high": "High", "3. low": "Low",
                            "4. close": "Close", "5. volume": "Volume"}).sort_index()
    df["Time"] = df.index
    return df[["Open", "High", "Low", "Close", "Volume", "Time"]]


def _bars_for_tf(ticker: str, tf: str, df_1m: pd.DataFrame) -> pd.DataFrame:
    if tf == "D":
        return _daily_bars(ticker)
    bars = resample_to_timeframe(df_1m, tf)
    if "Time" not in bars.columns:
        bars["Time"] = bars.index
    return bars


def run_ticker_tf(ticker: str, tf: str, cfg: IndicatorConfig,
                  df_1m: pd.DataFrame, train_frac: float,
                  min_support: int, top_k: int, max_order: int) -> str:
    bars = _bars_for_tf(ticker, tf, df_1m)
    if bars is None or len(bars) < 500:
        return md_header(f"{ticker} {tf} — insufficient bars", 3) + "\n"

    # Indicators + candidate features (production engine).
    enr = add_all_indicators(bars, close_col="Close", indicator_config=cfg)
    enr = cm.add_candidate_features(enr, cfg)

    # Strat classification (one true classifier) → next_bar_type (one true label).
    enr["strat_candle"] = StratClassifier().classify_series(enr)
    enr["bar_date"] = pd.to_datetime(enr["Time"]).dt.date
    labeled = label_next_bar_type(enr, _TF_KEY[tf], drop_warmup=True)
    if len(labeled) < 400:
        return md_header(f"{ticker} {tf} — too few labeled bars ({len(labeled)})", 3) + "\n"

    feats = cm.stationary_feature_filter(labeled.columns)
    cut = pd.to_datetime(labeled["Time"]).quantile(train_frac)
    train_mask = (pd.to_datetime(labeled["Time"]) <= cut).to_numpy()
    test_mask = ~train_mask
    label = labeled["next_bar_type"]

    lines = [md_header(f"{ticker} — {tf}", 2)]
    days = sorted(set(labeled["bar_date"]))
    lines.append(f"{len(labeled):,} labeled bars over {len(days)} sessions; "
                 f"train {int(train_mask.sum()):,} / test {int(test_mask.sum()):,} "
                 f"(split @ {pd.Timestamp(cut).date()}).")

    # 4-class model lift + permutation importance.
    ml = cm.model_lift(labeled, feats, label, train_mask, test_mask, "next_bar_type")
    mix = ", ".join(f"{k}={v:.3f}" for k, v in ml.class_mix.items())
    lines.append(f"**Model** OOS acc {ml.oos_accuracy:.4f} vs base {ml.base_rate:.4f} "
                 f"(lift {ml.lift:.3f}×). Class mix: {mix}")
    top = list(ml.perm_importance.items())[:8]
    lines.append("Top features: " + ", ".join(f"{f} {v:+.4f}" for f, v in top))
    lines.append("")

    # Interpretable combos per next-candle class (one-vs-rest MI feature ranking).
    for cls in STRAT_CLASSES:
        y_bin = (label == cls).astype(int)
        top_feats = cm.select_top_features(labeled, feats, y_bin, train_mask,
                                           k=10, method="mutual_info")
        combos = cm.mine_combos(labeled, top_feats, label, cls, train_mask, test_mask,
                                max_order=max_order, min_support=min_support, top_k=top_k)
        lines.append(md_header(f"Best combos → next={cls} ({ticker} {tf})", 3))
        if not combos:
            lines.append("_No combos cleared the support floor._\n")
            continue
        rows = [[f"{c.hit_rate:.3f}", f"{c.lift:.2f}", str(c.support),
                 " AND ".join(c.conditions)] for c in combos]
        lines.append(md_table(["hit", "lift", "n", "conditions"], rows))
        lines.append("")
    return "\n".join(lines)


def run_ticker(ticker: str, tfs: List[str], train_frac: float, min_support: int,
               top_k: int, max_order: int) -> str:
    cfg = IndicatorConfig()
    progress(f"loading {ticker} 1-min bars", ticker)
    df_1m = load_ticker_1m(ticker)
    if df_1m is None or df_1m.empty:
        # daily-only fallback still possible
        df_1m = pd.DataFrame()

    head = [md_header(f"Strat next-candle combination predictors — {ticker}", 1), ""]
    head.append(f"_Generated {timestamp_str()}_  ")
    head.append("**Method.** Production indicators + candidate features on each TF; "
                "`StratClassifier` → next_bar_type via the shared session-aware "
                "`label_next_bar_type`; time-split OOS; combos ranked by OOS hit×lift. "
                "Predicts the NEXT Strat candle (1/2U/2D/3), the gap the strat engine's "
                "single-feature MI doesn't fill.")
    head.append("")
    parts = []
    for tf in tfs:
        if tf != "D" and df_1m.empty:
            parts.append(md_header(f"{ticker} — {tf}: no 1-min data", 2))
            continue
        parts.append(run_ticker_tf(ticker, tf, cfg, df_1m, train_frac,
                                    min_support, top_k, max_order))
    return "\n".join(head + parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ticker", default="IWM", help="Comma-separated tickers.")
    ap.add_argument("--tf", default="5m,15m,D", help="Timeframes (5m,15m,30m,60m,D).")
    ap.add_argument("--train-frac", type=float, default=0.70)
    ap.add_argument("--min-support", type=int, default=300)
    ap.add_argument("--top-k", type=int, default=12)
    ap.add_argument("--max-order", type=int, default=3)
    args = ap.parse_args(argv)

    tickers = [t.strip().upper() for t in args.ticker.split(",") if t.strip()]
    tfs = [t.strip() for t in args.tf.split(",") if t.strip()]
    for tk in tickers:
        report = run_ticker(tk, tfs, args.train_frac, args.min_support,
                            args.top_k, args.max_order)
        save_report(report, f"strat_combo_predictors_{tk}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
