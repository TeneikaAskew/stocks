"""Intraday order-flow features — microstructure signed-volume imbalance (OFI).

The "rethink" §E5 tested DAILY EOD dealer options positioning and found it null
for intraday direction. This module tests the OTHER flow class the microstructure
literature points to: INTRADAY order-flow imbalance computed from the 1-minute
bars WITHIN each 15-minute strat bar. Where the EOD dealer-greek features are
slow (d-1, daily) and were stale against a 15m bar, OFI is contemporaneous —
it measures who is hitting the bid vs the ask DURING the current bar, which is a
genuinely different (sub-bar) information class than the 15m OHLCV the baseline
already has.

TEMPORAL ALIGNMENT / LEAK SAFETY (critical — see DIRECTION_RESEARCH_RESULTS.md
on the earlier +47pp leak):
  * `strat_features_15m.ts` is the UTC bar-OPEN timestamp (first RTH bar of a
    day = 14:30:00+00 = 09:30 ET). The 15m bar at ts=T aggregates the 1-min
    bars in [T, T+15m).
  * OFI for bucket T is computed from exactly those 1-min bars and is fully
    realized at the bar CLOSE (T+15m) — the same instant the baseline RSI/etc.
    for that bar are known. The triple-barrier label looks at bars AFTER the
    current one. So the current bar's OFI predicting the next bar's direction
    is leak-safe with NO shift (UNLIKE the d-1 daily flow block).
  * The tick-rule sign uses lag(close) over the CONTINUOUS 1-min series
    (extended hours included) so the 09:30 bar's first minute is signed against
    09:29 pre-market, not against the prior day's close across the overnight gap.

NO SILENT FALLBACKS (CLAUDE.md §3.7):
  * `volume` and `signed_vol` are financial fields — a bar with zero total
    volume yields NaN OFI, never 0 (0 imbalance ≠ "no data"). Ratios whose
    denominator is 0/NaN propagate NaN. DB errors are NOT swallowed.

CAPACITY (CLAUDE.md Rule 0):
  * The OFI aggregation (signed Σ over 1-min bars) is LINEAR, so it is pushed
    fully into Postgres — one GROUP BY returns ~26 RTH rows/day, not the ~625
    1-min rows/day. The expensive scan of `market_data_intraday` runs ONLY in
    the build-intraday-flow backfill/incremental Job; experiments read the
    materialized `intraday_flow_15m` table.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Derived OFI feature columns attached to the bar dataset. Deliberately MINIMAL
# (3 columns): the §E5 flow result showed that piling on correlated flow
# features lets the model overfit them in-sample and DILUTE a real edge. Each
# column here is a distinct, motivated microstructure quantity.
FEATURE_COLS = [
    "ofi_norm",       # this bar's signed-volume imbalance  signed_vol/tot_vol ∈[-1,1]
    "ofi_3bar",       # 3-bar persistence of ofi_norm (within-day)
    "cvd_intraday",   # running within-day cumulative imbalance fraction ∈[-1,1]
]

# Raw per-bucket aggregate columns materialized in intraday_flow_15m.
RAW_COLS = ["signed_vol", "tot_vol", "up_vol", "dn_vol", "n_min"]


# ============================================================================
# (a) PURE COMPUTE HELPER — numpy+pandas only, hermetically testable.
# ============================================================================

def compute_derived(buckets: pd.DataFrame) -> pd.DataFrame:
    """PURE: given the raw per-15m-bucket aggregates, return the derived OFI
    feature frame indexed by `ts`.

    `buckets` must have columns: ts (tz-aware UTC), signed_vol, tot_vol, up_vol,
    dn_vol, n_min. Within-day grouping uses the ET calendar date derived from
    ts. Missing / zero-volume denominators yield NaN (never 0), per §3.7.
    """
    if buckets.empty:
        return pd.DataFrame(columns=FEATURE_COLS,
                            index=pd.DatetimeIndex([], name="ts"))
    b = buckets.copy()
    b["ts"] = pd.to_datetime(b["ts"], utc=True)
    b = b.sort_values("ts").reset_index(drop=True)
    # ET calendar date for within-day grouping (matches strat bar_date).
    bar_date = b["ts"].dt.tz_convert("America/New_York").dt.date

    tot = pd.to_numeric(b["tot_vol"], errors="coerce")
    signed = pd.to_numeric(b["signed_vol"], errors="coerce")
    # tot_vol <= 0 (or NaN) -> NaN OFI, never 0. (A real RTH bar always trades;
    # a 0 here means missing/halted data, which must not read as "balanced".)
    denom = tot.where(tot > 0, np.nan)
    ofi_norm = signed / denom

    out = pd.DataFrame({"ts": b["ts"], "ofi_norm": ofi_norm.astype("float64")})
    out["__d"] = bar_date.values

    # 3-bar persistence WITHIN the day (expanding up to 3; min_periods=1 so the
    # first bars of the day carry a value rather than NaN).
    out["ofi_3bar"] = (out.groupby("__d")["ofi_norm"]
                          .transform(lambda s: s.rolling(3, min_periods=1).mean()))

    # Running within-day cumulative imbalance: cumsum(signed)/cumsum(tot).
    cs = signed.groupby(out["__d"]).cumsum()
    ct = denom.groupby(out["__d"]).cumsum()
    out["cvd_intraday"] = (cs / ct.where(ct > 0, np.nan)).astype("float64")

    out = out.set_index("ts")[FEATURE_COLS]
    return out.replace([np.inf, -np.inf], np.nan)


# ============================================================================
# (b) DB-BOUND LOADERS + JOINER. sqlalchemy is LAZY-imported here so the pure
#     helper above imports with numpy+pandas only.
# ============================================================================

def _load_ofi_buckets(engine, ticker: str, since: str, until: str) -> pd.DataFrame:
    """SQL-side OFI aggregation: the linear signed-volume Σ is pushed down to
    Postgres so a year of 1-min bars returns as ~6.5k bucket rows, not ~180k
    1-min rows. The tick-rule sign uses lag(close) over the CONTINUOUS series
    (extended hours), so RTH first-bar signing is correct. DB errors propagate
    (no swallow, §3.7). `since`/`until` are ISO dates (inclusive of `until`).
    """
    from sqlalchemy import text  # lazy — keep the pure helper DB-free
    sql = text(
        """
        WITH base AS (
            SELECT ts, close, volume,
                   sign(close - lag(close) OVER (ORDER BY ts)) AS dir
            FROM market_data_intraday
            WHERE ticker = :tk AND ts >= :s AND ts < :u
        )
        SELECT (date_trunc('hour', ts)
                + floor(extract(minute FROM ts)::int / 15) * interval '15 minutes'
               ) AS ts,
               SUM(dir * volume)                               AS signed_vol,
               SUM(volume)                                     AS tot_vol,
               SUM(CASE WHEN dir > 0 THEN volume ELSE 0 END)   AS up_vol,
               SUM(CASE WHEN dir < 0 THEN volume ELSE 0 END)   AS dn_vol,
               COUNT(*)                                        AS n_min
        FROM base
        GROUP BY 1
        ORDER BY 1
        """
    )
    s_year, u_year = int(since[:4]), int(until[:4])
    # `until` is an inclusive date; the SQL uses ts < :u so push the bound to
    # the next day's midnight to include all of `until`.
    chunks: list[pd.DataFrame] = []
    with engine.connect() as conn:
        for y in range(s_year, u_year + 1):
            y_s = max(since, f"{y}-01-01")
            y_u_date = min(until, f"{y}-12-31")
            y_u = (pd.Timestamp(y_u_date) + pd.Timedelta(days=1)).date().isoformat()
            t0 = pd.Timestamp.utcnow()
            df_y = pd.read_sql(sql, conn, params={"tk": ticker, "s": y_s, "u": y_u})
            log.info("intraday-flow OFI year=%d rows=%d elapsed=%.1fs", y,
                     len(df_y), (pd.Timestamp.utcnow() - t0).total_seconds())
            if not df_y.empty:
                chunks.append(df_y)
    if not chunks:
        return pd.DataFrame(columns=["ts"] + RAW_COLS)
    df = pd.concat(chunks, ignore_index=True)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def compute_intraflow_frame(engine, ticker: str, since: str,
                            until: str) -> pd.DataFrame:
    """Compute the RAW per-15m-bucket OFI aggregates (table schema:
    signed_vol, tot_vol, up_vol, dn_vol, n_min), indexed by ts.

    RULE 0: this scans market_data_intraday and is EXPENSIVE — called ONLY by
    the build-intraday-flow backfill/incremental Job, never per experiment.
    """
    b = _load_ofi_buckets(engine, ticker, since, until)
    if b.empty:
        return pd.DataFrame()
    b = b.set_index("ts").sort_index()
    return b[RAW_COLS]


def _load_intraflow_table(engine, ticker: str, since: str,
                          until: str) -> pd.DataFrame:
    """Read the MATERIALIZED per-bucket aggregates — the per-experiment path.
    NO scan of market_data_intraday. Indexed by ts (tz-aware UTC)."""
    from sqlalchemy import text  # lazy
    sql = text(
        """
        SELECT ts, signed_vol, tot_vol, up_vol, dn_vol, n_min
        FROM intraday_flow_15m
        WHERE ticker = :tk AND ts >= :s AND ts < :u
        ORDER BY ts
        """
    )
    u = (pd.Timestamp(until) + pd.Timedelta(days=1)).date().isoformat()
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"tk": ticker, "s": since, "u": u})
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def add_intraflow_features(df: pd.DataFrame, ticker: str, engine) -> pd.DataFrame:
    """Joiner — reads the MATERIALIZED intraday_flow_15m table (Rule 0: NO
    per-run scan of market_data_intraday), computes the derived OFI features,
    and merges to the bar dataset on the 15m bar `ts`. Contemporaneous (NO
    shift — the current bar's OFI is known at its close; see module docstring).
    Missing → NaN (never 0); float32 attach.
    """
    log.info("intraday-flow: adding to %d-row dataset for %s", len(df), ticker)
    if "ts" not in df.columns:
        raise RuntimeError("intraday-flow joiner requires 'ts' column")

    ts = pd.to_datetime(df["ts"], utc=True)
    since = ts.min().date().isoformat()
    until = ts.max().date().isoformat()

    raw = _load_intraflow_table(engine, ticker, since, until)
    if raw.empty:
        raise RuntimeError(
            f"intraday-flow INFEASIBLE: intraday_flow_15m empty for "
            f"ticker={ticker} in [{since}, {until}]. Run the build-intraday-flow "
            f"Job (--backfill) before using --feature-blocks=intraflow.")

    derived = compute_derived(raw)  # indexed by ts (UTC), columns = FEATURE_COLS

    for col in FEATURE_COLS:
        cov = float(derived[col].notna().mean()) if len(derived) else 0.0
        log.info("intraday-flow feature=%s bucket coverage=%.1f%%", col, cov * 100)

    available = set(derived.index)
    matched = int(ts.isin(available).sum())
    log.info("intraday-flow ts-coverage: %.1f%% (%d/%d bars)",
             (matched / max(1, len(ts))) * 100, matched, len(ts))

    lookup = {t: derived.loc[t].values for t in derived.index}
    nan_row = np.full(len(FEATURE_COLS), np.nan, dtype=np.float64)
    attached = np.array([lookup.get(t, nan_row) for t in ts],
                        dtype=np.float64)
    out = df.reset_index(drop=True).copy()
    for i, c in enumerate(FEATURE_COLS):
        out[c] = attached[:, i].astype(np.float32)
    out = out.replace([np.inf, -np.inf], np.nan)
    log.info("intraday-flow done: added %d feature columns", len(FEATURE_COLS))
    return out
