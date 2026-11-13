---
feat_id: FEAT-INSIGHT-001
spec: docs/superpowers/specs/2026-11-13-feat-insight-001-watchlist-default-lock-a.md
branch: feature/feat-insight-001-watchlist-default-lock
pr: null
status: ready
---

# Default watchlist lock, stage A, implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances (done_when[0] is the first item).

**Goal:** Every stocks read of the watchlist names the `'default'` owner in code, the web gets a read-only `GET /api/insights/watchlist/default`, the one reader that ignored removal and ownership is fixed, and `/replay` stops re-adding removed rows; the two web write routes are untouched until stage B.

**Architecture:** One new response model and endpoint in the insights router reading through `gcp.database.query_to_dataframe_strict`; the ranked route pinned to `user_id='default'`; a source-scan test over the spec's reader inventory; one SQL fix in `_backfill_targets`; one default flipped in `gcp/backfill_ticker.py`; the OpenAPI snapshot regenerated.

**Tech Stack:** FastAPI and Pydantic (`platform/api`), SQLAlchemy over pg8000 (`gcp/database.py`), pytest with the `client` fixture of `tests/api/test_platform_api.py:33`.

**Spec:** `docs/superpowers/specs/2026-11-13-feat-insight-001-watchlist-default-lock-a.md` (approved).

**Cross-repo order:** this stage merges first; solyra's implementation (solyra#334 plan, Task 12) runs `npm run contract:sync` against the regenerated OpenAPI; stage B follows the live-site check.

## Global Constraints

- No change to the two web write routes in this stage; `_watchlist_owner` (`platform/api/routers/insights.py:57`) stays and is called by them only (§ Non-goals).
- The new endpoint reads through `gcp.database.query_to_dataframe_strict` (`gcp/database.py:244`), never `query_to_dataframe`; a database error answers 503 with the exception text in `detail` (§ New read-only endpoint, Rule 3.7).
- The endpoint is gated like the rest of `/api/insights`: not added to `_OPEN_API_PREFIXES` (`platform/api/auth.py:70`).
- Response field names, verbatim: `as_of`, `owner`, `rows`; row fields `ticker`, `in_brief`, `in_insight`, `signals`, `source`, `added_at`; rows in `added_at, ticker` order.
- `BACKFILL_ADD_TO_WATCHLIST` defaults to `"false"`; `gcp/deploy.sh` is not touched (§ Replay stops re-adding).
- No em or en dashes in code or docs.

## Review Focus

1. `watchlists.added_at` is `TIMESTAMPTZ`; the endpoint serialises it as an ISO instant string, never a pandas `Timestamp` repr, so the solyra type `added_at: string` holds. Pinned in Task 1.
2. The strict reader returning zero rows (an empty default list) answers 200 with `rows: []`, which is a true state, not a fallback; the test distinguishes it from the 503 path. Pinned in Task 1.
3. `extras` with duplicates and lower-case entries on the ranked route (`extras=nvda,NVDA`) reaches `rank_tickers` upper-cased and once; the existing `test_watchlist_extras_uppercased_and_split` stays green. Pinned in Task 2.
4. The scan test must fail, not pass vacuously, when a listed file no longer exists or a listed helper name is renamed: it asserts each inventory path exists before scanning. Pinned in Task 3.
5. `BACKFILL_ADD_TO_WATCHLIST=TRUE` (upper case) and `true` both opt in; `yes` does not: the existing `.lower() == "true"` comparison at `gcp/backfill_ticker.py:611` is kept and tested for `TRUE`. Pinned in Task 5.
6. The ranker's forwarding site (`lib/agents/ranker/candidates.py:250-253`, `user_id if user_id is not None else DEFAULT_USER_ID`) is the one `user_id=` expression the scan cannot resolve statically: the scan asserts the expression verbatim, the caller scan pins `rank_tickers`' two production callers to the default owner, and Task 2's ranker tests prove the chain behaviourally. Pinned in Tasks 2 and 3.

---

### Task 1: `GET /api/insights/watchlist/default`

Spec: § New read-only endpoint. Advances done_when[0].

**Files:**
- Modify: `platform/api/schemas.py` (after `WatchlistRemoveResponse` at `:1468`)
- Modify: `platform/api/routers/insights.py` (new route beside `get_watchlist` at `:709`)
- Create: `tests/api/test_watchlist_default_lock.py`

