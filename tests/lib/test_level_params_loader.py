"""FEAT-STRAT-001 per-ticker params, done_when 1: parameter tables and loader.

level_param_policy and ticker_level_params are created in SQLite from the DDL
and policy seed committed in gcp/schema.sql, and read with
lib.strat_levels.load_level_params's own SQL. On the #1753 head neither the
tables nor the function exist.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from lib.strat_levels import (
    PARAMS_BASIS_MISMATCH, PARAMS_UNAVAILABLE, LevelParamsUnavailable,
    LevelParams, LevelParamUnavailable, load_level_params, policy_wide_param,
)
from tests.lib.level_params_fixtures import LEGACY_1753_VALUES, ParamsDb, legacy_db, seeded_policy

DESIGN_2_KEYS = set(LEGACY_1753_VALUES)
D = date(2026, 11, 9)


def test_schema_seeds_the_design_2_policy_and_no_ticker_values():
    db = ParamsDb()
    policy = seeded_policy()
    assert set(policy) == DESIGN_2_KEYS | {"atr_basis", "calibration_universe",
                                           "exit_legs", "entry_cutoff_et", "atr_rung_anchors",
                                           "plan_target_level_types", "plan_target_marks_atr",
                                           "ladder_history_sessions"}
    assert policy["atr_basis"]["extra"] == {"column": "atr_14"}
    assert {p["effective_from"] for p in policy.values()} == {"2015-01-02"}
    assert policy["trigger_window_long_atr"]["statistic_q"] == 0.99
    assert policy["trigger_window_long_atr"]["lookback_sessions"] == 750
    assert policy["trigger_window_long_atr"]["min_sample"] == 250
    assert policy["pm_spike_atr"]["statistic_q"] == 0.999
    assert policy["stop_aggressive_atr"]["statistic_q"] == 0.90
    assert policy["target_conservative_2_r"]["statistic_q"] == 0.50
    assert db.query("SELECT COUNT(*) AS n FROM ticker_level_params")["n"].iloc[0] == 0
    # The 23 Design 2 keys, the exits spec's two policy_seed keys and the
    # ATR levels spec's three.
    assert len(DESIGN_2_KEYS) == 28


def test_two_versions_a_session_between_them_reads_the_earlier():
    db = ParamsDb()
    db.write("SPY", {"trigger_window_long_atr": 2.61}, effective_from=date(2026, 11, 3))
    db.write("SPY", {"trigger_window_long_atr": 2.40}, effective_from=date(2026, 11, 7))
    p = db.load(["SPY"], date(2026, 11, 6))["SPY"].param("trigger_window_long_atr")
    assert p.value == 2.61 and p.effective_from == "2026-11-03"
    p = db.load(["SPY"], date(2026, 11, 7))["SPY"].param("trigger_window_long_atr")
    assert p.value == 2.40 and p.effective_from == "2026-11-07"
    # Recorded with the row: method, sample, input range, run id.
    assert p.method_id == "fixture" and p.sample_n == 750
    assert p.input_from == "2023-01-03" and p.input_to == "2026-11-07" and p.run_id


def test_ten_tickers_issue_exactly_one_query():
    db = ParamsDb()
    tickers = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "AVGO"]
    for t in tickers:
        db.write(t, {"trigger_window_long_atr": 2.5}, effective_from=date(2026, 11, 6))
    out = db.load(tickers, date(2026, 11, 6))
    assert len(db.queries) == 1
    assert sorted(out) == sorted(tickers)
    assert all(out[t].value("trigger_window_long_atr") == 2.5 for t in tickers)


@pytest.mark.parametrize("table", ["ticker_level_params", "level_param_policy"])
def test_a_dropped_table_raises(table):
    db = ParamsDb()
    db.drop(table)
    with pytest.raises(LevelParamsUnavailable):
        db.load(["SPY"], date(2026, 11, 6))


def test_a_failed_query_and_an_empty_policy_raise():
    def broken(sql, params=None):
        raise RuntimeError("connection reset")

    with pytest.raises(LevelParamsUnavailable):
        load_level_params(broken, ["SPY"], date(2026, 11, 6))
    db = ParamsDb()
    db.conn.execute("DELETE FROM level_param_policy")
    with pytest.raises(LevelParamsUnavailable):
        db.load(["SPY"], date(2026, 11, 6))


def test_an_unknown_ticker_gets_params_unavailable_for_every_key():
    db = ParamsDb()
    lp = db.load(["ZZZZ"], date(2026, 11, 6))["ZZZZ"]
    assert {k: lp.status(k) for k in DESIGN_2_KEYS} == {k: PARAMS_UNAVAILABLE for k in DESIGN_2_KEYS}
    with pytest.raises(LevelParamUnavailable) as exc:
        lp.value("trigger_window_long_atr")
    assert exc.value.key == "trigger_window_long_atr" and exc.value.status == PARAMS_UNAVAILABLE


def test_a_non_ok_status_is_typed_and_has_no_value():
    db = ParamsDb()
    db.write("NEWCO", {"trigger_window_long_atr": None}, effective_from=date(2026, 11, 6),
             status="insufficient_history", sample_n=100)
    lp = db.load(["NEWCO"], date(2026, 11, 6))["NEWCO"]
    p = lp.param("trigger_window_long_atr")
    assert p.status == "insufficient_history" and p.value is None
    assert p.sample_n == 100 and p.min_sample == 250
    with pytest.raises(LevelParamUnavailable):
        lp.value("trigger_window_long_atr")


def _atr14_history(db):
    for t, v in (("SPY", 2.61), ("QQQ", 2.36)):
        db.write(t, {"trigger_window_long_atr": v, "trigger_window_short_atr": v},
                 effective_from=date(2026, 11, 3))


def test_partial_calibration_failure_across_a_basis_change():
    """Policy switches atr_basis from atr_14 to atr_5 effective D; the job
    writes atr_5 rows for SPY and fails for QQQ. SPY reads its atr_5 rows;
    QQQ's keys are params_basis_mismatch on D and never its atr_14 values."""
    db = ParamsDb()
    _atr14_history(db)
    db.set_policy("atr_basis", effective_from=D, extra='{"column": "atr_5"}')
    db.write("SPY", {"trigger_window_long_atr": 4.10, "trigger_window_short_atr": 3.90},
             effective_from=D, atr_basis="atr_5", source="nightly")
    out = db.load(["SPY", "QQQ"], D)
    assert out["SPY"].atr_basis == "atr_5"
    assert out["SPY"].value("trigger_window_long_atr") == 4.10
    assert out["SPY"].param("trigger_window_long_atr").atr_basis == "atr_5"
    for key in ("trigger_window_long_atr", "trigger_window_short_atr"):
        assert out["QQQ"].status(key) == PARAMS_BASIS_MISMATCH
        with pytest.raises(LevelParamUnavailable):
            out["QQQ"].value(key)
    # The session before D still reads atr_14 rows for both.
    before = db.load(["SPY", "QQQ"], date(2026, 11, 6))
    assert before["SPY"].atr_basis == "atr_14" and before["SPY"].value("trigger_window_long_atr") == 2.61
    assert before["QQQ"].value("trigger_window_long_atr") == 2.36


