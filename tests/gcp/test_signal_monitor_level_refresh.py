"""Tests for refresh_level_map diagnostic + counters (Track D / G.P1.1).

Verification dispatches on 2026-05-09 confirmed signal_alerts.level_broken
was 0% populated across 1,178 alerts in the 2026-05-04 → 2026-05-08
window despite fresh strat_levels data being available. The
data-freeze hypothesis from issue #301 was disproven; the bug is
code-side. Two silent-failure layers caused it:

  1. lib/data_loader.py:_query_cloud_sql swallowed exceptions silently
     and returned an empty DataFrame, making downstream callers see
     the failure mode as a legitimate zero-row condition.
  2. gcp/signal_monitor.py:refresh_level_map's bare-except logged only
     str(e) and clobbered level_maps[ticker]=None without any
     instrumentation, so production had no signal that the path was
     consistently failing.

These tests lock in:
  * _query_cloud_sql now calls log.exception before returning empty
    (full traceback reaches Cloud Logging)
  * refresh_level_map now increments three counters
    (success / empty_df / exception) so session_summary surfaces the
    distribution per ticker per session
  * the empty-df path logs a warning instead of being silent
  * the exception path uses logger.exception (full traceback) instead
    of logger.warning("...%s", e) (str(e) only)
"""
from __future__ import annotations

import logging

from unittest.mock import patch, MagicMock

import pandas as pd
import pytest


def _make_monitor():
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    return monitor


# ── 1) Counters init to {ticker: 0} for each watchlist ticker ────────

def test_level_refresh_counters_initialize_to_zero():
    monitor = _make_monitor()
    for ticker in monitor.tickers:
        assert monitor.level_refresh_success_count[ticker] == 0
        assert monitor.level_refresh_empty_df_count[ticker] == 0
        assert monitor.level_refresh_exception_count[ticker] == 0


# ── 2) Empty-df path: counter + warning ──────────────────────────────

def test_refresh_level_map_empty_df_increments_counter_and_warns(caplog):
    """When loader.load_daily returns empty, the empty_df counter
    must increment AND a warning must reach the logger (pre-fix this
    path was silent — production had no signal that the path was
    consistently failing)."""
    monitor = _make_monitor()
    ticker = monitor.tickers[0]
    with patch("lib.data_loader.DataLoader") as mock_dl_class:
        mock_dl_class.return_value.load_daily.return_value = pd.DataFrame()
        with caplog.at_level(logging.WARNING, logger="gcp.signal_monitor"):
            monitor.refresh_level_map(ticker)
    assert monitor.level_refresh_empty_df_count[ticker] == 1
    assert monitor.level_refresh_success_count[ticker] == 0
    assert monitor.level_refresh_exception_count[ticker] == 0
    assert monitor.level_maps[ticker] is None
    assert any("empty df" in rec.message.lower() for rec in caplog.records), (
        "empty-df path must log a warning so Cloud Logging shows the "
        "silent failure mode"
    )


# ── 3) Exception path: counter + traceback ───────────────────────────

def test_refresh_level_map_exception_increments_counter_and_logs_traceback(caplog):
    """When loader.load_daily raises, the exception counter must
    increment AND logger.exception must be called (full traceback
    reaches Cloud Logging — pre-fix only str(e) was logged)."""
    monitor = _make_monitor()
    ticker = monitor.tickers[0]

    class _Boom(RuntimeError):
        pass

    with patch("lib.data_loader.DataLoader") as mock_dl_class:
        mock_dl_class.return_value.load_daily.side_effect = _Boom("simulated DB failure")
        with caplog.at_level(logging.ERROR, logger="gcp.signal_monitor"):
            monitor.refresh_level_map(ticker)
    assert monitor.level_refresh_exception_count[ticker] == 1
    assert monitor.level_refresh_success_count[ticker] == 0
    assert monitor.level_refresh_empty_df_count[ticker] == 0
    assert monitor.level_maps[ticker] is None
    # logger.exception emits at ERROR level with exc_info
    has_exc_info = any(
        rec.exc_info is not None and "raised" in rec.message
        for rec in caplog.records
    )
    assert has_exc_info, (
        "exception path must use logger.exception (full traceback in "
        "Cloud Logging), not logger.warning('...%s', e) which only "
        "captures str(e)"
    )


# ── 4) Happy path: success counter increments ────────────────────────

