#!/usr/bin/env python3
"""Verify the operational docs against live GCP state.

Why this exists
---------------
`docs/PIPELINE.md` said the market-data ingest ran at "23:00 UTC". The live
scheduler is `0 23 * * 1-5` in `America/New_York`. A timezone fix was then
designed off that doc and was wrong end-to-end, because a doc is a *claim*,
not evidence (CLAUDE.md §3.11).

This script closes that loop mechanically: every schedule and service claim
in the operational docs is compared against what `gcloud` actually returns.

Not to be confused with `gcp/audit_infra_drift.py`, which runs *inside* the
deployed container as a Cloud Run Job and compares GCP against GCP (image
digests, orphaned schedulers). It has no access to the repo, so it cannot
check documentation. This script is the repo-side half: docs vs GCP.

Usage
-----
    python scripts/verify_docs_against_live.py                 # read live via gcloud
    python scripts/verify_docs_against_live.py --write-snapshot live.json
    python scripts/verify_docs_against_live.py --snapshot live.json   # offline / CI

Exit code is 1 when any finding is reported, so it can gate CI.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass

REGION = "us-east1"

# Docs that describe the CURRENT system. Everything else under docs/ is a
# dated record (audits, incidents, changelogs, research write-ups) whose
# whole purpose is to state what was true on its date -- rewriting those
# would destroy the record, so they are deliberately out of scope.
LIVE_STATE_DOCS = [
    "README.md",
    "ARCHITECTURE.md",
    "RUNBOOK.md",
    "QUICK_REFERENCE.md",
    "INFRASTRUCTURE_NOTES.md",
    "SETUP.md",
    "DATA_DEPENDENCIES.md",
    "COST_ANALYSIS.md",
    "CLAUDE.md",
    "docs/PIPELINE.md",
    "docs/DATA_PIPELINE.md",
    "docs/EARNINGS_PIPELINE.md",
    "docs/GCP_ARCHITECTURE.md",
    "docs/GCP_IMPLEMENTATION_GUIDE.md",
    "docs/GCP_IMPLEMENTATION_STATUS.md",
    "docs/API.md",
    "docs/DATA_DICTIONARY.md",
    "docs/RUNBOOK_BACKFILL.md",
    "docs/STRAT_ENGINE_OPERATIONS.md",
    "docs/storage_overview.md",
    "docs/FAILURE_NOTIFIER_DEPLOYMENT.md",
    "platform/GCP_DATA_DICTIONARY.md",
]
LIVE_STATE_GLOBS = ["docs/product/*.md", "gcp/cloudbuild/*.md"]

# Cloud Run services deleted in the staging/prod split (2026-09-06). A
# live-state doc naming one is describing a service that no longer exists.
RETIRED_SERVICES = ["trading-platform-staging", "trading-platform"]

# Exempt lines: a retired name is legitimate when the line is explicitly
# about history, or names the container image / service account, neither of
# which was renamed (verified live 2026-09-06:
# image gcr.io/adept-mountain-474619-d4/trading-platform,
# SA trading-platform-svc@...).
RETIRED_OK = re.compile(
    r"trading-platform-svc|gcr\.io/[^ ]*trading-platform|"
    r"\b(was|were|formerly|previously|renamed|retired|deleted|predates|"
    r"replaced|superseded|old|legacy|until|removed|dropped|paused|missing|"
    r"deprecated|no longer)\b",
    re.I,
)

CRON = re.compile(
    r"(?<![0-9*/,\-])([0-9*/,\-]+ +[0-9*/,\-]+ +[0-9*/,\-]+ +[0-9*/,\-]+ +[0-9*/,\-]+)"
    r"(?![0-9*/,\-])"
)
# "weekdays 23:00", "Sun 19:15", "4:15 PM" -- a wall-clock claim about a job.
CLOCK = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?(?![\d:])")
# "Sun 6 AM", "11 PM nightly" -- the same claim with the minutes left off.
# Requiring the meridiem is what makes this safe: a bare number next to a job
# name is far more often a size, a count or a retry budget ("1 GiB / 30 min",
# "3-embed", "--max-retries 0") than an hour, and there is no way to tell them
# apart. AM/PM makes it unambiguous.
#
# Without this the checker was blind to a whole spelling: `fetch-earnings-
# history` was documented "Sun 6 AM weekly" against a live `15 19 * * 0`
# (19:15), and the run reported clean.
CLOCK_HOUR_ONLY = re.compile(r"(?<![\d:.])(\d{1,2})\s*(AM|PM|am|pm)\b")


def _clock_times(line: str) -> set[str]:
    """Every wall-clock time on the line, normalised to 24h HH:MM.

    A 12-hour claim ("4:15 PM") is expanded to BOTH readings when the meridiem
    is absent, because "11 PM nightly" and "23:00" are the same claim and a
    checker that only understood one of them reported correct docs as drift.
    """
    out: set[str] = set()
    for hh, mm, mer in CLOCK.findall(line):
        h = int(hh)
        if mer:
            out.add(f"{_h24(h, mer):02d}:{mm}")
        else:
            out.add(f"{h:02d}:{mm}")
            # "7:15" with no meridiem could be either; "07:15" is 24-hour by
            # its own padding, so only the unpadded form gets both readings.
            if len(hh) == 1 and 1 <= h <= 11:
                out.add(f"{h + 12:02d}:{mm}")
    for hh, mer in CLOCK_HOUR_ONLY.findall(line):
        h = int(hh)
        if h <= 12:
            out.add(f"{_h24(h, mer):02d}:00")
    return out


def _h24(hour: int, meridiem: str) -> int:
    """12-hour clock to 24-hour. 12 AM is 00, 12 PM is 12."""
    mer = meridiem.upper()
    if mer == "PM" and hour != 12:
        return hour + 12
    if mer == "AM" and hour == 12:
        return 0
    return hour


def _fire_times(crons: set[str]) -> set[str]:
    """Expand cron minute/hour fields into the HH:MM times they fire at.

    Only the minute and hour fields are expanded; a doc line states a clock
    time, not a day-of-week, and the day fields are checked separately by the
    cron comparison. Ranges and steps are handled because `*/5 9-15` is a
    common shape here; anything unparseable yields nothing, which suppresses
    the check rather than inventing a mismatch.
    """
    out: set[str] = set()
    for cron in crons:
        parts = cron.split()
        if len(parts) != 5:
            continue
        try:
            minutes = _expand(parts[0], 0, 59)
            hours = _expand(parts[1], 0, 23)
        except ValueError:
            continue
        if len(minutes) * len(hours) > 240:
            continue  # too broad to be a meaningful claim to check against
        for h in hours:
            for m in minutes:
                out.add(f"{h:02d}:{m:02d}")
    return out


def _expand(field: str, lo: int, hi: int) -> list[int]:
    """Expand one cron field (`*`, `5`, `9-15`, `*/5`, `1,3`) to its values."""
    values: list[int] = []
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, _, s = part.partition("/")
            step = int(s)
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            a, _, b = part.partition("-")
            start, end = int(a), int(b)
        else:
            start = end = int(part)
        if not (lo <= start <= end <= hi):
            raise ValueError(field)
        values.extend(range(start, end + 1, step))
    return sorted(set(values))


UTC_TIME = re.compile(r"\b\d{1,2}:\d{2}\s*(?:UTC|Z)\b|\b\d{1,2}:\d{2}\b[^.\n]{0,20}\bUTC\b")


# ── Day qualifiers ──────────────────────────────────────────────────────────
# A schedule table row often states SEVERAL cadences for one job:
#
#   | `premarket-brief` | 1 GiB / 30 min | weekdays 08:30 + Sun 09:00 | ...
#
# Checking such a row as a whole against the union of its live fire times
# accepts it as soon as ANY claimed time matches ANY live time -- so the
# correct weekday 08:30 vouched for a Sunday 09:00 that the live schedule
# fires at 21:00, and the run reported no drift.
#
# The whole-line rule is not simply wrong, though: the same tables carry an ET
# column and a UTC column, where one firing is legitimately stated twice and
# only one spelling can match. So the rule is kept WITHIN a day-qualified
# segment and applied per segment, which separates "the same firing written
# two ways" from "two different firings, one of them stale".
DAY_NAMES = {
    "sun": 0, "sunday": 0, "sundays": 0,
    "mon": 1, "monday": 1, "mondays": 1,
    "tue": 2, "tues": 2, "tuesday": 2, "tuesdays": 2,
    "wed": 3, "weds": 3, "wednesday": 3, "wednesdays": 3,
    "thu": 4, "thur": 4, "thurs": 4, "thursday": 4, "thursdays": 4,
    "fri": 5, "friday": 5, "fridays": 5,
    "sat": 6, "saturday": 6, "saturdays": 6,
}
DAY_ORDER = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
DAY_GROUPS = {
    "weekday": {1, 2, 3, 4, 5}, "weekdays": {1, 2, 3, 4, 5},
    "weekend": {0, 6}, "weekends": {0, 6},
}
# "nightly", "daily" and "hourly" are deliberately NOT qualifiers: they say how
# often, not on which days, and treating them as day words would split rows on
# prose ("Loads daily data") and invent segments with no claim in them.
_DAY_ALT = "|".join(sorted(set(DAY_NAMES) | set(DAY_GROUPS), key=len, reverse=True))
DAY_QUALIFIER = re.compile(
    rf"\b({_DAY_ALT})\b(?:\s*[-\u2010-\u2015]\s*\b({_DAY_ALT})\b)?", re.I)


def _dow_of(word: str) -> set[int]:
    w = word.lower()
    return set(DAY_GROUPS[w]) if w in DAY_GROUPS else {DAY_NAMES[w]}


def _qualifier_days(first: str, last: str) -> set[int]:
    """`Sun` -> {0}; `weekdays` -> {1..5}; `Tue-Sat` -> {2,3,4,5,6} (wrapping)."""
    days = _dow_of(first)
    if not last:
        return days
    end = _dow_of(last)
    if len(days) != 1 or len(end) != 1:
        return days | end
    a, b = next(iter(days)), next(iter(end))
    return {d % 7 for d in range(a, b + 1)} if a <= b else \
        {d % 7 for d in range(a, b + 8)}


def _day_segments(line: str) -> list[tuple[set[int], str]]:
    """Split a line at its day qualifiers into (days, text) pieces.

    Returns [] when the line carries no day qualifier at all, in which case
    the caller falls back to the whole-line rule -- which is right for an
    ET/UTC column pair and for any row that states a single cadence.
    """
    marks = list(DAY_QUALIFIER.finditer(line))
    if not marks:
        return []
    segments: list[tuple[set[int], str]] = []
    for n, m in enumerate(marks):
        end = marks[n + 1].start() if n + 1 < len(marks) else len(line)
        # The FIRST segment starts at the beginning of the line, not at its
        # qualifier. A clock that precedes its qualifier -- `7:00 PM ET Mon-Fri
        # + Sun`, which is how docs/DATA_PIPELINE.md writes it -- was sliced
        # off the front and then belonged to no segment at all, so neither
        # piece carried a clock and the comparison never ran (Codex, PR #990).
        start = 0 if n == 0 else m.start()
        segments.append((_qualifier_days(m.group(1), m.group(2)), line[start:end]))
    return segments


def _cron_dow(field: str) -> set[int]:
    """Day-of-week field to a set. `7` is Sunday as well as `0`."""
    if field.strip() == "*":
        return set(range(7))
    try:
        return {d % 7 for d in _expand(field, 0, 7)}
    except ValueError:
        return set(range(7))


def _cron_firings(cron: str) -> set[tuple[int, str]]:
    """A cron expression to the (weekday, HH:MM) pairs it fires at.

    Comparing FIRINGS rather than expression strings is what stops an
    equivalent respelling reading as drift: `docs/product/05-INFRASTRUCTURE.md`
    documents `fetch-sec-filings` as four separate crons where the live entry
    is one comma list, `0 7,10,13,17 * * 1-5`. Identical schedule, and the
    string comparison called it a finding -- a false positive is how a checker
    trains its readers to ignore it.

    Anything unparseable, or too broad to be a meaningful claim, yields the
    empty set, which suppresses the check rather than inventing a mismatch.
    """
    parts = cron.split()
    if len(parts) != 5:
        return set()
    try:
        minutes = _expand(parts[0], 0, 59)
        hours = _expand(parts[1], 0, 23)
    except ValueError:
        return set()
    if len(minutes) * len(hours) > 240:
        return set()
    days = _cron_dow(parts[4])
    return {(d, f"{h:02d}:{m:02d}")
            for d in days for h in hours for m in minutes}


def _cron_calendar(cron: str) -> tuple[frozenset, frozenset] | None:
    """(day-of-month set, month set) for a cron, or None if unparseable.

    `_cron_firings` deliberately reduces a cron to weekday and clock, which is
    what makes an equivalent respelling compare equal. It also discards fields
    3 and 4 entirely, so `0 5 1 * *` and `0 5 2 * *` were indistinguishable and
    a monthly or quarterly job could be documented on the wrong day or in the
    wrong months without a finding (Codex, PR #990). Compared separately rather
    than folded into the firing tuple, because the clock comparison is
    deliberately weekday-shaped and widening it would change what "equivalent"
    means for every daily schedule.
    """
    parts = cron.split()
    if len(parts) != 5:
        return None
    try:
        return frozenset(_expand(parts[2], 1, 31)), frozenset(_expand(parts[3], 1, 12))
    except ValueError:
        return None


# An explicit, reviewed exemption for a line the heuristics cannot judge: a
# historical narrative that must keep naming a deleted service, or a count that
# is deliberately about the repo rather than the live fleet. Placed on the line
# or the line above it, with the reason inline so the next reader sees why.
SUPPRESS = re.compile(r"<!--\s*verify-docs-ok:\s*(.+?)\s*-->")

# "`0 17 * * 1-5` ET *(now `0 23 * * 1-5`)*" -- a record that states the old
# value beside the new one. See the use site in check_schedules.
ANNOTATED_CORRECTION = re.compile(r"\b(now|currently|since|as of)\b", re.I)


@dataclass
class Finding:
    check: str
    path: str
    line: int
    detail: str

    def __str__(self) -> str:
        return f"[{self.check}] {self.path}:{self.line}\n    {self.detail}"


def _gcloud(*args: str) -> str:
    """Run gcloud, raising on failure.

    No fallback to a cached snapshot: reading a stale cache and calling it
    "live" is the exact failure this script exists to prevent.
    """
    proc = subprocess.run(
        ("gcloud",) + args, capture_output=True, text=True, timeout=180
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gcloud {' '.join(args)} failed: {proc.stderr.strip()[:400]}")
    return proc.stdout


def read_live() -> dict:
    """Snapshot the live state this script checks against."""
    sched = json.loads(
        _gcloud("scheduler", "jobs", "list", f"--location={REGION}", "--format=json")
    )
    run_jobs = json.loads(
        _gcloud("run", "jobs", "list", f"--region={REGION}", "--format=json")
    )
    services = json.loads(
        _gcloud("run", "services", "list", f"--region={REGION}", "--format=json")
    )
    # Secrets and Cloud Tasks queues are named in the same backticked style as
    # jobs, so the name check needs them too or it reports real resources as
    # missing (it did, for av-api-key and insight-pipeline-queue).
    secrets = json.loads(_gcloud("secrets", "list", "--format=json"))
    queues = json.loads(
        _gcloud("tasks", "queues", "list", f"--location={REGION}", "--format=json")
    )
    # Domain mappings live in Cloud Run, not in source, so a doc is the only
    # place the hostname appears and nothing compared it to anything. Eleven
    # places in these docs said `stocks.insightscollective.org` maps to
    # solyra-api-staging while the live mapping is `api.stocks...`; the bare
    # host is the Firebase email sending domain now (Codex, PR #990).
    mappings = json.loads(
        _gcloud("beta", "run", "domain-mappings", "list", f"--region={REGION}",
                "--format=json")
    )
    schedulers = {}
    for s in sched:
        name = s["name"].rsplit("/", 1)[-1]
        uri = (s.get("httpTarget") or {}).get("uri", "")
        m = re.search(r"/jobs/([^:/]+)", uri)
        schedulers[name] = {
            "schedule": s.get("schedule", ""),
            "timeZone": s.get("timeZone", ""),
            "state": s.get("state", ""),
            "target_job": m.group(1) if m else "",
        }
    return {
        "schedulers": schedulers,
        "run_jobs": sorted(j["metadata"]["name"] for j in run_jobs),
        "services": sorted(s["metadata"]["name"] for s in services),
        "secrets": sorted(x["name"].rsplit("/", 1)[-1] for x in secrets),
        "queues": sorted(q["name"].rsplit("/", 1)[-1] for q in queues),
        "domain_mappings": {m["metadata"]["name"]: m["spec"]["routeName"]
                            for m in mappings},
    }


def doc_paths(root: pathlib.Path) -> list[pathlib.Path]:
    seen: list[pathlib.Path] = []
    for rel in LIVE_STATE_DOCS:
        p = root / rel
        if p.is_file():
            seen.append(p)
    for pattern in LIVE_STATE_GLOBS:
        seen.extend(sorted(root.glob(pattern)))
    return seen


def _lines(path: pathlib.Path) -> list[tuple[int, str]]:
    """(line number, text) for every line not covered by a verify-docs-ok marker."""
    raw = path.read_text(errors="replace").splitlines()
    marked = set()
    for i, line in enumerate(raw, 1):
        if SUPPRESS.search(line):
            marked.update({i, i + 1})
    return [(i, line) for i, line in enumerate(raw, 1) if i not in marked]


def check_retired_services(path: pathlib.Path, rel: str, out: list[Finding]) -> None:
    for i, line in _lines(path):
        if RETIRED_OK.search(line):
            continue
        for name in RETIRED_SERVICES:
            if re.search(rf"\b{re.escape(name)}\b(?!-svc)", line):
                out.append(Finding("retired-service", rel, i,
                                   f"names deleted Cloud Run service `{name}`: {line.strip()[:120]}"))
                break


def _schedule_owners(live: dict) -> dict[str, list[tuple[str, dict]]]:
    """Map every name a doc might use -> the scheduler entries that fire it.

    Docs name the Cloud Run Job (`fetch-av-options-backfill`) at least as
    often as the scheduler entry (`av-options-daily`), and a schedule claim
    next to either one is a claim about the same firing. Keying on scheduler
    names alone missed a whole class of drift.
    """
    owners: dict[str, list[tuple[str, dict]]] = {}
    for name, meta in live["schedulers"].items():
        owners.setdefault(name, []).append((name, meta))
        if meta["target_job"]:
            owners.setdefault(meta["target_job"], []).append((name, meta))
    return owners


RULE = "\u2502"  # the box-drawing vertical these diagrams are built from


def _diagram_cells(path: pathlib.Path) -> list[tuple[int, str]]:
    """(first line number, joined text) for every cell of an ASCII box diagram.

    `check_schedules` reads a line at a time, which is the wrong unit for the
    box diagrams these docs draw: a cell wraps its own contents, so
    `docs/EARNINGS_PIPELINE.md` splits one box across `fetch-earnings-`,
    `history (weekly)` and `Sun 06:00 ET`. The job name is on no single line
    and the time is beside it on none, so two stale schedules survived a run
    that reported clean (Codex, PR #990).

    Joining whole lines is not the fix -- boxes sit side by side, so that
    splices three unrelated cells into one string and can pair one box's name
    with another box's clock. Columns are joined instead, and only at rule
    positions shared by EVERY line of the block, so a cell is never assembled
    across a boundary that is not actually there. Two pieces are run together
    when the first ends in a hyphen, which is how a name breaks across lines.
    """
    raw = path.read_text(errors="replace").splitlines()
    marked = set()
    for i, line in enumerate(raw, 1):
        if SUPPRESS.search(line):
            marked.update({i, i + 1})

    out: list[tuple[int, str]] = []
    block: list[tuple[int, str]] = []

    def flush() -> None:
        if len(block) < 2:
            block.clear()
            return
        shared = set.intersection(*({c for c, ch in enumerate(t) if ch == RULE}
                                    for _, t in block))
        if not shared:
            block.clear()
            return
        bounds = sorted(shared)
        for a, b in zip(bounds, bounds[1:]):
            pieces = [t[a + 1:b].strip() for _, t in block]
            text = ""
            for piece in pieces:
                if not piece:
                    continue
                if not text:
                    text = piece
                elif text.endswith("-"):
                    text += piece
                else:
                    text += " " + piece
            if text and block[0][0] not in marked:
                out.append((block[0][0], text))
        block.clear()

    for i, line in enumerate(raw, 1):
        if RULE in line:
            block.append((i, line))
        else:
            flush()
    flush()
    return out


def check_schedules(path: pathlib.Path, rel: str, live: dict, out: list[Finding]) -> None:
    """Compare every schedule claim sitting next to a scheduled-job name.

    Runs twice over the same file: once per line, which is the right unit for
    prose and table rows, and once per ASCII-diagram cell, which is the right
    unit for the box diagrams these docs draw. See `_diagram_cells`.
    """
    owners = _schedule_owners(live)
    if not owners:
        return
    names = sorted(owners, key=len, reverse=True)
    name_re = re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b")
    seen: set[tuple[str, int, str]] = set()
    units = list(_lines(path)) + _diagram_cells(path)
    for i, line in units:
        found = name_re.findall(line)
        if not found or RETIRED_OK.search(line):
            continue
        # One table row can name several jobs with their own times, so the
        # owning scheduler entries of every name on the row are collected.
        fresh = len(out)
        job = "`, `".join(dict.fromkeys(found))
        entries = list({n: (n, m)
                        for name in dict.fromkeys(found)
                        for n, m in owners[name]}.values())
        shown = ", ".join(f"`{n}` = `{m['schedule']}`" for n, m in entries)

        crons = {re.sub(r"\s+", " ", c.strip()) for c in CRON.findall(line)}
        crons = {c for c in crons if c.count(" ") == 4}
        claims_a_schedule = bool(crons or _clock_times(line))

        # A PAUSED scheduler does not fire, whatever its cron expression still
        # says. Comparing only the expression let `signal-quality-report-
        # hourly` -- paused -- back a doc line presenting it as running hourly
        # 10:00-16:00, and the run reported clean. Lines that acknowledge the
        # state are already exempt: RETIRED_OK matches "paused".
        stopped = [(n, m) for n, m in entries if m["state"] != "ENABLED"]
        running = [(n, m) for n, m in entries if m["state"] == "ENABLED"]
        if stopped and claims_a_schedule:
            out.append(Finding(
                "paused-schedule", rel, i,
                f"`{job}`: " + ", ".join(f"`{n}` is {m['state']}" for n, m in stopped)
                + ", so the documented schedule does not fire — " + shown))

        live_firings: set[tuple[int, str]] = set()
        for _, m in running:
            live_firings |= _cron_firings(re.sub(r"\s+", " ", m["schedule"]))
        if not live_firings:
            continue
        live_times = {t for _, t in live_firings}

        # Cron claims are compared by the firings they expand to, not by
        # spelling: four separate crons and one comma list can be the same
        # schedule. Drift is a claimed firing that does not happen.
        #
        # Except on a line that corrects itself. A deployment checklist entry
        # reads ``- [x] `fetch-market-data-daily` — `0 17 * * 1-5` ET *(now
        # `0 23 * * 1-5`)*``: the stale cron is deliberately kept beside the
        # live one so the record shows the change. Checking each cron
        # independently turned that into a finding, which is the whole-line
        # rule's original point resurfacing -- so it is kept, narrowly, for a
        # line that carries a correction word AND states the live schedule.
        corrects_itself = (ANNOTATED_CORRECTION.search(line)
                           and any(_cron_firings(c) <= live_firings
                                   for c in crons if _cron_firings(c)))
        live_calendars = [cal for cal in (_cron_calendar(re.sub(r"\s+", " ", m["schedule"]))
                                          for _, m in running) if cal]
        if not corrects_itself:
            for c in sorted(crons):
                claimed = _cron_firings(c)
                if claimed and not claimed <= live_firings:
                    out.append(Finding("schedule-drift", rel, i,
                                       f"`{job}` documented as `{c}`, which fires when the "
                                       f"live schedule does not; live: {shown}"))
                    continue
                # Same clock and weekday, different calendar: a monthly job
                # documented on the wrong day of the month, or a quarterly one
                # in the wrong months.
                cal = _cron_calendar(c)
                if claimed and cal and live_calendars and cal not in live_calendars:
                    out.append(Finding("schedule-drift", rel, i,
                                       f"`{job}` documented as `{c}`: the clock matches but "
                                       f"the day-of-month/month fields do not; live: {shown}"))

        # Clock claims, checked per day-qualified segment. Within a segment the
        # any-match rule still holds, because an ET column and a UTC column
        # state one firing twice and only one spelling can match.
        for days, segment in _day_segments(line) or [(None, line)]:
            claimed = _clock_times(segment)
            if not claimed:
                continue
            relevant = live_times if days is None else {
                t for d, t in live_firings if d in days}
            if days is not None and not relevant:
                # The line names days the live schedule does not fire on at
                # all. Skipping this as "nothing to compare" accepted a claim
                # that `fetch-market-data` runs on Sunday against a weekday
                # cron (Codex, PR #990).
                out.append(Finding(
                    "schedule-drift", rel, i,
                    f"`{job}` documented at {', '.join(sorted(claimed))} on "
                    f"{'/'.join(DAY_ORDER[d] for d in sorted(days))}, but the live "
                    f"schedule never fires on {'those days' if len(days) > 1 else 'that day'}"
                    f" — {shown}"))
                continue
            if relevant and not (claimed & relevant):
                where = "" if days is None else \
                    f" on {'/'.join(DAY_ORDER[d] for d in sorted(days))}"
                out.append(Finding("clock-drift", rel, i,
                                   f"`{job}` documented at "
                                   f"{', '.join(sorted(claimed))}{where}; no live fire "
                                   f"time matches ({', '.join(sorted(relevant))}) — {shown}"))

        # NOT CHECKED: which clock on the line belongs to which named job.
        #
        # A row naming two jobs passes as soon as ONE documented clock matches
        # ONE of them, so `orb-15m-alert`/`orb-30m-alert` at 09:45/10:00 would
        # still pass with 10:00 moved (Codex, PR #990). The obvious fix -- also
        # require every named scheduler to have a matching clock -- was written
        # and measured, and it reports four findings on correct documentation:
        #
        #   RUNBOOK.md:30            "Brief at 8:30 ET errors with ..."
        #   GCP_ARCHITECTURE.md:551  "premarket-refresh (08:20) MUST finish
        #                             before premarket-brief (08:30)"
        #   GCP_ARCHITECTURE.md:599  a mermaid node giving signal-monitor's
        #                             window
        #
        # In each case the doc names a JOB and states its weekday cadence,
        # while `_schedule_owners` maps that job to a family of schedulers
        # including a Sunday one whose time the line never claims to give. The
        # association cannot be recovered without the doc stating it, and a
        # checker that reports correct lines is one people learn to skip --
        # the argument this file makes about `EST` and about bare secret
        # counts. So the gap is named here instead: a row listing several jobs
        # should name each job beside its own time, and where that mattered
        # (docs/EARNINGS_PIPELINE.md:17) the row now does.

        if UTC_TIME.search(line):
            zones = {m["timeZone"] for _, m in entries}
            out.append(Finding("utc-claim", rel, i,
                               f"`{job}` is scheduled in {'/'.join(sorted(zones))} "
                               f"({shown}) but the line states a UTC clock time: "
                               f"{line.strip()[:120]}"))

        # A one-line cell is scanned by both passes, so the same drift can be
        # appended twice. Deduped here rather than by skipping the second pass:
        # a multi-line cell legitimately reports at its first line, which the
        # per-line pass may also have reached for a different reason.
        for f in out[fresh:]:
            key = (f.check, f.line, f.detail)
            if key in seen:
                out.remove(f)
            else:
                seen.add(key)


# The domains this project serves its own hostnames from. Held here rather than
# derived from the live mappings, because the live set can legitimately be
# EMPTY (every mapping deleted) and a scope derived from it is then empty too --
# so the check that should shout loudest would go silent (Codex, PR #990).
KNOWN_CUSTOM_DOMAINS = ("insightscollective.org",)


# "`host` maps to `service`", "host points at service", "host -> service".
# Backticks optional: these docs write the hostname both ways.
MAPPING_CLAIM = re.compile(
    r"`?([a-z0-9][a-z0-9.-]*\.[a-z]{2,})`?\s*"
    r"(?:maps? (?:to|here)|points? (?:at|to)|->|→)\s*"
    r"`?(solyra-api-[a-z]+|trading-platform[a-z-]*)`?", re.I)


def check_domain_mappings(path: pathlib.Path, rel: str, live: dict,
                          out: list[Finding]) -> None:
    """A documented hostname must map where the doc says it does.

    Cloud Run holds the mapping and nothing in source does, so a doc is the
    only record of it and every copy drifted together when the mapping moved.
    """
    mappings = live.get("domain_mappings")
    if mappings is None:
        return          # a snapshot written before this field existed

    # NOT `if not mappings: return`. Deleting every domain mapping -- the
    # routing outage this check exists to expose -- produced an empty dict,
    # and the early return then suppressed every mapping check: the verifier
    # reported `no findings` while the docs still routed readers at
    # `api.stocks.insightscollective.org` (Codex, PR #990). An empty live set
    # is a state to check against, not a reason to stop checking.

    # Every host under a domain we actually map, whether or not the line spells
    # out "maps to". Chasing phrasings with a pattern is the mistake #993 made
    # four times: these docs write the hostname as "maps here", "points at",
    # "via", "also served at" and "also `host`", and a checker that knows five
    # of those does not know the sixth. A hostname under our own domain IS a
    # claim that it serves something, so the presence of one that is not a live
    # mapping is the finding -- and a legitimate non-Cloud-Run use of the name
    # (it is the Firebase email sending domain now) takes a verify-docs-ok
    # marker, which makes that use visible rather than assumed.
    # The registrable domain, not the mapped host's immediate parent: from
    # `api.stocks.insightscollective.org` that is `insightscollective.org`, so
    # the bare `stocks.insightscollective.org` -- which is what every stale
    # copy says -- is inside the scope rather than outside it.
    # Union, not `or`: a mapping under a new domain widens the scope, and the
    # domains we are known to serve from keep it non-empty when every mapping
    # is gone -- which is precisely when the docs are most wrong.
    suffixes = {".".join(h.rsplit(".", 2)[-2:]) for h in mappings if h.count(".") >= 1}
    suffixes |= set(KNOWN_CUSTOM_DOMAINS)
    host_re = re.compile(
        r"\b((?:[a-z0-9][a-z0-9.-]*\.)?(?:" + "|".join(re.escape(x) for x in sorted(suffixes))
        + r"))\b", re.I) if suffixes else None

    for i, line in _lines(path):
        if RETIRED_OK.search(line):
            continue
        flagged: set[str] = set()
        if host_re:
            for hm in host_re.finditer(line):
                host = hm.group(1).lower()
                if host in mappings:
                    continue
                flagged.add(host)
                out.append(Finding(
                    "mapping-drift", rel, i,
                    f"`{host}` is named in an operational doc but is not a live "
                    f"Cloud Run domain mapping; live: "
                    + (", ".join(f"`{h}` -> `{sv}`" for h, sv in sorted(mappings.items()))
                       or "no domain mappings at all")))
        # The second pass exists for a host that IS a live mapping but is
        # documented against the wrong service. A host the first pass already
        # named would otherwise be reported twice for one line.
        for m in MAPPING_CLAIM.finditer(line):
            host, service = m.group(1).lower(), m.group(2)
            if host in flagged:
                continue
            actual = mappings.get(host)
            if actual == service:
                continue
            if actual is None:
                # A host that maps nowhere. Only a finding when the doc says
                # it maps to something -- which is what MAPPING_CLAIM matched.
                out.append(Finding(
                    "mapping-drift", rel, i,
                    f"`{host}` is documented as mapping to `{service}`, but no "
                    f"Cloud Run domain mapping exists for it; live: "
                    + (", ".join(f"`{h}` -> `{sv}`" for h, sv in sorted(mappings.items()))
                       or "no domain mappings at all")))
            else:
                out.append(Finding(
                    "mapping-drift", rel, i,
                    f"`{host}` is documented as mapping to `{service}`; live it "
                    f"maps to `{actual}`"))


def check_known_names(path: pathlib.Path, rel: str, live: dict, out: list[Finding]) -> None:
    """A backticked name introduced as GCP infrastructure must exist live."""
    known = (set(live["run_jobs"]) | set(live["schedulers"]) | set(live["services"])
             | set(live.get("secrets", ())) | set(live.get("queues", ()))
             | {"trading-system"})  # Artifact Registry package, not a CR resource
    # A retired service is not an unknown name: `check_retired_services` already
    # reports it, and with a message that says WHY the name is wrong. Reporting
    # the same line twice for one fact is the noise that teaches people to skim
    # the output.
    owned_elsewhere = set(RETIRED_SERVICES)
    # `Cloud Run service` was missing from this list, so a rename or a typo
    # that kept the total service count -- `solyra-api-stagin` -- stayed in an
    # operational doc under a run this script reported clean, while
    # `check_retired_services` only knows the two hard-coded legacy names
    # (Codex, PR #990). The count check and the name check answer different
    # questions and a service needs both.
    context = re.compile(r"Cloud Run Jobs?|Cloud Run services?|Cloud Scheduler"
                         r"|scheduler entry|CR Job", re.I)
    tick = re.compile(r"`([a-z][a-z0-9-]{4,})`")
    for i, line in _lines(path):
        if not context.search(line) or RETIRED_OK.search(line):
            continue
        for cand in tick.findall(line):
            if "-" not in cand or cand in known or cand in owned_elsewhere:
                continue
            # Only flag names that LOOK like ours: they share a prefix with a
            # real job. An unrelated backticked token is not a claim about us.
            head = cand.split("-")[0]
            if any(k.split("-")[0] == head for k in known):
                out.append(Finding("unknown-name", rel, i,
                                   f"`{cand}` is named as infrastructure but no such "
                                   f"job/scheduler/service/secret/queue exists live"))


# Counts stated in prose. The first version of this check knew only about
# "N Cloud Run Jobs", so it never compared services or schedulers even though
# read_live() fetches both -- and the advertised clean run was reported while
# docs/GCP_ARCHITECTURE.md claimed 3 services against a live 4 and 60
# schedulers against a live 64.
#
# Spelled-out numbers are parsed because the drift is spelled out: line 344 of
# that file says "Three long-lived HTTP services".
WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_NUM = r"(\d{1,3}|" + "|".join(WORD_NUMBERS) + r")"

# What may sit between the resource noun and its parenthesised live count.
# `\s*` was not enough: `platform/GCP_DATA_DICTIONARY.md` writes the noun in
# bold, so the text is `**Cloud Run — jobs** (~50 live)` and the closing `**`
# stopped the match dead. The verifier then reported clean on a file that
# contradicted its own live snapshot 26 lines further down (Codex, PR #990).
# Emphasis markers, backticks and a stray closing bracket are formatting, not
# content, so they are stepped over rather than treated as a word boundary.
_FMT = r"[\s*_`\]]*"

COUNT_CLAIMS: tuple[tuple[re.Pattern, str, str], ...] = (
    (re.compile(rf"\b{_NUM}\s+Cloud\s+Run\s+Jobs\b", re.I), "run_jobs", "Cloud Run Jobs"),
    # Qualified deliberately: a bare "N services" in operational prose is as
    # likely to mean GCP APIs or third-party vendors as Cloud Run services.
    (re.compile(rf"\b{_NUM}\s+(?:long-lived\s+)?(?:HTTP\s+|Cloud\s+Run\s+)"
                rf"(?:HTTP\s+)?services\b", re.I), "services", "Cloud Run services"),
    # The noun for a scheduler is spelled at least five ways across these
    # docs -- "cron triggers", "scheduler jobs", "scheduler entries",
    # "Cloud Scheduler entries", "schedulers" -- and the first version of this
    # pattern knew three of them, so `SCH[84 Cloud Scheduler entries]` and
    # "returns **84 scheduler entries**" were still invisible on a run that
    # reported clean. That is the same narrowing the review caught one level
    # up, so the alternation is now the whole vocabulary the repo uses.
    (re.compile(rf"\b{_NUM}\s+(?:cron\s+triggers|(?:Cloud\s+)?[Ss]cheduler\s+"
                rf"(?:jobs|entries|triggers)|schedulers)\b", re.I),
     "schedulers", "Cloud Scheduler jobs"),
    # "| Cloud Scheduler (60 jobs, 3 free) |" -- the "3 free" is a free-tier
    # quota, not a fleet count, so only the leading number is read.
    # `jobs` only -- the `live` spelling is handled by the declared/live
    # pattern below, and matching it here too reported one claim twice.
    (re.compile(rf"Cloud\s+Scheduler{_FMT}\(\s*{_NUM}\s+jobs\b", re.I),
     "schedulers", "Cloud Scheduler jobs"),
    # The declared/live pair, in either order:
    #   "Scheduler (58 declared / 84 live)"
    #   "Cloud Scheduler (84 live / 58 declared)"
    # Only the LIVE half is checkable -- the declared half describes
    # gcp/deploy.sh, a different measurement. The previous pattern required
    # the first number after "(" to be the live one, so it stopped at
    # "58 declared" and never looked at "84 live", leaving the contradiction
    # in place under an advertised clean run (Codex, PR #990).
    (re.compile(rf"[Ss]cheduler{_FMT}\([^)]*?\b{_NUM}\s+live\b", re.I),
     "schedulers", "live Cloud Scheduler jobs"),
    (re.compile(rf"(?:Cloud\s+Run\s+)?jobs{_FMT}\([^)]*?\b{_NUM}\s+live\b", re.I),
     "run_jobs", "live Cloud Run Jobs"),
    # NOUN FIRST, which is how RUNBOOK.md's recovery tables are written:
    # `Cloud Run Jobs (27 jobs)` and `Cloud Run Jobs (29)`. Every pattern above
    # requires the number BEFORE the noun, so a whole table of stale recovery
    # inventories was unreachable in a file the verifier explicitly scans
    # (Codex, PR #990).
    (re.compile(rf"Cloud\s+Run\s+Jobs{_FMT}\(\s*{_NUM}(?:\s+jobs)?\s*[),/]", re.I),
     "run_jobs", "Cloud Run Jobs"),
    (re.compile(rf"Cloud\s+Run\s+Services{_FMT}\(\s*{_NUM}\s*[),:]", re.I),
     "services", "Cloud Run services"),
    # Secret Manager had NO entry at all: `read_live` collects the secrets and
    # the run summary prints their count, so the number was measured, carried
    # and never compared to anything (Codex, PR #990).
    #
    # Qualified, like the services pattern above and for the same reason. A
    # bare "N secrets" is far more often a SUBSET -- "just two secrets" for one
    # workflow, "6 secrets" for one service -- than a fleet count, and a
    # checker that flags those is one people stop reading. So the noun has to
    # be near it, or the claim has to say it is the whole set.
    (re.compile(rf"Secret\s+Manager[^\n]{{0,120}}?\b{_NUM}\s+secrets\b", re.I),
     "secrets", "Secret Manager secrets"),
    (re.compile(rf"\bAll\s+{_NUM}\s+secrets\b", re.I),
     "secrets", "Secret Manager secrets"),
)


def check_counts(path: pathlib.Path, rel: str, live: dict, out: list[Finding]) -> None:
    r"""A stated resource count must match the live count.

    Scans the WHOLE file rather than line by line. Prose wraps, and a count
    claim wraps with it: `docs/product/05-INFRASTRUCTURE.md` says "returns
    **84 scheduler\nentries**", which a per-line scan cannot see even with the
    right vocabulary. That is the same blind spot the Eastern-timezone guard
    was caught with on #993 -- a formatter's line break defeating a check --
    so this uses the same remedy: match the full text, derive the line number
    from the match offset. The `\s+` in the patterns already spans newlines.
    """
    text = path.read_text(errors="replace")
    raw = text.splitlines()
    skip = {i for i, line in enumerate(raw, 1) if SUPPRESS.search(line)}
    skip |= {i + 1 for i in skip}
    for pattern, key, label in COUNT_CLAIMS:
        n_live = len(live[key])
        for m in pattern.finditer(text):
            i = text.count("\n", 0, m.start()) + 1
            if i in skip or RETIRED_OK.search(raw[i - 1]):
                continue
            claimed = m.group(1)
            n = WORD_NUMBERS.get(claimed.lower())
            if n is None:
                n = int(claimed)
            if n != n_live:
                out.append(Finding("count-drift", rel, i,
                                   f"claims {claimed} {label}; live count is {n_live}"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", help="read live state from this JSON instead of gcloud")
    ap.add_argument("--write-snapshot", help="write the live state read from gcloud here")
    ap.add_argument("--root", default=str(pathlib.Path(__file__).resolve().parent.parent))
    args = ap.parse_args()

    if args.snapshot:
        live = json.loads(pathlib.Path(args.snapshot).read_text())
    else:
        live = read_live()
    if args.write_snapshot:
        pathlib.Path(args.write_snapshot).write_text(json.dumps(live, indent=2))

    root = pathlib.Path(args.root)
    findings: list[Finding] = []
    paths = doc_paths(root)
    for p in paths:
        rel = str(p.relative_to(root))
        check_retired_services(p, rel, findings)
        check_schedules(p, rel, live, findings)
        check_known_names(p, rel, live, findings)
        check_counts(p, rel, live, findings)
        check_domain_mappings(p, rel, live, findings)

    print(f"checked {len(paths)} operational docs against "
          f"{len(live['schedulers'])} schedulers / {len(live['run_jobs'])} jobs / "
          f"{len(live['services'])} services / {len(live.get('secrets', ()))} secrets "
          f"/ {len(live.get('queues', ()))} queues")
    if not findings:
        print("no findings")
        return 0
    print(f"\n{len(findings)} finding(s):\n")
    for f in findings:
        print(f)
    return 1


if __name__ == "__main__":
    sys.exit(main())
