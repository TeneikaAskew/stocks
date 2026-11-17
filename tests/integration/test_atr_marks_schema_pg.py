"""FEAT-STRAT-001 ATR mark targets (2026-11-16 spec r2): what the merge
applies to production, on the ephemeral Postgres loaded with gcp/schema.sql.

* The two seeded level_param_policy rows (no marks, 250 sessions of reach
  history), each effective 2015-01-02, and exit_legs still {"legs": 3}.
* The eight nullable columns: plan_t4_price on premarket_analysis and on
  premarket_analysis_history, plan_t4_hit_ts and plan_mfe_atr on
  premarket_analysis.
* The two statements apply a second time without an error or a second row.
* Later-dated swap rows take force on their date through load_level_params.
* The brief's reach history statement runs on Postgres, bounded to the
  sessions, the rule version and the dates before the session.
* resolve_one writes the new outcome columns through the real engine.

On origin/main f3b2344c4 neither the rows nor the columns exist.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "gcp" / "schema.sql"
NEW_COLUMNS = {
    ("premarket_analysis", "calls_plan_t4_price"): "double precision",
    ("premarket_analysis", "puts_plan_t4_price"): "double precision",
    ("premarket_analysis_history", "calls_plan_t4_price"): "double precision",
    ("premarket_analysis_history", "puts_plan_t4_price"): "double precision",
    ("premarket_analysis", "calls_plan_t4_hit_ts"): "timestamp with time zone",
    ("premarket_analysis", "puts_plan_t4_hit_ts"): "timestamp with time zone",
    ("premarket_analysis", "calls_plan_mfe_atr"): "double precision",
    ("premarket_analysis", "puts_plan_mfe_atr"): "double precision",
}
MARKS_VERSION = "feat-strat-001.v6"


def _rows(conn, sql, **params):
    return [dict(r._mapping) for r in conn.execute(sqlalchemy.text(sql), params)]


def _statements_adding(columns) -> list[str]:
    """The ALTER TABLE statements of gcp/schema.sql that add any of
    `columns`, line comments dropped (some hold a ';')."""
    text = re.sub(r"--[^\n]*", "", SCHEMA.read_text())
    return [s.strip() + ";" for s in text.split(";")
            if s.strip().startswith("ALTER TABLE") and any(c in s for c in columns)]


def test_the_two_policy_rows_are_seeded(db_engine):
    with db_engine.connect() as conn:
        rows = _rows(conn, "SELECT param_key, method_id, extra, effective_from "
                           "FROM level_param_policy WHERE param_key IN "
                           "('plan_target_marks_atr', 'ladder_history_sessions', 'exit_legs') "
                           "ORDER BY param_key, effective_from")
    got = {(r["param_key"], r["effective_from"]): (r["method_id"], r["extra"]) for r in rows}
    seed = date(2015, 1, 2)
    assert got[("plan_target_marks_atr", seed)] == ("policy", {"marks": []})
    assert got[("ladder_history_sessions", seed)] == ("policy", {"sessions": 250})
    assert got[("exit_legs", seed)] == ("policy", {"legs": 3})
    assert sum(k == "plan_target_marks_atr" for k, _ in got) == 1
    assert sum(k == "ladder_history_sessions" for k, _ in got) == 1


def test_the_eight_columns_exist_and_are_nullable(db_engine):
    with db_engine.connect() as conn:
        rows = _rows(conn, "SELECT table_name, column_name, data_type, is_nullable "
                           "FROM information_schema.columns WHERE table_schema = 'public' "
                           "AND column_name IN ('calls_plan_t4_price', 'puts_plan_t4_price', "
                           "'calls_plan_t4_hit_ts', 'puts_plan_t4_hit_ts', "
                           "'calls_plan_mfe_atr', 'puts_plan_mfe_atr')")
    got = {(r["table_name"], r["column_name"]): (r["data_type"], r["is_nullable"]) for r in rows}
    assert got == {k: (t, "YES") for k, t in NEW_COLUMNS.items()}


def test_the_schema_applies_twice(db_engine):
    from tests.lib.level_params_fixtures import schema_statements

    insert = schema_statements()[3]
    alters = _statements_adding({c for _, c in NEW_COLUMNS})
    assert len(alters) >= 2
    with db_engine.begin() as conn:
        conn.exec_driver_sql(insert)
        for stmt in alters:
            conn.exec_driver_sql(stmt)
        rows = _rows(conn, "SELECT param_key, COUNT(*) AS n FROM level_param_policy WHERE "
                           "param_key IN ('plan_target_marks_atr', 'ladder_history_sessions') "
                           "GROUP BY param_key")
    assert {r["param_key"]: r["n"] for r in rows} == {"plan_target_marks_atr": 1,
                                                      "ladder_history_sessions": 1}


def test_swap_rows_take_force_on_their_date(db_engine):
    from lib.strat_levels import load_level_params

    with db_engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(sqlalchemy.text(
                "INSERT INTO level_param_policy (param_key, method_id, extra, effective_from, note) "
                "VALUES ('plan_target_marks_atr', 'policy', CAST(:m AS JSONB), '2026-12-01', 'test'), "
                "('exit_legs', 'policy', CAST(:l AS JSONB), '2026-12-01', 'test')"),
                {"m": json.dumps({"marks": [0.25, 0.5, 0.75, 1.0]}), "l": json.dumps({"legs": 4})})

            def query(sql, params):
                import pandas as pd
                return pd.read_sql(sqlalchemy.text(sql), conn, params=params)

            before = load_level_params(query, ["SPY"], date(2026, 11, 30))["SPY"]
            on = load_level_params(query, ["SPY"], date(2026, 12, 1))["SPY"]
        finally:
            tx.rollback()
    assert before.plan_target_marks() == () and before.value("exit_legs") == 3.0
    assert on.plan_target_marks() == (0.25, 0.5, 0.75, 1.0) and on.value("exit_legs") == 4.0


def _seed_reach_rows(conn, tickers, n, session):
    """`n` dated rows a ticker before `session` (and two on and after it):
    every fifth row of another version, every seventh with no reach value."""
    rows = []
    for t in tickers:
        for i in range(n + 2):
            d = session - timedelta(days=n - i)
            version = "feat-strat-001.v5" if i % 5 == 0 else MARKS_VERSION
            calls = None if i % 7 == 0 else round(0.01 * i, 4)
            rows.append({"analysis_date": d, "ticker": t, "run_kind": "live",
                         "level_basis": json.dumps({"rule_version": version}),
                         "calls_plan_mfe_atr": calls, "puts_plan_mfe_atr": 0.5})
    conn.execute(sqlalchemy.text(
        "INSERT INTO premarket_analysis (analysis_date, ticker, run_kind, level_basis, "
        "calls_plan_mfe_atr, puts_plan_mfe_atr) VALUES (:analysis_date, :ticker, :run_kind, "
        "CAST(:level_basis AS JSONB), :calls_plan_mfe_atr, :puts_plan_mfe_atr)"), rows)
    return rows


def test_reach_history_query_runs_and_is_bounded(clean_db, capsys):
    import pandas as pd

    import gcp.premarket_brief as brief
    from tests.lib.level_params_fixtures import ParamsDb

    tickers = ["SPY", "QQQ", "IWM"]
    session = date(2026, 11, 16)
    with clean_db.begin() as conn:
        rows = _seed_reach_rows(conn, tickers, 300, session)
    db = ParamsDb()
    db.set_policy("plan_target_marks_atr", effective_from=date(2026, 11, 1),
                  extra='{"marks": [0.25, 0.5, 0.75, 1.0]}')
    db.set_policy("exit_legs", effective_from=date(2026, 11, 1), extra='{"legs": 4}')
    params = db.load(tickers, session)

    statements = []

    def query(sql, p):
        statements.append((sql, p))
        with clean_db.connect() as conn:
            return pd.read_sql(sqlalchemy.text(sql), conn, params=p)

    out = brief.read_plan_reach_history(query, tickers, session, params)
    assert len(statements) == 1
    for t in tickers:
        last = sorted((r for r in rows if r["ticker"] == t and r["analysis_date"] < session),
                      key=lambda r: r["analysis_date"])[-250:]
        kept = [r for r in last if json.loads(r["level_basis"])["rule_version"] == MARKS_VERSION]
        assert out[t]["long"] == [r["calls_plan_mfe_atr"] for r in kept
                                  if r["calls_plan_mfe_atr"] is not None]
        assert out[t]["short"] == [r["puts_plan_mfe_atr"] for r in kept]
        assert len(out[t]["short"]) <= 250

    sql, p = statements[0]
    with clean_db.connect() as conn:
        plan = [r[0] for r in conn.execute(sqlalchemy.text("EXPLAIN (ANALYZE, BUFFERS) " + sql), p)]
    with capsys.disabled():
        print("\nEXPLAIN (ANALYZE, BUFFERS) of PLAN_REACH_HISTORY_SQL, 3 tickers x 302 rows:")
        print("\n".join(plan))
    limit = next(ln for ln in plan if "Limit" in ln)
    m = re.search(r"actual time=\S+ rows=(\d+) loops=(\d+)", limit)
    assert m and int(m.group(1)) <= 250 and int(m.group(2)) == len(tickers), limit


def test_resolve_one_writes_the_new_columns(clean_db, monkeypatch):
    from gcp.premarket_playbook_resolver import resolve_one
    from tests.lib.session_levels_helpers import d8_basis

    d = date(2026, 5, 6)
    basis = d8_basis()
    with clean_db.begin() as conn:
        conn.execute(sqlalchemy.text(
            "INSERT INTO premarket_analysis (analysis_date, ticker, run_kind, level_basis, "
            "calls_trigger_price, calls_stop_price, calls_t1_price, calls_t2_price, "
            "calls_t3_price, puts_trigger_price, puts_stop_price, puts_t1_price, "
            "puts_t2_price, puts_t3_price) VALUES (:d, 'TST', 'live', CAST(:lb AS JSONB), "
            "252.10, 248.20, 253.00, 275.00, 280.00, 248.20, 252.10, 247.50, 247.00, 225.00)"),
            {"d": d, "lb": json.dumps(basis)})
        t0 = datetime(2026, 5, 6, 13, 30, tzinfo=timezone.utc)
        conn.execute(sqlalchemy.text(
            "DELETE FROM market_data_intraday WHERE ticker = 'TST' AND ts >= :a AND ts < :b"),
            {"a": t0, "b": t0 + timedelta(days=1)})
        bars = [(0, 251.00, 251.50, 250.80, 251.40), (1, 251.90, 252.50, 251.80, 252.40),
                (2, 252.40, 255.00, 252.30, 254.00), (3, 254.00, 254.10, 248.00, 248.10)]
        conn.execute(sqlalchemy.text(
            "INSERT INTO market_data_intraday (ticker, interval, ts, open, high, low, close, "
            "volume) VALUES ('TST', '1min', :ts, :o, :h, :l, :c, 1000)"),
            [{"ts": t0 + timedelta(minutes=m), "o": o, "h": h, "l": lo, "c": c}
             for m, o, h, lo, c in bars])
    updates, reason = resolve_one(d, "TST", clean_db)
    assert reason == "resolved"
    with clean_db.connect() as conn:
        (row,) = _rows(conn, "SELECT calls_plan_t4_hit_ts, puts_plan_t4_hit_ts, "
                             "calls_plan_mfe_atr, puts_plan_mfe_atr, calls_plan_exit, "
                             "outcome_resolver_version FROM premarket_analysis "
                             "WHERE ticker = 'TST' AND analysis_date = :d", d=d)
    assert row["calls_plan_t4_hit_ts"] is None and row["puts_plan_t4_hit_ts"] is None
    assert row["calls_plan_exit"] == "stop,stop,stop"
    assert row["calls_plan_mfe_atr"] == pytest.approx(2.90 / 14.0)
    assert row["puts_plan_mfe_atr"] == 0.0
    assert row["outcome_resolver_version"] == "2026-11-16.v5"
