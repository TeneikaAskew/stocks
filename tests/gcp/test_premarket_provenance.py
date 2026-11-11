"""FEAT-STRAT-001 done_when 11, provenance: level_basis carries the premarket
snapshot's fetch time and its excluded-print counts.

The two writers (gcp/fetchers/fetch_premarket_refresh.py and
gcp/fetchers/fetch_market_data.py) record pre_fetched_at,
pre_excluded_stale_prints and pre_excluded_spikes on market_data_daily from
lib.indicators.calculate_premarket_context; the readers that build the
premarket snapshot pass them to lib.strat_levels.build_session_levels, which
puts them in level_basis['premarket'].

Production does not have the columns until the owner applies the schema
block, so every writer and reader is also run against a table without them.
Per-ticker parameters (2026-11-08) add pre_filter_status and
pre_filter_params: a snapshot read from a table without pre_filter_status is
still read, and the builder refuses it as premarket_unfiltered, because its
prints were not shown to be filtered with the ticker's thresholds.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pandas as pd
import pytest

from lib.strat_levels import (
    build_session_levels, premarket_snapshot_from_daily, read_session_premarket,
)
from tests.gcp.test_premarket_filter_callers import _Db, _run_nightly, _run_refresh
from tests.lib import strat_2026_11_06 as fx
from tests.lib.level_params_fixtures import fixture_params, install_level_params

SESSION = fx.SESSION


@pytest.fixture(autouse=True)
def _level_params(monkeypatch):
    install_level_params(monkeypatch, ["QQQ", "SPY", "IWM"])
FETCHED = datetime(2026, 11, 6, 13, 20, 4, tzinfo=timezone.utc)   # 08:20:04 ET
PROVENANCE = {"pre_fetched_at": FETCHED, "pre_excluded_stale_prints": 3,
              "pre_excluded_spikes": 1}


def _frame_with_provenance(ticker="QQQ", provenance=PROVENANCE):
    frame = fx.loader_frame(ticker)
    for col in PROVENANCE:
        frame[col] = None
    for col, v in provenance.items():
        frame.loc[frame.index.normalize() == pd.Timestamp(SESSION), col] = v
    return frame


def _build(ticker, frame):
    d = fx.daily(ticker)
    snap = premarket_snapshot_from_daily(frame, SESSION)
    return build_session_levels(ticker, SESSION, d, {"atr_14": fx.prior_atr(ticker)}, snap,
                                fixture_params(ticker, SESSION))


# ── the counts and fetch time reach level_basis ─────────────────────────

def test_daily_frame_snapshot_carries_provenance_into_level_basis():
    pm = _build("QQQ", _frame_with_provenance()).to_basis()["premarket"]
    assert pm["fetched_at"] == "2026-11-06T13:20:04+00:00"
    assert pm["excluded_stale_prints"] == 3
    assert pm["excluded_spikes"] == 1
    assert pm["excluded_bars"] == 4
    assert pm["pre_low"] == pytest.approx(649.62)


def test_naive_fetch_time_is_read_as_utc():
    frame = _frame_with_provenance(provenance={**PROVENANCE,
                                               "pre_fetched_at": "2026-11-06 13:20:04"})
    pm = _build("QQQ", frame).to_basis()["premarket"]
    assert pm["fetched_at"] == "2026-11-06T13:20:04+00:00"


def test_level_basis_round_trip_keeps_provenance():
    from lib.strat_levels import SessionLevels
    b = _build("QQQ", _frame_with_provenance()).to_basis()
    again = SessionLevels.from_basis(b).to_basis()["premarket"]
    assert again["fetched_at"] == b["premarket"]["fetched_at"]
    assert again["excluded_stale_prints"] == 3 and again["excluded_spikes"] == 1


def test_brief_level_basis_carries_provenance(monkeypatch):
    b = fx.run_brief(monkeypatch, "QQQ", _frame_with_provenance())["level_basis"]
    assert b["premarket"]["fetched_at"] == "2026-11-06T13:20:04+00:00"
    assert b["premarket"]["excluded_stale_prints"] == 3
    assert b["premarket"]["excluded_spikes"] == 1


def test_planner_reads_provenance_from_market_data_daily(monkeypatch):
    from lib.agents import summarizers
    frame = fx.loader_frame("QQQ")
    seen = []

    def q(sql, params=None):
        seen.append(sql)
        if "premarket_analysis" in sql:
            return pd.DataFrame()
        if "pre_high" in sql:
            snap = fx.session_premarket("QQQ")
            return pd.DataFrame([{**snap, "date": SESSION, **PROVENANCE}])
        return pd.DataFrame()

    class _L:
        def load_daily(self, *a, **k):
            return frame.copy()

    monkeypatch.setattr(summarizers, "_query", q)
    out = summarizers.summarize_session_levels("QQQ", as_of=SESSION, loader=_L())
    pm = out["level_basis"]["premarket"]
    assert pm["fetched_at"] == "2026-11-06T13:20:04+00:00"
    assert (pm["excluded_stale_prints"], pm["excluded_spikes"]) == (3, 1)
    assert any("pre_fetched_at" in s for s in seen)


def test_refresh_writer_records_fetch_time_and_counts(monkeypatch):
    before = datetime.now(timezone.utc)
    out = _run_refresh(monkeypatch, "QQQ", _Db("QQQ"))
    assert before <= out["pre_fetched_at"] <= datetime.now(timezone.utc)
    assert out["pre_fetched_at"].tzinfo is not None
    assert out["pre_excluded_stale_prints"] == out["excluded_prior_close_prints"] > 0
    assert out["pre_excluded_spikes"] == out["excluded_spike_prints"]


def test_nightly_writer_records_fetch_time_and_counts(monkeypatch):
    before = datetime.now(timezone.utc)
    row = _run_nightly(monkeypatch, "QQQ", _Db("QQQ"))
    pm = fx.premarket_context("QQQ")
    assert before <= row["pre_fetched_at"] <= datetime.now(timezone.utc)
    assert row["pre_excluded_stale_prints"] == pm["excluded_prior_close_prints"] > 0
    assert row["pre_excluded_spikes"] == pm["excluded_spike_prints"]


class _Conn:
    def __init__(self, log, columns):
        self.log, self.columns = log, columns

    def execute(self, sql, params=None):
        text = str(sql)
        if "information_schema" in text:
            if self.columns is None:
                raise RuntimeError("no information_schema")
            return type("R", (), {"fetchall": lambda s: [(c,) for c in self.columns]})()
        self.log.append((text, params))


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *a):
        return False


class _Engine:
    def __init__(self, columns):
        self.log = []
        self.conn = _Conn(self.log, columns)

    def connect(self):
        return _Ctx(self.conn)

    def begin(self):
        return _Ctx(self.conn)


_REFRESH_ROW = {"ticker": "QQQ", "date": SESSION, "pre_high": 660.4, "pre_low": 649.62,
                "pre_vwap": 655.0, "pre_volume": 1000, "gap_pct": -0.3, **PROVENANCE}


def test_refresh_upsert_writes_provenance_when_the_columns_exist(monkeypatch):
    from gcp import database
    from gcp.fetchers import fetch_premarket_refresh as fpr
    eng = _Engine(["pre_fetched_at", "pre_excluded_stale_prints", "pre_excluded_spikes",
                   "pre_filter_status", "pre_filter_params"])
    monkeypatch.setattr(database, "get_engine", lambda: eng)
    row = {**_REFRESH_ROW, "pre_filter_status": "ok", "pre_filter_params": "{}"}
    assert fpr.upsert_premarket([row]) == 1
    sql, params = eng.log[0]
    for col in PROVENANCE:
        assert f":{col}" in sql
    assert "pre_fetched_at = COALESCE(EXCLUDED.pre_fetched_at, market_data_daily.pre_fetched_at)" in sql
    # The filter status and its counts describe this snapshot only: overwritten.
    for col in ("pre_excluded_stale_prints", "pre_excluded_spikes", "pre_filter_status",
                "pre_filter_params"):
        assert f"{col} = EXCLUDED.{col}" in sql
    assert "CAST(:pre_filter_params AS JSONB)" in sql
    assert params["pre_filter_status"] == "ok"
    assert params["pre_fetched_at"] == FETCHED
    assert params["pre_excluded_stale_prints"] == 3 and params["pre_excluded_spikes"] == 1


# ── a row with the columns missing still builds ────────────────────────

@pytest.mark.parametrize("columns", [[], ["pre_fetched_at"], None,
                                     ["pre_fetched_at", "pre_excluded_stale_prints",
                                      "pre_excluded_spikes"]])
def test_refresh_upsert_leaves_the_columns_out_when_absent(monkeypatch, columns):
    from gcp import database
    from gcp.fetchers import fetch_premarket_refresh as fpr
    eng = _Engine(columns)
    monkeypatch.setattr(database, "get_engine", lambda: eng)
    assert fpr.upsert_premarket([dict(_REFRESH_ROW)]) == 1
    sql, params = eng.log[0]
    assert "pre_fetched_at" not in sql and "pre_excluded" not in sql
    assert ":gap_pct" in sql and params["pre_low"] == pytest.approx(649.62)


def test_nightly_row_to_a_table_without_the_columns_drops_them(monkeypatch):
    """upsert_dataframe keeps only the table's own columns, so the nightly
    row's provenance keys are dropped while market_data_daily lacks them."""
    import sqlalchemy as sa
    from gcp import database
    row = _run_nightly(monkeypatch, "QQQ", _Db("QQQ"))
    monkeypatch.undo()

    eng = sa.create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE market_data_daily (ticker TEXT, date TEXT, "
                          "pre_high REAL, pre_low REAL, PRIMARY KEY (ticker, date))"))
    sent = []

    class _C:
        def execute(self, stmt, params=None):
            from sqlalchemy.dialects import postgresql
            sent.append(str(stmt.compile(dialect=postgresql.dialect())))

    class _B:
        def __enter__(self):
            return _C()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(database, "get_engine", lambda: eng)
    monkeypatch.setattr(database, "_REFLECTED_TABLES", {})
    monkeypatch.setattr(eng, "begin", lambda: _B(), raising=False)
    df = pd.DataFrame([{k: row[k] for k in ("ticker", "pre_high", "pre_low", *PROVENANCE)}])
    df["date"] = SESSION.isoformat()
    assert row["pre_excluded_stale_prints"] > 0
    database.upsert_dataframe(df, "market_data_daily", ["ticker", "date"])
    assert sent and "INSERT INTO market_data_daily" in sent[0]
    assert "pre_low" in sent[0]
    assert all("pre_fetched_at" not in s and "pre_excluded" not in s for s in sent)


