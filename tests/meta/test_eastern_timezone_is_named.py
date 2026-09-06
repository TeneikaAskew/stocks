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

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
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
LEGACY_ZONES = re.compile(
    r"(?:" + _TZ_CONTEXT + r")\s*"
    r"""['"](?:US/Eastern|EST5EDT|America/Montreal|Canada/Eastern|EST|EDT)['"]"""
)

# A fixed offset standing in for Eastern.
FIXED_OFFSET = re.compile(
    r"timezone\s*\(\s*timedelta\s*\(\s*hours\s*=\s*-\s*[45]\s*\)"
    r"|timedelta\s*\(\s*hours\s*=\s*-\s*[45]\s*\)\s*\)"
)


def _source_files() -> list[pathlib.Path]:
    out = []
    for p in REPO.rglob("*.py"):
        if SKIP_DIRS & set(p.relative_to(REPO).parts):
            continue
        out.append(p)
    for pattern in ("*.sql", "*.sh"):
        for p in REPO.rglob(pattern):
            if SKIP_DIRS & set(p.relative_to(REPO).parts):
                continue
            out.append(p)
    return out


def _hits(pattern: re.Pattern, allow: re.Pattern | None = None) -> list[str]:
    found = []
    for p in _source_files():
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if allow is not None and allow.search(line):
                continue
            if pattern.search(line):
                found.append(f"{p.relative_to(REPO)}:{i}: {line.strip()[:110]}")
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

    Checked per enclosing shell function rather than per `gcloud` invocation,
    because several sites build their flags into a bash array declared earlier
    in the function (`_enrich_common`, `common_flags`). A line-window parser
    reported `strat-enrich-daily` as missing its timezone when the flag was
    eight lines above the call -- the same array-resolution trap
    `docs/product/05-INFRASTRUCTURE.md` records for its job-count parser.

    Live truth is checked separately by `scripts/verify_docs_against_live.py`;
    this test is the hermetic half.
    """
    src = (REPO / "gcp" / "deploy.sh").read_text()
    body = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))

    # Every timezone literal in the file must be Eastern, wherever it sits.
    zones = set(re.findall(r"--time-zone\s+[\"']?([A-Za-z_/+\-0-9]+)[\"']?", body))
    assert zones, "no --time-zone flags found -- has deploy.sh moved?"
    assert zones == {EASTERN}, f"non-Eastern scheduler timezones in deploy.sh: {sorted(zones - {EASTERN})}"

    # And every function that creates a scheduler must set one.
    funcs = re.split(r"\n(?=[A-Za-z_][A-Za-z0-9_]*\s*\(\)\s*\{)", body)
    offenders = []
    for f in funcs:
        if "gcloud scheduler jobs create http" not in f and \
           "gcloud scheduler jobs update http" not in f:
            continue
        if "--time-zone" not in f:
            name = f.split("(")[0].strip().splitlines()[-1] if "(" in f else "<top level>"
            offenders.append(name)
    assert not offenders, (
        "Cloud Scheduler defaults to UTC when --time-zone is omitted; "
        f"these functions create entries without it: {offenders}")


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