**Interfaces:**
- Produces:
  ```python
  class WatchlistDefaultRow(ApiModel):
      ticker: str; in_brief: bool; in_insight: bool; signals: bool; source: Optional[str] = None; added_at: str
  class WatchlistDefaultResponse(ApiModel):
      as_of: str; owner: Literal["default"]; rows: list[WatchlistDefaultRow]
  WATCHLIST_DEFAULT_SQL = "SELECT ticker, in_brief, in_insight, signals, source, added_at FROM watchlists WHERE user_id = 'default' AND removed_at IS NULL ORDER BY added_at, ticker"
  @router.get("/api/insights/watchlist/default", response_model=WatchlistDefaultResponse)
  def get_default_watchlist(request: Request) -> WatchlistDefaultResponse
  ```
  The handler imports `query_to_dataframe_strict` from `gcp.database` at module level, converts `added_at` with `.isoformat()`, sets `as_of` to `datetime.now(timezone.utc).isoformat()`, and wraps the read in `try/except Exception as exc: raise HTTPException(503, detail=f"watchlist read from Cloud SQL failed: {exc}")`.

- [ ] **Step 1: Write failing tests** (module `client` fixture copied from `tests/api/test_platform_api.py:33`; the fake engine's connection records every statement it executes): `test_default_watchlist_returns_rows_in_added_at_order` (patch `gcp.database.get_engine` with a fake engine whose connection returns three rows for the SQL; assert 200, `owner == "default"`, tickers `["SPY","QQQ","IWM"]` in `added_at` order, every row's `added_at` is an ISO string, and the one recorded statement equals `WATCHLIST_DEFAULT_SQL`, which contains `user_id = 'default'`, `removed_at IS NULL` and `ORDER BY added_at, ticker`); `test_default_watchlist_sql_excludes_removed_and_other_owners` (executes `WATCHLIST_DEFAULT_SQL` in an in-memory SQLite `watchlists` table holding active default rows SPY, QQQ and IWM with ascending `added_at`, a default row `AAA` with `removed_at` set, and an `alice@example.com` row `BBB`; asserts exactly `["SPY", "QQQ", "IWM"]` in `added_at, ticker` order; this test and the previous one both fail against a handler that drops either predicate); `test_default_watchlist_is_identical_for_open_and_signed_in_callers` (second call with `monkeypatch.setattr(insights_module, "current_user_email", lambda req: "alice@example.com")`, same body except `as_of`); `test_default_watchlist_503_when_cloud_sql_fails` (`patch("gcp.database.get_engine", side_effect=RuntimeError("db down"))`, assert 503 and `"db down" in detail`; this fails against an implementation on the swallowing `query_to_dataframe`, which would answer 200 with `rows: []`); `test_default_watchlist_empty_list_is_200` (zero rows → `rows == []`).
- [ ] **Step 2: Run** `pytest tests/api/test_watchlist_default_lock.py -v`; expected FAIL (404).
- [ ] **Step 3: Implement** the models and the route.
- [ ] **Step 4: Run** the file; expected PASS.
- [ ] **Step 5: Commit** `feat(api): read-only default watchlist endpoint through the strict reader`

### Task 2: The ranked route ranks `'default'` for every caller

Spec: § Ranked list. Advances done_when[1].

**Files:**
- Modify: `platform/api/routers/insights.py:709-756` (`get_watchlist`: `user_id="default"` instead of `_watchlist_owner(request)`)
- Modify: `tests/api/test_platform_api.py` (`test_watchlist_threads_signed_in_user` at `:1642` becomes `test_watchlist_ranks_default_for_signed_in_user`, asserting `user_id == "default"` for the signed-in caller; `test_watchlist_threads_default_owner_when_no_auth` at `:1627` and `test_watchlist_extras_uppercased_and_split` at `:1600` stay)
- Modify: `tests/api/test_watchlist_default_lock.py` (add `test_ranked_watchlist_passes_default_owner_and_extras`)
- Modify: `tests/agents/test_ranker.py` (add `test_rank_tickers_threads_user_id_to_gather_candidates`: patch `rank_module.gather_candidates` and assert `user_id="default"` and `extras=["NVDA"]` arrive; and `test_gather_candidates_loads_the_default_owner`: patch `gcp.fetchers._watchlist.load_watchlist` to record its keywords and the other candidate sources to return nothing, call `gather_candidates(user_id=None)` and `gather_candidates(user_id="default")`, assert both calls record `user_id="default"` and `surface="all"`, the end of the forwarding chain at `lib/agents/ranker/candidates.py:250-253`)

- [ ] **Step 1: Write the failing tests**: the API test patches `lib.agents.ranker.rank_tickers` and asserts `user_id == "default"` for a signed-in caller and `extras == ["NVDA"]` for `?extras=nvda`.
- [ ] **Step 2: Run** `pytest tests/api/test_watchlist_default_lock.py tests/api/test_platform_api.py -k watchlist tests/agents/test_ranker.py -v`; expected FAIL on the new tests and on the replaced one.
- [ ] **Step 3: Implement** the one-line change; `_watchlist_owner` stays for the write routes.
- [ ] **Step 4: Run**; expected PASS.
- [ ] **Step 5: Commit** `fix(api): ranked watchlist always ranks the default owner`

