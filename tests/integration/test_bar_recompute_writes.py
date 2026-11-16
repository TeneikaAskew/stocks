"""Real-SQL tests for the bar recompute writes (FEAT-DATA-001).

The hermetic tests in tests/gcp/ patch every read and never open a
transaction, so they cannot see whether the compare-and-set statement, the
ledger insert or the revert do what they say on Postgres. These run them
against the real gcp/schema.sql: gcp.bar_recompute.write_group directly, then
the two entry points (--re-resolve on the end-of-day resolver and
--recompute-premarket on the daily fetcher) through their main().
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone

import pytest
import sqlalchemy

from gcp import bar_recompute as br

# The module truncates tables. The shared db_engine fixture does not skip: it
# calls gcp.database.get_engine(), which reaches Cloud SQL wherever production
# credentials exist. This guard keeps a local run off production.
pytestmark = pytest.mark.skipif(
    not os.environ.get("DB_HOST"),
    reason="integration tests need a Postgres (DB_HOST) - see the "
    "integration-tests CI job in backtest-pipeline.yml",
)

UTC = timezone.utc

RECOMPUTE_TABLES = (
    "signal_alerts", "trades", "market_data_daily", "market_data_intraday",
    "bar_recompute_ledger", "ticker_level_params",
)


@pytest.fixture
def recompute_db(db_engine):
    """Empty the tables these tests write, before each test."""
    with db_engine.begin() as conn:
        for table in RECOMPUTE_TABLES:
            conn.execute(sqlalchemy.text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
    return db_engine


def rows(engine, table: str, where: str = "TRUE", params: dict | None = None,
         order: str = "id") -> list[dict]:
    """Every column of the rows of *table* that match."""
    with engine.connect() as conn:
        result = conn.execute(
            sqlalchemy.text(f"SELECT * FROM {table} WHERE {where} ORDER BY {order}"), params or {})
        return [dict(r) for r in result.mappings()]


def row(engine, table: str, where: str, params: dict | None = None) -> dict:
    """Every column of the one row of *table* that matches."""
    found = rows(engine, table, where, params)
    assert len(found) == 1, f"{table} WHERE {where}: {len(found)} rows"
    return found[0]


def execute(engine, sql: str, params=None) -> None:
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text(sql), params or {})


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def seed_alert(engine, ticker: str, alert_ts: datetime, *, direction: str = "CALL",
               entry: float = 100.0, target: float | None = 110.0, stop: int | None = 30,
               exit_ts: datetime | None = None, reason: str | None = None,
               price: float | None = None, ret: float | None = None,
               is_open: bool = False, run_kind: str = "live", trade: bool = True,
               alert_date: date | None = None) -> None:
    """One alert and, unless *trade* is false, its mirror trade."""
    day = alert_date or br._instant(alert_ts).date()
    execute(engine, """
        INSERT INTO signal_alerts (ticker, alert_ts, alert_date, direction, price_at_signal,
                                   target_price, time_stop_minutes, exit_ts, exit_reason,
                                   exit_price, exit_return_pct, is_open, run_kind)
        VALUES (:ticker, :alert_ts, :day, :direction, :entry, :target, :stop, :exit_ts,
                :reason, :price, :ret, :is_open, :run_kind)
    """, {"ticker": ticker, "alert_ts": alert_ts, "day": day, "direction": direction,
          "entry": entry, "target": target, "stop": stop, "exit_ts": exit_ts, "reason": reason,
          "price": price, "ret": ret, "is_open": is_open, "run_kind": run_kind})
    if trade:
        execute(engine, """
            INSERT INTO trades (ticker, direction, entry_time, entry_price, exit_time,
                                exit_price, exit_reason, return_pct, trade_date, run_kind)
            VALUES (:ticker, :direction, :alert_ts, :entry, :exit_ts, :price, :reason, :ret,
                    :day, :run_kind)
        """, {"ticker": ticker, "direction": direction, "alert_ts": alert_ts, "entry": entry,
              "exit_ts": exit_ts, "price": price, "reason": reason, "ret": ret, "day": day,
              "run_kind": run_kind})


ALERT_TRADE_READ = """
    SELECT a.ticker, a.alert_ts, a.alert_date, a.exit_ts, a.exit_reason, a.exit_price,
           a.exit_return_pct, a.exit_recompute_run,
           t.exit_time, t.exit_price AS trade_exit_price, t.exit_reason AS trade_exit_reason,
           t.return_pct, t.exit_recompute_run AS trade_exit_recompute_run
      FROM signal_alerts a
      JOIN trades t ON t.ticker = a.ticker AND t.entry_time = a.alert_ts AND t.run_kind = 'live'
     WHERE a.run_kind = 'live'
     ORDER BY a.alert_ts
"""


def exit_units(new_exit: dict) -> list[br.WriteUnit]:
    """One unit an alert, read through the strict reader as the tools read:
    the alert is the primary, its trade the follower, both taking *new_exit*."""
    from gcp.database import query_to_dataframe_strict

    frame = query_to_dataframe_strict(ALERT_TRADE_READ)
    units = []
    for record in frame.to_dict("records"):
        alert_old = {c: record[c] for c in br.ALERT_EXITS.columns}
        alert_old["exit_recompute_run"] = record["exit_recompute_run"]
        trade_old = {
            "exit_time": record["exit_time"], "exit_price": record["trade_exit_price"],
            "exit_reason": record["trade_exit_reason"], "return_pct": record["return_pct"],
            "exit_recompute_run": record["trade_exit_recompute_run"]}
        alert_new = dict(new_exit)
        trade_new = {"exit_time": new_exit["exit_ts"], "exit_price": new_exit["exit_price"],
                     "exit_reason": new_exit["exit_reason"],
                     "return_pct": new_exit["exit_return_pct"]}
        units.append(br.WriteUnit(
            ticker=record["ticker"], session_date=record["alert_date"],
            row_key=br.json_value(record["alert_ts"]),
            primary=br.TableWrite(
                br.ALERT_EXITS, {"ticker": record["ticker"], "alert_ts": record["alert_ts"]},
                alert_old, alert_new),
            follower=br.TableWrite(
                br.TRADE_EXITS, {"ticker": record["ticker"], "entry_time": record["alert_ts"]},
                trade_old, trade_new),
            changed=True, basis={"bars": {"rows": 1, "sha256": "x"}}))
    return units


NEW_EXIT = {"exit_ts": utc("2026-10-06T20:00:00"), "exit_reason": "eod_close",
            "exit_price": 0.1 + 0.2, "exit_return_pct": -0.25}


def seed_three_alerts(engine) -> list[datetime]:
    stamps = [utc("2026-10-06T14:00:07.500000"), utc("2026-10-06T15:00:01.000001"),
              utc("2026-10-06T19:50:00.250000")]
    seed_alert(engine, "SPY", stamps[0], exit_ts=utc("2026-10-06T14:31:00"),
               reason="time_stop", price=100.02, ret=0.02)
    seed_alert(engine, "SPY", stamps[1], exit_ts=utc("2026-10-06T15:03:00"),
               reason="target_hit", price=0.1 + 0.2, ret=0.495)
    seed_alert(engine, "SPY", stamps[2], exit_ts=utc("2026-10-06T20:20:00"),
               reason="time_stop", price=100.0, ret=0.0)
    return stamps


# ── gcp.bar_recompute.write_group, directly ───────────────────────────


def test_the_schema_is_ready(recompute_db):
    assert br.schema_missing() == []


def test_the_trade_follows_its_alert(recompute_db):
    engine = recompute_db
    stamps = seed_three_alerts(engine)
    units = exit_units(NEW_EXIT)

    # Another writer changes the third alert between the read and the write.
    execute(engine, "UPDATE signal_alerts SET exit_price = 999.0 WHERE alert_ts = :ts",
            {"ts": stamps[2]})
    third_alert = row(engine, "signal_alerts", "alert_ts = :ts", {"ts": stamps[2]})
    third_trade = row(engine, "trades", "entry_time = :ts", {"ts": stamps[2]})

    result = br.write_group(engine, target=br.TARGET_EXITS, action="recompute",
                            run_id="run-1", units=units)

    assert [result[u.row_key] for u in units] == [(True, True), (True, True), (False, False)]
    assert row(engine, "signal_alerts", "alert_ts = :ts", {"ts": stamps[2]}) == third_alert
    assert row(engine, "trades", "entry_time = :ts", {"ts": stamps[2]}) == third_trade

    for stamp in stamps[:2]:
        alert = row(engine, "signal_alerts", "alert_ts = :ts", {"ts": stamp})
        trade = row(engine, "trades", "entry_time = :ts", {"ts": stamp})
        assert alert["exit_ts"] == NEW_EXIT["exit_ts"] == trade["exit_time"]
        assert alert["exit_price"] == 0.1 + 0.2 == trade["exit_price"]
        assert alert["exit_reason"] == "eod_close" == trade["exit_reason"]
        assert alert["exit_return_pct"] == -0.25 == trade["return_pct"]
        assert alert["exit_recompute_run"] == "run-1" == trade["exit_recompute_run"]
        assert alert["is_open"] is False

    ledger = rows(engine, "bar_recompute_ledger")
    assert [entry["row_key"] for entry in ledger] == [u.row_key for u in units[:2]]
    assert ledger[0]["row_key"] == "2026-10-06T14:00:07.500000+00:00"
    assert ledger[1]["row_key"] == "2026-10-06T15:00:01.000001+00:00"
    assert {entry["action"] for entry in ledger} == {"recompute"}
    assert {entry["target"] for entry in ledger} == {"signal-alert-exits"}
    second = br.ledger_of_run("run-1", br.TARGET_EXITS)[1]
    assert second["old_values"]["signal_alerts"] == {
        "exit_ts": "2026-10-06T15:03:00.000000+00:00", "exit_reason": "target_hit",
        "exit_price": 0.1 + 0.2, "exit_return_pct": 0.495, "exit_recompute_run": None}
    assert second["new_values"]["trades"] == {
        "exit_time": "2026-10-06T20:00:00.000000+00:00", "exit_price": 0.1 + 0.2,
        "exit_reason": "eod_close", "return_pct": -0.25, "exit_recompute_run": "run-1"}
    assert second["changed"] is True
    assert second["basis"] == {"bars": {"rows": 1, "sha256": "x"}}


def test_a_trade_changed_underneath_leaves_only_the_trade(recompute_db):
    engine = recompute_db
    stamps = seed_three_alerts(engine)
    units = exit_units(NEW_EXIT)

    execute(engine, "UPDATE trades SET exit_price = 999.0 WHERE entry_time = :ts",
            {"ts": stamps[2]})
    third_trade = row(engine, "trades", "entry_time = :ts", {"ts": stamps[2]})

    result = br.write_group(engine, target=br.TARGET_EXITS, action="recompute",
                            run_id="run-1", units=units)

    assert result[units[2].row_key] == (True, False)
    assert row(engine, "trades", "entry_time = :ts", {"ts": stamps[2]}) == third_trade
    alert = row(engine, "signal_alerts", "alert_ts = :ts", {"ts": stamps[2]})
    assert alert["exit_reason"] == "eod_close"
    assert alert["exit_recompute_run"] == "run-1"
    entry = br.ledger_of_run("run-1", br.TARGET_EXITS)[2]
    assert entry["old_values"]["trades"] is None
    assert entry["new_values"]["trades"] is None
    assert entry["new_values"]["signal_alerts"]["exit_reason"] == "eod_close"


DAILY_READ = """
    SELECT ticker, date, pre_high, pre_low, pre_vwap, pre_volume, gap_pct, pre_range_atr,
           pre_fetched_at, pre_excluded_stale_prints, pre_excluded_spikes, pre_filter_status,
           pre_filter_params::text AS pre_filter_params, pre_recompute_run
      FROM market_data_daily ORDER BY date
