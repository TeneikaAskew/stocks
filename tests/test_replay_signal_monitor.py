"""Hermetic tests for the signal-monitor replay harness.

scripts/replay_signal_monitor.py is normally run against real
market_data_intraday rows. These tests prove the harness wiring works
without Cloud SQL by feeding synthetic bars in-memory.

Coverage:
  1. parse_args — single-date and start/end forms; ticker variants
  2. resolve_window — date / start-end / missing-args edge cases
  3. resolve_tickers — comma-list, single, missing
  4. make_capturing_fire_alert — captures a FireRecord with the right
     fields (timeframe_tag, agreement, embed title) when fire_alert is
     called in place of the real Discord push
  5. replay_ticker — empty bars short-circuits; non-empty advances the
     rolling window per-bar
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.replay_signal_monitor import (  # noqa: E402
    FireRecord,
    make_capturing_fire_alert,
    parse_args,
    replay_ticker,
    resolve_tickers,
    resolve_window,
)


# ── 1) parse_args ─────────────────────────────────────────────────────

def test_parse_args_with_single_date_and_ticker():
    a = parse_args(["--ticker", "SPY", "--date", "2026-05-01"])
    assert a.ticker == "SPY"
    assert a.date == "2026-05-01"


def test_parse_args_with_tickers_list_and_range():
    a = parse_args([
        "--tickers", "SPY,QQQ,IWM",
        "--start", "2026-04-29", "--end", "2026-05-01",
    ])
    assert a.tickers == "SPY,QQQ,IWM"
    assert a.start == "2026-04-29"
    assert a.end == "2026-05-01"


def test_parse_args_json_flag():
    a = parse_args(["--ticker", "SPY", "--date", "2026-05-01", "--json"])
    assert a.json is True


# ── 2) resolve_window ─────────────────────────────────────────────────

def test_resolve_window_single_date_spans_24h():
    args = parse_args(["--ticker", "SPY", "--date", "2026-05-01"])
    start, end = resolve_window(args)
    assert start == datetime(2026, 5, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 5, 2, tzinfo=timezone.utc)


def test_resolve_window_start_end_explicit_range():
    args = parse_args(["--ticker", "SPY", "--start", "2026-04-25", "--end", "2026-05-02"])
    start, end = resolve_window(args)
    assert start == datetime(2026, 4, 25, tzinfo=timezone.utc)
    assert end == datetime(2026, 5, 2, tzinfo=timezone.utc)


def test_resolve_window_missing_window_args_raises():
    args = parse_args(["--ticker", "SPY"])
    with pytest.raises(SystemExit):
        resolve_window(args)


# ── 3) resolve_tickers ────────────────────────────────────────────────

def test_resolve_tickers_single():
    args = parse_args(["--ticker", "spy", "--date", "2026-05-01"])
    assert resolve_tickers(args) == ["SPY"]


def test_resolve_tickers_comma_list_uppercased():
    args = parse_args(["--tickers", "spy, qqq , iwm", "--date", "2026-05-01"])
    assert resolve_tickers(args) == ["SPY", "QQQ", "IWM"]


def test_resolve_tickers_missing_raises():
    args = parse_args(["--date", "2026-05-01"])
    with pytest.raises(SystemExit):
        resolve_tickers(args)


def test_resolve_tickers_prefers_tickers_list_over_ticker():
    """When both flags are given (CLI ergonomics edge case), the list wins."""
    args = parse_args(["--ticker", "AVGO", "--tickers", "SPY,QQQ", "--date", "2026-05-01"])
    assert resolve_tickers(args) == ["SPY", "QQQ"]


# ── 4) make_capturing_fire_alert ──────────────────────────────────────

def test_capturing_fire_alert_records_basic_signal():
    """A solo fire (no agreement, with timeframe tag) populates a
    FireRecord with the right fields."""
    captured: list[FireRecord] = []
    monitor = MagicMock()
    monitor._latest_agreement = None
    monitor._latest_timeframe_tag = "30m"
    monitor._latest_expected_hold_min = 30

    fire_fn = make_capturing_fire_alert(captured, monitor)
    sig = {"direction": "CALL", "base_score": 4,
           "conditions_met": ["consecutive_down", "below_vwap"]}
    latest = pd.Series({
        "Time": pd.Timestamp("2026-05-01 14:30", tz="UTC"),
        "Close": 720.0,
    })
    fire_fn(monitor, "SPY", sig, total_score=4.0, strength="STRONG",
            size=0.10, strat_bonus=0, latest=latest)

    assert len(captured) == 1
    f = captured[0]
    assert f.ticker == "SPY"
    assert f.direction == "CALL"
    assert f.base_score == 4
    assert f.timeframe_tag == "30m"
    assert f.expected_hold_min == 30
    assert f.strategy_agreement is None
    assert "[30m]" in f.embed_title
    assert "STACKED" not in f.embed_title


def test_capturing_fire_alert_records_stacked_agreement():
    """A stacked-agreement fire records the payload AND the STACKED prefix."""
    captured: list[FireRecord] = []
    monitor = MagicMock()
    monitor._latest_agreement = {
        "agree": True,
        "strategies": ["mean_reversion", "momentum"],
        "directions": ["CALL", "CALL"],
        "base_scores": [4.0, 4.0],
        "composite_score": 5.0,
    }
    monitor._latest_timeframe_tag = "15m"
    monitor._latest_expected_hold_min = 15

    fire_fn = make_capturing_fire_alert(captured, monitor)
    sig = {"direction": "CALL", "base_score": 4, "conditions_met": ["consecutive_down"]}
    latest = pd.Series({
        "Time": pd.Timestamp("2026-05-01 14:30", tz="UTC"),
        "Close": 720.0,
    })
    fire_fn(monitor, "SPY", sig, total_score=5.0, strength="STRONG",
            size=0.10, strat_bonus=1, latest=latest)

    f = captured[0]
    assert f.strategy_agreement is not None
    assert f.strategy_agreement["composite_score"] == 5.0
    assert "STACKED" in f.embed_title
    assert "[15m]" in f.embed_title


def test_capturing_fire_alert_to_dict_is_json_safe():
    """FireRecord.to_dict() must produce something json.dumps-able for
    --json output mode."""
    import json
    captured: list[FireRecord] = []
    monitor = MagicMock()
    monitor._latest_agreement = None
    monitor._latest_timeframe_tag = "60m"
    monitor._latest_expected_hold_min = 60

    fire_fn = make_capturing_fire_alert(captured, monitor)
    sig = {"direction": "PUT", "base_score": 3, "conditions_met": ["consecutive_up"]}
    latest = pd.Series({
        "Time": pd.Timestamp("2026-05-01 14:30", tz="UTC"),
        "Close": 720.0,
    })
    fire_fn(monitor, "SPY", sig, 3.0, "MODERATE", 0.05, 0, latest)

    d = captured[0].to_dict()
    s = json.dumps(d)            # must not raise
    assert "PUT" in s
    assert "60m" in s


# ── 5) replay_ticker ──────────────────────────────────────────────────

def test_replay_ticker_empty_bars_short_circuits():
    captured: list[FireRecord] = []
    monitor = MagicMock()
    n_bars, n_fires = replay_ticker(monitor, "SPY", pd.DataFrame(), captured)
    assert n_bars == 0
    assert n_fires == 0
    monitor.update_window.assert_not_called()


def test_replay_ticker_calls_update_window_and_evaluate_per_bar():
    """The replay must walk bars one-by-one so the monitor sees the
    same shape it does in production (1-bar deltas, not bulk loads)."""
    captured: list[FireRecord] = []
    monitor = MagicMock()
    bars = pd.DataFrame({
        "Time": pd.date_range("2026-05-01 09:30", periods=5, freq="1min", tz="UTC"),
        "Open":  [100.0] * 5,
        "High":  [101.0] * 5,
        "Low":   [99.0] * 5,
        "Close": [100.5] * 5,
        "Volume": [1000] * 5,
    })

    n_bars, n_fires = replay_ticker(monitor, "SPY", bars, captured)
    assert n_bars == 5
    assert n_fires == 0   # no captures because monitor is a MagicMock
    assert monitor.update_window.call_count == 5
    assert monitor.evaluate_ticker.call_count == 5


def test_replay_ticker_swallows_evaluate_exceptions():
    """If evaluate_ticker raises mid-replay (e.g. a synthetic edge case),
    the harness logs and continues — doesn't abort the whole replay."""
    captured: list[FireRecord] = []
    monitor = MagicMock()
    # Raise on the 2nd bar; the replay should still process the 3rd.
    monitor.evaluate_ticker.side_effect = [None, RuntimeError("boom"), None]
    bars = pd.DataFrame({
        "Time": pd.date_range("2026-05-01 09:30", periods=3, freq="1min", tz="UTC"),
        "Open":  [100.0] * 3,
        "High":  [101.0] * 3,
        "Low":   [99.0] * 3,
        "Close": [100.5] * 3,
        "Volume": [1000] * 3,
    })

    n_bars, n_fires = replay_ticker(monitor, "SPY", bars, captured)
    assert n_bars == 3
    assert monitor.update_window.call_count == 3
    assert monitor.evaluate_ticker.call_count == 3
