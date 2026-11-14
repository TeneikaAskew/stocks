"""FEAT-STRAT-001 done_when 11: the level_basis snapshot with each brief or plan.

* The brief writes level_basis (levels, ATR(14), the last daily bar date,
  the premarket snapshot with its own date, the picks) with each
  premarket_analysis and premarket_analysis_history row, as plain JSON.
* The planner, the signal monitor, the playbook resolver and the movement
  statement read the session's level_basis only from a run_kind = 'live'
  row and build through build_session_levels when none exists.
* A planner run for a brief ticker loads no daily bars, and rewriting
  market_data_daily after the brief leaves its structural levels unchanged.
* Every writer and reader still works when the column is absent.
* A newer premarket snapshot replaces the premarket candidates.

The live and replay rows sit in an in-memory SQLite premarket_analysis,
queried with each reader's own SQL. On origin/main none of this exists.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date

import pandas as pd
import pytest

from lib.strat_levels import (
    LEVEL_RULE_VERSION,
    SessionLevels,
    read_live_level_basis,
    read_session_premarket,
)
from tests.lib import strat_2026_11_06 as fx
from tests.lib.session_levels_helpers import basis

SESSION = fx.SESSION


@pytest.fixture(autouse=True)
def _level_params(monkeypatch):
    """The level parameter tables (per-ticker parameters, 2026-11-08) behind
    the strict reader every consumer uses: every key at the #1753 values."""
    from tests.lib.level_params_fixtures import install_level_params
    install_level_params(monkeypatch, ["QQQ", "SPY", "IWM", "TST"])


@pytest.fixture
def brief_basis(monkeypatch) -> dict:
    """The level_basis the 08:30 ET brief writes for QQQ on 2026-11-06."""
    return fx.run_brief(monkeypatch, "QQQ", fx.loader_frame("QQQ"))["level_basis"]


class _AnalysisDb:
    """premarket_analysis in SQLite. `with_column=False` is the schema
    before gcp/schema.sql adds level_basis."""

    def __init__(self, rows=(), *, with_column=True):
        self.conn = sqlite3.connect(":memory:")
        lb = ", level_basis TEXT" if with_column else ""
        self.conn.execute(f"CREATE TABLE premarket_analysis (ticker TEXT, analysis_date TEXT, "
                          f"run_kind TEXT{lb})")
        for r in rows:
            if with_column:
                self.conn.execute("INSERT INTO premarket_analysis VALUES (?,?,?,?)",
                                  (r["ticker"], r["date"], r["run_kind"], json.dumps(r["basis"])))
            else:
                self.conn.execute("INSERT INTO premarket_analysis VALUES (?,?,?)",
                                  (r["ticker"], r["date"], r["run_kind"]))
        self.conn.commit()

    def query(self, sql, params=None):
        p = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in (params or {}).items()}
        return pd.read_sql_query(sql, self.conn, params=p)


def _bogus(b: dict) -> dict:
    """The same basis with PDH moved to 999.99 and PQL (the first long
    target) to 659.00, inside the premarket range, so a read of it shows."""
    out = json.loads(json.dumps(b))
    for lv in out["levels"]:
        if lv["name"] == "PDH":
            lv["price"] = 999.99
        if lv["name"] == "PQL":
            lv["price"] = 659.0
    return out


def _row(b, run_kind="live", ticker="QQQ"):
    return {"ticker": ticker, "date": SESSION.isoformat(), "run_kind": run_kind, "basis": b}


# ── the writer ──────────────────────────────────────────────────────────

