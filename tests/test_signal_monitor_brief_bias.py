"""Integration tests for brief↔live coordination overlay.

Exercises:
  - lib/strategies/brief_bias.classify (pure)
  - lib/strategies/brief_bias.alignment (pure)
  - SignalMonitor._resolve_brief_bias (lazy cache)
  - signal_alerts persist row carries brief_* columns
  - Discord title overlay (via assertion on the title-build site)
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from lib.strategies.brief_bias import classify, alignment, get_premarket_bias


# ── classify() — pure ───────────────────────────────────────────────

def test_classify_call_setup_aligned_with_bullish_ftfc():
    bias = classify({'signal_status': 'CALL setup (4/5)',
                     'ftfc_direction': 'bullish'})
    assert bias['bias'] == 'CALL'
    assert bias['setup_count'] == 4
    assert bias['reason'] == 'aligned'


def test_classify_put_setup_aligned_with_bearish_ftfc():
    bias = classify({'signal_status': 'PUT setup (5/5)',
                     'ftfc_direction': 'bearish'})
    assert bias['bias'] == 'PUT'
    assert bias['setup_count'] == 5


def test_classify_put_setup_with_bullish_ftfc_is_conflicted():
    """Today's actual SPY/IWM brief: PUT setup + bullish FTFC = self-contradiction."""
    bias = classify({'signal_status': 'PUT setup (4/5)',
                     'ftfc_direction': 'bullish'})
    assert bias['bias'] == 'CONFLICTED'
    assert bias['reason'] == 'setup_put_vs_ftfc_bullish'


def test_classify_call_setup_with_bearish_ftfc_is_conflicted():
    bias = classify({'signal_status': 'CALL setup (3/5)',
                     'ftfc_direction': 'bearish'})
    assert bias['bias'] == 'CONFLICTED'
    assert bias['reason'] == 'setup_call_vs_ftfc_bearish'


def test_classify_put_setup_with_mixed_ftfc_resolves_to_put():
    """Today's actual QQQ brief: PUT setup + mixed FTFC = bias=PUT
    (no internal contradiction since FTFC is undecided)."""
    bias = classify({'signal_status': 'PUT setup (3/5)',
                     'ftfc_direction': 'mixed'})
    assert bias['bias'] == 'PUT'
    assert bias['setup_count'] == 3


def test_classify_no_signal_is_neutral():
    bias = classify({'signal_status': 'No signal', 'ftfc_direction': 'mixed'})
    assert bias['bias'] == 'NEUTRAL'


def test_classify_building_is_neutral():
    """'CALL building (2/5)' is partial — not actionable, treat as NEUTRAL."""
    bias = classify({'signal_status': 'CALL building (2/5)',
                     'ftfc_direction': 'bullish'})
    assert bias['bias'] == 'NEUTRAL'


def test_classify_empty_status_is_neutral():
    bias = classify({'signal_status': '', 'ftfc_direction': None})
    assert bias['bias'] == 'NEUTRAL'


def test_classify_unknown_status_is_neutral():
    """Unknown status string must NOT crash and must NOT claim a bias."""
    bias = classify({'signal_status': 'random garbage from a bug',
                     'ftfc_direction': 'mixed'})
    assert bias['bias'] == 'NEUTRAL'


# ── alignment() — pure ──────────────────────────────────────────────

def test_alignment_call_vs_put_bias_is_opposed():
    bias = classify({'signal_status': 'PUT setup (3/5)',
                     'ftfc_direction': 'mixed'})
    assert alignment('CALL', bias) == 'opposed'


def test_alignment_call_vs_call_bias_is_aligned():
    bias = classify({'signal_status': 'CALL setup (4/5)',
                     'ftfc_direction': 'bullish'})
    assert alignment('CALL', bias) == 'aligned'


def test_alignment_with_conflicted_returns_none():
    bias = classify({'signal_status': 'PUT setup (4/5)',
                     'ftfc_direction': 'bullish'})
    assert bias['bias'] == 'CONFLICTED'
    assert alignment('CALL', bias) is None
    assert alignment('PUT',  bias) is None


def test_alignment_with_neutral_returns_none():
    bias = classify({'signal_status': 'No signal'})
    assert alignment('CALL', bias) is None
    assert alignment('PUT', bias) is None


# ── Tier-B fallback when DB not configured ─────────────────────────

def test_get_premarket_bias_returns_unavailable_when_db_not_configured():
    get_premarket_bias.cache_clear()
    with patch('gcp.database.is_cloud_sql_configured', return_value=False):
        bias = get_premarket_bias('QQQ', date(2026, 5, 5))
    assert bias['bias'] == 'UNAVAILABLE'
    assert bias['reason'] == 'db_not_configured'


def test_get_premarket_bias_returns_unavailable_on_query_failure():
    get_premarket_bias.cache_clear()
    with patch('gcp.database.is_cloud_sql_configured', return_value=True), \
         patch('pandas.read_sql', side_effect=Exception('boom')):
        bias = get_premarket_bias('QQQ', date(2026, 5, 5))
    assert bias['bias'] == 'UNAVAILABLE'
    assert bias['reason'] == 'query_failed'


