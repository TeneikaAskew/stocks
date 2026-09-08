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
    # repo_inventory reads these two unconditionally; empty stand-ins let a
    # test build a whole inventory from this tree.
    (tmp_path / "platform/api/routers").mkdir(parents=True)
    (tmp_path / "platform/api/main.py").write_text("")
    (tmp_path / "scripts/discord").mkdir(parents=True)
    (tmp_path / "scripts/discord/register_commands.py").write_text("")
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
    assert {"backtest-playability", "compare-tier-fires", "p2-build-gamma-levels",
            "strat-dir-features"} <= set(rec["jobs_live_only"])
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



# ── the §7 graph and the 05-c digest are rendered, not drawn ─────────────────

def _repo_and_refs():
    repo = inv.repo_inventory(REPO)
    return repo, repo["table_refs"]


def test_the_graph_is_rendered_from_table_refs_and_agrees_with_blast_radius():
    """05-c was the one step that kept dying inside the CLI's idle timeout
    while redrawing this graph from the raw 220 KB reference data (runs 20,
    21, 25 x2). Rendered, it is exact and costs the model nothing."""
    repo, refs = _repo_and_refs()
    out = inv.render_markdown("graph", repo, None)
    assert out.startswith("```mermaid\nflowchart LR") and out.endswith("```")
    assert out == inv.render_markdown("graph", repo, None), "render is not deterministic"
    # A write the blast table already attributes must be a thick edge here.
    blast = {b["job"]: b for b in inv.blast_radius(repo, refs)}
    job, table = next((j, b["writes"][0]) for j, b in sorted(blast.items()) if b["writes"])
    assert f"{inv._mermaid_id('J', job)} ==> {inv._mermaid_id('T', table)}" in out
    # Only nodes with an edge, and every id is Mermaid-safe.
    import re
    ids = set(re.findall(r"^\s+([JT]_[A-Za-z0-9_]+)[\[(]", out, re.M))
    used = set(re.findall(r"([JT]_[A-Za-z0-9_]+)\s+(?:==>|-->)\s+([JT]_[A-Za-z0-9_]+)", out))
    used = {a for pair in used for a in pair}
    assert ids == used, ids ^ used


def test_a_job_with_no_table_edge_is_not_drawn():
    repo, refs = _repo_and_refs()
    silent = next(e["job"] for e in inv.job_table_edges(repo, refs) if not e["writes"] and not e["reads"])
    assert inv._mermaid_id("J", silent) not in inv.render_markdown("graph", repo, None)


def test_the_refs_digest_is_small_and_carries_what_the_prose_needs():
    """What the 05-c prompt reads instead of repo_inventory.json (400 KB, of
    which table_refs is 220 KB). Same data as the rendered blocks, digested."""
    repo, refs = _repo_and_refs()
    out = inv.render_markdown("refs_digest", repo, None)
    assert len(out) < 40_000, len(out)
    assert "## Multi-writer tables" in out and "## Orphan tables" in out and "## Tables per job" in out
    # Same tables and writer counts as the §4 block, so the prose cannot
    # disagree with it; the digest additionally cites each writer file:line.
    block_rows = {(r.split("|")[1].strip(), r.split("|")[2].strip())
                  for r in inv._render_multiwriter(refs).splitlines()[2:]}
    digest_rows = {(r.split("|")[1].strip(), r.split("|")[2].strip())
                   for r in out.split("## Multi-writer tables")[1].split("## Orphan tables")[0].strip().splitlines()[2:]}
    assert block_rows and block_rows == digest_rows


# ── Codex, PR #1044: seven findings on the digest and the edge attribution ────

def test_the_digest_multiwriter_rows_cite_file_and_line():
    """The prompt requires `file:line` for every claim about code, and the
    digest is the only code input the 05-c model reads; a files-only writer
    list left it nothing to cite."""
    import re
    repo, refs = _repo_and_refs()
    out = inv.render_markdown("refs_digest", repo, None)
    rows = out.split("## Multi-writer tables")[1].split("## Orphan tables")[0].strip().splitlines()[2:]
    assert rows
    for r in rows:
        writers = r.split("|")[3]
        cited = re.findall(r"`([\w/.-]+\.py):(\d+(?:,\d+)*)`", writers)
        assert len(cited) == int(r.split("|")[2].strip()), r
    # and the §4 block itself stays files-only
    assert not re.search(r"\.py:\d+", inv._render_multiwriter(refs))


