"""FEAT-STRAT-001 done_when 11, the movement statement part.

Reach rates count only resolved rows whose level_basis carries the current
rule_version (numerator and denominator alike); for those rows the trigger
is anchored to level_basis's own cleared mark, inclusive in cents, so a
gap-down call, a gap-up put and a trigger on the mark's own cent are in
the population; _fetch_tracked_levels seeds the same way, so each rung of
an end-to-end movement statement keeps its own slot's rate.

The SQL runs on an in-memory SQLite premarket_analysis. SQLite has the
JSON ->> operator and COUNT(*) FILTER; the harness strips the Postgres-only
::float8 and ::numeric casts and nothing else. On origin/main the
population anchors to the persisted prior close in `price`, so the gap-down
call and the equal-cent rows drop out, and old-rule rows are counted.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date

import pandas as pd
import pytest

import lib.movement_statement as ms
from lib.strat_levels import LEVEL_RULE_VERSION, SessionLevels
from tests.lib.session_levels_helpers import basis

SESSION = date(2026, 11, 6)
SLOTS = ("trigger", "t1", "t2", "t3")
COLS = (["ticker", "analysis_date", "run_kind", "price", "level_basis", "outcome_resolved_at"]
        + [f"{s}_{k}_price" for s in ("calls", "puts") for k in SLOTS]
        + [f"{s}_{k}_hit_ts" for s in ("calls", "puts") for k in SLOTS])


class _Db:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(f"CREATE TABLE premarket_analysis ({', '.join(COLS)})")

    def add(self, **row):
        vals = [row.get(c) for c in COLS]
        if isinstance(row.get("level_basis"), dict):
            vals[COLS.index("level_basis")] = json.dumps(row["level_basis"])
        self.conn.execute(f"INSERT INTO premarket_analysis VALUES ({', '.join('?' * len(COLS))})", vals)

    def query(self, sql, params=None):
        sql = sql.replace("::float8", "").replace("::numeric", "")
        p = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in (params or {}).items()}
        return pd.read_sql_query(sql, self.conn, params=p)


def _mark_basis(*, above=None, below=None, rule=LEVEL_RULE_VERSION) -> dict:
    return {"rule_version": rule, "cleared_above": above, "cleared_below": below}


def _resolved(db, *, d, price, lb, calls=(None,) * 4, puts=(None,) * 4,
              calls_hit=(), puts_hit=()):
    row = dict(ticker="SPY", analysis_date=d, run_kind="live", price=price, level_basis=lb,
               outcome_resolved_at="2026-11-06T21:00:00Z")
    for side, prices, hits in (("calls", calls, calls_hit), ("puts", puts, puts_hit)):
        for k, v in zip(SLOTS, prices):
            row[f"{side}_{k}_price"] = v
            if k in hits:
                row[f"{side}_{k}_hit_ts"] = "2026-11-06T15:00:00Z"
    db.add(**row)


def test_only_new_rule_rows_are_counted():
    db = _Db()
    old = _mark_basis(above=100.0, rule="legacy")
    for i in range(3):     # old-rule and pre-column rows, all hit
        _resolved(db, d=f"2026-10-0{i + 1}", price=100.0, lb=old if i else None,
                  calls=(101.0, 102.0, 103.0, 104.0), calls_hit=("trigger", "t1"))
    _resolved(db, d="2026-10-10", price=100.0, lb=_mark_basis(above=100.0),
              calls=(101.0, 102.0, 103.0, 104.0), calls_hit=("trigger",))
    _resolved(db, d="2026-10-11", price=100.0, lb=_mark_basis(above=100.0),
              calls=(101.0, 102.0, 103.0, 104.0))
    out = ms._fetch_reach_rates("SPY", "calls", db.query)
    trig = out["slots"]["trigger"]
    assert (trig["sample_n"], trig["hits"]) == (2, 1)
    assert out["slots"]["t1"]["status"] != "OK" or out["slots"]["t1"]["hits"] == 0


def test_gap_down_call_gap_up_put_and_equal_cent_rows_are_in_the_population():
    db = _Db()
    # Gap-down call: prior close 102 (`price`), pre_vwap 100, pre_high 100.50,
    # trigger 101. The old anchor (`price` 102) dropped it.
    _resolved(db, d="2026-10-20", price=102.0, lb=_mark_basis(above=100.5, below=99.0),
              calls=(101.0, 103.0, None, None), calls_hit=("trigger",))
    # Gap-up put mirror: prior close 98, pre_vwap 100, pre_low 99.50, trigger 99.
    _resolved(db, d="2026-10-21", price=98.0, lb=_mark_basis(above=101.0, below=99.5),
              puts=(99.0, 97.0, None, None), puts_hit=("trigger", "t1"))
    # Trigger on the cleared mark's own cent: prior close 100, pre_high 100.
    _resolved(db, d="2026-10-22", price=100.0, lb=_mark_basis(above=100.0, below=99.0),
              calls=(100.0, 102.0, None, None))
    calls = ms._fetch_reach_rates("SPY", "calls", db.query)["slots"]
    puts = ms._fetch_reach_rates("SPY", "puts", db.query)["slots"]
    assert (calls["trigger"]["sample_n"], calls["trigger"]["hits"]) == (2, 1)
    assert (calls["t1"]["sample_n"], calls["t1"]["hits"]) == (2, 0)
    assert (puts["trigger"]["sample_n"], puts["trigger"]["hits"]) == (1, 1)
    assert (puts["t1"]["sample_n"], puts["t1"]["hits"]) == (1, 1)


def test_a_trigger_inside_the_premarket_range_is_out():
    """A new-rule call trigger below its own cleared mark was a broken
    level and is out of every population."""
    db = _Db()
    _resolved(db, d="2026-10-20", price=100.0, lb=_mark_basis(above=101.5),
              calls=(101.0, 103.0, None, None), calls_hit=("trigger",))
    out = ms._fetch_reach_rates("SPY", "calls", db.query)
    assert out["status"] != "OK"


# ── end to end on the session row ───────────────────────────────────────

def _session_basis(kind: str) -> dict:
    if kind == "gap_down":
        # prior close 102, reference 100, pre_high and trigger 101, T1 103
        b = basis({"PMH": 103.0, "PDL": 97.0}, prior_close=102.0, atr=3.0, ticker="SPY",
                  premarket={"pre_high": 101.0, "pre_low": 99.8, "pre_vwap": 100.0})
    else:
        # equal cent: prior close 100, pre_high 100.00 on PDC 100, T1 PDH 102
        b = basis({"PDC": 100.0, "PDH": 102.0, "PDL": 98.0}, prior_close=100.0, atr=3.0,
                  ticker="SPY", premarket={"pre_high": 100.0, "pre_low": 99.5, "pre_vwap": 100.0})
    return SessionLevels.from_basis(b).to_basis()


@pytest.mark.parametrize("kind, trig, t1", [("gap_down", 101.0, 103.0), ("equal_cent", 100.0, 102.0)])
def test_each_rung_shows_its_own_slots_rate(monkeypatch, kind, trig, t1):
    stored = _session_basis(kind)
    sl = SessionLevels.from_basis(stored)
    assert sl.long.trigger["price"] == trig and sl.long.targets[0]["price"] == t1
    lm = sl.to_level_map()

    db = _Db()
    # Five resolved new-rule rows: the trigger hit on 4, T1 on 1.
    for i in range(5):
        _resolved(db, d=f"2026-10-{10 + i}", price=stored["prior_close"], lb=stored,
                  calls=(trig, t1, None, None),
                  calls_hit=("trigger", "t1") if i == 0 else (("trigger",) if i < 4 else ()))
    # The session's own (unresolved) live row, as the brief wrote it.
    ct = lm.calls_trigger
    db.add(ticker="SPY", analysis_date=SESSION.isoformat(), run_kind="live",
           price=stored["prior_close"], level_basis=stored,
           calls_trigger_price=ct["trigger_level"], calls_t1_price=ct["targets"][0]["price"])

    monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "1")
    # The continuation block is not under test (and its model pulls
    # LightGBM, a research-only dependency).
    monkeypatch.setattr(ms, "_build_continuation",
                        lambda *a, **k: ms._unavailable("not under test"))

    def q(sql, params=None):
        if "premarket_analysis" in sql:
            return db.query(sql, params)
        return pd.DataFrame()

    out = ms.assemble_movement_statement(
        "SPY", "15m", engine=object(), level_map=lm, query_fn=q,
        gamma_fn=lambda *a, **k: {"available": False}, session_date=SESSION)
    rungs = out["levels"]["calls"]
    assert [r["price"] for r in rungs] == [trig, t1]
    first, second = rungs
    assert first["reach_rate"]["slot"] == "trigger"
    assert (first["reach_rate"]["hits"], first["reach_rate"]["sample_n"]) == (4, 5)
    assert second["reach_rate"]["slot"] == "t1"
    assert (second["reach_rate"]["hits"], second["reach_rate"]["sample_n"]) == (1, 5)


def test_tracked_levels_seed_from_the_cleared_mark():
    stored = _session_basis("gap_down")
    db = _Db()
    db.add(ticker="SPY", analysis_date=SESSION.isoformat(), run_kind="live", price=102.0,
           level_basis=stored, calls_trigger_price=101.0, calls_t1_price=103.0)
    got = ms._fetch_tracked_levels("SPY", db.query, SESSION)
    assert [(t["slot"], t["price"]) for t in got["calls"]] == [("trigger", 101.0), ("t1", 103.0)]
    # A legacy row (no basis) keeps the old prior-close seed.
    legacy = _Db()
    legacy.add(ticker="SPY", analysis_date=SESSION.isoformat(), run_kind="live", price=102.0,
               calls_trigger_price=101.0, calls_t1_price=103.0)
    got = ms._fetch_tracked_levels("SPY", legacy.query, SESSION)
    assert [(t["slot"], t["price"]) for t in got["calls"]] == [("trigger", 103.0)]


def test_tracked_levels_work_without_the_column():
    calls = []

    def q(sql, params=None):
        calls.append(sql)
        if "level_basis" in sql:
            raise RuntimeError('column "level_basis" does not exist')
        return pd.DataFrame([{"analysis_date": SESSION, "price": 100.0,
                              "calls_trigger_price": 101.0, "calls_t1_price": 102.0}])

    got = ms._fetch_tracked_levels("SPY", q, SESSION)
    assert got["status"] == "OK" and len(calls) == 2
    assert [t["price"] for t in got["calls"]] == [101.0, 102.0]
