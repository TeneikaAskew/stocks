"""Tests for the magnitude movement-simulation summary."""
import json
from types import SimpleNamespace

import pytest

from scripts import _magnitude_analysis_helpers as helpers
from scripts.magnitude_movement_sim import _build_summary

_ARGS = SimpleNamespace(ticker="IWM", tf="5m", phase="phase1", run_id="r1",
                        position="straddle", direction="both",
                        label_mode="body")


def test_the_summary_records_the_source_runs_readiness_version():
    """The movement sim is evidence about ONE walk-forward run, so it carries
    that run's policy, not whatever version the code holds when the sim is
    re-run later (Codex P2 on #1187)."""
    summary = _build_summary(_ARGS, 3, 0.12345, 0.1, [],
                             readiness_version="magnitude-production-readiness-v0")
    assert summary["production_readiness_version"] == "magnitude-production-readiness-v0"
    assert summary["n_bars"] == 3
    assert summary["overall_mean_payoff_atr"] == 0.1235


def test_a_pre_policy_source_run_is_recorded_as_none_not_the_current_policy():
    summary = _build_summary(_ARGS, 1, 0.0, 0.0, [], readiness_version=None)
    assert summary["production_readiness_version"] is None


class _Blob:
    def __init__(self, store, name):
        self._store, self.name = store, name

    def exists(self):
        return self.name in self._store

    def download_as_bytes(self):
        return self._store[self.name]


class _Client:
    def __init__(self, store):
        self._store = store

    def bucket(self, _name):
        return SimpleNamespace(blob=lambda n: _Blob(self._store, n))


def test_the_source_version_is_read_from_that_runs_walk_forward_summary(monkeypatch):
    name = helpers.research_prefix("phase1", "IWM", "5m") + "walk_forward_r1.json"
    store = {name: json.dumps(
        {"production_readiness_version": "magnitude-production-readiness-v1"}).encode()}
    monkeypatch.setattr(helpers.gcs, "Client", lambda: _Client(store))
    got = helpers.load_run_readiness_version("phase1", "IWM", "5m", "b", "r1")
    assert got == "magnitude-production-readiness-v1"


def test_a_run_that_predates_the_policy_reads_as_none(monkeypatch):
    name = helpers.research_prefix("phase1", "IWM", "5m") + "walk_forward_r1.json"
    store = {name: json.dumps({"phase": "phase1"}).encode()}
    monkeypatch.setattr(helpers.gcs, "Client", lambda: _Client(store))
    assert helpers.load_run_readiness_version("phase1", "IWM", "5m", "b", "r1") is None


def test_a_missing_run_summary_is_an_error_not_a_default(monkeypatch):
    monkeypatch.setattr(helpers.gcs, "Client", lambda: _Client({}))
    with pytest.raises(SystemExit, match="walk_forward_r1.json"):
        helpers.load_run_readiness_version("phase1", "IWM", "5m", "b", "r1")
