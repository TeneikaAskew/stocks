"""Regression tests for scripts/maintenance/doc_inventory.py.

The module exists because counting jobs, schedulers, tables and routes was
left to a language model and the 2026-09-02 ARCHITECTURE.md regeneration
named 4 of 67 declared jobs. These tests pin the parser to the real repo
(the counts the docs embed) and to small fixtures for the shapes deploy.sh
uses that a naive grep gets wrong: comment lines that mention job names,
`common_flags=(...)` arrays, `for h in ...` scheduler loops, backslash-
continued `_schedule_with_args` calls, and raw `gcloud scheduler jobs create`
blocks whose flags live in a bash array above the call.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from scripts.maintenance import doc_inventory as inv

REPO = pathlib.Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json"


# ── fixture-driven parser cases ─────────────────────────────────────────────

DEPLOY_SNIPPET = r'''
IMAGE="us-east1-docker.pkg.dev/${PROJECT_ID}/trading/trading-system"

# gcloud run jobs update leaves omitted flags untouched -- a comment, not a job.
deploy_alpha() {
    local research_image="${IMAGE}:research"
    local default_args="-m,gcp.research.alpha,--mode=full"
    local common_flags=(
        --image "${research_image}" --region "${REGION}"
        --memory 4Gi --cpu 2 --max-retries 0 --task-timeout 3600
        --command "python"
        --args="${default_args}"
    )
    gcloud run jobs create alpha "${common_flags[@]}" 2>/dev/null || \
    gcloud run jobs update alpha "${common_flags[@]}"
}

deploy_beta() {
    gcloud run jobs create beta \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 \
        --command "python,-m,gcp.fetchers.beta" \
        --quiet 2>/dev/null || \
    gcloud run jobs update beta --image "${IMAGE}" --quiet
}

_schedule() {
    local NAME=$1 CRON=$2 JOB=$3
    gcloud scheduler jobs create http "${NAME}" \
        --schedule "${CRON}" --uri "$(_job_uri "${JOB}")" --quiet
}

deploy_schedulers() {
    _schedule "alpha-daily" "35 23 * * 1-5" "alpha"
    # _schedule "retired-daily" "0 0 * * *" "alpha"
    for h in 08 09; do
        _schedule "news-${h}00"  "0 ${h} * * 1-5"  "beta"
    done
    _schedule_with_args "orb-15m"  "45 9 * * 1-5"  "alpha" \
        "--mode=orb-snapshot" "--window=15m"
    local _BODY='{"overrides":{"containerOverrides":[{"args":["-m","gcp.research.enrich","--mode=all"]}]}}'
    local _common=(
        --schedule "0 2 * * 2-6"
        --uri "$(_job_uri "alpha")"
        --message-body "${_BODY}"
    )
    gcloud scheduler jobs create http "enrich-daily" "${_common[@]}" 2>/dev/null || \
    gcloud scheduler jobs update http "enrich-daily" "${_common[@]}" --quiet
}

case "${1:-}" in
    alpha) deploy_alpha ;;
    beta) deploy_beta ;;
    schedulers) deploy_schedulers ;;
esac
'''

SCHEMA_SNIPPET = """
CREATE TABLE IF NOT EXISTS market_data_intraday (
    ticker TEXT
) PARTITION BY LIST (ticker);
CREATE TABLE IF NOT EXISTS market_data_intraday_spy
    PARTITION OF market_data_intraday FOR VALUES IN ('SPY');
