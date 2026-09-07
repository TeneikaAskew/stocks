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


# ── ftfc_score propagation (added 2026-05-10 to fix the live-monitor
#    hardcode at gcp/signal_monitor.py:637 that silently disabled the
#    Strat.get_strat_bonus FTFC alignment branch) ─────────────────────

def test_classify_propagates_positive_ftfc_score():
    """Bullish FTFC alignment from premarket_analysis flows through to
    the bias dict so signal_monitor can pass it to get_strat_bonus."""
    bias = classify({'signal_status': 'CALL setup (4/5)',
                     'ftfc_direction': 'bullish',
                     'ftfc_score': 0.82})
    assert bias['ftfc_score'] == 0.82
    assert bias['ftfc_direction'] == 'bullish'


def test_classify_propagates_negative_ftfc_score():
    bias = classify({'signal_status': 'PUT setup (3/5)',
                     'ftfc_direction': 'bearish',
                     'ftfc_score': -0.7})
    assert bias['ftfc_score'] == -0.7


def test_classify_ftfc_score_none_when_missing():
    """No `ftfc_score` key in row (e.g. older brief rows) → None,
    not 0.0 — signal_monitor distinguishes 'unknown' from 'neutral'."""
    bias = classify({'signal_status': 'No signal'})
    assert bias['ftfc_score'] is None


def test_classify_ftfc_score_clamped_to_unit_range():
    """Defensive clamp on out-of-range writes."""
    high = classify({'signal_status': 'CALL setup (3/5)',
                     'ftfc_direction': 'bullish', 'ftfc_score': 1.5})
    low = classify({'signal_status': 'PUT setup (3/5)',
                    'ftfc_direction': 'bearish', 'ftfc_score': -2.0})
    assert high['ftfc_score'] == 1.0
    assert low['ftfc_score'] == -1.0


def test_classify_ftfc_score_garbage_returns_none():
    bias = classify({'signal_status': 'CALL setup (4/5)',
                     'ftfc_direction': 'bullish',
                     'ftfc_score': 'not_a_number'})
    assert bias['ftfc_score'] is None


def test_classify_ftfc_score_nan_returns_none():
    """pandas may emit NaN for SQL NULL — must not propagate NaN."""
    bias = classify({'signal_status': 'CALL setup (4/5)',
                     'ftfc_direction': 'bullish',
                     'ftfc_score': float('nan')})
    assert bias['ftfc_score'] is None


def test_classify_conflicted_carries_ftfc_score():
    """CONFLICTED bias still surfaces the score so the monitor can
    decide whether to apply the strat-bonus penalty."""
    bias = classify({'signal_status': 'PUT setup (4/5)',
                     'ftfc_direction': 'bullish',
                     'ftfc_score': 0.65})
    assert bias['bias'] == 'CONFLICTED'
    assert bias['ftfc_score'] == 0.65


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


# ── level_aware_alignment (stop-breach downgrade) ──────────────────

def _call_bias(stop=725.33, **kw):
    b = {'bias': 'CALL', 'alignment': None, 'setup_count': 3,
         'ftfc_direction': 'bullish', 'ftfc_score': 0.8,
         'reason': 'aligned', 'calls_stop_price': stop,
         'puts_stop_price': None}
    b.update(kw)
    return b


def _put_bias(stop=745.0, **kw):
    b = {'bias': 'PUT', 'alignment': None, 'setup_count': 3,
         'ftfc_direction': 'bearish', 'ftfc_score': -0.8,
         'reason': 'aligned', 'calls_stop_price': None,
         'puts_stop_price': stop}
    b.update(kw)
    return b


def test_level_aware_call_breach_is_invalidated():
    """SPY 2026-06-11 shape: session low dipped through the call stop
    before the CALL fired."""
    from lib.strategies.brief_bias import level_aware_alignment
    tag = level_aware_alignment('CALL', _call_bias(stop=725.33),
                                session_high=727.24, session_low=725.04)
    assert tag == 'invalidated'


def test_level_aware_call_intact_stays_aligned():
    from lib.strategies.brief_bias import level_aware_alignment
    tag = level_aware_alignment('CALL', _call_bias(stop=725.33),
                                session_high=727.24, session_low=725.90)
    assert tag == 'aligned'


def test_level_aware_put_breach_is_invalidated():
    """2026-05-07/08 QQQ shape: session high traded through the put stop
    before the PUT fired."""
    from lib.strategies.brief_bias import level_aware_alignment
    tag = level_aware_alignment('PUT', _put_bias(stop=745.0),
                                session_high=748.36, session_low=745.68)
    assert tag == 'invalidated'