def test_frame_without_the_columns_builds_with_null_provenance():
    pm = _build("QQQ", fx.loader_frame("QQQ")).to_basis()["premarket"]
    assert pm["pre_low"] == pytest.approx(649.62)
    assert pm["fetched_at"] is None
    assert pm["excluded_stale_prints"] is None and pm["excluded_spikes"] is None
    assert pm["excluded_bars"] is None


def test_read_session_premarket_falls_back_without_the_columns():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE market_data_daily (ticker TEXT, date TEXT, pre_high REAL, "
                 "pre_low REAL, pre_vwap REAL, gap_pct REAL)")
    s = fx.session_premarket("QQQ")
    conn.execute("INSERT INTO market_data_daily VALUES (?,?,?,?,?,?)",
                 ("QQQ", SESSION.isoformat(), s["pre_high"], s["pre_low"], s["pre_vwap"],
                  s["gap_pct"]))
    conn.commit()          # pandas rolls back after the failed extended read
    calls = []

    def q(sql, params):
        calls.append(sql)
        return pd.read_sql_query(sql, conn, params=params)

    snap = read_session_premarket(q, "QQQ", SESSION)
    assert len(calls) == 2 and "pre_fetched_at" in calls[0] and "pre_fetched_at" not in calls[1]
    assert snap["pre_low"] == pytest.approx(649.62)
    assert snap["fetched_at"] is None and snap["excluded_spikes"] is None
    assert snap.get("pre_filter_status") is None
    sl = build_session_levels("QQQ", SESSION, fx.daily("QQQ"), {"atr_14": fx.prior_atr("QQQ")},
                              snap, fixture_params("QQQ", SESSION))
    assert sl.to_basis()["premarket"] is None
    assert sl.premarket_status == "premarket_unfiltered"


