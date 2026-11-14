"""--re-resolve on the end-of-day resolver (FEAT-DATA-001): the bounded force
mode that re-resolves closed alerts from proven 1-minute bars.

Hermetic. `gcp.database.query_to_dataframe_strict` and
`gcp.database.get_engine` raise unless a test installs an answer, so a query
or a transaction a test did not expect fails it.
"""
from __future__ import annotations

import logging
import sys
from datetime import date

import pandas as pd
import pytest

import gcp.database as database
import gcp.signal_monitor_eod_resolver as resolver_module
from gcp import bar_recompute as br
from gcp.signal_monitor_eod_resolver import EODResolver

TODAY = date(2026, 11, 14)

SELECTION_COLUMNS = [
    "ticker", "alert_ts", "alert_date", "direction", "price_at_signal", "target_price",
    "time_stop_minutes", "exit_ts", "exit_reason", "exit_price", "exit_return_pct",
    "exit_recompute_run", "trade_found", "trade_exit_time", "trade_exit_price",
    "trade_exit_reason", "trade_return_pct", "trade_exit_recompute_run",
]


def _collapse(text: str) -> str:
    return " ".join(text.split())


@pytest.fixture(autouse=True)
def hermetic(monkeypatch):
    """No query, no transaction, no HTTP request and no bucket unless a test
    says otherwise; today's Eastern date is fixed."""

    def no_query(*_args, **_kwargs):
        raise AssertionError("an unexpected query")

    def no_engine(*_args, **_kwargs):
        raise AssertionError("an unexpected transaction")

    def no_http(*_args, **_kwargs):
        raise AssertionError("an unexpected HTTP request")

    monkeypatch.setattr(database, "query_to_dataframe_strict", no_query)
    monkeypatch.setattr(database, "query_to_dataframe", no_query)
    monkeypatch.setattr(database, "get_engine", no_engine)
    monkeypatch.setattr(resolver_module.requests, "post", no_http)
    monkeypatch.setattr(resolver_module, "market_today", lambda: TODAY)
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    monkeypatch.delenv("CLOUD_RUN_EXECUTION", raising=False)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("DISCORD_WEBHOOK_SIGNALS_URL", raising=False)


def run_main(monkeypatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["signal_monitor_eod_resolver", *argv])
    return resolver_module.main()


class Reader:
    """A strict reader that answers by SQL text and records each call."""

    def __init__(self, answers):
        self.answers = answers
        self.calls: list[tuple[str, dict | None]] = []

    def __call__(self, sql, params=None, timeout_s=None):
        assert timeout_s is None
        self.calls.append((sql, params))
        for marker, answer in self.answers:
            if marker in sql:
                return answer(sql, params) if callable(answer) else answer
        raise AssertionError(f"no answer for: {_collapse(sql)[:120]}")

    def of(self, marker: str) -> list[tuple[str, dict | None]]:
        return [call for call in self.calls if marker in call[0]]


def schema_ready(_sql=None, _params=None) -> pd.DataFrame:
    return pd.DataFrame({
        "table_name": ["bar_recompute_ledger", "signal_alerts", "trades", "market_data_daily"],
        "column_name": ["run_id", "exit_recompute_run", "exit_recompute_run",
                        "pre_recompute_run"],
    })


def no_alerts(_sql=None, _params=None) -> pd.DataFrame:
    return pd.DataFrame(columns=SELECTION_COLUMNS)


# ── selection ─────────────────────────────────────────────────────────


def test_selection_is_one_strict_query(monkeypatch):
    answer = pd.DataFrame({"ticker": ["SPY"], "alert_ts": [pd.Timestamp("2026-05-01", tz="UTC")]})
    reader = Reader([("FROM signal_alerts", answer)])
    monkeypatch.setattr(database, "query_to_dataframe_strict", reader)

    found = EODResolver().find_resolved_alerts(["SPY", "QQQ"], date(2026, 5, 1), date(2026, 5, 8))

    assert found is answer
    assert len(reader.calls) == 1
    sql, params = reader.calls[0]
    text = _collapse(sql)
    for fragment in (
        "a.run_kind = 'live'",
        "a.is_open IS FALSE",
        "a.exit_ts IS NOT NULL",
        "a.exit_ts = date_trunc('minute', a.exit_ts)",
        "a.ticker = ANY(:tickers)",
        "a.alert_date >= :first AND a.alert_date <= :last",
        "t.run_kind = 'live'",
        "LEFT JOIN trades t ON t.ticker = a.ticker AND t.entry_time = a.alert_ts",
        "ORDER BY a.alert_date, a.ticker, a.alert_ts",
    ):
        assert fragment in text, fragment
    assert params == {"tickers": ["SPY", "QQQ"], "first": date(2026, 5, 1),
                      "last": date(2026, 5, 8)}


