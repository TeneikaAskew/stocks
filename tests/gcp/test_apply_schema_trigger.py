"""The apply-schema-on-change trigger must apply the triggering revision's schema.

Codex on #1022: the config was a bare `gcloud run jobs execute` of the
already deployed apply-schema-migrations job, which reads gcp/schema.sql
from inside its own image, and that image is only rebuilt by a manual
`./gcp/deploy.sh build`. A PR adding a column plus a reader of it would ship
the reader through the auto-deployed API while the trigger applied a stale
schema. These are config invariants, asserted by reading the file, in the
same spirit as tests/gcp/test_staging_deploy_paths.py.
"""
import pathlib

import pytest

yaml = pytest.importorskip("yaml")

REPO = pathlib.Path(__file__).resolve().parents[2]
CFG = REPO / "gcp/cloudbuild/apply-schema-cloudbuild.yaml"


def _steps():
    return yaml.safe_load(CFG.read_text())["steps"]


def _all_args(step) -> str:
    return " ".join(str(a) for a in step.get("args", []))


def _step(name):
    return next(s for s in _steps() if s["id"] == name)


def test_the_trigger_builds_the_trading_system_image_from_source():
    build = _step("build")
    args = _all_args(build)
    assert "gcp/Dockerfile" in args, "must build the job image from this revision"
    assert "${_IMAGE}:${SHORT_SHA}" in args, "immutable tag, never the mutable :latest"
    assert _all_args(_step("push")).endswith("${_IMAGE}:${SHORT_SHA}")


def test_the_job_is_moved_to_the_new_digest_before_it_runs():
    apply = _all_args(_step("apply"))
    assert "fully_qualified_digest" in apply
    update = apply.index("gcloud run jobs update apply-schema-migrations")
    execute = apply.index("gcloud run jobs execute apply-schema-migrations")
    assert update < execute, "the image update must precede the execute"
    assert "--wait" in apply[execute:]
    assert '--image="$${DIGEST}"' in apply, "the job must be pinned to the resolved digest"


def test_the_pipeline_order_is_preflight_build_push_serialize_apply_pin():
    ids = [s["id"] for s in _steps()]
    assert ids == ["preflight", "build", "push", "serialize", "apply", "pin"], ids
    assert "SHORT_SHA" in _all_args(_step("preflight")), "refuse a nameless tag"
    assert _step("apply")["waitFor"] == ["serialize"], "the job mutation must wait for the serializer"


WAIT = REPO / "gcp/cloudbuild/wait_for_earlier_schema_builds.sh"


def test_overlapping_schema_builds_apply_in_start_order():
    """Codex on #1022: two schema pushes minutes apart would race on the
    shared apply-schema-migrations job; completion order, not commit order,
    would decide which digest ran last. The serializer waits for every
    EARLIER-started build of this trigger, fails closed when it cannot look,
    and is bounded below the build timeout."""
    cfg = yaml.safe_load(CFG.read_text())
    assert cfg.get("tags") == ["apply-schema-on-change"], "the tag is how builds see each other"
    assert "wait_for_earlier_schema_builds.sh" in _all_args(_step("serialize"))
    src = WAIT.read_text()
    # Both triggers mutate the job, so both tags are scanned.
    assert 'TAGS="apply-schema-on-change solyra-api-staging-deploy"' in src
    staging = yaml.safe_load((REPO / "gcp/cloudbuild/deploy-solyra-api-staging-cloudbuild.yaml").read_text())
    assert staging.get("tags") == ["solyra-api-staging-deploy"]
    assert "--ongoing" in src and "createTime<'${self_create}'" in src, \
        "must wait only on builds that started earlier (total order, no deadlock)"
    code = [ln for ln in src.splitlines() if not ln.lstrip().startswith("#")]
    assert not any("|| true" in ln for ln in code), "the guard must fail closed"
    assert src.count("exit 1") >= 3, "cannot-describe, cannot-list and deadline all fail"
    assert "DEADLINE_SECONDS" not in src, "a fixed wait budget ignores the outer build timeout"