def test_refresh_level_map_success_increments_success_counter():
    """When the full path completes (load_daily returns data,
    calculate_historical_levels and build_level_map succeed), the
    success counter must increment and level_maps[ticker] must be
    populated (not None)."""
    monitor = _make_monitor()
    ticker = monitor.tickers[0]

    # Build a minimal daily df that compute_previous_levels will accept:
    # needs ≥ 2 rows with OHLC columns and a usable date axis.
    idx = pd.date_range("2026-04-01", periods=30, freq="D")
    df = pd.DataFrame({
        "Time": idx,
        "Open": 100.0, "High": 102.0, "Low": 99.0, "Close": 101.0,
    }, index=idx)
    df.index.name = "Time"

    # Patch the LevelMap constructor so we don't have to mock the
    # entire build_level_map plumbing.
    fake_level_map = MagicMock()
    with patch("lib.data_loader.DataLoader") as mock_dl_class, \
         patch("gcp.signal_monitor.build_level_map", return_value=fake_level_map):
        mock_dl_class.return_value.load_daily.return_value = df
        monitor.refresh_level_map(ticker)
    assert monitor.level_refresh_success_count[ticker] == 1
    assert monitor.level_refresh_empty_df_count[ticker] == 0
    assert monitor.level_refresh_exception_count[ticker] == 0
    assert monitor.level_maps[ticker] is fake_level_map


# ── 5) lib/data_loader._query_cloud_sql logs traceback ───────────────

def test_query_cloud_sql_logs_exception_before_returning_empty(caplog):
    """When gcp.database.query_to_dataframe raises, _query_cloud_sql
    must log the full traceback before returning empty (pre-fix it
    swallowed the exception silently)."""
    from lib import data_loader

    class _DBOops(RuntimeError):
        pass

    with patch("gcp.database.query_to_dataframe", side_effect=_DBOops("conn refused")):
        with caplog.at_level(logging.ERROR, logger="lib.data_loader"):
            df = data_loader._query_cloud_sql("SELECT 1", {})
    assert df.empty, "_query_cloud_sql still returns empty on error (back-compat)"
    has_exc_info = any(
        rec.exc_info is not None and "_query_cloud_sql" in rec.message
        for rec in caplog.records
    )
    assert has_exc_info, (
        "_query_cloud_sql must call log.exception so the underlying DB "
        "exception reaches Cloud Logging — silent swallowing was the "
        "outer cause of the level_broken=NULL bug (refresh_level_map "
        "saw empty-df without an exception)"
    )


# ── 6) Counters appear in the run-loop session_summary line ──────────

def test_session_summary_includes_level_refresh_counters():
    """The end-of-session log line in run_loop must include the new
    level_refresh_{success,empty_df,exception} counters so cross-track
    debuggers can grep Cloud Logging without a separate persistence
    layer.

    Sourced rather than runtime-asserted because the run-loop is a
    hard-to-mock infinite poll. Tokens are unique enough that they
    only appear in the session_summary path; if any go missing, this
    test fails fast at import time on the next push.
    """
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2] / "gcp" / "signal_monitor.py"
    ).read_text()
    assert "session_summary " in text, (
        "session_summary log call missing from signal_monitor.py"
    )
    for token in (
        # format-string fragment
        "level_refresh_success=%d",
        "level_refresh_empty_df=%d",
        "level_refresh_exception=%d",
        # the dict-name read at fmt-arg position
        "level_refresh_success_count.get",
        "level_refresh_empty_df_count.get",
        "level_refresh_exception_count.get",
    ):
        assert token in text, (
            f"signal_monitor.py must reference `{token}`; see G.P1.1 "
            f"instrumentation in session_summary"
        )


# ── 5) As-of bound (#823 / audit R6) ─────────────────────────────────
#
# DataLoader.load_daily has no upper date bound (lib/data_loader.py
# _load_daily_from_sql filters on ticker and optional year only), so the
# frame refresh_level_map hands to calculate_historical_levels and
# build_level_map ends at whatever market_data_daily holds:
#   * live: fetch-premarket-refresh INSERTs today's row at 08:20 ET with
#     pre_* fields only (OHLC NULL until the 23:00 ET fill) — verified
#     2026-09-07 on production: every session date's first row lands at
#     12:21 UTC — so from the open the last row is today's NULL-OHLC bar,
#     current_price = float(NaN), and the current-period levels and the
#     gap scan read a bar the session has not produced yet;
#   * replay of D: the frame carries D's COMPLETED bar and every bar
#     after it, so the replayed map is built from information the live
#     session on D never had.
# The premarket brief bounds its frame with `idx < analysis_date` before
# building; the monitor must apply the same cutoff so a D-replay and the
# D-live session build the map from the same rows.

def _daily_frame_through(last_day: str) -> pd.DataFrame:
    idx = pd.date_range("2026-08-03", last_day, freq="B")
    n = len(idx)
    df = pd.DataFrame({
        "Time": idx,
        "Open": [100.0 + i for i in range(n)],
        "High": [101.0 + i for i in range(n)],
        "Low": [99.0 + i for i in range(n)],
        "Close": [100.5 + i for i in range(n)],
    }, index=idx)
    df.index.name = "Time"
    return df


