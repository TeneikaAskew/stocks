"""Smoke test for the signal_monitor persist path.

Catches the class of bug that caused the 4/14 - 4/30 silent-write gap:
signal_monitor ran every weekday, exited 0 ("1/1 complete"), but
wrote 0 rows to signal_alerts. The standard CI pytest run doesn't
hit Cloud SQL, so this test mocks `upsert_dataframe` and asserts:

  1. _persist_signal_alert is reached when a signal fires
  2. It calls upsert_dataframe with the expected (table, conflict_keys)
  3. The DataFrame passed to upsert has all required columns
  4. Required columns are non-null where the schema demands

If anyone breaks the eval → fire → persist chain (drops the persist
call, swallows an exception silently, mis-renames a column, etc.),
this test fails BEFORE the change ships.
"""
from __future__ import annotations

import pandas as pd
import pytest
from unittest.mock import MagicMock, patch


REQUIRED_COLUMNS = {
    "ticker", "alert_ts", "alert_date", "direction",
    "base_score", "total_score", "price_at_signal", "rsi", "rvol",
    "conditions_met",
}


def _make_monitor_with_mocked_persist():
    """Construct a SignalMonitor with stubbed deps. The constructor reads
    config from the project's alert_config.json, which is fine — the test
    only validates the persist call shape, not the live config."""
    from gcp.signal_monitor import SignalMonitor

    monitor = SignalMonitor()
    # Disable Discord post-side-effect to keep the test hermetic
    monitor.webhook_url = ""
    return monitor


def _make_synthetic_latest_bar(direction: str = "CALL") -> pd.Series:
    """Build a fake `latest` bar that satisfies mean-reversion CALL conditions.

    For CALL: RSI in (25, 50), Price < VWAP, Price < EMA9, StochRSI < 30,
    Consecutive_Down >= 3.
    """
    if direction == "CALL":
        return pd.Series({
            "Close": 720.0, "Last": 720.0,
            "RSI14": 35.0, "RSI14_W": 35.0,
            "VWAP": 723.0,
            "EMA9": 722.0,
            "EMA20": 723.5,
            "StochRSI_K": 25.0,
            "Price_vs_VWAP": -0.42,
            "Price_vs_EMA9": -0.28,
            "Price_vs_EMA20": -0.49,
            "Consecutive_Down": 4,
            "Consecutive_Up": 0,
            "RVOL": 1.4,
            "ATR14": 1.2,
            "Broke_Prev_Day_Low": 0,
            "Broke_Prev_Day_High": 0,
        })
    # PUT mirror
    return pd.Series({
        "Close": 720.0, "Last": 720.0,
        "RSI14": 65.0, "RSI14_W": 65.0,
        "VWAP": 717.0,
        "EMA9": 718.0,
        "StochRSI_K": 75.0,
        "Price_vs_VWAP": 0.42,
        "Price_vs_EMA9": 0.28,
        "Price_vs_EMA20": 0.18,
        "Consecutive_Up": 4,
        "Consecutive_Down": 0,
        "RVOL": 1.4,
        "ATR14": 1.2,
        "Broke_Prev_Day_High": 0,
        "Broke_Prev_Day_Low": 0,
    })


def test_persist_signal_alert_calls_upsert_with_correct_table_and_keys():
    """When a CALL signal fires, _persist_signal_alert must call
    upsert_dataframe('signal_alerts', ['ticker', 'alert_ts'])."""
    monitor = _make_monitor_with_mocked_persist()

    sig = {
        "direction": "CALL",
        "base_score": 4,
        "conditions_met": ["consecutive_down", "rsi_oversold_zone",
                           "below_vwap", "near_below_emas"],
    }
    latest = _make_synthetic_latest_bar("CALL")

    with patch("gcp.database.upsert_dataframe") as mock_upsert, \
         patch("gcp.database.is_cloud_sql_configured", return_value=True):
        mock_upsert.return_value = 1

        monitor._persist_signal_alert(
            ticker="SPY", sig=sig, total_score=4.0,
            strength="STRONG", size=0.10, strat_bonus=0,
            latest=latest, target=722.5, time_stop=30,
        )

    assert mock_upsert.called, "_persist_signal_alert MUST call upsert_dataframe"
    args, kwargs = mock_upsert.call_args
    df = args[0]
    table = args[1]
    keys = args[2]

    assert table == "signal_alerts", f"target table should be 'signal_alerts', got {table!r}"
    assert list(keys) == ["ticker", "alert_ts"], f"conflict keys should be ['ticker','alert_ts'], got {keys}"
    assert isinstance(df, pd.DataFrame), "first arg should be a DataFrame"
    assert len(df) == 1, f"should write exactly 1 row per signal, got {len(df)}"


