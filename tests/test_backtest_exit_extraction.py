"""Characterization + unit tests for Task 3.1: extracting BacktestEngine's
inline exit-simulation loop into a reusable `simulate_exit()` method.

Two layers of protection:

1. ``TestIntegrationPin`` — pins the FULL ``engine.run()`` output (all
   Trade fields) on a small deterministic fixture day. The expected
   values below were captured by running ``engine.run()`` against
   ``lib/backtest.py`` BEFORE the refactor (via a throwaway scratch
   script, not committed) and hardcoded here. If the refactor changes
   behavior even slightly (rounding, bar-consumption order, MAE/MFE
   timing, etc.) this test fails.

2. ``TestSimulateExit`` — unit-level red/green tests for the new
   ``BacktestEngine.simulate_exit()`` method covering the four exit
   paths: profit target, stop loss, time stop, and eod force-close.
   These fail with AttributeError before the method is extracted
   (Step 2: red), pass after extraction (Step 3-4: green).
"""

import pandas as pd
import numpy as np
import pytest
from datetime import datetime

from lib.backtest import BacktestEngine, Trade
from lib.config import RiskConfig, ExitConfig, SignalConfig, StratConfig


def _make_pin_fixture_df(seed=7, bars_per_day=120):
    """Deterministic single-day 1-min OHLCV frame (matches the scratch
    script used to capture the pre-refactor pin below)."""
    np.random.seed(seed)
    day_date = pd.Timestamp('2024-03-04')  # a Monday
    times = pd.date_range(f'{day_date.date()} 09:30', periods=bars_per_day, freq='1min')

    base = 100.0
    returns = np.random.normal(0, 0.0015, bars_per_day)
    close = base * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(np.random.normal(0, 0.0012, bars_per_day)))
    low = close * (1 - np.abs(np.random.normal(0, 0.0012, bars_per_day)))
    open_ = np.roll(close, 1)
    open_[0] = base
    volume = np.random.randint(10000, 100000, bars_per_day).astype(float)

    df = pd.DataFrame({
        'Time': times,
        'Open': open_,
        'High': high,
        'Low': low,
        'Close': close,
        'Volume': volume,
    }, index=times)
    return df


# Captured PRE-refactor via a throwaway scratch script running
# `engine.run(_make_pin_fixture_df())` with
# SignalConfig(min_conditions=1), RiskConfig(), ExitConfig(), StratConfig()
# against the ORIGINAL inline exit loop in lib/backtest.py (before
# simulate_exit() existed). All 5 trades are CALL/stop_loss for this
# seed — that's expected (the four exit-path *variety* is covered by
# TestSimulateExit below, not this pin). This test only needs to prove
# run()'s output is byte-identical before and after the extraction.
_EXPECTED_TRADES = [
    dict(
        entry_time=pd.Timestamp('2024-03-04 09:30:00'),
        entry_price=100.25390063868385,
        direction='CALL',
        base_score=1,
        strat_bonus=0,
        total_score=1,
        position_size=0.25,
        exit_time=pd.Timestamp('2024-03-04 09:37:00'),
        exit_price=99.86845449185664,
        exit_reason='stop_loss',
        return_pct=-0.0038446997510486747,
        mae=-0.0012210398521890124,
        mfe=0.0,
    ),
    dict(
        entry_time=pd.Timestamp('2024-03-04 09:38:00'),
        entry_price=100.02101880429244,
        direction='CALL',
        base_score=2,
        strat_bonus=0,
        total_score=2,
        position_size=0.25,
        exit_time=pd.Timestamp('2024-03-04 09:45:00'),
        exit_price=99.77399343823038,
        exit_reason='stop_loss',
        return_pct=-0.002469734551948597,
        mae=-0.00029467465375752574,
        mfe=0.0009011535689859873,
    ),
    dict(
        entry_time=pd.Timestamp('2024-03-04 09:46:00'),
        entry_price=99.85702700862909,
        direction='CALL',
        base_score=2,
        strat_bonus=0,
        total_score=2,
        position_size=0.25,
        exit_time=pd.Timestamp('2024-03-04 09:49:00'),
        exit_price=99.68818430738605,
        exit_reason='stop_loss',
        return_pct=-0.001690844463339032,
        mae=0.0,
        mfe=0.0005976897889728699,
    ),
    dict(
        entry_time=pd.Timestamp('2024-03-04 09:50:00'),
        entry_price=99.93532302755597,
        direction='CALL',
        base_score=2,
        strat_bonus=0,
        total_score=2,
        position_size=0.25,
        exit_time=pd.Timestamp('2024-03-04 09:57:00'),
        exit_price=99.57719745928377,
        exit_reason='stop_loss',
        return_pct=-0.0035835734295215256,
        mae=-0.0003491456462128877,
        mfe=0.0026980348820431275,
    ),
    dict(
        entry_time=pd.Timestamp('2024-03-04 09:58:00'),
        entry_price=99.73406484007023,
        direction='CALL',
        base_score=2,
        strat_bonus=0,
        total_score=2,
        position_size=0.25,
        exit_time=pd.Timestamp('2024-03-04 10:00:00'),
        exit_price=99.56082364006042,
        exit_reason='stop_loss',
        return_pct=-0.0017370313772692937,
        mae=-0.0006245163861922067,
        mfe=0.0,
    ),
]

