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


class TestSignalsWebhookRouting:
    """SignalMonitor routes entries / exits / ORB snapshots to the
    dedicated signals channel (DISCORD_WEBHOOK_SIGNALS_URL) when set,
    falling back to DISCORD_WEBHOOK_URL otherwise."""

    def test_prefers_signals_webhook(self, monkeypatch):
        monkeypatch.setenv('DISCORD_WEBHOOK_SIGNALS_URL', 'https://discord.com/api/webhooks/SIG')
        monkeypatch.setenv('DISCORD_WEBHOOK_URL', 'https://discord.com/api/webhooks/MAIN')
        m = _build_monitor()
        assert m.webhook_url == 'https://discord.com/api/webhooks/SIG'

    def test_falls_back_to_main_webhook(self, monkeypatch):
        monkeypatch.delenv('DISCORD_WEBHOOK_SIGNALS_URL', raising=False)
        monkeypatch.setenv('DISCORD_WEBHOOK_URL', 'https://discord.com/api/webhooks/MAIN')
        m = _build_monitor()
        assert m.webhook_url == 'https://discord.com/api/webhooks/MAIN'

    def test_none_when_neither_set(self, monkeypatch):
        monkeypatch.delenv('DISCORD_WEBHOOK_SIGNALS_URL', raising=False)
        monkeypatch.delenv('DISCORD_WEBHOOK_URL', raising=False)
        m = _build_monitor()
        assert m.webhook_url is None


class TestIndicatorEngineContract:
    """Lock the 'one source of truth' contract: signal_monitor delegates to
    lib.indicators.add_all_indicators, which MUST produce every indicator
    column the live strategies read. Before 2026-05-31 the monitor hand-rolled
    a subset and silently lagged the engine; this guards against regressing to
    a second calculation location.
    """

    # Indicator columns the live strategies (MOMENTUM / agreement / signals /
    # brief_bias) read off each bar via row.get(...). NOT including
    # level/historical columns (Broke_Prev_Day_*), which are added by
    # refresh_level_map, not the indicator engine.
    REQUIRED = [
        'RSI14', 'EMA9', 'EMA20', 'ATR14', 'VWAP', 'RVOL', 'OBV',
        'StochRSI_K', 'StochRSI_D', 'Price_Change',
        'Consecutive_Up', 'Consecutive_Down', 'Consecutive_Up_5', 'Consecutive_Down_5',
        'RVol_Recent_20', 'ATR_Expansion', 'RSI_Thrust_3',
        'Price_vs_VWAP', 'Price_vs_EMA9', 'Price_vs_EMA20',
    ]

    def _window(self, n=120):
        import numpy as np, pandas as pd
        rng = np.random.RandomState(7)
        idx = pd.date_range('2026-05-29 09:30', periods=n, freq='1min', tz='UTC')
        close = pd.Series(200 + np.cumsum(rng.randn(n) * 0.05), index=idx)
        return pd.DataFrame({
            'Open': close.shift(1).fillna(close.iloc[0]),
            'High': close + abs(rng.randn(n)) * 0.05,
            'Low': close - abs(rng.randn(n)) * 0.05,
            'Close': close,
            'Volume': rng.randint(1e4, 1e5, n).astype(float),
            'Time': idx,
        }, index=idx)

    def test_engine_produces_all_live_columns(self):
        from lib.indicators import add_all_indicators
        out = add_all_indicators(self._window(), close_col='Close')
        missing = [c for c in self.REQUIRED if c not in out.columns]
        assert not missing, f"add_all_indicators missing live columns: {missing}"

    def test_engine_includes_promoted_features_for_live(self):
        """The 2026-05-31 promoted features now reach live firing too."""
        from lib.indicators import add_all_indicators
        out = add_all_indicators(self._window(), close_col='Close')
        for c in ['Realized_Vol_Short', 'Mins_Since_Open', 'EMA9_Slope',
                  'EMA_Spread_ATR', 'BB_Squeeze', 'RSI_Divergence', 'Price_vs_VWAP_ATR']:
            assert c in out.columns, f"promoted feature not in live engine output: {c}"

    def test_per_ticker_consecutive_override_flows_through(self):
        """Threading consecutive_periods via IndicatorConfig must change the
        Consecutive_Up/Down window (the live Tier-A calibration nuance)."""
        import dataclasses
        from lib.config import IndicatorConfig
        from lib.indicators import add_all_indicators
        w = self._window()
        base = add_all_indicators(w, close_col='Close',
                                  indicator_config=IndicatorConfig())
        cfg = dataclasses.replace(IndicatorConfig(), consecutive_periods=99)
        overridden = add_all_indicators(w, close_col='Close', indicator_config=cfg)
        # window 99 on a 120-bar frame => far fewer/zero qualifying streaks
        assert not base['Consecutive_Up'].equals(overridden['Consecutive_Up'])
        # the relaxed *_5 column is independent of the override
        import pandas as pd
        pd.testing.assert_series_equal(base['Consecutive_Up_5'],
                                       overridden['Consecutive_Up_5'])


