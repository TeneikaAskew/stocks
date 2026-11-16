"""FEAT-STRAT-001 done_when 1: one level builder.

An AST walk over lib/, gcp/, platform/ and scripts/ asserts that

* no module outside lib/strat_levels.py calls (or imports) the old level
  helpers or the deprecated build_level_map shim, so every consumer goes
  through build_session_levels or a stored level_basis;
* lib/agents/trade_planner.py holds no level walk of its own (no level
  names, no window or broken rule, no distance cap constant);
* no parent-bar walk (a loop over inside-bar labels) exists outside
  lib/strat_levels.py.

On origin/main this fails at lib/agents/summarizers.py (compute_previous_levels
and the inside-bar walk), gcp/premarket_brief.py, gcp/premarket_playbook_resolver.py,
gcp/signal_monitor.py and platform/api/routers/dashboard.py (build_level_map).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ROOTS = ("lib", "gcp", "platform", "scripts")
BUILDER = REPO / "lib" / "strat_levels.py"
PLANNER = REPO / "lib" / "agents" / "trade_planner.py"

FORBIDDEN_CALLS = {
    "compute_previous_levels",
    "compute_current_levels",
    "_compute_previous_levels",
    "_compute_current_levels",
    "identify_triggers",
    "select_nearest_levels",
    "reanchor_triggers",
    "build_level_map",
    "find_parent_bar",
}

PLANNER_LEVEL_NAMES = {
    "PDH", "PDL", "PDC", "PWH", "PWL", "PWC", "PMH", "PML", "PMC",
    "PQH", "PQL", "PQC", "PYH", "PYL", "PYC",
    "effective_PDH", "effective_PDL", "PMK_H", "PMK_L",
}


def _py_files():
    for root in ROOTS:
        base = REPO / root
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            yield p


def _parse(p: Path):
    try:
        return ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
    except SyntaxError:
        return None


def _called_name(node: ast.Call):
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO))


def test_no_module_outside_the_builder_calls_the_old_level_helpers():
    offenders = []
    for p in _py_files():
        if p == BUILDER:
            continue
        tree = _parse(p)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _called_name(node) in FORBIDDEN_CALLS:
                offenders.append(f"{_rel(p)}:{node.lineno} calls {_called_name(node)}")
            if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("strat_levels"):
                for alias in node.names:
                    if alias.name in FORBIDDEN_CALLS:
                        offenders.append(f"{_rel(p)}:{node.lineno} imports {alias.name}")
    assert not offenders, "level helpers used outside lib/strat_levels.py:\n" + "\n".join(offenders)


def test_the_old_level_helpers_are_not_public():
    import lib.strat_levels as sl

    for name in ("compute_previous_levels", "compute_current_levels",
                 "identify_triggers", "select_nearest_levels", "reanchor_triggers"):
        assert not hasattr(sl, name), f"lib.strat_levels.{name} is still public"
    assert callable(sl.build_session_levels)


def test_trade_planner_holds_no_level_walk():
    tree = _parse(PLANNER)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in PLANNER_LEVEL_NAMES:
                found.append(f"line {node.lineno}: level name {node.value!r}")
        if isinstance(node, ast.Call) and _called_name(node) in {
            "_within_staleness_window", "price_cents", "compute_premarket_levels",
        }:
            found.append(f"line {node.lineno}: calls {_called_name(node)}")
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name) and t.id in {"_EXTENDED_DISTANCE_ATR", "_TOUCH_TOLERANCE"}:
                    found.append(f"line {node.lineno}: defines {t.id}")
        if isinstance(node, ast.FunctionDef) and node.name == "trigger_for":
            found.append(f"line {node.lineno}: defines trigger_for")
    assert not found, "trade_planner walks levels itself:\n" + "\n".join(found)


def _is_inside_bar_loop(node: ast.AST) -> bool:
    """A while/for loop that compares a bar label with '1' or classifies
    candles against the previous bar: the shape of a parent-bar walk."""
    if not isinstance(node, (ast.While, ast.For)):
        return False
    for sub in ast.walk(node):
        if isinstance(sub, ast.Compare):
            for c in [sub.left, *sub.comparators]:
                if isinstance(c, ast.Constant) and c.value == "1":
                    return True
        if isinstance(sub, ast.Call) and _called_name(sub) == "classify_candle":
            return True
    return False


def test_no_parent_bar_walk_outside_the_builder():
    offenders = []
    for p in _py_files():
        if p == BUILDER:
            continue
        tree = _parse(p)
        if tree is None:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            lowered = fn.name.lower()
            if "mother" in lowered or "parent_bar" in lowered:
                offenders.append(f"{_rel(p)}:{fn.lineno} defines {fn.name}")
                continue
            body_src = ast.get_source_segment(p.read_text(encoding="utf-8"), fn) or ""
            if not any(_is_inside_bar_loop(n) for n in ast.walk(fn)):
                continue
            # A loop over inside-bar labels that then reads a bar's High and
            # Low is a parent-bar walk.
            if "'High'" in body_src and "'Low'" in body_src:
                offenders.append(f"{_rel(p)}:{fn.lineno} walks inside bars in {fn.name}")
    assert not offenders, "parent-bar walk outside lib/strat_levels.py:\n" + "\n".join(offenders)


@pytest.mark.parametrize("module", [
    "lib/agents/summarizers.py",
    "gcp/premarket_brief.py",
    "gcp/premarket_playbook_resolver.py",
    "gcp/signal_monitor.py",
    "platform/api/routers/dashboard.py",
])
def test_each_consumer_reaches_the_builder(module):
    src = (REPO / module).read_text(encoding="utf-8")
    assert "build_session_levels" in src or "read_live_level_basis" in src, module
