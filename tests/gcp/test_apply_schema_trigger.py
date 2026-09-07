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
    fn = body[body.index("_apply_schema_job_flags() {"):]
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


# ── Executable checks of the two deploy.sh functions (internal review of
# round 14): run them under bash with stub `gcloud` / `git` on PATH.
import os
import stat
import subprocess
import textwrap


def _bash_env(tmp_path, gcloud_script: str, git_script: str | None = None) -> dict:
    binder = tmp_path / "bin"
    binder.mkdir(exist_ok=True)
    for name, body in (("gcloud", gcloud_script), ("git", git_script)):
        if body is None:
            continue
        f = binder / name
        f.write_text("#!/usr/bin/env bash\n" + textwrap.dedent(body))
        f.chmod(f.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ)
    env["PATH"] = f"{binder}:{env['PATH']}"
    env["OUT"] = str(tmp_path)
    return env


def _run_fn(tmp_path, env, call: str) -> subprocess.CompletedProcess:
    defs = "\n".join(f"{n}() {{{_fn(n)}}}" for n in
                     ("_apply_schema_job_flags", "deploy_apply_schema_migrations", "apply_schema_via_build"))
    script = f"""set -uo pipefail
PROJECT_ID=proj; REGION=us-east1; SA_EMAIL=sa@proj.iam.gserviceaccount.com
IMAGE=us-east1-docker.pkg.dev/proj/trading/trading-system; DB_SECRET_FLAG='--set-secrets DB_PASSWORD=db-pw:latest'
_env_string() {{ echo 'CLOUD_SQL_CONNECTION_NAME=proj:us-east1:db,DB_USER=trading,DB_NAME=trading'; }}
pin_image_tags() {{ echo PINNED >> "$OUT/calls"; }}
{defs}
cd {REPO}
{call}
echo "rc=$?"
"""
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, cwd=str(REPO))


_GCLOUD_OK = """
    echo "$*" >> "$OUT/calls"
    case "$1 $2 $3" in
      "run jobs describe") echo "${DESCRIBE_STDERR:-}" >&2; exit "${DESCRIBE_RC:-0}" ;;
      "run jobs create") exit 0 ;;
      "artifacts docker images") echo "us-east1-docker.pkg.dev/proj/trading/trading-system@sha256:abc123"; exit 0 ;;
      "builds submit x") ;;
    esac
    if [ "$1 $2" = "builds submit" ]; then
      for a in "$@"; do case "$a" in --config) want=1 ;; *) if [ "${want:-0}" = 1 ]; then cp "$a" "$OUT/rendered.yaml"; want=0; fi ;; esac; done
      exit "${SUBMIT_RC:-0}"
    fi
    exit 0
"""
_GIT_ON_MAIN = """
    case "$*" in
      "fetch -q origin main") exit 0 ;;
      "merge-base --is-ancestor HEAD origin/main") exit "${OFF_MAIN:-0}" ;;
      "merge-base HEAD origin/main") echo bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb ;;
      "rev-parse HEAD") echo aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa ;;
      "rev-parse --short HEAD") echo aaaaaaaa ;;
      "status --porcelain") ;;
      *) case "$1" in log) echo 1700000000 ;; rev-list) printf '%s\\n' "$3" 1111111111111111111111111111111111111111 ;; esac ;;
    esac
"""


def test_bootstrap_distinguishes_not_found_from_a_describe_failure(tmp_path):
    """Internal review of round 14: `describe ... 2>/dev/null` treated a
    503 / auth blip like NOT_FOUND, fell into `jobs create`, which then
    failed with ALREADY EXISTS and aborted `all)` at its first job."""
    env = _bash_env(tmp_path, _GCLOUD_OK)
    env.update(DESCRIBE_RC="1", DESCRIBE_STDERR="ERROR: (gcloud.run.jobs.describe) Job [apply-schema-migrations] not found.")
    r = _run_fn(tmp_path, env, "deploy_apply_schema_migrations")
    calls = (tmp_path / "calls").read_text()
    assert "run jobs create apply-schema-migrations" in calls and "rc=0" in r.stdout, r.stdout + r.stderr
    (tmp_path / "calls").write_text("")
    env.update(DESCRIBE_RC="1", DESCRIBE_STDERR="ERROR: (gcloud.run.jobs.describe) PERMISSION_DENIED: quota")
    r = _run_fn(tmp_path, env, "deploy_apply_schema_migrations")
    calls = (tmp_path / "calls").read_text()
    assert "run jobs create" not in calls, "a describe failure that is not NOT_FOUND must not create"
    assert "rc=1" in r.stdout and "cannot tell" in r.stderr, r.stdout + r.stderr


