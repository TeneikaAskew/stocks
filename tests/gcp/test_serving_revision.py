"""`serving_revision.py` reads the TRAFFIC TARGET, never latest-ready.

Those differ exactly when it matters: after a rollback, during a split, and
after a `--no-traffic` deploy. In each case latest-ready is the revision
nobody validated (Codex, PR #990).
"""
import importlib.util
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "serving_revision", REPO / "gcp/cloudbuild/serving_revision.py")
sr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sr)


def _svc(traffic, latest="r-NEW"):
    return {"status": {"traffic": traffic, "latestReadyRevisionName": latest}}


def test_a_rollback_returns_the_serving_revision_not_the_latest():
    got = sr.serving_revision(_svc([{"revisionName": "r-OLD", "percent": 100},
                                    {"revisionName": "r-NEW", "percent": 0}]))
    assert got == "r-OLD"


def test_no_traffic_deploy_leaves_the_previous_revision_serving():
    got = sr.serving_revision(_svc([{"revisionName": "r-OLD", "percent": 100}]))
    assert got == "r-OLD"


def test_nothing_serving_is_fatal_not_a_guess():
    with pytest.raises(SystemExit) as e:
        sr.serving_revision(_svc([{"revisionName": "r-NEW", "percent": 0}]))
    assert "nothing validated" in str(e.value)


def test_a_split_is_fatal_and_names_both_revisions():
    with pytest.raises(SystemExit) as e:
        sr.serving_revision(_svc([{"revisionName": "r-A", "percent": 60},
                                  {"revisionName": "r-B", "percent": 40}]))
    assert "r-A=60%" in str(e.value) and "r-B=40%" in str(e.value)


def test_a_traffic_target_with_no_revision_name_falls_back_then_fails():
    assert sr.serving_revision(_svc([{"percent": 100}])) == "r-NEW"
    with pytest.raises(SystemExit):
        sr.serving_revision({"status": {"traffic": [{"percent": 100}]}})