def test_basis_transition_history_run_then_policy_row():
    """A new-basis history run is written beside the old rows, then the
    policy row takes effect on D. A session before D reads the same values
    before the history run, after it and after D; a session on or after D
    reads the new-basis rows."""
    db = ParamsDb()
    _atr14_history(db)
    before_d = date(2026, 11, 6)

    def snapshot(session):
        out = db.load(["SPY", "QQQ"], session)
        return {t: {k: (p.status, p.value, p.atr_basis) for k, p in lp.params.items()}
                for t, lp in out.items()}

    s0 = snapshot(before_d)
    for t, v in (("SPY", 4.10), ("QQQ", 3.70)):
        for eff in (date(2026, 11, 3), date(2026, 11, 6), D):
            db.write(t, {"trigger_window_long_atr": v, "trigger_window_short_atr": v},
                     effective_from=eff, atr_basis="atr_5", source="history")
    s1 = snapshot(before_d)
    assert snapshot(D) == {t: {k: v for k, v in s1[t].items()} for t in s1}  # still atr_14 before the policy row
    db.set_policy("atr_basis", effective_from=D, extra='{"column": "atr_5"}')
    s2 = snapshot(before_d)
    assert s0 == s1 == s2
    after = db.load(["SPY", "QQQ"], D)
    assert after["SPY"].value("trigger_window_long_atr") == 4.10
    assert after["QQQ"].value("trigger_window_long_atr") == 3.70
    assert after["QQQ"].param("trigger_window_long_atr").atr_basis == "atr_5"


