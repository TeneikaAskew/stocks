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


def test_the_pipeline_order_is_preflight_build_push_apply_pin():
    ids = [s["id"] for s in _steps()]
    assert ids == ["preflight", "build", "push", "apply", "pin"], ids
    assert "SHORT_SHA" in _all_args(_step("preflight")), "refuse a nameless tag"


def test_the_image_is_the_trading_system_repo_not_the_api_image():
    subs = yaml.safe_load(CFG.read_text())["substitutions"]
    assert subs["_IMAGE"].endswith("/trading/trading-system"), subs
