"""Every Eastern-time derivation must name `America/New_York`.

Two things this pins, and neither is hypothetical here.

**No fixed offset.** A hardcoded `-04:00` / `-05:00` / `EDT` / `EST` is right
for part of the year and wrong for the rest. Nothing in the repo does this
today; this guard is what keeps that true, because the wrong version reads
perfectly plausibly and only misbehaves for half the year.

**No legacy alias.** `US/Eastern` is a *backward link* in the IANA database,
kept for compatibility. It is DST-correct and resolves wherever the backward
links are installed — which is why 18 sites used it for months with no
symptom. It is still the wrong name to write:

* a slim tzdata (Debian's `tzdata-legacy` split, Alpine's default, some
  minimal `zoneinfo` installs) ships the zones without the backward links, so
  `ZoneInfo("US/Eastern")` raises there while `America/New_York` works;
* Cloud Scheduler, Postgres `AT TIME ZONE`, and the Python code all had to
  agree on one spelling, and every scheduler entry uses `America/New_York`
  (read live 2026-09-07: 66 of 66 — an earlier draft of this line said 84 of
  84 from a reading that does not reproduce, and 66 is the count `gcloud
  scheduler jobs list --location=us-east1` returns today);
* one site compared `str(ts.tz).upper() != 'US/EASTERN'` to skip a convert,
  which silently stopped matching the moment the zone was spelled the other
  way.

Hermetic: reads the repo's own source, no network and no database.
"""
from __future__ import annotations

import ast
import functools
import pathlib
import re
from datetime import datetime, timedelta
from typing import NamedTuple
from zoneinfo import ZoneInfo

import pytest

def _repo_root() -> pathlib.Path:
    """Walk up to the checkout root, rather than counting directories.

    `parent.parent.parent` was correct for exactly one layout. Moving this
    file one level deeper would silently resolve REPO to `tests/`, and the
    scans would then cover no production code at all while still passing --
    a guard reporting a clean repository it never looked at. That is the same
    class of breakage the file move already caused once on this branch, so
    counting depth twice would have been a poor lesson.
    """
    here = pathlib.Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / ".git").exists() and (candidate / "gcp").is_dir():
            return candidate
    raise RuntimeError(f"could not locate the repository root above {here}")


REPO = _repo_root()
EASTERN = "America/New_York"

# This file necessarily spells the forbidden names in order to forbid them, so
# it excludes itself. DERIVED, not written out: the exclusion used to be the
# literal "tests/test_eastern_timezone_is_named.py", and when #1001 moved the
# suite into per-area folders the string stopped matching and the guard
# reported its own docstring as a violation. A self-reference that a file move
# can invalidate is not a self-reference.
SELF = str(pathlib.Path(__file__).resolve().relative_to(REPO)).replace("\\", "/")

# `archive/` is retired code kept as a record; `.git` and caches are not source.
SKIP_DIRS = {".git", "node_modules", "__pycache__", "archive", ".venv", "venv"}

# Zone names that mean Eastern but are not the canonical IANA name. `EST5EDT`
# and `US/Eastern` are backward links; `EST` is a fixed-offset zone with no DST
# at all, which is the trap -- it looks like a zone name and silently freezes
# the clock at -05:00 through the summer.
#
# Matched only in a timezone context. A bare "EST" is also an ordinary token --
# `gcp/fetchers/fetch_rss_news.py` lists it as a headline stop-word -- and a
# guard that flags that is a guard people learn to ignore.
_TZ_CONTEXT = (
    r"tz\s*=|tzinfo\s*=|time_?zone\s*=|ZoneInfo\s*\(|pytz\.timezone\s*\(|"
    r"tz_convert\s*\(|tz_localize\s*\(|AT TIME ZONE\s*|--time-zone\s*|"
    r"Timestamp\.now\s*\(|astimezone\s*\("
)
# Directories whose executable sources carry no extension. Pine scripts are
# real source -- `tradingview-pine-scripts/orb-30` and `iwm-scalping` derive
# their trading sessions from a named zone today -- and an extension-only
# collector never looked at them, so a regression there would have passed a
# guard that claims to be repository-wide.
EXTENSIONLESS_SOURCE_DIRS = ("tradingview-pine-scripts",)
_NON_SOURCE_SUFFIXES = {".md", ".txt", ".json", ".png", ".jpg", ".svg"}


def _source_files() -> list[pathlib.Path]:
    out = []
    # YAML and Dockerfiles are where a `TZ: US/Eastern` or `ENV TZ=EST` would
    # live, and neither was scanned -- the guard's docstring says
    # repository-wide (Codex, PR #993).
    for pattern in ("*.py", "*.sql", "*.sh", "*.yml", "*.yaml", "Dockerfile*"):
        for p in REPO.rglob(pattern):
            if SKIP_DIRS & set(p.relative_to(REPO).parts):
                continue
            out.append(p)
    for d in EXTENSIONLESS_SOURCE_DIRS:
        root = REPO / d
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() in _NON_SOURCE_SUFFIXES:
                continue
            if SKIP_DIRS & set(p.relative_to(REPO).parts):
                continue
            out.append(p)
    return sorted(set(out))


# Names that mean Eastern but are not the canonical IANA name.
#
# Split by ambiguity, because that is what decides how hard we can look.
# `US/Eastern` and friends have no meaning other than a timezone, so they are
# banned outright wherever they appear. `EST`/`EDT` are also ordinary tokens --
# `gcp/fetchers/fetch_rss_news.py` lists `EST` as a headline stop-word -- so
# they are only flagged in a timezone context. A guard that flags a stop-word
# is one people learn to ignore.
# Every backward link into an Eastern-observing zone, not just the four that
# happened to be in use here. `US/East-Indiana` and `US/Michigan` are valid
# IANA links (to America/Indiana/Indianapolis and America/Detroit), follow the
# same -05:00/-04:00 pattern, and carry the same slim-tzdata portability
# problem as the rest -- so allowing them let an alternate legacy spelling
# through a guard whose whole purpose is to forbid legacy spellings
# (Codex, PR #993).
# Derived rather than recalled: every entry in IANA's `backward` file whose
# TARGET observes US/Canada Eastern -- America/New_York, America/Detroit,
# America/Toronto, America/Iqaluit, America/Indiana/Indianapolis and
# America/Kentucky/Louisville. That rule is what adds `America/Louisville`,
# `America/Nipigon`, `America/Thunder_Bay` and `America/Pangnirtung`, which a
# list of the spellings anyone had happened to meet did not (Codex, PR #993).
# The canonical targets are deliberately absent: `America/Toronto` is the
# right name for Toronto, and banning it would be a different rule.
# `America/Atikokan`/`America/Coral_Harbour` are absent too -- they link to
# America/Panama, which is EST year-round and is not Eastern.
UNAMBIGUOUS_LEGACY = ("US/Eastern", "EST5EDT", "America/Montreal",
                      "Canada/Eastern", "US/East-Indiana", "US/Michigan",
                      "America/Fort_Wayne", "America/Indianapolis",
                      "America/Louisville", "America/Nipigon",
                      "America/Thunder_Bay", "America/Pangnirtung")
AMBIGUOUS_LEGACY = ("EST", "EDT")
ALL_LEGACY = UNAMBIGUOUS_LEGACY + AMBIGUOUS_LEGACY

# `[:=]`, not `=`. Adding `*.yml`/`*.yaml` to the scan was pointless while the
# context accepted only assignment syntax: a Kubernetes or Compose file writes
# `TZ: EST` and `timezone: "-05:00"` as ordinary mapping entries, so the very
# files the scan was widened to cover kept their standard spelling outside it
# (Codex, PR #993). The colon costs nothing elsewhere -- these keys mean a
# timezone in any file that has them.
# Every alternative is anchored at an identifier boundary. Without it the two
# -character `tz` key matched the TAIL of any identifier ending in those
# letters, so `quartz=EST` read as `tz=EST` and reported a timezone in a line
# that has nothing to do with one -- a false CI failure on ordinary shell or
# YAML, which is precisely what the ambiguous names are kept context-gated to
# avoid (Codex, PR #993).
_B = r"(?<![A-Za-z0-9_])"
_TZ_CONTEXT = (
    _B + r"tz\s*[:=]|" + _B + r"tzinfo\s*[:=]|" + _B + r"time_?zone\s*[:=]|"
    + _B + r"time-zone[:= ]|" + _B + r"ZoneInfo\s*\(|"
    + _B + r"pytz\.timezone\s*\(|" + _B + r"tz_convert\s*\(|"
    + _B + r"tz_localize\s*\(|" + _B + r"AT TIME ZONE\s*|"
    + _B + r"Timestamp\.now\s*\(|" + _B + r"astimezone\s*\(|"
    + _B + r"timezone\s*\(|"
    # Postgres installs a session zone with `SET`, not only `AT TIME ZONE`,
    # and `SET TIME ZONE 'EST'` / `SET timezone TO 'EDT'` freeze the whole
    # connection at a fixed offset -- a wider blast radius than any single
    # expression, and neither spelling was a context (Codex, PR #993).
    # `LOCAL` and `SESSION` are the scope modifiers Postgres accepts between
    # `SET` and the setting name; requiring `TIME ZONE` immediately after
    # `SET` exempted `SET LOCAL timezone TO 'EST'`, which does the same thing
    # for the transaction (Codex, PR #993).
    + _B + r"SET\s+(?:LOCAL\s+|SESSION\s+)?TIME[ _]?ZONE\s*(?:TO\s+)?|"
    # Dockerfiles take `ENV <key> <value>` as well as `ENV <key>=<value>`, and
    # the abbreviated `tz` key required a `:` or `=`. Dockerfiles were added to
    # this scan precisely to cover deployment configuration, so accepting only
    # the equals form let an image pin a fixed Eastern offset with both guards
    # green (Codex, PR #993).
    + _B + r"ENV\s+TZ\s+"
)

# Non-Python source (.sh, .sql, Pine). Regex is the only option here, so the
# unambiguous names are matched with no context requirement at all -- which is
# what catches Pine's POSITIONAL form, `time(timeframe.period, session,
# "US/Eastern")`, where the zone is the third argument and no amount of
# context-prefix matching would reach it.
# IGNORECASE throughout. Postgres reads `AT TIME ZONE` case-insensitively and
# SQL is conventionally written lowercase, so `ts at time zone \'EST\'` -- a
# real way to install the frozen UTC-5 zone this guard exists to reject -- did
# not match a case-sensitive context (Codex, PR #993). It is safe on the
# names too: `US/Eastern` and its siblings mean nothing else in any casing,
# and the ambiguous `EST`/`EDT` still need a timezone context before them and
# a non-word character after, so `estimate` and `edtVersion` stay clean.
NONPY_UNAMBIGUOUS = re.compile(
    r"""['"]?(?:""" + "|".join(re.escape(z) for z in UNAMBIGUOUS_LEGACY)
    + r""")['"]?"""
    r"""(?![A-Za-z0-9_/-])""", re.I
)
NONPY_AMBIGUOUS = re.compile(
    r"(?:" + _TZ_CONTEXT + r")\s*"
    r"""['"]?(?:""" + "|".join(AMBIGUOUS_LEGACY) + r""")['"]?"""
    r"""(?![A-Za-z0-9_/-])""", re.I
)
# `EST5` is POSIX's fixed form -- a std abbreviation with an offset and NO DST
# rule, so it is frozen at UTC-5 all year, and it is what `TZ=EST5` installs
# for a whole process. `UTC-05:00` is the same zone spelled the way pandas and
# several config formats accept it. Both were invisible to a pattern that knew
# only a bare number and the `Etc/GMT` names (Codex, PR #993).
#
# `EST5EDT` deliberately does NOT match here: the anchors keep the `EST5`
# alternative from claiming its prefix, and it belongs to the backward-link
# test rather than this one -- it IS DST-correct, it is just the wrong name.
_FIXED_OFFSET_TEXT = (r"(?:-\s*0?[45]:?00|EST5|"
                      r"(?:UTC|GMT)\s*-\s*0?[45](?::?00)?)")
# Quotes optional, like the legacy-name pattern above and for the same reason:
# `timezone=-05:00` in a shell or YAML file is the ordinary spelling, and
# requiring both quotes exempted it (Codex, PR #993). The lookahead keeps the
# unquoted branch from matching a longer number.
NONPY_FIXED_OFFSET = re.compile(
    r"(?:" + _TZ_CONTEXT + r")\s*['\"]?\s*" + _FIXED_OFFSET_TEXT
    + r"\s*['\"]?(?![A-Za-z0-9_])", re.I
)

# ── Python: parsed, not pattern-matched ────────────────────────────────────
#
# Four rounds of review each defeated a regex with a different valid spelling:
# a line-wrapped call, an unquoted shell value, a string offset,
# `ZoneInfo(key="US/Eastern")`, `timedelta(hours=-5, minutes=0)`. Every fix
# was a narrower pattern and every one of them was beaten by the next
# spelling, because a regex reasons about characters and the question is about
# calls. Python is parsed now. The remaining regex work is confined to files
# that have no parser here, and that boundary is stated rather than implied.

