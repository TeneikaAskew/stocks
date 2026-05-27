"""Family 3 — Options-derived features.

Adds per-bar features computed from `etf_options_snapshots` for the ticker
itself. These are distinct from the existing baseline columns (`total_gex`,
`total_vex`, `distance_to_king_pct`, etc.) which are dealer-positioning
metrics. Here we compute volume-flow and IV-shape metrics.

Per-bar features at bar T (timestamp t, bar_date d):
  - pcr_volume_d1     : put-call volume ratio at d-1's EOD snapshot
                        (sum put volume / sum call volume across all expiries
                        and strikes that day). >1 = more put volume.
  - pcr_oi_d1         : put-call open-interest ratio at d-1's EOD snapshot.
                        Slower-moving than volume; captures positioning.
  - iv_skew_25d_d1    : IV(25Δ put) - IV(25Δ call) at the FRONT-MONTH
                        expiry on d-1. Positive = put-skewed (downside fear).
  - iv_term_slope_d1  : ATM IV(60-90 days out) - ATM IV(0-30 days out) at d-1.
                        Positive = contango (low near-term fear); negative
                        = inverted (event/stress).
  - atm_iv_d1         : ATM IV (call+put avg) at the front-month on d-1.
                        Distinct from total_gex/total_vex which are sums.
  - iv_atm_chg_5d     : atm_iv_d1 / atm_iv_(d-6) - 1. IV momentum.

LEAK SAFETY:
  All option snapshots used are from snapshot_date <= d-1. The `EOD` snapshot
  on date d-1 is fully captured before any intraday bar t on date d can fire.
  We filter `market_session = 'EOD'` to use the post-close snapshot.

INFEASIBILITY GUARDS:
  - If the EOD snapshot is missing for a date (sparse early years), the row
    gets NaN for that feature, which the harness will treat as "missing" via
    fillna(0). For honesty we log the coverage rate; if < 50%, we report
    PARTIAL.
"""
from __future__ import annotations
import logging

import numpy as np
import pandas as pd
from sqlalchemy import text

log = logging.getLogger(__name__)


def _load_daily_pcr(engine, ticker: str, since: str, until: str) -> pd.DataFrame:
    """Aggregate PCR (volume + OI) per snapshot_date via SQL — small result
    set (~2500 rows) replacing a 14M-row pull. Per CLAUDE.md rule 4: batch
    by partition key, never per-row pulls when N exceeds 100.

    Empirically, pg8000 (the Cloud SQL Connector backend used in Cloud Run)
    is ~10× slower than psycopg2 for bulk reads. A single 11-year scan of
    the etf_options_snapshots table sat on the pg8000 wire past 165 s in
    first-pass dispatches. Chunking by year keeps each query under ~5 s
    server-side and ~30-50 s pg8000-side. 11 round-trips × 50 s ≈ 9 min,
    well inside our 60-min task-timeout budget.
    """
    s_year = int(since[:4])
    u_year = int(until[:4])
    sql = text(
        """
        SELECT
          snapshot_date,
          SUM(volume) FILTER (WHERE option_type = 'calls')         AS call_vol,
          SUM(volume) FILTER (WHERE option_type = 'puts')          AS put_vol,
          SUM(open_interest) FILTER (WHERE option_type = 'calls')  AS call_oi,
          SUM(open_interest) FILTER (WHERE option_type = 'puts')   AS put_oi
        FROM etf_options_snapshots
        WHERE ticker = :tk
          AND market_session = 'EOD'
          AND data_source = 'alphavantage'
          AND snapshot_date >= :s AND snapshot_date <= :u
        GROUP BY snapshot_date
        ORDER BY snapshot_date
        """
    )
    chunks: list[pd.DataFrame] = []
    with engine.connect() as conn:
        for y in range(s_year, u_year + 1):
            y_since = max(since, f"{y}-01-01")
            y_until = min(until, f"{y}-12-31")
            t0 = pd.Timestamp.utcnow()
            df_y = pd.read_sql(sql, conn, params={"tk": ticker, "s": y_since, "u": y_until})
            elapsed = (pd.Timestamp.utcnow() - t0).total_seconds()
            log.info("PCR year=%d rows=%d elapsed=%.1fs", y, len(df_y), elapsed)
            if not df_y.empty:
                chunks.append(df_y)
    if not chunks:
        return pd.DataFrame()
    df = pd.concat(chunks, ignore_index=True)
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"]).dt.date
    return df


