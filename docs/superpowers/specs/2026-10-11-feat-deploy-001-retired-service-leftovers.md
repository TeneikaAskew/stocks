---
feat_id: FEAT-DEPLOY-001
req_ids: [REQ-DEPLOY-001]
issues: []
canvases: [https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN]
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
status: approved
supersedes: null
---

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
