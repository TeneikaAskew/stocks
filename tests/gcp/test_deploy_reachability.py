"""Reachability invariants for gcp/deploy.sh — #829 (K1), #834 (D2), #831 (K3).

Three audit findings were one missing invariant. `gamma-levels-daily`
scheduled a job (`p2-build-gamma-levels`) that no `deploy_*` function
created: the job was made by hand, so its image, memory, timeout and
retries lived nowhere in version control (#829, #834). Three Discord
backing-job deploy functions were defined but unreachable from the
dispatcher, and `all)` deployed neither the slash-command service nor its
jobs (#831). Nothing checked that a scheduler's target is a job the script
creates, or that `./gcp/deploy.sh all` reproduces what production runs, so
a fresh-environment rebuild would silently come up partial.

These tests parse deploy.sh statically (comment lines stripped) and pin:

1. every `_schedule*` target is a job or service some `deploy_*` creates;
2. every `deploy_*` function is reachable from the dispatcher;
3. `all)` (transitively) creates every scheduled job and service;
4. the captured `p2-build-gamma-levels` spec matches the live job
   (`gcloud run jobs describe`, 2026-09-07): research image, cpu 2,
   memory 2Gi, max-retries 0, task-timeout 5400.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DEPLOY_SH = (REPO / "gcp/deploy.sh").read_text()
# Comment lines would otherwise register phantom targets (a commented-out
# `_schedule_with_args "p7b-classifier-daily" ...` line still exists).
CODE = "\n".join(l for l in DEPLOY_SH.splitlines() if not l.lstrip().startswith("#"))

_FN_RE = re.compile(r"^([a-z_][a-z0-9_]*)\(\)\s*\{", re.M)


def _functions() -> dict[str, str]:
    bodies = {}
    for name in _FN_RE.findall(CODE):
        m = re.search(r"^" + name + r"\(\)\s*\{(.*?)^\}", CODE, re.M | re.S)
        assert m, f"could not delimit function {name}"
        bodies[name] = m.group(1)
    return bodies


FNS = _functions()
DISPATCH = CODE[CODE.index('case "${1:-help}" in'):]
ALL_BLOCK = re.search(r"\n\s+all\)\s*\n(.*?)\n\s+;;", DISPATCH, re.S).group(1)


def _closure(seed: set[str]) -> set[str]:
    reach, stack = set(), list(seed)
    while stack:
        f = stack.pop()
        if f in reach:
            continue
        reach.add(f)
        stack.extend(g for g in FNS if g not in reach and re.search(r"\b" + g + r"\b", FNS[f]))
    return reach


def _called_from(text: str) -> set[str]:
    return {f for f in FNS if re.search(r"\b" + f + r"\b", text)}


def _created_by(fns: set[str]) -> set[str]:
    out = set()
    for f in fns:
        out |= set(re.findall(r"gcloud run jobs create\s+([A-Za-z0-9\-]+)", FNS[f]))
        out |= set(re.findall(r"gcloud run deploy\s+([A-Za-z0-9\-]+)", FNS[f]))
    return out


# Every scheduler variant takes (name, cron, target) as its first three
# positional args, possibly split across `\`-continued lines.
_SCHED_RE = re.compile(
    r'_schedule[a-z_]*\s+"[^"]+"\s*(?:\\\n\s*)?"[^"]+"\s*(?:\\\n\s*)?"([^"]+)"'
)
SCHEDULED = set(_SCHED_RE.findall(FNS["deploy_schedulers"]))
# The notifier service is deployed under a variable name and is not a
# scheduler target, so it does not participate in the target checks.
DEPLOY_FNS = sorted(f for f in FNS if f.startswith("deploy_"))


def test_schedulers_were_parsed():
    assert {"phase6-playbook", "signal-monitor", "discord-interactions"} <= SCHEDULED
    assert "p2-build-gamma-levels" in SCHEDULED, "the K1 target must be visible to the parser"
    assert "p7b-next-candle-classifier" not in SCHEDULED, "commented-out schedule lines must be ignored"
    assert len(SCHEDULED) > 30


def test_every_schedule_target_is_created_by_some_deploy_function():
    """#829: a scheduler pointing at a job nothing creates is a rebuild trap."""
    created = _created_by(set(FNS))
    missing = sorted(SCHEDULED - created)
    assert not missing, (
        f"_schedule targets with no `gcloud run jobs create`/`gcloud run deploy` "
        f"in any deploy function: {missing}"
    )


