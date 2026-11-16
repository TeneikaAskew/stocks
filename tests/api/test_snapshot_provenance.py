"""Focused tests for `platform/api/snapshot_provenance.py` (FEAT-OPTION-001,
spec 2026-10-24-feat-option-001-legacy-snapshot-labels, done_when[2]).

The builder validates the WHOLE group of selected rows: every timestamp must
be an aware instant and all must agree in UTC; anything else is
`timestamp_invalid` with no age. A future instant keeps its timestamp and has
no age (`timestamp_future`), never a clamped zero. Statuses are always the
literal "unknown". Hermetic: no database, no network.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "platform") not in sys.path:
    sys.path.insert(0, str(REPO / "platform"))

from api.snapshot_provenance import (  # noqa: E402
    ChainEvidence,
    build_snapshot_provenance,
    with_observation,
)

T0 = datetime(2026, 6, 1, 15, 55, tzinfo=timezone.utc)
OBS = T0 + timedelta(seconds=90)


def _ev(timestamps, sessions=None, provider="alphavantage"):
    sessions = sessions if sessions is not None else ["REALTIME"] * len(timestamps)
    return ChainEvidence(provider=provider, sessions=sessions, timestamps=timestamps)


def test_aware_utc_group_is_valid():
    prov = build_snapshot_provenance(_ev([T0, pd.Timestamp(T0), T0]), OBS)
    assert prov == {
        "provider": "alphavantage",
        "market_session": "REALTIME",
        "snapshot_ts": "2026-06-01T15:55:00+00:00",
        "observed_at": "2026-06-01T15:56:30+00:00",
        "snapshot_age_seconds": 90,
        "freshness_status": "unknown",
        "completeness_status": "unknown",
        "reason": "legacy_snapshot_unqualified",
    }


def test_equal_instants_in_two_zones_are_valid():
    minus_four = timezone(timedelta(hours=-4))
    same_instant = T0.astimezone(minus_four)
    assert same_instant.hour == 11
    prov = build_snapshot_provenance(_ev([T0, same_instant, pd.Timestamp(same_instant)]), OBS)
    assert prov["snapshot_ts"] == "2026-06-01T15:55:00+00:00"
    assert prov["snapshot_age_seconds"] == 90
    assert prov["reason"] == "legacy_snapshot_unqualified"


def test_one_naive_among_aware_is_invalid():
    naive = pd.Timestamp("2026-06-01T15:55:00")
    prov = build_snapshot_provenance(_ev([T0, naive, T0]), OBS)
    assert prov["snapshot_ts"] is None
    assert prov["snapshot_age_seconds"] is None
    assert prov["reason"] == "timestamp_invalid"
    assert prov["observed_at"] == "2026-06-01T15:56:30+00:00"


def test_all_naive_is_invalid():
    naive = pd.Timestamp("2026-06-01T15:55:00")
    prov = build_snapshot_provenance(_ev([naive, naive]), OBS)
    assert (prov["snapshot_ts"], prov["snapshot_age_seconds"], prov["reason"]) == (
        None, None, "timestamp_invalid")


@pytest.mark.parametrize("missing", [None, pd.NaT])
def test_none_or_nat_is_invalid(missing):
    prov = build_snapshot_provenance(_ev([T0, missing]), OBS)
    assert (prov["snapshot_ts"], prov["snapshot_age_seconds"], prov["reason"]) == (
        None, None, "timestamp_invalid")


def test_empty_group_is_invalid_not_aged():
    prov = build_snapshot_provenance(ChainEvidence.empty(), OBS)
    assert prov["provider"] is None
    assert prov["market_session"] is None
    assert (prov["snapshot_ts"], prov["snapshot_age_seconds"], prov["reason"]) == (
        None, None, "timestamp_invalid")


def test_two_distinct_instants_are_invalid():
    prov = build_snapshot_provenance(_ev([T0, T0 + timedelta(seconds=1)]), OBS)
    assert (prov["snapshot_ts"], prov["snapshot_age_seconds"], prov["reason"]) == (
        None, None, "timestamp_invalid")


def test_future_instant_keeps_timestamp_and_null_age():
    future = OBS + timedelta(seconds=1)
    prov = build_snapshot_provenance(_ev([future, future]), OBS)
    assert prov["snapshot_ts"] == future.isoformat()
    assert prov["snapshot_age_seconds"] is None, "a future clock is never clamped to 0"
    assert prov["reason"] == "timestamp_future"


def test_statuses_are_always_unknown():
    for ts in ([T0], [None], [OBS + timedelta(hours=1)]):
        prov = build_snapshot_provenance(_ev(ts), OBS)
        assert prov["freshness_status"] == "unknown"
        assert prov["completeness_status"] == "unknown"


def test_sessions_all_realtime():
    prov = build_snapshot_provenance(_ev([T0, T0], ["REALTIME", "REALTIME"]), OBS)
    assert prov["market_session"] == "REALTIME"


def test_sessions_all_none():
    prov = build_snapshot_provenance(_ev([T0, T0], [None, None]), OBS)
    assert prov["market_session"] is None, "all-NULL legacy rows are not inferred as EOD"


def test_sessions_mixed_is_none():
    prov = build_snapshot_provenance(_ev([T0, T0, T0], ["EOD", None, "EOD"]), OBS)
    assert prov["market_session"] is None
    prov = build_snapshot_provenance(_ev([T0, T0], ["EOD", "REALTIME"]), OBS)
    assert prov["market_session"] is None


def test_from_frame_reads_projected_columns_and_unknown_session_otherwise():
    df = pd.DataFrame({"snapshot_ts": [T0, T0], "market_session": ["EOD", "EOD"]})
    ev = ChainEvidence.from_frame(df, "alphavantage")
    assert ev.sessions == ["EOD", "EOD"] and ev.provider == "alphavantage"
    assert all(t == T0 for t in ev.timestamps)
    df2 = pd.DataFrame({"snapshot_ts": [T0]})
    assert ChainEvidence.from_frame(df2, "alphavantage").sessions == [None]
    assert ChainEvidence.from_frame(pd.DataFrame(), "alphavantage") == ChainEvidence.empty()


def test_with_observation_does_not_mutate_input():
    prov = build_snapshot_provenance(_ev([T0]), OBS)
    frozen = dict(prov)
    later = with_observation(prov, OBS + timedelta(seconds=30))
    assert prov == frozen
    assert later is not prov


def test_with_observation_advances_age_by_clock_delta():
    prov = build_snapshot_provenance(_ev([T0]), OBS)
    later = with_observation(prov, OBS + timedelta(seconds=30))
    assert later["snapshot_age_seconds"] == 120
    assert later["observed_at"] == "2026-06-01T15:57:00+00:00"
    assert later["snapshot_ts"] == prov["snapshot_ts"]
    assert later["reason"] == "legacy_snapshot_unqualified"


def test_with_observation_future_becomes_aged_once_clock_passes():
    future = OBS + timedelta(seconds=600)
    prov = build_snapshot_provenance(_ev([future]), OBS)
    assert prov["reason"] == "timestamp_future" and prov["snapshot_age_seconds"] is None
    later = with_observation(prov, future + timedelta(seconds=5))
    assert later["snapshot_age_seconds"] == 5
    assert later["reason"] == "legacy_snapshot_unqualified"
    assert later["snapshot_ts"] == future.isoformat()


def test_with_observation_invalid_stays_invalid():
    prov = build_snapshot_provenance(_ev([None]), OBS)
    later = with_observation(prov, OBS + timedelta(hours=1))
    assert (later["snapshot_ts"], later["snapshot_age_seconds"], later["reason"]) == (
        None, None, "timestamp_invalid")
    assert later["observed_at"] == (OBS + timedelta(hours=1)).isoformat()
