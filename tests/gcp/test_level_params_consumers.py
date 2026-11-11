"""FEAT-STRAT-001 per-ticker params: every consumer reads the parameters in
force on its session.

done_when 10, missing table is loud. With the level parameter query raising
(the tables dropped from the SQLite ParamsDb, so load_level_params's own SQL
fails):
* the brief job (gcp.premarket_brief.main) exits 1 and persists no
  premarket_analysis row for any ticker;
* the insight run (gcp.insight_pipeline_job._run_one through the real
  orchestrator) records status failed with reason level_params_unavailable,
  and build_context_bundle raises instead of marking a degraded section;
* the signal monitor's level refresh logs and skips the map for that cycle,
  counts the skip, and the session summary line carries the count.

done_when 11, level_basis records the parameters:
* the brief's level_basis carries, per key, value, status, effective_from,
  method_id, sample_n, input_from, input_to and run_id, the policy version,
  atr_14, atr_5, atr_basis and the new rule_version;
* SessionLevels.from_basis rebuilds with the recorded parameters: changing
  ticker_level_params after the brief leaves the planner's picks and the
  movement statement's ladder for that session unchanged (the ladder is read
  with the tables dropped);
* the movement statement's reach-rate population counts only rows of the
  new rule_version, never a #1753 (feat-strat-001.v1) row.

done_when 12, point-in-time replays: with two versions of the rows, one in
force on 2026-11-06 and one effective after it, a replay of 2026-11-06
through the brief, the insight planner, the signal monitor's replay clock
and the playbook resolver gets the first version's picks; a second version
effective on the session itself changes them, so the comparison has teeth.

On origin/main and the #1753 head none of the parameter plumbing exists.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from lib.strat_levels import LEVEL_RULE_VERSION, LevelParamsUnavailable, SessionLevels
from tests.lib import strat_2026_11_06 as fx
from tests.lib.level_params_fixtures import (
    LEGACY_1753_VALUES, ParamsDb, install_level_params, legacy_db,
)

ROOT = Path(__file__).resolve().parents[2]
SESSION = fx.SESSION
FIRST = date(2015, 1, 2)
LATER = date(2026, 11, 9)          # a version that takes effect after the session
V1_RULE = "feat-strat-001.v1"      # the #1753 head's rule_version
# The second version: trigger windows inside QQQ's nearest levels on
# 2026-11-06 (PMK_H at 0.21 ATR, PMK_L at 0.50 ATR), so both sides go
# orb_only, and wider persona stops.
SECOND = {**LEGACY_1753_VALUES,
          "trigger_window_long_atr": 0.1, "trigger_window_short_atr": 0.1,
          "stop_aggressive_atr": 2.6, "stop_neutral_atr": 1.6, "stop_conservative_atr": 1.2}
# Persona values only, the windows untouched: the plans change, the triggers
# do not.
PERSONA_ONLY = {**LEGACY_1753_VALUES,
                "stop_aggressive_atr": 2.6, "stop_neutral_atr": 1.6, "stop_conservative_atr": 1.2,
                "entry_buffer_neutral_hi_atr": 0.4, "target_neutral_1_r": 1.5}


def _broken() -> ParamsDb:
    db = ParamsDb()
    db.drop("ticker_level_params")
    db.drop("level_param_policy")
    return db


def _two_versions(ticker: str, second_from: date, values: dict = SECOND, conn=None) -> ParamsDb:
    db = legacy_db(ticker, effective_from=FIRST, conn=conn)
    db.write(ticker, values, effective_from=second_from)
    return db


def _picks(basis: dict) -> dict:
    """Each side's picks as the basis records them. The side's window
    carries the run id of the rows it came from; two databases written
    with the same values hold different run ids, so it is left out."""
    out = {}
    for side in ("long", "short"):
        s = json.loads(json.dumps(basis[side], default=str))
        if isinstance(s.get("window"), dict):
            s["window"].pop("run_id", None)
        out[side] = s
    return out


def _refuse_network(monkeypatch):
    import socket

    def refuse(*_a, **_k):
        raise AssertionError("external I/O attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


# ── done_when 10: missing table is loud ────────────────────────────────

def test_brief_job_exits_non_zero_without_writing_a_row(monkeypatch, caplog):
    from gcp import premarket_brief as pb

    _refuse_network(monkeypatch)
    persisted, sent = [], []
    monkeypatch.setattr(pb, "_level_params_query", _broken().query)
    monkeypatch.setattr(pb, "persist_to_cloud_sql", lambda *a, **k: persisted.append(a) or 1)
    monkeypatch.setattr(pb, "send_to_discord", lambda *a, **k: sent.append(a))
    for key, value in {"BRIEF_AS_OF": "2026-11-06", "BRIEF_TICKERS": "SPY,QQQ,IWM",
                       "BRIEF_LLM_DISABLE": "1", "BRIEF_TRIGGERED_BY": "test",
                       "BRIEF_POST_TO_DISCORD": "false"}.items():
        monkeypatch.setenv(key, value)
    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit) as exc:
        pb.main([])
    assert exc.value.code == 1
    assert persisted == [] and sent == []
    assert "level_params_unavailable" in caplog.text


def _stub_other_sections(monkeypatch):
    """Every bundle section but session_levels answers available, so the
    only failure is the parameter read."""
    from lib.agents import summarizers
    for name in ("summarize_market_context", "summarize_strat_status", "summarize_options_flow",
                 "summarize_gamma_levels", "summarize_backtest_metrics", "summarize_catalysts",
                 "summarize_news_sentiment"):
        monkeypatch.setattr(summarizers, name, lambda *a, **k: {"available": True})
    monkeypatch.setattr(summarizers, "_query_strict", _broken().query)


def test_build_context_bundle_raises_on_level_params_unavailable(monkeypatch):
    from lib.agents import summarizers
    _refuse_network(monkeypatch)
    _stub_other_sections(monkeypatch)
    with pytest.raises(LevelParamsUnavailable) as exc:
        summarizers.build_context_bundle("SPY", SESSION)
    assert exc.value.reason == "level_params_unavailable"


def test_insight_run_records_failed_with_the_reason(monkeypatch):
    from gcp import insight_pipeline_job as job

    _refuse_network(monkeypatch)
    _stub_other_sections(monkeypatch)
    transitions = []
    monkeypatch.setattr(job, "_transition",
                        lambda run_id, status, **k: transitions.append((status, k)) or True)
    monkeypatch.setattr(job, "load_routes_snapshot", lambda: object())
    monkeypatch.setattr(job, "_insert_report_history",
                        lambda *a, **k: pytest.fail("no report on a failed run"))
    monkeypatch.setattr(job, "_upsert_report", lambda *a, **k: pytest.fail("no report on a failed run"))
    ok = asyncio.run(job._run_one("run-1", "SPY", as_of=SESSION))
    assert ok is False
    assert [s for s, _ in transitions] == ["running", "failed"]
    assert transitions[-1][1]["error"].startswith("level_params_unavailable: ")


def _monitor(monkeypatch, params_query, *, analysis_db=None):
    """A SignalMonitor on the 2026-11-06 replay clock whose daily frame is
    the committed QQQ fixture and whose level parameters come from
    `params_query`; no live level_basis unless `analysis_db` holds one."""
    import gcp.database as database
    from gcp import signal_monitor as sm
    from tests.gcp.test_level_basis import _AnalysisDb

    db = analysis_db if analysis_db is not None else _AnalysisDb()
    monkeypatch.setattr(database, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(database, "query_to_dataframe", db.query)
    frame = fx.loader_frame("QQQ")

    class _L:
        def __init__(self, *a, **k):
            pass

        def load_daily(self, *a, **k):
            return frame.copy()

    monkeypatch.setattr("lib.data_loader.DataLoader", _L)
    monitor = sm.SignalMonitor()
    monitor.webhook_url = ""
    monitor.replay_clock_ts = datetime(2026, 11, 6, 9, 0, tzinfo=ZoneInfo("America/New_York"))
    monitor._level_params_query = params_query
    return monitor


def test_signal_monitor_skips_the_level_map_with_the_reason(monkeypatch, caplog):
    monitor = _monitor(monkeypatch, _broken().query)
    monitor.level_map_atr["QQQ"] = 1.0
    with caplog.at_level(logging.ERROR, logger="gcp.signal_monitor"):
        monitor.refresh_level_map("QQQ")
    assert monitor.level_maps["QQQ"] is None
    assert "QQQ" not in monitor.level_map_atr
    assert monitor.level_refresh_params_unavailable_count["QQQ"] == 1
    assert monitor.level_refresh_exception_count.get("QQQ", 0) == 0
    assert monitor.level_refresh_success_count.get("QQQ", 0) == 0
    assert "level refresh skipped, reason=level_params_unavailable" in caplog.text
    # The count is a run counter (kept across a session reset) and the
    # end-of-session summary line carries it.
    assert "level_refresh_params_unavailable_count" in monitor.SESSION_KEEP
    text = (ROOT / "gcp" / "signal_monitor.py").read_text()
    summary = text[text.index('"session_summary '):]
    summary = summary[:summary.index("break")]
    assert "level_refresh_params_unavailable=%d" in summary
    assert "self.level_refresh_params_unavailable_count.get(t, 0)" in summary
    # The next cycle with readable tables builds the map.
    monitor._level_params_query = legacy_db("QQQ").query
    monitor.refresh_level_map("QQQ")
    assert monitor.level_maps["QQQ"] is not None


# ── done_when 11: level_basis records the parameters ───────────────────

def test_level_basis_records_every_parameter_and_the_policy(monkeypatch):
    from lib.indicators import calculate_atr

    db = ParamsDb()
    run_id = db.write("QQQ", LEGACY_1753_VALUES, effective_from=date(2026, 11, 2),
                      input_from="2023-10-30", input_to="2026-10-30", sample_n=749,
                      run_id="11111111-2222-3333-4444-555555555555")
    b = fx.run_brief(monkeypatch, "QQQ", fx.loader_frame("QQQ"), params_db=db)["level_basis"]
    b = json.loads(json.dumps(b))       # plain JSON as stored
    assert b["rule_version"] == LEVEL_RULE_VERSION != V1_RULE
    assert b["atr_basis"] == "atr_14" and b["policy_effective_from"] == "2015-01-02"
    d = fx.daily("QQQ")
    assert b["atr_14"] == pytest.approx(fx.prior_atr("QQQ"))
    assert b["atr_5"] == pytest.approx(calculate_atr(d["High"], d["Low"], d["Close"], 5).iloc[-1])
    # The exits spec's policy-wide keys are recorded beside the ticker rows,
    # with the policy row they came from.
    assert set(b["params"]) == set(LEGACY_1753_VALUES) | {"exit_legs", "entry_cutoff_et"}
    assert (b["params"]["exit_legs"]["value"], b["params"]["exit_legs"]["status"]) == (3.0, "ok")
    assert b["params"]["exit_legs"]["method_id"] == "policy"
    assert b["params"]["exit_legs"]["effective_from"] == "2015-01-02"
    assert b["params"]["entry_cutoff_et"]["extra"] == {"time_et": "10:00"}
    for key, value in LEGACY_1753_VALUES.items():
        p = b["params"][key]
        assert p["value"] == pytest.approx(value) and p["status"] == "ok"
        assert p["effective_from"] == "2026-11-02" and p["method_id"] == "fixture"
        assert p["sample_n"] == 749 and p["run_id"] == run_id
        assert (p["input_from"], p["input_to"]) == ("2023-10-30", "2026-10-30")


def test_from_basis_rebuilds_with_the_recorded_parameters(monkeypatch):
    from tests.lib.level_params_fixtures import fixture_params

    b = fx.run_brief(monkeypatch, "QQQ", fx.loader_frame("QQQ"))["level_basis"]
    other = fixture_params("QQQ", SESSION, overrides=SECOND)
    rebuilt = SessionLevels.from_basis(b)
    offered = SessionLevels.from_basis(b, params=other)
    assert _picks(rebuilt.to_basis()) == _picks(b) == _picks(offered.to_basis())
    assert offered.params.value("trigger_window_long_atr") == pytest.approx(3.0)


def test_pre_parameter_basis_without_params_is_params_unavailable():
    """A level_basis written before parameters were recorded (no params, no
    atr_basis, ATR(14) as `atr`), rebuilt with no parameters offered: every
    side with a candidate is orb_only with reason params_unavailable, as
    from_basis documents, never atr_unavailable (the ATR it recorded is
    fine; what is missing is the parameters that say which ATR to use)."""
    from tests.lib.session_levels_helpers import basis

    b = basis({"PDH": 101.0, "PDL": 99.0}, prior_close=100.0, atr=2.0)
    for k in ("params", "atr_basis", "policy_effective_from", "atr_14", "atr_5"):
        b.pop(k, None)
    s = SessionLevels.from_basis(b)
    assert s.params is None
    assert (s.long.reason, s.short.reason) == ("params_unavailable", "params_unavailable")
    assert s.long.trigger is None and s.short.trigger is None


def test_changing_rows_after_the_brief_leaves_the_planner_picks_unchanged(monkeypatch):
    frame = fx.loader_frame("QQQ")
    brief_db = legacy_db("QQQ")
    b = fx.run_brief(monkeypatch, "QQQ", frame, params_db=brief_db)["level_basis"]
    # After the brief, a calibration run writes new rows effective on the session.
    later_db = legacy_db("QQQ")
    later_db.write("QQQ", PERSONA_ONLY, effective_from=SESSION)
    for direction in ("long", "short"):
        _, _, before, _ = fx.run_planner(monkeypatch, "QQQ", frame, direction,
                                         live_basis=b, params_db=brief_db)
        _, _, after, _ = fx.run_planner(monkeypatch, "QQQ", frame, direction,
                                        live_basis=b, params_db=later_db)
        assert after == before
        # The same rows do move a plan that is built rather than rebuilt.
        _, _, built, _ = fx.run_planner(monkeypatch, "QQQ", frame, direction,
                                        live_basis=None, params_db=later_db)
        assert built != before


def test_movement_ladder_rebuilds_without_reading_the_tables(monkeypatch):
    from tests.gcp.test_level_basis import _AnalysisDb, _movement_map, _row

    b = fx.run_brief(monkeypatch, "QQQ", fx.loader_frame("QQQ"))["level_basis"]
    adb = _AnalysisDb([_row(b)])
    install_level_params(monkeypatch, ["QQQ"])
    with_tables = _movement_map(monkeypatch, adb)
    install_level_params(monkeypatch, db=_broken())     # any read would raise
    without = _movement_map(monkeypatch, adb)
    later = legacy_db("QQQ")
    later.write("QQQ", SECOND, effective_from=SESSION)
    install_level_params(monkeypatch, db=later)
    changed = _movement_map(monkeypatch, adb)
    for m in (without, changed):
        assert m.calls_trigger == with_tables.calls_trigger
        assert m.puts_trigger == with_tables.puts_trigger
    assert with_tables.calls_trigger["trigger_name"] == "PMK_H"


def test_reach_rate_population_counts_only_the_new_rule_version():
    import lib.movement_statement as ms
    from tests.lib.test_movement_statement_level_basis import _Db, _mark_basis, _resolved

    db = _Db()
    for i in range(4):           # #1753 rule rows, every slot hit
        _resolved(db, d=f"2026-10-0{i + 1}", price=100.0, lb=_mark_basis(above=100.0, rule=V1_RULE),
                  calls=(101.0, 102.0, 103.0, 104.0), calls_hit=("trigger", "t1", "t2", "t3"))
    _resolved(db, d="2026-10-10", price=100.0, lb=_mark_basis(above=100.0),
              calls=(101.0, 102.0, 103.0, 104.0), calls_hit=("trigger",))
    _resolved(db, d="2026-10-11", price=100.0, lb=_mark_basis(above=100.0),
              calls=(101.0, 102.0, 103.0, 104.0))
    assert LEVEL_RULE_VERSION != V1_RULE
    trig = ms._fetch_reach_rates("SPY", "calls", db.query)["slots"]["trigger"]
    assert (trig["sample_n"], trig["hits"]) == (2, 1)


# ── done_when 12: point-in-time replays ────────────────────────────────

def test_brief_replay_reads_the_version_in_force(monkeypatch):
    frame = fx.loader_frame("QQQ")
    first = fx.run_brief(monkeypatch, "QQQ", frame, params_db=legacy_db("QQQ"))["level_basis"]
    replay = fx.run_brief(monkeypatch, "QQQ", frame,
                          params_db=_two_versions("QQQ", LATER))["level_basis"]
    assert _picks(replay) == _picks(first)
    assert {p["effective_from"] for p in replay["params"].values()} == {FIRST.isoformat()}
    on_session = fx.run_brief(monkeypatch, "QQQ", frame,
                              params_db=_two_versions("QQQ", SESSION))["level_basis"]
    assert _picks(on_session) != _picks(first)
    assert on_session["long"]["reason"] == on_session["short"]["reason"] == "next_level_outside_window"


def test_insight_replay_reads_the_version_in_force(monkeypatch):
    frame = fx.loader_frame("QQQ")
    sec1, _, plans1, _ = fx.run_planner(monkeypatch, "QQQ", frame, "long", params_db=legacy_db("QQQ"))
    sec2, _, plans2, _ = fx.run_planner(monkeypatch, "QQQ", frame, "long",
                                        params_db=_two_versions("QQQ", LATER))
    assert sec2["source"] == "builder"
    assert _picks(sec2["level_basis"]) == _picks(sec1["level_basis"]) and plans2 == plans1
    sec3, _, plans3, _ = fx.run_planner(monkeypatch, "QQQ", frame, "long",
                                        params_db=_two_versions("QQQ", SESSION))
    assert _picks(sec3["level_basis"]) != _picks(sec1["level_basis"]) and plans3 != plans1


def test_signal_replay_reads_the_version_in_force(monkeypatch):
    def picks(db):
        monitor = _monitor(monkeypatch, db.query)
        monitor.refresh_level_map("QQQ")
        assert monitor.level_refresh_success_count.get("QQQ") == 1
        return _picks(monitor.session_levels["QQQ"].to_basis())

    first = picks(legacy_db("QQQ"))
    assert picks(_two_versions("QQQ", LATER)) == first
    assert picks(_two_versions("QQQ", SESSION)) != first


def _resolver(params_writer, *, live_basis=None):
    """gcp.premarket_playbook_resolver.derive_level_map_from_daily on one
    SQLite database holding market_data_daily (the committed QQQ fixture and
    the session's premarket row), premarket_analysis (with `live_basis` as
    the session's live row when given) and the parameter tables
    `params_writer(conn)` fills."""
    import sqlalchemy as sa
    from gcp.premarket_playbook_resolver import derive_level_map_from_daily
    from lib.indicators import calculate_atr
    from tests.gcp.test_level_basis import _AnalysisDb, _row

    adb = _AnalysisDb([_row(live_basis)] if live_basis is not None else [])
    eng = sa.create_engine("sqlite://", creator=lambda: adb.conn)
    params_writer(adb.conn)
    d = fx.daily("QQQ")
    daily = pd.DataFrame({
        "ticker": "QQQ", "date": [t.date().isoformat() for t in d.index],
        "open": d["Open"].values, "high": d["High"].values, "low": d["Low"].values,
        "close": d["Close"].values, "atr_14": fx.wilder_atr(d).values,
        "atr_5": calculate_atr(d["High"], d["Low"], d["Close"], 5).values,
        "strat_candle": "", "strat_combo": "",
        "pre_high": None, "pre_low": None, "pre_vwap": None, "gap_pct": None,
        "pre_fetched_at": None, "pre_excluded_stale_prints": None, "pre_excluded_spikes": None,
        "pre_filter_status": None, "pre_filter_params": None})
    snap = fx.session_premarket("QQQ")
    daily = pd.concat([daily, pd.DataFrame([{
        "ticker": "QQQ", "date": SESSION.isoformat(), "strat_candle": "", "strat_combo": "",
        **{k: snap[k] for k in ("pre_high", "pre_low", "pre_vwap", "gap_pct", "pre_filter_status")}}])],
        ignore_index=True)
    daily.to_sql("market_data_daily", eng, index=False, if_exists="replace")
    return derive_level_map_from_daily("QQQ", SESSION, eng)


def test_resolver_replay_reads_the_version_in_force():
    first = _resolver(lambda conn: legacy_db("QQQ", conn=conn))
    assert first["calls_trigger_name"] == "PMK_H" and first["puts_trigger_name"] == "PMK_L"
    assert _resolver(lambda conn: _two_versions("QQQ", LATER, conn=conn)) == first
    on_session = _resolver(lambda conn: _two_versions("QQQ", SESSION, conn=conn))
    assert on_session["calls_trigger_price"] is None and on_session["puts_trigger_price"] is None


def test_resolver_replay_of_a_pre_parameter_basis_reads_the_version_in_force(monkeypatch):
    """A live row written before parameters were recorded (a #1753 basis)
    rebuilds with the rows in force on its own session."""
    b = fx.run_brief(monkeypatch, "QQQ", fx.loader_frame("QQQ"))["level_basis"]
    old = {k: v for k, v in b.items() if k not in ("params", "atr_basis", "policy_effective_from")}
    old["rule_version"] = V1_RULE
    first = _resolver(lambda conn: legacy_db("QQQ", conn=conn), live_basis=old)
    assert first["calls_trigger_name"] == "PMK_H"
    assert _resolver(lambda conn: _two_versions("QQQ", LATER, conn=conn), live_basis=old) == first
    on_session = _resolver(lambda conn: _two_versions("QQQ", SESSION, conn=conn), live_basis=old)
    assert on_session != first


def test_resolver_rebuilds_a_recorded_basis_without_the_tables(monkeypatch):
    b = fx.run_brief(monkeypatch, "QQQ", fx.loader_frame("QQQ"))["level_basis"]
    first = _resolver(lambda conn: legacy_db("QQQ", conn=conn), live_basis=b)
    # No parameter tables in the database at all: a read would raise.
    assert _resolver(lambda conn: None, live_basis=b) == first


def _pre_parameter(b: dict, zones: list) -> dict:
    """The same basis as a pre-parameter (feat-strat-001.v1) snapshot: no
    params, no atr_basis, ATR(14) as `atr`, zones from the old rule."""
    legacy = json.loads(json.dumps(b, default=str))
    legacy["atr"] = legacy.get("atr_14")
    for k in ("params", "atr_basis", "policy_effective_from", "atr_14", "atr_5"):
        legacy.pop(k, None)
    legacy["pmg_zones"], legacy["pmg_status"] = zones, "ok"
    return legacy


def test_pre_parameter_basis_rebuilds_pmg_zones_with_the_supplied_cluster(monkeypatch):
    """Codex P2 on e4bb463e: a pre-parameter basis's stored zones (built with
    the old percentage tolerance) are never carried into a parameterised
    rebuild. With level_cluster_atr insufficient_history the rebuild has no
    zones and says so; with it ok the zones equal a fresh build's."""
    from tests.lib.level_params_fixtures import fixture_params

    b = fx.run_brief(monkeypatch, "QQQ", fx.loader_frame("QQQ"))["level_basis"]
    assert b["pmg_zones"], "the fixture session must have zones for this test to bite"
    stale = [{"center_price": 1.0, "level_names": ["old"], "timeframes": ["day"],
              "count": 2, "strength": "weak"}]
    legacy = _pre_parameter(b, stale)

    insufficient = fixture_params("QQQ", SESSION, statuses={"level_cluster_atr": "insufficient_history"})
    s = SessionLevels.from_basis(legacy, params=insufficient)
    assert s.pmg_zones == [] and s.pmg_status == "insufficient_history"

    ok = SessionLevels.from_basis(legacy, params=fixture_params("QQQ", SESSION))
    assert ok.pmg_status == "ok" and ok.pmg_zones == b["pmg_zones"]

    none = SessionLevels.from_basis(legacy)
    assert none.pmg_zones == [] and none.pmg_status == "params_unavailable"

    # A basis that recorded its parameters keeps its own zones.
    assert SessionLevels.from_basis(b, params=insufficient).pmg_zones == b["pmg_zones"]
