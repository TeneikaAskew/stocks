"""Magnitude Engine — dataset loader.

Wraps strat_engine.load_labeled_dataset(include_next_bar_ohlc=True),
replaces the type label with a bucketed magnitude label
|next_close - next_open| / atr_20, and (phase-aware) attaches additional
features that are NOT in the 143-col baseline.

Leakage guardrails:
  - magnitude is computed from next_open + next_close + atr_20-at-t.
    atr_20 is a t-known quantity (computed at-close of bar t in the
    source pipeline). next_open / next_close are session-aware shift(-1)
    of t+1 OHLC and live in the LABEL — they NEVER enter the feature
    matrix. The drop set in featurize() drops them explicitly.
  - Phase-1 vol-family additions use only t-and-earlier OHLCV.
  - Phase-3 event-proximity features compare bar `ts` against
    `economic_events.event_ts`. The "hours until next event" feature
    looks FORWARD in event-time, but events for U.S. data are
    pre-announced on a published calendar — the schedule itself is
    known well in advance, so feature value at bar t is t-known. We
    explicitly guard against using events whose DATA (the value) only
    becomes known at event_ts — we only use the SCHEDULE, not the
    outcome.
"""
from __future__ import annotations
import logging
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text

from gcp.research.magnitude_engine.mag_config import (
    LABEL_COL, LABEL_CLASSES, MAGNITUDE_THRESHOLDS, PHASE_FEATURES,
    NEW_INDICATORS_TABLE, NEW_CROSS_ASSET_TABLE,
)
from gcp.research.strat_engine.strat_dataset import (
    load_labeled_dataset as load_strat_dataset,
)
from gcp.research.strat_engine.strat_config import (
    LABEL_COL as STRAT_LABEL_COL,
)

log = logging.getLogger(__name__)


# ─────────────────────── Target ───────────────────────

def _compute_atr20(df: pd.DataFrame) -> pd.Series:
    """Compute ATR-20 from OHLCV via continuous true-range rolling mean.

    Required because `strat_features_{tf}.atr_20` is stored as NaN across all
    rows (upstream `lib.indicators.add_all_indicators` doesn't compute the
    20-bar variant; the column is silently NaN-filled by `strat_data_builder`).
    Computing locally keeps the magnitude target spec-compliant ("ATR-20
    multiples") rather than substituting atr_14 under a different label.

    Method: simple rolling-20 mean of continuous true range. ATR is
    inherently a multi-session measure — the rolling window crosses
    sessions intentionally so the overnight price gap (close[D-1] →
    open[D]) shows up in true_range at the first bar of the new day.
    That's the textbook definition; session-aware rolling would yield
    zero valid rows on 30m bars (only 13 RTH bars per day < 20-bar window).
    """
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr_components = pd.concat([
        (h - l),
        (h - prev_c).abs(),
        (l - prev_c).abs(),
    ], axis=1)
    true_range = tr_components.max(axis=1, skipna=True)
    return true_range.rolling(20, min_periods=20).mean()


def _bucket_magnitude(move: pd.Series, atr20: pd.Series) -> pd.Series:
    """Bucket |next_close - next_open| by ATR-20 multiple.

    Returns NaN where atr_20 is NaN/0 or move is NaN. Caller drops NaN.
    """
    # Mask invalid ATR (NaN, 0, negative).  Following Rule 3.7 — silent
    # fallback forbidden on financial fields: return NaN, drop later,
    # do NOT fill with a synthetic value.
    valid = atr20.notna() & (atr20 > 0) & move.notna()
    ratio = pd.Series(np.nan, index=move.index)
    ratio.loc[valid] = (move.loc[valid] / atr20.loc[valid]).astype(float)

    # bisect-style bucketing
    t0, t1, t2 = MAGNITUDE_THRESHOLDS
    bucket = pd.Series(pd.NA, index=move.index, dtype="object")
    bucket.loc[valid & (ratio < t0)] = LABEL_CLASSES[0]
    bucket.loc[valid & (ratio >= t0) & (ratio < t1)] = LABEL_CLASSES[1]
    bucket.loc[valid & (ratio >= t1) & (ratio < t2)] = LABEL_CLASSES[2]
    bucket.loc[valid & (ratio >= t2)] = LABEL_CLASSES[3]
    return bucket


# ─────────────────────── Phase-1 features (computed on the fly) ───────────────────────

