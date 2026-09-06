"""Tests for compute_risk_metrics (lib/agents/trade_planner.py) and the
RiskMetrics dataclass (lib/agents/schema.py).

These tests prove the deterministic math the LLM reviewers are now
required to read instead of compute. Empirical validation in
docs/audits/2026-05-10-risk-reviewer-validation.md showed the LLM had
44.4% precision computing 'stop < 1 ATR' itself; these tests prove
compute_risk_metrics has 100% precision (it's literal arithmetic).
"""
from __future__ import annotations

import pytest

from lib.agents.schema import RiskMetrics
from lib.agents.trade_planner import compute_risk_metrics


# ── Basic happy-path math ─────────────────────────────────────────


def test_long_stop_distance_atr_positive():
    """Long: entry_mid 100, stop 95 → risk 5; ATR 5 → 1.0 ATR."""
    m = compute_risk_metrics(
        entry_lo=99, entry_hi=101, stop=95,
        targets=[105, 110, 115], direction="long", atr=5.0,
    )
    assert m.stop_distance_atr == pytest.approx(1.0)
    assert m.stop_distance_pct == pytest.approx(5.0)


def test_long_stop_below_one_atr():
    """The 5/5 QQQ example from the validation audit:
    entry 676.73-678.73 (mid 677.73), stop 666.03 → risk 11.70.
    ATR 9.7 → 11.70 / 9.7 = 1.21 ATRs.
    The LLM flagged this as 'stop < 1 ATR' but mathematically it isn't."""
    m = compute_risk_metrics(
        entry_lo=676.73, entry_hi=678.73, stop=666.03,
        targets=[694.79], direction="long", atr=9.7,
    )
    assert m.stop_distance_atr == pytest.approx(1.21, abs=0.01)
    assert m.stop_distance_atr > 1.0, \
        "this stop is NOT below 1 ATR — the LLM's flag was a hallucination"


def test_short_target_r_multiples_signed():
    """Short: entry_mid 100, stop 105 → risk 5.
    Targets [95, 90, 85] → R-multiples [+1, +2, +3] (good for short)."""
    m = compute_risk_metrics(
        entry_lo=99, entry_hi=101, stop=105,
        targets=[95, 90, 85], direction="short", atr=5.0,
    )
    assert m.target_r_multiples == [pytest.approx(1.0), pytest.approx(2.0), pytest.approx(3.0)]


def test_long_target_above_entry_is_positive_r():
    m = compute_risk_metrics(
        entry_lo=100, entry_hi=100, stop=98,
        targets=[104, 108, 112], direction="long", atr=2.0,
    )
    # risk=2, t1=104 → +2/2=+2.0 R
    assert m.target_r_multiples == [
        pytest.approx(2.0), pytest.approx(4.0), pytest.approx(6.0),
    ]


def test_long_target_below_entry_is_negative_r():
    """Target on the wrong side of entry → negative R-multiple (warns)."""
    m = compute_risk_metrics(
        entry_lo=100, entry_hi=100, stop=98,
        targets=[97], direction="long", atr=2.0,
    )
    # risk=2, t1=97 → -3/2=-1.5 R
    assert m.target_r_multiples[0] == pytest.approx(-1.5)


# ── SMA200 distances ─────────────────────────────────────────────


def test_entry_above_sma200_pct():
    """Long entry 110, SMA200 100 → +10%."""
    m = compute_risk_metrics(
        entry_lo=110, entry_hi=110, stop=105,
        targets=[120], direction="long", atr=5.0, sma_200=100.0,
    )
    assert m.entry_vs_sma200_pct == pytest.approx(10.0)
    assert m.entry_vs_sma200_atr == pytest.approx(2.0)  # 10/5 = 2 ATRs


def test_entry_below_sma200_negative_pct():
    m = compute_risk_metrics(
        entry_lo=95, entry_hi=95, stop=90,
        targets=[100], direction="long", atr=5.0, sma_200=100.0,
    )
    assert m.entry_vs_sma200_pct == pytest.approx(-5.0)


