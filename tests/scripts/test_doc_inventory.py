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
    gcloud scheduler jobs update http "enrich-daily" "${_common[@]}" --update-headers "X=y"

    local _FULL='{"overrides":{"containerOverrides":[{"env":[{"name":"MODE","value":"full"}]}]}}'
    gcloud scheduler jobs create http "alpha-weekly" \
        --schedule "0 3 * * 0" \
        --uri "$(_job_uri "alpha")" \
        --message-body "${_FULL}" \
        --quiet 2>/dev/null || echo "  alpha-weekly: already exists"
    if _schedule_verified "news-hourly"  "0 8-17 * * 1-5"  "beta"; then
        _unschedule "news-0800"
    fi
    _schedule_min_instances "warm-open"  "0 9 * * 1-5"   "discord-interactions" 1 \
        || FAILURES=$((FAILURES + 1))
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
    # The array-based create above carries no --quiet of its own; the block must
    # stop at the blank line, not run on into alpha-weekly and steal its cron/env.
    assert s["alpha-weekly"]["cron"] == "0 3 * * 0" and s["alpha-weekly"]["args"] == "MODE=full"
    assert "MODE=full" not in s["enrich-daily"]["args"]
    # `if _schedule_verified ...; then` is a declaration (#1004 consolidation).
    assert s["news-hourly"]["cron"] == "0 8-17 * * 1-5" and s["news-hourly"]["target_job"] == "beta"
    # `_schedule_min_instances` PATCHes a service, not a job.
    w = s["warm-open"]
    assert w["target_job"] == "" and w["target_service"] == "discord-interactions"
    assert w["args"] == "minInstanceCount=1" and "services/discord-interactions" in w["target_uri"]


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
    services = {s["name"] for s in repo["schedulers"] if s["target_service"]}
    assert services == {"discord-warm-open", "discord-warm-close"}, services
    declared = {s["name"] for s in repo["schedulers"]}
    # the #1004 consolidations and the #1005 playbook are declared, not live-only
    assert {"sec-filings-intraday", "news-sentiment-hourly", "news-topics-hourly",
            "phase6-playbook-daily", "backfill-indicators-weekly"} <= declared


# ── reconcile + render against the saved live snapshot ──────────────────────

def test_reconcile_against_snapshot_reports_the_known_deltas():
    repo = inv.repo_inventory(REPO)
    live = json.loads(FIXTURE.read_text())
    rec = inv.reconcile(repo, live)
    assert {"backtest-playability", "compare-tier-fires",
            "strat-dir-features"} <= set(rec["jobs_live_only"])
    # p2-build-gamma-levels was hand-made and live-only until #829/#834
    # codified it as deploy_p2_build_gamma_levels; it now reconciles.
    assert "p2-build-gamma-levels" not in rec["jobs_live_only"]
    assert "compute-spx-greeks-backfill" in rec["jobs_repo_only"]
    # signal-quality-report-hourly was retired by #1005 and its paused live
    # entry deleted on 2026-09-07, so schedulers reconcile exactly.
    assert rec["schedulers_paused"] == [] and rec["schedulers_live_only"] == []
    assert rec["schedulers_repo_only"] == [] and rec["schedulers_cron_drift"] == []
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


def test_operator_advice_in_an_error_message_is_not_a_write():
    """`raise RuntimeError("... UPDATE watchlists SET ...")` executes nothing.

    signal_monitor only READS watchlists, but the advice string matched
    WRITE_RE and the four-line context window then pulled the following log
    line in with it, so the write graph cited two lines that run no SQL and
    the blast radius named signal-monitor a writer. (Codex, PR #1009.)
    """
    refs = inv.table_refs(REPO, ["watchlists"])
    writers = {r["file"] for r in refs["watchlists"]["writes"]}
    assert "gcp/signal_monitor.py" not in writers, sorted(writers)
    # the real writers must survive the exclusion
    assert {"gcp/discord_interactions/main.py", "gcp/fetchers/_watchlist.py"} <= writers


def test_a_logged_or_raised_statement_never_classifies_as_a_write(tmp_path):
    src = tmp_path / "gcp"
    src.mkdir()
    (src / "m.py").write_text(
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "def go(conn):\n"
        "    if not rows:\n"
        "        raise RuntimeError(\n"
        "            'no rows in demo_table -- fix with:\\n'\n"
        "            '  UPDATE demo_table SET flag = TRUE'\n"
        "        )\n"
        "    logger.info('demo_table loaded: %d', len(rows))\n"
        "    return conn.execute('SELECT * FROM demo_table')\n"
    )
    refs = inv.table_refs(tmp_path, ["demo_table"])
    assert refs["demo_table"]["writes"] == [], refs["demo_table"]["writes"]
    assert refs["demo_table"]["reads"], "the genuine SELECT must still be found"


