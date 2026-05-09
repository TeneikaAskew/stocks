"""Tests for #369 — momentum stand-alone evaluation.

Pre-#369 `_evaluate_strategies_for_bar` short-circuited at line 452
when mean-reversion didn't fire, so MOMENTUM.evaluate was never
called for mr-no-fire bars. The orchestration excluded momentum
structurally; the `momentum_evaluated_count` counter was biased to
the mr-fires intersection only.

Post-#369:
  - momentum is ALWAYS evaluated (counter increments every bar)
  - when mr misses but momentum fires AND `signal_cfg.enable_standalone_momentum=True`,
    the function returns a momentum-adapter dict so downstream consumers
    work without per-strategy mapping
  - flag defaults False → no production behavior change until policy review
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pandas as pd
import pytest


def _make_monitor():
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    return monitor


def _bar(**overrides):
    """Minimal bar that does NOT trigger mr default fires."""
    base = {
        "Close": 720.0, "Last": 720.0,
        "RSI14": 50.0, "RSI14_W": 50.0,
        "VWAP": 720.0, "EMA9": 720.0, "EMA20": 720.0,
        "StochRSI_K": 50.0,
        "Price_vs_VWAP": 0.0, "Price_vs_EMA9": 0.0, "Price_vs_EMA20": 0.0,
        "Consecutive_Down": 0, "Consecutive_Up": 0,
        "RVOL": 1.0, "ATR14": 1.0,
        "Time": pd.Timestamp("2026-05-09 13:30:00"),
    }
    base.update(overrides)
    return pd.Series(base)


# ── 1) Adapter shape ──────────────────────────────────────────────────


def test_momentum_signal_to_dict_field_mapping():
    """The adapter mirrors the 5 keys mr's evaluate_signal returns."""
    from gcp.signal_monitor import SignalMonitor
    from lib.strategies.base import Signal

    sig = Signal(
        strategy="momentum",
        direction="CALL",
        timestamp=pd.Timestamp("2026-05-09 13:45:00"),
        entry_price=720.50,
        base_score=5.0,
        weighted_score=6.5,
        conditions_met=["above_vwap", "above_ema9", "rvol_above_recent",
                         "atr_expansion", "rsi_thrust"],
        core_count=2,
    )
    out = SignalMonitor._momentum_signal_to_dict(sig)
    assert out["direction"] == "CALL"
    assert out["base_score"] == 5.0
    assert out["strat_bonus"] == 0
    assert out["total_score"] == 6.5
    assert out["conditions_met"] == [
        "above_vwap", "above_ema9", "rvol_above_recent",
        "atr_expansion", "rsi_thrust",
    ]
    # caller-supplied strat_bonus passes through
    out2 = SignalMonitor._momentum_signal_to_dict(sig, strat_bonus=2)
    assert out2["strat_bonus"] == 2


# ── 2) momentum is evaluated on EVERY bar ─────────────────────────────


def test_momentum_evaluated_when_mr_misses():
    """Pre-#369: counter only bumped when mr fired. Post-#369: every bar."""
    monitor = _make_monitor()
    ticker = monitor.tickers[0]
    before = monitor.momentum_evaluated_count[ticker]
    with patch("gcp.signal_monitor.evaluate_signal", return_value=None) as mr_mock, \
         patch("gcp.signal_monitor.MOMENTUM") as mom_mock:
        mom_mock.evaluate.return_value = None
        monitor._evaluate_strategies_for_bar(_bar(), 720.0, ticker)

    assert mr_mock.called, "mr should be evaluated"
    assert mom_mock.evaluate.called, "momentum should be evaluated even when mr missed"
    assert monitor.momentum_evaluated_count[ticker] == before + 1


# ── 3) flag OFF: momentum-only fire returns None ──────────────────────


def test_standalone_momentum_blocked_when_flag_off():
    """Default config (flag=False) preserves pre-#369 behavior:
    even if momentum fires stand-alone, no fire is returned."""
    monitor = _make_monitor()
    monitor.signal_cfg.enable_standalone_momentum = False
    ticker = monitor.tickers[0]
    from lib.strategies.base import Signal

    mom_signal = Signal(
        strategy="momentum", direction="CALL",
        timestamp=pd.Timestamp.now(), entry_price=720.0,
        base_score=5.0, weighted_score=5.0,
        conditions_met=["above_vwap", "rvol_above_recent",
                        "atr_expansion", "rsi_thrust", "above_ema9"],
        core_count=2,
    )
    with patch("gcp.signal_monitor.evaluate_signal", return_value=None), \
         patch("gcp.signal_monitor.MOMENTUM") as mom_mock:
        mom_mock.evaluate.return_value = mom_signal
        sig, agreement = monitor._evaluate_strategies_for_bar(_bar(), 720.0, ticker)

    assert sig is None, "flag OFF must NOT fire momentum stand-alone"
    assert agreement is None
    # but the counter still bumped — the eligibility data remains observable
    assert monitor.momentum_fired_count[ticker] == 1