def test_sma200_none_returns_none():
    m = compute_risk_metrics(
        entry_lo=100, entry_hi=100, stop=98,
        targets=[104], direction="long", atr=2.0, sma_200=None,
    )
    assert m.entry_vs_sma200_pct is None
    assert m.entry_vs_sma200_atr is None


# ── FTFC alignment flag ──────────────────────────────────────────


def test_long_with_strong_bullish_ftfc_aligned():
    m = compute_risk_metrics(
        entry_lo=100, entry_hi=100, stop=98,
        targets=[104], direction="long", atr=2.0, ftfc_score=0.75,
    )
    assert m.ftfc_aligned is True


def test_long_with_strong_bearish_ftfc_misaligned():
    m = compute_risk_metrics(
        entry_lo=100, entry_hi=100, stop=98,
        targets=[104], direction="long", atr=2.0, ftfc_score=-0.75,
    )
    assert m.ftfc_aligned is False


def test_long_with_weak_ftfc_misaligned():
    """|FTFC| < 0.5 doesn't count as aligned — matches _calibrate_conviction."""
    m = compute_risk_metrics(
        entry_lo=100, entry_hi=100, stop=98,
        targets=[104], direction="long", atr=2.0, ftfc_score=0.3,
    )
    assert m.ftfc_aligned is False


def test_short_with_strong_bearish_ftfc_aligned():
    m = compute_risk_metrics(
        entry_lo=100, entry_hi=100, stop=102,
        targets=[96], direction="short", atr=2.0, ftfc_score=-0.7,
    )
    assert m.ftfc_aligned is True


def test_ftfc_none_yields_none():
    m = compute_risk_metrics(
        entry_lo=100, entry_hi=100, stop=98,
        targets=[104], direction="long", atr=2.0, ftfc_score=None,
    )
    assert m.ftfc_aligned is None


# ── Edge cases / degenerate inputs ───────────────────────────────


def test_zero_atr_yields_none_atr_distance():
    m = compute_risk_metrics(
        entry_lo=100, entry_hi=100, stop=98,
        targets=[104], direction="long", atr=0.0,
    )
    assert m.stop_distance_atr is None
    # pct distance still computed
    assert m.stop_distance_pct == pytest.approx(2.0)


def test_zero_risk_yields_no_r_multiples():
    """Stop equals entry_mid → risk_per_unit=0 → division by zero avoided."""
    m = compute_risk_metrics(
        entry_lo=100, entry_hi=100, stop=100,
        targets=[105, 110], direction="long", atr=2.0,
    )
    assert m.stop_distance_atr is None  # zero risk
    # target_r_multiples should be empty (can't divide by zero)
    assert m.target_r_multiples == []


def test_empty_targets_yields_empty_r_multiples():
    m = compute_risk_metrics(
        entry_lo=100, entry_hi=100, stop=98,
        targets=[], direction="long", atr=2.0,
    )
    assert m.target_r_multiples == []


def test_invalidation_distance_atr():
    m = compute_risk_metrics(
        entry_lo=100, entry_hi=100, stop=95,
        targets=[110], direction="long", atr=5.0,
        invalidation_level=93.0,  # below stop
    )
    # |93 - 95| / 5 = 0.4
    assert m.invalidation_distance_atr == pytest.approx(0.4)


# ── Structural ───────────────────────────────────────────────────


def test_returns_riskmetrics_pydantic_object():
    m = compute_risk_metrics(
        entry_lo=100, entry_hi=100, stop=98,
        targets=[104], direction="long", atr=2.0,
    )
    assert isinstance(m, RiskMetrics)


def test_riskmetrics_serializes_to_json():
    """PersonaPlan.risk_metrics persists via JSONB; must round-trip."""
    import json
    m = compute_risk_metrics(
        entry_lo=100, entry_hi=100, stop=98,
        targets=[104], direction="long", atr=2.0, sma_200=95.0,
        ftfc_score=0.6,
    )
    payload = m.model_dump()
    s = json.dumps(payload)
    parsed = json.loads(s)
    assert parsed['stop_distance_atr'] == pytest.approx(1.0)
    assert parsed['ftfc_aligned'] is True
    assert parsed['entry_vs_sma200_pct'] == pytest.approx(5.263, abs=0.01)