def test_read_session_premarket_falls_back_when_the_query_swallows_errors():
    """summarizers._query returns an empty frame on any SQL error, so an
    empty extended read is retried without the columns."""
    snap_row = pd.DataFrame([{**fx.session_premarket("QQQ"), "date": SESSION}])
    snap = read_session_premarket(
        lambda sql, p: pd.DataFrame() if "pre_fetched_at" in sql else snap_row, "QQQ", SESSION)
    assert snap is not None and snap["pre_low"] == pytest.approx(649.62)


def test_resolver_builds_from_a_table_without_the_columns():
    """With the columns the session's filtered premarket low is the put
    trigger; without them the resolver still builds, and the snapshot (not
    shown to be filtered) is refused, so no premarket price is a pick."""
    from tests.gcp.test_level_basis import _AnalysisDb, _resolver_inputs
    out = _resolver_inputs(_AnalysisDb())
    assert out is not None
    assert out["puts_trigger_name"] == "PMK_L"
    assert out["puts_trigger_price"] == pytest.approx(649.62)
    bare = _resolver_inputs(_AnalysisDb(), with_provenance=False)
    assert bare is not None
    assert bare["puts_trigger_name"] != "PMK_L" and bare["calls_trigger_name"] != "PMK_H"


def test_data_loader_retries_without_the_columns(monkeypatch):
    from lib import data_loader as dl
    monkeypatch.setattr(dl, "_PREMARKET_PROVENANCE_PRESENT", None)
    rows = pd.DataFrame([{"date": "2026-11-05", "Open": 1.0, "High": 2.0, "Low": 0.5,
                          "Close": 1.5, "Volume": 10, "atr_14": 0.4, "pre_high": None}])
    calls = []

    def fake(sql, params=None):
        if "information_schema" in sql:
            # The table's column list: it has date and atr_5, not the
            # provenance columns.
            return pd.DataFrame({"column_name": ["date", "atr_5"]})
        calls.append(sql)
        return pd.DataFrame() if "pre_fetched_at" in sql else rows.copy()

    monkeypatch.setattr(dl, "_ATR5_PRESENT", True)
    monkeypatch.setattr(dl, "_query_cloud_sql", fake)
    loader = dl.DataLoader.__new__(dl.DataLoader)
    df = loader._load_daily_from_sql("QQQ", None)
    assert len(df) == 1 and "ATR14" in df.columns
    assert len(calls) == 2 and "pre_fetched_at" not in calls[1]
    assert dl._PREMARKET_PROVENANCE_PRESENT is False
    calls.clear()
    loader._load_daily_from_sql("QQQ", None)
    assert len(calls) == 1 and "pre_fetched_at" not in calls[0]


