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
PROMOTE = REPO / "gcp/cloudbuild/deploy-solyra-api-prod-cloudbuild.yaml"
SERVING = REPO / "gcp/cloudbuild/serving_revision.py"


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


# ── the gap between the build and the deploy ────────────────────────────────
#
# Moving the interlock inside platform/cloudbuild.yaml made the IMAGE BUILD
# visible to a peer. The manual `gcloud run deploy` runs AFTER that build has
# finished, so a trigger starting in the gap sees no ongoing build, deploys,
# and is then overwritten by the older invocation finishing last (Codex,
# PR #990).

def _deploy_sh_order(*needles):
    """Offset of each needle in platform/deploy.sh.

    The LAST occurrence, deliberately: the interlock is called twice, and it is
    the second call -- the one after the build -- this file is asserting about.
    """
    text = DEPLOY_SH.read_text()
    at = []
    for n in needles:
        assert n in text, f"platform/deploy.sh no longer contains {n!r}"
        at.append(text.rindex(n))
    return at


def test_the_interlock_is_re_asserted_before_the_manual_deploy():
    submit, recheck, deploy = _deploy_sh_order(
        "gcloud builds submit",
        "assert_no_concurrent_staging_deploy.sh",
        "gcloud run deploy ",
    )
    assert submit < recheck < deploy, (
        "the interlock must run again between the build and the deploy; "
        "the pre-submit call alone leaves the deploy unguarded")


def test_the_deploy_refuses_a_service_that_moved_under_it():
    baseline, submit, compare, deploy = _deploy_sh_order(
        "DEPLOY_BASELINE=",
        "gcloud builds submit",
        "DEPLOY_NOW=",
        "gcloud run deploy ",
    )
    assert baseline < submit < compare < deploy, (
        "the serving state must be read before the build and compared "
        "after it, or the comparison proves nothing")
    assert 'if [[ "${DEPLOY_NOW}" != "${DEPLOY_BASELINE}" ]]' in \
        DEPLOY_SH.read_text()


def test_an_absent_service_is_a_baseline_state_not_an_empty_string():
    """First creation is raced too, and an empty baseline did not guard it.

    The previous fix compared revisions only when the baseline was non-empty,
    so the create path -- where there is no revision to name -- skipped the
    comparison entirely. A peer that created and deployed the service while
    this build ran was then overwritten by this older invocation, which is the
    same overwrite the compare-and-swap exists to refuse (Codex, PR #990).
    """
    text = DEPLOY_SH.read_text()
    assert "printf 'absent" in text, (
        "absence must be a value the comparison can hold, not the empty string")
    assert text.count("describe_deploy_state)") == 2, (
        "the state must be read once before the build and once after it, "
        "through the same reader, or the two are not comparable")
    assert '-n "${DEPLOY_BASELINE' not in text, (
        "a non-empty test in front of the comparison skips the create path")


def test_the_manual_deploy_pins_the_digest_it_made_current():
    """The pre-build pin tags the revision this run REPLACES, not the new one.

    `pin-images` runs before the build, when the digest being deployed does not
    exist in the service inventory yet, so it comes out of that sweep with no
    `inuse-svc-*` tag. Against the 30-day delete rule this PR adds to the
    gcr.io cleanup policy, an unpinned digest is deletable while it is still
    the serving revision (Codex, PR #990).
    """
    text = DEPLOY_SH.read_text()
    call = "./gcp/deploy.sh pin-images"
    assert text.count(call) == 2, (
        "pin before the build and again after the deploy lands")
    assert text.rindex(call) > text.index("gcloud run deploy "), (
        "the deployed digest is only in the inventory after the deploy")


def test_both_deploy_paths_resolve_the_serving_revision_the_same_way():
    """One implementation, two callers — a second copy would drift silently."""
    assert SERVING.exists()
    assert "serving_revision.py" in DEPLOY_SH.read_text()
    assert "serving_revision.py" in PROMOTE.read_text()
    body = _all_args(_promote_step(yaml.safe_load(PROMOTE.read_text())))
    assert "latestReadyRevisionName" not in body, (
        "the promote config must not resolve the revision itself")
    assert "traffic" not in body


def _promote_step(cfg):
    """The step that deploys, not the interlock that now precedes it."""
    return next(s for s in cfg["steps"] if s.get("id") == "promote")


