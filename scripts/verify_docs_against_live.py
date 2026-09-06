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
            mer = mer.upper()
            if mer == "PM" and h != 12:
                h += 12
            elif mer == "AM" and h == 12:
                h = 0
            out.add(f"{h:02d}:{mm}")
        else:
            out.add(f"{h:02d}:{mm}")
            # "7:15" with no meridiem could be either; "07:15" is 24-hour by
            # its own padding, so only the unpadded form gets both readings.
            if len(hh) == 1 and 1 <= h <= 11:
                out.add(f"{h + 12:02d}:{mm}")
    return out


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


# An explicit, reviewed exemption for a line the heuristics cannot judge: a
# historical narrative that must keep naming a deleted service, or a count that
# is deliberately about the repo rather than the live fleet. Placed on the line
# or the line above it, with the reason inline so the next reader sees why.
SUPPRESS = re.compile(r"<!--\s*verify-docs-ok:\s*(.+?)\s*-->")


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


def check_schedules(path: pathlib.Path, rel: str, live: dict, out: list[Finding]) -> None:
    """Compare every schedule claim sitting next to a scheduled-job name."""
    owners = _schedule_owners(live)
    if not owners:
        return
    names = sorted(owners, key=len, reverse=True)
    name_re = re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b")
    for i, line in _lines(path):
        found = name_re.findall(line)
        if not found or RETIRED_OK.search(line):
            continue
        # One table row can name several jobs with their own times
        # ("fetch-market-data (11 PM), fetch-premarket-refresh (8:20 AM)"),
        # so the whole row is checked against the union of their schedules.
        job = "`, `".join(dict.fromkeys(found))
        entries = [e for name in dict.fromkeys(found) for e in owners[name]]
        live_crons = {re.sub(r"\s+", " ", e[1]["schedule"]) for e in entries}
        live_times = _fire_times(live_crons)
        shown = ", ".join(dict.fromkeys(
            f"`{n}` = `{e['schedule']}`" for n, e in entries))
        crons = {re.sub(r"\s+", " ", c.strip()) for c in CRON.findall(line)}
        crons = {c for c in crons if c.count(" ") == 4}
        # Whole-line rule, as with clock times below: a line that carries the
        # live cron alongside a historical one (an annotated status entry, a
        # before/after note) is correct, not drift.
        if crons and not (crons & live_crons):
            out.append(Finding("schedule-drift", rel, i,
                               f"`{job}` documented as "
                               f"{', '.join('`' + c + '`' for c in sorted(crons))}; "
                               f"live: {shown}"))
        # A line is checked as a whole, not per-token: schedule tables here
        # carry an ET column AND a UTC column, so a correct row states two
        # different times and only one of them can match. One match anywhere
        # on the line means the row is right.
        claimed = _clock_times(line)
        if claimed and live_times and not (claimed & live_times):
            out.append(Finding("clock-drift", rel, i,
                               f"`{job}` documented at {', '.join(sorted(claimed))}; "
                               f"no live fire time matches "
                               f"({', '.join(sorted(live_times))}) — {shown}"))
        if UTC_TIME.search(line):
            zones = {e[1]["timeZone"] for e in entries}
            out.append(Finding("utc-claim", rel, i,
                               f"`{job}` is scheduled in {'/'.join(sorted(zones))} "
                               f"({shown}) but the line states a UTC clock time: "
                               f"{line.strip()[:120]}"))


def check_known_names(path: pathlib.Path, rel: str, live: dict, out: list[Finding]) -> None:
    """Backticked names introduced as a Cloud Run Job / scheduler must exist."""
    known = (set(live["run_jobs"]) | set(live["schedulers"]) | set(live["services"])
             | set(live.get("secrets", ())) | set(live.get("queues", ()))
             | {"trading-system"})  # Artifact Registry package, not a CR resource
    context = re.compile(r"Cloud Run Job|Cloud Scheduler|scheduler entry|CR Job", re.I)
    tick = re.compile(r"`([a-z][a-z0-9-]{4,})`")
    for i, line in _lines(path):
        if not context.search(line) or RETIRED_OK.search(line):
            continue
        for cand in tick.findall(line):
            if "-" not in cand or cand in known:
                continue
            # Only flag names that LOOK like ours: they share a prefix with a
            # real job. An unrelated backticked token is not a claim about us.
            head = cand.split("-")[0]
            if any(k.split("-")[0] == head for k in known):
                out.append(Finding("unknown-name", rel, i,
                                   f"`{cand}` is named as infrastructure but no such "
                                   f"job/scheduler/service exists live"))


COUNT_CLAIM = re.compile(r"\b(\d{1,3})\s+Cloud Run Jobs\b", re.I)


def check_counts(path: pathlib.Path, rel: str, live: dict, out: list[Finding]) -> None:
    """A stated Cloud Run Job count must match the live count."""
    n_live = len(live["run_jobs"])
    for i, line in _lines(path):
        if RETIRED_OK.search(line):
            continue
        for claimed in COUNT_CLAIM.findall(line):
            if int(claimed) != n_live:
                out.append(Finding("count-drift", rel, i,
                                   f"claims {claimed} Cloud Run Jobs; live count is {n_live}"))


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