def test_brief_basis_is_plain_json_with_what_the_spec_lists(brief_basis):
    b = json.loads(json.dumps(brief_basis))            # no default=str needed
    assert b["rule_version"] == LEVEL_RULE_VERSION
    assert b["session_date"] == "2026-11-06" and b["last_bar_date"] == "2026-11-05"
    assert b["atr"] == pytest.approx(fx.prior_atr("QQQ"))
    assert b["premarket"]["date"] == "2026-11-06"
    assert b["premarket"]["pre_low"] == pytest.approx(649.62)
    assert {lv["name"] for lv in b["levels"]} >= {"PDH", "PDL", "PDC", "PWH", "PYH", "PMK_L"}
    assert b["long"]["trigger"]["name"] == "PMK_H" and b["short"]["trigger"]["name"] == "PMK_L"
    rebuilt = SessionLevels.from_basis(b)
    assert rebuilt.short.trigger == SessionLevels.from_basis(brief_basis).short.trigger


def test_persist_writes_level_basis_to_both_tables(monkeypatch, brief_basis):
    from gcp import database
    from gcp.premarket_brief import persist_to_cloud_sql
    captured = []
    monkeypatch.setattr(database, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(database, "bulk_insert_dataframe",
                        lambda df, table: captured.append((table, df.to_dict("records"))) or len(df))
    monkeypatch.setattr(database, "upsert_dataframe",
                        lambda df, table, keys: captured.append((table, df.to_dict("records"))) or len(df))
    monkeypatch.setattr(database, "row_exists", lambda *a, **k: False)
    monkeypatch.delenv("BRIEF_AS_OF", raising=False)      # a live run
    # Exits in thirds spec: the gating t1..t3 and the spaced plan targets
    # (the Design 8 calls) are written beside each other to both tables.
    prices = {"calls_t1_price": 253.0, "calls_t2_price": 275.0, "calls_t3_price": 280.0,
              "calls_plan_t1_price": 275.0, "calls_plan_t2_price": 280.0,
              "calls_plan_t3_price": 285.0, "puts_t1_price": 247.5, "puts_t2_price": 247.0,
              "puts_t3_price": 225.0, "puts_plan_t1_price": 225.0, "puts_plan_t2_price": 220.0,
              "puts_plan_t3_price": 215.0}
    brief = {"analysis_date": SESSION,
             "tickers": {"QQQ": {"status": None, "price": 647.05, "level_basis": brief_basis,
                                 **prices}}}
    persist_to_cloud_sql(brief, allow_update=True, run_kind="scheduled", triggered_by="test")
    tables = {t: rows for t, rows in captured}
    assert set(tables) == {"premarket_analysis_history", "premarket_analysis"}
    for rows in tables.values():
        assert rows[0]["level_basis"] == brief_basis
        assert {k: rows[0][k] for k in prices} == prices
    assert tables["premarket_analysis"][0]["run_kind"] == "live"


def test_writers_drop_the_column_when_it_is_absent(monkeypatch, brief_basis):
    """bulk_insert_dataframe and upsert_dataframe keep only the table's own
    columns, so a brief row with level_basis still writes before the
    schema change is applied."""
    import sqlalchemy as sa
    from gcp import database

    eng = sa.create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE premarket_analysis_history (ticker TEXT, analysis_date TEXT)"))
    monkeypatch.setattr(database, "get_engine", lambda: eng)
    df = pd.DataFrame([{"ticker": "QQQ", "analysis_date": "2026-11-06", "level_basis": brief_basis}])
    assert database.bulk_insert_dataframe(df, "premarket_analysis_history") == 1

    sent = []

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *e):
            return False

        def execute(self, stmt):
            sent.append(stmt)

    class _Eng:
        def begin(self):
            return _Conn()

    meta = sa.MetaData()
    tbl = sa.Table("premarket_analysis", meta, sa.Column("ticker", sa.Text, primary_key=True),
                   sa.Column("analysis_date", sa.Text, primary_key=True), sa.Column("price", sa.Float))
    monkeypatch.setattr(database, "get_engine", lambda: _Eng())
    monkeypatch.setitem(database._REFLECTED_TABLES, "premarket_analysis", tbl)
    df = pd.DataFrame([{"ticker": "QQQ", "analysis_date": "2026-11-06", "price": 647.05,
                        "level_basis": brief_basis}])
    assert database.upsert_dataframe(df, "premarket_analysis", ["ticker", "analysis_date"]) == 1
    assert "level_basis" not in str(sent[0])


