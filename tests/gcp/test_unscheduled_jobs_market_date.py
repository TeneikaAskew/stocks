"""On-demand and off-evening jobs read the exchange's date (FEAT-DATA-001, stage 1).

`backtest` and `indicator-correlation` have no scheduler (a Discord command or
a hand run starts them, at any hour); the audit runner and `regime-combo` run
on weekend mornings. A run started in the evening took its default window from
the container's UTC date, which is tomorrow. Each test runs at an evening
instant in both seasons and at two instants where the host date agrees.
"""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

import gcp.audit_job_runner as audit_runner
import gcp.backtest_job as backtest_job
import gcp.indicator_correlation_job as correlation_job
import gcp.regime_combo_job as regime_job
from tests.fixtures.market_clock import STANDARD_INSTANTS, freeze_market_clock

four_instants = pytest.mark.parametrize("instant, eastern", STANDARD_INSTANTS)


@four_instants
def test_backtest_window_ends_on_the_exchange_date(monkeypatch, instant, eastern):
    freeze_market_clock(monkeypatch, instant, backtest_job)
    monkeypatch.delenv("BACKTEST_START", raising=False)
    monkeypatch.delenv("BACKTEST_END", raising=False)

    assert backtest_job._resolve_window() == (
        (eastern - timedelta(days=1825)).isoformat(),
        eastern.isoformat(),
    )


@four_instants
def test_audit_runner_window(monkeypatch, instant, eastern):
    # The execution id built from datetime.now().timestamp() is an instant and stays (Appendix B).
    freeze_market_clock(monkeypatch, instant, audit_runner,
                        allow_instants=("datetime.now().timestamp()",))
    ran = []

    def recording_run(argv, check=False):
        ran.append(list(argv))
        return SimpleNamespace(returncode=0)

    for name in ("AUDIT_SCRIPT_ARGS", "AUDIT_ALLOWED_EXIT_CODES", "AUDIT_TRACKING_ISSUE",
                 "CLOUD_RUN_EXECUTION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AUDIT_SCRIPT_MODULE", "x")
    monkeypatch.setenv("AUDIT_WINDOW_DAYS", "30")
    monkeypatch.setattr(audit_runner.subprocess, "run", recording_run)

    assert audit_runner.main() == 0

    (argv,) = ran
    at = argv.index("--start")
    assert argv[at:at + 4] == [
        "--start", (eastern - timedelta(days=30)).isoformat(),
        "--end", eastern.isoformat(),
    ]


@four_instants
@pytest.mark.parametrize("module, variable", [
    (correlation_job, "INDICATOR_CORR_AS_OF"),
    (regime_job, "REGIME_COMBO_AS_OF"),
], ids=["indicator-correlation", "regime-combo"])
def test_correlation_and_regime_default_as_of(monkeypatch, module, variable, instant, eastern):
    freeze_market_clock(monkeypatch, instant, module)
    monkeypatch.delenv(variable, raising=False)
    calls = []
    monkeypatch.setattr(module, "run", lambda *args, **kwargs: calls.append(args))

    assert module.main([]) == 0

    (args,) = calls
    assert args[3] == eastern  # run(tickers, horizons, lookback_days, as_of, ...)


def test_the_audit_runner_starts_when_run_by_path(tmp_path):
    """`python gcp/audit_job_runner.py` puts gcp/, not the repo root, on
    sys.path. The runner reads market_today from lib, so it must find the repo
    root itself, as it found everything it needed before this change."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    runner = Path(__file__).resolve().parents[2] / 'gcp' / 'audit_job_runner.py'
    env = {k: v for k, v in os.environ.items()
           if k not in ('PYTHONPATH', 'AUDIT_SCRIPT_MODULE')}
    ran = subprocess.run([sys.executable, str(runner)], cwd=tmp_path, env=env,
                         capture_output=True, text=True, timeout=120)
    assert 'ModuleNotFoundError' not in ran.stderr, ran.stderr
    # With no module named, the runner's own refusal is the outcome.
    assert ran.returncode == 2, ran.stderr
    assert 'AUDIT_SCRIPT_MODULE env var is required' in ran.stderr
