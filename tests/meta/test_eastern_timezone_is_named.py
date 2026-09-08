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
import subprocess
import json
import pathlib
import re
import shlex
import uuid
from datetime import datetime, timedelta
from typing import NamedTuple
from zoneinfo import ZoneInfo

import pytest
import yaml

def _repo_root() -> pathlib.Path:
    """Walk up to the checkout root, rather than counting directories.

    `parent.parent.parent` was correct for exactly one layout. Moving this
    file one level deeper would silently resolve REPO to `tests/`, and the
    scans would then cover no production code at all while still passing --
    a guard reporting a clean repository it never looked at. That is the same
    class of breakage the file move already caused once on this branch, so
    counting depth twice would have been a poor lesson.
    """
    return _find_repo_root(pathlib.Path(__file__).resolve())


# Directories that together identify THIS checkout. Requiring `.git` as well
# made the no-git fallback in `_tracked_files` unreachable: `REPO` is computed
# at import, so a source export raised `RuntimeError` and the entire guard did
# not run -- while its own docstring claimed it degraded gracefully. A comment
# describing behaviour the code cannot perform is worse than no comment
# (Codex, PR #993).
_ROOT_MARKERS = ("gcp", "lib", "platform", "tests")


def _find_repo_root(start: pathlib.Path) -> pathlib.Path:
    """The nearest ancestor that looks like this repository.

    `.git` still wins where both could match, so a fixture tree that happens
    to carry the marker directories cannot capture the root ahead of the real
    checkout.
    """
    parents = list(start.parents)
    for candidate in parents:
        if (candidate / ".git").exists() and (candidate / "gcp").is_dir():
            return candidate
    for candidate in parents:
        if all((candidate / d).is_dir() for d in _ROOT_MARKERS):
            return candidate
    raise RuntimeError(f"could not locate the repository root above {start}")


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
# JSON the APPLICATION reads at runtime, as opposed to fixtures and captures.
RUNTIME_JSON_CONFIG = ("alert_config.json",)


@functools.lru_cache(maxsize=1)
def _tracked_files() -> frozenset:
    """Every path `git ls-files` reports, as absolute paths.

    The collector used `REPO.rglob`, which walks whatever happens to be in the
    working tree: a local `scratch.py` or copied build output containing
    `ZoneInfo("US/Eastern")` failed a guard that is supposed to be about
    repository sources, so the verdict depended on the machine (Codex,
    PR #993). Falling back to "everything" when git is unavailable keeps the
    guard working in a source export rather than silently scanning nothing --
    the failure direction that matters here is a MISSED violation.
    """
    try:
        out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z"],
                             capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return frozenset()
    return frozenset(REPO / n for n in out.stdout.decode().split("\0") if n)


#: What the repository-wide scan reads, by glob. `GNUmakefile` and lowercase
#: `makefile` are the other two names Make loads without being told, and
#: `_reads_as_make` already knew them while this list did not, so a newly
#: tracked one would have bypassed both guards (Codex, PR #993 final review).
SOURCE_PATTERNS = ("*.py", "*.sql", "*.sh", "*.yml", "*.yaml", "Dockerfile*",
                   "Makefile", "GNUmakefile", "makefile", "*.mk", "*.ipynb",
                   ".env.example", ".env.*.example", "*.env.example")


def _source_files() -> list[pathlib.Path]:
    tracked = _tracked_files()
    out = []
    # YAML and Dockerfiles are where a `TZ: US/Eastern` or `ENV TZ=EST` would
    # live, and neither was scanned -- the guard's docstring says
    # repository-wide (Codex, PR #993).
    # `.env.example` is tracked and is what people copy into `.env`, so a
    # legacy or fixed zone shipped there is distributed to every developer
    # while both guards pass (Codex, PR #993).
    #
    # The TEMPLATES only, never a bare `.env`: that file is gitignored and
    # local, so scanning it would make this suite report findings that depend
    # on the machine it runs on -- the environment-dependence #999 spent a
    # round removing from the route table.
    # `.ipynb` is executable source. Four tracked notebooks live under
    # `notebooks/`, and a cell pinning `US/Eastern` or a fixed offset makes
    # DST-sensitive research diverge from production with both guards green
    # (Codex, PR #993). Archived notebooks are excluded by SKIP_DIRS, like
    # every other archived path.
    # `Makefile` sits beside Dockerfile as tracked, executable configuration:
    # `export TZ = EST` there fixes the zone for every recipe (Codex, PR #993).
    for pattern in SOURCE_PATTERNS:
        for p in REPO.rglob(pattern):
            if SKIP_DIRS & set(p.relative_to(REPO).parts):
                continue
            if tracked and p not in tracked:
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
            if tracked and p not in tracked:
                continue
            out.append(p)
    # The runtime JSON configuration, by name rather than by extension.
    # `lib.config.load_config` reads `alert_config.json` in production, so a
    # `"timezone": "EST"` added there is consumed by the application while
    # every JSON file sat outside the scan as "not source" (Codex, PR #993).
    # Named individually because the blanket rule is still right: test
    # fixtures and captured payloads legitimately carry canned values, and
    # scanning them would make this guard cry wolf.
    for name in RUNTIME_JSON_CONFIG:
        cfg = REPO / name
        if cfg.is_file() and (not tracked or cfg in tracked):
            out.append(cfg)
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
# The assignment-shaped contexts additionally refuse a shell REFERENCE. In
# `if [ "$TZ" = EST ]` the quote-tolerant `_Q` consumed the closing quote and
# `TZ" = EST` read as an assignment, so a script that only compares a
# variable it never sets failed CI (Codex, PR #993 final review). `$TZ` is a
# read in every language this scan collects and never a target; `${TZ:=EST}`
# still assigns, and is untouched because the brace sits between.
_BV = _B + r"(?<!\$)"
# Every operator that BINDS a value to a key in the file types this scans.
# A bare `[:=]` covered shell, YAML and `.env`, and stopped one character
# short of Make: GNU Make writes `TZ := EST` (simple), `TZ ?= EST` (default)
# and `TZ ::= EST` (POSIX simple), and `export TZ := EST` puts the resulting
# fixed zone in every recipe's environment. Makefiles were added to the
# collector precisely to cover that, so accepting only the recursive `=`
# left the collector reading files whose ordinary spelling it could not match
# (Codex, PR #993). Longest alternatives first, or `:=` would match as `:`
# and leave `=` to be read as part of the value.
_ASSIGN = r"(?:::=|:=|\?=|\+=|[:=])"
# YAML quotes a key as readily as it leaves it bare, and the quote sits
# between the key and the colon: `"TZ": "EST"` matched no context at all,
# in exactly the file types this scan was widened to cover (Codex, PR #993).
_Q = r"[\"']?\s*"
_TZ_CONTEXT = (
    # `TZ = EST` with spaces around the `=` is make's ordinary spelling, and
    # the quote-tolerant `_Q` did not allow bare whitespace (Codex, PR #993).
    _BV + r"tz" + _Q + r"\s*" + _ASSIGN + r"|"
    + _BV + r"tzinfo" + _Q + r"\s*" + _ASSIGN + r"|"
    # libpq's own variable, for the shell and manifest side of the same
    # finding: `PGTZ` is not matched by the `tz` alternative above because
    # that one is anchored at an identifier boundary, and `PGTZ=EST` in a
    # Dockerfile or a compose file installs the frozen session zone just as
    # `os.environ["PGTZ"]` does (Codex, PR #993).
    + _BV + r"pgtz" + _Q + r"\s*" + _ASSIGN + r"|"
    + _BV + r"time_?zone" + _Q + r"\s*" + _ASSIGN + r"|"
    + _B + r"time-zone(?:" + _ASSIGN + r"| )|" + _B + r"ZoneInfo\s*\(|"
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
    # `INTERVAL` is optional and consumed here rather than left for the
    # offset matcher: `SET TIME ZONE INTERVAL '-05:00' HOUR TO MINUTE` is a
    # fixed UTC-5 session zone that Postgres accepts, and the keyword sat
    # between the context and the value so neither SQL matcher reached it
    # (Codex, PR #993).
    + _B + r"SET\s+(?:LOCAL\s+|SESSION\s+)?TIME[ _]?ZONE\s*(?:TO\s+)?"
    + r"(?:INTERVAL\s+)?|"
    # Dockerfiles take `ENV <key> <value>` as well as `ENV <key>=<value>`, and
    # the abbreviated `tz` key required a `:` or `=`. Dockerfiles were added to
    # this scan precisely to cover deployment configuration, so accepting only
    # the equals form let an image pin a fixed Eastern offset with both guards
    # green (Codex, PR #993).
    + _B + r"ENV\s+TZ\s+|"
    # Postgres has a third spelling. `SELECT set_config('timezone', 'EST',
    # false)` does exactly what `SET TIME ZONE 'EST'` does -- and the
    # transaction-local `true` form what `SET LOCAL` does -- but only the
    # statement forms were contexts (Codex, PR #993). The setting NAME is
    # required, so `set_config('work_mem', ...)` is not a timezone context.
    + _B + r"set_config\s*\(\s*[\"']timezone[\"']\s*,\s*"
)

# The SQL STATEMENT forms, split out of `_TZ_CONTEXT` so a string carrying
# Python source can be told from one carrying a query. `_TZ_CONTEXT`'s other
# alternatives (`tz=`, `timezone:`, a constructor call) appear in ordinary
# prose and in Python that another branch already reads properly, so they are
# not evidence that a string is SQL.
# libpq's per-connection settings: `-c timezone=EST` in `options`, or the
# long spelling. `PGTZ=` is already a `_TZ_CONTEXT`.
_LIBPQ_OPTION = re.compile(r"(?:^|\s)-c\s*timezone\s*=|--timezone\s*=", re.I)

_SQL_STATEMENT = re.compile(
    r"(?:" + _B + r"SET\s+(?:LOCAL\s+|SESSION\s+)?TIME[ _]?ZONE"
    r"|" + _B + r"AT TIME ZONE"
    r"|" + _B + r"set_config\s*\(\s*[\"']timezone[\"']\s*,)", re.I)


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
# A boundary on BOTH sides. Only the right-hand one was guarded, so the
# case-insensitive `US/Eastern` alternative matched the tail of an ordinary
# path -- `/api/status/eastern` contains `us/eastern` -- and `BUS/Eastern`
# matched for the same reason. A URL or an identifier is not a timezone, and
# a guard that fails on one is a false CI failure (Codex, PR #993).
# No `/` in this class, deliberately. The boundary exists to stop a match
# starting inside a WORD -- `status/eastern` and `BUS/Eastern` are rejected
# because the character before the match is alphanumeric -- and adding `/`
# to it also rejected `TZ=:/usr/share/zoneinfo/US/Eastern`, which is the
# Linux zone-file spelling and a real way to install the legacy zone. The
# first version of this boundary broke that (Codex, PR #993); a separator
# immediately before a COMPLETE zone name is exactly where one belongs.
_LB = r"(?<![A-Za-z0-9_-])"
NONPY_UNAMBIGUOUS = re.compile(
    _LB + r"""['"]?""" + _LB
    + r"""(?:""" + "|".join(re.escape(z) for z in UNAMBIGUOUS_LEGACY)
    + r""")['"]?"""
    r"""(?![A-Za-z0-9_/-])""", re.I
)
# `\` at end of line joins the next line in shell, so `export TZ=\` then
# `EST` is one assignment. Joining the text is not an option: every shell
# pass here is width-preserving because `_scalar_in_force` and
# `_scheduler_commands` resolve by character offset, and a join removes a
# newline. So the MATCHERS tolerate a continuation between context and value
# instead, and the text stays exactly as written (Codex, PR #993).
_GAP = r"(?:\s|\\\n)*"
NONPY_AMBIGUOUS = re.compile(
    r"(?:" + _TZ_CONTEXT + r")" + _GAP
    + r"""['"]?(?:""" + "|".join(AMBIGUOUS_LEGACY) + r""")['"]?"""
    r"""(?![A-Za-z0-9_/-])""", re.I
)
# `EST5` and `EDT4` are POSIX's fixed form -- a std abbreviation with an
# offset and NO DST rule, so they are frozen at UTC-5 / UTC-4 all year, and
# `TZ=EST5` installs that for a whole process. Both were invisible to a
# pattern that knew only a bare number and the `Etc/GMT` names (Codex,
# PR #993).
#
# `UTC-05:00` is NOT here, and its absence is the point. POSIX inverts the
# sign in a `TZ` value: `TZ=UTC-05:00` selects UTC+**5**, not Eastern, while
# `pd.Timestamp(tz="UTC-05:00")` really does mean UTC-5. I added it last round
# reading it the pandas way, which made `os.environ["TZ"] = "UTC-05:00"` a
# false finding on a timezone that is not Eastern in either season (Codex,
# PR #993). One string, two opposite meanings, decided by a context this
# guard does not track -- so it matches neither, and loses the pandas spelling
# rather than inventing a violation. The POSIX abbreviations above have no
# such ambiguity: the offset in `EST5` is hours WEST in every context.
#
# `EST5EDT` deliberately does NOT match: the anchors keep the `EST5`
# alternative from claiming its prefix, and it belongs to the backward-link
# test rather than this one -- it IS DST-correct, it is just the wrong name.
#
# The seconds field is OPTIONAL and must be `00`. `-05:00:00` is the same
# UTC-5 written longhand and stays a finding; `-05:00:30` is UTC-05:00:30,
# which is not Eastern in either season, and the pattern used to claim its
# `-05:00` prefix and fail CI on it (Codex, PR #993). Same shape as the
# `FixedOffset(-300.5)` finding two rounds ago -- a near-miss offset
# truncated into a violation -- in the text matcher rather than the AST one.
# POSIX writes the offset as `[+]h[h][:mm[:ss]]`, so `EST05`, `EST+5` and
# `EST05:00` are the same frozen UTC-5 as `EST5`, and only the shortest
# spelling was known: `TZ=EST05` passed the text path and the AST path both,
# while the ambiguous-name matcher rightly refuses `EST` followed by a digit
# (Codex, PR #993 final review). The lookahead on every user of this pattern
# still refuses `EST5EDT` and `EST05EDT`, which carry a DST rule.
# The POSIX fixed forms in one place, so the text matchers that need them
# with a context and the one that needs them without agree on the spelling.
_POSIX_EASTERN_FIXED = r"EST\+?0?5(?::00(?::00)?)?|EDT\+?0?4(?::00(?::00)?)?"
# The same POSIX form with `UTC` or `GMT` as the abbreviation. `TZ=UTC+5`
# names a zone called "UTC" at 5 hours WEST -- POSIX's sign -- so it is the
# same frozen UTC-5 as `EST5`, and `GMT+4` the same frozen UTC-4 as `EDT4`;
# the `+` and the leading zero are optional exactly as they are for `EST5`.
# Captured live: glibc `TZ=UTC+5 date` prints -0500, `TZ=GMT+4` -0400, and
# Postgres 16 `SET TIME ZONE 'GMT+4'` prints -04:00, which is what `PGTZ`
# issues; `TZ=UTC-5` prints +0500 and is not Eastern in either season.
# NOT folded into `_POSIX_EASTERN_FIXED`, because that pattern also serves
# contexts that read the sign the other way -- `pd.Timestamp(tz="UTC+5")`
# is UTC plus five -- while `EST5` has no second meaning anywhere. This one
# applies only where the value is known to be a process or session `TZ`
# (Codex, PR #993 final review).
# The ABBREVIATION is case-insensitive: glibc reads `TZ=utc+5` and `gMt+4`
# as the same frozen UTC-5 / UTC-4 as the uppercase forms (verified live).
# Written as inline classes rather than `re.I`, because `NONPY_POSIX_ENV_OFFSET`
# must keep its KEY (`TZ`/`PGTZ`) case-sensitive and so cannot carry the flag
# (Codex, PR #993 final review).
_UTC = r"(?:[Uu][Tt][Cc]|[Gg][Mm][Tt])"
_POSIX_UTC_FIXED = (_UTC + r"\+?0?5(?::00(?::00)?)?"
                    r"|" + _UTC + r"\+?0?4(?::00(?::00)?)?")
_POSIX_UTC_FIXED_VALUE = re.compile(r"(?:" + _POSIX_UTC_FIXED + r")")
#: The environment variables a process or libpq reads as a POSIX `TZ`. Env
#: names are case-sensitive on the Linux hosts these scripts target, so `tz`
#: is a different variable and does NOT configure the timezone -- the key is
#: matched exactly, only the abbreviation is case-folded (Codex, PR #993 final
#: review).
_POSIX_TZ_KEYS = {"TZ", "PGTZ"}
_FIXED_OFFSET_TEXT = r"(?:-\s*0?[45]:?00(?::00)?|" + _POSIX_EASTERN_FIXED + r")"
# Quotes optional, like the legacy-name pattern above and for the same reason:
# `timezone=-05:00` in a shell or YAML file is the ordinary spelling, and
# requiring both quotes exempted it (Codex, PR #993). The lookahead keeps the
# unquoted branch from matching a longer number.
NONPY_FIXED_OFFSET = re.compile(
    r"(?:" + _TZ_CONTEXT + r")" + _GAP + r"['\"]?\s*" + _FIXED_OFFSET_TEXT
    # `:` in the lookahead, so a seconds field the pattern did NOT consume
    # rejects the match instead of leaving it matched on a prefix.
    + r"\s*['\"]?(?![A-Za-z0-9_:])", re.I
)
# Only where the value is a process or session `TZ`: an assignment to `TZ`
# or `PGTZ` in a shell, Make, `.env` or Dockerfile (`=`, `:=`, `?=`, `+=`),
# a YAML `TZ:` key, or Dockerfile's `ENV TZ value` form. Not the generic
# `tz=`/`timezone=` contexts, whose readers may take the sign the other way.
# Case-sensitive on purpose: `tz` is another variable, and the POSIX sign
# belongs to `TZ`.
_POSIX_ENV_CONTEXT = (r"(?<![A-Za-z0-9_])(?:TZ|PGTZ)" + _GAP + r"(?:[:?+]?=|:)" + _GAP
                      + r"|" + _B + r"ENV\s+(?:TZ|PGTZ)\s+")
NONPY_POSIX_ENV_OFFSET = re.compile(
    r"(?:" + _POSIX_ENV_CONTEXT + r")['\"]?\s*(?:" + _POSIX_UTC_FIXED
    + r")\s*['\"]?(?![A-Za-z0-9_:])")
# Postgres also takes a bare number: `SET TIME ZONE -5` installs the same
# frozen UTC-5 session zone as `SET TIME ZONE '-05:00'`, and the matcher above
# requires the trailing `00` (Codex, PR #993).
#
# Confined to the SQL statement forms ON PURPOSE. POSIX inverts the sign in a
# `TZ` value, so `TZ=-5` selects UTC+5 and is not Eastern in either season --
# the same trap that keeps `UTC-05:00` out of `_FIXED_OFFSET_TEXT`. One
# spelling, two opposite meanings, decided by which side of the assignment it
# sits on.
# `SET timezone TO '-5'` and `SET TIMEZONE = -4` are the GUC spellings of the
# same statement -- `TIME ZONE` is the SQL-standard form, `timezone` the
# parameter name, and both `TO` and `=` are accepted -- and the numeric
# matcher knew only the standard form (Codex, PR #993).
_SQL_SET_TZ = r"\bSET\s+(?:LOCAL\s+|SESSION\s+)?TIME[ _]?ZONE\s*(?:TO\s+|=\s*)?"
NONPY_SQL_NUMERIC_OFFSET = re.compile(
    _SQL_SET_TZ + r"['\"]?\s*-\s*0?[45]\s*['\"]?(?![0-9:])", re.I
)


class _SqlIntervalOffset:
    """`SET TIME ZONE INTERVAL '-5 hours'`, evaluated rather than spelled.

    Round 18 added `INTERVAL '-05:00' HOUR TO MINUTE` as its own pattern, and
    the unit-bearing interval was the third `INTERVAL` shape in as many
    rounds. A fourth regex is the thing to stop: a constant interval is a
    NUMBER with a unit, so it is totalled and compared, as `_const_number`
    already does for folded arithmetic on the Python side (Codex, PR #993).

    `finditer`/`search` so it sits in the same loop as the compiled patterns.
    """
    _UNIT = {"h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
             "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
             "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1}
    _PAT = re.compile(
        _SQL_SET_TZ + r"INTERVAL\s+'\s*([^']*?)\s*'", re.I)
    _TERM = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*([A-Za-z]+)")

    def _total(self, body: str):
        total, seen = 0.0, False
        for num, unit in self._TERM.findall(body):
            scale = self._UNIT.get(unit.lower())
            if scale is None:
                return None             # a unit not modelled: undecidable
            total += float(num) * scale
            seen = True
        return total if seen else None

    def finditer(self, text: str):
        for m in self._PAT.finditer(text):
            total = self._total(m.group(1))
            if total is not None and total in _EASTERN_OFFSET_SECONDS:
                yield m

    def search(self, text: str):
        return next(self.finditer(text), None)


NONPY_SQL_INTERVAL_OFFSET = _SqlIntervalOffset()

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
                      "FixedOffset", "tzoffset"}
# `no_cache` is ZoneInfo's alternate constructor and returns the same object
# without the module cache; generic because plenty of unrelated APIs have a
# method by that name, so its RECEIVER is what makes it a timezone context
# (Codex, PR #993).
# `Timestamp` and `gettz` moved here from the specific set. Classified by
# name alone they convicted `factory.Timestamp("EST")` and
# `translator.gettz("EDT")` -- any library with a class or method of that name
# could fail CI on a string that is not a timezone, which is the same false
# positive already corrected for `now` and `localize` (Codex, PR #993).
# Nothing real is lost: `pd.Timestamp` and `dateutil.tz.gettz` are recognised
# by receiver, `from pandas import Timestamp` by import provenance, and an
# UNAMBIGUOUS zone name is reported through any call whatsoever -- it is only
# the bare `EST`/`EDT` tokens that need the stronger context.
# `tzstr` is dateutil's POSIX-string constructor: `tzstr("EST5")` is a frozen
# UTC-5 zone, and python-dateutil is a declared dependency here. Generic, so an
# unrelated `parser.tzstr(...)` cannot fail CI (Codex, PR #993).
_TZ_CALLS_GENERIC = {"timezone", "localize", "now", "no_cache",
                     "Timestamp", "gettz", "tzstr", "tzrange"}
_TZ_CALLS = _TZ_CALLS_SPECIFIC | _TZ_CALLS_GENERIC
# Receivers that make a generic name specific. Alias-resolved, so
# `import pytz as p` still reaches `pytz` -- and read as the LAST attribute of
# the chain, so `pd.Timestamp.now(...)` resolves to `Timestamp`.
_TZ_RECEIVERS = {"pytz", "tz", "dateutil", "pd", "pandas", "datetime",
                 "Timestamp", "zoneinfo", "ZoneInfo"}

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
# dateutil's `tzrange(name, offset)` takes SECONDS in the same second
# position as `tzoffset`, so it belongs with it rather than beside
# `FixedOffset` (Codex, PR #993).
_FIXED_OFFSET_SECOND_CALLS = {"tzoffset", "tzrange"}
# `key` is NOT here. It is the ZoneInfo constructor's parameter name and
# nothing else's, so as a GLOBAL keyword it flags `cache.get(key="EST")` and
# any other ordinary lookup -- a false CI failure on code that has no timezone
# in it, which is how a guard gets skipped (Codex, PR #993). The call branch
# below already reads every argument of a ZoneInfo call, keyword ones
# included, so `ZoneInfo(key="US/Eastern")` is still caught where it means
# something.
# `pgtz` joins them. This repository talks to Postgres through psycopg2, and
# libpq reads `PGTZ` when a connection is opened and issues it as the session
# timezone -- so `os.environ["PGTZ"] = "EST"` freezes every query on that
# connection at UTC-5, a wider blast radius than any single expression, and
# neither guard recognised the key (Codex, PR #993).
_TZ_KEYWORDS = {"tz", "tzinfo", "timezone", "time_zone", "pgtz"}
# Calls whose FIRST argument is a key and whose second is its value. Both set
# the process timezone when the key is `TZ`, and neither is a timezone
# constructor, so the call-name filter walked past them.
_ENV_SETTER_CALLS = {"putenv", "setdefault"}


def _posix_tz_offset(key_text, value, env):
    """`value`'s text when `key_text` names a process TZ and the text is a
    POSIX `UTC+5`/`GMT+4` fixed offset; else None.

    `os.environ["TZ"] = "UTC+5"` installs the same frozen UTC-5 as
    `"EST5"` -- the process reads the sign the POSIX way, whatever language
    wrote the variable -- and `follow` reads a string the pandas way, where
    `UTC+5` is UTC plus five, so the assignment passed (Codex, PR #993 final
    review). Decided by the KEY, which is what settles the sign.
    """
    if key_text is None or key_text not in _POSIX_TZ_KEYS or value is None:
        return None
    text = _const_string(value, env)
    if text is not None and _POSIX_UTC_FIXED_VALUE.fullmatch(text.strip()):
        return text
    return None
# `os.environ.update(...)`, whose argument is a whole mapping rather than a
# key and a value in two positions.
_ENV_UPDATE_CALLS = {"update"}
# The read side of the same idea. `getenv` and `get` are the two spellings
# `os.getenv(...)` and `os.environ.get(...)` present, and both take the value
# that runs when the variable is absent as their second argument.
_ENV_GETTER_CALLS = {"getenv", "get"}
# DB-API statement executors. Their FIRST argument is the query and the rest
# are bound parameters, which is how a timezone value reaches Postgres without
# ever appearing in a string this guard would otherwise read.
_SQL_EXECUTE_CALLS = {"execute", "executemany"}
# A fixed offset does not have to be spelled as a number. `Etc/GMT+5` is a
# real IANA zone frozen at UTC-5 (POSIX inverts the sign), so it stands in for
# Eastern through the winter and is wrong all summer -- exactly what this
# guard rejects, in a spelling that looked like a named zone and so passed
# (Codex, PR #993). Only +4 and +5: the others are not Eastern in any season.
# `EST5`/`EDT4` join the named fixed-offset zones: POSIX reads them as an
# abbreviation plus an offset and NO DST rule, so they are frozen all year.
# The non-Python scan already matched them textually; the Python path only
# knew the `Etc/GMT` spellings, so `tzstr("EST5")` had nothing to compare
# against (Codex, PR #993).
_FIXED_OFFSET_ZONES = ("Etc/GMT+4", "Etc/GMT+5", "Etc/GMT+04", "Etc/GMT+05",
                       "EST5", "EDT4", "EST05", "EDT04")
# IGNORECASE, like the non-Python detector has been since round 9: dateutil
# reads `est5` and `EST5` as the same frozen zone, so lowering the case walked
# past the Python path entirely (Codex, PR #993). Upper-casing the VALUE
# instead would have been the wrong fix -- it breaks `Etc/GMT+5`, which is
# mixed-case by definition, and a test caught that.
_FIXED_OFFSET_STRINGS = re.compile(
    r"^(?:" + _FIXED_OFFSET_TEXT + r"|Etc/GMT\+0?[45])$", re.I)
# The same set PLUS the `UTC-05:00` spellings, for the AST path only.
#
# `_FIXED_OFFSET_TEXT` leaves them out deliberately and the comment above says
# why: in a shell `TZ` value POSIX inverts the sign, so `UTC-05:00` selects
# UTC+5 and is not Eastern in either season -- one string, two opposite
# meanings, decided by a context the TEXT scan cannot see.
#
# The AST path CAN see it. Reaching `follow` means the string is already
# established as an argument to a timezone constructor or a `tz=` keyword,
# where `pd.Timestamp.now(tz="UTC-05:00")` means UTC minus five and nothing
# else (Codex, PR #993). The ambiguity is resolved by the context rather than
# guessed at, which is the same move `EST`/`EDT` already get on this path.
_FIXED_OFFSET_STRINGS_PY = re.compile(
    r"^(?:" + _FIXED_OFFSET_TEXT + r"|Etc/GMT\+0?[45]|UTC\s*-\s*0?[45]:?00)$",
    re.I)

# Matched with no context, like the unambiguous legacy names and for the same
# reason: `Etc/GMT+5` means one thing.
# `_LB` here too. `NONPY_UNAMBIGUOUS` got a left boundary last round and this
# sibling did not, so `IMAGE_TAG=latest5` and `echo LATEST5` matched the `EST5`
# alternative and failed the offset guard on text with no timezone in it
# (Codex, PR #993).
# The POSIX forms come from `_POSIX_EASTERN_FIXED` rather than the literal
# list, and `:` joins the lookahead: as literals, `EST5` claimed the prefix of
# `EST5:30`, which is UTC-5:30 and not Eastern in either season -- the same
# near-miss-truncated-into-a-violation shape as `-05:00:30`, found by this
# fix's own control (Codex, PR #993 final review). `EST5:00` is consumed whole
# and still matches.
NONPY_FIXED_ZONE = re.compile(
    _LB + r"""['"]?""" + _LB
    + r"""(?:""" + "|".join(re.escape(z) for z in _FIXED_OFFSET_ZONES
                            if z.startswith("Etc/"))
    + r"|" + _POSIX_EASTERN_FIXED
    + r""")['"]?(?![A-Za-z0-9_/:-])""", re.I
)


def _call_name(node: ast.Call) -> str:
    fn = node.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return ""


def _resolve_callable(name: str, env, seen=None):
    """Follow `NAME = <constructor>` chains to the constructor and its receiver.

    Returns `(name, receiver)`, because resolving the NAME alone was half a
    fix: `make_zone = pytz.timezone` reduces to the generic `timezone`, and
    provenance was then read off the original bare `make_zone(...)` call whose
    receiver is empty, so the name resolved and the context did not (Codex,
    PR #993).

    Cycle detection, not a hop cap. An earlier round replaced a four-hop cap
    in `follow()` with exactly this and recorded why: an alias chain has no
    natural length, and what it cannot do is revisit a name. This function
    then shipped with `depth > 4` in the same file, which is the same defect
    reintroduced one function along (Codex, PR #993).
    """
    seen = seen or set()
    if name in seen:
        return name, ""
    seen = seen | {name}
    # The IMPORT alias map is applied at EVERY hop, not only to the name the
    # call site wrote. `from zoneinfo import ZoneInfo as Z` then
    # `make_zone = Z` composes the two ordinary alias forms, and resolving
    # `make_zone` landed on the unrecognised `Z` because the alias map was
    # consulted once, before the recursion (Codex, PR #993).
    aliased = env.aliases.get(name, name)
    if aliased != name:
        if aliased in seen:
            return aliased, ""
        seen = seen | {aliased}
        name = aliased
    bound = env.bindings.get(name)
    if isinstance(bound, ast.Name):
        return _resolve_callable(bound.id, env, seen)
    if isinstance(bound, ast.Attribute):
        # The receiver is the LAST attribute before the constructor, exactly
        # as `_call_receiver` reads a direct call: `make = zoneinfo.ZoneInfo
        # .no_cache` is made on `ZoneInfo`. Reading only a bare Name left it
        # with no receiver and so no provenance, and `make("EST")` was
        # ignored while `zoneinfo.ZoneInfo.no_cache("EST")` was found
        # (Codex, PR #993 final review).
        inner = bound.value
        if isinstance(inner, ast.Name):
            receiver = inner.id
        elif isinstance(inner, ast.Attribute):
            receiver = inner.attr
        else:
            receiver = ""
        return bound.attr, receiver
    return name, ""


def _resolve_binding(node, env, seen=None):
    """Follow a NAME or ATTRIBUTE to the node it was bound to.

    Three separate branches each required their subject to be written inline
    -- the SQL query text, a `tzinfos` mapping, an offset constructor's
    argument -- while `env.bindings` already held the value under a name.
    Naming a constant once is the ordinary reason a constant gets a name, so
    each of them missed the form people actually write (Codex, PR #993).

    Returns the node unchanged when it is not an indirection or nothing is
    bound, so a caller can always use the result. Cycle detection, matching
    the other resolvers in this file.
    """
    seen = seen or set()
    while isinstance(node, (ast.Name, ast.Attribute)):
        if isinstance(node, ast.Name):
            key = node.id
            target = env.bindings.get(key)
        else:
            inner = node.value
            key = f"{inner.id}.{node.attr}" if isinstance(inner, ast.Name) else None
            target = (env.attrs.get(inner.id, {}).get(node.attr)
                      if isinstance(inner, ast.Name) else None)
        if key is None or key in seen or target is None:
            return node
        seen = seen | {key}
        node = target
    return node


def _unpack_arguments(node: ast.Call, env):
    """(positional, keyword) with statically known `*` and `**` flattened.

    `pytz.FixedOffset(*[-300])` and `FixedOffset(**{"offset": -300})` are
    valid UTC-5 constructors, and the numeric branch handed the `Starred`
    wrapper or the whole dict to `_const_number`, which reports None for
    both. The generic descent added one round earlier cannot rescue them
    either: by the time it sees `-300` it has lost the constructor that gives
    the number its unit (Codex, PR #993).

    Only literal containers are flattened. A `*args` forwarded from a
    parameter stays as it was and is simply not decidable here.
    """
    positional = []
    for arg in node.args:
        target = arg
        if isinstance(arg, ast.Starred):
            target = _resolve_binding(arg.value, env)
            if isinstance(target, (ast.Tuple, ast.List, ast.Set)):
                positional.extend(target.elts)
                continue
            continue                      # not statically known
        positional.append(target)
    keywords = []
    for kw in node.keywords:
        if kw.arg is not None:
            keywords.append((kw.arg, kw.value))
            continue
        mapping = _resolve_binding(kw.value, env)
        if not isinstance(mapping, ast.Dict):
            continue
        for k, v in zip(mapping.keys, mapping.values):
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                keywords.append((k.value, v))
    return positional, keywords


def _resolve_receiver(name: str, env, seen=None) -> str:
    """Follow `p = pytz` so a receiver aliased by ASSIGNMENT names its module.

    `import pytz as p` is an IMPORT alias and `env.aliases` already records it.
    `import pytz; p = pytz` is an assignment, which lands in `env.bindings`,
    and the provenance check consulted only the alias map -- so `p.timezone(...)`
    resolved its receiver to the bare name `p`, `specific` stayed false, and
    the ambiguous `EST` argument was ignored (Codex, PR #993). The callable
    half of this had already been fixed; the receiver half had not.

    Cycle detection rather than a hop cap, matching `_resolve_callable` and
    `follow`: an alias chain has no natural length, and what it cannot do is
    revisit a name.
    """
    seen = seen or set()
    while name and name not in seen:
        seen = seen | {name}
        bound = env.bindings.get(name)
        if isinstance(bound, ast.Name):
            name = bound.id
        elif isinstance(bound, ast.Attribute):
            name = bound.attr
        else:
            break
    return name


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


_CONST_BINOPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
                 ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b}


def _const_number(node: ast.AST, env=None, seen=None):
    """The value of a numeric constant expression, or None.

    Arithmetic is folded, because `-5 * 60` is how people write five hours in
    minutes: `FixedOffset(-5 * 60)`, `tzoffset(None, -5 * 60 * 60)` and
    `timedelta(minutes=-5 * 60)` are all fixed UTC-5 zones, and a check that
    accepted only a literal or a unary minus rejected the `BinOp` before any
    of the three offset checks could evaluate it (Codex, PR #993).

    Only the four operators above, and only over operands that are themselves
    constant, so nothing here executes or guesses: a non-constant operand
    still returns None and leaves the expression undecidable, which is the
    existing contract.

    With an `env`, a NAME is followed to the node it was bound to. Folding
    inline arithmetic was half the fix: `OFFSET = -5 * 60` on one line and
    `pytz.FixedOffset(OFFSET)` on the next is the ordinary way to name a
    constant once, and the constructor then received an `ast.Name` that no
    amount of folding could evaluate (Codex, PR #993). Cycle detection rather
    than a hop cap, for the reason `follow` and `_resolve_callable` already
    give: an alias chain has no natural length, and what it cannot do is
    revisit a name.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _const_number(node.operand, env, seen)
        return None if inner is None else -inner
    if isinstance(node, ast.BinOp) and type(node.op) in _CONST_BINOPS:
        left = _const_number(node.left, env, seen)
        right = _const_number(node.right, env, seen)
        if left is None or right is None:
            return None
        try:
            return _CONST_BINOPS[type(node.op)](left, right)
        except ZeroDivisionError:
            return None
    if env is not None and isinstance(node, ast.Name):
        seen = seen or set()
        if node.id in seen:
            return None
        bound = env.bindings.get(node.id)
        if bound is not None:
            return _const_number(bound, env, seen | {node.id})
    return None


def _const_string(node: ast.AST, env=None, seen=None, consumed=None):
    """The value of a constant string expression, or None.

    Concatenation is folded, for the same reason `_const_number` folds
    arithmetic: `"E" + "ST"` and `"US/" + "Eastern"` are the forbidden values
    written in two pieces, and every matcher here reads one `ast.Constant`
    (Codex, PR #993). Only `+`, and only over operands that are themselves
    constant strings, so nothing executes or guesses.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        if consumed is not None:
            consumed.append(node)
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _const_string(node.left, env, seen, consumed)
        right = _const_string(node.right, env, seen, consumed)
        if left is None or right is None:
            return None
        return left + right
    # `f"{'EST'}"` and `f"US/{'Eastern'}"` are `ast.JoinedStr`, so the fold
    # above saw no `Constant` and no `BinOp` and gave up, while the inner
    # fragment is ignored outside its call context (Codex, PR #993). Every
    # part has to be statically known -- a `FormattedValue` wrapping anything
    # but a constant expression makes the whole thing undecidable, which is
    # the same contract the numeric fold keeps.
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.FormattedValue):
                if value.format_spec is not None or value.conversion not in (-1, 115):
                    return None
                inner = _const_string(value.value, env, seen, consumed)
                if inner is None:
                    number = _const_number(value.value, env)
                    if number is None:
                        return None
                    inner = f"{number:g}"
                parts.append(inner)
                continue
            piece = _const_string(value, env, seen, consumed)
            if piece is None:
                return None
            parts.append(piece)
        return "".join(parts)
    if env is not None and isinstance(node, ast.Name):
        seen = seen or set()
        if node.id in seen:
            return None
        bound = env.bindings.get(node.id)
        if bound is not None:
            return _const_string(bound, env, seen | {node.id}, consumed)
    return None


def _is_eastern_fixed_timedelta(node: ast.AST, env=None) -> bool:
    """A constant `timedelta(...)` totalling -4h or -5h, however it is spelled.

    Checking only `hours=` missed `timedelta(seconds=-18000)` and the
    positional `timedelta(0, -18000)`, which are the same frozen zone in a
    different spelling (Codex, PR #993) -- the fourth time on this file that a
    check knew one way of writing the thing it forbids. The whole constant is
    evaluated now, so any combination of units that lands on the offset counts,
    and a `timedelta` with a non-constant argument is simply not decidable
    here and is left alone rather than guessed at.
    """
    total = _timedelta_seconds(node, env if env is not None else _EMPTY_ENV)
    if total is None:
        return False
    # Rounded, but only where rounding is honest: `timedelta` scales by
    # 1e-6 for microseconds, so an exact comparison would lose a legitimate
    # spelling to floating-point error. A total that is not within a
    # microsecond of a whole second is not one of these offsets and must not
    # be truncated into one (Codex, PR #993).
    if abs(total - round(total)) > 1e-6:
        return False
    return int(round(total)) in _EASTERN_OFFSET_SECONDS


def _timedelta_seconds(node: ast.AST, env, seen=None):
    """The constant duration `node` evaluates to, in seconds, or None.

    A `timedelta(...)` call with statically known arguments; a negation of
    one -- `timezone(-timedelta(hours=5))` is the same frozen zone written
    with the sign outside the call, and it once read as a non-constant
    argument (Codex, PR #993); a NAME bound to one, through the environment
    like every other named constant here; and a SUM or DIFFERENCE of any of
    those. `timezone(timedelta(hours=-6) + timedelta(hours=1))` is UTC-5, and
    the outer `BinOp` was rejected before either operand was totalled, so
    neither inner call matched an Eastern offset on its own and the frozen
    zone passed (Codex, PR #993 final review). Python does this arithmetic at
    import; this does the same arithmetic on the same constants, and gives up
    on anything it cannot see rather than guessing.
    """
    seen = seen or set()
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        inner = _timedelta_seconds(node.operand, env, seen)
        if inner is None:
            return None
        return -inner if isinstance(node.op, ast.USub) else inner
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
        left = _timedelta_seconds(node.left, env, seen)
        right = _timedelta_seconds(node.right, env, seen)
        if left is None or right is None:
            return None
        return left + right if isinstance(node.op, ast.Add) else left - right
    # A timedelta scaled by a constant is still a constant duration:
    # `timedelta(hours=-10) / 2` and `timedelta(hours=-1) * 5` are UTC-5, and
    # reading only add/sub let the outer operation escape (Codex, PR #993
    # final review). Exactly one side of a `*` is the duration and the other a
    # number; a `/` divides the duration on the left by a nonzero number.
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        for a, b in ((node.left, node.right), (node.right, node.left)):
            secs = _timedelta_seconds(a, env, seen)
            factor = _const_number(b, env)
            if secs is not None and factor is not None:
                return secs * factor
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.FloorDiv)):
        secs = _timedelta_seconds(node.left, env, seen)
        divisor = _const_number(node.right, env)
        if secs is None or not divisor:
            return None
        return secs // divisor if isinstance(node.op, ast.FloorDiv) else secs / divisor
    if isinstance(node, ast.Name):
        if node.id in seen:
            return None
        bound = env.bindings.get(node.id)
        if bound is None:
            return None
        return _timedelta_seconds(bound, env, seen | {node.id})
    if not isinstance(node, ast.Call):
        return None
    # Resolved through the alias map, not by literal name. `from datetime
    # import timedelta as TD` made `timezone(TD(hours=-5))` walk past the
    # offset check while the environment already recorded the alias -- the
    # same provenance gap already closed for ZoneInfo and timezone
    # (Codex, PR #993).
    called = _call_name(node)
    # Import alias, then assignment alias. Round 13 taught this check about
    # `from datetime import timedelta as TD` and round 14 added the callable
    # resolver, but this call site was never pointed at it, so `TD = timedelta`
    # still walked past (Codex, PR #993).
    if called != "timedelta" and env.aliases.get(called) != "timedelta":
        if _resolve_callable(called, env)[0] != "timedelta":
            return None
    total = 0.0
    # `env`, so a unit named once resolves: `HOURS = -5` then
    # `timedelta(hours=HOURS)` is the same frozen zone as the inline spelling.
    for arg, (_, scale) in zip(node.args, _TIMEDELTA_UNITS):
        v = _const_number(arg, env)
        if v is None:
            return None
        total += v * scale
    units = dict(_TIMEDELTA_UNITS)
    for kw in node.keywords:
        if kw.arg not in units:
            return None          # **kwargs, or a unit we do not model
        v = _const_number(kw.value, env)
        if v is None:
            return None
        total += v * units[kw.arg]
    return total


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


def _static_truth(test: ast.AST):
    """True or False when `test` is a constant Python can decide, else None."""
    if isinstance(test, ast.Constant):
        return bool(test.value)
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = _static_truth(test.operand)
        return None if inner is None else not inner
    return None


def _reachable_scope_nodes(scope: ast.AST):
    """`_scope_nodes`, minus the branches Python can never take.

    `if False:` and the `else` of `if True:` never run, and neither does the
    body of `while False:`. A call inside one is not an invocation and an
    assignment inside one binds nothing: `if False: reset()` was read as
    running the global writer, which suppressed the exported fixed zone the
    dormant helper could never replace (Codex, PR #993 final review). A test
    that is not a constant is not decided, and both branches are kept.
    """
    stack = list(ast.iter_child_nodes(scope))[::-1]
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, _SCOPES):
            continue
        children = list(ast.iter_child_nodes(node))
        if isinstance(node, (ast.If, ast.While)):
            truth = _static_truth(node.test)
            if truth is False:
                children = [node.test] + list(node.orelse)
            elif truth is True and isinstance(node, ast.If):
                children = [node.test] + list(node.body)
        stack.extend(children[::-1])


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


def _bound_names(scope: ast.AST, nodes=None) -> set[str]:
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
    for node in (nodes if nodes is not None else _scope_nodes(scope)):
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


def _replaces_the_module_binding(tree: ast.AST, name: str, assignment=None) -> bool:
    """True when a nested scope REPLACES the module's own value for `name`.

    Only `global NAME` plus an assignment does that. An ordinary local, a
    parameter or a comprehension target of the same name shadows it inside one
    scope and leaves what an importer reads off the module exactly as written.

    The first version of this asked whether any inner scope bound the name at
    all, which suppressed a real exported setting behind an unrelated helper
    that happened to use the same variable name (Codex, PR #993). That was too
    broad in the direction that hides findings, which is the worse direction.

    And only when that scope RUNS at import. A class body does; a function
    body does not until something calls it, so a module exporting
    `TIME_ZONE = "EST"` beside an uncalled `def reset(): global TIME_ZONE;
    TIME_ZONE = "UTC"` hands every importer the frozen zone -- and this check
    suppressed the finding because the helper *could* replace it (Codex,
    PR #993 final review). A function counts when a statement at module level
    invokes it by name -- or invokes a function it is nested in -- after the
    assignment in question; a method is never invoked that way, and a call
    that runs BEFORE the assignment is overwritten by it.
    """
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    after = assignment.lineno if assignment is not None else -1
    # Reachable statements only: `if False: reset()` invokes nothing (Codex,
    # PR #993 final review).
    invoked = {n.func.id for n in _reachable_scope_nodes(tree)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.lineno > after}
    for node in ast.walk(tree):
        if node is tree or not isinstance(node, _SCOPES):
            continue
        declared = {n for st in _scope_nodes(node)
                    if isinstance(st, ast.Global) for n in st.names}
        if name not in declared or name not in _bound_names(node):
            continue
        if isinstance(node, ast.ClassDef):
            return True         # a class body runs when the class is defined
        if _function_runs(node, tree, parents, invoked):
            return True
    return False


def _function_runs(fn, tree, parents, module_invoked, seen=frozenset()) -> bool:
    """Does `fn`'s body run at import, established from the inside out?

    Invoked by name at module level; or invoked by name inside the body of a
    function that itself runs. An invoked `init()` that merely DEFINES an
    uncalled `inner()` runs nothing of inner's, and the earlier walk stopped
    at the first invoked ancestor and said otherwise (Codex, PR #993 final
    review). A method is never invoked by name at import.
    """
    if (not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
            or id(fn) in seen):
        return False
    enclosing = parents.get(id(fn))
    while (enclosing is not None and enclosing is not tree
           and not isinstance(enclosing, _SCOPES)):
        enclosing = parents.get(id(enclosing))
    if enclosing is None or enclosing is tree:
        return fn.name in module_invoked
    if isinstance(enclosing, ast.ClassDef):
        return False
    called_inside = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == fn.name
        for n in _reachable_scope_nodes(enclosing))
    return called_inside and _function_runs(enclosing, tree, parents,
                                            module_invoked, seen | {id(fn)})


def _local_aliases(scope: ast.AST, nodes=None) -> dict[str, str]:
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
    for node in (nodes if nodes is not None else _scope_nodes(scope)):
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


def _local_modules(scope: ast.AST, nodes=None) -> dict[str, str]:
    """`local name -> module it was imported from`, for `from X import Y`.

    Separate from `_local_aliases`, which answers "what was this renamed
    from". This answers "where did it come from", and only the second one can
    tell that the `timezone` in `from pytz import timezone` is pytz's.

    Added because the generic-name gate I introduced last round turned a real
    `timezone("EST")` into a MISS: `_call_receiver` is empty for a bare call,
    so a directly imported constructor had no provenance and was treated as
    an unknown method (Codex, PR #993). Fixing a false positive created a
    false negative, which is the trade this file spends most of its comments
    trying not to make.

    Names imported from two different modules in one scope are dropped, for
    the reason `_local_aliases` gives: which import is in effect at a line is
    a flow question, and this guard does not answer flow questions.
    """
    seen: dict[str, str] = {}
    conflicted: set[str] = set()
    for node in (nodes if nodes is not None else _scope_nodes(scope)):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        tail = node.module.rsplit(".", 1)[-1]
        for a in node.names:
            local = a.asname or a.name
            if seen.setdefault(local, tail) != tail:
                conflicted.add(local)
    return {k: v for k, v in seen.items() if k not in conflicted}


def _local_attrs(scope: ast.AST, nodes=None) -> dict[str, dict[str, ast.AST]]:
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
    # Two `class Settings` in ONE scope are still two classes. Merging their
    # bodies by name made the later one overwrite the earlier, so a call
    # between them resolved to the wrong body -- a miss in one order and a
    # false finding in the reverse, which is the same pair the cross-scope fix
    # closed and this one did not (Codex, PR #993). Which definition is in
    # effect at a given line is a flow question, so a conflicted name resolves
    # to nothing, exactly as `_local_aliases` handles two imports of one name.
    seen_classes: dict[str, int] = {}
    for node in (nodes if nodes is not None else _scope_nodes(scope)):
        if isinstance(node, ast.ClassDef):
            seen_classes[node.name] = seen_classes.get(node.name, 0) + 1
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
    for name, count in seen_classes.items():
        if count > 1:
            out.pop(name, None)
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
    modules: dict[str, str]                        # from MODULE import NAME


_EMPTY_ENV = _Env({}, {}, {}, {})

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
        # The same kinds `_collect_bindings` keeps for an assigned local. Only
        # strings were retained, so `def build(offset=timedelta(hours=-5))`
        # left the body unable to resolve `offset` and the frozen zone passed
        # (Codex, PR #993). A default IS a binding; which node kinds count is
        # not a question the two should answer differently.
        # `_const_number` too, matching `_collect_bindings` exactly. Round 16
        # taught the assignment map to keep a resolvable number so an offset
        # constructor could read it, and this map -- whose docstring already
        # claimed to keep "the same kinds" -- was not updated, so
        # `def build(offset=-300): return pytz.FixedOffset(offset)` still
        # resolved to nothing (Codex, PR #993).
        if (_binding_text(default) is not None
                or _is_eastern_fixed_timedelta(default)
                or _const_number(default) is not None
                or isinstance(default, (ast.Name, ast.Attribute))):
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
        # ONE traversal of this scope, shared by every collector below. Each
        # of them materialised `_scope_nodes(scope)` again, and the final
        # descent walked it once more, so a cold `_scan()` spent most of its
        # time re-walking the same trees -- 23.7 s here, 39 s on the
        # reviewer's checkout, in the ordinary suite (Codex, PR #993).
        nodes = list(_scope_nodes(scope))
        shadowed, defaults = _parameter_bindings(scope)
        shadowed |= _bound_names(scope, nodes)

        def survives(m):
            return {k: v for k, v in m.items() if k not in shadowed}

        aliases = survives(inherited.aliases)
        aliases.update(_local_aliases(scope, nodes))

        bindings = survives(inherited.bindings)
        bindings.update(defaults)
        # With the aliases, so `from functools import partial as p` keeps
        # `ET = p(ZoneInfo, "EST")` for `_partial_of` to expand.
        bindings.update(_collect_bindings(nodes, {}, aliases))
        if scope is tree:
            for name, src in globals_.items():
                _keep(bindings, name, src)
        for name, src in nonlocals.get(id(scope), {}).items():
            _keep(bindings, name, src)

        modules = survives(inherited.modules)
        modules.update(_local_modules(scope, nodes))

        attrs = {k: dict(v) for k, v in survives(inherited.attrs).items()}
        for obj, members in _local_attrs(scope, nodes).items():
            attrs.setdefault(obj, {}).update(members)

        env = _Env(bindings, aliases, attrs, modules)
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
        for node in nodes:
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


def _collect_bindings(nodes, out: dict[str, ast.AST], aliases=None):
    """`NAME = "..."` -> (value, node), over the nodes handed in.

    `EASTERN = "US/Eastern"` then `ZoneInfo(EASTERN)` is a routine way to share
    one timezone across a module, and it passes a check that only reads
    constants at the call site because the argument is an `ast.Name` (Codex,
    PR #993). The caller decides which nodes are in scope; this reads them.
    """
    for node in nodes:
        # `for zone in ("EST",): ZoneInfo(zone)` and the comprehension form
        # bind the target to each element, exactly as an assignment would.
        # The scope machinery already marked the target as SHADOWING an
        # inherited name -- correctly -- but never bound it to anything, so
        # the call resolved to nothing while the ambiguous literal stayed
        # ignored outside a call context (Codex, PR #993). Only a statically
        # known literal iterable; anything computed is left unresolved, as
        # everywhere else here.
        if isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            if isinstance(node.iter, (ast.Tuple, ast.List, ast.Set)) \
                    and isinstance(node.target, ast.Name):
                for element in node.iter.elts:
                    _keep(out, node.target.id, element)
            continue
        # `zone = "US/"` then `zone += "Eastern"` builds the legacy name in
        # two statements. `_bound_names` marked the name as written, but the
        # collector skipped every `AugAssign`, so the call resolved to the
        # harmless prefix while each fragment passed on its own (Codex,
        # PR #993 final review). A string `+=` whose prior value and operand
        # are both statically known folds, in source order, to the value the
        # name holds afterwards; the operand may be a constant or a name
        # bound to one. Anything else stays as it was -- unresolved rather
        # than guessed -- and `_keep` decides the precedence as it does for
        # every other binding.
        if isinstance(node, ast.AugAssign):
            if isinstance(node.op, ast.Add) and isinstance(node.target, ast.Name):
                operand = node.value
                if isinstance(operand, ast.Name):
                    operand = out.get(operand.id)
                prior = _binding_text(out.get(node.target.id))
                added = _binding_text(operand)
                if prior is not None and added is not None:
                    _keep(out, node.target.id,
                          ast.copy_location(ast.Constant(prior + added), node))
            continue
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
        #
        # Plus a bare indirection. `LEGACY = "EST"; TZ = LEGACY; ZoneInfo(TZ)`
        # is an ordinary way to name a shared setting once, and dropping a
        # Name or Attribute right-hand side meant `TZ` resolved to nothing --
        # so `follow`'s recursion, which exists precisely to walk chains, had
        # no chain to walk (Codex, PR #993). Whether the chain ends in
        # anything interesting is `follow`'s question, not this one's; the
        # depth cap bounds it either way.
        # Plus a statically resolvable NUMBER. `OFFSET = -5 * 60` then
        # `pytz.FixedOffset(OFFSET)` is a fixed UTC-5 zone written the way a
        # constant usually is -- named once -- and dropping the `BinOp`
        # binding left the constructor holding an unresolvable `ast.Name`
        # (Codex, PR #993). A number alone is never a finding, so this cannot
        # report anything on its own; it only lets the constructor that gives
        # the number a unit evaluate it.
        # Plus a literal CONTAINER. `INFOS = {"EST": -18000}` reused across
        # call sites, `PARAMS = ("EST",)` handed to `execute`, and the list an
        # offset constructor is splatted from are all statically known values
        # that the resolvers added this round need to find under their name
        # (Codex, PR #993). A container is never a finding by itself; only a
        # branch that already has a timezone context looks inside one.
        # Plus a bound OFFSET CONSTRUCTOR call, kept by NAME rather than
        # evaluated here. `_is_eastern_fixed_timedelta(v)` was asked without
        # the environment this collector is still building, so
        # `HOURS = -5; OFFSET = timedelta(hours=HOURS)` evaluated to "not
        # decidable" and the binding was dropped -- while the same call
        # written at the use site resolved fine, because `follow` HAS the
        # environment (Codex, PR #993). Keeping the node and letting `follow`
        # evaluate it is the same division of labour the string bindings
        # already use; a `timedelta(hours=3)` kept this way still resolves to
        # nothing there.
        # Plus a bare `None`. `DST = None; tzrange("XX", -18000, DST)` freezes
        # the range -- a null daylight abbreviation disables DST -- and the
        # binding has to be followable for `_tzrange_is_frozen` to see it
        # (Codex, PR #993 final review). `None` is never a finding on its own.
        if (_binding_text(v) is None
                and _const_string(v) is None
                and not _is_eastern_fixed_timedelta(v)
                and not _is_offset_constructor_call(v)
                and not _is_partial_call(v, aliases=aliases)
                and _const_number(v) is None
                and not (isinstance(v, ast.Constant) and v.value is None)
                and not isinstance(v, (ast.Name, ast.Attribute, ast.Dict,
                                       ast.Tuple, ast.List, ast.Set))):
            continue
        for t in targets:
            if isinstance(t, ast.Name):
                _keep(out, t.id, v)
            # `TZ, fallback = ("EST", "UTC")` binds element-wise, and the
            # scope machinery already marked both names as bound -- to
            # nothing, since only a Name target was recorded (Codex, PR
            # #993). A literal sequence of the same length, no starred
            # target: anything else is not statically known and stays
            # unresolved rather than guessed at.
            elif isinstance(t, (ast.Tuple, ast.List)):
                # Through `_paired`, the same pairing the assignment loop
                # uses, so a single starred target resolves here too and the
                # call site reports it rather than the export check (Codex,
                # PR #993 final review).
                for elt, val in _paired(t, v):
                    if isinstance(elt, ast.Name):
                        _keep(out, elt.id, val)
    return out


def _is_partial_call(node: ast.AST, env=None, aliases=None) -> bool:
    """`functools.partial(f, ...)` / `partial(f, ...)`, kept for `follow`.

    `ET = functools.partial(ZoneInfo, "EST")` then `ET()` constructs the
    fixed zone, and dropping the binding meant `_resolve_callable` had
    nothing to follow (Codex, PR #993 final review).

    With an environment, the name must resolve to `functools`: through a
    `from functools import partial` (aliased or not), or through the
    `functools` module (aliased or not). A project's own `partial` that
    returns a lambda was rebuilt as a real `ZoneInfo("EST")` and failed CI on
    a call that constructs nothing (Codex, PR #993 final review). Without an
    environment -- the collector, which is still building one -- the name
    alone decides whether the binding is worth keeping; the use decides the
    rest.
    """
    if not (isinstance(node, ast.Call) and node.args):
        return False
    fn = node.func
    if env is None:
        written = _call_name(node)
        return (aliases or {}).get(written, written) == "partial"
    if isinstance(fn, ast.Name):
        return (env.aliases.get(fn.id, fn.id) == "partial"
                and env.modules.get(fn.id) == "functools")
    if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
        owner = env.aliases.get(fn.value.id, fn.value.id)
        return fn.attr == "partial" and owner == "functools"
    return False


def _partial_of(name: str, env):
    """`(callable_name, receiver, bound_args, bound_keywords)` if `name` is a partial."""
    seen: set = set()
    while name not in seen:
        seen.add(name)
        name = env.aliases.get(name, name)
        bound = env.bindings.get(name)
        if isinstance(bound, ast.Name):
            name = bound.id
            continue
        if isinstance(bound, ast.Call) and _is_partial_call(bound, env):
            target = bound.args[0]
            if isinstance(target, ast.Name):
                cname, receiver = _resolve_callable(target.id, env)
            elif isinstance(target, ast.Attribute):
                cname = target.attr
                receiver = target.value.id if isinstance(target.value, ast.Name) else ""
            else:
                return None
            return cname, receiver, list(bound.args[1:]), list(bound.keywords)
        return None
    return None


def _is_offset_constructor_call(node: ast.AST) -> bool:
    """Is this a `timedelta(...)`/`FixedOffset(...)`/`tzoffset(...)` call?

    By written name, deliberately without the environment: this runs inside
    the collector that builds the environment, so it can only ask a question
    that needs none. Whether the call totals an Eastern offset is `follow`'s
    question, asked later with the environment in hand.
    """
    while isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        node = node.operand
    return (isinstance(node, ast.Call)
            and _call_name(node) in ({"timedelta"} | _FIXED_OFFSET_CALLS
                                     | _FIXED_OFFSET_SECOND_CALLS))


def _embedded_sql_hit(text: str):
    """`(is_offset, shown)` for the first bad zone in a SQL statement's text.

    The one list of embedded-SQL matchers, so the constant scan and the
    folded-query branch of `execute(...)` cannot drift apart: `ZONE = "EST"`
    then `cur.execute(f"SET TIME ZONE {ZONE}")` folds to a statement the
    constant scan would have reported had it been written inline, and it is
    reported by the same rule (Codex, PR #993 final review).
    """
    for pattern, is_offset in ((NONPY_UNAMBIGUOUS, False),
                               (NONPY_AMBIGUOUS, False),
                               (NONPY_FIXED_ZONE, True),
                               (NONPY_FIXED_OFFSET, True),
                               (NONPY_SQL_NUMERIC_OFFSET, True),
                               (NONPY_SQL_INTERVAL_OFFSET, True)):
        m = pattern.search(text)
        if m:
            return is_offset, " ".join(m.group(0).split())[:80]
    return None


def _tzrange_is_frozen(flat_args, flat_kwargs, env) -> bool:
    """Does this `tzrange(...)` keep one offset all year?

    dateutil's signature is `(stdabbr, stdoffset, dstabbr, dstoffset, ...)`.
    No daylight abbreviation means no daylight time. With one, the daylight
    offset defaults to the standard offset plus an hour, so only an explicit
    daylight offset EQUAL to the standard one is frozen; anything not
    statically known is not decided.
    """
    kw = dict(flat_kwargs)
    dstabbr = flat_args[2] if len(flat_args) > 2 else kw.get("dstabbr")
    # `DST = None; tzrange("X", -18000, DST)` freezes the zone: a null daylight
    # abbreviation disables DST. The bound name resolves to the same `None` as
    # the inline constant, and reading only the inline form treated the range
    # as daylight-enabled (Codex, PR #993 final review).
    if dstabbr is not None:
        dstabbr = _resolve_binding(dstabbr, env)
    if dstabbr is None or (isinstance(dstabbr, ast.Constant)
                           and dstabbr.value is None):
        return True
    stdoffset = flat_args[1] if len(flat_args) > 1 else kw.get("stdoffset")
    dstoffset = flat_args[3] if len(flat_args) > 3 else kw.get("dstoffset")
    if stdoffset is None or dstoffset is None:
        return False
    std, dst = _const_number(stdoffset, env), _const_number(dstoffset, env)
    return std is not None and dst is not None and std == dst


def _destructured(targets, value: ast.AST):
    """`(target, value)` pairs, descending through tuple and list unpacking.

    `os.environ["TZ"], other = "EST", value` installs the frozen zone exactly
    as the one-target form does, but the assignment loop examined each
    top-level target only: the tuple is neither a `Subscript` nor an
    `Attribute`, so the timezone target inside it was never paired with its
    value, and the ambiguous literal is ignored everywhere else (Codex, PR #993
    final review). Paired positionally, recursively, when both sides are
    literal sequences; one starred target takes the head and tail around it,
    as Python does. Anything else -- a name bound to a tuple, a length
    mismatch -- is not statically known and is handed back whole, where the
    existing target checks find nothing to read.
    """
    for tgt in targets:
        yield from _paired(tgt, value)


def _paired(tgt: ast.AST, value: ast.AST):
    seq = (ast.Tuple, ast.List)
    if not (isinstance(tgt, seq) and isinstance(value, seq)):
        yield tgt, value
        return
    if any(isinstance(v, ast.Starred) for v in value.elts):
        yield tgt, value
        return
    stars = [i for i, t in enumerate(tgt.elts) if isinstance(t, ast.Starred)]
    if not stars and len(tgt.elts) == len(value.elts):
        for t, v in zip(tgt.elts, value.elts):
            yield from _paired(t, v)
        return
    if len(stars) == 1 and len(value.elts) >= len(tgt.elts) - 1:
        head, tail = tgt.elts[:stars[0]], tgt.elts[stars[0] + 1:]
        for t, v in zip(head, value.elts[:len(head)]):
            yield from _paired(t, v)
        for t, v in zip(tail, value.elts[len(value.elts) - len(tail):]):
            yield from _paired(t, v)
        return
    yield tgt, value


# Calls whose arguments are OUTPUT rather than configuration -- the Python
# side of `_SHELL_OUTPUT_CMD`. A method name alone, whatever the receiver:
# `logger.info`, `log.warning`, `logging.error`, `warnings.warn`, `click.echo`.
_DIAGNOSTIC_CALLS = frozenset({"print", "pprint"})
_DIAGNOSTIC_METHODS = frozenset({"debug", "info", "warning", "warn", "error",
                                 "critical", "exception", "log", "fatal",
                                 "echo", "secho"})


def _is_diagnostic_argument(node: ast.AST, parents: dict) -> bool:
    """Is `node` a direct argument of a print or logging call?

    `logger.info("SET TIME ZONE 'EST' was rejected")` carries the statement
    shape and reaches no executor, and it failed CI on a line that configures
    nothing -- the same false positive the shell path already blanks for
    `echo` (Codex, PR #993 final review). Direct means through an f-string or
    a concatenation only: the same text bound to a name, or nested inside
    `execute(...)` inside the log call, is still read.
    """
    child, parent = node, parents.get(id(node))
    while isinstance(parent, (ast.JoinedStr, ast.FormattedValue, ast.BinOp)):
        child, parent = parent, parents.get(id(parent))
    if not isinstance(parent, ast.Call) or child is parent.func:
        return False
    f = parent.func
    if isinstance(f, ast.Name):
        return f.id in _DIAGNOSTIC_CALLS
    return isinstance(f, ast.Attribute) and f.attr in _DIAGNOSTIC_METHODS


def _python_hits(path: pathlib.Path, text: str):
    """(legacy-name hits, fixed-offset hits) for one Python file.

    Returns None when the text does not parse. It used to return two empty
    lists, which read as "scanned, clean" -- so a tracked `.py` that did not
    parse passed both guards BY not parsing. That is a silent fallback in this
    file's own terms: the notebook path has always handed an unparseable cell
    to the regex pass rather than dropping it, and the `.py` path was the one
    that did not. `_scan` now routes an unparseable file the same way, so a
    fixed offset in it is caught by the only means left. Nothing is
    fabricated: the text IS read, by the weaker reader.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None

    legacy, offsets = [], []
    rel = path.relative_to(REPO)
    envs = _scoped_envs(tree)
    # Who contains what, for the one check that has to look UP the tree.
    parents: dict[int, ast.AST] = {}
    for _parent in ast.walk(tree):
        for _child in ast.iter_child_nodes(_parent):
            parents[id(_child)] = _parent
    # Statement ids at module scope, and every name this module ever reads --
    # both for the configuration-export check below.
    # Every statement in the module's LEXICAL scope, not only `tree.body`: a
    # setting under a module-level `if`, `try`, loop or `with` still becomes
    # a module attribute, and asking only whether it sat directly in the body
    # exempted `if True: TIME_ZONE = "EST"` (Codex, PR #993 final review).
    # Reachable ones only, so a dead branch binds nothing.
    _module_level = {id(n) for n in _reachable_scope_nodes(tree)
                     if isinstance(n, ast.stmt)}
    # A class body is a namespace read from OUTSIDE, as `Config.TIME_ZONE`,
    # exactly as a module's is read as `settings.TIME_ZONE`. Asking only
    # whether an assignment sits in `tree.body` exempted the class-based
    # settings object -- the ordinary Django/Flask shape -- while a function
    # local, which nobody reads from outside, correctly stayed exempt (Codex,
    # PR #993). Classes reached through classes only: a class defined inside
    # a function is that function's local.
    stack = [tree]
    while stack:
        scope = stack.pop()
        for stmt in _reachable_scope_nodes(scope):
            if isinstance(stmt, ast.ClassDef):
                _module_level.update(id(n) for n in _reachable_scope_nodes(stmt)
                                     if isinstance(n, ast.stmt))
                stack.append(stmt)
    # Value nodes this pass has actually REPORTED, and the module-level
    # settings assignments whose verdict has to wait for that answer.
    reported_values: set[int] = set()
    settings_exports: list = []

    def note(bucket, node, what):
        bucket.append(f"{rel}:{getattr(node, 'lineno', 0)}: {what}")

    reported: set[int] = set()

    def follow(bucket_legacy, bucket_offsets, node, arg, env, where,
               ambiguous_ok=True, depth=0, seen=None, utc_prefixed_ok=False):
        """Report `arg` when it is, or resolves to, a legacy zone or offset.

        `ambiguous_ok=False` drops the bare `EST`/`EDT` tokens, for a call
        whose name alone does not establish a timezone context.

        `utc_prefixed_ok=True` additionally accepts the `UTC-05:00` spelling,
        and is set ONLY for the arguments of a recognised timezone call. The
        sign in that string means opposite things in the two places it turns
        up: `pd.Timestamp.now(tz="UTC-05:00")` is UTC minus five, while POSIX
        reads `TZ=UTC-05:00` as UTC PLUS five, which is not Eastern in either
        season (Codex, PR #993, and the round-9 comment on
        `_FIXED_OFFSET_TEXT` that made this file refuse the spelling in the
        first place). A library argument is the one context that settles it,
        so it is the only one that opts in -- an env subscript, a config dict
        key and a bound SQL parameter all keep the narrower pattern.
        """
        if depth == 0:
            # Only the argument as written is marked reported. A value reached
            # THROUGH a name lives at its own assignment, where the standalone
            # scan should still see it.
            reported.add(id(arg))
        legacy_here = ALL_LEGACY if ambiguous_ok else UNAMBIGUOUS_LEGACY
        # Case-folded, because `pytz.timezone("est")` builds the same frozen
        # zone as `pytz.timezone("EST")` and an exact tuple test reported only
        # the second (Codex, PR #993). Safe HERE and not at the bare-constant
        # scan: `follow` is only ever reached through a real timezone context
        # -- a constructor argument, a `tz=` keyword, a timezone-named key --
        # so a lowercase `est` in ordinary prose or a stop-word list is
        # untouched, which is the distinction the non-Python patterns already
        # make with their IGNORECASE plus a required context.
        # One node, one finding. The settings-export check below runs after
        # the walk and re-follows an assignment a timezone use may already
        # have reported through; without this it would report the same value
        # twice (Codex, PR #993).
        if id(arg) in reported_values:
            return True
        # Folded before any matcher reads it: `ZoneInfo("E" + "ST")` and
        # `ZoneInfo("US/" + "Eastern")` build the forbidden zone, every check
        # below reads a single `ast.Constant`, and the standalone walk sees
        # only harmless fragments. The numeric side has folded arithmetic
        # since round 15 for exactly this reason (Codex, PR #993). The
        # ORIGINAL node stays the one marked reported, so the dedupe and the
        # line number still point at what was written.
        # WITH `env`, and every constant the fold consumed is marked
        # reported. Dropping `env` was how the previous round stopped the
        # module-settings pass double-reporting a value the fold had resolved
        # through a name -- but it also lost `PREFIX = "E"; ZoneInfo(PREFIX +
        # "ST")`, where the binding and the literal are only forbidden
        # together (Codex, PR #993). Both properties hold by marking the
        # LEAVES rather than the expression: the constant at the assignment is
        # exactly the node the settings pass would report next, so recording
        # it here is what makes one finding one finding.
        # Only a COMPOSITE expression is folded here. A bare name or
        # attribute is left to the indirection branch below, which resolves
        # it and labels the finding `EASTERN (= 'US/Eastern')` -- folding it
        # here instead resolved the value correctly and threw the provenance
        # away, which two scoping tests caught. The recursion reaches this
        # fold again at the leaf, so a name bound to a concatenation still
        # works and still names the binding.
        consumed: list = []
        folded = (_const_string(arg, env, None, consumed)
                  if isinstance(arg, (ast.BinOp, ast.JoinedStr)) else None)
        if folded is not None and not isinstance(arg, ast.Constant):
            reported_values.add(id(arg))
            for leaf in consumed:
                reported_values.add(id(leaf))
                reported.add(id(leaf))
            arg = ast.copy_location(ast.Constant(value=folded), arg)
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            folded = {z.lower() for z in legacy_here}
            if arg.value.lower() in folded:
                reported_values.add(id(arg))
                note(bucket_legacy, arg, where(repr(arg.value)))
                return True
        # Case-folded, for the reason the legacy names already are: dateutil
        # reads `est5` and `EST5` as the same frozen zone, and the non-Python
        # detector has been case-insensitive since round 9 while this one was
        # not (Codex, PR #993).
        offset_strings = (_FIXED_OFFSET_STRINGS_PY if utc_prefixed_ok
                          else _FIXED_OFFSET_STRINGS)
        if (isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                and offset_strings.match(arg.value)):
            reported_values.add(id(arg))
            note(bucket_offsets, arg, where(repr(arg.value)))
            return True
        if _is_eastern_fixed_timedelta(arg, env):
            reported_values.add(id(arg))
            note(bucket_offsets, arg, where("timedelta(hours=-4|-5, ...)"))
            return True
        # `ZoneInfo(os.getenv("TZ", "EST"))` -- the fallback is the value that
        # actually runs wherever TZ is unset, which for a container is the
        # ordinary case. `follow` reached the getter call, matched neither a
        # string nor a timezone constructor, and stopped (Codex, PR #993).
        #
        # The KEY is not tested. Reaching here already means a timezone
        # context, so whatever this getter falls back to is being used as a
        # zone regardless of what the variable is called.
        if isinstance(arg, ast.Call) and _call_name(arg) in _ENV_GETTER_CALLS:
            default = next((a for a in arg.args[1:]), None)
            if default is None:
                default = next((k.value for k in arg.keywords
                                if k.arg == "default"), None)
            if default is not None:
                return follow(bucket_legacy, bucket_offsets, node, default, env,
                              lambda shown, n=_call_name(arg):
                                  where(f"{n}(..., {shown})"),
                              ambiguous_ok, depth + 1, seen,
                              utc_prefixed_ok)
        # An indirection -- `Settings.tz`, `settings.tz`, or a plain name --
        # is resolved to the NODE it was bound to and re-dispatched through
        # this same function, so every spelling above is reachable through a
        # name. Resolving to a string instead was what made
        # `OFFSET = timedelta(hours=-5); timezone(OFFSET)` invisible: the
        # binding held no string, so there was nothing to compare
        # (Codex, PR #993).
        # Cycle detection, not a hop count. The cap here was 4, justified in a
        # comment saying a binding could only hold a constant or a constructor
        # call so a chain was short by construction -- and the same commit
        # started retaining `ast.Name` bindings, which made that sentence false
        # as I wrote it. `A="EST"; B=A; ...; F=E; ZoneInfo(F)` then hit the cap
        # and reported nothing (Codex, PR #993). A configuration alias chain has
        # no natural length; what it cannot do is revisit a node, and that is
        # the thing worth bounding.
        if seen is None:
            seen = set()
        if id(arg) not in seen:
            seen = seen | {id(arg)}
            target = label = None
            if (isinstance(arg, ast.Attribute)
                    and isinstance(arg.value, ast.Name)):
                target = env.attrs.get(arg.value.id, {}).get(arg.attr)
                label = f"{arg.value.id}.{arg.attr}"
            elif isinstance(arg, ast.Name):
                target = env.bindings.get(arg.id)
                label = arg.id
            # `ZONES = {"primary": "EST"}; ZoneInfo(ZONES["primary"])` -- the
            # registry is bound (containers have been kept since round 18)
            # and the lookup is static, but this branch resolved only names
            # and attributes, so the finding went with the subscript (Codex,
            # PR #993). A constant key into a bound dict, or a constant index
            # into a bound sequence; anything computed stays unresolved.
            elif (isinstance(arg, ast.Subscript)
                    and isinstance(arg.value, ast.Name)
                    and isinstance(arg.slice, ast.Constant)):
                base = env.bindings.get(arg.value.id)
                idx = arg.slice.value
                if isinstance(base, ast.Dict) and isinstance(idx, str):
                    target = next((v for k, v in zip(base.keys, base.values)
                                   if isinstance(k, ast.Constant)
                                   and k.value == idx), None)
                elif (isinstance(base, (ast.Tuple, ast.List))
                        and isinstance(idx, int) and not isinstance(idx, bool)
                        and -len(base.elts) <= idx < len(base.elts)):
                    target = base.elts[idx]
                label = f"{arg.value.id}[{idx!r}]"
            if target is not None:
                return follow(bucket_legacy, bucket_offsets, node, target, env,
                              lambda shown, l=label: where(f"{l} (= {shown})"),
                              ambiguous_ok, depth + 1, seen,
                              utc_prefixed_ok)

        # A statically present branch is a value this expression can take, so
        # `ZoneInfo("EST" if legacy else "America/New_York")` really can build
        # the frozen zone -- and the standalone scan deliberately ignores the
        # ambiguous literal, so nothing else would have caught it (Codex,
        # PR #993). Both branches are followed; either one reporting is enough.
        # `ZoneInfo(os.getenv("TZ") or "EST")` -- the idiom people actually
        # write for a default. Every operand is a value the expression can
        # take, exactly as with the ternary below, and the standalone scan
        # deliberately ignores a bare ambiguous literal so nothing else would
        # have seen it (Codex, PR #993).
        # `ZoneInfo(TZ := "EST")` builds the frozen zone AND binds it for
        # later use, so the walrus is a value this expression takes just as
        # much as a ternary branch is. `follow` had no case for it, and the
        # standalone scan deliberately ignores a bare ambiguous literal, so
        # nothing saw it (Codex, PR #993).
        if isinstance(arg, ast.NamedExpr):
            return follow(bucket_legacy, bucket_offsets, node, arg.value, env,
                          where, ambiguous_ok, depth + 1, seen,
                          utc_prefixed_ok)
        # A container in a timezone context holds values this call receives.
        # Two live shapes needed it and neither was reachable:
        # `cur.executemany("SET TIME ZONE %s", [("EST",)])`, where the
        # parameter loop unwrapped the outer list and handed `follow` the
        # inner TUPLE, and `ZoneInfo(*["EST"])`, where the loop handed it an
        # `ast.Starred` wrapper (Codex, PR #993). Every element is followed;
        # any one reporting is enough. Safe because `follow` is only reached
        # in an established timezone context -- an ordinary list of strings
        # elsewhere in the file is never handed to it.
        if isinstance(arg, ast.Starred):
            return follow(bucket_legacy, bucket_offsets, node, arg.value, env,
                          where, ambiguous_ok, depth + 1, seen,
                          utc_prefixed_ok)
        if isinstance(arg, (ast.Tuple, ast.List, ast.Set)):
            hit = False
            for element in arg.elts:
                if follow(bucket_legacy, bucket_offsets, node, element, env,
                          where, ambiguous_ok, depth + 1, seen,
                          utc_prefixed_ok):
                    hit = True
            if hit:
                return True
        # `ZoneInfo(**{"key": "EST"})`. The keyword loop below passes a `**`
        # mapping as one `keyword` whose `arg` is None and whose value is the
        # whole dict, so the zone sat one level below anything that looked at
        # it. The VALUES are followed, not the keys: a key here names the
        # parameter, not the zone.
        if isinstance(arg, ast.Dict):
            hit = False
            for element in arg.values:
                if follow(bucket_legacy, bucket_offsets, node, element, env,
                          where, ambiguous_ok, depth + 1, seen,
                          utc_prefixed_ok):
                    hit = True
            if hit:
                return True
        if isinstance(arg, ast.BoolOp):
            hit = False
            for operand in arg.values:
                if follow(bucket_legacy, bucket_offsets, node, operand, env,
                          where, ambiguous_ok, depth + 1, seen,
                          utc_prefixed_ok):
                    hit = True
            if hit:
                return True
        if isinstance(arg, ast.IfExp):
            hit = False
            for branch in (arg.body, arg.orelse):
                hit |= follow(bucket_legacy, bucket_offsets, node, branch, env,
                              where, ambiguous_ok, depth + 1, seen,
                              utc_prefixed_ok)
            return hit
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
            for tgt, value in _destructured(targets, node.value):
                key = tgt.slice if isinstance(tgt, ast.Subscript) else None
                # Through the environment, so `KEY = "TZ"; os.environ[KEY] =
                # "EST"` reads its key the way every other named constant here
                # is read. A literal-only comparison saw an `ast.Name` and
                # walked past the assignment that installs the zone (Codex,
                # PR #993).
                key_text = _const_string(key, env) if key is not None else None
                if key_text is not None and key_text.lower() in _TZ_KEYWORDS:
                    follow(legacy, offsets, node, value, env,
                           lambda shown, k=key_text: f"[{k!r}] = {shown}")
                    posix = _posix_tz_offset(key_text, value, env)
                    if posix is not None:
                        note(offsets, node, f"[{key_text!r}] = {posix!r}")
                # `settings.timezone = "EST"` -- an attribute target binds no
                # NAME either, so the same argument applies to it as to the
                # subscript above, and it was missed for the same reason
                # (Codex, PR #993).
                if (isinstance(tgt, ast.Attribute)
                        and tgt.attr.lower() in _TZ_KEYWORDS):
                    follow(legacy, offsets, node, value, env,
                           lambda shown, a=tgt.attr: f".{a} = {shown}")
                # `TIME_ZONE = "EST"` in a settings module. No constructor is
                # called here because something else consumes the setting --
                # a framework, or another module -- so waiting for a local
                # `ZoneInfo(...)` means never seeing it. The non-Python scan
                # already treats `time_zone=` as a context for exactly this
                # reason; the Python path was the inconsistent one (Codex,
                # PR #993).
                #
                # Reported only when the name is never READ in this module,
                # which is the finding's own condition made precise: "another
                # module consumes the setting". A name this file reads is
                # reported at the read instead, with the constructor that
                # gives it meaning -- so this branch adds the export case
                # without double-reporting the ordinary one.
                #
                # Both bounds were learned by removing them. Applied at every
                # scope and to read names alike, it reported every
                # `tz = "EST"` anywhere, which broke twenty tests in this file
                # -- a fair measure of how ordinary that line is, and of how
                # much noise the unbounded rule would add to a real module.
                if (isinstance(tgt, ast.Name)
                        and tgt.id.lower() in _TZ_KEYWORDS
                        and id(node) in _module_level):
                    settings_exports.append((node, tgt, value, env))

        # `if (TIME_ZONE := "EST"):` at module scope binds the same exported
        # name as an assignment, and only `Assign`/`AnnAssign` were read
        # (Codex, PR #993 final review). The statement the walrus sits in
        # decides whether it is module level.
        if (isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name)
                and node.target.id.lower() in _TZ_KEYWORDS):
            stmt = parents.get(id(node))
            while stmt is not None and not isinstance(stmt, ast.stmt):
                stmt = parents.get(id(stmt))
            if stmt is not None and id(stmt) in _module_level:
                settings_exports.append((stmt, node.target, node.value, env))

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
            # Diagnostic text is not a statement. `logger.info("SET TIME ZONE
            # 'EST' was rejected")` carries the statement shape and reaches no
            # executor, and the shape alone failed CI on a line that configures
            # nothing (Codex, PR #993 final review). Only a DIRECT argument of
            # an output call is exempt; the same text bound to a name, or
            # handed to `execute`, is still read below.
            if _is_diagnostic_argument(node, parents):
                continue
            # Comment-stripped first. This branch exists because Python
            # source carries SQL, and SQL carried in a string carries its
            # comments with it: a migration written as
            # `"-- Old: SET TIME ZONE 'EST'\nSET TIME ZONE 'America/New_York'"`
            # documents the change it makes, and reporting the commented half
            # is a false CI failure on a string whose executed half is
            # correct. The `.sql` files got this a round earlier; the embedded
            # copies did not (Codex, PR #993).
            text = _strip_sql_comments(node.value)
            if _LIBPQ_OPTION.search(node.value):
                # An options string is not SQL: `--timezone=EST` begins with
                # SQL's line-comment token and the stripper would blank the
                # very setting this branch exists to read.
                text = node.value
            # ...and only when the string really is a SQL STATEMENT. This
            # branch exists because Python source carries SQL, and it was
            # feeding EVERY string constant to the non-Python matchers -- so
            # `logger.info("The old setting was US/Eastern; it has been
            # migrated")` and `print("To reproduce, set TZ=EST")` failed the
            # guard, on text that constructs and configures nothing. The
            # shell path already blanks its diagnostics; this is the Python
            # side of the same rule (Codex, PR #993).
            #
            # A zone name reaching a timezone API is caught by the call and
            # constant branches above, which is where it means something; a
            # zone name inside prose is prose.
            # ...or a libpq OPTIONS string. `connect(options="-c
            # timezone=EST")` -- and SQLAlchemy's `connect_args` carrying the
            # same -- installs the session zone before any query runs, and
            # `-c timezone=` is not a statement (Codex, PR #993).
            if not (_SQL_STATEMENT.search(text) or _LIBPQ_OPTION.search(text)):
                continue
            # `NONPY_SQL_NUMERIC_OFFSET` belongs here too. It was applied to
            # standalone `.sql` files and not to the same statement carried in
            # a Python string, so moving `cur.execute("SET TIME ZONE -5")`
            # into the code that runs it walked past the guard (Codex,
            # PR #993). It is safe in this loop for the same reason it is safe
            # in the file scan: it is confined to the SQL statement forms,
            # which is what reaching this branch has just established.
            hit = _embedded_sql_hit(text)
            if hit is not None:
                is_offset, shown = hit
                reported.add(id(node))
                note(offsets if is_offset else legacy, node, f"in string: {shown}")

        # `{"tz": "EST"}` -- a config literal read back at some other site.
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                # `.lower()`, matching the subscript handling above. The
                # conventional spelling for a subprocess environment is
                # `env={"TZ": "EST"}` -- uppercase -- and a case-sensitive
                # membership test walked straight past it while the adjacent
                # `os.environ["TZ"]` form was caught (Codex, PR #993).
                # Through the environment, as the subscript branch already
                # reads its key: `KEY = "TZ"; env={KEY: "EST"}` hands the
                # child process the frozen zone, and a literal-only test
                # walked past it (Codex, PR #993 final review). A `**spread`
                # entry has no key and is skipped.
                key_text = _const_string(k, env) if k is not None else None
                if key_text is not None and key_text.lower() in _TZ_KEYWORDS:
                    follow(legacy, offsets, node, v, env,
                           lambda shown, k=key_text: f"{k!r}: {shown}")
                # `subprocess.run(env={"TZ": "UTC+5"})`: the child reads the
                # POSIX sign, so a `TZ`/`PGTZ` key (exact case) with a POSIX
                # offset is the frozen zone (Codex, PR #993 final review).
                posix = _posix_tz_offset(key_text, v, env)
                if posix is not None:
                    note(offsets, node, f"{{{key_text!r}: {posix!r}}}")

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

        _orig_call = node
        name = env.aliases.get(_call_name(node), _call_name(node))
        # A call through a `partial` is a call to what it wraps, with the
        # bound arguments in front: `ET = functools.partial(ZoneInfo, "EST")`
        # then `ET()` constructs the fixed zone, and every check below --
        # the constructor filter, the provenance lookups, the argument walk --
        # runs on the rebuilt call so it sees `ZoneInfo("EST")`
        # (Codex, PR #993 final review).
        _pf = _partial_of(node.func.id, env) if isinstance(node.func, ast.Name) else None
        if _pf is not None:
            name, _prec, _pargs, _pkw = _pf
            node = ast.copy_location(
                ast.Call(func=ast.Name(id=name, ctx=ast.Load()),
                         args=_pargs + list(node.args),
                         keywords=_pkw + list(node.keywords)),
                _orig_call)
            if _prec:
                node.func = ast.Attribute(value=ast.Name(id=_prec, ctx=ast.Load()),
                                          attr=name, ctx=ast.Load())

        # `os.putenv("TZ", "EST")` and `os.environ.setdefault("TZ", "EST")`
        # install the same process zone as `os.environ["TZ"] = "EST"`, which
        # is handled above -- but here the key and the value are POSITIONAL
        # arguments to a call whose name is not a timezone constructor, so the
        # filter below skipped them before either was looked at (Codex,
        # PR #993). Read before that filter, since the point is that the call
        # name is not the thing that makes this a timezone context.
        if name in _ENV_SETTER_CALLS:
            # Positional OR keyword: `os.environ.setdefault("TZ",
            # default="EST")` is the same call as the two-positional form,
            # and requiring `len(node.args) >= 2` skipped it (Codex, PR
            # #993). `key`/`default` are `MutableMapping.setdefault`'s
            # names; `value` is accepted as well so the spelling in the
            # finding cannot walk past either.
            # Unpacked first, as the offset constructors are: `os.putenv(*("TZ",
            # "EST"))` handed a single `Starred` here as the key, with no
            # value to follow (Codex, PR #993 final review).
            flat_args, flat_kwargs = _unpack_arguments(node, env)
            kws = dict(flat_kwargs)
            key = flat_args[0] if flat_args else kws.get("key")
            value = (flat_args[1] if len(flat_args) >= 2
                     else kws.get("default", kws.get("value")))
            key_text = _const_string(key, env) if key is not None else None
            if (value is not None and key_text is not None
                    and key_text.lower() in _TZ_KEYWORDS):
                follow(legacy, offsets, node, value, env,
                       lambda shown, k=key_text, n=name: f"{n}({k!r}, {shown})")
                posix = _posix_tz_offset(key_text, value, env)
                if posix is not None:
                    note(offsets, node, f"{name}({key_text!r}, {posix!r})")

        # `os.environ.update(...)` takes a mapping OR an iterable of pairs,
        # and both install the process zone. `update` is not a two-positional
        # setter, so it never entered the branch above, and a `("TZ", "EST")`
        # tuple is not an `ast.Dict` so the dict-literal branch missed it too
        # (Codex, PR #993). Keyword form (`update(TZ="EST")`) is already
        # covered by the keyword branch further down.
        if name in _ENV_UPDATE_CALLS:
            # `os.environ.update(TZ="UTC+5")` and `update(**{"TZ": "UTC+5"})`:
            # a keyword pair is a mapping entry too. The generic keyword branch
            # below reads `TZ=` the pandas way (`UTC+5` benign), so the POSIX
            # reading is applied here, scoped to this env-update call and an
            # exact `TZ`/`PGTZ` key (Codex, PR #993 final review).
            _kw_pairs = [(ast.Constant(kw.arg), kw.value)
                         for kw in node.keywords if kw.arg is not None]
            for kw in node.keywords:
                if kw.arg is None:
                    spread = _resolve_binding(kw.value, env)
                    if isinstance(spread, ast.Dict):
                        _kw_pairs.extend(zip(spread.keys, spread.values))
            for k, v in _kw_pairs:
                key_text = _const_string(k, env)
                if key_text is not None and key_text.lower() in _TZ_KEYWORDS:
                    follow(legacy, offsets, node, v, env,
                           lambda shown, kk=key_text, nn=name:
                               f"{nn}({kk}={shown})")
                    posix = _posix_tz_offset(key_text, v, env)
                    if posix is not None:
                        note(offsets, node, f"{name}({key_text}={posix!r})")
            for arg in node.args:
                mapping = _resolve_binding(arg, env)
                pairs = []
                if isinstance(mapping, ast.Dict):
                    pairs = list(zip(mapping.keys, mapping.values))
                elif isinstance(mapping, (ast.Tuple, ast.List, ast.Set)):
                    for element in mapping.elts:
                        element = _resolve_binding(element, env)
                        if (isinstance(element, (ast.Tuple, ast.List))
                                and len(element.elts) == 2):
                            pairs.append((element.elts[0], element.elts[1]))
                for k, v in pairs:
                    # Through the environment, like the dict and subscript
                    # keys: `KEY = "TZ"; os.environ.update([(KEY, "EST")])`
                    # installs the zone and a literal-only test walked past
                    # it (Codex, PR #993 final review).
                    key_text = _const_string(k, env)
                    if key_text is not None and key_text.lower() in _TZ_KEYWORDS:
                        follow(legacy, offsets, node, v, env,
                               lambda shown, kk=key_text, nn=name:
                                   f"{nn}({{{kk!r}: {shown}}})")
                        posix = _posix_tz_offset(key_text, v, env)
                        if posix is not None:
                            note(offsets, node, f"{name}({{{key_text!r}: {posix!r}}})")

        # `make_zone = ZoneInfo; make_zone("EST")`. Round 13 resolved IMPORT
        # aliases, which live in `env.aliases`; an ASSIGNMENT alias lives in
        # `env.bindings` and was never consulted, so the call name failed this
        # filter before its argument was looked at (Codex, PR #993).
        name, resolved_receiver = _resolve_callable(name, env)
        # `cur.execute("SET TIME ZONE %s", ("EST",))`. The statement carries
        # the context and the parameters carry the value, so each half looked
        # innocent on its own and `execute` was not a timezone call at all
        # (Codex, PR #993). When the query text IS a timezone context, its
        # statically known parameters are followed as if they were arguments
        # to a constructor -- which, one layer down, is what they are.
        if name in _SQL_EXECUTE_CALLS and node.args:
            # Through the bindings: `QUERY = "SET TIME ZONE %s"` on one line
            # and `cur.execute(QUERY, ("EST",))` on the next is the ordinary
            # way a statement gets named, and requiring the text inline meant
            # the context and its parameter were never joined
            # (Codex, PR #993).
            query = _resolve_binding(node.args[0], env)
            # FOLDED, not merely resolved: `ZONE = "EST"` then
            # `cur.execute(f"SET TIME ZONE {ZONE}")` is a `JoinedStr` the
            # constant-string evaluator already reads, and requiring an
            # `ast.Constant` here walked past it (Codex, PR #993 final review).
            query_text = _const_string(query, env)
            if query_text is not None and re.search(_TZ_CONTEXT, query_text, re.I):
                if not node.args[1:] and not isinstance(query, ast.Constant):
                    # The zone is IN the folded text, so it is matched the way
                    # an inline statement is -- the same six embedded-SQL
                    # matchers the constant scan runs -- and noted at the
                    # query. `follow` cannot do this: it reads a constant as
                    # a zone VALUE, not as SQL carrying one. (An inline
                    # Constant already takes the constant scan's path and is
                    # left alone here rather than reported twice.)
                    hit = _embedded_sql_hit(_strip_sql_comments(query_text))
                    if hit is not None:
                        is_offset, shown = hit
                        note(offsets if is_offset else legacy, node.args[0],
                             f"{name}(folded: {shown})")
                # Positional bindings AND the `vars=` keyword: psycopg2's
                # `execute(query, vars=None)` and sqlite3's `parameters=` name
                # the same tuple, so a keyword form escaped the positional-only
                # scan (Codex, PR #993 final review).
                binding_params = list(node.args[1:])
                for kw in node.keywords:
                    if kw.arg in ("vars", "parameters", "params", "args"):
                        binding_params.append(kw.value)
                for param in binding_params:
                    param = _resolve_binding(param, env)
                    items = (param.elts
                             if isinstance(param, (ast.Tuple, ast.List))
                             else [param])
                    for item in items:
                        follow(legacy, offsets, node, item, env,
                               lambda shown, n=name: f"{n}(..., {shown})")
        # `dateutil.parser.parse("... EST", tzinfos={"EST": -18000})`.
        # python-dateutil is a declared dependency and this is its documented
        # way to give an abbreviation a meaning -- and the meaning given here
        # is a FIXED offset, so the parsed datetime is frozen at UTC-5 all
        # year. Neither guard saw it: `parse` is not a timezone call, the key
        # is an ambiguous literal the standalone scan ignores on purpose, and
        # the value is a bare number (Codex, PR #993).
        #
        # Handled before the `_TZ_CALLS` filter for the same reason `execute`
        # is: the keyword carries the context, whatever the function is
        # called. The numeric value is read in SECONDS, which is the unit
        # dateutil documents for this mapping.
        for kw in node.keywords:
            if kw.arg != "tzinfos":
                continue
            # `INFOS = {"EST": -18000}` reused across call sites is the usual
            # shape for a mapping like this, and accepting only an inline
            # dict missed it (Codex, PR #993).
            mapping = _resolve_binding(kw.value, env)
            if not isinstance(mapping, ast.Dict):
                continue
            for k, v in zip(mapping.keys, mapping.values):
                seconds = _const_number(v, env)
                # Exact, for the reason the constructor branch above gives.
                if (seconds is not None
                        and seconds in _EASTERN_OFFSET_SECONDS):
                    reported.add(id(v))
                    reported_values.add(id(v))
                    label = (repr(k.value)
                             if isinstance(k, ast.Constant) else "?")
                    note(offsets, v,
                         f"tzinfos={{{label}: {seconds:g}}} seconds")
                    continue
                # Not a fixed Eastern offset, but the VALUE may still be a
                # legacy zone: `tzinfos={"EST": gettz("US/Eastern")}`.
                follow(legacy, offsets, node, v, env,
                       lambda shown: f"tzinfos={{... {shown}}}")
        # `setattr(settings, "timezone", "EST")` is the attribute assignment
        # the branch above already reads, written as a call, and it created
        # no assignment node for that branch to see (Codex, PR #993 final
        # review).
        if name == "setattr" and len(node.args) >= 3:
            attr = _const_string(node.args[1], env)
            if attr is not None and attr.lower() in _TZ_KEYWORDS:
                follow(legacy, offsets, node, node.args[2], env,
                       lambda shown, a=attr: f"setattr(..., {a!r}, {shown})")
            continue
        if name not in _TZ_CALLS:
            continue
        # Whether the CALL is enough of a timezone context to convict a bare
        # `EST`. A specific constructor is; a generic method name is only when
        # its receiver says so. Without this, `translator.localize("EST")` and
        # `cache.now("EDT")` were reported, which is a false CI failure on
        # code that has no timezone in it (Codex, PR #993).
        # The receiver the ALIAS carried, when the call itself has none. A bare
        # `make_zone(...)` has an empty receiver and no import module, so
        # resolving only the name left `specific` false and the ambiguous
        # `EST` ignored (Codex, PR #993).
        receiver = _call_receiver(node) or resolved_receiver
        # Provenance, in either of the two ways it can be written: the
        # RECEIVER for `pytz.timezone(...)`, or the module a bare
        # `timezone(...)` was imported from. Reading only the receiver made
        # `from pytz import timezone` a miss (Codex, PR #993). Looked up by
        # the name AS WRITTEN, since that is what `from X import Y as Z`
        # binds.
        # Looked up under BOTH spellings: the name as written, and the name
        # the alias chain resolves to. `from pytz import timezone` followed by
        # `make_zone = timezone` records the module under `timezone`, while
        # the call site says `make_zone` -- so asking only about the written
        # name left `specific` false and the ambiguous `EST` argument ignored,
        # which is the provenance half of a fix whose name half already
        # landed (Codex, PR #993).
        # The receiver is resolved through the BINDINGS first, so a module
        # aliased by assignment (`p = pytz`) reaches the same answer as one
        # aliased at import (`import pytz as p`), and only then through the
        # import-alias map (Codex, PR #993).
        resolved = _resolve_receiver(receiver, env)
        specific = (name in _TZ_CALLS_SPECIFIC
                    or env.aliases.get(resolved, resolved) in _TZ_RECEIVERS
                    or env.modules.get(_call_name(node), "") in _TZ_RECEIVERS
                    or env.modules.get(name, "") in _TZ_RECEIVERS)

        # `pytz.FixedOffset(-300)` and `dateutil.tz.tzoffset(None, -18000)` --
        # the offset is a plain number, so no string or `timedelta` check
        # could ever see it, and the two constructors disagree about the UNIT.
        if name in _FIXED_OFFSET_CALLS or name in _FIXED_OFFSET_SECOND_CALLS:
            seconds = name in _FIXED_OFFSET_SECOND_CALLS
            # `tzoffset(name, offset)` takes the offset SECOND; `FixedOffset`
            # takes it first. Both also accept it by keyword.
            #
            # Unpacked first, so `FixedOffset(*[-300])` and
            # `FixedOffset(**{"offset": -300})` reach the same candidate the
            # inline spellings do. The generic container descent below cannot
            # stand in for this: it would see a bare `-300` having lost the
            # constructor that says whether that is minutes or seconds
            # (Codex, PR #993).
            flat_args, flat_kwargs = _unpack_arguments(node, env)
            positional = flat_args[1:] if seconds else flat_args
            candidate = next(
                (a for a in positional
                 # `tzrange` names its keyword `stdoffset`; the positional
                 # form was already read and the keyword was not (Codex,
                 # PR #993).
                 + [v for a, v in flat_kwargs if a in ("offset", "stdoffset")]),
                None)
            # Through `env`: the argument is as often a name as a literal,
            # and `_const_number` follows one to the number it holds.
            value = (_const_number(candidate, env)
                     if candidate is not None else None)
            wanted = (_EASTERN_OFFSET_SECONDS if seconds
                      else _EASTERN_OFFSET_MINUTES)
            # `value in wanted`, NOT `int(value) in wanted`. Truncation made
            # `FixedOffset(-300.5)` -- which is UTC-05:00:30, neither Eastern
            # offset -- report as forbidden Eastern time, so a valid
            # non-Eastern zone failed CI (Codex, PR #993). A float that is
            # exactly the integer still compares equal, so the ordinary
            # spellings are unaffected.
            # `tzrange` is frozen only WITHOUT daylight time. After the
            # standard offset it takes `dstabbr` and `dstoffset`, and with
            # them it alternates: `tzrange("X", -18000, "Y", -21600)` is UTC-5
            # in winter and UTC-6 in summer -- neither a frozen UTC-5 nor
            # Eastern -- and reading the standard offset alone reported it
            # (Codex, PR #993 final review). Its abbreviations still go
            # through `follow` below like any other constructor argument.
            if name == "tzrange" and not _tzrange_is_frozen(
                    flat_args, flat_kwargs, env):
                value = None
            if value is not None and value in wanted:
                reported.add(id(candidate))
                note(offsets, node,
                     f"{name}({value:g}) {'seconds' if seconds else 'minutes'}")
                continue
        # Positional and keyword arguments alike.
        for arg in list(node.args) + [k.value for k in node.keywords]:
            follow(legacy, offsets, node, arg, env,
                   lambda shown, n=name: f"{n}(... {shown} ...)",
                   ambiguous_ok=specific, utc_prefixed_ok=True)

    # Module-level settings, judged last so that "already reported" is a
    # settled fact rather than a guess about walk order.
    #
    # Two bounds, and both were learned by removing them. The dedupe in
    # `follow` covers the first: a value some timezone use already reported is
    # not reported again here. `_rebound_in_an_inner_scope` covers the second:
    # a module-level `tz = "EST"` that an inner scope rebinds is a shadowed
    # decoy, not an exported setting, and reporting it broke seventeen
    # scoping tests in this file -- a fair measure of how ordinary that shape
    # is. What remains is the finding's own condition: a module-level
    # timezone-named binding that nothing here overrides and no use explains,
    # which is exactly the settings module another component imports.
    #
    # This replaces "the name is never READ in this module", which any read at
    # all defeated -- so `TIME_ZONE = "EST"; assert TIME_ZONE` exported a
    # frozen zone with both guards green (Codex, PR #993).
    for node, tgt, value, env in settings_exports:
        if _replaces_the_module_binding(tree, tgt.id, node):
            continue
        follow(legacy, offsets, node, value, env,
               lambda shown, n=tgt.id: f"module setting {n} = {shown}")

    # `ast.walk` is breadth-first, so a call is visited before its own
    # arguments: a constant already reported with the call that gives it
    # meaning is not reported a second time as a bare literal.
    return list(dict.fromkeys(legacy)), list(dict.fromkeys(offsets))


# Environment templates are sourced, not just read. `.env.example` is the file
# the setup docs tell people to copy to `.env`, and that copy is then sourced
# by the shell -- so `TZ=${TZ:-EST}` in the template installs a fixed UTC-5
# zone for every developer whenever TZ is unset. The shell preprocessing was
# keyed on `.sh`/`.yml`/`Dockerfile`/`Makefile`, which the templates match none
# of, so the raw regex saw only `${...}` and both guards passed
# (Codex, PR #993).
_ENV_TEMPLATE_SUFFIX = ".example"


def _reads_as_pine(p: pathlib.Path) -> bool:
    """Is this one of the extensionless TradingView sources?

    Kept next to the other two predicates, and derived from the same constant
    `_source_files` collects them by, so a directory added there is read with
    Pine's comment syntax rather than silently with none.
    """
    return (p.suffix in ("", ".pine")
            and any(d in p.parts for d in EXTENSIONLESS_SOURCE_DIRS))


def _reads_as_make(p: pathlib.Path) -> bool:
    """Is this file read by make rather than by a shell?

    Make and bash disagree about `#`, so the file type has to decide which
    rule applies -- see `_strip_shell_comments`.
    """
    return p.suffix == ".mk" or p.name.startswith(("Makefile", "GNUmakefile",
                                                   "makefile"))


def _reads_as_shell(p: pathlib.Path) -> bool:
    """Is this file's text subject to shell comment and default expansion?

    Named rather than inlined at its one call site because the set has grown
    with each round that found another file type this repository executes; a
    predicate is where the next one goes.
    """
    # `.mk` is collected by `_source_files` as an included Make fragment and
    # was not classified here, so a commented `# export TZ := EST` in
    # `rules.mk` failed while the identical line in `Makefile` did not --
    # a difference with no reason behind it, and one this branch created when
    # it taught the context matcher Make's `:=` (Codex, PR #993).
    # Every name `_reads_as_make` knows, through that predicate rather than a
    # second list: `GNUmakefile` and `makefile` were collected and classified
    # as Make, but this test still spelled `Makefile` alone, so neither was
    # expanded or comment-stripped -- `A = EST` then `export TZ = $(A)`
    # passed, and a commented `# export TZ = EST` failed (Codex, PR #993
    # final review).
    return (p.suffix in (".sh", ".yml", ".yaml")
            or p.suffix == _ENV_TEMPLATE_SUFFIX
            or p.name.startswith("Dockerfile")
            or _reads_as_make(p))


def _notebook_cells(text: str):
    """The source of each CODE cell, separately -- or None if not a notebook.

    Separately, because parsing them joined meant one unparseable cell lost
    the AST path for all the rest (Codex, PR #993).

    None, not [], for text that is not a notebook document. An empty list
    says "a notebook with no code cells", which is a real verdict; None says
    "I could not read this", which the caller must not confuse with it.
    """
    try:
        nb = json.loads(text)
    except (ValueError, TypeError):
        return None                 # not JSON: the caller decides, loudly
    if not isinstance(nb, dict):
        return None                 # JSON, but not a notebook document
    out = []
    for cell in nb.get("cells", []):
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        src = cell.get("source", "")
        out.append("".join(src) if isinstance(src, list) else str(src))
    return out


def _notebook_code(text: str) -> str:
    """The source of a notebook's CODE cells, joined.

    Markdown cells are prose -- this file's own explanations mention
    `US/Eastern` constantly -- so only `cell_type == "code"` is returned.
    """
    cells = _notebook_cells(text)
    return "\n".join(cells) if cells else ""


# `%name payload` / `%%name payload` / `!shell`, split so the payload can be
# looked at rather than thrown away with the sigil.
_MAGIC_LINE = re.compile(r"^([ \t]*)(%{1,2}|!)(\w*)[ \t]*(.*)$")
# IPython's object-help syntax, `df?` and `??df`. Not a magic, so the magic
# pass left it, and it is a SyntaxError to `ast.parse`.
_HELP_LINE = re.compile(r"^([ \t]*)\??\??(.*?)\?{1,2}[ \t]*$")


def _parses(src: str) -> bool:
    """Does this text parse as Python? The one question asked of every cell."""
    try:
        ast.parse(src)
    except SyntaxError:
        return False
    return True


# The line magics whose payload runs in a SHELL, and the one that sets the
# kernel's environment. Everything else with a `%` is either Python IPython
# evaluates (`%time expr`) or something that is neither (`%pip`, `%cd`).
_SHELL_LINE_MAGICS = {"sx", "system"}
_ENV_ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:=|\s+)(.+)$")


def _classify_magic(line: str):
    """ONE reading of an IPython line, for both passes.

    `(kind, payload)`: `"python"` for a line magic whose payload parses,
    `"shell"` for `!cmd`, `%sx cmd` and `%system cmd`, `"env"` for `%env NAME
    VALUE` and `%env NAME=VALUE` rendered as the shell assignment they
    perform, `None` for a magic with nothing to read, and `(False, line)`
    for a line that is not a magic at all.

    One classification rather than two special-case lists. `_strip_magic`
    and `_notebook_shell` each knew a different subset -- the first kept
    Python and blanked the rest, the second collected `!` and `%%bash` -- so
    `%env TZ EST` (a documented form whose payload is not Python) and
    `%sx env TZ=EST date` (a shell payload behind a `%`) fell between them
    and reached neither pass (Codex, PR #993, rounds 23 and 24). The
    `%%bash` cell that arrived twice was the same split from the other side.
    """
    m = _MAGIC_LINE.match(line)
    if not m:
        return False, line
    indent, sigil, name, payload = m.groups()
    payload = payload.strip()
    if sigil == "!":
        # Everything after the `!` is the command. `_MAGIC_LINE`'s name
        # group is for `%name`; on `!TZ=EST date` it would swallow `TZ` as a
        # name and hand the shell pass `=EST date`.
        command = line[m.end(2):].strip()
        return ("shell", command) if command else (None, "")
    if sigil != "%" or not payload:
        return None, ""
    if name in _SHELL_LINE_MAGICS:
        return "shell", payload
    if name in ("env", "set_env"):
        # `%set_env var val` / `%set_env var=val` is IPython's other
        # documented setter, with the same two forms (Codex, PR #993 final
        # review).
        e = _ENV_ASSIGN.match(payload)
        # `%env` and `%env NAME` READ the environment; only an assignment
        # form sets it, and that is the one that installs a zone.
        return ("env", f"export {e.group(1)}={e.group(2)}") if e else (None, "")
    return ("python", indent + payload) if _parses(payload) else (None, "")


def _strip_magic(line: str) -> str:
    """Blank an IPython magic, but KEEP the Python it runs.

    `%time timezone(timedelta(hours=-5))` builds a fixed UTC-5 zone and
    IPython executes it, but blanking the whole line on a leading `%` left
    neither an AST nor any text for the regex pass -- the expression vanished
    with the sigil that introduced it (Codex, PR #993).

    The payload is kept only when it parses ON ITS OWN, so `%pip install x`
    and `%cd ..` still blank and nothing that was not Python becomes Python.
    `!shell` has no Python payload at all, and a `%%cell` header applies to
    the cell rather than to itself -- its body is already ordinary lines --
    so both blank as before.
    """
    kind, payload = _classify_magic(line)
    if kind is False:
        return line
    return payload if kind == "python" else ""


def _strip_help(line: str) -> str:
    """`df?` -> `df`, when what is left parses.

    Applied only to a cell that has ALREADY failed to parse. A line ending in
    a question mark is ordinary inside a docstring, and rewriting one there
    would change a string's contents -- so this runs where the cell is known
    to be un-analysable anyway and the transform cannot cost anything.
    """
    m = _HELP_LINE.match(line)
    if not m:
        return line
    indent, payload = m.groups()
    if not payload.strip():
        return ""
    return indent + payload if _parses(payload) else ""


def _salvage(text: str):
    """Split a cell that will not parse into the half that does and the rest.

    Returns `(kept, dropped)` -- the cell with the other half BLANKED in each,
    so a line number still means the line it always meant -- or `(None, text)`
    when nothing survives.

    A cell is not all-or-nothing. `LEGACY = "EST"` and an IPython-only
    statement on the same cell left the binding in the regex fallback, where
    an ambiguous assignment is deliberately ignored, and out of the shared AST
    namespace -- so a later `ZoneInfo(LEGACY)` in a cell that parsed fine
    reported nothing either (Codex, PR #993).

    Line-at-a-time, driven by the parser's own `lineno`: the error names the
    line it could not read, so that line is blanked and the parse retried. A
    block header whose body was just blanked reports the error on a line this
    pass already emptied, so the nearest earlier standing line is dropped
    instead -- otherwise the loop would spin on a line with nothing left to
    remove.
    """
    lines = text.splitlines()
    dropped: set[int] = set()
    for _ in range(len(lines) + 1):
        src = "\n".join("" if i in dropped else l for i, l in enumerate(lines))
        try:
            ast.parse(src)
        except SyntaxError as exc:
            i = (exc.lineno or 0) - 1
        else:
            if not src.strip():
                return None, text
            return src, "\n".join(l if i in dropped else ""
                                   for i, l in enumerate(lines))
        if not (0 <= i < len(lines)) or i in dropped or not lines[i].strip():
            start = min(i, len(lines)) - 1
            i = next((j for j in range(start, -1, -1)
                      if j not in dropped and lines[j].strip()), -1)
            if i < 0:
                return None, text
        dropped.add(i)
    return None, text


# `%%bash`, `%%sh`, `%%script bash` -- the cell magics whose BODY is shell
# rather than Python. `%%time` and `%%capture` are not here: their body is
# ordinary Python and the parser should keep reading it.
_SHELLS = r"(?:bash|sh|zsh|ksh|dash|fish)"
_SHELL_CELL_MAGIC = re.compile(
    r"^[ \t]*%%(?:" + _SHELLS + r"|script\s+" + _SHELLS + r")\b")
# `%%python`, `%%python3`, `%%script python`: the body is Python and belongs
# on the parse path with the header blanked. `script\b.*` used to send EVERY
# `%%script` cell to the shell pass, so `%%script python` followed by
# `print("Never set TZ=EST")` reported text Python only prints (Codex,
# PR #993). Another interpreter -- ruby, perl -- is neither: its body goes to
# the regex pass as text, the weaker reader, which is how an unparseable
# Python cell is treated and errs toward reporting.
_PYTHON_CELL_MAGIC = re.compile(r"^[ \t]*%%(?:python3?|script\s+python3?)\b")


def _notebook_shell(cells) -> str:
    """Every line a notebook hands to a SHELL, for the regex pass.

    Two forms: a `!` escape on any line, and the whole body of a shell cell
    magic. Both execute, and both were blanked by the magic pass with nothing
    left for any scanner to read (Codex, PR #993).
    """
    out = []
    for cell in cells:
        lines = cell.splitlines()
        if lines and _SHELL_CELL_MAGIC.match(lines[0]):
            out.extend(lines[1:])
            continue
        for line in lines:
            kind, payload = _classify_magic(line)
            # `%sx`/`%system` payloads and `%env` assignments run in, or
            # configure, a shell -- so they go where `!` already went.
            if kind in ("shell", "env"):
                out.append(payload)
    return "\n".join(out)


def _notebook_hits(path, text: str):
    """Scan a notebook's code cells with the PYTHON analyzer where possible.

    Round 12 routed cells to the regex path and recorded the limit rather than
    closing it, which left `timezone(timedelta(hours=-5))` invisible: it is a
    fixed Eastern zone with no textual `-05:00` for any pattern to match
    (Codex, PR #993).

    Cell magics (`%matplotlib`, `!pip`) are not Python, so they are dropped --
    blanked rather than deleted, to keep line numbers meaning what they say.
    If the result still does not parse, the regex path runs instead: partial
    coverage beats a guard that reports nothing on a file it could not read.
    """
    if not text.strip():
        # Zero bytes: there is nothing in the file to scan, so "no cells" is
        # an accurate verdict rather than a fabricated one. (One tracked
        # notebook is empty today; that is a repository defect recorded
        # separately, not a reason for this guard to guess.)
        return [], [], ""
    cells = _notebook_cells(text)
    if cells is None:
        # Not a notebook. `_notebook_cells` used to return [] here, which read
        # as "scanned, clean" for a file whose contents the guard could not
        # read at all -- the same silent fallback as an unparseable `.py`,
        # and worse, because malformed JSON has no regex pass to fall back
        # to. Fail loudly instead.
        raise ValueError(f"{path}: not a readable notebook (invalid JSON)")
    if not cells:
        return [], [], ""
    # Shell escapes are EXECUTED, so their payload goes to the caller's regex
    # pass rather than being thrown away. `!TZ=EST date` and a `%%bash` cell
    # body run the command with a fixed zone, and blanking the line left the
    # cell parsing as empty Python with no text reaching any scanner
    # (Codex, PR #993). Collected before the Python pass, because those lines
    # are removed from what the parser sees.
    shell = _notebook_shell(cells)
    parseable, unparsed = [], []
    for cell in cells:
        # A shell cell's body is already in `shell`; sending it down the
        # parse path as well put every line in the caller's regex input
        # twice, which is a duplicate finding rather than a wrong one but
        # still a wrong count.
        lines = cell.splitlines()
        if lines and _SHELL_CELL_MAGIC.match(lines[0]):
            continue
        if lines and _PYTHON_CELL_MAGIC.match(lines[0]):
            lines = [""] + lines[1:]        # header blanked, body is Python
        stripped = "\n".join(_strip_magic(l) for l in lines)
        if _parses(stripped):
            parseable.append(stripped)
            continue
        # Parseability is decided PER CELL, so one `%%bash` or one line of
        # IPython syntax does not drop every other cell to the regex path
        # (Codex, PR #993). Two rescues before giving up on a cell, each
        # confined to cells that have already failed: the object-help syntax,
        # then a line-at-a-time salvage of whatever still parses.
        helped = "\n".join(_strip_help(l) for l in stripped.splitlines())
        if _parses(helped):
            parseable.append(helped)
            continue
        kept, rest = _salvage(helped)
        if kept is not None:
            # The analysable statements join the shared namespace; only the
            # lines actually dropped go to the regex pass, so no line is read
            # twice and neither half loses its line numbers.
            parseable.append(kept)
            unparsed.append(rest)
        else:
            unparsed.append(stripped)
    # ...but the cells that DO parse are analysed TOGETHER, because a notebook
    # executes them in one namespace. Analysing each on its own lost exactly
    # that: `LEGACY = "EST"` in one cell and `ZoneInfo(LEGACY)` in the next
    # resolved to nothing, since the literal is ambiguous without a context
    # and the second cell could not see the binding (Codex, PR #993). Both
    # properties hold at once this way.
    legacy, offsets = ([], [])
    if parseable:
        parsed = _python_hits(path, "\n".join(parseable))
        # Every cell here parsed on its own, so the join parses too; a None
        # would mean that invariant broke, and that is worth failing on.
        assert parsed is not None, f"{path}: joined cells did not parse"
        legacy, offsets = parsed
    # Always the same shape: findings from the cells that parsed, plus the
    # text of the ones that did not AND every shell escape, for the caller's
    # regex pass. Empty when every cell parsed and none shelled out. A
    # variable-arity return would put the caller's correctness at the mercy
    # of the notebook's contents.
    return legacy, offsets, "\n".join([t for t in unparsed + [shell] if t])


# The manifest shapes are PARSED, not pattern-matched.
#
# Four rounds each found a YAML spelling the previous regex could not see:
# `- name: TZ` / `value: EST` split across lines (round 21), `args:
# ["--time-zone", "EST"]` with the flag and its value as separate list items
# (22), the flow-style `env: [{name: TZ, value: EST}]` (23), and `- value:
# EST` written before `name: TZ` (24) -- which YAML permits, since mapping
# order carries no meaning. Every one of those is the same gap: a
# line-oriented regex over a format that is not line-oriented. This walks the
# document the loader builds instead, so the shape a manifest is written in
# is not the thing that decides whether it is read (Codex, PR #993).
#
# Only the STRUCTURAL forms live here. The plain mapping form -- `TZ: EST` on
# one line -- is still the regex pass's, because `_TZ_CONTEXT` reads it
# correctly and reporting it from both would double every finding.
#
# Character OFFSETS come from the loader's marks, so a finding still points at
# the line it always did, and the shell blanking `_scan` applies to these
# files first is width-preserving -- an offset into the raw text is the same
# offset into the blanked text.
_YAML_ENV_KEYS = {"TZ", "PGTZ", "TIMEZONE", "TIME_ZONE"}
_YAML_ARGV_KEYS = {"args", "command", "entrypoint"}


class _TextHit:
    """The two things `report` reads off a regex match, for a computed hit."""

    def __init__(self, offset: int, shown: str):
        self._offset = offset
        self._shown = shown

    def start(self) -> int:
        return self._offset

    def group(self, _n: int = 0) -> str:
        return self._shown


def _bad_zone_value(value: str):
    """`(is_offset)` when `value` names a legacy zone or a fixed offset, else None."""
    v = value.strip()
    if v.lower() in {z.lower() for z in UNAMBIGUOUS_LEGACY}:
        return False
    if v.upper() in AMBIGUOUS_LEGACY:
        return False
    if _FIXED_OFFSET_STRINGS.match(v) or re.fullmatch(_FIXED_OFFSET_TEXT, v, re.I):
        return True
    return None


def _yaml_scalar(node) -> "str | None":
    return node.value if isinstance(node, yaml.ScalarNode) else None


def _yaml_flattened(node, seen=None) -> dict:
    """`{key: value node}` for a mapping, with its `<<` merges resolved.

    A `<<` MERGE first, so an explicit key beside it wins. The composer leaves
    the merge node unresolved -- `env: [{name: *key, <<: *base}]` holds a `<<`
    entry whose value is the `base` mapping (or a sequence of mappings), not
    the folded pairs -- so `value` inherited through it was never associated
    with `name` (Codex, PR #993 final review). TRANSITIVELY: a merged mapping
    may itself carry a `<<`, and `base: &base {value: EST}` / `mid: &mid {<<:
    *base}` / `{name: TZ, <<: *mid}` copied `mid`'s unresolved `<<` entry
    instead of `base`'s value (Codex, PR #993 final review). The inherited
    scalar keeps its own mark, so the finding points at where it was written;
    a mapping already on the path is not entered twice.
    """
    seen = seen or frozenset()
    keys: dict = {}
    if id(node) in seen:
        return keys
    seen = seen | {id(node)}
    for k, v in node.value:
        if _yaml_scalar(k) == "<<":
            merged = v.value if isinstance(v, yaml.SequenceNode) else [v]
            for mnode in merged:
                if isinstance(mnode, yaml.MappingNode):
                    for mk, mv in _yaml_flattened(mnode, seen).items():
                        keys.setdefault(mk, mv)
    for k, v in node.value:
        ks = _yaml_scalar(k)
        if ks is not None and ks != "<<":
            keys[ks] = v
    return keys


def _yaml_env_pair_hits(text: str) -> list:
    """`(hit, value, is_offset)` for each structural manifest entry naming a bad zone.

    Two structures, in any nesting and either style:

    * a mapping holding a `name` and a `value` scalar -- the Kubernetes and
      Cloud Run environment entry -- in either key order;
    * a sequence under `args`/`command`/`entrypoint` carrying `--time-zone`
      followed by its value as the next item, or `--time-zone=VALUE` as one.

    Raises on text the loader cannot read. A `.yml` that is not YAML is not
    scanned by being skipped: the same rule as an unreadable notebook, and
    for the same reason. (No tracked YAML here is templated; if one ever is,
    excluding it becomes a stated decision rather than a silent one.)
    """
    out = []
    docs = list(yaml.compose_all(text))     # yaml.YAMLError propagates
    stack = [d for d in docs if d is not None]
    while stack:
        node = stack.pop()
        if isinstance(node, yaml.MappingNode):
            keys = _yaml_flattened(node)
            for _k, v in node.value:
                stack.append(v)
            name, value = _yaml_scalar(keys.get("name")), keys.get("value")
            if name is not None and name.upper() in _YAML_ENV_KEYS:
                val = _yaml_scalar(value)
                if val is not None:
                    is_offset = _bad_zone_value(val)
                    # A container's `TZ` is a process `TZ`: POSIX's sign.
                    if (is_offset is None and name in _POSIX_TZ_KEYS
                            and _POSIX_UTC_FIXED_VALUE.fullmatch(val.strip())):
                        is_offset = True
                    if is_offset is not None:
                        out.append((_TextHit(value.start_mark.index,
                                             f"name: {name} / value: {val}"),
                                    val, is_offset))
            for ks, v in keys.items():
                if ks in _YAML_ARGV_KEYS and isinstance(v, yaml.SequenceNode):
                    out.extend(_yaml_argv_hits(v))
        elif isinstance(node, yaml.SequenceNode):
            stack.extend(node.value)
    # Loader order is document order reversed by the stack; callers index
    # `hits[0]`, so restore source order.
    out.sort(key=lambda h: h[0].start())
    return out


# Pine's builtins that take a timezone POSITIONALLY: `time(timeframe,
# session, timezone)`, `time_close(...)`, `timestamp(timezone, year, ...)`.
# No textual context sits next to the value, so `NONPY_AMBIGUOUS` had nothing
# to anchor on and `time(timeframe.period, session, "EST")` was invisible in
# the one collected language that writes it this way (Codex, PR #993).
_PINE_TZ_HEAD = re.compile(r"\b(time|time_close|timestamp)\s*\(")


def _pine_tz_calls(text: str) -> list:
    """`(start, name, args_start, args)` for each timezone-taking call.

    Balanced parentheses, walked rather than matched: the regex this replaces
    allowed ONE nested level, so `time(timeframe.period, outer(inner(session)),
    "EST")` was not a call at all and its fixed zone -- a bare ambiguous
    literal, ignored by design outside a call -- passed (Codex, PR #993 final
    review). A parenthesis inside a string is data; an unterminated call is
    not a call.
    """
    out = []
    for m in _PINE_TZ_HEAD.finditer(text):
        i, depth, quote = m.end(), 1, None
        while i < len(text) and depth:
            ch = text[i]
            if quote:
                if ch == "\\" and i + 1 < len(text):
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        if depth:
            continue
        out.append((m.start(), m.group(1), m.end(), text[m.end():i - 1]))
    return out


# A Pine function header, `name(params) =>`, whose BODY is the indented block
# beneath it. Assignments in that block are the function's own: a helper's
# local `zone = "America/New_York"` shadowed nothing outside it in Pine, but
# the file-wide binding list read it as the value in force for a top-level
# `time(..., zone)` and missed the global `zone = "EST"` -- and, reversed,
# failed CI on a canonical call (Codex, PR #993 final review).
_PINE_FUNC_HEAD = re.compile(
    r"^([ \t]*)([A-Za-z_][A-Za-z0-9_]*)\s*\([^()\n]*\)\s*=>[ \t]*$")


def _pine_function_spans(text: str) -> list:
    """`(start, end)` character spans of each Pine function BODY."""
    spans = []
    lines = text.splitlines(keepends=True)
    offsets, at = [], 0
    for ln in lines:
        offsets.append(at)
        at += len(ln)
    i = 0
    while i < len(lines):
        head = _PINE_FUNC_HEAD.match(lines[i])
        if not head:
            i += 1
            continue
        indent = len(head.group(1).expandtabs(4))
        j, last = i + 1, i
        while j < len(lines):
            ln = lines[j]
            if not ln.strip():
                j += 1
                continue
            if len((ln[:len(ln) - len(ln.lstrip())]).expandtabs(4)) <= indent:
                break
            last = j
            j += 1
        if last > i:
            spans.append((offsets[i + 1], offsets[last] + len(lines[last])))
        i = last + 1 if last > i else i + 1
    return spans
_PINE_STRING = re.compile(r"\"([^\"\n]*)\"|'([^'\n]*)'")
# `const string MARKET_ZONE = "EST"` -- a Pine constant, later passed by name.
# The call then carries no literal to read, and the repository's own scripts
# pass variables such as `tz` to these builtins, so the literal-only reading
# was blind to the ordinary form (Codex, PR #993 final review).
_PINE_CONST = re.compile(
    r"^[ \t]*(?:(?:var|varip|const)\s+)?(?:string\s+)?([A-Za-z_][A-Za-z0-9_]*)"
    r"\s*(?::)?=\s*(.+?)[ \t]*$", re.M)
# One fragment of a Pine string expression: a literal, or a name.
_PINE_FRAG = re.compile(r"\s*(?:\"([^\"\n]*)\"|'([^'\n]*)'|([A-Za-z_][A-Za-z0-9_]*))\s*")


def _split_top_level(text: str, sep: str) -> list:
    """`(offset, piece)` for `text` split at `sep` outside parentheses and strings."""
    out, depth, quote, start = [], 0, None, 0
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == sep and depth == 0:
            out.append((start, text[start:i]))
            start = i + 1
    out.append((start, text[start:]))
    return out


def _pine_string_expr(expr: str, consts: dict, at: int, spans) -> "str | None":
    """The string a Pine expression evaluates to, or None if not statically known.

    Literals and bound names joined by `+`: `"E" + "ST"` hands `time(...)`
    the frozen EST, and reading each fragment on its own found nothing
    forbidden in either (Codex, PR #993 final review). A name resolves to the
    binding in force at `at`, so a concatenation stored in a variable folds
    the same way. Anything else -- a call, a number, an unbound name -- is
    not a string this scan can know.
    """
    parts = []
    for _off, piece in _split_top_level(expr, "+"):
        m = _PINE_FRAG.fullmatch(piece)
        if not m:
            return None
        if m.group(3) is not None:
            value = _pine_constant_at(consts, m.group(3), at, spans)
            if value is None:
                return None
            parts.append(value)
        else:
            parts.append(m.group(1) if m.group(1) is not None else m.group(2))
    return "".join(parts)
_PINE_IDENT = re.compile(r"(?<![A-Za-z0-9_.])([A-Za-z_][A-Za-z0-9_]*)(?![A-Za-z0-9_(])")


def _pine_constants(text: str) -> dict:
    """`{NAME: [(offset, value), ...]}` for every string constant assigned, in order.

    By POSITION, because Pine reassigns with `:=`: `zone = "America/New_York"`
    then `zone := "EST"` hands `time(...)` the frozen zone, and keeping the
    first binding as a constant read it as canonical -- and, reversed, read a
    canonical call as a violation (Codex, PR #993 final review). The same
    model `_shell_scalars` keeps, for the same reason.
    """
    # Each entry also records which function BODY it sits in, if any, so a
    # helper's local binding is visible to calls inside that helper and to
    # nothing outside it (Codex, PR #993 final review).
    spans = _pine_function_spans(text)
    out: dict = {}
    for m in _PINE_CONST.finditer(text):
        at = m.start(1)
        # A string expression, folded against the bindings in force here;
        # anything else is not a string constant and is not recorded.
        value = _pine_string_expr(m.group(2), out, at, spans)
        if value is None:
            continue
        scope = next((k for k, (s, e) in enumerate(spans) if s <= at < e), None)
        out.setdefault(m.group(1), []).append((at, value, scope))
    return out


def _pine_constant_at(consts: dict, name: str, at: int, spans=()):
    """The value bound to `name` by the last VISIBLE assignment before `at`."""
    latest = None
    for offset, value, scope in consts.get(name, ()):
        if offset >= at:
            break
        if scope is not None and not (spans[scope][0] <= at < spans[scope][1]):
            continue                # a function's own binding, seen from outside
        latest = value
    return latest


# Pine's own fixed-offset spelling, read only inside a timezone-taking call.
# `time(timeframe.period, session, "UTC-5")` fixes the session at UTC-5 and
# `"GMT-05:00"` is the same zone; Pine reads the sign the conventional way,
# so `"UTC+5"` is UTC plus five and is not Eastern. `_bad_zone_value` leaves
# every `UTC`-prefixed offset out because a shell `TZ` reads that sign the
# POSIX way, and reusing it here made a valid Pine call clean (Codex, PR #993
# final review). The call context has already settled which way the sign
# reads, so this is where the Pine spelling belongs -- not in the generic
# checker, which still has no context to settle it with.
_PINE_FIXED_OFFSET = re.compile(r"(?:UTC|GMT)-0?[45](?::?00)?")


def _pine_bad_zone_value(value: str):
    """`_bad_zone_value`, plus the fixed offsets Pine spells with `UTC`/`GMT`."""
    is_offset = _bad_zone_value(value)
    if is_offset is None and _PINE_FIXED_OFFSET.fullmatch(value.strip()):
        return True
    return is_offset


def _pine_call_hits(text: str) -> list:
    """`(hit, value, is_offset)` for each quoted bad zone inside a Pine timezone call."""
    out = []
    consts = _pine_constants(text)
    spans = _pine_function_spans(text)
    for start, head, args_start, args in _pine_tz_calls(text):
        for off, arg in _split_top_level(args, ","):
            lead = len(arg) - len(arg.lstrip())
            # The whole argument as one string expression first: a literal,
            # a bound name, or a `+` chain of them (Codex, PR #993 final
            # review).
            whole = _pine_string_expr(arg, consts, start, spans)
            if whole is not None:
                is_offset = _pine_bad_zone_value(whole)
                if is_offset is not None:
                    text_ = arg.strip()
                    shown = (repr(whole) if _PINE_STRING.fullmatch(text_)
                             else f"{text_} (= {whole!r})")
                    out.append((_TextHit(args_start + off + lead,
                                         f"{head}(... {shown} ...)"),
                                whole, is_offset))
                continue
            # Otherwise its literals and bound names one by one, as before.
            for m in _PINE_STRING.finditer(arg):
                value = m.group(1) if m.group(1) is not None else m.group(2)
                is_offset = _pine_bad_zone_value(value)
                if is_offset is not None:
                    out.append((_TextHit(args_start + off + m.start(),
                                         f"{head}(... {value!r} ...)"),
                                value, is_offset))
            bare = _PINE_STRING.sub(lambda q: " " * len(q.group(0)), arg)
            for m in _PINE_IDENT.finditer(bare):
                value = _pine_constant_at(consts, m.group(1), start, spans)
                if value is None:
                    continue
                is_offset = _pine_bad_zone_value(value)
                if is_offset is not None:
                    out.append((_TextHit(args_start + off + m.start(),
                                         f"{head}(... {m.group(1)} (= {value!r}) ...)"),
                                value, is_offset))
    return out


def _yaml_argv_hits(seq) -> list:
    """`--time-zone VALUE` and `--time-zone=VALUE` inside one argv sequence."""
    out = []
    items = [(_yaml_scalar(n), n) for n in seq.value]
    for i, (item, node) in enumerate(items):
        if item is None:
            continue
        value_node = None
        if item == "--time-zone" and i + 1 < len(items):
            value_node = items[i + 1][1]
        elif item.startswith("--time-zone="):
            value_node = node
        if value_node is None:
            continue
        val = _yaml_scalar(value_node)
        if val is None:
            continue
        val = val.partition("=")[2] if val.startswith("--time-zone=") else val
        is_offset = _bad_zone_value(val)
        if is_offset is not None:
            out.append((_TextHit(value_node.start_mark.index,
                                 f"--time-zone {val}"), val, is_offset))
    return out


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
        # No `except OSError: continue`. A tracked source this guard cannot
        # read is a checkout or permissions failure, and skipping it reported
        # a clean tree the guard never looked at -- the silent-fallback shape
        # this file forbids in the code it scans. `read_text` raising is the
        # honest answer: the test errors, naming the path.
        text = p.read_text(errors="replace")
        rel = str(p.relative_to(REPO)).replace("\\", "/")
        if rel == SELF:
            continue
        if p.suffix == ".py":
            parsed = _python_hits(p, text)
            if parsed is not None:
                l, o = parsed
                legacy += l
                offsets += o
                continue
            # Does not parse: fall through to the regex pass below rather
            # than reporting it clean. See `_python_hits`.
        if p.suffix == ".ipynb":
            # Code cells only, read by the Python analyzer when they parse and
            # by the regex path when they do not. The line number is a line
            # within the joined code, not a line of the JSON file -- which is
            # the useful one: a `.ipynb` file line points at an escaped string
            # inside a JSON array and locates nothing.
            nb_legacy, nb_offsets, nb_unparsed = _notebook_hits(p, text)
            legacy += nb_legacy
            offsets += nb_offsets
            if not nb_unparsed:
                continue
            # Only the cells that could not be parsed fall through to the
            # regex pass below; the ones that parsed were analysed properly.
            text = nb_unparsed
        # `${TZ:-EST}` -> `EST` before matching: the default is the value the
        # process actually gets whenever the variable is unset, which for a
        # container is the ordinary case (Codex, PR #993). Inline comments go
        # first, so a commented-out value cannot supply one.
        raw = text
        if _reads_as_shell(p):
            make = _reads_as_make(p)
            text = _expand_shell_defaults(
                _strip_shell_comments(text, make=make), make=make)
        elif _reads_as_pine(p):
            text = _strip_pine_comments(text)
        elif p.suffix == ".sql":
            # SQL has its own comment syntax and none of the shell expansion
            # forms, so it gets the one preprocessing step that applies to it
            # rather than being lumped in with the shell files.
            text = _strip_sql_comments(text)
        lines = text.splitlines()

        def report(bucket, m):
            lineno = text.count("\n", 0, m.start()) + 1
            line = lines[lineno - 1] if lineno <= len(lines) else ""
            bucket.append(f"{rel}:{lineno}: {' '.join(m.group(0).split())[:110]}"
                          f"   in: {line.strip()[:80]}")

        for pattern, bucket in ((NONPY_UNAMBIGUOUS, legacy),
                                (NONPY_AMBIGUOUS, legacy),
                                (NONPY_FIXED_ZONE, offsets),
                                (NONPY_FIXED_OFFSET, offsets),
                                (NONPY_POSIX_ENV_OFFSET, offsets),
                                (NONPY_SQL_NUMERIC_OFFSET, offsets),
                                (NONPY_SQL_INTERVAL_OFFSET, offsets)):
            for m in pattern.finditer(text):
                report(bucket, m)
        if _reads_as_pine(p):
            for m, _value, is_offset in _pine_call_hits(text):
                report(offsets if is_offset else legacy, m)
        if p.suffix in (".yml", ".yaml"):
            # The RAW text: the loader needs the comments and quoting the
            # shell pass blanks. Offsets agree because the blanking keeps
            # widths, so `report` still finds the right line in `text`.
            for m, _value, is_offset in _yaml_env_pair_hits(raw):
                report(offsets if is_offset else legacy, m)
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
    # Inline comments too, not just full lines -- see `_strip_shell_comments`.
    body = _strip_shell_comments(src)

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
    # Continuations joined FIRST. `--time-zone \` with the value on the next
    # line is ordinary wrapping, and reading the raw text captured the
    # backslash itself as the zone -- `zones == {'\\'}` -- so a correctly
    # zoned command failed this assertion (Codex, PR #993).
    # `_scheduler_commands` already joins them for the offender check; this
    # half of the test did not.
    joined = re.sub(r"\\\n\s*", " ", body)
    zones = set(re.findall(
        r"--time-zone[=\s]+[\"']?([^\s\"']+)[\"']?", joined))
    assert zones, "no --time-zone flags found -- has deploy.sh moved?"
    assert zones == {EASTERN}, f"non-Eastern scheduler timezones in deploy.sh: {sorted(zones - {EASTERN})}"

    offenders = []
    for name, func in _shell_functions(body):
        offenders.extend(_scheduler_offenders(name, func))
    assert not offenders, (
        "Cloud Scheduler defaults to UTC when --time-zone is omitted; these "
        "declarations set no timezone and expand no array that does:\n  "
        + "\n  ".join(offenders))


def _strip_shell_comments(text: str, make: bool = False) -> str:
    """Drop `#` to end of line, honouring quotes.

    Only FULL-line comments were removed, so a commented-out flag satisfied
    both halves of the scheduler check at once: the literal fed the file-wide
    zone set, and `_scheduler_offenders` saw the `--time-zone` substring in
    the same commented tail. A declaration that reads as compliant *because
    of a comment* is the quietest way for this guard to be wrong (Codex,
    PR #993).

    A `#` inside single or double quotes is data -- `msg="#tag"` -- so the
    scan tracks the quote state rather than cutting at the first `#`.

    `make=True` for a Makefile or `.mk`, because make's rule is not bash's:
    `#` starts a comment ANYWHERE, quotes and word boundaries included, so
    `NOTE := old# TZ=EST is forbidden` is entirely a comment. Reading it with
    bash's word-start rule -- added one round earlier for `${path#*/}` --
    preserved the tail and failed CI on text make never executes
    (Codex, PR #993).

    A RECIPE line still gets the bash rule. Make hands a tab-indented line to
    the shell verbatim, `#` and all, so the shell's rule is the one that
    decides there. Two rules in one file, because that is what make does.
    """
    out = []
    for line in text.splitlines():
        quote = None
        cut = len(line)
        escaped = False
        if make and not line.startswith("\t"):
            # Make: the first unescaped `#`, wherever it sits.
            j = 0
            while j < len(line):
                if line[j] == "\\":
                    j += 2
                    continue
                if line[j] == "#":
                    cut = j
                    break
                j += 1
            out.append(line[:cut].rstrip())
            continue
        for i, ch in enumerate(line):
            if escaped:
                # The previous character was a backslash inside double
                # quotes, so this one is literal whatever it is. Without it,
                # an escaped quote read as the CLOSING quote, the following
                # `#` was taken for a comment, and the rest of the line went
                # with it -- including a real `export TZ=EST` after a `;`.
                # The same shape as the `${path#*/}` finding one round
                # earlier: the stripper destroying the assignment it exists
                # to find (Codex, PR #993).
                escaped = False
                continue
            if quote:
                if ch == '\\' and quote == '"':
                    escaped = True      # single quotes take no escapes
                elif ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
            elif ch == "#" and (i == 0 or line[i - 1] in " \t;|&("):
                # Only at a word start, which is the rule bash actually uses.
                # Cutting at every unquoted `#` ate the parameter expansion in
                # `trimmed=${path#*/}` and everything after it on the line --
                # including a real `export TZ=EST` following a `;` -- so the
                # scanner deleted the assignment it exists to find, and would
                # equally mangle any `foo#bar` word (Codex, PR #993).
                cut = i
                break
        out.append(line[:cut].rstrip())
    return "\n".join(out)


# `${NAME:-VALUE}` and `${NAME-VALUE}`: the default is what the process gets
# whenever NAME is unset, which for a container is the ordinary case. The
# context matcher stopped at `$` and never reached it (Codex, PR #993).
#
# Only where a TIMEZONE CONTEXT sits immediately in front of it. Rewriting
# every expansion in the file turned `echo ${MESSAGE:-TZ=EST}` into
# `echo TZ=EST` and reported a line that only prints text; a help string
# carrying `--time-zone EST` did the same (Codex, PR #993). A false CI
# failure on correct code is the failure mode this guard keeps every
# ambiguous token gated to avoid, and it is worse here than a miss: it is
# red on someone else's PR.
#
# The context prefix is KEPT in the rewritten text rather than consumed, so
# the patterns that run afterwards see `TZ=EST`, exactly as if the default
# had been written inline.
_SHELL_DEFAULT = re.compile(
    r"((?:" + _TZ_CONTEXT + r")\s*[\"']?\s*)"
    r"\$\{[A-Za-z_][A-Za-z0-9_]*:?-([^}]*)\}", re.I)


# What is left after the timezone expansions are done: any OTHER `${X:-...}`.
# Its body is the default for some unrelated variable, not a line of shell, so
# it is blanked rather than read -- narrowing the EXPANSION alone was not
# enough, because `echo ${MESSAGE:-TZ=EST}` still carries the literal text
# `TZ=EST` and the context pattern matched it straight out of the raw line
# (Codex, PR #993). Replaced with spaces of the same width so every later line
# and column still means what it says.
_SHELL_OTHER_DEFAULT = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*:?-[^}]*\}")


# `export TZ="$LEGACY"` after `LEGACY=EST`. Same anchoring as the parameter
# default above and for the same reason: substituting every `$VAR` in the file
# is how the expansion pass came to report `echo ${MESSAGE:-TZ=EST}`, so a
# reference is resolved only where a timezone context sits immediately in
# front of it (Codex, PR #993).
_SHELL_TZ_VAR = re.compile(
    r"((?:" + _TZ_CONTEXT + r")\s*[\"']?\s*)\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?",
    re.I)


def _expand_shell_vars(text: str) -> str:
    """Substitute the scalar IN FORCE at each reference, if it is known."""
    scalars = _shell_scalars(text)

    def one(m):
        if _single_quoted(m.group(1)):
            return m.group(0)
        value = _scalar_in_force(scalars, m.group(2), m.start(),
                                 spans=_function_spans(text))
        return m.group(1) + value if value is not None else m.group(0)

    return _SHELL_TZ_VAR.sub(one, text)


def _single_quoted(prefix: str) -> bool:
    """Did the context prefix open a SINGLE-quoted string?

    The shell does not expand inside single quotes, so
    `export TZ='$LEGACY'` sets the literal text `$LEGACY` -- and rewriting it
    to `TZ='EST'` failed CI on a line that installs no zone at all
    (Codex, PR #993). Double quotes DO expand, so only `'` suppresses this.
    """
    return prefix.rstrip().endswith("'")


# Commands whose arguments are OUTPUT rather than configuration. A usage
# message or a reproduction hint routinely quotes the very setting this guard
# forbids -- `echo 'set TZ=EST to reproduce'`, `printf -- "--time-zone EST\n"`
# -- and the context patterns read the quoted text as an assignment or a flag,
# so a diagnostic became a false CI failure (Codex, PR #993).
#
# Narrow on purpose: only a QUOTED argument, and only to one of these names.
# An unquoted `echo $TZ` is untouched, and a real assignment is never inside
# quotes on the same line as one of these commands.
_SHELL_OUTPUT_CMD = re.compile(
    r"(?<![A-Za-z0-9_/-])(?:echo|printf|print|log|logger|warn|error|die|usage"
    r"|say|notice|info|debug)(?![A-Za-z0-9_-])")
# A redirect or a pipe means the text is not going to a terminal. `echo
# 'TZ=EST' > app.env` followed by `. app.env` WRITES configuration and then
# sources it, so blanking it hid a real assignment -- the previous version of
# this pass blanked every matching command regardless of where its output
# went (Codex, PR #993).
# `>` and `>>` count only when they write somewhere that can be read back. A
# redirect to stderr (`>&2`, `1>&2`, `>/dev/stderr`), to a descriptor, or to
# the bit bucket is still a diagnostic: `echo 'Never set TZ=EST' >&2` prints,
# and the raw operator test failed CI on it (Codex, PR #993).
_SHELL_REDIRECT = re.compile(
    r"\d?>>?(?!\s*(?:&\d|/dev/(?:stderr|stdout|null|tty)\b))"
    r"|\||(?<![A-Za-z0-9_-])tee(?![A-Za-z0-9_-])")
# Escape-aware, like `_command_end` and the comment stripper: a `\"` inside a
# double-quoted argument is data, and reading it as the closing quote left
# `TZ=EST` exposed between two blanked fragments of
# `echo "Never set \"TZ=EST\" here"` -- a false CI failure on a line that
# only prints (Codex, PR #993 final review).
_SHELL_QUOTED = re.compile(r"\"(?:[^\"\\\n]|\\.)*\"|'[^'\n]*'")


def _redirects_outside_quotes(text: str) -> bool:
    """Is there a `>`, `|` or `tee` the shell would actually act on?

    Searching the raw text found the `|` inside
    `echo 'Never set TZ=EST | use America/New_York'`, concluded the line was
    writing configuration, and left the quoted prose to be reported as a
    setting (Codex, PR #993). I named this failure shape when the redirect
    check went in last round and did not close it; an operator has to be
    outside quotes to mean anything.
    """
    quote = None
    escaped = False
    for i, ch in enumerate(text):
        if escaped:
            escaped = False
            continue
        if quote:
            if ch == '\\' and quote == '"':
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            continue
        if _SHELL_REDIRECT.match(text, i):
            return True
    return False


_HEREDOC_START = re.compile(
    r"<<[-~]?\s*([\"']?)([A-Za-z_][A-Za-z0-9_]*)\1")
#: Commands whose heredoc is text going to the terminal, not configuration.
_HEREDOC_DIAGNOSTIC = re.compile(
    r"(?<![A-Za-z0-9_/-])(?:cat|echo|printf|print|:|true|usage|warn|error|die"
    r"|say|notice|info|debug|help)(?![A-Za-z0-9_-])")


def _blank_heredoc_bodies(text: str) -> str:
    """Blank a heredoc body that only prints, width-preserving.

    `cat <<'EOF'` / `... Example: export TZ=EST` / `EOF` prints usage text and
    configures nothing, but the body's `export TZ=EST` was read as a real
    assignment (Codex, PR #993 final review). The same captured-output rule
    `_blank_shell_output` applies to `echo`/`printf` arguments applies here: a
    body is data unless its command is a diagnostic AND it is not redirected
    to a file or piped onward (`>`, `>>`, `|`, `tee`), in which case it is
    configuration and is kept. Newlines are preserved so offsets hold.
    """
    lines = text.splitlines(keepends=True)
    out = list(lines)
    i = 0
    while i < len(lines):
        m = _HEREDOC_START.search(lines[i])
        if m is None:
            i += 1
            continue
        before = lines[i][:m.start()]
        diagnostic = bool(
            _HEREDOC_DIAGNOSTIC.search(before)
            and not re.search(r">>?|(?<![A-Za-z0-9_/-])tee(?![A-Za-z0-9_-])|\|",
                              before))
        delim = m.group(2)
        j = i + 1
        while j < len(lines) and lines[j].strip() != delim:
            if diagnostic:
                out[j] = re.sub(r"[^\n]", " ", lines[j])
            j += 1
        i = j + 1
    return "".join(out)


def _blank_shell_output(text: str) -> str:
    """Empty the quoted arguments of a command that only prints them.

    EVERY quoted argument, not just the first: `printf '%s\n' 'TZ=EST'` puts
    the format string in the first and the data in the second, so blanking one
    left the other to be read as an assignment (Codex, PR #993).

    And only when the output is going nowhere. A line carrying `>`, `>>`, `|`
    or `tee` is writing its text somewhere that can be read back, which makes
    it configuration rather than a diagnostic, so it is left alone.

    Bounded to the CURRENT command. Blanking to the end of the physical line
    emptied every quoted string after the diagnostic, so `echo done; export
    TZ="EST"` was rewritten to `TZ="   "` and a real assignment on the same
    line stopped being a finding -- this pass, added to close a false
    positive, silently creating a false negative instead (Codex, PR #993).

    `;`, `&&`, `||` and a lone `&` end the command. A single `|` does not: it
    is the pipe `_redirects_outside_quotes` exists to notice, and treating it
    as a terminator would blank `echo 'TZ=EST' | tee app.env`, which IS
    writing configuration.
    """
    out = []
    for line in text.splitlines():
        # EVERY diagnostic on the line. Bounding the blanking to the current
        # command -- the fix one round earlier -- also stopped it at the first
        # one, so `echo "ok"; echo "never set TZ=EST"` blanked only the first
        # argument and the second was reported. The bound was right and
        # applying it once was not (Codex, PR #993).
        pos = 0
        while True:
            m = _SHELL_OUTPUT_CMD.search(line, pos)
            if not m:
                break
            cut = _command_end(line, m.end())
            rest = line[m.end():cut]
            if (not _redirects_outside_quotes(rest)
                    and not _output_is_captured(line[:m.start()])):
                rest = _SHELL_QUOTED.sub(
                    lambda q: (q.group(0)[0] + " " * (len(q.group(0)) - 2)
                               + q.group(0)[-1]),
                    rest)
            line = line[:m.end()] + rest + line[cut:]
            # Widths are preserved by the blanking, so `cut` still points at
            # the separator and the next search starts after it.
            pos = cut
        out.append(line)
    return "\n".join(out)


# A command whose captured output is EXECUTED: `eval "$(...)"`, `source
# <(...)`, `. <(...)`, `bash -c "$(...)"`. Matched against the text that
# precedes the `$(` or backtick, up to an optional opening quote.
_SHELL_CAPTURE_CONSUMER = re.compile(
    r"(?:^|[;&|({!]\s*|\b(?:then|do|else|elif|if|while|until)\s+)"
    r"(?:eval|source|\.|exec|bash|sh|zsh|ksh|dash)"
    r"(?:\s+-[A-Za-z]+)*\s+[\"']?$")


def _output_is_captured(prefix: str) -> bool:
    """Does the command that starts after `prefix` feed its output to something that runs it?

    `source <(printf 'TZ=EST')` executes the generated assignment, and so does
    `eval "$(printf 'TZ=EST')"`; the output pass read `printf` as a
    diagnostic and blanked the very text that becomes configuration (Codex,
    PR #993 final review). Inside a process substitution the output is always
    read back; inside a command substitution or backticks it counts when the
    substitution is an argument of `eval`, `source`, `.`, `exec` or a shell.
    `X=$(printf ...)` only stores text and is still a diagnostic here.
    """
    stack: list = []
    single = False
    i = 0
    while i < len(prefix):
        ch = prefix[i]
        if single:
            single = ch != "'"
        elif ch == "\\":
            i += 1
        elif ch == "'":
            single = True
        elif ch == "`":
            if stack and stack[-1][0] == "`":
                stack.pop()
            else:
                stack.append(("`", i))
        elif prefix.startswith(("$(", "<(", ">("), i):
            stack.append((prefix[i:i + 2], i))
            i += 1
        elif ch == "(":
            stack.append(("(", i))
        elif ch == ")" and stack:
            stack.pop()
        i += 1
    for opener, idx in reversed(stack):
        if opener in ("<(", ">("):
            return True
        if opener in ("$(", "`"):
            return bool(_SHELL_CAPTURE_CONSUMER.search(prefix[:idx]))
    return False


def _command_end(line: str, start: int) -> int:
    """Index of the separator ending the command that begins at `start`.

    Quote-aware, so a `;` inside `echo 'a; b'` does not end anything.
    """
    quote = None
    escaped = False
    i = start
    while i < len(line):
        ch = line[i]
        if escaped:
            escaped = False
        elif quote:
            if ch == "\\" and quote == '"':
                escaped = True
            elif ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == ";":
            return i
        elif line.startswith("&&", i) or line.startswith("||", i):
            return i
        elif ch == "&":
            # `>&2`, `2>&1`, `&>file`: the `&` belongs to the redirect. Reading
            # it as a background operator cut the command before the
            # descriptor, so `echo 'Never set TZ=EST' >&2` was bounded to
            # `... >` and the redirect check saw a write to a file
            # (Codex, PR #993).
            if (i > 0 and line[i - 1] in "<>") or line.startswith("&>", i):
                i += 1
                continue
            return i
        i += 1
    return len(line)


# Make's scalar assignment and reference. `LEGACY := EST` then `export TZ :=
# $(LEGACY)` installs the fixed zone in every recipe, and the shell collector
# reads neither the `:=` nor the `$(...)` (Codex, PR #993). Make has no
# function scopes, so a reference sees the last assignment before it -- the
# same in-force rule the shell scalars use, with no spans.
#
# SELECTIVE BY FILE. `$(...)` in a shell script is command substitution, a
# different thing entirely, and this expansion runs only for the files
# `_reads_as_make` names.
# `override` and `export`/`unexport` may precede the name, in either order
# (`override A = EST`, `export override A = EST`). GNU Make still binds the
# variable, and omitting the modifier left the reference unresolved (Codex,
# PR #993 final review).
_MAKE_SCALAR = re.compile(
    r"^[ \t]*(?:(?:override|export|unexport)[ \t]+)*"
    r"([A-Za-z_][A-Za-z0-9_.]*)[ \t]*"
    r"(::=|:=|\?=|\+=|=)[ \t]*([^#\n]*?)[ \t]*$", re.M)


class _Deferred(str):
    """A Make value assigned with `=` or `?=`: expanded where it is USED.

    GNU Make's `=` defines a recursively expanded variable, so with `A =
    America/New_York`, `B = $(A)`, `A = EST`, `export TZ = $(B)`, `B` is EST
    at the export. Folding every assignment at its definition froze `B` at
    the canonical value and, reversed, failed CI on a canonical export
    (Codex, PR #993 final review). `:=` and `::=` are immediate and stay
    folded where they are written.
    """
_MAKE_TZ_VAR = re.compile(
    r"((?:" + _TZ_CONTEXT + r")\s*[\"']?\s*)\$[({]([A-Za-z_][A-Za-z0-9_.]*)[)}]",
    re.I)


_MAKE_REF = re.compile(r"\$[({]([A-Za-z_][A-Za-z0-9_.]*)[)}]")


def _resolve_make_value(value: str, scalars: dict, at: int, seen=frozenset()):
    """`value` with every `$(NAME)` folded, or None if any is not static.

    A deferred (`=`) value met on the way is expanded here, at THIS offset,
    which is what makes the use site the point of expansion; a name already
    being expanded is a self-reference and is not static.
    """
    def one(m):
        name = m.group(1)
        if name in seen:
            raise LookupError
        v = _scalar_in_force(scalars, name, at)
        if isinstance(v, _Deferred):
            v = _resolve_make_value(v, scalars, at, seen | {name})
        if v is None:
            raise LookupError
        return v
    try:
        folded = _MAKE_REF.sub(one, value)
    except LookupError:
        return None
    return None if "$" in folded else folded


def _expand_make_vars(text: str) -> str:
    """Substitute the Make scalar in force at each `$(NAME)` in a timezone context."""
    scalars: dict = {}
    raw: list = []
    for m in _MAKE_SCALAR.finditer(text):
        # A recipe line (tab-indented) is shell, not a Make assignment.
        if text[m.start():m.start() + 1] == "\t":
            continue
        if m.group(3):
            raw.append((m.start(), m.group(1), m.group(2), m.group(3)))
    # CHAINS: `A := EST`, `B := $(A)`, `export TZ := $(B)`. GNU Make resolves
    # `B` to `EST`, and discarding every value that mentions `$` left `B`
    # unbound and the final reference unresolved (Codex, PR #993 final
    # review). Each value is resolved against the scalars in force at ITS OWN
    # offset, in source order, so a chain of any length folds and a reference
    # to something not statically known stays unresolved rather than guessed.
    # ...for the IMMEDIATE operators. `=` and `?=` define recursively expanded
    # variables, kept raw as `_Deferred` and expanded at each use; `?=` binds
    # only a name not already in force (Codex, PR #993 final review).
    for at, name, op, value in raw:
        if op in (":=", "::="):
            resolved = _resolve_make_value(value, scalars, at)
            if resolved is not None:
                scalars.setdefault(name, []).append((at, resolved, False))
            continue
        if op == "+=":
            # `A += EST` DEFINES an undefined `A`, recursively; otherwise it
            # appends with a space, keeping the variable's flavour -- deferred
            # stays deferred, immediate is expanded now (Codex, PR #993 final
            # review).
            prev = _scalar_in_force(scalars, name, at)
            if prev is None:
                scalars.setdefault(name, []).append((at, _Deferred(value), False))
            elif isinstance(prev, _Deferred):
                scalars.setdefault(name, []).append(
                    (at, _Deferred(prev + " " + value), False))
            else:
                resolved = _resolve_make_value(value, scalars, at)
                if resolved is not None:
                    scalars.setdefault(name, []).append(
                        (at, prev + " " + resolved, False))
            continue
        if op == "?=" and _scalar_in_force(scalars, name, at) is not None:
            continue
        scalars.setdefault(name, []).append((at, _Deferred(value), False))

    end = len(text)

    def one(m):
        # GNU Make expands a recursive (`=`) variable's references when it
        # builds the recipe environment -- so `export TZ = $(ZONE)` before a
        # later `ZONE = EST` still exports `EST`, and a redefinition of `ZONE`
        # after the export wins. Resolving at the reference offset saw only
        # earlier definitions, missing a forward reference and falsely
        # rejecting a later override. An immediate (`:=`) export is expanded
        # at its definition, so it keeps the reference-offset semantics
        # (Codex, PR #993 final review).
        immediate = ":=" in m.group(1) or "::=" in m.group(1)
        at = m.start() if immediate else end
        value = _scalar_in_force(scalars, m.group(2), at)
        if isinstance(value, _Deferred):
            value = _resolve_make_value(value, scalars, at)
        return m.group(1) + value if value is not None else m.group(0)

    return _MAKE_TZ_VAR.sub(one, text)


# Bash's ANSI-C quoting: `$'...'`, with backslash escapes decoded.
_ANSI_C_QUOTE = re.compile(r"\$'((?:[^'\\]|\\.)*)'", re.S)
_ANSI_C_ESCAPE = re.compile(
    r"\\(?:x([0-9A-Fa-f]{1,2})|u([0-9A-Fa-f]{1,4})|U([0-9A-Fa-f]{1,8})"
    r"|([0-7]{1,3})|(.))", re.S)
_ANSI_C_NAMED = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f",
                 "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\\": "\\",
                 "'": "'", '"': '"', "?": "?"}


def _decode_ansi_c(body: str) -> str:
    def one(m):
        if m.group(1):
            return chr(int(m.group(1), 16))
        if m.group(2):
            return chr(int(m.group(2), 16))
        if m.group(3):
            return chr(int(m.group(3), 16))
        if m.group(4):
            return chr(int(m.group(4), 8))
        return _ANSI_C_NAMED.get(m.group(5), "\\" + m.group(5))
    return _ANSI_C_ESCAPE.sub(one, body)


def _normalize_ansi_c_quotes(text: str) -> str:
    """Rewrite each `$'...'` as the ordinary `'...'` literal it denotes.

    `export TZ=$'EST'` and `export TZ=$'-05:00'` install the same frozen zones
    as the plainly quoted forms, and both passed: the context matchers stopped
    at the `$`, and the scalar collector refused a value containing one
    (Codex, PR #993 final review). Decoded in place and padded on the RIGHT
    to the original width, so every offset after it still means what it says
    -- the rule every shell pass here keeps -- and the literal stays against
    the `=` it follows, which the scalar collector requires (padding on the
    left turned `LEGACY=$'EST'` into `LEGACY= 'EST'`, which is a command, not
    an assignment; caught by this fix's own test). A literal that decodes to
    something a plain single-quoted string cannot hold (a quote, a newline)
    is left as written rather than rewritten into a different shape.
    """
    def one(m):
        decoded = _decode_ansi_c(m.group(1))
        if "'" in decoded or "\n" in decoded:
            return m.group(0)
        literal = "'" + decoded + "'"
        return literal + " " * (len(m.group(0)) - len(literal))
    return _ANSI_C_QUOTE.sub(one, text)


def _blank_dead_shell_branches(text: str) -> str:
    """Blank assignments the shell never runs, width-preserving.

    `LEGACY=EST; if false; then LEGACY=America/New_York; fi; export TZ="$LEGACY"`
    exports `EST` -- the `then` body never runs -- but collecting the dead
    `LEGACY=America/New_York` resolved the export to the canonical value and
    hid the violation; reversed, it failed CI on a correct script (Codex,
    PR #993 final review). A constant guard (`if true`/`if false`) makes one
    arm dead, and `false && CMD` / `true || CMD` short-circuits away `CMD`.
    Only these statically-decidable forms are blanked; anything whose truth is
    not known at read time is left untouched. Innermost first, iterated, so a
    nested constant `if` inside a live arm is handled without parsing the
    whole block.
    """
    def blank(seg: str) -> str:
        return re.sub(r"[^\n]", " ", seg)

    # `false && X`, `true || X`: X up to the next command separator is dead.
    text = re.sub(
        r"(?<![A-Za-z0-9_])(?:false[ \t]*&&|true[ \t]*\|\|)[ \t]*"
        r"([^\n;&|]*)",
        lambda m: m.group(0)[:m.start(1) - m.start()] + blank(m.group(1)),
        text)

    # `if <const>; then A [else B] fi`, innermost (no nested if/fi in the arms).
    arm = r"((?:(?!\bif\b|\bfi\b).)*?)"
    pat = re.compile(
        r"\bif[ \t]+(true|false)[ \t]*;?[ \t]*then\b" + arm
        + r"(?:\belse\b" + arm + r")?\bfi\b",
        re.S)

    def one(m):
        cond, a, b = m.group(1), m.group(2), m.group(3)
        dead_a = cond == "false"
        whole = m.group(0)
        out = list(whole)
        for grp, dead in ((2, dead_a), (3, not dead_a if b is not None else False)):
            if not dead or m.group(grp) is None:
                continue
            lo, hi = m.start(grp) - m.start(), m.end(grp) - m.start()
            out[lo:hi] = blank(m.group(grp))
        return "".join(out)

    prev = None
    while prev != text:
        prev = text
        text = pat.sub(one, text)
    return text


def _expand_shell_defaults(text: str, make: bool = False) -> str:
    """Expose a TIMEZONE parameter default; blank every other one.

    Two steps, and both are needed. A timezone expansion is rewritten to its
    default with the context prefix kept, so the patterns that run afterwards
    read `TZ=EST` exactly as if it had been written inline. Every other
    expansion is emptied, because its body is data belonging to another
    variable and reading it as shell is how `echo ${MESSAGE:-TZ=EST}` came to
    be reported as a process-timezone assignment.
    """
    # ANSI-C quoting first of all, so `$'EST'` reads as `'EST'` to every pass
    # below, the output blanking included.
    text = _normalize_ansi_c_quotes(text)
    # Output arguments go first, so a usage message quoting `${TZ:-EST}` is
    # emptied before the expansion pass can promote its default.
    text = _blank_shell_output(text)
    text = _blank_heredoc_bodies(text)
    text = _blank_dead_shell_branches(text)
    text = _join_shell_fragments(text)
    text = _SHELL_DEFAULT.sub(
        lambda m: (m.group(0) if _single_quoted(m.group(1))
                   else m.group(1) + m.group(2)), text)
    text = _SHELL_OTHER_DEFAULT.sub(lambda m: " " * len(m.group(0)), text)
    # Plain `$VAR` last, so a `${VAR:-default}` is read as its default rather
    # than as a reference to VAR. Make files get their own reference form
    # first; recipe lines in them are shell and take the shell pass after.
    if make:
        text = _expand_make_vars(text)
    return _expand_shell_vars(text)


def _opens_escape_string(text: str, i: int) -> bool:
    """Is the quote at `i` the start of a PostgreSQL `E'...'` literal?

    The `E` has to be its own token, so `TABLE'x'` and `CASE'x'` are ordinary
    literals rather than escape strings.
    """
    if text[i - 1:i] not in ("E", "e") or i == 0:
        return False
    return i < 2 or not re.match(r"[A-Za-z0-9_]", text[i - 2])


# `$$` or `$tag$`: a PostgreSQL dollar-quote delimiter, matched at an opening
# `$` outside any other literal.
# A dollar sign continuing an identifier (`foo$tag$`) is not a dollar-quote
# opener -- PostgreSQL allows `$` inside an identifier -- so the following
# `--` is a real comment, not string data. Requiring a non-identifier char
# (or start of text) before the opener stops the stripper preserving that
# comment and reporting a false violation (Codex, PR #993 final review).
_DOLLAR_QUOTE = re.compile(r"(?<![A-Za-z0-9_$])\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")


def _strip_pine_comments(text: str) -> str:
    """Blank Pine's `//` line comments and `/* ... */` blocks.

    The extensionless Pine sources are collected deliberately, and they
    reached the regex pass with their comments intact -- they match neither
    `_reads_as_shell` nor `.sql`, so no preprocessing branch claimed them. A
    migration note as ordinary as `// old: timezone = "EST"` therefore failed
    CI on text TradingView never executes: the same false positive the SQL
    branch was given comment stripping for two rounds ago, in the one
    collected language that still had none (Codex, PR #993).

    Pine has no `E'...'` literal, but EVERY Pine string honours a backslash,
    so `backslash_escapes` is on (Codex, PR #993 final review).
    """
    return _blank_comments(text, "//", escape_strings=False,
                           backslash_escapes=True)


def _strip_sql_comments(text: str) -> str:
    """Blank `--` line comments and `/* ... */` blocks, honouring quotes.

    A tracked `.sql` file may legitimately carry a commented example -- the
    old spelling beside its replacement is the ordinary way a migration
    explains itself -- and `-- SET TIME ZONE 'EST'` failed the guard on text
    that never executes (Codex, PR #993). Same class as the shell-expansion
    finding one round earlier, and worse for the same reason: a false finding
    is red CI on correct code, and it teaches people to skip the guard.

    Blanked rather than deleted, in spaces of the same width and keeping the
    newlines, so every line number and column still means what it says.

    Quote state is tracked, because `'--'` and `'/*'` inside a string literal
    are data. SQL escapes a quote by doubling it, which needs no special case
    here: the closing quote of the pair opens the next one, and the state
    machine ends up back inside the string.

    PostgreSQL's escape strings are the case that does need one. In `E'...'`
    a backslash escapes the following character, so the quote in
    `SELECT E'foo\' -- still data'; SET TIME ZONE 'EST';` does NOT close the
    literal -- but this machine read it as the closing quote, took the `--`
    for a comment, and blanked the real `SET` that followed. The third time
    the same shape has appeared: a stripper destroying the statement it exists
    to read, here in the direction that HIDES a finding (Codex, PR #993).

    Only `E'...'` honours backslashes at PostgreSQL's default
    `standard_conforming_strings = on`, so an ordinary literal is unchanged.

    Then the OTHER delimiters are rewritten as plain quotes, so the matchers
    that run on the result read `$$EST$$` and `E'EST'` as they read `'EST'`
    -- see `_normalize_sql_strings`.
    """
    return _normalize_sql_strings(
        _blank_comments(text, "--", escape_strings=True, dollar_quotes=True,
                        nested_blocks=True))


# A string-literal prefix that is its own token: `E'...'` (escape string),
# `N'...'` (national) and `U&'...'` (Unicode escapes). `CASE'x'` is not one.
_SQL_STRING_PREFIX = re.compile(r"(?<![A-Za-z0-9_])(U&|[EeNn])(?=')")


def _normalize_sql_strings(text: str) -> str:
    """PostgreSQL's other string delimiters as plain quotes, width kept.

    `SET TIME ZONE $$EST$$`, `SET TIME ZONE E'EST'` and
    `set_config('timezone', $tz$-05:00$tz$, false)` install exactly what the
    single-quoted forms install, and every matcher that runs on stripped SQL
    allows at most one bare quote between the context and the value, so all
    three passed both guards while the stripper -- which already reads these
    literals as strings when it looks for comments -- preserved them as
    written (Codex, PR #993 final review).

    A prefix letter becomes a space: `E'EST'` -> ` 'EST'`, `U&'EST'` ->
    `  'EST'`. A dollar delimiter becomes a quote at the end that touches
    the body and spaces elsewhere: `$$EST$$` -> ` 'EST' `, `$tz$EST$tz$` ->
    `   'EST'   `. Nothing moves, so every offset still means what it says.
    An opener with no matching closer is left as written, as the stripper
    leaves it. The body is taken literally: an escape inside `E'...'` is
    not decoded, which loses an evasion this guard was never meant to chase
    and changes nothing for the ordinary spellings.
    """
    text = _SQL_STRING_PREFIX.sub(lambda m: " " * len(m.group(1)), text)
    out, i = [], 0
    while True:
        m = _DOLLAR_QUOTE.search(text, i)
        if m is None:
            out.append(text[i:])
            break
        close = text.find(m.group(0), m.end())
        if close < 0:
            out.append(text[i:m.end()])
            i = m.end()
            continue
        width = len(m.group(0))
        out.append(text[i:m.start()])
        out.append(" " * (width - 1) + "'")
        out.append(text[m.end():close])
        out.append("'" + " " * (width - 1))
        i = close + width
    return "".join(out)


def _blank_comments(text: str, line_token: str, escape_strings: bool,
                    backslash_escapes: bool = False,
                    dollar_quotes: bool = False,
                    nested_blocks: bool = False) -> str:
    """Blank line and `/* */` comments, honouring quotes.

    Shared by the SQL and Pine strippers: they differ only in the line-comment
    token and in how their string literals are delimited. Blanked in spaces of
    the same width, keeping newlines, so every line and column still means
    what it says.

    `escape_strings`: PostgreSQL's `E'...'`, where a backslash escapes inside
    that literal only. `backslash_escapes`: every literal honours a backslash,
    which is Pine's rule -- `"literal \" // still data"` keeps its `//` inside
    the string, and reading the escaped quote as the closing one blanked the
    real `timezone = "EST"` after it (Codex, PR #993 final review).
    `dollar_quotes`: PostgreSQL's `$$...$$` and `$tag$...$tag$`, inside which
    `--` is data; `SELECT $$ -- still data $$; SET TIME ZONE 'EST';` lost the
    SET the same way (Codex, PR #993 final review).
    `nested_blocks`: PostgreSQL nests `/* */`, so `/* outer /* inner */ SET
    TIME ZONE 'EST'; */` is one comment to the end; a single open/closed flag
    closed at the inner `*/` and exposed the SET (Codex, PR #993 final
    review). A depth, for SQL; Pine does not nest.
    """
    out = []
    quote = None
    escapes = False
    block = 0
    i = 0
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if dollar_quotes and not quote and not block and ch == "$":
            m = _DOLLAR_QUOTE.match(text, i)
            if m:
                tag = m.group(0)
                end = text.find(tag, m.end())
                stop = len(text) if end < 0 else end + len(tag)
                out.append(text[i:stop]); i = stop
                continue
        if block:
            if ch == "*" and nxt == "/":
                out.append("  "); i += 2; block -= 1
                continue
            if nested_blocks and ch == "/" and nxt == "*":
                out.append("  "); i += 2; block += 1
                continue
            out.append("\n" if ch == "\n" else " "); i += 1
            continue
        if quote:
            out.append(ch)
            if (escapes or backslash_escapes) and ch == "\\" and i + 1 < len(text):
                # The escaped character is data whatever it is, including a
                # quote, so it cannot close the literal.
                out.append(text[i + 1]); i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            escapes = (escape_strings and ch == "'"
                       and _opens_escape_string(text, i))
            out.append(ch); i += 1
            continue
        if text.startswith(line_token, i):
            while i < len(text) and text[i] != "\n":
                out.append(" "); i += 1
            continue
        if ch == "/" and nxt == "*":
            out.append("  "); i += 2; block = 1
            continue
        out.append(ch); i += 1
    return "".join(out)


# Simple shell scalar assignments: `LEGACY=EST`, `export LEGACY="EST"`. Only a
# bare word or a fully quoted literal -- anything containing an expansion, a
# substitution or whitespace is not statically known and is left alone.
#
# The declaring builtins are accepted, with their options, exactly as
# `_arrays_carrying_timezone` accepts them. That parity was missing: the array
# collector learned `local`/`declare`/`typeset`/`readonly` in round 21 and this
# one still knew only a bare assignment and `export`, so `local LEGACY=EST`
# then `export TZ="$LEGACY"` resolved to nothing and the fixed zone passed both
# guards. A helper-scoped variable is the ordinary way to write this, so the
# gap was on the commoner spelling (Codex, PR #993).
# Anchored to a COMMAND, not a physical line: `LEGACY=EST; export TZ="$LEGACY"`
# is two commands on one line, and requiring the whole line to be one
# assignment collected neither (Codex, PR #993). The value may end at a
# separator as well as at end of line, and an assignment may start after one.
# `{` and `(` open a command position too, so a one-line body,
# `helper() { LEGACY=EST; }`, is collected like a multi-line one (Codex,
# PR #993 final review). So do the reserved words that precede a command --
# `if true; then LEGACY=EST; fi` runs the assignment and it was never
# collected -- and a case arm's `)` (Codex, PR #993 final review).
# A value is one shell WORD: adjacent quoted and bare fragments, which the
# shell concatenates. `export TZ="E""ST"`, `export TZ="US/"Eastern` and
# `export TZ=-"05:00"` are the same assignments as their single-literal
# forms, and a value pattern that accepted one fragment left the collector
# holding `E`, `US/` and `-` while no matcher ever saw the zone (Codex,
# PR #993 final review). `_shell_word` reads the fragments back.
_SHELL_WORD = r"(?:\"[^\"`\\\n]*\"|'[^'\n]*'|[^\s\"'`;|&\n]+)+"
_SHELL_FRAGMENT = re.compile(r"\"([^\"`\\\n]*)\"|'([^'\n]*)'|([^\s\"'`;|&\n]+)")
_SHELL_SCALAR = re.compile(
    r"(?:^|[;&|{()][ \t]*|\b(?:then|do|else|elif|if|while|until)[ \t]+)[ \t]*(?:(export|local|declare|typeset|readonly)[ \t]+"
    r"(?:-[A-Za-z]+[ \t]+)*)?([A-Za-z_][A-Za-z0-9_]*)="
    r"(" + _SHELL_WORD + r")[ \t]*(?=$|[;&|)}])",
    re.M)


# A declaring builtin with its options and ALL of its `NAME=value` operands.
_SHELL_DECL_MULTI = re.compile(
    r"(?:^|[;&|{()][ \t]*|\b(?:then|do|else|elif|if|while|until)[ \t]+)[ \t]*(export|local|declare|typeset|readonly)[ \t]+"
    r"(?:-[A-Za-z]+[ \t]+)*((?:[A-Za-z_][A-Za-z0-9_]*="
    + _SHELL_WORD + r"[ \t]*)+)", re.M)
_SHELL_DECL_OPERAND = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]*)=(" + _SHELL_WORD + r")")


def _shell_word(word: str) -> list:
    """`(text, literal)` per fragment of one shell word, in order.

    `literal` is a single-quoted fragment, which the shell does not expand;
    a double-quoted or bare fragment may hold a `$NAME` reference that
    `_shell_scalars` resolves at the assignment's own offset.
    """
    out = []
    for m in _SHELL_FRAGMENT.finditer(word):
        if m.group(1) is not None:
            out.append((m.group(1), False))       # double-quoted
        elif m.group(2) is not None:
            out.append((m.group(2), True))        # single-quoted: literal
        else:
            # Bare: the shell removes an unquoted backslash and keeps the
            # next character, so `E\ST` is the word `EST` (Codex, PR #993
            # final review). A single quote is literal and never reaches here.
            out.append((re.sub(r"\\(.)", r"\1", m.group(3)), False))
    return out


def _join_shell_fragments(text: str) -> str:
    """Each multi-fragment assignment value as one double-quoted word.

    `_shell_scalars` reads every fragment itself; this pass exposes the
    joined word to the TEXT matchers, which read the assignment as written.
    A word carrying a reference is replaced by the value the collector
    resolved for it, or left alone when it resolved nothing. Newlines are
    never touched, so line numbers hold; the value is padded to the width
    it replaced where it fits.
    """
    scalars = _shell_scalars(text)
    edits = []

    def consider(name: str, name_at: int, start: int, end: int, word: str) -> None:
        fragments = _shell_word(word)
        # One fragment is already the plain word -- UNLESS it carried a
        # backslash the shell removes mid-word (`E\\ST` -> `EST`), which the
        # text matchers must see decoded. A trailing continuation backslash
        # (`TZ=\\` before a newline) is not an escape and is left alone
        # (Codex, PR #993 final review).
        if len(fragments) < 2 and not re.search(r"\\[^\s]", word):
            return
        if any("$" in fragment for fragment, _literal in fragments):
            resolved = next((value for at, value, _local in scalars.get(name, ())
                             if at == name_at), None)
            if resolved is None:
                return
        else:
            resolved = "".join(fragment for fragment, _literal in fragments)
        edits.append((start, end, ('"' + resolved + '"').ljust(end - start)))

    for m in _SHELL_SCALAR.finditer(text):
        consider(m.group(2), m.start(2), m.start(3), m.end(3), m.group(3))
    for m in _SHELL_DECL_MULTI.finditer(text):
        for o in _SHELL_DECL_OPERAND.finditer(m.group(2)):
            consider(o.group(1), m.start(2) + o.start(1),
                     m.start(2) + o.start(2), m.start(2) + o.end(2), o.group(2))
    for start, end, replacement in sorted(set(edits), reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


# A simple reference inside a value: `$NAME` or `${NAME}`. Anything more --
# a default, a substitution, arithmetic -- is not statically known here.
_SHELL_REF = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")


def _resolve_shell_value(value: str, scalars: dict, at: int, spans) -> str | None:
    """`value` with every simple reference folded to the scalar in force, or None."""
    def one(m):
        v = _scalar_in_force(scalars, m.group(1) or m.group(2), at, spans)
        if v is None:
            raise LookupError
        return v
    try:
        folded = _SHELL_REF.sub(one, value)
    except LookupError:
        return None
    return None if "$" in folded else folded


def _shell_scalars(text: str) -> dict:
    """`{NAME: [(offset, value, function-scoped), ...]}`, in source order.

    By POSITION, not a single final value, because a shell script runs in
    order. The first version of this kept only the last assignment and both
    halves of that were wrong: with

        LEGACY=EST
        export TZ="$LEGACY"
        LEGACY=America/New_York

    the export really does install the frozen zone and the guard read the
    canonical one, and reversing the two values INVENTED a finding on a script
    that exports the canonical zone (Codex, PR #993). A regression I added one
    round earlier, and the same ordering mistake `_arrays_carrying_timezone`
    already records for scheduler flag arrays.
    """
    raw: list[tuple[int, str, list, bool]] = []
    for m in _SHELL_SCALAR.finditer(text):
        word = _shell_word(m.group(3))
        # `local`, and `declare`/`typeset` inside a function, bind in the
        # function's scope only. `export`, `readonly` and a bare assignment
        # bind globally. `_scalar_in_force` decides what a given reference can
        # see; this only records which kind it is.
        local = m.group(1) in ("local", "declare", "typeset")
        # The NAME's offset, not the match's: the match may begin at the
        # separator that ended the previous command.
        raw.append((m.start(2), m.group(2), word, local))
    # A declaring builtin takes SEVERAL operands: `local X=x LEGACY=EST`. The
    # anchored pattern above reads only the first, because the second begins
    # after whitespace rather than at a command boundary, so `LEGACY` was
    # never collected (Codex, PR #993 final review).
    for m in _SHELL_DECL_MULTI.finditer(text):
        local = m.group(1) in ("local", "declare", "typeset")
        for o in _SHELL_DECL_OPERAND.finditer(m.group(2)):
            at = m.start(2) + o.start(1)
            if not any(r[0] == at for r in raw):
                raw.append((at, o.group(1), _shell_word(o.group(2)), local))
    # CHAINS: `A=EST`, `B="$A"`, `export TZ="$B"`. The shell resolves `B` to
    # `EST` at ITS assignment, so each value is folded against the scalars in
    # force at its own offset, in source order -- exactly as `_expand_make_vars`
    # folds `$(NAME)`. Discarding every value that mentioned `$` left `B`
    # unbound and the export unresolved, and the bare `EST` binding has no
    # timezone context of its own, so the chain passed both guards (Codex,
    # PR #993 final review). A single-quoted value is literal text and is kept
    # as written; a reference to something not statically known stays
    # unresolved rather than guessed at.
    # A bare assignment INSIDE a function body binds globally in bash -- but
    # only when the body runs, and defining a function runs nothing. Ordered
    # by position alone, `LEGACY=EST`, an uncalled `helper() { LEGACY=America/
    # New_York; }` and `export TZ="$LEGACY"` read the dormant body as the
    # value in force and the frozen export as canonical; reversed, a correct
    # script failed CI (Codex, PR #993 final review). So a body assignment is
    # visible inside its own body, like a `local`, and outside it only from
    # each top-level command that invokes the function after its definition
    # -- the same rule the Python side applies to a `global` writer.
    named = _named_function_spans(text)
    spans = [(s, e) for _, s, e in named]
    invoked: dict[str, list] = {}
    applied: list = []
    for i, (at, name, word, local) in enumerate(raw):
        if local:
            continue
        body = next(((fn, s, e) for fn, s, e in named if s <= at < e), None)
        if body is None:
            continue
        fn, _s, end = body
        raw[i] = (at, name, word, True)
        if fn not in invoked:
            # `end` is the offset just past the body's closing line, so a call
            # on the very next line starts AT it.
            invoked[fn] = [c for c in _invoked_at(text, fn, named) if c >= end]
        applied.extend((c, name, word, False) for c in invoked[fn])
    raw.extend(applied)
    raw.sort(key=lambda r: r[0])
    out: dict[str, list] = {}
    for at, name, word, local in raw:
        parts = []
        for fragment, literal in word:
            if "$" in fragment and not literal:
                fragment = _resolve_shell_value(fragment, out, at, spans)
                if fragment is None:
                    break
            parts.append(fragment)
        else:
            out.setdefault(name, []).append((at, "".join(parts), local))
    return out


def _scalar_in_force(scalars: dict, name: str, at: int, spans=None):
    """The value bound to `name` at offset `at`, or None if it is unbound.

    A FUNCTION-LOCAL assignment is visible only to references inside that
    same function. Defining a function does not run its body, so
    `LEGACY=EST` then `helper() { local LEGACY=America/New_York; }` then
    `export TZ="$LEGACY"` exports EST -- but by textual position alone the
    `local` was the assignment in force and the real finding disappeared.
    That regression arrived with the fix one commit earlier that taught this
    collector to read `local` at all: before it, the declaration was
    invisible and the top-level value won by accident (Codex, PR #993).
    """
    latest = None
    for entry in scalars.get(name, ()):
        offset, value, local = entry
        if offset >= at:
            break
        if local and not _within_a_span(spans, offset, at):
            continue        # declared in a function body this reference is
        latest = value      # not inside, so it never runs before it
    return latest


def _within_a_span(spans, offset: int, at: int) -> bool:
    """Are `offset` and `at` inside the same function body?"""
    for start, end in (spans or ()):
        if start <= offset < end:
            return start <= at < end
    return True             # not in any body after all -- treat as file scope


def _named_function_spans(text: str) -> list[tuple[str, int, int]]:
    """`(name, start, end)` of each shell function BODY, outermost only.

    Same brace accounting as `_shell_functions`, which segments the text; this
    reports offsets, because the scalar collector records assignments by
    position and has to compare them against a reference's position -- and
    names, because whether a body's assignments ever run depends on whether
    something calls the function (Codex, PR #993 final review).
    """
    spans = []
    header = re.compile(
        r"^\s*(?:function\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(\)\s*)?"
        r"|([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*)\{")
    at = 0
    depth = 0
    start = None
    name = None
    pending = None                              # (offset, name) awaiting its `{`
    for line in text.splitlines(keepends=True):
        if depth == 0 and pending is not None:
            p_start, p_name = pending
            pending = None
            if line.strip().startswith("{"):
                start, name = p_start, p_name
                depth = _brace_delta(line)
                if depth <= 0:
                    spans.append((name, start, at + len(line)))
                    depth, start = 0, None
                at += len(line)
                continue
        opened = header.match(line) if depth == 0 else None
        if opened:
            start, name = at, (opened.group(1) or opened.group(2))
            depth = _brace_delta(line)
            if depth <= 0:                      # a one-line function body
                spans.append((name, start, at + len(line)))
                depth, start = 0, None
        elif depth == 0 and (bare := _HEADER_NO_BRACE.match(line)):
            pending = (at, bare.group(1) or bare.group(2))
        elif depth:
            depth += _brace_delta(line)
            if depth <= 0:
                spans.append((name, start, at + len(line)))
                depth, start = 0, None
        at += len(line)
    if start is not None:                       # unterminated, to end of file
        spans.append((name, start, at))
    return spans


def _function_spans(text: str) -> list[tuple[int, int]]:
    """Character span of each shell function BODY, outermost only."""
    return [(s, e) for _, s, e in _named_function_spans(text)]


def _invoked_at(text: str, name: str, spans) -> list[int]:
    """Offset of each top-level command that invokes function `name`.

    A command position -- the start of a line, a separator, a subshell or
    group opener, a `!`, or an `if`/`then`/`do`/`else` keyword, optionally
    after `VAR=value` prefixes -- followed by the name as a whole word that is
    not itself being defined or assigned. Outside every function body, since
    a body runs only when its own function does.
    """
    call = re.compile(
        r"(?:^|[;&|({!]|\b(?:then|do|else|elif|if|until|while)\b)[ \t]*"
        r"(?:[A-Za-z_][A-Za-z0-9_]*=\S*[ \t]+)*(" + re.escape(name)
        + r")(?![A-Za-z0-9_=/.(-])", re.M)
    return [m.start(1) for m in call.finditer(text)
            if not any(s <= m.start(1) < e for _, s, e in spans)]


# A function header WITHOUT its brace: `helper()` or `function helper`, with
# the `{` expected alone on the next line.
_HEADER_NO_BRACE = re.compile(
    r"^\s*(?:function\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(\)\s*)?"
    r"|([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*)$")


def _shell_functions(body: str) -> list[tuple[str, str]]:
    """[(name, text)] for each top-level shell function, plus the file scope.

    A function ends at its CLOSING BRACE, and everything after it belongs to
    the file scope again. Splitting only at the openings ran each function to
    the start of the next one, so a top-level command written after a helper
    was placed inside that helper -- and `_scheduler_offenders` then treated
    the helper's `local` array as visible to it. A genuinely zoneless
    top-level `gcloud scheduler jobs create` reported no offender, which is a
    UTC scheduler the guard calls fine (Codex, PR #993).

    Brace depth, tracked outside quotes and comments, because a `}` inside a
    string or a comment closes nothing.
    """
    lines = body.splitlines(keepends=True)
    out: list[tuple[str, list]] = [("<top level>", [])]
    # All three POSIX/bash spellings. Recognising only `name() {` meant a
    # helper written `function name {` opened no scope at all, so its `local`
    # zoned array was read as top level and covered a later top-level command
    # that actually receives nothing -- the same silent disarming of the
    # scheduler check this splitter was rewritten to fix, one spelling along
    # (Codex, PR #993).
    header = re.compile(
        r"^\s*(?:function\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(\)\s*)?"
        r"|([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*)\{")
    depth = 0
    pending = None      # a `name()` header whose `{` is on the NEXT line
    for idx, line in enumerate(lines):
        if depth == 0:
            if pending is not None:
                # The standard K&R-less layout: `helper()` then `{` alone on
                # the following line. Recognising only a same-line brace
                # opened no scope for it, so the helper's `local` zoned array
                # was read as file scope (Codex, PR #993 final review).
                name, header_line = pending
                pending = None
                if line.strip().startswith("{"):
                    out.append((name, [header_line, line]))
                    depth = _brace_delta(line)
                    if depth <= 0:
                        depth = 0
                        out.append(("<top level>", []))
                    continue
                out[-1][1].append(header_line)      # not a function after all
            m = header.match(line)
            if m:
                out.append((m.group(1) or m.group(2), [line]))
                depth = _brace_delta(line)
                if depth <= 0:          # a one-line function body
                    depth = 0
                    out.append(("<top level>", []))
                continue
            h = _HEADER_NO_BRACE.match(line)
            if h:
                pending = (h.group(1) or h.group(2), line)
                continue
            out[-1][1].append(line)
            continue
        out[-1][1].append(line)
        depth += _brace_delta(line)
        if depth <= 0:
            depth = 0
            out.append(("<top level>", []))
    merged: dict = {}
    ordered: list[tuple[str, str]] = []
    for name, chunk in out:
        text = "".join(chunk)
        if name == "<top level>":
            merged.setdefault(name, []).append(text)
        else:
            ordered.append((name, text))
    # One `<top level>` entry holding every file-scope region, so a caller
    # that looks up a name still finds one segment for it.
    return [("<top level>", "".join(merged.get("<top level>", [])))] + ordered


def _brace_delta(line: str) -> int:
    """`{` minus `}` in this line, ignoring quoted and commented braces."""
    depth = 0
    quote = None
    escaped = False
    for ch in line:
        if escaped:
            escaped = False
            continue
        if quote:
            if ch == "\\" and quote == '"':
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "#":
            break
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
    return depth


def _declares_zone_flag(cmd: str) -> bool:
    """Does this command pass `--time-zone` as an ARGUMENT?

    A substring test accepted any command whose payload happened to contain
    the text, so `--message-body '{"note":"--time-zone"}'` satisfied the
    check while the scheduler was created with no zone and defaulted to UTC
    (Codex, PR #993). The other half of the guard could not catch it either:
    the file-wide zone assertion is satisfied by the genuine flags elsewhere
    in `deploy.sh`.

    Tokenised, so the reverse also holds -- `"--time-zone"` written quoted is
    still the flag it is, which a blank-the-quotes approach would have missed
    and reported as an offender.

    On unbalanced quoting `shlex` raises and there is nothing to tokenise.
    The command is then NOT vouched for: it is reported as an offender, with
    the reason, rather than falling back to the substring test this replaced.
    A value this guard cannot read is a value it cannot vouch for -- the same
    rule `test_every_scheduler_declaration_uses_the_named_zone` already
    applies to a zone it cannot read -- and a permissive fallback here was a
    silent one. `gcp/deploy.sh` parses today, and
    `test_the_real_deploy_script_tokenises` fails if it stops.
    """
    # Only the FIRST command: `gcloud ... ; echo --time-zone X` puts the flag
    # on `echo`, and searching the whole line vouched for a scheduler that
    # defaults to UTC (Codex, PR #993 final review). Truncate at the first
    # unquoted `;`, `&&`, `||` or pipe before tokenising.
    cmd = _first_shell_command(cmd)
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return False
    return any(t == "--time-zone" or t.startswith("--time-zone=")
               for t in tokens)


def _first_shell_command(cmd: str) -> str:
    """`cmd` up to the first unquoted `;`, `&&`, `||` or `|` separator."""
    quote = ""
    i = 0
    while i < len(cmd):
        c = cmd[i]
        if quote:
            if c == quote:
                quote = ""
            elif c == "\\" and quote == '"':
                i += 1
        elif c in ("'", '"'):
            quote = c
        elif c == "\\":
            i += 1
        elif c in (";", "|") or cmd[i:i + 2] in ("&&", "||"):
            return cmd[:i]
        elif c == "&":
            return cmd[:i]
        i += 1
    return cmd


def _scheduler_offenders(name: str, func: str) -> list[str]:
    """Scheduler declarations in `func` that set no timezone.

    A named function rather than a loop body so the ordering rule below can
    be tested against synthetic shell rather than only against `deploy.sh`.
    An earlier test for it asserted on `_arrays_carrying_timezone`'s output
    instead and therefore passed against the whole-function scan it was meant
    to reject -- caught by running the injection, not by reading it.
    """
    zoned = _arrays_carrying_timezone(func)
    out = []
    for at, cmd in _scheduler_commands(func):
        if _declares_zone_flag(cmd):
            continue
        # `pos <= at`, not merely membership. An array assigned LATER in the
        # same function is still unset when this command runs, so bash expands
        # it to nothing and the scheduler is created with no timezone -- and
        # Cloud Scheduler's default is UTC, which is the whole point of this
        # check (Codex, PR #993).
        # The assignment IN FORCE, which is the last one completed before this
        # command -- not any assignment that ever carried the zone. bash
        # rebinds an array wholesale, so `flags=(--time-zone ...)` followed by
        # `flags=(--location ...)` leaves nothing of the first, and keeping
        # only the earliest definition read that as covered while the
        # scheduler was created with no zone at all (Codex, PR #993).
        covered = False
        expanded = _array_expansions(cmd)
        for spelling, assignments in zoned.items():
            # A real expansion, not the text of one inside another
            # argument. `--message-body '{"note":"${flags[@]}"}'` carries the
            # spelling and expands nothing -- single quotes are literal, and
            # even double-quoted it would be part of the body, not a flag --
            # while the raw substring test read it as covered (Codex, PR
            # #993). Same shape as the `--time-zone` substring one round ago.
            if spelling not in expanded:
                continue
            in_force = [carries for pos, carries in assignments if pos <= at]
            if in_force and in_force[-1]:
                covered = True
                break
        if covered:
            continue
        out.append(f"{name}: {' '.join(cmd.split())[:90]}")
    return out


def _array_expansions(cmd: str) -> set[str]:
    """The `${name[@]}` spellings that are whole, expanding words in `cmd`.

    Walked with the quote state machine: an expansion inside single quotes is
    literal, and one that shares a word with other text -- quoted or not --
    is the text of an argument rather than the array's elements. Only a word
    that IS the expansion, bare or double-quoted, hands the array to gcloud.
    """
    out: set[str] = set()
    words: list[tuple[str, bool]] = []        # (text, was single-quoted)
    word, quote, escaped, single = "", None, False, False
    for ch in cmd:
        if escaped:
            word += ch; escaped = False; continue
        if quote:
            if ch == "\\" and quote == '"':
                escaped = True
            elif ch == quote:
                quote = None
            else:
                word += ch
            continue
        if ch in "\"'":
            quote = ch; single = single or ch == "'"; continue
        if ch.isspace():
            if word or single:
                words.append((word, single))
            word, single = "", False
            continue
        word += ch
    if word or single:
        words.append((word, single))
    for text, was_single in words:
        if not was_single and re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*\[@\]\}", text):
            out.add(text)
    return out


def _elements_carry_zone(body: str) -> bool:
    """Do the ELEMENTS of an array literal pass `--time-zone America/New_York`?

    `shlex` splits the body the way bash does, so a flag inside a quoted
    element is that element's text. On unbalanced quoting there is nothing to
    tokenise and the body cannot vouch for a zone.
    """
    try:
        toks = shlex.split(body.replace("\\\n", " "))
    except ValueError:
        return False
    for n, t in enumerate(toks):
        if t == "--time-zone" and n + 1 < len(toks) and toks[n + 1] == EASTERN:
            return True
        if t == f"--time-zone={EASTERN}":
            return True
    return False


def _arrays_carrying_timezone(func: str) -> dict[str, list]:
    """`expansion spelling -> [(offset, carries the zone), ...]`, in order.

    Keyed by the spelling a command would contain, so the caller can test
    membership by substring without re-parsing; valued by POSITION, because
    bash reads a script in order. An array expanded before its assignment
    expands to nothing, and the scheduler then receives no timezone at all --
    while a whole-function scan reported the definition as satisfying every
    command in the function, including the ones above it (Codex, PR #993).

    EVERY assignment is recorded, not only the ones carrying a zone, and each
    says whether it carries one. bash rebinds an array wholesale, so a later
    zoneless assignment replaces an earlier zoned one entirely; keeping only
    the zoned definitions made that reassignment invisible and left the
    command reading as covered (Codex, PR #993).
    """
    names: dict[str, list] = {}
    # `local -a flags=(...)`, `declare -a`, `readonly`, `export`. Accepting
    # only a bare optional `local` meant a helper that TYPES its array -- the
    # more careful spelling, not the sloppier one -- recorded no array at all,
    # so `_scheduler_offenders` reported every command expanding it as
    # zoneless even though the canonical flag is passed at runtime. A false CI
    # failure on `gcp/deploy.sh`, aimed at the compliant form
    # (Codex, PR #993).
    for m in re.finditer(
            r"^\s*(?:(?:local|declare|typeset|readonly|export)\s+"
            r"(?:-[A-Za-z]+\s+)*)?([A-Za-z_][A-Za-z0-9_]*)(\+?)=\(",
            func, re.MULTILINE):
        start = m.end()
        depth = 1
        i = start
        quote = ""
        while i < len(func) and depth:
            c = func[i]
            # A `)` inside quotes is array DATA, not the closing paren:
            # `flags=(--message-body ")" --time-zone ...)` is one valid array
            # and closing at the quoted `)` recorded it as zoneless, failing a
            # compliant scheduler (Codex, PR #993 final review). Escapes are
            # honoured outside single quotes, where the shell takes them
            # literally.
            if quote:
                if c == quote:
                    quote = ""
                elif c == "\\" and quote == '"':
                    i += 1
            elif c in ("'", '"'):
                quote = c
            elif c == "\\":
                i += 1
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            i += 1
        # The LITERAL zone, not merely the flag. An array holding
        # `--time-zone "${SCHEDULER_TZ}"` satisfied every command that expanded
        # it while saying nothing about the zone those schedulers would run in.
        # TOKENISED, not searched. `flags=(--message-body 'note --time-zone
        # America/New_York')` is one element whose text mentions the flag; bash
        # passes a message body and no timezone. The substring read marked the
        # array as carrying the zone, and the file-wide assertion saw the same
        # payload text, so a zoneless scheduler passed the whole guard
        # (Codex, PR #993 final review).
        carries = _elements_carry_zone(func[start:i - 1])
        # `+=(` APPENDS. Reading it as a rebind lost the elements already
        # there, so `flags=(--location ...)` then `flags+=(--time-zone ...)`
        # recorded the zoneless assignment as the one in force and reported a
        # correctly zoned scheduler as an offender -- a false CI failure, on
        # the incremental spelling rather than the sloppy one
        # (Codex, PR #993).
        prior = names.get(m.group(1))
        if m.group(2) == "+" and prior:
            carries = carries or prior[-1][1]
        # The END of the assignment: bash has the value only after the
        # closing paren, so a command between `(` and `)` is not covered.
        names.setdefault(m.group(1), []).append((i, carries))
    # `${flags[@]}` only. Bash expands a bare `$flags` to element ZERO, so for
    # the `_enrich_common` layout that passes `--location` and silently drops
    # the `--time-zone` that follows it -- and accepting the scalar spelling
    # meant that typo produced no offender while the scheduler received no
    # zone at all (Codex, PR #993). The quoted and unquoted array forms both
    # expand to every element; the scalar does not.
    return {f"${{{n}[@]}}": v for n, v in names.items()}


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


def _scheduler_commands(func: str) -> list[tuple[int, str]]:
    """Each `gcloud scheduler jobs create/update http` command, whole.

    A command runs to the first line that does not end in a backslash, so a
    multi-line invocation is returned in one piece and its flags are not
    attributed to a neighbour.
    """
    lines = func.splitlines()
    # Character offset of each line, so a command can be compared against the
    # position of the array assignments it expands.
    starts, running = [], 0
    for line in lines:
        starts.append(running)
        running += len(line) + 1
    out = []
    i = 0
    while i < len(lines):
        at = starts[i]
        stmt = [lines[i]]
        while stmt[-1].rstrip().endswith("\\") and i + 1 < len(lines):
            i += 1
            stmt.append(lines[i])
        # Join the continuations BEFORE looking for the verb. Matching each
        # physical line first meant a declaration that wrapped inside the verb
        # itself -- `gcloud scheduler jobs \` then `create http ...` -- had no
        # single line carrying the whole invocation, so it was not a
        # declaration at all and its missing `--time-zone` went unreported
        # (Codex, PR #993). The joined form is what the shell runs, so it is
        # what this should read.
        joined = re.sub(r"\\\n\s*", " ", "\n".join(stmt))
        if _INVOCATION.search(joined):
            out.extend((at, c) for c in _split_invocations(joined))
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


def _hits_all(source: str) -> tuple[list[str], list[str]]:
    """Run the Python scan over `source` as if it were a file in the repo."""
    return _python_hits(REPO / "gcp" / "_scratch_for_this_test.py", source)


def _hits(source: str) -> tuple[list[str], list[str]]:
    """`_hits_all` without the module-setting exports.

    A module-level `TZ = "EST"` is a claim about what this module hands to an
    importer; every case below that plants one is using it as a DECOY for a
    shadowing question about some expression further down. Reporting both from
    one helper made those two claims indistinguishable, so narrowing the export
    rule (correctly) broke sixteen tests that were never about it.

    Tests that assert the export itself use `_hits_all`.
    """
    legacy, offsets = _hits_all(source)
    return ([h for h in legacy if "module setting " not in h],
            [h for h in offsets if "module setting " not in h])


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
                'os.environ["TZ"] = "EDT4"\n',
                'tz = ZoneInfo("EST5")\n'):
        assert _hits(src)[1], src

    # `UTC-05:00` is deliberately NOT matched. POSIX inverts the sign in a
    # `TZ` value, so `TZ=UTC-05:00` selects UTC+5 and is not Eastern in either
    # season, while `pd.Timestamp(tz="UTC-05:00")` really does mean UTC-5.
    # One string, two opposite meanings, decided by a context this guard does
    # not track — so it matches neither rather than inventing a violation on
    # the process-environment spelling (Codex, PR #993).
    assert _hits('os.environ["TZ"] = "UTC-05:00"\n') == ([], [])
    assert not NONPY_FIXED_OFFSET.search("ENV TZ UTC-05:00")

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


def test_a_directly_imported_constructor_keeps_its_provenance():
    """`from pytz import timezone; timezone("EST")`.

    The generic-name gate added last round reads the call's RECEIVER, and a
    bare call has none — so a constructor imported directly had no provenance
    and was treated as an unknown method. Fixing a false positive created a
    false negative (Codex, PR #993), which is the trade this file spends most
    of its comments trying not to make.
    """
    for src in ('from pytz import timezone\ntz = timezone("EST")\n',
                'from pytz import timezone as tzf\ntz = tzf("EST")\n',
                'from dateutil.tz import gettz\ntz = gettz("EST")\n'):
        assert _hits(src)[0], src

    # An unrelated module's `timezone` is still not a timezone constructor,
    # which is the false positive the gate exists to prevent.
    assert _hits('from mylib.text import localize\nlocalize("EST")\n') == ([], [])
    assert _hits('from cache import now\nnow("EDT")\n') == ([], [])

    # Provenance is per scope, like every other map here.
    assert _hits('def a():\n    from pytz import timezone\n    return timezone("UTC")\n'
                 '\n'
                 'def b(timezone):\n    return timezone("EST")\n') == ([], [])


def test_an_indirection_chain_is_followed_to_its_end():
    """`LEGACY = "EST"; TZ = LEGACY; ZoneInfo(TZ)`.

    Naming a shared setting once and referring to it is ordinary, and a
    binding map that kept only string constants and constructor calls left
    `TZ` resolving to nothing — so `follow`'s recursion, which exists exactly
    to walk chains, had no chain to walk (Codex, PR #993).
    """
    legacy, _ = _hits('LEGACY = "EST"\nTZ = LEGACY\nZoneInfo(TZ)\n')
    assert any("EST" in h for h in legacy), legacy

    _, offsets = _hits('OFF = timedelta(hours=-5)\nTZOFF = OFF\n'
                       'tz = timezone(TZOFF)\n')
    assert offsets, offsets

    # A chain ending in something benign is not a finding, and a chain that
    # goes nowhere resolvable is silent rather than guessed at.
    assert _hits('A = "UTC"\nB = A\nZoneInfo(B)\n') == ([], [])
    assert _hits('B = unknown_thing\nZoneInfo(B)\n') == ([], [])


def test_a_fixed_timedelta_default_is_a_binding_like_any_other():
    """`def build(offset=timedelta(hours=-5)): return timezone(offset)`.

    `_parameter_bindings` kept only string defaults, so the body could not
    resolve `offset`. A default IS a binding, and which node kinds count is
    not a question it and `_collect_bindings` should answer differently
    (Codex, PR #993).
    """
    _, offsets = _hits('def build(offset=timedelta(hours=-5)):\n'
                       '    return timezone(offset)\n')
    assert offsets, offsets

    assert _hits('def build(offset=timedelta(hours=1)):\n'
                 '    return timezone(offset)\n') == ([], [])


def test_positional_environment_setters_are_timezone_writes():
    """`os.putenv("TZ", "EST")` sets the same process zone as the subscript
    form, with the key and value as positional arguments to a call whose name
    is not a timezone constructor — so the call-name filter skipped it before
    either was looked at (Codex, PR #993)."""
    for src in ('os.putenv("TZ", "EST")\n',
                'os.environ.setdefault("TZ", "EST")\n',
                'os.putenv("TZ", "-05:00")\n'):
        assert _hits(src)[0] or _hits(src)[1], src

    # The key still has to mean a timezone.
    assert _hits('cache.setdefault("user", "est")\n') == ([], [])
    assert _hits('os.putenv("LANG", "EST")\n') == ([], [])


def test_a_recognised_call_matches_the_zone_in_any_casing():
    """`pytz.timezone("est")` builds the same frozen zone as `"EST"`.

    Safe here and not at the bare-constant scan: `follow` is only reached
    through a real timezone context, so a lowercase `est` in prose or a
    stop-word list is untouched — the same distinction the non-Python
    patterns make with IGNORECASE plus a required context (Codex, PR #993).
    """
    for src in ('import pytz\npytz.timezone("est")\n',
                'tz = ZoneInfo("Est")\n',
                'dt.astimezone(ZoneInfo("us/eastern"))\n'):
        assert _hits(src)[0], src

    assert _hits('STOPWORDS = ["est", "edt", "gmt"]\n') == ([], [])
    assert _hits('name = "Estonia"\n') == ([], [])


def test_a_timezone_named_module_constant_is_a_write():
    """`TIME_ZONE = "EST"` in a settings module needs no constructor here,
    because a framework or another module consumes it (Codex, PR #993).

    Bounded twice, and both bounds were learned by removing them: module
    scope only, and only when nothing in this module reads the name. Without
    them it reported every `tz = "EST"` anywhere, which broke twenty tests in
    this file — a fair measure of how ordinary that line is.
    """
    for src in ('TIME_ZONE = "EST"\n', 'TZ: str = "EST"\n',
                'timezone = "-05:00"\n'):
        assert _hits_all(src)[0] or _hits_all(src)[1], src

    # Read locally: reported at the read, with the constructor that gives it
    # meaning, rather than twice.
    once = _hits_all('TZ = "EST"\nZoneInfo(TZ)\n')[0]
    assert len(once) == 1, once
    # A local is not a setting another module can read.
    assert _hits_all('def f():\n    tz = "EST"\n    return tz\n') == ([], [])
    # And the name still has to mean a timezone.
    assert _hits_all('LABEL = "EST"\n') == ([], [])


def test_a_timezone_array_must_be_defined_before_it_is_expanded():
    """Bash reads a script in order.

    An array expanded before its assignment expands to nothing, so the
    scheduler is created with no `--time-zone` and Cloud Scheduler defaults to
    UTC — while a whole-function scan reported the later definition as
    satisfying every command in the function, including the ones above it
    (Codex, PR #993).
    """
    cmd = ('  gcloud scheduler jobs create http a --schedule "0 9 * * *" '
           '"${flags[@]}"\n')
    define = '  local flags=(--time-zone "America/New_York")\n'

    after = "deploy() {\n" + cmd + define + "}\n"
    assert _scheduler_offenders("deploy", after), (
        "an array assigned after the command it is expanded into was "
        "accepted; bash expands it to nothing and Cloud Scheduler defaults "
        "to UTC")

    before = "deploy() {\n" + define + cmd + "}\n"
    assert not _scheduler_offenders("deploy", before), (
        "the ordinary define-then-use order must still be accepted")


def test_an_alias_chain_has_no_length_limit():
    """The hop cap was justified by an invariant the same commit broke.

    It said a binding could only hold a constant or a constructor call, so a
    chain was short by construction — and that commit started retaining
    `ast.Name` bindings, making the sentence false as it was written. A
    six-hop configuration chain then hit the cap and reported nothing
    (Codex, PR #993). Cycle detection replaces it: a chain has no natural
    length, but it cannot revisit a node.
    """
    chain = 'A = "EST"\nB = A\nC = B\nD = C\nE = D\nF = E\nZoneInfo(F)\n'
    assert _hits(chain)[0], _hits(chain)

    # A cycle terminates rather than recursing forever.
    assert _hits('A = B\nB = A\nZoneInfo(A)\n') == ([], [])


def test_both_branches_of_a_conditional_are_values_it_can_take():
    """`ZoneInfo("EST" if legacy else "America/New_York")` builds the frozen
    zone on one path, and the standalone scan deliberately ignores the
    ambiguous literal, so nothing else would catch it (Codex, PR #993)."""
    assert _hits('ZoneInfo("EST" if legacy else "America/New_York")\n')[0]
    assert _hits('ZoneInfo("America/New_York" if x else "US/Eastern")\n')[0]
    assert _hits('tz = timezone(timedelta(hours=-5) if x else UTC)\n')[1]

    # Neither branch legacy, and the conditional itself is not a context.
    assert _hits('ZoneInfo("UTC" if x else "America/New_York")\n') == ([], [])
    assert _hits('label = "EST" if x else "EDT"\n') == ([], [])


def test_two_classes_of_one_name_in_one_scope_resolve_to_neither():
    """Merging their bodies by name let the later overwrite the earlier.

    The cross-scope fix keyed by object name and scope, which still merges two
    definitions inside ONE scope: a call between them resolved to the wrong
    body — a miss in one order and a false finding in the reverse (Codex,
    PR #993).

    A conflicted name now resolves to nothing, the same way `_local_aliases`
    treats one name imported from two modules. That closes the false finding
    and leaves the miss: which definition is in effect at a line is a flow
    question, and resolving it needs positional attribute lookup that would
    change every attribute resolution in the file for a shape as unusual as
    two same-named classes in one scope.
    """
    est_first = ('class Settings:\n    tz = "EST"\n'
                 'ZoneInfo(Settings.tz)\n'
                 'class Settings:\n    tz = "UTC"\n')
    utc_first = ('class Settings:\n    tz = "UTC"\n'
                 'ZoneInfo(Settings.tz)\n'
                 'class Settings:\n    tz = "EST"\n')
    assert _hits(utc_first) == ([], []), (
        "the later body's EST was attributed to a call that reads the "
        f"earlier body's UTC: {_hits(utc_first)}")
    assert _hits(est_first) == ([], []), _hits(est_first)

    # One definition per scope still resolves, which is the case that matters.
    assert _hits('class Settings:\n    tz = "EST"\nZoneInfo(Settings.tz)\n')[0]


def test_the_uncached_zoneinfo_constructor_is_still_a_constructor():
    """`ZoneInfo.no_cache("EST")` returns the same frozen zone; bypassing the
    cache must not also bypass the guard (Codex, PR #993)."""
    assert _hits('ZoneInfo.no_cache("EST")\n')[0]
    assert _hits('from zoneinfo import ZoneInfo\nZoneInfo.no_cache("-05:00")\n')[1]
    # Generic on its own: an unrelated `no_cache` is not a timezone context.
    assert _hits('store.no_cache("EST")\n') == ([], [])


def test_quoted_yaml_keys_are_timezone_keys():
    """YAML quotes a key as readily as it leaves it bare, and the quote sits
    between the key and the colon (Codex, PR #993)."""
    for line in ('  "TZ": "EST"', "  'timezone': 'EDT'", '  "tz": EST'):
        assert NONPY_AMBIGUOUS.search(line), line
    assert NONPY_FIXED_OFFSET.search("  'timezone': '-05:00'")
    # The bare form still works, and an unrelated quoted key is not a context.
    assert NONPY_AMBIGUOUS.search("  TZ: EST")
    assert not NONPY_AMBIGUOUS.search('  "quartz": EST')


def test_tracked_dotenv_templates_are_scanned():
    """`.env.example` is tracked and is what people copy into `.env`, so a
    legacy zone shipped there reaches every developer (Codex, PR #993).

    Templates only. A bare `.env` is gitignored and local, so scanning it
    would make this suite report findings that depend on the machine it runs
    on — the environment-dependence #999 spent a round removing.
    """
    scanned = {p.name for p in _source_files()}
    assert any(n.startswith(".env") and n.endswith(".example") for n in scanned), (
        f"no dotenv template in the scan: {sorted(n for n in scanned if 'env' in n)}")
    assert ".env" not in scanned, (
        "a bare .env is local and gitignored; scanning it makes this suite "
        "depend on the machine it runs on")


# ── Round 12: seven ways past the guard (Codex, PR #993) ───────────────────
#
# All seven are evasions of this file, not defects in the code it guards. They
# are grouped because they share one shape: a check that knew the spelling
# somebody had used and not the spelling somebody could use.


def test_a_read_does_not_suppress_a_fixed_zone_setting():
    """`TIME_ZONE = "EST"; assert TIME_ZONE` must still be a finding.

    The settings-export branch was bounded by "the name is never READ in this
    module", on the reasoning that a name this file reads gets reported at the
    read instead. But an ordinary read is not a timezone context, so it
    reports nothing -- and any read at all, a log line or a validation
    `assert`, switched the export check off. A settings module could then
    export a frozen Eastern zone with both guards green.

    The precise condition is the one the comment always claimed: suppress the
    assignment only when a timezone-context use ALREADY reported that value.
    """
    legacy, _ = _hits_all('TIME_ZONE = "EST"\nassert TIME_ZONE\n')
    assert any("EST" in h for h in legacy), (
        f"a read suppressed the export check: {legacy}")

    # And the reason the bound existed still holds: one finding, not two,
    # when a real timezone use reports the same value.
    legacy, _ = _hits_all('TIME_ZONE = "EST"\nZoneInfo(TIME_ZONE)\n')
    assert len(legacy) == 1, f"double-reported the same setting: {legacy}"


def test_a_reassigned_bash_array_loses_its_timezone():
    """`flags=(--time-zone ...)` then `flags=(--location ...)` carries nothing.

    The map kept the FIRST definition, so a later zoneless assignment left the
    command reading as covered while the scheduler received no zone at all.
    """
    func = (
        'deploy() {\n'
        '  local flags=(--time-zone "America/New_York")\n'
        '  flags=(--location us-east1)\n'
        '  gcloud scheduler jobs create http j1 --schedule "0 2 * * *" "${flags[@]}"\n'
        '}\n'
    )
    assert _scheduler_offenders("deploy", func), (
        "the zone was overwritten before the command ran, so this declaration "
        "creates a UTC scheduler")

    # The ordinary case must still pass: no reassignment, zone still in force.
    ok = (
        'deploy() {\n'
        '  local flags=(--time-zone "America/New_York")\n'
        '  gcloud scheduler jobs create http j1 --schedule "0 2 * * *" "${flags[@]}"\n'
        '}\n'
    )
    assert not _scheduler_offenders("deploy", ok), _scheduler_offenders("deploy", ok)


def test_a_foreign_timestamp_or_gettz_is_not_a_finding():
    """`factory.Timestamp("EST")` is not pandas, and `EST` is a stop-word.

    Both names were classified specific by NAME alone, so any library with a
    method or class called `Timestamp` or `gettz` could fail CI on a string
    that has nothing to do with a timezone -- the same false positive already
    corrected for `now` and `localize`.
    """
    for src in ('factory.Timestamp("EST")\n', 'translator.gettz("EDT")\n'):
        legacy, _ = _hits(src)
        assert not legacy, f"false finding on a foreign receiver: {src!r} -> {legacy}"

    # Provenance still convicts, by receiver or by import.
    for src in ('import pandas as pd\npd.Timestamp("EST")\n',
                'from dateutil.tz import gettz\ngettz("EDT")\n',
                'import pandas as pd\npd.Timestamp(tz="EST")\n'):
        legacy, _ = _hits(src)
        assert legacy, f"provenance should still make this a context: {src!r}"

    # And an unambiguous name is reported through ANY call, as before.
    legacy, _ = _hits('factory.Timestamp("US/Eastern")\n')
    assert legacy, legacy


def test_a_kubernetes_env_pair_installs_a_timezone():
    """`- name: TZ` / `value: EST` is the standard manifest spelling.

    The context patterns require the key and value to sit around one `:` or
    `=`, so the split name/value form used by every Cloud Run and Kubernetes
    manifest matched nothing -- in the file types this scan was widened to
    cover.
    """
    manifest = ('        env:\n'
                '        - name: TZ\n'
                '          value: EST\n')
    assert _yaml_env_pair_hits(manifest), "a split name/value TZ pair is a context"

    offset = ('        env:\n'
              '          - name: TZ\n'
              '            value: "-05:00"\n')
    assert _yaml_env_pair_hits(offset), "the fixed-offset value form too"

    # An unrelated pair is not a timezone.
    assert not _yaml_env_pair_hits('        - name: LOG_LEVEL\n          value: EST\n')
    # Nor is the named zone.
    assert not _yaml_env_pair_hits('        - name: TZ\n          value: America/New_York\n')


def test_an_env_getter_default_is_inspected():
    """`ZoneInfo(os.getenv("TZ", "EST"))` runs on the default when TZ is unset.

    `follow()` reached the getter call, recognised neither its value nor a
    timezone constructor, and stopped -- so the fallback that actually runs in
    a container with no TZ set was invisible.
    """
    for src in ('ZoneInfo(os.getenv("TZ", "EST"))\n',
                'ZoneInfo(os.environ.get("TZ", "-05:00"))\n',
                'ZoneInfo(os.getenv("TZ", default="US/Eastern"))\n'):
        legacy, offsets = _hits(src)
        assert legacy or offsets, f"the fallback that runs is a finding: {src!r}"

    # A named-zone default is fine.
    legacy, offsets = _hits('ZoneInfo(os.getenv("TZ", "America/New_York"))\n')
    assert not legacy and not offsets, (legacy, offsets)


def test_constant_arithmetic_in_a_fixed_offset_is_evaluated():
    """`FixedOffset(-5 * 60)` is UTC-5 written the way people write it.

    `_const_number` recognised a literal and a unary minus and rejected the
    `BinOp` before either the numeric-constructor or the timedelta check could
    reach it, so the three spellings below produced nothing.
    """
    assert _const_number(ast.parse("-5 * 60", mode="eval").body) == -300
    assert _const_number(ast.parse("-5 * 60 * 60", mode="eval").body) == -18000

    for src in ('import pytz\npytz.FixedOffset(-5 * 60)\n',
                'from dateutil.tz import tzoffset\ntzoffset(None, -5 * 60 * 60)\n',
                'from datetime import timezone, timedelta\n'
                'timezone(timedelta(minutes=-5 * 60))\n'):
        _, offsets = _hits(src)
        assert offsets, f"constant arithmetic is still a constant: {src!r}"

    # A non-constant stays undecidable and is left alone rather than guessed.
    _, offsets = _hits('import pytz\npytz.FixedOffset(-hours * 60)\n')
    assert not offsets, offsets


def test_notebook_code_cells_are_scanned():
    """Four tracked notebooks are executable source this guard never read.

    A cell can pin `US/Eastern` or a fixed offset and make DST-sensitive
    research diverge from production while the suite stays green. Archived
    notebooks stay excluded, like every other archived path.
    """
    nb = json.dumps({"cells": [
        {"cell_type": "markdown", "source": ["# US/Eastern in prose is not code\n"]},
        {"cell_type": "code", "source": ["import pytz\n", "tz = pytz.timezone('US/Eastern')\n"]},
    ]})
    assert "US/Eastern" in _notebook_code(nb), _notebook_code(nb)
    assert "in prose" not in _notebook_code(nb), "markdown cells are not code"

    tracked = {str(p.relative_to(REPO)) for p in _source_files()
               if p.suffix == ".ipynb"}
    assert any(t.startswith("notebooks/") for t in tracked), tracked
    assert not any(t.startswith("archive/") for t in tracked), tracked


# ── Round 13 (Codex, PR #993) ───────────────────────────────────────────────


def test_an_unrelated_inner_binding_does_not_hide_a_module_setting():
    """`_rebound_in_an_inner_scope` was too broad, and it was mine.

    Round 12 suppressed a module-level setting whenever ANY inner scope bound
    the same name. But a local, a parameter or a comprehension target does not
    change what importers read off the module -- it shadows the name inside
    one scope and leaves the exported value exactly as written. So an
    unrelated helper with its own `TIME_ZONE` variable hid a real exported
    fixed zone.

    Only a binding that can actually REPLACE the module value suppresses now,
    which is `global NAME` plus an assignment.
    """
    legacy, _ = _hits_all('TIME_ZONE = "EST"\n\n'
                      'def fmt(value):\n'
                      '    TIME_ZONE = value\n'
                      '    return TIME_ZONE\n')
    assert any("EST" in h for h in legacy), (
        f"an unrelated local named TIME_ZONE hid the exported setting: {legacy}")

    # A global rebinding CAN replace the module value -- once its function
    # runs. Defining `setup` runs nothing, so importers still read `EST`;
    # this case used to assert the suppression, which was the miss the final
    # review found (Codex, PR #993 final review).
    writer = ('TIME_ZONE = "EST"\n\n'
              'def setup():\n'
              '    global TIME_ZONE\n'
              '    TIME_ZONE = "America/New_York"\n')
    legacy, _ = _hits_all(writer)
    assert any("EST" in h for h in legacy), (
        f"an uncalled global writer hid the exported setting: {legacy}")
    legacy, _ = _hits_all(writer + "\nsetup()\n")
    assert not legacy, (
        f"a global rebinding that runs at import replaces the module value: {legacy}")


def test_a_notebook_cell_is_read_by_the_python_analyzer():
    """Text matching cannot see `timezone(timedelta(hours=-5))`.

    Round 12 routed notebook code cells to the regex path and I recorded that
    limit rather than closing it. It is reachable: that call has no textual
    `-05:00` for any pattern to match, so a cell could build a frozen Eastern
    zone with both guards green (Codex, PR #993).
    """
    nb = json.dumps({"cells": [
        {"cell_type": "code", "source": [
            "from datetime import timezone, timedelta\n",
            "ET = timezone(timedelta(hours=-5))\n"]},
    ]})
    _legacy, offsets, _rest = _notebook_hits(REPO / "notebooks" / "_probe.ipynb", nb)
    assert offsets, "a constant timedelta offset in a cell must be a finding"

    # A cell carrying a magic is not valid Python; the scan must still read
    # what it can rather than silently analysing nothing.
    nb = json.dumps({"cells": [
        {"cell_type": "code", "source": [
            "%matplotlib inline\n", "tz = 'US/Eastern'\n"]},
    ]})
    legacy, _offsets, _rest = _notebook_hits(REPO / "notebooks" / "_probe.ipynb", nb)
    assert legacy, "a cell with a magic still has to be scanned"


def test_an_aliased_timedelta_is_resolved():
    """`from datetime import timedelta as TD; timezone(TD(hours=-5))`.

    The constructor was matched by literal name while the environment already
    recorded the alias, so renaming the import walked past the offset check --
    the same provenance gap already closed for `ZoneInfo` and `timezone`.
    """
    _legacy, offsets = _hits('from datetime import timezone, timedelta as TD\n'
                             'ET = timezone(TD(hours=-5))\n')
    assert offsets, "an aliased timedelta is still a timedelta"


def test_dateutils_posix_string_constructor_is_recognized():
    """`tzstr("EST5")` builds a frozen UTC-5 zone, and python-dateutil is a
    declared dependency here."""
    _legacy, offsets = _hits('from dateutil.tz import tzstr\n'
                             'ET = tzstr("EST5")\n')
    assert offsets, "tzstr is a fixed-offset constructor"

    # Provenance gates the AMBIGUOUS token, as for every other generic name.
    # `EST5` itself is not gated and must not be: like `Etc/GMT+5` it means a
    # frozen offset and nothing else, so it is reported through any call --
    # the same rule the unambiguous zone names already follow.
    legacy, _offsets = _hits('parser.tzstr("EST")\n')
    assert not legacy, "an unrelated receiver must not fail CI on a stop-word"
    _legacy, offsets = _hits('parser.tzstr("EST5")\n')
    assert offsets, "EST5 is unambiguous, so no receiver excuses it"


def test_the_scan_reads_only_tracked_files():
    """A guard whose result depends on the working tree is not hermetic.

    `REPO.rglob` walked untracked files, so a local scratch file or copied
    build output containing `ZoneInfo("US/Eastern")` failed a guard about
    repository sources (Codex, PR #993).

    Three things about HOW this is checked, each one a defect the first
    version had (Codex, PR #993):

    * The probe file has a unique name and the test refuses to run if one
      somehow exists. The first version wrote a fixed path in the repository
      root and unlinked it in `finally`, so running the suite with a
      developer's own `_scratch_untracked_tz_probe.py` present destroyed it.
      A test may not delete a file it did not create.
    * It asks `_source_files()` whether the probe was COLLECTED, rather than
      running `_scan()` over every tracked file again. The scan takes ~43 s
      and `_scan` is `lru_cache`d precisely so the suite pays for it once;
      clearing that cache here doubled the guard's runtime for a question
      about the collector.
    * It skips when git tracking data is unavailable. `_source_files`
      deliberately falls back to scanning everything without it -- that
      fallback is documented and tested elsewhere -- so in a source export
      this assertion would fail on behaviour that is correct.
    """
    if not _tracked_files():
        pytest.skip("no git tracking data: _source_files deliberately falls "
                    "back to scanning every file, which this test would read "
                    "as a failure")

    scratch = REPO / f"_scratch_untracked_tz_probe_{uuid.uuid4().hex}.py"
    assert not scratch.exists(), scratch
    scratch.write_text('from zoneinfo import ZoneInfo\n'
                       'ET = ZoneInfo("US/Eastern")\n')
    try:
        collected = {p.resolve() for p in _source_files()}
        assert scratch.resolve() not in collected, (
            "an untracked file decided the result of a hermetic guard")
    finally:
        scratch.unlink(missing_ok=True)


def test_the_runtime_json_configuration_is_scanned():
    """`alert_config.json` is loaded by `lib.config.load_config` in production.

    Every JSON file was excluded as non-source, which is right for fixtures
    and wrong for the one file the application actually reads its settings
    from (Codex, PR #993).
    """
    tracked = {str(p.relative_to(REPO)) for p in _source_files()}
    assert "alert_config.json" in tracked, sorted(
        t for t in tracked if t.endswith(".json"))
    # Fixtures stay out: they legitimately carry canned values.
    assert not any(t.startswith("tests/") and t.endswith(".json")
                   for t in tracked), sorted(
        t for t in tracked if t.endswith(".json"))


def test_a_scheduler_verb_split_across_lines_is_still_a_declaration():
    """`gcloud scheduler jobs \\` then `create http ...`.

    The verb was matched per physical line before continuations were joined,
    so a wrapped declaration was invisible -- and an invisible declaration
    with no `--time-zone` is a UTC scheduler the guard reports as fine.
    """
    func = (
        'deploy() {\n'
        '  gcloud scheduler jobs \\\n'
        '    create http j1 --schedule "0 2 * * *" --uri https://x\n'
        '}\n'
    )
    assert _scheduler_commands(func), "a wrapped invocation is an invocation"
    assert _scheduler_offenders("deploy", func), (
        "it carries no --time-zone, so it creates a UTC scheduler")


# ── Round 14 (Codex, PR #993) ───────────────────────────────────────────────
#
# Grouped by root shape rather than by spelling. Rounds 12 and 13 fixed the
# named spellings one at a time and the next round named more, so these close
# the families: what the shell text means before anything reads it, how a
# callable or a value is resolved, and what counts as a source.


def test_an_inline_shell_comment_is_not_a_timezone_flag():
    """`create http ... # --time-zone America/New_York` sets no zone.

    Only FULL-line comments were stripped, so a commented-out flag satisfied
    both halves at once: the literal fed the file-wide zone set, and
    `_scheduler_offenders` saw the `--time-zone` substring in the same
    commented tail. A declaration that reads as compliant because of a comment
    is the quietest way for this guard to be wrong.
    """
    assert _strip_shell_comments('a=1 # --time-zone America/New_York').strip() == "a=1"
    # A `#` inside quotes is data, not a comment.
    assert "#tag" in _strip_shell_comments('msg="#tag" # real comment')
    assert "real comment" not in _strip_shell_comments('msg="#tag" # real comment')

    func = (
        'deploy() {\n'
        '  gcloud scheduler jobs create http j1 --schedule "0 2 * * *" '
        '--uri https://x  # --time-zone America/New_York\n'
        '}\n'
    )
    assert _scheduler_offenders("deploy", _strip_shell_comments(func)), (
        "a commented-out flag must not satisfy the per-declaration check")


def test_a_shell_parameter_default_is_read():
    """`export TZ="${TZ:-EST}"` installs UTC-5 whenever TZ is unset.

    The context matcher stopped at `$` and never reached the default, so the
    value that actually runs in a container with no TZ set was invisible.
    """
    assert NONPY_AMBIGUOUS.search(_expand_shell_defaults('export TZ="${TZ:-EST}"')), (
        "the default is the value that runs")
    assert NONPY_FIXED_OFFSET.search(
        _expand_shell_defaults('TZ=${TZ--05:00}')), "the `-` form too"
    # A named zone as the default is fine.
    assert not NONPY_AMBIGUOUS.search(
        _expand_shell_defaults('export TZ="${TZ:-America/New_York}"'))


def test_a_boolean_fallback_operand_is_followed():
    """`ZoneInfo(os.getenv("TZ") or "EST")` is the idiom people actually write.

    `follow()` descended into `IfExp` branches but not `BoolOp` values, and
    the standalone scan deliberately ignores a bare ambiguous literal, so
    nothing saw it.
    """
    legacy, _ = _hits('ZoneInfo(os.getenv("TZ") or "EST")\n')
    assert legacy, "the `or` fallback is a value this call can take"

    _legacy, offsets = _hits('ZoneInfo(os.environ.get("TZ") or "-05:00")\n')
    assert offsets, offsets

    legacy, offsets = _hits('ZoneInfo(os.getenv("TZ") or "America/New_York")\n')
    assert not legacy and not offsets, (legacy, offsets)


def test_a_posix_fixed_zone_string_is_matched_case_insensitively():
    """dateutil reads `est5` and `EST5` as the same frozen zone.

    The non-Python detector has been case-insensitive since round 9; the
    Python path was not, so lowering the case walked past it.
    """
    _legacy, offsets = _hits('from dateutil.tz import tzstr\nET = tzstr("est5")\n')
    assert offsets, "case does not change what POSIX builds"
    _legacy, offsets = _hits('from dateutil.tz import tzstr\nET = tzstr("EdT4")\n')
    assert offsets, offsets


def test_dateutil_tzrange_is_recognized():
    """`tzrange("EST", -18000)` is a fixed UTC-5 zone; the offset is in
    SECONDS and sits second, like `tzoffset`."""
    _legacy, offsets = _hits('from dateutil.tz import tzrange\n'
                             'ET = tzrange("EST", -18000)\n')
    assert offsets, offsets
    _legacy, offsets = _hits('from dateutil.tz import tzrange\n'
                             'ET = tzrange("IST", 19800)\n')
    assert not offsets, "UTC+5:30 is not Eastern"


def test_a_constructor_reached_through_an_assignment_alias_is_resolved():
    """`make_zone = ZoneInfo; make_zone("EST")`.

    Round 13 resolved IMPORT aliases; an assignment alias lives in
    `env.bindings` instead and was never consulted, so the call name failed
    the `_TZ_CALLS` filter before its argument was looked at.
    """
    legacy, _ = _hits('from zoneinfo import ZoneInfo\n'
                      'make_zone = ZoneInfo\n'
                      'ET = make_zone("EST")\n')
    assert legacy, legacy

    _legacy, offsets = _hits('from datetime import timezone, timedelta\n'
                             'make_zone = timezone\n'
                             'ET = make_zone(timedelta(hours=-5))\n')
    assert offsets, offsets


def test_the_makefile_is_scanned():
    """The root Makefile is tracked, executable configuration: `export TZ = EST`
    would fix the zone for every recipe."""
    tracked = {str(p.relative_to(REPO)) for p in _source_files()}
    assert "Makefile" in tracked, sorted(t for t in tracked if "ake" in t)
    assert NONPY_AMBIGUOUS.search("export TZ = EST"), (
        "the context must accept make's spaced assignment")


def test_postgres_set_config_is_a_timezone_context():
    """`SELECT set_config('timezone', 'EST', false)` does what
    `SET TIME ZONE 'EST'` does, and only the latter was a context."""
    assert NONPY_AMBIGUOUS.search(
        "SELECT set_config('timezone', 'EST', false)")
    assert NONPY_FIXED_OFFSET.search(
        "SELECT set_config('timezone', '-05:00', true)")
    assert not NONPY_AMBIGUOUS.search(
        "SELECT set_config('work_mem', 'EST', false)"), (
        "only the timezone setting is a timezone context")


def test_one_unparseable_notebook_cell_does_not_blind_the_rest():
    """A `%%bash` cell must not downgrade every other cell to regex.

    Round 13 parsed the joined source, so one non-Python cell lost the AST
    path for the whole notebook -- and `timezone(timedelta(hours=-5))` in a
    sibling cell has nothing textual for the regex to match.
    """
    # A `%%bash` cell whose body is shell: nothing in it is Python, so neither
    # the magic pass nor round 16's help-syntax and salvage passes can rescue
    # it. This used to be written with `pd?`, which round 16 now rewrites to
    # `pd` and analyses -- a better outcome, but no longer an example of a
    # cell that cannot be read, which is what this test is about.
    nb = json.dumps({"cells": [
        {"cell_type": "code", "source": ["%%bash\n", "echo TZ=EST\n"]},
        {"cell_type": "code", "source": [
            "from datetime import timezone, timedelta\n",
            "ET = timezone(timedelta(hours=-5))\n"]},
    ]})
    _legacy, offsets, unparsed = _notebook_hits(REPO / "notebooks" / "_probe.ipynb", nb)
    assert any("timedelta" in h for h in offsets), (
        f"the sibling cell that parses must still be analysed: {offsets}")
    # And the cell that could not be parsed is handed back rather than
    # dropped, so the caller still scans it by the only means left.
    assert "echo TZ=EST" in unparsed, unparsed


# ── Round 15 (Codex, PR #993) ───────────────────────────────────────────────
#
# Four of these are defects I introduced in rounds 13 and 14, and one is a
# docstring of mine describing behaviour the code could not reach. They are
# grouped with the two genuinely new gaps because the fix for several is the
# same: resolution has to carry provenance, not just a name.


def test_the_repo_root_is_found_without_git_metadata(tmp_path):
    """`_tracked_files` documents a no-git fallback that could never run.

    `REPO = _repo_root()` executes at import and required `.git`, so in a
    source export the module raised `RuntimeError` before any fallback was
    reachable and the ENTIRE guard silently did not run. A comment claiming
    behaviour the code cannot perform is worse than no comment (Codex,
    PR #993).
    """
    export = tmp_path / "export"
    for d in ("gcp", "lib", "platform", "tests"):
        (export / d).mkdir(parents=True)
    probe = export / "tests" / "meta"
    probe.mkdir(parents=True, exist_ok=True)

    assert _find_repo_root(probe / "probe.py") == export, (
        "a checkout is identifiable by its own directories, with or without "
        "git metadata")
    # And `.git` still wins where both could match, so a nested fixture tree
    # cannot capture the root.
    assert _find_repo_root(pathlib.Path(__file__).resolve()) == REPO


def test_a_callable_alias_chain_has_no_hop_cap():
    """The callable resolver reintroduced the cap `follow()` had removed.

    An earlier round replaced a four-hop cap with cycle detection and wrote
    down why: an alias chain has no natural length, and what it cannot do is
    revisit a name. `_resolve_callable` then shipped with `depth > 4` in the
    same file (Codex, PR #993).
    """
    src = ('from zoneinfo import ZoneInfo\n'
           'a = ZoneInfo\nb = a\nc = b\nd = c\ne = d\nf = e\n'
           'ET = f("EST")\n')
    legacy, _ = _hits(src)
    assert legacy, f"a six-hop alias chain resolved to nothing: {legacy}"

    # A cycle must terminate rather than spin.
    legacy, _ = _hits('a = b\nb = a\nET = a("EST")\n')
    assert legacy == [], legacy


def test_provenance_survives_an_assigned_constructor_alias():
    """`make_zone = pytz.timezone; make_zone("EST")`.

    `_resolve_callable` reduced the alias to the generic name `timezone`, but
    provenance was still read off the original bare call, whose receiver and
    import module are both empty. So the name resolved and the context did
    not, and an ambiguous `EST` stayed ignored (Codex, PR #993).
    """
    legacy, _ = _hits('import pytz\nmake_zone = pytz.timezone\n'
                      'ET = make_zone("EST")\n')
    assert legacy, legacy

    # An unrelated callable of the same shape must still not convict.
    legacy, _ = _hits('make_zone = factory.timezone\nET = make_zone("EST")\n')
    assert not legacy, legacy


def test_an_assigned_timedelta_alias_is_resolved():
    """`TD = timedelta; timezone(TD(hours=-5))`.

    Round 13 taught the offset check about import aliases and round 14 added
    a callable resolver, but the timedelta check was never pointed at it.
    """
    _legacy, offsets = _hits('from datetime import timezone, timedelta\n'
                             'TD = timedelta\n'
                             'ET = timezone(TD(hours=-5))\n')
    assert offsets, offsets


def test_notebook_cells_share_one_namespace():
    """A notebook executes its cells in one namespace, so the guard must too.

    Round 14 split them to stop one unparseable cell blinding the rest, and
    that lost cross-cell bindings: `LEGACY = "EST"` in one cell and
    `ZoneInfo(LEGACY)` in the next resolved to nothing (Codex, PR #993).
    Both properties have to hold at once.
    """
    nb = json.dumps({"cells": [
        {"cell_type": "code", "source": ['LEGACY = "EST"\n']},
        {"cell_type": "code", "source": ["from zoneinfo import ZoneInfo\n",
                                         "ET = ZoneInfo(LEGACY)\n"]},
    ]})
    legacy, _offsets, _rest = _notebook_hits(REPO / "notebooks" / "_probe.ipynb", nb)
    assert legacy, "a binding from an earlier cell must reach a later one"

    # And the round-14 property still holds: one bad cell does not blind the
    # parseable ones. `%%bash`, not the `pd?` this used to use -- round 16
    # rewrites the help syntax to `pd` and reads the cell, so it is no longer
    # a cell the analyzer must give up on.
    nb = json.dumps({"cells": [
        {"cell_type": "code", "source": ["%%bash\n", "echo TZ=EST\n"]},
        {"cell_type": "code", "source": [
            "from datetime import timezone, timedelta\n",
            "ET = timezone(timedelta(hours=-5))\n"]},
    ]})
    _legacy, offsets, unparsed = _notebook_hits(REPO / "notebooks" / "_probe.ipynb", nb)
    assert any("timedelta" in h for h in offsets), offsets
    assert "echo TZ=EST" in unparsed, unparsed


def test_a_numeric_postgres_session_offset_is_rejected():
    """`SET TIME ZONE -5` installs a fixed UTC-5 session zone.

    The offset matcher required the trailing `00`, so the numeric-hour form
    Postgres accepts went through while the quoted `'-05:00'` was rejected.
    """
    assert NONPY_SQL_NUMERIC_OFFSET.search("SET TIME ZONE -5")
    assert NONPY_SQL_NUMERIC_OFFSET.search("SET LOCAL TIME ZONE -4;")
    assert not NONPY_SQL_NUMERIC_OFFSET.search("SET TIME ZONE 5")
    # Not a partial match of a longer number.
    assert not NONPY_SQL_NUMERIC_OFFSET.search("SET TIME ZONE -530")

    # A SEPARATE pattern from `NONPY_FIXED_OFFSET`, confined to the SQL
    # statement forms on purpose: POSIX inverts the sign in a `TZ` value, so
    # `TZ=-5` selects UTC+5 and is not Eastern in either season. Same trap as
    # `UTC-05:00`, which this file already refuses to match for that reason.
    assert not NONPY_SQL_NUMERIC_OFFSET.search("export TZ=-5")
    assert not NONPY_FIXED_OFFSET.search("export TZ=-5")


def test_a_bound_sql_parameter_is_inspected():
    """`cur.execute("SET TIME ZONE %s", ("EST",))`.

    The statement carries the context and the value sits in the parameters,
    so each half looked innocent on its own.
    """
    legacy, _ = _hits('cur.execute("SET TIME ZONE %s", ("EST",))\n')
    assert legacy, legacy

    _legacy, offsets = _hits('cur.execute("SET TIME ZONE %s", ["-05:00"])\n')
    assert offsets, offsets

    # A statement with no timezone context does not make its parameters ones.
    legacy, _ = _hits('cur.execute("SELECT %s", ("EST",))\n')
    assert not legacy, legacy


# ── Round 16 (Codex, PR #993) ───────────────────────────────────────────────
#
# Five of the seven are the same shape as rounds 13-15: a resolution step that
# recovered one property of a value and dropped another. Two are not, and are
# the reason this round is worth landing rather than deferring to the runtime
# assertion in issue #1019 -- `PGTZ` and `.env.example` are live spellings
# this repository actually uses, not additional ways to write a value the
# guard already sees.


def test_a_numeric_constant_reaches_the_offset_constructor_through_a_name():
    """`OFFSET = -5 * 60; pytz.FixedOffset(OFFSET)`.

    Round 15 taught `_const_number` to fold `-5 * 60`, which only helps when
    the arithmetic sits at the call site. Naming the constant once -- the
    ordinary reason a constant gets a name -- put an `ast.Name` in front of
    the constructor and the binding map had already discarded the `BinOp`
    (Codex, PR #993).
    """
    _legacy, offsets = _hits(
        'import pytz\n'
        'OFFSET = -5 * 60\n'
        'ET = pytz.FixedOffset(OFFSET)\n')
    assert offsets, offsets

    # Seconds, through the constructor that takes them second.
    _legacy, offsets = _hits(
        'from dateutil.tz import tzoffset\n'
        'SECONDS = -5 * 60 * 60\n'
        'ET = tzoffset(None, SECONDS)\n')
    assert offsets, offsets

    # A unit named once reaches `timedelta` the same way.
    _legacy, offsets = _hits(
        'from datetime import timedelta, timezone\n'
        'HOURS = -5\n'
        'ET = timezone(timedelta(hours=HOURS))\n')
    assert offsets, offsets

    # And a number that is not Eastern still reports nothing: retaining the
    # binding must not turn every integer into a finding.
    _legacy, offsets = _hits(
        'import pytz\n'
        'OFFSET = 90\n'
        'TZ = pytz.FixedOffset(OFFSET)\n')
    assert not offsets, offsets


def test_import_provenance_survives_an_assignment_alias():
    """`from pytz import timezone; make_zone = timezone; make_zone("EST")`.

    Round 15's resolver recovered the callable's NAME through the alias and
    its RECEIVER, but provenance was still looked up under the name written at
    the call site -- so a bare `make_zone(...)` had no module, `specific`
    stayed false, and the ambiguous `EST` was ignored (Codex, PR #993).
    """
    legacy, _ = _hits(
        'from pytz import timezone\n'
        'make_zone = timezone\n'
        'ET = make_zone("EST")\n')
    assert legacy, legacy

    # The property that keeps this safe is unchanged: a callable with no
    # timezone provenance does not make `EST` a timezone.
    legacy, _ = _hits(
        'from mymodule import lookup\n'
        'get = lookup\n'
        'row = get("EST")\n')
    assert not legacy, legacy


def test_a_walrus_argument_is_followed():
    """`ZoneInfo(TZ := "EST")` builds the frozen zone and binds it.

    `follow` descends into a ternary and a boolean, which are the other two
    ways an expression carries a value it does not own; the walrus had no
    case, and the standalone scan deliberately ignores a bare `EST`
    (Codex, PR #993).
    """
    legacy, _ = _hits(
        'from zoneinfo import ZoneInfo\n'
        'ET = ZoneInfo(TZ := "EST")\n')
    assert legacy, legacy


def test_pgtz_is_a_postgres_session_timezone():
    """libpq reads `PGTZ` when a connection opens and issues it as SET TIME ZONE.

    This repository connects through psycopg2, so `os.environ["PGTZ"] = "EST"`
    freezes every query on that connection at UTC-5 -- and the key list knew
    only the generic `TZ`/`timezone` spellings (Codex, PR #993).
    """
    legacy, _ = _hits('import os\nos.environ["PGTZ"] = "EST"\n')
    assert legacy, legacy

    legacy, _ = _hits('env = {"PGTZ": "US/Eastern"}\n')
    assert legacy, legacy

    # And the shell/manifest side of the same variable. The `tz` alternative
    # is anchored at an identifier boundary, so `PGTZ=` matched no context.
    assert NONPY_AMBIGUOUS.search("PGTZ=EST")
    assert not NONPY_AMBIGUOUS.search("SOMETHING_ELSE=EST")


def test_a_magic_line_keeps_the_python_it_runs():
    """`%time timezone(timedelta(hours=-5))` executes; blanking it hid the zone.

    The magic pass blanked the whole line to keep line numbers honest, which
    also deleted the expression IPython evaluates -- leaving neither an AST
    nor any text for the regex fallback (Codex, PR #993).
    """
    nb = json.dumps({"cells": [
        {"cell_type": "code", "source": [
            "from datetime import timezone, timedelta\n",
            "%time ET = timezone(timedelta(hours=-5))\n"]},
    ]})
    _legacy, offsets, _rest = _notebook_hits(
        REPO / "notebooks" / "_probe.ipynb", nb)
    assert offsets, "the expression the magic runs must still be analysed"

    # A magic whose remainder is NOT Python still blanks, so nothing that was
    # never Python is handed to the parser.
    assert _strip_magic("%pip install pandas") == ""
    assert _strip_magic("!ls -la") == ""
    assert _strip_magic("%%bash") == ""
    # Indentation is preserved, so a magic inside a block keeps its position.
    assert _strip_magic("    %time x = 1") == "    x = 1"


def test_a_partly_unparseable_cell_keeps_the_statements_that_parse():
    """`LEGACY = "EST"; df?` binds a name IPython really does bind.

    The cell went whole to the regex fallback, where an ambiguous assignment
    is deliberately ignored, and its binding never joined the shared AST
    namespace -- so a later cell's `ZoneInfo(LEGACY)` reported nothing either
    (Codex, PR #993).
    """
    nb = json.dumps({"cells": [
        {"cell_type": "code", "source": ['LEGACY = "EST"; df?\n']},
        {"cell_type": "code", "source": ["from zoneinfo import ZoneInfo\n",
                                         "ET = ZoneInfo(LEGACY)\n"]},
    ]})
    legacy, _offsets, _rest = _notebook_hits(
        REPO / "notebooks" / "_probe.ipynb", nb)
    assert legacy, "a binding from a partly unparseable cell must still reach"

    # The salvage keeps line numbers meaning what they say: the dropped lines
    # are blanked in the kept half, not deleted.
    kept, dropped = _salvage('x = 1\nfor y in z\n    pass\n')
    assert kept is not None and "x = 1" in kept
    assert kept.splitlines()[0] == "x = 1"
    assert "for y in z" in dropped

    # A cell with nothing analysable in it is still handed to the regex pass
    # whole rather than reported as salvaged.
    nb = json.dumps({"cells": [
        {"cell_type": "code", "source": ["%%bash\n", "echo TZ=EST\n"]},
    ]})
    _legacy, _offsets, unparsed = _notebook_hits(
        REPO / "notebooks" / "_probe.ipynb", nb)
    assert "echo TZ=EST" in unparsed, unparsed


def test_an_environment_template_gets_shell_preprocessing(tmp_path):
    """`.env.example` is copied to `.env` and sourced; `${TZ:-EST}` runs.

    The preprocessing that turns a parameter expansion into its default was
    keyed on `.sh`/`.yml`/`Dockerfile`/`Makefile`, and the templates match
    none of those -- so the raw regex saw `${...}` and both guards passed
    (Codex, PR #993).
    """
    assert _reads_as_shell(pathlib.Path(".env.example"))
    assert _reads_as_shell(pathlib.Path(".env.staging.example"))
    assert not _reads_as_shell(pathlib.Path("notes.md"))

    # The expansion the predicate gates, on the value the template carries.
    assert NONPY_AMBIGUOUS.search(
        _expand_shell_defaults(_strip_shell_comments("TZ=${TZ:-EST}")))
    # And a commented-out template line still supplies nothing.
    assert not NONPY_AMBIGUOUS.search(
        _expand_shell_defaults(_strip_shell_comments("# TZ=${TZ:-EST}")))


# ── Round 17 (Codex, PR #993) ───────────────────────────────────────────────
#
# Six are more ways to spell a value the guard already understands one layer
# down, and follow round 16's shape exactly. The seventh is different in kind
# and is the one worth landing on its own: the shell-default expansion was
# producing FALSE findings, which is the failure mode that costs someone else
# a red CI run on correct code.


def test_a_receiver_aliased_by_assignment_still_names_its_module():
    """`import pytz; p = pytz; p.timezone("EST")`.

    Round 15 fixed the CALLABLE half of this -- `make_zone = pytz.timezone` --
    and left the receiver half. `_call_receiver` returns the bare `p`, the
    provenance check consulted only `env.aliases` (which records IMPORT
    aliases), so `specific` stayed false and the ambiguous `EST` was ignored
    (Codex, PR #993).
    """
    legacy, _ = _hits('import pytz\n'
                      'p = pytz\n'
                      'ET = p.timezone("EST")\n')
    assert legacy, legacy

    # Through a chain, and the cycle guard holds.
    legacy, _ = _hits('import pytz\n'
                      'a = pytz\n'
                      'b = a\n'
                      'ET = b.timezone("EST")\n')
    assert legacy, legacy

    # A receiver with no timezone provenance still does not make `EST` one.
    legacy, _ = _hits('import mymodule\n'
                      'p = mymodule\n'
                      'row = p.lookup("EST")\n')
    assert not legacy, legacy


def test_a_container_of_parameters_is_descended_into():
    """`cur.executemany("SET TIME ZONE %s", [("EST",)])` is the batch form.

    The parameter loop unwrapped the OUTER list and handed `follow` the inner
    tuple, which had no case for a container -- so the API the SQL branch was
    written to cover was covered in one shape and not the other
    (Codex, PR #993).
    """
    legacy, _ = _hits('cur.executemany("SET TIME ZONE %s", [("EST",)])\n')
    assert legacy, legacy

    _legacy, offsets = _hits(
        'cur.executemany("SET timezone TO %s", [("-05:00",), ("UTC",)])\n')
    assert offsets, offsets

    # The single-row form still works, and a statement with no timezone
    # context still does not make its parameters into one.
    legacy, _ = _hits('cur.execute("SELECT %s", [("EST",)])\n')
    assert not legacy, legacy


def test_statically_unpacked_arguments_are_inspected():
    """`ZoneInfo(*["EST"])` and `ZoneInfo(**{"key": "EST"})` both construct it.

    The positional loop handed `follow` an `ast.Starred` wrapper and the
    keyword loop handed it the whole `**` mapping; neither had a case, and the
    standalone scan ignores a bare ambiguous literal on purpose
    (Codex, PR #993).
    """
    legacy, _ = _hits('from zoneinfo import ZoneInfo\n'
                      'ET = ZoneInfo(*["EST"])\n')
    assert legacy, legacy

    legacy, _ = _hits('from zoneinfo import ZoneInfo\n'
                      'ET = ZoneInfo(**{"key": "EST"})\n')
    assert legacy, legacy

    # A container OUTSIDE a timezone context is untouched -- `follow` is only
    # reached once the call establishes one, which is what keeps this safe.
    legacy, _ = _hits('STOP_WORDS = ["EST", "GMT"]\n')
    assert not legacy, legacy


def test_a_numeric_dateutil_tzinfos_mapping_is_rejected():
    """`parse("...", tzinfos={"EST": -18000})` freezes the parse at UTC-5.

    python-dateutil is a declared dependency and this is its documented way to
    give an abbreviation a meaning. `parse` is not a timezone call, the key is
    an ambiguous literal the standalone scan ignores, and the value is a bare
    number -- so all three checks walked past it (Codex, PR #993).
    """
    _legacy, offsets = _hits(
        'from dateutil.parser import parse\n'
        'd = parse("2026-07-01 12:00 EST", tzinfos={"EST": -18000})\n')
    assert offsets, offsets
    assert "seconds" in offsets[0], (
        f"the unit dateutil documents for this mapping is seconds: {offsets}")

    # The value can also be a zone rather than a number.
    legacy, _ = _hits(
        'from dateutil.parser import parse\n'
        'from dateutil.tz import gettz\n'
        'd = parse("x", tzinfos={"EST": gettz("US/Eastern")})\n')
    assert legacy, legacy

    # An offset that is not Eastern is not this guard's business.
    _legacy, offsets = _hits(
        'from dateutil.parser import parse\n'
        'd = parse("x", tzinfos={"PST": -28800})\n')
    assert not offsets, offsets


def test_the_utc_prefixed_offset_is_caught_in_a_python_timezone_context():
    """`pd.Timestamp.now(tz="UTC-05:00")` is a fixed zone, unambiguously.

    The TEXT scan leaves this spelling alone on purpose and says why: in a
    shell `TZ` value POSIX inverts the sign, so `UTC-05:00` selects UTC+5.
    Reaching `follow` means the AST has already established the string as a
    timezone argument, where the ambiguity does not exist (Codex, PR #993).
    """
    _legacy, offsets = _hits('import pandas as pd\n'
                             't = pd.Timestamp.now(tz="UTC-05:00")\n')
    assert offsets, offsets

    _legacy, offsets = _hits('from zoneinfo import ZoneInfo\n'
                             'ET = ZoneInfo("UTC-04:00")\n')
    assert offsets, offsets

    # The sign still matters, and the TEXT scan is deliberately unchanged --
    # `export TZ=UTC-05:00` is UTC+5 and stays unmatched there.
    _legacy, offsets = _hits('import pandas as pd\n'
                             't = pd.Timestamp.now(tz="UTC+05:00")\n')
    assert not offsets, offsets
    assert not NONPY_FIXED_OFFSET.search("export TZ=UTC-05:00")


def test_a_split_yaml_env_pair_recognises_pgtz():
    """`- name: PGTZ` / `value: EST` is how a manifest sets it.

    Round 16 added `PGTZ` to the scalar contexts; the cross-line matcher that
    exists for exactly this Kubernetes and Cloud Run shape still accepted only
    `TZ`, `TIMEZONE` and `TIME_ZONE`, and the line-local regex cannot connect a
    key on one line to a value on the next (Codex, PR #993).
    """
    hits = _yaml_env_pair_hits("        - name: PGTZ\n          value: EST\n")
    assert hits, "a split PGTZ pair must be matched"
    assert hits[0][1] == "EST", hits

    # The keys it already knew still match, and an unrelated one still does not.
    assert _yaml_env_pair_hits("        - name: TZ\n          value: US/Eastern\n")
    assert not _yaml_env_pair_hits("        - name: REGION\n          value: EST\n")


def test_only_a_timezone_expansion_is_rewritten_to_its_default():
    """`echo ${MESSAGE:-TZ=EST}` prints text; it does not set a timezone.

    The expansion pass rewrote EVERY `${X:-...}` in the file before the context
    patterns ran, so an ordinary message default became `echo TZ=EST` and was
    reported as a process-timezone assignment -- a false CI failure on correct
    code, which is worse than a miss because it is red on someone else's PR
    (Codex, PR #993).

    Two halves, and the second is what actually closes it: narrowing the
    rewrite is not enough, because the raw line still carries the literal text
    `TZ=EST` inside the braces. Every non-timezone expansion is blanked.
    """
    def scanned(line: str) -> bool:
        text = _expand_shell_defaults(_strip_shell_comments(line))
        return bool(NONPY_AMBIGUOUS.search(text)
                    or NONPY_UNAMBIGUOUS.search(text))

    # False findings, gone.
    assert not scanned("echo ${MESSAGE:-TZ=EST}")
    assert not scanned("echo ${HELP:---time-zone EST}")
    assert not scanned("echo ${MSG:-US/Eastern is not set}")

    # Real ones, still found -- in every spelling the repository uses.
    assert scanned("TZ=${TZ:-EST}")
    assert scanned('TZ="${TZ:-EST}"')
    assert scanned("export TZ=${TZ:-US/Eastern}")
    assert scanned("--time-zone ${SCHED_TZ:-EST}")
    assert scanned("timezone: ${TZ:-EST}")

    # Blanking preserves width, so a line number and column still mean what
    # they say for everything after it on the same line.
    blanked = _expand_shell_defaults("echo ${MESSAGE:-TZ=EST}")
    assert len(blanked) == len("echo ${MESSAGE:-TZ=EST}"), repr(blanked)


# ── Round 18 (Codex, PR #993) ───────────────────────────────────────────────
#
# Twelve, up from seven. Eleven are compositions -- two alias forms chained, a
# constant named instead of written inline, a container where a scalar was
# expected -- which is what each round's fix creates more of. One is not: a
# commented-out example in a `.sql` file made the guard FAIL, the same class
# as round 17's shell expansion and the second false positive in two rounds.
#
# The trend is recorded in issue #1019, not argued here.


def test_sql_comments_are_not_executable_text():
    """`-- SET TIME ZONE 'EST'` in a migration is an explanation, not a zone.

    A tracked `.sql` file carrying the old spelling beside its replacement is
    the ordinary way a migration documents itself, and the guard failed on
    text that never runs. Preprocessing was gated solely on `_reads_as_shell`,
    which no `.sql` file matches (Codex, PR #993).
    """
    def scanned(text: str) -> bool:
        stripped = _strip_sql_comments(text)
        return bool(NONPY_AMBIGUOUS.search(stripped)
                    or NONPY_UNAMBIGUOUS.search(stripped)
                    or NONPY_FIXED_OFFSET.search(stripped))

    assert not scanned("-- SET TIME ZONE 'EST'")
    assert not scanned("/* SET TIME ZONE '-05:00' */")
    assert not scanned("-- old zone was US/Eastern")
    assert not scanned("/* multi\n   line US/Eastern */")

    # The executable statement is still a finding, including when a comment
    # sits on the same line after it.
    assert scanned("SET TIME ZONE 'EST';")
    assert scanned("SET TIME ZONE 'EST'; -- deliberate")

    # A `--` or `/*` INSIDE a string literal is data, not a comment, so the
    # stripper must not eat the rest of the statement.
    assert _strip_sql_comments("SELECT '-- x' AS a;") == "SELECT '-- x' AS a;"
    assert _strip_sql_comments("SELECT 'a/*b*/c';") == "SELECT 'a/*b*/c';"

    # Blanked, not deleted: line and column numbers survive.
    src = "SET TIME ZONE 'EST'; -- note\nSELECT 1;"
    out = _strip_sql_comments(src)
    assert len(out) == len(src) and out.count("\n") == src.count("\n")


def test_make_assignment_operators_are_contexts():
    """GNU Make writes `TZ := EST` and `TZ ?= EST`, and exports both.

    Makefiles were added to the collector to cover deployment configuration,
    and the context accepted only a bare `:` or `=` immediately after the key,
    so the operators Make actually uses left an extra character before the
    value (Codex, PR #993).
    """
    for line in ("export TZ := EST", "export TZ ?= EST", "TZ ::= EST",
                 "TZ += EST"):
        assert NONPY_AMBIGUOUS.search(line), line

    # The spellings that already worked still do, and the identifier boundary
    # that keeps `quartz=EST` clean is unaffected.
    assert NONPY_AMBIGUOUS.search("TZ=EST")
    assert NONPY_AMBIGUOUS.search("TZ: EST")
    assert not NONPY_AMBIGUOUS.search("quartz=EST")


def test_a_shell_scalar_reaches_a_timezone_assignment():
    """`LEGACY=EST` then `export TZ="$LEGACY"` installs the frozen zone.

    The first assignment has no timezone context and the second has no
    literal, so each half looked innocent -- the same shape as the bound SQL
    parameter, in shell (Codex, PR #993).

    Resolved only where a timezone context sits immediately in front of the
    reference, which is the anchoring the parameter-default expansion already
    uses; substituting every `$VAR` in a file is how that pass came to report
    `echo ${MESSAGE:-TZ=EST}`.
    """
    def scanned(text: str) -> bool:
        out = _expand_shell_defaults(_strip_shell_comments(text))
        return bool(NONPY_AMBIGUOUS.search(out)
                    or NONPY_UNAMBIGUOUS.search(out))

    assert scanned('LEGACY=EST\nexport TZ="$LEGACY"\n')
    assert scanned('LEGACY="US/Eastern"\nexport TZ=${LEGACY}\n')

    # A reference OUTSIDE a timezone context is not substituted, a benign
    # value stays benign, and an unknown name resolves to nothing.
    assert not scanned('LEGACY=EST\necho "$LEGACY"\n')
    assert not scanned('GOOD=America/New_York\nexport TZ="$GOOD"\n')
    assert not scanned('export TZ="$UNKNOWN"\n')


def test_the_postgres_interval_form_is_a_fixed_offset():
    """`SET TIME ZONE INTERVAL '-05:00' HOUR TO MINUTE` is a frozen session.

    `_TZ_CONTEXT` reached the statement and then `INTERVAL` sat between it and
    the value, so the offset matcher expected the number immediately and the
    numeric matcher rejected the keyword (Codex, PR #993).
    """
    assert NONPY_FIXED_OFFSET.search(
        "SET TIME ZONE INTERVAL '-05:00' HOUR TO MINUTE")
    assert NONPY_FIXED_OFFSET.search("SET LOCAL TIME ZONE INTERVAL '-04:00'")
    # The forms that already worked are unchanged.
    assert NONPY_FIXED_OFFSET.search("SET TIME ZONE '-05:00'")
    assert NONPY_SQL_NUMERIC_OFFSET.search("SET TIME ZONE -5")


def test_an_import_alias_is_resolved_at_every_hop():
    """`from zoneinfo import ZoneInfo as Z; make_zone = Z; make_zone("EST")`.

    The two alias forms were fixed separately -- imports in round 13,
    assignments in round 15 -- and composing them still failed, because the
    import map was consulted once before the recursion rather than at each
    hop, so the chain terminated on the unrecognised `Z` (Codex, PR #993).
    """
    legacy, _ = _hits('from zoneinfo import ZoneInfo as Z\n'
                      'make_zone = Z\n'
                      'ET = make_zone("EST")\n')
    assert legacy, legacy

    # The reverse composition, and a longer chain.
    legacy, _ = _hits('import pytz as p\n'
                      'mod = p\n'
                      'ET = mod.timezone("EST")\n')
    assert legacy, legacy

    # An alias chain with no timezone at the end of it is still nothing.
    legacy, _ = _hits('from mymodule import lookup as L\n'
                      'get = L\n'
                      'row = get("EST")\n')
    assert not legacy, legacy


def test_a_named_query_still_joins_its_bound_parameter():
    """`QUERY = "SET TIME ZONE %s"; cur.execute(QUERY, ("EST",))`.

    Naming the statement is the ordinary way this gets written, and the branch
    required the text inline, so the context and the value were never joined
    (Codex, PR #993).
    """
    legacy, _ = _hits('QUERY = "SET TIME ZONE %s"\n'
                      'cur.execute(QUERY, ("EST",))\n')
    assert legacy, legacy

    # A named query with no timezone context still does not convict its
    # parameters.
    legacy, _ = _hits('Q = "SELECT %s"\ncur.execute(Q, ("EST",))\n')
    assert not legacy, legacy


def test_an_unpacked_offset_constructor_argument_is_read():
    """`pytz.FixedOffset(*[-300])` and `FixedOffset(**{"offset": -300})`.

    The numeric branch handed the `Starred` wrapper or the whole dict to
    `_const_number`, which reports None for both, and the generic container
    descent added a round earlier cannot stand in: by the time it reaches
    `-300` it has lost the constructor that says the unit is minutes
    (Codex, PR #993).
    """
    _legacy, offsets = _hits('import pytz\nET = pytz.FixedOffset(*[-300])\n')
    assert offsets, offsets

    _legacy, offsets = _hits(
        'import pytz\nET = pytz.FixedOffset(**{"offset": -300})\n')
    assert offsets, offsets

    _legacy, offsets = _hits(
        'from dateutil.tz import tzoffset\nET = tzoffset(*[None, -18000])\n')
    assert offsets, offsets

    # A non-Eastern offset is still not a finding, and a splat this cannot
    # resolve statically is left alone rather than guessed at.
    _legacy, offsets = _hits('import pytz\nTZ = pytz.FixedOffset(*[90])\n')
    assert not offsets, offsets
    _legacy, offsets = _hits('import pytz\n'
                             'def f(*a):\n'
                             '    return pytz.FixedOffset(*a)\n')
    assert not offsets, offsets


def test_a_numeric_parameter_default_is_a_binding():
    """`def build(offset=-300): return pytz.FixedOffset(offset)`.

    Round 16 taught the ASSIGNMENT map to keep a resolvable number so an
    offset constructor could read it. `_parameter_bindings`, whose docstring
    claims to keep "the same kinds", was not updated -- so the two maps
    disagreed about what a binding is (Codex, PR #993).
    """
    _legacy, offsets = _hits('import pytz\n'
                             'def build(offset=-300):\n'
                             '    return pytz.FixedOffset(offset)\n')
    assert offsets, offsets

    _legacy, offsets = _hits('from dateutil.tz import tzoffset\n'
                             'def build(sec=-18000):\n'
                             '    return tzoffset(None, sec)\n')
    assert offsets, offsets

    _legacy, offsets = _hits('from datetime import timedelta, timezone\n'
                             'def build(hours=-5):\n'
                             '    return timezone(timedelta(hours=hours))\n')
    assert offsets, offsets

    # A default that is not Eastern is not a finding.
    _legacy, offsets = _hits('import pytz\n'
                             'def build(offset=90):\n'
                             '    return pytz.FixedOffset(offset)\n')
    assert not offsets, offsets


def test_an_environment_update_is_inspected():
    """`os.environ.update([("TZ", "EST")])` installs the process zone.

    `update` takes a mapping or an iterable of pairs, and neither reached the
    two-positional setter branch; a `("TZ", "EST")` tuple is not an
    `ast.Dict`, so the dict-literal branch missed it too (Codex, PR #993).
    """
    legacy, _ = _hits('import os\nos.environ.update([("TZ", "EST")])\n')
    assert legacy, legacy

    legacy, _ = _hits('import os\nos.environ.update({"TZ": "US/Eastern"})\n')
    assert legacy, legacy

    legacy, _ = _hits('import os\n'
                      'ENV = [("TZ", "EST")]\n'
                      'os.environ.update(ENV)\n')
    assert legacy, legacy

    # A non-timezone key is not a timezone.
    legacy, _ = _hits('d = {}\nd.update([("REGION", "EST")])\n')
    assert not legacy, legacy


def test_a_named_tzinfos_mapping_is_resolved():
    """`INFOS = {"EST": -18000}; parse("...", tzinfos=INFOS)`.

    The keyword branch accepted only an inline dict, though a mapping like
    this is exactly the kind of constant that gets named and reused
    (Codex, PR #993).
    """
    _legacy, offsets = _hits('from dateutil.parser import parse\n'
                             'INFOS = {"EST": -18000}\n'
                             'd = parse("x", tzinfos=INFOS)\n')
    assert offsets, offsets

    _legacy, offsets = _hits('from dateutil.parser import parse\n'
                             'INFOS = {"PST": -28800}\n'
                             'd = parse("x", tzinfos=INFOS)\n')
    assert not offsets, offsets


def test_a_constant_string_expression_is_folded():
    """`ZoneInfo("E" + "ST")` builds the forbidden zone.

    Every matcher reads a single `ast.Constant` and the standalone walk sees
    only harmless fragments. The numeric side has folded arithmetic since
    round 15 for exactly this reason (Codex, PR #993).
    """
    legacy, _ = _hits('from zoneinfo import ZoneInfo\nET = ZoneInfo("E" + "ST")\n')
    assert legacy, legacy

    legacy, _ = _hits('from zoneinfo import ZoneInfo\n'
                      'ET = ZoneInfo("US/" + "Eastern")\n')
    assert legacy, legacy

    # Through a name, since the fold and the indirection have to compose.
    legacy, _ = _hits('from zoneinfo import ZoneInfo\n'
                      'Z = "US/" + "Eastern"\n'
                      'ET = ZoneInfo(Z)\n')
    assert legacy, legacy

    # A concatenation that spells something else is not a zone. This is the
    # case that makes folding safe rather than noisy.
    legacy, _ = _hits('msg = "E" + "STIMATE"\n')
    assert not legacy, legacy

    assert _const_string(ast.parse('"E" + "ST"', mode="eval").body) == "EST"
    assert _const_string(ast.parse('"E" + x', mode="eval").body) is None


def test_a_loop_target_takes_the_values_it_iterates():
    """`for zone in ("EST",): ZoneInfo(zone)` constructs the frozen zone.

    The scope machinery marked the target as shadowing an inherited name --
    correctly -- and then bound it to nothing, so the call resolved to nothing
    while the ambiguous literal stayed ignored outside a call context
    (Codex, PR #993).
    """
    legacy, _ = _hits('from zoneinfo import ZoneInfo\n'
                      'for zone in ("EST",):\n'
                      '    ET = ZoneInfo(zone)\n')
    assert legacy, legacy

    legacy, _ = _hits('from zoneinfo import ZoneInfo\n'
                      'zs = [ZoneInfo(zone) for zone in ("EST",)]\n')
    assert legacy, legacy

    # A literal iterable OUTSIDE a timezone context is still nothing: the
    # binding is only ever read by a branch that already has one.
    legacy, _ = _hits('stop = []\n'
                      'for w in ("EST", "GMT"):\n'
                      '    stop.append(w)\n')
    assert not legacy, legacy

    # A computed iterable is not statically known and is left unresolved.
    legacy, _ = _hits('from zoneinfo import ZoneInfo\n'
                      'for zone in load_zones():\n'
                      '    ET = ZoneInfo(zone)\n')
    assert not legacy, legacy


# ── Round 19 (Codex, PR #993) ───────────────────────────────────────────────
#
# FOUR of the seven are FALSE findings -- the guard failing on correct code --
# and one of those is a regression I introduced in round 18. That ratio is the
# round's real result: the checks are now producing wrong answers faster than
# they are closing real gaps, which is the argument issue #1019 makes for
# replacing enumeration with a runtime assertion.


def test_a_shell_scalar_resolves_to_the_value_in_force():
    """A shell script runs in order, so a rebinding after an export is later.

    `_shell_scalars` kept only the LAST value of a name, and both halves of
    that were wrong (Codex, PR #993). A regression from round 16's own fix,
    and the same ordering mistake `_arrays_carrying_timezone` already records.
    """
    def scanned(text: str) -> bool:
        out = _expand_shell_defaults(_strip_shell_comments(text))
        return bool(NONPY_AMBIGUOUS.search(out)
                    or NONPY_UNAMBIGUOUS.search(out))

    # The export really does install the frozen zone; a later rebinding does
    # not reach back in time to fix it.
    assert scanned('LEGACY=EST\nexport TZ="$LEGACY"\nLEGACY=America/New_York\n')

    # And the reverse must not INVENT a finding on a script that exports the
    # canonical zone and only later reuses the name for something else.
    assert not scanned(
        'LEGACY=America/New_York\nexport TZ="$LEGACY"\nLEGACY=EST\n')

    # A name still unbound where it is referenced resolves to nothing.
    assert not scanned('export TZ="$LEGACY"\nLEGACY=EST\n')

    scalars = _shell_scalars('A=one\nA=two\n')
    assert [v for _, v, _ in scalars["A"]] == ["one", "two"], scalars
    assert _scalar_in_force(scalars, "A", 0) is None
    assert _scalar_in_force(scalars, "A", 6) == "one"
    assert _scalar_in_force(scalars, "A", 99) == "two"


def test_embedded_sql_comments_are_stripped_too():
    """Python source carries SQL, and SQL carries its comments with it.

    A migration written as a string that documents the change it makes --
    the old spelling commented above the new one -- had its commented half
    reported. The `.sql` files got comment stripping a round earlier and the
    embedded copies did not (Codex, PR #993).
    """
    legacy, _ = _hits(
        'QUERY = "-- Old: SET TIME ZONE \'EST\'\\n'
        'SET TIME ZONE \'America/New_York\'"\n')
    assert not legacy, legacy

    _legacy, offsets = _hits(
        'Q = "/* was AT TIME ZONE \'-05:00\' */ '
        'SELECT ts AT TIME ZONE \'America/New_York\'"\n')
    assert not offsets, offsets

    # An UNCOMMENTED embedded violation is still a finding -- this branch
    # exists for exactly that, and stripping must not disarm it.
    legacy, _ = _hits('Q = "SELECT ts AT TIME ZONE \'US/Eastern\'"\n')
    assert legacy, legacy


def test_a_shell_diagnostic_is_not_a_setting():
    """`echo 'set TZ=EST to reproduce'` prints text; it sets nothing.

    A usage message or a reproduction hint routinely quotes the very setting
    this guard forbids, and the context patterns read the quoted text as an
    assignment or a flag (Codex, PR #993).
    """
    def scanned(text: str) -> bool:
        out = _expand_shell_defaults(_strip_shell_comments(text))
        return bool(NONPY_AMBIGUOUS.search(out)
                    or NONPY_UNAMBIGUOUS.search(out)
                    or NONPY_FIXED_OFFSET.search(out))

    assert not scanned("echo 'set TZ=EST to reproduce'")
    assert not scanned('printf "--time-zone EST\\n"')
    assert not scanned('die "TZ=US/Eastern is not supported"')
    assert not scanned("echo 'usage: --time-zone ${TZ:-EST}'")

    # Everything that really does set or pass a zone still reports.
    assert scanned("export TZ=EST")
    assert scanned("TZ=EST date")
    assert scanned("--time-zone EST")
    assert scanned("gcloud scheduler jobs create http j --time-zone EST")
    # An UNQUOTED argument is not blanked: the narrowing is to quoted text
    # after an output command, not to the command itself.
    assert not scanned("echo $TZ")


def test_a_typed_scheduler_flag_array_is_recognised():
    """`local -a flags=(--time-zone America/New_York)` is the careful spelling.

    The array pattern permitted only an optional bare `local`, so a helper
    that TYPES its array recorded no array at all and every command expanding
    it was reported as zoneless -- a false CI failure aimed at the compliant
    form (Codex, PR #993).
    """
    call = 'gcloud scheduler jobs create http j "${flags[@]}"\n'
    for decl in ('flags=(--time-zone America/New_York)',
                 'local flags=(--time-zone America/New_York)',
                 'local -a flags=(--time-zone America/New_York)',
                 'declare -a flags=(--time-zone America/New_York)',
                 'readonly flags=(--time-zone America/New_York)',
                 'export -a flags=(--time-zone America/New_York)'):
        assert not _scheduler_offenders("f", decl + "\n" + call), decl

    # A zoneless array is still an offender, whichever way it is declared, so
    # widening the pattern did not turn the check off.
    assert _scheduler_offenders(
        "f", 'local -a flags=(--uri https://x)\n' + call)


def test_a_constant_f_string_is_folded():
    """`ZoneInfo(f"{'EST'}")` builds the forbidden zone.

    An f-string is an `ast.JoinedStr`, which the concatenation fold added a
    round earlier did not recognise, and the inner fragment is ignored outside
    its call context (Codex, PR #993).
    """
    legacy, _ = _hits('from zoneinfo import ZoneInfo\n'
                      'ET = ZoneInfo(f"{\'EST\'}")\n')
    assert legacy, legacy

    legacy, _ = _hits('from zoneinfo import ZoneInfo\n'
                      'ET = ZoneInfo(f"US/{\'Eastern\'}")\n')
    assert legacy, legacy

    # A runtime value makes the whole thing undecidable, which is the same
    # contract the numeric fold keeps.
    legacy, _ = _hits('from zoneinfo import ZoneInfo\n'
                      'ET = ZoneInfo(f"{name}")\n')
    assert not legacy, legacy

    # And a constant f-string that spells something else is not a zone.
    legacy, _ = _hits('msg = f"{\'E\'}STIMATE"\n')
    assert not legacy, legacy


def test_a_notebook_shell_escape_is_scanned():
    """`!TZ=EST date` and a `%%bash` body execute; blanking them hid both.

    Round 16 taught the magic pass to keep the Python a line magic runs. The
    SHELL escapes were still discarded, so the cell parsed as empty Python and
    no text reached the regex fallback either (Codex, PR #993).
    """
    def probe(cells):
        nb = json.dumps({"cells": [{"cell_type": "code", "source": c}
                                   for c in cells]})
        _legacy, _offsets, rest = _notebook_hits(
            REPO / "notebooks" / "_probe.ipynb", nb)
        return rest

    assert NONPY_AMBIGUOUS.search(probe([["!TZ=EST date\n"]]))
    assert NONPY_AMBIGUOUS.search(
        probe([["%%bash\n", "export TZ=EST\n", "date\n"]]))

    # A clean shell cell reports nothing, and an ordinary `!pip install` is
    # not a timezone.
    rest = probe([["%%bash\n", "export TZ=America/New_York\n"]])
    assert not NONPY_AMBIGUOUS.search(rest)
    assert not NONPY_AMBIGUOUS.search(probe([["!pip install pandas\n"]]))

    # The body is handed over ONCE. It used to arrive twice -- collected as
    # shell and again as an unparseable cell -- which is a duplicate finding
    # rather than a wrong one, but still a wrong count.
    rest = probe([["%%bash\n", "export TZ=EST\n"]])
    assert rest.count("export TZ=EST") == 1, rest

    # And a `%%time` cell is Python, so its body stays on the parse path.
    nb = json.dumps({"cells": [{"cell_type": "code", "source": [
        "%%time\n", "from datetime import timezone, timedelta\n",
        "ET = timezone(timedelta(hours=-5))\n"]}]})
    _legacy, offsets, _rest = _notebook_hits(
        REPO / "notebooks" / "_probe.ipynb", nb)
    assert offsets, offsets


def test_a_yaml_env_entry_survives_an_intervening_comment():
    """`- name: TZ` / `# explanation` / `value: EST` is one entry.

    The cross-line matcher required `value:` on the immediately following
    line, so the DOCUMENTED entry was the one that got through
    (Codex, PR #993).
    """
    assert _yaml_env_pair_hits(
        "        - name: TZ\n"
        "          # the app expects Eastern\n"
        "          value: EST\n")
    assert _yaml_env_pair_hits(
        "        - name: TZ\n          # why\n\n          value: EST\n")

    # It must not reach across into a sibling entry: a canonical TZ followed
    # by an unrelated key holding `EST` is not a finding.
    assert not _yaml_env_pair_hits(
        "        - name: TZ\n          value: America/New_York\n"
        "        - name: OTHER\n          value: EST\n")
    # But a later entry that IS bad is still found.
    assert _yaml_env_pair_hits(
        "        - name: OK\n          value: America/New_York\n"
        "        - name: TZ\n          value: EST\n")


# ── Round 20 (Codex, PR #993) ───────────────────────────────────────────────
#
# FIVE of the eight are FALSE findings, and two of those were created by the
# two rounds immediately before this one. That is the point at which adding
# spellings stops paying: the guard is now wrong more often than it is
# incomplete, and each fix widens the surface for the next mistake. The two
# genuine gaps this round found are recorded on issue #1019 rather than fixed
# here -- see the comment at the end of this section.


def test_a_python_string_is_only_scanned_as_sql():
    """`logger.info("...US/Eastern...")` documents; it does not configure.

    This branch exists because Python source carries SQL, and it was feeding
    EVERY string constant to the non-Python matchers -- so a migration note
    and a reproduction hint failed the guard on text that constructs nothing.
    The shell path already blanks its diagnostics; this is the Python side of
    the same rule (Codex, PR #993).
    """
    legacy, _ = _hits(
        'logger.info("The old setting was US/Eastern; it has been migrated")\n')
    assert not legacy, legacy

    legacy, _ = _hits('print("To reproduce, set TZ=EST")\n')
    assert not legacy, legacy

    legacy, _ = _hits('def f():\n    """Was US/Eastern before the migration."""\n')
    assert not legacy, legacy

    # A real embedded STATEMENT is still read, which is what the branch is
    # for -- in all three of its SQL spellings.
    legacy, _ = _hits('Q = "SELECT ts AT TIME ZONE \'US/Eastern\' FROM t"\n')
    assert legacy, legacy
    legacy, _ = _hits('Q = "SET TIME ZONE \'EST\'"\n')
    assert legacy, legacy
    _legacy, offsets = _hits('Q = "SELECT ts AT TIME ZONE \'-05:00\'"\n')
    assert offsets, offsets

    # And a zone reaching a timezone API, or standing alone as a constant, is
    # caught by the branches that exist for those -- narrowing this one does
    # not open a hole.
    legacy, _ = _hits('from zoneinfo import ZoneInfo\nET = ZoneInfo("US/Eastern")\n')
    assert legacy, legacy
    legacy, _ = _hits('ZONES = ["US/Eastern"]\n')
    assert legacy, legacy


def test_a_fractional_offset_is_not_truncated_into_eastern():
    """`FixedOffset(-300.5)` is UTC-05:00:30, which is not Eastern.

    `int(-300.5)` is `-300`, so a valid non-Eastern zone was reported as
    forbidden -- the guard failing CI on correct code (Codex, PR #993).
    """
    _legacy, offsets = _hits('import pytz\nTZ = pytz.FixedOffset(-300.5)\n')
    assert not offsets, offsets

    _legacy, offsets = _hits(
        'from dateutil.tz import tzoffset\nTZ = tzoffset(None, -18000.5)\n')
    assert not offsets, offsets

    _legacy, offsets = _hits(
        'from dateutil.parser import parse\n'
        'd = parse("x", tzinfos={"EST": -18000.5})\n')
    assert not offsets, offsets

    _legacy, offsets = _hits(
        'from datetime import timedelta, timezone\n'
        'TZ = timezone(timedelta(seconds=-18000, microseconds=-500000))\n')
    assert not offsets, offsets

    # A float that IS the integer still reports, so this did not turn the
    # check off -- and `timedelta`'s microsecond scaling still rounds, which
    # is why that one keeps a tolerance rather than comparing exactly.
    _legacy, offsets = _hits('import pytz\nET = pytz.FixedOffset(-300.0)\n')
    assert offsets, offsets
    _legacy, offsets = _hits('from datetime import timedelta, timezone\n'
                             'ET = timezone(timedelta(hours=-5))\n')
    assert offsets, offsets


def test_an_included_make_fragment_is_preprocessed():
    """`# export TZ := EST` in `rules.mk` is a comment, as it is in a Makefile.

    `_source_files` collects `*.mk` and `_reads_as_shell` did not classify it,
    so the identical line failed in one file and passed in the other -- a
    difference with no reason behind it, created by teaching the context
    matcher Make's `:=` one round earlier (Codex, PR #993).
    """
    assert _reads_as_shell(pathlib.Path("rules.mk"))
    assert _reads_as_shell(pathlib.Path("Makefile"))
    assert not _reads_as_shell(pathlib.Path("notes.md"))

    assert not NONPY_AMBIGUOUS.search(
        _strip_shell_comments("# export TZ := EST"))
    assert NONPY_AMBIGUOUS.search(
        _strip_shell_comments("export TZ := EST"))


def test_a_hash_inside_a_word_is_not_a_comment():
    """`${path#*/}` uses `#` as an operator, and the line keeps running.

    Cutting at every unquoted `#` deleted the parameter expansion and
    everything after it -- including a real `export TZ=EST` following a `;` --
    so the scanner removed the assignment it exists to find (Codex, PR #993).
    """
    kept = _strip_shell_comments('trimmed=${path#*/}; export TZ=EST')
    assert "export TZ=EST" in kept, kept
    assert NONPY_AMBIGUOUS.search(kept)

    # A `#` that really does start a word still starts a comment, inline and
    # on a line of its own.
    assert _strip_shell_comments("export TZ=EST # why") == "export TZ=EST"
    assert _strip_shell_comments("# export TZ=EST").strip() == ""
    assert _strip_shell_comments("run;# note") == "run;"
    # And a `#` inside a quoted string is still data.
    assert _strip_shell_comments('msg="#tag"') == 'msg="#tag"'


def test_an_unambiguous_zone_needs_a_left_boundary_too():
    """`/api/status/eastern` is a URL, not `US/Eastern`.

    Only the right-hand boundary was guarded, so the case-insensitive
    alternative matched the tail of an ordinary path (Codex, PR #993).
    """
    assert not NONPY_UNAMBIGUOUS.search("/api/status/eastern")
    assert not NONPY_UNAMBIGUOUS.search("BUS/Eastern")
    assert not NONPY_UNAMBIGUOUS.search("https://x/plus/eastern")

    # Every spelling that really is the zone still matches.
    assert NONPY_UNAMBIGUOUS.search("US/Eastern")
    assert NONPY_UNAMBIGUOUS.search("tz = 'US/Eastern'")
    assert NONPY_UNAMBIGUOUS.search("export TZ=US/Eastern")
    assert NONPY_UNAMBIGUOUS.search('{"tz": "US/Eastern"}')


def test_the_string_fold_resolves_names_without_double_reporting():
    """`PREFIX = "E"; ZoneInfo(PREFIX + "ST")` -- both halves at once.

    Round 19 dropped the environment from the fold to stop the
    module-settings pass reporting a resolved value twice, and that lost the
    binding-plus-literal composition. Both properties hold now: only a
    COMPOSITE expression is folded here (a bare name is left to the
    indirection branch, which labels the finding with its provenance), and
    every constant the fold consumed is marked reported so the settings pass
    does not see it again (Codex, PR #993).
    """
    legacy, _ = _hits('from zoneinfo import ZoneInfo\n'
                      'PREFIX = "E"\n'
                      'ET = ZoneInfo(PREFIX + "ST")\n')
    assert legacy, legacy

    # One finding, not two -- the property round 19 was protecting.
    legacy, offsets = _hits_all('from zoneinfo import ZoneInfo\n'
                                'TIME_ZONE = "EST"\n'
                                'ET = ZoneInfo(TIME_ZONE)\n')
    assert len(legacy + offsets) == 1, legacy + offsets

    # And the provenance label survives: a bare name is still resolved by the
    # branch that names it, not folded anonymously.
    legacy, _ = _hits('from zoneinfo import ZoneInfo\n'
                      'Z = "US/" + "Eastern"\n'
                      'ET = ZoneInfo(Z)\n')
    assert legacy and "Z (=" in legacy[0], legacy


# Two findings from this round are NOT fixed here, and the reason is the
# round's own arithmetic rather than a judgement about the findings:
#
#   * a tuple-destructuring binding -- `TZ, fallback = ("EST", "UTC")`
#   * a constant subscript into a known mapping -- `ZONES["primary"]`
#
# Both are real, both are more ways to reach a value this file already
# understands, and both would add another resolver to compose with the eleven
# already here. Rounds 18-20 added nine such resolvers and produced nine false
# findings, five of them in this round alone; the marginal spelling is now
# costing more than it catches. They are recorded on issue #1019, with the
# runtime assertion that would settle the whole class by construction instead
# of by enumeration.


# ── Round 21 (Codex, PR #993) ───────────────────────────────────────────────
#
# Six findings and not one of them is another spelling: two false findings, one
# real miss created by the previous round's false-positive fix, and three about
# a single test -- one of which could destroy a developer's untracked file.
# That last one is the most serious thing this review has surfaced, and it is
# in the harness rather than in the guard.


def test_a_fixed_zone_name_needs_a_left_boundary_too():
    """`IMAGE_TAG=latest5` is a tag, not the POSIX zone `EST5`.

    `NONPY_UNAMBIGUOUS` got a left boundary last round and this sibling did
    not, so the `EST5` alternative matched inside an ordinary word and failed
    the offset guard on text with no timezone in it (Codex, PR #993).
    """
    assert not NONPY_FIXED_ZONE.search("IMAGE_TAG=latest5")
    assert not NONPY_FIXED_ZONE.search("echo LATEST5")
    assert not NONPY_FIXED_ZONE.search("BEDT4")

    # The real zone still matches, quoted or bare.
    assert NONPY_FIXED_ZONE.search("TZ=EST5")
    assert NONPY_FIXED_ZONE.search("tzstr('EST5')")
    assert NONPY_FIXED_ZONE.search('TZ="Etc/GMT+5"')


def test_every_quoted_diagnostic_argument_is_blanked():
    """`printf '%s\\n' 'TZ=EST'` puts the data in the SECOND argument.

    The previous version blanked only the first quoted argument -- the format
    string -- and left the data to be read as an assignment (Codex, PR #993).
    """
    def scanned(text: str) -> bool:
        out = _expand_shell_defaults(_strip_shell_comments(text))
        return bool(NONPY_AMBIGUOUS.search(out)
                    or NONPY_UNAMBIGUOUS.search(out))

    assert not scanned("printf '%s\\n' 'TZ=EST'")
    assert not scanned("echo 'prefix' 'TZ=EST'")
    assert not scanned("log 'using' 'TZ=US/Eastern' 'today'")
    # The single-argument case the previous round fixed still holds.
    assert not scanned("echo 'set TZ=EST to reproduce'")


def test_redirected_output_is_configuration_not_a_diagnostic():
    """`echo 'TZ=EST' > app.env` writes a file that is then sourced.

    Blanking every matching command regardless of where its output went hid a
    real assignment -- the previous round's false-positive fix creating a miss
    (Codex, PR #993).
    """
    def scanned(text: str) -> bool:
        out = _expand_shell_defaults(_strip_shell_comments(text))
        return bool(NONPY_AMBIGUOUS.search(out)
                    or NONPY_UNAMBIGUOUS.search(out))

    assert scanned("echo 'TZ=EST' > /tmp/app.env")
    assert scanned("echo 'TZ=EST' >> /tmp/app.env")
    assert scanned("echo 'TZ=EST' | tee /tmp/app.env")
    assert scanned("printf 'TZ=%s\\n' 'US/Eastern' > app.env")

    # Output with nowhere to go is still a diagnostic.
    assert not scanned("echo 'set TZ=EST to reproduce'")
    assert not scanned('die "TZ=US/Eastern is not supported"')


def test_the_tracked_files_probe_cannot_clobber_local_work():
    """The harness must not delete a file it did not create.

    `test_the_scan_reads_only_tracked_files` wrote a FIXED path in the
    repository root and unlinked it in `finally`, so running the suite with a
    developer's own file of that name present destroyed it (Codex, PR #993).
    Asserted on the source, because the failure mode is what the test does
    rather than what it concludes.
    """
    source = pathlib.Path(__file__).read_text()
    body = source[source.index("def test_the_scan_reads_only_tracked_files"):]
    body = body[:body.index("\ndef test_", 1)]

    assert "uuid.uuid4()" in body, (
        "the probe path must be unique per run, not a fixed name another "
        "file could already occupy")
    assert "assert not scratch.exists()" in body, (
        "the test must refuse to run rather than overwrite an existing file")
    assert "missing_ok=True" in body, body
    # And it must not re-run the repository scan for a question about the
    # collector: `_scan` is cached so the suite pays ~43s for it once.
    assert "_scan.cache_clear()" not in body, (
        "clearing the cache here doubles the guard's runtime")
    assert "_source_files()" in body, body
    # ...nor fail in the source-export environment the collector documents.
    assert "pytest.skip" in body and "_tracked_files()" in body, body


# ── Round 22 (Codex, PR #993) ───────────────────────────────────────────────
#
# Two fixed here: a regression the round-20 left boundary introduced, and an
# asymmetry in a loop that round rewrote. The other four findings are new
# spellings in new contexts and are recorded on issue #1019 -- see the note at
# the end of this section.


def test_a_zone_name_after_a_path_separator_still_matches():
    """`TZ=:/usr/share/zoneinfo/US/Eastern` installs the legacy zone.

    The left boundary added in round 20 excluded `/` along with the
    alphanumerics, which rejected the Linux zone-FILE spelling -- a real way
    to set the variable -- while the cases it exists for do not need it: the
    character before `us/eastern` in `status/eastern` is `t`, and in
    `BUS/Eastern` it is `B` (Codex, PR #993).
    """
    assert NONPY_UNAMBIGUOUS.search("TZ=:/usr/share/zoneinfo/US/Eastern")
    assert NONPY_FIXED_ZONE.search("TZ=/usr/share/zoneinfo/Etc/GMT+5")

    # The round-20 cases still hold, which is what makes dropping `/` safe.
    assert not NONPY_UNAMBIGUOUS.search("/api/status/eastern")
    assert not NONPY_UNAMBIGUOUS.search("BUS/Eastern")
    assert not NONPY_UNAMBIGUOUS.search("https://x/plus/eastern")
    assert not NONPY_FIXED_ZONE.search("IMAGE_TAG=latest5")


def test_embedded_sql_is_scanned_for_a_numeric_offset():
    """`cur.execute("SET TIME ZONE -5")` is the same statement as in a file.

    `NONPY_SQL_NUMERIC_OFFSET` was applied to standalone `.sql` files and not
    to the same statement carried in the Python that runs it, so moving the
    query inline walked past the guard (Codex, PR #993).
    """
    _legacy, offsets = _hits('cur.execute("SET TIME ZONE -5")\n')
    assert offsets, offsets

    _legacy, offsets = _hits('Q = "SET LOCAL TIME ZONE -4;"\ncur.execute(Q)\n')
    assert offsets, offsets

    # Confined to the SQL statement forms, exactly as in the file scan: a bare
    # negative number in a query is not a timezone.
    _legacy, offsets = _hits('cur.execute("SELECT -5")\n')
    assert not offsets, offsets
    # And POSIX inverts the sign in a TZ value, so that spelling stays out.
    assert not NONPY_SQL_NUMERIC_OFFSET.search("export TZ=-5")


# Four findings from this round are NOT fixed here, for the reason recorded on
# issue #1019 and in the round-20 note above. All four are new spellings in
# contexts the analyzer does not model, and each needs its own matcher:
#
#   * YAML argv arrays -- `args: ["--time-zone", "EST"]`, where the flag and
#     its value are separate list elements
#   * PostgreSQL's GUC assignment spelling -- `SET LOCAL timezone TO '-5'`,
#     `SET TIMEZONE = -4`
#   * libpq connection options -- `connect(options="-c timezone=EST")`, and
#     the same string through SQLAlchemy's `connect_args`
#   * Pine's POSITIONAL timezone argument -- `time(timeframe.period, session,
#     "EST")`
#
# The libpq one is the most defensible of the four, since it is a live
# alternative to `PGTZ` in a repository that uses psycopg2. It is on #1019
# with the others rather than fixed here, because the runtime assertion
# proposed there covers the whole class -- every one of these ends in a real
# zone object being constructed or a real session being configured -- and
# rounds 18-21 measured what each additional matcher costs.


# ── Round 23 (Codex, PR #993) ───────────────────────────────────────────────
#
# Four fixed, three deferred. Two of the four are the shell text handling
# destroying or misreading the very line it exists to scan, one is a scope
# splitter that silently disabled the scheduler check for top-level commands,
# and one is a false CI failure on correctly wrapped shell.


def test_an_escaped_quote_does_not_end_the_quoted_string():
    """`printf "literal \\" # still quoted"; export TZ=EST` runs the export.

    The comment stripper treated the escaped quote as the CLOSING one, took
    the following `#` for a comment, and deleted the rest of the line --
    including the real assignment after the `;`. The same shape as the
    `${path#*/}` finding one round earlier, in the same function
    (Codex, PR #993).
    """
    kept = _strip_shell_comments(
        'printf "literal \\" # still quoted"; export TZ=EST')
    assert "export TZ=EST" in kept, kept
    assert NONPY_AMBIGUOUS.search(kept)

    # Single quotes take no escapes in shell, so a backslash inside them is
    # an ordinary character and must not start an escape.
    assert _strip_shell_comments("a='x\\'; export TZ=EST") == "a='x\\'; export TZ=EST"

    # Real comments are still cut, in all three positions.
    assert _strip_shell_comments("export TZ=EST # why") == "export TZ=EST"
    assert _strip_shell_comments("# export TZ=EST").strip() == ""
    assert _strip_shell_comments("run;# note") == "run;"


def test_a_quoted_redirect_character_is_not_a_redirect():
    """`echo 'Never set TZ=EST | use America/New_York'` only prints.

    The redirect check searched the raw text, found the `|` inside the quoted
    prose, concluded the line was writing configuration, and left the
    argument to be reported as a setting (Codex, PR #993).

    I named this failure shape in the thread where the redirect check went in
    and did not close it. The operator has to be outside quotes to mean
    anything.
    """
    def scanned(text: str) -> bool:
        out = _expand_shell_defaults(_strip_shell_comments(text))
        return bool(NONPY_AMBIGUOUS.search(out)
                    or NONPY_UNAMBIGUOUS.search(out))

    assert not scanned("echo 'Never set TZ=EST | use America/New_York'")
    assert not scanned('echo "TZ=EST > not a redirect"')

    # A real redirect still means configuration, so the round-22 property
    # holds.
    assert scanned("echo 'TZ=EST' > /tmp/app.env")
    assert scanned("echo 'TZ=EST' | tee app.env")

    assert _redirects_outside_quotes("echo x > f")
    assert not _redirects_outside_quotes("echo 'a | b'")
    assert not _redirects_outside_quotes('echo "a > b"')


def test_a_shell_function_scope_ends_at_its_closing_brace():
    """A command written AFTER a helper is not inside it.

    Splitting only at function openings ran each one to the start of the
    next, so a top-level `gcloud scheduler jobs create` was placed inside the
    preceding helper and `_scheduler_offenders` treated that helper's `local`
    array as visible to it. A genuinely zoneless command reported nothing,
    which is a UTC scheduler the guard calls fine (Codex, PR #993).
    """
    body = ('helper() {\n'
            '  local flags=(--time-zone America/New_York)\n'
            '}\n'
            'gcloud scheduler jobs create http j "${flags[@]}"\n')
    offenders = []
    for name, func in _shell_functions(body):
        offenders.extend(_scheduler_offenders(name, func))
    assert offenders, (
        "the top-level command expands an array that is local to the helper, "
        "so it receives no timezone")

    # The same command INSIDE the helper really does see the array, and must
    # not be reported -- otherwise this fix would be a false positive.
    inside = ('helper() {\n'
              '  local flags=(--time-zone America/New_York)\n'
              '  gcloud scheduler jobs create http j "${flags[@]}"\n'
              '}\n')
    offenders = []
    for name, func in _shell_functions(inside):
        offenders.extend(_scheduler_offenders(name, func))
    assert not offenders, offenders

    # A brace inside a string or a comment closes nothing.
    assert _brace_delta('msg="}"') == 0
    assert _brace_delta("run  # }") == 0
    assert _brace_delta("f() {") == 1
    assert _brace_delta("}") == -1


def test_a_wrapped_time_zone_flag_reads_its_value():
    """`--time-zone \\` then `"America/New_York"` is one flag.

    The zone-flag scan read the raw text and captured the continuation
    backslash as the zone, so a correctly wrapped and correctly zoned command
    failed the assertion (Codex, PR #993). `_scheduler_commands` already
    joined continuations for the offender half of the same test; this half
    did not.
    """
    body = ('gcloud scheduler jobs create http j \\\n'
            '    --time-zone \\\n'
            '    "America/New_York"\n')
    joined = re.sub(r"\\\n\s*", " ", body)
    zones = set(re.findall(
        r"--time-zone[=\s]+[\"']?([^\s\"']+)[\"']?", joined))
    assert zones == {"America/New_York"}, zones

    # The unjoined text is what produced the bad value, kept here so the
    # reason for the join cannot be optimised away.
    raw = set(re.findall(
        r"--time-zone[=\s]+[\"']?([^\s\"']+)[\"']?", body))
    assert raw == {"\\"}, raw


# Three findings from this round are NOT fixed here, for the reason recorded
# on issue #1019: each is a new spelling needing its own matcher, and rounds
# 19-23 have each produced a regression from the previous round's fix.
#
#   * `dateutil.tz.tzrange("ET", stdoffset=-18000)` -- the keyword filter
#     accepts only `offset`
#   * `%env TZ EST` -- IPython's whitespace form of the environment magic
#   * `env: [{name: TZ, value: EST}]` -- flow-style YAML, where the matcher
#     requires a newline between the two keys
#
# All three end in a real zone or a real process environment, so the runtime
# assertion on #1019 covers them.
# -- Round 24 (Codex, PR #993) ----------------------------------------------
#
# Ten findings. Five fixed, five recorded on #1019. Four of the five fixed are
# defects in this file's own preprocessing -- two of them created by the fixes
# one round earlier -- and the fifth is the scheduler check accepting a
# zoneless declaration because a substring appeared in a payload.


def test_a_postgres_escape_string_does_not_end_at_its_escaped_quote():
    """`SELECT E'foo\' -- still data'; SET TIME ZONE 'EST';` runs the SET.

    In an `E'...'` literal a backslash escapes the next character, so the
    quote is data. The stripper read it as the closing quote, took the `--`
    for a comment, and blanked the real `SET` -- hiding a fixed session
    timezone from both guards. The third instance of this shape, after the
    `${path#*/}` and escaped-quote findings in the SHELL stripper, and the
    first in the direction that hides rather than invents (Codex, PR #993).
    """
    kept = _strip_sql_comments(
        r"SELECT E'foo\' -- still data'; SET TIME ZONE 'EST';")
    assert "SET TIME ZONE 'EST'" in kept, kept
    assert NONPY_AMBIGUOUS.search(kept) or NONPY_UNAMBIGUOUS.search(kept)

    # Doubling still needs no special case, and an ordinary literal takes no
    # backslash escapes at PostgreSQL's default settings.
    assert "SET TIME ZONE 'EST'" in _strip_sql_comments(
        "SELECT 'it''s'; SET TIME ZONE 'EST';")

    # A real comment is still blanked, and `--` inside a literal is still data.
    assert not NONPY_AMBIGUOUS.search(
        _strip_sql_comments("-- SET TIME ZONE 'EST'"))
    assert "'a -- b'" in _strip_sql_comments("SELECT 'a -- b';")

    # `E` only counts as its own token, so a column called `table` keeps an
    # ordinary literal.
    assert _strip_sql_comments("SELECT table'x' -- c").rstrip() == (
        "SELECT table'x'")


def test_blanking_a_diagnostic_stops_at_the_command_separator():
    """`echo done; export TZ="EST"` still reports the export.

    The output-blanking pass emptied every quoted string to the end of the
    physical line, so a real assignment after a `;` was rewritten to
    `TZ="   "`. A pass added last round to close a FALSE POSITIVE had created
    a false negative instead, which is the more dangerous direction
    (Codex, PR #993).
    """
    def scanned(text: str) -> bool:
        out = _expand_shell_defaults(_strip_shell_comments(text))
        return bool(NONPY_AMBIGUOUS.search(out)
                    or NONPY_UNAMBIGUOUS.search(out))

    assert scanned('echo done; export TZ="EST"')
    assert scanned("echo done && export TZ=EST")
    assert scanned("echo done || export TZ=EST")

    # Every earlier round's property still holds. The diagnostics stay quiet:
    assert not scanned("echo 'set TZ=EST to reproduce'")          # round 21
    assert not scanned(r'printf "--time-zone EST\n"')                # round 21
    assert not scanned(
        "echo 'Never set TZ=EST | use America/New_York'")         # round 23
    # and writing the text somewhere is still configuration:
    assert scanned("echo 'TZ=EST' > /tmp/app.env")                # round 22
    assert scanned("echo 'TZ=EST' | tee app.env")                 # round 22

    # A separator inside quotes separates nothing.
    assert not scanned("echo 'a; b TZ=EST'")
    assert _command_end("echo a; export TZ=EST", 4) == 6
    assert _command_end("echo 'a; b'", 4) == len("echo 'a; b'")


def test_an_appended_array_keeps_what_it_already_held():
    """`flags=(--location ...)` then `flags+=(--time-zone ...)` is covered.

    `+=(` was read as a rebind, so the zoneless assignment was the one in
    force and a correctly zoned scheduler was reported as an offender. A false
    CI failure aimed at the incremental spelling (Codex, PR #993).
    """
    appended = ("flags=(--location us-east1)\n"
                "flags+=(--time-zone America/New_York)\n"
                'gcloud scheduler jobs create http j "${flags[@]}"\n')
    assert not _scheduler_offenders("<top level>", appended), (
        _scheduler_offenders("<top level>", appended))

    # An append carrying no zone leaves the array zoneless.
    zoneless = ("flags=(--location us-east1)\n"
                "flags+=(--attempt-deadline 60s)\n"
                'gcloud scheduler jobs create http j "${flags[@]}"\n')
    assert _scheduler_offenders("<top level>", zoneless)

    # A REBIND still wipes the zone, which is the round-21 property.
    rebound = ("flags=(--time-zone America/New_York)\n"
               "flags=(--location us-east1)\n"
               'gcloud scheduler jobs create http j "${flags[@]}"\n')
    assert _scheduler_offenders("<top level>", rebound)


def test_the_function_keyword_opens_a_scope():
    """`function helper { ... }` is a function, and its locals stay in it.

    The header pattern knew only `name() {`, so a helper written with the
    keyword opened no scope: its `local` zoned array was read as file scope
    and covered a later top-level command that actually expands an unset
    array and receives no zone at all. The same silent disarming of the
    scheduler check the splitter was rewritten to fix one round earlier, one
    spelling along (Codex, PR #993).
    """
    def bodies(header: str) -> str:
        return (header + "\n"
                "  local flags=(--time-zone America/New_York)\n"
                '  gcloud scheduler jobs create http a "${flags[@]}"\n'
                "}\n"
                'gcloud scheduler jobs create http b "${flags[@]}"\n')

    for header in ("function helper {", "function helper() {", "helper() {"):
        segs = _shell_functions(bodies(header))
        assert [n for n, _ in segs] == ["<top level>", "helper"], header
        found = [o for n, seg in segs for o in _scheduler_offenders(n, seg)]
        assert len(found) == 1 and "http b" in found[0], (header, found)


def test_a_scheduler_flag_is_an_argument_not_a_substring():
    """A payload quoting `--time-zone` does not satisfy the check.

    `--message-body '{"note":"--time-zone"}'` contained the text, so the
    command was skipped and a scheduler defaulting to UTC produced no
    offender. The file-wide zone assertion could not catch it either: the
    genuine flags elsewhere in `deploy.sh` already satisfy it
    (Codex, PR #993).
    """
    payload = ('gcloud scheduler jobs create http j '
               "--message-body '{\"note\":\"--time-zone\"}'\n")
    assert _scheduler_offenders("<top level>", payload), (
        "a payload is not a flag")

    # Tokenising cuts the other way too: a quoted flag is still the flag.
    for real in ('--time-zone America/New_York',
                 '"--time-zone" "America/New_York"',
                 '--time-zone=America/New_York'):
        cmd = f'gcloud scheduler jobs create http j {real}\n'
        assert not _scheduler_offenders("<top level>", cmd), real

    assert _declares_zone_flag("gcloud x --time-zone America/New_York")
    # `shlex` strips the quotes, so a payload that is EXACTLY the flag --
    # `--body '--time-zone'` -- still tokenises to it. Telling that from a
    # real flag needs gcloud's option arity, which this file does not model,
    # so it stays a limitation rather than a silent claim. The reported
    # shape, a flag quoted INSIDE a larger payload, is what is closed here.
    assert not _declares_zone_flag(
        "gcloud x --message-body '{\"note\":\"--time-zone\"}'")


def test_the_real_deploy_script_tokenises():
    """Every scheduler command in `gcp/deploy.sh` can actually be parsed.

    `_declares_zone_flag` falls back to the old substring test when `shlex`
    cannot read a command, so a script that stopped parsing would quietly
    return the guard to the weaker check this round replaced. This asserts
    the fallback is not currently load-bearing.
    """
    body = _strip_shell_comments((REPO / "gcp" / "deploy.sh").read_text())
    commands = [cmd for _, seg in _shell_functions(body)
                for _, cmd in _scheduler_commands(seg)]
    assert commands, "no scheduler commands found -- has deploy.sh moved?"
    for cmd in commands:
        shlex.split(cmd)          # raises ValueError if it cannot


# Recorded on #1019 rather than fixed, with the reasoning in the issue:
#
#   * Make variable references -- `LEGACY := EST` then `export TZ := $(LEGACY)`
#   * `SET TIME ZONE INTERVAL '-5 hours'`, the unit-bearing interval spelling
#   * `%sx` / `%system` line magics, whose payload runs in a shell
#   * YAML `- value: EST` before `name: TZ`, the reverse block order
#
# and one that is NOT merely another spelling, which is why it is written out
# here as well as there:
#
#   * `export TZ=\` continued onto the next physical line.
#
# Every shell preprocessing step in this file is WIDTH-PRESERVING -- comments
# and expansions are blanked in spaces rather than deleted -- because
# `_scalar_in_force` resolves a reference by comparing character offsets, and
# `_scheduler_commands` maps commands to array assignments the same way.
# Joining a continuation removes a newline, so it cannot preserve either the
# offsets or the line numbers this file reports, and the scheduler path gets
# away with joining only because it computes its own offsets afterwards.
#
# So closing it means re-basing every offset consumer on joined text: a change
# to the machinery six of the last twelve regressions came from, in service of
# one spelling. That is the trade this whole class is about, and it is the
# user's call rather than mine.
# -- Round 25 (Codex, PR #993) ----------------------------------------------


def test_a_clock_offset_with_seconds_is_read_whole():
    """`SET TIME ZONE INTERVAL '-05:00:30' HOUR TO SECOND` is NOT Eastern.

    The pattern matched the `-05:00` prefix and its lookahead permitted the
    following `:`, so a session set to UTC-05:00:30 -- an offset that is
    neither EST nor EDT -- failed the guard. A false CI failure, and the same
    shape as the `FixedOffset(-300.5)` finding two rounds ago: a near-miss
    offset truncated into a violation (Codex, PR #993).

    The seconds field is optional and must be `00`, so the longhand spelling
    of the real offsets is still caught.
    """
    forbidden = [
        "SET TIME ZONE INTERVAL '-05:00:00' HOUR TO SECOND",
        "SET TIME ZONE INTERVAL '-05:00' HOUR TO MINUTE",
        "SET TIME ZONE '-05:00'",
        "SET TIME ZONE '-04:00:00'",
        "SET TIME ZONE '-0500'",
        "timezone=-05:00",
        "TZ=EST5",
    ]
    for src in forbidden:
        assert NONPY_FIXED_OFFSET.search(src), src

    allowed = [
        "SET TIME ZONE INTERVAL '-05:00:30' HOUR TO SECOND",
        "SET TIME ZONE INTERVAL '-04:00:01' HOUR TO SECOND",
        "TZ=EST5EDT",          # DST-correct, just the wrong name
    ]
    for src in allowed:
        assert not NONPY_FIXED_OFFSET.search(src), src


# Recorded on #1019 rather than fixed:
#
#   * `HOURS = -5; OFFSET = timedelta(hours=HOURS); timezone(OFFSET)`.
#
# Each half already works on its own -- `OFFSET = timedelta(hours=-5)` is
# kept as a binding, and `timezone(timedelta(hours=HOURS))` resolves the name
# -- and only the COMPOSITION fails, because `_collect_bindings` decides
# whether to keep a call binding by evaluating it without the environment and
# drops the node when that cannot resolve.
#
# That is the same category as the tuple-destructuring and constant-subscript
# deferrals still open from rounds 19 and 20, and it is deferred for the same
# reason: closing it means either resolving inside the prefilter, which needs
# an environment the collector is still building, or retaining every call
# binding for `follow` to sort out later, which widens what eleven resolvers
# already compose over.
def test_a_scalar_declared_with_a_builtin_is_collected():
    """`local LEGACY=EST` then `export TZ="$LEGACY"` is a finding.

    `_shell_scalars` accepted a bare assignment and `export`, so a value
    declared with `local` -- the ordinary way to write it inside a helper --
    resolved to nothing and the reference stayed unexpanded.

    The parity is the point: `_arrays_carrying_timezone` learned
    `local`/`declare`/`typeset`/`readonly` and their options in round 21, for
    exactly this reason, and the scalar collector beside it did not. One half
    of a pair fixed and the other left is how this file has produced most of
    its misses (Codex, PR #993).
    """
    def scanned(text: str) -> bool:
        out = _expand_shell_defaults(_strip_shell_comments(text))
        return bool(NONPY_AMBIGUOUS.search(out)
                    or NONPY_UNAMBIGUOUS.search(out))

    for decl in ("local", "declare", "declare -r", "typeset", "readonly",
                 "export", ""):
        src = f'{decl} LEGACY=EST\nexport TZ="$LEGACY"\n'
        assert scanned(src), decl

    # The canonical zone declared the same way is still clean, and a value
    # that is not statically known is still left unresolved rather than
    # guessed at.
    assert not scanned('local LEGACY=America/New_York\nexport TZ="$LEGACY"\n')
    assert not scanned('local LEGACY="$OTHER"\nexport TZ="$LEGACY"\n')


def test_make_comments_are_read_with_makes_rule():
    """`NOTE := old# TZ=EST is forbidden` is entirely a comment.

    Make starts a comment at any unescaped `#`, word boundaries and quotes
    included. Round 22 narrowed the stripper to bash's word-start rule to stop
    it eating `${path#*/}`, and `.mk` and `Makefile` go through that same
    path -- so a Make comment kept its tail and failed CI on text make never
    executes. A false positive created by the interaction of two earlier
    fixes rather than by either one alone (Codex, PR #993).

    A RECIPE line keeps bash's rule, because make hands a tab-indented line
    to the shell verbatim and the shell's rule is the one that decides there.
    """
    def scanned(text: str, make: bool) -> bool:
        out = _expand_shell_defaults(_strip_shell_comments(text, make=make))
        return bool(NONPY_AMBIGUOUS.search(out)
                    or NONPY_UNAMBIGUOUS.search(out))

    # Comments, under make's rule.
    assert not scanned("NOTE := old# TZ=EST is forbidden", make=True)
    assert not scanned("# export TZ := EST", make=True)
    assert not scanned('MSG := "keep # this"', make=True)

    # Real settings still report, with and without a trailing comment.
    assert scanned("export TZ := EST", make=True)
    assert scanned("export TZ := EST # trailing", make=True)

    # A recipe line is shell: the round-22 property holds inside a Makefile.
    assert scanned("\texport TZ=EST", make=True)
    assert scanned("\ttrimmed=${path#*/}; export TZ=EST", make=True)

    # And the shell path is untouched.
    assert scanned("trimmed=${path#*/}; export TZ=EST", make=False)
    assert not scanned("a=1 # --time-zone America/New_York", make=False)

    assert _reads_as_make(REPO / "Makefile")
    assert _reads_as_make(REPO / "rules.mk")
    assert not _reads_as_make(REPO / "gcp" / "deploy.sh")


# Recorded on #1019 rather than fixed:
#
#   * `KEY = "TZ"; os.environ[KEY] = "EST"`.
#
# The subscript branch compares a literal slice against `_TZ_KEYWORDS` and
# never resolves the name. Same category as the constant-subscript deferral
# open since round 20 -- a value named once, where each half already works and
# only the composition does not -- and closing it means resolving inside a
# pass that is still building the environment it would resolve against.
# -- Round 27 (Codex, PR #993) ----------------------------------------------
#
# Five findings, four fixed. THREE of the four are false positives and TWO of
# those are regressions from the two commits immediately before this one,
# which is the fastest this file has produced them.


def test_every_diagnostic_on_a_line_is_blanked():
    """`echo "ok"; echo "never set TZ=EST"` prints, it does not configure.

    Bounding the blanking to the current command -- the fix one round earlier
    -- also stopped it at the FIRST command, so a second diagnostic on the
    same line kept its argument and was reported. The bound was right;
    applying it once was not (Codex, PR #993).
    """
    def scanned(text: str) -> bool:
        out = _expand_shell_defaults(_strip_shell_comments(text))
        return bool(NONPY_AMBIGUOUS.search(out)
                    or NONPY_UNAMBIGUOUS.search(out))

    assert not scanned('echo "ok"; echo "never set TZ=EST"')
    assert not scanned('echo "ok"; echo "a"; echo "set TZ=EST"')

    # The round-24 property holds: a real assignment after a diagnostic is
    # still a finding, and it is what the bound exists for.
    assert scanned('echo "ok"; export TZ="EST"')
    # As does round 22's: text written somewhere is configuration.
    assert scanned("echo 'a'; echo 'TZ=EST' > /tmp/app.env")


def test_a_function_local_does_not_bind_the_file_scope():
    """Defining a function does not run its body.

    `LEGACY=EST`, then a helper whose body declares `local
    LEGACY=America/New_York`, then a top-level `export TZ="$LEGACY"` exports
    EST -- but by textual position alone the `local` was the assignment in
    force, and the real finding disappeared.

    The regression arrived with the commit immediately before this one, which
    taught `_shell_scalars` to read `local` at all. Before it the declaration
    was invisible and the file-scope value won by accident; reading it made
    the accident into a wrong answer (Codex, PR #993).
    """
    def scanned(text: str) -> bool:
        out = _expand_shell_defaults(_strip_shell_comments(text))
        return bool(NONPY_AMBIGUOUS.search(out)
                    or NONPY_UNAMBIGUOUS.search(out))

    masked = ("LEGACY=EST\n"
              "helper() {\n"
              "  local LEGACY=America/New_York\n"
              "}\n"
              'export TZ="$LEGACY"\n')
    assert scanned(masked), "the file-scope EST is what the shell exports"

    # And the local IS what a reference inside the same function sees.
    inside = ("LEGACY=America/New_York\n"
              "helper() {\n"
              "  local LEGACY=EST\n"
              '  export TZ="$LEGACY"\n'
              "}\n")
    assert scanned(inside)

    # A `local` at top level is not in any function body, so it binds there.
    assert scanned('local LEGACY=EST\nexport TZ="$LEGACY"\n')

    # Round 21's ordering property, unchanged in both directions.
    assert scanned('LEGACY=EST\nexport TZ="$LEGACY"\n'
                   "LEGACY=America/New_York\n")
    assert not scanned('LEGACY=America/New_York\nexport TZ="$LEGACY"\n')

    spans = _function_spans(masked)
    assert len(spans) == 1
    start, end = spans[0]
    assert "local LEGACY" in masked[start:end]
    assert "export TZ" not in masked[start:end]


def test_a_single_quoted_reference_is_not_expanded():
    """`export TZ='$LEGACY'` sets the literal text, not the zone.

    The shell does not expand inside single quotes, so this line installs no
    timezone at all -- and rewriting it to `TZ='EST'` failed CI on it
    (Codex, PR #993). Double quotes do expand, which is why the substitution
    exists.
    """
    def scanned(text: str) -> bool:
        out = _expand_shell_defaults(_strip_shell_comments(text))
        return bool(NONPY_AMBIGUOUS.search(out)
                    or NONPY_UNAMBIGUOUS.search(out))

    assert not scanned("LEGACY=EST\nexport TZ='$LEGACY'\n")
    assert scanned('LEGACY=EST\nexport TZ="$LEGACY"\n')

    # The parameter-default rewrite is literal inside single quotes for the
    # same reason, and still expands outside them (round 19's property).
    assert not scanned("export TZ='${TZ:-EST}'")
    assert scanned('export TZ="${TZ:-EST}"')

    assert _single_quoted("export TZ='")
    assert not _single_quoted('export TZ="')
    assert not _single_quoted("export TZ=")


def test_pine_sources_are_read_without_their_comments():
    """`// old: timezone = "EST"` is a note, not a setting.

    The extensionless TradingView sources are collected deliberately and
    matched neither preprocessing branch, so they reached the regex pass with
    their comments intact and an ordinary migration note failed CI. The same
    false positive the SQL branch was given comment stripping for two rounds
    ago, in the one collected language that still had none
    (Codex, PR #993).
    """
    def hit(text: str) -> bool:
        out = _strip_pine_comments(text)
        return bool(NONPY_AMBIGUOUS.search(out)
                    or NONPY_UNAMBIGUOUS.search(out))

    assert not hit('// old: timezone = "EST"')
    assert not hit('/* old: timezone = "-05:00" */')
    assert not hit('timezone = "America/New_York"')

    # A real setting still reports, with or without a trailing note.
    assert hit('timezone = "EST"')
    assert hit('timezone = "EST"  // migrated')

    # `//` inside a string is data, not a comment.
    assert _strip_pine_comments('msg = "https://x.test"').rstrip() == (
        'msg = "https://x.test"')

    assert _reads_as_pine(REPO / "tradingview-pine-scripts" / "orb-30")
    assert not _reads_as_pine(REPO / "gcp" / "deploy.sh")

    # The SQL stripper shares the implementation and is unchanged.
    assert _strip_sql_comments("-- SET TIME ZONE 'EST'").strip() == ""
    assert "SET TIME ZONE 'EST'" in _strip_sql_comments(
        r"SELECT E'foo\' -- still data'; SET TIME ZONE 'EST';")
    # ...and its token stays `--`: `//` is not a SQL comment and is kept.
    assert _strip_sql_comments("SELECT 1 // kept").rstrip() == "SELECT 1 // kept"


# Recorded on #1019 rather than fixed:
#
#   * `class Config: TIME_ZONE = "EST"`.
#
# The export check asks whether the assignment is at MODULE level, so a class
# namespace -- which is also consumed externally, as `Config.TIME_ZONE` --
# falls outside it while an ordinary function local correctly does too.
# Separating those two is a change to the scope model rather than another
# matcher, which is why it belongs in the follow-up.
# -- Audit: the guard's own silent fallbacks -------------------------------
#
# Found by reading this file the way it reads the repository, not by review.
# Four places answered "clean" for input they had not read. Each is the shape
# the guarded code is forbidden from having, and each is exactly what the next
# review round would have named.


def test_a_python_file_that_does_not_parse_is_still_scanned_as_text():
    """`ZoneInfo('US/Eastern')` in a file with a syntax error is a finding.

    `_python_hits` returned two empty lists on SyntaxError, which `_scan` read
    as "scanned, clean" -- so a tracked `.py` passed both guards BY failing to
    parse. The notebook path already hands an unparseable cell to the regex
    pass; the `.py` path now does the same. Nothing is fabricated: the text is
    read, by the weaker reader.
    """
    src = "def broken(:\n    pass\nZoneInfo('US/Eastern')\n"
    assert _python_hits(REPO / "_probe.py", src) is None, (
        "an unparseable file must say so, not report clean")
    # ...and the regex pass, which `_scan` now falls through to, sees it.
    assert NONPY_UNAMBIGUOUS.search(src)
    # A file that parses still takes the AST path and returns the pair.
    parsed = _python_hits(REPO / "_probe.py", "x = 1\n")
    assert parsed == ([], [])


def test_a_notebook_that_is_not_json_fails_loudly():
    """Malformed notebook JSON is an error, not an empty scan.

    `_notebook_cells` returned [] for text that was not a notebook, which
    read as "no code cells" -- a verdict about a file the guard could not
    read. Unlike an unparseable `.py`, malformed JSON has no regex pass to
    fall back to, so the honest answer is to raise and name the file.
    """
    nb_path = REPO / "notebooks" / "_probe.ipynb"
    with pytest.raises(ValueError, match="not a readable notebook"):
        _notebook_hits(nb_path, "{not json")
    with pytest.raises(ValueError, match="not a readable notebook"):
        _notebook_hits(nb_path, "[1, 2, 3]")          # JSON, not a notebook

    # An EMPTY file has nothing in it, so "no cells" is accurate, not
    # guessed. (One tracked notebook is zero bytes today -- a repository
    # defect filed separately, not a reason for the guard to invent a
    # verdict either way.)
    assert _notebook_hits(nb_path, "") == ([], [], "")
    assert _notebook_hits(nb_path, "   \n") == ([], [], "")

    # A notebook with no code cells is a real, distinct verdict.
    assert _notebook_cells(json.dumps({"cells": []})) == []
    assert _notebook_cells("{not json") is None


def test_an_unparseable_scheduler_command_is_not_vouched_for():
    """A command `shlex` cannot read is an offender, not a substring match.

    `_declares_zone_flag` fell back to `"--time-zone" in cmd` on a
    `ValueError`, which is the permissive direction: a command with an
    unbalanced quote and the text `--time-zone` somewhere in it was accepted.
    This file already holds that a value the guard cannot read is a value it
    cannot vouch for, and the fallback contradicted it.
    """
    unbalanced = "gcloud scheduler jobs create http j --time-zone 'America/New_York\n"
    assert not _declares_zone_flag(unbalanced)
    assert _scheduler_offenders("<top level>", unbalanced), (
        "an unparseable declaration must be reported, with its text")

    # A parseable command with the real flag is still clean, quoted or not.
    assert _declares_zone_flag("gcloud x --time-zone America/New_York")
    assert _declares_zone_flag('gcloud x "--time-zone" "America/New_York"')
# -- Audit: the manifest surface, parsed --------------------------------------


def test_yaml_environment_entries_are_read_in_any_order_and_style():
    """The three open manifest spellings, closed by one loader.

    Reverse key order, flow style, and the argv list form each defeated the
    line-oriented matcher in its own round (Codex, PR #993). None of them is
    a special case to a parser.
    """
    # Reverse order: YAML mapping order carries no meaning.
    assert _yaml_env_pair_hits("- value: EST\n  name: TZ\n")
    # Flow style, both quotings.
    assert _yaml_env_pair_hits("env: [{name: TZ, value: EST}]\n")
    hits = _yaml_env_pair_hits('env: [{name: "TZ", value: "-05:00"}]\n')
    assert hits and hits[0][2] is True, hits
    # Nested where a manifest actually puts it.
    assert _yaml_env_pair_hits(
        "spec:\n  containers:\n  - env:\n"
        "      - name: PGTZ\n        value: US/Eastern\n")

    # The round-21 and round-22 properties, on the loader now.
    assert _yaml_env_pair_hits("        - name: TZ\n          value: EST\n")
    assert not _yaml_env_pair_hits("- name: LOG_LEVEL\n  value: EST\n")
    assert not _yaml_env_pair_hits("- name: TZ\n  value: America/New_York\n")
    # A comment between the halves is nothing to a parser.
    assert _yaml_env_pair_hits(
        "- name: TZ\n  # the app expects Eastern\n  value: EST\n")
    # And it cannot reach into a sibling entry.
    assert not _yaml_env_pair_hits(
        "- name: TZ\n  value: America/New_York\n- name: OTHER\n  value: EST\n")


def test_yaml_argv_lists_carry_the_scheduler_flag():
    """`args: ["--time-zone", "EST"]` passes the flag and its value as two items.

    Neither regex could fire: the comma, the quotes, or the list marker sat
    between the context and the value (Codex, PR #993, round 22).
    """
    assert _yaml_env_pair_hits('args: ["--time-zone", "EST"]\n')
    assert _yaml_env_pair_hits("args:\n  - --time-zone\n  - EST\n")
    assert _yaml_env_pair_hits("command: ['--time-zone=US/Eastern']\n")
    hits = _yaml_env_pair_hits("args: [--time-zone, '-04:00']\n")
    assert hits and hits[0][2] is True and hits[0][1] == "-04:00", hits

    # The canonical zone, an unrelated flag, and a flag with no value are
    # not findings.
    assert not _yaml_env_pair_hits('args: ["--time-zone", "America/New_York"]\n')
    assert not _yaml_env_pair_hits('args: ["--location", "EST"]\n')
    assert not _yaml_env_pair_hits('args: ["--time-zone"]\n')


def test_yaml_hits_carry_the_line_of_the_value():
    """`report` reads `start()` off a hit and turns it into a line number."""
    text = "a: 1\nenv:\n  - name: TZ\n    value: EST\n"
    hits = _yaml_env_pair_hits(text)
    assert hits
    assert text.count("\n", 0, hits[0][0].start()) + 1 == 4
    assert "EST" in hits[0][0].group(0)


def test_yaml_that_the_loader_cannot_read_fails_loudly():
    """A `.yml` that is not YAML is not scanned by being skipped."""
    with pytest.raises(yaml.YAMLError):
        _yaml_env_pair_hits("key: [unclosed\n")


def test_the_repos_real_manifests_load_and_are_clean():
    """Every tracked YAML file parses, and none installs a bad zone."""
    files = [p for p in _source_files() if p.suffix in (".yml", ".yaml")]
    assert files, "no YAML collected -- has the manifest set moved?"
    for p in files:
        assert _yaml_env_pair_hits(p.read_text()) == [], p
# -- Audit: the notebook surface, classified once -------------------------------


def test_every_ipython_line_is_classified_once():
    """`%env TZ EST` and `%sx env TZ=EST date` reach the shell pass.

    Two special-case lists -- what `_strip_magic` kept and what
    `_notebook_shell` collected -- left a gap between them, and both open
    notebook findings sat in it (Codex, PR #993, rounds 23 and 24). One
    classification feeds both passes now.
    """
    def probe(cells):
        nb = json.dumps({"cells": [{"cell_type": "code", "source": c}
                                   for c in cells]})
        _legacy, _offsets, rest = _notebook_hits(
            REPO / "notebooks" / "_probe.ipynb", nb)
        return rest

    # The environment magic, both documented forms.
    assert NONPY_AMBIGUOUS.search(probe([["%env TZ EST\n"]]))
    assert NONPY_AMBIGUOUS.search(probe([["%env TZ=EST\n"]]))
    assert NONPY_FIXED_OFFSET.search(probe([["%env PGTZ -05:00\n"]]))
    # The shell-executing line magics.
    assert NONPY_AMBIGUOUS.search(probe([["%sx env TZ=EST date\n"]]))
    assert NONPY_AMBIGUOUS.search(probe([["%system env TZ=EST date\n"]]))

    # `%env` and `%env NAME` READ the environment and set nothing.
    assert not probe([["%env\n"]]).strip()
    assert not probe([["%env TZ\n"]]).strip()
    # The canonical zone, set the same way, is clean.
    assert not NONPY_AMBIGUOUS.search(probe([["%env TZ America/New_York\n"]]))

    # Every earlier property, on the same classifier: a Python line magic
    # keeps its payload for the parser, `%pip` blanks, a `!` escape and a
    # `%%bash` body are shell and arrive exactly once.
    assert _classify_magic("    %time x = 1") == ("python", "    x = 1")
    assert _classify_magic("%pip install pandas") == (None, "")
    assert _classify_magic("!TZ=EST date") == ("shell", "TZ=EST date")
    assert _classify_magic("x = 1") == (False, "x = 1")
    assert _classify_magic("%env TZ EST") == ("env", "export TZ=EST")
    assert probe([["%%bash\n", "export TZ=EST\n"]]).count("export TZ=EST") == 1
# -- Audit: the scope-and-binding model, extended once -------------------------
#
# Four open threads described one subsystem: a value the guard could resolve
# when written inline and could not when named once. They are closed together
# because they share a mechanism, and each fix is checked against the case
# that must stay quiet.


def _probe_py(src: str):
    """`_python_hits` on a module written to a probe path, as a pair."""
    return _python_hits(REPO / "_probe.py", src)


def test_a_class_body_setting_is_an_exported_setting():
    """`class Config: TIME_ZONE = "EST"` is read from outside as `Config.TIME_ZONE`."""
    legacy, _ = _probe_py('class Config:\n    TIME_ZONE = "EST"\n')
    assert legacy, "a class-body setting is consumed externally"
    legacy, _ = _probe_py('class Config:\n    TIME_ZONE: str = "US/Eastern"\n')
    assert legacy, "the annotated form too"
    # A function local of the same name is nobody's setting, and a class
    # defined INSIDE a function is that function's local.
    legacy, _ = _probe_py('def f():\n    TIME_ZONE = "EST"\n    return 1\n')
    assert not legacy
    legacy, _ = _probe_py('def f():\n    class C:\n        TIME_ZONE = "EST"\n    return C\n')
    assert not legacy
    # The canonical zone in a class body is not a finding.
    legacy, _ = _probe_py('class Config:\n    TIME_ZONE = "America/New_York"\n')
    assert not legacy


def test_a_bound_offset_call_is_evaluated_with_the_environment():
    """`HOURS = -5; OFFSET = timedelta(hours=HOURS); timezone(OFFSET)` reports."""
    src = ("from datetime import timedelta, timezone\n"
           "HOURS = -5\nOFFSET = timedelta(hours=HOURS)\nET = timezone(OFFSET)\n")
    _, offsets = _probe_py(src)
    assert offsets, "the composition of two forms that each resolve alone"
    # A non-Eastern total through the same binding is not one.
    _, offsets = _probe_py(src.replace("-5", "-3"))
    assert not offsets
    assert _is_offset_constructor_call(ast.parse("-timedelta(hours=5)").body[0].value)
    assert not _is_offset_constructor_call(ast.parse("len(x)").body[0].value)


def test_a_subscript_key_named_once_is_resolved():
    """`KEY = "TZ"; os.environ[KEY] = "EST"` installs the zone."""
    legacy, _ = _probe_py('import os\nKEY = "TZ"\nos.environ[KEY] = "EST"\n')
    assert legacy
    # An unrelated key, named once, is still not a timezone context.
    legacy, _ = _probe_py('import os\nKEY = "REGION"\nos.environ[KEY] = "EST"\n')
    assert not legacy


def test_a_constant_lookup_into_a_bound_container_is_followed():
    """`ZONES = {"primary": "EST"}; ZoneInfo(ZONES["primary"])` reports."""
    head = "from zoneinfo import ZoneInfo\n"
    legacy, _ = _probe_py(head + 'ZONES = {"primary": "EST"}\nZ = ZoneInfo(ZONES["primary"])\n')
    assert legacy
    legacy, _ = _probe_py(head + 'ZONES = ("EST", "UTC")\nZ = ZoneInfo(ZONES[0])\n')
    assert legacy, "a constant index into a bound sequence"
    # The lookup that selects the CANONICAL entry is clean even when a
    # sibling entry is not, and a computed key stays unresolved.
    legacy, _ = _probe_py(head + 'ZONES = {"primary": "America/New_York", "old": "EST"}\n'
                          'Z = ZoneInfo(ZONES["primary"])\n')
    assert not legacy
    legacy, _ = _probe_py(head + 'ZONES = {"primary": "EST"}\nk = "primary"\n'
                          'Z = ZoneInfo(ZONES[k])\n')
    assert not legacy


def test_a_destructuring_assignment_binds_each_name():
    """`TZ, fallback = ("EST", "UTC"); ZoneInfo(TZ)` reports."""
    head = "from zoneinfo import ZoneInfo\n"
    legacy, _ = _probe_py(head + 'TZ, fallback = ("EST", "UTC")\nZ = ZoneInfo(TZ)\n')
    assert legacy
    legacy, _ = _probe_py(head + '[TZ, fallback] = ["EST", "UTC"]\nZ = ZoneInfo(TZ)\n')
    assert legacy, "the list form too"
    # The other element is the other name.
    legacy, _ = _probe_py(head + 'TZ, fallback = ("America/New_York", "EST")\nZ = ZoneInfo(TZ)\n')
    assert not legacy
    # A single starred target takes the head and tail around it, as Python
    # does, so `TZ` here is `"EST"` and is reported AT THE CALL; this used to
    # be "not statically known" (Codex, PR #993 final review). A ragged
    # unpack, or a value that is not a literal sequence, still is not.
    legacy, _ = _probe_py(head + 'TZ, *rest = ("EST", "UTC")\nZ = ZoneInfo(TZ)\n')
    assert legacy and "ZoneInfo" in legacy[0], legacy
    legacy, _ = _probe_py(head + '*rest, TZ = ("UTC", "EST")\nZ = ZoneInfo(TZ)\n')
    assert legacy
    legacy, _ = _probe_py(head + 'TZ, fallback = pair\nZ = ZoneInfo(TZ)\n')
    assert not legacy
# -- Audit: the seven remaining spellings, each with its negative control --------


def test_tzrange_reads_its_stdoffset_keyword():
    _, offsets = _probe_py("from dateutil.tz import tzrange\nz = tzrange('ET', stdoffset=-18000)\n")
    assert offsets
    _, offsets = _probe_py("from dateutil.tz import tzrange\nz = tzrange('X', stdoffset=-10800)\n")
    assert not offsets


def test_make_variable_references_resolve_in_make_files_only():
    def scanned(text: str, make: bool) -> bool:
        out = _expand_shell_defaults(_strip_shell_comments(text, make=make), make=make)
        return bool(NONPY_AMBIGUOUS.search(out) or NONPY_UNAMBIGUOUS.search(out))

    assert scanned("LEGACY := EST\nexport TZ := $(LEGACY)\n", make=True)
    assert scanned("LEGACY = US/Eastern\nTZ = ${LEGACY}\n", make=True)
    assert not scanned("LEGACY := America/New_York\nexport TZ := $(LEGACY)\n", make=True)
    # Last assignment before the reference is the one in force.
    assert not scanned("LEGACY := EST\nLEGACY := America/New_York\nexport TZ := $(LEGACY)\n", make=True)
    # A computed value is left unresolved, not guessed.
    assert not scanned("LEGACY := $(shell date)\nexport TZ := $(LEGACY)\n", make=True)
    # In a SHELL file `$(...)` is command substitution and is not expanded.
    assert not scanned("LEGACY=EST\nexport TZ=$(LEGACY)\n", make=False)
    # The real Makefile is clean.
    assert not scanned((REPO / "Makefile").read_text(), make=True)


def test_a_unit_bearing_interval_is_totalled():
    def hit(sql: str) -> bool:
        return NONPY_SQL_INTERVAL_OFFSET.search(_strip_sql_comments(sql)) is not None

    assert hit("SET TIME ZONE INTERVAL '-5 hours'")
    assert hit("SET TIME ZONE INTERVAL '-240 minutes'")
    assert hit("SET LOCAL timezone TO INTERVAL '-4 hours'")
    assert hit("SET TIME ZONE INTERVAL '-3 hours -120 minutes'")
    assert not hit("SET TIME ZONE INTERVAL '-3 hours'")
    assert not hit("SET TIME ZONE INTERVAL '-5 hours 30 minutes'")
    assert not hit("SET TIME ZONE INTERVAL '-5 fortnights'")     # unmodelled unit
    assert not hit("-- SET TIME ZONE INTERVAL '-5 hours'")


def test_a_shell_continuation_between_context_and_value_is_read():
    def scanned(text: str) -> bool:
        out = _expand_shell_defaults(_strip_shell_comments(text))
        return bool(NONPY_AMBIGUOUS.search(out) or NONPY_FIXED_OFFSET.search(out))

    assert scanned("export TZ=\\\nEST\n")
    assert scanned("export TZ=\\\n  -05:00\n")
    assert not scanned("export TZ=\\\nAmerica/New_York\n")
    # The text is untouched -- the continuation is still there and every
    # line keeps its width, so offsets still mean what they say. (The comment
    # stripper has always dropped the final newline; that is not a join.)
    text = "LEGACY=EST\nexport TZ=\\\n\"$LEGACY\"\n"
    out = _expand_shell_defaults(_strip_shell_comments(text))
    assert out.splitlines() == text.splitlines()[:1] + ["export TZ=\\", '"EST"'] or \
        [len(l) for l in out.splitlines()] == [len(l) for l in text.splitlines()]
    assert "export TZ=\\\n" in out


def test_postgres_guc_spellings_of_a_numeric_offset():
    for sql in ("SET LOCAL timezone TO '-5'", "SET TIMEZONE = -4",
                "SET SESSION time_zone TO -5", "SET TIME ZONE -5"):
        assert NONPY_SQL_NUMERIC_OFFSET.search(sql), sql
    for sql in ("SET TIMEZONE = -3", "SET timezone TO '-5:30'", "SET work_mem = -5"):
        assert not NONPY_SQL_NUMERIC_OFFSET.search(sql), sql


def test_libpq_connection_options_install_a_session_zone():
    legacy, _ = _probe_py('import psycopg2\nc = psycopg2.connect(options="-c timezone=EST")\n')
    assert legacy
    legacy, _ = _probe_py('from sqlalchemy import create_engine\n'
                          'e = create_engine(url, connect_args={"options": "--timezone=US/Eastern"})\n')
    assert legacy
    legacy, _ = _probe_py('import psycopg2\nc = psycopg2.connect(options="-c timezone=America/New_York")\n')
    assert not legacy
    # `-c` on its own is not a timezone context.
    legacy, _ = _probe_py('x = "-c work_mem=EST"\n')
    assert not legacy


def test_pine_positional_timezone_arguments_are_read():
    assert _pine_call_hits('t = time(timeframe.period, session, "EST")')
    assert _pine_call_hits("ts = timestamp('EDT', 2024, 1, 1, 9, 30)")
    hits = _pine_call_hits('t = time_close(timeframe.period, "0930-1600", "-05:00")')
    assert hits and hits[0][2] is True
    assert not _pine_call_hits('t = time(timeframe.period, session, "America/New_York")')
    assert not _pine_call_hits('label.new(bar_index, high, "EST")')        # not a timezone call
    assert not _pine_call_hits('t = time(timeframe.period, session, syminfo.timezone)')
    # Offsets point at the value, and a comment does not count.
    src = 'x = 1\nt = time(timeframe.period, session, "EST")'
    assert src[_pine_call_hits(src)[0][0].start():].startswith('"EST"')
    assert not _pine_call_hits(_strip_pine_comments('// t = time(timeframe.period, session, "EST")'))
# -- Round 28 (Codex, PR #993) ---------------------------------------------------
#
# Six findings on the head before the audit commits; all six fixed here rather
# than recorded, per the standing direction to close what a review could find.


def test_an_assignment_before_a_separator_is_collected():
    """`LEGACY=EST; export TZ="$LEGACY"` is two commands on one line."""
    def scanned(text: str) -> bool:
        out = _expand_shell_defaults(_strip_shell_comments(text))
        return bool(NONPY_AMBIGUOUS.search(out) or NONPY_UNAMBIGUOUS.search(out))

    assert scanned('LEGACY=EST; export TZ="$LEGACY"')
    assert scanned('LEGACY=EST && export TZ="$LEGACY"')
    # Ordering and the canonical zone, on the compound form.
    assert scanned('LEGACY=EST; export TZ="$LEGACY"; LEGACY=America/New_York')
    assert not scanned('LEGACY=America/New_York; export TZ="$LEGACY"')
    # The offset recorded is the NAME's, so the in-force rule still orders
    # assignments correctly when a match begins at the separator.
    scalars = _shell_scalars("A=one; A=two")
    assert [v for _, v, _ in scalars["A"]] == ["one", "two"]
    assert scalars["A"][0][0] < scalars["A"][1][0]


def test_a_diagnostic_to_stderr_is_still_a_diagnostic():
    """`echo 'Never set TZ=EST' >&2` prints; only a readable sink is configuration."""
    def scanned(text: str) -> bool:
        out = _expand_shell_defaults(_strip_shell_comments(text))
        return bool(NONPY_AMBIGUOUS.search(out) or NONPY_UNAMBIGUOUS.search(out))

    for line in ("echo 'Never set TZ=EST' >&2", "echo 'Never set TZ=EST' 1>&2",
                 "echo 'Never set TZ=EST' >/dev/stderr", "echo 'TZ=EST' > /dev/null"):
        assert not scanned(line), line
    for line in ("echo 'TZ=EST' > /tmp/app.env", "echo 'TZ=EST' >> app.env",
                 "echo 'TZ=EST' | tee app.env", "echo 'TZ=EST' 2>&1 > app.env",
                 "echo 'TZ=EST' &> app.env"):
        assert scanned(line), line
    # The root cause was one level down: `_command_end` read the `&` of a
    # redirect as a background operator and cut the command before the
    # descriptor. A real `&` still separates.
    assert _command_end("echo x >&2", 4) == len("echo x >&2")
    assert _command_end("sleep 1 & export TZ=EST", 5) == 8
    assert scanned("sleep 1 & export TZ=EST")


def test_an_array_expansion_must_be_a_whole_shell_word():
    """`--message-body '{"note":"${flags[@]}"}'` expands nothing."""
    zoned = "flags=(--time-zone America/New_York)\n"
    payload = zoned + "gcloud scheduler jobs create http j --message-body '{\"note\":\"${flags[@]}\"}'\n"
    assert _scheduler_offenders("<top level>", payload), "text inside another argument"
    literal = zoned + "gcloud scheduler jobs create http j '${flags[@]}'\n"
    assert _scheduler_offenders("<top level>", literal), "single quotes are literal"
    for real in ('"${flags[@]}"', "${flags[@]}"):
        cmd = zoned + f"gcloud scheduler jobs create http j {real}\n"
        assert not _scheduler_offenders("<top level>", cmd), real
    assert _array_expansions('a "${flags[@]}" b') == {"${flags[@]}"}
    assert _array_expansions("a '${flags[@]}' b") == set()
    assert _array_expansions('a "x ${flags[@]}" b') == set()


def test_script_cell_magics_route_by_interpreter():
    """`%%script python` is Python; `%%script bash` is shell; ruby is text."""
    def probe(cells):
        nb = json.dumps({"cells": [{"cell_type": "code", "source": c}
                                   for c in cells]})
        return _notebook_hits(REPO / "notebooks" / "_probe.ipynb", nb)

    _l, _o, rest = probe([["%%script python\n", 'print("Never set TZ=EST")\n']])
    assert not NONPY_AMBIGUOUS.search(rest), "printed text is not a setting"
    _l, offsets, _r = probe([["%%python\n", "from datetime import timezone, timedelta\n",
                              "ET = timezone(timedelta(hours=-5))\n"]])
    assert offsets, "a Python cell magic's body is parsed"
    for header in ("%%bash\n", "%%script bash\n", "%%sh\n"):
        _l, _o, rest = probe([[header, "export TZ=EST\n"]])
        assert NONPY_AMBIGUOUS.search(rest), header
    # Another interpreter is not blanked: it goes to the parse path like any
    # other cell, and whatever does not parse goes to the regex pass. Ruby's
    # `ENV['TZ'] = 'EST'` happens to parse as Python and is reported there;
    # the property is that it is reported SOMEWHERE rather than nowhere.
    legacy, _o, rest = probe([["%%script ruby\n", 'puts "hi"\n', "ENV['TZ'] = 'EST'\n"]])
    assert legacy or NONPY_AMBIGUOUS.search(rest)
    assert 'puts "hi"' in rest, "the line that is not Python reaches the weaker reader"


def test_environment_setters_take_keyword_arguments():
    """`os.environ.setdefault("TZ", default="EST")` installs the zone."""
    legacy, _ = _probe_py('import os\nos.environ.setdefault("TZ", default="EST")\n')
    assert legacy
    legacy, _ = _probe_py('import os\nos.environ.setdefault(key="TZ", default="EST")\n')
    assert legacy
    legacy, _ = _probe_py('import os\nos.environ.setdefault("TZ", "EST")\n')
    assert legacy
    legacy, _ = _probe_py('import os\nos.environ.setdefault("REGION", default="EST")\n')
    assert not legacy
    legacy, _ = _probe_py('import os\nos.environ.setdefault("TZ", default="America/New_York")\n')
    assert not legacy


def test_each_scope_is_traversed_once():
    """The collectors share one materialised node list per scope.

    Each collector re-walked `_scope_nodes(scope)`, and the descent walked it
    again, so a cold `_scan()` was mostly repeated traversal: 23.7 s here and
    39 s on the reviewer's checkout, in the ordinary suite (Codex, PR #993).
    Measured after: 17.4 s. This pins the sharing, not the wall clock -- a
    timing assertion in CI is a flake generator.
    """
    tree = ast.parse("import os\nx = 1\ndef f(tz):\n    return tz\n")
    nodes = list(_scope_nodes(tree))
    calls = []
    real = _scope_nodes

    def counting(scope):
        calls.append(id(scope))
        return real(scope)

    import builtins
    globals_ = globals()
    saved = globals_["_scope_nodes"]
    globals_["_scope_nodes"] = counting
    try:
        _scoped_envs(tree)
    finally:
        globals_["_scope_nodes"] = saved
    # `descend` walks each scope ONCE and shares the list with its five
    # collectors: the module once, `f` once. The two one-time passes that
    # run before the descent, `_declared_global_bindings` and
    # `_nonlocal_bindings`, look INSIDE the inner scopes for `global` and
    # `nonlocal` statements -- which is where those live -- so each walks `f`
    # once more and the module not at all. Measured, not reasoned: the first
    # version of this assertion had the two scopes the other way round. A
    # collector that starts re-walking its scope again shows up here as an
    # extra call against that scope.
    f = tree.body[2]
    assert calls.count(id(tree)) == 1, calls
    assert calls.count(id(f)) == 3, calls
    assert len(calls) == 4, calls
    # And the helpers still accept a scope alone.
    assert _bound_names(tree) == _bound_names(tree, nodes)


# -- Final review (Codex, PR #993) -------------------------------------------
#
# Twelve findings on `e1f3132c`, requested as a full-PR pass. All twelve fixed;
# each test was run against the pre-fix module first and reported nothing (or,
# for the two strippers, blanked the statement it exists to read).


def _scanned_shell(text: str, make: bool = False) -> bool:
    """Would the non-Python scan report `text`? All four matchers `_scan` runs."""
    out = _expand_shell_defaults(_strip_shell_comments(text, make=make), make=make)
    return bool(NONPY_AMBIGUOUS.search(out) or NONPY_UNAMBIGUOUS.search(out)
                or NONPY_FIXED_ZONE.search(out) or NONPY_FIXED_OFFSET.search(out)
                or NONPY_POSIX_ENV_OFFSET.search(out))


def _offenders(body: str) -> list:
    return [o for n, seg in _shell_functions(_strip_shell_comments(body))
            for o in _scheduler_offenders(n, seg)]


def _python_hit_lists(src: str):
    """`_python_hits` on `src`, written UNDER the repository.

    `_python_hits` reports paths relative to `REPO`, so pytest's `tmp_path`
    (outside it) raises. A unique directory inside the checkout, removed
    afterwards, is what `test_the_scan_reads_only_tracked_files` does too.
    """
    import shutil
    d = REPO / f"tmp_probe_{uuid.uuid4().hex}"
    d.mkdir()
    try:
        f = d / "m.py"
        f.write_text(src)
        return _python_hits(f.resolve(), src)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _python_finds(_tmp_path, src: str) -> bool:
    r = _python_hit_lists(src)
    return bool(r and (r[0] or r[1]))


def test_a_dollar_quoted_literal_is_data():
    """`SELECT $$ -- still data $$; SET TIME ZONE 'EST';` runs the SET.

    Inside PostgreSQL's `$$...$$` and `$tag$...$tag$` a `--` is text, and the
    stripper read it as a comment and blanked the executable statement after
    it -- the third stripper defect of this shape, after escape strings and
    the shell's escaped quote (Codex, PR #993 final review).
    """
    for src in ("SELECT $$ -- still data $$; SET TIME ZONE 'EST';",
                "SELECT $tag$ -- x $tag$; SET TIME ZONE 'EST';",
                "SELECT $q$it's -- fine$q$; SET TIME ZONE 'EST';"):
        assert "SET TIME ZONE 'EST'" in _strip_sql_comments(src), src
    # A real comment after the literal is still blanked, and an unterminated
    # dollar quote runs to the end rather than resurrecting a comment.
    assert _strip_sql_comments("SELECT $$x$$; -- SET TIME ZONE 'EST'").rstrip() == "SELECT  'x' ;"
    # An unterminated dollar quote runs to the end of the text: everything
    # after it is literal, so nothing is blanked and nothing is invented.
    src = "SELECT $$ open -- SET TIME ZONE 'EST'"
    assert _strip_sql_comments(src) == src
    # `$1` is a positional parameter, not a delimiter.
    assert _strip_sql_comments("SELECT $1; -- c").rstrip() == "SELECT $1;"


def test_a_pine_escaped_quote_does_not_end_the_string():
    """`x = "literal \" // still data"; timezone = "EST"` keeps the assignment.

    Every Pine string honours a backslash. With escapes off, the escaped quote
    closed the string, `//` read as a comment, and the real setting after it
    was blanked (Codex, PR #993 final review).
    """
    src = 'x = "literal ' + chr(92) + '" // still data"; timezone = "EST"'
    assert 'timezone = "EST"' in _strip_pine_comments(src)
    assert not _strip_pine_comments('// timezone = "EST"').strip()
    assert 'msg = "a // b"' in _strip_pine_comments('msg = "a // b"  // note')
    # SQL keeps its own rule: a backslash in an ordinary literal is a character.
    assert _strip_sql_comments("SELECT 'a" + chr(92) + "'; -- c").rstrip() == "SELECT 'a" + chr(92) + "';"


def test_a_pine_constant_reaches_the_call():
    """`const string MARKET_ZONE = "EST"` then `time(..., MARKET_ZONE)` reports.

    The call carries no literal, and the repository's own scripts pass
    variables such as `tz` to these builtins, so reading only quoted literals
    inside the call was blind to the ordinary form (Codex, PR #993 final
    review).
    """
    src = ('const string MARKET_ZONE = "EST"' + "\n"
           't = time(timeframe.period, session, MARKET_ZONE)' + "\n")
    hits = _pine_call_hits(_strip_pine_comments(src))
    assert hits and hits[0][1] == "EST" and hits[0][2] is False, hits
    assert "MARKET_ZONE" in hits[0][0].group(0)
    # `var`/`:=` spellings, and an offset value.
    src2 = 'var string zone = "-05:00"' + "\n" + 'ts = timestamp(zone, 2026, 1, 1)' + "\n"
    hits2 = _pine_call_hits(_strip_pine_comments(src2))
    assert hits2 and hits2[0][2] is True, hits2
    # The canonical zone by name, an unrelated variable, and a variable that
    # is not a string constant all stay quiet.
    for quiet in ('const string Z = "America/New_York"' + "\n" + "t = time(tf, s, Z)" + "\n",
                  'const string NOTE = "EST"' + "\n" + "t = time(tf, s, tz)" + "\n",
                  "Z = input.string()" + "\n" + "t = time(tf, s, Z)" + "\n"):
        assert not _pine_call_hits(_strip_pine_comments(quiet)), quiet


def test_an_array_element_carrying_flag_text_is_not_a_flag():
    """`flags=(--message-body 'note --time-zone America/New_York')` is zoneless.

    Bash passes one message-body element and no timezone; the substring read
    marked the array as carrying the zone, and the file-wide assertion saw
    the same payload text, so a UTC scheduler passed the whole guard
    (Codex, PR #993 final review).
    """
    body = ("flags=(--message-body 'note --time-zone America/New_York')" + "\n"
            'gcloud scheduler jobs create http j "${flags[@]}"' + "\n")
    assert _offenders(body), "a payload is not a flag"
    # The real spellings still carry it, as separate elements or as `=`.
    for real in ("flags=(--location us-east1 --time-zone America/New_York)",
                 'flags=(--time-zone "America/New_York")',
                 "flags=(--time-zone=America/New_York)"):
        assert not _offenders(real + "\n" + 'gcloud scheduler jobs create http j "${flags[@]}"' + "\n"), real
    assert _elements_carry_zone("--time-zone America/New_York")
    assert not _elements_carry_zone("--message-body 'x --time-zone America/New_York'")
    assert not _elements_carry_zone("--time-zone 'unterminated")


def test_a_function_brace_on_the_next_line_opens_a_scope():
    """`helper()` then `{` alone on the next line is a function.

    The header pattern wanted the brace on the same line, so the standard
    layout opened no scope and the helper's `local` zoned array covered a
    later top-level command that expands an unset array (Codex, PR #993
    final review).
    """
    for header in ("helper()", "function helper", "function helper()"):
        body = (header + "\n{\n"
                "  local flags=(--time-zone America/New_York)\n"
                '  gcloud scheduler jobs create http a "${flags[@]}"\n'
                "}\n"
                'gcloud scheduler jobs create http b "${flags[@]}"\n')
        found = _offenders(body)
        assert len(found) == 1 and "http b" in found[0], (header, found)
        assert [n for n, _ in _shell_functions(body)] == ["<top level>", "helper"], header
        assert len(_function_spans(body)) == 1, header
    # A bare `helper()` NOT followed by a brace is not a function header.
    body = "helper()\necho x\n" + 'gcloud scheduler jobs create http b "${flags[@]}"\n'
    assert [n for n, _ in _shell_functions(body)] == ["<top level>"]
    assert _function_spans(body) == []


def test_every_operand_of_a_declaring_builtin_is_collected():
    """`local X=x LEGACY=EST` binds both, so `export TZ="$LEGACY"` reports.

    The anchored pattern read only the first operand; the second begins after
    whitespace rather than a command boundary (Codex, PR #993 final review).
    """
    body = 'helper() {\n  local X=x LEGACY=EST\n  export TZ="$LEGACY"\n}\n'
    assert _scanned_shell(body)
    scal = _shell_scalars(body)
    assert "LEGACY" in scal and scal["LEGACY"][0][1] == "EST" and scal["LEGACY"][0][2] is True
    assert "X" in scal
    assert _scanned_shell('declare -r A=1 B="2" LEGACY=EST; export TZ="$LEGACY"')
    assert _scanned_shell("export A=1 LEGACY=EST\n" + 'export TZ="$LEGACY"\n')
    # Not statically known, and the canonical zone, stay quiet; a single
    # operand is recorded exactly once.
    assert not _scanned_shell('local X=x LEGACY="$OTHER"; export TZ="$LEGACY"')
    assert not _scanned_shell('local X=x LEGACY=America/New_York; export TZ="$LEGACY"')
    assert len(_shell_scalars("local LEGACY=EST\n")["LEGACY"]) == 1


def test_make_variable_chains_resolve():
    """`A := EST`, `B := $(A)`, `export TZ := $(B)` installs the fixed zone.

    GNU Make resolves `B` to `EST`; discarding every value that mentions `$`
    left `B` unbound and the final reference unresolved (Codex, PR #993 final
    review). Each value folds against the scalars in force at its own offset.
    """
    assert _scanned_shell("A := EST\nB := $(A)\nexport TZ := $(B)\n", make=True)
    assert _scanned_shell("A := EST\nB := ${A}\nC := $(B)\nexport TZ := $(C)\n", make=True)
    assert _scanned_shell("A := -05\nB := $(A):00\nexport TZ := $(B)\n", make=True)
    # A reference to something not static, a later reassignment, and the
    # canonical zone stay quiet.
    assert not _scanned_shell("A := $(shell date)\nB := $(A)\nexport TZ := $(B)\n", make=True)
    assert not _scanned_shell("A := EST\nB := $(A)\nA := America/New_York\nexport TZ := $(A)\n", make=True)
    assert not _scanned_shell("A := America/New_York\nB := $(A)\nexport TZ := $(B)\n", make=True)
    # A self-referencing chain terminates rather than spinning.
    assert not _scanned_shell("A := $(A)\nexport TZ := $(A)\n", make=True)


def test_a_yaml_merge_key_is_applied():
    """`env: [{name: *key, <<: *base}]` with `base: &base {value: EST}` reports.

    The composer leaves `<<` unresolved, so the inherited `value` was never
    associated with the explicit `name` (Codex, PR #993 final review). The
    inherited scalar keeps its own mark.
    """
    text = "base: &base {value: EST}\nkey: &key TZ\nenv: [{name: *key, <<: *base}]\n"
    hits = _yaml_env_pair_hits(text)
    assert hits and hits[0][1] == "EST", hits
    assert text[hits[0][0].start():].startswith("EST")
    # A sequence of merges, and an explicit key winning over an inherited one.
    text2 = ("a: &a {value: America/New_York}\nb: &b {name: TZ}\n"
             "env:\n  - <<: [*a, *b]\n    value: EST\n")
    assert _yaml_env_pair_hits(text2)[0][1] == "EST"
    assert not _yaml_env_pair_hits("base: &base {value: America/New_York}\nenv: [{name: TZ, <<: *base}]\n")
    assert not _yaml_env_pair_hits("base: &base {value: EST}\nenv: [{name: REGION, <<: *base}]\n")


def test_set_env_is_an_environment_setter():
    """`%set_env TZ EST` and `%set_env TZ=EST` reach the shell pass.

    IPython's other documented setter, with the same two forms as `%env`
    (Codex, PR #993 final review).
    """
    assert _classify_magic("%set_env TZ EST") == ("env", "export TZ=EST")
    assert _classify_magic("%set_env TZ=EST") == ("env", "export TZ=EST")
    assert _classify_magic("%set_env PGTZ -05:00")[0] == "env"
    # Read-only forms set nothing.
    assert _classify_magic("%set_env")[0] is None
    # `%set_env NAME` without a value is a READ, exactly like `%env NAME`.
    assert _classify_magic("%set_env TZ")[0] is None
    assert _classify_magic("%set_env TZ")[0] == _classify_magic("%env TZ")[0]


def test_a_partial_of_a_timezone_constructor_is_followed(tmp_path):
    """`ET = functools.partial(ZoneInfo, "EST")` then `ET()` reports.

    The binding collector dropped the `partial(...)` call and the callable
    resolver followed only names and attributes, so the bare `EST` -- ignored
    outside a timezone context by design -- was never given one (Codex,
    PR #993 final review). The call is rebuilt as `ZoneInfo("EST")` so every
    check below the loop head runs on what actually executes.
    """
    assert _python_finds(tmp_path, "import functools\nfrom zoneinfo import ZoneInfo\n"
                                   "ET = functools.partial(ZoneInfo, 'EST')\nz = ET()\n")
    assert _python_finds(tmp_path, "from functools import partial\nfrom zoneinfo import ZoneInfo\n"
                                   "ET = partial(ZoneInfo, 'EST')\nz = ET()\n")
    assert _python_finds(tmp_path, "import functools, pytz\n"
                                   "ET = functools.partial(pytz.timezone, 'EST')\nz = ET()\n")
    assert _python_finds(tmp_path, "import functools\nfrom zoneinfo import ZoneInfo\n"
                                   "mk = functools.partial(ZoneInfo)\nz = mk('EST')\n")
    assert not _python_finds(tmp_path, "import functools\nfrom zoneinfo import ZoneInfo\n"
                                       "ET = functools.partial(ZoneInfo, 'America/New_York')\nz = ET()\n")
    assert not _python_finds(tmp_path, "import functools\nlog = functools.partial(print, 'EST')\nlog()\n")


def test_a_folded_query_is_matched_as_a_statement(tmp_path):
    """`ZONE = "EST"` then `cur.execute(f"SET TIME ZONE {ZONE}")` reports.

    The branch accepted only an `ast.Constant` query while the constant-string
    evaluator could already fold the `JoinedStr`; the folded text now goes
    through the same six embedded-SQL matchers the constant scan uses, from
    one shared list, and is noted at the query (Codex, PR #993 final review).
    """
    assert _python_finds(tmp_path, "ZONE = 'EST'\ncur.execute(f'SET TIME ZONE {ZONE}')\n")
    assert _python_finds(tmp_path, "ZONE = 'EST'\ncur.execute('SET TIME ZONE ' + ZONE)\n")
    assert _python_finds(tmp_path, "OFF = '-05:00'\ncur.execute(f\"SET TIME ZONE '{OFF}'\")\n")
    assert not _python_finds(tmp_path, "ZONE = 'America/New_York'\ncur.execute(f'SET TIME ZONE {ZONE}')\n")
    assert not _python_finds(tmp_path, "T = 'EST'\ncur.execute(f'SELECT * FROM t WHERE tag = {T}')\n")
    assert not _python_finds(tmp_path, "cur.execute(f'SET TIME ZONE {zone_from_request()}')\n")
    # A commented half of a folded statement is still a comment.
    assert not _python_finds(tmp_path, "Z='EST'\ncur.execute(f'-- old: SET TIME ZONE EST\\nSET TIME ZONE America/New_York')\n")
    # The inline form reports exactly once, through the constant scan.
    legacy, offsets = _python_hit_lists("cur.execute(\"SET TIME ZONE 'EST'\")\n")
    assert len(legacy) + len(offsets) == 1
    assert _embedded_sql_hit("SET TIME ZONE 'EST'") == (False, "SET TIME ZONE 'EST'")
    assert _embedded_sql_hit("SELECT 1") is None


def test_setattr_of_a_timezone_attribute_is_an_assignment(tmp_path):
    """`setattr(settings, "timezone", "EST")` is `settings.timezone = "EST"`.

    The call created no assignment node for the attribute branch to read
    (Codex, PR #993 final review). The attribute name goes through the
    environment like every other named constant here.
    """
    assert _python_finds(tmp_path, "setattr(settings, 'timezone', 'EST')\n")
    assert _python_finds(tmp_path, "ATTR = 'time_zone'\nsetattr(cfg, ATTR, 'US/Eastern')\n")
    assert _python_finds(tmp_path, "setattr(cfg, 'tz', '-05:00')\n")
    assert not _python_finds(tmp_path, "setattr(settings, 'timezone', 'America/New_York')\n")
    assert not _python_finds(tmp_path, "setattr(settings, 'region', 'EST')\n")
    assert not _python_finds(tmp_path, "setattr(settings, name, 'EST')\n")


def test_arithmetic_between_timedeltas_is_folded(tmp_path):
    """`timezone(timedelta(hours=-6) + timedelta(hours=1))` is UTC-5.

    The outer `BinOp` was rejected before either operand was totalled, and
    neither inner call is Eastern on its own (Codex, PR #993 final review).
    """
    src = "from datetime import timezone, timedelta\n"
    assert _python_finds(tmp_path, src + "Z = timezone(timedelta(hours=-6) + timedelta(hours=1))\n")
    assert _python_finds(tmp_path, src + "Z = timezone(timedelta(hours=-4) - timedelta(hours=1))\n")
    assert _python_finds(tmp_path, src + "Z = timezone(-(timedelta(hours=6) - timedelta(hours=2)))\n")
    assert _python_finds(tmp_path, src + "BASE = timedelta(hours=-6)\nZ = timezone(BASE + timedelta(hours=2))\n")
    # Not Eastern, or not decidable: left alone rather than guessed at.
    assert not _python_finds(tmp_path, src + "Z = timezone(timedelta(hours=-6) + timedelta(hours=3))\n")
    assert not _python_finds(tmp_path, src + "Z = timezone(timedelta(hours=-6) + step)\n")
    assert not _python_finds(tmp_path, src + "Z = timezone(timedelta(hours=-6) + timedelta(seconds=3599.5))\n")


def test_a_shell_scalar_chain_resolves_through_each_link():
    """`A=EST; B="$A"; export TZ="$B"` exports the frozen zone.

    The value pattern excluded `$`, so `B` was discarded and the export stayed
    unresolved, and the bare `EST` has no context of its own (Codex, PR #993
    final review). Folded in source order, like the Make chain.
    """
    assert _scanned_shell('A=EST; B="$A"; export TZ="$B"\n')
    assert _scanned_shell('A=EST\nB="$A"\nexport TZ="$B"\n')
    assert _scanned_shell('A=EST\nB=${A}\nC=$B\nexport TZ="$C"\n')
    assert _scanned_shell('A=-05:00\nB="$A"\nexport TZ="$B"\n')
    assert not _scanned_shell('A=America/New_York\nB="$A"\nexport TZ="$B"\n')
    # Single quotes do not expand; an unknown or computed link breaks the chain.
    assert not _scanned_shell("A=EST\nB='$A'\nexport TZ=\"$B\"\n")
    assert not _scanned_shell('B="$UNKNOWN"\nexport TZ="$B"\n')
    assert not _scanned_shell('A=EST\nB="${A:-UTC}"\nexport TZ="$B"\n')
    assert not _scanned_shell('A=EST\nB="$(printf x)"\nexport TZ="$B"\n')
    # Position still decides: a later rebinding does not reach an earlier link.
    assert not _scanned_shell('A=UTC\nB="$A"\nexport TZ="$B"\nA=EST\n')
    assert _shell_scalars('A=EST\nB="$A"\n')["B"] == [(6, "EST", False)]


def test_a_dormant_global_writer_does_not_hide_a_module_setting(tmp_path):
    """Defining `def reset(): global TIME_ZONE; TIME_ZONE = "UTC"` runs nothing.

    Importers still receive the frozen `EST`, and the export check skipped it
    because the helper could replace it (Codex, PR #993 final review). A
    function counts only when a module-level statement invokes it after the
    assignment; a class body runs at import and still counts.
    """
    writer = 'def reset():\n    global TIME_ZONE\n    TIME_ZONE = "UTC"\n'
    assert _python_finds(tmp_path, 'TIME_ZONE = "EST"\n' + writer)
    assert not _python_finds(tmp_path, 'TIME_ZONE = "EST"\n' + writer + "reset()\n")
    assert not _python_finds(tmp_path, 'TIME_ZONE = "EST"\n' + writer + "if True:\n    reset()\n")
    # Called BEFORE the assignment, the assignment wins.
    assert _python_finds(tmp_path, writer + 'reset()\nTIME_ZONE = "EST"\n')
    # A class body runs when the class is defined; a method does not.
    assert not _python_finds(tmp_path, 'TIME_ZONE = "EST"\nclass _Init:\n    global TIME_ZONE\n    TIME_ZONE = "UTC"\n')
    assert _python_finds(tmp_path, 'TIME_ZONE = "EST"\nclass Svc:\n    def reset(self):\n        global TIME_ZONE\n        TIME_ZONE = "UTC"\n')
    # A writer nested in a function that IS called at import runs with it.
    assert not _python_finds(tmp_path, 'TIME_ZONE = "EST"\ndef init():\n    def inner():\n        global TIME_ZONE\n        TIME_ZONE = "UTC"\n    inner()\ninit()\n')


def test_zero_padded_posix_offsets_are_fixed_zones(tmp_path):
    """`TZ=EST05` is `TZ=EST5`: POSIX pads the offset as it likes.

    Only the shortest spelling was known, and the ambiguous-name matcher
    rightly refuses `EST` followed by a digit, so the padded forms passed both
    paths (Codex, PR #993 final review).
    """
    for value in ("EST05", "EDT04", "EST+5", "EST+05", "EST05:00", "EST5:00",
                  "EDT04:00", "est05"):
        assert _scanned_shell(f"export TZ={value}\n"), value
        assert _python_finds(tmp_path, f'import os\nos.environ["TZ"] = "{value}"\n'), value
    assert _python_finds(tmp_path, 'from dateutil.tz import tzstr\nz = tzstr("EST05")\n')
    assert NONPY_FIXED_ZONE.search("tzstr EST05")
    assert NONPY_FIXED_ZONE.search("tzstr EST5:00")
    # `EST5:30` is UTC-5:30: as a literal, `EST5` claimed its prefix.
    assert not NONPY_FIXED_ZONE.search("tzstr EST5:30")
    # A DST rule is not a fixed offset in either padding; `EST5EDT` is still
    # reported, by the backward-link matcher, as the legacy name it is.
    for value in ("EST5EDT", "EST05EDT"):
        assert not NONPY_FIXED_OFFSET.search(f"export TZ={value}"), value
    assert NONPY_UNAMBIGUOUS.search("export TZ=EST5EDT")
    # An offset that is not Eastern, or an invalid padding: clean.
    for value in ("EST03", "EST050", "EST5:30"):
        assert not _scanned_shell(f"export TZ={value}\n"), value
        assert not NONPY_FIXED_OFFSET.search(f"export TZ={value}"), value


def test_a_shell_comparison_is_not_an_assignment():
    """`if [ "$TZ" = EST ]` compares a variable it never sets.

    `_Q` consumed the closing quote and `TZ" = EST` read as an assignment, so
    the predicate failed CI (Codex, PR #993 final review). `$TZ` is a read.
    """
    for text in ('if [ "$TZ" = EST ]; then echo x; fi\n',
                 'if [ "$TZ" = "EST" ]; then :; fi\n',
                 'test "$TZ" = EST && echo x\n',
                 '[[ "$TZ" == EST ]] && echo x\n',
                 '[ "$PGTZ" = EST ] && echo x\n',
                 '[ "$TZ" = -05:00 ] && echo x\n'):
        assert not _scanned_shell(text), text
    # A real assignment beside the comparison, and the parameter forms that
    # assign, still report.
    assert _scanned_shell('if [ "$TZ" = EST ]; then export TZ=EST; fi\n')
    assert _scanned_shell(': "${TZ:=EST}"\n')
    assert _scanned_shell('export TZ="${TZ:-EST}"\n')
    assert _scanned_shell('export TZ=EST\n')


def test_ansi_c_quoted_values_are_read_as_their_literal():
    """`export TZ=$'EST'` is `export TZ='EST'` once bash decodes it.

    The context matchers stopped at the `$` and the scalar collector refused
    a `$` in a value, so both spellings passed (Codex, PR #993 final review).
    """
    assert _scanned_shell("export TZ=$'EST'\n")
    assert _scanned_shell("export TZ=$'-05:00'\n")
    assert _scanned_shell("export TZ=$'\\x45ST'\n")           # \x45 is E
    assert _scanned_shell("LEGACY=$'EST'\nexport TZ=\"$LEGACY\"\n")
    assert not _scanned_shell("export TZ=$'America/New_York'\n")
    assert not _scanned_shell("echo $'set TZ=EST to reproduce'\n")
    # Width-preserving, so every later offset still means what it says.
    text = "export TZ=$'\\x45ST'\nexport LEGACY=EST\n"
    out = _normalize_ansi_c_quotes(text)
    assert len(out) == len(text) and out.index("LEGACY") == text.index("LEGACY")
    assert out.startswith("export TZ='EST'    \n")
    # A literal a plain single-quoted string cannot hold is left as written.
    assert _normalize_ansi_c_quotes("x=$'it\\'s'") == "x=$'it\\'s'"


def test_destructured_configuration_targets_are_paired_with_their_values(tmp_path):
    """`os.environ["TZ"], other = "EST", value` installs the frozen zone.

    The loop examined each top-level target only, and a tuple is neither a
    `Subscript` nor an `Attribute` (Codex, PR #993 final review).
    """
    assert _python_finds(tmp_path, 'import os\nos.environ["TZ"], other = "EST", 1\n')
    assert _python_finds(tmp_path, 'other, settings.timezone = 1, "-05:00"\n')
    assert _python_finds(tmp_path, '(os.environ["TZ"], a), b = ("EST", 1), 2\n')
    assert _python_finds(tmp_path, '[os.environ["TZ"], a] = ["EST", 1]\n')
    assert _python_finds(tmp_path, 'os.environ["TZ"], *rest = "EST", 1, 2\n')
    assert _python_finds(tmp_path, '*head, os.environ["TZ"] = 1, 2, "EST"\n')
    # A module setting written through a tuple is still an export.
    assert _python_finds(tmp_path, 'TIME_ZONE, other = "EST", 1\n')
    # Positions matter, and a value that is not a literal sequence is not guessed.
    assert not _python_finds(tmp_path, 'os.environ["TZ"], other = "America/New_York", "EST"\n')
    assert not _python_finds(tmp_path, 'os.environ["TZ"], other = pair\n')
    assert not _python_finds(tmp_path, 'os.environ["TZ"], other = "EST"\n')


def test_sql_text_in_a_diagnostic_is_not_a_statement(tmp_path):
    """`logger.info("SET TIME ZONE 'EST' was rejected")` executes nothing.

    The statement shape alone classified the string as SQL and failed CI
    (Codex, PR #993 final review). Only a DIRECT argument of an output call is
    exempt; the same text bound to a name, or handed to an executor, is read.
    """
    assert not _python_finds(tmp_path, "import logging\nlog = logging.getLogger(__name__)\nlog.info(\"SET TIME ZONE 'EST' was rejected\")\n")
    assert not _python_finds(tmp_path, "print(\"SET TIME ZONE 'EST' failed\")\n")
    assert not _python_finds(tmp_path, "logging.warning(\"retrying after: SET TIME ZONE 'EST'\")\n")
    assert not _python_finds(tmp_path, "logger.error(f\"rejected: SET TIME ZONE 'EST' for {user}\")\n")
    assert not _python_finds(tmp_path, "logger.error(\"rejected: \" + \"SET TIME ZONE 'EST'\")\n")
    assert not _python_finds(tmp_path, "warnings.warn(\"-c timezone=EST is no longer honoured\")\n")
    # Still read: an executor, a binding logged and then executed, an
    # executor nested inside the log call.
    assert _python_finds(tmp_path, "cur.execute(\"SET TIME ZONE 'EST'\")\n")
    assert _python_finds(tmp_path, "SQL = \"SET TIME ZONE 'EST'\"\nlog.info(SQL)\ncur.execute(SQL)\n")
    assert _python_finds(tmp_path, "log.info(cur.execute(\"SET TIME ZONE 'EST'\"))\n")
    assert _python_finds(tmp_path, "log.info(\"x\", \"SET TIME ZONE 'EST'\") if False else cur.execute(\"SET TIME ZONE 'EST'\")\n")


def test_a_pine_reassignment_is_the_binding_in_force():
    """`zone := "EST"` after `zone = "America/New_York"` hands `time()` EST.

    The first binding was kept as a constant, so the frozen zone passed and,
    reversed, a canonical call failed CI (Codex, PR #993 final review).
    """
    call = 't = time(timeframe.period, session, zone)\n'
    assert _pine_call_hits('string zone = "America/New_York"\nzone := "EST"\n' + call)
    assert not _pine_call_hits('string zone = "EST"\nzone := "America/New_York"\n' + call)
    # Position, not order of appearance: a rebinding AFTER the call does not
    # reach it.
    assert _pine_call_hits('zone = "EST"\n' + call + 'zone := "America/New_York"\n')
    assert not _pine_call_hits('zone = "America/New_York"\n' + call + 'zone := "EST"\n')
    assert _pine_constants('a = "x"\na := "y"\n')["a"] == [(0, "x", None), (8, "y", None)]


def test_an_escaped_quote_does_not_end_a_shell_diagnostic():
    """`echo "Never set \\"TZ=EST\\" here"` prints; it configures nothing.

    The quoted-argument pattern read the escaped quote as the closing one and
    left `TZ=EST` exposed between two blanked fragments (Codex, PR #993 final
    review).
    """
    assert not _scanned_shell('echo "Never set \\"TZ=EST\\" here"\n')
    assert not _scanned_shell('printf "%s\\n" "set \\"TZ=EST\\" to reproduce"\n')
    assert not _scanned_shell('echo "quoted \\"x\\""; echo "TZ=EST"\n')
    # A real assignment after the diagnostic, and a diagnostic that WRITES
    # configuration, still report.
    assert _scanned_shell('echo "quoted \\"x\\""; export TZ=EST\n')
    assert _scanned_shell('echo "\\"TZ=EST\\"" > app.env\n')


def test_a_function_body_assignment_runs_only_when_the_function_does():
    """Defining `helper() { LEGACY=...; }` assigns nothing until it is called.

    Ordered by position alone, the dormant body was the value in force: the
    frozen export read as canonical and, reversed, a correct script failed CI
    (Codex, PR #993 final review). A body assignment is visible inside its
    body and, outside it, from each top-level call after the definition.
    """
    multi = 'LEGACY={a}\nhelper() {{\n    LEGACY={b}\n}}\n{call}export TZ="$LEGACY"\n'
    one = 'LEGACY={a}\nhelper() {{ LEGACY={b}; }}\n{call}export TZ="$LEGACY"\n'
    for form in (multi, one):
        est_then_dormant = form.format(a="EST", b="America/New_York", call="")
        canonical_then_dormant = form.format(a="America/New_York", b="EST", call="")
        assert _scanned_shell(est_then_dormant), form
        assert not _scanned_shell(canonical_then_dormant), form
        # Called, the body runs and its assignment is in force afterwards.
        assert _scanned_shell(form.format(a="America/New_York", b="EST", call="helper\n")), form
        assert not _scanned_shell(form.format(a="EST", b="America/New_York", call="helper\n")), form
        assert _scanned_shell(form.format(a="America/New_York", b="EST",
                                          call="if true; then helper; fi\n")), form
    # Inside its own body the assignment is in force at once, as before.
    assert _scanned_shell('LEGACY=America/New_York\nhelper() {\n    LEGACY=EST\n    export TZ="$LEGACY"\n}\n')
    # A call BEFORE the export but before the definition is not a call the
    # shell could make; the definition must precede it.
    assert not _scanned_shell('LEGACY=America/New_York\nhelper\nhelper() {\n    LEGACY=EST\n}\nexport TZ="$LEGACY"\n')
    # The definition line itself is not an invocation.
    assert _invoked_at('helper() {\n  :\n}\nhelper\n', "helper",
                       _named_function_spans('helper() {\n  :\n}\nhelper\n')) == [17]
    assert _named_function_spans('function f {\n  :\n}\ng()\n{\n  :\n}\n')[0][0] == "f"
    assert _named_function_spans('function f {\n  :\n}\ng()\n{\n  :\n}\n')[1][0] == "g"


def test_tzrange_is_frozen_only_without_daylight_time(tmp_path):
    """`tzrange("X", -18000, "Y", -21600)` alternates; it is not a fixed zone.

    The standard offset alone was compared, so a zone that is UTC-5 in winter
    and UTC-6 in summer -- not Eastern in either -- failed the offset guard
    (Codex, PR #993 final review).
    """
    head = "from dateutil.tz import tzrange, tzoffset\n"
    def offsets_of(src):
        return _python_hit_lists(head + src)[1]
    assert not offsets_of('z = tzrange("X", -18000, "Y", -21600)\n')
    assert not offsets_of('z = tzrange("X", stdoffset=-18000, dstabbr="Y")\n')
    assert not offsets_of('z = tzrange("X", -18000, dstabbr="Y", dstoffset=-14400)\n')
    # No daylight time, or daylight time at the same offset, is frozen.
    assert offsets_of('z = tzrange("EST", -18000)\n')
    assert offsets_of('z = tzrange("EST", stdoffset=-18000)\n')
    assert offsets_of('z = tzrange("X", -18000, None)\n')
    assert offsets_of('z = tzrange("X", -18000, "Y", -18000)\n')
    assert offsets_of('z = tzoffset("EST", -18000)\n')
    # A daylight abbreviation that is not statically known is not decided.
    assert not offsets_of('z = tzrange("X", -18000, dst_name())\n')


def test_a_dict_key_bound_to_a_name_is_read(tmp_path):
    """`KEY = "TZ"; env={KEY: "EST"}` gives the child the frozen zone.

    The dict branch accepted literal keys only, unlike the subscript branch
    beside it (Codex, PR #993 final review).
    """
    assert _python_finds(tmp_path, 'KEY = "TZ"\nsubprocess.run(cmd, env={KEY: "EST"})\n')
    assert _python_finds(tmp_path, 'KEY = "timezone"\ncfg = {KEY: "-05:00"}\n')
    assert _python_finds(tmp_path, 'cfg = {**base, "TZ": "EST"}\n')
    assert not _python_finds(tmp_path, 'KEY = "PATH"\ncfg = {KEY: "EST"}\n')
    assert not _python_finds(tmp_path, 'cfg = {key_from_call(): "EST"}\n')
    assert not _python_finds(tmp_path, 'KEY = "TZ"\ncfg = {KEY: "America/New_York"}\n')


def test_a_statically_dead_call_does_not_run_a_global_writer(tmp_path):
    """`if False: reset()` invokes nothing; the exported EST stands.

    The module-level call inside a dead branch counted as an invocation and
    suppressed the finding (Codex, PR #993 final review).
    """
    writer = 'TIME_ZONE = "EST"\ndef reset():\n    global TIME_ZONE\n    TIME_ZONE = "UTC"\n'
    for dead in ("if False:\n    reset()\n", "if 0:\n    reset()\n",
                 "if not True:\n    reset()\n", "while False:\n    reset()\n",
                 "if True:\n    pass\nelse:\n    reset()\n"):
        assert _python_finds(tmp_path, writer + dead), dead
    for live in ("if True:\n    reset()\n", "reset()\n", "if flag:\n    reset()\n",
                 "if False:\n    pass\nelse:\n    reset()\n", "while flag:\n    reset()\n"):
        assert not _python_finds(tmp_path, writer + live), live


def test_a_nested_yaml_merge_resolves_transitively():
    """`{name: TZ, <<: *mid}` where `mid` itself merges `base` inherits base's value.

    The merge loop copied `mid`'s unresolved `<<` entry instead of flattening
    it (Codex, PR #993 final review).
    """
    assert _yaml_env_pair_hits('base: &base {value: EST}\nmid: &mid {<<: *base}\nenv: [{name: TZ, <<: *mid}]\n')
    assert _yaml_env_pair_hits('base: &base {value: EST}\nmid: &mid {<<: *base}\ntop: &top {<<: *mid}\nenv: [{name: TZ, <<: *top}]\n')
    assert _yaml_env_pair_hits('base: &base {name: TZ}\nmid: &mid {<<: [*base], value: "-05:00"}\nenv: [{<<: *mid}]\n')
    # An explicit key beside the merge still wins, at every level.
    assert not _yaml_env_pair_hits('base: &base {value: EST}\nmid: &mid {<<: *base, value: America/New_York}\nenv: [{name: TZ, <<: *mid}]\n')
    assert not _yaml_env_pair_hits('base: &base {value: EST}\nmid: &mid {<<: *base}\nenv: [{name: TZ, <<: *mid, value: America/New_York}]\n')
    hit = _yaml_env_pair_hits('base: &base {value: EST}\nmid: &mid {<<: *base}\nenv: [{name: TZ, <<: *mid}]\n')[0][0]
    assert hit.start() == len("base: &base {value: ")      # the inherited scalar's own mark


def test_a_partial_needs_functools_provenance(tmp_path):
    """A project's own `partial` is not `functools.partial`.

    A custom `partial(ZoneInfo, "EST")` returning a lambda was rebuilt as a
    real `ZoneInfo("EST")` and failed CI (Codex, PR #993 final review).
    """
    body = 'ET = partial(ZoneInfo, "EST")\nz = ET()\n'
    assert not _python_finds(tmp_path, "from zoneinfo import ZoneInfo\ndef partial(f, *a):\n    return lambda: None\n" + body)
    assert not _python_finds(tmp_path, "from zoneinfo import ZoneInfo\nfrom toolz import partial\n" + body)
    assert _python_finds(tmp_path, "from zoneinfo import ZoneInfo\nfrom functools import partial\n" + body)
    assert _python_finds(tmp_path, "from zoneinfo import ZoneInfo\nfrom functools import partial as p\nET = p(ZoneInfo, 'EST')\nz = ET()\n")
    assert _python_finds(tmp_path, "from zoneinfo import ZoneInfo\nimport functools\nET = functools.partial(ZoneInfo, 'EST')\nz = ET()\n")
    assert _python_finds(tmp_path, "from zoneinfo import ZoneInfo\nimport functools as ft\nET = ft.partial(ZoneInfo, 'EST')\nz = ET()\n")


def test_a_name_used_as_an_update_pair_key_is_read(tmp_path):
    """`KEY = "TZ"; os.environ.update([(KEY, "EST")])` installs the zone.

    The pair path accepted literal keys only, unlike the dict and subscript
    paths beside it (Codex, PR #993 final review).
    """
    assert _python_finds(tmp_path, 'import os\nKEY = "TZ"\nos.environ.update([(KEY, "EST")])\n')
    assert _python_finds(tmp_path, 'import os\nKEY = "timezone"\nos.environ.update([(KEY, "-05:00")])\n')
    assert not _python_finds(tmp_path, 'import os\nKEY = "PATH"\nos.environ.update([(KEY, "EST")])\n')
    assert not _python_finds(tmp_path, 'import os\nos.environ.update([(key(), "EST")])\n')


def test_output_consumed_by_process_substitution_or_eval_is_configuration():
    """`source <(printf 'TZ=EST')` runs the assignment it prints.

    The output pass read `printf` as a diagnostic and blanked the text that
    becomes configuration (Codex, PR #993 final review).
    """
    for text in ("source <(printf 'TZ=EST')\n", ". <(printf 'TZ=EST')\n",
                 "eval \"$(printf 'TZ=EST')\"\n", "eval $(printf 'TZ=EST')\n",
                 "eval \"`printf 'TZ=EST'`\"\n", "bash -c \"$(printf 'TZ=EST')\"\n",
                 "if true; then eval \"$(echo 'TZ=EST')\"; fi\n"):
        assert _scanned_shell(text), text
    # Printed, shown, or merely stored: still a diagnostic.
    for text in ("echo 'TZ=EST'\n", "echo \"$(printf 'TZ=EST')\"\n",
                 "X=$(printf 'TZ=EST')\n", "printf 'TZ=EST' | cat\n" if False else "echo 'TZ=EST' >&2\n"):
        assert not _scanned_shell(text), text
    assert _output_is_captured("source <(")
    assert _output_is_captured('eval "$(')
    assert not _output_is_captured("X=$(")
    assert not _output_is_captured("echo '$(' ; ")


def test_a_pine_call_with_nested_parentheses_is_read():
    """`time(timeframe.period, outer(inner(session)), "EST")` is a call.

    The call regex allowed one nested level, so this was not matched at all
    and its fixed zone passed (Codex, PR #993 final review).
    """
    assert _pine_call_hits('t = time(timeframe.period, outer(inner(session)), "EST")\n')
    assert _pine_call_hits('t = time(timeframe.period, a(b(c(session))), "EST")\n')
    assert _pine_call_hits('t = time(f("(", x), session, "EST")\n')          # a paren in a string is data
    assert _pine_call_hits('zone = "EST"\nt = time(timeframe.period, outer(inner(session)), zone)\n')
    assert not _pine_call_hits('t = time(timeframe.period, outer(inner(session)), "America/New_York")\n')
    assert not _pine_call_hits('t = time(timeframe.period, outer(inner(session), "EST"\n')   # unterminated
    assert [c[1] for c in _pine_tz_calls('time(a(b())) time_close(x) timestamp("EDT", 2024)')] == ["time", "time_close", "timestamp"]


def test_a_nested_sql_block_comment_stays_a_comment():
    """`/* outer /* inner */ SET TIME ZONE 'EST'; */` is one comment.

    PostgreSQL nests block comments, and a single flag closed at the inner
    `*/` and exposed the SET (Codex, PR #993 final review).
    """
    assert not NONPY_AMBIGUOUS.search(_strip_sql_comments("/* outer /* inner */ SET TIME ZONE 'EST'; */\n"))
    assert not NONPY_AMBIGUOUS.search(_strip_sql_comments("/* a /* b /* c */ */ SET TIME ZONE 'EST'; */\n"))
    assert NONPY_AMBIGUOUS.search(_strip_sql_comments("/* a */ SET TIME ZONE 'EST';\n"))
    assert NONPY_AMBIGUOUS.search(_strip_sql_comments("/* a /* b */ */ SET TIME ZONE 'EST';\n"))
    # A `/*` inside a string literal is data, and Pine does not nest.
    assert NONPY_AMBIGUOUS.search(_strip_sql_comments("SELECT '/* x'; SET TIME ZONE 'EST';\n"))
    assert "timezone" in _strip_pine_comments('/* a /* b */ timezone = "EST"\n')


def test_a_setting_under_a_module_level_compound_statement_is_an_export(tmp_path):
    """`if True: TIME_ZONE = "EST"` is a module attribute.

    Only direct `tree.body` statements counted as module level (Codex,
    PR #993 final review). Reachable ones count; a dead branch binds nothing.
    """
    for src in ('if True:\n    TIME_ZONE = "EST"\n',
                'if flag:\n    TIME_ZONE = "EST"\n',
                'try:\n    TIME_ZONE = "EST"\nexcept Exception:\n    pass\n',
                'for _ in range(1):\n    TIME_ZONE = "EST"\n',
                'with ctx():\n    TIME_ZONE = "EST"\n',
                'if flag:\n    class Config:\n        TIME_ZONE = "EST"\n'):
        assert _python_finds(tmp_path, src), src
    for src in ('if False:\n    TIME_ZONE = "EST"\n',
                'def f():\n    TIME_ZONE = "EST"\n',
                'if True:\n    def f():\n        TIME_ZONE = "EST"\n'):
        assert not _python_finds(tmp_path, src), src


def test_pine_function_locals_do_not_shadow_globals():
    """A helper's local `zone` is not the `zone` a top-level call reads.

    The file-wide binding list read the helper's local as the value in force
    and, reversed, failed CI on a canonical call (Codex, PR #993 final
    review).
    """
    call = "t = time(timeframe.period, session, zone)\n"
    helper = "helper() =>\n    zone = {local}\n    zone\n"
    assert _pine_call_hits('zone = "EST"\n' + helper.format(local='"America/New_York"') + call)
    assert not _pine_call_hits('zone = "America/New_York"\n' + helper.format(local='"EST"') + call)
    # Inside the helper, its own binding is the one in force.
    assert _pine_call_hits('zone = "America/New_York"\nhelper() =>\n    zone = "EST"\n    ' + call)
    assert not _pine_call_hits('zone = "EST"\nhelper() =>\n    zone = "America/New_York"\n    ' + call)
    # A global rebinding after the helper still reaches a later call.
    assert _pine_call_hits('zone = "America/New_York"\n' + helper.format(local='"UTC"') + 'zone := "EST"\n' + call)
    assert _pine_function_spans('f(x) =>\n    a = 1\n\n    b = 2\nc = 3\n') == [(8, 29)]


def test_make_recursive_variables_expand_where_they_are_used():
    """`B = $(A)` is GNU Make's recursive variable: `A` is read at the use.

    Folding at the definition froze `B` at the earlier `A` and, reversed,
    failed CI on a canonical export (Codex, PR #993 final review).
    """
    assert _scanned_shell("A=America/New_York\nB=$(A)\nA=EST\nexport TZ=$(B)\n", make=True)
    assert not _scanned_shell("A=EST\nB=$(A)\nA=America/New_York\nexport TZ=$(B)\n", make=True)
    # `:=` and `::=` are immediate and keep the value at their definition.
    assert _scanned_shell("A=EST\nB:=$(A)\nA=America/New_York\nexport TZ=$(B)\n", make=True)
    assert not _scanned_shell("A=America/New_York\nB::=$(A)\nA=EST\nexport TZ=$(B)\n", make=True)
    # `?=` binds only a name not already set, and is recursive when it does.
    assert _scanned_shell("A?=EST\nexport TZ=$(A)\n", make=True)
    assert not _scanned_shell("A=America/New_York\nA?=EST\nexport TZ=$(A)\n", make=True)
    # A self-reference is not static and does not spin.
    assert not _scanned_shell("A=$(A)x\nexport TZ=$(A)\n", make=True)


def test_a_nested_global_writer_must_itself_run(tmp_path):
    """An invoked `init()` that only DEFINES `inner()` runs nothing of inner's.

    The ancestor walk stopped at the first invoked enclosing function and
    suppressed the exported EST (Codex, PR #993 final review).
    """
    inner = 'TIME_ZONE = "EST"\ndef init():\n    def inner():\n        global TIME_ZONE\n        TIME_ZONE = "UTC"\n{call}\ninit()\n'
    assert _python_finds(tmp_path, inner.format(call=""))
    assert not _python_finds(tmp_path, inner.format(call="    inner()"))
    assert _python_finds(tmp_path, inner.format(call="    if False:\n        inner()"))
    # Three levels: every link must run.
    three = 'TIME_ZONE = "EST"\ndef init():\n    def mid():\n        def inner():\n            global TIME_ZONE\n            TIME_ZONE = "UTC"\n{a}\n{b}\ninit()\n'
    assert not _python_finds(tmp_path, three.format(a="        inner()", b="    mid()"))
    assert _python_finds(tmp_path, three.format(a="        pass", b="    mid()"))
    assert _python_finds(tmp_path, three.format(a="        inner()", b="    pass"))
    # A method is never invoked by name at import, even inside a called function.
    assert _python_finds(tmp_path, 'TIME_ZONE = "EST"\ndef init():\n    class C:\n        def reset(self):\n            global TIME_ZONE\n            TIME_ZONE = "UTC"\n    reset()\ninit()\n')


def test_a_shell_assignment_after_a_control_keyword_is_collected():
    """`if true; then LEGACY=EST; fi; export TZ="$LEGACY"` exports EST.

    The scalar pattern opened a command only at a line start or after
    punctuation, so the assignment after `then` was never collected (Codex,
    PR #993 final review).
    """
    for text in ('if true; then LEGACY=EST; fi; export TZ="$LEGACY"\n',
                 'if false; then :; else LEGACY=EST; fi; export TZ="$LEGACY"\n',
                 'for i in 1; do LEGACY=EST; done; export TZ="$LEGACY"\n',
                 'case x in x) LEGACY=EST;; esac; export TZ="$LEGACY"\n',
                 'while false; do :; done; if true; then export LEGACY=EST; fi; export TZ="$LEGACY"\n'):
        assert _scanned_shell(text), text
    assert not _scanned_shell('if true; then LEGACY=America/New_York; fi; export TZ="$LEGACY"\n')
    assert _shell_scalars('if true; then LEGACY=EST; fi\n')["LEGACY"][0][1] == "EST"


def test_make_append_defines_or_extends():
    """`A += EST` defines an undefined `A`; otherwise it appends, keeping the flavour.

    `_MAKE_SCALAR` did not know `+=`, so the binding was absent at expansion
    (Codex, PR #993 final review).
    """
    assert _scanned_shell("A += EST\nexport TZ = $(A)\n", make=True)
    assert _scanned_shell("A := EST\nA += x\nexport TZ = $(A)\n", make=True)
    assert _scanned_shell("A = $(B)\nA += x\nB = EST\nexport TZ = $(A)\n", make=True)   # recursive stays recursive
    assert not _scanned_shell("A = America/New_York\nA += EST\nexport TZ = $(A)\n", make=True)
    assert not _scanned_shell("A += America/New_York\nexport TZ = $(A)\n", make=True)


def test_pine_string_expressions_are_folded():
    """`time(timeframe.period, session, "E" + "ST")` receives EST.

    Each fragment was read on its own and neither is forbidden alone (Codex,
    PR #993 final review). Bound names fold too, so a concatenation stored in
    a variable is the same.
    """
    call = 't = time(timeframe.period, session, {arg})\n'
    assert _pine_call_hits(call.format(arg='"E" + "ST"'))
    assert _pine_call_hits(call.format(arg='"US/" + "Eastern"'))
    assert _pine_call_hits('z = "E" + "ST"\n' + call.format(arg="z"))
    assert _pine_call_hits('p = "US/"\n' + call.format(arg='p + "Eastern"'))
    assert _pine_call_hits('a = "E"\nb = a + "ST"\n' + call.format(arg="b"))
    assert not _pine_call_hits(call.format(arg='"America/" + "New_York"'))
    assert not _pine_call_hits(call.format(arg='"E" + unknown'))
    assert not _pine_call_hits(call.format(arg='"E" + f("ST")'))
    src = call.format(arg='"E" + "ST"')
    assert src[_pine_call_hits(src)[0][0].start():].startswith('"E" + "ST"')
    assert _pine_string_expr('"a" + b + \'c\'', {"b": [(0, "B", None)]}, 10, []) == "aBc"
    assert _pine_string_expr('"a" + f(x)', {}, 10, []) is None


def test_every_conventional_makefile_name_is_collected():
    """`GNUmakefile` and `makefile` are read by Make without being told.

    The source collector listed only `Makefile` and `*.mk`, so a tracked
    file under either other name bypassed both guards while `_reads_as_make`
    already knew it (Codex, PR #993 final review).
    """
    for name in ("Makefile", "GNUmakefile", "makefile"):
        assert name in SOURCE_PATTERNS, name
        assert _reads_as_make(pathlib.Path(name)), name
    assert "*.mk" in SOURCE_PATTERNS


def test_a_module_setting_assigned_with_a_walrus_is_an_export(tmp_path):
    """`if (TIME_ZONE := "EST"):` at module scope exports the name.

    Only `Assign` and `AnnAssign` were read as configuration writes (Codex,
    PR #993 final review).
    """
    assert _python_finds(tmp_path, 'if (TIME_ZONE := "EST"):\n    pass\n')
    assert _python_finds(tmp_path, 'print(tz := "-05:00")\n')
    assert not _python_finds(tmp_path, 'if (TIME_ZONE := "America/New_York"):\n    pass\n')
    assert not _python_finds(tmp_path, 'def f():\n    if (TIME_ZONE := "EST"):\n        pass\n')
    assert not _python_finds(tmp_path, 'if False:\n    if (TIME_ZONE := "EST"):\n        pass\n')


def test_env_setter_arguments_are_unpacked(tmp_path):
    """`os.putenv(*("TZ", "EST"))` installs the zone.

    The setter branch read `node.args[0]` and saw a `Starred` (Codex, PR #993
    final review).
    """
    assert _python_finds(tmp_path, 'import os\nos.putenv(*("TZ", "EST"))\n')
    assert _python_finds(tmp_path, 'import os\nos.environ.setdefault(*("TZ", "-05:00"))\n')
    assert _python_finds(tmp_path, 'import os\nARGS = ("TZ", "EST")\nos.putenv(*ARGS)\n')
    assert _python_finds(tmp_path, 'import os\nos.putenv(*["TZ"], **{"value": "EST"})\n')
    assert not _python_finds(tmp_path, 'import os\nos.putenv(*("PATH", "EST"))\n')
    assert not _python_finds(tmp_path, 'import os\nos.putenv(*args)\n')


def test_postgres_alternate_string_delimiters_are_read():
    """`SET TIME ZONE $$EST$$`, `E'EST'` and `$tz$-05:00$tz$` install what the
    single-quoted forms install, and the matchers read them the same way
    (Codex, PR #993 final review)."""
    for sql in ("SET TIME ZONE $$EST$$;", "SET TIME ZONE E'EST';",
                "SET TIME ZONE $tz$EST$tz$;", "SET TIME ZONE N'EST';",
                "SET TIME ZONE U&'EST';", "set time zone e'EST';"):
        out = _strip_sql_comments(sql)
        assert len(out) == len(sql), sql
        assert NONPY_AMBIGUOUS.search(out), (sql, out)
    out = _strip_sql_comments("SELECT set_config('timezone', $$-05:00$$, false);")
    assert NONPY_FIXED_OFFSET.search(out), out
    out = _strip_sql_comments("SET TIME ZONE $$-5$$;")
    assert NONPY_SQL_NUMERIC_OFFSET.search(out), out
    # Width kept; a comment inside the body stays data; an unmatched opener
    # and an identifier that happens to end in E are left as written.
    assert _strip_sql_comments("SELECT $$-- x$$;") == "SELECT  '-- x' ;"
    assert _strip_sql_comments("SELECT $$oops;") == "SELECT $$oops;"
    assert _strip_sql_comments("SELECT CASE'x' END;") == "SELECT CASE'x' END;"
    # And through a Python string.
    legacy, _ = _probe_py('cur.execute("SET TIME ZONE $$EST$$")\n')
    assert legacy, "a dollar-quoted zone in an embedded statement"
    legacy, _ = _probe_py('cur.execute("SET TIME ZONE E\'EST\'")\n')
    assert legacy, "an escape-string zone in an embedded statement"


def test_a_posix_tz_with_utc_or_gmt_is_a_fixed_offset(tmp_path):
    """`TZ=UTC+5` is UTC-5 all year, POSIX's sign; `TZ=UTC-5` is not Eastern.
    Only where the value is a process or session TZ (Codex, PR #993 final
    review)."""
    for line in ("export TZ=UTC+5", "export TZ=GMT+05:00", "PGTZ=GMT+4",
                 "TZ=UTC5", "export TZ='GMT+4'", 'TZ="UTC+05:00:00"'):
        assert _scanned_shell(line), line
    for line in ("export TZ=UTC-5", "export TZ=UTC+5:30", "export TZ=UTC+9",
                 "export TZ=UTC", "export TZ=GMT+4EDT", "tz=UTC+5",
                 "timezone=GMT+5", "export TZ=UTC+05:00:30"):
        assert not _scanned_shell(line), line
    assert _scanned_shell("export TZ := UTC+5", make=True)
    assert NONPY_POSIX_ENV_OFFSET.search("ENV TZ GMT+05:00")
    assert NONPY_POSIX_ENV_OFFSET.search("ENV TZ=UTC+5")
    assert NONPY_POSIX_ENV_OFFSET.search("TZ: UTC+5")
    assert not NONPY_POSIX_ENV_OFFSET.search("ENV TIMEZONE UTC+5")
    hits = _yaml_env_pair_hits("- name: TZ\n  value: UTC+5\n")
    assert hits and hits[0][2] is True, hits
    hits = _yaml_env_pair_hits("- name: PGTZ\n  value: GMT+4\n")
    assert hits and hits[0][2] is True, hits
    assert not _yaml_env_pair_hits("- name: TIMEZONE\n  value: UTC+5\n")
    assert not _yaml_env_pair_hits("- name: TZ\n  value: UTC-5\n")
    assert _python_finds(tmp_path, 'import os\nos.environ["TZ"] = "UTC+5"\n')
    assert _python_finds(tmp_path, 'import os\nos.environ.setdefault("PGTZ", "GMT+4")\n')
    assert _python_finds(tmp_path, 'import os\nos.putenv("TZ", "GMT+05:00")\n')
    assert _python_finds(tmp_path, 'import os\nZONE = "UTC+5"\nos.environ["TZ"] = ZONE\n')
    assert _python_finds(tmp_path, 'import os\nos.environ.update({"TZ": "UTC+5"})\n')
    assert not _python_finds(tmp_path, 'import os\nos.environ["TZ"] = "UTC-5"\n')
    assert not _python_finds(tmp_path, 'import os\nos.environ["TZ"] = "UTC+9"\n')
    assert not _python_finds(tmp_path, 'import pandas as pd\npd.Timestamp.now(tz="UTC+5")\n')
    assert not _python_finds(tmp_path, 'settings = {}\nsettings["timezone"] = "UTC+5"\n')
    # The generic checker is unchanged: it has no context to settle the sign.
    assert _bad_zone_value("UTC+5") is None


def test_every_make_name_is_preprocessed_as_make():
    """Expansion and comment stripping follow `_reads_as_make`, not a second
    list that knew only `Makefile` (Codex, PR #993 final review)."""
    for name in ("Makefile", "GNUmakefile", "makefile", "rules.mk"):
        assert _reads_as_shell(pathlib.Path(name)), name
    assert not _reads_as_shell(pathlib.Path("notes.md"))
    # What that decision buys, through the preprocessing `_scan` applies to
    # a file it reads as Make: the variable resolves, the comment does not.
    assert _scanned_shell("A = EST\nexport TZ = $(A)\n", make=True)
    assert not _scanned_shell("# export TZ = EST\n", make=True)


def test_pine_fixed_utc_offsets_are_read_in_a_timezone_call():
    """Inside `time`/`timestamp`, `"UTC-5"` is a fixed UTC-5 and `"UTC+5"` is
    not Eastern: Pine reads the sign the conventional way (Codex, PR #993
    final review)."""
    for src, value in (('time(timeframe.period, session, "UTC-5")', "UTC-5"),
                       ('timestamp("GMT-05:00", 2024, 1, 1, 0, 0)', "GMT-05:00"),
                       ('time(timeframe.period, session, "UTC-4")', "UTC-4"),
                       ('z = "GMT-5"\ntime(timeframe.period, session, z)', "GMT-5")):
        hits = _pine_call_hits(src)
        assert [(h[1], h[2]) for h in hits] == [(value, True)], (src, hits)
    for src in ('time(timeframe.period, session, "UTC+5")',
                'time(timeframe.period, session, "GMT-0530")',
                'time(timeframe.period, session, "UTC-9")',
                'time(timeframe.period, session, "America/New_York")'):
        assert not _pine_call_hits(src), src
    # The generic checker is unchanged: a shell `TZ` reads the sign the other way.
    assert _bad_zone_value("UTC-5") is None


def test_a_static_string_augmented_assignment_folds(tmp_path):
    """`zone = "US/"; zone += "Eastern"; ZoneInfo(zone)` names the legacy zone
    (Codex, PR #993 final review)."""
    head = "from zoneinfo import ZoneInfo\n"
    assert _python_finds(tmp_path, head + 'zone = "US/"\nzone += "Eastern"\nZoneInfo(zone)\n')
    assert _python_finds(tmp_path, head + 'zone = "E"\nzone += "ST"\nZoneInfo(zone)\n')
    assert _python_finds(tmp_path, head + 'a = "US/"\nb = "Eastern"\na += b\nZoneInfo(a)\n')
    assert not _python_finds(tmp_path, head + 'zone = "America/"\nzone += "New_York"\nZoneInfo(zone)\n')
    assert not _python_finds(tmp_path, head + 'zone = "US/"\nzone += suffix\nZoneInfo(zone)\n')
    assert not _python_finds(tmp_path, head + 'n = 1\nn += 2\nZoneInfo("America/New_York")\n')


def test_an_alias_of_a_nested_constructor_keeps_its_receiver(tmp_path):
    """`make = zoneinfo.ZoneInfo.no_cache; make("EST")` is made on `ZoneInfo`
    (Codex, PR #993 final review)."""
    assert _python_finds(tmp_path, 'import zoneinfo\nmake = zoneinfo.ZoneInfo.no_cache\nmake("EST")\n')
    assert _python_finds(tmp_path, 'import zoneinfo as zi\nmake = zi.ZoneInfo.no_cache\nmake("EST")\n')
    assert not _python_finds(tmp_path, 'import zoneinfo\nmake = zoneinfo.ZoneInfo.no_cache\nmake("America/New_York")\n')


def test_adjacent_shell_fragments_form_one_word():
    """`export TZ="E""ST"` assigns `EST`: the shell concatenates adjacent
    fragments (Codex, PR #993 final review)."""
    for line in ('export TZ="E""ST"', 'export TZ="US/"Eastern', 'export TZ=-"05:00"',
                 "export TZ='US/'\"Eastern\"", 'SUFFIX=Eastern\nexport TZ="US/"$SUFFIX',
                 'local TZ="E""ST" X=1'):
        assert _scanned_shell(line), line
    assert not _scanned_shell('export TZ="America/"New_York')
    assert not _scanned_shell("A=E\nexport TZ='$A'\"ST\"")     # single quotes are literal
    assert _shell_scalars('export TZ="E""ST"\n')["TZ"] == [(7, "EST", False)]
    assert _shell_scalars('SUFFIX=Eastern\nexport TZ="US/"$SUFFIX\n')["TZ"][0][1] == "US/Eastern"
    assert _shell_scalars("A=E\nexport TZ='$A'\"ST\"\n")["TZ"][0][1] == "$AST"
    out = _expand_shell_defaults('export TZ="E""ST"\necho\n')
    assert out.splitlines()[0] == 'export TZ="EST"  ', out      # width kept




def test_a_posix_tz_abbreviation_is_case_insensitive_but_the_key_is_not():
    """glibc reads `TZ=utc+5` as UTC-5 (verified live), but `os.environ["tz"]`
    is a different, non-timezone variable (Codex, PR #993 final review)."""
    for line in ("export TZ=utc+5", "export TZ=gMt+4", "PGTZ=Utc+05:00",
                 'TZ="uTc+5"'):
        assert _scanned_shell(line), line
    assert not _scanned_shell("export tz=utc+5")   # key case-sensitive
    assert not _scanned_shell("export Tz=UTC+5")
    hits = _yaml_env_pair_hits("- name: TZ\n  value: gmt+4\n")
    assert hits and hits[0][2] is True, hits
    assert not _yaml_env_pair_hits("- name: tz\n  value: utc+5\n")


def test_posix_offsets_in_python_env_mappings(tmp_path):
    """`subprocess.run(env={"TZ": "UTC+5"})`, `os.environ.update(TZ="UTC+5")`
    and `update(**{"TZ": "UTC+5"})` install the frozen zone; a lowercase key
    or the pandas `tz=` kwarg do not (Codex, PR #993 final review)."""
    assert _python_finds(tmp_path, 'import subprocess\nsubprocess.run(["x"], env={"TZ": "UTC+5"})\n')
    assert _python_finds(tmp_path, 'import os\nos.environ.update(TZ="UTC+5")\n')
    assert _python_finds(tmp_path, 'import os\nos.environ.update(**{"PGTZ": "GMT+4"})\n')
    assert not _python_finds(tmp_path, 'import subprocess\nsubprocess.run(["x"], env={"tz": "UTC+5"})\n')
    assert not _python_finds(tmp_path, 'import pandas as pd\npd.Timestamp.now(tz="UTC+5")\n')
    assert not _python_finds(tmp_path, 'import os\nos.environ.update(TZ="UTC-5")\n')


def test_make_override_modifier_is_collected():
    """`override A = EST` binds `A`, as does `export override A = EST`
    (Codex, PR #993 final review)."""
    assert _scanned_shell("override A = EST\nexport TZ = $(A)\n", make=True)
    assert _scanned_shell("export override A = EST\nexport TZ = $(A)\n", make=True)
    assert _scanned_shell("override TZ = EST\n", make=True)
    assert not _scanned_shell("# override A = EST\nexport TZ = $(A)\n", make=True)


def test_a_dollar_in_an_identifier_is_not_a_dollar_quote():
    """`SELECT foo$tag$ -- SET TIME ZONE 'EST'`: `$tag$` continues the
    identifier `foo`, so the `--` is a real comment (Codex, PR #993 final
    review)."""
    out = _strip_sql_comments("SELECT foo$tag$ -- SET TIME ZONE 'EST'\n")
    assert "SET TIME ZONE 'EST'" not in out, out
    # A real dollar-quote at a token boundary still opens.
    assert "SET TIME ZONE 'EST'" in _strip_sql_comments("SELECT $$ -- x $$; SET TIME ZONE 'EST';")


def test_a_bound_null_daylight_abbreviation_freezes_tzrange(tmp_path):
    """`DST = None; tzrange("XX", -18000, DST)` is frozen UTC-5, as the inline
    `None` form is (Codex, PR #993 final review). Non-legacy abbreviations are
    used so only the frozen-offset logic decides, not the legacy-name scan."""
    assert _python_finds(tmp_path, 'from dateutil.tz import tzrange\nDST = None\ntzrange("XX", -18000, DST)\n')
    assert _python_finds(tmp_path, 'from dateutil.tz import tzrange\ntzrange("XX", -18000, None)\n')
    # A real daylight abbreviation, statically known, is not frozen.
    assert not _python_finds(tmp_path, 'from dateutil.tz import tzrange\ntzrange("XX", -18000, "YY", -14400)\n')
    assert not _python_finds(tmp_path, 'from dateutil.tz import tzrange\nDST = "YY"\ntzrange("XX", -18000, DST, -14400)\n')


def test_an_unquoted_backslash_is_removed_from_a_shell_word():
    """`export TZ=E\\ST` installs `EST`: bash drops the unquoted backslash
    (verified live; Codex, PR #993 final review)."""
    assert _scanned_shell("export TZ=E\\ST")
    assert _scanned_shell("export TZ=\\E\\S\\T")
    assert _shell_scalars("export TZ=E\\ST\n")["TZ"][0][1] == "EST"
    assert not _scanned_shell("export TZ=A\\m\\erica/New_York")


def test_a_statically_dead_shell_branch_is_not_collected():
    """A `then` body under `if false` never runs, and a `false && X` / `true ||
    X` is short-circuited away (verified live; Codex, PR #993 final review)."""
    # The dead assignment must not shadow the real one.
    assert _scanned_shell('LEGACY=EST; if false; then LEGACY=America/New_York; fi; export TZ="$LEGACY"')
    assert _scanned_shell('LEGACY=EST; false && LEGACY=America/New_York; export TZ="$LEGACY"')
    assert _scanned_shell('LEGACY=EST; true || LEGACY=America/New_York; export TZ="$LEGACY"')
    # The live arm still counts.
    assert _scanned_shell('if true; then LEGACY=EST; fi; export TZ="$LEGACY"')
    assert _scanned_shell('if false; then :; else LEGACY=EST; fi; export TZ="$LEGACY"')
    # And a correct script is not turned into a false finding by the dead arm.
    assert not _scanned_shell('LEGACY=America/New_York; if false; then LEGACY=EST; fi; export TZ="$LEGACY"')


def test_a_quoted_paren_does_not_close_a_scheduler_array():
    """`flags=(--message-body ")" --time-zone America/New_York)` is one valid
    array; the quoted `)` is data (Codex, PR #993 final review)."""
    body = ('deploy() {\n'
            '  local flags=(--message-body ")" --time-zone America/New_York)\n'
            '  gcloud scheduler jobs create http j "${flags[@]}"\n}\n')
    assert not _offenders(body), _offenders(body)
    # A genuinely zoneless array is still caught.
    bad = ('deploy() {\n'
           '  local flags=(--message-body ")" --uri https://x)\n'
           '  gcloud scheduler jobs create http j "${flags[@]}"\n}\n')
    assert _offenders(bad)


def test_scalar_arithmetic_on_a_timedelta_folds(tmp_path):
    """`timezone(timedelta(hours=-10) / 2)` and `... * 5` are UTC-5 (Codex,
    PR #993 final review)."""
    head = "from datetime import timedelta, timezone\n"
    assert _python_finds(tmp_path, head + "timezone(timedelta(hours=-10) / 2)\n")
    assert _python_finds(tmp_path, head + "timezone(timedelta(hours=-1) * 5)\n")
    assert _python_finds(tmp_path, head + "timezone(5 * timedelta(hours=-1))\n")
    # -3h and -8h are not Eastern; -4h would be EDT and IS a finding.
    assert not _python_finds(tmp_path, head + "timezone(timedelta(hours=-1) * 3)\n")
    assert not _python_finds(tmp_path, head + "timezone(timedelta(hours=-1) * 8)\n")
    assert _python_finds(tmp_path, head + "timezone(timedelta(hours=-1) * 4)\n")  # EDT


def test_a_recursive_make_export_resolves_at_recipe_time():
    """A recursive `export TZ = $(ZONE)` uses ZONE's value at recipe time, so a
    forward definition installs the zone and a later redefinition wins; an
    immediate `:=` export keeps definition-time semantics (Codex, PR #993
    final review)."""
    assert _scanned_shell("export TZ = $(ZONE)\nZONE = EST\n", make=True)
    assert not _scanned_shell(
        "ZONE = EST\nexport TZ = $(ZONE)\nZONE = America/New_York\n", make=True)
    # Immediate assignment is expanded at its definition: a forward reference
    # is empty there, so nothing is installed.
    assert not _scanned_shell("export TZ := $(ZONE)\nZONE = EST\n", make=True)


def test_a_scheduler_command_ends_at_a_shell_separator():
    """`gcloud ... ; echo --time-zone X` sets no scheduler timezone: the flag
    is on `echo` (Codex, PR #993 final review)."""
    body = ('deploy() {\n'
            "  gcloud scheduler jobs create http bad --schedule '0 2 * * *'"
            " ; echo --time-zone America/New_York\n}\n")
    assert _offenders(body), _offenders(body)
    # The compliant form, flag on the gcloud command itself, is not an offender.
    ok = ('deploy() {\n'
          "  gcloud scheduler jobs create http j --schedule '0 2 * * *'"
          " --time-zone America/New_York\n}\n")
    assert not _offenders(ok)


def test_a_keyword_binding_to_a_sql_executor_is_read(tmp_path):
    """`cur.execute("SET TIME ZONE %s", vars=("EST",))` installs the zone
    (Codex, PR #993 final review)."""
    assert _python_finds(tmp_path, 'cur.execute("SET TIME ZONE %s", vars=("EST",))\n')
    assert _python_finds(tmp_path, 'cur.execute("SET TIME ZONE %s", vars=["EST"])\n')
    assert _python_finds(tmp_path, 'P = ("EST",)\ncur.execute("SET TIME ZONE %s", vars=P)\n')
    assert not _python_finds(tmp_path, 'cur.execute("SET TIME ZONE %s", vars=("America/New_York",))\n')


def test_a_dollar_after_a_dollar_is_not_a_dollar_quote():
    """`SELECT foo$$tag$ -- SET TIME ZONE 'EST'`: every `$` continues the
    identifier, so the `--` is a real comment (Codex, PR #993 final review)."""
    out = _strip_sql_comments("SELECT foo$$tag$ -- SET TIME ZONE 'EST'\n")
    assert "SET TIME ZONE 'EST'" not in out, out
    assert "SET TIME ZONE 'EST'" in _strip_sql_comments("SELECT $$ -- x $$; SET TIME ZONE 'EST';")


def test_a_diagnostic_heredoc_body_is_not_a_finding():
    """`cat <<'EOF'` printing `Example: export TZ=EST` configures nothing
    (Codex, PR #993 final review)."""
    usage = "usage() {\n  cat <<'EOF'\nExample: export TZ=EST\nEOF\n}\n"
    assert not _scanned_shell(usage), usage
    # A heredoc redirected to a config file IS configuration and is read.
    config = "write() {\n  cat > app.env <<'EOF'\nexport TZ=EST\nEOF\n}\n"
    assert _scanned_shell(config), config

