---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-10-feat-cicd-001-retire-arch-refresh.md
branch: feature/feat-cicd-001-retire-arch-refresh
pr: 1788
status: ready
---

# Retire the monthly architecture-doc refresh: implementation plan (F)

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans. Steps use `- [ ]`. Every task cites a spec section and the done_when items it
> moves, numbered 1 to 15 in the spec's order (1 = "Retired files (F)", 15 = "Source identity (SHARED-01)").

**Goal:** retire `refresh-architecture-docs.yml` and its re-run workflow, delete what only they used, and keep
the deterministic renderers as on-demand tools whose docs, gates and audits no longer assume a monthly job.

**Architecture:** two workflow renames, five source deletions and four retired test files, then the code that read them (`check_generated_docs.py`,
`docs_audit.py`, `doc_inventory.py`, `refresh_calibration_table.py`, `refresh_architecture_drawio.py`) loses its
workflow, prompt and cost-report paths; README's Maintenance section becomes the on-demand procedure. The
`docs/product/` half (05-a, 05-c, 05-d, 05-e, 05, 09, manual README, the registry) is the records PR D, which
has no plan (the gate refuses a plan naming a `docs/` branch, and a documentation-only `docs/` change needs none;
D's PR body carries its checklist) and merges before F is marked ready.

**Tech Stack:** Python 3.11, pytest, git. The two workflow files are renamed, never executed.

**Spec:** `docs/superpowers/specs/2026-11-10-feat-cicd-001-retire-arch-refresh.md` (approved; lands with
stocks#1777). Read it beside this plan: its Design tables are the file-by-file contract this plan cites.

## Binding and sequence

- Cut this branch from `origin/main` after #1777 merges (the gate reads the approved spec from the merge base).
  Line anchors below are main `4f552e93`; re-read each one on the fork commit and on every merge of main, and
  locate edits by the quoted content, never by number alone.
- D (`docs/retire-arch-refresh-records`, no plan) merges first. F is opened as a draft (Task 1) and stays a draft
  while D is open; a draft draws no Codex review.
- F lands after stocks#1384 (open draft, head `2215223a`): both change `refresh_architecture_drawio.py`, both
  diagrams and `tests/scripts/test_refresh_architecture_drawio.py`, and #1384 edits
  `scripts/maintenance/render_doc_prompts.py`, which F deletes. #1384 also moves the drawio test's `SNAPSHOT` to
  `tests/fixtures/live_gcp_snapshot_2026-11-09.json`; every drawio check below uses whatever `SNAPSHOT` names at
  F's merge base, never a literal date.
- stocks#1775 (draft, FEAT-CICD-001 architecture export) adds `.github/workflows/architecture-export.yml`, edits
  the same two `Architecture.drawio` cells to "(11 workflows)", the FEAT-CICD-001 catalog and traceability
  records, and `doc_inventory.py`; #1778 (draft spec) gives it a SHARED-01 note. Whichever lands second merges
  the other's lines and keeps them; the workflow count is always `len(active_workflows())` on F's head.
- The ready push (Task 10) is one push: the merge of main that brings D (and #1384), the SHARED-01 note, the
  sidecar, the ticked body. Nothing is pushed between it and the Ready transition.

## Global Constraints

- No gate file changes: the F diff leaves `scripts/gate/` (pinned copies included), `.githooks/pre-commit`,
  `.github/workflows/spec-gate.yml`, `.github/workflows/registry-check.yml`, `tests/scripts/test_spec_gate.py`
  and `tests/scripts/test_export_model_registry.py` byte-identical. No red-team pass applies.
- The workflow count is derived (`refresh_architecture_drawio.active_workflows()`), never hard-coded in a test.
- F changes renderer inputs (`doc_inventory.py`, `check_generated_docs.py`, `tests/scripts/test_check_generated_docs.py`,
  spec_gate.py `RENDER_INPUTS`), so F carries no change to 05-a, 05-c or 05-e, and touches `docs/product/` only in
  the FEAT-CICD-001 catalog record, its traceability entry and the FEAT-CICD-001 / SHARED-01 SITE row.
- PATTERN, verbatim, case-insensitive (spec, done_when 3):
  `refresh-architecture-docs|rerun-transient-doc-refresh|monthly (architecture |documentation |doc )?(doc )?refresh|(re)?generated monthly|auto-refreshed monthly|on the 1st of (each|every) month|1st of month 06:00`
- The spec path string, wherever a header or test names it: `docs/superpowers/specs/2026-11-10-feat-cicd-001-retire-arch-refresh.md`.
- The calibration footer, byte for byte: ``_Manual refresh: `python -m scripts.refresh_calibration_table` (needs Cloud SQL access; not scheduled)._``
- README Maintenance commands, byte for byte (spec, "The on-demand procedure"):
  1. `python -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --insert docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  2. `python -m pytest tests/scripts/test_check_generated_docs.py tests/scripts/test_refresh_architecture_drawio.py -k committed`
  3. `python -m scripts.refresh_calibration_table`
- New prose in README.md, SETUP.md and `.github/workflows/README.md` states no new count, schedule or service
  name: `scripts/verify_docs_against_live.py` reads all three every weekday against live GCP.
- No Class A or D document may cite a retired file by a slashed path or link (`docs_audit.py` resolves backticked
  slashed paths and links; a bare `refresh-architecture-docs.yml` is not resolved).
- `docs_audit.py` and `doc_source_snapshot.py` run only from a non-shallow clone. Executed here: in the shallow
  `/home/user/stocks`, `docs_audit.py --no-owning-job-check --json` exited 2 with
  `committed-source repository admission failed: unsupported shallow repository`.
- New test names avoid the word `committed`, so README step 2 keeps selecting the same four tests.
- Every new test in this plan was run as written against main `4f552e93` (fixtures imported from the repository's
  own test modules, nothing in the tree changed): `31 failed, 7 passed`. The seven are the guards each task names
  (`test_the_check_without_cloud_sql_exits_2`, `test_what_the_spec_gate_imports_is_unchanged`,
  `test_the_cli_runs_clean_on_the_repository_docs`) and the `cites` parameters for the workflows README, 09, 05-c
  and 05-e, which already comply. The green side of each test has not been executed: no implementation exists.
- Before every commit: `python3 scripts/gate/spec_gate.py --commit`. Conventional commit messages.
- Until D merges, these are red on F by design and nowhere else: `test_committed_docs_pass_every_gate` (05-a's dead
  link to the renamed workflow), `test_the_cli_runs_clean_on_the_repository_docs` (same finding),
  `tests/meta/test_model_registry_consistency.py::test_product_docs_have_no_dead_relative_links`
  (05-INFRASTRUCTURE's link), and the D-owned parameters of `test_no_maintenance_doc_claims_a_scheduled_refresh`
  and `test_no_living_doc_cites_a_retired_file`. Executed in a scratch export of `4f552e93` with only the renames
  and deletions applied: `gate.run` over the committed docs reported exactly two findings, README's and 05-a's dead
  links to the renamed workflow (README's goes in Task 7, before the renames), and `tests/meta` gave
  `1 failed, 126 passed`, the failure being 05-INFRASTRUCTURE's link.

## Review Focus

1. A living document that still cites a retired file by slashed path or link (README, SETUP, the workflows README,
   INVESTMENT_MODELS_SUMMARY; D's 05-a, 05-INFRASTRUCTURE and registry) becomes a `dead-link` P2 the moment F
   renames or deletes the file, so the matched audit gains findings main lacks. Expected: none. Test:
   `test_no_living_doc_cites_a_retired_file` (Task 7).
2. The weekday `verify-docs-against-live.yml` reads README, SETUP and the workflows README; a count, schedule or
   service name written into the new prose turns the live check red after merge. Expected: no new verifier
   finding. Check: one live snapshot, verifier run over main and over F's head, outputs diffed (Task 10).
3. `python -m scripts.maintenance.check_generated_docs` (its CLI, whose only scheduled caller was the workflow)
   must still run clean on the committed documents with the cost and prompt gates gone. Expected: exit 0. Test:
   `test_the_cli_runs_clean_on_the_repository_docs` (Task 4).
4. The merge of main that brings #1384 (and #1775 if first) re-introduces `doc refresh`, the workflow name or a
   stale count in a drawio cell or REPLACEMENTS target, or revives `render_doc_prompts.py` through a
   modify/delete conflict. Expected: the merged head still has none. Tests: `test_no_label_names_the_retired_refresh`,
   `test_the_monthly_refresh_is_retired` and `--check` at the merge base's `SNAPSHOT`, re-run in Task 10.
5. A matched audit dated on or after 2026-12-29 (180 days past the table's 2026-07-01) carries the calibration P2
   on both sides with different detail text (F rewords it), so a detail-keyed diff shows one NEW and one GONE.
   Expected: read as the same finding reworded, not a regression. Test: the 181/180-day test (Task 5); Task 10
   records the audit date beside the diff.

---

## Task 1: bind the plan and open the draft
Spec: § Design, "Two PRs, in this order" (sequence step 1). Advances done_when 14.

**Files:** Create `docs/superpowers/plans/2026-11-10-feat-cicd-001-retire-arch-refresh.md` (this file, `pr: null`).

No behaviour changes here, so no test; the gate is the check.

- [ ] `git fetch origin && git checkout -b feature/feat-cicd-001-retire-arch-refresh origin/main`; confirm
      `git show origin/main:docs/superpowers/specs/2026-11-10-feat-cicd-001-retire-arch-refresh.md | grep -x 'status: approved'`.
- [ ] Stage the plan alone; `python3 scripts/gate/spec_gate.py --commit` prints `spec gate ok`; commit
      `docs(plan): FEAT-CICD-001 retire the monthly architecture refresh`.
- [ ] Push; open a draft PR titled `FEAT-CICD-001: retire the monthly architecture-doc refresh, keep the renderers on demand`.
      Body: the spec and plan paths; all fifteen done_when items as `- [ ]` lines, each starting with the item's
      text; `Closes #1118`; a Capacity section reading `n/a: this removes one monthly workflow and the re-run
      workflow that followed its failures, and adds no job, query, schedule or cloud call`;
      `Canvas check pending (report-only): https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN`; one line saying
      the draft waits for D and #1384.
- [ ] Commit `pr: <number>` in this plan, push. Check: `PR_NUMBER=<n> PR_DRAFT=true PR_TITLE='<title>' PR_BODY="$(cat body.md)" python3 scripts/gate/spec_gate.py --pr origin/main` prints `spec gate ok`.

## Task 2: the calibration footer (#1118)
Spec: § F: what changes, "`scripts/refresh_calibration_table.py` and its test (#1118)". Advances done_when 7.

**Files:**
- Modify: `scripts/refresh_calibration_table.py` (docstring line 20 "Auto-invoked monthly by ..."; footer in `_build_markdown`, lines 146 to 149)
- Modify: `docs/INVESTMENT_MODELS_SUMMARY.md:326` (the footer line inside `ticker_calibration_resolved_values`)
- Test: `tests/scripts/test_refresh_calibration_table.py`

**Interfaces:** Produces the footer line Task 7's claims test reads in `docs/INVESTMENT_MODELS_SUMMARY.md`.

- [ ] **Write the tests** (add `import os, subprocess, sys` and `from pathlib import Path`; `REPO = Path(__file__).resolve().parents[2]`):

```python
FOOTER = "_Manual refresh: `python -m scripts.refresh_calibration_table` (needs Cloud SQL access; not scheduled)._"

def test_the_footer_names_the_manual_command_and_no_schedule():
    out = rct._build_markdown([_row("IWM"), _row("QQQ")])
    footer = out.rstrip("\n").splitlines()[-1]
    assert footer == FOOTER
    assert "python -m scripts.refresh_calibration_table" in footer
    assert "monthly" not in footer.lower() and "refresh-architecture-docs" not in footer

def test_the_doc_footer_equals_the_rendered_one():
    doc = (REPO / "docs/INVESTMENT_MODELS_SUMMARY.md").read_text(encoding="utf-8")
    region = doc.split(rct.BEGIN_MARK, 1)[1].split(rct.END_MARK, 1)[0]
    assert region.rstrip("\n").splitlines()[-1] == FOOTER

def test_the_check_without_cloud_sql_exits_2():
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLOUD_SQL_CONNECTION_NAME", "DB_HOST", "DB_USER", "DB_PASS", "DB_NAME")}
    r = subprocess.run([sys.executable, "-m", "scripts.refresh_calibration_table", "--check"],
                       cwd=REPO, env=env, capture_output=True, text=True)
    assert r.returncode == 2, r.stderr
```

- [ ] Run `python3 -m pytest tests/scripts/test_refresh_calibration_table.py -q`. Expected: 2 failed (the two
      footer tests: main's footer says "Auto-refreshed monthly by `.github/workflows/refresh-architecture-docs.yml`");
      the exit-2 test passes on main (executed: `--check` without the variables logged `Cloud SQL env vars
      missing — aborting.`, rc 2) and stays as a guard.
- [ ] Set the footer in `_build_markdown` to `FOOTER`'s text (the blank line before it stays), drop "Auto-invoked
      monthly by ..." from the docstring (keep the two manual commands), and set line 326 of the doc to the same
      bytes. The rest of the region is untouched: it is Cloud SQL output and cannot be re-rendered here.
- [ ] Run the same command. Expected: all pass.
- [ ] Commit `fix(calibration): label the resolved-values table a manual refresh (#1118)`.

## Task 3: README badges
Spec: § F: what changes, "`scripts/maintenance/doc_inventory.py`" (badge half). Advances done_when 6.

**Files:**
- Modify: `scripts/maintenance/doc_inventory.py`: `readme_badges` (line 4202) stops emitting lines 4241 to 4242;
  its docstring and the comment at 4176 say four badges; `OWNED_BADGE` (4183 to 4199) is unchanged so a render
  over an old README still claims and removes the workflow badge.
- Modify: `README.md:11` (delete the `![Architecture refresh](...)` line).
- Test: `tests/scripts/test_check_generated_docs.py`

- [ ] **Write the test and update four** (`repo` and `live` are the file's fixtures):

```python
def test_the_readme_carries_no_workflow_badge(tmp_path, repo, live):
    lines = inv.readme_badges(repo, live, "2026-11-02").split("\n")
    assert len(lines) == 4 and all("](https://img.shields.io/badge/" in l for l in lines), lines
    assert not any("/actions/workflows/" in l for l in lines)
    readme = tmp_path / "README.md"
    readme.write_text(_readme_with())                    # still carries the Architecture refresh badge
    inv.insert_readme_badges(readme, repo, live, "2026-11-02")
    assert "/actions/workflows/" not in readme.read_text()
    assert "/actions/workflows/" not in (REPO / "README.md").read_text(encoding="utf-8")
```

  In `test_the_readme_badges_are_rendered_not_asked_for` replace the badge and `.exists()` assertions with
  `assert "/actions/workflows/" not in body`; in `test_the_badge_render_does_not_swallow_later_shield_links` and
  `test_a_maintainer_badge_beside_the_block_survives` the count of `refresh-architecture-docs.yml/badge.svg`
  becomes `== 0`; in `test_a_dead_workflow_badge_is_replaced_not_duplicated` the last assertion becomes
  `body.count("/actions/workflows/") == 0` ("the dead badge is removed, not replaced"). `_readme_with` keeps its
  five lines (it models a README rendered before F); its docstring says so.
- [ ] Run `python3 -m pytest tests/scripts/test_check_generated_docs.py -q -k badge`. Expected: these 5 fail.
      (Executed in reverse in a scratch export: with the renderer change and the old tests, exactly the four
      updated tests failed, `4 failed, 14 passed`.)
- [ ] Remove the badge from `readme_badges`, update its docstring and the 4176 comment, delete README line 11.
- [ ] Run the same command, then `python3 -m pytest tests/scripts/test_doc_inventory.py -q`. Expected: all pass.
- [ ] Commit `feat(docs): stop rendering the architecture-refresh workflow badge`.

## Task 4: generated-doc gates without the cost report
Spec: § F: what changes, "`scripts/maintenance/check_generated_docs.py` and its test". Advances done_when 5.

**Files:**
- Modify: `scripts/maintenance/check_generated_docs.py`: `COST` leaves `DOCS` (73), `MODEL_DOCS` (79), `REGENERATED`
  (110, becomes `()`) and `CHURN_EXEMPT` (154, becomes `()`), so `DIFF_DOCS` (155) follows; delete
  `_promised_sections`, `gate_regenerated_structure` (734 to 773) and `gate_cost_content` with what only it uses
  (776 to 1021: `COST_FIGURE`, `COST_BARE`, `_STYLE`, `_unstyle`, `COST_USD_PROSE`, `MONEY_HEADER`,
  `cost_figures`, `COST_REC`, the four `COST_MIN_*`, `_numbered_sections`, the unused `TABLE_SEP`, `_table_rows`);
  keep `TABLE_SEP_CELL`, `_table_cells` and `_is_table_sep` (`gate_inline_rule` calls it at 571); remove the two
  calls in `run()` (1473 to 1474); keep `COST`, `BYTE_FLOOR`, `README_REQUIRED_LINKS`, `REMOVED_HEADING`,
  `EXPECTED_MARKERS`, `_MARKER_LINE`. Rewrite the module docstring (lines 1 to 45: no workflow, no
  `refresh-inputs`, no structure bullet), the comments at 98 to 109 and 116 to 153 that justify the cost
  exemptions, the `.github/prompts/readme.md` comment at 180, and the 571 to 578 comment naming `TABLE_SEP` and
  `_table_rows`.
- Test: `tests/scripts/test_check_generated_docs.py`

- [ ] **Write the tests:**

```python
def test_the_cost_report_is_no_generated_document():
    for name in ("DOCS", "MODEL_DOCS", "DIFF_DOCS", "REGENERATED", "CHURN_EXEMPT"):
        assert gate.COST not in getattr(gate, name), name
    for name in ("gate_regenerated_structure", "gate_cost_content"):
        assert not hasattr(gate, name), name
    assert ".github/prompts" not in (REPO / "scripts/maintenance/check_generated_docs.py").read_text(encoding="utf-8")

def test_what_the_spec_gate_imports_is_unchanged():
    # main 4f552e93's values; spec_gate.py reads EXPECTED_MARKERS and _MARKER_LINE (4043 to 4047, 4196 to 4198)
    infra = "docs/product/infrastructure"
    assert gate.README_REQUIRED_LINKS == (
        f"{infra}/05-a-ARCHITECTURE.md", f"{infra}/05-c-DATA_DEPENDENCIES.md", f"{infra}/05-d-COST_ANALYSIS.md",
        "RUNBOOK.md", f"{infra}/05-b-ERD.md", f"{infra}/05-f-PIPELINE.md", f"{infra}/05-g-DATA_PIPELINE.md",
        f"{infra}/05-e-API.md", f"{infra}/05-i-GCP_IMPLEMENTATION_GUIDE.md", "docs/product/README.md",
        "docs/audits/", "gcp/cloudbuild/README.md", "CLAUDE.md", "SETUP.md")
    assert gate.EXPECTED_MARKERS == {
        f"{infra}/05-a-ARCHITECTURE.md": ("jobs", "schedulers", "tables", "dbtables", "routes", "services", "reconcile", "modules"),
        f"{infra}/05-c-DATA_DEPENDENCIES.md": ("tables", "dbtables", "writes", "reads", "multiwriter", "orphans", "blast", "graph"),
        f"{infra}/05-e-API.md": ("routers", "routes")}
    assert gate._MARKER_LINE.pattern == r"^\s*<!--\s*inventory:[A-Za-z0-9_]+:(start|end)\s*-->\s*$"

def test_the_cli_runs_clean_on_the_repository_docs():
    r = subprocess.run([sys.executable, "-m", "scripts.maintenance.check_generated_docs",
                        "--snapshot", str(SNAPSHOT)], cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:]
```

  The literals are main `4f552e93`'s, printed by `python3 -c "from scripts.maintenance import check_generated_docs as g; print(g.README_REQUIRED_LINKS, g.EXPECTED_MARKERS)"`; re-print them on the fork commit and stop if they differ.
- [ ] Run `python3 -m pytest tests/scripts/test_check_generated_docs.py -q -k "no_generated_document or spec_gate_imports or cli_runs_clean"`.
      Expected: `test_the_cost_report_is_no_generated_document` fails; the other two pass on main (guards).
- [ ] Make the source change. In the same commit delete the tests of the deleted code and `_cost_pair` (it copies
      `.github/prompts/cost-analysis.md`): `test_a_regenerated_cost_report_may_change_its_data_bearing_headings`,
      `test_a_regenerated_doc_is_measured_in_bytes_not_lines`, `test_a_regenerated_doc_must_carry_every_section_its_prompt_promises`,
      `test_the_cost_report_is_exempt_from_the_churn_ceiling`, `test_an_emptied_cost_report_is_still_caught_without_the_ceiling`,
      `test_the_whole_heading_must_match_not_a_prefix_of_it`, `test_prose_shaped_like_a_cost_report_is_a_finding`,
      `test_every_real_version_of_the_cost_report_passes_the_content_floors`, `test_a_heading_with_nothing_under_it_is_a_finding`,
      `test_a_recommendation_heading_stays_inside_section_five`, `test_a_table_without_outer_pipes_still_counts`,
      `test_only_monetary_values_count_toward_the_cost_floor`, `test_a_bare_decimal_in_a_money_cell_counts_as_a_cost_figure`,
      `test_pipe_shaped_prose_is_not_a_table`, `test_a_delimiter_row_needs_hyphens_in_every_cell`,
      `test_a_bare_amount_counts_in_any_cell_and_in_the_usd_form`, `test_a_row_may_omit_its_trailing_cells`,
      `test_a_bare_decimal_counts_only_under_a_money_column`, `test_one_amount_written_two_ways_counts_once`,
      `test_an_emphasised_amount_still_counts`, `test_the_bare_amount_pattern_accepts_what_the_csv_emits`,
      `test_a_generic_total_header_is_not_a_money_column`, `test_an_escaped_pipe_is_content_not_a_column` (24 tests,
      found by an `ast` scan for `gate.<deleted name>` plus a run with `COST` removed). Edit four that read `COST`
      as a gated document: `test_the_other_documents_keep_heading_persistence` copies `DOCS` into `root` and
      `previous` itself instead of calling `_cost_pair`; `test_every_other_document_still_has_a_churn_ceiling`
      asserts `gate.CHURN_EXEMPT == ()`; `test_diff_stats_report_names_what_moved` appends its section to
      `gate.ARCH` and reads the `gate.ARCH` row; `test_the_2026_09_02_regeneration_would_have_been_stopped` drops
      the `COST_ANALYSIS.md` pair (it skips where `b3b5271` is absent, as in this session's shallow clone, so it was
      not executed here).
- [ ] Run `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` (expected: all pass; the prompts and
      workflow still exist at this point) and `python3 -m pytest tests/scripts/test_spec_gate.py -q` (expected:
      passes unchanged).
- [ ] Commit `refactor(docs): drop the cost-report and prompt gates from check_generated_docs`.

## Task 5: docs audit without the Class A delivery audit
Spec: § F: what changes, "`scripts/maintenance/docs_audit.py` and `tests/scripts/test_docs_audit.py`" and "What docs_audit reports after F". Advances done_when 4.

**Files:**
- Modify: `scripts/maintenance/docs_audit.py`: delete 6737 to 6857 (`OWNING_JOB`, `GENERATED_RE`, `PR_PAGE_SIZE`,
  `PR_PAGE_LIMIT`, `fetch_owned_prs`), 6966 to 7210 (`DRY_RUN_MARKER`, `DELIVERING_MARKER`, `_run_delivered`,
  `_is_dry_run`, `_is_ambiguous`, `RUNS_PAGE_SIZE`, `RUNS_PAGE_LIMIT`, `fetch_owning_runs`, `_REFRESH_GEN_RE`,
  `_refresh_generation`, `superseded`, `last_delivering_conclusion`) and 7258 to 7469 (`visible_generated_stamps`,
  `check_owning_job`); keep `TOP_LEVEL_DIRS`, `BEST_EFFORT_ARTIFACTS`, `region_text`, `check_best_effort_artifacts`,
  `symlinked_component`, `refuse_symlink`. In `main()`: the `--no-owning-job-check` help (7480 to 7481) says the
  flag is accepted and ignored since the delivery audit's retirement on 2026-11-10; delete 7687 to 7693 (the flag
  test and the call). `region_owner` (2619) returns the new `GENERATED_OWNER` for `"generated"`. Reword the
  docstring lines 10 and 39, the comments at 1755, 6859 to 6872, 7499, 7684 to 7685 and 7804, and the three
  `check_best_effort_artifacts` details that cite a best-effort workflow step or a refresh PR.
- Test: `tests/scripts/test_docs_audit.py`

**Interfaces:** Produces `GENERATED_OWNER = "its renderer: scripts/maintenance/doc_inventory.py, scripts/refresh_calibration_table.py, scripts/maintenance/refresh_architecture_drawio.py or scripts/gate/export_model_registry.py (docs/DOC_REGISTRY.md names which)"`
and `BEST_EFFORT_ARTIFACTS[0]["refresher"] == "python -m scripts.refresh_calibration_table"` (the stale detail names it through `refresher`).

- [ ] **Write the tests** (module imports `datetime`, `json`; `audit_repo`, `_commit`, `CAL_REGION` exist):

```python
def test_the_class_a_delivery_audit_is_retired():
    for name in ("OWNING_JOB", "check_owning_job", "fetch_owning_runs", "fetch_owned_prs",
                 "DRY_RUN_MARKER", "DELIVERING_MARKER"):
        assert not hasattr(m, name), name
    assert "refresh-architecture-docs" not in (REPO_ROOT / "scripts/maintenance/docs_audit.py").read_text(encoding="utf-8")

def test_the_retired_owning_job_flag_is_accepted_and_changes_nothing(audit_repo, capsys, monkeypatch):
    calls, real = [], m.run
    monkeypatch.setattr(m, "run", lambda cmd, **kw: calls.append(" ".join(cmd)) or (real(cmd, **kw) if cmd[0] == "git" else ""))
    (audit_repo / "docs" / "d.md").write_text("# D\n\nbody\n")
    _commit(audit_repo, "tree")
    argv = ["--json", "--date", "2026-09-18", "--issues-snapshot", str(audit_repo / "issues.json")]
    reports = []
    for extra in (["--no-owning-job-check"], []):
        m.main(argv + extra)
        reports.append(json.loads(capsys.readouterr().out)["findings"])
    assert reports[0] == reports[1]
    assert not [c for c in calls if "actions/workflows" in c], calls

def test_a_generated_region_is_routed_to_its_renderer():
    owner = m.region_owner("generated", None)
    for renderer in ("doc_inventory", "refresh_calibration_table", "refresh_architecture_drawio", "export_model_registry"):
        assert renderer in owner, owner
    assert "workflow" not in owner and ".yml" not in owner

def test_the_calibration_staleness_finding_names_the_manual_command(audit_repo):
    art = [dict(m.BEST_EFFORT_ARTIFACTS[0], doc="docs/cal.md", region="cal")]   # the registered bound and regex
    today = datetime.date(2026, 9, 18)
    found = {}
    for days in (181, 180):
        (audit_repo / "docs" / "cal.md").write_text(CAL_REGION.format((today - datetime.timedelta(days=days)).isoformat()))
        found[days] = m.check_best_effort_artifacts(today.isoformat(), artifacts=art)
    assert found[180] == []
    assert [(f["check"], f["severity"]) for f in found[181]] == [("class-a", "P2")]
    detail = found[181][0]["detail"]
    assert "python -m scripts.refresh_calibration_table" in detail
    assert "workflow" not in detail.lower() and ".yml" not in detail and "refresh PR" not in detail
```

  (181 days before 2026-09-18 is 2026-03-21, 180 is 2026-03-22; executed with `datetime`.)
- [ ] Run `python3 -m pytest tests/scripts/test_docs_audit.py -q -k "delivery_audit_is_retired or retired_owning_job_flag or routed_to_its_renderer or names_the_manual_command"`.
      Expected: 4 failed (the flagless run reaches `check_owning_job`, whose faked GitHub read returns nothing).
- [ ] Make the source change. In the same commit edit `tests/scripts/test_docs_audit.py` by this scan, run on the
      fork commit (on 4f552e93 it prints 51 top-level names: 48 tests, `LIVE_TITLE`, `DRY_TITLE`, `_owning_doc`):

```python
import ast
names = {"OWNING_JOB", "GENERATED_RE", "PR_PAGE_SIZE", "PR_PAGE_LIMIT", "fetch_owned_prs", "DRY_RUN_MARKER",
         "DELIVERING_MARKER", "_run_delivered", "_is_dry_run", "_is_ambiguous", "RUNS_PAGE_SIZE", "RUNS_PAGE_LIMIT",
         "fetch_owning_runs", "_REFRESH_GEN_RE", "_refresh_generation", "superseded", "last_delivering_conclusion",
         "visible_generated_stamps", "check_owning_job"}
tree = ast.parse(open("tests/scripts/test_docs_audit.py").read())
uses = lambda n: any(isinstance(s, ast.Attribute) and getattr(s.value, "id", "") == "m" and s.attr in names for s in ast.walk(n))
for n in tree.body:
    if isinstance(n, (ast.FunctionDef, ast.Assign)) and uses(n):
        print(n.lineno, getattr(n, "name", None) or n.targets[0].id)
```

      Delete every name it prints except `test_plain_output_names_the_region_and_its_owner` and
      `test_the_region_owner_is_carried_in_json_too`, which now expect `m.GENERATED_OWNER`; also delete
      `test_the_owning_job_check_is_not_disabled_by_the_issues_snapshot` (2486; it asserts the flagless run calls
      GitHub) and the helpers only the deleted tests use: `_RUN_NAME` and `AMBIGUOUS_TITLE` (46, 49, with the
      comment at 38 to 45), `_pr_pages` (2638), `_filler` (2675). That is 47 tests. Keep
      `test_the_owning_job_check_can_still_be_turned_off` (2516) unchanged. Until `LIVE_TITLE` goes, collection
      fails at import (it reads `m.DELIVERING_MARKER`).
- [ ] Run `python3 -m pytest tests/scripts/test_docs_audit.py tests/scripts/test_doc_source_snapshot.py -q`.
      Expected: all pass, `test_doc_source_snapshot.py` unchanged (it passes `--no-owning-job-check` at 183 and 426).
- [ ] Commit `refactor(docs-audit): retire the Class A delivery audit, route generated regions to their renderers`.

## Task 6: diagram labels
Spec: § F: what changes, "Diagrams" (labels). Advances done_when 8.

**Files:**
- Modify: `scripts/maintenance/refresh_architecture_drawio.py`: the two REPLACEMENTS targets ending "docs-vs-live
  check, monthly doc refresh;\nAPI + schema deploys" (59, 61) drop ", monthly doc refresh"; the target "⑩ GitHub
  Actions (5 workflows) and Cloud Build (3 triggers) — CI, deploys, bridges, doc refresh" (75) ends "— CI, deploys,
  bridges, docs-vs-live check"; the tuple whose target begins `refresh-architecture-docs.yml (monthly:` (74) is
  deleted (its source text occurs in neither diagram: `grep -c` 0 for both, executed); both `gha_label` forms in
  `refresh_main` (264, 266) drop ", doc refresh"; the `ICON_COUNT_TEMPLATES` target "6 workflows: CI · deploys ·
  bridges · docs check · doc refresh" (362) drops " · doc refresh".
- Modify: `Architecture.drawio` cells `ext_gh` (43) and `gha_group` (268) to the same text (counts untouched here),
  `gha_other` (292) loses its first line `refresh-architecture-docs.yml (monthly: ...)&#10;`;
  `Architecture-icons.drawio` cell `g_cicd` (549) becomes `GitHub Actions  (N workflows: CI · deploys · bridges · docs check)`.
- Test: `tests/scripts/test_refresh_architecture_drawio.py`

- [ ] **Write the test:**

```python
RETIRED_LABELS = ("refresh-architecture-docs", "doc refresh")

def test_no_label_names_the_retired_refresh(live):
    main = {c.get("id"): c.get("value") or "" for c in ET.parse(dw.MAIN).getroot().iter("mxCell")}
    icons = {c.get("id"): c.get("value") or "" for c in ET.parse(dw.ICONS).getroot().iter("mxCell")}
    texts = [main["ext_gh"], main["gha_group"], main["gha_other"], icons["g_cicd"]]
    texts += [new for _, new in dw.REPLACEMENTS] + [tpl for _, tpl in dw.ICON_COUNT_TEMPLATES]
    for snapshot in (live, {k: v for k, v in live.items() if k != "_workflows"}):   # both gha_label forms
        root = ET.parse(dw.MAIN).getroot()
        dw.refresh_main(root, snapshot)
        texts.append(_cell(root, dw.GHA_GROUP_ID).get("value"))
    for text in texts:
        assert not any(r in text.lower() for r in RETIRED_LABELS), text
```

  (`refresh_main` over a parsed copy with and without `_workflows` was executed on main: it sets `gha_group` to
  each `gha_label` form. On main the test collects 11 offending texts, exactly the 11 edits below. If #1384's merge
  changes `refresh_main`'s signature, Task 10 calls it as the merged code requires; the assertion stays.)
- [ ] Run `python3 -m pytest tests/scripts/test_refresh_architecture_drawio.py -q -k retired_refresh`. Expected: FAIL.
- [ ] Make the edits; keep every count as it is.
- [ ] Run `python3 -m pytest tests/scripts/test_refresh_architecture_drawio.py -q` and
      `python3 scripts/maintenance/refresh_architecture_drawio.py --check --snapshot "$SNAP"` with
      `SNAP=$(python3 -c "from tests.scripts.test_refresh_architecture_drawio import SNAPSHOT; print(SNAPSHOT.relative_to(SNAPSHOT.parents[2]))")`.
      Expected: all pass; `drawio check: 0 problem(s)` (executed on main with that `SNAP`, `tests/fixtures/live_gcp_snapshot_2026-09-07.json`).
- [ ] Commit `fix(diagrams): drop the retired doc refresh from the GitHub Actions labels`.

## Task 7: maintenance docs, comments and the claims tests
Spec: § F: what changes, "Non-product docs and comments" and the `doc_inventory.py` strings; § The on-demand procedure; PATTERN. Advances done_when 3 and 9.

**Files:**
- Modify: `README.md`: 13 (badges show the 2026-09-07 snapshot, not refreshed on a schedule), 21 (05-d: dated
  record of 2026-09-02 billing data), 26 (05-e: rendered from the router files on each PR that changes them), 31
  (SETUP: one-time Workload Identity Federation setup for `deploy-staging.yml` and `verify-docs-against-live.yml`),
  38 (point at Maintenance step 1), 42 to 55 (the new Maintenance section, below), heading 57 renamed
  `## Moved and removed documents`, 66 becomes `Generated 2026-09-07 from the 2026-09-07 live snapshot. The audits
  behind these documents are in [`docs/audits/`](docs/audits).`
- Modify: `SETUP.md`: retitled to the Workload Identity Federation setup that `deploy-staging.yml` and
  `verify-docs-against-live.yml` use; remove the Vertex AI API, the five doc-refresh roles (`cloudasset.viewer`,
  `iam.securityReviewer`, `bigquery.dataViewer`, `bigquery.jobUser`, `aiplatform.user`), the dry run (§6), the
  Gemini model pin and Costs; one sentence records that the refresh it was written for was retired on 2026-11-10.
- Modify: `.github/workflows/README.md`: line 5 drops "and the monthly documentation refresh"; rows 16 and 17
  move to the Retired table as `refresh-architecture-docs.yml.disabled` and `rerun-transient-doc-refresh.yml.disabled`,
  "Replaced by" naming nothing; each of those lines contains the word `retired`.
- Modify: `.gitignore`: delete 196 to 204 (`!refresh-inputs/` block); keep `gha-creds-*.json` and reword 192 to
  name the retired `refresh-architecture-docs.yml.disabled`.
- Modify comments: `.github/workflows/deploy-staging.yml` 12, 44, 237; `verify-docs-against-live.yml` 46, 63;
  `update-superpowers.yml` 22, 158 name `refresh-architecture-docs.yml.disabled`, in the past tense.
- Modify: `scripts/maintenance/doc_inventory.py`: docstring line 6 (no workflow name), and the strings at 412,
  3686, 4267 ("the refresh workflow badge" becomes "the retired workflow badge"), 4380 lose "refresh workflow".
- Test: `tests/scripts/test_check_generated_docs.py`

README's Maintenance section says: the monthly refresh was retired on 2026-11-10 and nothing regenerates these
files on a schedule; every step is optional; step 1 is also enforced on each PR by the spec gate and the docs test;
then the three command groups in Global Constraints, step 1 noting the snapshot is the spec gate's
`RENDER_SNAPSHOT`, step 3 "from a machine with Cloud SQL access (not a 443-only sandbox)" with "or `--check` to
compare only"; then that the badges and the live-derived blocks show the 2026-09-07 snapshot, the diagram counts
the snapshot their test reads, and no tool on main refreshes them from live state. No drawio command, no other
fixture path.

- [ ] **Write the tests:**

```python
CLAIM = re.compile(r"refresh-architecture-docs|rerun-transient-doc-refresh|monthly (architecture |documentation |doc )?(doc )?refresh"
                   r"|(re)?generated monthly|auto-refreshed monthly|on the 1st of (each|every) month|1st of month 06:00", re.I)
RETIRE_WORD = re.compile(r"\bretire(?:d|ment)?\b", re.I)
CLAIM_DOCS = ("README.md", "SETUP.md", ".github/workflows/README.md", "docs/DOC_REGISTRY.md", "docs/INVESTMENT_MODELS_SUMMARY.md",
              "docs/product/05-INFRASTRUCTURE.md", "docs/product/09-SECURITY-AUTH.md", "docs/product/infrastructure/05-a-ARCHITECTURE.md",
              "docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md", "docs/product/infrastructure/05-e-API.md",
              "docs/product/infrastructure/manual/README.md")
RETIRED_PATH = re.compile(r"\.github/workflows/(?:refresh-architecture-docs|rerun-transient-doc-refresh)\.yml(?!\.disabled)"
                          r"|\.github/prompts/(?:architecture|cost-analysis|data-dependencies)\.md"
                          r"|\.github/scripts/is_transient_gemini_failure\.sh|scripts/maintenance/render_doc_prompts\.py")
STEPS = ("python -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --insert "
         "docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md "
         "docs/product/infrastructure/05-e-API.md",
         "python -m pytest tests/scripts/test_check_generated_docs.py tests/scripts/test_refresh_architecture_drawio.py -k committed",
         "python -m scripts.refresh_calibration_table")

@pytest.mark.parametrize("claim", CLAIM_DOCS + ("README specifics", "manual README title", "doc_inventory.py"))
def test_no_maintenance_doc_claims_a_scheduled_refresh(claim):
    if claim in CLAIM_DOCS:
        bad = [l for l in (REPO / claim).read_text(encoding="utf-8").splitlines() if CLAIM.search(l) and not RETIRE_WORD.search(l)]
        assert bad == [], bad
    elif claim == "README specifics":
        body = (REPO / "README.md").read_text(encoding="utf-8")
        assert not re.search(r"(?m)^#+\s*Removed since last refresh\s*$", body)
        assert "on each refresh" not in body and "on the 1st" not in body
        row = next(l for l in body.splitlines() if l.startswith("| [05-d-COST_ANALYSIS.md]"))
        assert "monthly" not in row.lower(), row
    elif claim == "manual README title":
        title = (REPO / "docs/product/infrastructure/manual/README.md").read_text(encoding="utf-8").splitlines()[0]
        assert "auto-refreshed" not in title.lower(), title
    else:
        src = (REPO / "scripts/maintenance/doc_inventory.py").read_text(encoding="utf-8")
        node = next(n for n in ast.parse(src).body if isinstance(n, ast.Assign)
                    and getattr(n.targets[0], "id", "") == "OWNED_BADGE")
        outside = src.splitlines()[:node.lineno - 1] + src.splitlines()[node.end_lineno:]
        assert not [l for l in outside if "refresh-architecture-docs" in l]
        assert not re.search(r"(?i)refresh workflow", src)

@pytest.mark.parametrize("doc", [d for d in CLAIM_DOCS if "/manual/" not in d])
def test_no_living_doc_cites_a_retired_file(doc):
    assert not RETIRED_PATH.findall((REPO / doc).read_text(encoding="utf-8"))

def test_the_readme_maintenance_section_is_the_on_demand_procedure():
    section = (REPO / "README.md").read_text(encoding="utf-8").split("\n## Maintenance\n", 1)[1].split("\n## ", 1)[0]
    assert RETIRE_WORD.search(section) and re.search(r"\boptional\b", section, re.I)
    assert re.findall(r"`(python3? -m [^`]+)`", section) == list(STEPS)
    assert "live_gcp_snapshot_" not in section.replace(STEPS[0], "")
```

  (Add `import ast`.)
- [ ] Run `python3 -m pytest tests/scripts/test_check_generated_docs.py -q -k "claims_a_scheduled_refresh or cites_a_retired_file or on_demand_procedure"`.
      Expected on this branch after Tasks 2 to 6: every `claims` parameter fails except
      `docs/INVESTMENT_MODELS_SUMMARY.md` (green since Task 2); `cites` fails for README, SETUP, DOC_REGISTRY,
      05-INFRASTRUCTURE and 05-a and passes for the workflows README, INVESTMENT_MODELS_SUMMARY, 09, 05-c and 05-e;
      the procedure test fails. (Executed on main with these exact tests: all 14 `claims` parameters failed, `cites`
      failed for those five plus INVESTMENT_MODELS_SUMMARY, the procedure test failed.)
- [ ] Make the README, SETUP, workflows README, `.gitignore`, workflow-comment and `doc_inventory.py` edits.
- [ ] Run the same command. Expected: the F-owned parameters pass (README, SETUP, workflows README,
      INVESTMENT_MODELS_SUMMARY, README specifics, doc_inventory.py) and the procedure test passes; the D-owned
      parameters (DOC_REGISTRY, 05-INFRASTRUCTURE, 09-SECURITY-AUTH, 05-a, 05-c, 05-e, manual README and its
      title) still fail and pass only after the Task 10 merge. Also
      `git grep -n -P 'refresh-architecture-docs\.yml(?!\.disabled)' -- '.github/workflows/*.yml'` prints only
      lines of `refresh-architecture-docs.yml` itself, which Task 8 renames out of the glob (executed on main: its
      lines 1084 and 1138 plus the seven comment lines).
- [ ] Commit `docs: describe the on-demand renderers and retire the monthly refresh wording`.

## Task 8: retire the files
Spec: § F: what is retired; § F: what changes, "Diagrams" (counts). Advances done_when 1, 2 and 8.

**Files:**
- Rename: `.github/workflows/refresh-architecture-docs.yml` to `...yml.disabled`, `.github/workflows/rerun-transient-doc-refresh.yml`
  to `...yml.disabled`; each gains a leading comment block (before `name:`) naming 2026-11-10 and the spec path,
  saying GitHub Actions runs only `*.yml`, and pointing at README "Maintenance" (the re-run file: retired with the
  refresh it re-ran). No count or run statistic in the header.
- Delete: `.github/prompts/architecture.md`, `cost-analysis.md`, `data-dependencies.md`;
  `.github/scripts/is_transient_gemini_failure.sh`; `scripts/maintenance/render_doc_prompts.py`;
  `tests/meta/test_refresh_architecture_docs_pr_token.py`, `test_refresh_open_pr_step.py`,
  `test_rerun_transient_doc_refresh.py`, `test_render_doc_prompts.py`.
- Move: `test_marker_names_agree_between_module_docs_and_gate` (in `tests/meta/test_refresh_architecture_docs_pr_token.py`
  at 196 to 208 on 4f552e93, not in `test_render_doc_prompts.py`) into `tests/scripts/test_check_generated_docs.py`,
  body unchanged (it reads only `REPO`, which that file defines identically).
- Modify: the counts in `Architecture.drawio` cells `ext_gh`, `gha_group` and `Architecture-icons.drawio` `g_cicd`
  to `len(active_workflows())` on this head (8 on 4f552e93 after the renames, executed; 9 once #1775 has landed).
- Test: `tests/scripts/test_check_generated_docs.py`

- [ ] **Write the test** (add `import itertools`; `SPEC_PATH` is the Global Constraints string):

```python
def test_the_monthly_refresh_is_retired():
    wf = REPO / ".github/workflows"
    for name in ("refresh-architecture-docs.yml", "rerun-transient-doc-refresh.yml"):
        assert not (wf / name).exists(), name
        lines = (wf / f"{name}.disabled").read_text(encoding="utf-8").splitlines()
        assert lines and lines[0].startswith("#"), name
        header = "\n".join(itertools.takewhile(lambda l: l.startswith("#"), lines))
        assert "2026-11-10" in header and SPEC_PATH in header, header
    prompts = REPO / ".github/prompts"
    assert not (prompts.exists() and any(p.is_file() for p in prompts.rglob("*")))
    assert not (REPO / ".github/scripts/is_transient_gemini_failure.sh").exists()
    assert not (REPO / "scripts/maintenance/render_doc_prompts.py").exists()
```

- [ ] Run `python3 -m pytest "tests/scripts/test_check_generated_docs.py::test_the_monthly_refresh_is_retired" -q`. Expected: FAIL.
- [ ] `git mv` the two workflows, add the headers, `git rm` the eight files, move the test, set the three counts.
- [ ] Run, expecting pass: the new test; `python3 -m pytest "tests/scripts/test_check_generated_docs.py::test_marker_names_agree_between_module_docs_and_gate" -q`;
      the body check below, which prints `body unchanged 13 lines` (executed on main with the old file on both sides);

```python
import ast, subprocess
def body(src):
    n = next(n for n in ast.parse(src).body if getattr(n, "name", "") == "test_marker_names_agree_between_module_docs_and_gate")
    return ast.get_source_segment(src, n)
old = subprocess.run(["git", "show", "origin/main:tests/meta/test_refresh_architecture_docs_pr_token.py"],
                     capture_output=True, text=True, check=True).stdout
new = open("tests/scripts/test_check_generated_docs.py").read()
assert body(old) == body(new); print("body unchanged", len(body(old).splitlines()), "lines")
```

      `python3 -m pytest tests/scripts/test_refresh_architecture_drawio.py -q`
      (with the renames and old counts, four failed in the scratch export: the committed-diagram, stale-workflow-count,
      count-tracks-the-repo and service-account tests); `--check --snapshot "$SNAP"`, `drawio check: 0 problem(s)`
      (executed before the counts moved: `cell ext_gh says 10 workflows, live is 8` and the same for `gha_group`).
- [ ] Run `python3 -m pytest tests/meta tests/scripts/test_check_generated_docs.py tests/scripts/test_scripts.py -q`.
      Expected: only the Global Constraints' pre-D reds fail.
- [ ] Commit `chore(ci): retire the monthly architecture refresh and its re-run workflow`.

## Task 9: records
Spec: § F: what changes, "Records"; product-delivery Phase 5. Advances done_when 14.

**Files:** Modify `docs/product/02-FEATURE-CATALOG.md` (FEAT-CICD-001 record only: Status keeps "Production but
needs remediation" and adds a clause "monthly architecture-doc refresh retired, renderers kept on demand
(#<F>, records #<D>)"; Last reviewed = the commit's date); `docs/product/12-PR-ISSUE-TRACEABILITY.md`
(FEAT-CICD-001 PR lineage: `· [#<F>](https://github.com/TeneikaAskew/stocks/pull/<F>) *monthly architecture-doc refresh retired under spec #1777, records #<D>; closes #1118; review and merge pending*`).

- [ ] Run `PR_NUMBER=<F> PR_DRAFT=false PR_TITLE='<title>' PR_BODY="$(cat body.md)" python3 scripts/gate/spec_gate.py --pr origin/main`.
      Expected: fails on the close-out (catalog record, traceability entry, unticked boxes).
- [ ] Edit the two records; no other capability's row or record.
- [ ] Run it again. Expected: only `ready for review with done_when item(s) not ticked` remains.
- [ ] Commit `docs(catalog): FEAT-CICD-001 records for the refresh retirement`.

## Task 10: the ready push
Spec: § Design, sequence step 3; § Source identity and close-out (pre-merge). Advances done_when 12, 13 and 15;
completes 3, 5, 8 and 9 on the merged head; re-runs the F-head clause of done_when 11 (owned by D's PR).

Preconditions: D merged; #1384 merged (or the owner has said F goes first); a non-shallow clone of this branch.

- [ ] `git fetch origin && git merge origin/main` (never rebase). Resolve: `scripts/maintenance/render_doc_prompts.py`
      deleted (`git rm`); drawio cells, REPLACEMENTS and the drawio test take main's content with Task 6's label
      rules and Task 8's counts re-applied; catalog and traceability keep main's FEAT-CICD-001 lines and add F's;
      the SITE file takes main's bytes.
- [ ] Spec blob equal three ways: `for r in $(git merge-base origin/main HEAD) origin/main HEAD; do git rev-parse "$r:docs/superpowers/specs/2026-11-10-feat-cicd-001-retire-arch-refresh.md"; done` prints one hash three times.
- [ ] Run `python3 -m pytest tests/scripts/test_check_generated_docs.py tests/scripts/test_refresh_architecture_drawio.py tests/scripts/test_docs_audit.py tests/scripts/test_doc_source_snapshot.py tests/scripts/test_refresh_calibration_table.py tests/scripts/test_doc_inventory.py tests/scripts/test_verify_docs_against_live.py tests/scripts/test_scripts.py tests/meta -q`
      then `python3 -m pytest tests/scripts/test_spec_gate.py tests/scripts/test_export_model_registry.py -q`. Expected: all pass, the pre-D reds included.
- [ ] done_when 8: `SNAP` as in Task 6; `--check --snapshot "$SNAP"` prints `drawio check: 0 problem(s)`; record `SNAP`.
- [ ] done_when 3: with `PATTERN` set to the Global Constraints string, `git grep -l -I -i -E "$PATTERN" -- '*.md' '*.drawio' | grep -v -E '^(docs/audit/|docs/audits/|docs/superpowers/|docs/product/infrastructure/manual/|docs/product/infrastructure/05-d-COST_ANALYSIS\.md$|docs/product/07-MODEL-REGISTRY\.md$|\.claude/commands/resolve-issue\.md$)'`
      prints only paths of `CLAIM_DOCS` (each already passing the claims test). Record the output. (On main it prints
      14 paths: the ten `CLAIM_DOCS` outside `manual/`, the three prompts and `Architecture.drawio`; executed.)
- [ ] done_when 9: README step 1 prints `unchanged` three times (executed in the scratch export with the renames
      and the badge change); step 2 passes.
- [ ] done_when 13: `git diff --exit-code origin/main...HEAD -- scripts/gate .githooks/pre-commit .github/workflows/spec-gate.yml .github/workflows/registry-check.yml tests/scripts/test_spec_gate.py tests/scripts/test_export_model_registry.py` exits 0.
- [ ] done_when 15: `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`
      on the committed head reports the current `source_identity_sha256` (unverified: the note is not yet bound).
      Edit only the FEAT-CICD-001 / SHARED-01 row: `source_identity_sha256=<hash>; ` + prose naming only F's
      scripts and tests changes (Tasks 2 to 8; no deployment, frontend or review claim) + ` Earlier: ` + the row's
      previous text after its old prefix, every sentence kept (none names the retired surfaces; read at 4f552e93).
      Commit; produce again; commit the sidecar; then
      `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000`
      reports identity matched. `git diff --exit-code origin/main -- docs/DOC_REGISTRY.md` exits 0. Repeat after any
      later watched-code, SITE-body or policy change, a further merge of main included.
- [ ] done_when 12 (F head): capture `python3 scripts/maintenance/docs_audit.py --no-owning-job-check --json --write-issues-snapshot <dir>/issues.json > <dir>/head.json`
      (the capture executed here in a full clone: `capturedAt 2026-11-10T18:33:05Z`, 1777 stocks and 323 solyra
      issues), run the same audit with `--issues-snapshot <dir>/issues.json` in a worktree of `origin/main` into
      `<dir>/main.json`, and diff them with the script below. Expected: `NEW 0`; none of the three 03-SITE findings
      in `head.json`. Record the audit date beside the output (Review Focus 5). (Executed on the spec author's
      main and simulated-D outputs, the script printed `NEW 5`, exactly done_when 12's five, and `GONE 4`, the
      prompts' findings.)

```python
import json, sys   # usage: python3 audit_diff.py main.json head.json
key = lambda f: (f["check"], f["doc"], f["severity"], f["detail"])
main, head = ({key(f) for f in json.load(open(p))["findings"]} for p in sys.argv[1:3])
print("NEW", len(head - main)); [print("  ", k) for k in sorted(head - main)]
print("GONE", len(main - head)); [print("  ", k) for k in sorted(main - head)]
```

- [ ] done_when 11 re-check (owned by D's PR): the filter below over `head.json` prints `0` (executed on the
      spec author's simulated D: `0`).

```python
import json, sys
rows = ("README.md", "docs/product/infrastructure/05-a-ARCHITECTURE.md", "docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md",
        "docs/product/infrastructure/05-d-COST_ANALYSIS.md", ".github/*.md", ".github/prompts")
hits = [f for f in json.load(open(sys.argv[1]))["findings"] if f["check"] in ("registry", "unowned")
        and any(r in f.get("doc", "") + " " + f.get("detail", "") for r in rows)]
print(len(hits)); [print(h) for h in hits]
```
- [ ] Review Focus 2: `env -u CLOUDSDK_AUTH_ACCESS_TOKEN python3 scripts/verify_docs_against_live.py --write-snapshot <dir>/verify.json --root <main worktree>`
      then `--snapshot <dir>/verify.json --root .`; diff the two finding lists. Expected: no new line.
- [ ] Tick every done_when box with its evidence (10 and 11 cite D's PR and the re-check); ready-mode gate as in
      Task 9 prints `spec gate ok`; one push; mark the PR ready.

## Task 11: review, merge and what follows
Spec: § Source identity and close-out (post-merge); CLAUDE.md 2.5. Advances done_when 12 (review and CI) and 14.

- [ ] After the Ready transition: wait for the Codex Code Review row to read Completed for the head SHA with its
      time after the transition; post `First Codex code review: Completed on <sha>, N findings.` (and the security
      row's line if it ran); read review comments before CI; resolve or answer every thread inside the two-round
      cap; required CI green; no conflict; merge only on the owner's authorization. `Closes #1118` stays in the body.
- [ ] Post-merge obligations, tracked in the PR and never ticked before their evidence exists: verify main's
      source and body identity in a fresh clone; the DOC main and staging close-out (F changes no deployed service;
      the owner names what counts as its staging evidence); retire the sidecar only by the skill's close-out routes;
      set this plan `status: done` on a `docs/` branch; the report-only canvas check through refresh-canvas (its
      "Docs refreshed 2026-09-02" pill).
