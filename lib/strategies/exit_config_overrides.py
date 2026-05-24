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

from lib.config import ExitConfig, SignalConfig

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
      * The exit_config_overrides table doesn't exist yet (e.g. PR-E1
        migration hasn't been applied — defends deploy ordering)
      * Engine creation fails (no GCP creds, e.g. unit-test environment
        that mocks `is_cloud_sql_configured` without setting up creds)
      * No row exists for the ticker
      * The latest row is older than _STALE_DAYS

    Any failure path falls back to Tier-B (`ExitConfig` defaults), so
    a missing table or transient DB error degrades gracefully instead
    of crashing every fire_alert. Cached per-process via lru_cache;
    force a refresh with `_latest_overrides.cache_clear()`.
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
               consecutive_periods,
               disabled_conditions, disabled_directions,
               blue_sky_atr_offset, notes
          FROM exit_config_overrides
         WHERE ticker = :ticker
         ORDER BY calibration_date DESC
         LIMIT 1
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


def get_consecutive_periods(ticker: str) -> int:
    """Resolve the per-ticker consecutive-bar-pressure window.

    Tier A: `exit_config_overrides.consecutive_periods` — written by the
    walk-forward calibration sweep. Tier B: the `SignalConfig` default.
    Unlike the target/stop knobs (Tier-B = ExitConfig), this one's
    universal default lives in SignalConfig.
    """
    row = _latest_overrides(ticker)
    if row and _is_usable_int(row.get("consecutive_periods")):
        return int(float(row["consecutive_periods"]))
    return SignalConfig().consecutive_periods


def get_disabled_directions(ticker: str) -> set[str]:
    """Return the set of upper-cased disabled directions for `ticker`.

    Reads `exit_config_overrides.disabled_directions` (JSONB list, e.g.
    `["PUT"]` or `["CALL", "PUT"]`) and normalises to a set of
    upper-case strings. Empty set on miss / NULL / parse failure —
    safe default lets the caller fire normally.

    Mirrors the resolution logic inlined inside
    `lib.signals.evaluate_signal` so any new fire path (#369
    stand-alone momentum) honors the same kill switch as
    mean-reversion. Without this, a `["PUT"]`-disabled side could be
    silently bypassed by the momentum-only path. Per Codex P2 review
    on PR #371.
    """
    row = _latest_overrides(ticker)
    if not row:
        return set()
    dd = row.get("disabled_directions") or []
    if isinstance(dd, str):
        try:
            import json as _json
            dd = _json.loads(dd)
        except Exception:
            return set()
    try:
        return {str(d).upper() for d in dd}
    except Exception:
        return set()


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
    if knob in ("call_time_stop", "put_time_stop", "consecutive_periods"):
        return "A" if _is_usable_int(val) else "B"
    return "A" if _is_usable_number(val) else "B"
