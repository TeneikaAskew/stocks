"""Tests for Task 4.2: `lib/style_miner.py`.

Fixture design
--------------
Two "patterns" of 29 synthetic 1-min bars are used throughout. Both were
constructed via `lib.indicators.add_signal_indicators` (the exact
production indicator path `style_miner.snapshot_entry_conditions` calls)
during fixture design, then hard-coded here as fixed close-price arrays —
this file does NOT call the indicator module to "self-check" its own
assertions; the printed RSI/VWAP/StochRSI-K/consecutive-move values below
are asserted as fixed expected outputs of style_miner, not re-derived at
test time.

  PATTERN1 (comfortable margin, verified via add_signal_indicators):
    RSI14=41.91 (in call band 25-50, ~8pt margin from the 50 edge)
    Price_vs_VWAP=+0.182 (above VWAP)
    Consecutive_Up=2.0, Consecutive_Down=1.0 (both < consecutive_periods=3)
    StochRSI_K=50.64 (neither <30 nor >70)
    -> conditions true: {rsi_25_50, above_vwap} ONLY.

  PATTERN2 (opposite bias):
    RSI14=55.35 (in put band 50-75, ~5pt margin from the 50 edge)
    Price_vs_VWAP=-0.178 (below VWAP)
    Consecutive_Up=1.0, Consecutive_Down=2.0 (both < 3)
    StochRSI_K=6.72 (< 30 -> oversold)
    -> conditions true: {rsi_50_75, below_vwap, stoch_oversold}.

Both patterns hold Volume=0 for the first 24 bars and Volume=1000 for the
last 5, so VWAP is driven only by the last 5 bars' typical prices (decouples
the long RSI-shaping history from the VWAP-side condition) — see
`_make_pattern_bars`. Each pattern is 29 bars long (index 0-28, entry at the
last bar, idx 28), comfortably past the 14-bar warm-up gate.
"""
from __future__ import annotations

import pandas as pd
import pytest

from lib.style_miner import StyleProfile, mine_style, snapshot_entry_conditions

# ---------------------------------------------------------------------------
# Fixture bars
# ---------------------------------------------------------------------------

# Pattern1: 24 bars alternating +0.10 / -0.20 from 100.0, then a 4-move tail
# [-0.05, +0.05, -0.05, +0.25] appended to the 24th value. Verified (see
# module docstring above) to yield RSI14=41.91, Price_vs_VWAP=+0.182 at the
# final bar (idx 28).
def _build_pattern1_closes() -> list:
    closes = [100.0]
    for i in range(24):
        if i % 2 == 0:
            closes.append(round(closes[-1] + 0.10, 4))
        else:
            closes.append(round(closes[-1] - 0.20, 4))
    tail_start = closes[-1]
    tail = [tail_start]
    for m in (-0.05, 0.05, -0.05, 0.25):
        tail.append(round(tail[-1] + m, 4))
    return closes[:-1] + tail


# Pattern2: mirror of pattern1 (+0.20 / -0.10 alternation, opposite tail).
# Verified to yield RSI14=55.35, Price_vs_VWAP=-0.178, StochRSI_K=6.72.
def _build_pattern2_closes() -> list:
    closes = [100.0]
    for i in range(24):
        if i % 2 == 0:
            closes.append(round(closes[-1] + 0.20, 4))
        else:
            closes.append(round(closes[-1] - 0.10, 4))
    tail_start = closes[-1]
    tail = [tail_start]
    for m in (0.05, -0.05, 0.05, -0.25):
        tail.append(round(tail[-1] + m, 4))
    return closes[:-1] + tail


_PATTERN1_CLOSES = _build_pattern1_closes()
_PATTERN2_CLOSES = _build_pattern2_closes()
assert len(_PATTERN1_CLOSES) == len(_PATTERN2_CLOSES) == 29

# Last bar of a 29-bar 09:30-start 1-min frame is 09:58.
_ENTRY_TIME = "09:58:00"


def _make_pattern_bars(closes: list, date_str: str) -> pd.DataFrame:
    """29 uppercase-OHLCV bars + 'Time' for `date_str`. Volume=0 for the
    first 24 bars, 1000 for the last 5 -- VWAP is driven only by the last 5
    bars' typical prices (see module docstring)."""
    n = len(closes)
    times = pd.date_range(f"{date_str} 09:30", periods=n, freq="1min")
    volumes = [0.0] * (n - 5) + [1000.0] * 5
    return pd.DataFrame({
        "Time": [str(t) for t in times],
        "Open": closes,
        "High": [c + 0.02 for c in closes],
        "Low": [c - 0.02 for c in closes],
        "Close": closes,
        "Volume": volumes,
    })


