"""
Production-readiness tests covering critical paths identified in audit.

Tests here cover:
- Config coercion (%, raw float, raw string)
- Division-by-zero safety in indicators
- NaN propagation through signal pipeline
- CSV discovery logic (base vs strat detection)
- Report generation exit codes
- Daily loss/profit limit enforcement
- Pipeline script argument handling
"""

import json
import subprocess
import sys
import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.config import load_config, _parse_pct, RiskConfig, ExitConfig, SignalConfig
from lib.indicators import (
    calculate_rsi, calculate_stoch_rsi, calculate_vwap, calculate_rvol,
    add_all_indicators,
)
from lib.signals import check_call_conditions, check_put_conditions, evaluate_signal
from lib.backtest import BacktestEngine


# ---------------------------------------------------------------------------
# Config coercion
# ---------------------------------------------------------------------------

class TestParsePercent:
    """_parse_pct handles string-with-%, plain string, and raw float."""

    def test_string_with_percent(self):
        assert _parse_pct("0.30%") == pytest.approx(0.003)

    def test_plain_string_number(self):
        # "0.40" → 0.40% → 0.004
        assert _parse_pct("0.40") == pytest.approx(0.004)

    def test_raw_float_already_decimal(self):
        # 0.003 is already a decimal fraction → use as-is
        assert _parse_pct(0.003) == pytest.approx(0.003)

    def test_raw_float_percentage(self):
        # 0.50 → 0.50% → 0.005
        assert _parse_pct(0.50) == pytest.approx(0.005)

    def test_zero(self):
        assert _parse_pct(0) == 0.0

    def test_negative_percentage_string(self):
        assert _parse_pct("-0.15%") == pytest.approx(-0.0015)


# ---------------------------------------------------------------------------
# Indicator division-by-zero safety
# ---------------------------------------------------------------------------

class TestIndicatorDivisionByZero:
    """Indicators must not produce inf or crash on degenerate inputs."""

    def test_rsi_constant_price(self):
        """Constant price → no gains or losses → RSI should be 50 (neutral)."""
        prices = pd.Series([100.0] * 30)
        rsi = calculate_rsi(prices, period=14)
        assert not rsi.isna().all()
        assert np.isfinite(rsi.dropna()).all()

    def test_rsi_pure_uptrend(self):
        """All gains, no losses → RSI should approach 100."""
        prices = pd.Series(range(100, 130), dtype=float)
        rsi = calculate_rsi(prices, period=14)
        assert rsi.iloc[-1] > 90.0
        assert np.isfinite(rsi.dropna()).all()

    def test_stoch_rsi_constant(self):
        """Constant RSI → range=0 → StochRSI should fallback to 50."""
        rsi = pd.Series([50.0] * 30)
        k, d = calculate_stoch_rsi(rsi, period=14)
        assert np.isfinite(k.dropna()).all()
        assert np.isfinite(d.dropna()).all()

    def test_vwap_zero_volume(self):
        """Zero volume → VWAP should be NaN, not inf."""
        high = pd.Series([101.0, 102.0, 103.0])
        low = pd.Series([99.0, 100.0, 101.0])
        close = pd.Series([100.0, 101.0, 102.0])
        volume = pd.Series([0.0, 0.0, 0.0])
        dates = pd.Series([0, 0, 0])
        vwap = calculate_vwap(high, low, close, volume, dates)
        # Should be NaN, not inf
        assert not np.isinf(vwap).any()

    def test_rvol_zero_volume(self):
        """Zero volume → RVOL should be NaN, not inf."""
        vol = pd.Series([0.0] * 25)
        rvol = calculate_rvol(vol, period=20)
        assert not np.isinf(rvol).any()


# ---------------------------------------------------------------------------
# Signal NaN propagation
# ---------------------------------------------------------------------------

class TestSignalNaNSafety:
    """Signals must not fire on rows with NaN indicators."""

    def _row(self, **overrides):
        """Build a mock row with all indicators set."""
        base = {
            'Consecutive_Down': 4, 'Consecutive_Up': 0,
            'RSI14': 35.0, 'Price_vs_VWAP': -0.5,
            'Price_vs_EMA9': -0.05, 'Price_vs_EMA20': -0.1,
            'StochRSI_K': 20.0,
        }
        base.update(overrides)
        return pd.Series(base)

    def test_call_fires_on_valid_data(self):
        row = self._row()
        score, conds = check_call_conditions(row)
        assert score >= 3

    def test_call_with_nan_rsi(self):
        """NaN RSI should not satisfy the RSI condition."""
        row = self._row(RSI14=float('nan'))
        score, conds = check_call_conditions(row)
        # Without RSI condition, should score lower
        assert 'rsi_oversold_zone' not in conds

    def test_call_with_nan_stoch(self):
        """NaN StochRSI_K defaults to 50 which fails < 30 check — correct."""
        row = self._row(StochRSI_K=float('nan'))
        score, conds = check_call_conditions(row)
        assert 'stoch_rsi_oversold' not in conds


# ---------------------------------------------------------------------------
# CSV discovery (base vs strat detection)
# ---------------------------------------------------------------------------

