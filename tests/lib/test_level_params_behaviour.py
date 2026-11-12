"""FEAT-STRAT-001 per-ticker params, done_when 2 (behavioural half) and
done_when 9: the level and plan code read the ticker's parameter rows, and a
parameter that is not ok publishes no price.

Every parameter here is read from level_param_policy and ticker_level_params
(created from gcp/schema.sql in SQLite) through lib.strat_levels
load_level_params's own SQL, so a single row change is the only difference
between the two sides of each comparison. On the #1753 head neither the
tables, the loader nor the params argument exist.
"""
from __future__ import annotations

from datetime import date

import pytest

from lib.agents.trade_planner import PlanContext, compute_persona_plans
from lib.strat_levels import (
    PARAM_OK, SessionLevels, build_session_levels, orb_only_text, premarket_filter_inputs,
)
from tests.lib import strat_2026_11_06 as fx
from tests.lib.level_params_fixtures import LEGACY_1753_VALUES, ParamsDb, legacy_db
from tests.lib.session_levels_helpers import basis

D = date(2026, 11, 6)
EFF = date(2026, 11, 3)


def _qqq_inputs():
    d = fx.daily("QQQ")
    from lib.indicators import calculate_atr
    atrs = {"atr_14": fx.prior_atr("QQQ"),
            "atr_5": float(calculate_atr(d["High"], d["Low"], d["Close"], 5).iloc[-1])}
    return d, atrs


# ── one row moves a side ──────────────────────────────────────────────


def _long_level_at_2_5_atr(params):
    """Prior close 100, ATR(14) 2, PDH at 105 (2.5 ATR above) and PDL at
    98 (1 ATR below), rebuilt through SessionLevels.from_basis with the
    loaded parameters."""
    b = basis({"PDH": 105.0, "PDL": 98.0}, prior_close=100.0, atr=2.0,
              ticker="SPY", session_date=D, params=params)
    return SessionLevels.from_basis(b, params=params)


def test_one_row_change_moves_the_long_side_to_orb_only():
    db = legacy_db(["SPY"], effective_from=EFF)
    before = _long_level_at_2_5_atr(db.load(["SPY"], D)["SPY"])
    assert before.long.regime == "normal"
    assert before.long.trigger["name"] == "PDH"
    assert before.long.distance_atr == pytest.approx(2.5)
    assert before.short.trigger["name"] == "PDL"

    # trigger_window_long_atr 3.0 -> 2.0: one row.
    db.write("SPY", {"trigger_window_long_atr": 2.0}, effective_from=EFF)
    after_params = db.load(["SPY"], D)["SPY"]
    after = _long_level_at_2_5_atr(after_params)
    assert after.long.regime == "orb_only"
    assert after.long.trigger is None
    assert after.long.reason == "next_level_outside_window"
    assert after.long.window["value"] == 2.0
    # The short side reads its own row, unchanged.
    assert after.short.trigger == before.short.trigger
    # The copy states the ticker's own window, not 3.
    text = orb_only_text(after.long.reason, "long", after.long.window)
    assert "2 x ATR(14)" in text and "SPY" in text and "3 x" not in text


def test_the_same_row_change_on_the_committed_fixture():
    """On QQQ's 2026-11-06 inputs: a long window just above the nearest long
    trigger's distance publishes it, one just below gives orb_only."""
    d, atrs = _qqq_inputs()
    db = legacy_db(["QQQ"], effective_from=EFF, overrides={"trigger_window_long_atr": 50.0})
    pm = fx.session_premarket("QQQ")
    wide = build_session_levels("QQQ", D, d, atrs, pm, db.load(["QQQ"], D)["QQQ"])
    dist = wide.long.distance_atr
    assert wide.long.trigger is not None and dist > 0

    db.write("QQQ", {"trigger_window_long_atr": dist + 0.01}, effective_from=EFF)
    inside = build_session_levels("QQQ", D, d, atrs, pm, db.load(["QQQ"], D)["QQQ"])
    assert inside.long.trigger == wide.long.trigger

    db.write("QQQ", {"trigger_window_long_atr": dist - 0.01}, effective_from=EFF)
    outside = build_session_levels("QQQ", D, d, atrs, pm, db.load(["QQQ"], D)["QQQ"])
    assert outside.long.trigger is None and outside.long.regime == "orb_only"
    assert outside.short.trigger == wide.short.trigger


