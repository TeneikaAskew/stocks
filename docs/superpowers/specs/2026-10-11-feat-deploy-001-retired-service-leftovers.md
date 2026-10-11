---
feat_id: FEAT-DEPLOY-001
req_ids: [REQ-DEPLOY-001]
issues: []
canvases: []
done_when:
  - "tests/scripts/test_refresh_architecture_drawio.py asserts that no REPLACEMENTS target, NEW_CELLS value or generated note in refresh_architecture_drawio.py contains solyra-api-prod, AUTH_MODE=iap or (IAP), that check() and check_icons() each report a cell carrying solyra-api-prod or 'staging / -prod' as stale, and that the live snapshot it checks against lists no solyra-api-prod service or deploy-solyra-api-prod trigger"
  - "Architecture.drawio and Architecture-icons.drawio as committed on the PR head contain neither solyra-api-prod nor 'staging / -prod', p4_tp and tp_txt no longer describe a prod or IAP-gated API service, the main page draws one box per live API service with svc_tp's four edges kept and no second deploy-solyra-api-staging box, and test_the_committed_diagram_agrees_with_the_snapshot passes on them"
  - "python3 scripts/export_openapi.py --check exits 0 on the PR head, and the /api/earnings/health/ping description in platform/api/openapi.json does not contain solyra-api-prod"
  - "tests/api/test_dev_page_auth.py asserts that the /dev page served in open mode with K_SERVICE set to solyra-api-staging contains gcloud run services proxy solyra-api-staging and does not contain solyra-api-prod"
  - "git grep -n solyra-api-prod -- platform/api scripts/maintenance/render_doc_prompts.py prints only lines that say it was retired"
  - "This PR's description links the open solyra PR whose tests/fixtures/stocks-openapi.json, synced with STOCKS_OPENAPI_REF set to this branch, differs from solyra main only in the /api/earnings/health/ping description"
  - "Each new or changed assertion is shown failing against origin/main when the PR opens, and the Backtest Pipeline Run Tests job is green on the PR head"
  - "The FEAT-DEPLOY-001 record in 02-FEATURE-CATALOG shows a current Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists the PR under FEAT-DEPLOY-001"
status: approved
supersedes: null
---

# Stop drawing and describing the retired API service

## Problem