### Task 3: Reader source scan

Spec: § Readers, § Tests. Advances done_when[2].

**Files:**
- Create: `tests/gcp/test_watchlist_readers_default_owner.py` (shape of `tests/gcp/test_signal_monitor_watchlist_source.py`)

**Interfaces:**
- Produces: a module constant `READERS` listing every path in the spec's Readers table (section Readers, `gcp/signal_monitor.py` through `gcp/discord_interactions/main.py`), each with the helper it calls (`load_watchlist`, `resolve_membership_at`, or `own-sql`); `WRITERS = {"gcp/discord_interactions/main.py", "gcp/backfill_ticker.py", "gcp/fetchers/_watchlist.py", "gcp/schema.sql"}`, the files whose SQL text inserts into or updates `watchlists` (`main.py:655, 691`, `backfill_ticker.py:328`, the helper, the seed); `MENTIONS_ONLY`, a dict from the three files whose only match is a log hint, a comment or a docstring (`gcp/signal_monitor.py:314`, `gcp/insight_pipeline_job.py:777`, `scripts/maintenance/doc_inventory.py:1769`) to the exact text of that line; `WRITE_ROUTE_EXCLUSION = "platform/api/routers/insights.py"` with a comment naming stage B as the change that removes it; `FORWARDING_SITE = ("lib/agents/ranker/candidates.py", "user_id=user_id if user_id is not None else DEFAULT_USER_ID")`, the one `user_id=` expression the scan accepts without resolving it, because the ranker tests of Task 2 prove the chain behind it; `RANK_TICKERS_CALLERS = {"platform/api/routers/insights.py", "gcp/auto_refresh_top_n.py"}`.