def test_default_tickers_are_the_three(monkeypatch, tmp_path):
    reader = Reader([("information_schema.columns", schema_ready),
                     ("FROM signal_alerts", no_alerts)])
    monkeypatch.setattr(database, "query_to_dataframe_strict", reader)

    code = run_main(monkeypatch, "--re-resolve", "--from", "2026-10-01", "--to", "2026-10-06",
                    "--report-dir", str(tmp_path))

    assert code == 0
    (_sql, params), = reader.of("FROM signal_alerts")
    assert params == {"tickers": ["SPY", "QQQ", "IWM"], "first": date(2026, 10, 1),
                      "last": date(2026, 10, 6)}


# ── refused before any query ──────────────────────────────────────────

WINDOW = ("--from", "2026-10-01", "--to", "2026-10-06")

REFUSED = {
    "another ticker": ("--re-resolve", *WINDOW, "--tickers", "SPY AMD"),
    "a comma in --tickers": ("--re-resolve", *WINDOW, "--tickers", "SPY,QQQ"),
    "no --from": ("--re-resolve", "--to", "2026-10-06"),
    "no --to": ("--re-resolve", "--from", "2026-10-01"),
    "--from after --to": ("--re-resolve", "--from", "2026-10-07", "--to", "2026-10-06"),
    "--to today": ("--re-resolve", "--from", "2026-10-01", "--to", "2026-11-14"),
    "--to after today": ("--re-resolve", "--from", "2026-10-01", "--to", "2026-11-17"),
    "a malformed date": ("--re-resolve", "--from", "2026-5-1x", "--to", "2026-10-06"),
    "with --since": ("--re-resolve", *WINDOW, "--since", "2026-05-01"),
    "with --backfill": ("--re-resolve", *WINDOW, "--backfill"),
    "with --revert-run": ("--re-resolve", *WINDOW, "--revert-run", "x"),
    "--commit alone": ("--commit",),
    "--from alone": ("--from", "2026-10-01"),
    "--tickers alone": ("--tickers", "SPY"),
    "--report-dir alone": ("--report-dir", "somewhere"),
    "--revert-run with a window": ("--revert-run", "x", *WINDOW),
    "--revert-run with --tickers": ("--revert-run", "x", "--tickers", "SPY"),
}


@pytest.mark.parametrize("argv", list(REFUSED.values()), ids=list(REFUSED))
def test_refused_before_any_query(monkeypatch, tmp_path, caplog, argv):
    if "--report-dir" not in argv:
        argv = (*argv, "--report-dir", str(tmp_path))
    with caplog.at_level(logging.ERROR):
        assert run_main(monkeypatch, *argv) == 2
    refusals = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(refusals) == 1
    assert "\n" not in refusals[0].getMessage()


@pytest.mark.parametrize("direction", ["call_exit_mode", "put_exit_mode"])
def test_an_exit_mode_other_than_target_stop_is_refused(monkeypatch, tmp_path, direction):
    from lib.config import load_config

    config = load_config()
    setattr(config.exit, direction, "fixed_horizon")
    monkeypatch.setattr(resolver_module, "load_config", lambda *a, **k: config)
    assert run_main(monkeypatch, "--re-resolve", *WINDOW, "--report-dir", str(tmp_path)) == 2


def test_no_report_destination_is_refused(monkeypatch):
    assert run_main(monkeypatch, "--re-resolve", *WINDOW) == 2
    assert run_main(monkeypatch, "--revert-run", "run-1") == 2


