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
# Quotes are OPTIONAL. `gcp/deploy.sh` is scanned and `--time-zone US/Eastern`
# is the ordinary shell spelling, so requiring quotes exempted the exact form
# most likely to appear in the file the scheduler check exists for. The
# trailing lookahead is what keeps the unquoted branch honest: without it,
# `EST` would match inside `ESTIMATE`.
LEGACY_ZONES = re.compile(
    r"(?:" + _TZ_CONTEXT + r")\s*"
    r"""['"]?(?:US/Eastern|EST5EDT|America/Montreal|Canada/Eastern|EST|EDT)"""
    r"""['"]?(?![A-Za-z0-9_/-])"""
)

# A fixed offset standing in for Eastern, in either of the two spellings.
#
# The `timedelta` form was the only one matched at first, which left the
# spelling a pandas user actually reaches for -- `tz="-05:00"`,
# `tz_localize("-04:00")` -- passing a guard whose whole claim is that a fixed
# offset cannot express Eastern. Same freeze, same half-the-year wrongness,
# invisible to the check.
FIXED_OFFSET = re.compile(
    r"timezone\s*\(\s*timedelta\s*\(\s*hours\s*=\s*-\s*[45]\s*\)"
    r"|timedelta\s*\(\s*hours\s*=\s*-\s*[45]\s*\)\s*\)"
    r"|(?:" + _TZ_CONTEXT + r")\s*['\"]\s*-\s*0?[45]:?00\s*['\"]"
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


def _hits(pattern: re.Pattern, allow: re.Pattern | None = None) -> list[str]:
    r"""Search whole files, not line by line.

    Matching per line meant a formatter could defeat the guard by wrapping:

        ZoneInfo(
            "US/Eastern"
        )

    Neither line contains both halves, so nothing matched -- and that is the
    routine output of a line-length formatter, not an exotic case. The
    patterns already join their two halves with `\s*`, and `\s` spans
    newlines, so searching the full text is all that was needed.

    `allow` keeps its per-line meaning (it exempts a line that spells a
    forbidden name deliberately), applied to the line the match STARTS on.
    """
    found = []
    for p in _source_files():
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        for m in pattern.finditer(text):
            lineno = text.count("\n", 0, m.start()) + 1
            line = lines[lineno - 1] if lineno <= len(lines) else ""
            if allow is not None and allow.search(line):
                continue
            snippet = " ".join(m.group(0).split())[:110]
            found.append(f"{p.relative_to(REPO)}:{lineno}: {snippet}")
    return found


def test_no_legacy_eastern_zone_names():
    """`US/Eastern` and friends are backward links; write the canonical name."""
    # This test file necessarily spells the forbidden names to forbid them.
    allow = re.compile(r"LEGACY_ZONES|test_eastern_timezone_is_named|^\s*[*#]")
    hits = [h for h in _hits(LEGACY_ZONES, allow)
            if SELF not in h]
    assert not hits, (
        "Eastern time must be named 'America/New_York', not a backward link:\n  "
        + "\n  ".join(hits))


def test_no_fixed_offset_standing_in_for_eastern():
    """-04:00/-05:00 is right for half the year and wrong for the other half."""
    hits = [h for h in _hits(FIXED_OFFSET)
            if SELF not in h]
    assert not hits, (
        "A fixed UTC offset cannot express Eastern time across DST:\n  "
        + "\n  ".join(hits))


def test_every_scheduler_declaration_uses_the_named_zone():
    """`gcp/deploy.sh` creates every Cloud Scheduler entry; all must be ET.

    Read live 2026-09-06, all 84 entries are `America/New_York`. This keeps a
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
    zones = set(re.findall(r"--time-zone\s+[\"']?([A-Za-z_/+\-0-9]+)[\"']?", body))
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
