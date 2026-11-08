"""FEAT-STRAT-001 per-ticker params, done_when 1: parameter tables and loader.

level_param_policy and ticker_level_params are created in SQLite from the DDL
and policy seed committed in gcp/schema.sql, and read with
lib.strat_levels.load_level_params's own SQL. On the #1753 head neither the
tables nor the function exist.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from lib.strat_levels import (
    PARAMS_BASIS_MISMATCH, PARAMS_UNAVAILABLE, LevelParamsUnavailable,
    LevelParamUnavailable, load_level_params,
)
from tests.lib.level_params_fixtures import LEGACY_1753_VALUES, ParamsDb, seeded_policy

DESIGN_2_KEYS = set(LEGACY_1753_VALUES)
D = date(2026, 11, 9)


def test_schema_seeds_the_design_2_policy_and_no_ticker_values():
    db = ParamsDb()
    policy = seeded_policy()
    assert set(policy) == DESIGN_2_KEYS | {"atr_basis", "calibration_universe"}
    assert policy["atr_basis"]["extra"] == {"column": "atr_14"}
    assert {p["effective_from"] for p in policy.values()} == {"2015-01-02"}
    assert policy["trigger_window_long_atr"]["statistic_q"] == 0.99
    assert policy["trigger_window_long_atr"]["lookback_sessions"] == 750
    assert policy["trigger_window_long_atr"]["min_sample"] == 250
    assert policy["pm_spike_atr"]["statistic_q"] == 0.999
    assert policy["stop_aggressive_atr"]["statistic_q"] == 0.90
    assert policy["target_conservative_2_r"]["statistic_q"] == 0.50
    assert db.query("SELECT COUNT(*) AS n FROM ticker_level_params")["n"].iloc[0] == 0
    assert len(DESIGN_2_KEYS) == 23


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