def test_serialized_apply_renders_a_valid_config_that_converges_the_full_job_declaration(tmp_path):
    """Internal review of round 14 (blocking): with the bootstrap no longer
    updating an existing job and the in-build update passing only --image,
    nothing could ever change the live job's task-timeout, env or secrets
    again (live was 600 s against the declared 1800). The serialized update
    now carries the same declaration the bootstrap creates with, the rendered
    config parses, and $BUILD_ID is the only Cloud Build substitution left."""
    import re
    env = _bash_env(tmp_path, _GCLOUD_OK, _GIT_ON_MAIN)
    r = _run_fn(tmp_path, env, "apply_schema_via_build")
    assert "rc=0" in r.stdout, r.stdout + r.stderr
    rendered = (tmp_path / "rendered.yaml").read_text()
    cfg = yaml.safe_load(rendered)
    assert [s["id"] for s in cfg["steps"]] == ["serialize", "apply"]
    assert cfg["tags"] == ["apply-schema-on-change"] and cfg["timeout"] == "5400s"
    assert cfg["serviceAccount"].endswith("/serviceAccounts/sa@proj.iam.gserviceaccount.com")
    assert re.findall(r"\$\{?[A-Za-z_]+\}?", rendered) == ["$BUILD_ID"], "only $BUILD_ID may be left for Cloud Build"
    apply = " ".join(cfg["steps"][1]["args"])
    update = apply[apply.index("gcloud run jobs update"):apply.index("gcloud run jobs execute")]
    for flag in ("--image=us-east1-docker.pkg.dev/proj/trading/trading-system@sha256:abc123",
                 "--task-timeout 1800", "--memory 512Mi", "--max-retries 0",
                 "--command python,-m,gcp.apply_schema", "--set-secrets DB_PASSWORD=db-pw:latest",
                 "--set-env-vars CLOUD_SQL_CONNECTION_NAME=proj:us-east1:db,DB_USER=trading,DB_NAME=trading"):
        assert flag in update, flag
    execute = apply[apply.index("gcloud run jobs execute"):]
    assert "--revision=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,--revision-time=1700000000,--revision-ancestors=aaaaaaaa" in execute
    assert "--wait" in execute
    calls = (tmp_path / "calls").read_text()
    assert "--timeout=5400s" in calls, "the submit must not depend on the operator's builds/timeout property"
    assert "PINNED" in calls, "the digest the job now runs must be pinned"


def test_job_declaration_is_one_function_used_by_create_and_update():
    body = _fn("_apply_schema_job_flags")
    assert "--task-timeout 1800" in body
    assert "_apply_schema_job_flags" in _fn("deploy_apply_schema_migrations")
    assert "_apply_schema_job_flags" in _fn("apply_schema_via_build")


def test_serialized_apply_pins_even_when_the_build_fails(tmp_path):
    """A failed execute after a successful update leaves the job on a digest
    only :latest keeps alive; the pin must run whatever the build's outcome."""
    env = _bash_env(tmp_path, _GCLOUD_OK, _GIT_ON_MAIN)
    env["SUBMIT_RC"] = "1"
    r = _run_fn(tmp_path, env, "apply_schema_via_build")
    assert "rc=1" in r.stdout, r.stdout + r.stderr
    assert "PINNED" in (tmp_path / "calls").read_text()


def test_manual_apply_records_the_main_base_when_head_is_off_main(tmp_path):
    """Internal review of round 14: recording a feature-branch SHA lets a
    later main apply be refused on committer time (the branch commit is
    neither ancestor nor descendant of the squash commit). Off main, the
    guard records the newest main commit the checkout contains."""
    env = _bash_env(tmp_path, _GCLOUD_OK, _GIT_ON_MAIN)
    env["OFF_MAIN"] = "1"
    r = _run_fn(tmp_path, env, "apply_schema_via_build")
    assert "rc=0" in r.stdout, r.stdout + r.stderr
    rendered = (tmp_path / "rendered.yaml").read_text()
    assert "--revision=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb," in rendered
    assert "--revision=aaaaaaaa" not in rendered
    assert "not on origin/main" in r.stderr