def test_a_missing_ledger_or_marker_is_exit_two(monkeypatch, tmp_path, caplog):
    def forbidden(*_a, **_k):
        raise AssertionError("the selection must not be reached")

    monkeypatch.setattr(br, "schema_missing", lambda: ["bar_recompute_ledger"])
    monkeypatch.setattr(EODResolver, "find_resolved_alerts", forbidden)
    base = ("--re-resolve", *WINDOW, "--report-dir", str(tmp_path))
    with caplog.at_level(logging.ERROR):
        assert run_main(monkeypatch, *base) == 2
        assert run_main(monkeypatch, *base, "--commit") == 2
        assert run_main(monkeypatch, "--revert-run", "run-1", "--report-dir", str(tmp_path)) == 2
    assert "bar_recompute_ledger" in caplog.text


# ── the scheduled path ────────────────────────────────────────────────

# The text find_open_alerts sent on main before this change
# (gcp/signal_monitor_eod_resolver.py:139-151 at 58d96807), whitespace collapsed.
OPEN_ALERTS_SQL_WITH_SINCE = (
    "SELECT ticker, alert_ts, alert_date, direction, "
    "price_at_signal, target_price, time_stop_minutes "
    "FROM signal_alerts "
    "WHERE (is_open IS TRUE OR exit_ts IS NULL) "
    "AND run_kind = 'live' "
    "AND alert_date <= CURRENT_DATE "
    "AND alert_date >= :since "
    "ORDER BY alert_date, ticker, alert_ts"
)