def test_level_params_round_trip_through_a_basis_dict():
    from lib.strat_levels import LevelParams
    db = ParamsDb()
    db.write("SPY", {"trigger_window_long_atr": 2.61}, effective_from=date(2026, 11, 3))
    lp = db.load(["SPY"], date(2026, 11, 6))["SPY"]
    back = LevelParams.from_basis("SPY", date(2026, 11, 6), lp.to_basis())
    assert back.to_basis() == lp.to_basis()
    assert back.value("trigger_window_long_atr") == 2.61
    assert back.status("pm_spike_atr") == PARAMS_UNAVAILABLE


def test_a_retained_value_carries_its_own_policy_versions_metadata():
    """Codex P2 on e4bb463e: a policy change for a key takes effect, but the
    ticker's replacement calibration has not succeeded, so the loader keeps
    the older value. Its quantile, minimum sample and lookback are those of
    the policy version it was calibrated under, never the version in force;
    a key with no calibrated row carries the version in force."""
    db = ParamsDb()
    db.write("SPY", {"trigger_window_long_atr": 2.61}, effective_from=date(2026, 11, 3))
    db.conn.execute(
        "INSERT INTO level_param_policy (param_key, method_id, statistic_q, lookback_sessions, "
        "min_sample, extra, effective_from) SELECT param_key, method_id, 0.90, 1500, 1000, extra, "
        "'2026-11-05' FROM level_param_policy WHERE param_key IN "
        "('trigger_window_long_atr', 'trigger_window_short_atr') AND effective_from = '2015-01-02'")
    db.conn.commit()
    pol = seeded_policy()["trigger_window_long_atr"]
    p = db.load(["SPY"], date(2026, 11, 6))["SPY"]
    kept = p.param("trigger_window_long_atr")
    assert kept.value == 2.61 and kept.policy_effective_from == "2015-01-02"
    assert (kept.statistic_q, kept.min_sample, kept.lookback_sessions) == \
        (pol["statistic_q"], pol["min_sample"], pol["lookback_sessions"])
    missing = p.param("trigger_window_short_atr")
    assert (missing.statistic_q, missing.min_sample, missing.lookback_sessions) == (0.90, 1000, 1500)


def test_a_row_naming_an_absent_policy_version_raises():
    db = ParamsDb()
    db.write("SPY", {"trigger_window_long_atr": 2.61}, effective_from=date(2026, 11, 3))
    db.conn.execute("UPDATE ticker_level_params SET policy_effective_from = '2020-01-02'")
    db.conn.commit()
    with pytest.raises(LevelParamsUnavailable, match="policy version"):
        db.load(["SPY"], date(2026, 11, 6))


# ── ATR levels spec (2026-11-11): the policy rows ──────────────────────


