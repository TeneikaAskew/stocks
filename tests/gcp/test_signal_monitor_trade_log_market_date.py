"""The monitor's bar filter, the trade log and the weekend review read the
exchange's date (FEAT-DATA-001, stage 1).

The signal monitor runs 09:25 to 16:00 America/New_York and the weekend review
on Saturday morning, hours at which the container's UTC date and the
exchange's agree, so nothing these sites store is wrong today. Nothing but the
schedule kept them right. Each test runs at an evening instant in both seasons
(where the old code was a day ahead) and at two instants where the host date
agrees (where the value must not move).
"""
from __future__ import annotations

import os
from datetime import timedelta

import pandas as pd
import pytest

import gcp.database as database
import gcp.signal_monitor as signal_monitor
import gcp.trade_logger as trade_logger
import gcp.weekend_review as weekend_review
from tests.fixtures.market_clock import STANDARD_INSTANTS, freeze_market_clock

four_instants = pytest.mark.parametrize("instant, eastern", STANDARD_INSTANTS)


class _Bars:
    def __init__(self, stamps):
        self._stamps = stamps

    def raise_for_status(self):
        return None

    def json(self):
        bar = {"1. open": "1.0", "2. high": "1.0", "3. low": "1.0", "4. close": "1.0", "5. volume": "100"}
        return {"Time Series (1min)": {stamp: dict(bar) for stamp in self._stamps}}


def _trade(**extra) -> dict:
    row = {"ticker": "SPY", "direction": "CALL", "entry_time": "09:35", "run_kind": "live"}
    row.update(extra)
    return row


@four_instants
def test_fetch_latest_bar_keeps_the_exchange_days_bars(monkeypatch, instant, eastern):
    # Built as tests/gcp/test_signal_monitor.py::_build_monitor builds one, before the freeze.
    os.environ.setdefault("ALPHA_VANTAGE_API_KEY", "test-key")
    monitor = signal_monitor.SignalMonitor()
    freeze_market_clock(monkeypatch, instant, signal_monitor)
    stamps = [f"{eastern} 15:59:00", f"{eastern + timedelta(days=1)} 09:30:00"]
    monkeypatch.setattr(signal_monitor.requests, "get", lambda *a, **k: _Bars(stamps))

    out = monitor.fetch_latest_bar("SPY")

    assert [stamp.date() for stamp in out.index] == [eastern]


@four_instants
def test_the_trade_log_names_todays_file_and_date(monkeypatch, tmp_path, instant, eastern):
    freeze_market_clock(monkeypatch, instant, trade_logger)
    logger = trade_logger.TradeLogger(output_dir=str(tmp_path))
    written = []

    def recording_upsert(df, table, conflict_cols=None, **kwargs):
        written.append(df.copy())
        return len(df)

    assert logger._daily_file().name == f"{eastern}.parquet"

    # log_trade stamps trade_date on the row it sends to Cloud SQL (the Parquet
    # backup keeps the caller's row as given), and appends to today's file.
    monkeypatch.setenv("CLOUD_SQL_CONNECTION_NAME", "project:region:instance")
    monkeypatch.setattr(database, "upsert_dataframe", recording_upsert)
    logger.log_trade(_trade())

    assert [list(df["trade_date"]) for df in written] == [[str(eastern)]]
    assert [path.name for path in tmp_path.glob("*.parquet")] == [f"{eastern}.parquet"]


@four_instants
def test_the_trade_readers_default_to_the_exchange_date(monkeypatch, tmp_path, instant, eastern):
    freeze_market_clock(monkeypatch, instant, trade_logger)
    logger = trade_logger.TradeLogger(output_dir=str(tmp_path))
    bound = []

    def recording_query(sql, params=None):
        bound.append(dict(params))
        return pd.DataFrame()

    monkeypatch.setenv("CLOUD_SQL_CONNECTION_NAME", "project:region:instance")
    monkeypatch.setattr(database, "query_to_dataframe_strict", recording_query)
    logger.get_daily_trades()
    logger.get_weekly_trades()

    assert bound[0]["d"] == str(eastern)
    assert bound[1]["end"] == str(eastern)
    assert bound[1]["start"] == str(eastern - timedelta(days=6))

    # With Cloud SQL off, the weekly read walks the seven files ending today.
    monkeypatch.delenv("CLOUD_SQL_CONNECTION_NAME")
    read = []
    monkeypatch.setattr(logger, "_load_parquet_for_date",
                        lambda day: (read.append(str(day)), pd.DataFrame())[1])
    logger.get_weekly_trades()

    assert read == [str(eastern - timedelta(days=i)) for i in range(7)]


@four_instants
def test_week_ending_is_the_exchange_date(monkeypatch, tmp_path, instant, eastern):
    freeze_market_clock(monkeypatch, instant, weekend_review, trade_logger)
    monkeypatch.setattr(trade_logger.TradeLogger, "get_weekly_trades",
                        lambda self, *a, **k: pd.DataFrame())

    review = weekend_review.generate_weekly_review(trades_dir=str(tmp_path))

    assert review["week_ending"] == eastern.isoformat()
    assert len(review["week_ending"]) == 10