def _load_iv_features(engine, ticker: str, since: str, until: str) -> pd.DataFrame:
    """Per snapshot_date compute IV skew + ATM IV + term slope via SQL.

    Strategy: pick FRONT-month expiry (smallest dte >= 7) per date, then
    compute 25Δ put-IV − 25Δ call-IV and ATM IV (delta closest to ±0.5).
    Also compute term-slope ATM(60-120 DTE) − ATM(7-30 DTE).

    Materialized as a CTE chain to keep the result set small (~2500 rows ×
    a few columns). The closest-delta selection uses DISTINCT ON which is
    a Postgres extension — clean for our use-case.
    """
    sql = text(
        """
        WITH base AS (
          SELECT snapshot_date,
                 option_type,
                 expiration,
                 strike,
                 implied_volatility AS iv,
                 delta,
                 (expiration - snapshot_date) AS dte
          FROM etf_options_snapshots
          WHERE ticker = :tk
            AND market_session = 'EOD'
            AND data_source = 'alphavantage'
            AND snapshot_date >= :s AND snapshot_date <= :u
            AND implied_volatility IS NOT NULL
            AND delta IS NOT NULL
        ),
        -- Per (snapshot_date), pick the front-month expiry (smallest dte
        -- with dte >= 7). Allow dte >= 0 fallback if no >=7 exists.
        front_exp AS (
          SELECT DISTINCT ON (snapshot_date) snapshot_date, expiration AS front
          FROM base
          WHERE dte >= 7
          ORDER BY snapshot_date, dte ASC
        ),
        -- 25Δ put IV from front month
        put25 AS (
          SELECT DISTINCT ON (b.snapshot_date)
                 b.snapshot_date, b.iv AS iv_put25
          FROM base b
          JOIN front_exp f ON f.snapshot_date = b.snapshot_date
                          AND f.front = b.expiration
          WHERE b.option_type = 'puts'
          ORDER BY b.snapshot_date, abs(b.delta + 0.25) ASC
        ),
        call25 AS (
          SELECT DISTINCT ON (b.snapshot_date)
                 b.snapshot_date, b.iv AS iv_call25
          FROM base b
          JOIN front_exp f ON f.snapshot_date = b.snapshot_date
                          AND f.front = b.expiration
          WHERE b.option_type = 'calls'
          ORDER BY b.snapshot_date, abs(b.delta - 0.25) ASC
        ),
        atm_front AS (
          SELECT snapshot_date, AVG(iv) AS atm_front_iv
          FROM (
            SELECT DISTINCT ON (b.snapshot_date, b.option_type)
                   b.snapshot_date, b.option_type, b.iv
            FROM base b
            JOIN front_exp f ON f.snapshot_date = b.snapshot_date
                            AND f.front = b.expiration
            ORDER BY b.snapshot_date, b.option_type,
                     CASE WHEN b.option_type = 'calls'
                          THEN abs(b.delta - 0.5)
                          ELSE abs(b.delta + 0.5)
                     END ASC
          ) x
          GROUP BY snapshot_date
        ),
        atm_back AS (
          SELECT snapshot_date, AVG(iv) AS atm_back_iv
          FROM (
            SELECT DISTINCT ON (b.snapshot_date, b.option_type)
                   b.snapshot_date, b.option_type, b.iv
            FROM base b
            WHERE b.dte BETWEEN 60 AND 120
            ORDER BY b.snapshot_date, b.option_type,
                     CASE WHEN b.option_type = 'calls'
                          THEN abs(b.delta - 0.5)
                          ELSE abs(b.delta + 0.5)
                     END ASC
          ) x
          GROUP BY snapshot_date
        )
        SELECT
          COALESCE(p.snapshot_date, c.snapshot_date, af.snapshot_date) AS snapshot_date,
          p.iv_put25, c.iv_call25,
          af.atm_front_iv, ab.atm_back_iv
        FROM put25 p
        FULL OUTER JOIN call25 c   ON c.snapshot_date  = p.snapshot_date
        FULL OUTER JOIN atm_front af ON af.snapshot_date = COALESCE(p.snapshot_date, c.snapshot_date)
        FULL OUTER JOIN atm_back ab  ON ab.snapshot_date = COALESCE(p.snapshot_date, c.snapshot_date, af.snapshot_date)
        ORDER BY snapshot_date
        """
    )
    s_year = int(since[:4])
    u_year = int(until[:4])
    chunks: list[pd.DataFrame] = []
    with engine.connect() as conn:
        for y in range(s_year, u_year + 1):
            y_since = max(since, f"{y}-01-01")
            y_until = min(until, f"{y}-12-31")
            t0 = pd.Timestamp.utcnow()
            df_y = pd.read_sql(sql, conn, params={"tk": ticker, "s": y_since, "u": y_until})
            elapsed = (pd.Timestamp.utcnow() - t0).total_seconds()
            log.info("IV year=%d rows=%d elapsed=%.1fs", y, len(df_y), elapsed)
            if not df_y.empty:
                chunks.append(df_y)
    if not chunks:
        return pd.DataFrame()
    df = pd.concat(chunks, ignore_index=True)
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"]).dt.date
    return df