def _make_warmup_bars(date_str: str) -> pd.DataFrame:
    """A 6-bar frame (< 14-bar warm-up floor) -- values are irrelevant since
    snapshot_entry_conditions must return None before touching indicators."""
    n = 6
    times = pd.date_range(f"{date_str} 09:30", periods=n, freq="1min")
    return pd.DataFrame({
        "Time": [str(t) for t in times],
        "Open": [100.0] * n,
        "High": [100.05] * n,
        "Low": [99.95] * n,
        "Close": [100.0] * n,
        "Volume": [1000.0] * n,
    })


def _entry(entry_id: str, direction: str, date_str: str) -> dict:
    return {
        "id": entry_id,
        "direction": direction,
        "entry_ts": f"{date_str} {_ENTRY_TIME}",
        "entry_price": 100.0,
        "exit_ts": f"{date_str} 10:30:00",
        "exit_price": 100.5,
    }


# ---------------------------------------------------------------------------
# snapshot_entry_conditions
# ---------------------------------------------------------------------------

class TestSnapshotEntryConditions:
    def test_pattern1_yields_rsi_25_50_and_above_vwap_only(self):
        bars = _make_pattern_bars(_PATTERN1_CLOSES, "2026-06-10")
        snap = snapshot_entry_conditions(bars, entry_idx=28)
        assert snap == {
            "rsi_25_50": True,
            "rsi_50_75": False,
            "above_vwap": True,
            "below_vwap": False,
            "consec_up_ge_3": False,
            "consec_down_ge_3": False,
            "stoch_oversold": False,
            "stoch_overbought": False,
        }

    def test_pattern2_yields_rsi_50_75_below_vwap_and_stoch_oversold(self):
        bars = _make_pattern_bars(_PATTERN2_CLOSES, "2026-06-11")
        snap = snapshot_entry_conditions(bars, entry_idx=28)
        assert snap == {
            "rsi_25_50": False,
            "rsi_50_75": True,
            "above_vwap": False,
            "below_vwap": True,
            "consec_up_ge_3": False,
            "consec_down_ge_3": False,
            "stoch_oversold": True,
            "stoch_overbought": False,
        }

    def test_within_warmup_returns_none(self):
        """entry_idx=5 -> only 6 bars available (< 14-bar floor) -> None,
        mirrors lib.backtest._SIGNAL_WARMUP_BARS / live.py's warm-up gate."""
        bars = _make_warmup_bars("2026-06-12")
        assert snapshot_entry_conditions(bars, entry_idx=5) is None

    def test_boundary_at_exactly_14_bars_is_not_warmup(self):
        """entry_idx=13 -> 14 bars available (entry_idx + 1 == 14) -> NOT
        excluded (the gate is strictly '< 14', matching lib.backtest.py's
        `entry_idx + 1 < _SIGNAL_WARMUP_BARS`)."""
        bars = _make_pattern_bars(_PATTERN1_CLOSES, "2026-06-13")
        snap = snapshot_entry_conditions(bars, entry_idx=13)
        assert snap is not None
        assert set(snap.keys()) == {
            "rsi_25_50", "rsi_50_75", "above_vwap", "below_vwap",
            "consec_up_ge_3", "consec_down_ge_3",
            "stoch_oversold", "stoch_overbought",
        }

    def test_out_of_range_entry_idx_raises(self):
        bars = _make_pattern_bars(_PATTERN1_CLOSES, "2026-06-14")
        with pytest.raises(ValueError):
            snapshot_entry_conditions(bars, entry_idx=99)


# ---------------------------------------------------------------------------
# mine_style
# ---------------------------------------------------------------------------

