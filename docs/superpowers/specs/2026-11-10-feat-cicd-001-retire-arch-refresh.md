---
feat_id: FEAT-CICD-001
req_ids: [REQ-DATA-001, REQ-GOV-004]
issues: [1118, 1409, 1661]
canvases:
  - https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN
site_source_notes: [SHARED-01]
done_when:
  - "Retired files (F): tests/scripts/test_check_generated_docs.py::test_the_monthly_refresh_is_retired asserts that .github/workflows/refresh-architecture-docs.yml and .github/workflows/rerun-transient-doc-refresh.yml do not exist, that refresh-architecture-docs.yml.disabled and rerun-transient-doc-refresh.yml.disabled exist beside them and each opens with a comment naming 2026-11-10 and this spec, that no file exists under .github/prompts/, and that .github/scripts/is_transient_gemini_failure.sh and scripts/maintenance/render_doc_prompts.py do not exist; the test fails on main before F."
  - "Retired tests (F): tests/meta/test_refresh_architecture_docs_pr_token.py, tests/meta/test_refresh_open_pr_step.py, tests/meta/test_rerun_transient_doc_refresh.py and tests/meta/test_render_doc_prompts.py are deleted, and test_marker_names_agree_between_module_docs_and_gate moves with its body unchanged into tests/scripts/test_check_generated_docs.py, where it passes."
  - "No scheduled-refresh claim (F): tests/scripts/test_check_generated_docs.py::test_no_maintenance_doc_claims_a_scheduled_refresh asserts that every line matching the Design's PATTERN in README.md, SETUP.md, .github/workflows/README.md, docs/DOC_REGISTRY.md, docs/INVESTMENT_MODELS_SUMMARY.md, docs/product/05-INFRASTRUCTURE.md, docs/product/09-SECURITY-AUTH.md, docs/product/infrastructure/05-a-ARCHITECTURE.md, 05-c-DATA_DEPENDENCIES.md, 05-e-API.md and docs/product/infrastructure/manual/README.md also contains the word retire, retired or retirement; that README.md has no heading Removed since last refresh, contains neither on each refresh nor on the 1st, and its documentation-map row for 05-d-COST_ANALYSIS.md does not contain the word monthly; that the title of docs/product/infrastructure/manual/README.md does not contain auto-refreshed; and that scripts/maintenance/doc_inventory.py names refresh-architecture-docs only inside OWNED_BADGE and never contains the words refresh workflow. git grep -n -I -i -E with PATTERN over '*.md' and '*.drawio' on the F head lists no path outside those files and the Design's dated-record set."
  - "Docs audit (F): tests/scripts/test_docs_audit.py asserts that scripts/maintenance/docs_audit.py defines none of OWNING_JOB, check_owning_job, fetch_owning_runs, fetch_owned_prs, DRY_RUN_MARKER and DELIVERING_MARKER and that its source never names refresh-architecture-docs; that --no-owning-job-check is still accepted and a run with it reports the same findings as one without on the same fixture; that region_owner('generated', None) names the renderers and no workflow; and that check_best_effort_artifacts reports exactly one P2 class-a finding, whose detail names python -m scripts.refresh_calibration_table and neither a workflow nor a refresh PR, for a calibration block dated 181 days before the audit date, and none for one dated 180 days before. tests/scripts/test_doc_source_snapshot.py passes unchanged."
  - "Generated-doc gates (F): tests/scripts/test_check_generated_docs.py asserts that 05-d-COST_ANALYSIS.md is in none of DOCS, MODEL_DOCS, DIFF_DOCS, REGENERATED and CHURN_EXEMPT, that check_generated_docs.py defines neither gate_regenerated_structure nor gate_cost_content and its source never names .github/prompts, and that README_REQUIRED_LINKS, EXPECTED_MARKERS and _MARKER_LINE equal main's; test_committed_docs_pass_every_gate passes, and tests/scripts/test_spec_gate.py passes unchanged."
  - "README badges (F): tests/scripts/test_check_generated_docs.py asserts that doc_inventory.readme_badges returns the four img.shields.io badge lines and no github.com/.../actions/workflows badge, and that insert_readme_badges over a README still carrying the Architecture refresh badge removes it; README.md on the F head carries no workflow badge."
  - "Issue 1118 (F): tests/scripts/test_refresh_calibration_table.py asserts that the footer _build_markdown writes contains python -m scripts.refresh_calibration_table and neither monthly nor refresh-architecture-docs, and that the footer line inside the ticker_calibration_resolved_values region of docs/INVESTMENT_MODELS_SUMMARY.md equals it byte for byte; python -m scripts.refresh_calibration_table --check without Cloud SQL variables exits 2."
  - "Diagrams (F): on the F head, python scripts/maintenance/refresh_architecture_drawio.py --check with --snapshot set to the file named by the SNAPSHOT constant of tests/scripts/test_refresh_architecture_drawio.py prints 0 problem(s), so the ext_gh and gha_group workflow counts equal the number of active *.yml workflows (refresh_architecture_drawio.active_workflows); that test file asserts that the ext_gh, gha_group and gha_other cells of Architecture.drawio, the g_cicd cell of Architecture-icons.drawio, every REPLACEMENTS target and both gha_label forms contain neither refresh-architecture-docs nor doc refresh, and the whole file passes."
  - "On-demand procedure (F): README.md's Maintenance section states that the refresh was retired and that the steps are optional, and lists exactly the three command groups of the Design, none naming a dated fixture for the diagrams; on the F head the insert command prints unchanged for 05-a, 05-c and 05-e and the step 2 pytest command passes."
  - "Records PR (D, docs/ branch, merged before F is marked ready): it changes only docs/DOC_REGISTRY.md, docs/product/05-INFRASTRUCTURE.md, docs/product/09-SECURITY-AUTH.md, docs/product/infrastructure/05-a-ARCHITECTURE.md, 05-c-DATA_DEPENDENCIES.md, 05-d-COST_ANALYSIS.md, 05-e-API.md and docs/product/infrastructure/manual/README.md as the Design lists; 05-a carries one review marker of the form **Last reviewed:** unknown · **Last scanned:** <date> · **Owner:** TBD directly after its header blockquote and 05-c one directly after its H1 (docs_audit.find_markers finds exactly one in each); 05-d keeps every existing byte and ends with an appended, dated status block naming docs/audits/COST_AUDIT_2026-09-06.md and #1409; neither 05-a nor 05-c links .github/workflows/refresh-architecture-docs.yml; tests/scripts/test_check_generated_docs.py passes on the D head."
  - "Registry (D): docs/DOC_REGISTRY.md's rows read exactly as the Design's registry table, and docs_audit.check_registry_paths and check_regions report no finding for those rows on the D head and again on the F head, where the prompts are gone."
  - "Matched audits: python3 scripts/maintenance/docs_audit.py --issues-snapshot <capture no older than its one-day limit> --no-owning-job-check --json on the D head reports exactly five findings that main does not, listed in D's PR and approved by the owner as this spec's one exception: changed-since P2 on docs/product/03-SITE-TRACEABILITY.md (content commits to its watched paths since 05ab15fcc762), changed-since P2 on 03-SITE (the document itself changed since 05ab15fcc762), source-provenance P2 on 03-SITE (implementation-source identity unavailable: SOURCE registry blob/mode/type differs from trusted POLICY), and marker P3 incomplete provenance (never reviewed; no reviewed-against SHA, so drift cannot be checked) on 05-a and on 05-c. On the F head, after the push that merges main with D, it reports no finding that main does not, and none of the three 03-SITE findings. Both PRs pass python3 scripts/gate/spec_gate.py --pr origin/main, current-head hosted code review and required CI before merge."
  - "Gate files untouched: the D and F diffs leave scripts/gate/ (pinned copies included), .githooks/pre-commit, .github/workflows/spec-gate.yml, .github/workflows/registry-check.yml, tests/scripts/test_spec_gate.py and tests/scripts/test_export_model_registry.py byte-identical, so no red-team pass applies."
  - "Records (F): the FEAT-CICD-001 record in docs/product/02-FEATURE-CATALOG.md shows a current Status and Last reviewed, docs/product/12-PR-ISSUE-TRACEABILITY.md lists F under FEAT-CICD-001, and F's body closes #1118; no other capability's row or record changes."
  - "Source identity (SHARED-01): on the F head, the existing bounded producer and verifier (scripts/maintenance/doc_source_snapshot.py produce, then verify with the fixed ceilings, run from the committed HEAD) prove committed source and SITE body identity bound to this approved spec at the actual merge base, where its blob equals the one on current main; the plan binds this spec; the only SITE change is the FEAT-CICD-001 / SHARED-01 row of the Implementation-source notes table, updated with the prefix source_identity_sha256=<current source hash> and nonempty prose that describes only F's scripts and tests changes, keeping every sentence of the existing row unless it is false on the F head; every other SITE byte is unchanged; the sidecar is produced from the final committed SITE body and committed; the registry docs/DOC_REGISTRY.md blob, mode and type equal main's (D included)."
