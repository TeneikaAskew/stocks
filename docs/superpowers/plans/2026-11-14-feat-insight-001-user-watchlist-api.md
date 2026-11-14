---
feat_id: FEAT-INSIGHT-001
spec: docs/superpowers/specs/2026-11-14-feat-insight-001-user-watchlist-api.md
branch: feature/feat-insight-001-user-watchlist-api
pr: null
status: ready
---

# Per-user watchlist API in Cloud SQL, implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances (done_when[0] is the first item).

**Goal:** A signed-in web user keeps a per-user watchlist in stocks Cloud SQL through three routes under `/api/me/watchlist`, keyed by the Firebase account id, with one shared `watched_tickers` row per ticker, and no job but the FEAT-DATA-001 ingest can read the two tables.

**Architecture:** Two idempotent tables in `gcp/schema.sql` (applied by the `apply-schema-on-change` trigger on merge); `api.auth.current_user_identity` beside `current_user_email`; one new router `platform/api/routers/me_watchlist.py` with module-level SQL constants, reads through `gcp.database.query_to_dataframe_strict`, writes in one `get_engine().begin()` transaction; four response models in `platform/api/schemas.py`; the OpenAPI snapshot regenerated; a source scan that keeps the two tables out of every job.

**Tech Stack:** FastAPI and Pydantic (`platform/api`), SQLAlchemy over pg8000 (`gcp/database.py`), pytest with the `client` fixture of `tests/api/test_platform_api.py:34` and the auth-mode pattern of `tests/api/test_platform_auth.py:33`, the ephemeral-Postgres fixtures of `tests/integration/conftest.py`.

**Spec:** `docs/superpowers/specs/2026-11-14-feat-insight-001-user-watchlist-api.md` (approved).

**Cross-repo order:** merges after lock stage A; solyra's v3 implementation runs `npm run contract:sync` against the regenerated OpenAPI; the ingest v2 job's first execution follows this PR's apply-schema build.

## Global Constraints

- Every statement is scoped by `owner_uid` taken from `current_user_identity(request)`, never from the body, the query string or a header the client controls (§ Identity, § Routes).
- Reads go through `query_to_dataframe_strict` (`gcp/database.py:244`); an infrastructure failure is a 503 with the exception text in `detail`, raised through `api.http_errors.unavailable(detail, exc)` so a defect stays a 500 and `tests/meta/test_http_status_classification.py` (which allows the new router no unclassified 503 handler) stays green; an empty result is a 200 with `tickers: []` (Rule 3.7).
- The router never names the `watchlists` table (whole word) and nothing is added to `_OPEN_API_PREFIXES` (`platform/api/auth.py:70`).
- The POST upsert never writes `added_at` on conflict; `owner_email` and `source` are refreshed; removal is a soft delete (§ Routes).
- Ticker rule, verbatim: trimmed, upper-cased, `^[A-Z0-9.]{1,10}$`; `source` is `ui` or `combobox-auto-add`; the cap is 200 active rows per user (§ Routes).
- `last_daily_bar` is `MAX(date)` over rows with `close IS NOT NULL`, null when there is none; `name`, `exchange` and `asset_type` are null without a `ticker_info` row, never `''` (Rule 3.7).
- SQL constants are module-level names (`ME_WATCHLIST_SQL`, `ME_WATCHLIST_LOCK_SQL`, `ME_WATCHLIST_COUNT_SQL`, `WATCHED_TICKER_INSERT_SQL`, `USER_WATCHLIST_UPSERT_SQL`, `USER_WATCHLIST_REMOVE_SQL`) so the API tests and the integration tests run the same text.
- No em or en dashes in code or docs.

## Review Focus