# ── 4) flag ON: momentum-only fire returns adapter dict ───────────────


def test_standalone_momentum_fires_when_flag_on():
    """With flag flipped, mr-misses + momentum-fires returns the adapter dict."""
    monitor = _make_monitor()
    monitor.signal_cfg.enable_standalone_momentum = True
    ticker = monitor.tickers[0]
    from lib.strategies.base import Signal

    mom_signal = Signal(
        strategy="momentum", direction="PUT",
        timestamp=pd.Timestamp.now(), entry_price=720.0,
        base_score=5.0, weighted_score=5.5,
        conditions_met=["below_vwap", "below_ema9", "rsi_thrust",
                        "rvol_above_recent", "atr_expansion"],
        core_count=2,
    )
    with patch("gcp.signal_monitor.evaluate_signal", return_value=None), \
         patch("gcp.signal_monitor.MOMENTUM") as mom_mock:
        mom_mock.evaluate.return_value = mom_signal
        sig, agreement = monitor._evaluate_strategies_for_bar(_bar(), 720.0, ticker)

    assert sig is not None, "flag ON must let momentum fire stand-alone"
    # adapter dict shape — keys mirror mr
    assert sig["direction"] == "PUT"
    assert sig["base_score"] == 5.0
    assert sig["total_score"] == 5.5
    assert sig["strat_bonus"] == 0
    assert "below_vwap" in sig["conditions_met"]
    # no agreement (no mr to agree with)
    assert agreement is None


# ── 5) mr-fire path unchanged ─────────────────────────────────────────


def test_mr_fire_path_unchanged_post_369():
    """When mr fires, the function returns the mr dict — same shape +
    semantics as pre-#369 (regression check)."""
    monitor = _make_monitor()
    ticker = monitor.tickers[0]

    mr_dict = {
        "direction": "CALL", "base_score": 4, "strat_bonus": 0,
        "total_score": 4, "conditions_met": ["below_vwap", "rsi_oversold_zone",
                                              "stoch_rsi_oversold"],
    }
    with patch("gcp.signal_monitor.evaluate_signal", return_value=mr_dict), \
         patch("gcp.signal_monitor.MOMENTUM") as mom_mock:
        mom_mock.evaluate.return_value = None
        sig, agreement = monitor._evaluate_strategies_for_bar(_bar(), 720.0, ticker)

    assert sig == mr_dict, "mr-fire path must return the mr dict unchanged"
    assert agreement is None  # only mr fired


# ── 6) agreement path: both fire same direction ───────────────────────


def test_agreement_payload_when_both_fire_same_direction():
    """Both strategies fire CALL → agreement payload populated."""
    monitor = _make_monitor()
    ticker = monitor.tickers[0]
    from lib.strategies.base import Signal

    mr_dict = {
        "direction": "CALL", "base_score": 4, "strat_bonus": 0,
        "total_score": 4, "conditions_met": ["below_vwap", "rsi_oversold_zone"],
    }
    mom_signal = Signal(
        strategy="momentum", direction="CALL",
        timestamp=pd.Timestamp.now(), entry_price=720.0,
        base_score=5.0, weighted_score=5.0,
        conditions_met=["above_vwap", "rvol_above_recent", "atr_expansion",
                        "rsi_thrust", "above_ema9"],
        core_count=2,
    )
    with patch("gcp.signal_monitor.evaluate_signal", return_value=mr_dict), \
         patch("gcp.signal_monitor.MOMENTUM") as mom_mock:
        mom_mock.evaluate.return_value = mom_signal
        sig, agreement = monitor._evaluate_strategies_for_bar(_bar(), 720.0, ticker)

    assert sig == mr_dict
    assert agreement is not None  # detect_agreement returned a dict


# ── 7) flag default is False ──────────────────────────────────────────


def test_flag_default_is_false():
    """No-config-change default: flag is OFF until alert_config.json is edited."""
    from lib.config import SignalConfig
    cfg = SignalConfig()
    assert cfg.enable_standalone_momentum is False
