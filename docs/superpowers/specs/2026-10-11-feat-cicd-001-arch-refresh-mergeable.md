---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-004]
issues: []
canvases: []
done_when:
  - "refresh-architecture-docs.yml pushes docs/arch-refresh-YYYY-MM, keeps the PR title Monthly architecture doc refresh: YYYY-MM, and its Open refresh PR step stages docs/generated/live-gcp-snapshot.json with the eight files it stages today"
  - "tests/meta/test_refresh_open_pr_step.py, the existing harness extended, takes the prefix from DOC['env']['PR_BRANCH_PREFIX'] in place of the literals at its lines 92, 107 and 237, runs the Open refresh PR step with bash -e, and asserts the pushed commit holds docs/generated/live-gcp-snapshot.json byte-identical to the frozen refresh-inputs/live.json, that the step exits non-zero and pushes nothing when the two differ, and that it exits 0 and pushes nothing when the snapshot is the only file that changed"
  - "tests/meta/test_refresh_open_pr_step.py, with that prefix and bash -e, runs the checkout's scripts/gate/spec_gate.py --pr on the branch the step pushes and asserts it passes, that every staged path is documentation by is_documentation, and that the same commit on bot/arch-refresh-YYYY-MM is refused"
  - "docs/generated/live-gcp-snapshot.json is a byte copy of tests/fixtures/live_gcp_snapshot_2026-09-07.json, which stays unchanged, and scripts/maintenance/doc_inventory.py names the new path in one constant, COMMITTED_SNAPSHOT"
  - "Every test that reads a snapshot and the committed 05-a, 05-c, 05-e or README.md reads COMMITTED_SNAPSHOT and derives each count or name it mutates from it; a test that reads the 2026-09-07 fixture reads none of those four committed files; tests/scripts/test_refresh_architecture_drawio.py is unchanged"
  - "tests/scripts/test_check_generated_docs.py asserts that the committed documents give findings naming an inventory block and an as-of label when checked against a copy of the committed snapshot with read_at moved one day and one Cloud Run service removed"
  - "The PR body shows the commands and pytest summary line of test_check_generated_docs.py and test_render_doc_prompts.py passing on a scratch copy of the head whose snapshot lost one job, scheduler, secret and service, with 05-a, 05-c, 05-e and README re-rendered from it"
  - "No gate file changes: nothing under scripts/gate/, and none of .githooks/pre-commit, .github/workflows/spec-gate.yml, .github/workflows/registry-check.yml, tests/scripts/test_spec_gate.py or tests/scripts/test_export_model_registry.py"
  - "python3 scripts/gate/spec_gate.py --pr origin/main passes on the PR head with PR_TITLE and PR_BODY set to the PR's title and body, and python3 scripts/maintenance/docs_audit.py reports no finding that origin/main lacks other than changed-since entries for documents whose declared code paths this PR changes or that this PR edits"
  - "The FEAT-CICD-001 record in 02-FEATURE-CATALOG shows a current Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists this PR under FEAT-CICD-001"
status: approved
supersedes: null
---

# Publish the monthly architecture refresh from a docs/ branch, with the snapshot it rendered from

Approved on 2026-10-11 under the owner's instruction to bring both repositories to a clean,
ready and closed-out state. Line numbers are stocks main at `17bbacd3` unless a line says otherwise.

## Problem

`.github/workflows/refresh-architecture-docs.yml` (cron `0 6 1 * *`) renders the infrastructure documents and the two
diagrams from a live GCP snapshot, then opens a pull request titled `Monthly architecture doc refresh: YYYY-MM`. No
such pull request has merged since #1009 rebuilt the pipeline (merged 2026-09-07). The last merged one, #953
(2026-09-02), predates the rebuild:

| PR | Month | Created | Closed | Merged |
|---|---|---|---|---|
| #750 | 2026-08 | 2026-08-01 | 2026-08-25 | no |
| #1060 | 2026-09 | 2026-09-08 | 2026-09-26 | no |
| #1240 | 2026-10 | 2026-10-01 12:34Z | 2026-10-11 | no, closed as stale |

Two defects block every refresh PR, and neither can be fixed on the PR itself. The workflow fixes the branch name, and
the snapshot the documents were rendered from is thrown away with the runner.

**1. The branch shape.** The Open refresh PR step builds `BRANCH="${PR_BRANCH_PREFIX}-${MONTH}"` with
`PR_BRANCH_PREFIX: bot/arch-refresh` (workflow lines 81 and 1011-1016). The spec gate accepts only `feature/`, `fix/`,
`docs/`, `chore/` and `bot/superpowers-` (`OTHER_BRANCH`, `scripts/gate/spec_gate.py:158`). #1240's `gate` job (job
110370543632) failed with:

```
SPEC GATE FAILED
 - branch 'bot/arch-refresh-2026-10' is not a delivery branch; a pull request comes from feature/<feat-id>-<slug>,
   fix/<feat-id>-<slug>, docs/<slug>, chore/<slug> or bot/superpowers-<tag>, documentation included
```