def test_upsert_binds_level_basis_as_jsonb_when_present(monkeypatch, brief_basis):
    import sqlalchemy as sa
    from sqlalchemy.dialects import postgresql
    from gcp import database

    sent = []

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *e):
            return False

        def execute(self, stmt):
            sent.append(stmt)

    class _Eng:
        def begin(self):
            return _Conn()

    meta = sa.MetaData()
    tbl = sa.Table("premarket_analysis", meta, sa.Column("ticker", sa.Text, primary_key=True),
                   sa.Column("analysis_date", sa.Text, primary_key=True),
                   sa.Column("level_basis", postgresql.JSONB))
    monkeypatch.setattr(database, "get_engine", lambda: _Eng())
    monkeypatch.setitem(database._REFLECTED_TABLES, "premarket_analysis", tbl)
    df = pd.DataFrame([{"ticker": "QQQ", "analysis_date": "2026-11-06", "level_basis": brief_basis}])
    database.upsert_dataframe(df, "premarket_analysis", ["ticker", "analysis_date"])
    compiled = sent[0].compile(dialect=postgresql.dialect())
    bound = [v for k, v in compiled.params.items() if k.startswith("level_basis")]
    assert bound == [brief_basis]


# ── the planner ─────────────────────────────────────────────────────────

def test_planner_for_a_brief_ticker_loads_no_daily_bars(monkeypatch, brief_basis):
    section, ctx, _plans, loads = fx.run_planner(
        monkeypatch, "QQQ", fx.loader_frame("QQQ"), "short", live_basis=brief_basis)
    assert loads == 0 and section["source"] == "level_basis"
    assert ctx.levels.short.trigger["name"] == "PMK_L"


def test_rewriting_daily_bars_after_the_brief_changes_no_planner_level(monkeypatch, brief_basis):
    frame = fx.loader_frame("QQQ")
    frame.loc[pd.Timestamp("2026-11-05"), ["High", "Low", "Close"]] = [900.0, 100.0, 500.0]
    _s, ctx, _p, loads = fx.run_planner(monkeypatch, "QQQ", frame, "long", live_basis=brief_basis)
    assert loads == 0
    stored = {lv["name"]: lv["price"] for lv in brief_basis["levels"]}
    got = {lv.name: lv.price for lv in ctx.levels.levels}
    for name in ("PDH", "PDL", "PDC", "PWH", "PWL", "PMH", "PQL", "PYH"):
        assert got[name] == pytest.approx(stored[name]), name


def test_planner_applies_a_newer_premarket_snapshot(monkeypatch):
    """Stored pre_high 101, newer pre_high 102, reference 100.5, ATR 3,
    next structural level 105: the long trigger is the new high 102."""
    from lib.agents import summarizers
    stored = basis({"PWH": 105.0, "PWL": 95.0}, prior_close=100.0, atr=3.0, ticker="TST",
                   premarket={"pre_high": 101.0, "pre_low": 99.5, "pre_vwap": 100.5})
    assert SessionLevels.from_basis(stored).long.trigger["price"] == 101.0

    def q(sql, params=None):
        if "level_basis" in sql:
            return pd.DataFrame([{"ticker": "TST", "level_basis": json.dumps(stored)}])
        if "pre_high" in sql:
            return pd.DataFrame([{"date": SESSION, "pre_high": 102.0, "pre_low": 99.5,
                                  "pre_vwap": 100.5, "gap_pct": 0.0,
                                  "pre_filter_status": "ok"}])
        return pd.DataFrame()

    monkeypatch.setattr(summarizers, "_query", q)
    out = summarizers.summarize_session_levels("TST", as_of=SESSION, loader=object())
    sl = SessionLevels.from_basis(out["level_basis"])
    assert out["source"] == "level_basis"
    assert sl.long.trigger["price"] == 102.0 and sl.long.trigger["name"] == "PMK_H"
    assert sl.level_named("PWH").price == 105.0