def _build_ten_entry_fixture():
    """5 CALL (4x pattern1 + 1x pattern2) + 5 PUT (5x pattern2) = 10 total.

    CALL: 4/5 share {rsi_25_50, above_vwap} (the 5th, pattern2, has neither)
      -> kept=['above_vwap', 'rsi_25_50'], support=4, total=5.
    PUT: 5/5 share {below_vwap, rsi_50_75, stoch_oversold}
      -> kept=['below_vwap', 'rsi_50_75', 'stoch_oversold'], support=5, total=5.
    """
    entries = []
    bars_by_date = {}

    call_dates = ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04", "2026-06-05"]
    for i, date_str in enumerate(call_dates):
        closes = _PATTERN1_CLOSES if i < 4 else _PATTERN2_CLOSES
        bars_by_date[date_str] = _make_pattern_bars(closes, date_str)
        entries.append(_entry(f"call-{i}", "CALL", date_str))

    put_dates = ["2026-06-06", "2026-06-07", "2026-06-08", "2026-06-09", "2026-06-10"]
    for i, date_str in enumerate(put_dates):
        bars_by_date[date_str] = _make_pattern_bars(_PATTERN2_CLOSES, date_str)
        entries.append(_entry(f"put-{i}", "PUT", date_str))

    return entries, bars_by_date


class TestMineStyle:
    def test_call_and_put_profiles_shape(self):
        entries, bars_by_date = _build_ten_entry_fixture()

        profiles = mine_style(entries, bars_by_date)

        assert profiles == [
            StyleProfile(direction="CALL", conditions=["above_vwap", "rsi_25_50"],
                         support=4, total=5),
            StyleProfile(direction="PUT",
                         conditions=["below_vwap", "rsi_50_75", "stoch_oversold"],
                         support=5, total=5),
        ]

    def test_determinism_independent_of_input_order(self):
        entries, bars_by_date = _build_ten_entry_fixture()

        forward = mine_style(entries, bars_by_date)
        shuffled = mine_style(list(reversed(entries)), bars_by_date)

        assert forward == shuffled

    def test_fewer_than_ten_total_entries_returns_empty_list(self):
        """9 entries, all CALL, all individually well past the 5-entry
        per-direction floor -- the explicit <10-TOTAL gate must still fire
        before any per-direction accounting happens."""
        entries = []
        bars_by_date = {}
        dates = [f"2026-05-{d:02d}" for d in range(1, 10)]
        for i, date_str in enumerate(dates):
            bars_by_date[date_str] = _make_pattern_bars(_PATTERN1_CLOSES, date_str)
            entries.append(_entry(f"call-{i}", "CALL", date_str))
        assert len(entries) == 9

        assert mine_style(entries, bars_by_date) == []

    def test_warmup_exclusion_can_drop_a_direction_below_minimum(self):
        """PUT has 5 RAW entries (>= _MIN_DIRECTION_ENTRIES on paper) but one
        is inside the 14-bar warm-up floor -> excluded -> only 4 RESOLVED
        PUT entries remain -> no PUT profile emitted. CALL is unaffected and
        still profiles normally. Raw total is still 10, so the <10 gate
        doesn't preempt this case."""
        entries, bars_by_date = _build_ten_entry_fixture()

        # Replace one PUT entry's bars with a warm-up-only (6-bar) frame,
        # with entry_ts matching bar idx 5 (well within the 14-bar floor).
        warmup_date = "2026-06-09"
        bars_by_date[warmup_date] = _make_warmup_bars(warmup_date)
        for e in entries:
            if e["id"] == "put-3":
                e["entry_ts"] = f"{warmup_date} 09:35:00"

        profiles = mine_style(entries, bars_by_date)

        assert len(profiles) == 1
        assert profiles[0].direction == "CALL"
        assert profiles[0].conditions == ["above_vwap", "rsi_25_50"]
        assert profiles[0].support == 4
        assert profiles[0].total == 5

    def test_entry_with_no_matching_bar_is_excluded_not_zero_filled(self):
        """An entry whose entry_ts doesn't minute-match any bar in its
        day's frame is excluded from the denominator entirely (mirrors the
        warm-up exclusion contract) -- never treated as a resolved entry
        with all-false conditions. Dropping one of the 5 PUT entries this
        way leaves only 4 resolved PUT entries (< _MIN_DIRECTION_ENTRIES=5),
        so PUT gets no profile either -- only CALL survives."""
        entries, bars_by_date = _build_ten_entry_fixture()
        for e in entries:
            if e["id"] == "put-4":
                e["entry_ts"] = "2026-06-10 23:59:00"  # no such bar that day

        profiles = mine_style(entries, bars_by_date)

        assert len(profiles) == 1
        assert profiles[0].direction == "CALL"
        assert profiles[0].support == 4
        assert profiles[0].total == 5
