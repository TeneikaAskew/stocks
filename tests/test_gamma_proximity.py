"""Tests for lib/strategies/gamma_proximity.py — Track 3 gamma alerts.

Covers the six directional cases, no-fire conditions, dedup_key
stability, and the FTFC alignment filter for gate/flip alerts.

The directional mapping is the load-bearing contract:
  - King-approach from below   → CALL  (magnet-↑, empirically validated 2026-05-23)
  - King-approach from above   → PUT   (magnet-↓, empirically validated 2026-05-23)
  - Gate-break close > Gate    → CALL  (FTFC-gated: needs prev_day=UP)
  - Gate-break close < Gate    → PUT   (FTFC-gated: needs prev_day=DOWN)
  - Flip-cross close > flip    → CALL  (FTFC-gated: needs prev_day=UP)
  - Flip-cross close < flip    → PUT   (FTFC-gated: needs prev_day=DOWN)

`prev_day_dir=None` disables the FTFC filter (legacy / test default).
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

    def test_below_king_within_threshold_fires_call(self):
        summary = _summary(kings=[_level(580.0, kind="king")])
        # Price $577.50 = 0.43% below $580 — within 0.5%
        alerts = gp.evaluate_king_approach(577.50, summary)
        assert len(alerts) == 1
        a = alerts[0]
        assert a.kind == "gamma_king_approach"
        assert a.direction == "CALL"  # magnet-↑: expect continuation up to king
        assert a.level_kind == "king"
        assert a.level_strike == 580.0
        assert a.distance_pct < 0     # signed: below

    def test_above_king_within_threshold_fires_put(self):
        summary = _summary(kings=[_level(580.0, kind="king")])
        alerts = gp.evaluate_king_approach(582.50, summary)
        assert len(alerts) == 1
        a = alerts[0]
        assert a.direction == "PUT"   # magnet-↓: expect continuation down to king
        assert a.distance_pct > 0

    def test_exactly_at_king_fires_put_tie(self):
        # Edge case: price == king. Default to PUT (price has stalled
        # at the wall — empirically a coin flip; slight bias to magnet-↓
        # since flow more often pulled back down through the wall).
        summary = _summary(kings=[_level(580.0, kind="king")])
        alerts = gp.evaluate_king_approach(580.0, summary)
        assert len(alerts) == 1
        assert alerts[0].direction == "PUT"
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
        assert alerts[0].direction == "CALL"  # magnet-↑ from below

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
        # Construct a bar that triggers king (near 580) + flip (crossed
        # 578 upward in the same wide-range bar). Verifies the combined
        # evaluator wires all three sub-evaluators.
        summary = _summary(
            flip=578.0, regime="negative_gamma",
            kings=[_level(580.0, kind="king")],
            gates=[_level(585.0, kind="gate")],
        )
        # prev=577.5, close=580.1 — crosses flip 578 upward → flip CALL,
        # ends 0.017% above king → king PUT (magnet-↓),
        # does NOT cross gate 585 → no gate alert.
        alerts = gp.evaluate_all(price=580.1, prev_close=577.5, summary=summary)
        kinds = sorted(a.kind for a in alerts)
        assert kinds == ["gamma_flip_cross", "gamma_king_approach"]
        # Different directions now: flip CALL (entering positive gamma)
        # but king PUT (magnet-↓ from above 580.0).
        flip = next(a for a in alerts if a.kind == "gamma_flip_cross")
        king = next(a for a in alerts if a.kind == "gamma_king_approach")
        assert flip.direction == "CALL"
        assert king.direction == "PUT"

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
        assert alerts[0].direction == "CALL"  # below king → magnet-↑ to king


# ── FTFC alignment filter ────────────────────────────────────────────


class TestFtfcAlignment:
    """The gate/flip evaluators accept an optional `prev_day_dir` keyword
    that filters alerts whose direction fights the prior day's bias.

    Empirical justification (SPY/IWM/QQQ 30d, 2026-05-23):
      gate PUT against UP-prev-day:   39.7-46.6% continuation
      flip PUT against UP-prev-day:   27.8-50.0% continuation
      flip CALL against DOWN-prev-day: 27.3-57.1% continuation
      → all <50%, so aligned-only is the production rule.
    """

    # ── _ftfc_aligned helper ─────────────────────────────────────────

    @pytest.mark.parametrize("direction, prev, expected", [
        ("CALL", "UP",   True),
        ("CALL", "DOWN", False),
        ("CALL", "FLAT", False),  # FLAT blocks both directions
        ("CALL", None,   True),   # None disables filter
        ("PUT",  "UP",   False),
        ("PUT",  "DOWN", True),
        ("PUT",  "FLAT", False),
        ("PUT",  None,   True),
    ])
    def test_ftfc_aligned_table(self, direction, prev, expected):
        assert gp._ftfc_aligned(direction, prev) is expected

    # ── Gate-break × FTFC ───────────────────────────────────────────

    def test_gate_call_aligned_with_up_day_fires(self):
        summary = _summary(gates=[_level(585.0, kind="gate")])
        alerts = gp.evaluate_gate_break(
            prev_close=584.8, close=585.2, summary=summary, prev_day_dir="UP",
        )
        assert len(alerts) == 1
        assert alerts[0].direction == "CALL"

    def test_gate_call_against_down_day_skipped(self):
        summary = _summary(gates=[_level(585.0, kind="gate")])
        alerts = gp.evaluate_gate_break(
            prev_close=584.8, close=585.2, summary=summary, prev_day_dir="DOWN",
        )
        assert alerts == []

    def test_gate_put_aligned_with_down_day_fires(self):
        summary = _summary(gates=[_level(575.0, kind="gate")])
        alerts = gp.evaluate_gate_break(
            prev_close=575.4, close=574.6, summary=summary, prev_day_dir="DOWN",
        )
        assert len(alerts) == 1
        assert alerts[0].direction == "PUT"

    def test_gate_put_against_up_day_skipped(self):
        # The disaster case the backtest flagged: PUT gate-break in a
        # bullish-FTFC regime. 39.7% hit-rate across all 3 ETFs / 30d.
        summary = _summary(gates=[_level(575.0, kind="gate")])
        alerts = gp.evaluate_gate_break(
            prev_close=575.4, close=574.6, summary=summary, prev_day_dir="UP",
        )
        assert alerts == []

    def test_gate_flat_prev_day_blocks_both_directions(self):
        summary = _summary(gates=[
            _level(585.0, kind="gate"),
            _level(575.0, kind="gate"),
        ])
        # FLAT prev day = no FTFC signal; conservatively skip both
        up_alerts = gp.evaluate_gate_break(584.8, 585.2, summary, prev_day_dir="FLAT")
        down_alerts = gp.evaluate_gate_break(575.4, 574.6, summary, prev_day_dir="FLAT")
        assert up_alerts == []
        assert down_alerts == []

    def test_gate_none_prev_day_disables_filter(self):
        # Backwards compat — None preserves legacy unfiltered behavior
        summary = _summary(gates=[_level(575.0, kind="gate")])
        alerts = gp.evaluate_gate_break(
            prev_close=575.4, close=574.6, summary=summary, prev_day_dir=None,
        )
        assert len(alerts) == 1
        assert alerts[0].direction == "PUT"

    def test_gate_mixed_gates_filter_one_direction(self):
        # Two gates crossed in opposite directions on a wide bar.
        # With prev_day_dir=UP, only the upward break (CALL) survives.
        summary = _summary(gates=[
            _level(585.0, kind="gate"),
            _level(575.0, kind="gate"),
        ])
        # prev=586, close=574 — crosses 585 DOWN and 575 DOWN. Two PUT
        # alerts (no upward cross), both filtered out under UP-prev-day.
        alerts = gp.evaluate_gate_break(586.0, 574.0, summary, prev_day_dir="UP")
        assert alerts == []
        # Same crossings under DOWN-prev-day → both PUTs survive
        alerts = gp.evaluate_gate_break(586.0, 574.0, summary, prev_day_dir="DOWN")
        assert len(alerts) == 2
        assert all(a.direction == "PUT" for a in alerts)

    # ── Flip-cross × FTFC ───────────────────────────────────────────

    def test_flip_call_aligned_fires(self):
        summary = _summary(flip=578.0, regime="negative_gamma")
        alerts = gp.evaluate_flip_cross(
            prev_close=577.5, close=578.5, summary=summary, prev_day_dir="UP",
        )
        assert len(alerts) == 1
        assert alerts[0].direction == "CALL"

    def test_flip_call_against_skipped(self):
        # Worst-case in 30d backtest: flip CALL against DOWN-prev-day,
        # 27-57% hit. Skip.
        summary = _summary(flip=578.0, regime="negative_gamma")
        alerts = gp.evaluate_flip_cross(
            prev_close=577.5, close=578.5, summary=summary, prev_day_dir="DOWN",
        )
        assert alerts == []

    def test_flip_put_aligned_fires_strongest_signal(self):
        # PUT + aligned DOWN-prev-day was the strongest signal in the
        # entire 30d backtest (76.7% across 3 ETFs).
        summary = _summary(flip=578.0, regime="positive_gamma")
        alerts = gp.evaluate_flip_cross(
            prev_close=578.5, close=577.5, summary=summary, prev_day_dir="DOWN",
        )
        assert len(alerts) == 1
        assert alerts[0].direction == "PUT"
        assert alerts[0].regime == "negative_gamma"

    def test_flip_put_against_skipped(self):
        summary = _summary(flip=578.0, regime="positive_gamma")
        alerts = gp.evaluate_flip_cross(
            prev_close=578.5, close=577.5, summary=summary, prev_day_dir="UP",
        )
        assert alerts == []

    def test_flip_none_prev_day_disables_filter(self):
        summary = _summary(flip=578.0, regime="positive_gamma")
        # Both directions fire without filter
        up = gp.evaluate_flip_cross(577.5, 578.5, summary, prev_day_dir=None)
        down = gp.evaluate_flip_cross(578.5, 577.5, summary, prev_day_dir=None)
        assert len(up) == 1 and up[0].direction == "CALL"
        assert len(down) == 1 and down[0].direction == "PUT"

    # ── King is FTFC-independent ────────────────────────────────────

    def test_king_evaluator_takes_no_prev_day_dir(self):
        """King-approach API intentionally lacks `prev_day_dir`. Magnet
        works regardless of FTFC (75-77% both directions, both regimes
        in the SPY 14d backtest)."""
        summary = _summary(kings=[_level(580.0, kind="king")])
        # Should accept no prev_day_dir kwarg; calling with one is a TypeError
        alerts = gp.evaluate_king_approach(577.5, summary)
        assert len(alerts) == 1 and alerts[0].direction == "CALL"
        with pytest.raises(TypeError):
            gp.evaluate_king_approach(  # type: ignore[call-arg]
                577.5, summary, prev_day_dir="DOWN",
            )

    # ── evaluate_all forwards correctly ─────────────────────────────

    def test_evaluate_all_filters_gate_flip_but_not_king(self):
        # prev_day_dir=UP should fire king (magnet, no filter) +
        # gate CALL (aligned) + flip CALL (aligned), but not PUT-direction
        # gates/flips even if technically crossed.
        summary = _summary(
            flip=578.0, regime="negative_gamma",
            kings=[_level(580.0, kind="king")],
            gates=[_level(585.0, kind="gate")],
        )
        # prev=577.5, close=580.1: king above (PUT magnet),
        # flip 578 crossed UP (CALL — aligned with UP), gate 585 not crossed
        alerts = gp.evaluate_all(
            price=580.1, prev_close=577.5, summary=summary, prev_day_dir="UP",
        )
        kinds_dirs = sorted((a.kind, a.direction) for a in alerts)
        assert ("gamma_king_approach", "PUT") in kinds_dirs   # king PUT survives
        assert ("gamma_flip_cross", "CALL") in kinds_dirs     # flip CALL survives
        assert len(alerts) == 2

    def test_evaluate_all_against_ftfc_only_king_survives(self):
        # Same bar but prev_day_dir=DOWN: king still fires, flip CALL
        # gets filtered (against), gate not crossed anyway.
        summary = _summary(
            flip=578.0, regime="negative_gamma",
            kings=[_level(580.0, kind="king")],
            gates=[_level(585.0, kind="gate")],
        )
        alerts = gp.evaluate_all(
            price=580.1, prev_close=577.5, summary=summary, prev_day_dir="DOWN",
        )
        kinds = [a.kind for a in alerts]
        assert kinds == ["gamma_king_approach"]
        assert alerts[0].direction == "PUT"

    def test_evaluate_all_no_prev_day_dir_unfiltered(self):
        # Backwards compat: callers that don't pass prev_day_dir get
        # the legacy unfiltered behavior.
        summary = _summary(
            flip=578.0, regime="negative_gamma",
            kings=[_level(580.0, kind="king")],
            gates=[_level(585.0, kind="gate")],
        )
        alerts_no_filter = gp.evaluate_all(580.1, 577.5, summary)
        alerts_up_filter = gp.evaluate_all(580.1, 577.5, summary, prev_day_dir="UP")
        # Default = unfiltered = same set as the UP case in this scenario
        # (because the only fired alerts are CALL-direction flip + PUT-direction
        # king, and king has no filter, and UP allows CALL flip).
        kinds_no = sorted(a.kind for a in alerts_no_filter)
        kinds_up = sorted(a.kind for a in alerts_up_filter)
        assert kinds_no == kinds_up == ["gamma_flip_cross", "gamma_king_approach"]


# ── Dedup key ────────────────────────────────────────────────────────


class TestDedupKey:

    def test_same_alert_same_key(self):
        a1 = gp.GammaAlert(
            kind="gamma_king_approach", direction="CALL", level_kind="king",
            level_strike=580.0, distance_pct=-0.1, regime="positive_gamma",
        )
        a2 = gp.GammaAlert(
            kind="gamma_king_approach", direction="CALL", level_kind="king",
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
