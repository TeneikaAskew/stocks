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
from sqlalchemy.exc import ProgrammingError, OperationalError

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

# Phase-1 volatility-expansion features, mapped to the spine columns that
# lib.indicators.add_all_indicators now produces and strat_data_builder
# persists. The magnitude engine consumes these instead of recomputing them.
_PHASE1_SPINE_COLUMNS = (
    "atr_expansion",            # ATR5/ATR20 (Wilder) — single-source ratio
    "bb20_bandwidth",
    "realized_vol_z",
    "range_expansion_ratio",
    "intraday_range_vs_prevday",
)


def _require_phase1_spine_features(df: pd.DataFrame) -> None:
    """Assert the Phase-1 volatility features are present from the spine.

    They are computed in lib.indicators.add_all_indicators (the _add_magnitude
    block + ATR_Expansion) and persisted in strat_features_<tf>, so they arrive
    with the base frame. If they're absent the strat_features rebuild that
    persists them has not run — fail loud rather than silently re-deriving
    (CLAUDE.md Rule 3.7 / no-workarounds).
    """
    missing = [c for c in _PHASE1_SPINE_COLUMNS if c not in df.columns]
    if missing:
        raise RuntimeError(
            f"Phase-1 spine features missing from strat_features: {missing}. "
            "Re-run strat_data_builder --rebuild so add_all_indicators' "
            "magnitude block is persisted. Do NOT recompute these inline.")


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


# ─────────────────────── Phase-calendar features (no DB lookup, ts-only) ────────────

def _add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Calendar-replacement test (Phase 3b) features.

    Per reviewer 2026-05-28: if Phase 3's QQQ 5m + SPY 5m gate-passing
    REPLICATES with calendar features only (no event_proximity), the
    answer is 'calendar proxy' and we know what the Phase 3 features
    were actually encoding. If those cells fail with calendar-only,
    the Phase 3 features encode something more specific.

    Features (all derivable from `ts` alone; no DB lookup):
      - hour_of_day, minute_of_hour
      - day_of_week (0=Mon..4=Fri; non-RTH weekends are pre-filtered upstream)
      - week_of_month (1..5)
      - is_first_friday — NFP day proxy (binary)
      - is_fomc_week — rough proxy: 3rd or 4th week of month (binary)
      - is_month_end — last 2 trading days of month (binary)
      - is_quarter_end — last 3 trading days of quarter (binary)

    These are GLOBALLY observable at bar t — no future data.
    """
    df = df.copy()
    ts_et = pd.to_datetime(df["ts"], utc=True).dt.tz_convert("America/New_York")

    df["cal_hour_of_day"] = ts_et.dt.hour
    df["cal_minute_of_hour"] = ts_et.dt.minute
    df["cal_day_of_week"] = ts_et.dt.dayofweek
    # week_of_month: 1..5, where week 1 = day 1-7
    df["cal_week_of_month"] = ((ts_et.dt.day - 1) // 7) + 1

    # First Friday of the month — NFP traditionally released here
    is_friday = ts_et.dt.dayofweek == 4
    is_first_week = ts_et.dt.day <= 7
    df["cal_is_first_friday"] = (is_friday & is_first_week).astype(int)

    # FOMC-week proxy. FOMC meetings happen ~every 6 weeks, typically
    # Tuesday-Wednesday. Without a calendar lookup the cheapest proxy
    # is "is this week 3 or 4 of the month" — captures ~half the actual
    # FOMC weeks. Imperfect; meant as a calendar-feature, not as a
    # claim about FOMC dates.
    df["cal_is_fomc_week"] = df["cal_week_of_month"].isin([3, 4]).astype(int)

    # Month-end and quarter-end approximations. We don't have the trading
    # calendar to identify "last N trading days" precisely without
    # joining a calendar table; the cheap proxy is "last 3 calendar days
    # of the month" / "last 5 calendar days of {Mar, Jun, Sep, Dec}".
    days_in_month = ts_et.dt.daysinmonth
    df["cal_is_month_end"] = (ts_et.dt.day >= (days_in_month - 2)).astype(int)
    is_quarter_month = ts_et.dt.month.isin([3, 6, 9, 12])
    df["cal_is_quarter_end"] = (is_quarter_month & (ts_et.dt.day >= (days_in_month - 4))).astype(int)

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
    except (ProgrammingError, OperationalError) as e:
        # Backfill not yet run — table doesn't exist OR can't be reached.
        # ProgrammingError catches "relation does not exist" (table not
        # yet created); OperationalError catches connection / permission
        # issues. We DO NOT catch bare Exception because any other failure
        # (e.g. an invalid feature column name) is a real bug we want loud.
        # Per Rule 3.7: this is an explicit failure (table doesn't exist
        # → schema not yet deployed), reported with structured log and a
        # column indicating the data was unavailable. The model will see
        # NaN for the entire phase, so Phase 2/4 results will be
        # uninformative until backfill lands — which is reported in the
        # results doc as PENDING_BACKFILL, not a "0" passing the gate.
        log.warning("phase feature join skipped for %s (%s: %s) — filling NaN",
                    table, type(e).__name__, str(e).split('\n')[0][:200])
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

    # Magnitude target = |next_close - next_open| / atr_20. atr_20 now comes
    # from the single indicator spine (lib.indicators.add_all_indicators →
    # strat_features_<tf>.atr_20), populated by the 2026-06-01 rebuild. No local
    # recompute / workaround (CLAUDE.md "one source of truth", no shortcuts).
    if "atr_20" not in df.columns:
        raise RuntimeError(
            "strat_features is missing the atr_20 column — the magnitude target "
            "requires it. Re-run strat_data_builder --rebuild so the spine's "
            "ATR20 is persisted; do NOT substitute a locally-recomputed ATR.")
    atr20 = df["atr_20"]
    if not (atr20.notna() & (atr20 > 0)).any():
        raise RuntimeError(
            "strat_features.atr_20 is entirely NaN/zero — the upstream rebuild "
            "that persists ATR20 from add_all_indicators has not run. Fix the "
            "data (rebuild), do not work around it.")
    move = (df["next_close"] - df["next_open"]).abs()
    df[LABEL_COL] = _bucket_magnitude(move, atr20)
    # Drop rows missing magnitude (no valid ATR or no next-bar OHLC).
    n_before = len(df)
    df = df[df[LABEL_COL].notna()].copy()
    n_after = len(df)
    log.info("magnitude label assigned: %d rows (%d dropped for missing atr/next-bar)",
             n_after, n_before - n_after)

    # Phase-specific feature additions. Phase-1 volatility-expansion features
    # now come from the spine (persisted in strat_features by add_all_indicators)
    # — they are loaded automatically with the base frame, so there is nothing to
    # compute here. Verify they're present rather than silently re-deriving.
    if phase in ("phase1",):
        _require_phase1_spine_features(df)
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
    if phase in ("phase_calendar",):
        df = _add_calendar_features(df)

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
})

_NUMERIC_DTYPES = (np.float64, np.int64, np.int32, np.int8, np.float32, np.int16)


def discover_numeric_features(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns
            if c not in _FEATURE_DROP_COLS and df[c].dtype in _NUMERIC_DTYPES]


def label_to_idx(label_series: pd.Series) -> np.ndarray:
    return label_series.map({c: i for i, c in enumerate(LABEL_CLASSES)}).astype(int).values


def base_rate(label_series: pd.Series) -> pd.Series:
    return label_series.value_counts(normalize=True).reindex(LABEL_CLASSES, fill_value=0.0)
