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


class TestReplayMode:
    """`gcp.signal_monitor:main` exposes --mode=replay (and accepts
    REPLAY_DATE / REPLAY_TICKER env-var triggers) so the existing
    Cloud Run Job can run the hermetic 1-min-bar replay harness in
    `scripts/replay_signal_monitor.py` without needing a separate
    job spec. These tests lock the dispatch contract so future
    refactors don't silently break the env-var → replay flow.
    """

    def test_replay_mode_dispatches_to_replay_main(self, monkeypatch):
        """When --mode=replay is passed, signal_monitor.main calls
        scripts.replay_signal_monitor.main with translated argv."""
        from gcp import signal_monitor

        captured = {}

        def fake_replay_main(argv):
            captured['argv'] = argv
            return 0

        # Replace the imported callable inside signal_monitor's
        # main() before invocation. The function does a local import
        # (`from scripts.replay_signal_monitor import main as
        # _replay_main`) so we patch at the source module.
        import scripts.replay_signal_monitor as rsm
        monkeypatch.setattr(rsm, 'main', fake_replay_main)
        monkeypatch.setenv('CLOUD_SQL_CONNECTION_NAME', 'x:y:z')
        monkeypatch.setenv('DB_USER', 'u')
        monkeypatch.setenv('DB_PASS', 'p')
        monkeypatch.setenv('DB_NAME', 'n')

        # Invoke main with replay flags
        with patch('sys.argv', [
            'signal_monitor', '--mode=replay',
            '--ticker=SPY', '--date=2026-05-07', '--json',
        ]):
            with pytest.raises(SystemExit) as exc:
                signal_monitor.main()
            assert exc.value.code == 0

        # Replay main was called with translated argv
        argv = captured['argv']
        assert '--ticker' in argv
        assert 'SPY' in argv
        assert '--date' in argv
        assert '2026-05-07' in argv
        assert '--json' in argv

    def test_replay_date_env_var_triggers_replay_mode(self, monkeypatch):
        """Setting REPLAY_DATE env-var alone (no --mode flag) flips
        the default loop mode to replay. This is the primary
        production-deploy entry point: `gcloud run jobs execute
        signal-monitor --update-env-vars=REPLAY_DATE=...` should
        Just Work without rebuilding the job spec."""
        from gcp import signal_monitor

        captured = {}

        def fake_replay_main(argv):
            captured['argv'] = argv
            return 0

        import scripts.replay_signal_monitor as rsm
        monkeypatch.setattr(rsm, 'main', fake_replay_main)
        monkeypatch.setenv('REPLAY_DATE', '2026-05-08')
        monkeypatch.setenv('REPLAY_TICKER', 'IWM')
        monkeypatch.setenv('CLOUD_SQL_CONNECTION_NAME', 'x:y:z')
        monkeypatch.setenv('DB_USER', 'u')
        monkeypatch.setenv('DB_PASS', 'p')
        monkeypatch.setenv('DB_NAME', 'n')

        # No --mode flag — env var alone should be sufficient
        with patch('sys.argv', ['signal_monitor']):
            with pytest.raises(SystemExit) as exc:
                signal_monitor.main()
            assert exc.value.code == 0

        argv = captured['argv']
        assert '--date' in argv and '2026-05-08' in argv
        assert '--ticker' in argv and 'IWM' in argv

    def test_replay_mode_skips_av_key_check(self, monkeypatch):
        """Replay reads from market_data_intraday only — it doesn't
        fetch fresh bars, so missing ALPHA_VANTAGE_API_KEY must NOT
        abort the run with exit code 2 (which is the live-mode
        fail-fast). Cloud SQL env vars are still required."""
        from gcp import signal_monitor

        def fake_replay_main(argv):
            return 0

        import scripts.replay_signal_monitor as rsm
        monkeypatch.setattr(rsm, 'main', fake_replay_main)
        monkeypatch.delenv('ALPHA_VANTAGE_API_KEY', raising=False)
        monkeypatch.setenv('REPLAY_DATE', '2026-05-08')
        monkeypatch.setenv('REPLAY_TICKER', 'SPY')
        monkeypatch.setenv('CLOUD_SQL_CONNECTION_NAME', 'x:y:z')
        monkeypatch.setenv('DB_USER', 'u')
        monkeypatch.setenv('DB_PASS', 'p')
        monkeypatch.setenv('DB_NAME', 'n')

        with patch('sys.argv', ['signal_monitor']):
            with pytest.raises(SystemExit) as exc:
                signal_monitor.main()
            # Replay path completed successfully — must NOT be exit 2
            # (the AV-key fail-fast) or 3 (Cloud SQL fail-fast)
            assert exc.value.code == 0
