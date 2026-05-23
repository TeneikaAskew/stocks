"""Tests for lib/strategies/gamma_proximity.py — Track 3 gamma alerts.

Covers the six directional cases (king-approach × from-below/above,
gate-break × up/down, flip-cross × up/down), no-fire conditions
(out-of-range, empty summary, prev_close=None), and dedup_key stability.

The directional mapping is the load-bearing contract:
  - King-approach from below   → PUT
  - King-approach from above   → CALL
  - Gate-break close > Gate    → CALL
  - Gate-break close < Gate    → PUT
  - Flip-cross close > flip    → CALL
  - Flip-cross close < flip    → PUT
"""
from __future__ import annotations

import pytest

from lib.gamma import GammaSummary, Level, SpotEstimate
from lib.strategies import gamma_proximity as gp


# ── Test fixtures ────────────────────────────────────────────────────


def _level(strike: float, kind: str = "none", gex: float = 0.0,
           tags: list[str] | None = None) -> Level:
    """Compact constructor — only strike / kind / tags matter for these tests."""
    return Level(
        strike=strike, gex=gex, net_gamma=gex,
        call_oi=0, put_oi=0,
        distance_pct=0.0, score=0.0,
        kind=kind, tags=tags or [kind],
    )


def _summary(
    *,
    spot_price: float = 580.0,
    flip: float | None = None,
    regime: str = "positive_gamma",
    kings: list[Level] | None = None,
    gates: list[Level] | None = None,
) -> GammaSummary:
    return GammaSummary(
        ticker="SPY",
        snapshot_date="2026-05-22",
        spot=SpotEstimate(price=spot_price, method="parity"),
        flip=flip,
        regime=regime,
        total_gex=0.0,
        levels=(kings or []) + (gates or []),
        kings=kings or [],
        gates=gates or [],
        flip_levels=[],
        window_pct=8.0,
    )


# ── King approach ────────────────────────────────────────────────────


class TestKingApproach:

    def test_below_king_within_threshold_fires_put(self):
        summary = _summary(kings=[_level(580.0, kind="king")])
        # Price $577.50 = 0.43% below $580 — within 0.5%
        alerts = gp.evaluate_king_approach(577.50, summary)
        assert len(alerts) == 1
        a = alerts[0]
        assert a.kind == "gamma_king_approach"
        assert a.direction == "PUT"   # approach-from-below = rejection-↓ thesis
        assert a.level_kind == "king"
        assert a.level_strike == 580.0
        assert a.distance_pct < 0     # signed: below

    def test_above_king_within_threshold_fires_call(self):
        summary = _summary(kings=[_level(580.0, kind="king")])
        alerts = gp.evaluate_king_approach(582.50, summary)
        assert len(alerts) == 1
        a = alerts[0]
        assert a.direction == "CALL"   # approach-from-above = rejection-↑ thesis
        assert a.distance_pct > 0

    def test_exactly_at_king_fires_call_tie(self):
        # Edge case: price == king. The implementation defaults to CALL
        # ("not strictly below"), which matches the "rejection-↑" reading
        # for a price that just touched the wall from above and stalled.
        summary = _summary(kings=[_level(580.0, kind="king")])
        alerts = gp.evaluate_king_approach(580.0, summary)
        assert len(alerts) == 1
        assert alerts[0].direction == "CALL"
        assert alerts[0].distance_pct == 0.0

    def test_outside_proximity_pct_no_fire(self):
        summary = _summary(kings=[_level(580.0, kind="king")])
        # Price $575 = 0.86% below — outside default 0.5%
        alerts = gp.evaluate_king_approach(575.0, summary)
        assert alerts == []

    def test_custom_proximity_pct(self):
        summary = _summary(kings=[_level(580.0, kind="king")])
        # $575 is 0.86% below; loosened threshold admits it
        alerts = gp.evaluate_king_approach(575.0, summary, proximity_pct=0.01)
        assert len(alerts) == 1
        assert alerts[0].direction == "PUT"

    def test_multiple_kings_each_fires_independently(self):
        # Both kings within range — should produce two alerts
        summary = _summary(
            spot_price=579.0,
            kings=[_level(580.0, kind="king"), _level(578.5, kind="king")],
        )
        alerts = gp.evaluate_king_approach(579.0, summary)
        assert len(alerts) == 2
        strikes = sorted(a.level_strike for a in alerts)
        assert strikes == [578.5, 580.0]

    def test_no_kings_no_fire(self):
        summary = _summary(kings=[])
        assert gp.evaluate_king_approach(580.0, summary) == []

    def test_none_summary_no_fire_no_crash(self):
        # Rule 3.7 — caller must handle missing summary; we don't fabricate.
        assert gp.evaluate_king_approach(580.0, None) == []  # type: ignore[arg-type]

    def test_zero_or_negative_price_no_fire(self):
        summary = _summary(kings=[_level(580.0, kind="king")])
        assert gp.evaluate_king_approach(0.0, summary) == []
        assert gp.evaluate_king_approach(-1.0, summary) == []