"""


def daily_units(new_of) -> list[br.WriteUnit]:
    from gcp.database import query_to_dataframe_strict

    frame = query_to_dataframe_strict(DAILY_READ)
    units = []
    for record in frame.to_dict("records"):
        old = {c: record[c] for c in br.DAILY_PREMARKET.columns}
        old["pre_recompute_run"] = record["pre_recompute_run"]
        units.append(br.WriteUnit(
            ticker=record["ticker"], session_date=record["date"],
            row_key=record["date"].isoformat(),
            primary=br.TableWrite(br.DAILY_PREMARKET,
                                  {"ticker": record["ticker"], "date": record["date"]},
                                  old, new_of(record)),
            follower=None, changed=True, basis={"bars": {"rows": 330}}))
    return units


def test_nulls_and_integers_are_written(recompute_db):
    engine = recompute_db
    execute(engine, """
        INSERT INTO market_data_daily (ticker, date, close, pre_high, pre_low, pre_vwap,
                                       pre_volume, gap_pct, pre_range_atr, pre_fetched_at,
                                       pre_excluded_stale_prints, pre_excluded_spikes,
                                       pre_filter_status, pre_filter_params)
        VALUES ('SPY', '2026-10-05', 99.0, 100.5, 99.5, 100.0, NULL, 1.0, NULL, NULL,
                NULL, NULL, NULL, NULL),
               ('SPY', '2026-10-06', 99.0, 100.5, 99.5, 100.0, 7654321, 1.0, 0.5,
                '2026-10-06T13:31:00+00:00', 2, 3, 'ok',
                CAST('{"pm_spike_atr": 0.5, "pm_stale_print_atr": 1.25}' AS JSONB))
    """)

    def new_of(record):
        if record["date"] == date(2026, 10, 5):
            return {"pre_high": 101.5, "pre_low": 99.25, "pre_vwap": 100.1,
                    "pre_volume": 330000, "gap_pct": 1.0101, "pre_range_atr": 0.5,
                    "pre_fetched_at": utc("2026-11-14T12:00:00.000123"),
                    "pre_excluded_stale_prints": 0, "pre_excluded_spikes": 0,
                    "pre_filter_status": "ok",
                    "pre_filter_params": {"pm_stale_print_atr": 1.25, "pm_spike_atr": 0.5}}
        return {"pre_high": 101.5, "pre_low": 99.25, "pre_vwap": 100.1,
                "pre_volume": 330000, "gap_pct": 1.0101, "pre_range_atr": None,
                "pre_fetched_at": utc("2026-11-14T12:00:00.000123"),
                "pre_excluded_stale_prints": None, "pre_excluded_spikes": None,
                "pre_filter_status": "params_unavailable", "pre_filter_params": None}

    units = daily_units(new_of)
    result = br.write_group(engine, target=br.TARGET_PREMARKET, action="recompute",
                            run_id="run-1", units=units)
    assert list(result.values()) == [(True, None), (True, None)]

    first = row(engine, "market_data_daily", "date = '2026-10-05'")
    assert first["pre_volume"] == 330000
    assert first["pre_range_atr"] == 0.5
    assert first["pre_excluded_spikes"] == 0
    assert first["pre_filter_params"] == {"pm_stale_print_atr": 1.25, "pm_spike_atr": 0.5}
    assert first["pre_fetched_at"] == utc("2026-11-14T12:00:00.000123")
    assert first["pre_recompute_run"] == "run-1"

    second = row(engine, "market_data_daily", "date = '2026-10-06'")
    assert second["pre_range_atr"] is None
    assert second["pre_excluded_stale_prints"] is None
    assert second["pre_excluded_spikes"] is None
    assert second["pre_filter_params"] is None
    assert second["pre_filter_status"] == "params_unavailable"
    assert second["pre_volume"] == 330000
    assert second["close"] == 99.0

    held = br.ledger_of_run("run-1", br.TARGET_PREMARKET)
    assert held[1]["old_values"]["market_data_daily"]["pre_volume"] == 7654321
    assert held[1]["old_values"]["market_data_daily"]["pre_fetched_at"] == \
        "2026-10-06T13:31:00.000000+00:00"
    assert held[1]["new_values"]["market_data_daily"]["pre_range_atr"] is None
    assert held[0]["old_values"]["market_data_daily"]["pre_volume"] is None


def test_the_ledger_refuses_a_second_row_for_a_key(recompute_db):
    engine = recompute_db
    seed_three_alerts(engine)
    br.write_group(engine, target=br.TARGET_EXITS, action="recompute", run_id="run-1",
                   units=exit_units(NEW_EXIT))
    before_alerts = rows(engine, "signal_alerts")
    before_trades = rows(engine, "trades")
    before_ledger = rows(engine, "bar_recompute_ledger")

    again = exit_units(dict(NEW_EXIT, exit_price=5.0))
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        br.write_group(engine, target=br.TARGET_EXITS, action="recompute", run_id="run-1",
                       units=again)

    assert rows(engine, "signal_alerts") == before_alerts
    assert rows(engine, "trades") == before_trades
    assert rows(engine, "bar_recompute_ledger") == before_ledger


def test_one_statement_a_table_and_no_executemany(recompute_db):
    engine = recompute_db
    for minute in range(40):
        seed_alert(engine, "SPY", utc(f"2026-10-06T14:{minute:02d}:07.500000"),
                   exit_ts=utc("2026-10-06T15:31:00"), reason="time_stop", price=100.0, ret=0.0)
    units = exit_units(NEW_EXIT)
    assert len(units) == 40

    seen = []

    def record(conn, cursor, statement, parameters, context, executemany):
        seen.append((statement, executemany))

    sqlalchemy.event.listen(engine, "before_cursor_execute", record)
    try:
        result = br.write_group(engine, target=br.TARGET_EXITS, action="recompute",
                                run_id="run-1", units=units)
    finally:
        sqlalchemy.event.remove(engine, "before_cursor_execute", record)

    assert all(pair == (True, True) for pair in result.values())
    assert len(seen) == 3
    assert not any(many for _statement, many in seen)
    assert seen[0][0].lstrip().startswith("UPDATE signal_alerts")
    assert seen[1][0].lstrip().startswith("UPDATE trades")
    assert seen[2][0].lstrip().startswith("INSERT INTO bar_recompute_ledger")


def test_an_empty_group_and_a_group_nothing_matches_run_no_extra_statement(recompute_db):
    engine = recompute_db
    stamps = seed_three_alerts(engine)
    units = exit_units(NEW_EXIT)
    execute(engine, "UPDATE signal_alerts SET exit_price = 999.0")

    seen = []

    def record(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    sqlalchemy.event.listen(engine, "before_cursor_execute", record)
    try:
        assert br.write_group(engine, target=br.TARGET_EXITS, action="recompute",
                              run_id="run-1", units=[]) == {}
        assert seen == []
        result = br.write_group(engine, target=br.TARGET_EXITS, action="recompute",
                                run_id="run-1", units=units)
    finally:
        sqlalchemy.event.remove(engine, "before_cursor_execute", record)

    assert set(result.values()) == {(False, False)}
    assert len(seen) == 1
    assert rows(engine, "bar_recompute_ledger") == []
    assert len(stamps) == 3


# ── --re-resolve and --revert-run, through the resolver's main() ──────

import csv  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
from datetime import time  # noqa: E402

from lib.eastern_time import eastern_bounds_utc, session_close  # noqa: E402

ALERT_EXIT_FIELDS = ("exit_ts", "exit_reason", "exit_price", "exit_return_pct",
                     "exit_recompute_run")
TRADE_EXIT_FIELDS = ("exit_time", "exit_price", "exit_reason", "return_pct",
                     "exit_recompute_run")


def seed_bars(engine, ticker: str, day: date, base: float, *, first_et: str = "04:00",
              last_et: str = "19:59") -> None:
    """One bar a minute, in one statement: the close is base + 0.02 on odd
    minutes and base on even ones. Inserted now, so every row is proven."""
    start, end = eastern_bounds_utc(day, time.fromisoformat(first_et), time.fromisoformat(last_et))
    execute(engine, """
        INSERT INTO market_data_intraday (ticker, interval, ts, open, high, low, close, volume)
        SELECT :ticker, '1min', g, c, c, c, c, 1000
          FROM (SELECT g, CASE WHEN MOD(CAST(extract(minute FROM g) AS INTEGER), 2) = 1
                               THEN CAST(:odd AS DOUBLE PRECISION)
                               ELSE CAST(:even AS DOUBLE PRECISION) END AS c
                  FROM generate_series(CAST(:start AS TIMESTAMPTZ), CAST(:end AS TIMESTAMPTZ),
                                       INTERVAL '1 minute') AS g) AS s
    """, {"ticker": ticker, "odd": round(base + 0.02, 2), "even": base,
          "start": start, "end": end})


def run_resolver(monkeypatch, tmp_path, run_id: str, *argv: str) -> int:
    import gcp.signal_monitor_eod_resolver as resolver_module

    def no_http(*_args, **_kwargs):
        raise AssertionError("the recompute made an HTTP request")

    monkeypatch.setattr(resolver_module.requests, "post", no_http)
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    monkeypatch.setenv("CLOUD_RUN_EXECUTION", run_id)
    monkeypatch.setattr(sys, "argv", ["signal_monitor_eod_resolver", *argv,
                                      "--report-dir", str(tmp_path)])
    return resolver_module.main()


def read_report(tmp_path, target: str, run_id: str) -> tuple[dict, dict]:
    """rows.csv by row key (ticker, row_key) and summary.json."""
    folder = tmp_path / "bar-recompute" / "v1" / target / run_id
    with open(folder / "rows.csv", newline="") as handle:
        table = {(r["ticker"], r["row_key"]): r for r in csv.DictReader(handle)}
    return table, json.loads((folder / "summary.json").read_text())


def differing(before: dict, after: dict) -> set:
    return {column for column in before if before[column] != after[column]}


EXIT_WINDOW = ("--from", "2026-10-05", "--to", "2026-10-07")

# alert_ts of each seeded alert, by a short name.
A = {
    "spy_late": utc("2026-10-06T19:50:00.250000"),     # time_stop after the close -> eod_close
    "spy_same": utc("2026-10-06T14:00:07.500000"),     # already what the bars give
    "spy_target": utc("2026-10-06T15:00:01.000001"),   # stored price 0.1 + 0.2 -> target_hit
    "qqq_stop": utc("2026-10-06T14:10:03.000004"),     # wrong minute -> time_stop
    "spy_next": utc("2026-10-07T19:50:00.250000"),     # a second date -> eod_close
    "iwm_nobars": utc("2026-10-07T14:10:03.000004"),   # no bars stored
}


def seed_exit_world(engine) -> None:
    seed_bars(engine, "SPY", date(2026, 10, 6), 100.0)                   # after-hours bars stored
    seed_bars(engine, "QQQ", date(2026, 10, 6), 400.0)
    seed_bars(engine, "SPY", date(2026, 10, 7), 100.0, last_et="15:59")  # nothing after the close
    seed_alert(engine, "SPY", A["spy_late"], exit_ts=utc("2026-10-06T20:20:00"),
               reason="time_stop", price=100.0, ret=0.0)
    seed_alert(engine, "SPY", A["spy_same"], direction="PUT", target=90.0,
               exit_ts=utc("2026-10-06T14:31:00"), reason="time_stop", price=100.02,
               ret=-0.01999999999999602)
    seed_alert(engine, "SPY", A["spy_target"], target=100.02,
               exit_ts=utc("2026-10-06T15:03:00"), reason="target_hit", price=0.1 + 0.2,
               ret=0.495)
    seed_alert(engine, "QQQ", A["qqq_stop"], entry=400.0, target=440.0,
               exit_ts=utc("2026-10-06T14:45:00"), reason="time_stop", price=400.5, ret=0.125)
    seed_alert(engine, "SPY", A["spy_next"], exit_ts=utc("2026-10-07T20:20:00"),
               reason="time_stop", price=100.0, ret=0.0)
    seed_alert(engine, "IWM", A["iwm_nobars"], entry=200.0, target=220.0,
               exit_ts=utc("2026-10-07T14:41:00"), reason="time_stop", price=200.0, ret=0.0)


def seed_rows_never_selected(engine) -> dict:
    """Rows the selection must not return, each a whole-row snapshot."""
    seed_alert(engine, "SPY", utc("2026-10-06T16:00:00.111111"), run_kind="replay",
               exit_ts=utc("2026-10-06T16:31:00"), reason="time_stop", price=1.0, ret=1.0)
    seed_alert(engine, "SPY", utc("2026-10-06T16:05:00.111111"), run_kind="backfill",
               exit_ts=utc("2026-10-06T16:36:00"), reason="time_stop", price=1.0, ret=1.0)
    seed_alert(engine, "SPY", utc("2026-10-06T16:10:00.111111"), is_open=True)
    seed_alert(engine, "SPY", utc("2026-10-06T16:15:00.111111"),
               exit_ts=utc("2026-10-06T16:44:12.345678"), reason="target_hit", price=1.0, ret=1.0)
    return never_selected_rows(engine)


NEVER_SELECTED = "{column} >= '2026-10-06T16:00:00+00:00' AND {column} < '2026-10-06T19:00:00+00:00'"


def never_selected_rows(engine) -> dict:
    return {"alerts": rows(engine, "signal_alerts", NEVER_SELECTED.format(column="alert_ts")),
            "trades": rows(engine, "trades", NEVER_SELECTED.format(column="entry_time"))}


def alert_row(engine, name: str) -> dict:
    return row(engine, "signal_alerts", "alert_ts = :ts", {"ts": A[name]})


def trade_row(engine, name: str) -> dict:
    return row(engine, "trades", "entry_time = :ts", {"ts": A[name]})


def key_of(name: str) -> str:
    return br.json_value(A[name])


def test_a_committed_run_overwrites_only_the_exit_fields(recompute_db, monkeypatch, tmp_path):
    engine = recompute_db
    seed_exit_world(engine)
    never = seed_rows_never_selected(engine)
    names = ("spy_late", "spy_same", "spy_target", "qqq_stop", "spy_next")
    before = {n: (alert_row(engine, n), trade_row(engine, n)) for n in names}

    code = run_resolver(monkeypatch, tmp_path, "exits-run-1", "--re-resolve", *EXIT_WINDOW,
                        "--commit")

    assert code == 1  # the IWM alert has no bars and is left
    expected = {
        "spy_late": (utc("2026-10-06T20:00:00"), "eod_close", 100.02, 0.01999999999999602),
        "spy_same": (utc("2026-10-06T14:31:00"), "time_stop", 100.02, -0.01999999999999602),
        "spy_target": (utc("2026-10-06T15:01:00"), "target_hit", 100.02, 0.01999999999999602),
        "qqq_stop": (utc("2026-10-06T14:41:00"), "time_stop", 400.02, 0.0049999999999954525),
        "spy_next": (utc("2026-10-07T20:00:00"), "eod_close", 100.02, 0.01999999999999602),
    }
    for name in names:
        alert, trade = alert_row(engine, name), trade_row(engine, name)
        exit_ts, reason, price, ret = expected[name]
        assert (alert["exit_ts"], alert["exit_reason"], alert["exit_price"],
                alert["exit_return_pct"], alert["exit_recompute_run"]) == (
            exit_ts, reason, price, ret, "exits-run-1"), name
        assert (trade["exit_time"], trade["exit_price"], trade["exit_reason"],
                trade["return_pct"], trade["exit_recompute_run"]) == (
            exit_ts, price, reason, ret, "exits-run-1"), name
        assert differing(before[name][0], alert) <= set(ALERT_EXIT_FIELDS), name
        assert differing(before[name][1], trade) <= set(TRADE_EXIT_FIELDS), name
        assert alert["is_open"] is False

    # Not selected: equal in every column.
    after = never_selected_rows(engine)
    assert len(never["alerts"]) == 4 and len(never["trades"]) == 4
    assert after == never

    table, summary = read_report(tmp_path, "signal-alert-exits", "exits-run-1")
    assert {k: (r["status"], r["written"]) for k, r in table.items()} == {
        ("SPY", key_of("spy_late")): ("recomputed", "true"),
        ("SPY", key_of("spy_same")): ("recomputed", "true"),
        ("SPY", key_of("spy_target")): ("recomputed", "true"),
        ("QQQ", key_of("qqq_stop")): ("recomputed", "true"),
        ("SPY", key_of("spy_next")): ("recomputed", "true"),
        ("IWM", key_of("iwm_nobars")): ("no_bars", "false"),
    }
    assert table[("SPY", key_of("spy_same"))]["changed"] == "false"
    assert summary["written"] == 5
    assert summary["arguments"]["commit"] is True


def test_a_diverged_trade_is_left_and_its_alert_written(recompute_db, monkeypatch, tmp_path):
    engine = recompute_db
    seed_exit_world(engine)
    execute(engine, "UPDATE trades SET exit_price = 77.0 WHERE entry_time = :ts",
            {"ts": A["qqq_stop"]})
    trade_before = trade_row(engine, "qqq_stop")

    code = run_resolver(monkeypatch, tmp_path, "exits-run-1", "--re-resolve",
                        "--from", "2026-10-06", "--to", "2026-10-06", "--commit")

    assert code == 1
    assert trade_row(engine, "qqq_stop") == trade_before
    alert = alert_row(engine, "qqq_stop")
    assert alert["exit_ts"] == utc("2026-10-06T14:41:00")
    assert alert["exit_recompute_run"] == "exits-run-1"
    table, _summary = read_report(tmp_path, "signal-alert-exits", "exits-run-1")
    assert table[("QQQ", key_of("qqq_stop"))]["status"] == "trade_diverged"
    assert table[("QQQ", key_of("qqq_stop"))]["written"] == "true"
    held = [h for h in br.ledger_of_run("exits-run-1", br.TARGET_EXITS) if h["ticker"] == "QQQ"]
    assert len(held) == 1 and held[0]["new_values"]["trades"] is None


def test_an_alert_with_no_trade_is_written(recompute_db, monkeypatch, tmp_path):
    engine = recompute_db
    seed_bars(engine, "QQQ", date(2026, 10, 6), 400.0)
    seed_alert(engine, "QQQ", A["qqq_stop"], entry=400.0, target=440.0, trade=False,
               exit_ts=utc("2026-10-06T14:45:00"), reason="time_stop", price=400.5, ret=0.125)

    code = run_resolver(monkeypatch, tmp_path, "exits-run-1", "--re-resolve",
                        "--from", "2026-10-06", "--to", "2026-10-06", "--commit")

    assert code == 0
    assert alert_row(engine, "qqq_stop")["exit_recompute_run"] == "exits-run-1"
    assert rows(engine, "trades") == []
    table, _summary = read_report(tmp_path, "signal-alert-exits", "exits-run-1")
    assert table[("QQQ", key_of("qqq_stop"))]["status"] == "trade_missing"
    assert table[("QQQ", key_of("qqq_stop"))]["written"] == "true"
    held, = br.ledger_of_run("exits-run-1", br.TARGET_EXITS)
    assert held["old_values"]["trades"] is None and held["new_values"]["trades"] is None


def test_an_alert_changed_underneath_leaves_its_trade(recompute_db, monkeypatch, tmp_path):
    engine = recompute_db
    seed_exit_world(engine)
    real_save = br.save_report
    saves = []

    def save_after_another_writer(*args, **kwargs):
        if not saves:
            # Between the run's read and its write.
            execute(engine, "UPDATE signal_alerts SET exit_price = 999.0 WHERE alert_ts = :ts",
                    {"ts": A["spy_late"]})
        saves.append(1)
        return real_save(*args, **kwargs)

    trade_before = trade_row(engine, "spy_late")
    monkeypatch.setattr(br, "save_report", save_after_another_writer)
    code = run_resolver(monkeypatch, tmp_path, "exits-run-1", "--re-resolve",
                        "--from", "2026-10-06", "--to", "2026-10-06", "--commit")

    assert code == 1
    alert = alert_row(engine, "spy_late")
    assert alert["exit_price"] == 999.0
    assert alert["exit_reason"] == "time_stop"
    assert alert["exit_recompute_run"] is None
    # The trade still held the alert's old exit; it follows its alert and stays.
    assert trade_row(engine, "spy_late") == trade_before
    table, _summary = read_report(tmp_path, "signal-alert-exits", "exits-run-1")
    assert table[("SPY", key_of("spy_late"))]["status"] == "changed_underneath"
    assert table[("SPY", key_of("spy_late"))]["written"] == "false"
    held = br.ledger_of_run("exits-run-1", br.TARGET_EXITS)
    assert key_of("spy_late") not in {h["row_key"] for h in held}
    assert len(held) == 3
    assert alert_row(engine, "spy_target")["exit_recompute_run"] == "exits-run-1"


def test_each_written_alert_has_one_ledger_row(recompute_db, monkeypatch, tmp_path):
    engine = recompute_db
    seed_exit_world(engine)
    run_resolver(monkeypatch, tmp_path, "exits-run-1", "--re-resolve", *EXIT_WINDOW, "--commit")

    held = br.ledger_of_run("exits-run-1", br.TARGET_EXITS)
    assert sorted(h["row_key"] for h in held) == sorted(
        key_of(n) for n in ("spy_late", "spy_same", "spy_target", "qqq_stop", "spy_next"))
    late = next(h for h in held if h["row_key"] == key_of("spy_late"))
    assert late["action"] == "recompute"
    assert late["changed"] is True
    assert late["session_date"] == date(2026, 10, 6)
    assert late["old_values"] == {
        "signal_alerts": {"exit_ts": "2026-10-06T20:20:00.000000+00:00",
                          "exit_reason": "time_stop", "exit_price": 100.0,
                          "exit_return_pct": 0.0, "exit_recompute_run": None},
        "trades": {"exit_time": "2026-10-06T20:20:00.000000+00:00", "exit_price": 100.0,
                   "exit_reason": "time_stop", "return_pct": 0.0, "exit_recompute_run": None}}
    assert late["new_values"] == {
        "signal_alerts": {"exit_ts": "2026-10-06T20:00:00.000000+00:00",
                          "exit_reason": "eod_close", "exit_price": 100.02,
                          "exit_return_pct": 0.01999999999999602,
                          "exit_recompute_run": "exits-run-1"},
        "trades": {"exit_time": "2026-10-06T20:00:00.000000+00:00", "exit_price": 100.02,
                   "exit_reason": "eod_close", "return_pct": 0.01999999999999602,
                   "exit_recompute_run": "exits-run-1"}}
    same = next(h for h in held if h["row_key"] == key_of("spy_same"))
    assert same["changed"] is False

    bars = late["basis"]["bars"]
    assert bars["rows"] == 960
    assert len(bars["sha256"]) == 64
    assert bars["first_ts"] == "2026-10-06T08:00:00.000000+00:00"
    assert bars["last_ts"] == "2026-10-06T23:59:00.000000+00:00"
    assert bars["inserted_min"] <= bars["inserted_max"]
    assert "git_commit" in late["basis"]["code"]
    assert late["basis"]["configuration"] == {
        "call_exit_mode": "target_stop", "put_exit_mode": "target_stop", "rsi_period": 14,
        "call_rsi_exit": 80.0, "put_rsi_exit": 20.0}


def test_groups_commit_one_at_a_time(recompute_db, monkeypatch, tmp_path):
    engine = recompute_db
    seed_exit_world(engine)
    real_write = br.write_group
    calls = []
    failure = RuntimeError("the second group fails")

    def failing_second(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise failure
        return real_write(*args, **kwargs)

    monkeypatch.setattr(br, "write_group", failing_second)
    with pytest.raises(RuntimeError) as caught:
        run_resolver(monkeypatch, tmp_path, "exits-run-1", "--re-resolve", *EXIT_WINDOW,
                     "--commit")
    assert caught.value is failure

    # The first group (QQQ 2026-10-06) is committed with its ledger row.
    assert alert_row(engine, "qqq_stop")["exit_recompute_run"] == "exits-run-1"
    assert trade_row(engine, "qqq_stop")["exit_recompute_run"] == "exits-run-1"
    held = br.ledger_of_run("exits-run-1", br.TARGET_EXITS)
    assert [h["ticker"] for h in held] == ["QQQ"]
    # The second (SPY 2026-10-06) and everything after it are not.
    for name in ("spy_late", "spy_same", "spy_target", "spy_next"):
        assert alert_row(engine, name)["exit_recompute_run"] is None
        assert trade_row(engine, name)["exit_recompute_run"] is None
    assert alert_row(engine, "spy_late")["exit_reason"] == "time_stop"


def test_a_second_run_writes_nothing(recompute_db, monkeypatch, tmp_path):
    engine = recompute_db
    seed_bars(engine, "SPY", date(2026, 10, 6), 100.0)
    for name in ("spy_late", "spy_same"):
        seed_alert(engine, "SPY", A[name], direction="PUT" if name == "spy_same" else "CALL",
                   target=90.0 if name == "spy_same" else 110.0,
                   exit_ts=utc("2026-10-06T14:31:00"), reason="time_stop", price=100.02,
                   ret=-0.01999999999999602)
    window = ("--from", "2026-10-06", "--to", "2026-10-06")
    assert run_resolver(monkeypatch, tmp_path, "exits-run-1", "--re-resolve", *window,
                        "--commit") == 0
    alerts, trades = rows(engine, "signal_alerts"), rows(engine, "trades")
    ledger = rows(engine, "bar_recompute_ledger")
    assert len(ledger) == 2

    assert run_resolver(monkeypatch, tmp_path, "exits-run-2", "--re-resolve", *window,
                        "--commit") == 0

    assert rows(engine, "signal_alerts") == alerts
    assert rows(engine, "trades") == trades
    assert rows(engine, "bar_recompute_ledger") == ledger
    table, summary = read_report(tmp_path, "signal-alert-exits", "exits-run-2")
    assert {r["status"] for r in table.values()} == {"already_current"}
    assert {r["written"] for r in table.values()} == {"false"}
    assert summary["written"] == 0


def marker_count(engine, table: str, column: str, run_id: str) -> int:
    with engine.connect() as conn:
        return conn.execute(sqlalchemy.text(
            f"SELECT count(*) FROM {table} WHERE {column} = :run_id"),
            {"run_id": run_id}).scalar_one()


def test_markers_per_run_and_coverage_are_two_checks(recompute_db, monkeypatch, tmp_path):
    engine = recompute_db
    seed_exit_world(engine)
    # Run A: one date. Run B: the whole window, one group of it with no bars.
    assert run_resolver(monkeypatch, tmp_path, "exits-run-A", "--re-resolve",
                        "--from", "2026-10-06", "--to", "2026-10-06", "--commit") == 0
    assert run_resolver(monkeypatch, tmp_path, "exits-run-B", "--re-resolve", *EXIT_WINDOW,
                        "--commit") == 1

    table, _summary = read_report(tmp_path, "signal-alert-exits", "exits-run-B")
    selected = len(table)
    written = [r for r in table.values() if r["written"] == "true"]
    refused_or_left = {k for k, r in table.items() if r["status"] in br.REFUSED_STATUSES}

    # Per run: the rows whose marker is this run's id are its written rows.
    assert marker_count(engine, "signal_alerts", "exit_recompute_run", "exits-run-B") == len(written)
    assert marker_count(engine, "trades", "exit_recompute_run", "exits-run-B") == len(written)
    assert len(br.ledger_of_run("exits-run-B", br.TARGET_EXITS)) == len(written)
    assert 0 < len(written) < selected

    # Coverage: a selected alert has a marker, or is in the report as refused or left.
    unmarked = rows(engine, "signal_alerts", "exit_recompute_run IS NULL")
    assert {(a["ticker"], br.json_value(a["alert_ts"])) for a in unmarked} == refused_or_left
    assert refused_or_left == {("IWM", key_of("iwm_nobars"))}

    # Run A's rows were already current for B and keep A's id.
    assert marker_count(engine, "signal_alerts", "exit_recompute_run", "exits-run-A") == 4
    for name in ("spy_late", "spy_same", "spy_target", "qqq_stop"):
        assert table[(alert_row(engine, name)["ticker"], key_of(name))]["status"] == "already_current"


def test_the_stored_exit_is_the_deciding_bars_close(recompute_db, monkeypatch, tmp_path):
    engine = recompute_db
    seed_exit_world(engine)
    run_resolver(monkeypatch, tmp_path, "exits-run-1", "--re-resolve", *EXIT_WINDOW, "--commit")

    written = rows(engine, "signal_alerts", "exit_recompute_run = 'exits-run-1'")
    assert {a["exit_reason"] for a in written} == {"eod_close", "time_stop", "target_hit"}
    for alert in written:
        at_exit = rows(engine, "market_data_intraday", "ticker = :t AND ts = :ts",
                       {"t": alert["ticker"], "ts": alert["exit_ts"]}, order="ts")
        if alert["exit_reason"] == "eod_close":
            # Stamped with the session close, priced from the last bar before it.
            assert alert["exit_ts"] == session_close(alert["alert_date"])
            before_close = rows(
                engine, "market_data_intraday", "ticker = :t AND ts < :ts AND ts >= :lo",
                {"t": alert["ticker"], "ts": alert["exit_ts"],
                 "lo": eastern_bounds_utc(alert["alert_date"], time(0), time(0))[0]},
                order="ts")
            deciding = before_close[-1]
            assert alert["exit_price"] == deciding["close"]
            assert (alert["exit_ts"] - deciding["ts"]).total_seconds() == 60
            # A bar at the exit minute, when one is stored, is the first
            # after-hours bar, and its close is not the exit price.
            assert all(bar["close"] != alert["exit_price"] for bar in at_exit)
        else:
            deciding, = at_exit
            assert alert["exit_price"] == deciding["close"]
    # Both shapes are in the fixture: after-hours bars stored, and none.
    assert len(rows(engine, "market_data_intraday", "ticker = 'SPY' AND ts = :ts",
                    {"ts": utc("2026-10-06T20:00:00")}, order="ts")) == 1
    assert rows(engine, "market_data_intraday", "ticker = 'SPY' AND ts = :ts",
                {"ts": utc("2026-10-07T20:00:00")}, order="ts") == []


def test_revert_restores_the_old_values(recompute_db, monkeypatch, tmp_path):
    engine = recompute_db
    seed_exit_world(engine)
    names = ("spy_late", "spy_same", "spy_target", "qqq_stop")
    before = {n: (alert_row(engine, n), trade_row(engine, n)) for n in names}
    window = ("--from", "2026-10-06", "--to", "2026-10-06")
    assert run_resolver(monkeypatch, tmp_path, "exits-run-A", "--re-resolve", *window,
                        "--commit") == 0
    after_run = {n: (alert_row(engine, n), trade_row(engine, n)) for n in names}
    ledger_after_run = rows(engine, "bar_recompute_ledger")

    # A dry revert writes nothing and says what it would do.
    assert run_resolver(monkeypatch, tmp_path, "revert-dry", "--revert-run", "exits-run-A") == 0
    assert {n: (alert_row(engine, n), trade_row(engine, n)) for n in names} == after_run
    assert rows(engine, "bar_recompute_ledger") == ledger_after_run
    table, _summary = read_report(tmp_path, "signal-alert-exits", "revert-dry")
    assert {r["status"] for r in table.values()} == {"would_revert"}
    assert {r["written"] for r in table.values()} == {"false"}

    # A later write changes one row; the revert must leave it.
    execute(engine, "UPDATE signal_alerts SET exit_price = 555.0 WHERE alert_ts = :ts",
            {"ts": A["qqq_stop"]})

    assert run_resolver(monkeypatch, tmp_path, "revert-1", "--revert-run", "exits-run-A",
                        "--commit") == 1

    for name in ("spy_late", "spy_same", "spy_target"):
        alert, trade = alert_row(engine, name), trade_row(engine, name)
        for field in ALERT_EXIT_FIELDS[:4]:
            assert alert[field] == before[name][0][field], (name, field)
        for field in TRADE_EXIT_FIELDS[:4]:
            assert trade[field] == before[name][1][field], (name, field)
        assert alert["exit_recompute_run"] == "revert-1"
        assert trade["exit_recompute_run"] == "revert-1"
        assert differing(before[name][0], alert) == {"exit_recompute_run"}
        assert differing(before[name][1], trade) == {"exit_recompute_run"}
    assert alert_row(engine, "spy_target")["exit_price"] == 0.1 + 0.2

    left = alert_row(engine, "qqq_stop")
    assert left["exit_price"] == 555.0
    assert left["exit_recompute_run"] == "exits-run-A"
    assert trade_row(engine, "qqq_stop") == after_run["qqq_stop"][1]

    reverted = br.ledger_of_run("revert-1", br.TARGET_EXITS)
    assert sorted(h["row_key"] for h in reverted) == sorted(
        key_of(n) for n in ("spy_late", "spy_same", "spy_target"))
    assert {h["action"] for h in reverted} == {"revert"}
    assert {h["basis"]["revert_of"] for h in reverted} == {"exits-run-A"}
    table, _summary = read_report(tmp_path, "signal-alert-exits", "revert-1")
    assert table[("QQQ", key_of("qqq_stop"))]["status"] == "changed_underneath"
    assert table[("SPY", key_of("spy_late"))]["status"] == "reverted"
    assert table[("SPY", key_of("spy_late"))]["written"] == "true"
    # The first run's ledger rows are still there: nothing is deleted.
    assert len(br.ledger_of_run("exits-run-A", br.TARGET_EXITS)) == 4


# ── --recompute-premarket and --revert-run, through the fetcher's main() ──

import uuid  # noqa: E402
from datetime import timedelta  # noqa: E402

PREMARKET_FIELDS = (
    "pre_high", "pre_low", "pre_vwap", "pre_volume", "gap_pct", "pre_range_atr",
    "pre_fetched_at", "pre_excluded_stale_prints", "pre_excluded_spikes",
    "pre_filter_status", "pre_filter_params", "pre_recompute_run",
)
SEPTEMBER = (date(2026, 9, 29), date(2026, 9, 30))
OCTOBER = (date(2026, 10, 5), date(2026, 10, 6))
PREMARKET_WINDOW = ("--from", "2026-09-29", "--to", "2026-10-06")


def seed_daily(engine, ticker: str, first: date, last: date) -> None:
    """One daily row a weekday: open 99, high 100, low 98, close 99, so the
    ATR of every session is 2.0."""
    execute(engine, """
        INSERT INTO market_data_daily (ticker, date, open, high, low, close, volume)
        SELECT :ticker, CAST(g AS DATE), 99.0, 100.0, 98.0, 99.0, 1000000
          FROM generate_series(CAST(:first AS DATE), CAST(:last AS DATE), INTERVAL '1 day') AS g
         WHERE extract(isodow FROM g) < 6
    """, {"ticker": ticker, "first": first, "last": last})


def seed_premarket_bars(engine, ticker: str, day: date) -> None:
    """330 bars, 04:00 to 09:29 Eastern: open 100.0, high 100.5, low 99.5,
    close 100.0, volume 1000. Inserted now, so every row is proven."""
    start, end = eastern_bounds_utc(day, time(4), time(9, 29))
    execute(engine, """
        INSERT INTO market_data_intraday (ticker, interval, ts, open, high, low, close, volume)
        SELECT :ticker, '1min', g, 100.0, 100.5, 99.5, 100.0, 1000
          FROM generate_series(CAST(:start AS TIMESTAMPTZ), CAST(:end AS TIMESTAMPTZ),
                               INTERVAL '1 minute') AS g
    """, {"ticker": ticker, "start": start, "end": end})


def seed_stored_premarket(engine, ticker: str, day: date, **overrides) -> None:
    values = {"pre_high": 100.25, "pre_low": 99.75, "pre_vwap": 100.01, "pre_volume": 300000,
              "gap_pct": 0.9, "pre_range_atr": 0.4}
    values.update(overrides)
    assignments = ", ".join(f"{column} = :{column}" for column in values)
    execute(engine, f"UPDATE market_data_daily SET {assignments} "
                    "WHERE ticker = :ticker AND date = :day",
            {**values, "ticker": ticker, "day": day})


def seed_level_params(engine, ticker: str, effective_from: date) -> None:
    for key, value in (("pm_stale_print_atr", 0.1), ("pm_spike_atr", 0.5)):
        execute(engine, """
            INSERT INTO ticker_level_params (ticker, param_key, value, status, atr_basis,
                method_id, policy_effective_from, sample_n, input_from, input_to,
                effective_from, run_id, source, calibrated_at)
            VALUES (:ticker, :key, :value, 'ok', 'atr_14', 'fixture', '2015-01-02', 750,
                    '2023-01-03', :eff, :eff, :run_id, 'history', NOW())
        """, {"ticker": ticker, "key": key, "value": value, "eff": effective_from,
              "run_id": str(uuid.uuid4())})


def seed_premarket_world(engine, *, qqq_october_bars: bool = True) -> None:
    """SPY and QQQ: two sessions in September (no parameters yet) and two in
    October (parameters in force from 2026-10-01), each holding stored
    premarket values, with daily history before them and premarket bars."""
    for ticker in ("SPY", "QQQ"):
        seed_daily(engine, ticker, date(2026, 7, 27), date(2026, 10, 6))
        seed_level_params(engine, ticker, date(2026, 10, 1))
        for day in (*SEPTEMBER, *OCTOBER):
            seed_stored_premarket(engine, ticker, day)
            if ticker == "QQQ" and day in OCTOBER and not qqq_october_bars:
                continue
            seed_premarket_bars(engine, ticker, day)


def run_fetcher(monkeypatch, tmp_path, run_id: str, *argv: str) -> int:
    from gcp.fetchers import fetch_market_data as fmd

    def no_http(*_args, **_kwargs):
        raise AssertionError("the recompute made an HTTP request")

    monkeypatch.setattr(fmd.requests, "get", no_http)
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    monkeypatch.setenv("CLOUD_RUN_EXECUTION", run_id)
    monkeypatch.setattr(sys, "argv", ["fetch_market_data", *argv, "--report-dir", str(tmp_path)])
    return fmd.main()


def daily_rows(engine, where: str = "TRUE", params: dict | None = None) -> list[dict]:
    """Daily rows with pre_filter_params as the database's own text too."""
    with engine.connect() as conn:
        result = conn.execute(sqlalchemy.text(
            "SELECT *, pre_filter_params::text AS pre_filter_params_text "
            f"FROM market_data_daily WHERE {where} ORDER BY ticker, date"), params or {})
        return [dict(r) for r in result.mappings()]