def test_a_declining_low_replaces_the_short_candidate():
    stored = basis({"PWH": 105.0, "PWL": 95.0}, prior_close=100.0, atr=3.0,
                   premarket={"pre_high": 100.5, "pre_low": 99.0, "pre_vwap": 99.5})
    sl = SessionLevels.from_basis(stored)
    assert sl.short.trigger["price"] == 99.0
    newer = sl.with_premarket({"date": SESSION.isoformat(), "pre_high": 100.5,
                               "pre_low": 98.0, "pre_vwap": 99.5, "pre_filter_status": "ok"})
    assert newer.short.trigger["price"] == 98.0 and newer.short.trigger["name"] == "PMK_L"
    assert [lv.price for lv in newer.levels if lv.name == "PMK_L"] == [98.0]


# ── live rows only, on every reader ─────────────────────────────────────

def test_read_live_level_basis_ignores_a_replay_row(brief_basis):
    db = _AnalysisDb([_row(_bogus(brief_basis), run_kind="replay")])
    assert read_live_level_basis(db.query, "QQQ", SESSION) is None
    db = _AnalysisDb([_row(_bogus(brief_basis), "replay"), _row(brief_basis, "live")])
    got = read_live_level_basis(db.query, "QQQ", SESSION)
    assert {lv["name"]: lv["price"] for lv in got["levels"]}["PDH"] != 999.99


def _planner_section(monkeypatch, db):
    from lib.agents import summarizers
    frame = fx.loader_frame("QQQ")
    snap = fx.premarket_snapshot_row(frame)

    def q(sql, params=None):
        if "premarket_analysis" in sql:
            return db.query(sql, params)
        if "pre_high" in sql:
            return snap
        return pd.DataFrame()

    class _L:
        def load_daily(self, *a, **k):
            return frame.copy()

    monkeypatch.setattr(summarizers, "_query", q)
    return summarizers.summarize_session_levels("QQQ", as_of=SESSION, loader=_L())


def _monitor_session(monkeypatch, db):
    import gcp.database as database
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from gcp import signal_monitor as sm
    monkeypatch.setattr(database, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(database, "query_to_dataframe", db.query)
    monitor = sm.SignalMonitor()
    monitor.webhook_url = ""
    monitor.replay_clock_ts = datetime(2026, 11, 6, 9, 0, tzinfo=ZoneInfo("America/New_York"))
    frame = fx.loader_frame("QQQ")

    class _L:
        def __init__(self, *a, **k):
            pass

        def load_daily(self, *a, **k):
            return frame.copy()

    monkeypatch.setattr("lib.data_loader.DataLoader", _L)
    monitor.refresh_level_map("QQQ")
    return monitor.session_levels["QQQ"]


def _movement_map(monkeypatch, db):
    import sys
    from pathlib import Path
    pytest.importorskip("fastapi")
    root = Path(__file__).resolve().parents[2]
    for p in (str(root / "platform"), str(root / "platform" / "api")):
        if p not in sys.path:
            sys.path.insert(0, p)
    from routers import dashboard
    from lib.data_loader import DataLoader
    monkeypatch.setattr(dashboard, "_query_fn", db.query)
    monkeypatch.setattr(DataLoader, "load_daily", lambda *a, **k: fx.loader_frame("QQQ"))
    return dashboard._build_movement_level_map("QQQ", analysis_date=SESSION)


def _resolver_inputs(db, *, with_provenance=True):
    import sqlalchemy as sa
    from gcp.premarket_playbook_resolver import derive_level_map_from_daily
    from lib.indicators import calculate_atr
    from tests.lib.level_params_fixtures import legacy_db
    eng = sa.create_engine("sqlite://", creator=lambda: db.conn)
    legacy_db("QQQ", conn=db.conn)   # the level parameter tables, same database
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
        "ticker": "QQQ", "date": SESSION.isoformat(), "open": None, "high": None, "low": None,
        "close": None, "atr_14": None, "atr_5": None, "strat_candle": "", "strat_combo": "",
        **{k: snap[k] for k in ("pre_high", "pre_low", "pre_vwap", "gap_pct",
                                "pre_filter_status")}}])],
        ignore_index=True)
    if not with_provenance:
        # market_data_daily before the provenance and filter-status columns.
        daily = daily.drop(columns=["pre_fetched_at", "pre_excluded_stale_prints",
                                    "pre_excluded_spikes", "pre_filter_status",
                                    "pre_filter_params"])
    daily.to_sql("market_data_daily", eng, index=False, if_exists="replace")
    return derive_level_map_from_daily("QQQ", SESSION, eng)


