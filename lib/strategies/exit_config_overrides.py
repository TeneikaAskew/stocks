"""Per-ticker exit-config overrides reader.

Resolves per-ticker target/stop/time-stop values from the
`exit_config_overrides` Cloud SQL table (seeded by PR-E1, refreshed
quarterly by PR-E7), with fallback to the universal Tier-B defaults in
`lib/config.py:ExitConfig` when overrides are absent, stale, or have
NULL columns.

Resolution chain (highest priority first):
  Tier A  exit_config_overrides.<col> for the latest snapshot per ticker.
  Tier B  ExitConfig defaults from lib/config.py.

This file mirrors `lib/strategies/calibration.py` exactly — same cache
strategy, same NaN-aware fallback. Diverging the patterns would risk a
subtle "Tier-A returned NaN, downstream computed `entry × (1 + NaN) =
NaN`" bug, exactly the failure mode `_is_usable_number` defends.

The audit (Track E, 2026-05-08) found the universal ExitConfig values
(target=0.003 / stop=0.0015) are 1.5–2× too wide for SPY/IWM/QQQ. With
per-ticker targets sized to actual MFE/MAE distributions, QQQ's mean
per-trade return flips from −0.0005% to +0.0127% (counterfactual replay
over 50 days of cached intraday).
"""
from __future__ import annotations

import logging
import math
from datetime import date
from functools import lru_cache
from typing import Optional

from lib.config import ExitConfig

log = logging.getLogger(__name__)

_STALE_DAYS = 180

# Columns whose latest non-NULL value should be merged across recent
# rows (rather than only reading from the absolute-latest row). This
# is the architectural defense against the "new job inserts a fresh
# row with NULLs in the columns IT didn't touch, silently clobbering
# values an earlier job calibrated" bug — when blue-sky-offset job
# refreshes monthly and PR-E7 (target/stop refresher) runs quarterly
# on different dates, neither should be able to NULL out the other's
# work just by writing a newer row.
#
# `notes` and `calibration_date` come from the absolute-latest row
# (audit-trail semantics — they describe THE most recent action, not
# accumulated state). Everything else uses latest-non-NULL-per-column.
_TIER_A_VALUE_COLUMNS = (
    "call_target", "put_target",
    "call_stop", "put_stop",
    "call_time_stop", "put_time_stop",
    "disabled_conditions", "blue_sky_atr_offset",
)


def _is_usable_number(v) -> bool:
    """True iff `v` is a non-None, non-NaN finite number.

    pd.read_sql materializes SQL NULL as NaN for DOUBLE PRECISION
    columns. A bare `is not None` would let NaN through and the
    downstream `entry × (1 + target)` becomes NaN, silently corrupting
    every alert for that ticker. Mirror calibration.py's defense.
    """
    if v is None:
        return False
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f)


def _is_usable_int(v) -> bool:
    """For INTEGER columns (call_time_stop / put_time_stop): None or
    NaN both invalid; positive int required."""
    if v is None:
        return False
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f) and f > 0


@lru_cache(maxsize=64)
def _latest_overrides(ticker: str) -> Optional[dict]:
    """Resolve per-column latest non-NULL Tier-A overrides for `ticker`.

    Fetches all `exit_config_overrides` rows for the ticker within the
    `_STALE_DAYS` window, then merges per-column: each column gets the
    value from the most recent row where that column is non-NULL (and
    non-NaN, since pandas materializes SQL NULL as NaN for DOUBLE
    PRECISION columns).

    This defends against multiple calibration jobs running on different
    cadences — e.g. blue-sky-offset (monthly) and the future PR-E7
    target/stop refresher (quarterly) — where each job inserts a row
    populating only its own columns. Without per-column merging, the
    newer row's NULLs would silently mask the older row's calibrated
    values for unrelated columns.

    `notes` and `calibration_date` describe the most recent action, so
    they always come from the absolute-latest row.

    Returns None when:
      * Cloud SQL is not configured
      * `exit_config_overrides` table doesn't exist (deploy-order defense)
      * Engine creation fails (no GCP creds, unit-test env)
      * No rows exist for the ticker within the staleness window

    Cached per-process via lru_cache; force a refresh with
    `_latest_overrides.cache_clear()`.
    """
    try:
        from gcp.database import get_engine, is_cloud_sql_configured
    except ImportError:
        return None

    if not is_cloud_sql_configured():
        return None

    import pandas as pd
    from sqlalchemy import text

    sql = text(
        """
        SELECT calibration_date, call_target, put_target,
               call_stop, put_stop, call_time_stop, put_time_stop,
               disabled_conditions, blue_sky_atr_offset, notes
          FROM exit_config_overrides
         WHERE ticker = :ticker
         ORDER BY calibration_date DESC
        """
    )
    try:
        df = pd.read_sql(sql, get_engine(), params={"ticker": ticker.upper()})
    except Exception as e:
        # Table missing (UndefinedTable), no creds, network blip, etc.
        # All resolve to Tier-B; log once per process per ticker so the
        # operator notices but the live monitor keeps firing.
        log.warning(
            "exit_config_overrides: query failed for %s (%s) — Tier-B fallback",
            ticker, type(e).__name__,
        )
        return None
    if df.empty:
        log.info("exit_config_overrides: no row for %s — Tier-B fallback", ticker)
        return None

    # Filter out stale rows. With multiple calibration jobs writing on
    # different cadences, even a fresh row can sit alongside older ones;
    # we want only rows updated within the last _STALE_DAYS to count.
    today = date.today()
    df["_age_days"] = df["calibration_date"].apply(
        lambda d: (today - d).days
    )
    df = df[df["_age_days"] <= _STALE_DAYS]
    if df.empty:
        latest_age = (today - df.iloc[0]["calibration_date"]).days if len(df) else None
        log.warning(
            "exit_config_overrides: all rows stale for %s (latest %s) — Tier-B fallback",
            ticker, f"{latest_age}d" if latest_age is not None else "n/a",
        )
        return None

    # `notes` and `calibration_date` describe the latest action.
    latest_row = df.iloc[0]
    merged: dict = {
        "calibration_date": latest_row["calibration_date"],
        "notes": latest_row.get("notes"),
    }
    # Per-column latest non-NULL across the staleness window. Rows are
    # already DESC by calibration_date so the first non-NaN we see is
    # the most recent calibrated value.
    for col in _TIER_A_VALUE_COLUMNS:
        if col not in df.columns:
            merged[col] = None
            continue
        series = df[col]
        # `disabled_conditions` is JSONB — pandas materializes as object
        # and pd.notna on a list raises ValueError. Guard with isinstance.
        if col == "disabled_conditions":
            non_null = [v for v in series if v is not None and v is not pd.NA]
            merged[col] = non_null[0] if non_null else None
        else:
            non_null = series.dropna()
            merged[col] = non_null.iloc[0] if not non_null.empty else None

    return merged


