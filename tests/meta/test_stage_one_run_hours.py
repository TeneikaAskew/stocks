"""The jobs whose stage-one sites are right "because of when they run" do not
run in the evening (FEAT-DATA-001, stage 1 of the market-time sweep).

The containers' clock is UTC, so ``date.today()`` there is tomorrow from 19:00
to 23:59 America/New_York (tests/lib/test_market_today_hours.py pins the
hours). For 31 of the 71 sites the spec says the date change moves no value
today, because the code only runs outside those hours. That is a statement
about ``gcp/deploy.sh``, and this test is what holds it: a schedule moved into
the evening, or a mode changed under an evening entry, fails here instead of
silently turning a "no value changes" into a changed value.

It is judged per scheduler entry and not per job, because one job can be
scheduled in two modes: ``refresh-earnings-views`` runs ``--mode=daily`` at
07:30 (which reaches both of its sites) and ``--mode=weekly`` on Sunday at
20:00 (which reaches neither).

``gcp/deploy.sh`` is read through the repo's own reader
(``scripts/maintenance/doc_inventory.py``), which also finds the entries
declared outside the three ``_schedule*`` helper forms.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import gcp.refresh_earnings_views as refresh_views
from scripts.maintenance import doc_inventory as inventory

REPO = Path(__file__).resolve().parents[2]

#: The hours, America/New_York, in which a run can start with the host's UTC
#: date already on tomorrow (19:00 in winter, 20:00 in summer, until midnight).
EVENING_HOURS = range(19, 24)

#: The scheduled jobs all of whose stage-one sites the spec's Appendix A marks
#: "no" (not wrong at the hours their code runs today).
NO_JOBS = (
    "audit-brief-bias",
    "audit-walkforward",
    "build-realtime-gex",
    "backfill-daily-indicators",
    "fetch-economic-events",
    "fetch-fred-rates",
    "fetch-insider-transactions",
    "fetch-premarket-refresh",
    "fetch-sec-filings",
    "fetch-top-movers",
    "refresh-earnings-views",
    "regime-combo",
    "signal-monitor",
    "weekend-review",
    "calibrate-thresholds",
)

#: The one scheduler entry of such a job that starts in the evening hours. It
#: passes no arguments of its own, so its run is the job's ``--mode=weekly``,
#: which never reaches the job's two stage-one sites (pinned below).
WEEKLY_VIEWS_ENTRY = ("refresh-earnings-views-weekly", "0 20 * * 0", ["--mode=weekly"])


def start_hours(cron: str) -> set[int]:
    """The hours the hour field of a five-field cron can start a run in."""
    fields = cron.split()
    if len(fields) != 5:
        raise ValueError(f"not a five-field cron: {cron!r}")
    hours: set[int] = set()
    for part in fields[1].split(","):
        step = 1
        if "/" in part:
            part, step_text = part.split("/")
            step = int(step_text)
        if part == "*":
            low, high = 0, 23
        elif "-" in part:
            low, high = (int(bound) for bound in part.split("-"))
        else:
            low = high = int(part)
        hours.update(range(low, high + 1, step))
    return hours


def resolved_args(entry: dict, jobs: dict) -> list[str]:
    """The arguments a scheduler entry's run is started with.

    An entry that overrides the command line runs with its own tokens (the
    reader flattens ``NAME=value`` env pairs into the same string; those are
    dropped). An entry that overrides nothing, or only an env var, runs with
    the ``--args`` its job's deploy function sets.
    """
    own = entry.get("args") or ""
    if inventory._overrides_argv(own):
        return [token for token in own.split() if token.startswith("-") or "=" not in token]
    return (jobs[entry["target_job"]]["args"] or "").split()


def evening_entries(root: Path) -> list[tuple[str, str, list[str]]]:
    """``(name, cron, resolved_args)`` for each entry of a NO_JOBS job that can start in the evening."""
    jobs = {job["name"]: job for job in inventory.deploy_jobs(root)}
    found = []
    for entry in inventory.deploy_schedulers(root):
        if entry["target_job"] not in NO_JOBS:
            continue
        if entry["time_zone"] != "America/New_York":
            raise AssertionError(
                f"{entry['name']} runs in {entry['time_zone']!r}; the evening hours here are Eastern")
        if start_hours(entry["cron"]) & set(EVENING_HOURS):
            found.append((entry["name"], entry["cron"], resolved_args(entry, jobs)))
    return found


def test_no_job_whose_sites_are_right_by_schedule_runs_in_the_evening():
    jobs = {job["name"] for job in inventory.deploy_jobs(REPO)}
    scheduled = {entry["target_job"] for entry in inventory.deploy_schedulers(REPO)}
    # A renamed or unscheduled job cannot pass by having no entry to judge.
    assert [job for job in NO_JOBS if job not in jobs] == []
    assert [job for job in NO_JOBS if job not in scheduled] == []

    assert evening_entries(REPO) == [WEEKLY_VIEWS_ENTRY]


def _called_names(function: ast.FunctionDef) -> set[str]:
    return {
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def test_the_weekly_views_run_never_reaches_the_daily_sites(monkeypatch):
    ran = []
    monkeypatch.setattr(refresh_views, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(refresh_views, "refresh_weekly", lambda: ran.append("weekly"))
    monkeypatch.setattr(refresh_views, "refresh_daily", lambda days: ran.append("daily"))

    assert refresh_views.main(WEEKLY_VIEWS_ENTRY[2]) == 0
    assert ran == ["weekly"]

    # Neither market-date read lies in refresh_weekly or in a function it calls.
    tree = ast.parse(Path(refresh_views.__file__).read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    reached, pending = set(), ["refresh_weekly"]
    while pending:
        name = pending.pop()
        if name in reached or name not in functions:
            continue
        reached.add(name)
        pending.extend(_called_names(functions[name]))
    readers = {"market_today", "market_today_sql"}
    assert "refresh_weekly" in reached and "_refresh_one" in reached
    assert [name for name in sorted(reached) if _called_names(functions[name]) & readers] == []
    # The check cannot pass empty: the daily path does hold both reads.
    assert readers <= _called_names(functions["refresh_daily"])


def _deploy_copy(root: Path, edit) -> Path:
    """A tree under *root* holding gcp/deploy.sh as *edit* rewrites it."""
    text = (REPO / "gcp" / "deploy.sh").read_text(encoding="utf-8")
    (root / "gcp").mkdir(parents=True)
    (root / "gcp" / "deploy.sh").write_text(edit(text), encoding="utf-8")
    return root


def _replace_once(old: str, new: str):
    def edit(text: str) -> str:
        # The text is found before it is replaced: a reworded deploy.sh fails here, not silently.
        assert text.count(old) == 1, f"{old!r} occurs {text.count(old)} times in gcp/deploy.sh"
        return text.replace(old, new)
    return edit


def _weekly_job_args_become_daily(text: str) -> str:
    start = text.index("deploy_refresh_earnings_views() {")
    body = text[start:text.index("\n}\n", start)]
    assert body.count('--args="--mode=weekly"') == 2  # the create and the update command
    return text.replace(body, body.replace('--args="--mode=weekly"', '--args="--mode=daily"'))


def test_a_moved_schedule_or_a_changed_mode_fails(tmp_path):
    # (a) a daytime entry of a NO_JOBS job is moved into the evening.
    moved = _deploy_copy(tmp_path / "moved", _replace_once(
        '"realtime-gex-daily" "0 17 * * 1-5"', '"realtime-gex-daily" "0 21 * * 1-5"'))
    assert evening_entries(moved) == [
        ("realtime-gex-daily", "0 21 * * 1-5", ["-m", "gcp.build_realtime_gex", "--incremental", "--days=3"]),
        WEEKLY_VIEWS_ENTRY,
    ]

    # (b) the job's own arguments change: the weekly entry passes none, so it follows them.
    job = _deploy_copy(tmp_path / "job", _weekly_job_args_become_daily)
    assert evening_entries(job) == [("refresh-earnings-views-weekly", "0 20 * * 0", ["--mode=daily"])]

    # (c) the entry itself is given other arguments.
    entry = _deploy_copy(tmp_path / "entry", _replace_once(
        '_schedule "refresh-earnings-views-weekly"     "0 20 * * 0"   "refresh-earnings-views"',
        '_schedule_args "refresh-earnings-views-weekly" "0 20 * * 0" "refresh-earnings-views" "--mode=daily"'))
    assert evening_entries(entry) == [("refresh-earnings-views-weekly", "0 20 * * 0", ["--mode=daily"])]


def test_an_entry_that_overrides_only_an_env_var_keeps_the_jobs_arguments():
    jobs = {job["name"]: job for job in inventory.deploy_jobs(REPO)}
    (weekly,) = [entry for entry in inventory.deploy_schedulers(REPO)
                 if entry["name"] == "backfill-indicators-weekly"]
    # Declared with a raw `gcloud scheduler jobs create`, outside the helper forms.
    assert weekly["args"] == "BACKFILL_MODE=full"
    assert resolved_args(weekly, jobs) == (jobs["backfill-daily-indicators"]["args"] or "").split()


@pytest.mark.parametrize("cron, hours", [
    ("30 9-15 * * 1-5", set(range(9, 16))),
    ("0 7,10,13,17 * * 1-5", {7, 10, 13, 17}),
    ("0 */6 * * *", {0, 6, 12, 18}),
    ("15 * * * *", set(range(24))),
    ("0 20 * * 0", {20}),
])
def test_start_hours(cron, hours):
    assert start_hours(cron) == hours


def test_start_hours_refuses_a_cron_that_is_not_five_fields():
    with pytest.raises(ValueError):
        start_hours("0 20 * *")