def test_promotion_requires_the_revision_the_operator_validated():
    cfg = yaml.safe_load(PROMOTE.read_text())
    assert "_EXPECT_STAGING_REVISION" in cfg.get("substitutions", {})
    body = _all_args(_promote_step(cfg))
    assert 'if [ -z "$$EXPECT" ]' in body, (
        "an absent expectation must abort; resolving the serving revision at "
        "run time answers a different question than what was validated")
    assert 'if [ "$$EXPECT" != "$$REV" ] && [ "$$EXPECT" != "$$DIGEST" ]' in body
    assert body.index('if [ -z "$$EXPECT" ]') < body.index("gcloud run deploy")


def test_the_baseline_read_fails_closed():
    """An unreadable service is not an absent one.

    `2>/dev/null` plus a bare `else` treated every nonzero exit as "does not
    exist", so a transient API error or an expired credential left the
    baseline empty and silently skipped the compare-and-swap (Codex, PR #990).
    """
    text = DEPLOY_SH.read_text()
    assert "NOT_FOUND" in text, (
        "only an explicit not-found may be treated as the create case")
    start = text.index("describe_deploy_state() {")
    body = text[start:text.index("\n}\n", start)]
    assert "2>/dev/null" not in body, (
        "the describe error is needed to tell not-found from a real failure")
    assert "return 1" in body, "an unreadable service must stop the deploy"
    assert "set -e" in text[:text.index("describe_deploy_state() {")], (
        "the caller assigns the state, so `set -e` is what turns the "
        "function's failure into a stopped deploy")


def test_both_triggers_pin_what_they_deployed():
    """The cleanup policy expires build tags, so the running digest needs one.

    Every qualifying push leaves a `solyra-api:<short sha>` tag; nothing
    removed them and the policy kept every tagged version, so the repository
    grew without bound (Codex, PR #990). Expiring them is only safe while the
    digests in use carry an `inuse-*` tag.
    """
    for path in (TRIGGER, PROMOTE):
        body = "\n".join(_all_args(step) for step in _steps(path))
        assert "pin-images --no-sweep" in body, (
            f"{path.name} deploys without pinning the digest it deployed")
        assert body.index("gcloud run deploy") < body.rindex("pin-images"), (
            f"{path.name} pins before it deploys, which pins the wrong digest")


def test_the_cleanup_policy_expires_build_tags_but_keeps_pins():
    text = REPO.joinpath("gcp/deploy.sh").read_text()
    # The gcr.io policy only. The `trading` repo holds the Jobs image, whose
    # tags are job names rather than one per commit, so keep-tagged is right
    # there and wrong here.
    opener = 'cat > "${gcr_policy}" <<\'EOF\'\n'
    gcr = text[text.index(opener) + len(opener):]
    gcr = gcr[:gcr.index("\nEOF")]
    assert '"delete-old-solyra-api-build-tags"' in gcr
    assert '"keep-in-use-and-latest"' in gcr
    assert '"tagPrefixes": ["inuse-", "latest"]' in gcr
    assert '"name": "keep-tagged"' not in gcr, (
        "a blanket keep-tagged rule is what let the build tags accumulate")


def test_two_prod_promotions_cannot_overlap():
    """The one that finishes last wins, which can roll prod backwards.

    Promotion A (validated revision A) and promotion B (validated later) can
    both pass their expectation checks; without an interlock both reach
    `gcloud run deploy` and the older one can land after the newer
    (Codex, PR #990).
    """
    cfg = yaml.safe_load(PROMOTE.read_text())
    assert "solyra-api-prod-promote" in cfg.get("tags", []), (
        "a promotion can only see a peer through a tag in this file")
    ids = [s.get("id") for s in cfg["steps"]]
    assert ids[0] == "no-concurrent-promote", (
        "the interlock must be the first step, so the build is registered and "
        "tagged before the scan")
    body = _all_args(cfg["steps"][0])
    assert "|| true" not in "\n".join(
        l for l in body.splitlines() if not l.strip().startswith("#")), (
        "the scan must fail closed: an unlistable peer is not an absent one")


def test_the_promotion_refuses_when_prod_moved():
    body = "\n".join(_all_args(s) for s in _steps(PROMOTE))
    assert "PROD_BEFORE" in body and "PROD_NOW" in body
    assert body.index("PROD_BEFORE=") < body.index("gcloud run deploy"), (
        "the baseline must be read before the deploy it guards")


def test_the_staging_trigger_filter_gap_is_recorded():
    """The image copies scripts/ and gcp/; the trigger filter does not.

    Trigger configuration is not repository content, so this file cannot carry
    the fix -- it carries the command and the reason (Codex, PR #990).
    """
    header = TRIGGER.read_text().split("steps:")[0]
    assert "includedFiles" in header
    assert "scripts/**" in header and "gcp/**" in header
    assert "gcloud builds triggers update github deploy-solyra-api-staging" in header