def _pdh_of(reader, monkeypatch, db):
    if reader == "planner":
        b = _planner_section(monkeypatch, db)["level_basis"]
        return {lv["name"]: lv["price"] for lv in b["levels"]}["PDH"]
    if reader == "signal_monitor":
        return _monitor_session(monkeypatch, db).level_named("PDH").price
    if reader == "movement_statement":
        lm = _movement_map(monkeypatch, db)
        return next(lv.price for lv in lm.levels if lv.name == "PDH")
    raise AssertionError(reader)


@pytest.mark.parametrize("reader", ["planner", "signal_monitor", "movement_statement"])
def test_each_live_reader_ignores_a_replay_row(monkeypatch, brief_basis, reader):
    real_pdh = {lv["name"]: lv["price"] for lv in brief_basis["levels"]}["PDH"]
    replay_only = _AnalysisDb([_row(_bogus(brief_basis), "replay")])
    assert _pdh_of(reader, monkeypatch, replay_only) == pytest.approx(real_pdh)
    live = _AnalysisDb([_row(_bogus(brief_basis), "live")])
    assert _pdh_of(reader, monkeypatch, live) == pytest.approx(999.99)   # it reads a live row


@pytest.mark.parametrize("reader", ["planner", "signal_monitor", "movement_statement"])
def test_each_reader_builds_when_the_column_is_absent(monkeypatch, brief_basis, reader):
    real_pdh = {lv["name"]: lv["price"] for lv in brief_basis["levels"]}["PDH"]
    no_column = _AnalysisDb([_row(brief_basis)], with_column=False)
    assert _pdh_of(reader, monkeypatch, no_column) == pytest.approx(real_pdh)


def test_resolver_reads_live_basis_ignores_replay_and_builds_without_the_column(brief_basis):
    bogus = _bogus(brief_basis)
    built = _resolver_inputs(_AnalysisDb([_row(bogus, "replay")]))
    assert built["calls_trigger_price"] == pytest.approx(660.398)
    assert built["calls_t1_price"] == pytest.approx(661.14)
    live = _resolver_inputs(_AnalysisDb([_row(bogus, "live")]))
    assert live["calls_t1_price"] != pytest.approx(661.14)        # read the live row
    absent = _resolver_inputs(_AnalysisDb([_row(bogus)], with_column=False))
    assert absent["calls_t1_price"] == pytest.approx(661.14)


# ── A failed read is never "no premarket" (Codex review on #1753) ──────────


def _raising(exc):
    def q(sql, params=None):
        raise exc
    return q


def test_read_session_premarket_raises_on_a_failed_query():
    with pytest.raises(TimeoutError):
        read_session_premarket(_raising(TimeoutError("statement timeout")), "SPY", "2026-11-06")


def test_read_session_premarket_retries_without_provenance_on_a_missing_column():
    calls = []

    def q(sql, params=None):
        calls.append(sql)
        if "pre_fetched_at" in sql:
            raise RuntimeError('column "pre_fetched_at" does not exist')
        return pd.DataFrame([{"pre_high": 738.04, "pre_low": 730.64,
                              "pre_vwap": 734.0, "gap_pct": -0.5}])

    snap = read_session_premarket(q, "SPY", "2026-11-06")
    assert len(calls) == 2
    assert snap["pre_high"] == 738.04 and snap["date"] == "2026-11-06"