def test_the_two_sides_read_separate_windows():
    d, atrs = _qqq_inputs()
    db = legacy_db(["QQQ"], effective_from=EFF,
                   overrides={"trigger_window_long_atr": 50.0, "trigger_window_short_atr": 0.01})
    s = build_session_levels("QQQ", D, d, atrs, fx.session_premarket("QQQ"),
                             db.load(["QQQ"], D)["QQQ"])
    assert s.long.trigger is not None
    assert s.short.trigger is None and s.short.reason == "next_level_outside_window"


# ── non-ok window parameters ─────────────────────────────────────────


def test_insufficient_history_gives_both_sides_params_insufficient_history():
    """A ticker with 100 daily bars has every key insufficient_history
    (sample 100 of 250): no trigger on either side, the reason is the
    parameter's status and the copy names the parameter and its sample."""
    d, atrs = _qqq_inputs()
    db = ParamsDb()
    db.write("QQQ", {k: None for k in LEGACY_1753_VALUES}, effective_from=EFF,
             status="insufficient_history", sample_n=100)
    s = build_session_levels("QQQ", D, d, atrs, fx.session_premarket("QQQ"),
                             db.load(["QQQ"], D)["QQQ"])
    for side in (s.long, s.short):
        assert side.trigger is None and side.regime == "orb_only"
        assert side.reason == "params_insufficient_history"
        assert side.targets == [] and side.stop is None and side.ladder == []
        text = orb_only_text(side.reason, side.side, side.window)
        assert side.window["key"] in text and "250" in text and "100" in text
    assert s.pmg_status == "insufficient_history" and s.pmg_zones == []


def test_basis_mismatch_gives_no_trigger():
    d, atrs = _qqq_inputs()
    db = legacy_db(["QQQ"], effective_from=EFF)
    db.set_policy("atr_basis", effective_from=D, extra='{"column": "atr_5"}')
    lp = db.load(["QQQ"], D)["QQQ"]
    s = build_session_levels("QQQ", D, d, atrs, fx.session_premarket("QQQ"), lp)
    assert s.atr_basis == "atr_5" and s.atr == pytest.approx(atrs["atr_5"])
    assert s.long.reason == s.short.reason == "params_basis_mismatch"
    assert s.long.trigger is None and s.short.trigger is None


def test_a_ticker_with_no_one_minute_bars_gets_premarket_unfiltered():
    """Calibration writes pm_stale_print_atr and pm_spike_atr as
    insufficient_history (sample 0) for a ticker with no one-minute bars
    (Design 5). The fetcher's
    filter inputs then carry that status and no thresholds, the filter does
    not run, and the builder refuses the snapshot: premarket_unfiltered, no
    premarket high or low candidate, the reference is the prior close."""
    d, atrs = _qqq_inputs()
    db = legacy_db(["QQQ"], effective_from=EFF,
                   statuses={"pm_stale_print_atr": "insufficient_history",
                             "pm_spike_atr": "insufficient_history"})
    lp = db.load(["QQQ"], D)["QQQ"]
    f = premarket_filter_inputs(lp, atrs)
    assert f["status"] == "insufficient_history"
    assert f["stale_print_atr"] is None and f["spike_atr"] is None
    pm = fx.premarket_context("QQQ", params=lp)
    assert pm["filtered"] is False
    assert pm["excluded_prior_close_prints"] is None and pm["excluded_spike_prints"] is None
    snap = {"date": D.isoformat(), "pre_high": pm["pre_high"], "pre_low": pm["pre_low"],
            "pre_vwap": pm["pre_vwap"], "gap_pct": pm["gap_pct"], "pre_filter_status": f["status"]}
    s = build_session_levels("QQQ", D, d, atrs, snap, lp)
    assert s.premarket_status == "premarket_unfiltered" and s.premarket is None
    assert s.reference == pytest.approx(float(d["Close"].iloc[-1]))
    assert not any(c["name"] in ("PMK_H", "PMK_L") for c in s.long.candidates + s.short.candidates)


