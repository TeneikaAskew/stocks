"""FEAT-STRAT-001 done_when 9: one copy per reason.

The orb_only text in the brief banners, the planner rationale, the Discord
push and the schema field descriptions comes from one reason-keyed table,
lib.strat_levels.ORB_ONLY_COPY. Each reason is rendered on each surface,
and no 'cleared every structural' string remains under lib/, gcp/ or
platform/. On origin/main there is no table and the old string is at
strat_levels.py:1346, :1427 and :1509, insight_discord_push.py:166 and :174
and schema.py:313.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from lib.agents.trade_planner import PlanContext, compute_persona_plans
from lib.strat_levels import (
    ORB_ONLY_COPY,
    ORB_ONLY_SCHEMA_DESCRIPTION,
    SessionLevels,
    format_levels_for_brief,
    orb_only_text,
)
from tests.lib.session_levels_helpers import basis

REPO = Path(__file__).resolve().parents[2]
REASONS = ("all_broken_by_premarket", "next_level_outside_window", "no_levels",
           "atr_unavailable", "stale_daily")


def _session_for(reason: str) -> SessionLevels:
    """A real SessionLevels whose both sides are orb_only for `reason`."""
    if reason == "all_broken_by_premarket":
        # Premarket traded through PWH 101 and PWL 99; the premarket extremes
        # themselves sit 10 points away, outside the 3 x ATR 1 window.
        b = basis({"PWH": 101.0, "PWL": 99.0}, prior_close=100.0, atr=1.0,
                  premarket={"pre_high": 110.0, "pre_low": 90.0, "pre_vwap": 100.0})
    elif reason == "next_level_outside_window":
        b = basis({"PWH": 120.0, "PWL": 80.0}, prior_close=100.0, atr=1.0)
    elif reason == "no_levels":
        b = basis({}, prior_close=100.0, atr=1.0)
    elif reason == "atr_unavailable":
        b = basis({"PWH": 101.0, "PWL": 99.0}, prior_close=100.0, atr=None)
    else:
        b = dict(basis({"PWH": 101.0}, prior_close=100.0, atr=1.0), status="stale_daily")
    sl = SessionLevels.from_basis(b)
    assert sl.long.reason == reason and sl.short.reason == reason, (sl.long.reason, sl.short.reason)
    return sl


def test_the_table_holds_every_reason():
    assert set(ORB_ONLY_COPY) == set(REASONS)
    for reason in REASONS:
        assert reason in ORB_ONLY_SCHEMA_DESCRIPTION
        for side, word in (("long", "call"), ("short", "put")):
            text = orb_only_text(reason, side)
            assert text == ORB_ONLY_COPY[reason].format(side=word)
            assert "15-min opening range" in text


@pytest.mark.parametrize("reason", REASONS)
def test_brief_banner(reason):
    text = format_levels_for_brief(_session_for(reason).to_level_map(), "neutral")
    assert f"CALLS: {orb_only_text(reason, 'long')}" in text
    assert f"PUTS: {orb_only_text(reason, 'short')}" in text


@pytest.mark.parametrize("reason", REASONS)
@pytest.mark.parametrize("direction", ["long", "short"])
def test_planner_rationale(reason, direction):
    ctx = PlanContext(direction=direction, conviction="medium", close=100.0, atr=1.0,
                      levels=_session_for(reason), ftfc_score=0.0)
    for plan in compute_persona_plans(ctx):
        assert plan.rationale == "ORB-only: " + orb_only_text(reason, direction)


@pytest.mark.parametrize("reason", REASONS)
@pytest.mark.parametrize("direction", ["long", "short"])
def test_discord_push(reason, direction):
    from gcp import insight_discord_push as push
    report = {"direction": direction,
              "level_basis": _session_for(reason).to_basis()}
    got = push._fmt_targets_field(None, None, [], regime="orb_only",
                                  reason=push._orb_only_reason(report), direction=direction)
    assert got.endswith(orb_only_text(reason, direction))


def test_schema_descriptions():
    from lib.agents.schema import InsightReport
    desc = InsightReport.model_fields["regime"].description
    assert ORB_ONLY_SCHEMA_DESCRIPTION in desc


def test_no_old_copy_remains():
    hits = []
    for root in ("lib", "gcp", "platform"):
        for p in (REPO / root).rglob("*"):
            if not p.is_file() or "__pycache__" in p.parts or "node_modules" in p.parts:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "cleared every structural" in text.lower():
                hits.append(str(p.relative_to(REPO)))
    assert not hits, hits
