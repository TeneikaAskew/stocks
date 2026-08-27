"""Corrected relative volume against a minute-of-day baseline (audit §16).

The legacy `calculate_rvol` divides a bar by a rolling mean of the SAME
session's recent bars. In the live monitor that window is today-only, so
the opening bar enters its own denominator and depresses every following
bar — 80% of live fires read below 1.0, which a relative measure should
not do. These tests pin the corrected semantics.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from lib.indicators import (
    calculate_rvol,
    calculate_rvol_vs_baseline,
    minute_of_day_volume_baseline,
)


def _times(strs):
    return pd.Series([pd.Timestamp(f'2026-08-27 {s}') for s in strs])


# ── baseline construction ───────────────────────────────────────────

def test_baseline_is_median_per_minute_of_day():
    times = _times(['09:30', '09:31'] * 3)
    times = pd.Series(sorted(times))
    # 09:30 volumes 100/200/900 -> median 200 (a spike must not move it)
    vol = pd.Series([100, 10, 200, 20, 900, 30])
    t = _times(['09:30', '09:31', '09:30', '09:31', '09:30', '09:31'])
    b = minute_of_day_volume_baseline(t, vol)
    assert b[9 * 60 + 30] == 200
    assert b[9 * 60 + 31] == 20


def test_baseline_excludes_the_current_session():
    t = pd.Series([pd.Timestamp('2026-08-25 09:30'),
                   pd.Timestamp('2026-08-26 09:30'),
                   pd.Timestamp('2026-08-27 09:30')])
    vol = pd.Series([100, 200, 999999])
    b = minute_of_day_volume_baseline(t, vol, exclude_date=date(2026, 8, 27))
    assert b[9 * 60 + 30] == 150, "today's own bar must not seed its baseline"


def test_baseline_empty_input_returns_empty_dict():
    b = minute_of_day_volume_baseline(pd.Series([], dtype='datetime64[ns]'),
                                      pd.Series([], dtype=float))
    assert b == {}


# ── the ratio ───────────────────────────────────────────────────────

def test_rvol_vs_baseline_is_volume_over_that_minutes_median():
    t = _times(['09:30', '09:31'])
    vol = pd.Series([400.0, 30.0])
    b = {9 * 60 + 30: 200.0, 9 * 60 + 31: 20.0}
    out = calculate_rvol_vs_baseline(t, vol, b)
    assert out.iloc[0] == 2.0
    assert out.iloc[1] == 1.5


def test_unknown_minute_yields_nan_not_a_fabricated_one():
    # CLAUDE.md §3.7 — a missing baseline must be distinguishable from a
    # real ratio, never silently 1.0.
    t = _times(['09:30', '15:59'])
    out = calculate_rvol_vs_baseline(t, pd.Series([100.0, 100.0]),
                                     {9 * 60 + 30: 50.0})
    assert out.iloc[0] == 2.0
    assert np.isnan(out.iloc[1])


def test_zero_baseline_yields_nan_not_inf():
    out = calculate_rvol_vs_baseline(_times(['09:30']), pd.Series([100.0]),
                                     {9 * 60 + 30: 0.0})
    assert np.isnan(out.iloc[0])


# ── the defect the correction addresses ─────────────────────────────

def test_opening_bar_poisons_the_legacy_same_session_rvol():
    """Reproduces the §16 mechanism on synthetic bars.

    An opening bar 100x a normal bar enters its own trailing mean, so
    subsequent NORMAL-volume bars read far below 1.0 under the legacy
    formula while the baseline formula correctly reads ~1.0.
    """
    vol = pd.Series([100_000.0] + [1_000.0] * 10)
    legacy = calculate_rvol(vol, 20)
    assert legacy.iloc[1] < 0.1, "legacy craters right after the open"
    assert legacy.iloc[5] < 0.3, "and stays depressed for the whole window"

    t = _times([f'09:{30 + i:02d}' for i in range(11)])
    baseline = {9 * 60 + 30 + i: 1_000.0 for i in range(11)}
    baseline[9 * 60 + 30] = 100_000.0     # opens are historically heavy
    corrected = calculate_rvol_vs_baseline(t, vol, baseline)
    assert abs(corrected.iloc[0] - 1.0) < 1e-9, "a normal open reads 1.0"
    assert all(abs(corrected.iloc[i] - 1.0) < 1e-9 for i in range(1, 11)), \
        "normal-volume bars read 1.0 regardless of position in the session"
