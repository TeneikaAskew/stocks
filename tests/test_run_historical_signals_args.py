"""Argparse / control-flow tests for scripts/run_historical_signals.py.

Covers the new --from-watchlist iteration mode and --max-tickers cap
introduced for PR D. Mocks the heavy DB / analyzer paths so tests
stay hermetic.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Make the script importable as a module.
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))


@pytest.fixture
def stub_load_watchlist(monkeypatch):
    """Replace gcp.fetchers._watchlist.load_watchlist with a controllable stub."""
    captured = {"return_value": ["IWM", "QQQ", "SPY"]}

    def fake_load(*_a, **_k):
        return list(captured["return_value"])

    import gcp.fetchers._watchlist as wl_mod
    monkeypatch.setattr(wl_mod, "load_watchlist", fake_load)
    return captured


def _import_script(monkeypatch):
    """Import the script module (re-importable across tests via patches)."""
    import importlib
    if "run_historical_signals" in sys.modules:
        del sys.modules["run_historical_signals"]
    mod = importlib.import_module("run_historical_signals")
    return mod


# ---------------------------------------------------------------------------
# _resolve_tickers
# ---------------------------------------------------------------------------


def test_resolve_tickers_symbol_returns_single(monkeypatch):
    mod = _import_script(monkeypatch)
    args = SimpleNamespace(symbol="iwm", from_watchlist=False)
    assert mod._resolve_tickers(args) == ["IWM"]


def test_resolve_tickers_from_watchlist_returns_active(monkeypatch, stub_load_watchlist):
    mod = _import_script(monkeypatch)
    stub_load_watchlist["return_value"] = ["AVGO", "MSFT", "NVDA"]
    args = SimpleNamespace(symbol=None, from_watchlist=True)
    assert mod._resolve_tickers(args) == ["AVGO", "MSFT", "NVDA"]


def test_resolve_tickers_from_watchlist_handles_load_failure(monkeypatch):
    mod = _import_script(monkeypatch)

    import gcp.fetchers._watchlist as wl_mod

    def explode(*_a, **_k):
        raise RuntimeError("Cloud SQL down")

    monkeypatch.setattr(wl_mod, "load_watchlist", explode)
    args = SimpleNamespace(symbol=None, from_watchlist=True)
    assert mod._resolve_tickers(args) == []


# ---------------------------------------------------------------------------
# main() — cap behaviour
# ---------------------------------------------------------------------------


def _build_parsed_args(**overrides):
    """Construct a Namespace matching parse_args() output."""
    defaults = dict(
        symbol=None,
        from_watchlist=True,
        start_date=None,
        end_date=None,
        backfill_from=None,
        force=False,
        dry_run=True,
        lookback_days=2,
        max_tickers=10,
        override_max=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_main_refuses_when_over_cap(monkeypatch, stub_load_watchlist):
    mod = _import_script(monkeypatch)
    stub_load_watchlist["return_value"] = [f"T{i:02d}" for i in range(15)]
    monkeypatch.setattr(mod, "parse_args", lambda: _build_parsed_args(max_tickers=10))

    processed: list[str] = []
    monkeypatch.setattr(mod, "_process_ticker", lambda tk, _a: processed.append(tk) or 0)

    rc = mod.main()
    assert rc == 1
    assert processed == [], "no tickers should have been processed when cap exceeded"


def test_main_override_bypasses_cap(monkeypatch, stub_load_watchlist):
    mod = _import_script(monkeypatch)
    stub_load_watchlist["return_value"] = [f"T{i:02d}" for i in range(15)]
    monkeypatch.setattr(
        mod, "parse_args",
        lambda: _build_parsed_args(max_tickers=10, override_max=True),
    )

    processed: list[str] = []
    monkeypatch.setattr(mod, "_process_ticker", lambda tk, _a: processed.append(tk) or 0)

    rc = mod.main()
    assert rc == 0
    assert len(processed) == 15


def test_main_at_cap_runs_all(monkeypatch, stub_load_watchlist):
    """Boundary: exactly at the cap is allowed."""
    mod = _import_script(monkeypatch)
    stub_load_watchlist["return_value"] = [f"T{i:02d}" for i in range(10)]
    monkeypatch.setattr(mod, "parse_args", lambda: _build_parsed_args(max_tickers=10))

    processed: list[str] = []
    monkeypatch.setattr(mod, "_process_ticker", lambda tk, _a: processed.append(tk) or 0)

    rc = mod.main()
    assert rc == 0
    assert len(processed) == 10


def test_main_empty_watchlist_returns_2(monkeypatch, stub_load_watchlist):
    mod = _import_script(monkeypatch)
    stub_load_watchlist["return_value"] = []
    monkeypatch.setattr(mod, "parse_args", lambda: _build_parsed_args())
    rc = mod.main()
    assert rc == 2


def test_main_per_ticker_failure_does_not_kill_batch(monkeypatch, stub_load_watchlist):
    """One ticker raising shouldn't stop the others."""
    mod = _import_script(monkeypatch)
    stub_load_watchlist["return_value"] = ["IWM", "QQQ", "SPY"]
    monkeypatch.setattr(mod, "parse_args", lambda: _build_parsed_args(max_tickers=10))

    processed: list[str] = []

    def fake_process(tk, _args):
        if tk == "QQQ":
            raise RuntimeError("simulated QQQ failure")
        processed.append(tk)
        return 0

    monkeypatch.setattr(mod, "_process_ticker", fake_process)

    rc = mod.main()
    # batch returns 0 even with one failure (per the existing semantics
    # — partial failures are surfaced via insight_runs.error, not by
    # exiting non-zero from the orchestrator)
    assert rc == 0
    assert "IWM" in processed and "SPY" in processed
    assert "QQQ" not in processed