def test_schema_seeds_the_atr_rung_policy_rows():
    policy = seeded_policy()
    assert policy["atr_rung_anchors"]["method_id"] == "policy"
    assert policy["atr_rung_anchors"]["extra"] == {"anchors": ["PDH", "PDL", "PMK_H", "PMK_L"]}
    for key, seed in (("atr_rung_step_atr", 0.5), ("atr_rung_max_atr", 2.0),
                      ("atr_rung_stretch_atr", 1.5)):
        assert policy[key]["method_id"] == "policy_seed"
        assert policy[key]["extra"] == {"seed": seed}
    for key in ("atr_rung_anchors", "atr_rung_step_atr", "atr_rung_max_atr",
                "atr_rung_stretch_atr"):
        assert policy[key]["effective_from"] == "2015-01-02"
    schema = (Path(__file__).resolve().parents[2] / "gcp" / "schema.sql").read_text()
    block = schema[schema.index("('atr_rung_anchors'"):]
    assert block.index("ON CONFLICT (param_key, effective_from) DO NOTHING") < block.index(";")


def test_load_reads_the_anchor_list_like_atr_basis():
    db = legacy_db(["SPY"], effective_from=date(2026, 11, 3))
    lp = db.load(["SPY"], D)["SPY"]
    assert lp.atr_rung_anchors() == ("PDH", "PDL", "PMK_H", "PMK_L")
    p = lp.param("atr_rung_anchors")
    assert (p.status, p.method_id, p.effective_from) == ("ok", "policy", "2015-01-02")


def test_a_policy_with_no_anchor_row_raises_naming_the_key():
    db = legacy_db(["SPY"], effective_from=date(2026, 11, 3))
    db.conn.execute("DELETE FROM level_param_policy WHERE param_key = 'atr_rung_anchors'")
    db.conn.commit()
    with pytest.raises(LevelParamsUnavailable, match="atr_rung_anchors"):
        db.load(["SPY"], D)


@pytest.mark.parametrize("extra", ['{"anchors": []}', '{}', '{"anchors": ["PDH", "OPEN"]}',
                                   '{"anchors": ["PDH", "PDH"]}', '{"anchors": "PDH"}'])
def test_an_empty_or_unknown_anchor_list_raises(extra):
    """A later row that is empty, names a level that is not a trigger
    candidate (OPEN), or names one twice cannot be read."""
    db = legacy_db(["SPY"], effective_from=date(2026, 11, 3))
    db.set_policy("atr_rung_anchors", effective_from=date(2026, 11, 5), extra=extra)
    assert db.load(["SPY"], date(2026, 11, 4))["SPY"].atr_rung_anchors() == (
        "PDH", "PDL", "PMK_H", "PMK_L")
    with pytest.raises(LevelParamsUnavailable, match="atr_rung_anchors"):
        db.load(["SPY"], D)


def test_a_later_anchor_row_of_the_prior_close_builds_prior_close_rungs():
    """An atr_rung_anchors row listing [PDC] effective D builds the rungs
    from the prior close from D, with no code change."""
    from tests.lib.session_levels_helpers import D8_LEVELS, D8_PREMARKET, basis
    from lib.strat_levels import SessionLevels
    db = legacy_db(["TST"], effective_from=date(2026, 11, 3))
    db.set_policy("atr_rung_anchors", effective_from=D, extra='{"anchors": ["PDC"]}')

    def rungs(day):
        lp = db.load(["TST"], day)["TST"]
        sl = SessionLevels.from_basis(basis(D8_LEVELS, prior_close=247.00, atr=14.0,
                                            premarket=D8_PREMARKET, session_date=day, params=lp))
        return {r["anchor"] for r in sl.atr_rungs + sl.atr_rungs_dropped}, sl

    before, _ = rungs(date(2026, 11, 6))
    after, sl = rungs(D)
    assert before == {"PDH", "PDL", "PMK_H", "PMK_L"}
    assert after == {"PDC"}
    assert sorted(r["price"] for r in sl.atr_rungs + sl.atr_rungs_dropped) == [
        219.0, 226.0, 233.0, 240.0, 254.0, 261.0, 268.0, 275.0]


