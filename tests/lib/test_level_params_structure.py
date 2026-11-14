"""FEAT-STRAT-001 per-ticker params, done_when 2 (structural half): no
numbers in the level and plan code.

* The #1753 constants and helpers that held a distance are gone:
  MAX_TRIGGER_DISTANCE_ATR, MAX_TRIGGER_DISTANCE_PCT, MIN_ROOM_PCT and
  compute_room_to_run (lib/strat_levels.py), _ENTRY_BUFFER, _STOP_ATR_MULT,
  _TARGET_R_MULTIPLES and PlanContext.safe_atr (lib/agents/trade_planner.py).
* lib.strat_levels.build_session_levels, lib.indicators
  calculate_premarket_context and lib.agents.trade_planner
  compute_persona_plans, and every same-module function each one calls
  (followed by name through the module's functions and methods), hold no
  int or float literal other than 0, 1, -1, 2, -2 and 100, outside round()
  digit arguments and slice bounds, and read no module-level numeric
  constant other than the persona sizing and FTFC names that done_when 15
  pins (plus two bar counts and the premarket clock boundaries, see
  ALLOWED_COUNTS and ALLOWED_CLOCK).

On the #1753 head it fails: the constants exist and the walk finds 3.0,
0.08, 0.5, 0.1, 0.15 and the persona tables (lib/strat_levels.py:865-866 and
:851, lib/indicators.py:615 and :623, lib/agents/trade_planner.py:91,
:130-148 and :289).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

ALLOWED_VALUES = {0, 1, -1, 2, -2, 100}
# done_when 15: persona sizing, the catalyst damper and the FTFC gates
# (lib/agents/trade_planner.py:151-166) are allocation fractions and score
# thresholds, unchanged by this spec.
ALLOWED_SIZING_AND_FTFC = {
    "_SIZE_BY_CONVICTION", "_CONSERVATIVE_CATALYST_DAMPER", "_CONSERVATIVE_MIN_FTFC",
    "_FTFC_ALIGNED_MIN", "_FTFC_ALIGNED_TOLERANCE",
}
# Bar counts the spec names under "Counts that set the product's shape, not a
# distance" (the 20-bar gap-level lookback) and the parent-bar walk's bound.
# They are not distances, so the policy table does not hold them.
ALLOWED_COUNTS = {"GAP_LEVEL_LOOKBACK_BARS", "_PARENT_BAR_LOOKBACK"}
# The premarket window's clock boundaries (04:00 and 09:30 ET): when the
# session is, not how far price may be.
ALLOWED_CLOCK = {"PREMARKET_START", "REGULAR_SESSION_OPEN"}

REMOVED = {
    "lib/strat_levels.py": ("MAX_TRIGGER_DISTANCE_ATR", "MAX_TRIGGER_DISTANCE_PCT",
                            "MIN_ROOM_PCT", "compute_room_to_run"),
    "lib/agents/trade_planner.py": ("_ENTRY_BUFFER", "_STOP_ATR_MULT", "_TARGET_R_MULTIPLES"),
}
ROOTS = {
    "lib/strat_levels.py": "build_session_levels",
    "lib/indicators.py": "calculate_premarket_context",
    "lib/agents/trade_planner.py": "compute_persona_plans",
}


def _tree(rel: str) -> ast.Module:
    return ast.parse((ROOT / rel).read_text())


def _module_numeric_constants(tree: ast.Module) -> set[str]:
    """Module-level names bound to a value holding a number."""
    out = set()
    for node in tree.body:
        targets, value = [], None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        if value is None:
            continue
        has_number = any(isinstance(n, ast.Constant) and type(n.value) in (int, float)
                         for n in ast.walk(value))
        if has_number:
            out.update(t.id for t in targets if isinstance(t, ast.Name))
    return out


def _functions(tree: ast.Module) -> dict[str, list[ast.AST]]:
    out: dict[str, list[ast.AST]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.setdefault(node.name, []).append(node)
    return out


def _reachable(tree: ast.Module, root: str) -> dict[str, list[ast.AST]]:
    funcs = _functions(tree)
    seen: dict[str, list[ast.AST]] = {}
    todo = [root]
    while todo:
        name = todo.pop()
        if name in seen or name not in funcs:
            continue
        seen[name] = funcs[name]
        for fn in funcs[name]:
            for n in ast.walk(fn):
                if isinstance(n, ast.Call):
                    f = n.func
                    callee = f.id if isinstance(f, ast.Name) else (
                        f.attr if isinstance(f, ast.Attribute) else None)
                    if callee in funcs:
                        todo.append(callee)
                elif isinstance(n, ast.Attribute) and n.attr in funcs:
                    # A property or a method passed by reference.
                    todo.append(n.attr)
    return seen


def _exempt_constant_ids(fn: ast.AST) -> set[int]:
    """Constants that are round() digit arguments or slice bounds."""
    ids = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "round":
            for a in n.args[1:]:
                ids.update(id(c) for c in ast.walk(a) if isinstance(c, ast.Constant))
            for kw in n.keywords:
                if kw.arg == "ndigits":
                    ids.update(id(c) for c in ast.walk(kw.value) if isinstance(c, ast.Constant))
        if isinstance(n, ast.Slice):
            for part in (n.lower, n.upper, n.step):
                if part is not None:
                    ids.update(id(c) for c in ast.walk(part) if isinstance(c, ast.Constant))
    return ids


def _violations(rel: str) -> list[str]:
    tree = _tree(rel)
    constants = _module_numeric_constants(tree)
    allowed_names = ALLOWED_SIZING_AND_FTFC | ALLOWED_COUNTS | ALLOWED_CLOCK
    out = []
    for name, fns in sorted(_reachable(tree, ROOTS[rel]).items()):
        for fn in fns:
            exempt = _exempt_constant_ids(fn)
            for n in ast.walk(fn):
                if (isinstance(n, ast.Constant) and type(n.value) in (int, float)
                        and id(n) not in exempt and n.value not in ALLOWED_VALUES):
                    out.append(f"{rel}:{n.lineno} {name}: literal {n.value!r}")
                if (isinstance(n, ast.Name) and n.id in constants
                        and n.id not in allowed_names):
                    out.append(f"{rel}:{n.lineno} {name}: module constant {n.id}")
    return out


@pytest.mark.parametrize("rel", sorted(REMOVED))
def test_the_1753_distance_constants_are_gone(rel):
    tree = _tree(rel)
    defined = {t.id for node in tree.body if isinstance(node, (ast.Assign, ast.AnnAssign))
               for t in (node.targets if isinstance(node, ast.Assign) else [node.target])
               if isinstance(t, ast.Name)}
    defined |= set(_functions(tree))
    assert not (set(REMOVED[rel]) & defined), sorted(set(REMOVED[rel]) & defined)


def test_plan_context_has_no_safe_atr():
    from lib.agents.trade_planner import PlanContext
    assert not hasattr(PlanContext, "safe_atr")


@pytest.mark.parametrize("rel", sorted(ROOTS))
def test_no_numbers_on_the_level_and_plan_path(rel):
    assert ROOTS[rel] in _functions(_tree(rel))
    assert _violations(rel) == []


def test_the_walk_reaches_the_rules_it_must_cover():
    """The walk is not vacuous: it reaches the side rule, the window check,
    the cluster detector, the premarket acceptance, the target spacing (exits
    in thirds spec) and the persona plan."""
    reach = set(_reachable(_tree("lib/strat_levels.py"), "build_session_levels"))
    assert {"_pick_side", "_within_staleness_window", "detect_level_clusters",
            "_accept_premarket", "compute_gap_levels", "_plan_targets"} <= reach
    plan = set(_reachable(_tree("lib/agents/trade_planner.py"), "compute_persona_plans"))
    assert {"_plan", "compute_risk_metrics", "_build_rationale"} <= plan


def test_the_scan_finds_a_planted_number():
    """A literal 3.0 in a reachable function is reported."""
    src = "def build_session_levels(x):\n    return helper(x)\n\ndef helper(x):\n    return x * 3.0\n"
    tree = ast.parse(src)
    reach = _reachable(tree, "build_session_levels")
    found = [n.value for fn in reach["helper"] for n in ast.walk(fn)
             if isinstance(n, ast.Constant) and n.value not in ALLOWED_VALUES]
    assert found == [3.0]
