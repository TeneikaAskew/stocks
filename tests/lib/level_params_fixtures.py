"""Per-ticker level parameter fixtures (FEAT-STRAT-001, 2026-11-08).

* ``ParamsDb``: level_param_policy and ticker_level_params in an in-memory
  SQLite, created from the DDL and policy seed in gcp/schema.sql, queried
  with lib.strat_levels.load_level_params's own SQL. Counts queries.
* ``fixture_params``: a LevelParams built in memory, every key ok. The
  default values are the #1753 constants, so a test that pins a #1753 rule
  (the side rule, the broken rule, the cents rule, the planner's offset
  arithmetic) keeps its arithmetic; a test of the calibrated path passes its
  own values. These are test inputs, not defaults any production path reads.
"""
from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import date
from pathlib import Path

import pandas as pd

from lib.strat_levels import (
    PARAM_OK, LevelParam, LevelParams, load_level_params, policy_in_force,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "gcp" / "schema.sql"

# The #1753 head's constants, keyed by the parameter that replaces each.
LEGACY_1753_VALUES = {
    "trigger_window_long_atr": 3.0,
    "trigger_window_short_atr": 3.0,
    "pm_spike_atr": 0.5,
    "pm_stale_print_atr": 0.1,
    "level_cluster_atr": 0.15,
    "entry_buffer_aggressive_lo_atr": 0.0,
    "entry_buffer_aggressive_hi_atr": 0.5,
    "entry_buffer_neutral_lo_atr": 0.0,
    "entry_buffer_neutral_hi_atr": 0.25,
    "entry_buffer_conservative_lo_atr": 0.1,
    "entry_buffer_conservative_hi_atr": 0.4,
    "stop_aggressive_atr": 2.0,
    "stop_neutral_atr": 1.0,
    "stop_conservative_atr": 0.7,
    "min_stop_atr": 0.5,
    "target_aggressive_1_r": 2.0,
    "target_aggressive_2_r": 3.5,
    "target_aggressive_3_r": 5.0,
    "target_neutral_1_r": 1.0,
    "target_neutral_2_r": 2.0,
    "target_neutral_3_r": 3.0,
    "target_conservative_1_r": 1.0,
    "target_conservative_2_r": 1.75,
}


def schema_statements() -> list[str]:
    """The two CREATE TABLE statements, the index and the policy seed from
    gcp/schema.sql, as committed."""
    text = SCHEMA.read_text()
    out = []
    for pattern in (
        r"CREATE TABLE IF NOT EXISTS level_param_policy \(.*?\n\);",
        r"CREATE TABLE IF NOT EXISTS ticker_level_params \(.*?\n\);",
        r"CREATE INDEX IF NOT EXISTS idx_ticker_level_params_in_force.*?;",
        r"INSERT INTO level_param_policy \(.*?ON CONFLICT \(param_key, effective_from\) DO NOTHING;",
    ):
        m = re.search(pattern, text, re.S)
        assert m, f"gcp/schema.sql lacks {pattern[:60]}"
        out.append(m.group(0))
    return out


def seeded_policy() -> dict:
    """The policy rows the schema seeds, in force from 2015-01-02."""
    db = ParamsDb()
    df = pd.read_sql_query("SELECT * FROM level_param_policy", db.conn)
    return policy_in_force(df.to_dict("records"))


class ParamsDb:
    def __init__(self, conn: sqlite3.Connection | None = None):
        """`conn`: an existing SQLite connection to create the tables in (for
        a production path that queries one engine for everything)."""
        self.conn = conn if conn is not None else sqlite3.connect(":memory:")
        for stmt in schema_statements():
            self.conn.execute(stmt)
        self.conn.commit()
        self.queries: list[str] = []

    def query(self, sql, params=None):
        self.queries.append(sql)
        p = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in (params or {}).items()}
        return pd.read_sql_query(sql, self.conn, params=p)

    def load(self, tickers, session_date):
        return load_level_params(self.query, tickers, session_date)

    def write(self, ticker, values: dict, *, effective_from, atr_basis="atr_14",
              status="ok", sample_n=750, source="history", run_id=None,
              input_from="2023-01-03", input_to=None, statuses: dict | None = None):
        run_id = run_id or str(uuid.uuid4())
        eff = effective_from.isoformat() if isinstance(effective_from, date) else effective_from
        for key, value in values.items():
            st = (statuses or {}).get(key, status)
            self.conn.execute(
                "INSERT INTO ticker_level_params (ticker, param_key, value, status, atr_basis, "
                "method_id, policy_effective_from, sample_n, input_from, input_to, effective_from, "
                "run_id, source, calibrated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT (ticker, param_key, atr_basis, effective_from) DO UPDATE SET "
                "value = excluded.value, status = excluded.status, run_id = excluded.run_id",
                (ticker, key, value if st == PARAM_OK else None, st, atr_basis, "fixture",
                 "2015-01-02", sample_n, input_from, input_to or eff, eff, run_id, source,
                 "2026-11-08T04:00:00Z"))
        self.conn.commit()
        return run_id

    def set_policy(self, key, *, effective_from, extra: str, method_id="policy"):
        self.conn.execute(
            "INSERT INTO level_param_policy (param_key, method_id, extra, effective_from) "
            "VALUES (?,?,?,?)", (key, method_id, extra, effective_from.isoformat()))
        self.conn.commit()

    def drop(self, table):
        self.conn.execute(f"DROP TABLE {table}")
        self.conn.commit()


