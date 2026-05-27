"""Family 2 — Cross-asset features.

Adds daily cross-asset signals to the labeled strat-engine dataset. The
sandbox `market_data_intraday` is empty for SPY/IWM/QQQ/^VIX in production,
so intraday VIX delta is not feasible — falling back to daily-rolled
features that DO have full coverage 2016-2026.

Per-bar features at bar T (timestamp t, bar_date d = D-of-t):
  - vix_chg_1d        : ^VIX close(d-1) / close(d-2) - 1  (uses d-1, the
                        last fully-closed VIX day before bar t)
  - vix_chg_5d        : ^VIX close(d-1) / close(d-6) - 1
  - vix_level_z_60d   : z-score of ^VIX close(d-1) vs trailing 60-day
                        mean/std (regime locator)
  - vix3m_minus_vix_d1: ^VIX3M(d-1) - ^VIX(d-1)  (contango/backwardation;
                        negative = backwardation = stress)
  - vvix_level_z_60d  : ^VVIX z-score (vol-of-vol regime)
  - iwm_minus_spy_5d  : (IWM(d-1) ret over 5d) - (SPY(d-1) ret over 5d)
                        Small-cap vs large-cap relative strength.
  - iwm_minus_spy_20d : same over 20d.
  - qqq_minus_spy_5d  : tech vs market relative strength (proxy for
                        risk-on rotation that often correlates with IWM).
  - iwm_corr_spy_20d  : 20-day daily-return correlation between IWM and SPY.
                        High = market-driven; low = idiosyncratic.

LEAK SAFETY:
  All cross-asset features use data through D-1 (the prior trading day's
  close), never D itself. The strat dataset's `bar_date` is D; the lookup
  table is keyed on (D-1)'s daily bar, which is fully closed at the start
  of D's session, before any intraday bar t on D can fire.
"""
from __future__ import annotations
import logging

import numpy as np
import pandas as pd
from sqlalchemy import text

log = logging.getLogger(__name__)


def _load_daily(engine, ticker: str, since: str, until: str) -> pd.DataFrame:
    sql = text(
        """
        SELECT date, close
        FROM market_data_daily
        WHERE ticker = :tk AND date >= :s AND date <= :u
        ORDER BY date
        """
    )
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"tk": ticker, "s": since, "u": until})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.set_index("date")
    return df


def add_cross_asset_features(df: pd.DataFrame, ticker: str,
                              engine) -> pd.DataFrame:
    """Family-2 feature joiner."""
    log.info("Family 2 (cross-asset): adding %d-row dataset for %s", len(df), ticker)
    if "bar_date" not in df.columns:
        raise RuntimeError("cross_asset joiner requires 'bar_date' column")

    bar_dates = pd.to_datetime(df["bar_date"]).dt.date
    since = (pd.Timestamp(bar_dates.min()) - pd.Timedelta(days=90)).date().isoformat()
    until = pd.Timestamp(bar_dates.max()).date().isoformat()

    vix = _load_daily(engine, "^VIX", since, until)
    vix3m = _load_daily(engine, "^VIX3M", since, until)
    vvix = _load_daily(engine, "^VVIX", since, until)
    spy = _load_daily(engine, "SPY", since, until)
    iwm = _load_daily(engine, "IWM", since, until)
    qqq = _load_daily(engine, "QQQ", since, until)

    if any(x.empty for x in (vix, spy, iwm, qqq)):
        missing = [n for n, x in zip(("VIX", "SPY", "IWM", "QQQ"),
                                      (vix, spy, iwm, qqq)) if x.empty]
        raise RuntimeError(f"cross-asset family INFEASIBLE: missing daily data for {missing}")

    # Compute daily indicator series, indexed on calendar date.
    def _pct_chg(s: pd.Series, n: int) -> pd.Series:
        return s.pct_change(n)

    def _zscore_60(s: pd.Series) -> pd.Series:
        m = s.rolling(60, min_periods=20).mean()
        sd = s.rolling(60, min_periods=20).std()
        return (s - m) / sd.replace(0, np.nan)

    feats_daily = pd.DataFrame(index=spy.index.union(iwm.index).union(qqq.index)
                                .union(vix.index).union(vix3m.index).union(vvix.index))
    feats_daily.index = pd.to_datetime(feats_daily.index)

    # Reindex each onto the union index, forward-fill ONLY through prior data
    # (no future look). Because all of these are daily closes, the chain just
    # aligns by date; we will shift(1) at the very end so bar_date D reads
    # values from D-1.
    def _align(s: pd.DataFrame, col: str = "close") -> pd.Series:
        idx = pd.to_datetime(s.index)
        return pd.Series(s[col].values, index=idx).reindex(feats_daily.index)

    vix_s = _align(vix)
    vix3m_s = _align(vix3m)
    vvix_s = _align(vvix)
    spy_s = _align(spy)
    iwm_s = _align(iwm)
    qqq_s = _align(qqq)

    feats_daily["vix_chg_1d"] = _pct_chg(vix_s, 1)
    feats_daily["vix_chg_5d"] = _pct_chg(vix_s, 5)
    feats_daily["vix_level_z_60d"] = _zscore_60(vix_s)
    feats_daily["vix3m_minus_vix_d1"] = (vix3m_s - vix_s)
    feats_daily["vvix_level_z_60d"] = _zscore_60(vvix_s)

    spy_ret5 = _pct_chg(spy_s, 5)
    iwm_ret5 = _pct_chg(iwm_s, 5)
    qqq_ret5 = _pct_chg(qqq_s, 5)
    spy_ret20 = _pct_chg(spy_s, 20)
    iwm_ret20 = _pct_chg(iwm_s, 20)

    feats_daily["iwm_minus_spy_5d"] = iwm_ret5 - spy_ret5
    feats_daily["iwm_minus_spy_20d"] = iwm_ret20 - spy_ret20
    feats_daily["qqq_minus_spy_5d"] = qqq_ret5 - spy_ret5

    # 20-day daily-return correlation IWM vs SPY
    spy_ret1 = _pct_chg(spy_s, 1)
    iwm_ret1 = _pct_chg(iwm_s, 1)
    feats_daily["iwm_corr_spy_20d"] = iwm_ret1.rolling(20, min_periods=10).corr(spy_ret1)

    # CRITICAL: shift(1) so bar_date D reads D-1's daily values.
    feats_daily = feats_daily.shift(1)

    # Now broadcast onto df's bars by bar_date.
    feats_daily.index = pd.to_datetime(feats_daily.index).date
    out = df.reset_index(drop=True).copy()
    bar_date_arr = pd.to_datetime(out["bar_date"]).dt.date.values

    feature_cols = list(feats_daily.columns)
    # Build a lookup dict (date -> row) for O(1) per-bar attach
    lookup: dict = {d: feats_daily.loc[d].values for d in feats_daily.index
                    if d in feats_daily.index}
    nan_row = np.full(len(feature_cols), np.nan, dtype=np.float64)
    attached = np.array(
        [lookup.get(d, nan_row) for d in bar_date_arr],
        dtype=np.float64,
    )
    for i, c in enumerate(feature_cols):
        out[c] = attached[:, i].astype(np.float32)
    out = out.replace([np.inf, -np.inf], np.nan)
    log.info("Family 2 done: added %d feature columns", len(feature_cols))
    return out