def test_the_seeded_entry_cutoff_is_the_regular_close():
    """Drop-entry-cutoff spec, Design 1: the policy seeded in gcp/schema.sql
    gives entry_cutoff_et 16:00 ET, 960 minutes after midnight."""
    from lib.strat_levels import policy_wide_param
    from tests.lib.level_params_fixtures import seeded_policy

    p = policy_wide_param("entry_cutoff_et", seeded_policy()["entry_cutoff_et"], "SPY", "atr_14")
    assert p.status == "ok" and p.value == 960.0
    assert p.extra == {"time_et": "16:00"}


def test_schema_seeds_the_plan_target_level_types_row():
    """Gap-edge plan targets spec, done_when 'Policy': one policy-wide row,
    read like atr_rung_anchors, ok with value 2 on the seeded policy."""
    policy = seeded_policy()
    row = policy["plan_target_level_types"]
    assert row["method_id"] == "policy" and row["effective_from"] == "2015-01-02"
    assert row["extra"] == {"level_types": ["gap_high", "gap_low"]}
    p = policy_wide_param("plan_target_level_types", row, "SPY", "atr_14")
    assert (p.status, p.value, p.source) == ("ok", 2.0, "policy")
    schema = (Path(__file__).resolve().parents[2] / "gcp" / "schema.sql").read_text()
    block = schema[schema.index("('plan_target_level_types'"):]
    assert block.index("ON CONFLICT (param_key, effective_from) DO NOTHING") < block.index(";")


@pytest.mark.parametrize("extra, status, value", [
    ({"level_types": ["gap_high", "gap_low"]}, "ok", 2.0),
    ({"level_types": ["gap_low"]}, "ok", 1.0),
    ({"level_types": []}, "ok", 0.0),
    ({}, "input_unavailable", None),
    ({"level_types": "gap_high"}, "input_unavailable", None),
    ({"level_types": ["gap_high", "open"]}, "input_unavailable", None),
    ({"level_types": ["gap_high", "gap_high"]}, "input_unavailable", None),
])
def test_plan_target_level_types_reads_its_extra(extra, status, value):
    row = {"param_key": "plan_target_level_types", "method_id": "policy", "extra": extra,
           "effective_from": "2015-01-02"}
    p = policy_wide_param("plan_target_level_types", row, "SPY", "atr_14")
    assert (p.status, p.value) == (status, value)
    lp = LevelParams(ticker="SPY", session_date=D, atr_basis="atr_14",
                     policy_effective_from="2015-01-02",
                     params={"plan_target_level_types": p})
    expect = tuple(extra["level_types"]) if status == "ok" else None
    assert lp.plan_target_level_types() == expect


# ── ATR marks spec (2026-11-16), done_when "Policy rows" ───────────────
#
# Two policy-wide rows seeded to reproduce today's plan: no ATR marks (the
# level rule picks the targets) and 250 analysis dates of reach history.

