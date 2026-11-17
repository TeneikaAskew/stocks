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
