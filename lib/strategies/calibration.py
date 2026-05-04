"""Tier-A per-ticker calibration reader.

Resolves per-ticker RSI ranges from the `ticker_calibration` Cloud SQL
table (written quarterly by `scripts/calibrate_thresholds.py`), with
fallback to the universal Tier-B constants in `lib.strategies.config`
when calibration is absent, stale, or has NULL percentile columns.

Resolution chain (highest priority first):
  Tier A  ticker_calibration.rsi_p10..p90 — per-ticker, 60-day rolling.
          PUT  range = (rsi_p50, rsi_p90)
          CALL range = (rsi_p10, rsi_p50)
  Tier B  PUT_RSI_RANGE / CALL_RSI_RANGE constants in
          lib/strategies/config.py.

Cache: functools.lru_cache(maxsize=64) per-process. Cloud Run Jobs are
short-lived so the cache lifetime is bounded by process lifetime — well
below the quarterly calibration cadence. No TTL needed.

Cold start: a ticker without a calibration row gets Tier-B (universal).
That is the design — Tier-B is the production-tested default; per-ticker
just makes the fire-rate comparable across tickers when calibration is
available.
"""
from __future__ import annotations

import logging
from datetime import date
from functools import lru_cache
from typing import Optional, Tuple

from .config import CALL_RSI_RANGE, PUT_RSI_RANGE

log = logging.getLogger(__name__)

_STALE_DAYS = 180


@lru_cache(maxsize=64)
def _latest_calibration(ticker: str) -> Optional[dict]:
    """Fetch the most recent ticker_calibration row for `ticker`.

    Returns None when:
      * Cloud SQL is not configured (CI / unit tests)
      * No row exists for the ticker
      * The latest row is older than _STALE_DAYS

    Cached per-process via lru_cache. To force a refresh (e.g. after a
    fresh calibration run within the same process), call
    `_latest_calibration.cache_clear()`.
    """
    from gcp.database import get_engine, is_cloud_sql_configured

    if not is_cloud_sql_configured():
        return None

    import pandas as pd
    from sqlalchemy import text

    sql = text(
        """
        SELECT calibration_date, rsi_p10, rsi_p25, rsi_p50, rsi_p75, rsi_p90,
               lookback_days, n_bars_used
          FROM ticker_calibration
         WHERE ticker = :ticker
         ORDER BY calibration_date DESC
         LIMIT 1
        """
    )
    df = pd.read_sql(sql, get_engine(), params={"ticker": ticker.upper()})
    if df.empty:
        log.info("ticker_calibration: no row for %s — Tier-B fallback", ticker)
        return None

    row = df.iloc[0].to_dict()
    age_days = (date.today() - row["calibration_date"]).days
    if age_days > _STALE_DAYS:
        log.warning(
            "ticker_calibration: stale for %s (%dd old) — Tier-B fallback",
            ticker, age_days,
        )
        return None
    return row


def get_put_rsi_range(ticker: str) -> Tuple[float, float]:
    """Resolve the PUT RSI range for `ticker`. Tier A → Tier B fallback."""
    row = _latest_calibration(ticker)
    if row and row.get("rsi_p50") is not None and row.get("rsi_p90") is not None:
        rng = (float(row["rsi_p50"]), float(row["rsi_p90"]))
        log.debug(
            "PUT_RSI_RANGE Tier-A for %s: %s (cal=%s)",
            ticker, rng, row["calibration_date"],
        )
        return rng
    return PUT_RSI_RANGE


def get_call_rsi_range(ticker: str) -> Tuple[float, float]:
    """Resolve the CALL RSI range for `ticker`. Tier A → Tier B fallback."""
    row = _latest_calibration(ticker)
    if row and row.get("rsi_p10") is not None and row.get("rsi_p50") is not None:
        rng = (float(row["rsi_p10"]), float(row["rsi_p50"]))
        log.debug(
            "CALL_RSI_RANGE Tier-A for %s: %s (cal=%s)",
            ticker, rng, row["calibration_date"],
        )
        return rng
    return CALL_RSI_RANGE


def get_resolution_tier(ticker: str, side: str) -> str:
    """Return 'A' or 'B' indicating which tier resolved the range.

    Used by signal_monitor for audit-trail logging — every fire records
    where its threshold came from. `side` is 'PUT' or 'CALL'.
    """
    row = _latest_calibration(ticker)
    if not row:
        return "B"
    if side == "PUT":
        return "A" if (row.get("rsi_p50") is not None and row.get("rsi_p90") is not None) else "B"
    return "A" if (row.get("rsi_p10") is not None and row.get("rsi_p50") is not None) else "B"
