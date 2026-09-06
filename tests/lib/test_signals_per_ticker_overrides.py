"""Regression tests for the per-ticker overrides wired into
`lib/signals.py:evaluate_signal` (Track A G.P0.12 + G.P0.13 + G.P1.19).

PR #329 wired `disabled_conditions` into the offline
`MeanReversionStrategy._check_put_conditions` path but the LIVE signal
path through `lib/signals.py:evaluate_signal` was never patched. The
2026-05-09 validation caught this — 5/8 alerts still listed
`above_vwap` on 95/98 IWM PUTs.

This test suite locks both:
1. `disabled_conditions` strips matching factor names from scoring
   pre-min_conditions check
2. `disabled_directions` returns None for the disabled side regardless
   of score (G.P1.19 — disable QQQ MR PUT entirely)
"""
from __future__ import annotations

import pandas as pd
import pytest

from lib.signals import evaluate_signal


def _put_row():
    """A row that scores 4-5 conditions on the PUT side."""
    return pd.Series({
        "Consecutive_Up": 4, "Consecutive_Down": 0,
        "RSI14": 65.0,
        "Price_vs_VWAP": 0.5, "Price_vs_EMA9": 0.2,
        "StochRSI_K": 80.0,
        "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 0,
    })


def _call_row():
    """A row that scores 4-5 conditions on the CALL side."""
    return pd.Series({
        "Consecutive_Down": 4, "Consecutive_Up": 0,
        "RSI14": 35.0,
        "Price_vs_VWAP": -0.5, "Price_vs_EMA9": -0.2,
        "StochRSI_K": 20.0,
        "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 0,
    })


# ─── disabled_conditions wiring (PR #329 missed live path) ──────────


def test_disabled_conditions_strips_above_vwap_globally(monkeypatch):
    """G.P0.12: above_vwap is a -16pp anti-signal on every ticker's
    MR PUT side. With ticker='SPY' and SPY's overrides set to disable
    above_vwap, the PUT score should NOT include it."""
    from lib.strategies import exit_config_overrides as eco
    eco._latest_overrides.cache_clear()

    monkeypatch.setattr(
        eco, "_latest_overrides",
        lambda t: {
            "calibration_date": __import__("datetime").date.today(),
            "disabled_conditions": ["above_vwap"],
            "disabled_directions": None,
            "call_target": 0.00184, "put_target": 0.00202,
            "call_stop": 0.00075, "put_stop": 0.00075,
            "call_time_stop": 25, "put_time_stop": 25,
            "blue_sky_atr_offset": 0.15, "notes": "test",
        },
    )

    sig = evaluate_signal(_put_row(), min_conditions=3, ticker="SPY")
    assert sig is not None
    assert "above_vwap" not in sig["conditions_met"], (
        "above_vwap must be stripped from the live path's PUT scoring "
        "when ticker has it in disabled_conditions."
    )


def test_disabled_conditions_string_jsonb_form_handled(monkeypatch):
    """conditions_met round-trips as JSONB; the column may come back
    as a Python list OR (legacy pre-#308 rows) a JSON-encoded string."""
    from lib.strategies import exit_config_overrides as eco
    eco._latest_overrides.cache_clear()

    monkeypatch.setattr(
        eco, "_latest_overrides",
        lambda t: {
            "calibration_date": __import__("datetime").date.today(),
            "disabled_conditions": '["above_vwap"]',  # JSON-encoded string
            "disabled_directions": None,
            "call_target": 0.00184, "put_target": 0.00202,
            "call_stop": 0.00075, "put_stop": 0.00075,
            "call_time_stop": 25, "put_time_stop": 25,
            "blue_sky_atr_offset": 0.15, "notes": "test",
        },
    )

    sig = evaluate_signal(_put_row(), min_conditions=3, ticker="SPY")
    assert sig is not None
    assert "above_vwap" not in sig["conditions_met"]


def test_disabled_conditions_drops_score_below_threshold(monkeypatch):
    """If enough conditions are disabled to push score below
    min_conditions, the side falls through to None."""
    from lib.strategies import exit_config_overrides as eco
    eco._latest_overrides.cache_clear()

    # Disable 3 of 5 PUT conditions — leaves 2, below min=3.
    monkeypatch.setattr(
        eco, "_latest_overrides",
        lambda t: {
            "calibration_date": __import__("datetime").date.today(),
            "disabled_conditions": [
                "above_vwap", "stoch_rsi_overbought", "rsi_overbought_zone",
            ],
            "disabled_directions": None,
            "call_target": 0.00184, "put_target": 0.00202,
            "call_stop": 0.00075, "put_stop": 0.00075,
            "call_time_stop": 25, "put_time_stop": 25,
            "blue_sky_atr_offset": 0.15, "notes": "test",
        },
    )

    sig = evaluate_signal(_put_row(), min_conditions=3, ticker="IWM")
    # PUT had 4 conditions; -3 = 1, below min=3 → None.
    # Row's CALL side scores 0 (it's a pure-PUT row), so total None.
    assert sig is None


