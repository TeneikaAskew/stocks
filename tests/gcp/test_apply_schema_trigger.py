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
WAIT = REPO / "gcp/cloudbuild/wait_for_earlier_schema_builds.sh"


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


def test_the_pipeline_order_is_preflight_build_push_serialize_apply_pin_verify():
    ids = [st["id"] for st in _steps()]
    assert ids == ["preflight", "build", "push", "serialize", "apply", "pin", "verify"], ids
    by = {st["id"]: st for st in _steps()}
    assert by["build"]["waitFor"] == ["preflight"] and by["push"]["waitFor"] == ["build"]
    assert by["serialize"]["waitFor"] == ["push"] and by["apply"]["waitFor"] == ["serialize"]
    assert by["pin"]["waitFor"] == ["apply"] and by["verify"]["waitFor"] == ["pin"]


def _pins_on_failure(path, mutate_step: str, pin_step: str, gate_step: str):
    cfg = yaml.safe_load(path.read_text())
    by = {st["id"]: st for st in cfg["steps"]}
    assert by[mutate_step].get("allowFailure") is True, f"{path.name}: {mutate_step} must not stop the pin"
    body = _all_args(by[mutate_step])
    assert "/workspace/apply.rc" in body and "echo 0 > /workspace/apply.rc" in body, body
    assert by[pin_step]["waitFor"] == [mutate_step] and "pin-images --no-sweep" in _all_args(by[pin_step])
    gate = _all_args(by[gate_step])
    assert "/workspace/apply.rc" in gate and "exit" in gate, gate


def test_the_trigger_pins_the_job_digest_even_when_the_apply_fails():
    """A failed `jobs execute` after a successful `jobs update` leaves the job
    on a digest only :latest keeps alive. The manual path pins whatever the
    build's outcome; the trigger's pin step was skipped by the failure
    (internal review of #1022, schema-apply round). The apply step now
    records its exit code, the pin runs regardless, and a final step fails
    the build with that code."""
    _pins_on_failure(CFG, "apply", "pin", "verify")


def test_the_staging_trigger_pins_the_job_digest_even_when_migrate_fails():
    staging = REPO / "gcp/cloudbuild/deploy-solyra-api-staging-cloudbuild.yaml"
    _pins_on_failure(staging, "migrate", "pin-job", "deploy")
    cfg = yaml.safe_load(staging.read_text())
    ids = [st["id"] for st in cfg["steps"]]
    assert ids == ["preflight", "build", "push", "migrate", "pin-job", "deploy", "pin"], ids
    by = {st["id"]: st for st in cfg["steps"]}
    deploy = _all_args(by["deploy"])
    assert deploy.index("/workspace/apply.rc") < deploy.index("gcloud run deploy"), \
        "deploy must refuse before deploying when the migrate step failed"



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
    assert 'TAGS="${TAGS:-apply-schema-on-change solyra-api-staging-deploy}"' in src
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
    # Measured 2026-09-07 (build e4be0456): ~90 s pass between the apply
    # step starting and the Cloud Run execution starting (image pull,
    # digest describe, git deepen, jobs update, provisioning), before the
    # job's own 1800 s budget; then deploy and pin.
    assert reserve >= _apply_job_task_timeout() + 90 + 300 + 200, \
        "the reserve must cover the preamble, the apply job's timeout and the deploy/pin steps"
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
    assert "timeout: 7200s" in body
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
    # Captured from gcloud 583.0.0 on 2026-09-07 (internal review of #1022,
    # schema-apply round): `jobs describe` says "Cannot find job [x].",
    # `jobs update` says "Job [x] could not be found." Neither contains
    # "not found", which is the only phrase the first version matched, so
    # the bootstrap could never create the job and `all)` died at it.
    for stderr in ("ERROR: (gcloud.run.jobs.describe) Cannot find job [apply-schema-migrations].",
                   "ERROR: (gcloud.run.jobs.update) Job [apply-schema-migrations] could not be found.",
                   "ERROR: (gcloud.run.jobs.describe) NOT_FOUND: Job [apply-schema-migrations] not found."):
        (tmp_path / "calls").write_text("")
        env.update(DESCRIBE_RC="1", DESCRIBE_STDERR=stderr)
        r = _run_fn(tmp_path, env, "deploy_apply_schema_migrations")
        calls = (tmp_path / "calls").read_text()
        assert "run jobs create apply-schema-migrations" in calls and "rc=0" in r.stdout, \
            (stderr, r.stdout + r.stderr)
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
    assert cfg["tags"] == ["apply-schema-on-change"] and cfg["timeout"] == "7200s"
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
    assert "--timeout=7200s" in calls, "the submit must not depend on the operator's builds/timeout property"
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