def fixture_params(ticker: str = "TST", session_date: date = date(2026, 11, 6), *,
                   atr_basis: str = "atr_14", overrides: dict | None = None,
                   statuses: dict | None = None, sample_n: int = 750) -> LevelParams:
    """A LevelParams with every Design 2 key ok at the #1753 values, unless
    `overrides` gives a value or `statuses` a non-ok status for a key."""
    policy = seeded_policy()
    values = {**LEGACY_1753_VALUES, **(overrides or {})}
    params = {}
    for key, value in values.items():
        pol = policy[key]
        st = (statuses or {}).get(key, PARAM_OK)
        params[key] = LevelParam(
            key=key, status=st, value=(float(value) if st == PARAM_OK else None),
            ticker=ticker, effective_from=session_date.isoformat(),
            method_id=pol["method_id"], sample_n=sample_n if st == PARAM_OK else min(sample_n, (pol["min_sample"] or 1) - 1),
            min_sample=pol["min_sample"], statistic_q=pol["statistic_q"],
            lookback_sessions=pol["lookback_sessions"], input_from="2023-11-06",
            input_to="2026-11-05", run_id="00000000-0000-0000-0000-000000000001",
            atr_basis=atr_basis, policy_effective_from="2015-01-02", source="history",
        )
    return LevelParams(ticker=ticker, session_date=session_date, atr_basis=atr_basis,
                       policy_effective_from="2015-01-02", params=params)


def legacy_db(tickers, *, effective_from: date = date(2015, 1, 2), overrides: dict | None = None,
              statuses: dict | None = None, conn: sqlite3.Connection | None = None) -> ParamsDb:
    """A ParamsDb whose `tickers` hold every Design 2 key at the #1753
    values (or `overrides`), effective from `effective_from`, so a production
    path driven offline reads them through load_level_params's own SQL."""
    db = ParamsDb(conn)
    for t in ([tickers] if isinstance(tickers, str) else tickers):
        db.write(t, {**LEGACY_1753_VALUES, **(overrides or {})},
                 effective_from=effective_from, statuses=statuses)
    return db


def install_level_params(monkeypatch, tickers=("SPY", "QQQ", "IWM"), *, db: ParamsDb | None = None,
                         **legacy_kw) -> ParamsDb:
    """Answer the level parameter query on gcp.database's strict reader
    (the one every production consumer reads the tables through) from a
    ParamsDb; every other strict query goes to the reader that was in place.
    By default every listed ticker holds every key at the #1753 values."""
    import gcp.database as database

    pdb = db if db is not None else legacy_db(list(tickers), **legacy_kw)
    previous = database.query_to_dataframe_strict

    def strict(sql, params=None):
        if "level_param_policy" in sql:
            return pdb.query(sql, params)
        return previous(sql, params)

    monkeypatch.setattr(database, "query_to_dataframe_strict", strict)
    return pdb