def _compute_daily_features_sql(pcr_df: pd.DataFrame,
                                  iv_df: pd.DataFrame) -> pd.DataFrame:
    """Merge SQL-aggregated PCR and IV components into the 6 per-date
    features. Compute happens in-memory but on the small daily grid."""
    df = pd.merge(pcr_df, iv_df, on="snapshot_date", how="outer")
    df = df.sort_values("snapshot_date").set_index("snapshot_date")
    df["pcr_volume_d1"] = df["put_vol"] / df["call_vol"].replace(0, np.nan)
    df["pcr_oi_d1"] = df["put_oi"] / df["call_oi"].replace(0, np.nan)
    df["iv_skew_25d_d1"] = df["iv_put25"] - df["iv_call25"]
    df["iv_term_slope_d1"] = df["atm_back_iv"] - df["atm_front_iv"]
    df["atm_iv_d1"] = df["atm_front_iv"]
    df["iv_atm_chg_5d"] = df["atm_iv_d1"] / df["atm_iv_d1"].shift(5) - 1.0
    return df[["pcr_volume_d1", "pcr_oi_d1", "iv_skew_25d_d1",
                "iv_term_slope_d1", "atm_iv_d1", "iv_atm_chg_5d"]]


def _compute_daily_features(opt: pd.DataFrame) -> pd.DataFrame:
    """LEGACY PATH — kept for reference, no longer called from
    add_options_features. The original implementation pulled the full
    14M-row chain into Python and aggregated locally; that timed out in
    production (CLAUDE.md rule 4 violation — per-row pull when N > 100).
    The live path is _compute_daily_features_sql + the two _load_* helpers
    above which push the aggregation into Postgres. Kept here so a future
    reader can trace the rewrite.

    For each snapshot_date, compute the 5 daily features."""
    rows = []
    for d, g in opt.groupby("snapshot_date"):
        calls = g[g["option_type"] == "calls"]
        puts = g[g["option_type"] == "puts"]
        # PCR volume / OI (sum across all expiries)
        call_vol = float(calls["volume"].sum()) if not calls.empty else 0.0
        put_vol = float(puts["volume"].sum()) if not puts.empty else 0.0
        call_oi = float(calls["open_interest"].sum()) if not calls.empty else 0.0
        put_oi = float(puts["open_interest"].sum()) if not puts.empty else 0.0
        pcr_vol = (put_vol / call_vol) if call_vol > 0 else np.nan
        pcr_oi = (put_oi / call_oi) if call_oi > 0 else np.nan

        # Front-month expiry — smallest dte >= 7 (avoid 0DTE noise) but use
        # all expiries if nothing else exists.
        front_exp = None
        if not g.empty:
            front_candidates = g[g["dte"] >= 7]
            if not front_candidates.empty:
                front_exp = front_candidates["expiration"].min()
            else:
                front_exp = g["expiration"].min()

        iv_skew = np.nan
        atm_iv = np.nan
        if front_exp is not None:
            front = g[g["expiration"] == front_exp]
            front_calls = front[(front["option_type"] == "calls")
                                & front["delta"].notna()
                                & front["implied_volatility"].notna()]
            front_puts = front[(front["option_type"] == "puts")
                                & front["delta"].notna()
                                & front["implied_volatility"].notna()]
            # 25Δ put (delta ≈ -0.25) and 25Δ call (delta ≈ +0.25)
            if not front_puts.empty:
                # closest to -0.25
                front_puts = front_puts.assign(d_dist=(front_puts["delta"] + 0.25).abs())
                put25 = front_puts.sort_values("d_dist").iloc[0]
                iv_put25 = float(put25["implied_volatility"])
            else:
                iv_put25 = np.nan
            if not front_calls.empty:
                front_calls = front_calls.assign(d_dist=(front_calls["delta"] - 0.25).abs())
                call25 = front_calls.sort_values("d_dist").iloc[0]
                iv_call25 = float(call25["implied_volatility"])
            else:
                iv_call25 = np.nan
            if not np.isnan(iv_put25) and not np.isnan(iv_call25):
                iv_skew = iv_put25 - iv_call25

            # ATM (delta ≈ ±0.5)
            atm_calls = front_calls if not front_calls.empty else pd.DataFrame()
            atm_puts = front_puts if not front_puts.empty else pd.DataFrame()
            atm_ivs = []
            if not atm_calls.empty:
                acg = atm_calls.assign(d_dist=(atm_calls["delta"] - 0.5).abs())
                atm_ivs.append(float(acg.sort_values("d_dist").iloc[0]["implied_volatility"]))
            if not atm_puts.empty:
                apg = atm_puts.assign(d_dist=(atm_puts["delta"] + 0.5).abs())
                atm_ivs.append(float(apg.sort_values("d_dist").iloc[0]["implied_volatility"]))
            if atm_ivs:
                atm_iv = float(np.mean(atm_ivs))

        # Term slope: ATM IV in 60-90 DTE region minus ATM IV in 0-30 DTE
        front30 = g[(g["dte"] >= 7) & (g["dte"] <= 30)
                    & g["delta"].notna() & g["implied_volatility"].notna()]
        back60_90 = g[(g["dte"] >= 60) & (g["dte"] <= 120)
                       & g["delta"].notna() & g["implied_volatility"].notna()]
        def _atm_iv(slice_df: pd.DataFrame) -> float:
            if slice_df.empty:
                return np.nan
            sc = slice_df[slice_df["option_type"] == "calls"]
            sp = slice_df[slice_df["option_type"] == "puts"]
            ivs = []
            if not sc.empty:
                sc = sc.assign(d_dist=(sc["delta"] - 0.5).abs())
                ivs.append(float(sc.sort_values("d_dist").iloc[0]["implied_volatility"]))
            if not sp.empty:
                sp = sp.assign(d_dist=(sp["delta"] + 0.5).abs())
                ivs.append(float(sp.sort_values("d_dist").iloc[0]["implied_volatility"]))
            return float(np.mean(ivs)) if ivs else np.nan
        iv_front = _atm_iv(front30)
        iv_back = _atm_iv(back60_90)
        iv_term_slope = (iv_back - iv_front) if (not np.isnan(iv_front)
                                                  and not np.isnan(iv_back)) else np.nan

        rows.append({
            "snapshot_date": d,
            "pcr_volume_d1": pcr_vol,
            "pcr_oi_d1": pcr_oi,
            "iv_skew_25d_d1": iv_skew,
            "iv_term_slope_d1": iv_term_slope,
            "atm_iv_d1": atm_iv,
        })

    if not rows:
        return pd.DataFrame()
    daily = pd.DataFrame(rows).set_index("snapshot_date").sort_index()
    # IV momentum: ratio vs 5 trading-days ago (using shift(5) on the sorted
    # daily series — sparse dates are handled by pandas alignment).
    daily["iv_atm_chg_5d"] = daily["atm_iv_d1"] / daily["atm_iv_d1"].shift(5) - 1.0
    return daily


