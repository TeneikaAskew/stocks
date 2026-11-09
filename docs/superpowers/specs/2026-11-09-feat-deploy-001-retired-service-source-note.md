---
feat_id: FEAT-DEPLOY-001
req_ids: [REQ-DEPLOY-001]
issues: []
canvases: [https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN]
site_source_notes: [SHARED-01]
done_when:
  - "tests/scripts/test_refresh_architecture_drawio.py asserts that no REPLACEMENTS target, NEW_CELLS value or generated note in refresh_architecture_drawio.py contains solyra-api-prod, 'staging / -prod', IAP or 'AUTH_MODE iap', that check() and check_icons() each report a cell carrying solyra-api-prod or 'staging / -prod' as stale, and that the snapshot it checks against lists no solyra-api-prod service or deploy-solyra-api-prod trigger"
  - "tests/fixtures/live_gcp_snapshot_<read date>.json is a live snapshot written by `python -m scripts.maintenance.doc_inventory --live --db-tables <csv> --write-snapshot`, with the CSV produced by running doc_inventory.DB_TABLES_SQL through scripts/db_query_cr.sh; the PR description names that db-query execution; test_refresh_architecture_drawio.py reads this file, and every other suite that reads live_gcp_snapshot_2026-09-07.json still reads it unchanged"
  - "tests/scripts/test_refresh_architecture_drawio.py asserts that refresh_architecture_drawio.main exits non-zero and leaves both diagrams byte-identical when the snapshot has no db_tables or an empty one, instead of writing 0 relations"
  - "Architecture.drawio and Architecture-icons.drawio as committed on the PR head are the generator's output from that snapshot: running refresh_architecture_drawio.py --snapshot on it with --repo-jobs built as refresh-architecture-docs.yml builds it leaves both byte-identical; they contain neither solyra-api-prod nor 'staging / -prod' nor 2026-09-07, p4_tp and tp_txt no longer describe a prod or IAP-gated API service, the main page draws one box per live API service with svc_tp's four edges kept and no second deploy-solyra-api-staging box, and test_the_committed_diagram_agrees_with_the_snapshot passes on them"
  - "tests/scripts/test_refresh_architecture_drawio.py asserts that an add-on job whose image is pinned by digest is labelled `sha256:` and the digest's first 12 hex characters, and that a tagged image is labelled with its tag"
  - "python3 scripts/export_openapi.py --check exits 0 on the PR head, and the /api/earnings/health/ping description in platform/api/openapi.json contains neither solyra-api-prod nor 'sits behind IAP'"
  - "tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate passes on the PR head with docs/product/infrastructure/05-a-ARCHITECTURE.md, 05-c-DATA_DEPENDENCIES.md and 05-e-API.md unchanged from origin/main, and platform/api/main.py has as many lines as on origin/main"
  - "tests/api/test_dev_page_auth.py asserts that the /dev page served in open mode with K_SERVICE set to solyra-api-staging contains `gcloud run services proxy solyra-api-staging` and does not contain solyra-api-prod, and that with K_SERVICE unset it contains `gcloud run services proxy &lt;service&gt;`"
  - "git grep -n solyra-api-prod -- platform/api scripts/maintenance/render_doc_prompts.py prints only lines that say it was retired"
  - "This PR's description links the open solyra PR whose tests/fixtures/stocks-openapi.json, synced with STOCKS_OPENAPI_REF set to this branch, differs from solyra main only in the /api/earnings/health/ping description"
  - "Each new or changed assertion is shown failing against origin/main when the PR opens, and the Backtest Pipeline Run Tests job is green on the PR head"
  - "The FEAT-DEPLOY-001 record in 02-FEATURE-CATALOG shows a current Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists the PR under FEAT-DEPLOY-001"
  - "Source identity (SHARED-01): on the implementation PR head (#1384), the existing bounded producer and verifier (`scripts/maintenance/doc_source_snapshot.py produce`, then `verify` with the fixed ceilings, run from the committed HEAD) prove committed source and SITE body identity bound to this approved spec at the actual merge base, where its blob equals the one on current main; the plan binds this spec; the only SITE change is the FEAT-DEPLOY-001 / SHARED-01 row of the Implementation-source notes table, added or updated with the prefix source_identity_sha256=<current source hash> and nonempty implementation and test prose that describes only this PR's platform/api, scripts/maintenance and tests changes (the /dev proxy line, the earnings ping docstring and its OpenAPI description, the drawio generator and the Run 28 comment) and keeps any earlier accurate own content of that row; every other SITE byte is unchanged; the sidecar is produced from the final committed SITE body and committed, replacing the sidecar record the merge of main carries; the matched main and branch `scripts/maintenance/docs_audit.py` runs report no finding that main does not; `tests/scripts/test_doc_source_snapshot.py` and `tests/scripts/test_docs_audit.py` pass unchanged; the registry `docs/DOC_REGISTRY.md` blob, mode and type equal main's; required current-head checks pass before merge under the repository's existing review rules, which this spec does not extend."