def _add_phase1_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add Phase-1 volatility-family features. Session-aware within bar_date
    so the rolling windows never cross overnight gaps inside the same bar."""
    df = df.copy()

    # atr5 / atr20 ratio. atr_5 not in source — compute from high-low-close.
    # ATR uses Wilder smoothing in lib/indicators; for research we use
    # simple rolling-mean of true_range over 5 bars — clearly noted as a
    # research approximation, NOT a substitute label that is supposed to
    # mirror an external API.
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.groupby(df["bar_date"]).shift(1)
    tr = pd.concat([
        (h - l),
        (h - prev_c).abs(),
        (l - prev_c).abs(),
    ], axis=1).max(axis=1)
    df["atr_5_simple"] = tr.groupby(df["bar_date"]).rolling(5).mean().reset_index(level=0, drop=True)
    # Use the locally-computed atr_20 (stored atr_20 is NaN in source).
    atr20 = df["atr_20_computed"]
    df["atr5_atr20_ratio"] = np.where(
        atr20.notna() & (atr20 > 0),
        df["atr_5_simple"] / atr20, np.nan,
    )

    # BB20 bandwidth: (bb_upper - bb_lower) / sma. We have bb_upper/lower
    # already; bb_width in strat_features is already (upper-lower)/middle
    # in some places but we recompute clean to avoid version drift:
    # bandwidth = (upper - lower) / close — same denominator everywhere.
    df["bb20_bandwidth"] = np.where(
        df["close"].notna() & (df["close"] != 0),
        (df["bb_upper"] - df["bb_lower"]) / df["close"], np.nan,
    )

    # 15-bar realized volatility z-score. Realized vol = stddev of log returns
    # over 15 bars; z = (current - rolling_mean_60) / rolling_std_60.
    logret = np.log(c / prev_c)
    rv15 = logret.groupby(df["bar_date"]).rolling(15).std().reset_index(level=0, drop=True)
    rv_mu = rv15.groupby(df["bar_date"]).rolling(60).mean().reset_index(level=0, drop=True)
    rv_sd = rv15.groupby(df["bar_date"]).rolling(60).std().reset_index(level=0, drop=True)
    df["realized_vol_z15"] = np.where(
        rv_sd.notna() & (rv_sd > 0),
        (rv15 - rv_mu) / rv_sd, np.nan,
    )

    # range_expansion_ratio = current bar range / avg of prior 5 bars' range
    rng = h - l
    avg_prior5 = rng.groupby(df["bar_date"]).shift(1).groupby(df["bar_date"]).rolling(5).mean().reset_index(level=0, drop=True)
    df["range_expansion_ratio"] = np.where(
        avg_prior5.notna() & (avg_prior5 > 0),
        rng / avg_prior5, np.nan,
    )

    # intraday_range_vs_prior_day: cumulative intraday range / prior day's full range.
    # bar_date groups intraday; prior-day range comes from a per-day max-high - min-low.
    daily_range = (
        df.groupby("bar_date")
          .apply(lambda g: g["high"].max() - g["low"].min())
          .rename("daily_range")
          .reset_index()
    )
    daily_range["prev_daily_range"] = daily_range["daily_range"].shift(1)
    df = df.merge(daily_range[["bar_date", "prev_daily_range"]], on="bar_date", how="left")
    cumrange = (
        df.groupby("bar_date").apply(lambda g: g["high"].cummax() - g["low"].cummin())
          .reset_index(level=0, drop=True)
    )
    df["intraday_range_vs_prior_day"] = np.where(
        df["prev_daily_range"].notna() & (df["prev_daily_range"] > 0),
        cumrange / df["prev_daily_range"], np.nan,
    )

    return df


# ─────────────────────── Phase-3 features (event proximity) ───────────────────────

def _add_phase3_features(df: pd.DataFrame, engine) -> pd.DataFrame:
    """Hours until / since the next / last HIGH-impact economic event.

    Uses ONLY the published schedule (event_ts), not the released VALUE.
    The schedule is announced weeks in advance, so the feature at bar t
    is fully t-known.
    """
    df = df.copy()
    # Pull high-impact events covering the dataset's date range.
    # economic_events schema: event_ts, impact, event_type, ...
    min_ts = df["ts"].min()
    max_ts = df["ts"].max()
    # economic_events schema: event_date + event_time + importance.
    # event_time may be NULL for all-day events — default to 09:00 ET (13:00
    # UTC) for those. ET-vs-UTC: the table stores ET local times in the
    # event_time column for U.S. data. We convert to UTC by adding 4 hours
    # (EDT) / 5 hours (EST). Approximation: 4 hours year-round adds at most
    # 1 hour of error on the "hours_until" feature near DST transitions —
    # acceptable for a research signal at hour resolution.
    # pg8000 misparses `:lo::date` (sees `::date` and confuses cast-op
    # with a second bound param). Use CAST(... AS date) instead, and pass
    # python date objects so no SQL cast is even needed.
    lo_date = pd.to_datetime(min_ts).date() if pd.notna(min_ts) else None
    hi_date = pd.to_datetime(max_ts).date() if pd.notna(max_ts) else None
    with engine.connect() as conn:
        events = pd.read_sql(
            text("""
                SELECT event_date, event_time, importance
                  FROM economic_events
                 WHERE LOWER(importance) = 'high'
                   AND event_date BETWEEN :lo AND :hi
                 ORDER BY event_date, event_time
            """),
            conn,
            params={"lo": lo_date, "hi": hi_date},
        )
    if not events.empty:
        # Build event_ts as UTC = date + COALESCE(time, 09:00 ET) + 4 hours.
        events["event_time"] = events["event_time"].fillna(pd.Timestamp("09:00").time())
        events["event_ts"] = (
            pd.to_datetime(events["event_date"].astype(str) + " "
                            + events["event_time"].astype(str), utc=False)
            + pd.Timedelta(hours=4)
        ).dt.tz_localize("UTC")
    if events.empty:
        log.warning("phase3: no high-impact events in window — features filled NaN")
        df["hours_until_next_hi_event"] = np.nan
        df["hours_since_last_hi_event"] = np.nan
        df["is_event_day_pm4h"] = 0
        return df

    events["event_ts"] = pd.to_datetime(events["event_ts"], utc=True)
    event_ts = events["event_ts"].values.astype("datetime64[ns]")

    # For each bar, find next/prev event by binary search.
    bar_ts = pd.to_datetime(df["ts"], utc=True).values.astype("datetime64[ns]")
    idx_next = np.searchsorted(event_ts, bar_ts, side="right")
    idx_prev = idx_next - 1

    hours_until = np.full(len(df), np.nan)
    hours_since = np.full(len(df), np.nan)
    mask_next = idx_next < len(event_ts)
    mask_prev = idx_prev >= 0
    hours_until[mask_next] = (
        (event_ts[idx_next[mask_next]] - bar_ts[mask_next])
        / np.timedelta64(1, "h")
    )
    hours_since[mask_prev] = (
        (bar_ts[mask_prev] - event_ts[idx_prev[mask_prev]])
        / np.timedelta64(1, "h")
    )
    df["hours_until_next_hi_event"] = hours_until
    df["hours_since_last_hi_event"] = hours_since
    df["is_event_day_pm4h"] = (
        ((hours_until <= 4) | (hours_since <= 4)).astype(int)
    )
    return df


# ─────────────────────── Phase-2 / Phase-4 features (table joins) ───────────────────────

def _add_table_join_features(df: pd.DataFrame, engine, table: str,
                              feature_cols: list[str], ticker: str) -> pd.DataFrame:
    """LEFT JOIN av-indicator / cross-asset table onto intraday bars.

    AV's pre-computed indicators are stored per `interval`:
      - `interval='daily'`  ts is midnight of the bar's DATE
      - `interval='15min'`  ts is the 15-minute bar's open time
    Daily features apply to ALL intraday bars of the same date (broadcast).
    Intraday features need a (ts, interval) join that's a backward-asof if
    the strat TF doesn't align exactly with av's grid.

    Strategy: pull DAILY rows only and broadcast by date. The 15min AV
    history is too shallow (~6 months) for the 2019-2026 walk-forward to
    benefit; daily indicators go back to 2000 so they actually populate
    all 8 folds. If a future iteration wants the 15min features, add an
    explicit merge_asof on (ts, interval='15min') here.
    """
    try:
        col_list = ", ".join(feature_cols)
        with engine.connect() as conn:
            ext = pd.read_sql(
                text(f"""
                    SELECT ts AS av_ts, {col_list}
                      FROM {table}
                     WHERE ticker = :t
                       AND interval = 'daily'
                """),
                conn,
                params={"t": ticker},
            )
        if ext.empty:
            log.warning("%s: empty for ticker=%s — Phase features filled NaN",
                        table, ticker)
            for c in feature_cols:
                df[c] = np.nan
            return df
        ext["av_ts"] = pd.to_datetime(ext["av_ts"], utc=True)
        # Broadcast daily indicators to intraday bars by DATE.
        ext["bar_date"] = ext["av_ts"].dt.date
        # Drop av_ts, keep bar_date as the join key.
        ext = ext.drop(columns=["av_ts"])
        # Deduplicate (one row per ticker-date for daily; should be unique).
        ext = ext.drop_duplicates(subset=["bar_date"], keep="last")
        # df["bar_date"] is a pandas date or datetime; normalize to date.
        if pd.api.types.is_datetime64_any_dtype(df["bar_date"]):
            df["bar_date"] = df["bar_date"].dt.date
        df = df.merge(ext, on="bar_date", how="left")
        log.info("%s: joined %d daily-broadcast rows (%d cols) for ticker=%s — "
                  "covers %d / %d intraday bars",
                 table, len(ext), len(feature_cols), ticker,
                 int(df[feature_cols[0]].notna().sum()) if feature_cols else 0,
                 len(df))
        return df
    except Exception as e:
        # Backfill not yet run — surface clearly, fill NaN, continue.
        # Per Rule 3.7: this IS an explicit failure (table doesn't exist
        # → schema not yet deployed), reported with structured log and a
        # column indicating the data was unavailable. The model will see
        # NaN for the entire phase, so Phase 2/4 results will be
        # uninformative until backfill lands — which is reported in the
        # results doc as PENDING_BACKFILL, not a "0" passing the gate.
        log.warning("phase feature join failed for %s (%s) — filling NaN: %s",
                    table, ticker, type(e).__name__)
        for c in feature_cols:
            df[c] = np.nan
        df[f"{table}__pending_backfill"] = 1  # explicit flag
        return df


# ─────────────────────── Public loader ───────────────────────

def load_magnitude_dataset(engine, ticker: str, tf: str, phase: str,
                            since: str | None = None,
                            until: str | None = None) -> pd.DataFrame:
    """Load the labeled dataset for one (ticker, tf, phase) cell."""
    # Reuse strat_engine's loader with next-bar OHLC so we can compute the
    # magnitude target. The strat_engine label (next_bar_type) is also in
    # the frame; we drop it explicitly via featurize()'s drop set.
    df = load_strat_dataset(
        engine, ticker, tf, since=since, until=until,
        include_levels=True, include_next_bar_ohlc=True,
    )

    # Compute magnitude target. atr_20 is stored as NaN in strat_features
    # (upstream pipeline never computed it) so we recompute locally from
    # OHLCV via session-aware true-range rolling mean.
    df["atr_20_computed"] = _compute_atr20(df)
    move = (df["next_close"] - df["next_open"]).abs()
    df[LABEL_COL] = _bucket_magnitude(move, df["atr_20_computed"])
    # Drop rows missing magnitude (no valid ATR or no next-bar OHLC).
    n_before = len(df)
    df = df[df[LABEL_COL].notna()].copy()
    n_after = len(df)
    log.info("magnitude label assigned: %d rows (%d dropped for missing atr/next-bar)",
             n_after, n_before - n_after)

    # Phase-specific feature additions.
    if phase in ("phase1",):
        df = _add_phase1_features(df)
    if phase in ("phase3",):
        df = _add_phase3_features(df, engine)
    if phase in ("phase2",):
        df = _add_table_join_features(
            df, engine, NEW_INDICATORS_TABLE,
            list(PHASE_FEATURES["phase2"]), ticker,
        )
    if phase in ("phase4",):
        df = _add_table_join_features(
            df, engine, NEW_CROSS_ASSET_TABLE,
            list(PHASE_FEATURES["phase4"]), ticker,
        )

    # Class-balance log
    balance = df[LABEL_COL].value_counts(normalize=True).reindex(LABEL_CLASSES, fill_value=0)
    log.info("class balance — %s", " ".join(
        f"{c}={balance[c]:.3f}" for c in LABEL_CLASSES))

    return df.reset_index(drop=True)


# ─────────────────────── Feature discovery ───────────────────────

# Columns excluded from the numeric feature matrix.  Identity, OHLCV,
# labels (BOTH strat label and magnitude label), forward-looking, etc.
_FEATURE_DROP_COLS = frozenset({
    "ticker", "ts", "tf", "bar_date",
    "open", "high", "low", "close", "volume",
    "fwd_close_5bars", "fwd_close_15bars", "fwd_close_30bars", "fwd_close_60bars",
    "fwd_ret_5bars_bps", "fwd_ret_15bars_bps", "fwd_ret_30bars_bps", "fwd_ret_60bars_bps",
    "computed_at", "trigger_high", "trigger_low",
    "is_continuation", "is_reversal", "is_inside", "strat_setup",
    "prev_strat_candle",
    # Forward-looking — must NEVER enter the feature matrix.
    "next_open", "next_close", "next_high", "next_low",
    # Both labels.
    LABEL_COL,
    STRAT_LABEL_COL,  # = "next_bar_type"
    # Target-construction intermediate.
    "atr_20_computed",
})

_NUMERIC_DTYPES = (np.float64, np.int64, np.int32, np.int8, np.float32, np.int16)


def discover_numeric_features(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns
            if c not in _FEATURE_DROP_COLS and df[c].dtype in _NUMERIC_DTYPES]


def label_to_idx(label_series: pd.Series) -> np.ndarray:
    return label_series.map({c: i for i, c in enumerate(LABEL_CLASSES)}).astype(int).values


def base_rate(label_series: pd.Series) -> pd.Series:
    return label_series.value_counts(normalize=True).reindex(LABEL_CLASSES, fill_value=0.0)