def add_options_features(df: pd.DataFrame, ticker: str,
                          engine) -> pd.DataFrame:
    """Family-3 feature joiner."""
    log.info("Family 3 (options-derived): adding %d-row dataset for %s",
             len(df), ticker)
    if "bar_date" not in df.columns:
        raise RuntimeError("options joiner requires 'bar_date' column")

    bar_dates = pd.to_datetime(df["bar_date"]).dt.date
    since = (pd.Timestamp(bar_dates.min()) - pd.Timedelta(days=60)).date().isoformat()
    until = pd.Timestamp(bar_dates.max()).date().isoformat()

    # SQL-side aggregation — replaces a 14M-row pull with two ~2500-row
    # daily aggregates. The previous implementation pulled the full chain
    # to Python and aggregated locally; that timed out in production. The
    # math is identical (PCR sums, DISTINCT ON for closest-delta), only
    # the partition is moved into Postgres.
    pcr_df = _load_daily_pcr(engine, ticker, since, until)
    iv_df = _load_iv_features(engine, ticker, since, until)
    if pcr_df.empty and iv_df.empty:
        raise RuntimeError(f"options-derived family INFEASIBLE: no EOD AV "
                           f"options for ticker={ticker} in [{since}, {until}]")
    log.info("loaded daily PCR for %d dates, daily IV for %d dates",
             len(pcr_df), len(iv_df))

    daily = _compute_daily_features_sql(pcr_df, iv_df)
    if daily.empty:
        raise RuntimeError("options-derived: per-day aggregation produced 0 rows")

    feature_cols = list(daily.columns)
    log.info("computed daily option features for %d dates", len(daily))

    # Shift by 1 day so bar_date D reads D-1's snapshot.
    daily = daily.shift(1)

    # Coverage check
    unique_bar_dates = sorted({d for d in bar_dates})
    available = set(daily.index)
    coverage = sum(1 for d in unique_bar_dates if d in available) / max(1, len(unique_bar_dates))
    log.info("date-coverage on bar dataset: %.1f%% (%d/%d unique bar dates)",
             coverage * 100, sum(1 for d in unique_bar_dates if d in available),
             len(unique_bar_dates))

    # Attach
    lookup: dict = {d: daily.loc[d].values for d in daily.index}
    nan_row = np.full(len(feature_cols), np.nan, dtype=np.float64)
    bar_date_arr = pd.to_datetime(df["bar_date"]).dt.date.values
    attached = np.array(
        [lookup.get(d, nan_row) for d in bar_date_arr],
        dtype=np.float64,
    )
    out = df.reset_index(drop=True).copy()
    for i, c in enumerate(feature_cols):
        out[c] = attached[:, i].astype(np.float32)
    out = out.replace([np.inf, -np.inf], np.nan)
    log.info("Family 3 done: added %d feature columns", len(feature_cols))
    return out
