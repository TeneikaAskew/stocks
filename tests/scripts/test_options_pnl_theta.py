"""Tests for the THETA_MODEL toggle in scripts/analysis/options_pnl_translation.

The recalibration (lib.options_intraday) redistributes 0DTE theta cost across the
session; THETA_MODEL=linear restores the legacy hold_min/1440 distribution so the
two can be diffed. return_pct=0 isolates theta from the delta P&L.
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.analysis.options_pnl_translation import estimate_options_pnl

_ATM = pd.Series({'mark': 3.0, 'bid': 2.95, 'ask': 3.05, 'delta': 0.5, 'theta': -1.30})
_D = '2026-06-10 '


def _trade(entry: str, exit_: str) -> pd.Series:
    hold_min = (pd.Timestamp(_D + exit_) - pd.Timestamp(_D + entry)).total_seconds() / 60.0
    return pd.Series({'entry_price': 100.0, 'return_pct': 0.0, 'direction': 'CALL',
                      'hold_min': hold_min,
                      'entry_time': pd.Timestamp(_D + entry),
                      'exit_time': pd.Timestamp(_D + exit_)})


def _theta_cost(trade, model, monkeypatch):
    monkeypatch.setenv('THETA_MODEL', model)
    return estimate_options_pnl(trade, _ATM)['theta_cost']


def test_linear_model_matches_legacy_formula(monkeypatch):
    t = _trade('11:00', '12:00')             # 60-min midday hold
    cost = _theta_cost(t, 'linear', monkeypatch)
    assert cost == pytest.approx(1.30 * (60.0 / 1440.0))   # |theta| * hold_min/1440


def test_empirical_redistributes_morning_vs_midday(monkeypatch):
    # Same 60-min hold: morning (open IV crush) must cost MORE than midday (lull).
    morning = _theta_cost(_trade('09:45', '10:45'), 'empirical', monkeypatch)
    midday = _theta_cost(_trade('12:30', '13:30'), 'empirical', monkeypatch)
    assert morning > midday


def test_terminal_cliff_costs_more_than_midday(monkeypatch):
    # A hold into the close eats the expiry cliff — pricier than a midday hold.
    into_close = _theta_cost(_trade('15:00', '16:00'), 'empirical', monkeypatch)
    midday = _theta_cost(_trade('12:30', '13:30'), 'empirical', monkeypatch)
    assert into_close > 2 * midday


def test_full_day_hold_is_magnitude_preserving(monkeypatch):
    # A full RTH hold must cost the same under both models (the recalibration
    # only redistributes the daily budget, it doesn't change it).
    t = _trade('09:30', '16:00')
    assert (_theta_cost(t, 'empirical', monkeypatch)
            == pytest.approx(_theta_cost(t, 'linear', monkeypatch)))


def test_default_model_is_empirical(monkeypatch):
    # No THETA_MODEL set -> empirical (differs from linear for a non-full-day hold).
    monkeypatch.delenv('THETA_MODEL', raising=False)
    default = estimate_options_pnl(_trade('12:30', '13:30'), _ATM)['theta_cost']
    linear = _theta_cost(_trade('12:30', '13:30'), 'linear', monkeypatch)
    assert default != pytest.approx(linear)
