"""Phase-2 feature families for the DIRECTION and SIZE engines. New columns are
returned NaN-preserving for the engine to concat AFTER featurize (so they never
hit featurize's fillna(0) — CLAUDE.md Rule 3.7). Feature math is reused from
lib/; this module only orchestrates and shapes."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib.features.experimental.options_derived import add_options_features
from gcp.research.strat_engine.strat_dataset import load_labeled_dataset

log = logging.getLogger(__name__)


def prune_feature_cols(feature_cols: list[str], drop_set: set) -> list[str]:
    return [c for c in feature_cols if c not in drop_set]


# FOMC meeting weeks (Mon–Fri containing a scheduled FOMC decision).
# Coverage = 2024-2026 ONLY. The engines train back to ~2015, but we do not
# have a verified FOMC calendar before 2024, so `cal_is_fomc_week` is emitted
# as NaN ("unknown") for any bar dated outside the covered years rather than a
# false 0 (CLAUDE.md Rule 3.7 — honest missing, never a fabricated negative).
# Extend both the table and _FOMC_COVERED_YEARS as new years are verified.
_FOMC_COVERED_YEARS = {2024, 2025, 2026}
_FOMC_WEEKS = {
    # 2024
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    # 2025
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    # 2026
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
}
_FOMC_WEEK_STARTS = {
    (pd.Timestamp(d) - pd.Timedelta(days=pd.Timestamp(d).weekday())).date()
    for d in _FOMC_WEEKS
}


def calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    d = pd.to_datetime(df["bar_date"])
    week_of_month = ((d.dt.day - 1) // 7 + 1).astype(np.float32)
    month_end = d.dt.is_month_end.astype(np.float32)
    quarter_end = (d.dt.is_month_end & d.dt.month.isin([3, 6, 9, 12])
                   ).astype(np.float32)
    week_start = (d - pd.to_timedelta(d.dt.weekday, unit="D")).dt.date
    # 0/1 for years we have a verified FOMC calendar; NaN ("unknown") outside
    # the covered range so a pre-2024 bar is never labeled a false 0.
    covered = d.dt.year.isin(_FOMC_COVERED_YEARS).to_numpy()
    is_fomc_bool = week_start.map(lambda x: x in _FOMC_WEEK_STARTS).to_numpy()
    is_fomc = pd.Series(
        np.where(covered, is_fomc_bool.astype(np.float32), np.nan),
        index=df.index, dtype=np.float32)
    out = pd.DataFrame({
        "cal_dow": d.dt.weekday.astype(np.float32),
        "cal_week_of_month": week_of_month,
        "cal_is_month_end": month_end,
        "cal_is_quarter_end": quarter_end,
        "cal_is_fomc_week": is_fomc,
    }, index=df.index)
    return out


def cross_asset_features(df: pd.DataFrame, peers: dict) -> pd.DataFrame:
    base_ts = pd.to_datetime(df["ts"], utc=True)
    out = pd.DataFrame(index=df.index)
    for pk, pdf in peers.items():
        p = pdf.sort_values("ts").reset_index(drop=True)
        p_ts = pd.to_datetime(p["ts"], utc=True)
        p_ret = p["close"].astype(float) / p["close"].astype(float).shift(1) - 1.0
        # For each base bar, take the peer return of the last peer bar
        # STRICTLY before the base bar's ts (searchsorted 'left' - 1).
        idx = np.searchsorted(p_ts.values, base_ts.values, side="left") - 1
        # clip avoids negative-index wraparound during the lookup; the
        # np.where guard is what actually maps idx == -1 (no prior peer
        # bar) to NaN, overriding whatever the clipped lookup produced.
        vals = np.where(idx >= 0, p_ret.values[np.clip(idx, 0, len(p) - 1)], np.nan)
        out[f"xa_{pk}_ret_1"] = vals.astype(np.float32)
    return out


_FAMILY_COLS = {
    "positioning": ["pcr_volume_d1", "pcr_oi_d1", "iv_skew_25d_d1"],
    # iv_term_slope_d1 excluded — atm_back_iv is NULL upstream (options_derived.py)
    # so the slope is structurally always-NaN.
    "options_iv": ["atm_iv_d1"],
}


def options_features(df: pd.DataFrame, ticker: str, engine,
                     families: set) -> pd.DataFrame:
    joined = add_options_features(df, ticker, engine)
    want = [c for fam in families for c in _FAMILY_COLS[fam]]
    out = pd.DataFrame(index=df.index)
    for c in want:
        # explicit-missing if the joiner didn't produce this column
        out[c] = (joined[c].to_numpy(dtype=np.float32) if c in joined.columns
                  else np.full(len(df), np.nan, dtype=np.float32))
    # Coverage visibility: a 100%-NaN requested column means the joiner
    # produced nothing (e.g. a missing materialized run) — surface it loudly
    # instead of letting it read as a silent all-false-negative downstream.
    n = len(out)
    if n:
        for c in want:
            non_nan = int(out[c].notna().sum())
            if non_nan == 0:
                log.warning("options_features: ticker=%s column=%s is 100%% NaN "
                            "(%d rows) — missing materialized run?", ticker, c, n)
    return out


# All three tickers both engines walk-forward over. Kept local (not
# imported from strat_config/mag_config) so this module has no
# import-time dependency on either engine's config beyond the dataset
# loader itself.
_ALL_TICKERS = ("IWM", "SPY", "QQQ")


def _load_peers(engine, ticker: str, tf: str) -> dict:
    """Load the OTHER two of (IWM, SPY, QQQ) for cross_asset_features,
    returning only `ts`+`close` per peer. Shared by both the DIRECTION
    and SIZE engines via the common base loader (load_labeled_dataset —
    the SIZE engine's load_magnitude_dataset itself wraps this same
    loader for OHLCV), so peer bars are identical regardless of which
    axis is asking. Leak-safe by construction: cross_asset_features
    only reads peer bars strictly before the base bar's ts."""
    peers = {}
    for pk in _ALL_TICKERS:
        if pk == ticker:
            continue
        pdf = load_labeled_dataset(engine, pk, tf, include_next_bar_ohlc=False)
        peers[pk] = pdf[["ts", "close"]]
    return peers


def build_family_columns(df, families, axis, ticker, tf, engine, peers=None):
    """Assemble the additive Phase-2 families into one NaN-preserving frame
    aligned to df's row order. `prune` is NOT handled here — it filters the
    base feature_cols in the engine, before this is called."""
    parts = []
    if {"options_iv", "positioning"} & families:
        parts.append(options_features(
            df, ticker, engine, families & {"options_iv", "positioning"}))
    if "cross_asset" in families:
        parts.append(cross_asset_features(df, peers or {}))
    if "calendar" in families:
        parts.append(calendar_features(df))
    if not parts:
        return pd.DataFrame(index=df.index), []
    new_df = pd.concat([p.reset_index(drop=True) for p in parts], axis=1)
    return new_df, list(new_df.columns)
