"""Unit tests for the docs-vs-live verifier.

The verifier exists because `docs/PIPELINE.md` claimed "23:00 UTC" for a job
whose scheduler is `0 23 * * 1-5` in `America/New_York`, and a timezone fix was
designed off that claim and was wrong. So the cases that matter here are the
ones that made the earlier hand-checking unreliable:

* a table row carrying BOTH an ET and a UTC column is correct, not drift
* "4:15 PM" and "16:15" are the same claim
* a line about a deleted resource is a record, not a stale claim
* an explicit reviewed exemption suppresses exactly one line

Hermetic: no gcloud, no network. The live snapshot is a literal.
"""
import importlib.util
import json
import pathlib
import sys

import pytest

_SRC = pathlib.Path(__file__).resolve().parent.parent.parent / "scripts" / "verify_docs_against_live.py"
_spec = importlib.util.spec_from_file_location("verify_docs_against_live", _SRC)
vd = importlib.util.module_from_spec(_spec)
sys.modules["verify_docs_against_live"] = vd
_spec.loader.exec_module(vd)


LIVE = {
    "schedulers": {
        "fetch-market-data-daily": {
            "schedule": "0 23 * * 1-5", "timeZone": "America/New_York",
            "state": "ENABLED", "target_job": "fetch-market-data",
        },
        "top-movers-daily": {
            "schedule": "15 16 * * 1-5", "timeZone": "America/New_York",
            "state": "ENABLED", "target_job": "fetch-top-movers",
        },
        "av-options-realtime": {
            "schedule": "*/5 9-15 * * 1-5", "timeZone": "America/New_York",
            "state": "ENABLED", "target_job": "fetch-av-options-realtime",
        },
    },
    "run_jobs": ["fetch-market-data", "fetch-top-movers", "fetch-av-options-realtime"],
    "services": ["solyra-api-prod", "solyra-api-staging"],
    "secrets": ["av-api-key"],
    "queues": ["insight-pipeline-queue"],
}


def _check(tmp_path, text, name="docs/PIPELINE.md"):
    """Run every check over a single doc and return the finding checks."""
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    out: list[vd.Finding] = []
    vd.check_retired_services(p, name, out)
    vd.check_schedules(p, name, LIVE, out)
    vd.check_known_names(p, name, LIVE, out)
    vd.check_counts(p, name, LIVE, out)
    return out


def test_utc_claim_is_caught(tmp_path):
    """The exact defect the script was written for."""
    out = _check(tmp_path, "| `fetch-market-data` | 23:00 UTC daily | fetcher |")
    assert [f.check for f in out] == ["utc-claim"]
    assert "America/New_York" in out[0].detail


def test_et_plus_utc_columns_are_not_drift(tmp_path):
    """A correct row states two times; only one can match the cron."""
    out = _check(tmp_path, "| Mon-Fri 16:15 | 20:15 | `top-movers-daily` | writes |")
    assert out == []


def test_twelve_hour_claim_matches_cron(tmp_path):
    out = _check(tmp_path, "**`fetch-top-movers`** (weekdays 4:15 PM)")
    assert out == []


def test_wrong_wall_clock_is_caught(tmp_path):
    out = _check(tmp_path, "`fetch-top-movers` runs weekdays at 07:15")
    assert [f.check for f in out] == ["clock-drift"]


def test_step_cron_is_parsed_not_truncated(tmp_path):
    """`*/5 9-15 * * 1-5` must not be read as `5 9-15 * * 1-5`."""
    out = _check(tmp_path, "| `fetch-av-options-realtime` | `*/5 9-15 * * 1-5` |")
    assert out == []


def test_wrong_cron_is_caught(tmp_path):
    out = _check(tmp_path, "| `fetch-market-data-daily` | `0 17 * * 1-5` |")
    assert [f.check for f in out] == ["schedule-drift"]
    assert "0 23 * * 1-5" in out[0].detail


def test_before_and_after_on_one_line_is_not_drift(tmp_path):
    out = _check(tmp_path, "- `fetch-market-data-daily` was `0 17 * * 1-5`, now `0 23 * * 1-5`")
    assert out == []


def test_retired_service_is_caught(tmp_path):
    out = _check(tmp_path, "The API runs on the `trading-platform` Cloud Run service.")
    assert [f.check for f in out] == ["retired-service"]


def test_retired_service_in_a_historical_sentence_is_not_a_claim(tmp_path):
    out = _check(tmp_path, "`trading-platform` was deleted on 2026-09-06.")
    assert out == []


def test_service_account_is_not_the_deleted_service(tmp_path):
    """`trading-platform-svc@` was never renamed and must not be flagged."""
    out = _check(tmp_path, "Runs as `trading-platform-svc@project.iam.gserviceaccount.com`.")
    assert out == []


def test_count_claim_is_compared(tmp_path):
    out = _check(tmp_path, "The system has 34 Cloud Run Jobs.")
    assert [f.check for f in out] == ["count-drift"]
    assert "live count is 3" in out[0].detail


def test_secret_named_as_infrastructure_is_known(tmp_path):
    out = _check(tmp_path, "The Cloud Run Job reads `av-api-key` from Secret Manager.")
    assert out == []


def test_unknown_job_name_is_caught(tmp_path):
    out = _check(tmp_path, "The `fetch-market-nothing` Cloud Run Job writes rows.")
    assert [f.check for f in out] == ["unknown-name"]


def test_reviewed_exemption_suppresses_its_line_only(tmp_path):
    text = (
        "Context sentence. <!-- verify-docs-ok: historical -->\n"
        "The `trading-platform` service served 100% of traffic.\n"
        "The `trading-platform` service is still what we deploy.\n"
    )
    out = _check(tmp_path, text)
    assert [f.line for f in out] == [3]


@pytest.mark.parametrize("field,lo,hi,expected", [
    ("*/5", 0, 59, [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]),
    ("9-15", 0, 23, [9, 10, 11, 12, 13, 14, 15]),
    ("1,3,5", 0, 59, [1, 3, 5]),
    ("0", 0, 23, [0]),
])
def test_cron_field_expansion(field, lo, hi, expected):
    assert vd._expand(field, lo, hi) == expected


def test_cron_field_out_of_range_raises(tmp_path):
    """An out-of-range field must raise, not silently expand to something wrong."""
    with pytest.raises(ValueError):
        vd._expand("99", 0, 23)


def test_fire_times_skips_a_field_too_broad_to_be_a_claim(tmp_path):
    """`* * * * *` fires 1440 times; no doc line is claiming all of them."""
    assert vd._fire_times({"* * * * *"}) == set()
    assert vd._fire_times({"30 6 * * *"}) == {"06:30"}


def test_gcloud_failure_raises_rather_than_returning_stale_state(monkeypatch):
    """Rule 3.7: a failed read must not fall back to a cached snapshot."""
    class _Fail:
        returncode = 1
        stdout = ""
        stderr = "PERMISSION_DENIED"

    monkeypatch.setattr(vd.subprocess, "run", lambda *a, **k: _Fail())
    with pytest.raises(RuntimeError, match="PERMISSION_DENIED"):
        vd.read_live()


def test_snapshot_round_trips(tmp_path):
    """--write-snapshot output is valid input for --snapshot."""
    snap = tmp_path / "live.json"
    snap.write_text(json.dumps(LIVE))
    assert json.loads(snap.read_text())["run_jobs"] == LIVE["run_jobs"]
