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
from datetime import date

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


def test_resolver_failure_fails_closed(monkeypatch, caplog):
    """Audit C-04 (docs/audits/FALLBACK_AUDIT_2026-05-13.md 12.1) was
    marked OPEN: a resolver failure evaluated "with NO disabled conditions
    or directions applied", so a side an operator switched OFF for risk
    fired anyway. The decision is now taken the safe way round: when the
    kill switch cannot be read, no mean-reversion signal fires for that
    bar, and the failure is logged at ERROR with its traceback."""
    import logging

    from lib.strategies import exit_config_overrides as eco
    eco._latest_overrides.cache_clear()

    def _boom(t):
        raise RuntimeError("connection lost")

    monkeypatch.setattr(eco, "_latest_overrides", _boom)
    row = _put_row()
    row["Broke_Prev_Day_Low"] = 1
    with caplog.at_level(logging.ERROR, logger="lib.signals"):
        sig = evaluate_signal(row, min_conditions=3, ticker="QQQ")
    assert sig is None, "an unreadable kill switch must not read as open"
    assert "connection lost" in caplog.text and "Traceback" in caplog.text


def test_malformed_disabled_conditions_fails_closed(monkeypatch, caplog):
    import logging

    from lib.strategies import exit_config_overrides as eco
    eco._latest_overrides.cache_clear()
    monkeypatch.setattr(eco, "_latest_overrides", lambda t: {
        "disabled_conditions": "not json", "disabled_directions": None})
    row = _put_row()
    row["Broke_Prev_Day_Low"] = 1
    with caplog.at_level(logging.ERROR, logger="lib.signals"):
        assert evaluate_signal(row, min_conditions=3, ticker="QQQ") is None
    assert "disabled_conditions" in caplog.text


def test_a_failed_override_query_fails_closed_not_open(monkeypatch, caplog):
    """The fail-closed handler above was UNREACHABLE for the failure it was
    written for (Codex on #1022).

    `_latest_overrides` caught every exception from the Cloud SQL read and
    returned None, so `get_disabled_directions` saw "no row", answered
    `set()` = nothing disabled, and evaluation carried on. The swallow one
    level down defeated the strict caller one level up, which is the exact
    shape CLAUDE.md 3.7.1 warns about. This test drives the real failure —
    the query itself raising — rather than a malformed value."""
    import logging

    from lib.strategies import exit_config_overrides as eco
    eco._latest_overrides.cache_clear()

    from gcp import database as gcp_db
    monkeypatch.setattr(gcp_db, "is_cloud_sql_configured", lambda: True)

    def _boom(*a, **k):
        raise RuntimeError("connection lost")

    monkeypatch.setattr("pandas.read_sql", _boom)
    monkeypatch.setattr(gcp_db, "get_engine", lambda: object())

    row = _put_row()
    row["Broke_Prev_Day_Low"] = 1
    with caplog.at_level(logging.ERROR, logger="lib.signals"):
        sig = evaluate_signal(row, min_conditions=3, ticker="QQQ")
    assert sig is None, "an unreadable kill switch must not read as open"
    assert "connection lost" in caplog.text
    eco._latest_overrides.cache_clear()


def test_one_failed_read_does_not_disable_the_kill_switch_for_the_process(monkeypatch):
    """`_latest_overrides` is lru_cached, so the swallowed None was CACHED:
    a single transient failure turned the kill switch off for the rest of
    the process, and the next 390 bars of the session fired as though
    nothing were disabled. A raise is not cached, so the read is retried."""
    import pandas as pd

    from lib.strategies import exit_config_overrides as eco
    eco._latest_overrides.cache_clear()
    from gcp import database as gcp_db
    monkeypatch.setattr(gcp_db, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(gcp_db, "get_engine", lambda: object())

    calls = {"n": 0}
    good = pd.DataFrame([{
        "calibration_date": date.today(), "call_target": None, "put_target": None,
        "call_stop": None, "put_stop": None, "call_time_stop": None,
        "put_time_stop": None, "consecutive_periods": None,
        "disabled_conditions": None, "disabled_directions": ["PUT"],
        "blue_sky_atr_offset": None, "notes": None,
    }])

    def _flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("connection lost")
        return good

    monkeypatch.setattr("pandas.read_sql", _flaky)

    import pytest
    with pytest.raises(Exception):
        eco.get_disabled_directions("QQQ")
    # Second call must reach the database again, not replay a cached failure.
    assert eco.get_disabled_directions("QQQ") == {"PUT"}
    assert calls["n"] == 2
    eco._latest_overrides.cache_clear()


def test_the_tier_b_getters_still_degrade_on_a_failed_read(monkeypatch):
    """The exit-target getters are deliberately lenient: Tier-B defaults are
    the documented answer when no usable override exists, and a read failure
    must not take fire_alert down. Their leniency is now explicit at each
    call site instead of a blanket swallow, so this pins it."""
    from lib.strategies import exit_config_overrides as eco
    from lib.config import ExitConfig, SignalConfig
    eco._latest_overrides.cache_clear()
    from gcp import database as gcp_db
    monkeypatch.setattr(gcp_db, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(gcp_db, "get_engine", lambda: object())

    def _boom(*a, **k):
        raise RuntimeError("connection lost")

    monkeypatch.setattr("pandas.read_sql", _boom)

    defaults = ExitConfig()
    assert eco.get_call_target("QQQ") == defaults.call_target
    assert eco.get_put_stop("QQQ") == defaults.put_stop
    # This knob's Tier-B default lives in SignalConfig, not ExitConfig.
    assert eco.get_consecutive_periods("QQQ") == SignalConfig().consecutive_periods
    assert eco.get_blue_sky_atr_offset("QQQ") is None
    assert eco.get_resolution_tier("QQQ", "call_target") == "B"
    eco._latest_overrides.cache_clear()