**2. The snapshot never reaches the repository.** The workflow writes the snapshot to `refresh-inputs/live.json`
(line 358), in a directory that is untracked and never staged (lines 245-247). It freezes the file with a sha256
manifest before Gemini runs, then restores and verifies it before the gates (lines 508-554 and 702-707). The only
staging is line 1020, and no step runs `git add -A`, `git add .` or `git commit -a`:

```
$ git grep -n "git add\|git commit\|git push" .github/workflows/refresh-architecture-docs.yml
.github/workflows/refresh-architecture-docs.yml:1020: git add docs/product/infrastructure/05-a-ARCHITECTURE.md
    docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-d-COST_ANALYSIS.md README.md
    docs/product/infrastructure/05-e-API.md docs/INVESTMENT_MODELS_SUMMARY.md Architecture.drawio Architecture-icons.drawio
.github/workflows/refresh-architecture-docs.yml:1027: git commit -m "docs: monthly architecture doc refresh ${MONTH}"
.github/workflows/refresh-architecture-docs.yml:1037: git push --force -u origin "$BRANCH"
```

Every test that judges those files reads one snapshot, by a hard-coded path:

```
$ git grep -n live_gcp_snapshot -- tests scripts
tests/meta/test_render_doc_prompts.py:366:      live = json.loads((REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json").read_text())
tests/scripts/test_check_generated_docs.py:21:  SNAPSHOT = REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json"
tests/scripts/test_check_generated_docs.py:342: live = _json.loads((REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json").read_text())
tests/scripts/test_check_generated_docs.py:2244: snapshot = REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json"
tests/scripts/test_doc_inventory.py:23:         FIXTURE = REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json"
tests/scripts/test_refresh_architecture_drawio.py:30: SNAPSHOT = REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json"
```

`doc_inventory.py` and `check_generated_docs.py` take the snapshot only through `--snapshot`, and no script names a
path. A refresh rendered from a newer snapshot therefore fails the tests. #1240's Run Tests (job 110370543040) stopped
at its first failure (`pytest -x`):

```
FAILED tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate - AssertionError:
  05-a-ARCHITECTURE.md: inventory:jobs block differs from a fresh render ... (live 2026-10-01) ... (live 2026-09-07)
  [schedulers, services, reconcile, dbtables in 05-a and 05-c likewise]
  05-a-ARCHITECTURE.md: as-of label says 2026-10-01 but this run read live state on 2026-09-07 (prose line 7)
  [and prose lines 107 and 474]
1 failed, 5744 passed, 67 skipped
```

**The gate admits a refresh from a `docs/` branch that carries the snapshot under `docs/`, and refuses one under
`tests/`.** Run on 2026-10-11 with main's gate (`1a6ff45e`), importing `spec_gate.py` as a module:

```
path                                                                     doc  process gate
tests/fixtures/live_gcp_snapshot_2026-09-07.json                         False False   False
tests/fixtures/live_gcp_snapshot_2026-10-01.json                         False False   False
docs/product/infrastructure/live-gcp-snapshot.json                       True  False   False
docs/generated/live-gcp-snapshot.json                                    True  False   False
README.md / Architecture.drawio / Architecture-icons.drawio / 05-a..05-e True  False   False
.github/workflows/refresh-architecture-docs.yml                          False True    False
OTHER_BRANCH docs/arch-refresh-2026-11: True     OTHER_BRANCH bot/arch-refresh-2026-11: False
```

A branch whose files are all documentation returns before the trace (`spec_gate.py:2099-2115`), so no plan, catalog
row or traceability entry is read. Documents re-rendered from a copy of the live snapshot (below) were committed in an
isolated clone and run through the PR-mode gate (`PR_HEAD_REF=<branch> PR_BASE_REF=main python3
scripts/gate/spec_gate.py --pr 089f271e HEAD`):

| Branch and contents | Gate |
|---|---|
| `bot/arch-refresh-2026-11`, the refreshed documents | refused: not a delivery branch |
| `docs/arch-refresh-2026-11`, the same plus the snapshot as `docs/product/infrastructure/live-gcp-snapshot.json` | `spec gate ok (branch=docs/arch-refresh-2026-11, 5 changed file(s))` |
| `docs/...`, the snapshot added as `tests/fixtures/live_gcp_snapshot_2026-11-01.json` | refused: `changes 1 gated file(s) ... but is not feature/<feat-id>-<slug>` |
| `docs/...`, the 2026-09-07 fixture overwritten in place | refused, same message |
| `feature/feat-cicd-001-arch-refresh-mergeable`, 05-a re-rendered with the tests and snapshot | refused: `docs/product/infrastructure/05-a-ARCHITECTURE.md changes in this feature change; under docs/product/ only the FEAT's own catalog and traceability records, the model registry and its generated files may change here` |

The last row matters for the order of work below. No single branch can change the tests and re-render 05-a, 05-c or
05-e:

- A `docs/` branch cannot touch `tests/`.
- A feature branch cannot touch `docs/product/` (`check_product_scope`, `spec_gate.py:3714`).
- The approved render spec allows block bodies only when the snapshot and the docs test are unchanged. The three as-of
  labels in 05-a are prose outside every block, and `gate_stale_asof` requires them to equal the snapshot's `read_at`.