CREATE TABLE trades (id INT);
CREATE MATERIALIZED VIEW earnings_ticker_lean AS SELECT 1;
CREATE OR REPLACE VIEW v_node AS SELECT 1;
"""


@pytest.fixture()
def mini_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "gcp").mkdir()
    (tmp_path / "gcp/deploy.sh").write_text(DEPLOY_SNIPPET)
    (tmp_path / "gcp/schema.sql").write_text(SCHEMA_SNIPPET)
    return tmp_path


def test_jobs_ignore_comments_and_read_common_flags_arrays(mini_repo):
    jobs = {j["name"]: j for j in inv.deploy_jobs(mini_repo)}
    assert set(jobs) == {"alpha", "beta"}, "the comment's `update leaves` must not count as a job"
    a = jobs["alpha"]
    assert a["image"] == "research"
    assert a["memory"] == "4Gi" and a["task_timeout"] == "3600" and a["max_retries"] == "0"
    assert a["args"] == "-m gcp.research.alpha --mode=full", "local default_args must be resolved"
    b = jobs["beta"]
    assert b["timeout_defaulted"] and b["task_timeout"] == inv.CLOUD_RUN_DEFAULT_TASK_TIMEOUT
    assert b["command"] == "python -m gcp.fetchers.beta"


def test_schedulers_expand_loops_continuations_and_arrays(mini_repo):
    s = {x["name"]: x for x in inv.deploy_schedulers(mini_repo)}
    assert "${NAME}" not in s, "helper definitions must not leak placeholder rows"
    assert "retired-daily" not in s, "commented-out schedulers are not declared"
    assert s["news-0800"]["cron"] == "0 08 * * 1-5" and s["news-0900"]["target_job"] == "beta"
    assert s["orb-15m"]["args"] == "--mode=orb-snapshot --window=15m"
    assert s["enrich-daily"]["cron"] == "0 2 * * 2-6"
    assert s["enrich-daily"]["target_job"] == "alpha"
    assert s["enrich-daily"]["args"] == "-m gcp.research.enrich --mode=all"


def test_schema_tables_partitions_views(mini_repo):
    sc = inv.schema_tables(mini_repo)
    names = {t["name"]: t for t in sc["tables"]}
    assert set(names) == {"market_data_intraday", "market_data_intraday_spy", "trades"}
    assert names["market_data_intraday_spy"]["partition_of"] == "market_data_intraday"
    assert [v["name"] for v in sc["materialized_views"]] == ["earnings_ticker_lean"]
    assert [v["name"] for v in sc["views"]] == ["v_node"]


def test_deploy_targets_from_case_block(mini_repo):
    assert inv.deploy_targets(mini_repo) == ["alpha", "beta", "schedulers"]


# ── the real repo: the numbers the docs embed ───────────────────────────────

def test_real_repo_counts_match_the_workflow_gate():
    repo = inv.repo_inventory(REPO)
    # Same regex as the refresh workflow's DATA_DEPENDENCIES gate.
    import re
    gate = sorted({m.group(1) for m in re.finditer(
        r"^CREATE TABLE(?: IF NOT EXISTS)? ([a-zA-Z0-9_]+)", (REPO / "gcp/schema.sql").read_text(), re.M)})
    assert [t["name"] for t in repo["tables"]] == gate
    assert repo["counts"]["jobs"] >= 67
    assert repo["counts"]["routers"] >= 20
    assert {"replay", "replay-signals", "watchlist", "validate", "backtest"} <= {
        c["name"] for c in repo["discord_commands"]}
    assert {"deploy-solyra-api-staging", "deploy-solyra-api-prod", "apply-schema-on-change"} <= {
        t["trigger"] for t in repo["cloudbuild_triggers"]}
    assert any(r["path"] == "/api/me/profile" and r["method"] == "PUT" for r in repo["routes"])


def test_every_scheduler_targets_a_declared_job_or_a_known_gap():
    repo = inv.repo_inventory(REPO)
    jobs = {j["name"] for j in repo["jobs"]}
    gaps = {s["name"] for s in repo["schedulers"] if s["target_job"] and s["target_job"] not in jobs}
    # gamma-levels-daily fires p2-build-gamma-levels, which exists live but has
    # no deploy_* function (issue #829). Anything else here is new drift.
    assert gaps <= {"gamma-levels-daily"}, gaps


# ── reconcile + render against the saved live snapshot ──────────────────────

def test_reconcile_against_snapshot_reports_the_known_deltas():
    repo = inv.repo_inventory(REPO)
    live = json.loads(FIXTURE.read_text())
    rec = inv.reconcile(repo, live)
    assert {"backtest-playability", "compare-tier-fires", "p2-build-gamma-levels",
            "strat-dir-features"} <= set(rec["jobs_live_only"])
    assert "compute-spx-greeks-backfill" in rec["jobs_repo_only"]
    assert "signal-quality-report-hourly" in rec["schedulers_paused"]
    assert rec["counts"]["jobs_live"] == live["counts"]["jobs"]


def test_render_is_idempotent_and_marker_insert_round_trips(tmp_path):
    repo = inv.repo_inventory(REPO)
    live = json.loads(FIXTURE.read_text())
    for section in inv.SECTIONS:
        once = inv.render_markdown(section, repo, live)
        assert once == inv.render_markdown(section, repo, live)
    doc = tmp_path / "ARCH.md"
    doc.write_text("# x\n<!-- inventory:jobs:start -->\nstale\n<!-- inventory:jobs:end -->\ntail\n")
    assert inv.insert_blocks(doc, repo, live) is True
    first = doc.read_text()
    assert "stale" not in first and "`signal-monitor`" in first and first.endswith("tail\n")
    assert inv.insert_blocks(doc, repo, live) is False, "second insert must be a no-op"


def test_missing_end_marker_is_an_error(tmp_path):
    repo = inv.repo_inventory(REPO)
    doc = tmp_path / "ARCH.md"
    doc.write_text("<!-- inventory:tables:start -->\n")
    with pytest.raises(ValueError):
        inv.insert_blocks(doc, repo, None)