# ── persona plans ─────────────────────────────────────────────────────


def _plans(lp, direction="long"):
    b = basis({"PDH": 105.0, "PDL": 98.0}, prior_close=100.0, atr=2.0,
              ticker="SPY", session_date=D, params=lp)
    levels = SessionLevels.from_basis(b, params=lp)
    ctx = PlanContext(direction=direction, conviction="medium", close=100.0, atr=2.0,
                      levels=levels, ftfc_score=1.0)
    return {p.persona: p for p in compute_persona_plans(ctx)}


def test_a_non_ok_persona_key_nulls_that_persona_and_names_the_parameter():
    db = legacy_db(["SPY"], effective_from=EFF,
                   statuses={"stop_neutral_atr": "insufficient_history"})
    plans = _plans(db.load(["SPY"], D)["SPY"])
    n = plans["neutral"]
    assert n.entry_zone is None and n.stop is None and n.targets == []
    assert n.risk_metrics is None and n.position_size_pct == 0.0
    assert "stop_neutral_atr" in n.rationale and "SPY" in n.rationale
    # The other personas read their own keys, all ok.
    for persona in ("aggressive", "conservative"):
        assert plans[persona].entry_zone is not None and plans[persona].stop is not None


def test_persona_offsets_come_from_the_rows():
    """Changing stop_aggressive_atr from 2.0 to 1.5 moves the aggressive
    stop by 0.5 ATR and nothing else."""
    db = legacy_db(["SPY"], effective_from=EFF)
    a = _plans(db.load(["SPY"], D)["SPY"])
    db.write("SPY", {"stop_aggressive_atr": 1.5}, effective_from=EFF)
    b = _plans(db.load(["SPY"], D)["SPY"])
    assert b["aggressive"].stop - a["aggressive"].stop == pytest.approx(0.5 * 2.0)
    assert b["aggressive"].entry_zone == a["aggressive"].entry_zone
    assert b["neutral"] == a["neutral"] and b["conservative"] == a["conservative"]


def test_no_positive_target_truncates_the_target_list():
    """target_neutral_3_r no_positive_target: the neutral plan publishes T1
    and T2 and no third price."""
    db = legacy_db(["SPY"], effective_from=EFF,
                   statuses={"target_neutral_3_r": "no_positive_target"})
    plans = _plans(db.load(["SPY"], D)["SPY"])
    assert len(plans["neutral"].targets) == 2
    assert len(plans["aggressive"].targets) == 3