def test_the_digest_orphans_carry_the_same_partition_status_as_the_block():
    """The §5 block labels the five `market_data_intraday_*` children as
    partitions routed by Postgres; the digest called them 'no writer and no
    reader', and the model would have written that into the prose."""
    repo, refs = _repo_and_refs()
    block = inv.render_markdown("orphans", repo, None)
    digest = inv.render_markdown("refs_digest", repo, None)
    section = digest.split("## Orphan tables")[1].split("## Tables per job")[0].strip()
    assert section == block
    spy = next(r for r in section.splitlines() if r.startswith("| `market_data_intraday_spy`"))
    assert "partition of `market_data_intraday`" in spy, spy


def test_a_read_is_recorded_even_when_the_same_job_writes_the_table():
    """backfill-daily-indicators runs `SELECT DISTINCT ticker FROM
    market_data_daily` and then writes market_data_daily; dropping the read
    because a write exists hid the dependency from the graph and the digest."""
    repo, refs = _repo_and_refs()
    e = next(x for x in inv.job_table_edges(repo, refs) if x["job"] == "backfill-daily-indicators")
    assert "market_data_daily" in e["writes"] and "market_data_daily" in e["reads"], e
    graph = inv.render_markdown("graph", repo, None)
    j, t = inv._mermaid_id("J", "backfill-daily-indicators"), inv._mermaid_id("T", "market_data_daily")
    assert f"{j} ==> {t}" in graph and f"{t} --> {j}" in graph


def test_a_docstring_sql_example_is_not_an_edge():
    """gcp/db_query_job.py's module docstring shows an operator example
    `DB_QUERY_SQL=SELECT count(*) FROM trades`; that line made db-query a
    static reader of `trades`. The job reads whatever SQL it is handed at
    run time and has no static table edge at all."""
    src = "\"\"\"Run me:\n  DB_QUERY_SQL=SELECT count(*) FROM trades\n\"\"\"\n\n\ndef f():\n    \"\"\"SELECT 1 FROM trades\"\"\"\n    return 1\n"
    assert inv._diagnostic_lines(src) >= {1, 2, 3, 7}
    assert 8 not in inv._diagnostic_lines(src)
    repo, refs = _repo_and_refs()
    e = next(x for x in inv.job_table_edges(repo, refs) if x["job"] == "db-query")
    assert e["writes"] == [] and e["reads"] == [], e
    assert not any(r["file"] == "gcp/db_query_job.py" for r in refs["trades"]["reads"])


def test_job_table_edges_walks_the_selected_root_not_the_checkout(mini_repo):
    """`--root` selects a tree; the import scope used to be resolved against
    the checkout the script lives in, so a job in the selected tree whose
    writes live in a module it imports lost every edge."""
    (mini_repo / "gcp/research").mkdir()
    (mini_repo / "gcp/research/alpha.py").write_text("from gcp import helpers\n\ndef main():\n    helpers.save()\n")
    # four blank lines apart: the scanner's context window is the three
    # lines above a match, and the write above must not colour the read.
    (mini_repo / "gcp/helpers.py").write_text(
        "def save(conn):\n    conn.execute(\"INSERT INTO trades VALUES (1)\")\n\n\n\n\n"
        "def load(conn):\n    return conn.execute(\"SELECT * FROM trades\")\n")
    repo = inv.repo_inventory(mini_repo)
    assert repo["root"] == str(mini_repo)
    e = {x["job"]: x for x in inv.job_table_edges(repo, repo["table_refs"])}
    assert e["alpha"]["writes"] == ["trades"] and e["alpha"]["reads"] == ["trades"], e["alpha"]
    blast = {b["job"]: b for b in inv.blast_radius(repo, repo["table_refs"])}
    assert blast["alpha"]["writes"] == ["trades"]
    # the graph and the digest rendered from this inventory see the same tree
    assert f"{inv._mermaid_id('J', 'alpha')} ==> {inv._mermaid_id('T', 'trades')}" in inv.render_markdown("graph", repo, None)
    assert "| `alpha` | `trades` | `trades` |" in inv.render_markdown("refs_digest", repo, None)


