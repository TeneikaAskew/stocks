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
