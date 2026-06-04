"""Hermetic tests for the pure helpers in
gcp.research.strat_engine.strat_dir_probes (Phase 1 direction probes).

Locks the two correctness-critical behaviours and proves the helpers import
with only numpy + pandas (no lightgbm / sklearn / Cloud SQL):
  1. session_aware_fwd_ret_bps never crosses the overnight gap (the same
     contamination class fixed for the t+1 label on 2026-05-25; the precomputed
     fwd_ret_* columns DO cross it, which is why the probe recomputes).
  2. embargo_days_for converts a BAR horizon to a DAY embargo with ceil + slack
     so a forward label window cannot overlap the test fold.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from gcp.research.strat_engine.strat_dir_probes import (  # noqa: E402
    session_aware_fwd_ret_bps,
    embargo_days_for,
    _session_third,
    _stratified_hit_rates,
)


def _two_sessions(closes_by_day: dict[str, list[float]]) -> pd.DataFrame:
    rows = []
    for d, closes in closes_by_day.items():
        for i, c in enumerate(closes):
            rows.append({"bar_date": d,
                         "ts": pd.Timestamp(f"{d} 09:{30 + i:02d}"),
                         "close": float(c)})
    return pd.DataFrame(rows)


# ── session_aware_fwd_ret_bps ───────────────────────────────────────────────

def test_fwd_ret_is_session_aware_no_overnight_crossing():
    df = _two_sessions({
        "2026-01-02": [100, 101, 102, 103],
        "2026-01-05": [200, 202, 204, 206],
    })
    out = session_aware_fwd_ret_bps(df, horizon=2)
    # Within-session forward returns are correct.
    assert out.iloc[0] == pytest.approx((102 - 100) / 100 * 10000)   # day1 bar0
    assert out.iloc[1] == pytest.approx((103 - 101) / 101 * 10000)   # day1 bar1
    assert out.iloc[4] == pytest.approx((204 - 200) / 200 * 10000)   # day2 bar0
    # The last `horizon` bars of EACH session have no forward label (NaN),
    # and crucially day1's tail does NOT borrow day2's open (no crossing).
    assert pd.isna(out.iloc[2]) and pd.isna(out.iloc[3])             # day1 tail
    assert pd.isna(out.iloc[6]) and pd.isna(out.iloc[7])             # day2 tail


def test_fwd_ret_horizon_one_matches_next_bar():
    df = _two_sessions({"2026-01-02": [100, 110, 121]})
    out = session_aware_fwd_ret_bps(df, horizon=1)
    assert out.iloc[0] == pytest.approx((110 - 100) / 100 * 10000)
    assert out.iloc[1] == pytest.approx((121 - 110) / 110 * 10000)
    assert pd.isna(out.iloc[2])  # last bar of session


# ── embargo_days_for ────────────────────────────────────────────────────────

@pytest.mark.parametrize("tf,horizon,expected", [
    ("15m", 15, 2),    # ceil(15/26)=1 + 1
    ("15m", 26, 2),    # ceil(26/26)=1 + 1
    ("15m", 27, 3),    # ceil(27/26)=2 + 1
    ("15m", 60, 4),    # ceil(60/26)=3 + 1
    ("5m", 78, 2),     # exactly one day of 5m bars: ceil(78/78)=1 + 1
    ("30m", 13, 2),    # one day of 30m bars
    ("1d", 5, 6),      # daily: ceil(5/1)=5 + 1
])
def test_embargo_days_for(tf, horizon, expected):
    assert embargo_days_for(tf, horizon) == expected


def test_embargo_unknown_tf_defaults_safely():
    # Unknown tf falls back to 26 bars/day (intraday-ish) rather than crashing.
    assert embargo_days_for("7m", 26) == 2


# ── _session_third ──────────────────────────────────────────────────────────

def test_session_third_buckets_by_position():
    df = _two_sessions({"2026-01-02": [1, 2, 3, 4, 5, 6]})
    thirds = _session_third(df).astype(str).tolist()
    assert thirds == ["early", "early", "mid", "mid", "late", "late"]


# ── _stratified_hit_rates ───────────────────────────────────────────────────

def test_stratified_hit_rates_filters_decisive_and_scores_per_level():
    y_true = np.array([1, 1, 0, 0, 0])
    p_up = np.array([0.9, 0.5, 0.1, 0.52, 0.6])  # decisive: T,F,T,F,T
    strata = {"regime": pd.Series(["a", "a", "b", "b", "a"])}
    out = _stratified_hit_rates(y_true, p_up, strata)["regime"]
    # level a: decisive rows are idx0 (pred1==1 hit) and idx4 (pred1 vs 0 miss)
    assert out["a"]["n"] == 2
    assert out["a"]["hit_rate"] == pytest.approx(0.5)
    # level b: only idx2 decisive (pred0==0 hit); idx3 not decisive
    assert out["b"]["n"] == 1
    assert out["b"]["hit_rate"] == pytest.approx(1.0)


def test_stratified_hit_rates_none_when_no_decisive():
    y_true = np.array([1, 0])
    p_up = np.array([0.5, 0.5])  # nothing ≥0.55
    out = _stratified_hit_rates(y_true, p_up, {"r": pd.Series(["x", "x"])})["r"]
    assert out["x"]["n"] == 0
    assert out["x"]["hit_rate"] is None