class TestCheckOrbTimezone:
    """#819 (audit R2) — `check_orb` compared bar clock times against the
    ET market open without converting the index, so in replay (where
    `market_data_intraday` bars are UTC) the 09:30-10:00 ET window
    selected 09:30-10:00 UTC, i.e. pre-market bars, and the ORB levels
    were built from the wrong half hour. This is the 2026-05-06 V1
    harness bug in production code. The replay-aware conversion already
    exists twice in the same class (`update_window`'s level-tracking and
    leg-tracker paths); `check_orb` must use it too."""

    @staticmethod
    def _utc_bars(start_utc: str, minutes: int, base: float = 200.0):
        import pandas as pd
        times = pd.date_range(start_utc, periods=minutes, freq="1min")
        highs = [base + i * 0.1 for i in range(minutes)]
        return pd.DataFrame({
            "Time": times,
            "Open": highs, "High": highs, "Low": [h - 0.05 for h in highs],
            "Close": highs, "Volume": [1000] * minutes,
        })

    def test_replay_utc_bars_use_et_open(self):
        """Replay: naive-UTC bars from 13:25 UTC (09:25 ET). The 5-minute
        ORB is 09:30-09:35 ET == 13:30-13:35 UTC, whose highs are the bars
        at index 5..10. Under the old code nothing matched 09:30-09:35
        (all clock times are 13:xx) and no ORB level was recorded."""
        import pandas as pd
        m = _build_monitor()
        df = self._utc_bars("2026-05-06 13:25:00", 45)
        m.replay_clock_ts = pd.Timestamp("2026-05-06 14:10:00")
        m.check_orb("IWM", df)
        lv = m.orb_levels["IWM"]
        assert "5m_high" in lv, "ORB never formed: window compared UTC clock to ET open"
        assert lv["5m_high"] == pytest.approx(200.0 + 10 * 0.1)   # 13:35 UTC bar
        assert lv["5m_low"] == pytest.approx(200.0 + 5 * 0.1 - 0.05)  # 13:30 UTC bar
        assert lv["30m_high"] == pytest.approx(200.0 + 35 * 0.1)  # 14:00 UTC bar

    def test_replay_does_not_take_premarket_utc_bars(self):
        """The same frame with a pre-market run-up: if the window were
        still read in UTC, 09:30-10:00 UTC (05:30-06:00 ET) bars would be
        the ORB. Make those bars the highest and assert they are ignored."""
        import pandas as pd
        m = _build_monitor()
        pre = self._utc_bars("2026-05-06 09:25:00", 40, base=300.0)   # 05:25 ET
        rth = self._utc_bars("2026-05-06 13:25:00", 40, base=200.0)   # 09:25 ET
        df = pd.concat([pre, rth], ignore_index=True)
        m.replay_clock_ts = pd.Timestamp("2026-05-06 14:05:00")
        m.check_orb("IWM", df)
        lv = m.orb_levels["IWM"]
        assert lv["30m_high"] < 250.0, "ORB built from pre-market UTC bars"

    def test_live_tz_aware_et_bars_unchanged(self):
        """Live path: tz-aware ET timestamps keep working exactly as before."""
        import pandas as pd
        m = _build_monitor()
        df = self._utc_bars("2026-05-06 13:25:00", 45)
        df["Time"] = df["Time"].dt.tz_localize("UTC").dt.tz_convert("America/New_York")
        m.check_orb("IWM", df)
        assert m.orb_levels["IWM"]["5m_high"] == pytest.approx(200.0 + 10 * 0.1)