def test_an_executed_write_is_still_a_write(tmp_path):
    src = tmp_path / "gcp"
    src.mkdir()
    (src / "w.py").write_text(
        "def go(conn):\n"
        "    conn.execute('UPDATE demo_table SET flag = TRUE')\n"
    )
    refs = inv.table_refs(tmp_path, ["demo_table"])
    assert [r["line"] for r in refs["demo_table"]["writes"]] == [2]


def test_the_module_catalog_reaches_every_production_subpackage():
    """A hand-listed set of directories globbed non-recursively omitted every
    subpackage nobody remembered to add. (Codex, PR #1009.)"""
    paths = {m["path"] for m in inv.repo_inventory(REPO)["modules"]}
    for pkg in ("lib/features/", "lib/agents/ranker/", "gcp/research/direction_program/"):
        assert any(p.startswith(pkg) for p in paths), f"{pkg} missing from the module catalog"
    # and nothing from the trees that are not production code
    assert not [p for p in paths if "_archive" in p or "__pycache__" in p
                or p.startswith("tests/") or "/tests/" in p]


def test_the_module_catalog_matches_a_plain_recursive_walk():
    """The catalog must equal what a filesystem walk of the roots finds, so a
    new subpackage cannot go missing without this failing."""
    paths = {m["path"] for m in inv.repo_inventory(REPO)["modules"]}
    expected = set()
    for d in inv.MODULE_ROOTS:
        for f in (REPO / d).rglob("*.py"):
            rel = f.relative_to(REPO)
            if f.name.startswith("__") or f.name.startswith("test_") or f.name.endswith("_test.py"):
                continue
            if inv.MODULE_EXCLUDE_PARTS & set(rel.parts):
                continue
            expected.add(str(rel))
    assert paths == expected


def test_reconcile_catches_a_scheduler_redirected_to_another_existing_job():
    """Cron alone said the fleets matched.

    A scheduler kept its name and cron but pointed at a different job that also
    exists, so every missing-target check passed and §15 read clean while
    production fired the wrong job. (Codex, PR #1009.)
    """
    live = json.loads(FIXTURE.read_text())
    repo = inv.repo_inventory(REPO)
    name = next(s["name"] for s in repo["schedulers"]
                if s.get("target_job") and s["name"] in live["schedulers"])
    other = next(j["name"] for j in repo["jobs"]
                 if j["name"] != next(s["target_job"] for s in repo["schedulers"] if s["name"] == name))
    live["schedulers"][name] = dict(live["schedulers"][name], target_job=other)
    rec = inv.reconcile(repo, live)
    assert rec["schedulers_targeting_missing_job"] == [], "the old check must still pass — that is the point"
    assert any(n.startswith(f"{name}:") for n in rec["schedulers_target_drift"]), rec["schedulers_target_drift"]


def test_reconcile_catches_a_scheduler_moved_to_another_time_zone():
    live = json.loads(FIXTURE.read_text())
    repo = inv.repo_inventory(REPO)
    name = next(s["name"] for s in repo["schedulers"]
                if s.get("time_zone") and s["name"] in live["schedulers"])
    live["schedulers"][name] = dict(live["schedulers"][name], time_zone="UTC")
    rec = inv.reconcile(repo, live)
    assert rec["schedulers_cron_drift"] == [] or all(not c.startswith(f"{name}:") for c in rec["schedulers_cron_drift"])
    assert any(n.startswith(f"{name}:") for n in rec["schedulers_tz_drift"]), rec["schedulers_tz_drift"]


def test_the_committed_fleets_have_no_target_or_timezone_drift():
    live = json.loads(FIXTURE.read_text())
    rec = inv.reconcile(inv.repo_inventory(REPO), live)
    assert rec["schedulers_target_drift"] == []
    assert rec["schedulers_tz_drift"] == []


def test_a_service_targeting_scheduler_is_compared_by_its_service():
    """Requiring two non-empty target_job fields skipped service schedulers.

    `discord-warm-open` / `-close` target the discord-interactions SERVICE, so
    redirecting one to another service produced no drift at all.
    (Codex, PR #1009.)
    """
    live = json.loads(FIXTURE.read_text())
    repo = inv.repo_inventory(REPO)
    name = "discord-warm-open"
    assert inv._sched_target(live["schedulers"][name]).startswith("service:")
    live["schedulers"][name] = dict(live["schedulers"][name], target_service="failure-notifier")
    rec = inv.reconcile(repo, live)
    assert any(n.startswith(f"{name}:") for n in rec["schedulers_target_drift"]), rec["schedulers_target_drift"]