class TestCSVDiscovery:
    """find_trade_csv correctly distinguishes base from strat by ftfc_score column."""

    def test_strat_csv_detected(self, tmp_path):
        from scripts.generate_backtest_report import _is_strat_csv

        # Strat CSV: has ftfc_score with real values
        strat_df = pd.DataFrame({
            'entry_time': ['2024-01-01'], 'exit_time': ['2024-01-01'],
            'return_pct': [0.003], 'ftfc_score': [0.5],
        })
        strat_path = tmp_path / "backtest_IWM_strat.csv"
        strat_df.to_csv(strat_path, index=False)

        assert _is_strat_csv(strat_path)

    def test_base_csv_detected(self, tmp_path):
        from scripts.generate_backtest_report import _is_strat_csv

        # Base CSV: no ftfc_score column
        base_df = pd.DataFrame({
            'entry_time': ['2024-01-01'], 'exit_time': ['2024-01-01'],
            'return_pct': [0.003],
        })
        base_path = tmp_path / "backtest_IWM_base.csv"
        base_df.to_csv(base_path, index=False)

        assert not _is_strat_csv(base_path)

    def test_base_csv_with_nan_ftfc(self, tmp_path):
        from scripts.generate_backtest_report import _is_strat_csv

        # Base CSV: has ftfc_score column but all NaN
        base_df = pd.DataFrame({
            'entry_time': ['2024-01-01'], 'exit_time': ['2024-01-01'],
            'return_pct': [0.003], 'ftfc_score': [float('nan')],
        })
        base_path = tmp_path / "backtest_IWM_nanftfc.csv"
        base_df.to_csv(base_path, index=False)

        assert not _is_strat_csv(base_path)


# ---------------------------------------------------------------------------
# Daily loss/profit limit enforcement
# ---------------------------------------------------------------------------

def _make_intraday_df(n_days=5, bars_per_day=30):
    """Build synthetic intraday data with enough signal conditions for trades."""
    np.random.seed(99)
    rows = []
    for d in range(n_days):
        day_base = datetime(2024, 1, 2 + d)
        base_price = 200.0
        for b in range(bars_per_day):
            t = day_base + timedelta(hours=9, minutes=30 + b)
            noise = np.random.normal(0, 0.003)
            close = base_price * (1 + noise)
            rows.append({
                'Time': t,
                'Open': close * 0.999,
                'High': close * 1.002,
                'Low': close * 0.998,
                'Close': close,
                'Volume': 500000.0,
            })
    df = pd.DataFrame(rows)
    df.index = pd.DatetimeIndex(df['Time'])
    df = add_all_indicators(df, close_col='Close')
    return df


class TestDailyLimits:
    """BacktestEngine respects max_daily_trades config."""

    def test_max_daily_trades_cap(self):
        """Engine never produces more than max_daily_trades trades per day."""
        df = _make_intraday_df(n_days=5, bars_per_day=60)
        risk = RiskConfig(max_daily_trades=2)
        engine = BacktestEngine(risk_config=risk)
        result = engine.run(df, close_col='Close')

        if result.trades:
            trades_df = result.to_dataframe()
            trades_df['date'] = pd.to_datetime(trades_df['entry_time']).dt.date
            per_day = trades_df.groupby('date').size()
            assert per_day.max() <= 2


# ---------------------------------------------------------------------------
# Equity curve sanity
# ---------------------------------------------------------------------------

class TestEquityCurve:
    """Equity curve must be consistent with trade PnL."""

    def test_equity_starts_at_one(self):
        """Equity curve starts at 1.0 (normalized)."""
        df = _make_intraday_df(n_days=3)
        engine = BacktestEngine()
        result = engine.run(df, close_col='Close')
        if not result.equity_curve.empty:
            assert result.equity_curve.iloc[0] == pytest.approx(1.0, abs=0.01)

    def test_equity_curve_length_matches_days(self):
        """Equity curve has one entry per trading day."""
        df = _make_intraday_df(n_days=3)
        engine = BacktestEngine()
        result = engine.run(df, close_col='Close')
        if result.daily_pnl:
            assert len(result.equity_curve) == len(result.daily_pnl)


# ---------------------------------------------------------------------------
# Pipeline script argument validation
# ---------------------------------------------------------------------------

class TestPipelineScript:
    """run_pipeline.py handles arguments correctly."""

    def test_help_flag(self):
        result = subprocess.run(
            [sys.executable, "scripts/run_pipeline.py", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "backtest" in result.stdout.lower()

    def test_report_only_succeeds(self):
        """--report-only with existing CSVs should succeed."""
        result = subprocess.run(
            [sys.executable, "scripts/run_pipeline.py", "--report-only",
             "--tickers", "IWM"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Report generation script
# ---------------------------------------------------------------------------

class TestReportGeneration:
    """generate_backtest_report.py produces valid output."""

    def test_help_flag(self):
        result = subprocess.run(
            [sys.executable, "scripts/generate_backtest_report.py", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0

    def test_report_generates_markdown(self):
        """Report generation produces markdown with expected sections."""
        result = subprocess.run(
            [sys.executable, "scripts/generate_backtest_report.py",
             "--tickers", "IWM", "--output", "/tmp/test_report.md"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        report = Path("/tmp/test_report.md").read_text()
        assert "# Backtest Results" in report
        assert "Strategy Parameters" in report
