"""Pin the #722 tz guard on migrate_to_gcp's trade-time normalization.

The trade parquets store NAIVE ET wall-clock times. The pre-fix code ran
``pd.to_datetime(..., utc=True)``, which relabels a naive series as UTC —
a 4-5h shift. Because the trades upsert conflicts on (ticker, entry_time),
a re-run after the shift lands under a DIFFERENT key and duplicates every
row instead of converging. The guard branches on tz-awareness the same way
the intraday ``ts`` path does.
"""
from __future__ import annotations

import pandas as pd

from gcp.migrate_to_gcp import _trade_times_to_utc


def test_naive_series_is_treated_as_eastern_wall_clock():
    # 2026-07-15 10:05 ET (EDT, UTC-4) → 14:05 UTC
    out = _trade_times_to_utc(pd.Series(["2026-07-15 10:05:00"]))
    assert str(out.dt.tz) == "UTC"
    assert out.iloc[0] == pd.Timestamp("2026-07-15 14:05:00", tz="UTC")


def test_naive_winter_uses_est_offset():
    # 2026-01-15 10:05 ET (EST, UTC-5) → 15:05 UTC
    out = _trade_times_to_utc(pd.Series(["2026-01-15 10:05:00"]))
    assert out.iloc[0] == pd.Timestamp("2026-01-15 15:05:00", tz="UTC")


def test_aware_series_converts_without_relabeling():
    """An already-UTC-aware series must pass through unchanged — the
    pre-fix failure mode was double-conversion on re-run."""
    src = pd.Series([pd.Timestamp("2026-07-15 14:05:00", tz="UTC")])
    out = _trade_times_to_utc(src)
    assert out.iloc[0] == src.iloc[0]


def test_aware_eastern_series_converts_to_utc():
    src = pd.Series([pd.Timestamp("2026-07-15 10:05:00", tz="America/New_York")])
    out = _trade_times_to_utc(src)
    assert out.iloc[0] == pd.Timestamp("2026-07-15 14:05:00", tz="UTC")


def test_idempotent_across_reruns():
    """Round-tripping the guard's own output must be a fixed point —
    this is the convergence property the (ticker, entry_time) upsert
    key depends on."""
    first = _trade_times_to_utc(pd.Series(["2026-07-15 10:05:00"]))
    second = _trade_times_to_utc(first)
    assert (first == second).all()


def test_unparseable_becomes_nat_not_crash():
    out = _trade_times_to_utc(pd.Series(["not-a-time"]))
    assert out.isna().all()
