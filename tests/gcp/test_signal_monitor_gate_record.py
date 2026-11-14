"""FEAT-SIGNAL-001: the live direction gate's decision is recorded on
every persisted signal_alerts row.

Spec: docs/superpowers/specs/2026-11-11-feat-signal-001-gate-decision-record.md

These tests drive the real evaluate_ticker fire path (direction gate
included) with a stubbed insight cache, then hand the fire to the real
_persist_signal_alert with upsert_dataframe mocked, and read the row it
would have written. No fire, score, strength or delivery behavior is
changed by the feature; the strength assertions below pin that.
"""
from __future__ import annotations

import logging
from unittest.mock import patch

import pandas as pd
import pytest

from lib.strategies.insight_cache import InsightContext


GATE_COLUMNS = (
    "gate_action", "gate_reason", "insight_direction",
    "insight_conviction", "insight_regime", "thesis_invalidated",
)


class _StubCache:
    """InsightCache stand-in: returns a fixed context per ticker."""

    def __init__(self, by_ticker):
        self.by_ticker = by_ticker

    def get(self, ticker, fetcher):
        return self.by_ticker.get(ticker)


class _RaisingCache:
    def get(self, ticker, fetcher):
        raise RuntimeError("insight fetch blew up")


def _ctx(ticker, direction, conviction="medium", regime="normal",
         invalidation_level=None):
    return InsightContext(
        ticker=ticker, direction=direction, conviction=conviction,
        regime=regime, invalidation_level=invalidation_level,
    )


def _make_monitor(mode="active", cache=None):
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    monitor.insight_gate_mode = mode
    monitor.insight_cache = cache or _StubCache({})
    monitor.strat_cfg.enabled = False
    for t in ("SPY", "QQQ", "IWM"):
        monitor.daily_trades[t] = 0
        monitor.daily_pnl[t] = 0.0
        monitor.orb_levels[t] = {}
    return monitor


def _bar():
    return pd.Series({
        "Close": 720.0, "Last": 720.0, "RSI14": 35.0, "RSI14_W": 35.0,
        "VWAP": 723.0, "EMA9": 722.0, "EMA20": 723.5, "StochRSI_K": 25.0,
        "Price_vs_VWAP": -0.42, "Price_vs_EMA9": -0.28,
        "Price_vs_EMA20": -0.49, "Consecutive_Down": 4, "Consecutive_Up": 0,
        "RVOL": 1.4, "ATR14": 1.2,
        "Broke_Prev_Day_Low": 0, "Broke_Prev_Day_High": 0,
    })


def _fire(monitor, ticker="SPY", direction="CALL", strength="medium"):
    """Run evaluate_ticker for one bar; return (row or None, fired strength).

    The fire is routed straight to the real _persist_signal_alert so the
    test sees exactly the row the monitor would upsert.
    """
    enriched = pd.DataFrame([_bar()] * 40).reset_index(drop=True)
    enriched.index = pd.date_range(
        "2026-11-09 14:30", periods=40, freq="1min", tz="UTC")
    sig = {"direction": direction, "base_score": 4,
           "conditions_met": ["consecutive_down", "below_vwap"]}
    captured = {}

    def fake_fire_alert(tkr, s, total_score, strn, size, strat_bonus, latest):
        captured["strength"] = strn
        monitor._persist_signal_alert(
            tkr, s, total_score, strn, size, strat_bonus, latest,
            target=722.5, time_stop=30)

    with patch.object(monitor, "calculate_indicators", return_value=enriched), \
         patch.object(monitor, "_evaluate_strategies_for_bar",
                      return_value=(sig, None)), \
         patch.object(monitor, "fire_alert", side_effect=fake_fire_alert), \
         patch.object(monitor, "check_orb"), \
         patch("gcp.signal_monitor.get_signal_strength_label",
               return_value=strength), \
         patch("lib.strategies.catalyst_proximity.get_catalyst_context",
               return_value={"proximity_bucket": "quiet"}), \
         patch("gcp.database.get_engine", return_value=None), \
         patch("gcp.database.is_cloud_sql_configured", return_value=True), \
         patch("gcp.database.upsert_dataframe", return_value=1) as upsert, \
         patch("gcp.trade_logger.TradeLogger"):
        monitor.evaluate_ticker(ticker)

    if not upsert.called:
        return None, captured.get("strength")
    df = upsert.call_args[0][0]
    assert upsert.call_args[0][1] == "signal_alerts"
    return df.iloc[0].to_dict(), captured.get("strength")


def _none(v):
    return v is None or (isinstance(v, float) and pd.isna(v))


# ── each gate outcome that fires ────────────────────────────────────

@pytest.mark.parametrize("insight_dir, strength, action, reason, fired_strength", [
    ("long",  "medium", "pass",      "aligned_with_plan_long",          "medium"),
    ("short", "medium", "downgrade", "opposing_medium_vs_plan_short",   "weak"),
    ("short", "strong", "tag",       "opposing_strong_vs_plan_short_kept", "strong"),
    ("flat",  "weak",   "annotate",  "flat_day_weak_momentum_passthrough", "weak"),
])
def test_row_records_gate_decision_and_insight(insight_dir, strength, action,
                                                reason, fired_strength):
    monitor = _make_monitor(cache=_StubCache(
        {"SPY": _ctx("SPY", insight_dir, conviction="high", regime="extended")}))
    row, fired = _fire(monitor, strength=strength)
    assert row is not None
    assert row["gate_action"] == action
    assert row["gate_reason"] == reason
    assert row["insight_direction"] == insight_dir
    assert row["insight_conviction"] == "high"
    assert row["insight_regime"] == "extended"
    assert fired == fired_strength


