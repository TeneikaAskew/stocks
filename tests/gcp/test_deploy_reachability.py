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


def test_all_target_creates_the_job_both_cloud_build_triggers_update():
    """Codex on #1022: apply-schema-cloudbuild.yaml and the staging deploy
    both `gcloud run jobs update apply-schema-migrations`, which requires
    the job to exist, and only the separate `apply-schema)` target created
    it. A rebuild from `all)` then left every staging deploy unable to
    reach its `deploy` step."""
    created = _created_by(_closure(_called_from(ALL_BLOCK)))
    assert "apply-schema-migrations" in created, "apply-schema-migrations is not created by all)"
    assert "deploy_apply_schema_migrations" in _called_from(ALL_BLOCK)


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
    r"--set-secrets=DB_PASS=db-trading-pass:latest",
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


def test_all_builds_the_research_image_before_any_research_job():
    """Codex on #1022: deploy_indicator_correlation deploys from
    ${IMAGE}:research and ran before build_research_image in `all)`, so it
    stayed on the previous research digest (or failed on a fresh project
    where the tag did not exist yet). The research build must precede the
    first function that deploys from that tag."""
    order = [f for f in re.findall(r"^\s*([a-z_][a-z0-9_]*)\s*$", ALL_BLOCK, re.M) if f in FNS]
    assert "build_research_image" in order, "all) must build the research image"
    build_at = order.index("build_research_image")
    research_users = [f for f in order if ":research" in FNS[f] and f != "build_research_image"]
    assert research_users, "expected at least one research-image deploy in all)"
    early = [f for f in research_users if order.index(f) < build_at]
    assert not early, f"research-image deploys before build_research_image: {early}"


@pytest.mark.parametrize("fn, flag", [
    ("deploy_build_options_greeks", r"--task-timeout\s+7200"),
    ("deploy_strat_engine", r"--memory\s+16Gi"),
])
def test_research_jobs_newly_in_all_declare_their_live_sizing(fn, flag):
    """Codex on #1022: `all` now redeploys these jobs, and their declared
    sizing was below the values raised by hand after production failures
    (greeks timeout 3600 vs live 7200; strat-engine 8Gi vs live 16Gi, read
    with `gcloud run jobs describe` on 2026-09-07). Both branches carry the
    live value so a redeploy converges rather than halves the budget."""
    body = FNS[fn]
    assert len(re.findall(flag, body)) == 2, f"{fn}: {flag} must be on the create and update branches"


def test_backfill_ticker_declares_max_retries_zero_on_both_branches():
    """Internal review of #1022 (capacity): backfill-ticker carried
    `--max-retries 1` with no justification at the flag (Rule 0.5), and
    the update branch omitted it, so a live job kept whatever it had. A
    retry on a permanent failure (bad ticker, AV outage) only doubles the
    AV calls and the /replay caller's wait; the job is dispatched
    per calendar month with --wait, so the caller re-runs on failure."""
    body = _functions()["deploy_backfill_ticker"]
    create, update = body.split("gcloud run jobs update", 1)
    assert "--max-retries 0" in create, create
    assert "--max-retries 1" not in body
    assert "--max-retries 0" in update, "the update branch must converge max-retries too"


# ── the DB_SECRET_FLAG exemption list (#1022) ─────────────────────────────


def _flag_exempt_targets() -> set[str]:
    """The dispatcher labels that skip resolving DB_SECRET_FLAG."""
    m = re.search(r"\ncase \"\$\{1:-\}\" in\n\s*([^)]+)\)\s*DB_SECRET_FLAG=\"\"", CODE)
    assert m, "the DB_SECRET_FLAG case statement moved or changed shape"
    # The pattern list wraps over several lines with `\` continuations.
    flat = m.group(1).replace("\\", " ").replace("\n", " ")
    return {lbl.strip().strip('"') for lbl in flat.split("|") if lbl.strip()}


def test_no_flag_exempt_target_consumes_the_secret_flag():
    """Skipping the probe for a target that DOES use ${DB_SECRET_FLAG}
    would deploy that job with an empty --set-secrets, i.e. silently strip
    its credentials. The exemption is therefore only valid for targets that
    never reach the flag, and this is the check that keeps the list honest
    as targets are added."""
    exempt = _flag_exempt_targets()
    arms = _dispatch_arms()
    for label in sorted(exempt):
        if label in ("help", ""):
            continue
        assert label in arms, f"exempt label {label!r} is not a dispatcher target"
        assert not _reaches_token(arms[label], "DB_SECRET_FLAG"), (
            f"./gcp/deploy.sh {label} skips resolving DB_SECRET_FLAG but uses it")


def test_setup_and_the_secret_bootstraps_are_exempt():
    """setup enables the Secret Manager API and setup-notifier-secrets
    creates secrets; neither can require them to be readable first."""
    exempt = _flag_exempt_targets()
    for label in ("setup", "setup-notifier-secrets"):
        assert label in exempt, f"{label} must not gate on a Secret Manager read"


def _dispatch_arms() -> dict[str, str]:
    body = DISPATCH[:DISPATCH.index("\nesac")]
    arms: dict[str, str] = {}
    for m in re.finditer(r"^\s{4}([a-z0-9|_\-\"]+)\)(.*?);;", body, re.S | re.M):
        for lbl in m.group(1).split("|"):
            arms[lbl.strip().strip('"')] = m.group(2)
    return arms


def _reaches_token(body: str, token: str, seen: set[str] | None = None) -> bool:
    seen = set() if seen is None else seen
    if token in body:
        return True
    for fn in FNS:
        if fn in seen or not re.search(r"\b" + fn + r"\b", body):
            continue
        seen.add(fn)
        if _reaches_token(FNS[fn], token, seen):
            return True
    return False


def test_p2_build_gamma_levels_takes_only_the_database_password():
    """The live job holds exactly one secret (`gcloud run jobs describe
    p2-build-gamma-levels`, 2026-09-08: DB_PASS <- db-trading-pass, plus
    four plain env vars), and the module reads no API key or webhook.
    Deploying it through the shared ${DB_SECRET_FLAG} would hand it the
    AlphaVantage key and three Discord webhooks on the next run of this
    target — a capture that widens what it captured."""
    body = _gamma_levels_body()
    assert "DB_SECRET_FLAG" not in body, (
        "the shared secret set grants more than this job uses")
    assert body.count("--set-secrets=DB_PASS=db-trading-pass:latest") == 2, (
        "both the create and the update branch must name the one secret")
