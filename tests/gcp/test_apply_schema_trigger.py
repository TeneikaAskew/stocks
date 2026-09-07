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
    assert "--ongoing" in src and "createTime<'${self_start}'" in src, \
        "must wait only on builds that started earlier (total order, no deadlock)"
    code = [ln for ln in src.splitlines() if not ln.lstrip().startswith("#")]
    assert not any("|| true" in ln for ln in code), "the guard must fail closed"
    assert src.count("exit 1") >= 3, "cannot-describe, cannot-list and deadline all fail"
    deadline = int(src.split('DEADLINE_SECONDS:-')[1].split('}')[0])
    assert deadline < int(str(cfg["timeout"]).rstrip("s")), "the wait must end before the build times out"


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