def _apply_job_task_timeout() -> int:
    """The --task-timeout deploy.sh declares for apply-schema-migrations."""
    import re
    body = (REPO / "gcp/deploy.sh").read_text()
    fn = body[body.index("deploy_apply_schema_migrations() {"):]
    fn = fn[:fn.index("\n}")]
    timeouts = {int(m) for m in re.findall(r"--task-timeout (\d+)", fn)}
    assert len(timeouts) == 1, timeouts
    return timeouts.pop()


def test_the_wait_reserves_the_build_time_the_apply_and_deploy_need():
    """Codex on #1022: the waiter's budget was a constant below the build
    timeout, but the wait starts after the image build and is followed by
    the apply job (its own timeout) plus pin or deploy, so the outer Cloud
    Build timeout could kill the build mid-apply. The waiter now reads its
    build's createTime and timeout and stops when the remaining budget
    falls below a reserve that covers the apply job and the deploy."""
    src = WAIT.read_text()
    # Cloud Build's `timeout` is the duration the build may RUN; queued time
    # is bounded separately by queueTtl (Codex on #1022). So the budget is
    # anchored to startTime, while createTime still orders peers.
    assert "value(createTime,startTime,timeout)" in src, "the budget comes from the build itself"
    assert 'date -u -d "${self_start_time}"' in src, "the deadline is anchored to startTime"
    assert "createTime<'${self_create}'" in src, "peer ordering stays on createTime"
    reserve = int(src.split("RESERVE_SECONDS:-")[1].split("}")[0])
    assert reserve >= _apply_job_task_timeout() + 240, \
        "the reserve must cover the apply job's timeout plus the deploy/pin step"
    for path in (CFG, REPO / "gcp/cloudbuild/deploy-solyra-api-staging-cloudbuild.yaml"):
        timeout = int(str(yaml.safe_load(path.read_text())["timeout"]).rstrip("s"))
        # image build (staging builds measure 4.5-6 min) + a full earlier
        # build's apply + this build's reserve
        assert timeout >= 2 * reserve + 900, (path.name, timeout, reserve)


def test_the_image_is_the_trading_system_repo_not_the_api_image():
    subs = yaml.safe_load(CFG.read_text())["substitutions"]
    assert subs["_IMAGE"].endswith("/trading/trading-system"), subs


def test_the_apply_passes_the_source_revision_to_the_guard():
    """Codex on #1022: build start order is not commit order. Both schema-
    mutating builds pass the commit SHA and committer time so gcp/apply_schema
    refuses a revision older than the newest successfully applied one."""
    for path in (CFG, REPO / "gcp/cloudbuild/deploy-solyra-api-staging-cloudbuild.yaml"):
        steps = yaml.safe_load(path.read_text())["steps"]
        step = next(s for s in steps if s["id"] in ("apply", "migrate"))
        args = _all_args(step)
        assert 'git log -1 --format=%ct "$COMMIT_SHA"' in args, path.name
        assert '--args="--revision=$COMMIT_SHA,--revision-time=$${COMMIT_TIME},' in args, path.name
        assert args.index("COMMIT_TIME=$(git log") < args.index("gcloud run jobs execute"), path.name


def test_the_apply_hands_the_checkout_ancestry_to_the_guard():
    """Codex on #1022: equal committer seconds are real on main, so the guard
    needs ancestry to order a tie. The trigger checkout is a single-revision
    fetch (FETCHSOURCE: `* branch <sha> -> FETCH_HEAD`), so each build deepens
    it first, then passes `git rev-list` of the revision; a checkout that
    cannot be deepened is reported, and the applier refuses the tie."""
    for path in (CFG, REPO / "gcp/cloudbuild/deploy-solyra-api-staging-cloudbuild.yaml"):
        steps = yaml.safe_load(path.read_text())["steps"]
        step = next(s for s in steps if s["id"] in ("apply", "migrate"))
        args = _all_args(step)
        assert 'git fetch --deepen=' in args, path.name
        assert 'ANCESTORS=$(git rev-list --max-count=' in args, path.name
        assert '--revision-ancestors=$${ANCESTORS}' in args, path.name
        assert args.index("git fetch --deepen=") < args.index("ANCESTORS=$(git rev-list") \
            < args.index("gcloud run jobs execute"), path.name


