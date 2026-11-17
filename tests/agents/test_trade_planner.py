"""FEAT-INSIGHT-001: the insight's plan is the brief's stored plan.

Spec: docs/superpowers/specs/2026-11-16-feat-insight-001-insight-one-plan-one-voice.md
Fixture: tests/fixtures/insight_2026_11_16/ (exported read-only, see its
sources.json), loaded through tests/agents/insight_2026_11_16.py.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from tests.agents import insight_2026_11_16 as fx


# ---------------------------------------------------------------------------
# The fixture itself
# ---------------------------------------------------------------------------


def test_fixture_matches_sources_json():
    """The directory holds exactly the nine exported files and sources.json;
    each file's bytes are the ones sources.json records; the short side of
    each stored level_basis carries the spec's D3 numbers. A mismatch with
    the spec is a finding for the owner, never a changed expectation."""
    sources = json.loads((fx.FIXTURE_DIR / "sources.json").read_text())
    expected_files = {f"{t}_{kind}.json" for t in fx.TICKERS
                      for kind in ("stored_report", "level_basis", "brief_row")}
    on_disk = {p.name for p in fx.FIXTURE_DIR.iterdir()}
    assert on_disk == expected_files | {"sources.json"}
    assert set(sources["files"]) == expected_files
    for name, entry in sources["files"].items():
        data = (fx.FIXTURE_DIR / name).read_bytes()
        assert len(data) == entry["bytes"], name
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], name
    assert sources["db_query_execution"].startswith("db-query-")
    assert sources["commit"] is False

    for t in fx.TICKERS:
        entry, trigger_name, stop, stop_name, targets = fx.EXPECTED_SHORT[t]
        short = fx.level_basis(t)["short"]
        assert short["trigger"]["price"] == entry, t
        if trigger_name is not None:
            assert short["trigger"]["name"] == trigger_name, t
        assert short["stop"]["price"] == stop, t
        assert short["stop"]["name"] == stop_name, t
        assert [x["price"] for x in short["targets"]] == targets, t
    assert round(fx.level_basis("IWM")["atr"], 5) == 4.87495