def test_read_live_level_basis_raises_on_a_failed_query_and_none_on_a_missing_column():
    with pytest.raises(ConnectionError):
        read_live_level_basis(_raising(ConnectionError("server closed the connection")),
                              "SPY", "2026-11-06")
    missing = _raising(RuntimeError('column "level_basis" does not exist'))
    assert read_live_level_basis(missing, "SPY", "2026-11-06") is None


# ── exits in thirds spec, Design 7: level_basis and the rule version ───

EXIT_KEYS = ("target_min_spacing_atr", "gap_fill_flag_atr", "exit_legs", "entry_cutoff_et")


def _exit_picks(sl):
    return [([round(r["price"], 2) for r in side.targets],
             [round(r["price"], 2) for r in side.gate_targets],
             [round(r["price"], 2) for r in side.skipped], side.target_status)
            for side in (sl.long, sl.short)]


def test_v3_basis_records_the_exit_parameters():
    from tests.lib.session_levels_helpers import d8_basis
    stored = json.loads(json.dumps(SessionLevels.from_basis(d8_basis()).to_basis()))
    assert LEVEL_RULE_VERSION == stored["rule_version"] == "feat-strat-001.v3"
    for key in EXIT_KEYS:
        p = stored["params"][key]
        assert p["status"] == "ok" and p["value"] is not None
        assert p["method_id"] and p["effective_from"]
    assert stored["params"]["target_min_spacing_atr"]["value"] == 0.25
    assert stored["params"]["exit_legs"]["value"] == 3.0
    assert stored["long"]["plan"]["legs"] == 3


def test_from_basis_v3_rebuilds_the_recorded_plan_after_the_row_changes():
    from tests.lib.session_levels_helpers import d8_basis, d8_params
    stored = json.loads(json.dumps(SessionLevels.from_basis(d8_basis()).to_basis()))
    rebuilt = SessionLevels.from_basis(stored)
    offered = SessionLevels.from_basis(stored, params=d8_params(spacing=0.05))
    want = [([275.0, 280.0, 285.0], [253.0, 275.0, 280.0], [253.0], "ok"),
            ([225.0, 220.0, 215.0], [247.5, 247.0, 225.0], [247.5, 247.0], "ok")]
    assert _exit_picks(rebuilt) == _exit_picks(offered) == want


def test_from_basis_v2_rebuilds_the_v2_targets():
    """A stored feat-strat-001.v2 basis records no spacing: it rebuilds the
    v2 targets (the gating ones), no skipped list and no plan, and the brief
    copy is the v2 copy."""
    from tests.lib.session_levels_helpers import d8_basis
    stored = json.loads(json.dumps(d8_basis()))
    stored["rule_version"] = "feat-strat-001.v2"
    for key in EXIT_KEYS:
        stored["params"].pop(key)
    rebuilt = SessionLevels.from_basis(stored)
    assert rebuilt.to_basis()["rule_version"] == "feat-strat-001.v2"
    assert _exit_picks(rebuilt) == [([253.0, 275.0, 280.0], [253.0, 275.0, 280.0], [], "ok"),
                                    ([247.5, 247.0, 225.0], [247.5, 247.0, 225.0], [], "ok")]
    assert rebuilt.long.plan is None
    lm = rebuilt.to_level_map()
    assert "plan" not in lm.calls_trigger
    from lib.strat_levels import format_levels_for_brief
    text = format_levels_for_brief(lm, "neutral")
    assert "    T1: 253.00 (PDH)\n" in text and "sell" not in text


