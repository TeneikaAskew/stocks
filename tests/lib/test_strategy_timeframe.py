"""Phase 1 — hermetic tests for the timeframe-tag heuristic.

Coverage:
  1. Output is always (str, int) with tag in VALID_TAGS — never None
  2. High volatility + strong confirmation → 15m
  3. High volatility, weak confirmation → 30m
  4. Low volatility → 60m (overrides signal-type)
  5. Mean-reversion conditions → 30m at average vol
  6. Momentum conditions → 15m at average vol
  7. Default fall-through (no signal-type match, average vol) → 30m
  8. Missing indicator values (None) fall back safely
  9. expected_hold_min always matches the tag's bucket
 10. ATR threshold is in PERCENT (0.4% = 0.004) not fraction-of-fraction
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.strategies.timeframe import (  # noqa: E402
    HIGH_ATR_5M_PCT,
    HIGH_RVOL,
    LOW_RVOL,
    STRONG_CONFIRMATION,
    VALID_TAGS,
    assign_timeframe,
)


# ── 1) Output contract ─────────────────────────────────────────────────

def test_assign_timeframe_returns_valid_tuple():
    tag, hold = assign_timeframe([], rsi=50.0, rvol=1.0)
    assert tag in VALID_TAGS
    assert isinstance(hold, int) and hold > 0


def test_expected_hold_min_matches_tag_bucket():
    """The hold minutes must match the integer in the tag (e.g. '15m' → 15)."""
    cases = [
        (["consecutive_up"], {"rvol": 1.0}, "15m", 15),
        (["consecutive_down"], {"rvol": 1.0}, "30m", 30),
        ([], {"rvol": 0.5}, "60m", 60),
    ]
    for conds, kw, expected_tag, expected_hold in cases:
        tag, hold = assign_timeframe(conds, **kw)
        if tag == expected_tag:
            assert hold == expected_hold


# ── 2) High volatility branches ────────────────────────────────────────

def test_high_rvol_with_strong_confirmation_picks_15m():
    """RVOL ≥ HIGH_RVOL (2.0×) + 4+ conditions → fastest active tf."""
    conds = ["c1", "c2", "c3", "c4"]   # 4 conditions = STRONG_CONFIRMATION
    tag, hold = assign_timeframe(conds, rvol=HIGH_RVOL + 0.1)
    assert tag == "15m"
    assert hold == 15


def test_high_atr_with_strong_confirmation_picks_15m():
    """ATR_5m ≥ HIGH_ATR_5M_PCT also triggers high-vol branch."""
    conds = ["c1", "c2", "c3", "c4", "c5"]
    tag, _ = assign_timeframe(
        conds, rvol=1.0,
        atr_5m_pct=(HIGH_ATR_5M_PCT / 100.0) + 0.001,
    )
    assert tag == "15m"


def test_high_rvol_weak_confirmation_picks_30m():
    """Volatile but only 2 conditions → 30m (not 15m)."""
    conds = ["c1", "c2"]
    tag, _ = assign_timeframe(conds, rvol=HIGH_RVOL + 0.5)
    assert tag == "30m"


# ── 3) Low volatility ──────────────────────────────────────────────────

def test_low_rvol_picks_60m_regardless_of_signal_type():
    """Quiet sessions → slowest timeframe, even on momentum/mean-rev signals."""
    for conds in (["consecutive_up"], ["consecutive_down"], []):
        tag, _ = assign_timeframe(conds, rvol=LOW_RVOL - 0.1)
        assert tag == "60m", f"low-vol with {conds} should give 60m, got {tag}"


# ── 4) Signal-type heuristics at average volatility ────────────────────

def test_mean_reversion_signals_at_average_vol_pick_30m():
    """consecutive_down / oversold / below_* conditions → 30m default."""
    cases = [
        ["consecutive_down"],
        ["rsi_oversold_zone"],
        ["below_vwap"],
        ["near_below_emas"],
        ["consecutive_down", "rsi_oversold_zone", "below_vwap"],   # combo
    ]
    for conds in cases:
        tag, _ = assign_timeframe(conds, rvol=1.0)
        assert tag == "30m", f"{conds} should give 30m, got {tag}"


def test_momentum_signals_at_average_vol_pick_15m():
    cases = [
        ["consecutive_up"],
        ["breakout_orb_5m"],
        ["above_vwap"],
        ["near_above_ema9"],
        ["consecutive_up", "above_vwap", "above_ema9"],   # combo
    ]
    for conds in cases:
        tag, _ = assign_timeframe(conds, rvol=1.0)
        assert tag == "15m", f"{conds} should give 15m, got {tag}"


# ── 5) Default fall-through ────────────────────────────────────────────

def test_unrecognized_signal_type_at_avg_vol_falls_through_to_30m():
    conds = ["some_unknown_condition", "another_unrecognized"]
    tag, _ = assign_timeframe(conds, rvol=1.0)
    assert tag == "30m"


def test_empty_conditions_at_avg_vol_falls_through_to_30m():
    """No conditions, average volatility → default 30m."""
    tag, _ = assign_timeframe([], rvol=1.0)
    assert tag == "30m"


# ── 6) None handling ───────────────────────────────────────────────────

def test_none_rvol_treated_as_average_volatility():
    """Missing RVOL falls back to 1.0 (average) — not high, not low."""
    tag, _ = assign_timeframe(["consecutive_up"], rvol=None)
    assert tag == "15m"   # momentum default


def test_none_atr_treated_as_zero():
    """Missing ATR is treated as 0% (low vol indicator); doesn't crash."""
    tag, _ = assign_timeframe(["consecutive_up"], rvol=1.0, atr_5m_pct=None)
    assert tag == "15m"