def test_the_scheduled_path_is_untouched(monkeypatch):
    seen = []

    def run(self, since=None):
        seen.append(since)
        return {"skipped_stale": 0}

    monkeypatch.setattr(EODResolver, "run", run)
    assert run_main(monkeypatch) == 0
    assert run_main(monkeypatch, "--since", "2026-04-01") == 0
    assert run_main(monkeypatch, "--backfill") == 0
    assert seen == [None, "2026-04-01", None]

    monkeypatch.setattr(EODResolver, "run", lambda self, since=None: {"skipped_stale": 2})
    assert run_main(monkeypatch) == 1

    sent = []

    def swallowing(sql, params=None):
        sent.append((sql, params))
        return pd.DataFrame()

    monkeypatch.setattr(database, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(database, "query_to_dataframe", swallowing)
    EODResolver().find_open_alerts(since="2026-04-01")
    (sql, params), = sent
    assert _collapse(sql) == OPEN_ALERTS_SQL_WITH_SINCE
    assert params == {"since": "2026-04-01"}


# ── the proof-requiring day read and the dry run ──────────────────────
#
# Two tickers, two sessions. Bars: one a minute from 04:00 to 19:59 Eastern,
# close base + 0.02 on odd minutes and base on even ones, open, high and low
# equal to the close, volume 1000.

import csv  # noqa: E402
import json  # noqa: E402
from datetime import datetime, time, timezone  # noqa: E402

UTC = timezone.utc
RUN_ID = "eod-resolver-test1"


def session_bars(day: date, base: float, inserted: str, *, last_et: str = "19:59",
                 one_inserted: str | None = None) -> pd.DataFrame:
    from lib.eastern_time import eastern_bounds_utc

    start, end = eastern_bounds_utc(day, time(4), time.fromisoformat(last_et))
    ts = pd.date_range(start, end, freq="1min")
    close = [round(base + 0.02, 2) if stamp.minute % 2 else base for stamp in ts]
    inserted_at = [pd.Timestamp(inserted, tz="UTC")] * len(ts)
    if one_inserted is not None:
        inserted_at[100] = pd.Timestamp(one_inserted, tz="UTC")
    return pd.DataFrame({
        "ts": ts, "open": close, "high": close, "low": close, "close": close,
        "volume": 1000, "inserted_at": inserted_at,
    })


def stored_bars() -> dict:
    return {
        ("SPY", date(2026, 10, 6)): session_bars(date(2026, 10, 6), 100.0, "2026-10-07"),
        ("SPY", date(2026, 9, 24)): session_bars(date(2026, 9, 24), 101.0, "2026-11-14"),
        ("QQQ", date(2026, 9, 24)): session_bars(
            date(2026, 9, 24), 101.0, "2026-11-14", one_inserted="2026-09-24 21:00"),
    }


def alert(ticker, alert_ts, direction, entry, target, stop, exit_ts, reason, price, ret,
          **overrides) -> dict:
    stamp = pd.Timestamp(alert_ts, tz="UTC")
    exit_stamp = pd.Timestamp(exit_ts, tz="UTC")
    record = {
        "ticker": ticker, "alert_ts": stamp, "alert_date": stamp.date(),
        "direction": direction, "price_at_signal": entry, "target_price": target,
        "time_stop_minutes": stop, "exit_ts": exit_stamp, "exit_reason": reason,
        "exit_price": price, "exit_return_pct": ret, "exit_recompute_run": None,
        "trade_found": True, "trade_exit_time": exit_stamp, "trade_exit_price": price,
        "trade_exit_reason": reason, "trade_return_pct": ret,
        "trade_exit_recompute_run": None,
    }
    record.update(overrides)
    return record


def stored_alerts() -> list[dict]:
    return [
        alert("QQQ", "2026-09-24 14:10:03.000004", "CALL", 101.0, 111.0, 30,
              "2026-09-24 14:41:00", "time_stop", 101.0, 0.0),
        alert("QQQ", "2026-09-24 15:10:03.000004", "PUT", 101.0, 91.0, 30,
              "2026-09-24 15:41:00", "time_stop", 101.0, 0.0),
        alert("SPY", "2026-09-24 15:00:01.000001", "CALL", 101.0, 101.02, 30,
              "2026-09-24 15:03:00", "target_hit", 101.5, 0.495),
        alert("QQQ", "2026-10-06 14:10:03.000004", "CALL", 100.0, 110.0, 30,
              "2026-10-06 14:41:00", "time_stop", 100.0, 0.0),
        alert("SPY", "2026-10-06 14:00:07.500000", "PUT", 100.0, 90.0, 30,
              "2026-10-06 14:31:00", "time_stop", 100.02, -0.01999999999999602),
        alert("SPY", "2026-10-06 19:50:00.250000", "CALL", 100.0, 110.0, 30,
              "2026-10-06 20:20:00", "time_stop", 100.0, 0.0),
    ]


# rows.csv, as text: ticker, session date, alert_ts, the four old exit values,
# the four new ones, changed, status, the bars' row count and sha256, written.
SPY_1006_SHA = "3d0abb76f18fbe6f4401b4755e9d06a23a2813bf21473f3fde530285e1042f60"
SPY_0924_SHA = "3cb85aabdeeeef0d9fa28cc67439231f9d2e0f02edf58432bb22dcc7fa24d344"

EXPECTED_ROWS = [
    ["QQQ", "2026-09-24", "2026-09-24T14:10:03.000004+00:00",
     "2026-09-24T14:41:00.000000+00:00", "time_stop", "101.0", "0.0",
     "", "", "", "", "", "unproven_rows", "", "", "false"],
    ["QQQ", "2026-09-24", "2026-09-24T15:10:03.000004+00:00",
     "2026-09-24T15:41:00.000000+00:00", "time_stop", "101.0", "0.0",
     "", "", "", "", "", "unproven_rows", "", "", "false"],
    ["SPY", "2026-09-24", "2026-09-24T15:00:01.000001+00:00",
     "2026-09-24T15:03:00.000000+00:00", "target_hit", "101.5", "0.495",
     "2026-09-24T15:01:00.000000+00:00", "target_hit", "101.02", "0.01980198019801586",
     "true", "recomputed", "960", SPY_0924_SHA, "false"],
    ["QQQ", "2026-10-06", "2026-10-06T14:10:03.000004+00:00",
     "2026-10-06T14:41:00.000000+00:00", "time_stop", "100.0", "0.0",
     "", "", "", "", "", "no_bars", "", "", "false"],
    ["SPY", "2026-10-06", "2026-10-06T14:00:07.500000+00:00",
     "2026-10-06T14:31:00.000000+00:00", "time_stop", "100.02", "-0.01999999999999602",
     "2026-10-06T14:31:00.000000+00:00", "time_stop", "100.02", "-0.01999999999999602",
     "false", "recomputed", "960", SPY_1006_SHA, "false"],
    ["SPY", "2026-10-06", "2026-10-06T19:50:00.250000+00:00",
     "2026-10-06T20:20:00.000000+00:00", "time_stop", "100.0", "0.0",
     "2026-10-06T20:00:00.000000+00:00", "eod_close", "100.02", "0.01999999999999602",
     "true", "recomputed", "960", SPY_1006_SHA, "false"],
]

CSV_HEADER = [
    "ticker", "session_date", "row_key", "old_exit_ts", "old_exit_reason", "old_exit_price",
    "old_exit_return_pct", "new_exit_ts", "new_exit_reason", "new_exit_price",
    "new_exit_return_pct", "changed", "status", "bars_rows", "bars_sha256", "written",
]


def exits_reader(alerts: list[dict] | None = None, bars: dict | None = None) -> Reader:
    """The strict reader of a run: the schema check, the selection (filtered by
    the bound tickers and window) and the day read (filtered by the bound
    ticker and instants)."""
    alerts = stored_alerts() if alerts is None else alerts
    bars = stored_bars() if bars is None else bars

    def selection(_sql, params):
        chosen = [a for a in alerts
                  if a["ticker"] in params["tickers"]
                  and params["first"] <= a["alert_date"] <= params["last"]]
        if not chosen:
            return pd.DataFrame(columns=SELECTION_COLUMNS)
        return pd.DataFrame(chosen, columns=SELECTION_COLUMNS)

    def day_read(_sql, params):
        frames = [frame for (ticker, _day), frame in bars.items() if ticker == params["t"]]
        empty = pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume",
                                      "inserted_at"])
        if not frames:
            return empty
        every = pd.concat(frames, ignore_index=True)
        inside = every[(every["ts"] >= params["start"]) & (every["ts"] < params["end"])]
        return inside.sort_values("ts").reset_index(drop=True) if len(inside) else empty

    return Reader([("information_schema.columns", schema_ready),
                   ("FROM signal_alerts", selection),
                   ("FROM market_data_intraday", day_read)])