def test_manual_apply_off_main_records_head_and_forces_the_guard(tmp_path):
    """Seen in production (build e4be0456, 2026-09-07): off main the manual
    apply recorded the merge-base, an OLD main commit, and once the newest
    applied row was newer than that the guard refused it as an ancestor.
    There was no override, so the documented break-glass path was unusable
    from a branch (internal review of #1022, schema-apply round). Off main
    the real HEAD is recorded, the guard's ordering check is bypassed with
    --force-revision, and the row is marked forced."""
    env = _bash_env(tmp_path, _GCLOUD_OK, _GIT_ON_MAIN)
    env["OFF_MAIN"] = "1"
    r = _run_fn(tmp_path, env, "apply_schema_via_build")
    assert "rc=0" in r.stdout, r.stdout + r.stderr
    rendered = (tmp_path / "rendered.yaml").read_text()
    assert "--revision=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa," in rendered
    assert "--revision=bbbbbbbb" not in rendered
    assert ",--force-revision" in rendered
    assert "not on origin/main" in r.stderr and "forced" in r.stderr.lower()
    env["OFF_MAIN"] = "0"
    r = _run_fn(tmp_path, env, "apply_schema_via_build")
    assert "--force-revision" not in (tmp_path / "rendered.yaml").read_text(), "on main the guard is not bypassed"


def test_serialized_apply_reports_the_build_exit_code_when_the_pin_also_fails(tmp_path):
    """`pin_image_tags || return 1` returned before the build's own exit code
    could, so a failed apply plus a failed pin reported 1 and lost the
    diagnostic (internal review of #1022, schema-apply round)."""
    env = _bash_env(tmp_path, _GCLOUD_OK, _GIT_ON_MAIN)
    env["SUBMIT_RC"] = "3"
    r = _run_fn(tmp_path, env, 'pin_image_tags() { echo PINNED >> "$OUT/calls"; return 1; }; apply_schema_via_build')
    assert "rc=3" in r.stdout, r.stdout + r.stderr
    assert "PINNED" in (tmp_path / "calls").read_text()


def test_serialized_apply_submits_in_the_global_region(tmp_path):
    """The serializer inside the build describes and lists builds without
    --region, i.e. global; a builds/region property on the operator's
    machine would submit the build regionally, where its own describe cannot
    find it and the wait fails closed. --timeout is already pinned for the
    same reason."""
    env = _bash_env(tmp_path, _GCLOUD_OK, _GIT_ON_MAIN)
    r = _run_fn(tmp_path, env, "apply_schema_via_build")
    assert "rc=0" in r.stdout, r.stdout + r.stderr
    calls = (tmp_path / "calls").read_text()
    submit = next(ln for ln in calls.splitlines() if ln.startswith("builds submit"))
    assert "--region=global" in submit, submit