def daily_row(engine, ticker: str, day: date) -> dict:
    found = daily_rows(engine, "ticker = :t AND date = :d", {"t": ticker, "d": day})
    assert len(found) == 1
    return found[0]


SELECTED_DAILY = "pre_high IS NOT NULL AND ticker IN ('SPY', 'QQQ') AND date <= '2026-10-06'"


def test_a_committed_run_overwrites_the_twelve_columns(recompute_db, monkeypatch, tmp_path):
    from lib.eastern_time import market_today

    engine = recompute_db
    seed_premarket_world(engine)
    # Never selected: another ticker, a row with no premarket value, today's row.
    seed_daily(engine, "AMD", date(2026, 10, 6), date(2026, 10, 6))
    seed_stored_premarket(engine, "AMD", date(2026, 10, 6))
    today = market_today()
    execute(engine, "INSERT INTO market_data_daily (ticker, date, close, pre_high, gap_pct) "
                    "VALUES ('SPY', :today, 99.0, 100.25, 0.9)", {"today": today})
    untouched_where = ("ticker = 'AMD' OR (ticker = 'SPY' AND date = :today) "
                       "OR (ticker IN ('SPY', 'QQQ') AND pre_high IS NULL)")
    untouched = daily_rows(engine, untouched_where, {"today": today})
    assert len(untouched) > 50
    before = {(r["ticker"], r["date"]): r for r in daily_rows(engine, SELECTED_DAILY)}
    assert len(before) == 8

    code = run_fetcher(monkeypatch, tmp_path, "premarket-run-1", "--recompute-premarket",
                       *PREMARKET_WINDOW, "--commit")

    assert code == 0
    after = {(r["ticker"], r["date"]): r for r in daily_rows(engine, SELECTED_DAILY)}
    for key, row_after in after.items():
        ticker, day = key
        assert (row_after["pre_high"], row_after["pre_low"], row_after["pre_vwap"],
                row_after["pre_volume"], row_after["gap_pct"]) == (
            100.5, 99.5, 100.0, 330000, 1.0101), key
        assert row_after["pre_recompute_run"] == "premarket-run-1"
        assert row_after["pre_fetched_at"] is not None
        if day in OCTOBER:
            assert row_after["pre_filter_status"] == "ok"
            assert row_after["pre_range_atr"] == 0.5
            assert (row_after["pre_excluded_stale_prints"], row_after["pre_excluded_spikes"]) == (0, 0)
            assert row_after["pre_filter_params"]["pm_spike_atr"]["value"] == 0.5
            assert row_after["pre_filter_params"]["pm_spike_atr"]["effective_from"] == "2026-10-01"
        else:
            # No parameters in force yet: unfiltered, and the stored 0.4 is
            # replaced by NULL, not kept beside the new values.
            assert row_after["pre_filter_status"] == "params_unavailable"
            assert row_after["pre_range_atr"] is None
            assert row_after["pre_excluded_stale_prints"] is None
            assert row_after["pre_excluded_spikes"] is None
            assert row_after["pre_filter_params"]["pm_spike_atr"]["status"] == "params_unavailable"
        changed_columns = differing(before[key], row_after)
        assert changed_columns <= {*PREMARKET_FIELDS, "pre_filter_params_text", "updated_at"}, key

    assert daily_rows(engine, untouched_where, {"today": today}) == untouched

    table, summary = read_report(tmp_path, "daily-premarket", "premarket-run-1")
    assert len(table) == 8
    assert {r["status"] for r in table.values()} == {"recomputed"}
    assert {r["written"] for r in table.values()} == {"true"}
    assert summary["written"] == 8


