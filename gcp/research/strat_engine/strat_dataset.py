"""Shared dataset loader for the Strat Directionality Engine.

The PRD's Stage 1 output is "a model-ready table per ticker/TF or a labeled
view over strat_features." We use the view path: no new tables to maintain,
always current, free.

This module is imported by Stage 2 (EDA), Stage 3 (correlation),
Stage 4 (model), Stage 5 (FTFC), Stage 6 (read-out). It is the ONLY place
the label is computed, so all stages see the same target definition.
"""
from __future__ import annotations
import logging
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text

from gcp.research.strat_engine.strat_config import (
    LABEL_CLASSES, LABEL_COL, strat_features_table,
)
from gcp.research.strat_engine.strat_enrich_levels import levels_table

log = logging.getLogger(__name__)


def load_labeled_dataset(engine, ticker: str, tf: str,
                          since: str | None = None,
                          until: str | None = None,
                          drop_warmup: bool = True,
                          include_levels: bool = True) -> pd.DataFrame:
    """Pull strat_features_{tf} for one ticker; add labels + prev2/prev3 lags.

    Returns a DataFrame with:
      - All ~50 indicator columns from strat_features_{tf}
      - `strat_candle`, `prev1_candle` (= prev_strat_candle from source)
      - `prev2_candle`, `prev3_candle` (NEW — shift(2), shift(3))
      - `next_bar_type` (the label — LEAD by 1)
      - All regime columns

    Leakage guardrail: the label is strictly t+1. Features must already be
    known at bar t close — strat_features computed at-close, so this is safe.

    The last bar per (ticker) is dropped (no t+1 to label).
    `drop_warmup=True` also drops bars where prev3_candle is null (the first
    3 bars per ticker).
    """
    where_s = "WHERE s.ticker = :t AND s.strat_candle IS NOT NULL"
    params: dict[str, Any] = {"t": ticker}
    if since:
        where_s += " AND s.bar_date >= :s"
        params["s"] = since
    if until:
        where_s += " AND s.bar_date < :u"
        params["u"] = until

    if include_levels:
        # LEFT JOIN the enrichment table (ORB / historical levels / order
        # blocks). If the enrichment table doesn't exist yet for this TF,
        # fall back to plain strat_features load.
        try:
            sql = text(
                f"SELECT s.*, l.* "
                f"FROM {strat_features_table(tf)} s "
                f"LEFT JOIN {levels_table(tf)} l "
                f"  ON l.ticker = s.ticker AND l.ts = s.ts "
                f"{where_s} ORDER BY s.ts"
            )
            log.info("loading %s LEFT JOIN %s (ticker=%s, since=%s, until=%s)",
                     strat_features_table(tf), levels_table(tf), ticker, since, until)
            with engine.connect() as conn:
                df = pd.read_sql(sql, conn, params=params)
        except Exception as e:
            log.warning("levels join failed (%s); falling back to plain features", type(e).__name__)
            sql = text(f"SELECT * FROM {strat_features_table(tf)} s {where_s} ORDER BY s.ts")
            with engine.connect() as conn:
                df = pd.read_sql(sql, conn, params=params)
    else:
        sql = text(f"SELECT * FROM {strat_features_table(tf)} s {where_s} ORDER BY s.ts")
        log.info("loading %s ONLY (no levels join) (ticker=%s)", strat_features_table(tf), ticker)
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params=params)

    # Deduplicate columns (SELECT s.*, l.* duplicates ticker/ts if not renamed)
    df = df.loc[:, ~df.columns.duplicated()]
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts").reset_index(drop=True)

    # Map source's prev_strat_candle -> prev1_candle (PRD naming)
    df["prev1_candle"] = df.get("prev_strat_candle")

    # NEW lags
    df["prev2_candle"] = df["strat_candle"].shift(2)
    df["prev3_candle"] = df["strat_candle"].shift(3)

    # NEW label: next bar's strat_candle. Strictly t+1.
    df[LABEL_COL] = df["strat_candle"].shift(-1)

    # Drop the final bar (no label) + optionally the 3-bar warmup
    df = df[df[LABEL_COL].notna()].copy()
    if drop_warmup:
        df = df[df["prev3_candle"].notna()].copy()

    # Keep only valid label classes (drops any junk like 'X' that appeared
    # in earlier audit data)
    df = df[df[LABEL_COL].isin(LABEL_CLASSES)].copy()

    log.info("dataset: %d rows after labels + warmup drop", len(df))
    return df.reset_index(drop=True)


def label_to_idx(label_series: pd.Series) -> np.ndarray:
    """Map class strings → class indices in LABEL_CLASSES order."""
    return label_series.map({c: i for i, c in enumerate(LABEL_CLASSES)}).astype(int).values


def base_rate(label_series: pd.Series) -> pd.Series:
    """Class frequencies for the dataset (the benchmark Stage 4 must beat)."""
    return label_series.value_counts(normalize=True).reindex(LABEL_CLASSES, fill_value=0.0)