`solyra-api-prod` and its `deploy-solyra-api-prod` trigger were deleted on 2026-10-10 (#1366), and
the documentation now says so (#1374). Code and the two architecture diagrams still describe the
service as live:

- `scripts/maintenance/refresh_architecture_drawio.py` regenerates an auth banner naming the service on
  every run (line 337), maps labels onto it (lines 40-41, 49-50, 54-56, 71-72, 80), and `check()` calls
  it prod (line 541). The map no longer fires: none of its source labels is in either committed diagram,
  so the cells that name or describe the service (`svc_tp`, `gha_dep`, `flow_c`, `p4_tp` on the main
  page; `tp_txt`, `gh_txt`, `ref_s2` on the icon page) are kept as they are by every refresh, which edits
  the committed files in place.
- `platform/api/routers/earnings.py:329`, the `/api/earnings/health/ping` docstring, says the service
  "sits behind IAP". The docstring is part of `platform/api/openapi.json`, so the API's own description
  and solyra's vendored copy carry it.
- `platform/api/main.py:529`, on the `/dev` page that only `open` and `iap` modes serve, tells the
  reader to `gcloud run services proxy solyra-api-prod`.

#1366's spec deferred these under the stale-reference policy. The diagrams are not stale prose: the
refresh cannot reach their labels, so they keep the retired service until edited.

## Non-goals

- Not the `iap` auth mode. REQ-AUTH-002 still requires it, so the `/dev` page that serves it stays;
  only its proxy line stops naming a deleted service.
- Not 05-a, 05-d, 05-e and their `manual/` copies, which the monthly refresh rewrites once this and
  #1377's implementation merge. The two drawio files change here: the refresh edits them in place and
  cannot reach their current labels.
- Not the shared snapshot `tests/fixtures/live_gcp_snapshot_2026-09-07.json`. The approved
  generated-docs spec makes it a FEAT-CICD-001 file and three other suites read it; this change drops the
  retired service from the test's own copy instead.
- Not dated text that says what was true then: `gcp/schema.sql:2237` and the Run 28 comment in
  `scripts/maintenance/render_doc_prompts.py:74` are history and keep it in the past tense.
- Not lines that already say the service was retired (`platform/deploy.sh`, `gcp/deploy.sh:4823`,
  `gcp/cloudbuild/`), nor the tests that assert the retirement refusal.

## Approaches considered

1. Leave it for opportunistic fixes. Rejected: no refresh will ever correct the diagrams.
2. Edit the diagrams only. Rejected: the generator's banner and its stale check would still treat the
   service as live, and the OpenAPI description and the `/dev` page would still name it.
3. Fix the generator, its stale checks and both diagrams, the docstring with the OpenAPI regeneration,
   and the `/dev` line, in one change. Chosen.

Chosen on 2026-10-11 under the owner's instruction to bring both repositories to a clean, closed-out
state.

## Design

- **Drawio generator and diagrams.** New REPLACEMENTS entries take each committed label that names the
  retired service (the cells above) to its staging form. `svc_tp` becomes the staging service box and
  keeps its four edges (`e_browser_tp`, `e_tp_sql`, `e_tp_ct`, `e_lib_tp`); `svc_st` joins `DELETE_IDS`
  and leaves `NEW_CELLS`. `gha_dep` joins `DELETE_IDS`, since `gha_ds` already draws the staging
  trigger. The targets at lines 40-41, 49-50, 54-56, 71-72 and 80 stop naming the retired service or
  IAP. The auth banner (line 337) reads `AUTH_MODE firebase (solyra-api-staging) / open (local)`, and its
  CORS clause names the custom domain #1366 admitted (`platform/api/main.py:130`). `svc_st`'s "reserved
  for the SPA" text goes too, since FEAT-UI-001 serves it. `check()` and `check_icons()` report
  `solyra-api-prod` and `staging / -prod` as stale, and the `check()` message stops saying "prod is
  solyra-api-prod". The test's `live` fixture drops the retired service and trigger in code and sets the
  service count to 3; the shared snapshot is unchanged. The test's mutation at line 140 targets
  `solyra-api-staging`. The PR commits both diagrams as the generator writes them from that snapshot.
- **OpenAPI.** The ping docstring says the keep-warm scheduler was dropped while the API sat behind IAP,
  and that the endpoint stays for manual and in-cluster warm-up. `python3 scripts/export_openapi.py`
  regenerates `platform/api/openapi.json`. Rule 6 in solyra: solyra CI runs `npm run contract:check`
  on every PR (`ci.yml:90-91`) and its gate treats the vendored copy as code, so the sync rides a
  solyra `feature/` PR: solyra FEAT-AUTH-001's confirm-on-return PR, which runs
  `STOCKS_OPENAPI_REF=<this branch> npm run contract:sync`. Merge order: that solyra PR is open first;
  this PR merges; that PR's CI re-runs against the new stocks main and it merges.
- **`/dev` page.** The proxy line reads `gcloud run services proxy {K_SERVICE} --region us-east1`, from
  Cloud Run's `K_SERVICE`, and `&lt;service&gt;` when it is unset: a bare `<service>` in this HTML
  f-string (`platform/api/main.py:480`) is parsed as a tag and shows nothing.

Capacity: n/a. No workload changes; the merge redeploys solyra-api-staging through
`deploy-solyra-api-staging` (it fires on a push to main touching `platform/`, `lib/`,
`requirements.txt` or `gcp/database.py`) with the same behaviour.

## Risks

- A cell left naming the retired service fails `check()` on the PR and on every monthly run, by design.
- The OpenAPI change turns solyra's `contract:check` red on any solyra PR without the sync, from this
  merge until the carrying PR merges. The merge order above keeps that window to one CI re-run.