# `gettz` is dateutil's, and python-dateutil is a declared dependency here.
# A whitelist of constructors is a list of the ones someone thought of, which
# is why the unambiguous names are ALSO matched independently of it below.
# Split by how much the NAME ALONE tells you, because `_call_name` reads the
# final attribute and drops the receiver. `translator.localize("EST")` and
# `cache.now("EDT")` are ordinary calls in an i18n layer and a cache, and
# reporting them is a false CI failure on code with no timezone in it -- the
# exact outcome the ambiguous names are kept context-gated to avoid
# (Codex, PR #993).
#
# A SPECIFIC name means a timezone and nothing else, so it is a context on its
# own. A GENERIC one is a context only when the receiver says so: `pytz` or
# `pd` makes `timezone`/`now` a timezone call, an unknown object does not.
# Unambiguous zone names and fixed offsets are still reported through a
# generic call, because those spellings mean one thing wherever they appear;
# it is only the bare `EST`/`EDT` tokens that need the stronger context.
_TZ_CALLS_SPECIFIC = {"ZoneInfo", "tz_localize", "tz_convert", "astimezone",
                      "Timestamp", "gettz", "FixedOffset", "tzoffset"}
_TZ_CALLS_GENERIC = {"timezone", "localize", "now"}
_TZ_CALLS = _TZ_CALLS_SPECIFIC | _TZ_CALLS_GENERIC
# Receivers that make a generic name specific. Alias-resolved, so
# `import pytz as p` still reaches `pytz` -- and read as the LAST attribute of
# the chain, so `pd.Timestamp.now(...)` resolves to `Timestamp`.
_TZ_RECEIVERS = {"pytz", "tz", "dateutil", "pd", "pandas", "datetime",
                 "Timestamp", "zoneinfo"}

# Constructors whose numeric argument IS the offset, in MINUTES.
# `pytz.FixedOffset(-300)` is a fixed UTC-5 zone -- right for Eastern in
# winter, wrong all summer -- and it produced no hit at all: the value is a
# plain integer, so none of the string or `timedelta` checks could see it, and
# the call name was not even in the whitelist (Codex, PR #993). pytz is a
# declared dependency of this repository, so this is a live spelling.
_FIXED_OFFSET_CALLS = {"FixedOffset"}
_EASTERN_OFFSET_MINUTES = (-240, -300)
# dateutil's equivalent, and the unit is the trap: `tzoffset(None, -18000)` is
# the same frozen UTC-5 zone as `FixedOffset(-300)`, in SECONDS. Reading it as
# minutes would have compared -18000 against (-240, -300) and found nothing,
# so the constructor and its unit have to arrive together (Codex, PR #993).
_FIXED_OFFSET_SECOND_CALLS = {"tzoffset"}
# `key` is NOT here. It is the ZoneInfo constructor's parameter name and
# nothing else's, so as a GLOBAL keyword it flags `cache.get(key="EST")` and
# any other ordinary lookup -- a false CI failure on code that has no timezone
# in it, which is how a guard gets skipped (Codex, PR #993). The call branch
# below already reads every argument of a ZoneInfo call, keyword ones
# included, so `ZoneInfo(key="US/Eastern")` is still caught where it means
# something.
_TZ_KEYWORDS = {"tz", "tzinfo", "timezone", "time_zone"}
# A fixed offset does not have to be spelled as a number. `Etc/GMT+5` is a
# real IANA zone frozen at UTC-5 (POSIX inverts the sign), so it stands in for
# Eastern through the winter and is wrong all summer -- exactly what this
# guard rejects, in a spelling that looked like a named zone and so passed
# (Codex, PR #993). Only +4 and +5: the others are not Eastern in any season.
_FIXED_OFFSET_ZONES = ("Etc/GMT+4", "Etc/GMT+5", "Etc/GMT+04", "Etc/GMT+05")
_FIXED_OFFSET_STRINGS = re.compile(
    r"^(?:" + _FIXED_OFFSET_TEXT + r"|Etc/GMT\+0?[45])$")

# Matched with no context, like the unambiguous legacy names and for the same
# reason: `Etc/GMT+5` means one thing.
NONPY_FIXED_ZONE = re.compile(
    r"""['"]?(?:""" + "|".join(re.escape(z) for z in _FIXED_OFFSET_ZONES)
    + r""")['"]?(?![A-Za-z0-9_/-])""", re.I
)


def _call_name(node: ast.Call) -> str:
    fn = node.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return ""


def _call_receiver(node: ast.Call) -> str:
    """What the call is made ON, as written: `pytz` in `pytz.timezone(...)`.

    `_call_name` reads the final attribute and drops this, which is what let
    an unrelated `translator.localize(...)` be classified from its method name
    alone. Read as the LAST attribute of the chain, so `pd.Timestamp.now(...)`
    reports `Timestamp` rather than `pd`; a bare `f(...)` has no receiver.
    """
    fn = node.func
    if not isinstance(fn, ast.Attribute):
        return ""
    inner = fn.value
    if isinstance(inner, ast.Name):
        return inner.id
    if isinstance(inner, ast.Attribute):
        return inner.attr
    return ""


# timedelta's signature, in the order its positional arguments take.
_TIMEDELTA_UNITS = (("days", 86400), ("seconds", 1), ("microseconds", 1e-6),
                    ("milliseconds", 1e-3), ("minutes", 60), ("hours", 3600),
                    ("weeks", 604800))
_EASTERN_OFFSET_SECONDS = (-14400, -18000)   # UTC-4 and UTC-5