# ── Gate break ───────────────────────────────────────────────────────


class TestGateBreak:

    def test_break_upward_fires_call(self):
        summary = _summary(gates=[_level(585.0, kind="gate")])
        alerts = gp.evaluate_gate_break(prev_close=584.8, close=585.2, summary=summary)
        assert len(alerts) == 1
        a = alerts[0]
        assert a.kind == "gamma_gate_break"
        assert a.direction == "CALL"
        assert a.level_strike == 585.0
        assert a.distance_pct > 0

    def test_break_downward_fires_put(self):
        summary = _summary(gates=[_level(575.0, kind="gate")])
        alerts = gp.evaluate_gate_break(prev_close=575.4, close=574.6, summary=summary)
        assert len(alerts) == 1
        assert alerts[0].direction == "PUT"
        assert alerts[0].distance_pct < 0

    def test_close_does_not_cross_no_fire(self):
        summary = _summary(gates=[_level(585.0, kind="gate")])
        # prev=584.8, close=584.9 — both below 585, no cross
        assert gp.evaluate_gate_break(584.8, 584.9, summary) == []

    def test_touch_only_no_fire(self):
        # Plan §Track 3 tuning: "Gate breaks on close, not touch."
        # If close == gate, no cross condition is met (uses strict
        # inequality on the side just entered).
        summary = _summary(gates=[_level(585.0, kind="gate")])
        # prev=584.8 (below), close=585.0 (at). Not crossed_up because
        # crossed_up requires 584.8 <= 585.0 < 585.0 = False.
        assert gp.evaluate_gate_break(584.8, 585.0, summary) == []

    def test_prev_close_none_no_fire(self):
        # First bar of session — no prev_close to compare against
        summary = _summary(gates=[_level(585.0, kind="gate")])
        assert gp.evaluate_gate_break(None, 585.5, summary) == []

    def test_multiple_gates_only_crossed_one_fires(self):
        summary = _summary(gates=[
            _level(585.0, kind="gate"),
            _level(575.0, kind="gate"),
        ])
        # Only crosses 585 upward
        alerts = gp.evaluate_gate_break(584.8, 585.5, summary)
        assert len(alerts) == 1
        assert alerts[0].level_strike == 585.0
        assert alerts[0].direction == "CALL"

    def test_no_gates_no_fire(self):
        summary = _summary(gates=[])
        assert gp.evaluate_gate_break(584.0, 586.0, summary) == []


# ── Flip cross ───────────────────────────────────────────────────────


class TestFlipCross:

    def test_cross_upward_fires_call_positive_regime(self):
        # Entering positive gamma (pinning) regime
        summary = _summary(flip=578.0, regime="negative_gamma")
        alerts = gp.evaluate_flip_cross(prev_close=577.5, close=578.5, summary=summary)
        assert len(alerts) == 1
        a = alerts[0]
        assert a.kind == "gamma_flip_cross"
        assert a.direction == "CALL"
        assert a.level_kind == "flip"
        assert a.level_strike == 578.0
        # New regime, not the snapshot's stale regime
        assert a.regime == "positive_gamma"

    def test_cross_downward_fires_put_negative_regime(self):
        summary = _summary(flip=578.0, regime="positive_gamma")
        alerts = gp.evaluate_flip_cross(prev_close=578.5, close=577.5, summary=summary)
        assert len(alerts) == 1
        assert alerts[0].direction == "PUT"
        assert alerts[0].regime == "negative_gamma"

    def test_no_cross_no_fire(self):
        summary = _summary(flip=578.0)
        # Both above
        assert gp.evaluate_flip_cross(578.2, 578.4, summary) == []
        # Both below
        assert gp.evaluate_flip_cross(577.5, 577.8, summary) == []

    def test_no_flip_no_fire(self):
        summary = _summary(flip=None)
        assert gp.evaluate_flip_cross(577.5, 578.5, summary) == []

    def test_prev_close_none_no_fire(self):
        summary = _summary(flip=578.0)
        assert gp.evaluate_flip_cross(None, 578.5, summary) == []