def test_job_edges_follow_imports_transitively(mini_repo):
    """gcp/backtest_job.py imports scripts/run_backtest.py, which imports
    lib/data_loader.py, which reads market_data_daily. A one-level scope
    stopped at run_backtest and the backtest job had no read edge at all."""
    (mini_repo / "gcp/research").mkdir()
    (mini_repo / "gcp/research/alpha.py").write_text("from gcp import helpers\n")
    (mini_repo / "gcp/helpers.py").write_text("from gcp import deep\n")
    (mini_repo / "gcp/deep.py").write_text("def load(conn):\n    return conn.execute(\"SELECT * FROM trades\")\n")
    # a cycle must terminate, and gcp/database.py stays excluded at any depth
    (mini_repo / "gcp/database.py").write_text("from gcp import deep\ndef log(conn):\n    conn.execute(\"INSERT INTO trades VALUES (1)\")\n")
    (mini_repo / "gcp/deep.py").write_text((mini_repo / "gcp/deep.py").read_text() + "from gcp import helpers\nfrom gcp import database\n")
    repo = inv.repo_inventory(mini_repo)
    scope = inv._import_scope(mini_repo, "gcp/research/alpha.py")
    assert scope == {"gcp/research/alpha.py", "gcp/helpers.py", "gcp/deep.py"}, scope
    e = {x["job"]: x for x in inv.job_table_edges(repo, repo["table_refs"])}
    assert e["alpha"]["reads"] == ["trades"] and e["alpha"]["writes"] == [], e["alpha"]
    blast = {b["job"]: b for b in inv.blast_radius(repo, repo["table_refs"])}
    assert blast["alpha"]["writes"] == []


def test_the_backtest_job_reads_through_run_backtest():
    repo, refs = _repo_and_refs()
    e = next(x for x in inv.job_table_edges(repo, refs) if x["job"] == "backtest")
    assert "market_data_daily" in e["reads"], e


def test_the_digest_carries_the_live_only_name_sets(mini_repo):
    """The 05-c prose names the runtime-created relations and the
    hand-created jobs, and `live.json` and the §1b block are off-limits to
    the model, so those names have to travel in the digest."""
    (mini_repo / "gcp/helpers.py").write_text("def save(conn):\n    conn.execute(\"INSERT INTO trades VALUES (1)\")\n")
    repo = inv.repo_inventory(mini_repo)
    ok = {"last_execution": {"result": "ok", "time": "2026-09-07T00:00:00Z"},
          "memory": "4Gi", "cpu": "1", "task_timeout": "3600", "max_retries": 0, "tasks": 1}
    live = {"jobs": {"alpha": dict(ok, command="python", args="-m gcp.research.alpha --mode=full"),
                     "gamma": dict(ok, command="python -m gcp.helpers", args=""),
                     "delta": dict(ok, command="python -m gcp.gone", args="")},
            "schedulers": {},
            "db_tables": {"trades": {"kind": "table", "rows": 5, "size": "8 kB"},
                          "strat_features_1m": {"kind": "table", "rows": 3105422, "size": "4080 MB"}}}
    assert inv.runtime_relations(repo, live) == ["strat_features_1m"]
    out = inv.render_markdown("refs_digest", repo, live)
    rt = out.split("## Runtime-created relations")[1].split("## Hand-created")[0]
    assert "| `strat_features_1m` | table | 3,105,422 | 4080 MB |" in rt and "`trades`" not in rt
    hc = out.split("## Hand-created live jobs")[1]
    assert "| `gamma` | `gcp/helpers.py` | `trades` | — |" in hc
    assert "| `delta` | `gcp/gone.py` (not in this checkout) | — | — |" in hc
    assert "`alpha`" not in hc, "a declared job is not hand-created"
    # without a snapshot the sections say so, rather than silently listing nothing
    out = inv.render_markdown("refs_digest", repo, None)
    assert out.count("_no live snapshot supplied; not computable_") == 2


def test_restore_prints_only_the_names_of_the_blocks_it_rewrote(mini_repo, capsys):
    """The workflow captures `--restore` stdout and emits one `::warning::`
    per line. The CLI fell through to the inventory summary on that path, so
    an untouched document still produced three lines of warnings."""
    doc = mini_repo / "doc.md"
    doc.write_text("# t\n\n<!-- inventory:tables:start -->\nx\n<!-- inventory:tables:end -->\n")
    assert inv.main(["--root", str(mini_repo), "--insert", "doc.md"]) == 0
    capsys.readouterr()
    assert inv.main(["--root", str(mini_repo), "--restore", "doc.md"]) == 0
    assert capsys.readouterr().out == "", "an untouched document must print nothing"
    doc.write_text(doc.read_text().replace("| `trades` |", "| `trades_edited` |"))
    assert inv.main(["--root", str(mini_repo), "--restore", "doc.md"]) == 0
    assert capsys.readouterr().out == "restored inventory:tables in doc.md\n"
    assert "| `trades` |" in doc.read_text()


def test_the_fixture_digest_names_every_runtime_relation_and_hand_created_job():
    repo, refs = _repo_and_refs()
    live = json.loads(FIXTURE.read_text())
    out = inv.render_markdown("refs_digest", repo, live)
    for t in inv.runtime_relations(repo, live):
        assert f"| `{t}` |" in out, t
    for j in inv.reconcile(repo, live)["jobs_live_only"]:
        assert f"| `{j}` |" in out, j
    assert len(out) < 40_000, len(out)
