"""FTFC consumer gates in lib/agents: the aligned flag and the conservative minimum.

Two gates read the signed legacy FTFC score (-1 bearish to +1 bullish):

* ``ftfc_aligned`` (trade_planner.compute_risk_metrics and
  orchestrator._calibrate_conviction): long needs >= +0.5, short <= -0.5.
* the conservative persona minimum (trade_planner._plan and its
  rationale): the score must agree with the trade's direction by 0.30.

The scores here come from the real producer, StratClassifier.calculate_ftfc
with the default weights on the brief's 1d/1w/1mo frames, so the floating
point values are the ones production computes.
"""

from __future__ import annotations

import pandas as pd
import pytest

from lib.agents.orchestrator import _calibrate_conviction
from lib.agents.trade_planner import (
    PlanContext,
    compute_persona_plans,
    compute_risk_metrics,
)
from lib.config import StratConfig
from lib.strat import StratClassifier

_UP = {"Open": [10.0, 10.5], "High": [11.0, 12.0], "Low": [9.0, 9.5], "Close": [10.5, 11.5]}
_DOWN = {"Open": [10.0, 9.5], "High": [11.0, 10.5], "Low": [9.0, 8.0], "Close": [10.5, 8.5]}


def _legacy_score(daily: dict, weekly: dict) -> float:
    """calculate_ftfc on a daily and a weekly frame with the default weights
    (1d 0.30, 1w 0.10; 1mo carries no weight), as compute_strat_status runs it."""
    clf = StratClassifier(strat_config=StratConfig())
    score, _direction, _labels = clf.calculate_ftfc(
        {"1d": pd.DataFrame(daily), "1w": pd.DataFrame(weekly)})
    return score


def _aligned_via_planner(direction: str, score: float) -> bool:
    return compute_risk_metrics(entry_lo=100.0, entry_hi=101.0, stop=98.0, targets=[104.0],
                                direction=direction, atr=2.0, ftfc_score=score).ftfc_aligned


def _high_conviction(direction: str, score: float) -> bool:
    return _calibrate_conviction(direction=direction, confidence_score=0.8,
                                 analyst_agreement_count=5, ftfc_score=score,
                                 risk_severities=[]) == "high"


# ─── Bug: ftfc_aligned differs between the raw score and its 2 dp snapshot ───


@pytest.mark.parametrize("direction,daily,weekly", [
    ("long", _UP, _DOWN),     # (0.3 - 0.1) / 0.4
    ("short", _DOWN, _UP),    # (-0.3 + 0.1) / 0.4
])
def test_aligned_is_the_same_for_the_raw_score_and_its_snapshot(direction, daily, weekly):
    raw = _legacy_score(daily, weekly)
    snapshot = round(raw, 2)          # summarize_strat_status / StratSnapshot precision
    assert abs(raw) != 0.5 and abs(snapshot) == 0.5   # the float that caused the split
    assert _aligned_via_planner(direction, raw) is True
    assert _aligned_via_planner(direction, snapshot) is True
    assert _high_conviction(direction, raw) is True
    assert _high_conviction(direction, snapshot) is True


@pytest.mark.parametrize("direction,score,aligned", [
    ("long", 0.75, True), ("long", 0.25, False), ("long", -0.5, False),
    ("short", -0.75, True), ("short", -0.25, False), ("short", 0.5, False),
    ("flat", 1.0, False), ("flat", -1.0, False),
])
def test_aligned_thresholds_are_unchanged_away_from_the_boundary(direction, score, aligned):
    assert _aligned_via_planner(direction, score) is aligned
    if direction != "flat":
        assert _high_conviction(direction, score) is aligned


# ─── Bug: the conservative FTFC minimum ignores the trade's direction ───


def _ctx(direction: str, score: float) -> PlanContext:
    return PlanContext(direction=direction, conviction="medium",  # type: ignore[arg-type]
                       close=100.0, atr=2.0, trigger_high=101.0, trigger_low=99.0,
                       ftfc_score=score)


def _conservative(direction: str, score: float):
    return next(p for p in compute_persona_plans(_ctx(direction, score))
                if p.persona == "conservative")


@pytest.mark.parametrize("direction,score,takes", [
    ("long", 0.75, True), ("long", 0.30, True), ("long", 0.25, False), ("long", -0.75, False),
    ("short", -0.75, True), ("short", -0.30, True), ("short", -0.25, False), ("short", 0.75, False),
])
def test_conservative_minimum_follows_the_trade_direction(direction, score, takes):
    plan = _conservative(direction, score)
    assert (plan.position_size_pct > 0) is takes
    if not takes:
        assert "FTFC" in plan.rationale
        assert f"{score:+.2f}" in plan.rationale


def test_conservative_short_rationale_names_the_bearish_threshold():
    plan = _conservative("short", 0.75)
    assert plan.rationale == "Stand aside: FTFC alignment +0.75 above -0.30 threshold."


def test_conservative_long_rationale_is_unchanged():
    plan = _conservative("long", 0.10)
    assert plan.rationale == "Stand aside: FTFC alignment +0.10 below +0.30 threshold."


def test_flat_still_has_no_plans():
    assert compute_persona_plans(_ctx("flat", -0.75)) == []