def test_a_premarket_row_changed_underneath_is_left(recompute_db, monkeypatch, tmp_path):
    engine = recompute_db
    seed_premarket_world(engine)
    real_save = br.save_report
    saves = []

    def save_after_another_writer(*args, **kwargs):
        if not saves:
            execute(engine, "UPDATE market_data_daily SET pre_high = 1.0 "
                            "WHERE ticker = 'SPY' AND date = '2026-10-06'")
        saves.append(1)
        return real_save(*args, **kwargs)

    monkeypatch.setattr(br, "save_report", save_after_another_writer)
    code = run_fetcher(monkeypatch, tmp_path, "premarket-run-1", "--recompute-premarket",
                       *PREMARKET_WINDOW, "--commit")

    assert code == 1
    left = daily_row(engine, "SPY", date(2026, 10, 6))
    assert left["pre_high"] == 1.0
    assert left["pre_low"] == 99.75
    assert left["pre_recompute_run"] is None
    table, _summary = read_report(tmp_path, "daily-premarket", "premarket-run-1")
    assert table[("SPY", "2026-10-06")]["status"] == "changed_underneath"
    assert table[("SPY", "2026-10-06")]["written"] == "false"
    held = br.ledger_of_run("premarket-run-1", br.TARGET_PREMARKET)
    assert len(held) == 7
    assert ("SPY", "2026-10-06") not in {(h["ticker"], h["row_key"]) for h in held}
    # The other row of the same group was written in the same transaction.
    assert daily_row(engine, "SPY", date(2026, 10, 5))["pre_recompute_run"] == "premarket-run-1"


