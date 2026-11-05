"""lib/eastern_time.py is the only NYSE calendar in the repo.

Why (FEAT-DATA-001): five hand-written holiday sets and three direct
``pandas_market_calendars`` imports used to disagree about which days the
market is open (one list stopped at 2026, another had no early closes). They
now all call ``lib.eastern_time``. This guard keeps it that way, by AST rather
than by grepping spellings, over every Python module the product runs:

  no-direct-import  ``import pandas_market_calendars`` /
                    ``from pandas_market_calendars ...`` anywhere but
                    ``lib/eastern_time.py``, which owns the lazy import and the
                    process-wide calendar object
  no-holiday-set    an assignment whose target name contains HOLIDAY or CLOSURE
                    and whose value is a set / list / tuple / frozenset of
                    ``date(...)`` calls: a second calendar, one year long
  retired-names     ``MARKET_HOLIDAYS_2026`` / ``NYSE_FULL_CLOSURES`` in any
                    file text, comments and docstrings included, so a stale
                    reference cannot send the next reader to a list that no
                    longer exists

Each scanner takes the files to scan, so the last tests below point it at a
throwaway fixture and prove the guard goes red; a guard that cannot fail is
not a guard.

Repo-level invariant, so it lives in tests/meta/ (two levels below root).
"""
from __future__ import annotations

import ast
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ("lib", "gcp", "scripts", "platform/api")
SKIP_PARTS = {"_archive", "archive", "__pycache__", "node_modules"}
CALENDAR_MODULE = "pandas_market_calendars"
OWNER = "lib/eastern_time.py"
RETIRED_NAMES = ("MARKET_HOLIDAYS_2026", "NYSE_FULL_CLOSURES")
_CONTAINER_CALLS = {"set", "frozenset", "list", "tuple"}


def _files(suffixes: tuple[str, ...] = (".py",)) -> list[Path]:
    out = []
    for root in SCAN_ROOTS:
        base = REPO / root
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix in suffixes and SKIP_PARTS.isdisjoint(p.relative_to(REPO).parts):
                out.append(p)
    return sorted(out)


def _parse(path: Path) -> ast.AST:
    # A module that does not parse is not "clean": let the SyntaxError fail the test.
    # Other modules' own SyntaxWarnings (a stray escape in a docstring) are not this guard's to report.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _is_calendar_module(name: str | None) -> bool:
    return name is not None and (name == CALENDAR_MODULE or name.startswith(CALENDAR_MODULE + "."))


def scan_direct_imports(files: list[Path], *, root: Path = REPO, owner: str = OWNER) -> list[str]:
    """``file:line`` of every import of the calendar library outside ``owner``."""
    hits = []
    for path in files:
        rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()
        if rel == owner:
            continue
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.Import) and any(_is_calendar_module(a.name) for a in node.names):
                hits.append(f"{rel}:{node.lineno}")
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and _is_calendar_module(node.module):
                hits.append(f"{rel}:{node.lineno}")
    return sorted(hits)


def _target_names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Attribute):
        return [target.attr]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [n for elt in target.elts for n in _target_names(elt)]
    return []


