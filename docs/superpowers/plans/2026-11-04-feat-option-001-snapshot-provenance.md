---
feat_id: FEAT-OPTION-001
spec: docs/superpowers/specs/2026-10-24-feat-option-001-legacy-snapshot-labels.md
branch: feature/feat-option-001-snapshot-provenance
pr: null
status: ready
---

# Snapshot provenance on grid, levels and chain responses — implementation plan (S2)

> **Status notes (2026-11-04 18:58 UTC, session machine clock).** Spec on `origin/main`
> at `0b9977800c404160314e65ffaca9256908321206` (#1580 merged about 18:42 UTC, squash of
> `b0f67dac`): `docs/superpowers/specs/2026-10-24-feat-option-001-legacy-snapshot-labels.md`,
> `status: approved`, git blob `53b43ae5bf7cc7052c8f516cda83d9ef99fc13e0`, sha256
> `5717968aeee0e7f510bd905cb2a4bd494ca1aafbd55862c7abf8f28cca48ed88`; its six `done_when`
> strings are quoted verbatim in the mapping table. `0b997780` differs from `1fb97576` only by
> that spec file, so every code line cited below was re-read on `0b997780`. Open
> dependencies are listed in the next section and are not satisfied by this plan existing:
> done_when[3] needs the solyra paired evidence, done_when[5] needs the A8 binding from its
> owner, and the chain-response field (X1) is a conditional proposal. Nothing here is a
> readiness claim.
>
> For agentic workers: use superpowers:subagent-driven-development or
> superpowers:executing-plans. Every task cites a spec section and the done_when
> item it advances. done_when indices below are 0-based against the spec list.

## Dependency status (verified 2026-11-04 18:47 to 18:58 UTC unless marked)

