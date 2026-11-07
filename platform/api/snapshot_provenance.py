"""Snapshot provenance for stored options chains (FEAT-OPTION-001, spec
docs/superpowers/specs/2026-10-24-feat-option-001-legacy-snapshot-labels.md).

Three clock rules, applied by every route that serves a stored chain:

1. The stored clock is retained. ``snapshot_ts`` is the selected rows' own
   ``snapshot_ts`` instant, re-emitted as aware UTC ISO-8601; it is never
   replaced by a request-time stamp.
2. ``observed_at`` is the moment this response was assembled. On a cache hit
   it is re-stamped from a copy of the cached provenance (``with_observation``),
   never by writing into the cached payload.
3. ``snapshot_age_seconds`` is a display age (observed_at minus snapshot_ts,
   floored). It says how old the stored snapshot is as of this response; it
   is not a provider lag, a freshness grade or a completeness check.

``freshness_status`` and ``completeness_status`` are always the literal
``"unknown"``: this module classifies nothing. ``reason`` describes the clock
validation only (``legacy_snapshot_unqualified``, ``timestamp_invalid``,
``timestamp_future``), never a qualification result. The source-journal A6
evaluator remains the sole current-source evaluator.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

PROVIDER_ALPHAVANTAGE = "alphavantage"

REASON_LEGACY = "legacy_snapshot_unqualified"
REASON_INVALID = "timestamp_invalid"
REASON_FUTURE = "timestamp_future"


def _now_utc() -> datetime:
    """The only observation clock the routers call; tests monkeypatch this name."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ChainEvidence:
    """The selected rows' own ``market_session`` and ``snapshot_ts`` values,
    untouched, plus the provider identity proven by the query's WHERE clause."""

    provider: Optional[str]
    sessions: list
    timestamps: list

    @classmethod
    def empty(cls) -> "ChainEvidence":
        return cls(provider=None, sessions=[], timestamps=[])

    @classmethod
    def from_frame(cls, df: pd.DataFrame, provider: Optional[str]) -> "ChainEvidence":
        """Evidence from a selected frame. ``market_session`` is read only when
        the statement projected it; otherwise every session is ``None``
        (unknown), never inferred from a label."""
        if df is None or df.empty:
            return cls.empty()
        sessions = (df["market_session"].tolist() if "market_session" in df.columns
                    else [None] * len(df))
        timestamps = df["snapshot_ts"].tolist() if "snapshot_ts" in df.columns else [None] * len(df)
        return cls(provider=provider, sessions=sessions, timestamps=timestamps)


def _as_aware_utc(value: Any) -> Optional[datetime]:
    """An aware instant as UTC ``datetime``; ``None`` for anything else
    (missing, NaT, naive, not a datetime)."""
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        if value.tzinfo is None:
            return None
        return value.tz_convert("UTC").to_pydatetime()
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return None
        return value.astimezone(timezone.utc)
    return None


def _single_instant(timestamps: list) -> Optional[datetime]:
    """The one aware instant every timestamp resolves to, or ``None`` when the
    group is empty, has any missing/naive/NaT member, or spans two instants."""
    if not timestamps:
        return None
    instants: set[datetime] = set()
    for raw in timestamps:
        inst = _as_aware_utc(raw)
        if inst is None:
            return None
        instants.add(inst)
    if len(instants) != 1:
        return None
    return next(iter(instants))


def _single_session(sessions: list) -> Optional[str]:
    """The single distinct non-null session when every row agrees; otherwise
    ``None`` (all-NULL legacy rows stay ``None``; mixed values are ``None``)."""
    if not sessions:
        return None
    distinct = set()
    for s in sessions:
        if s is None or (isinstance(s, float) and pd.isna(s)):
            return None
        distinct.add(str(s))
    if len(distinct) != 1:
        return None
    return next(iter(distinct))


def _iso_utc(instant: datetime) -> str:
    return instant.astimezone(timezone.utc).isoformat()


def _age_fields(instant: Optional[datetime], observed_at: datetime) -> tuple[Optional[int], str]:
    """``(snapshot_age_seconds, reason)`` for a validated instant (or ``None``)."""
    if instant is None:
        return None, REASON_INVALID
    observed_utc = observed_at.astimezone(timezone.utc)
    if instant > observed_utc:
        return None, REASON_FUTURE
    return int((observed_utc - instant).total_seconds()), REASON_LEGACY


def build_snapshot_provenance(evidence: ChainEvidence, observed_at: datetime) -> dict:
    """Validate the whole group of selected rows and describe it.

    Every timestamp must be an aware instant and all must be the same instant
    in UTC; otherwise ``snapshot_ts`` and the age are ``None`` with reason
    ``timestamp_invalid`` (missing, naive, NaT, mixed and inconsistent groups
    alike). A valid instant later than ``observed_at`` keeps its timestamp,
    has no age, and reason ``timestamp_future``; it is never clamped to zero.
    """
    instant = _single_instant(evidence.timestamps)
    age, reason = _age_fields(instant, observed_at)
    return {
        "provider": evidence.provider,
        "market_session": _single_session(evidence.sessions),
        "snapshot_ts": _iso_utc(instant) if instant is not None else None,
        "observed_at": _iso_utc(observed_at),
        "snapshot_age_seconds": age,
        "freshness_status": "unknown",
        "completeness_status": "unknown",
        "reason": reason,
    }


def with_observation(prov: dict, observed_at: datetime) -> dict:
    """A new provenance dict for a later observation of the same stored snapshot.

    Re-stamps ``observed_at`` and recomputes the age from the stored
    ``snapshot_ts`` (re-parsed). A ``timestamp_future`` entry becomes a finite
    age once the clock passes it; ``timestamp_invalid`` stays invalid. The
    argument is never written to.
    """
    stored = prov.get("snapshot_ts")
    instant = _as_aware_utc(datetime.fromisoformat(stored)) if isinstance(stored, str) else None
    if instant is None:
        age, reason = None, REASON_INVALID
    else:
        age, reason = _age_fields(instant, observed_at)
    return {
        **prov,
        "snapshot_ts": _iso_utc(instant) if instant is not None else None,
        "observed_at": _iso_utc(observed_at),
        "snapshot_age_seconds": age,
        "reason": reason,
    }