def test_secret_helpers_fail_loud_instead_of_defaulting(tmp_path):
    """apply_schema_via_build writes the job's ENTIRE env and secret set
    through `_env_string` and `_build_secret_flag`, and both degraded
    silently: `_secret` echoed '' on any read failure (an auth blip would
    have set CLOUD_SQL_CONNECTION_NAME= on the live job and every later
    apply exited 2), and `_build_secret_flag` dropped a secret on ANY
    describe error, not only NOT_FOUND (internal review of #1022,
    schema-apply round; CLAUDE.md 3.7)."""
    # The probe is `versions access`, the one call roles/secretmanager.
    # secretAccessor (trading-runner@) permits; `secrets describe` needs
    # secrets.get, which it lacks. Captured 2026-09-07: a missing secret
    # answers "NOT_FOUND: Secret [...] not found or has no versions."
    gcloud = """
    echo "$*" >> "$OUT/calls"
    case "$1 $2 $3" in
      "secrets versions access")
        secret=""; for a in "$@"; do case "$a" in --secret=*) secret="${a#--secret=}" ;; esac; done
        if [ "$secret" = "${PROBE_SECRET:-}" ]; then echo "${PROBE_STDERR:-}" >&2; exit "${PROBE_RC:-0}"; fi
        if [ "${ACCESS_RC:-0}" = 0 ]; then echo "value-of-$secret"; fi; exit "${ACCESS_RC:-0}" ;;
    esac
    exit 0
    """
    env = _bash_env(tmp_path, gcloud)
    defs = "\n".join(f"{n}() {{{_fn(n)}}}" for n in ("_secret", "_optional_secret_pair", "_build_secret_flag"))
    def run(call):
        script = f'set -uo pipefail\nPROJECT_ID=proj\n{defs}\n{call}\n'
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, cwd=str(REPO))
    probe = 'if v=$(_secret db-trading-user); then echo "got=$v"; else echo "failed=$?"; fi'
    r = run(probe)
    assert "got=value-of-db-trading-user" in r.stdout, r.stdout + r.stderr
    env["ACCESS_RC"] = "1"
    r = run(probe)
    assert "failed=1" in r.stdout and "got=" not in r.stdout, r.stdout + r.stderr
    assert "cannot read secret" in r.stderr.lower()
    env["ACCESS_RC"] = "0"
    env.update(PROBE_SECRET="fred-api-key", PROBE_RC="1",
               PROBE_STDERR="ERROR: (gcloud.secrets.versions.access) NOT_FOUND: Secret [projects/1/secrets/fred-api-key] not found or has no versions.")
    r = run('_build_secret_flag; echo "rc=$?"')
    assert "rc=0" in r.stdout and "FRED_API_KEY" not in r.stdout and "skipping FRED_API_KEY" in r.stderr, r.stdout + r.stderr
    assert "BENZINGA_API_KEY=benzinga-api-key:latest" in r.stdout, "the other optional secrets are still added"
    env.update(PROBE_STDERR="ERROR: (gcloud.secrets.versions.access) PERMISSION_DENIED: quota")
    r = run('_build_secret_flag; echo "rc=$?"')
    assert "rc=1" in r.stdout and "--set-secrets" not in r.stdout, r.stdout + r.stderr
    assert "cannot tell" in r.stderr.lower()
    assert "secrets describe" not in (tmp_path / "calls").read_text(), "the deploy SA cannot describe secrets"


def test_pin_images_does_not_resolve_the_secret_set():
    """pin-images runs inside the trigger builds as trading-runner@ and needs
    no job declaration; every subcommand that deploys something resolves the
    secret set at start-up so a read failure aborts before any mutation.

    The exemption is matched by label rather than by the literal case line:
    `setup` and the other bootstraps joined it on #1022, and the complete
    list is checked against what each target actually uses in
    tests/gcp/test_deploy_reachability.py."""
    import re

    src = (REPO / "gcp/deploy.sh").read_text()
    top = src[:src.index("_env_string() {")]
    m = re.search(r'\n\s*([^)\n]+(?:\\\n[^)\n]+)*)\)\s*DB_SECRET_FLAG="" ;;', top)
    assert m, "the DB_SECRET_FLAG exemption arm is gone"
    exempt = {lbl.strip().strip('"')
              for lbl in m.group(1).replace("\\", " ").replace("\n", " ").split("|")}
    assert "pin-images" in exempt
    assert '*) DB_SECRET_FLAG="$(_build_secret_flag)" ;;' in top