| Dependency | State | Evidence or what is missing |
|---|---|---|
| Spec on main with `status: approved` | **verified** | `0b997780`, blob `53b43ae5`, sha256 `5717968a…ed88` |
| Code baseline unchanged since the audit | **verified** | `git diff --stat 1fb97576 0b997780`: one file, the spec; all anchors re-read on `0b997780` |
| Accepted A10 binding (done_when[5]) | **published binding recorded; not re-run** | `docs/superpowers/specs/2026-10-29-feat-option-001-collector-source-declaration.md` on `0b997780` (L23) names the accepted reproduction packet SHA256 `ecda596ae24b85adfc537d7203a40ce62c1ae2c241e0d4c646340ec32c4d8f87` with a 175-test A10 profile; `tests/gcp/test_av_options_collector_entry.py` pins the accepted transport SHA256 `af238d07c2043a0d34319dd533f6e36842e68a9ff536c37d9700e859de117284` (L144 at `a5437994`, still L144 at `0b997780`), and `gcp/fetchers/_av_realtime_transport.py` at `0b997780` hashes to exactly that value. The three current-main blob OIDs below are the identity of the A10-side files today, not a substitute for the accepted packet or member manifest, and unchanged acceptance is not re-run here |
| A10-side files on main (identity only) | **verified** | `gcp/fetchers/fetch_av_realtime_options.py` `82d2575d`, `gcp/options_retention_job.py` `22bd2cdc`, `tests/gcp/test_av_options_realtime_producer.py` `4b1293ec` (blob OIDs at `0b997780`) |
| Accepted A8 member manifest (done_when[5]) | **missing, explicitly** | Not on `0b997780` (`tests/gcp/test_av_options_archive.py`, `lib/av_options_admission.py` absent). Not in #1495's tree at `e641f0cd` (its plan `2026-10-13-feat-option-001-av-source-journal.md` names the old A spec SHA256 `9e634992fb089c9a00d79b31234e81ede30ad93c2c66daec1fbb31f72cbc35d4` and the `av-options-normalized/v1` codec, no A8 member hashes). #1521 comments 6204262200 and 6204262874 (2026-10-15) name the successor candidate SHA256 `94e980e5…1400`, the native gate SHA256 `aa259cfa…0bd0`, and state that the private codec and tests "remain untouched at e641 with their three previously untracked paths": untracked, so not readable here. Owner identity as recorded there: the sole A CODE owner, reviewing from `/root/options_implementation`. The manifest is not recreated or published by this plan; done_when[5] stays unticked until that owner supplies the member hashes or states the binding in writing |
| Q/API #1528 shared boundaries | **open, coordination required** | see "Shared boundaries with the guarded-API contract" below |
| Solyra F2 spec approved on solyra main | **missing** | solyra main re-read 18:5x UTC: `e8d1df4c`, unchanged; no F2 spec and no Options PR on main or in the open list; `drafts/solyra-spec-2026-11-04-feat-option-001-snapshot-provenance-consumer.md` is a scratch proposal only; no solyra writer is verified (this session has read-only access and seeks none) |
| Paired exact-SHA evidence for done_when[3] | **mechanism defined; cannot start** | the ordering in Task 10 stands (F2 developed against this branch's full head SHA after Task 9, hermetic run and screenshots posted on this PR before it is marked ready, F2 re-synced after merge); it cannot begin until the F2 spec is on solyra main and a writer exists. The missing writer and spec are a separate gap from the ordering, which is unchanged |
| F2 contract pin target | not yet available | this branch's head SHA after Task 9 |
| X1 chain-response field | **unresolved** | the field on `OptionsChainResponse` is a conditional proposal (Task 1c, Task 6, Task 9); the approved spec names grid and levels response schemas and "levels/chain cache hits"; without X1 the chain provenance stays internal to `_CHAIN_CACHE` and is copied onto levels only |
| X2 unavailable envelope | **closed by the contract's default** | the field is nullable; the unavailable envelope carries `snapshot_provenance: null` (no rows to describe). No behaviour requirement changes |
| X3 A8 binding | **open** | same as the A8 row |
| Serial order on `platform/api/openapi.json` | S2 first | S3, S4, S5 follow; Earnings #1608 and ORB #1642 heads not re-read |
| Other owners' contracts | untouched | `lib/` unchanged; Timezone helpers consumed not edited; A6 evaluator sole; nodes payloads unchanged; Q/API files shared, see below |

## Shared boundaries with the guarded-API contract (#1528, Q)

PR #1528 (`docs/spec-feat-option-001-api-reviewed-recut`, head `0e18b90169174a6d68735c485d4b89a502b457b0`, open, spec on its branch) assigns to Q the same surfaces this plan edits: Q1 `options.py::get_options/_CHAIN_CACHE`, Q5 `options.py::get_gamma_levels` and `GammaLevelsResponse` with a nullable `source_provenance` (≤32 KiB), Q6 to Q9 both live and historical grid and node hit sites in `grid.py`, and the shared `schemas.py`. Q requires `Cache-Control: no-store` on every success, refusal, error and hit response, at most two SQL round trips per request, and "no mutable fallback". Q's provenance members are `source_provenance` and computation provenance, not this spec's `snapshot_provenance`. Different field names are not compatibility proof; the approved #1580 spec says it "complements the existing guarded API contract in #1528 and does not supersede or reopen its qualification protocol" and asks to "coordinate any field-name collision with that contract's owner before implementation".

Shared boundaries recorded, not resolved here:

- Files both touch: `platform/api/routers/options.py` (hit sites L534 to L547, store L626, `get_gamma_levels`), `platform/api/routers/grid.py` (hit reads L650, L662, L763, L775; stores L733, L806), `platform/api/schemas.py` (`GammaLevelsResponse`, `GammaGridResponse`), `platform/api/openapi.json`.
- Semantics that could interact: S2 copies the cached payload on a hit and re-stamps `observed_at`; Q forbids a mutable fallback and bounds SQL round trips. S2 adds zero SQL round trips and no fallback, but the two caching rules have not been shown compatible by anyone. S2 attaches `snapshot_provenance` with statuses fixed to `unknown`; Q's `source_provenance` is a qualification result. The two objects describe different things and the spec says so, but their co-presence on one response has not been confirmed by Q's owner.
- Confirmation needed before this plan's PR is marked ready (recorded in Task 12 as a gate, not an assumption): the existing Q owner confirms in writing, on this PR or the #1528 thread, that (a) `snapshot_provenance` may be added to `GammaLevelsResponse` and `GammaGridResponse` beside Q's planned members with no renaming on either side, (b) S2's hit-site copy and re-stamp does not conflict with Q's no-store and round-trip rules as Q will implement them, and (c) whichever of S2 and Q lands second rebases onto the other's hit-site changes. This plan does not ask the Q owner to adapt Q's contract, and does not change it.

## What this plan delivers, and what it does not

Adds one nullable `snapshot_provenance` object (spec § Design: metadata and clock
rules) to the live and dated grid responses and the levels response, built from
evidence the existing queries already return, and retains the chain's provenance inside
`_CHAIN_CACHE` so levels can copy it; publishing it on the chain response itself is a
conditional proposal gated on X1 (Task 1c, Task 6, Task 9), with the
observation clock re-stamped on every cache hit without mutating the cached
payload. No source-selector change, no cache-policy change, no new SQL
statement, no provider call, no numerical change (spec § Non-goals). The
`GammaNodesResponse` is not in the spec's wire list and is not changed; its
callers only absorb the loader's wider return value.

Six done_when items, mapped:

| done_when | Item (abridged) | Tasks |
|---|---|---|
| [0] | Direct and ASGI grid/levels tests show actual selected source timestamp and origin, freshness and completeness unknown | 1, 3, 4, 6 |
| [1] | Warm-cache tests advance observation time and age, source timestamp fixed, no added SQL/provider calls | 5, 7 |
| [2] | Timestamp edge tests: missing, naive, mixed, future, no manufactured age | 2, 8 |
| [3] | Hermetic Playwright on the solyra options screen with screenshots | 10 (cross-repo evidence rule) |
| [4] | Compatibility: numerical outputs, source selection, nullable fields preserved across grid and levels | 1, 3, 4, 9 |
| [5] | A8/A10 source hashes unchanged, no Q qualification evaluator duplicated | 11 |

## Verified baseline (2026-11-04 18:47 UTC, read from the tree at `0b997780`, not from docs)

- `platform/api/routers/grid.py`: caches L100-103; `_unavailable_envelope` L192-214;
  `_load_chain_for_live` L220-302 and `_load_chain_for_historical` L303-347 each return a 5-tuple
  `(contracts, snapshot_ts_iso, snapshot_date, data_source, days_behind)`; its two
  SELECT lists do not project `market_session` (the REALTIME statement filters on it,
  the EOD statement accepts `'EOD' OR NULL`, so the row's session is not retained);
  `_fetch_on_demand` L440-600 stamps `snapshot_ts = datetime.now(timezone.utc)` (an aware
  receive stamp, exactly the "native rows may contain a receive stamp" case the spec
  names); live grid `get_grid_live` L619-735 with cache-hit reads at L650 (pre-claim) and L662
  (in-claim, inside `_LIVE_GRID_FLIGHT.claim` L660) and the store at L733; dated grid
  `get_grid_historical` L739-808 with hit reads at L763 and L775 (claim L773) and the
  store at L806; nodes `get_nodes_live` L933-999 and `get_nodes_historical` L1001-1068
  call the same loaders and unpack 5 values at L967 and L1036.
- `platform/api/routers/options.py`: `_CHAIN_CACHE` L90 (12 h), `_CHAIN_FLIGHT` L112; `get_options`
  L525-627 reads the cache at L534 (pre-claim, return L539) and L545 (in-claim inside
  `_CHAIN_FLIGHT.claim` L543, return L547), stores at L626, and returns `{**cached, "cached": True}` at both hit sites and its SELECT does
  not project `market_session`; `get_gamma_levels` L810-848 calls `get_options`
  directly (sync; `tests/api/test_api_handler_dispatch.py::test_gamma_levels_and_its_chain_loader_agree`
  pins that) and spreads `summary.to_dict()` plus `snapshot_timestamp`, `chain_size`.
- `platform/api/schemas.py`: `ApiModel` is `extra="allow"` (L43-46);
  `OptionsChainResponse` L819-825; `GammaLevelsResponse` L908-924; `GammaGridResponse`
  L949-969; `GammaNodesResponse` L991-1009. Routes use
  `response_model_exclude_unset=True`, so a key absent from the payload dict is not
  emitted: the new key must be present (as `None` or an object) in every payload that
  should carry it.
- `lib/gamma.py`: `GammaGridSummary.to_dict()` is `asdict(self)` (L197; `GammaSummary.to_dict()` likewise at L126); the object is
  attached by the router after `to_dict()`, so `lib/` is untouched.
- Tests: `tests/api/test_grid_router.py` builds a clean `FastAPI()` with the grid
  router, monkeypatches `gcp.database.query_to_dataframe` by SQL text
  (`_install_query_router`, L114), and its `_chain_df` fixture (L39) stamps a **naive**
  `pd.Timestamp(".. T15:55:00")` (L45); its `client` fixture builds the app at L94-111. `tests/api/test_options_router.py` calls the
  Greeks handler directly and has no TestClient yet (0 occurrences at `0b997780`). `tests/api/test_openapi_snapshot.py`
  fails on any schema change until `python scripts/export_openapi.py` is re-run.
- No existing `platform/api` helper covers timestamp-group validation; the only
  shared modules beside the routers are `threadsafe_cache.py`, `http_errors.py`,
  `gcs_reader.py`, `auth.py`. Neither router imports the other.

Not checked here: whether pg8000 returns `TIMESTAMPTZ` as aware `datetime` in
production (the builder handles both; the naive case is `timestamp_invalid`, never a
manufactured age). Response-size and latency deltas are measured in Task 12 against
the hermetic app only; production p95 is not claimed (spec § Verification).

## Capacity (CLAUDE.md rule 0, copied into the PR body)

- **Volume:** 0 new rows read or written. Inputs are the rows the existing statements
  already select (≈5K contracts per chain; ≈12 in fixtures). Output grows by one
  object of 9 scalar members, ≈250 bytes per response.
- **Velocity:** 0 additional SQL statements, 0 provider calls, 0 network round trips.
  Projecting `market_session` adds one column to four existing SELECT lists; a cache
  hit still runs 0 queries (Tasks 5 and 7 assert the counter).
- **Wall-clock:** one pass over the selected rows' `snapshot_ts`/`market_session`
  columns (`min`/`max`/`nunique` on a 5K-row Series, sub-millisecond) plus one
  `datetime.now(timezone.utc)` per response. No Cloud Run job, no scheduler, so no
  task-timeout or $/run; cost delta $0.

## Task 1: schema object and nullable field on three response models
Spec: § Design: metadata and clock rules (wire members). Advances done_when[0], [4].
- [ ] In `platform/api/schemas.py`, add before `GammaLevelsResponse`:
  `class SnapshotProvenance(ApiModel)` with `provider: Optional[str] = None`,
  `market_session: Optional[str] = None`, `snapshot_ts: Optional[str] = None`,
  `observed_at: str`, `snapshot_age_seconds: Optional[int] = None`,
  `freshness_status: Literal["unknown"]`, `completeness_status: Literal["unknown"]`,
  `reason: Literal["legacy_snapshot_unqualified", "timestamp_invalid", "timestamp_future"]`.
  Docstring states the three clock rules in one line each (stored clock retained;
  observed_at is response assembly; age is display age, not provider lag).
- [ ] Add `snapshot_provenance: Optional[SnapshotProvenance] = None` to
  `GammaGridResponse` and `GammaLevelsResponse` (the two schemas the approved spec
  names).
- [ ] **Task 1c, conditional on X1 (not approved):** adding the same field to
  `OptionsChainResponse` is a proposal, because the spec's cache rule names
  "levels/chain cache hits" and the levels response copies the chain's evidence (Task
  6). Until the owner resolves X1 this sub-task is not executed: the chain's provenance
  stays internal to `_CHAIN_CACHE`, the chain HTTP response is unchanged, and the
  solyra F2 spec reads the chain field as optional for exactly this reason.
- [ ] Write failing test `tests/api/test_grid_router.py::TestSnapshotProvenanceSchema::test_null_provenance_is_emitted_when_present`:
  a payload dict with `"snapshot_provenance": None` serialises with the key present
  and null through `response_model_exclude_unset=True`; a payload without the key omits
  it (documents the rule the routers depend on).
- [ ] Run: `python -m pytest tests/api/test_grid_router.py -k SnapshotProvenanceSchema tests/api/test_openapi_snapshot.py -q`
  (expect FAIL: new test red, snapshot stale).
- [ ] Implement; run again (expect the new test PASS; the snapshot test stays red until Task 9).
- [ ] Commit: `feat(api): add nullable snapshot_provenance to grid, levels and chain schemas`

## Task 2: provenance builder with a mockable observation clock
Spec: § Design: metadata and clock rules (validation paragraphs). Advances done_when[2].
- [ ] Create `platform/api/snapshot_provenance.py` (one new module; both routers need
  it, neither may import the other, and `lib/` is the math spine, not API assembly).
  Contents:
  - `_now_utc() -> datetime` returning `datetime.now(timezone.utc)`; the only clock
    the routers call, so tests monkeypatch one name.
  - `@dataclass(frozen=True) class ChainEvidence`: `provider: Optional[str]`,
    `sessions: list[Optional[str]]`, `timestamps: list[Any]` (the selected rows'
    `market_session` and `snapshot_ts` values, untouched).
  - `build_snapshot_provenance(evidence: ChainEvidence, observed_at: datetime) -> dict`:
    validates the **whole group**. Every timestamp must be a `datetime`/`pd.Timestamp`
    with `tzinfo` set and all must be the same instant when converted to UTC
    (`len({t.astimezone(timezone.utc) for t in ts}) == 1`); otherwise
    `snapshot_ts=None, snapshot_age_seconds=None, reason="timestamp_invalid"`
    (covers missing, naive, mixed, and inconsistent). Valid and `> observed_at`:
    `snapshot_ts` kept as aware UTC ISO, age `None`, `reason="timestamp_future"`.
    Valid otherwise: age `= int((observed_at - ts).total_seconds())` (floor; finite,
    non-negative by construction), `reason="legacy_snapshot_unqualified"`.
    `market_session` is the single distinct non-null value when every row agrees,
    else `None` (all-NULL legacy rows stay `None`; never infer `EOD` from the
    fallback label). `provider` passes through. `freshness_status` and
    `completeness_status` are the literal `"unknown"`.
  - `with_observation(prov: dict, observed_at: datetime) -> dict`: returns a **new**
    dict with `observed_at` and a recomputed age from the stored `snapshot_ts`
    (re-parsed; a `timestamp_future` entry can become a finite age once the clock
    passes it, and its reason then becomes `legacy_snapshot_unqualified`;
    `timestamp_invalid` stays invalid). Never writes into its argument.
- [ ] Write failing tests in new `tests/api/test_snapshot_provenance.py` (the module is
  new; its focused tests sit beside it): aware UTC group; equal instants in two zones
  (`+00:00` and `-04:00`) validate; one naive among aware → invalid; all naive →
  invalid; `None`/`NaT` present → invalid; two distinct aware instants → invalid;
  future by 1 s → `timestamp_future`, age `None`, `snapshot_ts` retained, never
  clamped to 0; sessions all `REALTIME` → `REALTIME`; all `None` → `None`;
  mixed `EOD`/`None` → `None`; `with_observation` leaves the input dict byte-equal
  and advances age by the clock delta.
- [ ] Run: `python -m pytest tests/api/test_snapshot_provenance.py -q` (expect FAIL, then PASS).
- [ ] Commit: `feat(api): snapshot provenance builder with whole-group clock validation`

## Task 3: retain query evidence through both grid loaders, keep nodes unchanged
Spec: § Design: metadata and clock rules ("retain the original timestamp's source-row
evidence", "no new SQL"); § Ownership (grid.py outside A4). Advances done_when[0], [4].
- [ ] In `_load_chain_for_live` and `_load_chain_for_historical`, add `market_session`
  to the three existing SELECT lists (same statements, same WHERE, same rows; the test
  router keys on the `market_session = 'REALTIME'` / `'EOD'` WHERE text and still
  matches). Return a 6-tuple ending in `ChainEvidence(provider="alphavantage" if rows
  else None, sessions=df["market_session"].tolist(), timestamps=df["snapshot_ts"].tolist())`.
  Empty result: `ChainEvidence(None, [], [])`. The `data_source='alphavantage'`
  literal in the WHERE clause is the proven provider identity for these rows.
- [ ] On-demand branch (live grid): read `_fetch_on_demand` L440-600 and record in the
  PR which `market_session` the persisted frame carries. Evidence is
  `provider="alphavantage"` (the call was made), `timestamps=[snapshot_ts]*len(rows)`
  (the aware receive stamp), `sessions=` the persisted value if the frame carries one,
  else `[None]*len(rows)`. Do not write `REALTIME` from the `data_source="realtime"`
  label.
- [ ] Update every unpack site to six values: live grid (two calls, L673 and L692),
  dated grid (L786), nodes live (L967), nodes historical (L1036). Nodes ignore the
  sixth value; their payload dicts are unchanged.
- [ ] Extend `_chain_df(snapshot_date, market_session="REALTIME", tz=None)` in
  `tests/api/test_grid_router.py`: add a `market_session` column from the argument
  (`None` allowed) and make `snapshot_ts` aware when `tz` is given. Default `tz=None`
  keeps every existing assertion byte-identical.
- [ ] Write failing tests `TestLoaderEvidence::test_live_loader_returns_group_evidence`
  and `::test_historical_loader_returns_group_evidence` (direct calls, not ASGI):
  sessions and timestamps equal the fixture column values; the first five tuple
  members equal the pre-change values for the same fixture (pin them from a run on
  `origin/main` and paste the numbers into the test docstring).
- [ ] Run: `python -m pytest tests/api/test_grid_router.py -q` (expect only the new
  tests to fail, then the whole file green).
- [ ] Commit: `feat(grid): retain market_session and snapshot_ts group evidence from the chain loaders`

## Task 4: cold assembly on the live and dated grid routes
Spec: § Design: metadata and clock rules; § Verification ("Direct and ASGI live/dated grid").
Advances done_when[0], [4].
- [ ] In `get_grid_live` and `get_grid_historical`, after `payload = summary.to_dict()`,
  set `payload["snapshot_provenance"] = build_snapshot_provenance(evidence, _now_utc())`
  before `_LIVE_GRID_CACHE[cache_key] = payload` / `_HIST_GRID_CACHE[...]`. The cached
  payload therefore stores the fill-time observation; Task 5 re-stamps on hits.
- [ ] Unavailable path: `_unavailable_envelope` gains `"snapshot_provenance": None`,
  the nullable contract's safe default (X2 closed by default): the spec says "if no rows
  exist, metadata remains unknown with null timestamp, origin and age; preserve the
  existing unavailable envelope and do not invent data" and "propagate null rather than
  invent provenance". A null object says "no selected rows to describe"; the solyra
  consumer treats unavailable as unavailable regardless (its spec's state precedence).
  No behaviour requirement changes.
- [ ] Write failing ASGI tests in `TestGridLive` / `TestGridHistorical`:
  - realtime fixture (`tz="UTC"`, `market_session="REALTIME"`, dated three sessions
    back): `provider=="alphavantage"`, `market_session=="REALTIME"`,
    `snapshot_ts` equals the fixture instant as UTC ISO, `freshness_status=="unknown"`,
    `completeness_status=="unknown"`, `reason=="legacy_snapshot_unqualified"`,
    `observed_at` equals the monkeypatched clock, age equals the difference in
    seconds; `data_source=="realtime"` still (source selection unchanged, spec
    non-goal) and `days_behind` semantics untouched.
  - EOD fallback fixture with `market_session=None` on every row:
    `market_session is None` (not `"EOD"`).
  - dated grid: same assertions on `/api/options/SPY/2026-06-01/grid`.
  - unavailable: `snapshot_provenance is None`, every pre-existing envelope key
    unchanged (compare to the Task-0 envelope literal).
  - compatibility: `cells`, `strikes`, `expirations`, `total_gex`, `total_vex`,
    `spot`, `regime`, `warnings` equal a baseline captured from `origin/main` for the
    same fixture (store the baseline dict in the test module; the numbers are the
    evidence).
- [ ] Run: `python -m pytest tests/api/test_grid_router.py -q` (FAIL, then PASS).
- [ ] Commit: `feat(grid): attach snapshot_provenance on cold live and dated grid assembly`

## Task 5: both grid cache-hit sites copy before re-stamping observation
Spec: § Design: metadata and clock rules (cache paragraph: "copy the cached result
before attaching current observed_at and recomputed age. Never mutate shared cached
payloads in place."). Advances done_when[1].
- [ ] Add a module-level helper in `grid.py`,
  `_serve_cached(cached: dict) -> dict`, returning
  `{**cached, "snapshot_provenance": with_observation(cached["snapshot_provenance"], _now_utc()) if cached.get("snapshot_provenance") else cached.get("snapshot_provenance")}`.
  Shallow copy of the outer dict plus a new provenance dict; `cells` and other lists
  are shared read-only, as today.
- [ ] Use it at all four grid hit sites: live pre-claim (read L650), live in-claim
  (read L662), dated pre-claim (read L763), dated in-claim (read L775). Cache-Control headers unchanged.
- [ ] Write failing ASGI tests `TestGridLive::test_warm_hit_advances_observation_not_source`
  and the dated twin: install a counting `fake_query`; call at clock T0 (cold, N
  queries), advance the monkeypatched `_now_utc` by 30 s, call again: query count
  unchanged (0 new calls), `observed_at` advanced by 30 s, `snapshot_age_seconds`
  increased by exactly 30, `snapshot_ts` identical, `data_source` identical; then
  assert `grid_router._LIVE_GRID_CACHE[cache_key]["snapshot_provenance"]` still equals
  the T0 values (the cached payload was not mutated) and that the two response dicts
  are not the same object.
- [ ] Concurrency assertion (spec § Verification, "concurrent cached readers cannot
  overwrite each other's observation timestamps"): with the cache warm, run 8 threads
  through `TestClient` with per-thread clock offsets injected via a thread-local in
  the monkeypatched `_now_utc`; every response's `observed_at` equals its own thread's
  clock and the cached entry is unchanged afterwards.
- [ ] Run: `python -m pytest tests/api/test_grid_router.py -k warm -q` (FAIL, then PASS).
- [ ] Commit: `feat(grid): re-stamp observation on cache hits from a copy, never in place`

## Task 6: chain and levels assembly in options.py
Spec: § Design: metadata and clock rules; § Ownership (options.py levels and chain cache
assembly). Advances done_when[0].
- [ ] In `get_options`, add `market_session` to the existing SELECT list (same
  statement). After `contracts = _df_to_contracts(df)`, build
  `evidence = ChainEvidence("alphavantage", df["market_session"].tolist(), df["snapshot_ts"].tolist())`
  and store `build_snapshot_provenance(evidence, _now_utc())` with the cached entry
  before `_CHAIN_CACHE[cache_key] = response`. **X1 unresolved:** by default the object
  is kept beside the cached payload for levels to copy and is stripped from the chain
  HTTP response before serialisation; only an approved X1 makes it a `response` key. Existing `snapshot_timestamp`
  computation is unchanged (it stays the legacy `max()` string; the provenance object
  is where group validation lives).
- [ ] Both hit sites (returns at L539 and L547, after the reads at L534 and L545) become
  `{**cached, "cached": True, "snapshot_provenance": with_observation(cached["snapshot_provenance"], _now_utc())}`
  (the `{**cached}` copy already exists there; the provenance copy is the addition).
- [ ] In `get_gamma_levels`, add `"snapshot_provenance": chain_response.get("snapshot_provenance")`
  to the returned dict. `get_options` already hands back a fresh outer dict and a fresh
  provenance dict, so no second copy is needed; say so in a comment.
- [ ] Write failing tests in `tests/api/test_options_router.py`, new class
  `TestChainAndLevelsProvenance` with a TestClient over `routers.options.router`
  (mirror the grid file's `client` fixture: patch `is_cloud_sql_configured`, clear
  `_CHAIN_CACHE`, monkeypatch `query_to_dataframe` to return a chain frame with
  aware `snapshot_ts` and a `market_session` column):
  - ASGI `GET /api/options/SPY/2026-06-01` carries the object with the row instant and
    session; `cached` false then true on the second call.
  - ASGI `GET /api/options/SPY/2026-06-01/levels` carries the same object values as the
    chain response it was built from; `snapshot_timestamp`, `chain_size`, `levels`,
    `kings`, `gates`, `total_gex`, `regime` equal a baseline captured on `origin/main`.
  - Direct: `get_gamma_levels("SPY", "2026-06-01")` returns the key (spec: "Direct and
    ASGI").
- [ ] Run: `python -m pytest tests/api/test_options_router.py tests/api/test_api_handler_dispatch.py -q`
  (FAIL, then PASS; the dispatch test must stay green: `get_gamma_levels` stays `def`).
- [ ] Commit: `feat(options): attach snapshot_provenance on chain fill and copy it onto levels`

## Task 7: levels and chain warm-cache tests
Spec: § Verification ("the levels 12-hour cache are exercised"). Advances done_when[1].
- [ ] Write failing tests in `TestChainAndLevelsProvenance`: chain at T0, clock +45 s,
  chain again → `cached` true, 0 new queries, age +45, `snapshot_ts` fixed,
  `_CHAIN_CACHE[(ticker, date)]["snapshot_provenance"]` equals T0 values; levels at
  T0 and T0+45 s → same properties, 0 new queries on the second call (levels has no
  cache of its own; it rides the chain cache, and the test proves that is still true).
- [ ] Run: `python -m pytest tests/api/test_options_router.py -k warm -q` (FAIL, then PASS).
- [ ] Commit: `test(options): warm chain and levels hits advance observation only`

## Task 8: timestamp edge cases through the routes
Spec: § Design: metadata and clock rules (validation); § Verification
("Missing/naive/mixed/future clocks refuse invented ages; equal aware instants agree").
Advances done_when[2].
- [ ] Write failing ASGI tests in `tests/api/test_grid_router.py::TestProvenanceEdgeCases`
  (grid) and `tests/api/test_options_router.py::TestChainAndLevelsProvenance` (levels):
  - naive rows (the existing `_chain_df` default): `snapshot_ts is None`, age `None`,
    `reason=="timestamp_invalid"`, while the legacy top-level `snapshot_ts` /
    `snapshot_timestamp` strings are byte-identical to `origin/main` output.
  - mixed: one row aware, rest naive → `timestamp_invalid`.
  - two aware instants in one group → `timestamp_invalid` (the loaders select one
    `snapshot_ts`, so this is a regression guard, not an expected production state).
  - equal instants, `+00:00` on half the rows and `-04:00` on the rest → valid.
  - future (fixture instant = clock + 600 s): `snapshot_ts` retained as the aware UTC
    ISO string, age `None`, `reason=="timestamp_future"`; a warm hit after advancing
    the clock past the instant yields a finite age and
    `reason=="legacy_snapshot_unqualified"` (the spec's "never clamped to zero").
  - `None`/`NaT` in `snapshot_ts` on one row → `timestamp_invalid`.
- [ ] Run both files (FAIL, then PASS).
- [ ] Commit: `test(api): provenance edge clocks never manufacture an age`

## Task 9: regenerate the OpenAPI snapshot and review its diff
Spec: § Ownership ("generated OpenAPI only through the existing renderer"). Advances
done_when[4]; prerequisite for the solyra F2 branch (Task 10).
- [ ] Run `python scripts/export_openapi.py`; then
  `python -m pytest tests/api/test_openapi_snapshot.py -q` (PASS).
- [ ] `git diff --stat platform/api/openapi.json` and read the diff: exactly one new
  component `SnapshotProvenance` and two `anyOf [$ref, null]` properties on
  `GammaGridResponse` and `GammaLevelsResponse` (a third on `OptionsChainResponse` only
  if X1 is approved); no operation added or removed; `GammaNodesResponse` unchanged. Paste the hunk headers into the PR
  body.
- [ ] Commit: `chore(api): regenerate openapi.json for snapshot_provenance`

## Task 10: cross-repo evidence for done_when[3] (hermetic Playwright on the solyra screen)
Spec: § Design: visible consumer; § Verification ("Hermetic Playwright exercises the
actual options screen ... Record screenshots under test-results"); § Ownership
("Cross-repository work requires separate ready plans/branches and draft PRs").
Closes done_when[3] on this PR by evidence produced in solyra.
- [ ] The paired solyra change is spec
  `solyra docs/superpowers/specs/2026-11-04-feat-option-001-snapshot-provenance-consumer.md`
  (draft F2). F2 code starts only after that spec is approved on solyra `main`
  (solyra gate). F2 does not wait for the solyra F1 batch or for stocks S3: its only
  stocks dependency is this branch's contract. Its branch is developed against
  **this** branch's exact draft contract, pinned to an immutable identity, never a
  mutable branch name: `STOCKS_OPENAPI_REF=<full 40-hex commit SHA of this branch's
  head after Task 9> npm run contract:sync` in solyra, or
  `STOCKS_OPENAPI_FILE=<path>/platform/api/openapi.json` whose sha256 is recorded
  and verified against `git -C stocks show <full SHA>:platform/api/openapi.json | sha256sum`
  before use. Either way the F2 branch commits the full SHA and the JSON sha256
  in its PR body, and the regenerated `tests/fixtures/stocks-openapi.json` and
  `src/types/stocksOpenApi.gen.d.ts` come from that exact file.
- [ ] Evidence attached to this PR before it is marked ready, as a PR comment and ticked
  next to done_when[3]: the solyra hermetic run of `tests/options/snapshot-provenance.spec.ts`
  (`npm run e2e`, chromium project) naming the solyra branch and its exact head SHA, the
  exact stocks head SHA of this branch the contract was synced from (the backend evidence
  is this PR's own API tests at that same SHA), and the screenshots the spec saves under `test-results/`
  with the state each shows (prior-session REALTIME stored label and no pulse;
  legacy payload without the object; null/invalid timestamp; future timestamp;
  unavailable; loading; error; warm client cache). The screenshots are the evidence;
  a green run alone is not (CLAUDE.md rule 3.11).
- [ ] Ordering, written into both PR bodies: this stocks PR does not merge before that
  exact-SHA evidence is posted; the solyra F2 PR does not merge before this one,
  because solyra's CI `contract:check` fetches stocks `main`; after this merge F2
  re-runs `npm run contract:sync` against `main` with no override, shows a
  byte-identical vendored file, and proceeds to its own review. F2 waits for nothing
  else (not F1, not S3). Neither PR stacks on the other's unmerged branch (spec §
  Problem and authority, last paragraph). One open solyra implementation PR at a
  time: F2 opens when the solyra lane's previous code PR has merged.
- [ ] No code changes in this task; it is a gate on marking the PR ready.

## Task 11: A8/A10 unchanged and no qualification evaluator duplicated
Spec: § Non-goals ("No edits to accepted A8/A10"); § Ownership ("The existing
source-journal A6 evaluator remains the sole current-source evaluator"). Advances
done_when[5].
- [ ] A10: record the **published binding**, not a current-main substitute: accepted
  reproduction packet SHA256 `ecda596ae24b85adfc537d7203a40ce62c1ae2c241e0d4c646340ec32c4d8f87`
  with its 175-test A10 profile (`2026-10-29-feat-option-001-collector-source-declaration.md`
  L23 on `0b997780`), and the accepted transport SHA256
  `af238d07c2043a0d34319dd533f6e36842e68a9ff536c37d9700e859de117284` pinned by
  `tests/gcp/test_av_options_collector_entry.py` L144. Assert on HEAD that
  `sha256(gcp/fetchers/_av_realtime_transport.py)` still equals `af238d07…7284` and that
  `git diff --stat origin/main..HEAD -- gcp/fetchers/fetch_av_realtime_options.py gcp/fetchers/_av_realtime_transport.py gcp/options_retention_job.py tests/gcp/test_av_options_realtime_producer.py tests/gcp/test_av_options_collector_entry.py`
  prints nothing. The current-main blob OIDs (`82d2575d`, `22bd2cdc`, `4b1293ec`) are
  recorded as today's identity of those files only. The accepted 175-test suite is not
  re-run as evidence for this item.
- [ ] A8: the member manifest is **not located** in any source this plan's author can
  read (not on `0b997780`; not in #1495's tree at `e641f0cd`; #1521 comments 6204262200
  and 6204262874 record that the private codec and tests are untracked at `e641`). Before
  this task closes, the sole A CODE owner (as recorded in comment 6204262874, reviewing
  from `/root/options_implementation`) supplies the A8 member paths and preserved hashes
  or states the binding in writing on this PR; the author does not recreate, infer or
  publish that proof. Until then done_when[5] stays unticked and this PR is not marked
  ready.
- [ ] `grep -rn "def classify_gamma_freshness" lib/ platform/` returns the one existing
  definition and the diff adds no function whose name or docstring classifies
  freshness, completeness, cadence or qualification; the only new statuses are the
  literal `"unknown"`. Note in the PR body that `reason` values describe clock
  validation, not qualification.
- [ ] Commit (docs/PR body only; no code).

## Planned tests (exact ids, consolidated)

New or extended, all hermetic, no database, network or provider call:

- `tests/api/test_snapshot_provenance.py` (new): `test_aware_utc_group_is_valid`, `test_equal_instants_in_two_zones_are_valid`, `test_one_naive_among_aware_is_invalid`, `test_all_naive_is_invalid`, `test_none_or_nat_is_invalid`, `test_two_distinct_instants_are_invalid`, `test_future_instant_keeps_timestamp_and_null_age`, `test_sessions_all_realtime`, `test_sessions_all_none`, `test_sessions_mixed_is_none`, `test_with_observation_does_not_mutate_input`, `test_with_observation_advances_age_by_clock_delta`.
- `tests/api/test_grid_router.py`: `TestSnapshotProvenanceSchema::test_null_provenance_is_emitted_when_present`; `TestLoaderEvidence::test_live_loader_returns_group_evidence`, `::test_historical_loader_returns_group_evidence`; `TestGridLive::test_cold_realtime_fixture_carries_provenance`, `::test_eod_fallback_with_null_sessions_keeps_market_session_none`, `::test_unavailable_envelope_carries_null_provenance_and_unchanged_keys`, `::test_compatibility_numerics_equal_baseline`, `::test_warm_hit_advances_observation_not_source`, `::test_concurrent_warm_readers_keep_own_observation`; `TestGridHistorical::test_dated_grid_carries_provenance`, `::test_warm_hit_advances_observation_not_source`; `TestProvenanceEdgeCases::test_naive_rows_are_timestamp_invalid`, `::test_mixed_rows_are_timestamp_invalid`, `::test_two_instants_are_timestamp_invalid`, `::test_equal_instants_two_zones_valid`, `::test_future_then_aged`, `::test_nat_row_is_timestamp_invalid`.
- `tests/api/test_options_router.py`: `TestChainAndLevelsProvenance::test_chain_carries_provenance_and_cached_flag`, `::test_levels_carries_chain_provenance_and_baseline_numerics`, `::test_direct_levels_call_returns_key`, `::test_chain_warm_hit_advances_observation_only`, `::test_levels_warm_hit_rides_chain_cache`, `::test_levels_naive_rows_are_timestamp_invalid`.
- Existing, must stay green unchanged: `tests/api/test_api_handler_dispatch.py::test_gamma_levels_and_its_chain_loader_agree`, every pre-existing test in both router files, `tests/api/test_openapi_snapshot.py::test_committed_openapi_snapshot_matches_app` after Task 9.
- Cross-repo (solyra, Task 10): `tests/options/snapshot-provenance.spec.ts` hermetic run with screenshots; `tests/options/snapshot-provenance.cloud.spec.ts` is the owner's post-deploy close-out, not a pre-merge box.

Expected baseline outcomes are expectations to record when run; no pass or fail is claimed in this draft.

## Task 12: measure, record, close
Spec: § Verification ("Measure actual response-size/latency delta during
implementation"); § Done when. Closes the records every done_when item depends on.
- [ ] Measure hermetically: with the Task 4 realtime fixture, `len(resp.content)` and
  the median of 200 `TestClient` calls on a warm cache, on `origin/main` and on HEAD;
  put both numbers in the PR body. State plainly that production p95 is not measured
  here.
- [ ] Update only the FEAT-OPTION-001 record in `docs/product/02-FEATURE-CATALOG.md`
  (Status: provenance metadata implemented, rollout pending; Last reviewed: date;
  Evidence status: source and hermetic tests, no deployment claim).
- [ ] Add this PR under FEAT-OPTION-001 in `docs/product/12-PR-ISSUE-TRACEABILITY.md`.
- [ ] `python3 scripts/maintenance/docs_audit.py` on this branch and on `origin/main`:
  no new finding. `python3 scripts/gate/spec_gate.py --pr origin/main`: clean.
- [ ] PR body: title `FEAT-OPTION-001: snapshot provenance on grid, levels and chain
  responses`; spec and plan paths; the six done_when lines as `- [ ]` with evidence
  (test ids from Tasks 1-9, the solyra run from Task 10, the OIDs from Task 11);
  Capacity section from above; the Task 9 diff hunks; the Task 12 measurements. Open
  as draft, then set `pr:` here in the next commit.
- [ ] Gate before marking ready: the Q/API owner's written compatibility confirmation
  (section "Shared boundaries with the guarded-API contract", items a to c) is posted on
  this PR or #1528 and linked here; the A8 binding (Task 11) is supplied; the solyra
  paired evidence (Task 10) is posted. None of the three is assumed.
- [ ] Rule 2.5: wait for Codex's first review, post the first-review comment per
  review type, resolve every thread, two review rounds at most, then merge. After the
  merge, on a `docs/<slug>` branch, set this plan's `status: done`.
