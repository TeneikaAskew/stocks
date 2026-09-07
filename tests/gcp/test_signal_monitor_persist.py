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


# ── CLAUDE.md 3.7 on the persisted row (internal review of #1022) ────────

def _persist(monitor, latest, **patches):
    sig = {"direction": "CALL", "base_score": 4,
           "conditions_met": ["consecutive_down", "rsi_oversold_zone"]}
    upsert = patches.get("upsert") or MagicMock(return_value=1)
    logged: list = []

    class _TL:
        def log_trade(self, trade_data):
            if patches.get("trade_raises"):
                raise RuntimeError("parquet write failed")
            logged.append(trade_data)

    with patch("gcp.database.upsert_dataframe", upsert), \
         patch("gcp.database.is_cloud_sql_configured", return_value=True), \
         patch("gcp.trade_logger.TradeLogger", _TL):
        monitor._persist_signal_alert(
            ticker="SPY", sig=sig, total_score=4.0, strength="STRONG", size=0.10,
            strat_bonus=0, latest=latest, target=722.5, time_stop=30)
    row = upsert.call_args[0][0].iloc[0] if upsert.call_args else None
    return row, logged


def test_persisted_rsi_and_rvol_are_null_when_the_bar_has_none():
    """fire_alert refuses `.get('RVOL', 0)` for the gate (its comment cites
    3.7) and then _persist_signal_alert wrote rvol=0.0 and rsi=0.0 into the
    columns the out-of-sample GROUP BY reads, indistinguishable from a real
    zero-volume minute or an RSI of 0."""
    monitor = _make_monitor_with_mocked_persist()
    latest = _make_synthetic_latest_bar("CALL").drop(labels=["RSI14"])
    latest["RVOL"] = float("nan")
    row, logged = _persist(monitor, latest)
    assert row["rsi"] is None or pd.isna(row["rsi"]), row["rsi"]
    assert row["rvol"] is None or pd.isna(row["rvol"]), row["rvol"]
    assert row["price_at_signal"] == 720.0
    assert logged[0]["entry_price"] == 720.0 and logged[0]["run_kind"] == "live"


def test_persist_raises_when_the_bar_has_no_price():
    """A bar with neither Close nor Last cannot have fired; writing
    entry_price=0.0 (the old `.get(k, 0)`) fabricated a trade at $0. That
    is an INTERNAL invariant, so it raises instead."""
    monitor = _make_monitor_with_mocked_persist()
    latest = _make_synthetic_latest_bar("CALL").drop(labels=["Close", "Last"])
    with pytest.raises(ValueError, match="Close"):
        _persist(monitor, latest)


def test_persist_uses_the_monitor_clock_for_alert_ts():
    """alert_ts came from datetime.now() rather than the monitor's clock; a
    replay that persists through this path would have stamped wall-clock."""
    monitor = _make_monitor_with_mocked_persist()
    monitor.replay_clock_ts = pd.Timestamp("2026-08-28 14:31:00")
    row, logged = _persist(monitor, _make_synthetic_latest_bar("CALL"))
    assert pd.Timestamp(row["alert_ts"]) == pd.Timestamp("2026-08-28 14:31:00"), row["alert_ts"]
    assert str(row["alert_date"]) == "2026-08-28"
    assert logged[0]["trade_date"] == "2026-08-28"


def test_persist_failures_are_counted_and_logged_with_traceback(caplog):
    """Both writes swallowed their failure at logger.warning with no
    counter, so a day of silent write failures looked like a quiet day
    (the 4/14-4/30 gap shape). They now increment structured counters and
    log the exception; the monitor loop still continues."""
    import logging
    monitor = _make_monitor_with_mocked_persist()
    latest = _make_synthetic_latest_bar("CALL")
    with caplog.at_level(logging.ERROR, logger="gcp.signal_monitor"):
        _persist(monitor, latest, upsert=MagicMock(side_effect=RuntimeError("connection lost")),
                 trade_raises=True)
    assert monitor.persist_alert_failure_count["SPY"] == 1
    assert monitor.persist_trade_failure_count["SPY"] == 1
    assert "connection lost" in caplog.text and "parquet write failed" in caplog.text
    assert "Traceback" in caplog.text