# The policy rows gcp/schema.sql seeds on origin/main f3b2344c4, each in
# force from 2015-01-02: (method_id, statistic_q, lookback_sessions,
# min_sample, extra). No existing row changes.
BASE_POLICY_ROWS = {
    'atr_basis': ('policy', None, None, None, {'column': 'atr_14'}),
    'atr_rung_anchors': ('policy', None, None, None, {'anchors': ['PDH', 'PDL', 'PMK_H', 'PMK_L']}),
    'atr_rung_max_atr': ('policy_seed', None, None, None, {'seed': 2.0}),
    'atr_rung_step_atr': ('policy_seed', None, None, None, {'seed': 0.5}),
    'atr_rung_stretch_atr': ('policy_seed', None, None, None, {'seed': 1.5}),
    'calibration_universe': ('policy', None, None, None, {'sources': ['market_config_tickers', 'insight_default_tickers', 'watchlist', 'on_demand']}),
    'entry_buffer_aggressive_hi_atr': ('follow_through_quantile', 0.75, 750, 150, {'persona': 'aggressive', 'edge': 'hi', 'follow_through_minutes': 15}),
    'entry_buffer_aggressive_lo_atr': ('at_trigger', None, 750, 150, {'persona': 'aggressive', 'edge': 'lo', 'follow_through_minutes': 15}),
    'entry_buffer_conservative_hi_atr': ('follow_through_quantile', 0.65, 750, 150, {'persona': 'conservative', 'edge': 'hi', 'follow_through_minutes': 15}),
    'entry_buffer_conservative_lo_atr': ('follow_through_quantile', 0.2, 750, 150, {'persona': 'conservative', 'edge': 'lo', 'follow_through_minutes': 15}),
    'entry_buffer_neutral_hi_atr': ('follow_through_quantile', 0.5, 750, 150, {'persona': 'neutral', 'edge': 'hi', 'follow_through_minutes': 15}),
    'entry_buffer_neutral_lo_atr': ('at_trigger', None, 750, 150, {'persona': 'neutral', 'edge': 'lo', 'follow_through_minutes': 15}),
    'entry_cutoff_et': ('policy', None, None, None, {'time_et': '16:00'}),
    'exit_legs': ('policy', None, None, None, {'legs': 3}),
    'gap_fill_flag_atr': ('policy_seed', None, None, None, {'seed': 0.5}),
    'level_cluster_atr': ('rth_interval_change_quantile', 0.5, 60, 40, {'interval_minutes': 15}),
    'min_stop_atr': ('filled_held_mae_quantile', 0.5, 750, 150, {'persona': 'neutral'}),
    'plan_target_level_types': ('policy', None, None, None, {'level_types': ['gap_high', 'gap_low']}),
    'pm_spike_atr': ('premarket_wick_excess_quantile', 0.999, 60, 40, {'min_bars_per_session': 60}),
    'pm_stale_print_atr': ('premarket_bar_spread_quantile', 0.95, 60, 40, {'min_bars_per_session': 60}),
    'stop_aggressive_atr': ('filled_held_mae_quantile', 0.9, 750, 150, {'persona': 'aggressive'}),
    'stop_conservative_atr': ('filled_held_mae_quantile', 0.6, 750, 150, {'persona': 'conservative'}),
    'stop_neutral_atr': ('filled_held_mae_quantile', 0.75, 750, 150, {'persona': 'neutral'}),
    'target_aggressive_1_r': ('filled_reach_share', 0.4, 750, 150, {'persona': 'aggressive', 'k': 1}),
    'target_aggressive_2_r': ('filled_reach_share', 0.25, 750, 150, {'persona': 'aggressive', 'k': 2}),
    'target_aggressive_3_r': ('filled_reach_share', 0.15, 750, 150, {'persona': 'aggressive', 'k': 3}),
    'target_conservative_1_r': ('filled_reach_share', 0.65, 750, 150, {'persona': 'conservative', 'k': 1}),
    'target_conservative_2_r': ('filled_reach_share', 0.5, 750, 150, {'persona': 'conservative', 'k': 2}),
    'target_min_spacing_atr': ('policy_seed', None, None, None, {'seed': 0.25}),
    'target_neutral_1_r': ('filled_reach_share', 0.6, 750, 150, {'persona': 'neutral', 'k': 1}),
    'target_neutral_2_r': ('filled_reach_share', 0.45, 750, 150, {'persona': 'neutral', 'k': 2}),
    'target_neutral_3_r': ('filled_reach_share', 0.3, 750, 150, {'persona': 'neutral', 'k': 3}),
    'trigger_window_long_atr': ('daily_excursion_quantile', 0.99, 750, 250, {'side': 'long'}),
    'trigger_window_short_atr': ('daily_excursion_quantile', 0.99, 750, 250, {'side': 'short'}),
}


