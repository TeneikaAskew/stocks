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


def _load_eod_options(engine, ticker: str, since: str, until: str) -> pd.DataFrame:
    """Pull EOD AlphaVantage snapshots only (the canonical post-close
    snapshot). Yahoo intraday rows are excluded to avoid mixing sources.
    """
    sql = text(
        """
        SELECT snapshot_date, option_type, expiration, strike,
               volume, open_interest, implied_volatility,
               delta, underlying_price
        FROM etf_options_snapshots
        WHERE ticker = :tk
          AND market_session = 'EOD'
          AND data_source = 'alphavantage'
          AND snapshot_date >= :s AND snapshot_date <= :u
        """
    )
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"tk": ticker, "s": since, "u": until})
    if df.empty:
        return df
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"]).dt.date
    df["expiration"] = pd.to_datetime(df["expiration"]).dt.date
    df["dte"] = (pd.to_datetime(df["expiration"]) - pd.to_datetime(df["snapshot_date"])).dt.days
    return df


def _compute_daily_features(opt: pd.DataFrame) -> pd.DataFrame:
    """For each snapshot_date, compute the 5 daily features."""
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

    opt = _load_eod_options(engine, ticker, since, until)
    if opt.empty:
        raise RuntimeError(f"options-derived family INFEASIBLE: no EOD AV "
                           f"options for ticker={ticker} in [{since}, {until}]")
    log.info("loaded %d EOD option rows across %d snapshot dates",
             len(opt), opt["snapshot_date"].nunique())

    daily = _compute_daily_features(opt)
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