status: draft
supersedes: null
---

# Retire the monthly architecture-doc refresh

## Authority

On 2026-11-10 the owner decided to retire the schedule and the Gemini steps of
`.github/workflows/refresh-architecture-docs.yml`, to keep the deterministic renderers as tools a person
or agent runs on demand, and to add an on-demand live-snapshot path only later, if a need appears.
stocks#1426, which kept the model, was closed the same day (`state: closed`, `merged: false`, read with
the GitHub tools). This file is a draft for the owner's approval, including the audit exception in
done_when 12. Line numbers are read at main `4f552e93`; the only change since `4245d545` is the #1770
spec file, so they equal `4245d545`'s.

## Problem

The workflow has not delivered what it was built for, and what it does deliver is done better elsewhere.

- **Runs:** 38 runs, 9 succeeded and 29 failed; the 6 scheduled ones split 3 and 3
  (`actions_list list_workflow_runs resource_id=refresh-architecture-docs.yml`, `total_count: 38`). The
  latest, run 38 on 2026-11-01, failed at Verify; its issue #1661 was closed not planned on 2026-11-10.
- **Delivery:** four refresh PRs (#750, #953, #1060, #1240); only #953 merged (2026-09-02), and #1009
  rebuilt the documents it touched by hand five days later. No scheduled run has produced a merged,
  correct update (PR states read with `list_pull_requests head=TeneikaAskew:bot/arch-refresh-2026-MM`;
  the #1009 rebuild and the run causes are from the evaluation, sections 3 and 5.4).
- **Model content:** the prose of 05-a and 05-c on main has been hand-maintained since #1009 (evaluation
  5.4). 05-d is #953's 2026-09-02 model output, written from billing data that ends on 2026-09-02:
  `docs/audits/COST_AUDIT_2026-09-06.md` lines 21 to 27 record the move to a billing account with no
  BigQuery export, and the open owner issue #1409 confirms no cost data after 2026-09-01. So 05-d
  cannot become current from any repository change.
- **What already works without it:** the spec gate's render check and
  `test_committed_docs_pass_every_gate` keep every code-derived inventory block equal to a fresh render
  on each PR (executed: `doc_inventory --snapshot <fixture> --insert` printed `unchanged` for 05-a, 05-c
  and 05-e), and `verify-docs-against-live.yml` reads live drift every weekday.
- **#1118:** the calibration step swallows its failure (`python -m scripts.refresh_calibration_table ||
  echo "::warning::..."`, workflow lines 904 to 905), while `docs/INVESTMENT_MODELS_SUMMARY.md` line 326
  and the footer `scripts/refresh_calibration_table.py` writes (lines 146 to 149) say the table is
  "Auto-refreshed monthly by `.github/workflows/refresh-architecture-docs.yml`". The owner's comment on
  #1118 of 2026-11-10 found the block not stale against the database (latest `calibration_date`
  2026-07-01) and asked for a manual-refresh label instead.

## Non-goals

- An on-demand live-snapshot path. #1770's on-demand architecture export merged as a draft spec at
  `47f77f49` and was approved at `4f552e93` (#1771); its implementation adds
  `.github/workflows/architecture-export.yml`. This spec neither depends on nor blocks it. Until a live
  path exists, the live-derived blocks and the README badges stay at the 2026-09-07 snapshot and the
  diagram counts at the snapshot `tests/scripts/test_refresh_architecture_drawio.py` reads, and the docs
  say so.
- Revoking any role of `arch-refresh-bot@`, deleting a GitHub secret or changing the WIF provider.
  Revocation is the owner's step. D's note names only the five original doc-refresh roles as serving no
  remaining workflow, and keeps `cloudscheduler.viewer` and `cloudtasks.viewer`, which
  `verify_docs_against_live.py` needs (`gcloud scheduler jobs list` at line 372, `tasks queues list` at
  line 385).
- #1239 (the quarterly `calibrate-thresholds` drift refusals), the calibration data, and enabling the
  billing export (#1409, an owner action in the billing console).
- `docs/product/07-MODEL-REGISTRY.md` DOC-09 and its generated JSON: a dated audit finding and its
  disposition ("FILED as #1118"), which stay true as records and feed the models canvas.
- The `docs/product/infrastructure/manual/` copies, which stay as Class B snapshots of 2026-09-08; only
  their README is reworded. Deleting them is a separate decision.
- `.claude/commands/resolve-issue.md`, `.github/ISSUE_TEMPLATE/01-defect.yml` and
  `03-dormant-surface.yml`, which search `.github/prompts` as one of four executable-markdown scopes.
  With the directory gone that search is a no-op: `git grep -qE -e anything -- .github/no-such-dir`
  exits 1 (executed).
- The `Removed since last refresh` headings of 05-a (§18, line 1123) and 05-c (§9, line 1436) stay:
  `check_generated_docs.py` names them (`REMOVED_HEADING`, line 156; `HISTORY_OK`, line 177) and 05-a's
  table of contents links the anchor (line 28). They head lists of what was removed, not a schedule claim.
- Pruning model-only code paths that stay harmless in kept modules (`doc_inventory`'s digest renderers,
  `check_generated_docs.gate_transcripts`), and `verify_docs_against_live.py`'s enrolment of 05-d.
- Shortening 05-a, changing REQ-GOV-004, the render check or the 2026-09-07 fixture.

## Approaches considered

From the evaluation (section 7), one line each:

- A. Keep the workflow and make its PRs mergeable as #1426 designed: about 10 nominal PRs, two gate
  red-team passes, then a monthly PR of model prose that has drawn a P1 each time.
- B. Keep a monthly deterministic refresh without Gemini: most of A's one-time cost for live counts no
  one has asked for monthly.
- C. Retire the workflow outright: 2 to 4 nominal PRs, no gate change.
- **D, chosen (owner, 2026-11-10).** C's retirement now, keeping the renderers for on-demand use, with a
  live-snapshot path only if a need appears. It stops the red runs, issues, stub PRs and review load at
  the cost of the unattended cadence, which has not delivered since September.

Two choices inside D:

- **Rename, not delete, the two workflow files.** CLAUDE.md "Workflow retirement / Cloud-Run-migration
  convention" says a fully retired workload with no replacement is renamed to `*.yml.disabled` with a
  header saying when and why; `.github/workflows/README.md` keeps a Retired table for them. Everything
  else the workflows alone used is deleted. Deleting the two files instead is the owner's option and
  changes only done_when 1.
- **Two PRs, not three.** The registry row `D | .github/prompts/*.md` must leave in the same change that
  deletes the prompts, or `check_registry_paths` reports P1 "registry declaration matches no tracked
  document"; removed before, the prompts read as unclassified (both executed). The prompts can only be
  deleted on a feature branch (`is_documentation` returns False under `.github/prompts/`, spec_gate.py
  lines 1343 to 1345), and that feature PR cannot touch the registry (below). Replacing the row in D
  with `X | .github/*.md` resolves it (trade-off under Risks).

## Design

### Two PRs, in this order

**D: `docs/retire-arch-refresh-records`.** Every `docs/product/` and registry change. Its wording is true
whether or not F has merged: it describes what reaches main (renders on PRs, hand-maintained prose)
rather than the workflow's state.

**F: `feature/feat-cicd-001-retire-arch-refresh`.** The code, tests, workflow files, prompts,
non-product docs and the SITE source note.

Why D comes first:

1. F cannot pass while 05-a links the workflow file. With the two workflow files removed and nothing
   else changed, `test_committed_docs_pass_every_gate` failed with "README.md: dead relative link
   .github/workflows/refresh-architecture-docs.yml" and the same for 05-a (executed). F fixes README;
   only a `docs/` PR may change 05-a's prose (`check_product_scope`, spec_gate.py line 4278 onward).
2. F changes watched SITE paths (`scripts/`, `tests/`; SITE's registry row names `platform/api,
   platform/deploy.sh, platform/Dockerfile, gcp, lib, scripts, tests`), so it needs the source note, and
   the note route refuses a branch whose `docs/DOC_REGISTRY.md` differs from main's
   (`doc_source_snapshot.py` lines 613 to 618). So the registry changes in D.
3. Any registry change unverifies SITE's source identity until a source-note PR rebinds it, because the
   policy hash includes the registry blob (`Snapshot.policy`, lines 613 to 627). Executed:
   `doc_source_snapshot.py verify` gave "SOURCE registry blob/mode/type differs from trusted POLICY" on a
   registry-only branch and "note is not bound to current committed source identity" with that change
   landed. The repository has done this once: #1548 (`d78201b0`, 2026-10-27 10:01) changed the registry
   and left main unverified until #1621 (`e7c48250`, 15:01 the same day) rebound it (all three commits
   verified with today's verifier). D's audit therefore shows the five findings done_when 12 lists:
   the three 03-SITE ones, which are temporary and which F's sidecar and note clear, and two P3
   "incomplete provenance" findings for the new markers, which stay like those on README, 05-e and
   `INVESTMENT_MODELS_SUMMARY.md`. No CI job runs the docs audit (`git grep docs_audit -- .github
   scripts/gate`), so nothing mechanical blocks D; the owner approves the exception with this spec.

The sequence, to keep the SITE window to F's review time:

1. F is opened as a draft and stays one while D is open (a draft triggers no Codex review, CLAUDE.md
   "A resolved thread is not a reviewed commit").
2. D is reviewed and merged.
3. One push to F merges main, commits the SITE note and the sidecar produced against the new registry,
   and F is marked ready. Its first review covers its final shape, inside the two-round cap.

### D: what changes

| File | Change |
|---|---|
| `docs/product/05-INFRASTRUCTURE.md` | Lines 40 to 53: no schedule and no workflow link. 05-a and 05-c: inventory blocks rendered by `doc_inventory.py`, carried by the PR that changes what they cite (REQ-GOV-004), prose hand-edited. 05-d: dated record of 2026-09-02 billing data. 05-e: rendered from the router files. |
| `05-a-ARCHITECTURE.md` | Line 5 header note: the same render statement, prose maintained by hand. Line 43: the identity behind the `GCP_WIF_PROVIDER` and `GCP_WIF_SA_EMAIL` secrets that `deploy-staging.yml` (lines 227 to 228) and `verify-docs-against-live.yml` (lines 51 to 52) authenticate with. Line 122: the billing export with no reader named, its tables ending 2026-09-02 (cost audit section 1, #1409). Line 819: 05-d as a dated record. Line 869: the §14 row removed. Line 1146: footer keeps `Generated 2026-09-07` and `from the 2026-09-07 live snapshot`, drops the monthly sentence. A review marker after the header blockquote. |
| `05-c-DATA_DEPENDENCIES.md` | Line 3 and line 1440: the render statement without a refresh; a review marker after the H1. |
| `05-d-COST_ANALYSIS.md` | Every existing byte kept; an appended, dated status block (DOC_REGISTRY line 28: a Class C record "may receive an appended, dated status block"): written 2026-09-02 from billing data that ends that day, not maintained, see `docs/audits/COST_AUDIT_2026-09-06.md` and #1409. Main's cost gates still pass on it until F removes them. |
| `05-e-API.md` | Line 5: "on every monthly refresh" becomes the PR render statement. |
| `docs/product/09-SECURITY-AUTH.md` | Line 302 in the past tense, with the retirement decision on the line that names the file, and one dated sentence: the owner decided on 2026-11-10 to retire the refresh; of the roles in this section only the five original doc-refresh roles (`cloudasset.viewer`, `iam.securityReviewer`, `bigquery.dataViewer`, `bigquery.jobUser`, `aiplatform.user`) then serve no workflow (read from source, not checked live), `cloudscheduler.viewer` and `cloudtasks.viewer` stay needed by `verify_docs_against_live.py`, and any revocation is the owner's step. |
| `manual/README.md` | Title (line 1, "the auto-refreshed documents") and lines 3 to 8 and 17 to 21 in the past tense: the copies are 2026-09-08 snapshots taken when a scheduled workflow rewrote the originals in place; the originals have been maintained by hand since. |
| `docs/DOC_REGISTRY.md` | The rows below; narrative: Class A means a renderer regenerates the region (`doc_inventory.py`, `refresh_calibration_table.py`, `refresh_architecture_drawio.py`, the registry exporter); the delivery-check clause, the "Model prose (`prose:`)" and "Job ran but its PR never merged" routing rows and the stray-write paragraph (lines 108 to 114) are removed; the quotation of the workflow's `Freeze gate inputs` step (lines 65 to 68) dates the retirement decision on the line that names the file; the 2026-09-16 history (lines 31 to 44) keeps the past tense without the quoted PR title. |

Registry rows after D (all others unchanged):

| Class | Path glob | Declared code paths | Generated regions |
|---|---|---|---|
| A | README.md | gcp/deploy.sh, gcp/schema.sql | `line:img\.shields\.io; line:^Generated \d{4}-\d{2}-\d{2}\b` |
| A | docs/product/infrastructure/05-a-ARCHITECTURE.md | unchanged | the nine `inventory:` specs, no `prose:` |
| A | docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md | unchanged | the nine `inventory:` specs, no `prose:` |
| C | docs/product/infrastructure/05-d-COST_ANALYSIS.md | | |
| X | .github/*.md | | |

The last row replaces `D | .github/prompts/*.md | scripts/maintenance/doc_inventory.py`. With `prose:`
gone, docs_audit treats 05-a's and 05-c's prose as Class D and requires a review marker (docs_audit.py
line 7800 makes them stampable; lines 7825 to 7827 report "no review marker"). The marker is the form
README, 05-e and `INVESTMENT_MODELS_SUMMARY.md` carry (line 3 of each):

```
**Last reviewed:** unknown · **Last scanned:** <date> · **Owner:** TBD
```

It is chosen because `Last reviewed` "is only ever moved by an actual review" (`render_marker`'s
docstring, line 4136) and D reviews nothing. An `Against` SHA is worse: set to main's SHA it added
"changed-since ... the document itself changed since" P2s on both documents on the D head (executed); set
to a D commit it breaks after the squash; and any valid `Against`, such as a post-merge stamp, adds a
changed-since P2 to every later PR touching their declared paths (independent review, executed there). `--stamp` inserts after the H1, which in 05-a fails
`gate_stale_asof` ("the header note carries no as-of label", executed); after the blockquote the docs test
passes and `find_markers` reads it (executed).

### F: what is retired

| Path | Lines | Action | Only user, `git grep` at main |
|---|---|---|---|
| `.github/workflows/refresh-architecture-docs.yml` | 1,145 | renamed `.yml.disabled`, header added | itself; `rerun-transient-doc-refresh.yml` (`on: workflow_run`, lines 56 to 59) |
| `.github/workflows/rerun-transient-doc-refresh.yml` | 230 | renamed `.yml.disabled`, header added | fires only on the refresh's completion |
| `.github/scripts/is_transient_gemini_failure.sh` | 150 | deleted | the re-run workflow and its test |
| `.github/prompts/{architecture,cost-analysis,data-dependencies}.md` | 302 | deleted | the workflow, `render_doc_prompts.py`, `check_generated_docs._promised_sections` (line 740, cost-analysis only), tests, the registry `prose:` rows (gone in D) |
| `scripts/maintenance/render_doc_prompts.py` | 177 | deleted | the workflow (line 454) and `tests/meta/test_render_doc_prompts.py` |
| `tests/meta/test_refresh_architecture_docs_pr_token.py`, `test_refresh_open_pr_step.py`, `test_rerun_transient_doc_refresh.py`, `test_render_doc_prompts.py` | 2,403 | deleted, except `test_marker_names_agree_between_module_docs_and_gate` (lines 196 to 208), which reads only `doc_inventory`, `check_generated_docs` and the committed docs and moves to `test_check_generated_docs.py` | the workflow files, the prompts, the classifier, `render_doc_prompts.py`, the manual copies |

Other references to these names are history (`docs/audit/`, `docs/audits/`, `docs/superpowers/`, the
sidecar JSON), the non-goal process files, comments, or a string fixture (`tests/scripts/test_scripts.py`
lines 181 to 201 build branch names from the workflow name without reading a file). Kept:
`doc_inventory.py`, `refresh_architecture_drawio.py`, `check_generated_docs.py`,
`verify_docs_against_live.py`, `refresh_calibration_table.py`, the 2026-09-07 fixture.

### F: what changes

- **`scripts/maintenance/docs_audit.py` and `tests/scripts/test_docs_audit.py`.** Remove the Class A
  delivery audit: `OWNING_JOB` (line 6738), `fetch_owned_prs` (6774), `DRY_RUN_MARKER` (6995),
  `DELIVERING_MARKER` (7012), `_run_delivered` (7015), `fetch_owning_runs` (7068), `_REFRESH_GEN_RE`
  (7146), `superseded` (7160), `last_delivering_conclusion` (7195), `check_owning_job` (7289 to 7469),
  its call (7692 to 7693), and every helper only they use. Kept as is, `check_owning_job` would fail
  forever once the file is gone: P1 "last delivering run concluded failure" for run 38 and P2 "Generated
  ... is Nd old; the refresh is monthly" (line 7468) for four documents, or exit 2 if GitHub stops listing
  runs for a renamed file (not checked). `--no-owning-job-check` (line 7480) stays accepted with help text
  saying it is ignored, because `tests/scripts/test_doc_source_snapshot.py` lines 183 and 426 pass it.
  `region_owner` (line 2628) routes a generated region to its renderer instead of the workflow.
  `BEST_EFFORT_ARTIFACTS` and `check_best_effort_artifacts` (lines 6861 to 6964) keep the 180-day bound
  (`STALE_DAYS`) but drop the best-effort-workflow premise from comments and details, and name the
  manual command.
- **What docs_audit reports after F.** For README, the two diagrams, 05-a, 05-c, 05-e and
  `INVESTMENT_MODELS_SUMMARY.md`: their declared regions (P1 when a region matches nothing or a marker is
  unbalanced), and on the hand-written remainder the Class D checks (review marker, drift since
  `Against`, dead links, closed issues). 05-d (Class C): cross-references only. The calibration table:
  one P2 class-a finding from the first audit date more than 180 days after its `latest calibration`
  date, 2026-12-29 for the current 2026-07-01, naming `python -m scripts.refresh_calibration_table`; it
  clears only when `ticker_calibration` gains a newer row, which is #1239's defect, so the finding is
  true rather than stuck. No check reads a `Generated` stamp's age; these documents are judged by their
  review markers like any living document.
- **`scripts/maintenance/check_generated_docs.py` and its test.** Remove `COST` from `DOCS`,
  `MODEL_DOCS`, `REGENERATED` and `CHURN_EXEMPT` (lines 73, 79, 110, 154) and therefore `DIFF_DOCS`;
  delete `_promised_sections` and `gate_regenerated_structure` (lines 734 to 773, the only prompt
  reader, which would report "cost-analysis.md: no numbered sections found" once the prompt is gone)
  and `gate_cost_content` with the floors and counters only it uses (lines 776 to 1021;
  `_is_table_sep`, which `gate_inline_rule` also calls at line 571, stays), and their calls (1473 to
  1474). Keep `README_REQUIRED_LINKS` (README still links 05-d and SETUP.md), `REMOVED_HEADING`,
  `EXPECTED_MARKERS` and `_MARKER_LINE`, which the spec gate imports (spec_gate.py lines 4043 to 4047,
  4196 to 4198). Docstring without the workflow. This changes renderer inputs, so F carries no 05-a, 05-c
  or 05-e change (REQ-GOV-004).
- **`scripts/maintenance/doc_inventory.py`.** `readme_badges` (line 4202) stops emitting the
  `![Architecture refresh](...refresh-architecture-docs.yml/badge.svg)` line (4241 to 4242);
  `OWNED_BADGE` (line 4183, the alternative at 4199) still claims it, so a render over an old README
  removes it. The docstring (line 6) and the strings at lines 412, 3686, 4267 ("the refresh workflow
  badge") and 4380 ("The refresh workflow pins one date") stop naming the workflow.
- **`scripts/refresh_calibration_table.py` and its test (#1118).** The footer (lines 146 to 149) becomes
  `_Manual refresh: \`python -m scripts.refresh_calibration_table\` (needs Cloud SQL access; not
  scheduled)._`, the docstring (line 20) loses "Auto-invoked monthly", and
  `docs/INVESTMENT_MODELS_SUMMARY.md` line 326 is set to that footer byte for byte. The renderer needs
  Cloud SQL and cannot run here; without its variables it exits 2 (executed), so it never swallows.
- **Diagrams.** `refresh_architecture_drawio.py`: `gha_label` (lines 264 and 266) and the REPLACEMENTS
  targets at lines 59, 61, 74, 75 and 362 lose "doc refresh" and the workflow name. `Architecture.drawio`
  cells `ext_gh` (line 43), `gha_group` (268) and `gha_other` (292) and `Architecture-icons.drawio` cell
  `g_cicd` (549) are edited to match. The counts in `ext_gh` and `gha_group`, the two that `check` reads,
  are set to the number of active `*.yml` workflows on F's head (`active_workflows`): 8 after the two
  renames at `4f552e93`, 9 if #1770's `architecture-export.yml` lands first; `g_cicd`'s count, which no
  check reads and which says 6 today, is set to the same number. With the two files removed (a rename is
  the same to `active_workflows`, which globs `*.yml`), `--check` reported "cell ext_gh says 10 workflows,
  live is 8" and the same for `gha_group`, and four drawio tests failed; with the two counts set to 8, 0
  problems and 10 passed (executed). Regenerating the whole diagram instead also changed ten job labels,
  so F edits only these cells.
- **Non-product docs and comments.** README.md: the workflow badge (line 11), lines 13, 21 (05-d is "the
  monthly GCP bill"; it becomes a dated record of 2026-09-02 billing data), 26 (05-e is rendered "on each
  refresh"; it becomes on each PR that changes the routers), 31 and 38, the Maintenance section (lines 42
  to 55), the `Removed since last refresh` heading (line 57, renamed; README has no table of contents, and
  the only gate that reads the section is the `--previous-dir` heading gate, which only the retired
  workflow ran, `check_generated_docs.py` line 8 and workflow line 795) and the footer (line 66, keeping
  `Generated 2026-09-07`). SETUP.md: retitled to the WIF setup that `deploy-staging.yml` and
  `verify-docs-against-live.yml` use; the refresh-only parts (the Vertex AI API, the five doc-refresh
  roles, the dry run, the model pin, Costs) are removed and one sentence records the retirement.
  `.github/workflows/README.md`: line 5 ("the monthly documentation refresh") and rows 16 and 17, which
  move to the Retired table. `.gitignore`: the `!refresh-inputs/` block (lines 196 to 204) goes; the
  `gha-creds-*.json` rule stays with its comment reworded. Comments naming the workflow in
  `deploy-staging.yml` (12, 44, 237), `verify-docs-against-live.yml` (46, 63) and `update-superpowers.yml`
  (22, 158) name the `.disabled` file.
- **Records.** The FEAT-CICD-001 catalog record and traceability section; the SITE note and sidecar.

PATTERN, for done_when 3, case-insensitive:

```
refresh-architecture-docs|rerun-transient-doc-refresh|monthly (architecture |documentation |doc )?(doc )?refresh|(re)?generated monthly|auto-refreshed monthly|on the 1st of (each|every) month|1st of month 06:00
```

The dated-record set it may still match: `docs/audit/`, `docs/audits/`, `docs/superpowers/`,
`docs/product/infrastructure/manual/` (Class B), `docs/product/infrastructure/05-d-COST_ANALYSIS.md`
(Class C), `docs/product/07-MODEL-REGISTRY.md` (DOC-09) and `.claude/commands/resolve-issue.md`
(non-goal). On main `4f552e93` the grep lists 35 paths (executed); every one outside that set is
relabelled or removed by D or F. done_when 3 adds the claims PATTERN cannot see: README's 05-d row,
section heading, "on each refresh" (line 26) and "on the 1st" (line 55), the manual README's title, and
the `doc_inventory.py` strings.

### The on-demand procedure (README Maintenance, written by F)

README.md's Maintenance section owns the repository's maintenance procedures (SETUP.md is one-time
setup). It says the refresh was retired, that nothing regenerates these files on a schedule, that every
step is optional, and that step 1 is also enforced on each PR by the spec gate and the docs test:

1. After changing what the blocks cite (`gcp/deploy.sh`, `gcp/schema.sql`, `platform/api`):
   `python -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --insert docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
   (the snapshot is the spec gate's `RENDER_SNAPSHOT`, spec_gate.py line 78).
2. To check the blocks and the diagrams, each against the snapshot its test names:
   `python -m pytest tests/scripts/test_check_generated_docs.py tests/scripts/test_refresh_architecture_drawio.py -k committed`
3. The calibration table, from a machine with Cloud SQL access (not a 443-only sandbox):
   `python -m scripts.refresh_calibration_table`, or `--check` to compare only.

It adds that the badges and the live-derived blocks show the 2026-09-07 snapshot, the diagram counts
the snapshot their test reads, and that no tool on main refreshes them from live state. Executed on main:
step 1 printed `unchanged` three times; step 2 ran the three committed-docs tests and
`test_the_committed_diagram_agrees_with_the_snapshot`, `4 passed`; step 3 without Cloud SQL variables
exited 2.

### Gate files and the Chain element

No gate file changes. `git grep` for every retired name over `scripts/gate`, `.githooks/pre-commit`, both
gate workflows and both gate suites returns a comment (spec_gate.py line 1348) and a synthetic fixture
(test_spec_gate.py lines 3678 and 3714); neither reads the real files. No red-team pass applies.

`site_source_notes: [SHARED-01]`: executed on SITE's body, `declaration` accepts it and refuses
`[NOPE-99]`, an unsorted pair, a duplicate and a bare string. No Chain element names any path F changes
(greps for the renderers, `render_doc_prompts`, `drawio` and `INVESTMENT_MODELS_SUMMARY` find nothing).
SHARED-01 is the component of the existing `(FEAT-CICD-001, SHARED-01)` note row, one of 15, and the
anchor every FEAT-CICD-001 spec with a note declares. It is an identity anchor, not a claim that F
changes the API service or its auth.

### Capacity (CLAUDE.md rule 0)

n/a: this removes one monthly workflow (about 20 to 25 runner minutes and three Gemini sessions per run,
evaluation section 6) and the re-run workflow that followed its failures, and adds no job, query,
schedule or cloud call. Vertex spend per run (the owner's figure of about $0.34) stops; not measured.

## Risks

- **A check that fails forever or passes on nothing.** Caught by done_when 4: the delivery audit is gone,
  and the one remaining freshness check reads the artifact's own date.
- **A dangling reference.** Caught by done_when 1, 3, 5 and 8 and by the docs test (dead links).
- **The SITE window.** From D's merge until F's one ready push lands, main reports the three 03-SITE
  findings, and every open source-note PR in other lanes must merge main and produce its sidecar again.
  Bounded by the draft sequence above; #1548 to #1621 lasted about five hours.
- **The `X | .github/*.md` row is broader than the row it replaces.** A future markdown file anywhere
  under `.github/`, at any depth (docs_audit matches with `fnmatch`, whose `*` crosses `/`), would be
  classed out of scope instead of reported as unclassified (P2, docs_audit.py line 7720). Today the glob
  matches five files; after F, two (`.github/workflows/README.md` and `pull_request_template.md`), and
  both keep their exact rows, which win (`classify`, most specific match). A narrower row needs the
  prompts deleted in the same change as the registry, which means a third PR, a second plan and a second
  registry change with its own SITE window; the owner can still narrow the row later.
- **Overlap with #1384 (and its spec #1764).** Both change `refresh_architecture_drawio.py`, the
  diagrams and the drawio test, and #1384 edits `render_doc_prompts.py`, which F deletes. #1384 also
  moves the drawio test's `SNAPSHOT` to `live_gcp_snapshot_2026-11-09.json`. done_when 8 and 9 name the
  test's snapshot rather than a date, so either order works: if #1384 lands first, F edits the cells of
  its regenerated diagrams; if F lands first, #1384 drops its `render_doc_prompts.py` hunk and
  regenerates with F's labels. Whichever lands second re-runs the drawio check and produces its sidecar
  again.
- **#1770.** Its `architecture-export.yml` changes the active workflow count; done_when 8 derives the
  count, so either order passes.
- **A run before F merges.** The next cron is 2026-12-01 06:00 UTC. A run in the D to F window opens a PR
  that cannot merge, as #1240 did; D's text stays true either way. The owner may disable the workflow in
  the Actions tab (reversible) if F slips past that date.

## Source identity and close-out

Declaration: only `FEAT-CICD-001 / SHARED-01` in the existing Implementation-source notes table may
describe F's source and tests. Every other SITE byte, the historical marker, foreign rows and every
Chain, checklist, frontend, progress and deployment cell stay unchanged. The note claims no deployment,
frontend effect or external review.

Pre-merge (done_when 15), in F's ready push, after the merge of main that brings in D and this approved
spec: this spec's blob is equal in the actual merge base, current main and F's head; read the producer's
source hash, commit the row with the `source_identity_sha256=<hash>; ` prefix, produce the sidecar from
the final committed body, commit it, run `verify` on the final head within the unchanged ceilings, and
repeat after any later watched-code, SITE-body or policy change, a further merge of main included.

Post-merge obligations, tracked here, in the plan and in the PR, never as pre-merge boxes and never
ticked before the evidence exists:

- Verify main's source and body identity in a fresh clone after the squash.
- Complete the DOC main and staging close-out with real evidence. F changes no deployed service; what
  counts as its staging evidence is the owner's decision at close-out, recorded then.
- Retire the sidecar only as the skill prescribes (product-delivery SKILL.md, the close-out routes).
- Set F's plan to `status: done` on a `docs/` branch after the merge, and run the canvas check below.

Canvas check pending (report-only), after F merges, through the refresh-canvas skill in chat: the backend
architecture diagram shows a "Docs refreshed 2026-09-02" pill (read from the artifact on 2026-11-10),
which no longer describes anything that runs.

## Separation of evidence

Executed (commands and outputs in the authoring report): the run history and refresh PR states; the
`--insert`, drawio and step 2 checks on main; the docs test and the drawio check and tests with the two
workflow files removed, and with the counts edited; `check_registry_paths`, `classify` and `check_regions`
for main, prompts deleted, the prompts row removed, and the D rows before and after the deletion;
`doc_source_snapshot.py verify` on main, on a registry-only branch, on it landed, and at `d78201b0^`,
`d78201b0` and `e7c48250`; `docs_audit.py --issues-snapshot --no-owning-job-check --json` on main
`4f552e93` and on a simulated D (its 05-a and 05-c edits, unknown markers, 05-d's appended status block,
the registry rows), which added exactly the five done_when 12 findings, and with main's SHA as `Against`,
which added two changed-since P2s instead of the P3s; that simulated D against
`test_check_generated_docs.py`, `tests/meta` and `test_verify_docs_against_live.py` (497 passed);
`find_markers`; `refresh_calibration_table --check` without Cloud SQL (exit 2); the empty-pathspec
`git grep` (exit 1); the SHARED-01 declaration check.

From the independent review, executed there: the D-commit `Against` marker breaking after a squash; a
trunk `Against` (a post-merge stamp) adding a changed-since P2 to a later PR; #1384's head checking clean
only against its 2026-11-09 snapshot.

Read from source, not executed: every line anchor; the roles the remaining WIF workflows need; F's
sidecar production after D.

Not checked: whether GitHub keeps listing runs for a renamed workflow file; live IAM; whether
`verify_docs_against_live.py` reports findings in 05-d's body; behaviour of any proposed code.

## Status

Draft prepared 2026-11-10 for the owner's decision, revised once after an independent review. Two owner
approvals are needed before `status: approved`: this exact text, and the one exception it carries, that
D's docs audit reports the five findings done_when 12 lists, three of them until F lands. Approval is
followed by current-head hosted code review and CI before merge. It is not a merge or deployment
permission.