def test_each_written_premarket_row_has_one_ledger_row(recompute_db, monkeypatch, tmp_path):
    engine = recompute_db
    seed_premarket_world(engine)
    run_fetcher(monkeypatch, tmp_path, "premarket-run-1", "--recompute-premarket",
                *PREMARKET_WINDOW, "--commit")

    held = br.ledger_of_run("premarket-run-1", br.TARGET_PREMARKET)
    assert sorted((h["ticker"], h["row_key"]) for h in held) == sorted(
        (t, d.isoformat()) for t in ("SPY", "QQQ") for d in (*SEPTEMBER, *OCTOBER))
    entry = next(h for h in held if (h["ticker"], h["row_key"]) == ("SPY", "2026-09-29"))
    assert entry["action"] == "recompute" and entry["changed"] is True
    assert entry["session_date"] == date(2026, 9, 29)
    assert entry["old_values"] == {"market_data_daily": {
        "pre_high": 100.25, "pre_low": 99.75, "pre_vwap": 100.01, "gap_pct": 0.9,
        "pre_range_atr": 0.4, "pre_volume": 300000, "pre_fetched_at": None,
        "pre_excluded_stale_prints": None, "pre_excluded_spikes": None,
        "pre_filter_status": None, "pre_filter_params": None, "pre_recompute_run": None}}
    new = entry["new_values"]["market_data_daily"]
    stored = daily_row(engine, "SPY", date(2026, 9, 29))
    assert new["pre_recompute_run"] == "premarket-run-1"
    assert new["pre_range_atr"] is None
    assert new["pre_volume"] == 330000
    assert new["pre_fetched_at"] == br.json_value(stored["pre_fetched_at"])
    assert json.loads(new["pre_filter_params"]) == stored["pre_filter_params"]
    basis = entry["basis"]
    assert basis["bars"]["rows"] == 330 and len(basis["bars"]["sha256"]) == 64
    assert basis["bars"]["first_ts"] == "2026-09-29T08:00:00.000000+00:00"
    assert basis["bars"]["last_ts"] == "2026-09-29T13:29:00.000000+00:00"
    assert basis["prior"] == {"close": 99.0, "open": 99.0, "atr_14": 2.0, "atr_5": 2.0}
    assert basis["filter"]["status"] == "params_unavailable"
    assert "git_commit" in basis["code"]


