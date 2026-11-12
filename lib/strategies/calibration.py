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
import math
from datetime import date
from functools import lru_cache
from typing import Optional, Tuple

from .config import CALL_RSI_RANGE, PUT_RSI_RANGE

log = logging.getLogger(__name__)

_STALE_DAYS = 180


def _is_usable_number(v) -> bool:
    """True iff `v` is a non-None, non-NaN finite number.

    pd.read_sql materializes SQL NULL as NaN for numeric columns
    (DOUBLE PRECISION rsi_p10..p90), not as Python None. A pure
    `is not None` check would let NaN through and we'd return a
    (nan, nan) Tier-A range — causing the RSI gate `low < rsi < high`
    to silently always be False for that ticker (NaN comparisons
    return False). We must also reject NaN/inf to fall back to Tier-B.
    """
    if v is None:
        return False
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f)


@lru_cache(maxsize=64)
def _latest_calibration(ticker: str, as_of: Optional[date] = None) -> Optional[dict]:
    """Fetch the most recent ticker_calibration row for `ticker`.

    With `as_of` (the premarket brief, live or replayed), only rows dated on
    or before `as_of` are read and staleness is measured from `as_of`, so a
    replay uses the row that was in force on its session (REQ-DATA-002).
    Without it (the signal monitor), the latest row and `date.today()`.

    Returns None when:
      * Cloud SQL is not configured (CI / unit tests)
      * No row exists for the ticker (on or before `as_of`)
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

    # #250 drift_flagged: when the calibrate-thresholds writer detected
    # >2σ drift from the rolling 4-row mean for any percentile column,
    # it sets drift_flagged=TRUE on that row. Resolver falls back to
    # Tier-B for flagged rows so a single anomalous calibration window
    # doesn't whipsaw production thresholds. The COALESCE handles the
    # pre-#250 deploy window where the column doesn't exist yet — those
    # rows behave as drift_flagged=FALSE (the original behavior).
    params = {"ticker": ticker.upper()}
    as_of_filter = ""
    if as_of is not None:
        as_of_filter = "\n           AND calibration_date <= :as_of"
        params["as_of"] = as_of
    sql = text(
        """
        SELECT calibration_date, rsi_p10, rsi_p25, rsi_p50, rsi_p75, rsi_p90,
               lookback_days, n_bars_used,
               COALESCE(drift_flagged, FALSE) AS drift_flagged
          FROM ticker_calibration
         WHERE ticker = :ticker{as_of_filter}
         ORDER BY calibration_date DESC
         LIMIT 1
        """.format(as_of_filter=as_of_filter)
    )
    try:
        df = pd.read_sql(sql, get_engine(), params=params)
    except Exception as e:
        # COALESCE on missing column → UndefinedColumn. Pre-#250 fallback:
        # query without the column so this resolver works on instances
        # that haven't run the schema migration yet. Behaviour is
        # equivalent to drift_flagged=FALSE on every row.
        log.debug("ticker_calibration drift_flagged column missing — "
                  "falling back to pre-#250 query: %s", e)
        sql_legacy = text(
            """
            SELECT calibration_date, rsi_p10, rsi_p25, rsi_p50, rsi_p75, rsi_p90,
                   lookback_days, n_bars_used
              FROM ticker_calibration
             WHERE ticker = :ticker{as_of_filter}
             ORDER BY calibration_date DESC
             LIMIT 1
            """.format(as_of_filter=as_of_filter)
        )
        df = pd.read_sql(sql_legacy, get_engine(), params=params)
    if df.empty:
        log.info("ticker_calibration: no row for %s — Tier-B fallback", ticker)
        return None

    row = df.iloc[0].to_dict()
    age_days = ((as_of or date.today()) - row["calibration_date"]).days
    if age_days > _STALE_DAYS:
        log.warning(
            "ticker_calibration: stale for %s (%dd old) — Tier-B fallback",
            ticker, age_days,
        )
        return None
    if bool(row.get("drift_flagged", False)):
        log.warning(
            "ticker_calibration: drift_flagged=TRUE for %s (calibration "
            "%s) — Tier-B fallback. Re-run calibrate-thresholds with "
            "--force after manual verification to clear the flag.",
            ticker, row["calibration_date"],
        )
        return None
    return row


def get_put_rsi_range(ticker: str, as_of: Optional[date] = None) -> Tuple[float, float]:
    """Resolve the PUT RSI range for `ticker`. Tier A → Tier B fallback."""
    row = _latest_calibration(ticker, as_of)
    if row and _is_usable_number(row.get("rsi_p50")) and _is_usable_number(row.get("rsi_p90")):
        rng = (float(row["rsi_p50"]), float(row["rsi_p90"]))
        log.debug(
            "PUT_RSI_RANGE Tier-A for %s: %s (cal=%s)",
            ticker, rng, row["calibration_date"],
        )
        return rng
    return PUT_RSI_RANGE


def get_call_rsi_range(ticker: str, as_of: Optional[date] = None) -> Tuple[float, float]:
    """Resolve the CALL RSI range for `ticker`. Tier A → Tier B fallback."""
    row = _latest_calibration(ticker, as_of)
    if row and _is_usable_number(row.get("rsi_p10")) and _is_usable_number(row.get("rsi_p50")):
        rng = (float(row["rsi_p10"]), float(row["rsi_p50"]))
        log.debug(
            "CALL_RSI_RANGE Tier-A for %s: %s (cal=%s)",
            ticker, rng, row["calibration_date"],
        )
        return rng
    return CALL_RSI_RANGE


def get_resolution_tier(ticker: str, side: str, as_of: Optional[date] = None) -> str:
    """Return 'A' or 'B' indicating which tier resolved the range.

    Used by signal_monitor for audit-trail logging — every fire records
    where its threshold came from. `side` is 'PUT' or 'CALL'.
    """
    row = _latest_calibration(ticker, as_of)
    if not row:
        return "B"
    if side == "PUT":
        return "A" if (_is_usable_number(row.get("rsi_p50")) and _is_usable_number(row.get("rsi_p90"))) else "B"
    return "A" if (_is_usable_number(row.get("rsi_p10")) and _is_usable_number(row.get("rsi_p50"))) else "B"


def resolve_rsi_bands(ticker: str, as_of: Optional[date] = None) -> dict:
    """Both RSI bands for `ticker` from one calibration read, with their
    provenance: ``call`` (p10, p50) and ``put`` (p50, p90) under Tier A, each
    side falling back to its Tier-B constant on its own; ``call_tier`` and
    ``put_tier`` ('A' or 'B'); ``calibration_date`` of the row used, or None
    when neither side is Tier A. The premarket brief calls it with
    ``as_of=analysis_date`` (FEAT-SIGNAL-001, 2026-11-11 spec).
    """
    row = _latest_calibration(ticker, as_of)
    p10, p50, p90 = ((row.get("rsi_p10"), row.get("rsi_p50"), row.get("rsi_p90"))
                     if row else (None, None, None))
    call_a = _is_usable_number(p10) and _is_usable_number(p50)
    put_a = _is_usable_number(p50) and _is_usable_number(p90)
    return {
        "call": (float(p10), float(p50)) if call_a else CALL_RSI_RANGE,
        "put": (float(p50), float(p90)) if put_a else PUT_RSI_RANGE,
        "call_tier": "A" if call_a else "B",
        "put_tier": "A" if put_a else "B",
        "calibration_date": row["calibration_date"] if (call_a or put_a) else None,
    }
