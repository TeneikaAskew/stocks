---
feat_id: FEAT-INSIGHT-001
spec: docs/superpowers/specs/2026-11-14-feat-insight-001-watchlist-write-routes-410-r2.md
branch: feature/feat-insight-001-watchlist-write-routes-410-r2
pr: null
status: ready
---

# Default watchlist lock, stage B, implementation plan (r2: site source notes): the web write routes answer 410

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances (done_when[0] is the first item).

**Goal:** `POST /api/insights/watchlist/add` and `DELETE /api/insights/watchlist/{ticker}` answer 410 and write nothing, once the live site shows solyra no longer calls them.

**Architecture:** A route dependency on the two write routes in `platform/api/routers/insights.py` raises `HTTPException(410, detail)` before the body is validated, and each handler's only statement raises it again, so no database work and no fabricated response remain; `_watchlist_owner` and the imports from `gcp.fetchers._watchlist` are deleted; the response models stay so the operations stay declared, with a 410 response added to the OpenAPI document.

**Tech Stack:** FastAPI (`platform/api`), pytest with the `client` fixture of `tests/api/test_platform_api.py:33` and the auth-mode pattern of `tests/api/test_platform_auth.py:33`.

**Spec:** `docs/superpowers/specs/2026-11-14-feat-insight-001-watchlist-write-routes-410-r2.md` (approved; it supersedes the 2026-11-13 stage B spec that this plan's predecessor, `2026-11-13-feat-insight-001-watchlist-write-routes-410.md`, named, and adds the `site_source_notes` declaration INSIGHTS-09, JOURNAL-01, OPTIONS-06, SIGNALS-01 with its done_when item, so Task 4 below is new and the close moves to Task 5).

**Precondition (owner's gate):** Task 1 runs first and the branch is not marked ready until its log read shows zero requests.

## Global Constraints

- The 410 detail, verbatim: `The watchlist is managed in Discord (/watchlist add, /watchlist remove); the web app keeps per-user lists in solyra.`
- Both routes stay declared (no deletion here; owner's decision 3) and keep their response models `WatchlistAddResponse` (`insights.py:543`) and `WatchlistRemoveResponse` (`platform/api/schemas.py:1479`).
- After this stage `platform/api/routers/insights.py` imports nothing from `gcp.fetchers._watchlist` and defines no `_watchlist_owner`.
- No em or en dashes in code or docs.

## Review Focus

1. A request body that fails validation (`{}` on POST) still answers 410, not 422: the 410 is raised by a route dependency, and FastAPI (0.162.4 here, `fastapi.dependencies.utils.solve_dependencies`) solves dependencies before it validates the body and collects body errors into the 422 afterwards, so the dependency's `HTTPException` wins. Declaring the body `Optional[...] = None` would not do it: a present `{}` is still validated against the model. A body that is not JSON at all still gets FastAPI's 422 from the decoder, which runs before dependencies; the test sends `{}`, valid JSON that fails the model. The typed `body: WatchlistAddRequest` parameter stays so the operation's `requestBody` in the OpenAPI document is unchanged. Pinned in Task 2.
2. An `OPTIONS` preflight to either route is unaffected (CORS middleware answers before routing); the test confirms a preflight still gets its CORS headers. Pinned in Task 2.
3. `extras` on the ranked route keeps working after the imports are removed (the ranked route does not use the deleted helpers). Pinned in Task 2 by re-running the stage A API tests.

---

### Task 1: Live-site precondition

Spec: § Live-site precondition. Advances done_when[3]. Owner or implementer, read-only.

- [ ] **Step 1:** confirm solyra's per-user watchlist implementation (solyra spec `2026-11-14-feat-insight-001-user-watchlist-v3.md`, solyra #341, merged as b4b37022 on 2026-11-14) is published on the live site, which is the deploy: fetch `https://stocks.insightscollective.org/` (`solyra-stocks.lovable.app` redirects there), its main bundle and every lazy chunk it names, and confirm no chunk contains the string `insights/watchlist/add` while the combobox chunk contains `api/me/watchlist`; note the time the published build changed (at 09:58Z on 2026-11-14 it still served the previous build).
- [ ] **Step 2:** at least one full trading day after that publish (a Saturday publish makes Monday the first full trading day, so the read runs on Tuesday or later), with `--freshness` set to cover the whole window from the publish time, run:
  ```
  env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud logging read \
    'resource.type="cloud_run_revision" AND resource.labels.service_name="solyra-api-staging"
     AND (httpRequest.requestUrl:"/api/insights/watchlist/add"
          OR (httpRequest.requestMethod="DELETE" AND httpRequest.requestUrl:"/api/insights/watchlist/"))' \
    --project=adept-mountain-474619-d4 --freshness=48h --limit=50 \
    --format='table(timestamp, httpRequest.requestMethod, httpRequest.requestUrl, httpRequest.status)'
  ```
- [ ] **Step 3:** zero rows: paste the command, the window and the empty result in the PR body. Any row: stop, name the caller in the PR, and wait.

### Task 2: The two routes answer 410 and write nothing

Spec: § Design, § Tests. Advances done_when[0] and done_when[1].

**Files:**
- Modify: `platform/api/routers/insights.py` (`add_to_watchlist`, decorator at `:607`; `remove_from_watchlist`, decorator at `:684`; `_watchlist_owner` `:61`; the `gcp.fetchers._watchlist` imports at `:624` and `:690`; the `from fastapi import` line at `:30`)
- Modify: `tests/api/test_watchlist_default_lock.py` (stage A's file; add the 410 tests)
- Modify: `tests/api/test_platform_api.py` (`TestWatchlistMutationAPI` at `:2101`, the four tests at `:2113`, `:2137`, `:2166` and `:2194`: `test_add_threads_default_owner_when_no_auth`, `test_add_scopes_to_signed_in_user`, `test_remove_scopes_to_signed_in_user`, `test_two_users_do_not_share_watchlist` are replaced by one `test_write_routes_answer_410`)
- Modify: `tests/gcp/test_watchlist_readers_default_owner.py` (drop `WRITE_ROUTE_EXCLUSION` at `:120` and `WRITE_ROUTES` at `:121` with the carve-outs at `:278`, `:298`, `:310` and the assertion at `:435` inside `test_only_the_named_writers_insert_or_update_watchlists`; delete `test_write_routes_read_back_their_own_rows_and_nothing_else_does` at `:362`, whose docstring already says stage B deletes it, and `test_write_routes_are_the_only_callers_of_watchlist_owner` at `:438`, whose own assertion message says to remove it once `_watchlist_owner` is gone; rewrite the module docstring at `:26-30`, which describes the exclusion; add `test_insights_router_imports_nothing_from_watchlist_helper`)
- Modify: `tests/api/test_ticker_info.py` (`TestTickerInfoAPI.test_watchlist_add_endpoint` at `:481-510` patches `gcp.fetchers._watchlist.add_to_watchlist` and expects 200 with enrichment data: delete it, since the route's 410 is covered in `tests/api/test_watchlist_default_lock.py` and nothing is enriched any more)
- Modify: `tests/api/test_route_coverage.py` (`:293` and `:294`: the POST `/api/insights/watchlist/add` and DELETE `/api/insights/watchlist/{ticker}` entries expect 503 with no backend; they become 410, with a note that the dependency answers before any backend is reached)
- Modify: `tests/meta/test_http_status_classification.py` (drop the `"routers/insights.py": 2` entry from `KNOWN_BACKLOG` at `:63`: the two handlers it counted as unclassified 503 answers no longer answer 503, and `test_the_pre_existing_backlog_only_shrinks` at `:126` fails when a file's count falls below its record)

**Interfaces:**
- Produces:
  ```python
  WATCHLIST_WRITE_RETIRED_DETAIL = "The watchlist is managed in Discord (/watchlist add, /watchlist remove); the web app keeps per-user lists in solyra."
  def _watchlist_writes_retired() -> None:      # route dependency: runs before body validation
      raise HTTPException(status_code=410, detail=WATCHLIST_WRITE_RETIRED_DETAIL)
  @router.post("/api/insights/watchlist/add", response_model=WatchlistAddResponse, response_model_exclude_unset=True,
               dependencies=[Depends(_watchlist_writes_retired)], responses={410: {"description": "The web write path is retired"}})
  def add_to_watchlist(body: WatchlistAddRequest, request: Request) -> WatchlistAddResponse       # its one statement: raise HTTPException(410, WATCHLIST_WRITE_RETIRED_DETAIL)
  @router.delete("/api/insights/watchlist/{ticker}", response_model=WatchlistRemoveResponse, response_model_exclude_unset=True,
                 dependencies=[Depends(_watchlist_writes_retired)], responses={410: {"description": "The web write path is retired"}})
  def remove_from_watchlist(ticker: str, request: Request) -> WatchlistRemoveResponse             # its one statement: the same raise
  ```
  `Depends` joins the `from fastapi import ...` line at `insights.py:30`.

- [ ] **Step 1: Write failing tests**: `test_add_and_remove_answer_410_in_open_mode` and `test_add_and_remove_answer_410_in_firebase_mode` (`monkeypatch.setattr(api.auth, "AUTH_MODE", "firebase")` with `_verify_bearer_email` stubbed to return `alice@example.com` for `Bearer good:alice@example.com`), both asserting the detail; `test_write_routes_touch_no_connection` (two recorders: `patch("gcp.database.get_engine")` with a fake engine whose `begin()` connection records every executed statement, and `patch("lib.agents.model_routing.connect")` with a fake DB-API connection whose `cursor().execute` records every statement, the path `add_to_watchlist` and `remove_from_watchlist` use at `gcp/fetchers/_watchlist.py:521` and `:571`; after both calls both records are empty, and the same test fails on origin/main); `test_add_with_empty_body_is_410_not_422`; `test_preflight_still_answers_cors`; in the scan file `test_insights_router_imports_nothing_from_watchlist_helper` (`"gcp.fetchers._watchlist" not in source` and `"_watchlist_owner" not in source`).
- [ ] **Step 2: Run** `pytest tests/api/test_watchlist_default_lock.py tests/api/test_platform_api.py -k watchlist tests/gcp/test_watchlist_readers_default_owner.py tests/api/test_ticker_info.py tests/api/test_route_coverage.py tests/meta/test_http_status_classification.py -v`; expected FAIL on the new tests and on the existing tests that still expect the write behaviour (the four in `TestWatchlistMutationAPI`, `test_watchlist_add_endpoint`, the two route-coverage entries, `test_write_routes_are_the_only_callers_of_watchlist_owner` and, once the handlers change, `test_the_pre_existing_backlog_only_shrinks` until its record is dropped).
- [ ] **Step 3: Implement**: the dependency and the raise in both handlers, delete `_watchlist_owner` and the two `gcp.fetchers._watchlist` imports, add the `dependencies` and `responses` declarations; delete the four replaced tests in `TestWatchlistMutationAPI` and `test_watchlist_add_endpoint`, set the two route-coverage entries to 410, drop the `routers/insights.py` record from `KNOWN_BACKLOG`, and make the reader-scan file's changes listed above, so that `make test` in Task 5 has no test left that expects the retired behaviour.
- [ ] **Step 4: Run** the Step 2 command, then `grep -rn "insights/watchlist/add\|_watchlist_owner\|WRITE_ROUTE_EXCLUSION" tests/` to confirm no test still expects the write behaviour or the deleted helper (the per-user API tests in `tests/api/test_me_watchlist.py` and the CLI backfill's own `add_to_watchlist` in `tests/gcp/test_backfill_ticker.py` are unrelated and stay); expected PASS, including stage A's ranked and default tests unchanged.
- [ ] **Step 5: Commit** `feat(api): web watchlist write routes answer 410 and write nothing`

### Task 3: OpenAPI snapshot

Spec: done_when[2].

- [ ] **Step 1: Run** `python scripts/export_openapi.py`; `pytest tests/api/test_openapi_snapshot.py -v` passes; `git diff platform/api/openapi.json` shows a `"410"` response on `add_to_watchlist_api_insights_watchlist_add_post` and on the delete operation and nothing else.
- [ ] **Step 2:** write in the PR body: "Operations changed: POST /api/insights/watchlist/add and DELETE /api/insights/watchlist/{ticker} gained a 410 response. Operations added: none." (solyra's `npm run contract:sync` reads this.)
- [ ] **Step 3: Commit** `chore(api): regenerate the OpenAPI snapshot with the 410 responses`
- [ ] **Step 4:** note in the PR body that after this merge solyra's `npm run contract:check` is red until a solyra chore PR runs `npm run contract:sync` against stocks main (its vendored OpenAPI gains the two 410 responses); that PR is this stage's close-out on the solyra side.

### Task 4: Implementation-source notes and source snapshot

Spec: done_when[4] (the FEAT-CICD-001 documentation identity protocol, `.claude/skills/product-delivery/SKILL.md`, "Committed-source documentation identity"). Advances done_when[4].

**Files:**
- Modify: `docs/product/03-SITE-TRACEABILITY.md` (the `## Implementation-source notes` table: the existing FEAT-INSIGHT-001 INSIGHTS-09 row, at line 1312 on main, updated in place with its hash replaced, its sentences kept and the new sentence appended; three new rows for FEAT-INSIGHT-001 JOURNAL-01, OPTIONS-06 and SIGNALS-01, which have no row yet, inserted immediately after the INSIGHTS-09 row in that order, because `scripts/maintenance/doc_source_snapshot.py` refuses a table whose rows are not sorted by (FEAT, Component) and the FEAT-OPTION-001 rows follow; no other byte)
- Modify: `docs/review-evidence/site-source-snapshot.json` (regenerated)

- [ ] **Step 1: Preflight**: `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json` on the branch head; it refuses until the declared notes carry the current identity and reports the head's `source_identity_sha256`; copy it.
- [ ] **Step 2: Update the rows**: INSIGHTS-09 becomes `| FEAT-INSIGHT-001 | INSIGHTS-09 | source_identity_sha256=<hash>; <the row's existing sentences>; POST /api/insights/watchlist/add and DELETE /api/insights/watchlist/{ticker} answer 410 and write nothing (platform/api/routers/insights.py, _watchlist_writes_retired; the router imports nothing from gcp.fetchers._watchlist); tests: tests/api/test_watchlist_default_lock.py, tests/gcp/test_watchlist_readers_default_owner.py. |`, and each of JOURNAL-01, OPTIONS-06 and SIGNALS-01 gains the row `| FEAT-INSIGHT-001 | <ID> | source_identity_sha256=<hash>; POST /api/insights/watchlist/add and DELETE /api/insights/watchlist/{ticker}, which this element's page called through the ticker combobox, answer 410 and write nothing (platform/api/routers/insights.py, _watchlist_writes_retired); tests: tests/api/test_watchlist_default_lock.py, tests/gcp/test_watchlist_readers_default_owner.py. |` inserted immediately after the INSIGHTS-09 row, in the order JOURNAL-01, OPTIONS-06, SIGNALS-01, with every other row left where it is; `git diff --numstat` shows only those four rows changed or added; commit `docs(site): FEAT-INSIGHT-001 implementation-source notes for the 410 write routes`.
- [ ] **Step 3: Produce** the snapshot with the Step 1 command (it now installs the record) and commit `docs(evidence): site source snapshot for the stage B lock`.
- [ ] **Step 4: Verify**: `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000` exits 0 with `status identity-matched`; `python3 scripts/maintenance/docs_audit.py` on the branch reports nothing `origin/main` does not. Repeat Steps 1 to 4 after any later code change or merge of main on this branch, since the identity moves with the source and the record's baseline must be main's tip.

### Task 5: Close

Spec: § Done when. Closes done_when[5].

- [ ] Update the `### FEAT-INSIGHT-001` record in `docs/product/02-FEATURE-CATALOG.md` (`:279`) and the FEAT-INSIGHT-001 PR lineage in `docs/product/12-PR-ISSUE-TRACEABILITY.md` (`:495`, the `**PR lineage:**` line at `:497`); set this plan's `pr`.
- [ ] `python3 scripts/maintenance/docs_audit.py` on the branch and on `origin/main`: nothing new.
- [ ] `make test` green; `python3 scripts/gate/spec_gate.py --pr origin/main` ok.
- [ ] Tick every done_when line in the PR body with its evidence, Task 1's log read included; only then mark the PR ready.