def test_row_without_insight_records_annotate_and_null_insight():
    monitor = _make_monitor(cache=_StubCache({}))
    row, fired = _fire(monitor, strength="medium")
    assert row["gate_action"] == "annotate"
    assert row["gate_reason"] == "no_insight_available"
    for col in ("insight_direction", "insight_conviction", "insight_regime",
                "thesis_invalidated"):
        assert _none(row[col]), col
    assert fired == "medium"


def test_suppressed_fire_writes_no_row():
    monitor = _make_monitor(cache=_StubCache({"SPY": _ctx("SPY", "short")}))
    row, fired = _fire(monitor, strength="weak")
    assert row is None and fired is None


# ── no stale decision, disabled, raising gate ───────────────────────

def test_no_stale_decision_across_tickers():
    monitor = _make_monitor(cache=_StubCache({
        "QQQ": _ctx("QQQ", "short", conviction="medium", regime="extended"),
    }))
    first, _ = _fire(monitor, ticker="QQQ", strength="strong")
    assert first["gate_action"] == "tag"
    second, _ = _fire(monitor, ticker="SPY", strength="medium")
    assert second["gate_action"] == "annotate"
    assert second["gate_reason"] == "no_insight_available"
    assert _none(second["insight_direction"])
    assert _none(second["insight_regime"])


def test_disabled_mode_leaves_all_gate_columns_null():
    monitor = _make_monitor(mode="disabled",
                            cache=_StubCache({"SPY": _ctx("SPY", "short")}))
    # Seed a stale stash as a previous fire would have left it.
    monitor._latest_gate_action = "tag"
    monitor._latest_gate_reason = "stale"
    monitor._latest_insight_ctx = _ctx("SPY", "short")
    row, fired = _fire(monitor, strength="weak")
    assert row is not None, "disabled gate must not suppress"
    for col in GATE_COLUMNS:
        assert _none(row[col]), col
    assert fired == "weak"


def test_raising_gate_leaves_columns_null_and_fire_proceeds():
    monitor = _make_monitor(cache=_RaisingCache())
    monitor._latest_gate_action = "pass"
    row, fired = _fire(monitor, strength="medium")
    assert row is not None
    for col in GATE_COLUMNS:
        assert _none(row[col]), col
    assert fired == "medium"


# ── shadow mode ─────────────────────────────────────────────────────

def test_shadow_mode_records_would_have_decision_without_applying_it():
    monitor = _make_monitor(mode="shadow",
                            cache=_StubCache({"SPY": _ctx("SPY", "short")}))
    row, fired = _fire(monitor, strength="medium")
    assert row["gate_action"] == "downgrade"
    assert row["gate_reason"] == "shadow:opposing_medium_vs_plan_short"
    assert fired == "medium", "shadow must not change strength"

    row, fired = _fire(monitor, strength="weak")
    assert row is not None, "shadow must not suppress"
    assert row["gate_action"] == "suppress"
    assert row["gate_reason"] == "shadow:opposing_weak_vs_plan_short"
    assert fired == "weak"


# ── width truncation ────────────────────────────────────────────────

def test_over_width_insight_values_are_truncated_with_warning(caplog):
    monitor = _make_monitor(cache=_StubCache({"SPY": _ctx(
        "SPY", "long_bias_x", conviction="very_high_x",
        regime="gap_faded_extended_session_x")}))
    with caplog.at_level(logging.WARNING, logger="gcp.signal_monitor"):
        row, _ = _fire(monitor, strength="medium")
    assert row is not None, "the signal_alerts row must still be written"
    assert row["insight_direction"] == "long_bia"
    assert row["insight_conviction"] == "very_hig"
    assert row["insight_regime"] == "gap_faded_extended_s"
    assert len(row["insight_regime"]) == 20
    trunc = [r for r in caplog.records if "truncated" in r.getMessage()]
    assert {m for r in trunc for m in ("insight_direction", "insight_conviction",
                                       "insight_regime") if m in r.getMessage()} \
        == {"insight_direction", "insight_conviction", "insight_regime"}
    assert len(trunc) == 3, "one warning line per truncated column"


# ── thesis_invalidated ──────────────────────────────────────────────

def test_thesis_invalidated_null_without_invalidation_level():
    monitor = _make_monitor(cache=_StubCache({"SPY": _ctx("SPY", "long")}))
    row, _ = _fire(monitor, strength="medium")
    assert _none(row["thesis_invalidated"]), "never a fabricated FALSE"


def test_thesis_invalidated_bool_with_invalidation_level():
    monitor = _make_monitor(cache=_StubCache(
        {"SPY": _ctx("SPY", "long", invalidation_level=710.0)}))
    row, _ = _fire(monitor, strength="medium")
    assert row["thesis_invalidated"] is False or row["thesis_invalidated"] == False  # noqa: E712
    assert not _none(row["thesis_invalidated"])

    monitor.insight_invalidated["SPY"] = True
    row, _ = _fire(monitor, strength="medium")
    assert row["thesis_invalidated"] == True  # noqa: E712
    assert row["gate_action"] == "annotate"
    assert row["gate_reason"] == "thesis_invalidated_at_price_level"
