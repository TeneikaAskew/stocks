---
feat_id: FEAT-OPTION-001
req_ids: [REQ-UX-001, REQ-MARKET-001, REQ-DATA-001, REQ-DATA-003, REQ-FRESH-001, REQ-FRESH-002]
issues: [1211, 1562]
canvases: []
done_when:
  - "Direct and ASGI grid/levels tests show actual selected source timestamp and origin with freshness and completeness unknown for legacy snapshots"
  - "Warm-cache tests advance observation time and snapshot age without changing source timestamps or adding SQL/provider calls"
  - "Timestamp edge tests cover missing, naive, mixed and future timestamps without manufacturing a valid age"
  - "Hermetic Playwright options-screen tests and screenshots show stored/unverified timestamps without origin-only LIVE claims while preserving unavailable/loading/error states"
  - "Compatibility tests preserve numerical outputs, source selection and nullable response fields across existing grid and levels routes"
  - "Accepted A8/A10 source hashes remain unchanged and no Q qualification evaluator is duplicated"
status: approved
supersedes: null
---

# Truthful legacy options snapshot metadata and labels

## Problem and authority

Repository source treats source origin as evidence of freshness: grid's REALTIME
selection can use rows within twenty calendar days and return days_behind=0;
Solyra's SourcePill translates realtime into LIVE with a pulse. A source name does
not establish temporal freshness or chain completeness. A successful write
acknowledgement likewise does not independently verify persistence or completeness.