_EXPECTED_DAILY_PNL = [
    {'date': pd.Timestamp('2024-03-04').date(), 'trades': 5, 'pnl': -0.003331470893281781},
]
_EXPECTED_EQUITY_CURVE = [0.9966685291067182]
_EXPECTED_FILTER_COUNTS = {'ftfc_rejected': 0, 'orb_rejected': 0, 'signals_evaluated': 5}


class TestIntegrationPin:
    """Pins engine.run() output captured BEFORE the simulate_exit()
    extraction. Must remain unchanged AFTER the refactor."""

    def _run(self):
        df = _make_pin_fixture_df()
        engine = BacktestEngine(
            risk_config=RiskConfig(),
            exit_config=ExitConfig(),
            signal_config=SignalConfig(min_conditions=1),
            strat_config=StratConfig(),
        )
        return engine.run(df)

    def test_trade_count_unchanged(self):
        result = self._run()
        assert result.total_trades == len(_EXPECTED_TRADES)

    def test_trade_fields_unchanged(self):
        result = self._run()
        assert len(result.trades) == len(_EXPECTED_TRADES)
        for actual, expected in zip(result.trades, _EXPECTED_TRADES):
            assert actual.entry_time == expected['entry_time']
            assert actual.entry_price == pytest.approx(expected['entry_price'])
            assert actual.direction == expected['direction']
            assert actual.base_score == expected['base_score']
            assert actual.strat_bonus == expected['strat_bonus']
            assert actual.total_score == expected['total_score']
            assert actual.position_size == pytest.approx(expected['position_size'])
            assert actual.exit_time == expected['exit_time']
            assert actual.exit_price == pytest.approx(expected['exit_price'])
            assert actual.exit_reason == expected['exit_reason']
            assert actual.return_pct == pytest.approx(expected['return_pct'])
            assert actual.mae == pytest.approx(expected['mae'], abs=1e-12)
            assert actual.mfe == pytest.approx(expected['mfe'], abs=1e-12)

    def test_daily_pnl_and_equity_curve_unchanged(self):
        result = self._run()
        assert len(result.daily_pnl) == len(_EXPECTED_DAILY_PNL)
        assert result.daily_pnl[0]['date'] == _EXPECTED_DAILY_PNL[0]['date']
        assert result.daily_pnl[0]['trades'] == _EXPECTED_DAILY_PNL[0]['trades']
        assert result.daily_pnl[0]['pnl'] == pytest.approx(_EXPECTED_DAILY_PNL[0]['pnl'])
        assert result.equity_curve.tolist() == pytest.approx(_EXPECTED_EQUITY_CURVE)

    def test_filter_counts_unchanged(self):
        result = self._run()
        assert result.filter_counts == _EXPECTED_FILTER_COUNTS


# ---------------------------------------------------------------------------
# Unit tests for the extracted simulate_exit() method
# ---------------------------------------------------------------------------

def _bars(rows):
    """Build a minimal OHLC bars DataFrame from (time, close) pairs,
    indexed by time (no 'Time' column — exercises the `bars.index[i]`
    fallback path in the exit walk, matching how day_df is indexed in
    the fixtures used elsewhere in tests/test_backtest.py)."""
    times = [r[0] for r in rows]
    closes = [r[1] for r in rows]
    return pd.DataFrame({'Close': closes}, index=pd.DatetimeIndex(times))


