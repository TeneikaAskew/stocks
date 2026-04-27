"""Tests for gcp/signal_monitor.py — level-break detection + ORB snapshot mode.

These tests target the pure-Python helpers that don't need Cloud SQL or
AlphaVantage credentials: SignalMonitor.check_level_breaks and the
argparse path for --mode=orb-snapshot.
"""

from datetime import datetime
from unittest.mock import patch

import pytest


def _build_monitor():
    """Construct a SignalMonitor without hitting Cloud SQL / AlphaVantage."""
    import os
    os.environ.setdefault('ALPHA_VANTAGE_API_KEY', 'test-key')
    from gcp.signal_monitor import SignalMonitor
    return SignalMonitor()


def _build_levelmap_with(levels):
    from lib.strat_levels import LevelMap, StratLevel
    return LevelMap(
        ticker='IWM', as_of=datetime.utcnow(), current_price=200.0,
        levels=[StratLevel(name=n, price=p) for n, p in levels],
    )


class TestCheckLevelBreaks:
    def test_fires_on_first_crossing(self):
        m = _build_monitor()
        lm = _build_levelmap_with([('PDH', 215.85), ('PDL', 213.20)])
        # prev_price 215.50 (below PDH), last_price 216.00 (above PDH)
        broken = m.check_level_breaks('IWM', last_price=216.00,
                                       prev_price=215.50, level_map=lm)
        assert 'PDH' in broken

    def test_dedups_subsequent_ticks(self):
        m = _build_monitor()
        lm = _build_levelmap_with([('PDH', 215.85)])
        first = m.check_level_breaks('IWM', last_price=216.00,
                                      prev_price=215.50, level_map=lm)
        # Second tick still above PDH — should NOT fire again
        second = m.check_level_breaks('IWM', last_price=216.10,
                                       prev_price=216.00, level_map=lm)
        assert 'PDH' in first
        assert 'PDH' not in second

    def test_fires_on_crossing_down(self):
        m = _build_monitor()
        lm = _build_levelmap_with([('PDL', 213.20)])
        broken = m.check_level_breaks('IWM', last_price=213.00,
                                       prev_price=213.30, level_map=lm)
        assert 'PDL' in broken

    def test_no_break_when_price_unchanged_relative_to_levels(self):
        m = _build_monitor()
        lm = _build_levelmap_with([('PDH', 215.85), ('PDL', 213.20)])
        broken = m.check_level_breaks('IWM', last_price=214.50,
                                       prev_price=214.40, level_map=lm)
        assert broken == []

    def test_safe_when_level_map_none(self):
        m = _build_monitor()
        broken = m.check_level_breaks('IWM', last_price=215, prev_price=214,
                                       level_map=None)
        assert broken == []

    def test_safe_when_prev_price_none(self):
        m = _build_monitor()
        lm = _build_levelmap_with([('PDH', 215.85)])
        broken = m.check_level_breaks('IWM', last_price=216,
                                       prev_price=None, level_map=lm)
        assert broken == []


class TestOrbSnapshotMode:
    def test_invalid_window_returns_2(self):
        from gcp.signal_monitor import run_orb_snapshot
        assert run_orb_snapshot('1h') == 2

    def test_valid_window_returns_0_with_no_data(self):
        """Without AV data, the snapshot path should still return 0
        (logs warnings, doesn't raise)."""
        from gcp.signal_monitor import run_orb_snapshot
        with patch('gcp.signal_monitor.SignalMonitor.fetch_latest_bar') as f:
            f.return_value.empty = True
            # The function constructs SignalMonitor() inside; mock fetch
            # so we don't hit network. Empty df -> warning + skip.
            import pandas as pd
            f.return_value = pd.DataFrame()
            assert run_orb_snapshot('15m') == 0
