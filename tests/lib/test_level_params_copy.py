"""FEAT-STRAT-001 per-ticker params, done_when 13: the copy states the
ticker's own values.

* No string literal in lib/strat_levels.py, lib/agents/schema.py,
  lib/agents/trade_planner.py or gcp/insight_discord_push.py holds
  '3x ATR', '3 ATR', '8% of price' or '0.5 x ATR'.
* The schema field descriptions in lib/agents/schema.py name no ATR
  multiple in a trigger or regime description.
* The window copy for a side whose window sits at coverage 0.99 states the
  ticker's window, the coverage share as sessions that stayed inside it and
  the exceedance share (1 - coverage) as sessions that went past it, each
  its own figure, and never the coverage share as sessions that reached it.
* The entry-zone rationale states, for an edge at follow-through quantile
  q, that 1 - q of breaks reached it.

On the #1753 head lib/strat_levels.py:1015 and :1024 and
lib/agents/schema.py:250-251 and :314-315 hold the fixed copy.
"""
from __future__ import annotations

import ast
import re
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from lib.agents.trade_planner import PlanContext, compute_persona_plans
from lib.strat_levels import ORB_ONLY_COPY, SessionLevels, orb_only_text
from tests.lib.level_params_fixtures import fixture_params, legacy_db
from tests.lib.session_levels_helpers import basis

ROOT = Path(__file__).resolve().parents[2]
FILES = ("lib/strat_levels.py", "lib/agents/schema.py", "lib/agents/trade_planner.py",
         "gcp/insight_discord_push.py")
FORBIDDEN = ("3x ATR", "3 ATR", "8% of price", "0.5 x ATR")
D = date(2026, 11, 6)


def _strings(rel):
    tree = ast.parse((ROOT / rel).read_text())
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            yield n.lineno, n.value


@pytest.mark.parametrize("rel", FILES)
def test_no_fixed_distance_in_any_string_literal(rel):
    hits = [(ln, f, s[:80]) for ln, s in _strings(rel) for f in FORBIDDEN if f in s]
    assert hits == []


# A number compared against an ATR distance ("< 1.0 typically warns",
# ">= 3 ATR"): a fixed ATR threshold stated as copy.
ATR_THRESHOLD = re.compile(r"[<>≤≥]=?\s*\d+(\.\d+)?")


def _docstring_ids(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = n.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                out.add(id(body[0].value))
    return out


@pytest.mark.parametrize("rel", FILES)
def test_no_string_literal_states_an_atr_threshold(rel):
    """No string literal outside a docstring that mentions ATR compares it
    with a fixed number (the RiskMetrics.stop_distance_atr description said
    '< 1.0 typically warns'). Docstrings are developer notes that cite the
    audits' history; the literals checked here reach a reader or a model."""
    tree = ast.parse((ROOT / rel).read_text())
    skip = _docstring_ids(tree)
    hits = [(n.lineno, n.value[:100]) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip
            and "ATR" in n.value and ATR_THRESHOLD.search(n.value)]
    assert hits == []


def test_no_schema_field_description_states_an_atr_threshold():
    """The same rule over every pydantic field description in
    lib/agents/schema.py, as the report JSON schema carries them."""
    import pydantic

    from lib.agents import schema

    hits = []
    for name in dir(schema):
        model = getattr(schema, name)
        if isinstance(model, type) and issubclass(model, pydantic.BaseModel) \
                and model.__module__ == schema.__name__:
            for field, info in model.model_fields.items():
                d = info.description or ""
                if "ATR" in d and ATR_THRESHOLD.search(d):
                    hits.append((name, field, d))
    assert hits == []


def test_schema_regime_descriptions_name_no_atr_multiple():
    from lib.agents.schema import InsightReport, PersonaPlan
    for model in (PersonaPlan, InsightReport):
        desc = model.model_fields["regime"].description
        assert not re.search(r"\d+(\.\d+)?\s*(x|×)?\s*ATR", desc), desc
        assert "calibrated trigger window" in desc


def _spy_window(value=2.4, q=0.99, lookback=750):
    lp = fixture_params("SPY", D, overrides={"trigger_window_long_atr": value})
    lp.params["trigger_window_long_atr"] = replace(
        lp.params["trigger_window_long_atr"], statistic_q=q, lookback_sessions=lookback)
    b = basis({"PDH": 100.0 + 2.0 * (value + 0.1), "PDL": 98.0}, prior_close=100.0, atr=2.0,
              ticker="SPY", session_date=D, params=lp)
    return SessionLevels.from_basis(b, params=lp)


def test_window_copy_states_coverage_and_exceedance_as_separate_figures():
    s = _spy_window()
    assert s.long.reason == "next_level_outside_window"
    text = orb_only_text(s.long.reason, "long", s.long.window)
    assert text.startswith(
        "No unbroken call level within 2.4 x ATR(14); SPY's daily move stayed inside "
        "that distance on 99% of the last 750 sessions and went past it on 1%.")
    # Never the coverage share as sessions that reached the window.
    assert not re.search(r"reach\w*[^.;]*99%|99%[^.;]*reach", text)


def test_window_copy_follows_the_row():
    s = _spy_window(value=1.85, q=0.95, lookback=500)
    text = orb_only_text(s.long.reason, "long", s.long.window)
    assert "1.85 x ATR(14)" in text and "95% of the last 500 sessions" in text
    assert "went past it on 5%" in text


def test_atr_unavailable_copy_states_the_window():
    lp = fixture_params("SPY", D, overrides={"trigger_window_short_atr": 2.2})
    b = basis({"PDH": 101.0, "PDL": 99.0}, prior_close=100.0, atr=None, ticker="SPY",
              session_date=D, params=lp)
    s = SessionLevels.from_basis(b, params=lp)
    assert s.short.reason == "atr_unavailable"
    text = orb_only_text(s.short.reason, "short", s.short.window)
    assert "ATR(14) is unavailable" in text and "SPY's 2.2 x ATR(14) window" in text


def test_copy_without_a_recorded_window_states_no_number():
    for reason in ORB_ONLY_COPY:
        text = orb_only_text(reason, "long", None)
        assert not re.search(r"\d", text.replace("15-min", "")), (reason, text)


def test_entry_rationale_states_the_reach_share_of_each_edge():
    """Conservative edges at follow-through quantiles 0.20 and 0.65 are
    reached by 80% and 35% of breaks; the aggressive lower edge is the
    trigger itself."""
    db = legacy_db(["SPY"], effective_from=date(2026, 11, 3))
    lp = db.load(["SPY"], D)["SPY"]
    b = basis({"PDH": 105.0, "PDL": 98.0}, prior_close=100.0, atr=2.0,
              ticker="SPY", session_date=D, params=lp)
    ctx = PlanContext(direction="long", conviction="medium", close=100.0, atr=2.0,
                      levels=SessionLevels.from_basis(b, params=lp), ftfc_score=1.0)
    plans = {p.persona: p for p in compute_persona_plans(ctx)}
    cons = plans["conservative"].rationale
    assert "0.10x ATR past the trigger, reached by 80% of past breaks" in cons
    assert "0.40x ATR past the trigger, reached by 35% of past breaks" in cons
    agg = plans["aggressive"].rationale
    assert agg.startswith("entry at the trigger to 0.50x ATR past the trigger, reached by 25%")
    for persona, p in plans.items():
        assert "reached by 20%" not in p.rationale and "reached by 65%" not in p.rationale