@pytest.fixture
def engine():
    """Default-config engine — ExitConfig() defaults:
    call_target=0.0030, call_stop=0.0015, call_time_stop=30min,
    call_rsi_exit=80.0 (RSI column absent from test bars -> _check_exit
    falls back to the neutral 50.0 default, so rsi_extreme never fires
    in these unit tests)."""
    return BacktestEngine(
        risk_config=RiskConfig(),
        exit_config=ExitConfig(),
        signal_config=SignalConfig(),
        strat_config=StratConfig(),
    )


class TestSimulateExit:
    def test_target_hit(self, engine):
        t0 = pd.Timestamp('2024-01-02 09:30:00')
        # entry_idx=2: two unrelated pre-entry bars precede the entry bar
        # to confirm simulate_exit walks from entry_idx+1, not index 0.
        bars = _bars([
            (t0 - pd.Timedelta(minutes=2), 200.0),   # 0: unused pre-entry bar
            (t0 - pd.Timedelta(minutes=1), 200.0),   # 1: unused pre-entry bar
            (t0, 100.0),                             # 2: entry bar
            (t0 + pd.Timedelta(minutes=1), 100.10),  # 3: +0.10% (below target/stop)
            (t0 + pd.Timedelta(minutes=2), 100.35),  # 4: +0.35% >= target (0.30%)
        ])
        trade = Trade(
            entry_time=t0, entry_price=100.0, direction='CALL',
            base_score=3, strat_bonus=0, total_score=3, position_size=0.25,
            conditions_met=['c1', 'c2', 'c3'],
        )

        result = engine.simulate_exit(trade, bars, entry_idx=2, close_col='Close')

        assert result is trade
        assert trade.exit_reason == 'target'
        assert trade.exit_price == pytest.approx(100.35)
        assert trade.exit_time == t0 + pd.Timedelta(minutes=2)
        assert trade.return_pct == pytest.approx(0.0035)
        # MAE/MFE tracked only on the bar BEFORE the exit bar (bar 3);
        # the exit bar itself is not folded into MAE/MFE.
        assert trade.mae == pytest.approx(0.0)
        assert trade.mfe == pytest.approx(0.001)

    def test_stop_hit(self, engine):
        t0 = pd.Timestamp('2024-01-02 09:30:00')
        bars = _bars([
            (t0, 100.0),                              # 0: entry bar
            (t0 + pd.Timedelta(minutes=1), 99.90),     # 1: -0.10% (above stop)
            (t0 + pd.Timedelta(minutes=2), 99.80),     # 2: -0.20% <= -stop (0.15%)
        ])
        trade = Trade(
            entry_time=t0, entry_price=100.0, direction='CALL',
            base_score=3, strat_bonus=0, total_score=3, position_size=0.25,
            conditions_met=['c1', 'c2', 'c3'],
        )

        result = engine.simulate_exit(trade, bars, entry_idx=0, close_col='Close')

        assert result is trade
        assert trade.exit_reason == 'stop_loss'
        assert trade.exit_price == pytest.approx(99.80)
        assert trade.exit_time == t0 + pd.Timedelta(minutes=2)
        assert trade.return_pct == pytest.approx(-0.002)
        assert trade.mae == pytest.approx(-0.001)
        assert trade.mfe == pytest.approx(0.0)

    def test_time_stop(self, engine):
        t0 = pd.Timestamp('2024-01-02 09:30:00')
        # Flat price (unrealized 0.05%) never trips target (0.30%) or
        # stop (-0.15%). call_time_stop defaults to 30 minutes, so the
        # bar at entry+30min should trip time_stop.
        rows = [(t0, 100.0)]
        for m in range(1, 31):
            rows.append((t0 + pd.Timedelta(minutes=m), 100.05))
        bars = _bars(rows)
        trade = Trade(
            entry_time=t0, entry_price=100.0, direction='CALL',
            base_score=3, strat_bonus=0, total_score=3, position_size=0.25,
            conditions_met=['c1', 'c2', 'c3'],
        )

        result = engine.simulate_exit(trade, bars, entry_idx=0, close_col='Close')

        assert result is trade
        assert trade.exit_reason == 'time_stop'
        assert trade.exit_price == pytest.approx(100.05)
        assert trade.exit_time == t0 + pd.Timedelta(minutes=30)
        assert trade.return_pct == pytest.approx(0.0005)
        assert trade.mae == pytest.approx(0.0)
        assert trade.mfe == pytest.approx(0.0005)

    def test_eod_close(self, engine):
        t0 = pd.Timestamp('2024-01-02 09:30:00')
        # Flat price, well under the 30-minute time stop, and bars run
        # out — must force-close at the LAST bar in `bars` with
        # exit_reason='eod_close', mirroring the post-loop force-close
        # block that used to run after run()'s per-day for-loop.
        bars = _bars([
            (t0, 100.0),                             # 0: entry bar
            (t0 + pd.Timedelta(minutes=1), 100.05),   # 1
            (t0 + pd.Timedelta(minutes=2), 100.05),   # 2
            (t0 + pd.Timedelta(minutes=3), 100.05),   # 3
            (t0 + pd.Timedelta(minutes=4), 100.05),   # 4: last bar of the day
        ])
        trade = Trade(
            entry_time=t0, entry_price=100.0, direction='CALL',
            base_score=3, strat_bonus=0, total_score=3, position_size=0.25,
            conditions_met=['c1', 'c2', 'c3'],
        )

        result = engine.simulate_exit(trade, bars, entry_idx=0, close_col='Close')

        assert result is trade
        assert trade.exit_reason == 'eod_close'
        assert trade.exit_price == pytest.approx(100.05)
        assert trade.exit_time == t0 + pd.Timedelta(minutes=4)
        assert trade.return_pct == pytest.approx(0.0005)
        assert trade.mae == pytest.approx(0.0)
        assert trade.mfe == pytest.approx(0.0005)

    def test_entry_bar_excluded_under_divergent_fill_price(self, engine):
        """Pins the entry-bar-exclusion invariant when `trade.entry_price`
        diverges from the entry bar's own Close (e.g. next-bar-open fill,
        slippage, or — Task 3.2's use case — a labeled trade whose entry
        price came from the user, not from `bars`).

        entry bar (idx0) Close=100.0 but trade.entry_price=100.5. If the
        walk ever evaluated the entry bar itself, unrealized there would be
        (100.0 - 100.5) / 100.5 = -0.4975%, which blows through the -0.15%
        CALL stop and would wrongly stop the trade out on bar 0. Instead the
        walk must start at entry_idx + 1 (bar1, flat at 100.50 relative to
        entry_price), so the trade rides to bar2's +0.4975% target hit
        instead — and MAE never reflects the entry bar's phantom -0.4975%."""
        t0 = pd.Timestamp('2024-01-02 09:30:00')
        bars = _bars([
            (t0, 100.0),                              # 0: entry bar (Close != entry_price)
            (t0 + pd.Timedelta(minutes=1), 100.50),   # 1: flat vs entry_price (0.0%)
            (t0 + pd.Timedelta(minutes=2), 101.00),   # 2: +0.4975% vs entry_price >= target (0.30%)
        ])
        trade = Trade(
            entry_time=t0, entry_price=100.5, direction='CALL',
            base_score=3, strat_bonus=0, total_score=3, position_size=0.25,
            conditions_met=['c1', 'c2', 'c3'],
        )

        result = engine.simulate_exit(trade, bars, entry_idx=0, close_col='Close')

        assert result is trade
        assert trade.exit_reason == 'target'
        assert trade.exit_price == pytest.approx(101.00)
        assert trade.exit_time == t0 + pd.Timedelta(minutes=2)
        assert trade.return_pct == pytest.approx((101.00 - 100.5) / 100.5)
        # MAE/MFE only ever see bar1 (0.0% unrealized) — never the entry
        # bar's phantom -0.4975%, and never the exit bar itself (bar2).
        assert trade.mae == pytest.approx(0.0)
        assert trade.mfe == pytest.approx(0.0)

    def test_put_direction_sign_correction(self, engine):
        """return_pct is sign-corrected for PUT — price falling is a WIN."""
        t0 = pd.Timestamp('2024-01-02 09:30:00')
        bars = _bars([
            (t0, 100.0),                              # 0: entry bar
            (t0 + pd.Timedelta(minutes=1), 99.99),     # 1
            (t0 + pd.Timedelta(minutes=2), 99.60),     # 2: -0.40% price move
        ])
        trade = Trade(
            entry_time=t0, entry_price=100.0, direction='PUT',
            base_score=3, strat_bonus=0, total_score=3, position_size=0.25,
            conditions_met=['c1', 'c2', 'c3'],
        )

        # PUT target defaults to 0.0038 (+0.38%); a 0.40% favorable move
        # (price DOWN) should trip the target, not the stop.
        result = engine.simulate_exit(trade, bars, entry_idx=0, close_col='Close')

        assert result is trade
        assert trade.exit_reason == 'target'
        assert trade.return_pct == pytest.approx(0.004)