def test_the_apply_checks_the_job_exists_before_updating_it():
    """Codex on #1022: `gcloud run jobs update` fails when the job is
    missing (fresh project, or the maintenance job deleted). Both configs
    look first and fail with the bootstrap command (the job's env, secrets
    and service account live in gcp/deploy.sh, so the build must not
    create it from a partial spec)."""
    for path in (CFG, REPO / "gcp/cloudbuild/deploy-solyra-api-staging-cloudbuild.yaml"):
        steps = yaml.safe_load(path.read_text())["steps"]
        step = next(s for s in steps if s["id"] in ("apply", "migrate"))
        args = _all_args(step)
        assert "gcloud run jobs describe apply-schema-migrations" in args, path.name
        assert args.index("gcloud run jobs describe apply-schema-migrations") \
            < args.index("gcloud run jobs update apply-schema-migrations"), path.name
        assert "./gcp/deploy.sh apply-schema" in args, "the failure must name the bootstrap command"


# ── Every mutation of apply-schema-migrations goes through the serializer ──
DEPLOY_SH = (REPO / "gcp/deploy.sh").read_text()
_CODE = "\n".join(l for l in DEPLOY_SH.splitlines() if not l.lstrip().startswith("#"))


def _fn(name: str) -> str:
    import re
    m = re.search(r"^" + name + r"\(\)\s*\{(.*?)^\}", _CODE, re.M | re.S)
    assert m, f"{name} not found in deploy.sh"
    return m.group(1)


def _target(name: str) -> str:
    import re
    dispatch = _CODE[_CODE.index('case "${1:-help}" in'):]
    m = re.search(r"\n\s+" + re.escape(name) + r"\)\s*(.*?);;", dispatch, re.S)
    assert m, f"{name}) target not found"
    return m.group(1)


def test_all_only_bootstraps_the_migration_job_and_never_updates_it():
    """Codex on #1022: an `all)` run between a Cloud Build's `jobs update`
    and `jobs execute` could repoint the shared job at the local image,
    and the build would then execute a different schema while recording
    its own revision as applied. The serializer only sees tagged builds,
    so deploy.sh must not update an existing job outside it: `all)` creates
    the job when it is missing and otherwise leaves it alone."""
    body = _fn("deploy_apply_schema_migrations")
    assert "gcloud run jobs create apply-schema-migrations" in body
    assert "gcloud run jobs update apply-schema-migrations" not in body, \
        "bootstrap only: the image is moved by the serialized path"
    assert "deploy_apply_schema_migrations" in _target("all")
    assert "apply_schema_via_build" not in _target("all")


def test_the_manual_apply_target_is_a_tagged_serialized_cloud_build():
    """`./gcp/deploy.sh apply-schema` submits a Cloud Build carrying the
    same tag the triggers use, runs the same serializer inside it, and
    moves + executes the job from there, so it is ordered with the trigger
    builds instead of racing them. The revision guard args come from the
    local checkout."""
    body = _fn("apply_schema_via_build")
    assert "gcloud builds submit" in body
    assert "apply-schema-on-change" in body, "must carry the tag the serializer scans"
    assert "wait_for_earlier_schema_builds.sh" in body
    assert "gcloud run jobs update apply-schema-migrations" in body
    assert "gcloud run jobs execute apply-schema-migrations" in body and "--wait" in body
    for arg in ("--revision=", "--revision-time=", "--revision-ancestors="):
        assert arg in body, arg
    assert "timeout: 5400s" in body
    target = _target("apply-schema")
    assert "build_image" in target and "apply_schema_via_build" in target
    assert target.index("deploy_apply_schema_migrations") < target.index("apply_schema_via_build"), \
        "bootstrap (create if missing) before the serialized move"
    # No other function updates the job outside a Cloud Build.
    import re
    updaters = {name for name in re.findall(r"^([a-z_][a-z0-9_]*)\(\)\s*\{", _CODE, re.M)
                if "gcloud run jobs update apply-schema-migrations" in _fn(name)}
    assert updaters == {"apply_schema_via_build"}, updaters
