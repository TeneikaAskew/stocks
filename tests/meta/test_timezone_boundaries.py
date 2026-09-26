"""Market timestamps change zone only through lib/eastern_time.py.

``market_data_intraday`` came to hold Eastern wall time stamped as UTC because a
writer relabelled a clock reading (``tz_localize(None)``) instead of converting
it (CLAUDE.md 3.9). ``lib/eastern_time.py`` now owns every conversion:
``eastern_index_to_utc`` / ``utc_to_eastern_naive`` for bars,
``market_today`` / ``market_date`` / ``eastern_bounds_utc`` for dates and
windows, ``market_date_sql`` / ``market_today_sql`` for SQL.

This guard finds the patterns those helpers replace, by AST rather than by
grepping for spellings (the retired repo-wide scanner chased spellings and
drifted; see the module docstring of ``lib/eastern_time.py``):

  tz-localize-none   ``.tz_localize(None)`` / ``tz_localize(tz=None)`` /
                     ``.replace(tzinfo=None)``: drops a zone without converting
  utc-parse          ``pd.to_datetime(..., utc=True)``: on naive Eastern text it
                     stamps wall time as UTC (the original bug's other spelling)
  zone-built-locally ``ZoneInfo(...)`` / ``pytz.timezone(...)`` of an Eastern
                     name outside ``lib/eastern_time.py``
  fixed-offset       ``timedelta(hours=4|5)``, ``minutes=240|300``,
                     ``pd.Timedelta("4h")``: Eastern is -4 half the year and -5
                     the other half
  host-today         ``date.today()``, ``datetime.today()``, ``datetime.now()``
                     / ``pd.Timestamp.now()`` / ``.today()`` with no zone,
                     ``datetime.utcnow()``: the container's UTC clock, which is
                     already tomorrow from 20:00 Eastern
  sql-utc-date       SQL text using ``CURRENT_DATE``, ``DATE(<column>)`` or
                     ``<x>ts::date`` / ``<x>_at::date``: a UTC date here

It is a ratchet. Existing hits are recorded in
``tests/fixtures/timezone_boundary_baseline.json`` by identity (file, rule,
enclosing scope and the offending expression, as a multiset; a SQL string by a
hash of its full text), not by count or line number, so a
fixed hit cannot be traded for a new one elsewhere in the file and an edit
that only shifts lines is not a change. They are the remediation backlog. A
hit not in the baseline fails: that is a new violation. A baseline entry that
no longer occurs also fails, with the command to drop it, so a fix cannot be
undone silently. A line that is legitimately UTC (a log stamp, a UTC-by-contract API)
opts out with a trailing ``# tz-ok: <reason>`` comment.

Regenerate the baseline after fixing sites:
    python -m tests.meta.test_timezone_boundaries --write-baseline
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASELINE = REPO / "tests" / "fixtures" / "timezone_boundary_baseline.json"
SCAN_ROOTS = ("gcp", "lib", "scripts", "platform/api")
SKIP_PARTS = {"_archive", "archive", "__pycache__", "node_modules"}
HELPER = "lib/eastern_time.py"
EASTERN_NAMES = {"America/New_York", "US/Eastern", "EST5EDT", "EST", "EDT"}
OPT_OUT = "tz-ok:"

_SQL_UTC_DATE = re.compile(
    r"\bCURRENT_DATE\b|\bDATE\s*\(\s*[A-Za-z_][\w.]*\s*\)|\b[\w.]*(?:ts|_at)\s*::\s*date\b",
    re.IGNORECASE,
)
_OFFSET_STR = re.compile(r"^\s*-?\s*[45]\s*(h|hr|hrs|hour|hours|H)\s*$")
_LOOKS_LIKE_SQL = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|WHERE)\b", re.IGNORECASE)


def _files() -> list[Path]:
    out = []
    for root in SCAN_ROOTS:
        for p in (REPO / root).rglob("*.py"):
            if SKIP_PARTS.isdisjoint(p.relative_to(REPO).parts):
                out.append(p)
    return sorted(out)


def _name(node: ast.AST) -> str:
    """Dotted name of a call target: ``pd.Timedelta``, ``datetime.now``."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


_ALIASABLE = {
    ("datetime", "datetime"): "datetime.datetime",
    ("datetime", "date"): "datetime.date",
    ("pandas", "Timestamp"): "pandas.Timestamp",
    ("pandas", "Timedelta"): "pandas.Timedelta",
    ("pandas", "to_datetime"): "pandas.to_datetime",
    ("datetime", "timedelta"): "datetime.timedelta",
    ("zoneinfo", "ZoneInfo"): "zoneinfo.ZoneInfo",
}


