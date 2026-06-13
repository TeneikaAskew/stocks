#!/usr/bin/env python3
"""Regime combination miner (Cloud Run Job) — Effort A, scheduled.

Reads 1-minute bars from Cloud SQL ``market_data_intraday``, computes the
production indicator suite + candidate features, and mines the indicator-value
COMBINATIONS that best predict each forward regime (BIG / UP / DOWN / FLAT)
out-of-sample. Persists the ranked combos to ``regime_combo_results`` so the
edge (and its drift over time) is queryable.

Shares ALL math with the sandbox analysis script via ``lib.combo_mining`` and
``scripts.analysis.regime_combo_miner`` — no logic is re-implemented here
(CLAUDE.md Rule 3.6); this job is the scheduled, DB-backed wrapper.

Run modes:
    python -m gcp.regime_combo_job                      # trailing window, today
    python -m gcp.regime_combo_job --as-of 2026-05-08   # historical replay
    python -m gcp.regime_combo_job --tickers IWM,SPY,QQQ --horizons 5,15,30,60 --dry-run

Env overrides: REGIME_COMBO_TICKERS, REGIME_COMBO_HORIZONS,
REGIME_COMBO_LOOKBACK_DAYS, REGIME_COMBO_AS_OF.

Exit 0 = success (incl. clean no-op when a ticker has no data); 1 = unrecoverable
(e.g. ALL tickers empty → likely a connection/staleness problem worth surfacing).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger("regime_combo_job")

from lib.config import IndicatorConfig  # noqa: E402
from lib import combo_mining as cm  # noqa: E402
from gcp.indicator_correlation_job import enrich, _RETURN_PREFIX  # noqa: E402
from scripts.analysis.regime_combo_miner import label_regimes  # noqa: E402

RESULTS_TABLE = "regime_combo_results"
_REGIME_TARGETS = [
    # (target_class, label_kind, ranking_metric_sign)
    ("UP", "direction", "signed"),
    ("DOWN", "direction", "signed"),
    ("FLAT", "direction", "abs_neg"),
    ("BIG", "magnitude", "abs"),
]


def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name, default)
    return v.strip() if isinstance(v, str) else v


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tickers", default=_env("REGIME_COMBO_TICKERS", "SPY,IWM,QQQ"))
    p.add_argument("--horizons", default=_env("REGIME_COMBO_HORIZONS", "5,15,30,60"))
    p.add_argument("--lookback-days", type=int,
                   default=int(_env("REGIME_COMBO_LOOKBACK_DAYS", "365")))
    p.add_argument("--as-of", default=_env("REGIME_COMBO_AS_OF", "") or None)
    p.add_argument("--train-frac", type=float, default=0.70)
    p.add_argument("--min-support", type=int, default=1000)
    p.add_argument("--top-k", type=int, default=12)
    p.add_argument("--max-order", type=int, default=3)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def mine_ticker(ticker: str, raw: pd.DataFrame, horizons: List[int],
                train_frac: float, min_support: int, top_k: int,
                max_order: int) -> List[dict]:
    """Return tidy combo rows for one ticker (all horizons × regimes)."""
    cfg = IndicatorConfig()
    enr = enrich(raw, cfg, horizons)
    enr = cm.add_candidate_features(enr, cfg)
    feats = cm.stationary_feature_filter(enr.columns)

    rows: List[dict] = []
    for h in horizons:
        ret_col = f"{_RETURN_PREFIX}{h}"
        sub = enr.dropna(subset=[ret_col]).copy()
        if len(sub) < 2000:
            logger.warning("[%s] horizon %dm: only %d bars; skipping", ticker, h, len(sub))
            continue
        t = pd.to_datetime(sub["Time"])
        cut = t.quantile(train_frac)
        train_mask = (t <= cut).to_numpy()
        test_mask = ~train_mask
        direction, magnitude, _, _ = label_regimes(sub, ret_col, train_mask)

        for cls, kind, sign in _REGIME_TARGETS:
            lab = direction if kind == "direction" else magnitude
            if sign == "signed":
                metric = sub[ret_col]
            elif sign == "abs":
                metric = sub[ret_col].abs()
            else:  # abs_neg → FLAT prefers small |move|
                metric = -sub[ret_col].abs()
            top_feats = cm.select_top_features(sub, feats, metric, train_mask,
                                               k=10, method="spearman")
            combos = cm.mine_combos(sub, top_feats, lab, cls, train_mask, test_mask,
                                    max_order=max_order, min_support=min_support,
                                    top_k=top_k)
            for c in combos:
                rows.append({
                    "ticker": ticker, "horizon_min": h, "target_class": cls,
                    "conditions": " AND ".join(c.conditions),
                    "combo_order": len(c.conditions),
                    "hit_rate": c.hit_rate, "base_rate": c.base_rate,
                    "lift": c.lift, "support": c.support,
                    "train_support": c.train_support,
                })
    return rows


def run(tickers: List[str], horizons: List[int], lookback_days: int, as_of: date,
        train_frac: float, min_support: int, top_k: int, max_order: int,
        dry_run: bool) -> pd.DataFrame:
    from lib.data_loader import DataLoader

    loader = DataLoader(data_dir=_env("DATA_DIR", "data"))
    start = as_of - timedelta(days=lookback_days)
    start_str, end_str = start.isoformat(), as_of.isoformat()
    logger.info("Window %s → %s | tickers=%s | horizons=%s",
                start_str, end_str, tickers, horizons)

    all_rows: List[dict] = []
    loaded = 0
    for tk in tickers:
        raw = loader.load_intraday(tk, start_date=start_str, end_date=end_str,
                                   on_stale="warn")
        if raw is None or raw.empty:
            logger.warning("No intraday data for %s; skipping.", tk)
            continue
        if "Time" not in raw.columns:
            raw = raw.copy()
            raw["Time"] = pd.to_datetime(raw.index)
        loaded += 1
        rows = mine_ticker(tk, raw, horizons, train_frac, min_support, top_k, max_order)
        logger.info("[%s] %d combo rows", tk, len(rows))
        all_rows.extend(rows)

    if loaded == 0:
        raise RuntimeError(
            f"No intraday data for ANY of {tickers} in {start_str}..{end_str}. "
            "Refusing to write an empty result set."
        )

    results = pd.DataFrame(all_rows)
    if results.empty:
        logger.warning("No combos cleared the support floor for any ticker.")
        return results
    results["computed_date"] = as_of
    results["window_start"] = start
    results["window_end"] = as_of

    # Headline log.
    for tk in results["ticker"].unique():
        big = results[(results.ticker == tk) & (results.target_class == "BIG")]
        if not big.empty:
            top = big.sort_values("lift", ascending=False).iloc[0]
            logger.info("[%s] best BIG combo lift=%.2f×: %s",
                        tk, top["lift"], top["conditions"])

    if dry_run:
        logger.info("(dry-run) skipping write of %d rows to %s", len(results), RESULTS_TABLE)
        return results
    _persist(results)
    return results


def _persist(results: pd.DataFrame) -> int:
    from gcp.database import upsert_dataframe
    conflict = ["computed_date", "window_start", "window_end", "ticker",
                "horizon_min", "target_class", "conditions"]
    n = upsert_dataframe(results, RESULTS_TABLE, conflict_cols=conflict)
    logger.info("Upserted %d rows into %s", n, RESULTS_TABLE)
    return n


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    horizons = sorted({int(h) for h in args.horizons.split(",") if h.strip()})
    as_of = (datetime.strptime(args.as_of, "%Y-%m-%d").date()
             if args.as_of else date.today())
    if not tickers or not horizons:
        logger.error("No tickers/horizons resolved; nothing to do.")
        return 1
    try:
        run(tickers, horizons, args.lookback_days, as_of, args.train_frac,
            args.min_support, args.top_k, args.max_order, args.dry_run)
    except Exception as e:  # noqa: BLE001 — top-level boundary
        logger.error("regime_combo_job failed: %s", e, exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