# ─── disabled_directions kill switch (G.P1.19 new) ────────────────────


def test_disabled_directions_qqq_put_kill_switch(monkeypatch):
    """G.P1.19: QQQ MR PUT has 11.1% win-rate, the worst in the system.
    Disable PUT entirely until rebuild — even a 5/5 PUT score returns
    None instead of firing."""
    from lib.strategies import exit_config_overrides as eco
    eco._latest_overrides.cache_clear()

    monkeypatch.setattr(
        eco, "_latest_overrides",
        lambda t: {
            "calibration_date": __import__("datetime").date.today(),
            "disabled_conditions": None,
            "disabled_directions": ["PUT"],
            "call_target": 0.00301, "put_target": 0.00238,
            "call_stop": 0.00075, "put_stop": 0.00075,
            "call_time_stop": 20, "put_time_stop": 25,
            "blue_sky_atr_offset": 0.20, "notes": "QQQ kill switch",
        },
    )

    # Row that would score 5/5 on PUT — must still return None.
    row = _put_row()
    row["Broke_Prev_Day_Low"] = 1  # bumps to 5/5
    sig = evaluate_signal(row, min_conditions=3, ticker="QQQ")
    assert sig is None, (
        "QQQ PUT must NOT fire when disabled_directions includes 'PUT', "
        "regardless of score."
    )


def test_disabled_directions_does_not_block_other_side(monkeypatch):
    """QQQ has PUT disabled, but a strong CALL signal must still fire."""
    from lib.strategies import exit_config_overrides as eco
    eco._latest_overrides.cache_clear()

    monkeypatch.setattr(
        eco, "_latest_overrides",
        lambda t: {
            "calibration_date": __import__("datetime").date.today(),
            "disabled_conditions": None,
            "disabled_directions": ["PUT"],
            "call_target": 0.00301, "put_target": 0.00238,
            "call_stop": 0.00075, "put_stop": 0.00075,
            "call_time_stop": 20, "put_time_stop": 25,
            "blue_sky_atr_offset": 0.20, "notes": "test",
        },
    )

    sig = evaluate_signal(_call_row(), min_conditions=3, ticker="QQQ")
    assert sig is not None
    assert sig["direction"] == "CALL"


def test_disabled_directions_jsonb_string_form_handled(monkeypatch):
    from lib.strategies import exit_config_overrides as eco
    eco._latest_overrides.cache_clear()

    monkeypatch.setattr(
        eco, "_latest_overrides",
        lambda t: {
            "calibration_date": __import__("datetime").date.today(),
            "disabled_conditions": None,
            "disabled_directions": '["PUT"]',  # JSON string
            "call_target": 0.00301, "put_target": 0.00238,
            "call_stop": 0.00075, "put_stop": 0.00075,
            "call_time_stop": 20, "put_time_stop": 25,
            "blue_sky_atr_offset": 0.20, "notes": "test",
        },
    )

    row = _put_row()
    sig = evaluate_signal(row, min_conditions=3, ticker="QQQ")
    assert sig is None


def test_no_ticker_means_no_overrides(monkeypatch):
    """Legacy callers / backtests pass ticker=None — behaviour must be
    unchanged from pre-#329."""
    sig = evaluate_signal(_put_row(), min_conditions=3, ticker=None)
    assert sig is not None
    assert sig["direction"] == "PUT"
    assert "above_vwap" in sig["conditions_met"]  # not stripped


def test_resolver_failure_degrades_gracefully(monkeypatch):
    """If the resolver raises (network blip, table missing), the live
    path must not crash — silently degrade to legacy behaviour."""
    from lib.strategies import exit_config_overrides as eco
    eco._latest_overrides.cache_clear()

    def _boom(t):
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(eco, "_latest_overrides", _boom)

    sig = evaluate_signal(_put_row(), min_conditions=3, ticker="QQQ")
    # Should still fire — fallback to legacy path despite resolver failure.
    assert sig is not None
    assert sig["direction"] == "PUT"
