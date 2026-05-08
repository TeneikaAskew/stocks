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
    """Fetch the most recent exit_config_overrides row for `ticker`.

    Returns None when:
      * Cloud SQL is not configured
      * No row exists for the ticker
      * The latest row is older than _STALE_DAYS

    Cached per-process via lru_cache. Force a refresh with
    `_latest_overrides.cache_clear()`.
    """
    from gcp.database import get_engine, is_cloud_sql_configured

    if not is_cloud_sql_configured():
        return None

    import pandas as pd
    from sqlalchemy import text

    sql = text(
        """
        SELECT calibration_date, call_target, put_target,
               call_stop, put_stop, call_time_stop, put_time_stop,
               disabled_conditions, notes
          FROM exit_config_overrides
         WHERE ticker = :ticker
         ORDER BY calibration_date DESC
         LIMIT 1
        """
    )
    df = pd.read_sql(sql, get_engine(), params={"ticker": ticker.upper()})
    if df.empty:
        log.info("exit_config_overrides: no row for %s — Tier-B fallback", ticker)
        return None

    row = df.iloc[0].to_dict()
    age_days = (date.today() - row["calibration_date"]).days
    if age_days > _STALE_DAYS:
        log.warning(
            "exit_config_overrides: stale for %s (%dd old) — Tier-B fallback",
            ticker, age_days,
        )
        return None
    return row


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


def get_disabled_conditions(ticker: str) -> list[str]:
    """Return the list of strategy condition names that should be DROPPED
    from MR PUT scoring for `ticker`. Empty list when no override or
    NULL — the strategy's full condition set scores normally.

    Used by `lib/strategies/mean_reversion.py:_apply_disabled_conditions`
    to gate per-ticker drops without changing the inline scoring math.

    The audit (Track A G.P0.13) recommends:
      - IWM: ['stoch_rsi_overbought', 'rsi_overbought_zone']
      - QQQ: ['stoch_rsi_overbought', 'rsi_overbought_zone']
      - SPY: [] (the factor mix was acceptable)

    Stored as JSONB in `exit_config_overrides.disabled_conditions`.
    """
    row = _latest_overrides(ticker)
    if not row:
        return []
    val = row.get("disabled_conditions")
    if val is None:
        return []
    # JSONB can come back as list or str depending on driver — coerce.
    if isinstance(val, str):
        import json
        try:
            val = json.loads(val)
        except (TypeError, ValueError):
            return []
    if not isinstance(val, list):
        return []
    return [str(c) for c in val if isinstance(c, str)]


def get_resolution_tier(ticker: str, knob: str) -> str:
    """Return 'A' or 'B' for audit-trail logging on each fired alert.

    `knob` is one of: 'call_target', 'put_target', 'call_stop',
    'put_stop', 'call_time_stop', 'put_time_stop'. Mirrors the
    convention in calibration.get_resolution_tier.
    """
    row = _latest_overrides(ticker)
    if not row:
        return "B"
    val = row.get(knob)
    if knob in ("call_time_stop", "put_time_stop"):
        return "A" if _is_usable_int(val) else "B"
    return "A" if _is_usable_number(val) else "B"