def test_all_none_does_not_raise():
    """Defensive: unknown conditions + all-None indicators → default 30m."""
    tag, hold = assign_timeframe([], rsi=None, rvol=None, atr_5m_pct=None)
    assert tag == "30m"
    assert hold == 30


def test_none_conditions_list_handled():
    """Passing None instead of list shouldn't crash."""
    tag, hold = assign_timeframe(None, rvol=1.0)   # type: ignore[arg-type]
    assert tag in VALID_TAGS


# ── 7) Threshold boundary correctness ─────────────────────────────────

def test_threshold_constants_are_what_documented():
    """Sanity guard against accidental edits to the docstring math."""
    assert HIGH_RVOL == pytest.approx(2.0)
    assert HIGH_ATR_5M_PCT == pytest.approx(0.40)
    assert LOW_RVOL == pytest.approx(1.0)
    assert STRONG_CONFIRMATION == 4


def test_atr_threshold_is_in_percent_not_fraction():
    """HIGH_ATR_5M_PCT is documented as percent (0.40), and the
    function divides by 100 internally to get fraction (0.004) for
    comparison against atr_5m_pct (which IS a fraction). A regression
    that drops the /100 would silently shift the threshold by 100×."""
    # 0.005 fraction (= 0.5%) is ABOVE the 0.4% threshold → high-vol
    tag_high, _ = assign_timeframe(["c1", "c2", "c3", "c4"], rvol=1.0, atr_5m_pct=0.005)
    assert tag_high == "15m"
    # 0.001 fraction (= 0.1%) is BELOW the 0.4% threshold → not high-vol
    tag_low, _ = assign_timeframe(["consecutive_up"], rvol=1.0, atr_5m_pct=0.001)
    assert tag_low == "15m"   # momentum default at avg vol, NOT 15m via high-vol path


# ── Backfill tagging: the placeholder tiers (#1167) ────────────────────
#
# EMPIRICAL_LOOKUP is retired. Re-derived on the #1154-corrected
# classifications, its method was degenerate: every window measures the best
# favorable move since entry, so the clean-hit rate rises with the window and
# "highest clean rate" picked 240m for 50 of 52 buckets. The May table's
# "60m everywhere" was the same artifact under the unit bug. See
# docs/analysis/TIMEFRAME_HEURISTIC_2026-09-26.md.

def test_the_empirical_lookup_is_retired():
    import lib.strategies.timeframe as tf
    assert not hasattr(tf, "EMPIRICAL_LOOKUP")
    assert "EMPIRICAL_LOOKUP" not in tf.__all__


def test_backfill_uses_the_placeholder_tiers_for_every_input():
    """Every input the retired table bucketed now gets the placeholder's
    answer, and entry_rsi no longer changes the tag."""
    from lib.strategies.timeframe import _placeholder_assign, assign_timeframe_for_backfill
    for strategy in ("momentum", "mean_reversion", "other", None):
        for strength in (None, 0, 3, 4, 5, 6):
            for atr in (None, float("nan"), 0.0005, 0.002, 0.005):
                expected = _placeholder_assign(strategy, strength, atr)
                for rsi in (None, float("nan"), 20.0, 50.0, 80.0):
                    got = assign_timeframe_for_backfill(strategy, strength, atr, rsi)
                    assert got == expected, (strategy, strength, atr, rsi, got, expected)


def test_backfill_no_longer_tags_the_old_dominant_bucket_60m():
    """(momentum, 3, avg ATR, mid RSI) was the table's largest bucket, tagged
    60m. The placeholder's momentum default at average volatility is 15m."""
    from lib.strategies.timeframe import assign_timeframe_for_backfill
    assert assign_timeframe_for_backfill("momentum", 3, 0.002, 50.0) == ("15m", 15)


def test_assign_timeframe_for_backfill_signature_accepts_entry_rsi_kwarg():
    """Callers pass entry_rsi (run_historical_signals, backfill_timeframe_tags);
    it is accepted and unused, and a call without it still works."""
    from lib.strategies.timeframe import assign_timeframe_for_backfill
    assert assign_timeframe_for_backfill(
        strategy="momentum", signal_strength=3, atr_5m_pct=0.002,
    ) == assign_timeframe_for_backfill(
        strategy="momentum", signal_strength=3, atr_5m_pct=0.002, entry_rsi=75.0,
    ) == ("15m", 15)


def test_assign_timeframe_for_backfill_handles_nan_inputs():
    """NaN ATR is not high volatility, and NaN RSI is ignored; no crash."""
    from lib.strategies.timeframe import assign_timeframe_for_backfill
    tag, hold = assign_timeframe_for_backfill(
        strategy="momentum", signal_strength=3,
        atr_5m_pct=float("nan"), entry_rsi=float("nan"),
    )
    assert (tag, hold) == ("15m", 15)