class NoTransactionEngine:
    def begin(self):
        raise AssertionError("a dry run entered a transaction")

    def connect(self):
        raise AssertionError("a dry run opened a connection")


def dry_run(monkeypatch, tmp_path, reader, *extra: str,
            window=("--from", "2026-09-24", "--to", "2026-10-06")) -> int:
    monkeypatch.setattr(database, "query_to_dataframe_strict", reader)
    monkeypatch.setattr(database, "get_engine", lambda: NoTransactionEngine())
    monkeypatch.setenv("CLOUD_RUN_EXECUTION", RUN_ID)
    return run_main(monkeypatch, "--re-resolve", *window, "--report-dir", str(tmp_path), *extra)


def report(tmp_path, run_id: str = RUN_ID):
    folder = tmp_path / "bar-recompute" / "v1" / "signal-alert-exits" / run_id
    with open(folder / "rows.csv", newline="") as handle:
        table = list(csv.reader(handle))
    return table, json.loads((folder / "summary.json").read_text())


def test_the_dry_run_report_equals_the_expected_table(monkeypatch, tmp_path, caplog):
    reader = exits_reader()
    with caplog.at_level(logging.INFO):
        code = dry_run(monkeypatch, tmp_path, reader, "--tickers", "SPY QQQ")

    assert code == 1  # QQQ rows were refused
    table, summary = report(tmp_path)
    assert table[0] == CSV_HEADER
    assert table[1:] == EXPECTED_ROWS

    assert summary["run_id"] == RUN_ID
    assert summary["counts"] == {
        "QQQ": {"2026-09-24": {"unproven_rows": 2}, "2026-10-06": {"no_bars": 1}},
        "SPY": {"2026-09-24": {"recomputed": 1}, "2026-10-06": {"recomputed": 2}},
    }
    assert summary["totals"] == {"unproven_rows": 2, "no_bars": 1, "recomputed": 3}
    assert summary["written"] == 0
    assert summary["outcomes"]["SPY"]["wins_before"] == 1
    assert summary["outcomes"]["SPY"]["wins_after"] == 2
    assert summary["outcomes"]["SPY"]["alerts"] == 3
    assert summary["outcomes"]["QQQ"]["wins_before"] == summary["outcomes"]["QQQ"]["wins_after"] == 0
    assert summary["outcomes"]["all"]["alerts"] == 6
    assert summary["configuration"] == {
        "call_exit_mode": "target_stop", "put_exit_mode": "target_stop", "rsi_period": 14,
        "call_rsi_exit": 80.0, "put_rsi_exit": 20.0}
    assert summary["arguments"] == {
        "tickers": ["SPY", "QQQ"], "from": "2026-09-24", "to": "2026-10-06", "commit": False}
    assert set(summary["code_version"]) == {"git_commit", "git_dirty", "built_at"}

    assert "RECOMPUTE-EXITS SPY 2026-10-06 candidates=2 changed=1 unchanged=1 refused=0" in caplog.text
    assert "RECOMPUTE-EXITS QQQ 2026-09-24 candidates=2 changed=0 unchanged=0 refused=2" in caplog.text

    # One bar read a (ticker, date), each bounded to that Eastern day.
    from lib.eastern_time import eastern_bounds_utc

    day_reads = reader.of("FROM market_data_intraday")
    assert len(day_reads) == 4
    seen = set()
    for sql, params in day_reads:
        text = _collapse(sql)
        assert "interval = '1min'" in text
        assert "inserted_at" in text
        assert "ts >= :start AND ts < :end" in text
        day = params["start"].astimezone(resolver_module.ET).date()
        assert params["start"] == eastern_bounds_utc(day, time(0), time(0))[0]
        assert (params["end"] - params["start"]).total_seconds() == 24 * 3600
        seen.add((params["t"], day))
    assert seen == {("QQQ", date(2026, 9, 24)), ("SPY", date(2026, 9, 24)),
                    ("QQQ", date(2026, 10, 6)), ("SPY", date(2026, 10, 6))}
    assert len(reader.of("FROM signal_alerts")) == 1