The owner explicitly approved the written design at PR #1580 head
`2c49a24e3624e8e2f55ab7545d8a8969ffcd28bb` on October 24, 2026, replying
"Yes i approve" to the request to approve this written freshness design. This
records design approval only; the decisions and acceptance criteria below are
unchanged. Required review, checks and actual specification MAIN merge still
precede implementation. No external review-bot contact is authorized by this
approval.
It complements the existing guarded API contract in
[TeneikaAskew/stocks#1528](https://github.com/TeneikaAskew/stocks/pull/1528)
and does not supersede or reopen its qualification protocol. Coordinate any
field-name collision with that contract's owner before implementation. Do not
stack an implementation on its unmerged branch.

Catalog intake: FEAT-OPTION-001 is "Options / gamma", "Flow, Greeks, GEX grid",
with backend `/api/options`, `/api/grid` and source `etf_options_snapshots`.
The requirements above govern truthful market context and shared freshness;
this display-only slice makes no cadence classification and introduces no
competing freshness evaluator. No catalog canvas maps to FEAT-OPTION-001.

Source baseline: stocks main 6f03ab14a7c858e741d9023f215a1bf24e0371c1;
Solyra local source da584ca45403183c741231d95511a0f5747d333f.
The recorded October 24 07:09 UTC runtime revision is
solyra-api-staging-00044-kbs, image
sha256:abc888153654bb0e4bb1425972a6773a4e40a36294ebf0480b188e43a06c6a7d.
Its source equivalence remains unknown. These repository findings must not be
presented as independently verified behavior of that deployed image.

## Non-goals

No Gamma, Greeks, valuation or strategy formula changes; no new eligibility
threshold, positive live/current/fresh certificate, source selector, fallback
policy, chain completeness assertion or provider call. No retry/quota/calendar
policy, source-journal schema or A4 recovery change. No edits to accepted A8/A10.
No production data correction, merge, deployment, backfill or GCP upload.
Numerical suppression and universal no-store/financial fencing remain Q-owned.
C summarizer/report/footer adoption remains separately owned and is not completed
by this API/UI slice.

## Approaches considered

1. Metadata plus matching consumer labels (selected): make the existing stored
   snapshot visible without claiming qualification or modifying numerical output.
2. Timestamp-only backend fields: smaller, but existing consumers could still show
   LIVE; insufficient for the user-visible acceptance criterion.
3. New cadence evaluator and numerical suppression: changes financial serving and
   duplicates Q ownership; excluded from this bounded contract.

## Design: metadata and clock rules

Add a nullable `snapshot_provenance` object to the actual grid and levels response
schemas, including dated variants that share their response model. Preserve
existing fields and numerical outputs. Proposed wire members:

- `provider`: actual selected source identity, or null when unavailable; never
  manufacture Alpha Vantage identity for an unproven source.
- `market_session`: actual selected REALTIME/EOD origin, otherwise null.
- `snapshot_ts`: aware UTC ISO timestamp derived from actual selected source rows,
  otherwise null. Retain the actual stored clock; legacy rows may contain a collector
  batch-start stamp, while native rows may contain a receive stamp. Neither is
  proof of the provider market as-of time. Do not relabel or replace that stored
  value with current request time, cache-fill time, a new retrieval time or ACK.
- `observed_at`: aware response-assembly UTC timestamp.
- `snapshot_age_seconds`: finite nonnegative observed_at minus valid snapshot_ts;
  otherwise null. This is display age, not A's measured source retrieval age.
- `freshness_status`: always `unknown` for this unqualified legacy path.
- `completeness_status`: always `unknown` without Q whole-group evidence.
- `reason`: `legacy_snapshot_unqualified`, `timestamp_invalid`, or
  `timestamp_future` as applicable.

Retain the original timestamp's source-row evidence in caches. Validate the entire
selected row group: missing, naive or inconsistent timestamps yield null source
timestamp/age and timestamp_invalid. Aware equivalent instants in different time
zones are valid. A timestamp after observed_at yields null age and timestamp_future;
it may be retained as the aware source timestamp for diagnostic display, never
clamped to zero. If no rows exist, metadata remains unknown with null timestamp,
origin and age; preserve the existing unavailable envelope and do not invent data.

The original selected source/session must accompany the cached payload; do not
infer EOD versus unknown from the legacy fallback label alone. If the loader does
not retain enough evidence, propagate null rather than invent provenance. This
requires no new SQL, only retaining existing query evidence through response
assembly. Do not substitute MAX across mixed source groups as a coherent group
clock. Origin and timestamp validation must cover the same selected contracts.

At both grid cache-hit sites, levels/chain cache hits and cold response assembly,
copy the cached result before attaching current observed_at and recomputed age.
Never mutate shared cached payloads in place. Source timestamps do not advance
when responses are served. HTTP/client-cached response bodies retain their recorded
observed_at; consumers must not imply continuous freshness from a static response.
Existing cache policy is unchanged; cache drain/version compatibility is an explicit
rollout limitation rather than a promise of universal live-clock accuracy.

## Design: visible consumer

Solyra useGammaGrid.ts and useGammaLevels.ts consume the additive nullable object.
Existing unavailable, loading and error states take precedence: an empty or failed
result is never described as a stored snapshot. The stored/unverified label applies
only to actual present snapshot data.
SwingMode.tsx SourcePill and source-derived exposure wording render
"Stored options snapshot — freshness and completeness unverified" with the actual
full Eastern date/time (including zone) when available, described as the recorded
snapshot time. Its age is time since that stored clock, not a measured provider
market-data delay. Provider as-of and actual feed latency remain unknown without
independent original-source evidence. Missing/invalid provenance
renders unavailable timestamp and unverified status. A REALTIME origin alone must
not trigger LIVE wording, a live pulse, "5-min snapshot" or live dealer exposure.
An older server or old cached body with actual snapshot data but lacking the
additive object gets the same neutral unverified label; retain a valid existing
snapshot_ts for explicitly unverified display. Absent data remains unavailable.
Never invent a current timestamp, zero age or positive freshness status.
Client cache storage preserves source time. If showing age, identify its observed_at
or calculate elapsed display age from the same immutable source timestamp; never
claim an additional provider refresh. Test future and invalid timestamps explicitly.

## Ownership and implementation boundaries

API owner coordinates the wire contract with #1528; DATA #1489 keeps qualified
publication ownership, COMMON #1478 keeps operation metadata ownership. Do not
copy private implementations or imports whose actual published interface is absent.
The existing source-journal A6 evaluator remains the sole current-source evaluator.

Stocks paths: platform/api/routers/grid.py response/cache assembly outside A4;
platform/api/routers/options.py levels and chain cache assembly; actual response
models in platform/api/schemas.py or their existing owning module; generated
OpenAPI only through the existing renderer. Verify concrete model locations when
writing the ready plan. Solyra paths: src/hooks/useGammaGrid.ts,
src/hooks/useGammaLevels.ts, src/components/options/SwingMode.tsx and hermetic tests.
Cross-repository work requires separate ready plans/branches and draft PRs under
FEAT-OPTION-001. One writer per change; no private-owner branch pushes.

## Verification and risks

Each behavioral done_when item requires failing fixtures on the baseline before
implementation and passing fixtures on the eventual implementation. In particular:

- Prior-session REALTIME, current-looking rows, calls-only chains, missing Greeks
  and missing siblings all remain unknown; recency does not prove completeness.
- Direct and ASGI live/dated grid and levels responses expose real source clocks;
  both outer/postflight grid caches and the levels 12-hour cache are exercised.
- Missing/naive/mixed/future clocks refuse invented ages; equal aware instants agree.
- ASGI schema serialization preserves nullable fields and known numeric zero;
  numerical arrays/levels and route/source selection match baseline fixtures.
- Hermetic Playwright exercises the actual options screen with intercepted fixture
  API responses, including old payloads with/without data, prior-session REALTIME,
  null/invalid timestamps, unavailable/loading/error states and warm client caches.
  Record screenshots under test-results with state descriptions, proving hook and
  Toolbar wiring cannot retain origin-only LIVE labels or pulse. Component tests
  additionally cover midnight Eastern and DST date/zone display. No provider or
  production network access is permitted in these tests.
- Concurrent cached readers cannot overwrite each other's observation timestamps.
- Hash checks against preserved A8/A10 manifests prove those components unchanged.

No new job or provider request is introduced. Incremental API velocity is zero
SQL/provider calls, bounded work over already selected rows plus one metadata
object. Measure actual response-size/latency delta during implementation; this spec
makes no unmeasured p95 claim. Production behavior and recovered data completeness
remain unverified until separately authorized deployment and persisted coverage
checks. The rejected ExecuteSql route must not be retried or bypassed.

## Delivery sequence

1. Review this draft with the existing Q/API and Solyra consumer owners. Resolve
   contract collisions without widening numerical or qualification authority.
2. Obtain written-artifact approval and authorized spec-main publication through
   normal repository rules. This draft grants no merge authority.
3. Write the unique ready implementation plans, then independent failing tests,
   minimal implementation and independent review. Keep every new PR a draft.
4. Separately obtain any rollout authorization. Verify real deployed source identity
   before asserting this repair addresses the observed production deployment.