def _const_number(node: ast.AST):
    """The value of a numeric constant, negation included, or None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub)):
        inner = _const_number(node.operand)
        return None if inner is None else -inner
    return None


def _is_eastern_fixed_timedelta(node: ast.AST) -> bool:
    """A constant `timedelta(...)` totalling -4h or -5h, however it is spelled.

    Checking only `hours=` missed `timedelta(seconds=-18000)` and the
    positional `timedelta(0, -18000)`, which are the same frozen zone in a
    different spelling (Codex, PR #993) -- the fourth time on this file that a
    check knew one way of writing the thing it forbids. The whole constant is
    evaluated now, so any combination of units that lands on the offset counts,
    and a `timedelta` with a non-constant argument is simply not decidable
    here and is left alone rather than guessed at.
    """
    # `timezone(-timedelta(hours=5))` is the same frozen zone written with the
    # sign outside the call, and it read as a non-constant argument and was
    # left alone (Codex, PR #993). The negation is part of the constant.
    sign = 1
    while isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        if isinstance(node.op, ast.USub):
            sign = -sign
        node = node.operand
    if not isinstance(node, ast.Call) or _call_name(node) != "timedelta":
        return False
    total = 0.0
    for arg, (_, scale) in zip(node.args, _TIMEDELTA_UNITS):
        v = _const_number(arg)
        if v is None:
            return False
        total += v * scale
    units = dict(_TIMEDELTA_UNITS)
    for kw in node.keywords:
        if kw.arg not in units:
            return False          # **kwargs, or a unit we do not model
        v = _const_number(kw.value)
        if v is None:
            return False
        total += v * units[kw.arg]
    return int(round(total * sign)) in _EASTERN_OFFSET_SECONDS


# A new lexical scope. `ast.walk` does not know about these, which is how the
# file-wide binding map came to join names that Python never joins.
# A comprehension has its own scope in Python 3 -- its target is invisible
# outside it -- so it is descended into rather than folded into the enclosing
# function, which would have shadowed the name for the whole function body.
_SCOPES = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
           ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp,
           ast.GeneratorExp)


def _scope_nodes(scope: ast.AST):
    """Every node lexically inside `scope`, not descending into nested scopes.

    A nested `def` is yielded (it is a statement of this scope) but its body is
    not, so a binding made inside it does not leak outward.
    """
    # Reversed onto a LIFO stack, which yields SOURCE order. Pushing them
    # forwards yielded each statement list backwards, so "a later assignment
    # replaces an earlier one" was silently "an earlier one replaces a later".
    # `_keep` makes that harmless for the values this guard cares about -- a
    # legacy binding is never overwritten by a benign one in either direction
    # -- but a traversal that runs backwards is a trap for the next check
    # added here, and it cost one test to notice.
    stack = list(ast.iter_child_nodes(scope))[::-1]
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, _SCOPES):
            stack.extend(list(ast.iter_child_nodes(node))[::-1])


def _target_names(node: ast.AST) -> set[str]:
    """Every name an assignment target BINDS, through tuples and stars.

    Filtered on `ast.Store` context rather than on node type, because a
    target subtree contains loads too: in `cfg[tz] = 1` both `cfg` and `tz`
    are `Name` nodes and NEITHER is bound -- the subscript writes into an
    existing object. Collecting every Name in the subtree shadowed `tz` and
    silenced the guard for the rest of the scope, which is the failure mode
    opposite to the one this shadowing logic exists to fix, and just as bad.
    Python already marks the distinction; this reads it rather than guessing.
    """
    return {sub.id for sub in ast.walk(node)
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store)}


def _bound_names(scope: ast.AST) -> set[str]:
    """Every name this scope binds, by ANY construct, nested scopes excluded.

    This is the shadowing question, and it is separate from "can I resolve
    what it was bound to". `_collect_bindings` only reads `NAME = "literal"`,
    so every OTHER way of rebinding a name left the enclosing scope's binding
    in place and reported it -- `for tz in zones`, `[... for tz in ...]`,
    `name, tz = pair`, `with f as tz`, `except E as tz`, `(tz := f())`,
    `import zoneinfo as tz`. Seven false CI failures of one shape.

    Three of that shape had already been found individually (a file-wide map,
    a parameter, a class body), each fixed by naming the construct. Naming
    constructs one at a time is the losing move this file argues against
    elsewhere: the answer is to collect what Python binds and treat anything
    unresolvable as shadowing, which fails toward silence rather than toward
    a false accusation.

    `global`/`nonlocal` need no special case, and an earlier version that gave
    them one was wrong in both directions. A bare `global TZ` binds nothing,
    so it never enters this set and the outer binding correctly survives. A
    `global TZ` WITH an assignment does rebind the name -- to whatever was
    assigned, which is usually not a literal this file can resolve -- so it
    must shadow, and subtracting the declaration would have kept a stale
    outer binding and reported it. Collecting bindings rather than
    declarations gets both right with no branch.
    """
    out: set[str] = set()
    for node in _scope_nodes(scope):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                out |= _target_names(tgt)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            out |= _target_names(node.target)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            out |= _target_names(node.target)
        elif isinstance(node, ast.withitem):
            if node.optional_vars is not None:
                out |= _target_names(node.optional_vars)
        elif isinstance(node, ast.ExceptHandler):
            if node.name:
                out.add(node.name)
        elif isinstance(node, ast.NamedExpr):
            out |= _target_names(node.target)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                out.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef)):
            out.add(node.name)          # binds in THIS scope, body excluded
        elif isinstance(node, ast.Delete):
            for tgt in node.targets:
                out |= _target_names(tgt)
        elif isinstance(node, ast.MatchAs) and node.name:
            out.add(node.name)
        elif isinstance(node, ast.MatchStar) and node.name:
            out.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            out.add(node.rest)
    return out


def _local_aliases(scope: ast.AST) -> dict[str, str]:
    """`alias -> original name`, for `import X as Y` / `from X import Y as Z`.

    `_call_name` reports the name as written, so `from zoneinfo import
    ZoneInfo as ZI` made `ZI("EST")` miss `_TZ_CALLS` entirely and the call
    was skipped before its argument was looked at (Codex, PR #993). Renaming
    an import is not obscure, and a whitelist that only knows the canonical
    spelling is a whitelist of what someone thought of -- the argument this
    file already makes about call-name whitelists, one level down.

    Collected PER SCOPE, like every other map here. A file-wide version keyed
    on the alias alone joined two unrelated imports that reuse a short name:
    `from zoneinfo import ZoneInfo as load` in one function and `from json
    import loads as load` in another resolved to whichever appeared last in
    the file, which is a MISS in one order and a FALSE POSITIVE in the other
    -- both reproduced (Codex, PR #993).

    One scope aliasing one name to two DIFFERENT originals drops the name
    instead of picking a winner. Which import is in effect at a given line is
    a flow question and this guard is not flow-sensitive, so either answer is
    a guess: keeping the constructor invents a timezone call out of an
    unrelated one, and keeping the other hides a real one. `_keep` resolves
    the same tie the other way for VALUES, deliberately -- a name ever bound
    to a legacy zone is reported. The difference is what a wrong guess costs.
    A misresolved value reports a literal that is genuinely written in the
    file; a misresolved alias reports a call to a function that has nothing to
    do with timezones, which is a false CI failure on correct code.
    """
    seen: dict[str, str] = {}
    conflicted: set[str] = set()
    for node in _scope_nodes(scope):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for a in node.names:
            if not a.asname:
                continue
            # `import pytz as p` -> the tail, so `p.timezone(...)` still
            # resolves through the attribute path.
            original = (a.name if isinstance(node, ast.ImportFrom)
                        else a.name.rsplit(".", 1)[-1])
            if seen.setdefault(a.asname, original) != original:
                conflicted.add(a.asname)
    return {k: v for k, v in seen.items() if k not in conflicted}


def _local_attrs(scope: ast.AST) -> dict[str, dict[str, ast.AST]]:
    """`obj -> {attr: (value, node)}`, for resolving `obj.attr` as a zone.

    Two spellings land in one map because they read identically at the use
    site. `class Settings: tz = "EST"` then `ZoneInfo(Settings.tz)` produced
    nothing -- the literal is ambiguous so it is not reported on its own, and
    `follow` resolved only `ast.Name`, never the `ast.Attribute` the call
    receives. `settings.timezone = "EST"` was invisible for the mirror-image
    reason: the target is an `ast.Attribute`, so it binds no NAME either
    (Codex, PR #993).

    Keyed by the OBJECT name and scoped, not by the attribute name and
    file-wide. A `(ClassName, attr)` key looked specific enough and was not:
    two `class Settings` bodies in two different functions are different
    classes, and conflating them produced a miss in one declaration order and
    a false finding in the reverse. That is the third map on this file to
    default to file-wide, which is why they are now built by one descent.
    """
    out: dict[str, dict[str, ast.AST]] = {}
    for node in _scope_nodes(scope):
        if isinstance(node, ast.ClassDef):
            body = _collect_bindings(_scope_nodes(node), {})
            if body:
                out.setdefault(node.name, {}).update(body)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = (node.targets if isinstance(node, ast.Assign)
                       else [node.target])
            v = node.value
            if _binding_text(v) is None and not _is_eastern_fixed_timedelta(v):
                continue
            for tgt in targets:
                if (isinstance(tgt, ast.Attribute)
                        and isinstance(tgt.value, ast.Name)):
                    _keep(out.setdefault(tgt.value.id, {}), tgt.attr, v)
    return out


def _declared_global_bindings(tree: ast.AST) -> dict[str, ast.AST]:
    """Module-level bindings written from inside a function.

    `def setup(): global TZ; TZ = "EST"` really does bind the module's `TZ`,
    so an unrelated `ZoneInfo(TZ)` elsewhere reads `EST` -- and the descent
    below saw only a local assignment in `setup`, resolved nothing outside it,
    and reported nothing (Codex, PR #993).

    `nonlocal` is the same statement pointed at a different scope, and it gets
    `_nonlocal_bindings` rather than a share of this one. Folding it in here
    was the first attempt and it resolved nothing at all: `nonlocal` is only
    legal when an enclosing scope already binds the name, and that binding
    shadows a module-level entry before it is ever read.
    """
    out: dict[str, ast.AST] = {}
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        declared: set[str] = set()
        for node in _scope_nodes(scope):
            if isinstance(node, ast.Global):
                declared.update(node.names)
        if not declared:
            continue
        for name, src in _collect_bindings(_scope_nodes(scope), {}).items():
            if name in declared:
                _keep(out, name, src)
    return out


def _nonlocal_bindings(tree: ast.AST) -> dict[int, dict[str, ast.AST]]:
    """`id(enclosing scope)` -> the bindings a nested `nonlocal` writes into it.

    `def outer(): TZ = "UTC"; def inner(): nonlocal TZ; TZ = "EST"` rebinds
    OUTER's `TZ`, so a later `ZoneInfo(TZ)` in `outer` reads `EST`. Resolved to
    the nearest enclosing function that binds the name, which is the scope
    Python itself picks -- an approximation that merged it at module level
    instead never fired, because the enclosing binding shadows it.
    """
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node

    out: dict[int, dict[str, ast.AST]] = {}
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        declared: set[str] = set()
        for node in _scope_nodes(scope):
            if isinstance(node, ast.Nonlocal):
                declared.update(node.names)
        if not declared:
            continue
        for name, src in _collect_bindings(_scope_nodes(scope), {}).items():
            if name not in declared:
                continue
            anc = parents.get(id(scope))
            while anc is not None:
                if (isinstance(anc, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.Lambda))
                        and name in _bound_names(anc)):
                    _keep(out.setdefault(id(anc), {}), name, src)
                    break
                anc = parents.get(id(anc))
    return out


class _Env(NamedTuple):
    """What a name resolves to at one point in the tree.

    Three maps, one descent. Each was added separately, each defaulted to
    file-wide, and each was then found by review to join names Python keeps
    apart. Building them together means a scope's shadowing applies to all
    three at once and there is one place left to get that wrong.
    """

    bindings: dict[str, ast.AST]                   # NAME = <value node>
    aliases: dict[str, str]                        # import ... as NAME
    attrs: dict[str, dict[str, ast.AST]]           # NAME.attr = <value node>


_EMPTY_ENV = _Env({}, {}, {})

_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _outer_evaluated(scope: ast.AST):
    """Subtrees of `scope` that Python evaluates in the ENCLOSING scope.

    A scope node is not evaluated all at once. Its header -- decorators, base
    classes, parameter defaults, annotations, a comprehension's first iterable
    -- runs where the `def`/`class`/`[...]` is written, before the new scope
    exists. Mapping the whole node to its own environment therefore resolved
    those against names the runtime cannot see there: with `TZ = "EST"`,
    `def f(TZ="UTC", value=ZoneInfo(TZ))` builds its default from the OUTER
    `EST` while the descent read the parameter's own `UTC` (Codex, PR #993).

    The comprehension case was fixed first and on its own; this is the same
    rule for the rest of the family, which is the level it should have been
    fixed at. Only the FIRST comprehension iterable qualifies -- every later
    clause really does run inside.
    """
    if isinstance(scope, _COMPREHENSIONS):
        yield scope.generators[0].iter
        return
    for attr in ("decorator_list", "bases", "keywords"):
        yield from (getattr(scope, attr, None) or [])
    args = getattr(scope, "args", None)
    if args is None:
        return
    yield from args.defaults
    yield from (d for d in args.kw_defaults if d is not None)
    for group in (args.posonlyargs, args.args, args.kwonlyargs):
        for a in group:
            if a.annotation is not None:
                yield a.annotation
    for extra in (args.vararg, args.kwarg):
        if extra is not None and extra.annotation is not None:
            yield extra.annotation
    if getattr(scope, "returns", None) is not None:
        yield scope.returns


def _parameter_bindings(scope: ast.AST) -> tuple[set[str], dict]:
    """(names a parameter shadows, names a constant default binds).

    Returns empty sets for a Module or ClassDef, neither of which takes
    parameters.
    """
    args = getattr(scope, "args", None)
    if args is None:
        return set(), {}
    positional = list(args.posonlyargs) + list(args.args)
    names = {a.arg for a in positional + list(args.kwonlyargs)}
    for extra in (args.vararg, args.kwarg):
        if extra is not None:
            names.add(extra.arg)

    # `defaults` right-aligns with posonlyargs+args; `kw_defaults` is 1:1 with
    # kwonlyargs, holding None where a keyword-only argument has none.
    defaults: dict[str, ast.AST] = {}
    pairs = list(zip(positional[len(positional) - len(args.defaults):],
                     args.defaults))
    pairs += [(a, d) for a, d in zip(args.kwonlyargs, args.kw_defaults)
              if d is not None]
    for arg, default in pairs:
        if _binding_text(default) is not None:
            defaults[arg.arg] = default
    return names, defaults


def _scoped_envs(tree: ast.AST) -> dict[int, _Env]:
    """`id(node)` -> the names visible at that node, lexically.

    Collecting bindings once for the whole module joined names that share
    nothing but a spelling: an ordinary local `value = "EST"` in one function
    and an independent `ZoneInfo(value)` in another were reported as a single
    violation, which is a CI failure on correct code (Codex, PR #993). The
    guard tolerates ambiguous tokens outside a timezone context precisely so it
    does not do that, and this is the same mistake one level down.

    An inner scope INHERITS its enclosing scopes -- `EASTERN = "US/Eastern"` at
    module level really is what `ZoneInfo(EASTERN)` inside a function reads,
    and following that is the whole point of the map -- and shadows them, which
    is what Python does. The "a legacy binding wins over a later one" rule
    stays inside a single scope, where the reassignment it models happens.
    """
    out: dict[int, _Env] = {}
    globals_ = _declared_global_bindings(tree)
    nonlocals = _nonlocal_bindings(tree)

    def descend(scope: ast.AST, inherited: _Env) -> None:
        # A parameter shadows whatever the enclosing scope bound to that name,
        # and `_collect_bindings` reads assignments only -- so with
        # `TZ = "EST"` at module level, `def load(TZ): ZoneInfo(TZ)` inherited
        # the module's binding and was reported for a value the runtime never
        # sees. That is the same false CI failure the scoping fix was for, one
        # level in (Codex, PR #993).
        #
        # A parameter with a constant string DEFAULT is not merely dropped:
        # `def load(tz="EST")` really does resolve to `EST` when the caller
        # passes nothing, so the default is bound instead.
        # An inherited name survives only if this scope does not rebind it AT
        # ALL -- by any construct, not just the ones resolvable to a literal --
        # and that one `shadowed` set governs all three maps, because Python
        # has one namespace per scope and not three.
        shadowed, defaults = _parameter_bindings(scope)
        shadowed |= _bound_names(scope)

        def survives(m):
            return {k: v for k, v in m.items() if k not in shadowed}

        bindings = survives(inherited.bindings)
        bindings.update(defaults)
        bindings.update(_collect_bindings(_scope_nodes(scope), {}))
        if scope is tree:
            for name, src in globals_.items():
                _keep(bindings, name, src)
        for name, src in nonlocals.get(id(scope), {}).items():
            _keep(bindings, name, src)

        aliases = survives(inherited.aliases)
        aliases.update(_local_aliases(scope))

        attrs = {k: dict(v) for k, v in survives(inherited.attrs).items()}
        for obj, members in _local_attrs(scope).items():
            attrs.setdefault(obj, {}).update(members)

        env = _Env(bindings, aliases, attrs)
        out[id(scope)] = env

        # Python does NOT close over a class namespace: a method does not see
        # the class body's names, it sees the enclosing function or module. So
        # a class-level `value = "EST"` label beside a global
        # `value = "America/New_York"` made `ZoneInfo(value)` in a method
        # resolve to the label the runtime never uses -- a false CI failure,
        # and the third one this scoping machinery has produced (Codex,
        # PR #993). A nested scope under a class inherits what the CLASS
        # inherited, not what the class defines.
        nested = inherited if isinstance(scope, ast.ClassDef) else env
        for node in _scope_nodes(scope):
            out[id(node)] = env
            if not isinstance(node, _SCOPES):
                continue
            descend(node, nested)
            # ...then put back the parts of its header that the enclosing
            # scope evaluates. Done after the descent so it overrides what
            # that wrote, and stopping at nested scopes so a lambda inside a
            # default keeps its own environment.
            for header in _outer_evaluated(node):
                stack = [header]
                while stack:
                    sub = stack.pop()
                    out[id(sub)] = env
                    if not isinstance(sub, _SCOPES):
                        stack.extend(ast.iter_child_nodes(sub))

    descend(tree, _EMPTY_ENV)
    return out


def _binding_text(node: ast.AST) -> "str | None":
    """The string a binding holds, or None when it is not a string constant."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_interesting(node: ast.AST) -> bool:
    """Would this value, reached through a name, be a finding on its own?"""
    text = _binding_text(node)
    if text is not None:
        return text in ALL_LEGACY or bool(_FIXED_OFFSET_STRINGS.match(text))
    return _is_eastern_fixed_timedelta(node)


def _keep(out: dict, name: str, v: ast.AST) -> None:
    """Record `name -> node`, keeping a legacy binding over a benign one.

    Shared by every map here -- bindings, class and instance attributes,
    `global` and `nonlocal` writes -- so the precedence is stated once.

    A LEGACY binding wins, not the last one. "Last assignment wins" was the
    first rule here and it says the opposite of what this file claims: with
    `TZ = "EST"; ZoneInfo(TZ); TZ = "UTC"` the later value overwrote the
    earlier one and the call resolved to `UTC`, so the violation between them
    disappeared (Codex, PR #993). A guard does not need to model reassignment
    correctly, but it must not model it in the direction that hides the thing
    it looks for: if a name is EVER bound to a legacy zone or a fixed offset
    in this scope, that binding is what the guard keeps.

    The stored value is the NODE. A binding used to hold the string it read,
    which meant only string constants could be followed -- so the routine
    `OFFSET = timedelta(hours=-5); timezone(OFFSET)` resolved to nothing and
    the fixed-offset check only ever saw a constructor called inline
    (Codex, PR #993). Keeping the node lets `follow` re-dispatch on whatever
    was bound, and the string checks read it back through `_binding_text`.
    """
    held = out.get(name)
    if held is not None and not _is_interesting(v) and _is_interesting(held):
        return              # do not overwrite a violation with a value
    out[name] = v


def _collect_bindings(nodes, out: dict[str, ast.AST]):
    """`NAME = "..."` -> (value, node), over the nodes handed in.

    `EASTERN = "US/Eastern"` then `ZoneInfo(EASTERN)` is a routine way to share
    one timezone across a module, and it passes a check that only reads
    constants at the call site because the argument is an `ast.Name` (Codex,
    PR #993). The caller decides which nodes are in scope; this reads them.
    """
    for node in nodes:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        else:
            continue
        v = node.value
        # A string constant, whatever it says -- a benign one has to be
        # recorded so it can shadow an inherited legacy one. Plus the
        # constructed offsets, which are only worth carrying when they are the
        # thing this guard looks for; a `timedelta(hours=3)` resolves to
        # nothing and shadowing is already handled by `_bound_names`.
        if _binding_text(v) is None and not _is_eastern_fixed_timedelta(v):
            continue
        for t in targets:
            if isinstance(t, ast.Name):
                _keep(out, t.id, v)
    return out


def _python_hits(path: pathlib.Path, text: str) -> tuple[list[str], list[str]]:
    """(legacy-name hits, fixed-offset hits) for one Python file."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [], []

    legacy, offsets = [], []
    rel = path.relative_to(REPO)
    envs = _scoped_envs(tree)

    def note(bucket, node, what):
        bucket.append(f"{rel}:{getattr(node, 'lineno', 0)}: {what}")

    reported: set[int] = set()
    # A binding can only hold a constant or a constructor call, so a chain is
    # short by construction and cannot cycle. The cap is a guard against a
    # future binding kind that could, not a limit anything hits today.
    _MAX_FOLLOW_DEPTH = 4

    def follow(bucket_legacy, bucket_offsets, node, arg, env, where,
               ambiguous_ok=True, depth=0):
        """Report `arg` when it is, or resolves to, a legacy zone or offset.

        `ambiguous_ok=False` drops the bare `EST`/`EDT` tokens, for a call
        whose name alone does not establish a timezone context.
        """
        if depth == 0:
            # Only the argument as written is marked reported. A value reached
            # THROUGH a name lives at its own assignment, where the standalone
            # scan should still see it.
            reported.add(id(arg))
        legacy_here = ALL_LEGACY if ambiguous_ok else UNAMBIGUOUS_LEGACY
        if isinstance(arg, ast.Constant) and arg.value in legacy_here:
            note(bucket_legacy, arg, where(repr(arg.value)))
            return True
        if (isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                and _FIXED_OFFSET_STRINGS.match(arg.value)):
            note(bucket_offsets, arg, where(repr(arg.value)))
            return True
        if _is_eastern_fixed_timedelta(arg):
            note(bucket_offsets, arg, where("timedelta(hours=-4|-5, ...)"))
            return True
        # An indirection -- `Settings.tz`, `settings.tz`, or a plain name --
        # is resolved to the NODE it was bound to and re-dispatched through
        # this same function, so every spelling above is reachable through a
        # name. Resolving to a string instead was what made
        # `OFFSET = timedelta(hours=-5); timezone(OFFSET)` invisible: the
        # binding held no string, so there was nothing to compare
        # (Codex, PR #993).
        if depth < _MAX_FOLLOW_DEPTH:
            target = label = None
            if (isinstance(arg, ast.Attribute)
                    and isinstance(arg.value, ast.Name)):
                target = env.attrs.get(arg.value.id, {}).get(arg.attr)
                label = f"{arg.value.id}.{arg.attr}"
            elif isinstance(arg, ast.Name):
                target = env.bindings.get(arg.id)
                label = arg.id
            if target is not None:
                return follow(bucket_legacy, bucket_offsets, node, target, env,
                              lambda shown, l=label: where(f"{l} (= {shown})"),
                              ambiguous_ok, depth + 1)
        return False

    for node in ast.walk(tree):
        # The names visible in the scope this node sits in, not the module's.
        env = envs.get(id(node), _EMPTY_ENV)

        # `os.environ["TZ"] = "EST"` -- and `settings["timezone"] = ...`. The
        # target is an ast.Subscript, so it binds no NAME for the map above to
        # follow later: the assignment is itself the use, and the value is the
        # violation (Codex, PR #993).
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for tgt in targets:
                key = tgt.slice if isinstance(tgt, ast.Subscript) else None
                if (isinstance(key, ast.Constant) and isinstance(key.value, str)
                        and key.value.lower() in _TZ_KEYWORDS):
                    follow(legacy, offsets, node, node.value, env,
                           lambda shown, k=key.value: f"[{k!r}] = {shown}")
                # `settings.timezone = "EST"` -- an attribute target binds no
                # NAME either, so the same argument applies to it as to the
                # subscript above, and it was missed for the same reason
                # (Codex, PR #993).
                if (isinstance(tgt, ast.Attribute)
                        and tgt.attr.lower() in _TZ_KEYWORDS):
                    follow(legacy, offsets, node, node.value, env,
                           lambda shown, a=tgt.attr: f".{a} = {shown}")

        # Every UNAMBIGUOUS legacy name, wherever it stands, with no call-name
        # whitelist in front of it. A whitelist is a list of the constructors
        # somebody thought of, and `dateutil.tz.gettz("US/Eastern")` was not
        # on it (Codex, PR #993); nor is the assignment an indirect use reads
        # from. These four words mean a timezone and nothing else, which is
        # exactly the rule the non-Python scan already applies -- `EST`/`EDT`
        # still need a context, because they are also ordinary tokens.
        if (isinstance(node, ast.Constant)
                and node.value in UNAMBIGUOUS_LEGACY
                and id(node) not in reported):
            reported.add(id(node))
            note(legacy, node, repr(node.value))

        # Same rule, different bucket: `Etc/GMT+5` is a named zone frozen at
        # a fixed offset, so it belongs to the offset test rather than the
        # backward-link one.
        if (isinstance(node, ast.Constant)
                and node.value in _FIXED_OFFSET_ZONES
                and id(node) not in reported):
            reported.add(id(node))
            note(offsets, node, repr(node.value))

        # A zone name EMBEDDED in a longer string. Python source carries SQL,
        # and `cur.execute("SELECT ts AT TIME ZONE 'US/Eastern' ...")` is a
        # live way to name the zone that no exact-value check can see -- the
        # constant is the whole statement, not the zone (Codex, PR #993). The
        # `.sql` scan already reads exactly these patterns; this points them at
        # the same SQL when it happens to be quoted inside a `.py` file, so the
        # spelling is not permitted in one place and banned in the other.
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in reported):
            for pattern, bucket in ((NONPY_UNAMBIGUOUS, legacy),
                                    (NONPY_AMBIGUOUS, legacy),
                                    (NONPY_FIXED_ZONE, offsets),
                                    (NONPY_FIXED_OFFSET, offsets)):
                m = pattern.search(node.value)
                if m:
                    reported.add(id(node))
                    note(bucket, node,
                         f"in string: {' '.join(m.group(0).split())[:80]}")
                    break

        # `{"tz": "EST"}` -- a config literal read back at some other site.
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                # `.lower()`, matching the subscript handling above. The
                # conventional spelling for a subprocess environment is
                # `env={"TZ": "EST"}` -- uppercase -- and a case-sensitive
                # membership test walked straight past it while the adjacent
                # `os.environ["TZ"]` form was caught (Codex, PR #993).
                if (isinstance(k, ast.Constant) and isinstance(k.value, str)
                        and k.value.lower() in _TZ_KEYWORDS):
                    follow(legacy, offsets, node, v, env,
                           lambda shown, k=k: f"{k.value!r}: {shown}")

        # A legacy zone name as the value of a timezone-ish keyword, anywhere.
        # `.lower()`, matching the dict-key and subscript branches. Building
        # an environment is conventionally `os.environ.update(TZ="EST")` or
        # `dict(os.environ, TZ="-05:00")` -- uppercase -- and a case-sensitive
        # test walked past both while the adjacent forms were caught, which is
        # the same inconsistency this file already fixed once for dict keys
        # (Codex, PR #993).
        if (isinstance(node, ast.keyword) and node.arg
                and node.arg.lower() in _TZ_KEYWORDS):
            follow(legacy, offsets, node, node.value, env,
                   lambda shown, a=node.arg: f"{a}={shown}")

        if not isinstance(node, ast.Call):
            continue
        name = env.aliases.get(_call_name(node), _call_name(node))
        if name not in _TZ_CALLS:
            continue
        # Whether the CALL is enough of a timezone context to convict a bare
        # `EST`. A specific constructor is; a generic method name is only when
        # its receiver says so. Without this, `translator.localize("EST")` and
        # `cache.now("EDT")` were reported, which is a false CI failure on
        # code that has no timezone in it (Codex, PR #993).
        receiver = _call_receiver(node)
        specific = (name in _TZ_CALLS_SPECIFIC
                    or env.aliases.get(receiver, receiver) in _TZ_RECEIVERS)

        # `pytz.FixedOffset(-300)` and `dateutil.tz.tzoffset(None, -18000)` --
        # the offset is a plain number, so no string or `timedelta` check
        # could ever see it, and the two constructors disagree about the UNIT.
        if name in _FIXED_OFFSET_CALLS or name in _FIXED_OFFSET_SECOND_CALLS:
            seconds = name in _FIXED_OFFSET_SECOND_CALLS
            # `tzoffset(name, offset)` takes the offset SECOND; `FixedOffset`
            # takes it first. Both also accept it by keyword.
            positional = list(node.args)[1:] if seconds else list(node.args)
            candidate = next(
                (a for a in positional
                 + [k.value for k in node.keywords if k.arg in (None, "offset")]),
                None)
            value = _const_number(candidate) if candidate is not None else None
            wanted = (_EASTERN_OFFSET_SECONDS if seconds
                      else _EASTERN_OFFSET_MINUTES)
            if value is not None and int(value) in wanted:
                reported.add(id(candidate))
                note(offsets, node,
                     f"{name}({value:g}) {'seconds' if seconds else 'minutes'}")
                continue
        # Positional and keyword arguments alike.
        for arg in list(node.args) + [k.value for k in node.keywords]:
            follow(legacy, offsets, node, arg, env,
                   lambda shown, n=name: f"{n}(... {shown} ...)",
                   ambiguous_ok=specific)

    # `ast.walk` is breadth-first, so a call is visited before its own
    # arguments: a constant already reported with the call that gives it
    # meaning is not reported a second time as a bare literal.
    return list(dict.fromkeys(legacy)), list(dict.fromkeys(offsets))


@functools.lru_cache(maxsize=1)
def _scan() -> tuple[list[str], list[str]]:
    """Repository-wide (legacy-name hits, fixed-offset hits).

    Cached: the two tests below ask the same question of the same tree, and
    the scan reads and parses 612 files. Uncached it ran twice at ~6.8 s each,
    so the guard cost the suite seven seconds of duplicated work for one
    answer (Codex, PR #993). Nothing in this module mutates the tree between
    calls, and a test that needs a fresh read can call `_scan.cache_clear()`.

    Python is parsed; everything else is matched against whole file text --
    not line by line, because a formatter wrapping a call put the two halves
    on separate lines and neither matched.
    """
    legacy, offsets = [], []
    for p in _source_files():
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        rel = str(p.relative_to(REPO)).replace("\\", "/")
        if rel == SELF:
            continue
        if p.suffix == ".py":
            l, o = _python_hits(p, text)
            legacy += l
            offsets += o
            continue
        lines = text.splitlines()

        def report(bucket, m):
            lineno = text.count("\n", 0, m.start()) + 1
            line = lines[lineno - 1] if lineno <= len(lines) else ""
            bucket.append(f"{rel}:{lineno}: {' '.join(m.group(0).split())[:110]}"
                          f"   in: {line.strip()[:80]}")

        for pattern, bucket in ((NONPY_UNAMBIGUOUS, legacy),
                                (NONPY_AMBIGUOUS, legacy),
                                (NONPY_FIXED_ZONE, offsets),
                                (NONPY_FIXED_OFFSET, offsets)):
            for m in pattern.finditer(text):
                report(bucket, m)
    return legacy, offsets


def test_no_legacy_eastern_zone_names():
    """`US/Eastern` and friends are backward links; write the canonical name."""
    legacy, _ = _scan()
    assert not legacy, (
        "Eastern time must be named 'America/New_York', not a backward link:\n  "
        + "\n  ".join(legacy))


def test_no_fixed_offset_standing_in_for_eastern():
    """-04:00/-05:00 is right for half the year and wrong for the other half."""
    _, offsets = _scan()
    assert not offsets, (
        "A fixed UTC offset cannot express Eastern time across DST:\n  "
        + "\n  ".join(offsets))


def test_every_scheduler_declaration_uses_the_named_zone():
    """`gcp/deploy.sh` creates every Cloud Scheduler entry; all must be ET.

    Read live 2026-09-07, all 66 entries are `America/New_York` (66 in
    us-east1, 0 in every other Cloud Scheduler location). This keeps a
    new entry from being added without a timezone -- Cloud Scheduler defaults
    to **UTC** when `--time-zone` is omitted, which would silently move a
    "02:00 ET" job to 21:00 or 22:00 the previous evening.

    Checked per DECLARATION, resolving shared flag arrays.

    Two wrong versions preceded this one and both are worth recording,
    because they failed in opposite directions. A line-window parser reported
    `strat-enrich-daily` as missing its timezone when the flag sat eight
    lines above the call inside a bash array -- the array-resolution trap
    `docs/product/05-INFRASTRUCTURE.md` records for its job-count parser. I
    then over-corrected to per-enclosing-function, which resolves arrays
    correctly and accepts ANY declaration in a function that has at least one
    timezone anywhere: `deploy_notifier` and `_schedule_args` each hold
    several, so a new zoneless one added beside them would pass.

    So: each `gcloud scheduler jobs create/update http` command is examined on
    its own, and a command satisfies the check if it carries `--time-zone`
    itself or expands an array whose definition in the same function carries
    one.

    Live truth is checked separately by `scripts/verify_docs_against_live.py`;
    this test is the hermetic half.
    """
    src = (REPO / "gcp" / "deploy.sh").read_text()
    body = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))

    # Every timezone literal in the file must be Eastern, wherever it sits.
    # BOTH gcloud spellings. Requiring whitespace missed `--time-zone=UTC`,
    # while the per-declaration check below accepts a command merely for
    # containing `--time-zone` -- so an equals-form non-Eastern declaration
    # satisfied the second check and was invisible to the first.
    # The value is captured up to the next quote or space, NOT restricted to
    # the characters a zone name uses. The narrow class could not match
    # `${SCHEDULER_TZ}`, so a dynamic value contributed nothing to this set,
    # left it as {America/New_York}, and satisfied the per-declaration check
    # below merely by containing the flag (Codex, PR #993). A value this guard
    # cannot read is a value it cannot vouch for, so it has to fail here.
    zones = set(re.findall(
        r"--time-zone[=\s]+[\"']?([^\s\"']+)[\"']?", body))
    assert zones, "no --time-zone flags found -- has deploy.sh moved?"
    assert zones == {EASTERN}, f"non-Eastern scheduler timezones in deploy.sh: {sorted(zones - {EASTERN})}"

    offenders = []
    for name, func in _shell_functions(body):
        zoned_arrays = _arrays_carrying_timezone(func)
        for cmd in _scheduler_commands(func):
            if "--time-zone" in cmd:
                continue
            if any(a in cmd for a in zoned_arrays):
                continue
            offenders.append(f"{name}: {' '.join(cmd.split())[:90]}")
    assert not offenders, (
        "Cloud Scheduler defaults to UTC when --time-zone is omitted; these "
        "declarations set no timezone and expand no array that does:\n  "
        + "\n  ".join(offenders))


def _shell_functions(body: str) -> list[tuple[str, str]]:
    """[(name, text)] for each top-level shell function, plus the file scope."""
    parts = re.split(r"\n(?=([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{)", body)
    out = [("<top level>", parts[0])]
    for i in range(1, len(parts), 2):
        out.append((parts[i], parts[i + 1]))
    return out


def _arrays_carrying_timezone(func: str) -> set[str]:
    """Names of bash arrays/vars defined in `func` whose value sets a timezone.

    Returned as the expansion spellings a command would contain, so the
    caller can test membership by substring without re-parsing.
    """
    names = set()
    for m in re.finditer(r"^\s*(?:local\s+)?([A-Za-z_][A-Za-z0-9_]*)=\(", func,
                         re.MULTILINE):
        start = m.end()
        depth = 1
        i = start
        while i < len(func) and depth:
            if func[i] == "(":
                depth += 1
            elif func[i] == ")":
                depth -= 1
            i += 1
        # The LITERAL zone, not merely the flag. An array holding
        # `--time-zone "${SCHEDULER_TZ}"` satisfied every command that expanded
        # it while saying nothing about the zone those schedulers would run in.
        if re.search(r"--time-zone[=\s]+[\"']?" + re.escape(EASTERN)
                     + r"[\"']?", func[start:i]):
            names.add(m.group(1))
    # `${flags[@]}` only. Bash expands a bare `$flags` to element ZERO, so for
    # the `_enrich_common` layout that passes `--location` and silently drops
    # the `--time-zone` that follows it -- and accepting the scalar spelling
    # meant that typo produced no offender while the scheduler received no
    # zone at all (Codex, PR #993). The quoted and unquoted array forms both
    # expand to every element; the scalar does not.
    return {f"${{{n}[@]}}" for n in names}


_INVOCATION = re.compile(r"gcloud\s+scheduler\s+jobs\s+(?:create|update)\s+http")


def _split_invocations(statement: str) -> list[str]:
    """One continued shell statement -> one entry per gcloud invocation in it.

    `deploy_notifier` writes a create/update fallback as a single statement:
    every linking line ends in a backslash, so `create ... || update ...` is
    one continuation and the create branch\'s `--time-zone` satisfied the
    check for the update branch too. Dropping the update branch\'s own flag
    then produced zero offenders while a redeploy of an existing scheduler
    kept whatever zone it already had (Codex, PR #993).

    Splitting on the invocation itself is what makes each branch answer for
    its own flags. `||`, `&&` and `;` are deliberately not the delimiter: the
    thing being counted is a declaration, not a shell operator, and a create
    piped into anything at all is still a declaration that needs a zone.
    """
    parts = re.split(r"(?=" + _INVOCATION.pattern + r")", statement)
    return [p for p in parts if _INVOCATION.search(p)]


def _scheduler_commands(func: str) -> list[str]:
    """Each `gcloud scheduler jobs create/update http` command, whole.

    A command runs to the first line that does not end in a backslash, so a
    multi-line invocation is returned in one piece and its flags are not
    attributed to a neighbour.
    """
    lines = func.splitlines()
    out = []
    i = 0
    while i < len(lines):
        if re.search(r"gcloud\s+scheduler\s+jobs\s+(?:create|update)\s+http",
                     lines[i]):
            cmd = [lines[i]]
            while cmd[-1].rstrip().endswith("\\") and i + 1 < len(lines):
                i += 1
                cmd.append(lines[i])
            out.extend(_split_invocations("\n".join(cmd)))
        i += 1
    return out


def test_a_named_fixed_offset_zone_is_rejected():
    """`Etc/GMT+5` is a zone name AND a fixed offset.

    POSIX inverts the sign, so it is frozen at UTC-5: right for Eastern in
    winter, wrong all summer. It looked like a named zone and so passed a
    check that only recognised numeric offsets (Codex, PR #993).
    """
    assert _FIXED_OFFSET_STRINGS.match("Etc/GMT+5")
    assert _FIXED_OFFSET_STRINGS.match("Etc/GMT+05")
    assert _FIXED_OFFSET_STRINGS.match("-05:00")
    # UTC+5 is not Eastern in any season, and neither is UTC.
    assert not _FIXED_OFFSET_STRINGS.match("Etc/GMT-5")
    assert not _FIXED_OFFSET_STRINGS.match("Etc/GMT+9")
    assert NONPY_FIXED_ZONE.search("tz = 'Etc/GMT+5'")
    assert not NONPY_FIXED_ZONE.search("tz = 'Etc/GMT+9'")


def test_a_legacy_binding_survives_a_later_reassignment():
    """`TZ = "EST"; ZoneInfo(TZ); TZ = "UTC"` must still be a violation.

    Last-assignment-wins resolved the call to the LATER value, so the
    violation between the two disappeared -- the opposite of what the
    docstring claimed the rule was (Codex, PR #993).
    """
    tree = ast.parse('TZ = "EST"\nZoneInfo(TZ)\nTZ = "UTC"\n')
    assert _binding_text(_scoped_envs(tree)[id(tree)].bindings["TZ"]) == "EST"

    # A name never bound to anything interesting still takes its last value.
    tree = ast.parse('TZ = "UTC"\nTZ = "America/New_York"\n')
    assert (_binding_text(_scoped_envs(tree)[id(tree)].bindings["TZ"])
            == "America/New_York")

    # And end to end, which is the claim that matters.
    legacy, _ = _hits('TZ = "EST"\nZoneInfo(TZ)\nTZ = "UTC"\n')
    assert any("EST" in h for h in legacy), legacy


def test_the_repository_scan_is_read_once():
    """Two tests, one question, one read of 600-odd files.

    Uncached the scan ran twice at ~6.8 s each, so this guard cost the suite
    seven seconds to answer the same question twice (Codex, PR #993).
    """
    assert hasattr(_scan, "cache_info"), "_scan must be memoised"
    first = _scan()
    assert _scan() is first, "the second call re-read the tree"


@pytest.mark.parametrize("instant,expected_offset,label", [
    (datetime(2026, 7, 15, 12, 0), timedelta(hours=-4), "EDT (summer)"),
    (datetime(2026, 1, 15, 12, 0), timedelta(hours=-5), "EST (winter)"),
    # 2026 US transitions: 2026-03-08 and 2026-11-01, both at 02:00 local.
    (datetime(2026, 3, 8, 1, 0), timedelta(hours=-5), "hour before spring-forward"),
    (datetime(2026, 3, 8, 3, 0), timedelta(hours=-4), "hour after spring-forward"),
    (datetime(2026, 11, 1, 0, 30), timedelta(hours=-4), "before fall-back"),
    (datetime(2026, 11, 1, 3, 0), timedelta(hours=-5), "after fall-back"),
])
def test_named_zone_tracks_dst(instant, expected_offset, label):
    """The whole reason a named zone beats an offset: it moves, twice a year."""
    assert instant.replace(tzinfo=ZoneInfo(EASTERN)).utcoffset() == expected_offset, label


def test_market_open_is_the_same_wall_clock_on_both_sides_of_dst():
    """9:30 ET is 13:30 UTC in summer and 14:30 UTC in winter.

    A fixed offset would put one of these an hour wrong, which is the failure
    that motivates this whole file: the RTH filter would either drop the first
    bar of the session or admit a pre-market one.
    """
    et = ZoneInfo(EASTERN)
    summer = datetime(2026, 7, 15, 9, 30, tzinfo=et)
    winter = datetime(2026, 1, 15, 9, 30, tzinfo=et)
    assert summer.astimezone(ZoneInfo("UTC")).hour == 13
    assert winter.astimezone(ZoneInfo("UTC")).hour == 14


def _hits(source: str) -> tuple[list[str], list[str]]:
    """Run the Python scan over `source` as if it were a file in the repo."""
    return _python_hits(REPO / "gcp" / "_scratch_for_this_test.py", source)


def test_a_local_in_one_function_does_not_taint_another():
    """The binding map must not join names Python never joins.

    Collected once for the whole module, an ordinary local `value = "EST"` in
    one function and an independent `ZoneInfo(value)` in another resolved to
    the same binding and reported a violation -- a CI failure on correct code,
    from a guard whose whole design tolerates ambiguous tokens outside a
    timezone context so it would not do that (Codex, PR #993).
    """
    legacy, offsets = _hits(
        'def stop_word_list():\n'
        '    value = "EST"\n'
        '    return [value]\n'
        '\n'
        'def load(value):\n'
        '    return ZoneInfo(value)\n'
    )
    assert (legacy, offsets) == ([], [])


def test_an_enclosing_binding_still_reaches_the_call_that_reads_it():
    """Scoping must not cost the indirection the map exists for.

    `EASTERN = "US/Eastern"` at module level really is what `ZoneInfo(EASTERN)`
    inside a function reads, and following that is the reason this map exists.
    """
    legacy, _ = _hits(
        'EASTERN = "US/Eastern"\n'
        '\n'
        'def load():\n'
        '    return ZoneInfo(EASTERN)\n'
    )
    assert any("EASTERN" in h and "US/Eastern" in h for h in legacy), legacy

    # And a nested binding shadows it, the way Python does.
    legacy, _ = _hits(
        'TZ = "EST"\n'
        '\n'
        'def load():\n'
        '    TZ = "America/New_York"\n'
        '    return ZoneInfo(TZ)\n'
    )
    assert legacy == [], legacy


def test_the_tz_environment_variable_is_read_as_a_timezone():
    """`os.environ["TZ"] = "EST"` sets the process clock for every naive call.

    The target is an `ast.Subscript`, so it binds no name the map can follow
    later and the assignment is itself the use -- and nothing looked at it
    (Codex, PR #993).
    """
    legacy, _ = _hits('import os\nos.environ["TZ"] = "EST"\n')
    assert any("EST" in h for h in legacy), legacy

    _, offsets = _hits('os.environ["TZ"] = "Etc/GMT+5"\n')
    assert any("Etc/GMT+5" in h for h in offsets), offsets

    # The canonical name is not a finding, and neither is an unrelated key.
    assert _hits('os.environ["TZ"] = "America/New_York"\n') == ([], [])
    assert _hits('os.environ["EST_LABEL"] = "EST"\n') == ([], [])


def test_a_parameter_shadows_an_inherited_binding():
    """`TZ = "EST"` at module level says nothing about `def load(TZ)`.

    The scoping fix stopped joining names across sibling functions but still
    inherited enclosing scopes into a function whose own PARAMETER shadows
    them, because `_collect_bindings` reads assignments and a parameter is not
    one. Same false CI failure, one level in (Codex, PR #993).
    """
    legacy, offsets = _hits(
        'TZ = "EST"\n'
        '\n'
        'def load(TZ):\n'
        '    return ZoneInfo(TZ)\n'
    )
    assert (legacy, offsets) == ([], [])

    # Every parameter kind shadows, not just a positional one.
    assert _hits('TZ = "EST"\n\ndef load(*, TZ="America/New_York"):\n'
                 '    return ZoneInfo(TZ)\n') == ([], [])
    assert _hits('TZ = "EST"\n\nload = lambda TZ: ZoneInfo(TZ)\n') == ([], [])


def test_a_constant_default_is_bound_rather_than_merely_shadowed():
    """`def load(tz="EST")` really does resolve to EST when nothing is passed.

    Dropping the inherited binding is right; dropping the parameter entirely
    would let the default through, so the default is bound instead.
    """
    # An AMBIGUOUS value, deliberately. `US/Eastern` as a default would be
    # reported anyway — it is an unambiguous zone name and the bare-constant
    # check catches it wherever it stands — so it cannot tell whether the
    # binding did any work. `EST` is only ever reported through a timezone
    # context, so the binding is the whole mechanism here.
    legacy, _ = _hits('def load(tz="EST"):\n    return ZoneInfo(tz)\n')
    assert any("EST" in h for h in legacy), legacy

    _, offsets = _hits('def load(*, tz="-05:00"):\n    return ZoneInfo(tz)\n')
    assert any("-05:00" in h for h in offsets), offsets

    # And the canonical default is not a finding.
    assert _hits('def load(tz="America/New_York"):\n'
                 '    return ZoneInfo(tz)\n') == ([], [])


def test_an_uppercase_dict_key_is_a_timezone_key():
    """`env={"TZ": "EST"}` is the conventional spelling for a subprocess.

    The case-sensitive membership test walked past it while the adjacent
    `os.environ["TZ"]` form was caught — the same key, two spellings, two
    answers (Codex, PR #993).
    """
    legacy, _ = _hits('subprocess.run(cmd, env={"TZ": "EST"})\n')
    assert any("EST" in h for h in legacy), legacy
    assert _hits('subprocess.run(cmd, env={"TZ": "America/New_York"})\n') == ([], [])
    # An unrelated key is still not a timezone context.
    assert _hits('d = {"EST_LABEL": "EST"}\n') == ([], [])


def test_a_yaml_mapping_entry_is_a_timezone_context():
    """`TZ: EST` is how a Compose or Kubernetes file spells it.

    Adding *.yml/*.yaml to the scan achieved nothing while the context
    required `=`: the standard mapping syntax of the files just brought in
    was the one spelling it could not see (Codex, PR #993).
    """
    assert NONPY_AMBIGUOUS.search("      TZ: EST")
    assert NONPY_AMBIGUOUS.search('  timezone: "EDT"')
    assert NONPY_FIXED_OFFSET.search("  timezone: -05:00")
    # Still not a bare word out of context.
    assert not NONPY_AMBIGUOUS.search("headline stop words: EST")
    assert NONPY_AMBIGUOUS.search("tz=EST")   # the assignment form still works


def test_only_a_whole_array_expansion_carries_the_later_flags():
    """Bash expands `$flags` to element ZERO, not the whole array.

    For the `_enrich_common` layout that passes `--location` and drops the
    `--time-zone` after it, so accepting the scalar spelling meant the typo
    produced no offender while the scheduler received no zone at all
    (Codex, PR #993).
    """
    func = (
        '_enrich_common() {\n'
        '  local flags=(--location "$REGION" --time-zone "America/New_York")\n'
        '}\n'
    )
    zoned = _arrays_carrying_timezone(func)
    assert "${flags[@]}" in zoned
    assert "$flags" not in zoned, (
        "a scalar expansion passes only the first element, so it does not "
        "carry the --time-zone that follows")


def test_a_pytz_fixed_offset_constructor_is_an_offset():
    """`pytz.FixedOffset(-300)` is UTC-5 with no DST — right for half the year.

    The offset is a plain integer count of minutes, so no string check and no
    `timedelta` check could see it, and `FixedOffset` was not even in the call
    whitelist. pytz is a declared dependency here, so this is a live spelling
    (Codex, PR #993).
    """
    _, offsets = _hits("import pytz\ntz = pytz.FixedOffset(-300)\n")
    assert any("FixedOffset" in h for h in offsets), offsets

    _, offsets = _hits("tz = pytz.FixedOffset(-240)\n")   # EDT half of the year
    assert any("FixedOffset" in h for h in offsets), offsets

    # Not Eastern in any season, so not this guard's business.
    assert _hits("tz = pytz.FixedOffset(0)\n") == ([], [])
    assert _hits("tz = pytz.FixedOffset(330)\n") == ([], [])


def test_a_class_attribute_resolves_at_the_call_site():
    """`class Settings: tz = "EST"` then `ZoneInfo(Settings.tz)`.

    The literal is ambiguous, so it is deliberately not reported on its own,
    and `follow` resolved only `ast.Name` — never the `ast.Attribute` the call
    actually receives. A routine configuration shape installed fixed UTC-5
    with the guard green (Codex, PR #993).
    """
    legacy, _ = _hits(
        'class Settings:\n'
        '    tz = "EST"\n'
        '\n'
        'def load():\n'
        '    return ZoneInfo(Settings.tz)\n'
    )
    assert any("Settings.tz" in h and "EST" in h for h in legacy), legacy

    # Keyed on the PAIR: an unrelated class with the same attribute name must
    # not inherit the finding.
    assert _hits(
        'class Settings:\n'
        '    tz = "America/New_York"\n'
        '\n'
        'class Other:\n'
        '    tz = "UTC"\n'
        '\n'
        'def load():\n'
        '    return ZoneInfo(Other.tz)\n'
    ) == ([], [])


def test_a_postgres_timezone_call_is_a_timezone_context():
    """`timezone('EST', ts)` is the function form of `AT TIME ZONE`.

    The context knew `AT TIME ZONE` and assignment syntax but not the call, so
    Postgres applied the fixed UTC-5 abbreviation with both repository-wide
    guards green (Codex, PR #993).
    """
    assert NONPY_AMBIGUOUS.search("SELECT timezone('EST', ts) FROM bars")
    assert NONPY_AMBIGUOUS.search("select TIMEZONE( 'EDT' , ts)")
    assert NONPY_FIXED_OFFSET.search("SELECT timezone('-05:00', ts)")
    # The canonical name is not a finding.
    assert not NONPY_AMBIGUOUS.search("SELECT timezone('America/New_York', ts)")


def test_the_remaining_eastern_backward_links_are_rejected():
    """`US/East-Indiana` and `US/Michigan` are Eastern backward links too.

    Both resolve to Eastern-observing zones, follow the same -05:00/-04:00
    pattern, and break identically on a slim tzdata — so allowing them let an
    alternate legacy spelling through a guard that exists to forbid legacy
    spellings (Codex, PR #993).
    """
    for name in ("US/East-Indiana", "US/Michigan", "America/Fort_Wayne",
                 "America/Indianapolis", "America/Louisville",
                 "America/Nipigon", "America/Thunder_Bay",
                 "America/Pangnirtung"):
        legacy, _ = _hits(f'tz = ZoneInfo("{name}")\n')
        assert any(name in h for h in legacy), f"{name} not reported: {legacy}"
        assert NONPY_UNAMBIGUOUS.search(f'tz = "{name}"'), name

    # A Central backward link is a different zone, not this guard's business.
    assert _hits('tz = ZoneInfo("US/Central")\n') == ([], [])
    # Nor is a link whose target is not Eastern: America/Coral_Harbour points
    # at America/Panama, which is EST year-round and never observes Eastern.
    assert _hits('tz = ZoneInfo("America/Coral_Harbour")\n') == ([], [])
    # And the canonical names of the Eastern-observing zones stay legal: this
    # guard forbids legacy SPELLINGS, not other cities.
    for canonical in ("America/Toronto", "America/Detroit",
                      "America/Kentucky/Louisville"):
        assert _hits(f'tz = ZoneInfo("{canonical}")\n') == ([], []), canonical


def test_an_identifier_ending_in_tz_is_not_a_timezone_key():
    """`quartz=EST` is not `tz=EST`.

    The two-character `tz` key had no left boundary, so it matched the TAIL of
    any identifier ending in those letters and reported a timezone in a line
    that has nothing to do with one — a false CI failure on ordinary shell or
    YAML, which is exactly what keeping the ambiguous names context-gated is
    for (Codex, PR #993).
    """
    assert not NONPY_AMBIGUOUS.search("quartz=EST")
    assert not NONPY_AMBIGUOUS.search("SHOWBIZ_TZ_LABEL=EST".lower().replace("_tz", "xtz"))
    assert not NONPY_AMBIGUOUS.search("my_timezone_label=EST".replace("_timezone", "xtimezone"))

    # The real keys still match, in both syntaxes.
    assert NONPY_AMBIGUOUS.search("tz=EST")
    assert NONPY_AMBIGUOUS.search("  TZ: EST")
    assert NONPY_AMBIGUOUS.search("timezone: EDT")
    # And a boundary character before the key is still a boundary.
    assert NONPY_AMBIGUOUS.search("export TZ=EST")


def test_a_class_body_is_not_an_enclosing_scope_for_its_methods():
    """Python does not close over a class namespace.

    A method sees the enclosing function or module, not the class body — so a
    class-level label beside a canonical global made `ZoneInfo(value)` resolve
    to the label the runtime never uses. That is a false CI failure, and the
    third one this scoping machinery has produced (Codex, PR #993).
    """
    assert _hits(
        'value = "America/New_York"\n'
        '\n'
        'class C:\n'
        '    value = "EST"          # a display label, not a timezone\n'
        '\n'
        '    def load(self):\n'
        '        return ZoneInfo(value)\n'
    ) == ([], [])

    # Code directly IN the class body does see the class binding, which is
    # what Python does and what the attribute test below relies on.
    legacy, _ = _hits('class C:\n    value = "EST"\n    tz = ZoneInfo(value)\n')
    assert any("EST" in h for h in legacy), legacy

    # And the attribute path is untouched: `C.value` still resolves.
    legacy, _ = _hits('class S:\n    tz = "EST"\n\ndef load():\n'
                      '    return ZoneInfo(S.tz)\n')
    assert any("S.tz" in h for h in legacy), legacy


def test_an_aliased_import_still_resolves_to_the_constructor():
    """`from zoneinfo import ZoneInfo as ZI` then `ZI("EST")`.

    `_call_name` reports the name as written, so the call missed `_TZ_CALLS`
    and was skipped before its argument was looked at. A whitelist that knows
    only the canonical spelling is a list of what someone thought of — the
    argument this file already makes about call-name whitelists, one level
    down (Codex, PR #993).
    """
    legacy, _ = _hits('from zoneinfo import ZoneInfo as ZI\ntz = ZI("EST")\n')
    assert any("EST" in h for h in legacy), legacy

    _, offsets = _hits('from zoneinfo import ZoneInfo as ZI\ntz = ZI("-05:00")\n')
    assert any("-05:00" in h for h in offsets), offsets

    # `import pytz as p` -> `p.FixedOffset(-300)` resolves through the tail.
    _, offsets = _hits('import pytz as p\ntz = p.FixedOffset(-300)\n')
    assert any("FixedOffset" in h for h in offsets), offsets

    # The canonical value through an alias is still not a finding.
    assert _hits('from zoneinfo import ZoneInfo as ZI\n'
                 'tz = ZI("America/New_York")\n') == ([], [])


@pytest.mark.parametrize("label,source", [
    ("for-loop target",
     'tz = "EST"\n\ndef load(zones):\n    for tz in zones:\n        ZoneInfo(tz)\n'),
    ("comprehension target",
     'tz = "EST"\n\ndef load(zones):\n    return [ZoneInfo(tz) for tz in zones]\n'),
    ("generator target",
     'tz = "EST"\n\ndef load(zones):\n    return (ZoneInfo(tz) for tz in zones)\n'),
    ("tuple unpacking",
     'tz = "EST"\n\ndef load(pair):\n    name, tz = pair\n    return ZoneInfo(tz)\n'),
    ("starred unpacking",
     'tz = "EST"\n\ndef load(row):\n    *rest, tz = row\n    return ZoneInfo(tz)\n'),
    ("with .. as",
     'tz = "EST"\n\ndef load(f):\n    with f as tz:\n        return ZoneInfo(tz)\n'),
    ("except .. as",
     'tz = "EST"\n\ndef load(f):\n    try:\n        pass\n    except Exception as tz:\n'
     '        return ZoneInfo(tz)\n'),
    ("walrus",
     'tz = "EST"\n\ndef load(f):\n    if (tz := f()):\n        return ZoneInfo(tz)\n'),
    ("import as",
     'tz = "EST"\n\ndef load():\n    import zoneinfo as tz\n    return ZoneInfo(tz)\n'),
    ("augmented assignment",
     'tz = "EST"\n\ndef load(s):\n    tz = s\n    tz += "!"\n    return ZoneInfo(tz)\n'),
    ("nested def name",
     'tz = "EST"\n\ndef load():\n    def tz():\n        return "America/New_York"\n'
     '    return ZoneInfo(tz())\n'),
])
def test_any_rebinding_shadows_an_enclosing_binding(label, source):
    """A name this scope rebinds by ANY construct is not the outer one.

    `_collect_bindings` only reads `NAME = "literal"`, so every other way of
    rebinding a name left the enclosing binding in place and reported it.
    Three instances of this shape had already been found and fixed one at a
    time — a file-wide map, a parameter, a class body — and eleven more were
    sitting behind them.

    Naming constructs one at a time is the losing move this file argues
    against elsewhere, so `_bound_names` collects what Python binds and
    anything unresolvable shadows: the guard falls silent rather than
    accusing valid code (Codex, PR #993, and pre-empting the rest of the
    family).
    """
    assert _hits(source) == ([], []), label


def test_shadowing_does_not_swallow_the_bindings_that_matter():
    """The other direction: over-shadowing would silence the whole guard.

    Dropping an inherited binding whenever the scope mentions the name would
    be trivially free of false positives and useless, so each resolvable
    shape is pinned here alongside the parametrised cases above.
    """
    # A module constant read inside a function.
    legacy, _ = _hits('EASTERN = "US/Eastern"\n\ndef load():\n'
                      '    return ZoneInfo(EASTERN)\n')
    assert any("EASTERN" in h for h in legacy), legacy

    # An ambiguous value, which is ONLY ever reported through the binding.
    legacy, _ = _hits('TZ = "EST"\n\ndef load():\n    return ZoneInfo(TZ)\n')
    assert any("EST" in h for h in legacy), legacy

    # `global` declares that the assignment writes the OUTER name, so the
    # outer binding still describes what the call reads — it must not shadow.
    legacy, _ = _hits('TZ = "EST"\n\ndef setup():\n    global TZ\n    TZ = TZ\n'
                      '\ndef load():\n    return ZoneInfo(TZ)\n')
    assert any("EST" in h for h in legacy), legacy

    # A subscript target binds no name. Both `cfg` and `tz` are `Name` nodes
    # inside `cfg[tz] = 1` and neither is bound, so collecting every Name in
    # the target subtree shadowed `tz` and silenced the guard for the rest of
    # the scope -- the opposite failure to the one shadowing exists to fix.
    # The binding must be INHERITED for this to test anything: a literal
    # assigned in the same scope is re-added by `_collect_bindings` whatever
    # the shadowing set says, so a local `tz = "EST"` would pass either way.
    legacy, _ = _hits('tz = "EST"\n\ndef load(cfg):\n    cfg[tz] = 1\n'
                      '    return ZoneInfo(tz)\n')
    assert any("EST" in h for h in legacy), legacy

    # A bare `global` binds nothing, so the outer binding survives.
    legacy, _ = _hits('TZ = "EST"\n\ndef load():\n    global TZ\n'
                      '    return ZoneInfo(TZ)\n')
    assert any("EST" in h for h in legacy), legacy


def test_a_global_assignment_still_shadows():
    """`global TZ` WITH an assignment rebinds the name.

    An earlier version subtracted declared names from the bound set, which
    kept the module's stale literal and reported it against a value the
    function had just replaced. Collecting bindings rather than declarations
    gets both directions right with no branch.
    """
    assert _hits('TZ = "EST"\n\ndef load(src):\n    global TZ\n'
                 '    TZ = src.read()\n    return ZoneInfo(TZ)\n') == ([], [])


def test_a_comprehension_shadows_only_inside_itself():
    """A comprehension is its own scope; folding it into the enclosing
    function would shadow the name for the whole body.

    Here the same name means two different things: the comprehension's own
    target, and the function local read after it. Only the second is a
    finding, and a checker that treats the comprehension as part of the
    function misses it entirely.
    """
    legacy, _ = _hits(
        'tz = "EST"\n'
        '\n'
        'def load(zones):\n'
        '    seen = [str(tz) for tz in zones]   # the comprehension\'s own tz\n'
        '    return ZoneInfo(tz)                # the module\'s tz\n'
    )
    assert any("EST" in h for h in legacy), (
        "the read after the comprehension was shadowed by the comprehension's "
        f"own target: {legacy}")

    # And the read INSIDE the comprehension is correctly the loop variable.
    assert _hits('tz = "EST"\n\ndef load(zones):\n'
                 '    return [ZoneInfo(tz) for tz in zones]\n') == ([], [])


def test_an_import_alias_does_not_cross_between_scopes():
    """Two functions may rename two different imports to one short name.

    The alias map was file-wide and keyed on the alias alone, so
    `from zoneinfo import ZoneInfo as load` in one function and
    `from json import loads as load` in another resolved to whichever came
    LAST in the file. Both orders are wrong and in opposite directions, which
    is why both are asserted here (Codex, PR #993).
    """
    real_first = (
        'def load_zone():\n'
        '    from zoneinfo import ZoneInfo as load\n'
        '    return load("EST")\n'
        '\n'
        'def load_config(raw):\n'
        '    from json import loads as load\n'
        '    return load(raw)\n'
    )
    legacy, _ = _hits(real_first)
    assert any("EST" in h for h in legacy), (
        f"the real constructor was masked by a later unrelated alias: {legacy}")

    # The reverse order is the false-finding direction: nothing here builds a
    # timezone, so nothing may be reported.
    unrelated_first = (
        'def load_config(raw):\n'
        '    from json import loads as load\n'
        '    return load("EST")\n'
        '\n'
        'def load_zone(name):\n'
        '    from zoneinfo import ZoneInfo as load\n'
        '    return load(name)\n'
    )
    assert _hits(unrelated_first) == ([], []), (
        "an unrelated call was read as a ZoneInfo constructor because some "
        "other scope aliased that name")

    # ONE scope aliasing one name to two different originals is a flow
    # question, and this guard is not flow-sensitive. Neither answer is
    # defensible, so the name resolves to nothing: a wrong guess here reports
    # a call to a function that has nothing to do with timezones, and a false
    # CI failure is the one outcome this file will not trade for a catch.
    both_in_one_scope = (
        'from zoneinfo import ZoneInfo as load\n'
        'load("EST")\n'
        'from json import loads as load\n'
    )
    assert _hits(both_in_one_scope) == ([], []), _hits(both_in_one_scope)

    # Aliasing the same name to the same original twice is not a conflict.
    legacy, _ = _hits('from zoneinfo import ZoneInfo as ZI\n'
                      'from zoneinfo import ZoneInfo as ZI\n'
                      'ZI("EST")\n')
    assert any("EST" in h for h in legacy), legacy


def test_two_local_classes_of_the_same_name_are_not_one_class():
    """`(ClassName, attr)` looked specific enough and is not.

    Two `class Settings` bodies in two functions are two classes. Keyed on the
    pair and collected file-wide, whichever body came last won — a MISS in one
    declaration order and a FALSE FINDING in the reverse (Codex, PR #993).
    """
    legacy, _ = _hits(
        'def eastern():\n'
        '    class Settings:\n'
        '        tz = "EST"\n'
        '    return ZoneInfo(Settings.tz)\n'
        '\n'
        'def utc():\n'
        '    class Settings:\n'
        '        tz = "UTC"\n'
        '    return ZoneInfo(Settings.tz)\n'
    )
    assert any("EST" in h for h in legacy), (
        f"a later same-named class body masked the violation: {legacy}")
    assert len([h for h in legacy if "EST" in h]) == 1, (
        f"the UTC class was reported as the EST one: {legacy}")

    # Reverse order: the UTC class is declared first, and must not inherit the
    # other function's attribute.
    legacy, _ = _hits(
        'def utc():\n'
        '    class Settings:\n'
        '        tz = "UTC"\n'
        '    return ZoneInfo(Settings.tz)\n'
        '\n'
        'def eastern():\n'
        '    class Settings:\n'
        '        tz = "EST"\n'
        '    return ZoneInfo(Settings.tz)\n'
    )
    assert len(legacy) == 1 and "EST" in legacy[0], legacy


def test_a_global_write_reaches_the_module_binding():
    """`global TZ; TZ = "EST"` binds the module's name, not a local one.

    The descent saw a local assignment inside the writer, resolved nothing
    outside it, and reported nothing — while at runtime every other reader of
    the module global gets `EST` (Codex, PR #993).
    """
    legacy, _ = _hits(
        'def configure():\n'
        '    global TZ\n'
        '    TZ = "EST"\n'
        '\n'
        'def stamp(ts):\n'
        '    return ts.astimezone(ZoneInfo(TZ))\n'
    )
    assert any("EST" in h for h in legacy), legacy

    # Without the `global` it is an ordinary local and reaches nothing.
    assert _hits('def configure():\n'
                 '    TZ = "EST"\n'
                 '\n'
                 'def stamp(ts):\n'
                 '    return ZoneInfo(TZ)\n') == ([], [])


def test_a_nonlocal_write_reaches_the_enclosing_binding():
    """`nonlocal` is the same statement pointed at a closure, not the module.

    Folding it in with `global` resolved nothing at all: `nonlocal` is only
    legal where an enclosing scope already binds the name, and that binding
    shadows a module-level entry before it is read. It has to land on the
    scope Python picks — the nearest enclosing function that binds the name.
    """
    legacy, _ = _hits(
        'def outer():\n'
        '    tz = "America/New_York"\n'
        '\n'
        '    def override():\n'
        '        nonlocal tz\n'
        '        tz = "EST"\n'
        '\n'
        '    override()\n'
        '    return ZoneInfo(tz)\n'
    )
    assert any("EST" in h for h in legacy), legacy

    # A sibling function that binds its own `tz` is a different name.
    assert _hits(
        'def outer():\n'
        '    tz = "America/New_York"\n'
        '\n'
        '    def override():\n'
        '        nonlocal tz\n'
        '        tz = "EST"\n'
        '\n'
        '    return override\n'
        '\n'
        'def elsewhere(tz):\n'
        '    return ZoneInfo(tz)\n') == ([], [])


def test_an_attribute_assignment_is_a_timezone_write():
    """`settings.timezone = "EST"` binds no NAME, so nothing followed it.

    Exactly the argument the subscript branch already makes for
    `os.environ["TZ"] = "EST"`: the assignment IS the use, and the value is
    the violation (Codex, PR #993).
    """
    legacy, _ = _hits('settings.timezone = "EST"\n')
    assert any("EST" in h for h in legacy), legacy

    _, offsets = _hits('conn.tz = "-05:00"\n')
    assert any("-05:00" in h for h in offsets), offsets

    # And the write is readable afterwards, like a class attribute.
    legacy, _ = _hits('cfg.tzinfo = "US/Eastern"\ndt.astimezone(cfg.tzinfo)\n')
    assert legacy, legacy

    # An attribute that is not a timezone key carries no such meaning.
    assert _hits('parser.stopword = "EST"\n') == ([], [])
    assert _hits('settings.timezone = "America/New_York"\n') == ([], [])


def test_a_negated_timedelta_is_still_a_fixed_offset():
    """`timezone(-timedelta(hours=5))` puts the sign outside the call.

    The whole-constant evaluation only looked inside `timedelta(...)`, so a
    negation wrapping it read as a non-constant argument and was left alone —
    the fifth spelling of the same frozen zone to walk past this check
    (Codex, PR #993).
    """
    for src in ('tz = timezone(-timedelta(hours=5))\n',
                'tz = timezone(-timedelta(hours=4))\n',
                'tz = timezone(-timedelta(seconds=18000))\n'):
        _, offsets = _hits(src)
        assert offsets, src

    # The sign still has to land on Eastern.
    assert _hits('tz = timezone(-timedelta(hours=8))\n') == ([], [])
    assert _hits('tz = timezone(timedelta(hours=5))\n') == ([], [])


def test_a_session_timezone_statement_is_a_timezone_context():
    """`SET TIME ZONE 'EST'` freezes the whole connection.

    `AT TIME ZONE` was a context and `SET TIME ZONE` was not, though the
    second has the wider blast radius: it applies to every subsequent query on
    that connection rather than to one expression (Codex, PR #993).
    """
    for stmt in ("SET TIME ZONE 'EST'", "SET timezone TO 'EDT'",
                 "set time zone 'est'", "SET TIMEZONE TO 'EST'"):
        assert NONPY_AMBIGUOUS.search(stmt), stmt
        legacy, _ = _hits(f'cur.execute("{stmt}")\n')
        assert legacy, stmt

    # The canonical name through the same statement is not a finding.
    assert _hits('cur.execute("SET TIME ZONE \'America/New_York\'")\n') == ([], [])
    # And an unrelated `SET` is not a timezone context.
    assert not NONPY_AMBIGUOUS.search("SET search_path TO estimates")


def test_a_zone_named_inside_an_embedded_sql_string_is_found():
    """Python source carries SQL, and the constant is the statement.

    `cur.execute("SELECT ts AT TIME ZONE 'US/Eastern' ...")` is a live way to
    name the zone that no exact-value check can see. The `.sql` scan already
    reads these patterns; a spelling cannot be banned in one file type and
    permitted in another because of where the quotes fall (Codex, PR #993).
    """
    legacy, _ = _hits(
        'SQL = "SELECT ts AT TIME ZONE \'US/Eastern\' AS d FROM bars"\n')
    assert any("US/Eastern" in h for h in legacy), legacy

    legacy, _ = _hits(
        'SQL = "SELECT ts AT TIME ZONE \'EST\' AS d FROM bars"\n')
    assert legacy, legacy

    _, offsets = _hits('SQL = "SELECT ts AT TIME ZONE \'Etc/GMT+5\' FROM bars"\n')
    assert offsets, offsets

    # The canonical zone in the same shape is clean, and so is prose that
    # merely contains the ambiguous token with no timezone context.
    assert _hits(
        'SQL = "SELECT ts AT TIME ZONE \'America/New_York\' FROM bars"\n') == ([], [])
    assert _hits('STOPWORDS = ["est", "edt", "gmt"]\n') == ([], [])

    # A constant already reported by the call that gives it meaning is not
    # reported a second time by the embedded scan.
    legacy, _ = _hits('tz = ZoneInfo("US/Eastern")\n')
    assert len(legacy) == 1, legacy


def test_the_first_comprehension_iterable_is_evaluated_outside():
    """Python builds the first iterator before the comprehension scope exists.

    So in `[tz for tz in [ZoneInfo(tz)]]` the inner `tz` is the OUTER one,
    while the descent had just shadowed it with the comprehension's own target
    and resolved nothing (Codex, PR #993).
    """
    legacy, _ = _hits('tz = "EST"\nzones = [tz for tz in [ZoneInfo(tz)]]\n')
    assert any("EST" in h for h in legacy), legacy

    # Every other clause really is inner: a second `for` iterates over names
    # the comprehension itself bound, so the outer binding does not reach it.
    assert _hits('tz = "EST"\n'
                 'zones = [ZoneInfo(tz) for group in groups for tz in group]\n'
                 ) == ([], [])


def test_a_dateutil_fixed_offset_is_an_offset():
    """`tzoffset(None, -18000)` is UTC-5 in SECONDS, not minutes.

    python-dateutil is a declared dependency, so this is a live spelling. The
    unit is the trap: read as minutes, -18000 matches nothing and the frozen
    zone passes (Codex, PR #993).
    """
    _, offsets = _hits('from dateutil.tz import tzoffset\n'
                       'tz = tzoffset(None, -18000)\n')
    assert any("seconds" in h for h in offsets), offsets

    # UTC-4, and the keyword form, and a timedelta argument.
    for src in ('tz = dateutil.tz.tzoffset(None, -14400)\n',
                'tz = tzoffset("EST", offset=-18000)\n',
                'tz = tzoffset(None, timedelta(hours=-5))\n'):
        assert _hits(src)[1], src

    # A different zone is not this guard's business, and the FIRST argument is
    # a name rather than an offset — reading it as one would report any
    # tzoffset whose label happened to be numeric.
    assert _hits('tz = tzoffset(None, -28800)\n') == ([], [])
    assert _hits('tz = tzoffset(-300, 3600)\n') == ([], [])


def test_a_definition_header_is_evaluated_in_the_enclosing_scope():
    """A `def`'s header runs where it is written, not inside itself.

    With `TZ = "EST"`, `def f(TZ="UTC", value=ZoneInfo(TZ))` builds its
    default from the OUTER `EST`; mapping the whole function to its own
    environment resolved it to the parameter's `UTC` and reported nothing
    (Codex, PR #993).

    The comprehension case was fixed first and on its own. This is the same
    rule for decorators, base classes, defaults and annotations — the level
    it should have been fixed at, since each was a separate miss.
    """
    legacy, _ = _hits('TZ = "EST"\n\ndef f(TZ="UTC", value=ZoneInfo(TZ)):\n'
                      '    return value\n')
    assert any("EST" in h for h in legacy), (
        f"a default built from the outer binding was read as the "
        f"parameter's own: {legacy}")

    # A decorator, a base class, and an annotation, all evaluated outside.
    for label, src in (
        ("decorator", 'TZ = "EST"\n\n@register(ZoneInfo(TZ))\ndef f(TZ="UTC"):\n'
                      '    pass\n'),
        ("base class", 'TZ = "EST"\n\nclass C(Base[ZoneInfo(TZ)]):\n'
                       '    TZ = "UTC"\n'),
        ("annotation", 'TZ = "EST"\n\ndef f(TZ="UTC", x: ZoneInfo(TZ) = None):\n'
                       '    pass\n'),
    ):
        assert any("EST" in h for h in _hits(src)[0]), (label, _hits(src))

    # The BODY still sees the parameter, which is the shadowing this must not
    # undo.
    assert _hits('TZ = "EST"\n\ndef f(TZ="America/New_York"):\n'
                 '    return ZoneInfo(TZ)\n') == ([], [])


def test_a_fixed_offset_stored_in_a_name_still_resolves():
    """`OFFSET = timedelta(hours=-5); timezone(OFFSET)` is the routine form.

    Bindings held the STRING they read, so a name bound to a constructor call
    resolved to nothing and the fixed-offset check only ever saw a constructor
    passed inline (Codex, PR #993). They hold the node now, and `follow`
    re-dispatches on whatever was bound — so every spelling it recognises is
    reachable through a name, not just the string ones.
    """
    _, offsets = _hits('OFFSET = timedelta(hours=-5)\ntz = timezone(OFFSET)\n')
    assert offsets, offsets

    # Through a class attribute, and through the negated spelling.
    _, offsets = _hits('class C:\n    OFF = timedelta(hours=-4)\n'
                       'tz = timezone(C.OFF)\n')
    assert offsets, offsets
    _, offsets = _hits('OFFSET = -timedelta(hours=5)\ntz = timezone(OFFSET)\n')
    assert offsets, offsets

    # A benign offset stored the same way is not a finding.
    assert _hits('OFFSET = timedelta(hours=1)\ntz = timezone(OFFSET)\n') == ([], [])


def test_an_uppercase_keyword_argument_is_a_timezone_key():
    """`os.environ.update(TZ="EST")` is the conventional spelling.

    The dict-key and subscript branches were lowercased and this one was not,
    so the same value was caught in two forms and missed in the third
    (Codex, PR #993).
    """
    legacy, _ = _hits('os.environ.update(TZ="EST")\n')
    assert legacy, legacy
    _, offsets = _hits('env = dict(os.environ, TZ="-05:00")\n')
    assert offsets, offsets

    # Still gated on the key meaning a timezone.
    assert _hits('cache.set(KEY="EST")\n') == ([], [])


def test_posix_and_utc_prefixed_offsets_are_offsets():
    """`EST5` and `UTC-05:00` are fixed zones spelled as names.

    `TZ=EST5` installs a POSIX zone with no DST rule — frozen at UTC-5 all
    year — and a pattern that knew only a bare number and the `Etc/GMT` names
    walked past both (Codex, PR #993).
    """
    for src in ('os.environ["TZ"] = "EST5"\n',
                'ts = pd.Timestamp("2026-01-01", tz="UTC-05:00")\n',
                'tz = ZoneInfo("GMT-05:00")\n'):
        assert _hits(src)[1], src

    # `EST5EDT` is DST-correct and belongs to the backward-link test, not
    # this one — the anchors must stop `EST5` claiming its prefix.
    legacy, offsets = _hits('tz = ZoneInfo("EST5EDT")\n')
    assert legacy and not offsets, (legacy, offsets)
    # And a non-Eastern POSIX zone is not this guard's business.
    assert _hits('os.environ["TZ"] = "PST8PDT"\n') == ([], [])


def test_a_generic_method_name_is_not_a_timezone_context():
    """`translator.localize("EST")` has nothing to do with timezones.

    `_call_name` reads the final attribute and drops the receiver, so any
    method named `localize`, `now` or `timezone` was classified as a timezone
    constructor — and since `EST`/`EDT` are deliberately allowed as ordinary
    tokens, that is a false CI failure on unrelated code (Codex, PR #993).
    """
    assert _hits('translator.localize("EST")\n') == ([], [])
    assert _hits('cache.now("EDT")\n') == ([], [])
    assert _hits('settings.timezone("EST")\n') == ([], [])

    # A recognised receiver makes the same name specific again.
    assert _hits('import pytz\ntz = pytz.timezone("EST")\n')[0]
    assert _hits('import pytz as p\ntz = p.timezone("EST")\n')[0]
    assert _hits('ts = pd.Timestamp.now("EST")\n')[0]
    # As does a constructor whose name means one thing.
    assert _hits('tz = ZoneInfo("EST")\n')[0]
    assert _hits('dt.astimezone(ZoneInfo("EST"))\n')[0]

    # An UNAMBIGUOUS name is still reported through a generic call: only the
    # bare tokens need the stronger context.
    assert _hits('translator.localize("US/Eastern")\n')[0]
    assert _hits('cache.now("-05:00")\n')[1]
    # And a timezone keyword is a context on its own, whatever the receiver.
    assert _hits('cache.now(tz="EST")\n')[0]


def test_postgres_set_scope_modifiers_are_still_set():
    """`SET LOCAL timezone TO 'EST'` freezes the transaction.

    Requiring `TIME ZONE` immediately after `SET` exempted the two standard
    scope modifiers (Codex, PR #993).
    """
    for stmt in ("SET LOCAL timezone TO 'EST'", "SET SESSION TIME ZONE 'EDT'",
                 "set local time zone 'est'"):
        assert NONPY_AMBIGUOUS.search(stmt), stmt
    assert NONPY_FIXED_OFFSET.search("SET SESSION TIME ZONE '-05:00'")
    # Not every `SET LOCAL` is a timezone.
    assert not NONPY_AMBIGUOUS.search("SET LOCAL search_path TO estimates")


def test_dockers_whitespace_env_form_is_a_timezone_key():
    """`ENV TZ EST` is valid Dockerfile, and Dockerfiles are scanned for
    exactly this (Codex, PR #993)."""
    assert NONPY_AMBIGUOUS.search("ENV TZ EST")
    assert NONPY_FIXED_OFFSET.search("ENV TZ -05:00")
    # The equals form still works, and an unrelated ENV is not a timezone.
    assert NONPY_AMBIGUOUS.search("ENV TZ=EST")
    assert not NONPY_AMBIGUOUS.search("ENV ESTIMATOR fast")


def test_the_timezone_context_is_not_vacuous():
    """An empty alternative in `_TZ_CONTEXT` matches everywhere.

    Found while injection-testing the Dockerfile form: deleting one
    alternative left the `|` before it, and the context then matched the empty
    string — so every bare `EST` and `EDT` in the repository became a
    finding. CI would go red loudly rather than silently, but the failure
    reads as "the guard found 400 violations" rather than "the guard is
    broken", which is the wrong thing to debug at 2am. One assertion here says
    which it is.
    """
    assert not re.compile(_TZ_CONTEXT).match(""), (
        "_TZ_CONTEXT matches the empty string — an alternative is missing "
        "its body, probably a trailing or doubled '|'")
    # And the ambiguous names still need a real context in front of them.
    assert not NONPY_AMBIGUOUS.search("the estimate was EST")
    assert not NONPY_AMBIGUOUS.search("EST")
