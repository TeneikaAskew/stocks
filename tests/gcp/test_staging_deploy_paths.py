"""The two paths that deploy `solyra-api-staging` must not be able to interleave.

`solyra-api-staging` is deployed by two things that cannot see each other: the
`deploy-solyra-api-staging` Cloud Build trigger on push to main, and
`.github/workflows/deploy-staging.yml` (dispatched, running
`platform/deploy.sh` -> `gcloud builds submit platform/cloudbuild.yaml`). The
workflow's `concurrency: deploy-staging` group serialises the workflow against
ITSELF and has no reach over a Cloud Build run (Codex, PR #990).

Both paths used to build, push and deploy the bare image -- `:latest`, a
mutable pointer both of them write. Two overlapping runs could push over each
other between one run's push and its deploy, so `gcloud run deploy --image
...:latest` resolved to an image that run never built. The promote trigger
deliberately promotes whatever digest is serving staging, so a mutable tag put
an unvalidated image one click from production.

These are config invariants, not behaviour, so they are asserted by reading the
files. A live deploy is the only thing that proves the mechanism, and that
cannot go in a unit suite -- what CAN go here is that nobody quietly puts the
mutable tag back.
"""
import pathlib

import pytest

yaml = pytest.importorskip("yaml")

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
TRIGGER = REPO / "gcp/cloudbuild/deploy-solyra-api-staging-cloudbuild.yaml"
PLATFORM = REPO / "platform/cloudbuild.yaml"
DEPLOY_SH = REPO / "platform/deploy.sh"
INTERLOCK = REPO / "gcp/cloudbuild/assert_no_concurrent_staging_deploy.sh"
WORKFLOW = REPO / ".github/workflows/deploy-staging.yml"


def _steps(path):
    return yaml.safe_load(path.read_text())["steps"]


def _all_args(step) -> str:
    return " ".join(str(a) for a in step.get("args", []))


def test_the_trigger_builds_an_immutable_tag():
    build = next(s for s in _steps(TRIGGER) if s["id"] == "build")
    args = _all_args(build)
    assert "${_IMAGE}:${SHORT_SHA}" in args, args
    assert "--tag ${_IMAGE} " not in args, "the bare (mutable :latest) tag is back"


def test_the_trigger_deploys_a_digest_not_a_tag():
    deploy = next(s for s in _steps(TRIGGER) if s["id"] == "deploy")
    args = _all_args(deploy)
    assert "fully_qualified_digest" in args, (
        "the deploy must resolve the tag to a sha256 digest, so the revision is "
        "pinned to the artifact this build produced")
    assert "--image=${_IMAGE}" not in args, "deploying a mutable tag again"


def test_the_platform_config_requires_an_explicit_tag():
    cfg = yaml.safe_load(PLATFORM.read_text())
    assert cfg["images"] == ["${_IMAGE}:${_TAG}"], cfg["images"]


def test_deploy_sh_deploys_a_digest():
    src = DEPLOY_SH.read_text()
    assert "fully_qualified_digest" in src
    assert '--image "${IMAGE_DIGEST}"' in src, "deploy.sh is not deploying the digest"
    assert '--image "${IMAGE}"' not in src, "the mutable tag is back in deploy.sh"
    assert "_TAG=${IMAGE_TAG}" in src, "the build no longer passes an immutable tag"


def test_both_paths_run_the_interlock():
    """Each path checks for the other before building."""
    trigger_first = _steps(TRIGGER)[0]
    assert "assert_no_concurrent_staging_deploy.sh" in _all_args(trigger_first), (
        "the trigger must check for a concurrent deploy in its FIRST step, "
        f"got {trigger_first['id']!r}")
    src = DEPLOY_SH.read_text()
    assert "assert_no_concurrent_staging_deploy.sh" in src
    assert 'if [[ "${STAGING_SERVICE:-0}" == "1" ]]; then\n  bash' in src, (
        "the interlock must be gated on STAGING_SERVICE (which deploys "
        "solyra-api-staging), not STAGING (the legacy revision-tag mode on prod)")


def test_the_interlock_scans_both_build_tags():
    """`gcloud builds submit` has no flag for build tags, so each path's tag
    lives in its own config and they differ. Scanning for only one would leave
    the visibility one-way, which is the same gap in a new place."""
    src = INTERLOCK.read_text()
    trigger_tags = yaml.safe_load(TRIGGER.read_text())["tags"]
    platform_tags = yaml.safe_load(PLATFORM.read_text())["tags"]
    for tag in trigger_tags + platform_tags:
        assert tag in src, f"the interlock does not scan for `{tag}`"


def test_the_interlock_excludes_its_own_build():
    """It runs INSIDE one of the builds it is scanning for."""
    assert '[ "${id}" = "${SELF}" ]' in INTERLOCK.read_text()


def test_the_workflow_concurrency_group_is_documented_as_insufficient():
    """The group is still right and still not enough; a reader who thinks it
    covers the Cloud Build path will delete the interlock."""
    src = WORKFLOW.read_text()
    assert "group: deploy-staging" in src
    assert "assert_no_concurrent_staging_deploy.sh" in src, (
        "the concurrency block must say what actually serialises the two paths")