def test_schema_seeds_the_two_rows():
    policy = seeded_policy()
    marks, history = policy["plan_target_marks_atr"], policy["ladder_history_sessions"]
    assert (marks["method_id"], marks["effective_from"], marks["extra"]) == (
        "policy", "2015-01-02", {"marks": []})
    assert (history["method_id"], history["effective_from"], history["extra"]) == (
        "policy", "2015-01-02", {"sessions": 250})
    assert policy["exit_legs"]["extra"] == {"legs": 3}
    rest = {k: (r["method_id"], r["statistic_q"], r["lookback_sessions"], r["min_sample"], r["extra"])
            for k, r in policy.items()
            if k not in ("plan_target_marks_atr", "ladder_history_sessions")}
    assert rest == BASE_POLICY_ROWS
    assert {r["effective_from"] for r in policy.values()} == {"2015-01-02"}
    schema = (Path(__file__).resolve().parents[2] / "gcp" / "schema.sql").read_text()
    for key in ("plan_target_marks_atr", "ladder_history_sessions"):
        block = schema[schema.index(f"('{key}'"):]
        assert block.index("ON CONFLICT (param_key, effective_from) DO NOTHING") < block.index(";")


def test_both_keys_are_policy_wide():
    import ast

    from lib.strat_levels import LADDER_HISTORY_KEY, PLAN_TARGET_MARKS_KEY, POLICY_WIDE_KEYS

    assert {PLAN_TARGET_MARKS_KEY, LADDER_HISTORY_KEY} <= set(POLICY_WIDE_KEYS)
    src = (Path(__file__).resolve().parents[2] / "lib" / "strat_levels.py").read_text()
    strings = [n.value for n in ast.walk(ast.parse(src))
               if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    for key in ("plan_target_marks_atr", "ladder_history_sessions"):
        assert sum(key in s for s in strings) == 1, key


def _load_with_policy(key, extra):
    db = ParamsDb()
    db.set_policy(key, effective_from=date(2026, 11, 2), extra=extra)
    return db.load(["SPY"], D)["SPY"]


@pytest.mark.parametrize("extra, status, value", [
    ('{"marks": []}', "ok", 0.0),
    ('{"marks": [0.25, 0.5, 0.75, 1.0]}', "ok", 4.0),
    ('{"marks": [0.25]}', "ok", 1.0),
    ('{}', "input_unavailable", None),
    ('{"marks": null}', "input_unavailable", None),
    ('{"marks": "0.25"}', "input_unavailable", None),
    ('{"marks": [0.25, "0.5"]}', "input_unavailable", None),
    ('{"marks": [true]}', "input_unavailable", None),
    ('{"marks": [0.0, 0.5]}', "input_unavailable", None),
    ('{"marks": [-0.25]}', "input_unavailable", None),
    ('{"marks": [0.25, 0.25]}', "input_unavailable", None),
    ('{"marks": [0.5, 0.25]}', "input_unavailable", None),
])
def test_marks_param_status(extra, status, value):
    lp = _load_with_policy("plan_target_marks_atr", extra)
    p = lp.param("plan_target_marks_atr")
    assert (p.status, p.value) == (status, value)
    import json
    expect = tuple(json.loads(extra)["marks"]) if status == "ok" else None
    assert lp.plan_target_marks() == expect


@pytest.mark.parametrize("extra, status, value", [
    ('{"sessions": 250}', "ok", 250.0),
    ('{"sessions": 1}', "ok", 1.0),
    ('{"sessions": 0}', "input_unavailable", None),
    ('{"sessions": -1}', "input_unavailable", None),
    ('{"sessions": 2.5}', "input_unavailable", None),
    ('{"sessions": "250"}', "input_unavailable", None),
    ('{"sessions": true}', "input_unavailable", None),
    ('{}', "input_unavailable", None),
])
def test_history_sessions_param_status(extra, status, value):
    p = _load_with_policy("ladder_history_sessions", extra).param("ladder_history_sessions")
    assert (p.status, p.value) == (status, value)


def test_seeded_marks_accessor():
    from tests.lib.level_params_fixtures import fixture_params

    assert fixture_params().plan_target_marks() == ()
    lp = ParamsDb().load(["SPY"], D)["SPY"]
    assert lp.plan_target_marks() == ()
    assert (lp.status("ladder_history_sessions"), lp.value("ladder_history_sessions")) == ("ok", 250.0)
