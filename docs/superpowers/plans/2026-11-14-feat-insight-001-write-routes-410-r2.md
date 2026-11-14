---
feat_id: FEAT-INSIGHT-001
spec: docs/superpowers/specs/2026-11-14-feat-insight-001-watchlist-write-routes-410-r2.md
branch: feature/feat-insight-001-write-routes-410-r2
pr: null
status: ready
---

# Default watchlist lock, stage B, implementation plan: the web write routes answer 410 (r2: site source notes)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances (done_when[0] is the first item).

**Goal:** `POST /api/insights/watchlist/add` and `DELETE /api/insights/watchlist/{ticker}` answer 410 and write nothing, once the live site shows solyra no longer calls them.

**Architecture:** A route dependency on the two write routes in `platform/api/routers/insights.py` raises `HTTPException(410, detail)` before the body is validated, and each handler's only statement raises it again, so no database work and no fabricated response remain; `_watchlist_owner` and the imports from `gcp.fetchers._watchlist` are deleted; the response models stay so the operations stay declared, with a 410 response added to the OpenAPI document.

**Tech Stack:** FastAPI (`platform/api`), pytest with the `client` fixture of `tests/api/test_platform_api.py:33` and the auth-mode pattern of `tests/api/test_platform_auth.py:33`.

**Spec:** `docs/superpowers/specs/2026-11-14-feat-insight-001-watchlist-write-routes-410-r2.md` (approved; the 2026-11-13 stage B text plus the `site_source_notes` declaration, and the solyra precondition names the v3 spec).

