---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-004]
issues: [1661]
canvases:
  - https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN
site_source_notes: [SHARED-01]
done_when:
  - "Exporter: python3 -m scripts.maintenance.architecture_export --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --output <path> writes one JSON object with schema 'architecture-export/1' and the top-level keys schema, sources, jobs, services, schedulers, tables, counts and drift (Design 1); tests/scripts/test_architecture_export.py asserts every key and that counts.declared equals what scripts/maintenance/doc_inventory.repo_inventory returns for jobs, schedulers, tables, routes and services on the same tree"
  - "Built from the inventory, not a second parser: scripts/maintenance/architecture_export.py imports its facts from scripts/maintenance/doc_inventory.py (repo_inventory, deploy_services, live_snapshot, table_refs and job_table_edges) and contains no regular expression over gcp/deploy.sh, platform/deploy.sh, gcp/schema.sql or platform/api; a structural (AST) test asserts it compiles no re pattern and opens none of those four paths itself"
  - "Declared services come from the deploy scripts: a new scripts/maintenance/doc_inventory.deploy_services returns every Cloud Run service gcp/deploy.sh and platform/deploy.sh deploy (by literal name or by the variable they deploy), repo_inventory carries it as services, and on the 2026-11-10 tree it names discord-interactions, failure-notifier and solyra-api-staging; tests/scripts/test_doc_inventory.py asserts that list, and test_architecture_export.py asserts that a snapshot lacking one declared service and holding one service no script deploys yields that service declared true with live null, the other declared false with live set, and each listed once in drift.declared_not_live and drift.live_not_declared"
  - "Unresolved table families stay unresolved: for a job whose only evidence for a table is an unresolved run-time template (the case test_an_unresolved_template_is_marked_instead_of_asserting_every_relation builds), the export lists that table under the job's possible_reads or possible_writes with its template and not under reads or writes, and lists the job under that table's possible_readers or possible_writers and not under readers or writers (test on the same mini repo)"
  - "Scheduler targets keep their kind: every exported scheduler has target {kind, name, uri} with kind job, service or uri; on the 2026-11-10 tree discord-warm-open and discord-warm-close export kind service naming discord-interactions and reconcile-failure-notifier-hourly exports kind service naming failure-notifier, and no scheduler with a non-empty target_job, target_service or target_uri in deploy_schedulers exports an empty target (test)"
  - "Deterministic and free of line numbers: two runs on the same commit and the same snapshot produce byte-identical files (test), and no string value in the export matches the file-and-line pattern '<path>.(py|sh|sql):<digits>' (test over the fixture export)"
  - "Provenance: sources.commit equals git rev-parse HEAD and sources.files lists the git blob id of gcp/deploy.sh, platform/deploy.sh and gcp/schema.sql and the tree id of platform/api; with an uncommitted change under gcp/, lib/, scripts/, platform/api or platform/deploy.sh the exporter exits non-zero and writes nothing (test using a temporary clone)"
  - "Unread live counts stay unread: live_snapshot reads no database relations and no deployed routes, so counts.live.tables and counts.live.routes are null in every mode (never a copied declared count or a zero), counts.live for jobs, services and schedulers comes from the snapshot, and the job summary shows the null counts as not read; a test runs the exporter on the 2026-09-07 fixture with db_tables removed and asserts both nulls and the summary text"
  - "Repo-only mode needs no cloud access: with neither --snapshot nor --live, sources.live is null, every live field is null, drift is empty, and the run exits 0 with no gcloud executable on PATH (test)"
  - "Drift is computed, not described: given a snapshot that lacks one declared job, holds one job no deploy function creates and has one paused scheduler, drift.declared_not_live, drift.live_not_declared and drift.paused_schedulers each list exactly that one name (test with a synthetic snapshot)"
  - "On-demand workflow: .github/workflows/architecture-export.yml has workflow_dispatch as its only trigger, refuses any ref other than refs/heads/main before authenticating, grants only contents: read and id-token: write, reads no database secret, installs no model CLI, runs no git push, gh pr or gh issue command, and uploads the export as the run artifact architecture-export with retention-days 30 and writes counts and drift to the job summary; tests/meta/test_architecture_export_workflow.py parses the YAML and asserts each of these"
  - "Capacity measured: the PR body states the exporter's wall-clock and peak memory for the repo-only and fixture runs measured on the PR head, and the gcloud read count of a live run (Design 3)"
  - "Canvas skill reads the export: .claude/skills/refresh-canvas/SKILL.md describes a canvas fed by an architecture export (Design 4): it takes the JSON from the latest successful Architecture export run on main or from the exporter run on a fresh clone of main, refuses an export whose sources.commit is not on main, reports how many commits main has moved since that commit, and keeps the diff-first, write-on-approval steps unchanged"
  - "python3 scripts/gate/spec_gate.py --pr origin/main passes on the PR head, and python3 scripts/maintenance/docs_audit.py reports nothing on the branch that it does not report on origin/main, using the merged source-review verifier, this approved SHARED-01 declaration, the FEAT-CICD-001 SHARED-01 implementation-source note in 03-SITE-TRACEABILITY updated to the current source hash, and a committed docs/review-evidence/site-source-snapshot.json that verifies; no watcher or historical marker is changed"
  - "The FEAT-CICD-001 record in 02-FEATURE-CATALOG shows a current Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists this PR under FEAT-CICD-001"
