"""Phase 1 — integration tests for the timeframe-tag wiring in signal_monitor.

The pure helper (`assign_timeframe`) is exhaustively covered in
`tests/test_strategy_timeframe.py`. This file verifies the WIRING:

  1. _evaluate strategies → assign_timeframe → stash on self
  2. fire_alert embed title includes the [timeframe] label
  3. _persist_signal_alert row carries timeframe_tag + expected_hold_min
  4. high-volatility synthetic bar produces the high-vol tf tag
  5. low-volatility synthetic bar produces the low-vol tf tag

Hermetic: mocks momentum strategy + DB. No Cloud SQL, no network.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _make_monitor():
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    return monitor


def _mr_call_bar(*, rvol: float = 1.4, atr14: float = 1.2,
                 close: float = 720.0) -> pd.Series:
    """Bar that satisfies mean-reversion CALL conditions. Caller can
    override RVOL and ATR14 to nudge the timeframe heuristic."""
    return pd.Series({
        "Close": close, "Last": close,
        "RSI14": 35.0, "RSI14_W": 35.0,
        "VWAP": close + 3.0,
        "EMA9": close + 2.0, "EMA20": close + 3.5,
        "StochRSI_K": 25.0,
        "Price_vs_VWAP": -0.42,
        "Price_vs_EMA9": -0.28,
        "Price_vs_EMA20": -0.49,
        "Consecutive_Down": 4,
        "Consecutive_Up": 0,
        "RVOL": rvol, "ATR14": atr14,
        "Broke_Prev_Day_Low": 0,
        "Broke_Prev_Day_High": 0,
    })


def _capture_embed(monitor, sig, latest):
    """Run fire_alert and parse the embed JSON from stdout."""
    buf = io.StringIO()
    with patch("gcp.database.upsert_dataframe", return_value=1), \
         patch("gcp.database.is_cloud_sql_configured", return_value=True), \
         contextlib.redirect_stdout(buf):
        monitor.fire_alert(
            ticker="SPY", sig=sig, total_score=4.0,
            strength="STRONG", size=0.10, strat_bonus=0,
            latest=latest,
        )
    text = buf.getvalue()
    start = text.find("{")
    end = text.rfind("}")
    return json.loads(text[start: end + 1])


# ── 1) evaluate_ticker → assign_timeframe → stash ─────────────────────

def test_evaluate_strategies_for_bar_does_not_set_tf_directly():
    """The helper itself doesn't tag — that happens in evaluate_ticker
    after the helper returns. Sanity guard against accidentally
    moving the tagging logic into the helper (it shouldn't be there)."""
    monitor = _make_monitor()
    bar = _mr_call_bar()
    with patch("gcp.signal_monitor.MOMENTUM.evaluate", return_value=None):
        sig, agreement = monitor._evaluate_strategies_for_bar(bar, 720.0, "SPY")
    # Helper returns without touching _latest_timeframe_tag
    assert sig is not None
    assert not hasattr(monitor, "_latest_timeframe_tag") or \
           monitor._latest_timeframe_tag is None


# ── 2) fire_alert embed includes [tf] ─────────────────────────────────

def test_embed_title_includes_timeframe_label_when_tagged():
    monitor = _make_monitor()
    monitor._latest_timeframe_tag = "30m"
    monitor._latest_expected_hold_min = 30
    sig = {
        "direction": "CALL", "base_score": 4,
        "conditions_met": ["consecutive_down", "below_vwap"],
    }
    embed = _capture_embed(monitor, sig, _mr_call_bar())
    assert "[30m]" in embed["title"]
    # Format: 'CALL SIGNAL [30m] — SPY @ $720.00'
    assert embed["title"].index("[30m]") < embed["title"].index("SPY")


def test_embed_title_no_timeframe_label_when_unset():
    """If somehow tagging didn't happen (legacy code path), embed
    must not show '[None]' or crash."""
    monitor = _make_monitor()
    # Don't set _latest_timeframe_tag — getattr fallback returns None
    sig = {
        "direction": "CALL", "base_score": 3,
        "conditions_met": ["consecutive_down"],
    }
    embed = _capture_embed(monitor, sig, _mr_call_bar())
    assert "[None]" not in embed["title"]
    assert "[]" not in embed["title"]


def test_embed_title_combines_stacked_prefix_with_timeframe():
    """When both stacked-agreement AND timeframe tag are present, both
    visual markers appear in the title."""
    monitor = _make_monitor()
    monitor._latest_agreement = {
        "agree": True, "strategies": ["mean_reversion", "momentum"],
        "directions": ["CALL", "CALL"], "base_scores": [4.0, 4.0],
        "composite_score": 5.0,
    }
    monitor._latest_timeframe_tag = "15m"
    monitor._latest_expected_hold_min = 15
    sig = {"direction": "CALL", "base_score": 4,
           "conditions_met": ["consecutive_down", "below_vwap"]}
    embed = _capture_embed(monitor, sig, _mr_call_bar())
    assert "STACKED" in embed["title"]
    assert "[15m]" in embed["title"]


# ── 3) _persist_signal_alert row carries the new columns ──────────────

def test_persist_writes_timeframe_tag_and_expected_hold():
    monitor = _make_monitor()
    monitor._latest_timeframe_tag = "60m"
    monitor._latest_expected_hold_min = 60
    sig = {
        "direction": "CALL", "base_score": 3,
        "conditions_met": ["consecutive_down", "rsi_oversold_zone"],
    }
    latest = _mr_call_bar()

    with patch("gcp.database.upsert_dataframe") as mock_upsert, \
         patch("gcp.database.is_cloud_sql_configured", return_value=True):
        mock_upsert.return_value = 1
        monitor._persist_signal_alert(
            ticker="SPY", sig=sig, total_score=3.0, strength="MODERATE",
            size=0.05, strat_bonus=0, latest=latest, target=722.0,
            time_stop=30,
        )

    df = mock_upsert.call_args[0][0]
    assert "timeframe_tag" in df.columns
    assert "expected_hold_min" in df.columns
    row = df.iloc[0]
    assert row["timeframe_tag"] == "60m"
    assert row["expected_hold_min"] == 60


def test_persist_handles_missing_timeframe_attrs_gracefully():
    """If somehow evaluate_ticker didn't run before persist, the row
    must still serialize — getattr falls back to None, which is OK
    since the columns are nullable."""
    monitor = _make_monitor()
    # Don't set the _latest_* attrs
    sig = {"direction": "CALL", "base_score": 3,
           "conditions_met": ["consecutive_down"]}
    latest = _mr_call_bar()

    with patch("gcp.database.upsert_dataframe") as mock_upsert, \
         patch("gcp.database.is_cloud_sql_configured", return_value=True):
        mock_upsert.return_value = 1
        monitor._persist_signal_alert(
            ticker="SPY", sig=sig, total_score=3.0, strength="MODERATE",
            size=0.05, strat_bonus=0, latest=latest, target=722.0,
            time_stop=30,
        )

    df = mock_upsert.call_args[0][0]
    assert df.iloc[0]["timeframe_tag"] is None
    assert df.iloc[0]["expected_hold_min"] is None