def test_converting_a_job_scheduler_into_a_service_request_is_drift():
    live = json.loads(FIXTURE.read_text())
    repo = inv.repo_inventory(REPO)
    name = next(s["name"] for s in repo["schedulers"]
                if s.get("target_job") and s["name"] in live["schedulers"])
    live["schedulers"][name] = {k: v for k, v in live["schedulers"][name].items() if k != "target_job"}
    live["schedulers"][name]["target_service"] = "discord-interactions"
    rec = inv.reconcile(repo, live)
    assert any(n.startswith(f"{name}:") for n in rec["schedulers_target_drift"]), rec["schedulers_target_drift"]


def test_a_templated_uri_target_is_not_reported_as_drift():
    """The repo can only know the host as a deploy-time variable, so comparing
    the raw string made `${service_url}/reconcile` differ from the live URL on
    every run."""
    repo = inv.repo_inventory(REPO)
    templated = next((s for s in repo["schedulers"] if s.get("target_uri") and "${" in s["target_uri"]), None)
    assert templated is not None, "fixture assumption: a templated URI target exists"
    live_form = dict(templated, target_uri="https://failure-notifier-5sjtb3yl7a-ue.a.run.app/reconcile")
    assert inv._sched_target(templated) == inv._sched_target(live_form)


def test_a_uri_target_keeps_the_service_it_points_at():
    """Discarding the host made a redirect to any other host with the same
    path invisible. deploy.sh derives ${service_url} from NOTIFIER_SERVICE, so
    the identity is knowable. (Codex, PR #1009.)"""
    repo = inv.repo_inventory(REPO)
    live = json.loads(FIXTURE.read_text())
    name = "reconcile-failure-notifier-hourly"
    r, l = next(s for s in repo["schedulers"] if s["name"] == name), live["schedulers"][name]
    assert inv._sched_target(r) == inv._sched_target(l) == "service:failure-notifier/reconcile"
    # a redirect to a DIFFERENT service on the same path is drift
    moved = dict(l, target_uri="https://some-other-svc-abc-ue.a.run.app/reconcile")
    assert inv._sched_target(moved) != inv._sched_target(r)
    live["schedulers"][name] = moved
    assert any(n.startswith(f"{name}:") for n in inv.reconcile(repo, live)["schedulers_target_drift"])


def test_live_job_config_drift_is_reported():
    """Job rows were rendered only from deploy.sh, so a job running at 2 GiB
    against a 1 GiB declaration read as 1 GiB and reconciled clean.
    (Codex, PR #1009.)"""
    live = json.loads(FIXTURE.read_text())
    drift = inv.reconcile(inv.repo_inventory(REPO), live)["jobs_config_drift"]
    assert any("compute-earnings-reactions.memory" in d and "1Gi" in d and "2Gi" in d for d in drift), drift
    assert any("strat-engine.memory" in d for d in drift), drift


def test_a_deploy_time_variable_is_not_config_drift():
    """`--tasks ${n}` is a value the repo cannot state, exactly like a
    templated scheduler URI."""
    live = json.loads(FIXTURE.read_text())
    drift = inv.reconcile(inv.repo_inventory(REPO), live)["jobs_config_drift"]
    assert not [d for d in drift if "${" in d], drift
    assert inv._norm_cfg("${plan_size}") is None
    assert inv._norm_cfg("2Gi") == inv._norm_cfg("2G")


def test_config_drift_compares_the_field_names_that_exist():
    """The first version compared `timeout`; both sides store `task_timeout`,
    so that entry was None-vs-None on every job and the check was dead for the
    field. (Codex, PR #1009.)"""
    assert "task_timeout" in inv.JOB_CONFIG_FIELDS
    assert "timeout" not in inv.JOB_CONFIG_FIELDS
    live = json.loads(FIXTURE.read_text())
    drift = inv.reconcile(inv.repo_inventory(REPO), live)["jobs_config_drift"]
    assert any("compute-earnings-reactions.task_timeout" in d and "1800" in d and "5400" in d
               for d in drift), drift


def test_an_entrypoint_change_is_drift_but_its_spelling_is_not():
    """deploy.sh puts the whole invocation in command; the live record splits
    `python` from `-m gcp.x`. Compared separately that reported four jobs as
    drifted on representation alone. (Codex, PR #1009.)"""
    live = json.loads(FIXTURE.read_text())
    drift = inv.reconcile(inv.repo_inventory(REPO), live)["jobs_config_drift"]
    assert any("magnitude-recal.entrypoint" in d for d in drift), drift
    assert not [d for d in drift if d.endswith(".command: repo `python -m gcp.backtest_job` live `python`")]


def test_a_route_registered_only_behind_a_dist_guard_is_not_inventoried():
    """platform/Dockerfile copies no dist/, so the SPA fallback never
    registers in production. (Codex, PR #1009.)"""
    routes = {r["path"] for r in inv.repo_inventory(REPO)["routes"]}
    assert "/{full_path:path}" not in routes, "an inactive route is published as live"
