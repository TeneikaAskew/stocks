"""The nightly option jobs end their windows on the exchange's date (FEAT-DATA-001, stage 1).

`av-options-daily` (21:00 ET), `options-daily-features` (22:00 ET) and
`options-daily-greeks` (23:15 ET) run in containers whose clock is UTC, where
it is already tomorrow. The AV job asked the vendor for tomorrow's chain every
night Monday to Thursday; the two builders recomputed ``[D-6, D+1]`` where
``[D-7, D]`` was meant.

These are I/O-shape tests (CLAUDE.md Rule 0.3): they run each job's ``main()``
and assert the dates handed to the fetch loop and to the builder, not a
helper's return value.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

import pandas as pd
import pytest

import gcp.build_options_daily_greeks as greeks
import gcp.build_realtime_gex as realtime_gex
import gcp.database as database
import gcp.fetchers.build_options_daily_features as features
import gcp.fetchers.fetch_av_historical_options as av_options
from tests.fixtures.market_clock import DAYTIME, STANDARD_INSTANTS, freeze_market_clock

THURSDAY_21_EST = "2026-11-13T02:00:00Z"  # Thursday 2026-11-12 21:00 EST


def _run_av_main(monkeypatch, argv, watermark=None):
    """Run the job's main() with the vendor, the database and the pacing sleep stubbed."""
    fetched: list[tuple[str, str]] = []

    def recording_process(ticker, fetch_date, api_key, skip_existing=False):
        fetched.append((ticker, fetch_date))

    rows = [] if watermark is None else [{"ticker": "SPY", "d": pd.Timestamp(watermark)}]
    monkeypatch.setattr(database, "query_to_dataframe",
                        lambda *a, **k: pd.DataFrame(rows, columns=["ticker", "d"]))
    monkeypatch.setattr(av_options, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(av_options, "process_ticker", recording_process)
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    monkeypatch.setenv("AV_API_KEY", "k")
    monkeypatch.setattr(sys, "argv", ["x", "--tickers", "SPY", *argv])
    av_options.main()
    return fetched


@pytest.mark.parametrize("instant, watermark, want", [
    (THURSDAY_21_EST, "2026-11-11", ["2026-11-12"]),
    ("2026-07-10T01:00:00Z", "2026-07-08", ["2026-07-09"]),       # Thursday 21:00 EDT
    (DAYTIME, "2026-11-10", ["2026-11-11", "2026-11-12"]),
])
def test_from_latest_ends_on_the_exchange_date(monkeypatch, instant, watermark, want):
    freeze_market_clock(monkeypatch, instant, av_options)

    fetched = _run_av_main(monkeypatch, ["--from-latest"], watermark)

    assert fetched == [("SPY", day) for day in want]


def test_an_empty_table_starts_on_the_exchange_date(monkeypatch):
    freeze_market_clock(monkeypatch, THURSDAY_21_EST, av_options)
    monkeypatch.setattr(database, "query_to_dataframe",
                        lambda *a, **k: pd.DataFrame(columns=["ticker", "d"]))

    assert av_options._resolve_start_from_latest([]) == date(2026, 11, 12)
    assert av_options._resolve_start_from_latest(["SPY"]) == date(2026, 11, 12)


def test_an_end_date_passed_by_hand_is_used(monkeypatch):
    freeze_market_clock(monkeypatch, THURSDAY_21_EST, av_options)

    fetched = _run_av_main(monkeypatch, ["--start-date", "2026-11-10", "--end-date", "2026-11-10"])

    assert fetched == [("SPY", "2026-11-10")]


def _run_features_main(monkeypatch):
    windows: list[tuple[str, str]] = []

    def recording_build(engine, ticker, since, until):
        windows.append((since, until))
        return 0

    monkeypatch.setattr(features, "get_engine", lambda: object())
    monkeypatch.setattr(features, "build_materialized", recording_build)
    features.main()
    return windows


def _run_greeks_main(monkeypatch):
    windows: list[tuple[str, str]] = []

    def recording_build(engine, tickers, since, until):
        windows.append((since, until))
        return {}

    monkeypatch.setattr(database, "get_engine", lambda: object())
    monkeypatch.setattr(greeks, "build", recording_build)
    greeks.main()
    return windows


@pytest.mark.parametrize("module, run, instant", [
    (features, _run_features_main, "2026-11-13T03:00:00Z"),  # Thursday 2026-11-12 22:00 EST
    (features, _run_features_main, DAYTIME),
    (greeks, _run_greeks_main, "2026-11-13T04:15:00Z"),      # Thursday 2026-11-12 23:15 EST
    (greeks, _run_greeks_main, DAYTIME),
], ids=["features-22:00-EST", "features-daytime", "greeks-23:15-EST", "greeks-daytime"])
def test_the_incremental_window_is_seven_days_back_from_the_exchange_date(monkeypatch, module, run, instant):
    freeze_market_clock(monkeypatch, instant, module)
    monkeypatch.setattr(sys, "argv", ["x", "--incremental", "--days=7"])

    windows = run(monkeypatch)

    # Thursday 2026-11-12 at every instant here: [D-7, D], on every call to the builder.
    assert windows and set(windows) == {("2026-11-05", "2026-11-12")}


@pytest.mark.parametrize("instant, eastern", STANDARD_INSTANTS)
def test_realtime_gex_window(monkeypatch, instant, eastern):
    freeze_market_clock(monkeypatch, instant, realtime_gex)
    windows: list[tuple[str, str]] = []

    def recording_build(engine, tickers, since, until, resume=False):
        windows.append((since, until))
        return {}

    monkeypatch.setattr(database, "get_engine", lambda: object())
    monkeypatch.setattr(realtime_gex, "build", recording_build)
    monkeypatch.setattr(sys, "argv", ["x", "--incremental", "--days=3"])

    realtime_gex.main()

    assert windows == [((eastern - timedelta(days=3)).isoformat(), eastern.isoformat())]