def test_a_run_that_refuses_no_row_is_exit_zero(monkeypatch, tmp_path):
    reader = exits_reader()
    assert dry_run(monkeypatch, tmp_path, reader, "--tickers", "SPY") == 0
    table, summary = report(tmp_path)
    assert [line[0] for line in table[1:]] == ["SPY", "SPY", "SPY"]
    assert summary["totals"] == {"recomputed": 3}


def test_the_force_frame_equals_the_scheduled_frame(monkeypatch):
    day = date(2026, 10, 6)
    bars = stored_bars()[("SPY", day)]

    def both(sql, params=None, timeout_s=None):
        inside = bars[(bars["ts"] >= params["start"]) & (bars["ts"] <= params["end"])]
        if 'AS "Open"' in sql:  # the loader's read
            return inside.rename(columns={
                "open": "Open", "high": "High", "low": "Low", "close": "Close",
                "volume": "Volume"})[["ts", "Open", "High", "Low", "Close", "Volume"]]
        assert "inserted_at" in sql
        return bars[(bars["ts"] >= params["start"]) & (bars["ts"] < params["end"])]

    monkeypatch.setenv("CLOUD_SQL_CONNECTION_NAME", "project:region:instance")
    monkeypatch.setattr(database, "query_to_dataframe_strict", both)
    resolver = EODResolver()

    scheduled = resolver._load_day("SPY", day)
    forced = resolver.day_frame(resolver.read_day_bars("SPY", day))

    assert scheduled.shape == (960, 6)
    pd.testing.assert_frame_equal(scheduled, forced)


def test_a_naive_stored_time_is_not_localized(monkeypatch):
    raw = stored_bars()[("SPY", date(2026, 10, 6))].copy()
    raw["ts"] = raw["ts"].dt.tz_convert(None)
    with pytest.raises(TypeError):
        EODResolver().day_frame(raw)


def test_each_alert_goes_through_resolve_one(monkeypatch, tmp_path):
    calls = []
    real = EODResolver.resolve_one

    def recording(self, alert_row, bars=None):
        calls.append((alert_row["ticker"], bars is not None))
        return real(self, alert_row, bars=bars)

    class NoLoader:
        def __getattr__(self, name):
            raise AssertionError(f"the loader was used: {name}")

    def unloaded(*_a, **_k):
        return NoLoader()

    monkeypatch.setattr(EODResolver, "resolve_one", recording)
    monkeypatch.setattr(resolver_module, "DataLoader", unloaded)
    assert dry_run(monkeypatch, tmp_path, exits_reader(), "--tickers", "SPY QQQ") == 1
    # Three alerts in the two proven groups; the refused groups resolve nothing.
    assert calls == [("SPY", True), ("SPY", True), ("SPY", True)]


