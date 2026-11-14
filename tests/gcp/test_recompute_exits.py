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
