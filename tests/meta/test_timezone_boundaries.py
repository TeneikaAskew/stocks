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

  tz-localize-none   ``.tz_localize(None)``: drops a zone without converting
  zone-built-locally ``ZoneInfo(...)`` / ``pytz.timezone(...)`` of an Eastern
                     name outside ``lib/eastern_time.py``
  fixed-offset       ``timedelta(hours=4|5)`` / ``pd.Timedelta(hours=4|5)``:
                     Eastern is -4 half the year and -5 the other half
  host-today         ``date.today()``, ``datetime.now()`` with no zone,
                     ``datetime.utcnow()``: the container's UTC clock, which is
                     already tomorrow from 20:00 Eastern
  sql-utc-date       SQL text using ``CURRENT_DATE``, ``DATE(<x>ts)`` or
                     ``<x>ts::date``: a UTC date in this database

It is a ratchet. Existing hits are recorded in
``tests/fixtures/timezone_boundary_baseline.json`` by identity (file, rule and
the stripped source line, as a multiset), not by count or line number, so a
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
    r"\bCURRENT_DATE\b|\bDATE\s*\(\s*[\w.]*ts\s*\)|\b[\w.]*ts\s*::\s*date\b",
    re.IGNORECASE,
)
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


def _is_none(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _hits(path: Path) -> list[tuple[str, int]]:
    rel = path.relative_to(REPO).as_posix()
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    lines = src.splitlines()
    found: list[tuple[str, int]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = _name(node.func)
            short = fn.rsplit(".", 1)[-1]
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            if short == "tz_localize" and node.args and _is_none(node.args[0]):
                found.append(("tz-localize-none", node.lineno))
            elif short in ("ZoneInfo", "timezone") and fn in ("ZoneInfo", "zoneinfo.ZoneInfo", "pytz.timezone") \
                    and node.args and isinstance(node.args[0], ast.Constant) \
                    and node.args[0].value in EASTERN_NAMES and rel != HELPER:
                found.append(("zone-built-locally", node.lineno))
            elif short in ("timedelta", "Timedelta") and "hours" in kw \
                    and isinstance(kw["hours"], ast.Constant) and kw["hours"].value in (4, 5, -4, -5):
                found.append(("fixed-offset", node.lineno))
            elif fn in ("date.today", "datetime.date.today", "datetime.utcnow",
                        "datetime.datetime.utcnow") \
                    or (fn in ("datetime.now", "datetime.datetime.now") and not node.args and not kw):
                found.append(("host-today", node.lineno))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            if _LOOKS_LIKE_SQL.search(text) and _SQL_UTC_DATE.search(text):
                found.append(("sql-utc-date", node.lineno))

    def opted_out(lineno: int) -> bool:
        return 0 < lineno <= len(lines) and OPT_OUT in lines[lineno - 1]

    return [(rule, ln) for rule, ln in found if not opted_out(ln)]


def current_hits() -> dict[str, dict[str, list[str]]]:
    """{file: {rule: sorted stripped source lines}}, the identity of each hit."""
    out: dict[str, dict[str, list[str]]] = {}
    for p in _files():
        hits = _hits(p)
        if not hits:
            continue
        lines = p.read_text(encoding="utf-8").splitlines()
        by_rule: dict[str, list[str]] = {}
        for rule, ln in hits:
            by_rule.setdefault(rule, []).append(lines[ln - 1].strip())
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
        "from datetime import date, datetime, timedelta\n"
        "from zoneinfo import ZoneInfo\n"
        "idx = idx.tz_localize(None)\n"
        "z = ZoneInfo('America/New_York')\n"
        "off = timedelta(hours=4)\n"
        "d = date.today()\n"
        "n = datetime.now()\n"
        "q = 'SELECT 1 FROM t WHERE DATE(ts) = CURRENT_DATE'\n"
        "ok = datetime.utcnow()  # tz-ok: log stamp\n"
    )
    monkeypatch.setattr(sys.modules[__name__], "REPO", tmp_path)
    rules = Counter(r for r, _ in _hits(sample))
    assert rules == Counter({"tz-localize-none": 1, "zone-built-locally": 1,
                             "fixed-offset": 1, "host-today": 2, "sql-utc-date": 1})


if __name__ == "__main__":
    if "--write-baseline" in sys.argv:
        BASELINE.write_text(json.dumps(current_hits(), indent=1, sort_keys=True) + "\n")
        print(f"wrote {BASELINE.relative_to(REPO)}")
    else:
        print(json.dumps(current_hits(), indent=1))