def test_a_replay_with_no_spacing_row_publishes_no_unspaced_target():
    """A session the history run did not cover for the exits keys reads
    target_min_spacing_atr as params_unavailable: the side keeps its
    trigger and stop and publishes no target, never the unspaced ones."""
    from tests.lib.level_params_fixtures import LEGACY_1753_VALUES, ParamsDb
    from tests.lib.session_levels_helpers import D8_LEVELS, D8_PREMARKET
    db = ParamsDb()
    db.write("TST", {k: v for k, v in LEGACY_1753_VALUES.items()
                     if k not in ("target_min_spacing_atr", "gap_fill_flag_atr")},
             effective_from=date(2015, 1, 2))
    lp = db.load(["TST"], SESSION)["TST"]
    assert lp.status("target_min_spacing_atr") == "params_unavailable"
    sl = SessionLevels.from_basis(basis(D8_LEVELS, prior_close=247.0, atr=14.0,
                                        premarket=D8_PREMARKET, params=lp))
    for side in (sl.long, sl.short):
        assert side.trigger is not None and side.stop is not None
        assert side.targets == [] and side.target_status == "params_unavailable"


# ── ATR levels spec (2026-11-11): level_basis and replay ────────────────

ATR_RUNG_PARAM_KEYS = ("atr_rung_anchors", "atr_rung_step_atr", "atr_rung_max_atr",
                       "atr_rung_stretch_atr")
SESSION_D8 = "2026-11-06"     # the Design 8 fixture's session
ATR_BASIS_KEYS = ("atr_rungs", "atr_rungs_dropped", "atr_rung_status", "atr_rung_anchors",
                  "atr_rung_params")


def _rungs(sl):
    return ([(r["price"], r["name"]) for r in sl.atr_rungs],
            [(r["price"], r["name"], r["reason"]) for r in sl.atr_rungs_dropped])


def test_basis_records_the_atr_rungs_and_their_parameters():
    from tests.lib.session_levels_helpers import d8_basis
    stored = json.loads(json.dumps(SessionLevels.from_basis(d8_basis()).to_basis()))
    assert stored["atr_rung_status"] == "ok"
    kept = stored["atr_rungs"]
    assert [(r["price"], r["anchor"], r["multiple"], r["sign"], r["stretch"], r["aliases"])
            for r in kept] == [(234.2, "PMK_L", 1.0, "-", False, []),
                               (241.2, "PMK_L", 0.5, "-", False, []),
                               (259.1, "PMK_H", 0.5, "+", False, []),
                               (266.1, "PMK_H", 1.0, "+", False, [])]
    dropped = stored["atr_rungs_dropped"]
    assert len(dropped) == 28
    assert all({"price", "anchor", "multiple", "reason"} <= set(r) for r in dropped)
    assert [(a["name"], a["price"], a["status"]) for a in stored["atr_rung_anchors"]] == [
        ("PDH", 253.0, "ok"), ("PDL", 247.5, "ok"), ("PMK_H", 252.1, "ok"), ("PMK_L", 248.2, "ok")]
    params = stored["atr_rung_params"]
    assert set(params) == set(ATR_RUNG_PARAM_KEYS)
    for key in ATR_RUNG_PARAM_KEYS:
        assert set(params[key]) == {"value", "status", "method_id", "effective_from"}
        assert params[key]["status"] == "ok" and params[key]["effective_from"]
    assert params["atr_rung_anchors"]["value"] == ["PDH", "PDL", "PMK_H", "PMK_L"]
    assert params["atr_rung_anchors"]["method_id"] == "policy"
    assert (params["atr_rung_step_atr"]["value"], params["atr_rung_max_atr"]["value"],
            params["atr_rung_stretch_atr"]["value"]) == (0.5, 2.0, 1.5)
    # The rungs are never levels, candidates or targets in the stored basis.
    names = [lv["name"] for lv in stored["levels"]]
    names += [c["name"] for side in ("long", "short") for c in stored[side]["candidates"]]
    assert not any(n.endswith("ATR") for n in names)