**The docs audit sees nothing new on a `docs/` refresh.** It was run offline: `--issues-snapshot` with every cited
issue open, and `--no-owning-job-check`, since this session does not call GitHub's REST API. Main and the `docs/`
branch above gave 253 findings each, with 0 new and 0 gone.

- On `089f271e`, `03-SITE-TRACEABILITY.md` carried a P2 `changed-since` finding ("1 content commit(s) to platform/api,
  ..., scripts, tests since 28292da6"). A documentation-only refresh left it at 1, and a commit under `tests/` moved it
  to 2. #1382 has since re-stamped 03 against `303b66a3`. On `17bbacd3` the audit, run offline as above with an issue
  snapshot read 2026-10-11, reports 280 findings and no `changed-since` entry for 03. One local commit under `tests/`
  adds one: "1 content commit(s) to platform/api, platform/deploy.sh, platform/Dockerfile, gcp, lib, scripts, tests".
- A refresh therefore needs no catalog, traceability or 03 change. The gate reads none of them for a
  documentation-only branch.
- The audit's Class A delivery check matches merged PRs by title
  (`^\s*Monthly architecture doc refresh:\s*\d{4}-\d{2}\s*$`, `docs_audit.py` `OWNING_JOB`), not by branch.

**What the next scheduled run would do, measured 2026-10-11.** A read-only live snapshot
(`env -u CLOUDSDK_AUTH_ACCESS_TOKEN python3 -m scripts.maintenance.doc_inventory --write-snapshot ...`, read
`2026-10-11T03:30:53Z`) shows 76 jobs, 3 services, 65 schedulers and 22 secrets. `solyra-api-prod` is gone (#1366).

The workflow's deterministic steps were run on main in a scratch worktree: `--insert` for 05-a, 05-c and 05-e,
`--readme-badges`, and `refresh_architecture_drawio.py` with `--repo-jobs`. Cloud SQL is unreachable from this
sandbox, so table statistics came from the fixture and 05-c's `dbtables` block did not move. The steps changed 05-a,
README and both diagrams, and `check_generated_docs.py --snapshot` reported `0 finding(s)`: the as-of labels and badges
are rendered, not model-written.

Two facts about those steps bear on any refresh:

- The workflow refuses a snapshot without `db_tables` (lines 374-378). Without that guard, the drawio generator prints
  "0 relations", because it counts `len(live.get('db_tables', {}))`. The leftovers spec (below) fixes the generator side.
- The workflow passes `--repo-jobs` to the drawio generator (lines 499-500). Without it, the add-on job grid keeps the
  previous read's last-execution dates.

The run itself, step by step:

1. The schedule fires on main. October's scheduled run (run 37) started at 12:14Z, not 06:00. It authenticates through
   WIF, takes the snapshots and renders as above.
2. Gemini rewrites the prose of 05-a, 05-c and 05-d. Its prompt still says
   `The API is served by TWO API-only Cloud Run services: solyra-api-prod ...` (`.github/prompts/architecture.md:92`).
3. "Verify regenerated docs" fails the run on any docs-vs-live drift in those three documents. Today's documents
   already carry three such findings (`verify_docs_against_live.py`, live read):
   `[unknown-name] 05-a-ARCHITECTURE.md:111 solyra-api-prod`, `[count-drift] 05-a-ARCHITECTURE.md:111 claims 4 Cloud
   Run services; live count is 3`, and `[unknown-name] 05-d-COST_ANALYSIS.md:92 solyra-api-prod`. The run goes green
   only if the model corrects all three against its own prompt. Gemini was not run here, so the outcome is not checked.
   A red run opens a failure issue and a draft fix PR through `handle-failure`.
4. A green run opens `bot/arch-refresh-2026-11`, which fails the gate (defect 1) and Run Tests (defect 2).

**Tests are coupled to the snapshot.** The four files that read it pass on main (283 passed). With the documents and
diagrams re-rendered in the scratch worktree, they gave:

| Snapshot the tests read | Committed documents | Result |
|---|---|---|
| the 2026-09-07 fixture (today) | rendered from the 2026-10-11 live snapshot | 5 failed, 278 passed |
| the 2026-10-11 snapshot, committed under `docs/` | same | 1 failed: `test_a_stale_service_count_is_caught` |
| a copy with one job, scheduler and secret fewer | rendered from that copy | 3 failed (below) |

- `test_doc_inventory.py::test_reconcile_against_snapshot_reports_the_known_deltas` asserts the 2026-09-07 capture's
  deltas (`schedulers_repo_only == ['earnings-sweep-sunday']`). It is a test of that capture and keeps reading it.
- `test_refresh_architecture_drawio.py::test_a_stale_secret_count_in_any_cell_is_caught` replaces the literal
  `22 secrets` in the committed diagram, and `test_a_stale_service_count_is_caught` expects
  `svc_group says 4 Cloud Run Services, live is 5`. Both literals go stale with any count change.

No other test reads the refreshed files in a way a refresh breaks. All of `tests/meta` and `tests/scripts` on that
last tree gave `3 failed, 1850 passed, 4 skipped, 1 error`. The three failures are the ones above. The error is
`test_magnitude_movement_sim.py` failing to import `google.cloud.storage`, which is not installed in this sandbox.

**A second snapshot lands before this change.** The approved FEAT-DEPLOY-001 leftovers spec
(`2026-10-11-feat-deploy-001-retired-service-leftovers.md`, merged in #1381) regenerates both diagrams from a fresh
live read. It commits that read as `tests/fixtures/live_gcp_snapshot_<read date>.json`, which only
`test_refresh_architecture_drawio.py` reads; that is "the leftovers fixture" below.

- A trial of that recipe read `2026-10-11T04:15:52Z`: 3 services, 2 triggers and 98 relations from a db-query
  execution, with the same top-level keys as the 2026-09-07 fixture and 84,562 bytes. The implementation takes its own
  read, so the committed fixture's numbers can differ.
- 05-a, 05-c, 05-e and README stay rendered from 2026-09-07.
- After it merges, the committed generated files therefore agree with two different snapshots.
- Re-rendering 05-a, 05-c, 05-e and README from that trial read with the workflow's render commands changed 05-a
  (382 lines), 05-c (111) and README (8), and `check_generated_docs.py --snapshot <that read>` reported `0 finding(s)`.
  Prose counts are not rendered: 05-a still says `95 relations live` at lines 109 and 141 against 98 in that read.
  They belong to #1372.

## Non-goals

- **The Gemini prompt's stale service description.** `.github/prompts/architecture.md:92` is fixed under
  `docs/superpowers/specs/2026-10-11-feat-cicd-001-review-guidelines.md` (approved, #1377). Step B corrects the
  documents by hand, but until the prompt lands, a run whose model writes the retired service back fails its own
  verify step. That is a red run and an issue, not an unmergeable PR.
- **The diagrams, their generator and their test.** They belong to the leftovers spec, and to the diagram step of the
  sequence below. This PR does not touch `test_refresh_architecture_drawio.py` or the leftovers fixture.
- **The render check and prose citations.** The gate's own render of the blocks belongs to
  `docs/superpowers/specs/2026-10-11-feat-cicd-001-generated-docs-render.md`, and prose citations and counts belong to
  #1372. This spec only names the snapshot that render reads (Design, "With the render spec").
- **Merging without review.** "Mergeable" means the gate and Run Tests pass on the PR exactly as the workflow opens
  it.
- **What a snapshot holds.** It keeps the key set `doc_inventory.live_snapshot()` and `--db-live` write today, the
  same as the committed 2026-09-07 fixture's (compared 2026-10-11).
- **A DOC_REGISTRY row for the snapshot.** The audit reads Markdown and files the registry names outright
  (`document_set`). The snapshot is data, and leaving it unregistered added no finding (measured above).
- **The grep recipes** in `.claude/commands/resolve-issue.md` and `.github/ISSUE_TEMPLATE/` that exclude
  `tests/fixtures/live_gcp_snapshot_*.json`. Every recipe already excludes `docs/`.
- **The schedule.** The cron, GitHub's start delay and the WIF condition pinning runs to `refs/heads/main` stay.

## Approaches considered

1. **One committed snapshot at a fixed path under `docs/`, read by the tests through one constant.** Chosen. A `docs/`
   branch may carry it, it travels with the files rendered from it, and the tests still compare the committed files
   with a render.
2. **Dated snapshots in a directory, with the test reading the newest** (the triage's option a). Rejected. "Newest" is
   a selection rule that a stray or hand-added file can win. The render spec's parity item expects one path, and old
   snapshots would pile up at about 84 KB a month with nothing reading them.
3. **A marker inside the generated docs naming the snapshot** (option b). Rejected as the selector, because the
   document would choose its own oracle: editing the marker picks which snapshot the test judges against. It still needs
   the snapshot committed, so it adds a lookup and removes nothing. The useful half already exists: `gate_stale_asof`
   requires 05-a's as-of labels to equal the snapshot's `read_at` day.
4. **Run the refresh as `feature/feat-cicd-001-arch-refresh-YYYY-MM`.** Rejected. It needs a plan per month's branch,
   a commit with the PR number, a monthly catalog and traceability close-out, and `check_product_scope` refuses 05-a's
   prose and all of 05-d on a feature branch.
5. **Keep the snapshot under `tests/fixtures/` and give `docs/` branches an allowance for it.** Rejected. It is a gate
   change with a red team, and it makes a test fixture writable from documentation branches.
6. **Drop the live-dependent checks, or render against live GCP in CI.** Rejected. The first stops the test failing
   when live blocks, labels or diagrams do not match a render. The second cannot authenticate (WIF is pinned to main)
   and is not deterministic.
7. **One PR that adds the snapshot as a copy of the leftovers read, re-renders the blocks and README from it, and moves
   every test onto it.** Rejected because the gate refuses it (the last row of the gate table above). The convergence
   must ride a `docs/` branch, which cannot change tests, so the tests move in two feature PRs on either side of it.

The path sits outside `docs/product/` because this PR is a feature branch, and `check_product_scope` refuses
`docs/product/` there.

## Design

**One snapshot.** `COMMITTED_SNAPSHOT = "docs/generated/live-gcp-snapshot.json"` in
`scripts/maintenance/doc_inventory.py`. It is the one snapshot that every inventory block, as-of label and badge in the
committed generated files agrees with, once the sequence below completes. Prose counts outside the blocks are #1372's.
After that, each monthly refresh replaces it together with the files rendered from it.

**The sequence.** The leftovers PR merges first, then A, B and C. The render implementation (R, stocks#1383) lands any
time after A. Every inventory block, as-of label and badge agrees with one snapshot once L, A, B and C have merged:

| Step | Branch | What changes | Snapshot each test reads | Content of COMMITTED_SNAPSHOT |
|---|---|---|---|---|
| L (leftovers) | feature, FEAT-DEPLOY-001 | diagrams regenerated; leftovers fixture added | docs: 2026-09-07 fixture; diagrams: leftovers fixture | (absent) |
| A (this spec) | `feature/feat-cicd-001-<slug>` | workflow; COMMITTED_SNAPSHOT added; docs tests moved to it | docs: COMMITTED_SNAPSHOT; diagrams: leftovers fixture | byte copy of the 2026-09-07 fixture |
| R (render, stocks#1383) | `feature/feat-cicd-001-generated-docs-render` | the gate renders a feature PR's blocks from COMMITTED_SNAPSHOT | unchanged | unchanged |
| B (convergence) | `docs/<slug>` | COMMITTED_SNAPSHOT replaced; 05-a, 05-c, 05-e and README re-rendered; retired-service prose corrected by hand | unchanged | byte copy of the leftovers fixture |
| C (diagram test) | feature, FEAT-CICD-001, `2026-10-11-feat-cicd-001-drawio-committed-snapshot.md` | diagram test moved to COMMITTED_SNAPSHOT; leftovers fixture deleted; secret count literal derived | all: COMMITTED_SNAPSHOT | unchanged |

- Each step is green on its own commit. At A the docs agree with 2026-09-07 and the diagrams with the leftovers read,
  each through its own test. R moves no docs or diagram test, and renders feature PRs' blocks from COMMITTED_SNAPSHOT,
  which holds the 2026-09-07 content until B. B changes only documentation: the docs now agree with the leftovers read,
  through COMMITTED_SNAPSHOT. The diagrams already do, through the leftovers fixture, whose bytes are now the same. C
  then moves the last test onto the shared file.
- A trial of step B's recipe is measured above: re-rendering from the trial read gives `0 finding(s)`. Its recipe:
  1. `cp tests/fixtures/live_gcp_snapshot_<read date>.json docs/generated/live-gcp-snapshot.json`.
  2. `python -m scripts.maintenance.doc_inventory --snapshot docs/generated/live-gcp-snapshot.json --insert` on 05-a,
     05-c and 05-e.
  3. `--readme-badges README.md --day <read date>`.
  4. `refresh_architecture_drawio.py --snapshot docs/generated/live-gcp-snapshot.json --repo-jobs <list> --check` must
     report no problem, and regenerating without `--check` must leave both diagrams byte-identical. Both hold because
     the two snapshots are the same bytes, provided the repository facts the generator also reads, `active_workflows()`
     and the `--repo-jobs` list, are unchanged since the leftovers PR. If either moved, the diagrams are regenerated
     and committed with the rest of B.
  5. Correct by hand the prose that still describes the retired service, or its trigger, as live. A `docs/` branch may
     edit these files, so the refresh no longer waits on Gemini or the #1377 prompt fix. The live read has 3 services
     (`solyra-api-staging`, `discord-interactions`, `failure-notifier`), none IAP-enabled, and 2 Cloud Build triggers
     (`deploy-solyra-api-staging`, `apply-schema-on-change`). `git grep -n solyra-api-prod -- docs/product/infrastructure`
     on origin/main `089f271e`, before the re-render:
     - 05-a:72 and the edges at 94, 95, 96, 97 and 100: the mermaid node `API1` for the retired service.
     - 05-a:103 "the two API services".
     - 05-a:111 "4 long-lived HTTP services" naming it (verifier: unknown-name, and count-drift 4 against 3 live).
     - 05-a:113 and 871: the trigger lists that include `deploy-solyra-api-prod` (3 against 2 live).
     - 05-a:118: the IAP row "gates solyra-api-prod". No live service has IAP.
     - 05-a:444 "7.1 The two API services" and its table at 448 and 453: two columns and the manual prod trigger.
     - 05-a:803 and 833: the promote-to-prod step and its `gcloud builds triggers run deploy-solyra-api-prod` command.
     - 05-d:27: the Services CPU row's resource list, which keeps the service but marks it retired 2026-10-10 (#1366),
       because the 90-day billing window includes its spend.
     - 05-d:92: recommendation #2 naming it as the resource (verifier: unknown-name).
     - 05-e:5, the hand-written header: "deployed twice ... as solyra-api-prod (IAP) and solyra-api-staging".

     Each line is rewritten to the live state, or says the service was retired on 2026-10-10 (#1366). The rest are
     left alone. 05-a:440 is inside the `inventory:services` block, and step 2's re-render drops it. 05-a:7 records what
     #990 renamed. The `manual/` copies are hand-maintained snapshots frozen at 2026-09-08 by their own header, so they
     stay too. Two strings on rewritten lines are kept verbatim, because tests replace them and a `docs/` branch cannot
     change a test: the `discord-interactions` fragment on 05-a:111, from `(min-instances 1 only inside the weekday warm
     window` to `§7.4)` (`test_a_fixed_min_instances_for_a_windowed_service_is_a_finding`), and the marker text
     `gcloud builds triggers list 2026-09-07` on 05-a:871 (`test_moving_the_date_inside_an_exemption_is_a_finding`).
  6. Check the result. `check_generated_docs.py --snapshot docs/generated/live-gcp-snapshot.json` must report no
     finding. `env -u CLOUDSDK_AUTH_ACCESS_TOKEN python3 scripts/verify_docs_against_live.py` must report no finding in
     05-a, 05-c or 05-d, the gate the refresh applies. The verifier reads live GCP, not the leftovers read, so a
     finding explained by a fleet change after that read's `read_at` is listed in the PR, not edited.
     `git grep -n solyra-api-prod -- docs/product/infrastructure ':!docs/product/infrastructure/manual'` must print
     only 05-a:7 and lines that say the service was retired.
     `python -m pytest tests/scripts/test_check_generated_docs.py tests/meta/test_render_doc_prompts.py` passes.
- No run of the workflow may be dispatched between A and C. A refresh PR opened in that window fails Run Tests on the
  diagram test whenever a job, scheduler, secret, service or relation count moved, because the test still reads the
  leftovers fixture while the workflow re-renders the diagrams. If the 2026-11-01
  schedule fires first, a dispatch after C force-pushes the same branch and rewrites the PR body.
- This spec covers steps A and B. The gate admits B as documentation (`spec_gate.py:2099-2115`), but B is not TRIVIAL
  under the product-delivery skill's Phase 0, which covers a typo, a comment or wording. This spec therefore authorises
  B, and the recipe above is B's contract. Step C is `2026-10-11-feat-cicd-001-drawio-committed-snapshot.md`: the
  diagram test reads COMMITTED_SNAPSHOT, the leftovers fixture is deleted, and the secret mutation test derives its
  count from the snapshot. The service mutation test already derives its count, from the leftovers PR (its Design,
  `test_a_stale_service_count_is_caught`).

**The workflow** (`.github/workflows/refresh-architecture-docs.yml`), changed in step A:

- `PR_BRANCH_PREFIX: docs/arch-refresh` gives `docs/arch-refresh-YYYY-MM`, which `OTHER_BRANCH` accepts. The title
  `Monthly architecture doc refresh: YYYY-MM` stays, because the docs audit's delivery check keys on it.
- In the Open refresh PR step, before `git add`, the step copies `refresh-inputs/live.json` to
  `docs/generated/live-gcp-snapshot.json`. It runs `cmp` against `$RUNNER_TEMP/frozen/refresh-inputs/live.json`, the
  copy every gate judged, and exits non-zero before committing when they differ. The path joins the `git add` and
  `--stat` lines.
- The snapshot is written only there, after the model has run and the inputs are restored. A model edit to the
  committed copy is still a stray write, and the step overwrites the file anyway.
- "Detect meaningful changes" ignores the snapshot, because its `read_at` changes every run. Any opened PR stages it,
  so documents and snapshot land together.
- The step's empty-index check compares the eight documents only (`git diff --cached --quiet -- <the eight>`), so a
  run whose only staged change is the snapshot still exits clean without committing or pushing.
- The force-push, the existing-PR body update, permissions, secrets and every gate stay. Comments naming
  `bot/arch-refresh`, `.github/workflows/README.md:16` and the docstring at
  `tests/meta/test_refresh_architecture_docs_pr_token.py:75` are updated.

**The tests, changed in step A.**

- A test that reads a snapshot together with the committed 05-a, 05-c, 05-e or README reads
  `REPO / inv.COMMITTED_SNAPSHOT`. In `test_check_generated_docs.py` that is `SNAPSHOT` (line 21), which the `live`
  fixture and `test_committed_docs_pass_every_gate` read, and the inline copy at line 342, which is checked against
  copies of the committed documents. Any count or name such a test mutates comes from the snapshot, such as the job
  `signal-monitor` that line 56 copies.
- Tests of one capture keep the 2026-09-07 fixture and read none of the committed four: every test in
  `test_doc_inventory.py`, which reads `gcp/schema.sql` and the source tree but no committed document, so its `FIXTURE`
  stays; the CLI test at `test_check_generated_docs.py:2244`, which writes and reads a temporary README; and the
  digest-section test in `test_render_doc_prompts.py`.
- **New negative test.** `test_check_generated_docs.py` writes a copy of the committed snapshot with `read_at` moved
  one day and one service removed. It asserts that `gate.run` over the committed documents reports a block that differs
  from a fresh render and an as-of label naming the wrong day. This keeps the docs test meaningful.
- **`tests/meta/test_refresh_open_pr_step.py`** exists (292 lines, added in #1048 and extended by #1070 and #1080). It
  extracts the step's script from the workflow and runs it against a temporary repository with a bare remote and a
  stubbed `gh`. Step A extends it; no new harness is written.
  - The prefix comes from `DOC['env']['PR_BRANCH_PREFIX']`, in place of the literal `bot/arch-refresh` passed at lines
    92 and 237 and asserted at line 107. With the literal, the tests pass whatever the workflow says.
  - The step runs with `bash -e`, as Actions runs a `run:` block that names no `shell:`. Today both call sites, lines 97
    and 242, use `bash -c`, under which a failing command falls through to the next line. Measured: the script
    `mkdir d; mkdir d; cp missing.json d/s.json; echo "reached git add"` printed `reached git add` and exited 0 under
    `bash -c`, and exited 1 under `bash -e`.
  - Under `-e`, the second-run test (line 242) runs the step in a fresh clone of the bare remote, as a new runner does,
    because `git checkout -b` on an existing local branch exits 128.
  - `test_nothing_staged_exits_clean_without_touching_github` keeps asserting a clean exit, now with the snapshot as the
    only change, and the body test's file count includes the snapshot.
  - It seeds `refresh-inputs/live.json` and its frozen copy under `RUNNER_TEMP`.

  It asserts:
  - the pushed commit holds the snapshot byte for byte;
  - the step refuses, pushing nothing, when the frozen copy differs;
  - the checkout's `scripts/gate/spec_gate.py --pr`, copied into its temporary repository, passes on the pushed branch;
  - every staged path is `is_documentation`;
  - the same commit on a `bot/arch-refresh-` branch is refused.

  This is feasible: measured 2026-10-11 in a minimal temporary repository, `docs/arch-refresh-2026-11` gave
  `spec gate ok` and `bot/arch-refresh-2026-11` was refused. Because the test copies the checkout's gate, it judges
  #1383's gate on every run once that lands.
- **Scratch re-render (done_when item 7).** In a detached worktree of the head:
  1. Overwrite COMMITTED_SNAPSHOT with a copy that has `read_at` moved and one entry removed from each of `jobs`,
     `schedulers`, `secrets` and `services`, with `counts` updated.
  2. Run the workflow's `--insert` and `--readme-badges` lines against it.
  3. Run `check_generated_docs.py --snapshot`, then pytest on `test_check_generated_docs.py` and
     `test_render_doc_prompts.py`. `test_doc_inventory.py` is left out: none of its tests reads a committed document,
     so the copy cannot change its result.

  No GCP access is needed. The diagrams and their test join this check in step C.

**With the render spec and REQ-GOV-004.**

- REQ-GOV-004 requires the blocks to equal what `doc_inventory.py` renders "from the repository on main". The snapshot
  is now part of that repository, and "the GCP snapshot that test reads" is COMMITTED_SNAPSHOT.
- The render spec renders a feature PR's blocks with main's snapshot, through a gate constant pinned by parity to the
  docs test's `SNAPSHOT`. That constant becomes COMMITTED_SNAPSHOT, so feature PRs render against main's current
  snapshot. That is the 2026-09-07 content until B, and the leftovers read after it.
- A feature branch still cannot change the snapshot alongside blocks (REQ-GOV-004's render-input rule). Once the render
  check is on main, `is_process_file` also keeps other capabilities off it.
- Steps B and every monthly refresh are `docs/` branches. `check_product_scope` does not judge them, so the render check
  does not apply. The docs test judges them in Run Tests, running main's code, because a `docs/` branch cannot change
  code. A `docs/` branch can now change the snapshot together with the blocks rendered from it and pass both the gate
  and Run Tests; before A, Run Tests pinned every block to a fixture under `tests/` that a `docs/` branch cannot
  change. The monthly refresh needs exactly this capability; the remaining check is a reviewer reading the snapshot's
  diff beside the documents' (Risks).
- **Order with the render implementation.** A merges first and changes no gate file. The render PR (stocks#1383,
  branch `feature/feat-cicd-001-generated-docs-render`, head `f552ec59`) then merges main and takes COMMITTED_SNAPSHOT
  as its snapshot path. Its done_when 4 asks parity with the docs test's `SNAPSHOT`, which A moves. The reverse order
  cannot merge: `spec-gate / base-suite` runs main's suite against the pull request's gate (`spec-gate.yml:81-100`), so
  #1383's parity test (`tests/scripts/test_spec_gate.py:3880-3892` there) would compare A's gate path with main's docs
  test, which still reads the fixture.
- **What #1383 does with COMMITTED_SNAPSHOT** after merging main, so that done_when item 3 still holds once it lands:
  - It sets `RENDER_SNAPSHOT` to COMMITTED_SNAPSHOT and adds it to `RENDER_INPUTS` (unchanged beside blocks) and
    `RENDERER_FILES` (`is_process_file`), `spec_gate.py:77-81` there, with the parity assertion and the fixture tree's
    `SNAPSHOT_FILE` (`test_spec_gate.py:3900` there) moved to match.
  - It keeps the 2026-09-07 fixture in both lists, as its done_when 2 and 5 require.
  - It does not make COMMITTED_SNAPSHOT anything other than documentation to `is_documentation`, and adds it to no check
    that runs before the documentation-only return (`spec_gate.py:2125-2141` there). `check_product_scope` (line 4447)
    runs only for a branch `BRANCH` matches, and the `is_process_file` check (line 4454) only when `check()` returned a
    trace, which the documentation-only return (`spec_gate.py:2141` there) does not; a `docs/` branch reaches neither.
  - Its push after merging main gets the red-team pass CLAUDE.md requires before every gate push.

  Measured 2026-10-11 by running #1383's gate (`f552ec59`) in a temporary repository holding its renderer, the eight
  refreshed files and the snapshot at COMMITTED_SNAPSHOT. With `RENDER_SNAPSHOT` set to COMMITTED_SNAPSHOT and the
  fixture kept in `RENDERER_FILES`:
  - `docs/arch-refresh-2026-11`, changing the snapshot, rows in 05-a's blocks, README and both diagrams, gave
    `spec gate ok (branch=docs/arch-refresh-2026-11, 9 changed file(s))`;
  - `bot/arch-refresh-2026-11` with the same commit was refused as not a delivery branch;
  - `feature/feat-cicd-001-probe`, changing 05-a beside the snapshot, was refused with `changes alongside
    docs/generated/live-gcp-snapshot.json, which decide the render`;
  - `is_process_file` and `is_documentation` both returned true for COMMITTED_SNAPSHOT.

  The unmodified gate gave the same verdicts on both refresh branches. With `is_documentation` returning false for the
  snapshot, the `docs/` refresh was refused: `changes 1 gated file(s) (docs/generated/live-gcp-snapshot.json) but is
  not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>`. That is the change #1383 must not make.
- The render spec's Design names the 2026-09-07 fixture as the snapshot the child loads; that described main when it
  was approved. Its done_when 4 (parity with the docs test's `SNAPSHOT`) governs once A moves `SNAPSHOT`, and its
  done_when 2 and 5 still hold because the fixture stays in both lists.
- **Recommended order overall:** leftovers, A, the render implementation, B, C, then a dispatch of the workflow.

**Capacity (CLAUDE.md rule 0).**

The PR body's Capacity section carries these lines, in the form `check_capacity` reads: each value starts with its
figure, and the cost line carries the `30` label. Run through main's `check_capacity` for a change to the workflow,
they return `[]`.

- Volume: 84,562 bytes (one snapshot, the size of the trial read) per monthly refresh PR, about 1 MB a year before git's delta compression.
- Velocity: 0 new GCP, BigQuery, Vertex or GitHub calls; one `cp` and one `cmp` per run, and two gate runs in a temporary repository per test run (one pass, one refusal).
- Wall-clock: <1 s added per run. The job's 45 minutes is its timeout, not its run time.
- $/run × runs/day × 30: $0

## Risks

- **The sequence stalls between A and C.** Refresh PRs then fail Run Tests on the diagram test, as they do today; the
  sequence table says why, and no dispatch is made in that window. C is small, but it needs its own approved spec.
- **A test that hard-codes a fact of the refreshed files fails a refresh PR.** Item 7 and step C's scratch re-render
  catch today's three such tests. A later one names itself in Run Tests. It is fixed on a FEAT-CICD-001 branch and the
  workflow is re-dispatched, so the refresh PR is never edited by hand.
- **A refresh PR goes stale against main.** If a PR that moves cited lines merges first, the refresh PR conflicts or
  fails on the merge ref. A dispatch from main re-renders, force-pushes the same branch and rewrites the body. In the
  other order, an open feature PR rendered against the previous snapshot fails until it is re-rendered, which is the
  render spec's own stale-block risk.
- **The snapshot is published monthly in a public repository** (`visibility: public`). It carries the same keys as the
  fixture public since #1009 (merged 2026-09-07): secret names, service-account emails, service URLs and invokers, job
  arguments and Cloud SQL settings. A credential passed in a job's arguments would be published. REQ-SECRET-001 forbids
  that, and 05-a already publishes each job's entrypoint. Reviewers read the snapshot's diff.
- **The force-push replaces anything a person pushed to `docs/arch-refresh-YYYY-MM`.** The branch is bot-owned, as
  `bot/arch-refresh-` was, and CLAUDE.md's force-push ban covers `main` only.
- **Step A raises docs-audit `changed-since` entries.** On 17bbacd3 main carries none for 03 (#1382 re-stamped it);
  the leftovers PR, which merges first, adds one, and A's commits under `scripts/` and `tests/` extend it, since 03's
  declared code paths include both. A raises one for any other document that declares a path A changes. done_when
  item 9 counts exactly those. The next re-stamp of each document clears its entry, and documentation-only steps raise
  none.