1. 401 is decided before any database call: the identity check runs first in every handler and the tests assert the recorders saw nothing. Pinned in Tasks 4 and 5.
2. `added_at` survives a duplicate add and a remove-then-re-add: the upsert's `DO UPDATE SET` list has no `added_at`, and the integration test reads it back unchanged. Pinned in Tasks 5 and 6.
3. The 503 path is the strict reader's: the tests patch `query_to_dataframe_strict` to raise and the source scan refuses `query_to_dataframe` in the router. Pinned in Task 4.
4. `current_user_identity` returns None, never a partial identity, for an unverified email, so an unverified address cannot own rows. Pinned in Task 2.
5. The identifier scan names exactly three files; a fourth reader of the two tables fails the suite. Pinned in Task 8.

---

### Task 1: Tables in gcp/schema.sql

Spec: § Tables. Advances done_when[0].

**Files:**
- Modify: `gcp/schema.sql` (after the `watchlists` block that ends near `:2485`, before `watchlist_history` at `:2672`; the exact SQL block of § Tables)
- Create: `tests/gcp/test_schema_user_watchlists.py`

**Interfaces:**
- Consumes: `gcp.apply_schema.split_statements(sql_text)` (`gcp/apply_schema.py:200`) to parse the file the way the apply job does.

- [ ] **Step 1: Write failing tests**: `test_watched_tickers_table_statement` (one statement starts with `CREATE TABLE IF NOT EXISTS watched_tickers`, contains `ticker VARCHAR(10) PRIMARY KEY`, the CHECK with `UPPER(ticker)` and `^[A-Z0-9.]{1,10}$`, and `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`); `test_user_watchlists_table_statement` (`CREATE TABLE IF NOT EXISTS user_watchlists`, the six columns with their types and nullability, `REFERENCES watched_tickers(ticker)`, `PRIMARY KEY (owner_uid, ticker)`); `test_user_watchlists_partial_indexes` (`CREATE INDEX IF NOT EXISTS user_watchlists_active_idx ON user_watchlists (owner_uid) WHERE removed_at IS NULL` and the `_ticker_active_idx` on `(ticker)`); `test_statements_are_idempotent` (each of the four carries `IF NOT EXISTS`).
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_schema_user_watchlists.py -v`; expected FAIL (no such statements).
- [ ] **Step 3: Implement** the block in `gcp/schema.sql` with the two comments of § Tables.
- [ ] **Step 4: Run** the file and `python3 -m pytest tests/gcp/test_apply_schema.py -q`; expected PASS.
- [ ] **Step 5: Commit** `feat(schema): watched_tickers and user_watchlists tables for the per-user watchlist`

### Task 2: `current_user_identity`

Spec: § Identity. Advances done_when[1].

**Files:**
- Modify: `platform/api/auth.py` (beside `_verify_bearer_email` at `:114` and `current_user_email` at `:148`)
- Modify: `tests/api/test_platform_auth.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class UserIdentity:
      uid: str
      email: str
  def _decode_bearer(request: Request) -> Optional[dict]      # the token decode shared with _verify_bearer_email: None without a bearer, raises on an invalid token
  def _verify_bearer_identity(request: Request) -> Optional[UserIdentity]   # uid = decoded['uid'], email through _verified_email_or_none (raises UnverifiedEmailError); None without a bearer or without a uid
  def current_user_identity(request: Request) -> Optional[UserIdentity]     # firebase mode: try _verify_bearer_identity, any exception -> None; open and iap modes: None
  ```
  `_verify_bearer_email` is rewritten to call `_decode_bearer` and keeps its return and raise behaviour byte for byte.

- [ ] **Step 1: Write failing tests** with the `_build(monkeypatch, mode)` pattern of `tests/api/test_platform_auth.py:33`, patching `a._decode_bearer` to return a dict for `Bearer good` (`{"uid": "u1", "email": "Alice@Example.com", "email_verified": True}` → `UserIdentity("u1", "alice@example.com")`), to raise for `Bearer bad` (None), to return `{"uid": "u1", "email": "a@b.c", "email_verified": False}` (None), and to return a dict without `uid` (None); no header (None); open mode with `Bearer good` (None); iap mode with the IAP header (None). Also `test_current_user_email_unchanged` reruns the existing email cases.
- [ ] **Step 2: Run** `python3 -m pytest tests/api/test_platform_auth.py -v`; expected FAIL on the new tests.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run** the file and `python3 -m pytest tests/api/test_platform_api.py -q -k "me or auth"`; expected PASS.
- [ ] **Step 5: Commit** `feat(auth): current_user_identity returns the Firebase uid with the verified email`

### Task 3: Response models

Spec: § Routes (models). Advances done_when[2] and [3].

**Files:**
- Modify: `platform/api/schemas.py` (after `WatchlistRemoveResponse` at `:1468`)

**Interfaces:**
- Produces (all `ApiModel`): `MeWatchlistAddRequest {ticker: str, source: Literal['ui', 'combobox-auto-add']}`, `MeWatchlistRow {ticker: str, added_at: str, source: Optional[str] = None, name: Optional[str] = None, exchange: Optional[str] = None, asset_type: Optional[str] = None, last_daily_bar: Optional[str] = None}`, `MeWatchlistResponse {owner_email: str, as_of: str, tickers: list[MeWatchlistRow]}`, `MeWatchlistRemoveResponse(MeWatchlistResponse) {removed: Literal[True]}`.

- [ ] **Step 1: Write the failing test** `test_me_watchlist_models_round_trip` in `tests/api/test_me_watchlist.py` (a row with nulls validates; `source: 'cli'` is refused by `MeWatchlistAddRequest`).
- [ ] **Step 2: Run** `python3 -m pytest tests/api/test_me_watchlist.py -v`; expected FAIL (import error).
- [ ] **Step 3: Implement** the four models.
- [ ] **Step 4: Run**; expected PASS.
- [ ] **Step 5: Commit** `feat(api): response models for the per-user watchlist routes`

### Task 4: `GET /api/me/watchlist`

Spec: § Routes (GET), § Identity. Advances done_when[2].

**Files:**
- Create: `platform/api/routers/me_watchlist.py`
- Modify: `platform/api/main.py` (`:41` import list; `app.include_router(me_watchlist.router, prefix="")` beside `:201`)
- Modify: `tests/api/test_me_watchlist.py`

**Interfaces:**
- Produces:
  ```python
  router = APIRouter()
  from api.auth import current_user_identity                      # module-level, so tests patch api.routers.me_watchlist.current_user_identity
  from gcp.database import get_engine, query_to_dataframe_strict   # module-level, so tests patch the router's names
  ME_WATCHLIST_SQL = """SELECT u.ticker, u.added_at, u.source, ti.name, ti.exchange, ti.asset_type, (SELECT MAX(m.date) FROM market_data_daily m WHERE m.ticker = u.ticker AND m.close IS NOT NULL) AS last_daily_bar FROM user_watchlists u LEFT JOIN ticker_info ti ON ti.ticker = u.ticker WHERE u.owner_uid = :owner_uid AND u.removed_at IS NULL ORDER BY u.added_at, u.ticker"""
  def _require_identity(request: Request) -> UserIdentity          # raises HTTPException(401, "sign in required")
  def _list(identity: UserIdentity) -> MeWatchlistResponse          # the strict read, ISO conversion, as_of
  @router.get("/api/me/watchlist", response_model=MeWatchlistResponse)
  def get_me_watchlist(request: Request) -> MeWatchlistResponse
  ```
  `_list` wraps the read in `try/except Exception as exc: unavailable(f"watchlist read from Cloud SQL failed: {exc}", exc)` (`from api.http_errors import unavailable`; a defect re-raises as a 500); `added_at` through `.isoformat()`, `last_daily_bar` through `date.isoformat()` or None, pandas NaN and NaT mapped to None.

- [ ] **Step 1: Write failing tests** (the `client` fixture copied from `tests/api/test_platform_api.py:34`; `monkeypatch.setattr(me_watchlist, "current_user_identity", lambda req: UserIdentity("u1", "alice@example.com"))`; a recorder in place of `me_watchlist.query_to_dataframe_strict` that stores `(sql, params)` and returns a prepared DataFrame): `test_get_requires_identity` (identity None → 401 `sign in required`, recorder never called); `test_get_lists_active_rows_in_added_at_order` (three rows → 200, the recorded statement equals `ME_WATCHLIST_SQL`, params `{"owner_uid": "u1"}`, `owner_email == "alice@example.com"`, ISO strings, nulls where the frame holds NaN or NaT); `test_get_empty_is_200` (`tickers == []`); `test_get_503_when_read_fails` (recorder raises `RuntimeError("db down")` → 503 with `db down` in detail); `test_router_reads_only_through_the_strict_reader` (the module source contains `query_to_dataframe_strict` and no other `query_to_dataframe`, and no whole word `watchlists`).
- [ ] **Step 1b: Classification tests**: `test_get_503_when_cloud_sql_fails` patches `query_to_dataframe_strict` to raise `ConnectionError("db down")` (classified by `lib.infra_errors.is_infrastructure_error`) and asserts 503 with the text in `detail`; `test_get_defect_is_500_not_503` patches it to raise `KeyError("shape")` and asserts 500 (`raise_server_exceptions=False` on the client), so the handler must go through `api.http_errors.unavailable` and `tests/meta/test_http_status_classification.py::test_the_pre_existing_backlog_only_shrinks` stays green (the new router is allowed no unclassified 503 handler).
- [ ] **Step 2: Run** `python3 -m pytest tests/api/test_me_watchlist.py -v`; expected FAIL (404 or import error).
- [ ] **Step 3: Implement** the module and register the router.
- [ ] **Step 4: Run** the file and `python3 -m pytest tests/api/test_platform_api.py -q`; expected PASS.
- [ ] **Step 5: Commit** `feat(api): GET /api/me/watchlist reads the caller's list through the strict reader`