- [ ] **Step 1: Write the failing tests**: `test_every_inventory_path_exists`; `test_no_reader_passes_a_non_default_user_id` (regex over each inventory file for `load_watchlist(` and `resolve_membership_at(` calls, each classified as one of three shapes: no `user_id=` argument, so the helper's `DEFAULT_USER_ID` applies, which is every job and script in the inventory; `user_id=` equal to the literal `"default"` or `DEFAULT_USER_ID`; or `FORWARDING_SITE`, `lib/agents/ranker/candidates.py:250-253`, whose argument the test asserts verbatim as `user_id if user_id is not None else DEFAULT_USER_ID`, so its fallback is the default owner and any other expression there, or a second forwarding site anywhere, fails the test; the `own-sql` check for `gcp/calibrate_level_params.py` asserts that `WATCHLIST_SQL` (`:96-99`) contains `user_id = :user_id` and `removed_at IS NULL`, that `WATCHLIST_OWNER = 'default'` is the module's assignment (`:100`), and that the `strict_watchlist` call passes `{'user_id': WATCHLIST_OWNER}` (`:275`), each read from the file: the calibration reader binds its owner, it does not inline it, and the inventory row keeps `own-sql` as the helper); `test_rank_tickers_callers_pass_the_default_owner` (the production callers of `rank_tickers` are exactly `RANK_TICKERS_CALLERS`, `platform/api/routers/insights.py:749` and `gcp/auto_refresh_top_n.py:219`, and each call's argument list carries `user_id="default"` or no `user_id` at all; this is the static half of the forwarding chain, whose behavioural half is Task 2's `test_rank_tickers_threads_user_id_to_gather_candidates` and `test_gather_candidates_loads_the_default_owner`); `test_only_the_named_writers_insert_or_update_watchlists` (grep `INSERT INTO watchlists` and `UPDATE watchlists` across `gcp/`, `lib/`, `platform/`, `scripts/`, skipping tests and `__pycache__`; the set of matching files equals `WRITERS | MENTIONS_ONLY.keys()`, and each `MENTIONS_ONLY` file's matching line equals the recorded text, so a mention that turns into a statement fails the test; `insights.py` holds no SQL text, it calls the helpers, so it is not in the set); `test_write_routes_are_the_only_callers_of_watchlist_owner` (the string `_watchlist_owner(` appears in `insights.py` only inside `add_to_watchlist` and `remove_from_watchlist`).
- [ ] **Step 2: Run** `pytest tests/gcp/test_watchlist_readers_default_owner.py -v`; expected: `test_rank_tickers_callers_pass_the_default_owner` fails until Task 2 lands, because `insights.py:755` still passes `_watchlist_owner(request)` (run after Task 2: PASS), and the rest pass on the current tree, which is what proves the inventory.
- [ ] **Step 3:** adjust the inventory list until every path exists and the scan is exact.
- [ ] **Step 4: Run**; expected PASS.
- [ ] **Step 5: Commit** `test(gcp): source scan keeps every watchlist reader on the default owner`

### Task 4: `_backfill_targets` filters removed rows and other owners

Spec: § The one reader fix. Advances done_when[3].

**Files:**
- Modify: `gcp/fetchers/fetch_market_data.py:841-848` (the `watchlists` arm of the `eligible` CTE, `:846-847`)
- Create or modify: `tests/gcp/test_fetch_market_data_backfill_targets.py` (shared with the FEAT-DATA-001 ingest plan, which adds its union tests to the same file)

- [ ] **Step 1: Write failing tests** with the `_captured_sql(monkeypatch, backfill_all=False)` pattern of `tests/gcp/test_backfill_targets_orphans.py`: the captured SQL's `watchlists` arm contains `user_id = 'default' AND removed_at IS NULL AND (COALESCE(in_brief, false) OR COALESCE(in_insight, false))`; and a behavioural test evaluating the arm in SQLite over fixtures: a removed default ticker and an `alice@example.com` ticker are not targets, an active flagged default ticker is.
- [ ] **Step 2: Run**; expected FAIL. **Step 3: Implement** the arm as `SELECT ticker FROM watchlists WHERE user_id = 'default' AND removed_at IS NULL AND (COALESCE(in_brief, false) OR COALESCE(in_insight, false))`, the two `COALESCE` terms as today. **Step 4: Run** with `tests/gcp/test_backfill_targets_orphans.py`; expected PASS.
- [ ] **Step 5: Commit** `fix(fetchers): manual backfill targets only the active default watchlist`

### Task 5: `/replay` stops re-adding

Spec: § Replay stops re-adding. Advances done_when[5].

**Files:**
- Modify: `gcp/backfill_ticker.py:611` (default `"false"`), its docstring lines 36-42
- Modify: `tests/gcp/test_backfill_ticker.py` (`test_watchlist_add_is_the_default` becomes `test_watchlist_add_is_off_by_default`; `test_watchlist_add_can_be_opted_out` becomes `test_watchlist_add_can_be_opted_in` with `BACKFILL_ADD_TO_WATCHLIST=true`; add `test_watchlist_add_opt_in_is_case_insensitive` for `TRUE`)

- [ ] **Step 1: Write the failing tests** with the file's `stubbed_run` fixture: default run never calls `add_to_watchlist` and logs `BACKFILL_ADD_TO_WATCHLIST=false`; `true` and `TRUE` call it once; `yes` does not.
- [ ] **Step 2: Run** `pytest tests/gcp/test_backfill_ticker.py -k watchlist -v`; expected FAIL. **Step 3: Implement.** **Step 4: Run**; expected PASS.
- [ ] **Step 5: Commit** `fix(backfill): a replay no longer re-adds a removed default row by default`

### Task 6: OpenAPI snapshot

Spec: done_when[4].

- [ ] **Step 1: Run** `python scripts/export_openapi.py` (from the repo root; it chdirs into `platform/`).
- [ ] **Step 2: Run** `pytest tests/api/test_openapi_snapshot.py -v`; expected PASS; `git diff --stat platform/api/openapi.json` shows the one added operation `get_default_watchlist_api_insights_watchlist_default_get` and the two new schemas.
- [ ] **Step 3:** write in the PR body: "Operations added: GET /api/insights/watchlist/default. Operations changed: none." (solyra's `npm run contract:sync` reads this.)
- [ ] **Step 4: Commit** `chore(api): regenerate the OpenAPI snapshot for the default watchlist endpoint`

### Task 7: Production verification query

Spec: done_when[6]. Read-only.

- [ ] **Step 1: Run** `./scripts/db_query_cr.sh -q "SELECT ticker FROM watchlists WHERE user_id = 'default' AND removed_at IS NULL ORDER BY ticker"` (no `--commit`).
- [ ] **Step 2:** expected exactly `IWM, QQQ, SPY`; paste the output and the execution id in the PR body before marking it ready. Any other result stops here for the owner.

### Task 8: Close

Spec: § Done when. Closes done_when[7].

- [ ] Update the `### FEAT-INSIGHT-001` record in `docs/product/02-FEATURE-CATALOG.md` (`:279`: Status, Last reviewed) and the FEAT-INSIGHT-001 PR lineage in `docs/product/12-PR-ISSUE-TRACEABILITY.md` (`:495`).
- [ ] `python3 scripts/maintenance/docs_audit.py` on the branch and on `origin/main`: nothing new.
- [ ] `make test` green; `python3 scripts/gate/spec_gate.py --pr origin/main` ok.
- [ ] Tick every done_when line in the PR body with its evidence (test names, the snapshot diff, the query output with its execution id).