# Single instance of the Tier-B defaults (cheap; ExitConfig is a small
# dataclass). Constructed lazily so import-time order doesn't matter.
def _defaults() -> ExitConfig:
    return ExitConfig()


def get_call_target(ticker: str) -> float:
    """Resolve the CALL target return for `ticker`. Tier A → Tier B fallback."""
    row = _latest_overrides(ticker)
    if row and _is_usable_number(row.get("call_target")):
        return float(row["call_target"])
    return _defaults().call_target


def get_put_target(ticker: str) -> float:
    row = _latest_overrides(ticker)
    if row and _is_usable_number(row.get("put_target")):
        return float(row["put_target"])
    return _defaults().put_target


def get_call_stop(ticker: str) -> float:
    row = _latest_overrides(ticker)
    if row and _is_usable_number(row.get("call_stop")):
        return float(row["call_stop"])
    return _defaults().call_stop


def get_put_stop(ticker: str) -> float:
    row = _latest_overrides(ticker)
    if row and _is_usable_number(row.get("put_stop")):
        return float(row["put_stop"])
    return _defaults().put_stop


def get_call_time_stop(ticker: str) -> int:
    row = _latest_overrides(ticker)
    if row and _is_usable_int(row.get("call_time_stop")):
        return int(float(row["call_time_stop"]))
    return _defaults().call_time_stop


def get_put_time_stop(ticker: str) -> int:
    row = _latest_overrides(ticker)
    if row and _is_usable_int(row.get("put_time_stop")):
        return int(float(row["put_time_stop"]))
    return _defaults().put_time_stop


def get_blue_sky_atr_offset(ticker: str) -> Optional[float]:
    """Resolve the per-ticker blue-sky synthetic-trigger ATR offset.

    Used by ``lib/agents/trade_planner.select_trigger_and_regime`` when
    every historical level has been cleared by pre-market and a synthetic
    trigger is projected past pre_high/pre_low. Returns ``None`` when no
    per-ticker calibration exists — caller falls back to the global
    default ``_BLUE_SKY_ATR_OFFSET``.

    Audit 2026-05-08 G.P1.4 follow-up: SPY/IWM seeded at 0.15, QQQ at 0.20.
    """
    row = _latest_overrides(ticker)
    if row and _is_usable_number(row.get("blue_sky_atr_offset")):
        return float(row["blue_sky_atr_offset"])
    return None


def get_resolution_tier(ticker: str, knob: str) -> str:
    """Return 'A' or 'B' for audit-trail logging on each fired alert.

    `knob` is one of: 'call_target', 'put_target', 'call_stop',
    'put_stop', 'call_time_stop', 'put_time_stop', 'blue_sky_atr_offset'.
    Mirrors the convention in calibration.get_resolution_tier.
    """
    row = _latest_overrides(ticker)
    if not row:
        return "B"
    val = row.get(knob)
    if knob in ("call_time_stop", "put_time_stop"):
        return "A" if _is_usable_int(val) else "B"
    return "A" if _is_usable_number(val) else "B"
