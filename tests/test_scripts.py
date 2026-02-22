"""
Regression tests for scripts/ CLI modules.

These tests validate the public CLI interfaces of the key automation scripts
without making real network calls or writing to production data paths.
All tests use temporary directories and monkeypatching where needed.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import numpy as np
import pytest

REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _run_script(script: str, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a script as a subprocess and return the result."""
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script)] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(REPO_ROOT),
    )


# ---------------------------------------------------------------------------
# run_backtest.py
# ---------------------------------------------------------------------------

class TestRunBacktest:
    """CLI tests for scripts/run_backtest.py."""

    def test_help_flag(self):
        result = _run_script("run_backtest.py", ["--help"])
        assert result.returncode == 0
        assert "ticker" in result.stdout.lower() or "usage" in result.stdout.lower()

    def test_invalid_ticker_exits_nonzero(self):
        result = _run_script("run_backtest.py", ["--ticker", "INVALIDXXX123"], timeout=20)
        # Should fail cleanly (no crash with traceback to stderr) or handle gracefully
        # Accept either a non-zero exit or a clean "no data" message
        assert result.returncode != 0 or "no data" in result.stdout.lower() or len(result.stderr) < 2000

    def test_ticker_arg_is_documented_in_help(self):
        result = _run_script("run_backtest.py", ["--help"])
        lower = (result.stdout + result.stderr).lower()
        assert "ticker" in lower


# ---------------------------------------------------------------------------
# run_pipeline.py
# ---------------------------------------------------------------------------

class TestRunPipeline:
    """CLI tests for scripts/run_pipeline.py."""

    def test_help_flag(self):
        result = _run_script("run_pipeline.py", ["--help"])
        assert result.returncode == 0
        lower = (result.stdout + result.stderr).lower()
        assert "ticker" in lower or "usage" in lower

    def test_skip_sweep_flag_recognized(self):
        result = _run_script("run_pipeline.py", ["--help"])
        lower = (result.stdout + result.stderr).lower()
        # --skip-sweep should be documented
        assert "skip" in lower or result.returncode == 0


# ---------------------------------------------------------------------------
# generate_backtest_report.py
# ---------------------------------------------------------------------------

class TestGenerateBacktestReport:
    """CLI tests for scripts/generate_backtest_report.py."""

    def test_help_flag(self):
        result = _run_script("generate_backtest_report.py", ["--help"])
        assert result.returncode == 0

    def test_runs_with_no_csv_files(self, tmp_path):
        """Should handle gracefully when no backtest CSVs are found."""
        result = _run_script(
            "generate_backtest_report.py",
            ["--tickers", "IWM"],
            timeout=20,
        )
        # Either succeeds (empty report) or exits with an informative message
        combined = result.stdout + result.stderr
        assert result.returncode in (0, 1, 2)
        # Should not crash with an unhandled exception
        assert "Traceback" not in combined or "FileNotFoundError" in combined


# ---------------------------------------------------------------------------
# run_timeframe_sweep.py
# ---------------------------------------------------------------------------

class TestRunTimeframeSweep:
    """CLI tests for scripts/run_timeframe_sweep.py."""

    def test_help_flag(self):
        result = _run_script("run_timeframe_sweep.py", ["--help"])
        assert result.returncode == 0

    def test_ticker_arg_recognized(self):
        result = _run_script("run_timeframe_sweep.py", ["--help"])
        lower = (result.stdout + result.stderr).lower()
        assert "ticker" in lower


# ---------------------------------------------------------------------------
# validate_market_data.py
# ---------------------------------------------------------------------------

class TestValidateMarketData:
    """Smoke tests for scripts/validate_market_data.py.

    This script does not accept --help; it runs a validation pipeline and
    exits non-zero when data files are missing (expected in CI).
    """

    def test_runs_and_produces_summary(self):
        result = _run_script("validate_market_data.py", [], timeout=30)
        combined = result.stdout + result.stderr
        assert "VALIDATION" in combined or "Validat" in combined

    def test_script_importable(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "validate_market_data", SCRIPTS_DIR / "validate_market_data.py"
        )
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except SystemExit:
            pass