def test_a_retry_under_the_same_run_id_reports_from_the_ledger(recompute_db, monkeypatch,
                                                                tmp_path):
    engine = recompute_db
    seed_premarket_world(engine)
    real_write = br.write_group
    calls = []
    failure = RuntimeError("the second group fails")

    def failing_second(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise failure
        return real_write(*args, **kwargs)

    with monkeypatch.context() as first_attempt:
        first_attempt.setattr(br, "write_group", failing_second)
        with pytest.raises(RuntimeError) as caught:
            run_fetcher(first_attempt, tmp_path, "premarket-run-1", "--recompute-premarket",
                        *PREMARKET_WINDOW, "--commit")
        assert caught.value is failure
    # The first group (QQQ 2026-09) is committed; nothing after it is.
    assert len(br.ledger_of_run("premarket-run-1", br.TARGET_PREMARKET)) == 2

    # The retry: the same execution, so the same run id.
    code = run_fetcher(monkeypatch, tmp_path, "premarket-run-1", "--recompute-premarket",
                       *PREMARKET_WINDOW, "--commit")

    assert code == 0
    held = br.ledger_of_run("premarket-run-1", br.TARGET_PREMARKET)
    assert len(held) == 8
    assert len({(h["ticker"], h["row_key"]) for h in held}) == 8
    table, summary = read_report(tmp_path, "daily-premarket", "premarket-run-1")
    for day in SEPTEMBER:
        first_group_row = table[("QQQ", day.isoformat())]
        # The values stored before the first attempt, not the new ones read back.
        assert first_group_row["old_pre_high"] == "100.25"
        assert first_group_row["old_pre_range_atr"] == "0.4"
        assert first_group_row["new_pre_high"] == "100.5"
        assert first_group_row["written"] == "true"
        assert first_group_row["changed"] == "true"
        assert first_group_row["status"] == "recomputed"
    assert {r["written"] for r in table.values()} == {"true"}
    assert summary["written"] == 8
    assert marker_count(engine, "market_data_daily", "pre_recompute_run", "premarket-run-1") == 8


def test_a_second_run_at_a_later_instant_writes_nothing(recompute_db, monkeypatch, tmp_path):
    from gcp.fetchers import fetch_market_data as fmd

    engine = recompute_db
    seed_premarket_world(engine)
    assert run_fetcher(monkeypatch, tmp_path, "premarket-run-1", "--recompute-premarket",
                       *PREMARKET_WINDOW, "--commit") == 0
    recorded = {(r["ticker"], r["date"]): (r["pre_fetched_at"], r["pre_recompute_run"],
                                           r["updated_at"])
                for r in daily_rows(engine, SELECTED_DAILY)}
    ledger = rows(engine, "bar_recompute_ledger")

    later = fmd.utc_now() + timedelta(hours=1)
    monkeypatch.setattr(fmd, "utc_now", lambda: later)
    code = run_fetcher(monkeypatch, tmp_path, "premarket-run-2", "--recompute-premarket",
                       *PREMARKET_WINDOW, "--commit")

    assert code == 0
    assert rows(engine, "bar_recompute_ledger") == ledger
    assert {(r["ticker"], r["date"]): (r["pre_fetched_at"], r["pre_recompute_run"],
                                       r["updated_at"])
            for r in daily_rows(engine, SELECTED_DAILY)} == recorded
    table, summary = read_report(tmp_path, "daily-premarket", "premarket-run-2")
    assert {r["status"] for r in table.values()} == {"already_current"}
    assert summary["written"] == 0
    # The report shows the read time this run would have written, had a value changed.
    assert all(r["new_pre_fetched_at"] == br.json_value(later) for r in table.values())


def test_premarket_markers_per_run_and_coverage_are_two_checks(recompute_db, monkeypatch,
                                                               tmp_path):
    engine = recompute_db
    seed_premarket_world(engine, qqq_october_bars=False)
    assert run_fetcher(monkeypatch, tmp_path, "premarket-run-A", "--recompute-premarket",
                       "--from", "2026-09-29", "--to", "2026-09-30", "--commit") == 0
    assert run_fetcher(monkeypatch, tmp_path, "premarket-run-B", "--recompute-premarket",
                       *PREMARKET_WINDOW, "--commit") == 1

    table, _summary = read_report(tmp_path, "daily-premarket", "premarket-run-B")
    written = [r for r in table.values() if r["written"] == "true"]
    refused_or_left = {k for k, r in table.items() if r["status"] in br.REFUSED_STATUSES}

    # Per run.
    assert marker_count(engine, "market_data_daily", "pre_recompute_run",
                        "premarket-run-B") == len(written) == 2
    assert len(br.ledger_of_run("premarket-run-B", br.TARGET_PREMARKET)) == len(written)
    assert len(written) < len(table) == 8

    # Coverage.
    unmarked = daily_rows(engine, SELECTED_DAILY + " AND pre_recompute_run IS NULL")
    assert {(r["ticker"], r["date"].isoformat()) for r in unmarked} == refused_or_left
    assert refused_or_left == {("QQQ", "2026-10-05"), ("QQQ", "2026-10-06")}
    assert {table[k]["status"] for k in refused_or_left} == {"no_bars"}

    # Run A's rows were already current for B and keep A's id.
    assert marker_count(engine, "market_data_daily", "pre_recompute_run", "premarket-run-A") == 4


def test_revert_restores_the_eleven_columns(recompute_db, monkeypatch, tmp_path):
    engine = recompute_db
    seed_premarket_world(engine)
    # One row with every column set, a read time to the microsecond and a
    # stored number with more digits than a float holds.
    execute(engine, """
        UPDATE market_data_daily
           SET pre_fetched_at = '2026-10-06T13:31:00.123456+00:00', pre_excluded_stale_prints = 2,
               pre_excluded_spikes = 3, pre_filter_status = 'ok', pre_vwap = :vwap,
               pre_filter_params = CAST('{"atr": 1.23456789012345678901, "b": null}' AS JSONB)
         WHERE ticker = 'SPY' AND date = '2026-10-06'
    """, {"vwap": 0.1 + 0.2})
    before = {(r["ticker"], r["date"]): r for r in daily_rows(engine, SELECTED_DAILY)}
    assert before[("SPY", date(2026, 10, 6))]["pre_filter_params_text"] == \
        '{"b": null, "atr": 1.23456789012345678901}'

    assert run_fetcher(monkeypatch, tmp_path, "premarket-run-A", "--recompute-premarket",
                       *PREMARKET_WINDOW, "--commit") == 0
    after_run = daily_rows(engine, SELECTED_DAILY)
    assert {r["pre_recompute_run"] for r in after_run} == {"premarket-run-A"}

    # Dry: nothing is written.
    assert run_fetcher(monkeypatch, tmp_path, "revert-dry", "--revert-run",
                       "premarket-run-A") == 0
    assert daily_rows(engine, SELECTED_DAILY) == after_run
    table, _summary = read_report(tmp_path, "daily-premarket", "revert-dry")
    assert {r["status"] for r in table.values()} == {"would_revert"}

    # A later write changes one row; the revert leaves it.
    execute(engine, "UPDATE market_data_daily SET pre_low = 5.0 "
                    "WHERE ticker = 'QQQ' AND date = '2026-09-29'")

    assert run_fetcher(monkeypatch, tmp_path, "revert-1", "--revert-run", "premarket-run-A",
                       "--commit") == 1

    restored = {(r["ticker"], r["date"]): r for r in daily_rows(engine, SELECTED_DAILY)}
    for key, original in before.items():
        if key == ("QQQ", date(2026, 9, 29)):
            assert restored[key]["pre_low"] == 5.0
            assert restored[key]["pre_recompute_run"] == "premarket-run-A"
            continue
        assert differing(original, restored[key]) == {"pre_recompute_run", "updated_at"}, key
        assert restored[key]["pre_recompute_run"] == "revert-1"
    full = restored[("SPY", date(2026, 10, 6))]
    assert full["pre_fetched_at"] == utc("2026-10-06T13:31:00.123456")
    assert full["pre_vwap"] == 0.1 + 0.2
    assert full["pre_filter_params_text"] == '{"b": null, "atr": 1.23456789012345678901}'
    assert restored[("SPY", date(2026, 9, 29))]["pre_fetched_at"] is None
    assert restored[("SPY", date(2026, 9, 29))]["pre_range_atr"] == 0.4

    reverted = br.ledger_of_run("revert-1", br.TARGET_PREMARKET)
    assert len(reverted) == 7
    assert {h["action"] for h in reverted} == {"revert"}
    table, _summary = read_report(tmp_path, "daily-premarket", "revert-1")
    assert table[("QQQ", "2026-09-29")]["status"] == "changed_underneath"
    assert table[("SPY", "2026-10-06")]["status"] == "reverted"
    assert len(br.ledger_of_run("premarket-run-A", br.TARGET_PREMARKET)) == 8


# ── statement budgets (CLAUDE.md Rule 0) ──────────────────────────────
#
# One statement a table a group, whatever the number of rows. Every statement
# the engine sends between the start of main() and its return is recorded and
# split in two:
#
# - the tool's own statements: the schema check, the ledger read, the
#   selection, the reads and the writes. These are what the budget counts.
# - catalog probes. gcp.database.query_to_dataframe_strict reads through
#   pandas.read_sql, which first asks the catalog whether the SQL text is the
#   name of a table (has_table), so each strict read is two statements on the
#   wire. The probe is not the tools' statement and is the same for every
#   strict read in the repository, but it is a round trip, so each test pins
#   its count too: exactly one a read, and nothing else unaccounted.
#
# Run with -s to see the counts and the seconds.

import time as clock  # noqa: E402


def count_statements(engine, run) -> tuple[int, list, list, float]:
    """Run *run* and return its result, the tool's own statements, the
    catalog probes pandas sent before each read, and the seconds it took."""
    seen = []

    def record(conn, cursor, statement, parameters, context, executemany):
        seen.append((statement, executemany))

    sqlalchemy.event.listen(engine, "before_cursor_execute", record)
    started = clock.monotonic()
    try:
        result = run()
    finally:
        sqlalchemy.event.remove(engine, "before_cursor_execute", record)
    seconds = clock.monotonic() - started
    probes = [pair for pair in seen if "pg_catalog.pg_class" in pair[0]]
    own = [pair for pair in seen if "pg_catalog.pg_class" not in pair[0]]
    return result, own, probes, seconds


BUDGET_SESSIONS = [date(2026, 10, d) for d in (5, 6, 7, 8, 9, 12, 13, 14, 15)]


def test_exits_statement_budget(recompute_db, monkeypatch, tmp_path):
    engine = recompute_db
    groups = [(ticker, day) for day in BUDGET_SESSIONS for ticker in ("SPY", "QQQ", "IWM")]
    assert len(groups) == 27
    total = 0
    for i, (ticker, day) in enumerate(groups):
        seed_bars(engine, ticker, day, 100.0)
        alerts = 34 if i < 9 else 33
        total += alerts
        # Alerts a minute apart from 10:00:00.5 Eastern, each stored with a
        # whole-minute exit the bars do not give.
        first = eastern_bounds_utc(day, time(10), time(10))[0] + timedelta(milliseconds=500)
        seeded = {"ticker": ticker, "first": first, "n": alerts - 1, "day": day}
        execute(engine, """
            INSERT INTO signal_alerts (ticker, alert_ts, alert_date, direction, price_at_signal,
                                       target_price, time_stop_minutes, exit_ts, exit_reason,
                                       exit_price, exit_return_pct, is_open, run_kind)
            SELECT :ticker, CAST(:first AS TIMESTAMPTZ) + g * INTERVAL '1 minute', :day, 'CALL',
                   100.0, 110.0, 30,
                   date_trunc('minute', CAST(:first AS TIMESTAMPTZ)) + (g + 45) * INTERVAL '1 minute',
                   'time_stop', 1.0, -99.0, FALSE, 'live'
              FROM generate_series(0, :n) AS g
        """, seeded)
        execute(engine, """
            INSERT INTO trades (ticker, direction, entry_time, entry_price, exit_time,
                                exit_price, exit_reason, return_pct, trade_date, run_kind)
            SELECT :ticker, 'CALL', CAST(:first AS TIMESTAMPTZ) + g * INTERVAL '1 minute', 100.0,
                   date_trunc('minute', CAST(:first AS TIMESTAMPTZ)) + (g + 45) * INTERVAL '1 minute',
                   1.0, 'time_stop', -99.0, :day, 'live'
              FROM generate_series(0, :n) AS g
        """, seeded)
    assert total == 900

    code, seen, probes, seconds = count_statements(engine, lambda: run_resolver(
        monkeypatch, tmp_path, "exits-budget", "--re-resolve",
        "--from", "2026-10-05", "--to", "2026-10-15", "--commit"))

    print(f"\nexits budget: {len(seen)} statements of the tool, {len(probes)} catalog probes "
          f"({len(seen) + len(probes)} on the wire), {seconds:.2f} s, 900 alerts, 27 groups")
    assert code == 0
    assert marker_count(engine, "signal_alerts", "exit_recompute_run", "exits-budget") == 900
    assert marker_count(engine, "trades", "exit_recompute_run", "exits-budget") == 900
    assert len(br.ledger_of_run("exits-budget", br.TARGET_EXITS)) == 900
    assert not any(many for _statement, many in seen)
    assert len(seen) < 120
    # 1 schema check, 1 ledger read, 1 selection, 27 day reads, 3 a written group.
    assert len(seen) == 1 + 1 + 1 + 27 + 3 * 27 == 111
    updates = [s for s, _many in seen if s.lstrip().startswith("UPDATE")]
    assert len(updates) == 54  # one a table a group
    assert len(probes) == 1 + 1 + 1 + 27  # one a strict read


def test_premarket_statement_budget(recompute_db, monkeypatch, tmp_path):
    engine = recompute_db
    for ticker in ("SPY", "QQQ", "IWM"):
        seed_daily(engine, ticker, date(2025, 5, 1), date(2026, 10, 30))
    # 150 sessions over 8 months: the first 19 weekdays of March to August and
    # the first 18 of September and October, for each of the three tickers.
    execute(engine, """
        UPDATE market_data_daily AS d
           SET pre_high = 100.25, pre_low = 99.75, pre_vwap = 100.01, pre_volume = 300000,
               gap_pct = 0.9
          FROM (SELECT ticker, date, extract(month FROM date) AS month_no,
                       row_number() OVER (PARTITION BY ticker, extract(month FROM date)
                                          ORDER BY date) AS n
                  FROM market_data_daily
                 WHERE date >= '2026-03-01' AND date <= '2026-10-30') AS s
         WHERE d.ticker = s.ticker AND d.date = s.date
           AND s.n <= CASE WHEN s.month_no >= 9 THEN 18 ELSE 19 END
    """)
    assert len(daily_rows(engine, "pre_high IS NOT NULL")) == 450
    # Every selected session's premarket bars, one statement a ticker.
    for ticker in ("SPY", "QQQ", "IWM"):
        execute(engine, """
            INSERT INTO market_data_intraday (ticker, interval, ts, open, high, low, close, volume)
            SELECT :ticker, '1min',
                   ((CAST(s.date AS TIMESTAMP) + INTERVAL '4 hours') AT TIME ZONE 'America/New_York')
                       + m * INTERVAL '1 minute',
                   100.0, 100.5, 99.5, 100.0, 1000
              FROM market_data_daily AS s CROSS JOIN generate_series(0, 329) AS m
             WHERE s.ticker = :ticker AND s.pre_high IS NOT NULL
        """, {"ticker": ticker})

    code, seen, probes, seconds = count_statements(engine, lambda: run_fetcher(
        monkeypatch, tmp_path, "premarket-budget", "--recompute-premarket",
        "--from", "2026-03-01", "--to", "2026-10-30", "--commit"))

    print(f"\npremarket budget: {len(seen)} statements of the tool, {len(probes)} catalog "
          f"probes ({len(seen) + len(probes)} on the wire), {seconds:.2f} s, 450 rows, "
          "24 groups")
    assert code == 0
    assert marker_count(engine, "market_data_daily", "pre_recompute_run", "premarket-budget") == 450
    assert len(br.ledger_of_run("premarket-budget", br.TARGET_PREMARKET)) == 450
    assert not any(many for _statement, many in seen)
    assert len(seen) < 240
    # 1 schema check, 1 ledger read, 1 selection, 3 daily reads, 24 month
    # reads, 150 parameter reads (one a distinct session date), 2 a written group.
    assert len(seen) == 1 + 1 + 1 + 3 + 24 + 150 + 2 * 24 == 228
    updates = [s for s, _many in seen if s.lstrip().startswith("UPDATE")]
    assert len(updates) == 24  # one a group
    assert len(probes) == 1 + 1 + 1 + 3 + 24 + 150  # one a strict read


def test_the_premarket_bar_read_scans_one_index_range_a_window(recompute_db):
    """EXPLAIN of the statement the tool sends, on Postgres: the windows are
    the outer side of a nested loop and the bars are an index scan run once a
    window, so the rows read are the rows returned. The table also holds a
    year of other bars the read must not visit."""
    from gcp.fetchers import fetch_market_data as fmd

    engine = recompute_db
    sessions = [d for d in (date(2026, 10, 1) + timedelta(days=n) for n in range(30))
                if d.weekday() < 5]
    assert len(sessions) == 22
    for day in sessions:
        seed_premarket_bars(engine, "SPY", day)
    execute(engine, """
        INSERT INTO market_data_intraday (ticker, interval, ts, open, high, low, close, volume)
        SELECT 'SPY', '1min', g, 1.0, 1.0, 1.0, 1.0, 1
          FROM generate_series(CAST('2025-06-02T14:00:00+00:00' AS TIMESTAMPTZ),
                               CAST('2026-06-01T14:00:00+00:00' AS TIMESTAMPTZ),
                               INTERVAL '2 minutes') AS g
    """)
    execute(engine, "ANALYZE market_data_intraday")

    bind = {"t": "SPY"}
    for i, day in enumerate(sessions):
        bind[f"s{i}"], bind[f"e{i}"] = eastern_bounds_utc(day, time(4), time(9, 30))
    with engine.connect() as conn:
        plan = conn.execute(sqlalchemy.text(
            "EXPLAIN (ANALYZE, FORMAT JSON) " + fmd.premarket_bars_sql(len(sessions))),
            bind).scalar_one()
    if isinstance(plan, str):
        plan = json.loads(plan)

    def nodes(node):
        yield node
        for child in node.get("Plans", []):
            yield from nodes(child)

    every = list(nodes(plan[0]["Plan"]))
    returned = plan[0]["Plan"]["Actual Rows"]
    assert returned == 22 * 330
    scans = [n for n in every if n.get("Relation Name", "").startswith("market_data_intraday")]
    assert len(scans) == 1
    scan = scans[0]
    assert scan["Node Type"] in ("Index Scan", "Index Only Scan")
    assert scan["Actual Loops"] == 22            # a loop a window
    assert scan["Actual Rows"] == 330            # the rows of one window, each loop
    assert scan.get("Rows Removed by Filter", 0) == 0
    assert not any("Rows Removed by Join Filter" in n and n["Rows Removed by Join Filter"]
                   for n in every)