def _is_date_call(node: ast.AST) -> bool:
    """``date(...)`` or ``datetime.date(...)`` / ``dt.date(...)``."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Name) and func.id == "date") or (
        isinstance(func, ast.Attribute) and func.attr == "date"
    )


def _is_container_literal(value: ast.AST) -> bool:
    if isinstance(value, (ast.Set, ast.List, ast.Tuple)):
        return True
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in _CONTAINER_CALLS
    )


def scan_holiday_sets(files: list[Path], *, root: Path = REPO) -> list[str]:
    """``file:line NAME`` of every HOLIDAY/CLOSURE-named container of ``date(...)``."""
    hits = []
    for path in files:
        rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets, value = [node.target], node.value
            else:
                continue
            names = [n for t in targets for n in _target_names(t)]
            flagged = [n for n in names if "HOLIDAY" in n.upper() or "CLOSURE" in n.upper()]
            if flagged and _is_container_literal(value) and any(_is_date_call(n) for n in ast.walk(value)):
                hits.append(f"{rel}:{node.lineno} {flagged[0]}")
    return sorted(hits)


def scan_retired_names(files: list[Path], *, root: Path = REPO) -> list[str]:
    """``file:line NAME`` of every mention of a retired list, comments included."""
    hits = []
    for path in files:
        rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for name in RETIRED_NAMES:
                if name in line:
                    hits.append(f"{rel}:{lineno} {name}")
    return sorted(hits)


# ── The repository ───────────────────────────────────────────────────────────


def test_scan_covers_the_product():
    """An empty scan passes every guard below; make sure it is not empty."""
    rels = {p.relative_to(REPO).as_posix() for p in _files()}
    assert OWNER in rels
    assert any(r.startswith("gcp/") for r in rels)
    assert any(r.startswith("scripts/") for r in rels)
    assert any(r.startswith("platform/api/") for r in rels)


def test_no_direct_calendar_import():
    hits = scan_direct_imports(_files())
    assert hits == [], (
        "import pandas_market_calendars only in lib/eastern_time.py; "
        f"call lib.eastern_time instead: {hits}"
    )


def test_no_hardcoded_holiday_sets():
    hits = scan_holiday_sets(_files())
    assert hits == [], f"a holiday list is a second NYSE calendar; use lib.eastern_time: {hits}"


def test_retired_names_absent():
    # Every file type in the scanned roots, not just .py: a shell script or a
    # doc that still names the retired lists is as misleading as a module.
    hits = scan_retired_names(_files((".py", ".sh", ".sql", ".md", ".yml", ".yaml", ".json", ".txt")))
    assert hits == [], f"retired calendar names still referenced: {hits}"


# ── The guards can fail ──────────────────────────────────────────────────────


def _write(tmp_path: Path, name: str, body: str) -> list[Path]:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return [path]


def test_import_guard_fails_on_each_spelling(tmp_path):
    for i, body in enumerate(
        (
            "import pandas_market_calendars\n",
            "import pandas_market_calendars as mcal\n",
            "def f():\n    import pandas_market_calendars as mcal\n",
            "from pandas_market_calendars import get_calendar\n",
            "from pandas_market_calendars.exchange_calendars_mirror import X\n",
        )
    ):
        files = _write(tmp_path, f"m{i}.py", body)
        assert len(scan_direct_imports(files, root=tmp_path)) == 1, body


def test_import_guard_allows_the_owner_and_unrelated_imports(tmp_path):
    (tmp_path / "lib").mkdir()
    owner = tmp_path / "lib" / "eastern_time.py"
    owner.write_text("def f():\n    import pandas_market_calendars as mcal\n", encoding="utf-8")
    other = _write(tmp_path, "ok.py", "import pandas as pd\nfrom lib.eastern_time import is_session\n")
    assert scan_direct_imports([owner, *other], root=tmp_path) == []


def test_holiday_guard_fails_on_each_shape(tmp_path):
    for i, body in enumerate(
        (
            "from datetime import date\nMARKET_CLOSED_HOLIDAYS = {date(2027, 1, 1)}\n",
            "import datetime as dt\nNYSE_HOLIDAYS = [dt.date(2027, 1, 1)]\n",
            "from datetime import date\nFULL_CLOSURES = (date(2027, 1, 1),)\n",
            "from datetime import date\nholidays = frozenset({date(2027, 1, 1)})\n",
            "from datetime import date\nHOLIDAYS: set = {date(2027, 1, 1)}\n",
            "from datetime import date\nself.holiday_set = set([date(2027, 1, 1)])\n",
        )
    ):
        files = _write(tmp_path, f"h{i}.py", body)
        assert len(scan_holiday_sets(files, root=tmp_path)) == 1, body


def test_holiday_guard_ignores_unrelated_assignments(tmp_path):
    files = _write(
        tmp_path,
        "ok.py",
        "from datetime import date\n"
        "EARNINGS_DATES = {date(2027, 1, 1)}\n"  # not a holiday name
        "HOLIDAY_LABELS = {'new-year'}\n"  # no date(...)
        "HOLIDAY_COUNT = len([1])\n",  # not a container literal
    )
    assert scan_holiday_sets(files, root=tmp_path) == []


def test_retired_name_guard_fails_in_code_and_in_comments(tmp_path):
    files = _write(
        tmp_path,
        "stale.py",
        '"""Reads MARKET_HOLIDAYS_2026."""\n# see NYSE_FULL_CLOSURES\nx = 1\n',
    )
    assert scan_retired_names(files, root=tmp_path) == [
        "stale.py:1 MARKET_HOLIDAYS_2026",
        "stale.py:2 NYSE_FULL_CLOSURES",
    ]
