"""FEAT-PLAYBOOK-001 B8b: one helper reads the pick rule's version.

v3, v4 and v5 share the pick rule and differ only in how the premarket high
and low were taken, so a reader that asks "is this the pick rule" goes through
lib.strat_levels.is_current_pick_rule. Only the movement statement's reach
population filters on one exact version. Any other comparison with the
version constants, or any other statement parameter built from them, fails
here with its file and line.
"""
import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCANNED = ('lib', 'gcp', 'platform')
WATCHED = {'LEVEL_RULE_VERSION', 'LEVEL_RULE_V3', 'LEVEL_RULE_V4', 'PICK_RULE_VERSIONS'}

# (file, enclosing function) -> why the site may hold the name.
ALLOWED = {
    ('lib/strat_levels.py', 'is_current_pick_rule'): 'the helper, through PICK_RULE_VERSIONS',
    ('lib/strat_levels.py', 'entry_rule_version'): 'the helper, through is_current_pick_rule',
    ('lib/movement_statement.py', '_fetch_reach_rates'): 'the reach population binds one version',
    ('lib/movement_statement.py', '_reach_rate_sql'): 'the reach population filters on one version',
}


def _names(node) -> set:
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id in WATCHED:
            out.add(n.id)
        elif isinstance(n, ast.Attribute) and n.attr in WATCHED:
            out.add(n.attr)
    return out


def sites(source: str, rel: str) -> list:
    """Every (file, function, line, name) where a watched name is one side of
    a comparison (==, !=, in, not in, is, is not) or sits in a dict literal's
    value (a statement's bound parameters)."""
    found = []

    def visit(node, func):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func = node.name
        hit = set()
        if isinstance(node, ast.Compare):
            for side in [node.left, *node.comparators]:
                hit |= _names(side)
        elif isinstance(node, ast.Dict):
            for value in node.values:
                hit |= _names(value)
        for name in sorted(hit):
            found.append((rel, func, node.lineno, name))
        for child in ast.iter_child_nodes(node):
            visit(child, func)

    visit(ast.parse(source), '<module>')
    return found


def scan() -> list:
    out = []
    for top in SCANNED:
        for path in sorted((REPO / top).rglob('*.py')):
            if 'node_modules' in path.parts:
                continue
            rel = path.relative_to(REPO).as_posix()
            out.extend(sites(path.read_text(encoding='utf-8'), rel))
    return out


def test_the_scan_sees_each_shape():
    src = (
        "from lib.strat_levels import LEVEL_RULE_VERSION\n"
        "import lib.strat_levels as m\n"
        "def a(b):\n"
        "    return b.get('rule_version') == LEVEL_RULE_VERSION\n"
        "def c(b):\n"
        "    return b['rule_version'] not in m.PICK_RULE_VERSIONS\n"
        "def d(q):\n"
        "    return q('SELECT 1', {'rule_version': LEVEL_RULE_VERSION})\n"
        "def e(x=LEVEL_RULE_VERSION):\n"
        "    return x\n"
    )
    assert [(f, n) for _, f, _, n in sites(src, 'x.py')] == [
        ('a', 'LEVEL_RULE_VERSION'), ('c', 'PICK_RULE_VERSIONS'), ('d', 'LEVEL_RULE_VERSION')]


def test_only_the_helper_and_the_population_compare_the_version():
    found = scan()
    stray = [f'{rel}:{line} {func}() {name}' for rel, func, line, name in found
             if (rel, func) not in ALLOWED]
    assert not stray, 'the pick rule version is compared outside the helper:\n' + '\n'.join(stray)
    # The helper and the population are really there, so an empty scan
    # (a moved file, a renamed constant) does not pass.
    seen = {(rel, func) for rel, func, _, _ in found}
    assert ('lib/strat_levels.py', 'is_current_pick_rule') in seen
    assert ('lib/movement_statement.py', '_fetch_reach_rates') in seen