def test_persist_dataframe_has_all_required_columns():
    """The DataFrame passed to upsert_dataframe must have every column
    that signal_alerts.* schema requires (or that any consumer reads)."""
    monitor = _make_monitor_with_mocked_persist()

    sig = {
        "direction": "PUT",
        "base_score": 3,
        "conditions_met": ["consecutive_up", "rsi_overbought_zone", "above_vwap"],
    }
    latest = _make_synthetic_latest_bar("PUT")

    with patch("gcp.database.upsert_dataframe") as mock_upsert, \
         patch("gcp.database.is_cloud_sql_configured", return_value=True):
        mock_upsert.return_value = 1

        monitor._persist_signal_alert(
            ticker="QQQ", sig=sig, total_score=3.5,
            strength="MODERATE", size=0.05, strat_bonus=0.5,
            latest=latest, target=672.0, time_stop=20,
        )

    df = mock_upsert.call_args[0][0]
    cols = set(df.columns)
    missing = REQUIRED_COLUMNS - cols
    assert not missing, (
        f"persist DataFrame missing required columns: {missing}. "
        f"Schema {REQUIRED_COLUMNS} must be present so signal_alerts rows are usable downstream."
    )

    row = df.iloc[0]
    assert row["ticker"] == "QQQ"
    assert row["direction"] == "PUT"
    assert row["base_score"] == 3
    assert row["total_score"] == pytest.approx(3.5)
    # Track D audit § 6 / G.P0.6: `conditions_met` must reach upsert as a
    # native Python list so SQLAlchemy + pg8000 bind it to a JSONB array.
    # The pre-fix code did `json.dumps(...)` first, which bound a JSONB
    # scalar string (`"[\"a\",\"b\"]"`), breaking `jsonb_array_length` /
    # `@>` predicates downstream.
    assert isinstance(row["conditions_met"], list), \
        f"conditions_met must be a Python list (not str) so it binds as JSONB array; got {type(row['conditions_met']).__name__}"
    assert all(isinstance(c, str) for c in row["conditions_met"]), \
        "every condition entry must be a string"


def test_persist_skipped_when_cloud_sql_not_configured():
    """If Cloud SQL is not configured (local dev), persist should
    early-return without raising. Catches the case where deploy.sh
    was misconfigured and Cloud SQL env vars are missing."""
    monitor = _make_monitor_with_mocked_persist()

    sig = {
        "direction": "CALL", "base_score": 3,
        "conditions_met": ["consecutive_down", "rsi_oversold_zone", "below_vwap"],
    }
    latest = _make_synthetic_latest_bar("CALL")

    with patch("gcp.database.upsert_dataframe") as mock_upsert, \
         patch("gcp.database.is_cloud_sql_configured", return_value=False):

        # Should not raise
        monitor._persist_signal_alert(
            ticker="SPY", sig=sig, total_score=3.0, strength="WEAK",
            size=0.05, strat_bonus=0, latest=latest, target=721.0, time_stop=15,
        )

    assert not mock_upsert.called, (
        "When Cloud SQL is not configured, upsert MUST NOT be called "
        "(prevents spurious connection attempts in local dev)"
    )


def test_persist_logs_warning_but_does_not_raise_on_upsert_failure():
    """If upsert raises (network blip, schema mismatch), persist must
    log the warning and return — NOT crash the monitor loop. The 4/14
    incident was the opposite case (silent success) but this guard is
    important so a single bad row doesn't kill the whole session."""
    monitor = _make_monitor_with_mocked_persist()

    sig = {
        "direction": "CALL", "base_score": 3,
        "conditions_met": ["consecutive_down", "rsi_oversold_zone", "below_vwap"],
    }
    latest = _make_synthetic_latest_bar("CALL")

    with patch("gcp.database.upsert_dataframe", side_effect=RuntimeError("connection lost")) as mock_upsert, \
         patch("gcp.database.is_cloud_sql_configured", return_value=True):

        # Should swallow + log, not raise
        try:
            monitor._persist_signal_alert(
                ticker="IWM", sig=sig, total_score=3.0,
                strength="WEAK", size=0.05, strat_bonus=0,
                latest=latest, target=278.0, time_stop=15,
            )
        except RuntimeError:
            pytest.fail("_persist_signal_alert MUST NOT propagate upsert exceptions")

    assert mock_upsert.called, "should attempt the upsert even though it fails"