def test_data_loader_transient_error_does_not_mark_the_columns_missing(monkeypatch):
    """The wider query fails for a reason other than the schema (the
    reader answers empty for every error) and the column-list probe fails
    too: the narrower read still returns the bars, and the provenance
    columns stay unknown, so the next read asks for them again."""
    from lib import data_loader as dl
    monkeypatch.setattr(dl, "_PREMARKET_PROVENANCE_PRESENT", None)
    monkeypatch.setattr(dl, "_ATR5_PRESENT", True)
    rows = pd.DataFrame([{"date": "2026-11-05", "Open": 1.0, "High": 2.0, "Low": 0.5,
                          "Close": 1.5, "Volume": 10, "atr_14": 0.4, "pre_high": None}])
    outage = {"on": True}
    calls = []

    def fake(sql, params=None):
        calls.append(sql)
        if outage["on"] and ("pre_fetched_at" in sql or "information_schema" in sql):
            return pd.DataFrame()
        if "information_schema" in sql:
            return pd.DataFrame({"column_name": ["date", "pre_fetched_at", "atr_5"]})
        return rows.assign(pre_fetched_at=FETCHED) if "pre_fetched_at" in sql else rows.copy()

    monkeypatch.setattr(dl, "_query_cloud_sql", fake)
    loader = dl.DataLoader.__new__(dl.DataLoader)
    assert len(loader._load_daily_from_sql("QQQ", None)) == 1
    assert dl._PREMARKET_PROVENANCE_PRESENT is None
    outage["on"] = False
    calls.clear()
    loader._load_daily_from_sql("QQQ", None)
    assert len(calls) == 1 and "pre_fetched_at" in calls[0]
    assert dl._PREMARKET_PROVENANCE_PRESENT is True


def test_data_loader_reads_the_columns_when_present(monkeypatch):
    from lib import data_loader as dl
    monkeypatch.setattr(dl, "_PREMARKET_PROVENANCE_PRESENT", None)
    monkeypatch.setattr(dl, "_ATR5_PRESENT", True)
    rows = pd.DataFrame([{"date": "2026-11-06", "Open": None, "pre_high": 660.4,
                          "pre_low": 649.62, "pre_vwap": 655.0, "gap_pct": -0.3,
                          **PROVENANCE}])
    calls = []
    monkeypatch.setattr(dl, "_query_cloud_sql",
                        lambda sql, params=None: calls.append(sql) or rows.copy())
    loader = dl.DataLoader.__new__(dl.DataLoader)
    df = loader._load_daily_from_sql("QQQ", None)
    assert len(calls) == 1 and "pre_fetched_at" in calls[0]
    assert dl._PREMARKET_PROVENANCE_PRESENT is True
    snap = premarket_snapshot_from_daily(df, SESSION)
    assert snap["excluded_stale_prints"] == 3 and snap["fetched_at"] == FETCHED