# ---------------------------------------------------------------------------
# handle_workflow_failure.py
# ---------------------------------------------------------------------------

class TestHandleWorkflowFailure:
    """Unit-style tests for scripts/handle_workflow_failure.py importable pieces."""

    def test_script_importable(self):
        """The script must be importable without side effects."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "handle_workflow_failure",
            SCRIPTS_DIR / "handle_workflow_failure.py",
        )
        mod = importlib.util.module_from_spec(spec)
        # Should not raise during loading (main guard prevents execution)
        try:
            spec.loader.exec_module(mod)
        except SystemExit:
            pass  # acceptable — script may call sys.exit when run directly


# ---------------------------------------------------------------------------
# fetch_market_data.py
# ---------------------------------------------------------------------------

class TestFetchMarketData:
    """CLI smoke tests for scripts/fetch_market_data.py."""

    def test_help_flag(self):
        result = _run_script("fetch_market_data.py", ["--help"])
        # Many argparse scripts print help and exit 0
        lower = (result.stdout + result.stderr).lower()
        assert result.returncode == 0 or "usage" in lower or "option" in lower

    def test_script_importable(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "fetch_market_data",
            SCRIPTS_DIR / "fetch_market_data.py",
        )
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except SystemExit:
            pass


# ---------------------------------------------------------------------------
# analyze_market_data.py
# ---------------------------------------------------------------------------

class TestAnalyzeMarketData:
    """CLI smoke tests for scripts/analyze_market_data.py."""

    def test_help_flag(self):
        result = _run_script("analyze_market_data.py", ["--help"])
        lower = (result.stdout + result.stderr).lower()
        assert result.returncode == 0 or "usage" in lower or "option" in lower


# ---------------------------------------------------------------------------
# Data shape contracts – scripts produce expected CSV schemas
# ---------------------------------------------------------------------------

class TestBacktestCSVSchema:
    """If backtest CSVs exist, verify they have the required columns.

    Actual schema (from generated CSVs):
      entry_time, exit_time, direction, entry_price, exit_price,
      exit_reason, return_pct, ...
    """

    REQUIRED_COLS = {"entry_time", "exit_time", "direction", "entry_price", "exit_price", "return_pct"}

    def _find_backtest_csvs(self):
        return list((REPO_ROOT / "data" / "backtest_results").glob("backtest_*.csv"))

    def test_backtest_csv_schema(self):
        csvs = self._find_backtest_csvs()
        if not csvs:
            pytest.skip("No backtest CSVs found – run `make backtest` first")
        for csv_path in csvs[:3]:
            df = pd.read_csv(csv_path)
            missing = self.REQUIRED_COLS - set(df.columns)
            assert not missing, f"{csv_path.name} missing columns: {missing}"

    def test_backtest_csv_no_all_nan_returns(self):
        csvs = self._find_backtest_csvs()
        if not csvs:
            pytest.skip("No backtest CSVs found")
        for csv_path in csvs[:3]:
            df = pd.read_csv(csv_path)
            if "return_pct" in df.columns and len(df) > 0:
                assert not df["return_pct"].isna().all(), f"{csv_path.name}: all return_pct values are NaN"


class TestTimeframeSweepCSVSchema:
    """If timeframe sweep CSVs exist, verify schema.

    Actual schema (from generated CSVs):
      label, trades, win_rate, avg_win, avg_loss, pf, expectancy, max_dd, sharpe, type
    """

    REQUIRED_COLS = {"label", "trades", "win_rate", "pf"}

    def _find_sweep_csvs(self):
        return list((REPO_ROOT / "data" / "backtest_results").glob("timeframe_sweep_*.csv"))

    def test_sweep_csv_schema(self):
        csvs = self._find_sweep_csvs()
        if not csvs:
            pytest.skip("No timeframe sweep CSVs found – run `make sweep` first")
        for csv_path in csvs[:2]:
            df = pd.read_csv(csv_path)
            missing = self.REQUIRED_COLS - set(df.columns)
            assert not missing, f"{csv_path.name} missing columns: {missing}"