def test_an_unchanged_exit_is_not_a_change(monkeypatch, tmp_path):
    captured = {}
    real = br.finish_run

    def capture(**kwargs):
        captured.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(br, "finish_run", capture)
    assert dry_run(monkeypatch, tmp_path, exits_reader(), "--tickers", "SPY") == 0

    units = [u for _label, group in captured["groups"] for u in group]
    unchanged = next(u for u in units if u.row_key == "2026-10-06T14:00:07.500000+00:00")
    assert unchanged.changed is False
    assert unchanged.primary.new["exit_ts"].tzinfo is not None
    assert unchanged.primary.new["exit_ts"] == datetime(2026, 10, 6, 14, 31, tzinfo=UTC)
    assert unchanged.follower is not None
    assert unchanged.follower.new["exit_time"] == unchanged.primary.new["exit_ts"]
    assert captured["commit"] is False
    assert set(unchanged.basis) == {"bars", "code", "configuration"}
    assert unchanged.basis["bars"]["sha256"] == SPY_1006_SHA

    # Equal values with a marker already set: nothing to write.
    marked = [dict(a, exit_recompute_run="earlier-run", trade_exit_recompute_run="earlier-run")
              for a in stored_alerts()]
    captured.clear()
    assert dry_run(monkeypatch, tmp_path, exits_reader(alerts=marked), "--tickers", "SPY") == 0
    by_key = {row.row_key: row for row in captured["rows"]}
    assert by_key["2026-10-06T14:00:07.500000+00:00"].status == "already_current"
    assert by_key["2026-10-06T19:50:00.250000+00:00"].status == "recomputed"
    written_keys = {u.row_key for _label, group in captured["groups"] for u in group}
    assert "2026-10-06T14:00:07.500000+00:00" not in written_keys


def test_a_trade_that_is_missing_or_not_the_mirror(monkeypatch, tmp_path):
    alerts = stored_alerts()
    missing = dict(alerts[4], trade_found=False, trade_exit_time=pd.NaT,
                   trade_exit_price=float("nan"), trade_exit_reason=None,
                   trade_return_pct=float("nan"))
    diverged = dict(alerts[5], trade_exit_price=99.0)
    captured = {}
    real = br.finish_run

    def capture(**kwargs):
        captured.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(br, "finish_run", capture)
    code = dry_run(monkeypatch, tmp_path, exits_reader(alerts=[alerts[2], missing, diverged]),
                   "--tickers", "SPY")
    assert code == 1  # a diverged trade is left
    statuses = {row.row_key: row.status for row in captured["rows"]}
    assert statuses == {
        "2026-09-24T15:00:01.000001+00:00": "recomputed",
        "2026-10-06T14:00:07.500000+00:00": "trade_missing",
        "2026-10-06T19:50:00.250000+00:00": "trade_diverged",
    }
    units = {u.row_key: u for _label, group in captured["groups"] for u in group}
    assert units["2026-10-06T14:00:07.500000+00:00"].follower is None
    assert units["2026-10-06T19:50:00.250000+00:00"].follower is None
    assert units["2026-09-24T15:00:01.000001+00:00"].follower is not None


@pytest.mark.parametrize("column", ["price_at_signal", "target_price", "direction",
                                    "time_stop_minutes"])
def test_a_null_input_raises_naming_the_alert(monkeypatch, tmp_path, column):
    alerts = stored_alerts()
    alerts[5] = dict(alerts[5], **{column: None})
    frame = pd.DataFrame(alerts, columns=SELECTION_COLUMNS)
    if column != "direction":
        # As pandas returns it: NaN beside the other rows' numbers.
        assert frame[column].isna().sum() == 1 and frame[column].dtype == "float64"
    with pytest.raises(ValueError) as caught:
        dry_run(monkeypatch, tmp_path, exits_reader(alerts=alerts), "--tickers", "SPY")
    message = str(caught.value)
    assert "SPY" in message
    assert "2026-10-06T19:50:00.250000+00:00" in message
    assert column in message


def test_bars_that_stop_early_are_bars_incomplete(monkeypatch, tmp_path):
    day = date(2026, 10, 6)
    bars = {("SPY", day): session_bars(day, 100.0, "2026-10-07", last_et="15:40")}
    quiet = alert("SPY", "2026-10-06 19:30:07.000001", "CALL", 100.0, 110.0, 600,
                  "2026-10-06 20:00:00", "eod_close", 100.2, 0.2)
    code = dry_run(monkeypatch, tmp_path, exits_reader(alerts=[quiet], bars=bars),
                   "--tickers", "SPY", window=("--from", "2026-10-06", "--to", "2026-10-06"))
    assert code == 1
    table, summary = report(tmp_path)
    assert table[1][7:13] == ["", "", "", "", "", "bars_incomplete"]
    assert summary["totals"] == {"bars_incomplete": 1}


