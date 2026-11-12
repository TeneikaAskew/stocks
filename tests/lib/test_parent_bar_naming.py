"""FEAT-STRAT-001 done_when 10: parent bar.

Code identifiers, level keys and user-facing labels say parent bar
(parent_bar_high, parent_bar_low, 'Parent bar high', 'Parent bar low'). No
identifier or string under lib/, gcp/ or platform/ contains 'mother', and
the insight key-levels block labels the levels 'Parent bar high' and
'Parent bar low'. On origin/main lib/strat_levels.py defines
_walk_back_to_mother_bar and the labels read 'Effective PDH'.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from lib.strat_levels import PARENT_BAR_HIGH, PARENT_BAR_LOW, build_session_levels
from tests.lib.level_params_fixtures import fixture_params
from tests.lib.session_levels_helpers import basis

REPO = Path(__file__).resolve().parents[2]


def test_nothing_says_mother():
    hits = []
    for root in ("lib", "gcp", "platform"):
        for p in (REPO / root).rglob("*"):
            if not p.is_file() or "__pycache__" in p.parts or "node_modules" in p.parts:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "mother" in text.lower():
                hits.append(str(p.relative_to(REPO)))
    assert not hits, hits


def test_level_keys_are_parent_bar():
    assert (PARENT_BAR_HIGH, PARENT_BAR_LOW) == ("parent_bar_high", "parent_bar_low")
    idx = pd.bdate_range("2026-10-26", periods=3)
    df = pd.DataFrame([(100, 110, 90, 105), (104, 108, 95, 100), (100, 107, 96, 101)],
                      columns=["Open", "High", "Low", "Close"], index=idx, dtype=float)
    sl = build_session_levels("TST", (idx[-1] + pd.offsets.BDay(1)).date(), df,
                              {"atr_14": 2.0}, None, fixture_params("TST"))
    assert sl.level_named("parent_bar_high").price == 110.0
    assert sl.level_named("parent_bar_low").price == 90.0
    assert sl.level_named("effective_PDH") is None


def test_insight_key_levels_block_labels_the_parent_bar():
    from lib.agents.orchestrator import _derive_key_levels
    b = basis({"PDH": 700.0, "PDL": 680.0, "parent_bar_high": 690.10,
               "parent_bar_low": 670.25}, prior_close=685.0, atr=8.0)
    bundle = {"strat": {"available": True}, "session_levels": {"level_basis": b}}
    kl = _derive_key_levels(bundle)
    assert kl["Parent bar high"] == 690.10
    assert kl["Parent bar low"] == 670.25
    assert not any("Effective" in k or "mother" in k.lower() for k in kl)


def test_the_brief_prints_parent_bar_labels():
    from lib.strat_levels import _display_level_name
    assert _display_level_name("parent_bar_high") == "Parent bar high"
    assert _display_level_name("parent_bar_low") == "Parent bar low"