### Task 5: `POST /api/me/watchlist` and `DELETE /api/me/watchlist/{ticker}`

Spec: § Routes (POST, DELETE). Advances done_when[3].

**Files:**
- Modify: `platform/api/routers/me_watchlist.py`, `tests/api/test_me_watchlist.py`

**Interfaces:**
- Produces:
  ```python
  TICKER_RE = re.compile(r"^[A-Z0-9.]{1,10}$")
  MAX_ACTIVE_ROWS = 200
  ME_WATCHLIST_LOCK_SQL = "SELECT pg_advisory_xact_lock(hashtext(:owner_uid))"   # serializes adds per owner for the transaction's life
  ME_WATCHLIST_COUNT_SQL = "SELECT COUNT(*) AS n FROM user_watchlists WHERE owner_uid = :owner_uid AND removed_at IS NULL"
  WATCHED_TICKER_INSERT_SQL = "INSERT INTO watched_tickers (ticker) VALUES (:ticker) ON CONFLICT (ticker) DO NOTHING"
  USER_WATCHLIST_UPSERT_SQL = "INSERT INTO user_watchlists (owner_uid, owner_email, ticker, source) VALUES (:owner_uid, :owner_email, :ticker, :source) ON CONFLICT (owner_uid, ticker) DO UPDATE SET removed_at = NULL, source = EXCLUDED.source, owner_email = EXCLUDED.owner_email"
  USER_WATCHLIST_REMOVE_SQL = "UPDATE user_watchlists SET removed_at = NOW() WHERE owner_uid = :owner_uid AND ticker = :ticker AND removed_at IS NULL"
  def _normalize_ticker(raw: str) -> str                           # strip, upper, raises HTTPException(422) unless TICKER_RE matches
  @router.post("/api/me/watchlist", response_model=MeWatchlistResponse)
  def add_me_watchlist(body: MeWatchlistAddRequest, request: Request) -> MeWatchlistResponse
  @router.delete("/api/me/watchlist/{ticker}", response_model=MeWatchlistRemoveResponse)
  def remove_me_watchlist(ticker: str, request: Request) -> MeWatchlistRemoveResponse
  ```
  POST order: identity, normalize, then one transaction `with get_engine().begin() as conn:` that runs `conn.execute(text(ME_WATCHLIST_LOCK_SQL), {"owner_uid": ...})` first (adds for one owner serialize on the advisory lock, which Postgres releases at commit or rollback), then `conn.execute(text(ME_WATCHLIST_COUNT_SQL), ...).scalar()` and raises `HTTPException(409, "watchlist full")` at 200 (leaving the `with` rolls the transaction back), then `conn.execute(text(WATCHED_TICKER_INSERT_SQL), ...); conn.execute(text(USER_WATCHLIST_UPSERT_SQL), ...)`; after the commit, `_list`. The count never runs outside the lock: two concurrent adds at 199 rows would otherwise both read 199 and both commit (spec § Routes). DELETE: identity, normalize, `rowcount` of the update inside `begin()`; 0 → 404 `not on your watchlist`; then `_list` plus `removed: True`. Any infrastructure exception on the write path is a 503 with the exception text, through the same `unavailable` guard; a defect re-raises as a 500.