def _capture_build_inputs(monitor, ticker, df):
    """Run refresh_level_map over `df` and return (daily_df, current_price)
    as passed to build_level_map, plus the frame calculate_historical_levels
    received (via the length of its `times` argument)."""
    seen = {}

    def _fake_build(**kw):
        seen["daily_df"] = kw["daily_df"]
        seen["current_price"] = kw["current_price"]
        seen["analysis_date"] = kw["analysis_date"]
        return MagicMock()

    real_hist = __import__("lib.indicators", fromlist=["calculate_historical_levels"]).calculate_historical_levels

    def _spy_hist(ts, high, low, open_, close):
        seen["hist_last_ts"] = pd.Timestamp(pd.Series(ts).iloc[-1])
        return real_hist(ts, high, low, open_, close)

    with patch("lib.data_loader.DataLoader") as mock_dl_class, \
         patch("gcp.signal_monitor.build_level_map", side_effect=_fake_build), \
         patch("lib.indicators.calculate_historical_levels", side_effect=_spy_hist):
        mock_dl_class.return_value.load_daily.return_value = df
        monitor.refresh_level_map(ticker)
    return seen


def test_refresh_level_map_excludes_the_analysis_date_row_and_everything_after():
    """A row dated exactly analysis_date (and any later row) must not reach
    calculate_historical_levels, build_level_map or current_price."""
    monitor = _make_monitor()
    ticker = monitor.tickers[0]
    monitor.replay_clock_ts = pd.Timestamp("2026-09-03 09:31:00")
    df = _daily_frame_through("2026-09-05")          # carries 09-03, 09-04
    seen = _capture_build_inputs(monitor, ticker, df)

    assert seen["analysis_date"] == pd.Timestamp("2026-09-03").date()
    passed = seen["daily_df"]
    assert passed.index.max() == pd.Timestamp("2026-09-02"), \
        f"frame must end BEFORE analysis_date; got {passed.index.max()}"
    assert seen["hist_last_ts"] == pd.Timestamp("2026-09-02")
    expected_close = float(df.loc[pd.Timestamp("2026-09-02"), "Close"])
    assert seen["current_price"] == expected_close, \
        "current_price must be the last close BEFORE analysis_date, not the as-of bar"
    assert monitor.level_refresh_success_count[ticker] == 1


def test_replay_of_d_and_live_on_d_build_from_the_same_rows():
    """#823 definition of done: the level map for date D is identical
    between a D-replay (frame extends past D) and the D-live session
    (frame ends at D's not-yet-filled row)."""
    replay = _make_monitor()
    replay.replay_clock_ts = pd.Timestamp("2026-09-03 09:31:00")
    seen_replay = _capture_build_inputs(replay, replay.tickers[0],
                                        _daily_frame_through("2026-09-05"))

    live = _make_monitor()
    live.replay_clock_ts = pd.Timestamp("2026-09-03 09:31:00")
    live_df = _daily_frame_through("2026-09-03")
    # Live: today's row exists from 08:20 ET with NULL OHLC (premarket refresh).
    live_df.loc[pd.Timestamp("2026-09-03"), ["Open", "High", "Low", "Close"]] = float("nan")
    seen_live = _capture_build_inputs(live, live.tickers[0], live_df)

    pd.testing.assert_frame_equal(seen_replay["daily_df"], seen_live["daily_df"])
    assert seen_replay["current_price"] == seen_live["current_price"]
    assert seen_live["current_price"] == seen_live["current_price"], \
        "live current_price must not be NaN from today's unfilled row"


def test_frame_empty_after_the_bound_is_the_empty_df_path():
    """Only rows on/after analysis_date -> nothing to build from; take the
    explicit empty-df path (counter + warning), never a map from as-of data."""
    monitor = _make_monitor()
    ticker = monitor.tickers[0]
    monitor.replay_clock_ts = pd.Timestamp("2026-08-03 09:31:00")
    df = _daily_frame_through("2026-08-05")   # all rows >= 08-03
    with patch("lib.data_loader.DataLoader") as mock_dl_class, \
         patch("gcp.signal_monitor.build_level_map") as build:
        mock_dl_class.return_value.load_daily.return_value = df
        monitor.refresh_level_map(ticker)
    build.assert_not_called()
    assert monitor.level_maps[ticker] is None
    assert monitor.level_refresh_empty_df_count[ticker] == 1
    assert monitor.level_refresh_exception_count[ticker] == 0