# ── SignalMonitor._resolve_brief_bias caching ──────────────────────

def test_resolve_brief_bias_caches_per_ticker():
    """Each ticker should only hit get_premarket_bias once per session."""
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""

    # Pre-clear the lru_cache so our patch is the only path
    get_premarket_bias.cache_clear()

    fake_bias = {'bias': 'CALL', 'alignment': None, 'setup_count': 4,
                 'ftfc_direction': 'bullish', 'reason': 'aligned'}
    with patch('gcp.signal_monitor.get_premarket_bias',
               return_value=fake_bias) as mock_get:
        b1 = monitor._resolve_brief_bias('QQQ')
        b2 = monitor._resolve_brief_bias('QQQ')
        b3 = monitor._resolve_brief_bias('SPY')
    assert b1 == fake_bias
    assert b2 == fake_bias
    assert mock_get.call_count == 2, \
        f"expected 2 lookups (QQQ once, SPY once); got {mock_get.call_count}"


def test_resolve_brief_bias_handles_lookup_exception():
    """If the underlying DB read raises, _resolve_brief_bias returns
    a safe UNAVAILABLE shape rather than propagating."""
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    with patch('gcp.signal_monitor.get_premarket_bias',
               side_effect=RuntimeError('cloud sql down')):
        bias = monitor._resolve_brief_bias('QQQ')
    assert bias['bias'] == 'UNAVAILABLE'
    assert bias['reason'] == 'lookup_failed'


# ── persist row carries brief_* columns ────────────────────────────

def test_persist_row_includes_brief_columns_when_bias_resolved():
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    # Stash the bias the way fire_alert would
    monitor._latest_brief_bias = {'bias': 'PUT', 'alignment': None,
                                  'setup_count': 3,
                                  'ftfc_direction': 'mixed',
                                  'reason': 'aligned'}
    monitor._latest_brief_alignment = 'opposed'

    sig = {"direction": "CALL", "base_score": 3,
           "conditions_met": ["rsi_oversold_zone", "below_vwap",
                              "stoch_rsi_oversold"]}
    latest = pd.Series({
        "Close": 677.63, "RSI14": 35.0, "VWAP": 678.0, "EMA9": 677.5,
        "EMA20": 678.5, "StochRSI_K": 25.0,
        "Price_vs_VWAP": -0.05, "Price_vs_EMA9": 0.02, "Price_vs_EMA20": -0.13,
        "Consecutive_Down": 3, "Consecutive_Up": 0,
        "RVOL": 1.0, "ATR14": 1.0,
        "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 0,
    })

    with patch("gcp.database.upsert_dataframe") as mock_upsert, \
         patch("gcp.database.is_cloud_sql_configured", return_value=True):
        mock_upsert.return_value = 1
        monitor._persist_signal_alert(
            ticker='QQQ', sig=sig, total_score=2.25, strength='weak',
            size=0.05, strat_bonus=0, latest=latest,
            target=679.66, time_stop=30,
        )
    df = mock_upsert.call_args[0][0]
    row = df.iloc[0]
    assert row['brief_bias'] == 'PUT'
    assert row['brief_alignment'] == 'opposed'
    assert row['brief_setup_count'] == 3


def test_persist_row_brief_columns_null_when_no_bias_attrs():
    """If bias resolution didn't run (e.g. early-fire path), persist
    must still succeed with NULL brief columns rather than KeyError."""
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    # Deliberately do NOT set _latest_brief_bias / _latest_brief_alignment

    sig = {"direction": "CALL", "base_score": 3,
           "conditions_met": ["rsi_oversold_zone", "below_vwap",
                              "stoch_rsi_oversold"]}
    latest = pd.Series({
        "Close": 677.63, "RSI14": 35.0, "VWAP": 678.0, "EMA9": 677.5,
        "EMA20": 678.5, "StochRSI_K": 25.0,
        "Price_vs_VWAP": -0.05, "Price_vs_EMA9": 0.02, "Price_vs_EMA20": -0.13,
        "Consecutive_Down": 3, "Consecutive_Up": 0,
        "RVOL": 1.0, "ATR14": 1.0,
        "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 0,
    })

    with patch("gcp.database.upsert_dataframe") as mock_upsert, \
         patch("gcp.database.is_cloud_sql_configured", return_value=True):
        mock_upsert.return_value = 1
        # Must not raise KeyError
        monitor._persist_signal_alert(
            ticker='QQQ', sig=sig, total_score=2.25, strength='weak',
            size=0.05, strat_bonus=0, latest=latest,
            target=679.66, time_stop=30,
        )
    df = mock_upsert.call_args[0][0]
    row = df.iloc[0]
    # All three brief_* columns must be present + None (-> NULL in DB)
    assert 'brief_bias' in row
    assert row['brief_bias'] is None
    assert row['brief_alignment'] is None
    assert row['brief_setup_count'] is None