@pytest.mark.parametrize("cut", ["target_aggressive_2_r", "target_aggressive_3_r"])
def test_analog_stretch_never_moves_a_target_before_t3(cut):
    """The aggressive day-5 analog stretch applies to the persona's top
    target, T3. With T2 or T3 no_positive_target the plan publishes fewer
    targets and none of them is stretched: T1 (and T2) stay at their
    calibrated R multiples of the plan's own risk."""
    lp = legacy_db(["SPY"], effective_from=EFF,
                   statuses={cut: "no_positive_target"}).load(["SPY"], D)["SPY"]
    b = basis({"PDH": 105.0, "PDL": 98.0}, prior_close=100.0, atr=2.0,
              ticker="SPY", session_date=D, params=lp)
    levels = SessionLevels.from_basis(b, params=lp)
    ctx = PlanContext(direction="long", conviction="medium", close=100.0, atr=2.0,
                      levels=levels, ftfc_score=1.0, analog_median_day_5_pct=40.0)
    agg = {p.persona: p for p in compute_persona_plans(ctx)}["aggressive"]
    mid = (agg.entry_zone.low + agg.entry_zone.high) / 2
    risk = mid - agg.stop
    multiples = []
    for k in (1, 2, 3):
        if not lp.ok(f"target_aggressive_{k}_r"):
            break
        multiples.append(lp.value(f"target_aggressive_{k}_r"))
    assert len(agg.targets) == len(multiples) < 3
    for t, r in zip(agg.targets, multiples):
        assert t == pytest.approx(mid + r * risk, abs=0.01)
    # With every target published the same analog stretches T3 only.
    full = legacy_db(["SPY"], effective_from=EFF).load(["SPY"], D)["SPY"]
    b = basis({"PDH": 105.0, "PDL": 98.0}, prior_close=100.0, atr=2.0,
              ticker="SPY", session_date=D, params=full)
    ctx = PlanContext(direction="long", conviction="medium", close=100.0, atr=2.0,
                      levels=SessionLevels.from_basis(b, params=full), ftfc_score=1.0,
                      analog_median_day_5_pct=40.0)
    agg = {p.persona: p for p in compute_persona_plans(ctx)}["aggressive"]
    mid = (agg.entry_zone.low + agg.entry_zone.high) / 2
    assert agg.targets[0] == pytest.approx(mid + 2.0 * (mid - agg.stop), abs=0.01)
    assert agg.targets[2] == pytest.approx(mid * 1.40, abs=0.01)


@pytest.mark.parametrize("key", sorted(LEGACY_1753_VALUES))
def test_no_published_price_comes_from_a_non_ok_parameter(key):
    """For every key: with that one key not ok, every price the levels and
    plans publish is either unchanged from the all-ok build or absent."""
    def published(lp):
        b = basis({"PDH": 105.0, "PDL": 98.0, "PWH": 106.0, "PWL": 96.5}, prior_close=100.0,
                  atr=2.0, ticker="SPY", session_date=D, params=lp)
        levels = SessionLevels.from_basis(b, params=lp)
        out = set()
        for side in (levels.long, levels.short):
            for r in ([side.trigger, side.stop] + side.targets):
                if r:
                    out.add((side.side, "level", r["name"], round(r["price"], 4)))
        # ATR levels spec: the kept ATR rungs the brief prints.
        for r in levels.atr_rungs:
            out.add(("atr", "rung", r["name"], round(r["price"], 4)))
        for direction in ("long", "short"):
            ctx = PlanContext(direction=direction, conviction="medium", close=100.0, atr=2.0,
                              levels=levels, ftfc_score=1.0)
            for p in compute_persona_plans(ctx):
                tag = (direction, p.persona)
                if p.entry_zone is not None:
                    out.add(tag + ("entry", round(p.entry_zone.low, 4), round(p.entry_zone.high, 4)))
                if p.stop is not None:
                    out.add(tag + ("stop", round(p.stop, 4)))
                for i, t in enumerate(p.targets):
                    out.add(tag + (f"T{i + 1}", round(t, 4)))
        return out

    ok = published(legacy_db(["SPY"], effective_from=EFF).load(["SPY"], D)["SPY"])
    db = legacy_db(["SPY"], effective_from=EFF, statuses={key: "insufficient_history"})
    lp = db.load(["SPY"], D)["SPY"]
    assert lp.status(key) != PARAM_OK
    bad = published(lp)
    assert bad <= ok, sorted(bad - ok)
    # gap_fill_flag_atr only labels a prior-close target; it moves no price.
    assert bad != ok or key in ("level_cluster_atr", "pm_spike_atr", "pm_stale_print_atr",
                                "gap_fill_flag_atr"), \
        f"{key} not ok changed nothing it publishes"