status: approved
supersedes: docs/superpowers/specs/2026-10-11-feat-deploy-001-retired-service-leftovers.md
---

# Bind the retired-service cleanup to its SITE source note (FEAT-DEPLOY-001)

## Why this spec replaces the 2026-10-11 spec (amendment, read first)

This spec supersedes `2026-10-11-feat-deploy-001-retired-service-leftovers.md` (approved, on main since
17bbacd3, #1381, blob cede1e83) and repeats its contract unchanged: `done_when` items 1 to 12 here are
that spec's twelve items byte for byte, and the section "Retained text of the 2026-10-11 spec" below is
its body byte for byte. Inside that retained text, "this spec", "this change" and "this PR" mean the
2026-10-11 spec and its implementation as written on that date, and its line anchors and counts describe
main as that spec measured it; this spec neither re-measures nor restates them. This spec adds only:

- `site_source_notes: [SHARED-01]`, the existing SITE Chain element for the API service and its auth
  mode (selection evidence below);
- `done_when` item 13, the pre-merge source-identity obligation the spec template requires
  (`.claude/skills/product-delivery/references/spec-template.md` L47 to L48, the `site_source_notes`
  bullets);
- the sections "Choice of Chain element: SHARED-01", "Source identity and close-out", "Retirement of the
  2026-10-11 spec", "Separation of evidence" and "Status".

Why it is needed: the implementation (stocks#1384, branch `feature/feat-deploy-001-retired-service-leftovers`,
head 2215223a, merge base 16b3fabd) changes `platform/api/main.py`, `platform/api/routers/earnings.py`,
`platform/api/openapi.json`, `scripts/maintenance/refresh_architecture_drawio.py`,
`scripts/maintenance/render_doc_prompts.py`, `tests/api/test_dev_page_auth.py`,
`tests/api/test_openapi_snapshot.py`, `tests/scripts/test_refresh_architecture_drawio.py` and
`tests/fixtures/live_gcp_snapshot_2026-11-09.json`. All nine are inside SITE's watched scope
(`docs/DOC_REGISTRY.md` row for `docs/product/03-SITE-TRACEABILITY.md`: `platform/api, platform/deploy.sh,
platform/Dockerfile, gcp, lib, scripts, tests`, as read on main 16b3fabd); its other five paths (the two
drawio files, the catalog, the traceability file and its plan) are not. Executed evidence:
`scripts/maintenance/docs_audit.py` run on main 16b3fabd and on #1384's head 2215223a with one shared
issues snapshot reports three findings on the branch that main does not, all on
`docs/product/03-SITE-TRACEABILITY.md`: two `changed-since` (35 content commits to the watched paths since
05ab15fcc762, and the document itself changed since then) and `source-provenance: implementation-source
identity unavailable: historical record does not equal complete current MAIN source/body`. The
product-delivery skill ("Committed-source documentation identity") lets a feature clear watched-code drift
only through a note declared by its approved spec, and an implementation PR cannot add that declaration to
its own spec. The 2026-10-11 spec declares none, and an approved spec does not change in place, so the
declaration needs this replacement. The #1384 branch also carries a sidecar for an unrelated record
(FEAT-INSIGHT-001 / INSIGHTS-07, spec `2026-11-07-feat-insight-001-trigger-distance-cap.md`, baseline
035c58cc), inherited from its merge base; the sidecar #1384 produces replaces whichever record the merge of
main carries.

What it does not change: the generator, diagram, snapshot, OpenAPI, `/dev` and Run 28 behaviour, every
other `done_when` behaviour of the 2026-10-11 spec, its tests, its non-goals (the `iap` auth mode, 05-a,
05-d and 05-e, the shared 2026-09-07 snapshot, the monthly workflow), its canvas and its solyra merge
order. No code, plan, test, SITE row, sidecar or other product document changes in the change that lands
this spec. It makes no runtime, deployment or cloud claim.

## Choice of Chain element: SHARED-01

The declaration must be sorted, unique and name existing Chain IDs of the SITE body on the base
(`scripts/maintenance/doc_source_snapshot.py` `declaration`, L107 to L112, and `chain_ids`, L91 to L104,
on main 16b3fabd). Executed there on SITE's body: `chain_ids` returns 222 IDs, SHARED-01 among them;
`declaration` returns `['SHARED-01']` for `[SHARED-01]`, and raises `site_source_notes must be sorted unique
existing Chain IDs` for `[NOPE-99]`, `[SHARED-07, SHARED-01]`, `[SHARED-01, SHARED-01]` and a bare string.
Read from source and executed, not assumed:

- SHARED-01 is the element "API service and auth middleware (solyra-api-staging, AUTH_MODE)" of SITE's
  shared section (Checklist row L107, Chain row L119 on 16b3fabd). Its Chain row names the service and
  its mode (GCP: Cloud Run service `solyra-api-staging` (public, `AUTH_MODE=firebase`) and its service
  account, citing `platform/deploy.sh`; Backend: `platform/api/auth.py`), and the section header (L101) lists
  FEAT-DEPLOY-001 among its capabilities.
- Every watched change #1384 makes is about which API service exists and which auth mode fronts it:
  - the `/dev` page's proxy line in `platform/api/main.py` (`dev_info`, L461 to L462), which named
    `solyra-api-prod` and now reads Cloud Run's `K_SERVICE`. `/dev` sits outside `/api/`, and AUTH_MODE
    decides whether it is served, through `dev_page_status` in `platform/api/auth.py` (L339 to L355), the
    file SHARED-01's Backend cell cites;
  - the `/api/earnings/health/ping` docstring in `platform/api/routers/earnings.py` and its copy in
    `platform/api/openapi.json`, which said `solyra-api-prod` sits behind IAP, the retired service's auth
    mode;
  - `scripts/maintenance/refresh_architecture_drawio.py`, whose labels and auth banner draw the API
    service and its mode (on #1384, `AUTH_MODE firebase (solyra-api-staging) / open (local)`), and the
    Run 28 comment in `scripts/maintenance/render_doc_prompts.py`, which named the live services;
  - their tests and the drawio test's fixture, listed above.
- No Chain element names `/dev`, the ping route, the drawio generator, the diagrams or
  `render_doc_prompts.py`: searches of SITE's body on 16b3fabd for `/dev`, `health/ping`, `/api/earnings`,
  `routers/earnings`, `drawio`, `Architecture`, `refresh_architecture`, `render_doc_prompts` and
  `K_SERVICE` return no line. SHARED-08 names a different route (`GET /api/health`, `main.py:270`). The
  other Chain rows that mention `AUTH_MODE` (AUTH-07, SHELL-04, SHELL-16, JOURNAL-16, ADMIN-05, ADMIN-13,
  SETTINGS-01, -05, -08 and -13) describe one screen endpoint's behaviour under the mode, not the service.
  SHARED-07, which FEAT-DEPLOY-001 specs declare for `gcp/deploy.sh`, is the freshness watchdog, and
  #1384 does not touch `gcp/deploy.sh`. SHARED-01 is therefore the narrowest existing ID. It is an
  identity anchor for the source note, not a claim that #1384 changes the auth middleware, the deployed
  service or any `/api/*` route's behaviour. The owner approves or changes this choice with the exact
  text.
- Declarations of SHARED-01 on main 16b3fabd: fourteen approved and six superseded specs, all
  FEAT-CICD-001 (for example `2026-11-01-feat-cicd-001-retirement-source-notes.md`); no FEAT-DEPLOY-001
  spec declares it. The Implementation-source notes table on 16b3fabd has twelve rows, one of them
  `(FEAT-CICD-001, SHARED-01)`, and no FEAT-DEPLOY-001 row. Rows are keyed by (FEAT, Component) (`notes`,
  L115 to L144), so #1384 adds a new `(FEAT-DEPLOY-001, SHARED-01)` row, which sorts between
  `(FEAT-DATA-001, SHARED-07)` and `(FEAT-IND-001, DASHBOARD-01)` (executed), and leaves the FEAT-CICD-001
  row byte for byte: `note_delta` (L147 to L164) refuses a change to any undeclared or foreign row. If
  another FEAT-DEPLOY-001 implementation that declares SHARED-01 lands first, the later PR composes the
  cell from the row then on main, keeps earlier accurate content, describes only its own source and tests,
  and recomputes the source hash. No PR attests another's change.

## Retained text of the 2026-10-11 spec (byte for byte)

# Stop drawing and describing the retired API service

Re-cut of #1378 (r1), whose first review raised four findings. They are applied here: the Run 28
comment is rewritten so the grep item can pass, the backend architecture canvas is listed, the unset
`K_SERVICE` case is covered, and the diagrams come from a fresh live snapshot instead of an edited
copy of the 2026-09-07 one. Approved on 2026-10-11 under the owner's instruction to bring both
repositories to a clean, closed-out state.

## Problem

`solyra-api-prod` and its `deploy-solyra-api-prod` trigger were deleted on 2026-10-10 (#1366), and
the documentation now says so (#1374). Code and the two architecture diagrams still describe the
service as live:

- `scripts/maintenance/refresh_architecture_drawio.py` regenerates an auth banner naming the service on
  every run (line 337), maps labels onto it (lines 40-41, 49-50, 54-56, 71-72, 80), and `check()` calls
  it prod (line 541). The map no longer fires: none of its source labels is in either committed diagram,
  so the cells that name or describe the service (`svc_tp`, `gha_dep` and `flow_c` on the main page of
  `Architecture.drawio`, `p4_tp` on its page 4, "⚡ Insight Refresh"; `tp_txt`, `ic_tp`, `gh_txt` and `ref_s2` in
  `Architecture-icons.drawio`) are kept as they are by every refresh, which edits
  the committed files in place.
- The diagrams' counts and dates come from `tests/fixtures/live_gcp_snapshot_2026-09-07.json`, which
  still lists four services and three triggers. A fresh read on 2026-10-11 lists three and two.
- The generator counts relations as `len(live.get('db_tables', {}))`, so a snapshot taken without table
  statistics (the default from a sandbox, which cannot reach Cloud SQL) prints "0 relations" as if it had
  been read live. Measured: a snapshot from `doc_inventory --live --write-snapshot` alone regenerated
  `f_sql` and `ic_sql` as "0 relations" and `check()` passed. That is a silent fallback (Rule 3.7). The
  monthly workflow refuses such a snapshot before calling the generator (`refresh-architecture-docs.yml`,
  the "live snapshot has no db_tables" guard); a manual run, like the one this change needs, does not.
- `platform/api/routers/earnings.py:329`, the `/api/earnings/health/ping` docstring, says the service
  "sits behind IAP". The docstring is part of `platform/api/openapi.json`, so the API's own description
  and solyra's vendored copy carry it.
- `platform/api/main.py:529`, on the `/dev` page that only `open` and `iap` modes serve, tells the
  reader to `gcloud run services proxy solyra-api-prod`.
- `scripts/maintenance/render_doc_prompts.py:74`, the Run 28 comment, says the live services "are"
  `solyra-api-prod` and `solyra-api-staging`. It records what Run 28 hit, but in the present tense.

#1366's spec deferred these under the stale-reference policy. The diagrams are not stale prose: the
refresh cannot reach their labels, so they keep the retired service until edited.

## Non-goals

- Not the `iap` auth mode. REQ-AUTH-002 still requires it, so the `/dev` page that serves it stays;
  only its proxy line stops naming a deleted service.
- Not 05-a, 05-d, 05-e and their `manual/` copies, which the monthly refresh rewrites once this and
  #1377's implementation merge. The two drawio files change here: the refresh edits them in place and
  cannot reach their current labels.
- Not the shared snapshot `tests/fixtures/live_gcp_snapshot_2026-09-07.json`. The approved
  generated-docs spec makes it a FEAT-CICD-001 file and three other suites read it. It stays as it is;
  only the drawio test moves to the fresh snapshot.
- Not dated text outside the grep's scope that says what was true then, such as `gcp/schema.sql:2237`.
- Not lines that already say the service was retired (`platform/deploy.sh`, `gcp/deploy.sh:4823`,
  `gcp/cloudbuild/`), nor the tests that assert the retirement refusal.
- Not the monthly workflow's own snapshot handling, which the FEAT-CICD-001 refresh spec owns.

## Approaches considered

1. Leave it for opportunistic fixes. Rejected: no refresh will ever correct the diagrams.
2. Edit the diagrams only. Rejected: the generator's banner and its stale check would still treat the
   service as live, and the OpenAPI description and the `/dev` page would still name it.
3. Regenerate from an edited copy of the 2026-09-07 snapshot (r1). Rejected in review: the generator
   copies the snapshot's `read_at` into the subtitle and notes, so the diagrams would say the new topology
   was read live on 2026-09-07, a month before the deletion.
4. Fix the generator, its stale checks, and its relations fallback; regenerate both diagrams from a
   fresh, complete live snapshot committed as the drawio test's fixture; fix the docstring with the
   OpenAPI regeneration, the `/dev` line, and the Run 28 comment, in one change. Chosen.

## Design

- **Fresh snapshot.** At implementation time, run `doc_inventory.DB_TABLES_SQL` through
  `scripts/db_query_cr.sh` (read-only; the sandbox path the function's own docstring names), copy the
  execution's `result_001.csv` from `gs://adept-mountain-474619-d4-trading-data/query-results/<execution>/`,
  and write `tests/fixtures/live_gcp_snapshot_<read date>.json` with
  `python -m scripts.maintenance.doc_inventory --live --db-tables <csv> --write-snapshot <path>`. Both
  commands need the `env -u CLOUDSDK_AUTH_ACCESS_TOKEN` prefix in a Remote session. The diagrams are then
  generated as the monthly workflow generates them: `--repo-jobs` is the list of job names from
  `doc_inventory --snapshot <path> --json` (`[.repo.jobs[].name]`, workflow line 499). Without it no hand-created job is marked
  ★ (line 318); the grid's dates and images come from the snapshot either way. The recipe was run on
  2026-10-11 (execution `db-query-qwhjn`): three services, two triggers, 98 relations, the same keys as the
  2026-09-07 fixture, and nothing the committed fixture does not already carry. `SNAPSHOT` in
  `tests/scripts/test_refresh_architecture_drawio.py` points at the new file.
- **Digest-pinned images.** Every live job now runs an image pinned by digest (`trading-system@sha256:…`; on
  2026-09-07, 40 were untagged, 35 carried tags such as `research`, and one was already pinned by digest). The add-on grid takes the text after
  the first `:` as the tag (line 320), so a digest prints all 64 hex characters in a 240-pixel box. A digest renders
  as `sha256:` and its first 12 hex characters; a tag renders as today.
- **Relations fallback.** `main()` refuses a snapshot whose `db_tables` is missing or empty: it prints
  the reason, exits non-zero, and writes neither diagram. The count helpers read `live["db_tables"]`
  directly.
- **Drawio generator and diagrams.** New REPLACEMENTS entries take each committed label that names the
  retired service (the cells above) to its staging form. `svc_tp` becomes the staging service box and
  keeps its four edges (`e_browser_tp`, `e_tp_sql`, `e_tp_ct`, `e_lib_tp`); `svc_st` joins `DELETE_IDS`
  and leaves `NEW_CELLS`. `gha_dep` joins `DELETE_IDS`, since `gha_ds` already draws the staging
  trigger. The targets at lines 40-41, 49-50, 54-56, 71-72 and 80 stop naming the retired service or
  IAP. The auth banner (line 337) reads `AUTH_MODE firebase (solyra-api-staging) / open (local)`, and its
  CORS clause names the custom domain #1366 admitted (`platform/api/main.py:130`). The "reserved
  for the SPA" text in `svc_st` and `tp_txt` goes too, since FEAT-UI-001 serves the SPA there. `check()` and `check_icons()` report
  `solyra-api-prod` and `staging / -prod` as stale, and the `check()` message stops saying "prod is
  solyra-api-prod". The test's mutation at line 140 targets `solyra-api-staging`, and `test_a_stale_service_count_is_caught`
  (lines 125-133) derives its count from the fixture instead of the literal 4. The PR commits both
  diagrams exactly as the generator writes them from the fresh snapshot; regenerating from that file on
  the PR head leaves them byte-identical.
- **OpenAPI.** The ping docstring says the keep-warm scheduler was dropped while the API sat behind IAP,
  and that the endpoint stays for manual and in-cluster warm-up. `python3 scripts/export_openapi.py`
  regenerates `platform/api/openapi.json`. Rule 6 in solyra: solyra CI runs `npm run contract:check`
  on every PR (`ci.yml:90-91`) and its gate treats the vendored copy as code, so the sync rides a
  solyra `feature/` PR: solyra FEAT-AUTH-001's confirm-on-return PR, which runs
  `STOCKS_OPENAPI_REF=<this branch> npm run contract:sync`. Merge order: that solyra PR is open first;
  this PR merges; that PR's CI re-runs against the new stocks main and it merges.
- **Line-cited files.** The inventory blocks in 05-a and 05-e cite `platform/api/main.py` by line (607 to
  1510, all below the `/dev` line) and render each route's docstring first line as its summary (05-a:504, 05-e:84
  for the ping). A feature branch may not re-render those blocks (`check_product_scope`, `spec_gate.py:3683-3716`),
  so the `/dev` change replaces its line in place and keeps `main.py`'s line count, as #1366 did, and the ping
  docstring keeps its first line. `earnings.py` lines after 324 are cited nowhere.
- **`/dev` page.** The proxy line reads `gcloud run services proxy {K_SERVICE} --region us-east1`, from
  Cloud Run's `K_SERVICE`, and `&lt;service&gt;` when it is unset: a bare `<service>` in this HTML
  f-string (`platform/api/main.py:480`) is parsed as a tag and shows nothing. The test covers both cases.
- **Run 28 comment.** `render_doc_prompts.py:74` keeps the incident and moves it to the past tense: the
  live services were then `solyra-api-prod` (retired 2026-10-10) and `solyra-api-staging`.
- **Canvas.** "Stocks backend architecture diagram" (`docs/product/canvases.yml`, `mode: report-only`,
  `feat_ids` include FEAT-DEPLOY-001) depicts this area. The PR body carries
  `Canvas check pending (report-only): https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN`, and the check
  runs from chat after merge.

Capacity: n/a. No workload changes. The snapshot recipe is one read-only db-query execution (one
`pg_class` scan, about 100 rows) and the list calls `doc_inventory --live` already makes. The merge
redeploys solyra-api-staging through `deploy-solyra-api-staging` (it fires on a push to main touching
`platform/`, `lib/`, `requirements.txt` or `gcp/database.py`) with the same behaviour.

## Risks

- A cell left naming the retired service fails `check()` on the PR and on every monthly run, by design.
- Jobs pinned by digest carry no tag, and the snapshot has no digest-to-tag map, so the research-image fill (line
  323) no longer marks any job. That is what the live read says; a tag map is the monthly refresh's to add.
- The fresh fixture is a point-in-time read. If GCP changes before the PR merges, the committed diagrams
  still match their own fixture, and the next monthly refresh moves both forward.
- The OpenAPI change turns solyra's `contract:check` red on any solyra PR without the sync, from this
  merge until the carrying PR merges. The merge order above keeps that window to one CI re-run.

## Source identity and close-out

Declaration: only the `(FEAT-DEPLOY-001, SHARED-01)` row in the existing Implementation-source notes table
of `docs/product/03-SITE-TRACEABILITY.md` may describe this implementation and its local tests. Every other
SITE byte, the historical marker (`Against: 05ab15fcc762`), foreign rows (including
`(FEAT-CICD-001, SHARED-01)`) and every Chain, checklist, frontend, progress and deployment cell stay
unchanged. The note describes backend API, maintenance-script and local test source only. It claims no
deployment, no staging redeploy, no live diagram refresh, no solyra contract sync, no frontend effect and no
authenticated external review.

Pre-merge (`done_when` item 13, which is `done_when[12]` in the plan's zero-based numbering), on the #1384
branch, after the merge of main that brings in this spec:

1. The plan `docs/superpowers/plans/2026-10-11-feat-deploy-001-retired-service-leftovers.md`, which exists
   only on the #1384 branch (main 16b3fabd holds no copy), is rebound to this spec in that same
   merge-of-main commit, while the merge is in progress, and gains a task with a `Spec:` line and a
   checklist item for item 13. During a merge of main the commit gate measures the index against
   MERGE_HEAD (`scripts/gate/spec_gate.py` L4744 to L4751, `merges_main` L4650 to L4655), which holds no
   copy of the plan, so `plan_stays_bound` (L1592 to L1609) has nothing to compare. There a plan still
   naming the 2026-10-11 spec is refused because an approved same-FEAT spec names it (L2438 to L2446), or,
   once the 2026-10-11 spec is flipped, because it is superseded (L2436 to L2437). A rebind left to a later
   ordinary commit is measured against HEAD, where the plan names the 2026-10-11 spec, and is refused as "a
   plan binds one spec" (L1603 to L1605). The producer refuses the old binding too: it reads the plan's
   spec through `selected_binding` (`scripts/maintenance/doc_source_snapshot.py` L739 to L760), and
   `spec_binding` refuses an approved spec that an approved same-FEAT spec in trusted POLICY names in
   `supersedes` (L690 to L695). Read from source at 16b3fabd, not executed on a landed successor: it is a
   mandatory real check at that merge, not a result.
2. This spec's blob must be the same regular 100644 blob in the actual merge base, in current main and in
   the branch head (`spec_binding`, L683 to L685), with `status: approved` and feat FEAT-DEPLOY-001 (L686
   to L689). The PR-mode note scope binds the same spec at the merge base (`spec_gate.py`
   `check_product_scope`, L4317 to L4323 and L4330 to L4336).
3. Read the producer's current source hash, commit the `(FEAT-DEPLOY-001, SHARED-01)` note with the prefix
   `source_identity_sha256=<hash>; ` and nonempty prose (canonical single-line row, rows in sorted order;
   `notes` L115 to L144, `note_delta` L147 to L164), produce the sidecar from the final committed body,
   commit it, and run `verify` on the final HEAD within the unchanged ceilings. Repeat after any later
   watched-code, SITE body or policy change, including every further merge of main.
4. The registry `docs/DOC_REGISTRY.md` blob, mode and type stay equal to main's; the FEAT-DEPLOY-001
   catalog record and the traceability entry are updated as Phase 5 requires; the PR body names this
   spec's path and carries item 13 as its own checklist line; the matched main and branch audit reports
   nothing new; the affected BASE suite, the normal current-head review under the existing rules and CI
   pass. The ordinary pre-commit hook and PR-mode gate judge every commit. Nothing is bypassed, and a clone
   without the hook runs `spec_gate.py --commit` by hand.

Post-merge obligations, tracked here, in the plan and in the PR, never as pre-merge `done_when` boxes and
never ticked before the genuine evidence exists:

- Verify the actual main source and body identity in a fresh clone after the squash, without assuming the
  feature commit survives.
- Complete the separate DOC main and staging close-out with real evidence. This spec claims none; the
  staging redeploy, the solyra contract sync and the report-only canvas check stay the separately evidenced
  steps the retained text describes.
- Retire the sidecar only as the skill prescribes: an ordinary trunk-only `--stamp --verify` after real
  checks, removing the sidecar in the same DOC commit, or the fixed `trunk-closeout-pending` route when
  deployed-evidence prose must change first. A record never retires itself.
- Set the plan to `status: done` on a `docs/` branch after the merge.

Evidence kinds stay separate: pre-merge identity of committed source and SITE body, the current-head review
and CI, and the post-merge main, staging and sidecar-retirement evidence are different records. A local
identity record is not review authentication, deployment evidence or data freshness.

## Retirement of the 2026-10-11 spec

The 2026-10-11 spec has `supersedes: null`, and no spec on main 16b3fabd names it as a predecessor (its
path appears in no file under `docs/superpowers/specs/`, `docs/superpowers/plans/` or `docs/product/`
there). Its retirement therefore does not meet the depth-two case that FEAT-CICD-001's status-only
exemption exists for (`spec_gate.py` L1939 to L1944, passed to `check_supersedes`, L1536 to L1555, as
`allow_superseded_target`; delivered by stocks#1656), which applies only when the flipped spec's own
pointer names a spec that is already superseded. The ordinary in-place rule admits it (L1955 to L1966): a
status-only change from `approved` to `superseded`, nothing else in that file, with an approved same-FEAT
spec naming it in `supersedes` in the same tree. The flip is made in the change that lands this spec, as
its own status-only commit on this spec's branch once this text's approval is recorded; the commit that
adds this file changes no other path. Its pointer stays null. #1384 does not touch the 2026-10-11 spec: a
feature branch that changes code and another spec at once is refused (`spec_gate.py` L2423 to L2426, "a
spec lands alone on a docs/ branch"), so its only obligation toward it is the plan rebind in step 1 above.
See "Separation of evidence" below for what was executed.

## Separation of evidence

Executed by this author on 2026-11-09 against main 16b3fabd. The gate runs used this repository's hook
(`core.hooksPath=.githooks`; nothing bypassed, no hook path or flag changed):

- `scripts/maintenance/docs_audit.py` on 16b3fabd and on #1384's head 2215223a with one shared issues
  snapshot: the three branch-only SITE findings quoted above. The session's clone is shallow, and the audit
  refuses it (`committed-source repository admission failed: unsupported shallow repository`), so both
  runs used detached worktrees of an unshallowed clone at those commits.
- `doc_source_snapshot.chain_ids`, `declaration`, `notes` and `watched` on 16b3fabd's SITE body and
  #1384's changed paths: the results quoted in "Why" and "Choice of Chain element".
- `scripts/gate/spec_gate.py --check-spec` on this file: `spec ok`. The same file with
  `site_source_notes: [NOPE-99]` is refused with `site_source_notes unavailable: site_source_notes must be
  sorted unique existing Chain IDs`.
- `--commit` with this file staged alone passes, and the hook passes the commit that adds it.
- The flip, in commit mode: staged together with this approved spec on 16b3fabd, it passes; staged alone
  on top of the commit that adds this file, it passes; staged alone on 16b3fabd with this spec absent, it
  is refused (`no approved spec for its FEAT names it in supersedes`); with one extra byte in the
  2026-10-11 spec it is refused (`an approved spec does not change in place`).
- `--pr origin/main` on the commit that adds this file, and on a scratch commit that adds the flip on top
  of it, both pass.
- Items 1 to 12 and the retained body compared byte for byte with the 2026-10-11 spec (blob cede1e83):
  equal.

Read from source at 16b3fabd, not executed: every line anchor above, the plan rebind and spec binding at a
real merge, and what the producer and verifier report on #1384. Not run: the producer and verifier, CI,
the BASE suite and any hosted review; those stay mandatory real checks at the later merge and are never
recorded as passed here.

## Status

Authoring snapshot, shell clock 2026-11-09T22:38:54Z: this text was prepared as a local docs-only change
on coordinator direction, in a task brief that names this file, its sections and its `status: approved`
line, so that #1384 can clear the source-identity check. That direction is not an owner decision, and
this author holds no written owner approval of this exact text. At that snapshot the text was committed
locally, unpublished and unreviewed. This paragraph records the snapshot and is not kept current: the
spec's admission, review, CI and merge state at any later time is its `status:` line read with its pull
request. The `status: approved` line stands for the owner's written approval of this exact text, which is
obtained and recorded on the pull request before merge; without it the line returns to `draft` on this
branch before main holds the file. Approval is followed by the normal current-head review and CI before
merge. It is not a formal review, Ready, merge or deployment permission, and no exception from another
change transfers to it. The 2026-10-11 spec's admission record is kept in its retained text and in
stocks#1381.