def test_every_deploy_function_is_reachable_from_the_dispatcher():
    """#831: an unreachable deploy_* reads as available infrastructure but
    can never run."""
    reach = _closure(_called_from(DISPATCH))
    dead = sorted(f for f in DEPLOY_FNS if f not in reach)
    assert not dead, f"deploy_* functions unreachable from any dispatcher target: {dead}"


def test_all_target_creates_every_scheduled_job_and_service():
    """#829/#831 definition of done: `./gcp/deploy.sh all` on an empty
    project must produce every job and service its schedulers target."""
    created = _created_by(_closure(_called_from(ALL_BLOCK)))
    missing = sorted(SCHEDULED - created)
    assert not missing, f"scheduled targets `all)` never creates: {missing}"


def test_all_target_deploys_discord_service_and_its_backing_jobs():
    """#831 (Codex on #802): the slash-command service and the three jobs
    it dispatches (gcp/discord_interactions/main.py execute()s
    backfill-ticker, validate-brief, backtest) must survive a rebuild."""
    created = _created_by(_closure(_called_from(ALL_BLOCK)))
    for job in ("discord-interactions", "backfill-ticker", "validate-brief", "backtest"):
        assert job in created, f"{job} is not created by all)"


def test_discord_target_deploys_service_and_backing_jobs_together():
    m = re.search(r"\n\s+discord\)\s*(.*?);;", DISPATCH, re.S)
    assert m, "discord) dispatcher target missing"
    created = _created_by(_closure(_called_from(m.group(1))))
    assert {"discord-interactions", "backfill-ticker", "validate-brief", "backtest"} <= created


def _gamma_levels_body() -> str:
    assert "deploy_p2_build_gamma_levels" in FNS, \
        "deploy_p2_build_gamma_levels() must exist (#834: the job's config lives nowhere in the repo)"
    return FNS["deploy_p2_build_gamma_levels"]


@pytest.mark.parametrize("flag", [
    r'research_image="\$\{IMAGE\}:research"',
    r'--image\s+"\$\{research_image\}"',
    r"--memory\s+2Gi",
    r"--cpu\s+2\b",
    r"--max-retries\s+0",
    r"--task-timeout\s+5400",
    r'--service-account\s+"\$\{SA_EMAIL\}"',
    r'--command\s+"python"',
    r'--args="-m,gcp\.research\.p2_build_gamma_levels"',
    r"\$\{DB_SECRET_FLAG\}",
    r'--set-env-vars\s+"\$\(_env_string\)"',
])
def test_p2_build_gamma_levels_reproduces_the_live_spec(flag):
    """#834: captured from `gcloud run jobs describe p2-build-gamma-levels`
    on 2026-09-07 — image trading-system:research, python -m
    gcp.research.p2_build_gamma_levels, cpu 2, memory 2Gi, maxRetries 0,
    timeoutSeconds 5400, SA trading-runner, env CLOUD_SQL_CONNECTION_NAME/
    DB_USER/DB_NAME/GCS_BUCKET + DB_PASS secret. Default args only, so the
    nightly run rebuilds the current year (see the module's --start-year)."""
    body = _gamma_levels_body()
    assert re.search(flag, body), f"{flag} not found in deploy_p2_build_gamma_levels"


def test_p2_build_gamma_levels_create_and_update_carry_the_same_command():
    body = _gamma_levels_body()
    assert body.count('--args="-m,gcp.research.p2_build_gamma_levels"') == 2, \
        "both the create and the update branch must set the module explicitly"


def test_gamma_levels_dispatcher_target_uses_the_research_image_without_rebuilding_latest():
    m = re.search(r"\n\s+gamma-levels\)\s*(.*?);;", DISPATCH, re.S)
    assert m, "gamma-levels) dispatcher target missing (#829)"
    assert "deploy_p2_build_gamma_levels" in m.group(1)
    assert "build_image" not in m.group(1), \
        "research-image jobs deploy from :research; do not rebuild :latest for them"