def test_level_aware_touch_counts_as_breach():
    """A stop executes at touch — equality is a breach, not a survive."""
    from lib.strategies.brief_bias import level_aware_alignment
    assert level_aware_alignment('CALL', _call_bias(stop=291.17),
                                 session_high=293.29,
                                 session_low=291.17) == 'invalidated'
    assert level_aware_alignment('PUT', _put_bias(stop=745.0),
                                 session_high=745.0,
                                 session_low=740.0) == 'invalidated'


def test_level_aware_opposed_never_downgrades():
    """Breach only re-labels agreement; disagreement stays 'opposed'."""
    from lib.strategies.brief_bias import level_aware_alignment
    tag = level_aware_alignment('PUT', _call_bias(stop=725.33),
                                session_high=727.24, session_low=725.04)
    assert tag == 'opposed'


def test_level_aware_no_stop_degrades_to_aligned():
    from lib.strategies.brief_bias import level_aware_alignment
    tag = level_aware_alignment('CALL', _call_bias(stop=None),
                                session_high=727.24, session_low=700.0)
    assert tag == 'aligned'


def test_level_aware_missing_extremes_degrades_to_aligned():
    """First bars of the session / replay edge: no extremes yet must
    never produce a false 'invalidated'."""
    from lib.strategies.brief_bias import level_aware_alignment
    tag = level_aware_alignment('CALL', _call_bias(stop=725.33),
                                session_high=None, session_low=None)
    assert tag == 'aligned'


def test_level_aware_neutral_bias_returns_none():
    from lib.strategies.brief_bias import level_aware_alignment
    bias = {'bias': 'NEUTRAL', 'calls_stop_price': 100.0,
            'puts_stop_price': 110.0}
    assert level_aware_alignment('CALL', bias, 120.0, 90.0) is None


def test_get_premarket_bias_attaches_stop_levels():
    """The brief's stop prices ride along on the resolved bias dict —
    NaN (pandas NULL) must come back as None, not NaN (a NaN stop makes
    every comparison False and silently disables the breach check)."""
    get_premarket_bias.cache_clear()
    df = pd.DataFrame([{'signal_status': 'CALL setup (3/5)',
                        'ftfc_direction': 'bullish', 'ftfc_score': 0.8,
                        'strat_combo': None,
                        'calls_stop_price': 293.41,
                        'puts_stop_price': float('nan')}])
    with patch('gcp.database.is_cloud_sql_configured', return_value=True), \
         patch('gcp.database.get_engine', return_value=object()), \
         patch('pandas.read_sql', return_value=df):
        bias = get_premarket_bias('IWM', date(2026, 7, 23))
    assert bias['bias'] == 'CALL'
    assert bias['calls_stop_price'] == 293.41
    assert bias['puts_stop_price'] is None


# ── SignalMonitor session-extremes tracking ────────────────────────

def _bars(times, highs, lows):
    return pd.DataFrame({
        'Time': pd.to_datetime(times),
        'Open': lows, 'High': highs, 'Low': lows,
        'Close': highs, 'Volume': [100] * len(times),
    })


def test_session_extremes_accumulate_across_polls():
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    monitor.replay_clock_ts = pd.Timestamp('2026-07-23 14:00:00')  # UTC
    monitor.session_extremes.setdefault('IWM', {})
    # Replay convention: naive-UTC Times (13:30 UTC == 09:30 ET in July)
    monitor._update_session_extremes(
        'IWM', _bars(['2026-07-23 13:30', '2026-07-23 13:31'],
                     highs=[291.0, 292.0], lows=[290.34, 290.9]))
    monitor._update_session_extremes(
        'IWM', _bars(['2026-07-23 14:00'], highs=[293.01], lows=[291.5]))
    ext = monitor.session_extremes['IWM']
    assert ext['high'] == 293.01
    assert ext['low'] == 290.34


def test_session_extremes_exclude_premarket_bars():
    """Premarket bars must not count as 'the session traded through the
    stop' — the brief's plan is an RTH plan."""
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    monitor.replay_clock_ts = pd.Timestamp('2026-07-23 13:45:00')
    # 12:00 UTC == 08:00 ET (premarket), 13:31 UTC == 09:31 ET (RTH)
    monitor._update_session_extremes(
        'IWM', _bars(['2026-07-23 12:00', '2026-07-23 13:31'],
                     highs=[299.0, 291.0], lows=[280.0, 290.5]))
    ext = monitor.session_extremes['IWM']
    assert ext['high'] == 291.0, "premarket high leaked into session high"
    assert ext['low'] == 290.5, "premarket low leaked into session low"


