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
  (read live 2026-09-06: 84 of 84);
* one site compared `str(ts.tz).upper() != 'US/EASTERN'` to skip a convert,
  which silently stopped matching the moment the zone was spelled the other
  way.

Hermetic: reads the repo's own source, no network and no database.
"""
from __future__ import annotations

import ast
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
NONPY_UNAMBIGUOUS = re.compile(
    r"""['"]?(?:""" + "|".join(UNAMBIGUOUS_LEGACY) + r""")['"]?"""
    r"""(?![A-Za-z0-9_/-])"""
)
NONPY_AMBIGUOUS = re.compile(
    r"(?:" + _TZ_CONTEXT + r")\s*"
    r"""['"]?(?:""" + "|".join(AMBIGUOUS_LEGACY) + r""")['"]?"""
    r"""(?![A-Za-z0-9_/-])"""
)
NONPY_FIXED_OFFSET = re.compile(
    r"(?:" + _TZ_CONTEXT + r")\s*['\"]\s*-\s*0?[45]:?00\s*['\"]"
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

_TZ_CALLS = {"ZoneInfo", "timezone", "localize", "tz_localize", "tz_convert",
             "astimezone", "now", "Timestamp"}
_TZ_KEYWORDS = {"tz", "tzinfo", "timezone", "time_zone", "key"}
_FIXED_OFFSET_STRINGS = re.compile(r"^-0?[45]:?00$")


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


def _python_hits(path: pathlib.Path, text: str) -> tuple[list[str], list[str]]:
    """(legacy-name hits, fixed-offset hits) for one Python file."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [], []

    legacy, offsets = [], []
    rel = path.relative_to(REPO)

    def note(bucket, node, what):
        bucket.append(f"{rel}:{getattr(node, 'lineno', 0)}: {what}")

    for node in ast.walk(tree):
        # A legacy zone name as the value of a timezone-ish keyword, anywhere.
        if isinstance(node, ast.keyword) and node.arg in _TZ_KEYWORDS:
            v = node.value
            if isinstance(v, ast.Constant) and v.value in ALL_LEGACY:
                note(legacy, v, f"{node.arg}={v.value!r}")
            elif (isinstance(v, ast.Constant) and isinstance(v.value, str)
                    and _FIXED_OFFSET_STRINGS.match(v.value)):
                note(offsets, v, f"{node.arg}={v.value!r}")
            elif _is_eastern_fixed_timedelta(v):
                note(offsets, v, f"{node.arg}=timedelta(hours=-4|-5, ...)")

        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name not in _TZ_CALLS:
            continue
        # Positional and keyword arguments alike.
        for arg in list(node.args) + [k.value for k in node.keywords]:
            if isinstance(arg, ast.Constant) and arg.value in ALL_LEGACY:
                note(legacy, arg, f"{name}(... {arg.value!r} ...)")
            elif (isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                    and _FIXED_OFFSET_STRINGS.match(arg.value)):
                note(offsets, arg, f"{name}(... {arg.value!r} ...)")
            elif _is_eastern_fixed_timedelta(arg):
                note(offsets, arg, f"{name}(timedelta(hours=-4|-5, ...))")
    return legacy, offsets


def _scan() -> tuple[list[str], list[str]]:
    """Repository-wide (legacy-name hits, fixed-offset hits).

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

    Read live 2026-09-07, all 64 entries are `America/New_York` (64 in
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
    zones = set(re.findall(
        r"--time-zone[=\s]+[\"']?([A-Za-z_/+\-0-9]+)[\"']?", body))
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
        if "--time-zone" in func[start:i]:
            names.add(m.group(1))
    return {f"${{{n}[@]}}" for n in names} | {f"${n}" for n in names}


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
            out.append("\n".join(cmd))
        i += 1
    return out


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