def test_the_staging_trigger_waits_for_earlier_deploys_instead_of_refusing():
    """Internal review of #1022 (schema-apply round): the staging preflight
    REFUSED on any ongoing staging build while its migrate step WAITED on
    earlier schema builds, so with two pushes minutes apart the second
    staging build died at preflight, the second schema build applied its
    schema, and staging served push 1's code against push 2's schema. The
    trigger now waits (bounded by its own build budget) for every earlier
    build of any of the three tags; the operator path keeps refusing."""
    staging = yaml.safe_load((REPO / "gcp/cloudbuild/deploy-solyra-api-staging-cloudbuild.yaml").read_text())
    first = _all_args(staging["steps"][0])
    assert "wait_for_earlier_schema_builds.sh" in first
    assert 'TAGS="apply-schema-on-change solyra-api-staging-deploy solyra-api-image-build"' in first
    assert "assert_no_concurrent_staging_deploy.sh" not in first
    platform_cfg = yaml.safe_load((REPO / "platform/cloudbuild.yaml").read_text())
    assert "assert_no_concurrent_staging_deploy.sh" in _all_args(platform_cfg["steps"][0])


def _wait_script_env(tmp_path, ongoing_lists: list[str]) -> dict:
    """Stub gcloud: each `builds list` call pops the next entry of ongoing_lists."""
    (tmp_path / "n").write_text("0")
    lists = tmp_path / "lists"
    lists.write_text("\n".join(ongoing_lists) + "\n")
    gcloud = f"""
    echo "$*" >> "$OUT/calls"
    if [ "$1 $2" = "builds list" ]; then
      n=$(cat "$OUT/n"); echo $((n+1)) > "$OUT/n"
      sed -n "$((n+1))p" "$OUT/lists" | tr ',' '\\n'
      exit 0
    fi
    exit 0
    """
    return _bash_env(tmp_path, gcloud)


def test_the_wait_script_has_an_external_mode_for_a_runner_that_is_not_a_build(tmp_path):
    """.github/workflows/deploy-staging.yml applies the schema from a GitHub
    runner, which is not a Cloud Build and so cannot be ordered by
    createTime or budgeted by a build timeout. In external mode the script
    waits for EVERY ongoing tagged build under a caller-supplied budget, and
    refuses without one."""
    env = _wait_script_env(tmp_path, ["b1", "", "", ""])
    env["POLL_SECONDS"] = "0"
    r = subprocess.run(["bash", str(WAIT), "--external"], capture_output=True, text=True, env=env)
    assert r.returncode == 2 and "WAIT_BUDGET_SECONDS" in r.stderr, r.stdout + r.stderr
    env["WAIT_BUDGET_SECONDS"] = "60"
    r = subprocess.run(["bash", str(WAIT), "--external"], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    calls = (pathlib.Path(env["OUT"]) / "calls").read_text()
    assert "builds describe" not in calls, "a runner has no build to describe"
    assert "createTime<" not in calls, "external mode waits for every ongoing tagged build"
    assert "waiting" in r.stdout and "proceeding" in r.stdout


def test_the_workflow_apply_passes_the_guard_and_waits_for_builds():
    """The GHA deploy-staging path ran `python -m gcp.apply_schema` bare:
    outside the serializer and outside the revision guard, so it recorded
    nothing in schema_apply_history and the guard's "last row is the schema
    in force" contract was false right after it (internal review of #1022,
    schema-apply round)."""
    wf = yaml.safe_load((REPO / ".github/workflows/deploy-staging.yml").read_text())
    steps = wf["jobs"]["deploy"]["steps"]
    checkout = next(st for st in steps if str(st.get("uses", "")).startswith("actions/checkout"))
    assert checkout.get("with", {}).get("fetch-depth") == 100, "the guard's ancestry needs history"
    apply = next(st for st in steps if st.get("id") == "apply")
    run = apply["run"]
    assert "wait_for_earlier_schema_builds.sh --external" in run
    assert "WAIT_BUDGET_SECONDS" in run
    for flag in ("--revision=", "--revision-time=", "--revision-ancestors="):
        assert flag in run, flag
    assert "git rev-list --max-count=100" in run