- [ ] **Step 1: Write failing tests** with a fake engine (`begin()` returns a context manager whose connection's `execute(statement, params)` records `(str(statement), params)` and returns an object with a configurable `rowcount` and, for the count statement, the `scalar()` the test sets), patched as `me_watchlist.get_engine`: `test_post_requires_identity_before_any_statement`; `test_post_rejects_bad_ticker_and_source` (`"ap pl"`, `"TOOLONGTICKER"`, source `cli` → 422, nothing recorded); `test_post_409_when_full` (the count statement answers 200 → 409; the recorded statements are the lock then the count and nothing else); `test_post_inserts_ticker_then_upserts_membership` (`" nvda "` → four statements in order inside one `begin()`: the lock, the count, the ticker insert, the membership upsert, params with `ticker == "NVDA"`, `owner_uid == "u1"`, `owner_email == "alice@example.com"`, `source == "ui"`, and the upsert text has no `added_at` in its `DO UPDATE SET` list); `test_delete_404_when_no_active_row` (rowcount 0); `test_delete_soft_deletes_and_answers_list` (rowcount 1 → `removed is True`, the statement equals `USER_WATCHLIST_REMOVE_SQL`); `test_write_failure_is_503` (the connection raises).
- [ ] **Step 1b: Classification tests**: `test_post_503_when_cloud_sql_fails` makes the fake engine's `begin()` raise `ConnectionError("db down")` and asserts 503; `test_post_defect_is_500_not_503` makes it raise `KeyError("shape")` and asserts 500, so the write path also goes through `api.http_errors.unavailable`.
- [ ] **Step 2: Run** `python3 -m pytest tests/api/test_me_watchlist.py -v`; expected FAIL (405).
- [ ] **Step 3: Implement** both handlers.
- [ ] **Step 4: Run** the file; expected PASS.
- [ ] **Step 5: Commit** `feat(api): add and remove per-user watchlist rows with one shared ticker row`

### Task 6: Integration test against ephemeral Postgres

Spec: § Routes, § Tests. Advances done_when[3].

**Files:**
- Create: `tests/integration/test_me_watchlist_sql.py`

**Interfaces:**
- Consumes: the `db_engine` fixture of `tests/integration/conftest.py` and the router's SQL constants.

- [ ] **Step 1: Write the tests** (they run only where `DB_HOST` is set, like the rest of `tests/integration/`; locally they are skipped by the conftest's engine branch): a fixture truncates `user_watchlists` and `watched_tickers` (CASCADE); `test_two_users_one_ticker_row` (the insert and upsert statements for `u1` and `u2` on `NVDA` → one `watched_tickers` row, two memberships); `test_readd_keeps_added_at` (add, read `added_at`, remove, re-add → same `added_at`, `removed_at` null, `source` updated); `test_remove_leaves_other_membership_and_ticker_row`; `test_get_sql_scopes_and_orders` (`ME_WATCHLIST_SQL` for `u1` returns only u1's active rows in `added_at` order with `last_daily_bar` null and `name` null when `ticker_info` has no row, and the date when one `market_data_daily` bar with a close is inserted); `test_schema_objects_exist` (`information_schema.tables` lists `watched_tickers` and `user_watchlists`, `information_schema.columns` lists the declared columns with their types and nullability, and `pg_indexes` lists `user_watchlists_active_idx` and `user_watchlists_ticker_active_idx` with `WHERE (removed_at IS NULL)` in their definitions: the pre-merge proof of done_when[0]); `test_cap_holds_under_concurrent_adds` (seed `u1` with 199 active rows; two threads, each on its own connection and transaction, run the POST's statement sequence for two different tickers, the lock, the count, the inserts, meeting at a `threading.Barrier` just before the lock statement; one commits and the other reads 200 and rolls back; afterwards `SELECT COUNT(*) FROM user_watchlists WHERE owner_uid = 'u1' AND removed_at IS NULL` is 200, which is the spec's concurrent cap case and fails without the lock).
- [ ] **Step 2: Run** `python3 -m pytest tests/integration/test_me_watchlist_sql.py -q` locally; expected: skipped or passing (no Postgres here); CI's Integration Tests job is the proof.
- [ ] **Step 3: Commit** `test(integration): per-user watchlist statements against Postgres`

### Task 7: OpenAPI snapshot

Spec: done_when[4].

- [ ] **Step 1: Run** `python scripts/export_openapi.py` from the repo root (it chdirs into `platform/`).
- [ ] **Step 2: Run** `python3 -m pytest tests/api/test_openapi_snapshot.py -v`; expected PASS; `git diff --stat platform/api/openapi.json` shows the three operations (`get_me_watchlist_api_me_watchlist_get`, `add_me_watchlist_api_me_watchlist_post`, `remove_me_watchlist_api_me_watchlist__ticker__delete`) and the four schemas.
- [ ] **Step 3:** write in the PR body: "Operations added: GET /api/me/watchlist, POST /api/me/watchlist, DELETE /api/me/watchlist/{ticker}. Operations changed: none." (solyra's `npm run contract:sync` reads this.)
- [ ] **Step 4: Commit** `chore(api): regenerate the OpenAPI snapshot for the per-user watchlist routes`

### Task 8: Identifier isolation scan

Spec: § Non-goals, done_when[5].

**Files:**
- Create: `tests/gcp/test_user_watchlist_isolation.py`

- [ ] **Step 1: Write the test**: walk `gcp/`, `lib/`, `scripts/` and `platform/api/` (skip `tests/`, `__pycache__`, `.pyc`), regex `\b(user_watchlists|watched_tickers)\b` over `.py`, `.sql` and `.sh` files; the set of matching paths is a subset of `{"gcp/schema.sql", "platform/api/routers/me_watchlist.py", "gcp/fetchers/fetch_watched_tickers.py"}` (the third is the FEAT-DATA-001 job, absent until its PR); and `tests/gcp/test_watchlist_readers_default_owner.py` (stage A) runs green in the same session.
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_user_watchlist_isolation.py tests/gcp/test_watchlist_readers_default_owner.py -v`; expected PASS.
- [ ] **Step 3: Commit** `test(gcp): the per-user watchlist tables stay out of every job but the ingest`

### Task 9: Implementation-source note and source snapshot

Spec: done_when[6] (the FEAT-CICD-001 documentation identity protocol, `.claude/skills/product-delivery/SKILL.md`, "Committed-source documentation identity"). Advances done_when[6].

**Files:**
- Modify: `docs/product/03-SITE-TRACEABILITY.md` (one FEAT-INSIGHT-001 INSIGHTS-09 row in the `## Implementation-source notes` table: appended if absent, updated in place if a later PR added one; no other byte)
- Modify: `docs/review-evidence/site-source-snapshot.json` (regenerated)

- [ ] **Step 1: Preflight**: `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json` on the branch head; it refuses with `no declared source-bound note updates` and reports the head's source identity; copy that hash.
- [ ] **Step 2: Write the row** `| FEAT-INSIGHT-001 | INSIGHTS-09 | source_identity_sha256=<hash>; GET, POST /api/me/watchlist and DELETE /api/me/watchlist/{ticker} (platform/api/routers/me_watchlist.py) read and write the caller's rows in user_watchlists and watched_tickers (gcp/schema.sql), scoped by the Firebase uid from api.auth.current_user_identity, admission serialized per owner by an advisory lock; tests: tests/api/test_me_watchlist.py, tests/api/test_platform_auth.py, tests/integration/test_me_watchlist_sql.py, tests/gcp/test_schema_user_watchlists.py, tests/gcp/test_user_watchlist_isolation.py. |` and commit `docs(site): INSIGHTS-09 implementation-source note for the per-user watchlist API`.
- [ ] **Step 3: Produce** the snapshot with the Step 1 command (it now installs the record) and commit `docs(evidence): site source snapshot for the per-user watchlist API`.
- [ ] **Step 4: Verify**: `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000` exits 0 with `status identity-matched`, and `python3 scripts/maintenance/docs_audit.py` on the branch reports nothing `origin/main` does not.

### Task 10: Close

Spec: § Done when. Closes done_when[7].

- [ ] Update the `### FEAT-INSIGHT-001` record in `docs/product/02-FEATURE-CATALOG.md` (`:279`: Status, Last reviewed) and the FEAT-INSIGHT-001 PR lineage in `docs/product/12-PR-ISSUE-TRACEABILITY.md` (`:495`).
- [ ] `python3 scripts/maintenance/docs_audit.py` on the branch and on `origin/main`: nothing new.
- [ ] `make test` green; `python3 scripts/gate/spec_gate.py --pr origin/main` ok.
- [ ] Tick every done_when line in the PR body with its evidence (test names, the snapshot diff, the integration test names for item 0); the post-merge close-out comment follows the merge (Task 11).

### Task 11: Post-merge close-out

Spec: § Post-merge close-out. After the merge, read-only, recorded as one PR comment; none of it is an acceptance item.

- [ ] **Step 1:** `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud builds list --region us-east1 --filter='substitutions.TRIGGER_NAME="apply-schema-on-change"' --limit=1 --format='value(id,status,createTime)'`: the build the merge started reads `SUCCESS`; note its id.
- [ ] **Step 2:** `./scripts/db_query_cr.sh -q "SELECT table_name FROM information_schema.tables WHERE table_name IN ('watched_tickers', 'user_watchlists') ORDER BY 1"` (no `--commit`): expected exactly `user_watchlists`, `watched_tickers`; note the execution id.
- [ ] **Step 3:** `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud run services describe solyra-api-staging --region us-east1 --format='value(status.latestReadyRevisionName)'` names the revision serving the merge; `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud run revisions describe <revision> --region us-east1 --format='value(spec.containers[0].image)'` and `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud builds list --filter='substitutions.COMMIT_SHA="<merge sha>"' --format='value(id,status,images)'` agree on the image, which proves the deployed code is the merge commit whose OpenAPI snapshot lists the three operations. Note, not a check: `curl -s https://solyra-api-staging-5sjtb3yl7a-ue.a.run.app/api/me/watchlist` answers 401 `sign in to continue` from the auth middleware for any path, so it proves nothing about the route.
- [ ] **Step 4:** post the three results as one PR comment. Any other result stops here for the owner.