# ── Unknown rule version spec (2026-11-16), U9: one classifier ──────────
# A stored rule_version is classified only through
# lib.strat_levels.rule_version_status (and is_current_pick_rule). Beyond
# the watched names above, a comparison is any ast.Compare one of whose
# operands holds a level rule constant (LEVEL_RULE_V2 included), a
# 'feat-strat-001.' string, or a stored version read as .get('rule_version')
# or ['rule_version']; a version handed to the helpers as an argument is the
# allowed route and does not count. The movement statement's two
# reach-population lines bind the version as a query parameter and hold no
# comparison, so the watched-name scan above is what allows them.

LEVEL_RULE_NAMES = WATCHED | {'LEVEL_RULE_V2'}
VERSION_HELPERS = {'rule_version_status', 'is_current_pick_rule', 'entry_rule_version'}
_LEGACY_CHECK = ("U9: a legacy check against LEVEL_RULE_V2 that keeps a v2 basis's own plan, "
                 "unchanged (spec Non-goals; U3)")

# (file, enclosing function) -> why it may compare a level rule version.
LEVEL_RULE_COMPARISONS = {
    ('lib/strat_levels.py', 'is_current_pick_rule'): 'the helper, through PICK_RULE_VERSIONS',
    ('lib/strat_levels.py', '_assemble'): _LEGACY_CHECK,
    ('lib/strat_levels.py', '_pick_side'): _LEGACY_CHECK,
    ('gcp/premarket_playbook_resolver.py', 'plan_inputs'): _LEGACY_CHECK,
}


def _call_name(node) -> str:
    f = node.func
    return f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else '')


def _holds_a_version(node) -> bool:
    if isinstance(node, ast.Call) and _call_name(node) in VERSION_HELPERS:
        return False
    if isinstance(node, ast.Name) and node.id in LEVEL_RULE_NAMES:
        return True
    if isinstance(node, ast.Attribute) and node.attr in LEVEL_RULE_NAMES:
        return True
    if (isinstance(node, ast.Constant) and isinstance(node.value, str)
            and node.value.startswith('feat-strat-001.')):
        return True
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'get' and node.args
            and isinstance(node.args[0], ast.Constant) and node.args[0].value == 'rule_version'):
        return True
    if (isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant)
            and node.slice.value == 'rule_version'):
        return True
    return any(_holds_a_version(child) for child in ast.iter_child_nodes(node))


def comparison_sites(source: str, rel: str) -> list:
    """Every (file, function, line) where a comparison's operand holds a
    level rule version, as defined above."""
    found = []

    def visit(node, func):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func = node.name
        if isinstance(node, ast.Compare) and any(
                _holds_a_version(side) for side in [node.left, *node.comparators]):
            found.append((rel, func, node.lineno))
        for child in ast.iter_child_nodes(node):
            visit(child, func)

    visit(ast.parse(source), '<module>')
    return found


def test_the_comparison_scan_sees_each_shape():
    src = (
        "def a(x):\n"
        "    return x.get('rule_version') == 'feat-strat-001.v5'\n"
        "def b(b):\n"
        "    return b['rule_version'] in VERSIONS\n"
        "def c(v):\n"
        "    return v != LEVEL_RULE_V2\n"
        "def d(self):\n"
        "    return self.rule_version == 'legacy-pattern-v1'\n"
        "def e(basis):\n"
        "    return rule_version_status(basis.get('rule_version')) in REFUSED_RULE_VERSION_STATUSES\n"
    )
    assert [f for _, f, _ in comparison_sites(src, 'x.py')] == ['a', 'b', 'c']


def test_no_other_site_compares_a_level_rule_version():
    found = []
    for top in SCANNED:
        for path in sorted((REPO / top).rglob('*.py')):
            if 'node_modules' in path.parts:
                continue
            rel = path.relative_to(REPO).as_posix()
            found.extend(comparison_sites(path.read_text(encoding='utf-8'), rel))
    seen = {(rel, func) for rel, func, _ in found}
    stray = sorted(f'{rel}:{line} {func}()' for rel, func, line in found
                   if (rel, func) not in LEVEL_RULE_COMPARISONS)
    assert not stray, ('a level rule version is compared outside rule_version_status; route it '
                       'through the helper:\n' + '\n'.join(stray))
    assert seen == set(LEVEL_RULE_COMPARISONS)
    assert ('lib/strat_levels.py', 'rule_version_status') not in seen
    assert ('lib/strat_levels.py', 'newest_pick_rule_version') not in seen