**Precondition (owner's gate):** Task 1 runs first and the branch is not marked ready until its log read shows zero requests.

## Global Constraints

- The 410 detail, verbatim: `The watchlist is managed in Discord (/watchlist add, /watchlist remove); the web app keeps per-user lists in solyra.`
- Both routes stay declared (no deletion here; owner's decision 3) and keep their response models `WatchlistAddResponse` (`insights.py:535`) and `WatchlistRemoveResponse` (`platform/api/schemas.py:1468`).
- After this stage `platform/api/routers/insights.py` imports nothing from `gcp.fetchers._watchlist` and defines no `_watchlist_owner`.
- No em or en dashes in code or docs.

## Review Focus

1. A request body that fails validation (`{}` on POST) still answers 410, not 422: the 410 is raised by a route dependency, and FastAPI (0.162.4 here, `fastapi.dependencies.utils.solve_dependencies`) solves dependencies before it validates the body and collects body errors into the 422 afterwards, so the dependency's `HTTPException` wins. Declaring the body `Optional[...] = None` would not do it: a present `{}` is still validated against the model. A body that is not JSON at all still gets FastAPI's 422 from the decoder, which runs before dependencies; the test sends `{}`, valid JSON that fails the model. The typed `body: WatchlistAddRequest` parameter stays so the operation's `requestBody` in the OpenAPI document is unchanged. Pinned in Task 2.
2. An `OPTIONS` preflight to either route is unaffected (CORS middleware answers before routing); the test confirms a preflight still gets its CORS headers. Pinned in Task 2.
3. `extras` on the ranked route keeps working after the imports are removed (the ranked route does not use the deleted helpers). Pinned in Task 2 by re-running the stage A API tests.

---

### Task 1: Live-site precondition

Spec: § Live-site precondition. Advances done_when[3]. Owner or implementer, read-only.

- [ ] **Step 1:** confirm solyra's per-user watchlist implementation (plan solyra#338) is merged and deployed, and note the deploy time.
- [ ] **Step 2:** at least one full trading day later, run:
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
- Modify: `platform/api/routers/insights.py` (`add_to_watchlist` `:599-673`, `remove_from_watchlist` `:676-701`, `_watchlist_owner` `:57`, the `gcp.fetchers._watchlist` imports at `:616` and `:682`)
- Modify: `tests/api/test_watchlist_default_lock.py` (stage A's file; add the 410 tests)
- Modify: `tests/api/test_platform_api.py` (`TestWatchlistMutationAPI` around `:1667`: `test_add_threads_default_owner_when_no_auth`, `test_add_scopes_to_signed_in_user`, `test_remove_scopes_to_signed_in_user`, `test_two_users_do_not_share_watchlist` are replaced by one `test_write_routes_answer_410`)
- Modify: `tests/gcp/test_watchlist_readers_default_owner.py` (drop `WRITE_ROUTE_EXCLUSION` and `test_write_routes_are_the_only_callers_of_watchlist_owner`; add `test_insights_router_imports_nothing_from_watchlist_helper`)
- Modify: `tests/meta/test_http_status_classification.py` (`KNOWN_BACKLOG`: drop the `routers/insights.py` entry)

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
- [ ] **Step 2: Run** `pytest tests/api/test_watchlist_default_lock.py tests/api/test_platform_api.py -k watchlist tests/gcp/test_watchlist_readers_default_owner.py -v`; expected FAIL on the new tests.
- [ ] **Step 3: Implement**: the dependency and the raise in both handlers, delete `_watchlist_owner` and the two `gcp.fetchers._watchlist` imports, add the `dependencies` and `responses` declarations; delete the four replaced tests.
- [ ] **Step 4: Run**; expected PASS, including stage A's ranked and default tests unchanged.
- [ ] **Step 4b: Lower the classification backlog**: the two retired handlers were the two unclassified 503 handlers that `tests/meta/test_http_status_classification.py` records for `routers/insights.py` (`KNOWN_BACKLOG["routers/insights.py"] == 2`; stage A r2's endpoint is classified through `unavailable`), and `test_the_pre_existing_backlog_only_shrinks` fails when a file's count drops below its record, so remove the `routers/insights.py` entry and run `pytest tests/meta/test_http_status_classification.py -v`; expected PASS (Codex on #1905). The Step 4 run includes this file.
- [ ] **Step 5: Commit** `feat(api): web watchlist write routes answer 410 and write nothing`

### Task 3: OpenAPI snapshot

Spec: done_when[2].

- [ ] **Step 1: Run** `python scripts/export_openapi.py`; `pytest tests/api/test_openapi_snapshot.py -v` passes; `git diff platform/api/openapi.json` shows a `"410"` response on `add_to_watchlist_api_insights_watchlist_add_post` and on the delete operation and nothing else.
- [ ] **Step 2:** write in the PR body: "Operations changed: POST /api/insights/watchlist/add and DELETE /api/insights/watchlist/{ticker} gained a 410 response. Operations added: none." (solyra's `npm run contract:sync` reads this.)
- [ ] **Step 3: Commit** `chore(api): regenerate the OpenAPI snapshot with the 410 responses`

### Task 4: Implementation-source notes and source snapshot

Spec: done_when[4] (the FEAT-CICD-001 documentation identity protocol, `.claude/skills/product-delivery/SKILL.md`, "Committed-source documentation identity"). Advances done_when[4].

**Files:**
- Modify: `docs/product/03-SITE-TRACEABILITY.md` (the FEAT-INSIGHT-001 rows for INSIGHTS-09, JOURNAL-01, OPTIONS-06 and SIGNALS-01 in the `## Implementation-source notes` table: INSIGHTS-09 updated if the user-watchlist API PR added it, the other three appended; no other byte)
- Modify: `docs/review-evidence/site-source-snapshot.json` (regenerated)

- [ ] **Step 1: Preflight**: `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json` on the branch head; it refuses with `no declared source-bound note updates` and reports the head's source identity; copy that hash.
- [ ] **Step 2: Write the rows**, each `| FEAT-INSIGHT-001 | <ID> | source_identity_sha256=<hash>; POST /api/insights/watchlist/add and DELETE /api/insights/watchlist/{ticker} answer 410 from a route dependency before body validation and write nothing (platform/api/routers/insights.py); the web app's lists are the /api/me/watchlist routes; tests: tests/api/test_watchlist_default_lock.py, tests/gcp/test_watchlist_readers_default_owner.py. |` (for INSIGHTS-09 keep the API PR's prose and append the 410 sentence), and commit `docs(site): implementation-source notes for the 410 write routes`.
- [ ] **Step 3: Produce** the snapshot with the Step 1 command (it now installs the record) and commit `docs(evidence): site source snapshot for the stage B lock`.
- [ ] **Step 4: Verify**: `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000` exits 0 with `status identity-matched`, and `python3 scripts/maintenance/docs_audit.py` on the branch reports nothing `origin/main` does not.

### Task 5: Close

Spec: § Done when. Closes done_when[5].

- [ ] Update the `### FEAT-INSIGHT-001` record in `docs/product/02-FEATURE-CATALOG.md` (`:279`) and the FEAT-INSIGHT-001 PR lineage in `docs/product/12-PR-ISSUE-TRACEABILITY.md` (`:495`).
- [ ] `python3 scripts/maintenance/docs_audit.py` on the branch and on `origin/main`: nothing new.
- [ ] `make test` green; `python3 scripts/gate/spec_gate.py --pr origin/main` ok.
- [ ] Tick every done_when line in the PR body with its evidence, Task 1's log read included; only then mark the PR ready.