status: draft
supersedes: docs/superpowers/specs/2026-11-10-feat-cicd-001-architecture-export.md
---

# On-demand architecture export that feeds the backend architecture diagram (revision 2)

## Authority

On 2026-11-10 the owner asked for "a full evaluation of what the intent of that was and how we can
actually revamp this to actually work, because it doesn't work and it seems to not be helpful or
useful anymore", and named the Claude Design backend architecture diagram as the thing that had been
more useful. After the evaluation the owner chose the option that generates the architecture facts
from code and feeds the diagram from them, then asked for it to run on demand: "Make it on demand".

## Revision 2

Revision 1 (#1770, #1771) is unchanged here except in two places. It now declares
`site_source_notes: [SHARED-01]`, and its docs-audit done_when item names the committed-source
route that declaration opens. The exporter changes watched code under `scripts/` and `tests/`, which
03-SITE-TRACEABILITY tracks, so without a declared note the docs audit on the build PR (#1775) reports
two changed-since findings and one source-provenance finding for that document that main does not.
Every code spec since 2026-11-01 clears them this way, and a spec cannot gain the declaration in its
own implementation PR (product-delivery skill, "Committed-source documentation identity"). Nothing
the exporter, the workflow or the canvas skill does changes.

## Problem

`refresh-architecture-docs.yml` (cron `0 6 1 * *`, added in #232, rebuilt in #1009) reads live GCP
state, re-renders the inventory blocks and asks Gemini to update the prose of `05-a-ARCHITECTURE.md`,
`05-c-DATA_DEPENDENCIES.md`, `05-d-COST_ANALYSIS.md` and the README, then opens a PR. Only one of its
PRs ever merged (#953, 2026-09-02, the run that replaced the hand-written document with a thin
rewrite). #750, #1060 and #1240 closed unmerged; the 2026-11-01 run (#38) failed at "Verify
regenerated docs" and #1661 is still open. The reasons are recorded in the unmerged spec PR #1426: the
gate refuses its `bot/` branch, and the docs tests judge the documents against the 2026-09-07
snapshot fixture, so a document rendered from a fresh snapshot fails them.

The effect on main, read 2026-11-10:
- The live facts in `05-a-ARCHITECTURE.md` are stamped 2026-09-07. Its services block still lists
  `solyra-api-prod` and §7.1 still describes "two API services"; the 2026-11-09 live read in #1384
  shows 3 services, 76 jobs and 66 schedulers. `05-d-COST_ANALYSIS.md` is stamped 2026-09-02.
- Feature PRs keep the inventory blocks equal to the renderer (REQ-GOV-004), so those blocks track
  code, but the diffs they carry are mostly `file:line` citations moving (#1753 changed 68 lines of
  05-a and 157 of 05-c). The prose does not describe recent work such as the one level source,
  TF bias or `orb_only`.
- The backend architecture diagram (canvas `LXZ5iRtXogCyFfApfsxXVN`, last saved about 2026-09-08)
  is the view the owner used: clickable nodes with triggers, upstream and downstream, and a trigger
  timeline. It says "Docs refreshed 2026-09-02", shows 44 live schedulers and a `trading-platform`
  service that was renamed in early September. `docs/product/canvases.yml` registers it as
  `mode: report-only` with no exporter, so nothing can keep it current.

## Non-goals

- Retiring `refresh-architecture-docs.yml`, `rerun-transient-doc-refresh.yml`, the prompts under
  `.github/prompts/`, the `docs/product/infrastructure/manual/` copies and the README and docs text
  that describe a monthly refresh. That is a second spec (B), written once this one is approved, so
  the removal and its test and wording changes are reviewed on their own. Until it merges the owner
  can switch the schedule off in the Actions tab ("Disable workflow"), which is reversible.
- Shortening `05-a-ARCHITECTURE.md` or changing REQ-GOV-004 and its inventory blocks. This spec reads
  the same inventory and leaves those documents and their checks as they are.
- Restructuring the canvas itself and declaring its board in `canvases.yml`. The canvas is changed
  only through the refresh-canvas skill, in chat, diff first and on the owner's approval (Close-out).
- Cost figures and live table statistics. The export reads no billing data and no database; the
  canvas keeps its cost figure as a canvas-owned field until a later spec sources it.
- Any scheduled or per-merge run, any committed export, any bot branch or bot PR.
- The open PRs that make the monthly refresh mergeable (#1426, #1383). Spec B proposes closing them;
  closing is the owner's call. #1384 (retired service leftovers) is unaffected.

## Approaches considered

1. Commit the export on every merge, checked by CI like `model-registry.json`. Always current, but
   the owner asked for on demand instead.
2. Keep a monthly job and let it open its own PR. This is the shape that has failed since September:
   it needs a gate exception for one bot branch, which is a gate change with its own red-team pass,
   and still produces a PR to review each month.
3. Chosen: run on demand and commit nothing. The export is either a workflow run artifact (with
   live state, run from main where the Workload Identity condition allows it) or the output of the
   exporter run on a fresh clone of main. Because nothing is committed, there is no PR and nothing
   for the gate to judge; provenance is the main commit recorded inside the export, checked by the
   canvas skill before it writes anything.

## Design

### 1. Exporter

`scripts/maintenance/architecture_export.py`, run as
`python3 -m scripts.maintenance.architecture_export [--snapshot PATH | --live] --output PATH`.
It is a thin layer over `scripts/maintenance/doc_inventory.py` and never re-parses the repo. One
inventory gap is closed there, not in the exporter: `repo_inventory` has no services today, so a new
`deploy_services()` in `doc_inventory.py` lists the Cloud Run services `gcp/deploy.sh` and
`platform/deploy.sh` deploy (`discord-interactions`, `failure-notifier` through
`NOTIFIER_SERVICE`, `solyra-api-staging` through `SERVICE`), and `repo_inventory` returns it as
`services`.

Output (`schema: "architecture-export/1"`, keys sorted, two-space indent, trailing newline):

- `sources`: `commit` (HEAD), `files` (blob ids of `gcp/deploy.sh`, `platform/deploy.sh`,
  `gcp/schema.sql`, tree id of `platform/api`), `live` (`null`, or `{read_at, project, region}` from the snapshot).
- `jobs[]`: `name`, `kind` (`fetcher` when the entry module is under `gcp.fetchers`, else
  `compute`), `module`, `deploy_function`, `resources` (memory, cpu, timeout, retries),
  `schedules[]` (scheduler name, cron, time zone, args), `reads[]` and `writes[]` (table names
  `job_table_edges` resolves), `possible_reads` and `possible_writes` (table name to template, from
  its `unresolved` map: a run-time template whose family member is chosen at run time, so the
  table may be touched but is not asserted), `live` (`null`, or `{exists, last_execution: {time, result}}`).
- `services[]`: `name`, `declared` (boolean, from `deploy_services`), `live` (`null` or `{auth, min_instances,
  max_instances, created}`).
- `schedulers[]`: `name`, `cron`, `time_zone`, `target` (`{kind, name, uri}`: kind `job` from
  `target_job`, `service` from `target_service` or from a `target_uri` whose host variable the
  inventory already maps to a service (`service_url` is `failure-notifier`), else `uri` from
  `target_uri`), `args`, `live`
  (`null` or `{state}`). Service-targeting schedulers such as `discord-warm-open` keep their
  destination.
- `tables[]`: `name`, `kind` (table, view, materialized view), `writers[]`, `readers[]`,
  `possible_writers[]`, `possible_readers[]` (job names, split the same way as the job lists).
- `counts`: `declared` for jobs, services, schedulers, tables, routes; `live` for jobs, services and
  schedulers from the snapshot, and `null` for tables and routes, which `live_snapshot` does not read
  (relations come from a separate database read this design excludes, and deployed routes are not
  listed by any read). The job summary shows a `null` count as "not read".
- `drift`: `declared_not_live`, `live_not_declared`, `paused_schedulers`, each a sorted list of names.

Rules: no `file:line` citation anywhere (names only, so an unrelated edit never changes the export);
refuse a dirty tree under `gcp/`, `lib/`, `scripts/`, `platform/api`, `platform/deploy.sh` so `sources.commit` is true;
`--live` raises on any failed read, as `live_snapshot` already does (CLAUDE.md Rule 3.7).

### 2. On-demand workflow

`.github/workflows/architecture-export.yml`, name "Architecture export":

- `on: workflow_dispatch` only. First step refuses any ref but `refs/heads/main`, the same check the
  monthly workflow uses, because the Workload Identity provider only admits main.
- `permissions: contents: read, id-token: write`. Authenticates with the existing
  `GCP_WIF_PROVIDER` / `GCP_WIF_SA_EMAIL` secrets; needs only the viewer roles that service account
  already has (run, scheduler, cloudbuild, cloudsql viewer, secretmanager viewer, pubsub, logging,
  cloudtasks, artifactregistry reader, storage object viewer). No database secret, no Gemini.
- Runs the exporter with `--live`, uploads `architecture-export.json` as artifact
  `architecture-export` (`retention-days: 30`), and writes the counts table and the three drift
  lists to the job summary so a run can be read without downloading anything.
- Commits nothing, pushes nothing, opens no PR or issue. `timeout-minutes: 15`.

How to run it: Actions, "Architecture export", "Run workflow" on main; or from a session with GCP
access, `python3 -m scripts.maintenance.architecture_export --live --output architecture-export.json`
on a clean checkout of main.

### 3. Capacity (CLAUDE.md Rule 0)

- Volume: about 70 declared jobs, 68 schedulers, 74 relations and 102 routes; 337 Python files
  scanned under `gcp/`, `lib/`, `scripts/`, `platform/api`. The export is tens of kilobytes.
- Velocity: repo mode makes no network call. Live mode makes the reads `live_snapshot` makes today:
  about 20 `gcloud` calls (one list per resource type plus one IAM read per service), independent of
  the number of jobs.
- Wall-clock: the reference scan the exporter reuses took 19 s on the 2026-11-10 tree; 20 calls at
  1 to 3 s add 20 to 60 s. Under 2 minutes in total against a 15 minute timeout.
- Cost: an on-demand GitHub-hosted run of a few minutes and read-only API calls; no Cloud Run job,
  no scheduler, nothing recurring.

### 4. Canvas skill

`.claude/skills/refresh-canvas/SKILL.md` gains a path for a canvas whose `canvases.yml` entry names
`source_export: architecture` instead of `source_json`:

1. Get the export: download artifact `architecture-export` from the latest successful "Architecture
   export" run on main, or run the exporter with `--live` (or `--snapshot`) on a fresh clone of main.
2. Provenance: `sources.commit` must be an ancestor of, or equal to, main; otherwise refuse
   ("Canvases track main"). Report how many commits main has moved since, and `sources.live.read_at`.
3. Steps 2 to 7 of the skill are unchanged: read the canvas, diff the repo-owned fields only, show
   the diff, write only on approval, data line only, never layout.

The `canvases.yml` entry itself changes from `report-only` to `source_export` only after the canvas
has a data board the skill can diff (Close-out), on a `docs/canvases-…` branch.

## Risks

- The export drifts from the inventory documents. It is built from the same functions, and the
  "built from the inventory" item forbids a second parser.
- The diagram overstates dependencies. Run-time table families stay in the possible lists, as the
  inventory digest already marks them, so a candidate is never drawn as a confirmed edge.
- A stale export reaches the canvas. The provenance step refuses an export not on main and reports
  how far behind main it is and when live state was read.
- The workflow is misused as a writer. The workflow test pins its trigger, permissions and the
  absence of push, PR, issue and database steps.
- Line-number churn returns. The determinism item forbids `file:line` values.

## Close-out (after merge, not pre-merge boxes)

1. Owner runs "Architecture export" on main once; the run's summary shows live counts and drift.
2. In chat, with the refresh-canvas skill: restructure the canvas's node data into one data board
   keyed by job, service and scheduler name, with repo-owned and canvas-owned fields, shown as a diff
   and saved only on the owner's approval.
3. On a `docs/canvases-…` branch, change the canvas entry in `docs/product/canvases.yml` to
   `source_export: architecture` with its board and fields.
4. Spec B: retire the monthly refresh (Non-goals).