def test_read_failures_propagate(monkeypatch, tmp_path):
    def failing(marker: str, failure: Exception) -> Reader:
        reader = exits_reader()

        def fail(_sql, _params):
            raise failure

        reader.answers = [(m, fail if m == marker else a) for m, a in reader.answers]
        return reader

    for marker, failure in (
        ("FROM signal_alerts", ConnectionError("connection refused")),
        ("FROM market_data_intraday", ConnectionError("connection refused")),
        ("FROM market_data_intraday", KeyError("close")),
    ):
        with pytest.raises(type(failure)) as caught:
            dry_run(monkeypatch, tmp_path, failing(marker, failure), "--tickers", "SPY")
        assert caught.value is failure


def test_an_empty_selection_is_exit_zero(monkeypatch, tmp_path):
    reader = exits_reader(alerts=[])
    assert dry_run(monkeypatch, tmp_path, reader) == 0
    table, summary = report(tmp_path)
    assert table == [CSV_HEADER]
    assert summary["totals"] == {}
    assert reader.of("FROM market_data_intraday") == []


# ── --revert-run ──────────────────────────────────────────────────────


def test_revert_of_an_unknown_run_is_exit_one(monkeypatch, tmp_path, caplog):
    asked = []

    def nothing_held(run_id, target):
        asked.append((run_id, target))
        return []

    monkeypatch.setattr(database, "query_to_dataframe_strict",
                        Reader([("information_schema.columns", schema_ready)]))
    monkeypatch.setattr(br, "ledger_of_run", nothing_held)
    with caplog.at_level(logging.ERROR):
        code = run_main(monkeypatch, "--revert-run", "no-such-run", "--commit",
                        "--report-dir", str(tmp_path))

    assert code == 1
    assert asked == [("no-such-run", "signal-alert-exits")]
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "no-such-run" in errors[0] and "signal-alert-exits" in errors[0]
    assert not (tmp_path / "bar-recompute").exists()


def test_a_dry_revert_reads_only_the_ledger(monkeypatch, tmp_path):
    held = [{
        "run_id": "exits-run-A", "ticker": "SPY", "session_date": date(2026, 10, 6),
        "row_key": "2026-10-06T19:50:00.250000+00:00", "action": "recompute", "changed": True,
        "old_values": {
            "signal_alerts": {"exit_ts": "2026-10-06T20:20:00.000000+00:00",
                              "exit_reason": "time_stop", "exit_price": 100.0,
                              "exit_return_pct": 0.0, "exit_recompute_run": None},
            "trades": None},
        "new_values": {
            "signal_alerts": {"exit_ts": "2026-10-06T20:00:00.000000+00:00",
                              "exit_reason": "eod_close", "exit_price": 100.02,
                              "exit_return_pct": 0.01999999999999602,
                              "exit_recompute_run": "exits-run-A"},
            "trades": None},
        "basis": {},
    }]
    monkeypatch.setattr(br, "ledger_of_run", lambda run_id, target: held)
    code = dry_run_revert(monkeypatch, tmp_path)
    assert code == 0
    table, summary = report(tmp_path, "revert-dry")
    assert table[1] == [
        "SPY", "2026-10-06", "2026-10-06T19:50:00.250000+00:00",
        "2026-10-06T20:00:00.000000+00:00", "eod_close", "100.02", "0.01999999999999602",
        "2026-10-06T20:20:00.000000+00:00", "time_stop", "100.0", "0.0",
        "true", "would_revert", "", "", "false"]
    assert summary["arguments"] == {"revert_run": "exits-run-A", "commit": False}
    assert summary["totals"] == {"would_revert": 1}


def dry_run_revert(monkeypatch, tmp_path) -> int:
    monkeypatch.setattr(database, "query_to_dataframe_strict",
                        Reader([("information_schema.columns", schema_ready)]))
    monkeypatch.setattr(database, "get_engine", lambda: NoTransactionEngine())
    monkeypatch.setenv("CLOUD_RUN_EXECUTION", "revert-dry")
    return run_main(monkeypatch, "--revert-run", "exits-run-A", "--report-dir", str(tmp_path))
