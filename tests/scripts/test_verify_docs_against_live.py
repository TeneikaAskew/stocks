"""Unit tests for the docs-vs-live verifier.

The verifier exists because `docs/PIPELINE.md` claimed "23:00 UTC" for a job
whose scheduler is `0 23 * * 1-5` in `America/New_York`, and a timezone fix was
designed off that claim and was wrong. So the cases that matter here are the
ones that made the earlier hand-checking unreliable:

* a table row carrying BOTH an ET and a UTC column is correct, not drift
* "4:15 PM" and "16:15" are the same claim
* a line about a deleted resource is a record, not a stale claim
* an explicit reviewed exemption suppresses exactly one line

And four blind spots found in review, each of which let real drift through a
run that reported clean:

* "Sun 6 AM" -- an hour-only claim, invisible to a pattern needing ``:MM``
* "weekdays 08:30 + Sun 09:00" -- one correct time on a multi-cadence line
  vouching for a wrong one, because the line was checked as a whole
* a PAUSED scheduler whose cron expression still matches
* only ``N Cloud Run Jobs`` was compared, so service and scheduler counts
  were never checked at all

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
        # Two cadences for one job -- the shape that hid a wrong Sunday time
        # behind a right weekday one.
        "premarket-brief-daily": {
            "schedule": "30 8 * * 1-5", "timeZone": "America/New_York",
            "state": "ENABLED", "target_job": "premarket-brief",
        },
        "premarket-brief-sunday": {
            "schedule": "0 21 * * 0", "timeZone": "America/New_York",
            "state": "ENABLED", "target_job": "premarket-brief",
        },
        # Paused: the expression still matches, the job does not run.
        "signal-quality-report-hourly": {
            "schedule": "0 10-16 * * 1-5", "timeZone": "America/New_York",
            "state": "PAUSED", "target_job": "signal-quality-report",
        },
        # One comma list where a doc spells out the equivalent four crons.
        "sec-filings-intraday": {
            "schedule": "0 7,10,13,17 * * 1-5", "timeZone": "America/New_York",
            "state": "ENABLED", "target_job": "fetch-sec-filings",
        },
        # Monthly: same clock and weekday set as a wrong day-of-month claim.
        "av-options-monthly": {
            "schedule": "0 5 1 * *", "timeZone": "America/New_York",
            "state": "ENABLED", "target_job": "fetch-av-options-monthly",
        },
    },
    "run_jobs": ["fetch-market-data", "fetch-top-movers", "fetch-av-options-realtime"],
    # A monthly entry, for the calendar-field comparison.
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


def test_markdown_wrapped_live_count_is_read(tmp_path):
    """`**...jobs** (~50 live)` is a count claim; the emphasis is not a boundary.

    GCP_DATA_DICTIONARY.md writes the noun in bold, so `\\s*\\(` never reached
    the parenthesis and the file could contradict its own live snapshot under
    a clean run (Codex, PR #990).
    """
    out = _check(tmp_path, "| **Cloud Run — jobs** (~50 live) | ingestion |")
    assert [f.check for f in out] == ["count-drift"]
    assert "50" in out[0].detail and "3" in out[0].detail


def test_diagram_cell_joins_a_split_name_with_its_clock(tmp_path):
    """A box wraps its own contents; neither line alone carries the claim."""
    out = _check(tmp_path, "\n".join([
        "  ┌───────────────────┐",
        "  │ premarket-        │",
        "  │ brief (weekly)    │",
        "  │ Sun 06:00 ET      │",
        "  └───────────────────┘",
    ]))
    assert [f.check for f in out] == ["clock-drift"]
    assert "premarket-brief" in out[0].detail and "06:00" in out[0].detail


def test_diagram_cells_are_not_spliced_across_boxes(tmp_path):
    """Side-by-side boxes must not lend each other names and times.

    Joining whole lines would read `fetch-market-data` against the RIGHT box's
    07:15 and report a drift that is not there, which is worse than the miss
    this scan fixes.
    """
    out = _check(tmp_path, "\n".join([
        "  ┌───────────────────┐  ┌───────────────────┐",
        "  │ fetch-market-     │  │ fetch-top-        │",
        "  │ data (daily)      │  │ movers (daily)    │",
        "  │ Mon–Fri 23:00 ET  │  │ Mon–Fri 07:15 ET  │",
        "  └───────────────────┘  └───────────────────┘",
    ]))
    assert [f.check for f in out] == ["clock-drift"]
    assert "fetch-top-movers" in out[0].detail
    assert "fetch-market-data" not in out[0].detail


def test_a_one_line_cell_is_not_reported_twice(tmp_path):
    """Both passes see it; the reader should not read it twice."""
    out = _check(tmp_path, "\n".join([
        "  ┌────────────────────────────────────┐",
        "  │ `fetch-top-movers` weekdays 07:15  │",
        "  │ writes top_movers_daily            │",
        "  └────────────────────────────────────┘",
    ]))
    assert [f.check for f in out] == ["clock-drift"]


def test_a_noun_first_job_count_is_read(tmp_path):
    """`Cloud Run Jobs (27 jobs)` is a count claim too.

    Every pattern required the number BEFORE the noun, which is not how
    RUNBOOK.md's recovery tables are written, so a whole table of stale
    inventories was unreachable in a file the verifier explicitly scans
    (Codex, PR #990).
    """
    out = _check(tmp_path, "| **Cloud Run Jobs (27 jobs) + Schedulers (40+)** | 60-90 min |")
    assert "count-drift" in [f.check for f in out]
    assert "27" in " ".join(f.detail for f in out)


def test_a_secret_count_is_compared_at_all(tmp_path):
    """`read_live` collected the secrets and nothing ever checked them."""
    out = _check(tmp_path, "| **Secret Manager (19 secrets)** | 1-4 hours |")
    assert [f.check for f in out] == ["count-drift"]
    assert "19" in out[0].detail and "1" in out[0].detail


def test_a_subset_of_secrets_is_not_a_fleet_count(tmp_path):
    """"Just two secrets" for one workflow is not a claim about the project.

    A bare `N secrets` is more often a subset than a fleet count, and a
    checker that flags those is one people stop reading -- the same reason
    the services pattern is qualified.
    """
    out = _check(tmp_path, "Just two secrets: one for the DB and one for the API key.")
    assert out == [], [f.detail for f in out]


def test_the_calendar_fields_of_a_cron_are_compared(tmp_path):
    """`0 5 1 * *` and `0 5 2 * *` are not the same schedule.

    Firings are reduced to weekday and clock, which is what makes an
    equivalent respelling compare equal -- and it discarded day-of-month and
    month entirely, so a monthly job could be documented on the wrong day
    (Codex, PR #990).
    """
    out = _check(tmp_path, "| `fetch-av-options-monthly` | `0 5 2 * *` |")
    assert [f.check for f in out] == ["schedule-drift"]
    assert "day-of-month" in out[0].detail

    # The live spelling itself must stay clean.
    assert _check(tmp_path, "| `fetch-av-options-monthly` | `0 5 1 * *` |") == []


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


# ── Hour-only clock claims ──────────────────────────────────────────────────
# `docs/GCP_ARCHITECTURE.md:211` documented `fetch-earnings-history` as
# "Sun 6 AM weekly" against a live `15 19 * * 0`, and the run reported clean.

def test_hour_only_claim_is_compared(tmp_path):
    out = _check(tmp_path, "**`fetch-market-data-daily`** (weekdays 6 AM)")
    assert [f.check for f in out] == ["clock-drift"]
    assert "06:00" in out[0].detail


def test_correct_hour_only_claim_is_not_drift(tmp_path):
    out = _check(tmp_path, "**`fetch-market-data-daily`** (weekdays 11 PM)")
    assert out == []


def test_a_bare_number_is_not_read_as_an_hour(tmp_path):
    """Requiring AM/PM is what keeps this safe: a number beside a job name is
    usually a size, a count or a retry budget."""
    out = _check(tmp_path,
                 "| `fetch-market-data-daily` | 1 GiB / 30 min / `--max-retries 0` |")
    assert out == []


# ── Multi-cadence lines ─────────────────────────────────────────────────────

def test_one_correct_time_does_not_vouch_for_a_wrong_one(tmp_path):
    """The exact line from `docs/GCP_ARCHITECTURE.md:314`.

    Weekday 08:30 is right; Sunday is 21:00 live, not 09:00. Checking the line
    as a whole accepted it because 08:30 matched something.
    """
    out = _check(tmp_path, "| `premarket-brief` | 1 GiB | weekdays 08:30 + Sun 09:00 |")
    assert [f.check for f in out] == ["clock-drift"]
    assert "09:00" in out[0].detail and "Sun" in out[0].detail
    assert "08:30" not in out[0].detail, "the correct weekday time is not the finding"


def test_a_correct_multi_cadence_line_is_clean(tmp_path):
    out = _check(tmp_path, "| `premarket-brief` | 1 GiB | weekdays 08:30 + Sun 21:00 |")
    assert out == []


def test_the_any_match_rule_survives_inside_a_segment(tmp_path):
    """Within one day-qualified segment the any-match rule still holds, which
    is what keeps an ET column beside a UTC column (or a fire time beside a
    completion deadline) from reading as drift. Only ACROSS segments is each
    cadence judged on its own."""
    out = _check(tmp_path,
                 "| `premarket-brief` | weekdays 08:30, must finish by 09:15 |")
    assert [f.check for f in out] == []


# ── Paused schedulers ───────────────────────────────────────────────────────

def test_a_paused_scheduler_is_not_a_running_schedule(tmp_path):
    """`docs/GCP_ARCHITECTURE.md:321` presented a PAUSED entry as running
    hourly, and its cron expression still matched, so the run reported clean."""
    out = _check(tmp_path, "| `signal-quality-report-hourly` | weekdays hourly 10:00-16:00 |")
    assert "paused-schedule" in [f.check for f in out]
    assert "PAUSED" in [f for f in out if f.check == "paused-schedule"][0].detail


def test_a_line_that_says_paused_is_not_flagged(tmp_path):
    out = _check(tmp_path,
                 "`signal-quality-report-hourly` is paused; it would run `0 10-16 * * 1-5`.")
    assert out == []


# ── Counts beyond Cloud Run Jobs ────────────────────────────────────────────

def test_service_count_is_compared(tmp_path):
    out = _check(tmp_path, "| **Cloud Run Services** | 3 long-lived HTTP services |")
    assert [f.check for f in out] == ["count-drift"]
    assert "live count is 2" in out[0].detail


def test_a_spelled_out_service_count_is_compared(tmp_path):
    """`docs/GCP_ARCHITECTURE.md:344` says "Three long-lived HTTP services"."""
    out = _check(tmp_path, "Three long-lived HTTP services, all `min-instances=0`.")
    assert [f.check for f in out] == ["count-drift"]


def test_scheduler_count_is_compared(tmp_path):
    out = _check(tmp_path, "**60 cron triggers** drive the Jobs above.")
    assert [f.check for f in out] == ["count-drift"]
    assert f"live count is {len(LIVE['schedulers'])}" in out[0].detail


def test_the_free_tier_quota_is_not_read_as_a_fleet_count(tmp_path):
    """"Cloud Scheduler (N jobs, 3 free)" states one count and one quota."""
    n = len(LIVE["schedulers"])
    out = _check(tmp_path, f"| Cloud Scheduler ({n} jobs, 3 free) | **$0.30** |")
    assert out == []


def test_an_unqualified_service_count_is_not_a_cloud_run_claim(tmp_path):
    """"three services" in prose can mean vendors or APIs; only a Cloud Run
    qualifier makes it a claim this script can judge."""
    out = _check(tmp_path, "The pipeline depends on three services we do not control.")
    assert out == []


# ── Equivalent cron spellings ───────────────────────────────────────────────

def test_an_equivalent_respelling_is_not_drift(tmp_path):
    """`docs/product/05-INFRASTRUCTURE.md` writes the live `0 7,10,13,17 * * 1-5`
    as four separate crons. Identical schedule; the string comparison called it
    a finding, and a false positive is how a checker trains its readers to
    ignore it."""
    out = _check(tmp_path,
                 "| `fetch-sec-filings` | `0 7 * * 1-5`; `0 10 * * 1-5`; "
                 "`0 13 * * 1-5`; `0 17 * * 1-5` |")
    assert out == []


def test_a_cron_that_fires_when_live_does_not_is_still_drift(tmp_path):
    out = _check(tmp_path, "| `fetch-sec-filings` | `0 9 * * 1-5` |")
    assert [f.check for f in out] == ["schedule-drift"]


def test_a_self_correcting_record_is_not_drift(tmp_path):
    """A checklist entry keeps the old value beside the new one on purpose:
    ``- [x] `fetch-market-data-daily` — `0 17 * * 1-5` ET *(now `0 23 * * 1-5`)*``
    """
    out = _check(tmp_path,
                 "- [x] `fetch-market-data-daily` — `0 17 * * 1-5` ET "
                 "*(now `0 23 * * 1-5`)*")
    assert out == []


def test_a_wrong_cron_without_the_live_one_is_still_drift(tmp_path):
    """The correction exemption requires the line to actually state the live
    schedule, or "now" would excuse any stale cron."""
    out = _check(tmp_path, "- `fetch-market-data-daily` now runs `0 17 * * 1-5`")
    assert [f.check for f in out] == ["schedule-drift"]


# ── Day qualifiers ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,days", [
    ("weekdays 08:30", {1, 2, 3, 4, 5}),
    ("Sun 21:00", {0}),
    ("Tue-Sat 01:00", {2, 3, 4, 5, 6}),
    ("Sat\u2013Sun 09:00", {6, 0}),
    ("Fri-Mon 09:00", {5, 6, 0, 1}),
])
def test_day_qualifier_parsing(text, days):
    segments = vd._day_segments(text)
    assert segments and segments[0][0] == days


def test_a_line_with_no_day_qualifier_falls_back_to_the_whole_line():
    assert vd._day_segments("runs at 23:00 ET / 03:00 UTC") == []


def test_cadence_words_are_not_day_qualifiers():
    """"daily"/"nightly"/"hourly" say how often, not on which days. Treating
    them as day words split rows on prose ("Loads daily data") and invented
    segments carrying no claim."""
    assert vd._day_segments("nightly at 01:00, loads daily data hourly") == []


# ── Count vocabulary and wrapped claims ─────────────────────────────────────
# Widening `check_counts` to services and schedulers was still not enough on
# the first pass: the repo spells a scheduler at least five ways, and a run
# that reported clean was sitting on `SCH[84 Cloud Scheduler entries]`,
# `Cloud Scheduler (84 live / 58 declared)` and a claim broken across two
# lines by prose wrapping. Same narrowing, one level down.

@pytest.mark.parametrize("text", [
    "**60 cron triggers** drive the Jobs above.",
    "SCH[60 Cloud Scheduler entries] --> JOBS",
    "returns **60 scheduler entries**.",
    # The declared/live pair, in BOTH orders. The first version of this check
    # required the live number to come first inside the parens, so
    # "Scheduler (58 declared / 84 live)" stopped at `58 declared` and never
    # looked at the live half -- leaving a contradiction under a clean run
    # (Codex, PR #990).
    "| Cloud Scheduler (60 live / 58 declared) |",
    "| Scheduler (58 declared / 60 live) / manual |",
    "driven by 60 Cloud Scheduler entries",
    "# Create 60 Cloud Scheduler triggers",
])
def test_every_scheduler_spelling_is_counted(tmp_path, text):
    out = _check(tmp_path, text)
    assert [f.check for f in out] == ["count-drift"], text
    assert f"live count is {len(LIVE['schedulers'])}" in out[0].detail


def test_a_count_claim_broken_across_lines_is_still_counted(tmp_path):
    """`docs/product/05-INFRASTRUCTURE.md` says "returns **84 scheduler\nentries**".

    A per-line scan cannot see that however good its vocabulary is — the same
    blind spot the Eastern-timezone guard was caught with on #993, where a
    formatter's line break defeated the check. `check_counts` matches the whole
    file and derives the line from the match offset.
    """
    out = _check(tmp_path,
                 "`gcloud scheduler jobs list --location=us-east1` returns **60 scheduler\n"
                 "entries**. The two numbers answer different questions.")
    assert [f.check for f in out] == ["count-drift"]
    assert out[0].line == 1, "the finding must point at the line the claim starts on"


def test_a_reviewed_exemption_still_suppresses_a_wrapped_claim(tmp_path):
    """Whole-file matching must not lose the per-line suppression markers."""
    out = _check(tmp_path,
                 "<!-- verify-docs-ok: deliberately the declared count -->\n"
                 "**60 scheduler entries** are declared in the repo.")
    assert out == []


def test_the_free_tier_quota_is_still_not_a_fleet_count(tmp_path):
    n = len(LIVE["schedulers"])
    out = _check(tmp_path, f"| Cloud Scheduler ({n} jobs, 3 free) | **$0.30** |")
    assert out == []


def test_the_declared_half_of_a_declared_live_pair_is_not_checked(tmp_path):
    """`58 declared` describes gcp/deploy.sh, which is a different
    measurement from the live fleet — flagging it would be a false positive
    on a row that is telling the truth about both."""
    n = len(LIVE["schedulers"])
    out = _check(tmp_path, f"| Scheduler (58 declared / {n} live) / manual |")
    assert out == [], out


def test_a_declared_live_pair_reports_once_not_twice(tmp_path):
    """Two patterns can match the same claim; only one finding should result."""
    out = _check(tmp_path, "| Cloud Scheduler (60 live / 58 declared) |")
    assert len(out) == 1, [str(f) for f in out]