def _aliases(tree: ast.AST) -> dict[str, str]:
    """Local name -> canonical dotted name, for ``from X import Y as Z`` and
    ``import X as Z``, so ``from datetime import datetime as clock`` makes
    ``clock.now()`` read as ``datetime.datetime.now()`` (Codex P2 on #1185)."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                canon = _ALIASABLE.get((node.module, a.name))
                if canon and a.asname:
                    out[a.asname] = canon
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.asname and a.name in ("datetime", "pandas", "zoneinfo"):
                    out[a.asname] = a.name
    return out


def _resolve(fn: str, aliases: dict[str, str]) -> str:
    head, _, rest = fn.partition(".")
    if head in aliases:
        return aliases[head] + ("." + rest if rest else "")
    return fn


def _is_none(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _host_clock(call: ast.Call, kw: dict) -> bool:
    """now()/today() read the container's clock unless given a real zone.
    An explicit ``tz=None`` (or a positional None) is the same host clock
    (Codex P2 on #1185)."""
    if call.args:
        return _is_none(call.args[0])
    tz = kw.get("tz", kw.get("tzinfo"))
    return tz is None or _is_none(tz)


def _hits(path: Path) -> list[tuple[str, int]]:
    """(rule, line) for each hit in *path*."""
    return [(rule, ln) for rule, ln, _ in _scan(path)]


def _scopes(tree: ast.AST) -> dict:
    """node -> dotted name of its enclosing class/function, or '<module>'."""
    out: dict = {}

    def visit(node: ast.AST, scope: str) -> None:
        for child in ast.iter_child_nodes(node):
            out[child] = scope
            name = getattr(child, "name", None)
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                visit(child, name if scope == "<module>" else f"{scope}.{name}")
            else:
                visit(child, scope)
    visit(tree, "<module>")
    return out


def _fstring_text(node: ast.JoinedStr) -> str:
    """An f-string as ONE text, each placeholder rendered as its expression
    (``f"DATE({col})"`` reads ``DATE(col)``). Its literal pieces are separate
    Constant nodes, so matching them one at a time missed a SQL keyword in one
    piece and ``CURRENT_DATE`` in the next (Codex P2 on #1185)."""
    parts = []
    for v in node.values:
        if isinstance(v, ast.Constant):
            parts.append(str(v.value))
        elif isinstance(v, ast.FormattedValue):
            parts.append(ast.unparse(v.value))
    return "".join(parts)


def _identity(node: ast.AST, scope: str) -> str:
    """What makes a hit THIS hit: its enclosing scope and the offending
    expression itself (a SQL string by a hash of its full text), so two hits
    whose first line reads the same (e.g. a bare triple quote) are distinct
    (Codex P2 on #1185). Line numbers are left out, so an edit that only
    shifts code is not a change."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return f"{scope}::str#{hashlib.sha1(node.value.encode()).hexdigest()[:12]}"
    if isinstance(node, ast.JoinedStr):
        return f"{scope}::fstr#{hashlib.sha1(_fstring_text(node).encode()).hexdigest()[:12]}"
    return f"{scope}::{' '.join(ast.unparse(node).split())[:200]}"


def _scan(path: Path) -> list[tuple[str, int, str]]:
    """(rule, line, identity) for each hit in *path*."""
    rel = path.relative_to(REPO).as_posix()
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    lines = src.splitlines()
    found: list[tuple[str, int]] = []

    aliases = _aliases(tree)
    # The literal pieces of an f-string are matched as part of the whole below.
    in_fstring = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)
                  for v in n.values}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = _resolve(_name(node.func), aliases)
            short = fn.rsplit(".", 1)[-1]
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            if short == "tz_localize" and (
                    (node.args and _is_none(node.args[0])) or ("tz" in kw and _is_none(kw["tz"]))):
                found.append(("tz-localize-none", node))
            elif short == "replace" and "tzinfo" in kw and _is_none(kw["tzinfo"]):
                found.append(("tz-localize-none", node))
            elif short == "to_datetime" and isinstance(kw.get("utc"), ast.Constant) \
                    and kw["utc"].value is True:
                found.append(("utc-parse", node))
            elif short in ("ZoneInfo", "timezone") and fn in ("ZoneInfo", "zoneinfo.ZoneInfo", "pytz.timezone") \
                    and node.args and isinstance(node.args[0], ast.Constant) \
                    and node.args[0].value in EASTERN_NAMES and rel != HELPER:
                found.append(("zone-built-locally", node))
            elif short in ("timedelta", "Timedelta") and (
                    ("hours" in kw and isinstance(kw["hours"], ast.Constant)
                     and kw["hours"].value in (4, 5, -4, -5, 4.0, 5.0, -4.0, -5.0))
                    or ("minutes" in kw and isinstance(kw["minutes"], ast.Constant)
                        and kw["minutes"].value in (240, 300, -240, -300))
                    or (node.args and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)
                        and _OFFSET_STR.match(node.args[0].value))):
                found.append(("fixed-offset", node))
            elif (short in ("now", "today")
                  and fn.endswith(("datetime.now", "Timestamp.now", "date.today",
                                   "datetime.today", "Timestamp.today"))
                  and _host_clock(node, kw)) \
                    or short == "utcnow":
                found.append(("host-today", node))
        elif isinstance(node, (ast.Constant, ast.JoinedStr)) and id(node) not in in_fstring:
            if isinstance(node, ast.JoinedStr):
                text = _fstring_text(node)
            elif isinstance(node.value, str):
                text = node.value
            else:
                continue
            if _LOOKS_LIKE_SQL.search(text) and _SQL_UTC_DATE.search(text):
                found.append(("sql-utc-date", node))

    def opted_out(node: ast.AST) -> bool:
        """``# tz-ok:`` on ANY line the node spans (a multi-line call or SQL
        string carries it on whichever line reads best)."""
        lo, hi = node.lineno, getattr(node, "end_lineno", node.lineno) or node.lineno
        return any(OPT_OUT in lines[i - 1] for i in range(lo, min(hi, len(lines)) + 1))

    scope = _scopes(tree)
    return [(rule, node.lineno, _identity(node, scope.get(node, "<module>")))
            for rule, node in found if not opted_out(node)]


def current_hits() -> dict[str, dict[str, list[str]]]:
    """{file: {rule: sorted hit identities}} (see _identity)."""
    out: dict[str, dict[str, list[str]]] = {}
    for p in _files():
        hits = _scan(p)
        if not hits:
            continue
        by_rule: dict[str, list[str]] = {}
        for rule, _, ident in hits:
            by_rule.setdefault(rule, []).append(ident)
        out[p.relative_to(REPO).as_posix()] = {r: sorted(v) for r, v in sorted(by_rule.items())}
    return dict(sorted(out.items()))


def test_no_new_timezone_relabels_and_the_backlog_only_shrinks():
    baseline = json.loads(BASELINE.read_text())
    now = current_hits()
    new, fixed = [], []
    for f in sorted(set(baseline) | set(now)):
        for rule in sorted(set(baseline.get(f, {})) | set(now.get(f, {}))):
            b = Counter(baseline.get(f, {}).get(rule, []))
            n = Counter(now.get(f, {}).get(rule, []))
            new += [f"{f}: {rule}: {src}" for src in (n - b).elements()]
            fixed += [f"{f}: {rule}: {src}" for src in (b - n).elements()]
    assert not new, (
        "New market-time relabel(s). Convert through lib/eastern_time.py, or add "
        "'# tz-ok: <reason>' if the value is genuinely UTC by contract:\n  "
        + "\n  ".join(new)
    )
    assert not fixed, (
        "Baselined sites no longer occur; drop them so they cannot come back:\n  "
        + "\n  ".join(fixed)
        + "\nRun: python -m tests.meta.test_timezone_boundaries --write-baseline"
    )


def test_a_swapped_violation_is_caught_even_when_the_count_is_unchanged(tmp_path, monkeypatch):
    """Codex P2 on #1185: with per-file counts, deleting one baselined
    date.today() and adding a datetime.now() elsewhere left host-today at 1
    and passed. Identity catches both halves."""
    mod = sys.modules[__name__]
    f = tmp_path / "gcp" / "x.py"
    f.parent.mkdir(parents=True)
    f.write_text("from datetime import date\nd = date.today()\n")
    monkeypatch.setattr(mod, "REPO", tmp_path)
    base = tmp_path / "baseline.json"
    monkeypatch.setattr(mod, "BASELINE", base)
    base.write_text(json.dumps(current_hits()))
    f.write_text("from datetime import datetime\nn = datetime.now()\n")
    try:
        test_no_new_timezone_relabels_and_the_backlog_only_shrinks()
    except AssertionError as e:
        assert "datetime.now()" in str(e)
    else:
        raise AssertionError("a swapped violation passed the ratchet")


def test_two_sql_strings_that_open_the_same_way_are_distinct(tmp_path, monkeypatch):
    """Codex P2 on #1185 (538ffc2): identities were the stripped first line, so
    every multi-line SQL string was just a triple quote. Fixing one and adding
    another left the multiset unchanged and passed."""
    mod = sys.modules[__name__]
    f = tmp_path / "gcp" / "q.py"
    f.parent.mkdir(parents=True)
    f.write_text('A = """\nSELECT 1 FROM t WHERE DATE(ts) = :d\n"""\n')
    monkeypatch.setattr(mod, "REPO", tmp_path)
    base = tmp_path / "baseline.json"
    monkeypatch.setattr(mod, "BASELINE", base)
    base.write_text(json.dumps(current_hits()))
    f.write_text('A = """\nSELECT 1 FROM t WHERE created_at::date = CURRENT_DATE\n"""\n')
    try:
        test_no_new_timezone_relabels_and_the_backlog_only_shrinks()
    except AssertionError as e:
        assert "str#" in str(e)
    else:
        raise AssertionError("a replaced SQL string passed the ratchet")


def test_the_helper_module_is_the_only_place_eastern_is_built():
    offenders = [f for f, c in current_hits().items() if "zone-built-locally" in c]
    baseline = json.loads(BASELINE.read_text())
    allowed = {f for f, c in baseline.items() if "zone-built-locally" in c}
    assert set(offenders) <= allowed, sorted(set(offenders) - allowed)


def test_the_guard_catches_each_pattern(tmp_path, monkeypatch):
    """The rules are only worth having if they fire. One seeded example each."""
    sample = tmp_path / "gcp" / "seeded.py"
    sample.parent.mkdir(parents=True)
    sample.write_text(
        "import datetime as dt\n"
        "import pandas as pd\n"
        "from datetime import date, datetime, timedelta\n"
        "from zoneinfo import ZoneInfo\n"
        "idx = idx.tz_localize(None)\n"
        "idx = idx.tz_localize(tz=None)\n"
        "t = t.replace(tzinfo=None)\n"
        "s = pd.to_datetime(raw, utc=True)\n"
        "z = ZoneInfo('America/New_York')\n"
        "off = timedelta(hours=4)\n"
        "off = timedelta(minutes=300)\n"
        "off = pd.Timedelta('4h')\n"
        "d = date.today()\n"
        "d = datetime.today()\n"
        "n = datetime.now()\n"
        "n = dt.datetime.now()\n"
        "n = pd.Timestamp.now()\n"
        "q = 'SELECT 1 FROM t WHERE DATE(created_at) = CURRENT_DATE'\n"
        "q2 = 'SELECT 1 FROM t WHERE a.created_at::date = :d'\n"
        "q3 = f'SELECT * FROM t WHERE DATE({column}) = CURRENT_DATE'\n"
        "q4 = f'SELECT * FROM {tbl} WHERE ' f'{col} >= CURRENT_DATE'\n"
        "ok = datetime.utcnow()  # tz-ok: log stamp\n"
        "ok2 = datetime.now(tz=ET)\n"
        "ok3 = pd.Timestamp.now(tz='UTC')\n"
        "n = datetime.now(tz=None)\n"
        "n = pd.Timestamp.now(None)\n"
        "d = pd.Timestamp.today(tz=None)\n"
        "from datetime import datetime as clock, date as day\n"
        "import pandas as p2\n"
        "n = clock.now()\n"
        "d = day.today()\n"
        "n = p2.Timestamp.now()\n"
        "ok4 = datetime.utcnow(\n"
        ")  # tz-ok: opt-out on the closing line of a multi-line call\n"
    )
    monkeypatch.setattr(sys.modules[__name__], "REPO", tmp_path)
    rules = Counter(r for r, _ in _hits(sample))
    assert rules == Counter({"tz-localize-none": 3, "utc-parse": 1, "zone-built-locally": 1,
                             "fixed-offset": 3, "host-today": 11, "sql-utc-date": 4})


if __name__ == "__main__":
    if "--write-baseline" in sys.argv:
        BASELINE.write_text(json.dumps(current_hits(), indent=1, sort_keys=True) + "\n")
        print(f"wrote {BASELINE.relative_to(REPO)}")
    else:
        print(json.dumps(current_hits(), indent=1))
