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
    for pattern in ("*.py", "*.sql", "*.sh"):
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
UNAMBIGUOUS_LEGACY = ("US/Eastern", "EST5EDT", "America/Montreal",
                      "Canada/Eastern")
AMBIGUOUS_LEGACY = ("EST", "EDT")
ALL_LEGACY = UNAMBIGUOUS_LEGACY + AMBIGUOUS_LEGACY

_TZ_CONTEXT = (
    r"tz\s*=|tzinfo\s*=|time_?zone\s*=|time-zone[= ]|ZoneInfo\s*\(|"
    r"pytz\.timezone\s*\(|tz_convert\s*\(|tz_localize\s*\(|"
    r"AT TIME ZONE\s*|Timestamp\.now\s*\(|astimezone\s*\("
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
    r"""['"]?(?:""" + "|".join(UNAMBIGUOUS_LEGACY) + r""")['"]?"""
    r"""(?![A-Za-z0-9_/-])""", re.I
)
NONPY_AMBIGUOUS = re.compile(
    r"(?:" + _TZ_CONTEXT + r")\s*"
    r"""['"]?(?:""" + "|".join(AMBIGUOUS_LEGACY) + r""")['"]?"""
    r"""(?![A-Za-z0-9_/-])""", re.I
)
NONPY_FIXED_OFFSET = re.compile(
    r"(?:" + _TZ_CONTEXT + r")\s*['\"]\s*-\s*0?[45]:?00\s*['\"]", re.I
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
_TZ_CALLS = {"ZoneInfo", "timezone", "localize", "tz_localize", "tz_convert",
             "astimezone", "now", "Timestamp", "gettz"}
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
    r"^(?:-0?[45]:?00|Etc/GMT\+0?[45])$")

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


def _is_eastern_fixed_timedelta(node: ast.AST) -> bool:
    """`timedelta(hours=-4|-5, ...)`, with any number of other arguments.

    The `, minutes=0` case is why this is a walk and not a pattern: the old
    regex required the closing paren immediately after the hour value.
    """
    if not isinstance(node, ast.Call) or _call_name(node) != "timedelta":
        return False
    for kw in node.keywords:
        if kw.arg != "hours":
            continue
        v = kw.value
        if (isinstance(v, ast.UnaryOp) and isinstance(v.op, ast.USub)
                and isinstance(v.operand, ast.Constant)
                and v.operand.value in (4, 5)):
            return True
    return False


def _string_bindings(tree: ast.AST) -> dict[str, tuple[str, ast.AST]]:
    """`NAME = "..."` -> (value, node), for following an indirect zone.

    `EASTERN = "US/Eastern"` then `ZoneInfo(EASTERN)` is a routine way to share
    one timezone across a module, and it passes a check that only reads
    constants at the call site because the argument is an `ast.Name` (Codex,
    PR #993).

    A LEGACY binding wins, not the last one. "Last assignment wins" was the
    first rule here and it says the opposite of what this file claims: with
    `TZ = "EST"; ZoneInfo(TZ); TZ = "UTC"` the later value overwrote the
    earlier one and the call resolved to `UTC`, so the violation between them
    disappeared (Codex, PR #993). A guard does not need to model reassignment
    correctly, but it must not model it in the direction that hides the thing
    it looks for: if a name is EVER bound to a legacy zone or a fixed offset
    in this file, that binding is what the guard keeps.
    """
    out: dict[str, tuple[str, ast.AST]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        else:
            continue
        v = node.value
        if not (isinstance(v, ast.Constant) and isinstance(v.value, str)):
            continue
        interesting = (v.value in ALL_LEGACY
                       or bool(_FIXED_OFFSET_STRINGS.match(v.value)))
        for t in targets:
            if not isinstance(t, ast.Name):
                continue
            held = out.get(t.id)
            if held is not None and not interesting:
                held_value = held[0]
                if (held_value in ALL_LEGACY
                        or _FIXED_OFFSET_STRINGS.match(held_value)):
                    continue      # do not overwrite a violation with a value
            out[t.id] = (v.value, v)
    return out


def _python_hits(path: pathlib.Path, text: str) -> tuple[list[str], list[str]]:
    """(legacy-name hits, fixed-offset hits) for one Python file."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [], []

    legacy, offsets = [], []
    rel = path.relative_to(REPO)
    bindings = _string_bindings(tree)

    def note(bucket, node, what):
        bucket.append(f"{rel}:{getattr(node, 'lineno', 0)}: {what}")

    reported: set[int] = set()

    def follow(bucket_legacy, bucket_offsets, node, arg, where):
        """Report `arg` when it is, or resolves to, a legacy zone or offset."""
        reported.add(id(arg))
        if isinstance(arg, ast.Constant) and arg.value in ALL_LEGACY:
            note(bucket_legacy, arg, where(repr(arg.value)))
            return True
        if (isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                and _FIXED_OFFSET_STRINGS.match(arg.value)):
            note(bucket_offsets, arg, where(repr(arg.value)))
            return True
        if _is_eastern_fixed_timedelta(arg):
            note(bucket_offsets, arg, where("timedelta(hours=-4|-5, ...)"))
            return True
        if isinstance(arg, ast.Name) and arg.id in bindings:
            value, _src = bindings[arg.id]
            shown = f"{arg.id} (= {value!r})"
            if value in ALL_LEGACY:
                note(bucket_legacy, arg, where(shown))
                return True
            if _FIXED_OFFSET_STRINGS.match(value):
                note(bucket_offsets, arg, where(shown))
                return True
        return False

    for node in ast.walk(tree):
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
            note(legacy, node, repr(node.value))

        # Same rule, different bucket: `Etc/GMT+5` is a named zone frozen at
        # a fixed offset, so it belongs to the offset test rather than the
        # backward-link one.
        if (isinstance(node, ast.Constant)
                and node.value in _FIXED_OFFSET_ZONES
                and id(node) not in reported):
            note(offsets, node, repr(node.value))

        # `{"tz": "EST"}` -- a config literal read back at some other site.
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if (isinstance(k, ast.Constant) and k.value in _TZ_KEYWORDS
                        and isinstance(v, ast.Constant)):
                    follow(legacy, offsets, node, v,
                           lambda shown, k=k: f"{k.value!r}: {shown}")

        # A legacy zone name as the value of a timezone-ish keyword, anywhere.
        if isinstance(node, ast.keyword) and node.arg in _TZ_KEYWORDS:
            follow(legacy, offsets, node, node.value,
                   lambda shown, a=node.arg: f"{a}={shown}")

        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name not in _TZ_CALLS:
            continue
        # Positional and keyword arguments alike.
        for arg in list(node.args) + [k.value for k in node.keywords]:
            follow(legacy, offsets, node, arg,
                   lambda shown, n=name: f"{n}(... {shown} ...)")

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
    return {f"${{{n}[@]}}" for n in names} | {f"${n}" for n in names}


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
    assert _string_bindings(tree)["TZ"][0] == "EST"

    # A name never bound to anything interesting still takes its last value.
    tree = ast.parse('TZ = "UTC"\nTZ = "America/New_York"\n')
    assert _string_bindings(tree)["TZ"][0] == "America/New_York"


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
