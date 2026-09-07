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


def test_both_paths_run_the_interlock_inside_their_build():
    """The check has to run in the SUBMITTED build, not before it.

    platform/deploy.sh ran it before `gcloud builds submit`, so its build did
    not exist yet and carried no tag — a trigger starting in that window saw
    only itself and both paths deployed (Codex, PR #990). Running it as the
    first step of each config means the build is registered and tagged when
    the scan happens.
    """
    for cfg in (TRIGGER, PLATFORM):
        first = _steps(cfg)[0]
        assert "assert_no_concurrent_staging_deploy.sh" in _all_args(first), (
            f"{cfg.name}: the interlock must be the FIRST build step, got "
            f"{first.get('id', '<unnamed>')!r}")


def test_the_pre_submit_check_is_not_presented_as_the_interlock():
    """deploy.sh keeps a fast-fail courtesy check so an operator finds out
    before uploading a tarball. It must not be described as the guard, or the
    in-build step looks redundant and gets deleted."""
    src = DEPLOY_SH.read_text()
    assert "assert_no_concurrent_staging_deploy.sh" in src
    assert "authoritative check is the first step of platform/cloudbuild.yaml" in src, (
        "the comment must say which check is load-bearing")
    assert 'if [[ "${STAGING_SERVICE:-0}" == "1" ]]; then' in src, (
        "gated on STAGING_SERVICE (which deploys solyra-api-staging), not "
        "STAGING (the legacy revision-tag mode on prod)")


def test_the_interlock_fails_closed_when_it_cannot_look():
    """A guard that cannot check must stop, not reassure.

    `|| true` turned a revoked cloudbuild.builds.list, an expired credential
    or a transient API error into an empty result — so in exactly the
    environment where peer builds are invisible, it announced there were none
    (Codex, PR #990).
    """
    src = INTERLOCK.read_text()
    # Non-comment lines only: the fix's own comment quotes `|| true` to say
    # what it replaced, and a substring check on the whole file would call
    # that a regression.
    code = [ln for ln in src.splitlines() if not ln.lstrip().startswith("#")]
    assert not any("|| true" in ln for ln in code), (
        "the build scan swallows its own failure again:\n"
        + "\n".join(ln for ln in code if "|| true" in ln))
    assert "Refusing rather than assuming none" in src
    assert src.count("exit 1") >= 2, (
        "expected an exit for the unreadable-listing case as well as for a "
        "detected concurrent build")


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