# ── Combined evaluator ───────────────────────────────────────────────


class TestEvaluateAll:

    def test_all_three_alerts_can_fire_on_one_bar(self):
        # Construct a bar that triggers king (near 580) + gate (crossed 585)
        # + flip (crossed 578 upward in the same wide-range bar).
        # Pathological but verifies the combined evaluator wires through.
        summary = _summary(
            flip=578.0, regime="negative_gamma",
            kings=[_level(580.0, kind="king")],
            gates=[_level(585.0, kind="gate")],
        )
        # prev=577.5, close=585.5 — crosses flip up, crosses gate up,
        # and ends within proximity of king (585.5 vs 580 = 0.94% — NOT
        # within 0.5%, so no king alert). Pick close=580.1 instead.
        alerts = gp.evaluate_all(price=580.1, prev_close=577.5, summary=summary)
        # 580.1 vs 580 king = 0.017% within → king fires (above → CALL)
        # 577.5 → 580.1 crosses flip 578 upward → flip fires (CALL)
        # 577.5 → 580.1 does NOT cross gate 585 → no gate fire
        kinds = sorted(a.kind for a in alerts)
        assert kinds == ["gamma_flip_cross", "gamma_king_approach"]
        # Both should be CALL (above king + entering positive gamma)
        assert all(a.direction == "CALL" for a in alerts)

    def test_empty_summary_no_alerts(self):
        summary = _summary()  # no kings, no gates, no flip
        assert gp.evaluate_all(580.0, 579.5, summary) == []

    def test_first_bar_prev_close_none_only_king_can_fire(self):
        # gate_break and flip_cross require prev_close; only king_approach
        # is reachable on the first bar of a session.
        summary = _summary(
            flip=578.0,
            kings=[_level(580.0, kind="king")],
            gates=[_level(585.0, kind="gate")],
        )
        alerts = gp.evaluate_all(price=579.5, prev_close=None, summary=summary)
        # 579.5 vs 580 = 0.086% — within proximity
        assert len(alerts) == 1
        assert alerts[0].kind == "gamma_king_approach"
        assert alerts[0].direction == "PUT"   # below king


# ── Dedup key ────────────────────────────────────────────────────────


class TestDedupKey:

    def test_same_alert_same_key(self):
        a1 = gp.GammaAlert(
            kind="gamma_king_approach", direction="PUT", level_kind="king",
            level_strike=580.0, distance_pct=-0.1, regime="positive_gamma",
        )
        a2 = gp.GammaAlert(
            kind="gamma_king_approach", direction="PUT", level_kind="king",
            level_strike=580.0, distance_pct=-0.3, regime="positive_gamma",
        )
        # Same kind + strike → dedup_key collides even though distance_pct differs
        assert a1.dedup_key() == a2.dedup_key()

    def test_different_kind_different_key(self):
        a1 = gp.GammaAlert(
            kind="gamma_king_approach", direction="PUT", level_kind="king",
            level_strike=580.0, distance_pct=0.0, regime="positive_gamma",
        )
        a2 = gp.GammaAlert(
            kind="gamma_gate_break", direction="PUT", level_kind="gate",
            level_strike=580.0, distance_pct=0.0, regime="positive_gamma",
        )
        assert a1.dedup_key() != a2.dedup_key()

    def test_different_strike_different_key(self):
        a1 = gp.GammaAlert(
            kind="gamma_king_approach", direction="PUT", level_kind="king",
            level_strike=580.0, distance_pct=0.0, regime="positive_gamma",
        )
        a2 = gp.GammaAlert(
            kind="gamma_king_approach", direction="PUT", level_kind="king",
            level_strike=585.0, distance_pct=0.0, regime="positive_gamma",
        )
        assert a1.dedup_key() != a2.dedup_key()