def test_from_basis_rebuilds_the_recorded_rungs_after_the_rows_change():
    """A later ticker_level_params or policy row (offered as params) does
    not move a recorded basis's rungs: the recorded parameters rebuild."""
    from tests.lib.session_levels_helpers import d8_basis, d8_params
    first = SessionLevels.from_basis(d8_basis())
    stored = json.loads(json.dumps(first.to_basis()))
    rebuilt = SessionLevels.from_basis(stored)
    offered = SessionLevels.from_basis(stored, params=d8_params(
        anchors=["PDC"], atr_rung_step_atr=0.25, atr_rung_max_atr=3.0))
    assert _rungs(rebuilt) == _rungs(offered) == _rungs(first)
    assert rebuilt.to_basis()["atr_rungs"] == stored["atr_rungs"]
    assert rebuilt.to_basis()["atr_rungs_dropped"] == stored["atr_rungs_dropped"]


def test_a_basis_without_the_atr_keys_rebuilds_no_rungs_and_the_same_targets():
    """A level_basis stored before ATR rungs (no rung keys, no rung
    parameters recorded) rebuilds none, even when the rows in force are
    offered, and its targets, stop and gate targets are unchanged."""
    from tests.lib.session_levels_helpers import d8_basis, d8_params
    new = SessionLevels.from_basis(d8_basis())
    stored = json.loads(json.dumps(new.to_basis()))
    for k in ATR_BASIS_KEYS:
        stored.pop(k)
    for k in ATR_RUNG_PARAM_KEYS:
        stored["params"].pop(k)
    old = SessionLevels.from_basis(stored, params=d8_params())
    assert old.atr_rungs == [] and old.atr_rungs_dropped == [] and old.atr_rung_status is None
    assert not set(ATR_BASIS_KEYS) & set(old.to_basis())
    assert old.to_level_map().atr_levels is None
    assert _exit_picks(old) == _exit_picks(new)
    assert (old.long.stop, old.short.stop) == (new.long.stop, new.short.stop)
    assert old.with_premarket({"date": SESSION_D8, "pre_high": 253.5, "pre_low": 246.0,
                               "pre_vwap": 250.0, "pre_filter_status": "ok"}).atr_rungs == []


def test_with_premarket_rebuilds_the_premarket_rungs():
    from tests.lib.session_levels_helpers import d8_basis
    sl = SessionLevels.from_basis(d8_basis())
    newer = sl.with_premarket({"date": SESSION_D8, "pre_high": 253.60, "pre_low": 247.80,
                               "pre_vwap": 250.00, "pre_filter_status": "ok"})
    pmk = sorted((r["price"], r["label"]) for r in newer.atr_rungs + newer.atr_rungs_dropped
                 if r["anchor"] in ("PMK_H", "PMK_L"))
    assert (260.6, "PMK_H+0.5") in pmk and (240.8, "PMK_L-0.5") in pmk
    assert (259.1, "PMK_H+0.5") not in pmk and (241.2, "PMK_L-0.5") not in pmk
    anchors = {a["name"]: a["price"] for a in newer.atr_rung_anchors}
    assert (anchors["PMK_H"], anchors["PMK_L"]) == (253.6, 247.8)
    # PDH and PDL rungs are the same as before the newer snapshot.
    def pd(s):
        return sorted(r["cents"] for r in s.atr_rungs + s.atr_rungs_dropped
                      if r["anchor"] in ("PDH", "PDL"))
    assert pd(newer) == pd(sl)


def test_published_prices_include_the_kept_rungs():
    from lib.strat_levels import price_cents
    from tests.lib.session_levels_helpers import d8_basis
    sl = SessionLevels.from_basis(d8_basis())
    known = sl.published_prices()
    assert {25910, 26610, 24120, 23420} <= known
    assert {price_cents(lv.price) for lv in sl.levels} <= known
    level_cents = {price_cents(lv.price) for lv in sl.levels}
    dropped_off_level = {r["cents"] for r in sl.atr_rungs_dropped} - level_cents
    assert dropped_off_level and not (dropped_off_level & known)