def test_session_extremes_live_mode_treats_times_as_eastern():
    """Live AV bars carry naive America/New_York stamps; with no replay clock
    a 09:31 stamp is RTH as-is (it would be 05:31 ET if misread as UTC,
    and the bar would be dropped)."""
    from gcp.signal_monitor import SignalMonitor
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _zi
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    assert monitor.replay_clock_ts is None
    today = _dt.now(_zi('America/New_York')).date()
    bars = _bars([f'{today} 09:31', f'{today} 10:15'],
                 highs=[500.0, 501.5], lows=[498.0, 499.0])
    monitor._update_session_extremes('SPY', bars)
    ext = monitor.session_extremes['SPY']
    assert ext['high'] == 501.5
    assert ext['low'] == 498.0


def test_session_extremes_reset_on_new_date():
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    monitor.replay_clock_ts = pd.Timestamp('2026-07-23 14:00:00')
    monitor._update_session_extremes(
        'IWM', _bars(['2026-07-23 13:31'], highs=[291.0], lows=[290.0]))
    # Next session: clock moves to 7/24, stale 7/23 extremes must drop
    monitor.replay_clock_ts = pd.Timestamp('2026-07-24 13:35:00')
    monitor._update_session_extremes(
        'IWM', _bars(['2026-07-24 13:31'], highs=[295.0], lows=[294.0]))
    ext = monitor.session_extremes['IWM']
    assert ext['low'] == 294.0, "prior session's low survived the rollover"


def test_update_window_feeds_session_extremes():
    """update_window is the choke point — extremes must advance without
    any separate call."""
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    monitor.replay_clock_ts = pd.Timestamp('2026-07-23 13:31:00')
    monitor.update_window(
        'IWM', _bars(['2026-07-23 13:31'], highs=[291.0], lows=[290.34]))
    assert monitor.session_extremes['IWM']['low'] == 290.34


def test_fire_alert_tags_invalidated_when_stop_breached():
    """End-to-end through fire_alert: IWM 2026-07-23 shape — CALL-bias
    brief with stop 293.41, session low already at 290.34, CALL fires →
    persisted row must carry brief_alignment='invalidated'."""
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    monitor._brief_bias_cache['IWM'] = _call_bias(stop=293.41)
    monitor.session_extremes['IWM'] = {
        'date': date(2026, 7, 23), 'high': 293.01, 'low': 290.34}
    sig = {"direction": "CALL", "base_score": 3,
           "conditions_met": ["rsi_oversold_zone"]}
    latest = pd.Series({
        "Close": 291.51, "RSI14": 35.0, "VWAP": 291.0, "EMA9": 291.5,
        "EMA20": 291.8, "StochRSI_K": 25.0,
        "Price_vs_VWAP": -0.05, "Price_vs_EMA9": 0.02,
        "Price_vs_EMA20": -0.13,
        "Consecutive_Down": 3, "Consecutive_Up": 0,
        "RVOL": 1.2, "ATR14": 1.0,
        "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 0,
    })
    with patch("gcp.database.upsert_dataframe") as mock_upsert, \
         patch("gcp.database.is_cloud_sql_configured", return_value=True):
        mock_upsert.return_value = 1
        monitor.fire_alert(ticker='IWM', sig=sig, total_score=3.0,
                           strength='medium', size=0.10, strat_bonus=0,
                           latest=latest)
    assert monitor._latest_brief_alignment == 'invalidated'
    df = mock_upsert.call_args[0][0]
    assert df.iloc[0]['brief_alignment'] == 'invalidated'


def test_fire_alert_stays_aligned_when_stop_intact():
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    monitor._brief_bias_cache['IWM'] = _call_bias(stop=289.00)
    monitor.session_extremes['IWM'] = {
        'date': date(2026, 7, 23), 'high': 293.01, 'low': 290.34}
    sig = {"direction": "CALL", "base_score": 3,
           "conditions_met": ["rsi_oversold_zone"]}
    latest = pd.Series({
        "Close": 291.51, "RSI14": 35.0, "VWAP": 291.0, "EMA9": 291.5,
        "EMA20": 291.8, "StochRSI_K": 25.0,
        "Price_vs_VWAP": -0.05, "Price_vs_EMA9": 0.02,
        "Price_vs_EMA20": -0.13,
        "Consecutive_Down": 3, "Consecutive_Up": 0,
        "RVOL": 1.2, "ATR14": 1.0,
        "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 0,
    })
    with patch("gcp.database.upsert_dataframe") as mock_upsert, \
         patch("gcp.database.is_cloud_sql_configured", return_value=True):
        mock_upsert.return_value = 1
        monitor.fire_alert(ticker='IWM', sig=sig, total_score=3.0,
                           strength='medium', size=0.10, strat_bonus=0,
                           latest=latest)
    assert monitor._latest_brief_alignment == 'aligned'
    df = mock_upsert.call_args[0][0]
    assert df.iloc[0]['brief_alignment'] == 'aligned'
