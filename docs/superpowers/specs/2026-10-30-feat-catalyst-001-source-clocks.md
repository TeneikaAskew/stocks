---
feat_id: FEAT-CATALYST-001
req_ids: [REQ-DATA-001, REQ-DATA-004, REQ-MARKET-001, REQ-REL-001, REQ-PERF-001, REQ-FRESH-001]
issues: [1303]
canvases: []
done_when:
  - "tests/api/test_catalyst_temporal_projection.py exercises the actual catalyst router, SQL projection and response schema with provider/SQL boundaries forbidden: existing economic event_time and first-insert time, earnings provider/session label/fetched_at/inserted_at/updated_at, news publication/ingestion and SEC ingestion survive as distinct typed fields; missing, NaT, invalid and timezone-unqualified clocks remain unavailable without request-time or cross-clock substitution. Projection controls fail unchanged d4478433 and pass the implementation."
  - "tests/api/test_catalyst_temporal_projection.py proves compact per-source clock descriptors and requested/returned/verified-unknown coverage, empty bounds, unchanged grouping/counts/filtering/dedup/finite EPS and unrelated sources, and the same five DB calls with no extra provider acquisition; first-insert, DB-update and retrieval times never become provider observed_at or dataset freshness."
  - "tests/gcp/test_fetch_economic_events.py proves the actual ForexFactory normalizer converts aware instants through the canonical Eastern helper before date/time extraction and weekend filtering: October UTC12:30 and November UTC13:30 both yield08:30ET, UTC Saturday00:30 remains Friday20:30ET, naive/invalid inputs are explicitly rejected, and equivalent existing Eastern-offset input retains its event identity. Provider calls, existing timeouts, cadence, FRED horizon and persistence columns/keys remain unchanged."
  - "Shared literal temporal/payload fixtures cover legacy08:30 without known timezone, categorical postmarket without a release instant, independently recorded UTC clocks,101-event complete groups and an oversized counterexample; supported OpenAPI generation and the paired Solyra generated-contract check pass. The existing45,000-character complete-source refusal is unchanged: no trimming, limit increase, synthetic current timestamp or inferred coverage, and date-only quote and Replay withholding semantics remain intact."
  - "Normal approved-spec/unique-plan delivery, own capability traceability, matched current-MAIN no-new audit, source-bound generated-document verification and required independent/current-head reviews and checks pass before runtime source merge; authenticated deployed API/frontend acceptance and any future producer qualification are separately recorded owner closeout, never claimed by hermetic fixtures."
status: draft
supersedes: null
---

# Preserve catalyst source clocks and qualify scheduled time

## Draft decision and intent

This is a new narrow contract, not an amendment to an approved specification. Status remains draft. The owner decision requested is approval of the exact additive projection, legacy-time qualification and ForexFactory normalization below so the parent publisher can advance the ordinary specification review/MAIN path. Approval would not authorize provider calls, production SQL, deployment, a migration, a freshness SLA or a longer acquisition horizon. Implementation requires the normal approved spec on MAIN and a ready plan; this draft PR contains no runtime code.

The user's requested outcome is to fix live freshness and catalyst timing without inventing clocks or claiming that selected timeline entries exhaust a source. Source availability, event schedule, provider observation, retrieval, storage and displayed summary coverage must remain distinct. A reachable source can have unknown freshness. This contract provides honest existing metadata; it does not create missing provider history.

## Capability, requirements and lineage

The existing catalog row is FEAT-CATALYST-001, “Earnings / catalysts”, capability “Events, reactions, news, filings”, surface `/catalysts`, backend `/api/catalysts`, `/api/earnings`, data `earnings_*`, `economic_events`, `news_sentiment`, `sec_filings`, status “Production but needs remediation”. Its existing issue1303 describes missing per-source age/short-source visibility. This slice touches that issue without claiming to close it: authoritative observation history and verified provider coverage remain absent for some sources. Issue references come from the repository snapshot; no fresh hosted issue-state claim is made.

REQ-MARKET-001 and REQ-FRESH-001 motivate source/clock meaning and honest unavailable freshness; REQ-DATA-001 protects unavailable values; REQ-DATA-004 requires canonical named-zone conversion; REQ-REL-001 and REQ-PERF-001 require boundary fixtures and retained payload/resource limits. This slice advances those requirements, not complete capability remediation. No registered canvas specifically maps this CAT slice.

Immutable source: Stocks d4478433777283524377a61f142893807351b9b7; paired consumer reference Solyra8c17238065377dfb69fb21fda9107c8ea0070fd7, preserving #306. Local investigation remains intact on spike/live-source-clocks at15deb336b630e9398f0e4dd486989dad82974773. It contains48 passing existing baseline tests and8 failing proposed regression controls plus4 passing characterization/admission controls. This is evidence for a design, not implementation or production parity.

Existing approved specs remain byte-identical, including the optional finite earnings estimate contract and broader catalyst delivery/receipt contracts. This spec neither marks their outstanding work complete nor changes source selection, financial normalization, clocks or caps they already protect. No review allowance resets: parent publication must record this user's repair lineage, related frontend work and any subsequent actual review runs before requesting judgment. This draft has initiated no hosted or independent review.

## Problem and bounded evidence

At the exact source revision:

- Economic rows store event_date, event_time and inserted_at. The existing SQL/adapter omits event_time and inserted_at. The schema has no economic fetched_at, updated_at or provider observation clock. Existing upserts update only submitted fields, so inserted_at stays first insertion, not last refresh.
- Earnings rows carry earnings_time, data_source, fetched_at, inserted_at and updated_at. The event response embeds a time label in its title but omits structured label/provider/clocks. Provider retrieval is not the release instant or provider publication time.
- News has published_ts and inserted_at; SEC has filing/report dates and inserted_at. Insider clusters aggregate transactions and have no single honest ingestion instant. The Benzinga JSON save clock is naive and describes a mixed cache save; it cannot qualify all merged DB sources.
- The quote endpoint maps last_updated to GLOBAL_QUOTE's latest trading day, a date. An HTTP retrieval now does not make that date a quote observation instant.
- The current ForexFactory parser extracts date/time and checks weekends before converting an aware source instant to Eastern. Hermetic UTC-offset controls demonstrate shifted times and a wrongly dropped Friday-evening event. Naive timestamps are accepted without timezone qualification.
- Catalyst date_range echoes the requested window. It is not returned extent or verified completeness. FRED's deployed-code CLI default is30days while the research consumer requests+60days; this is a possible reach limitation, not proof of the saved response's cause. Seven selected/grouped timeline entries are not all101 underlying events.

Parent-supplied bounded READ ONLY/ROLLBACK evidence, existing DB-owner run db-query-bfqb2 at11:20:05UTC: two Oct30 economic rows have08:30 schedule with Sep30/Oct27 insertions; three AAPL Nov2/postmarket rows have provider-specific Oct29 23:00:33–40UTC fetched_at values. Exact IWM news/SEC sample windows returned zero rows. This confirms omissions for those samples only. It does not certify all101 rows, current API parity, provider completeness or a historical row's timezone provenance. No new SQL is required to establish the projection defect.

## Approaches considered

1. Stamp responses with now, infer freshness from MAX(inserted_at), or attach ET to legacy time: rejected because it fabricates observation or historical provenance.
2. Rebuild producer history and extend acquisition horizons first: useful separately, but requires new schema/provider accounting and does not justify hiding already stored fields.
3. Add compact typed projections of recorded metadata, qualify legacy schedule precision, and fix the demonstrated producer timezone boundary: selected. Preserve existing acquisition, response grouping and resource guards; leave genuinely absent history explicit.

## Scope and owned paths

Runtime implementation, only after this spec is approved on MAIN:

- platform/api/routers/catalysts.py: existing row projections/serialization, compact response metadata and requested/returned coverage. The route continues using the existing five DB queries and existing cache/provider seams.
- platform/api/schemas.py and platform/api/openapi.json: additive typed CatalystEvent/CatalystsResponse fields; regenerate OpenAPI with the supported producer command, never hand-edit generated output. LiveQuoteResponse may receive a field description explaining date-only last_updated; its field/type/value behavior does not change.
- gcp/fetchers/fetch_economic_events.py: only the actual ForexFactory timestamp validation/conversion/filter boundary, using lib/eastern_time.py's existing aware/named-zone helper. No duplicate timezone framework or canonical-helper behavior change.
- Existing/new focused API/fetcher tests and a small literal temporal/payload fixture; approved capability delivery records and trusted generated evidence through their normal machinery.

The paired Solyra owner retains the Edge adapter, source/session clock labels and selected-summary UI. This Stocks spec defines the producer wire contract and cross-repo acceptance, not ownership of frontend runtime. Coordinate the exact generated contract and complete101-row payload with that owner before implementation publication. Do not race another catalyst/calendar writer or take over their producer work.

## Additive event contract

Retain every existing field, title, source label, event identity and events_by_date/total behavior. New optional fields are emitted only when their existing input is present and valid:

| New field | Exact source/meaning | Qualification |
|---|---|---|
| event_time | economic_events.event_time | Raw HH:MM:SS wall clock; historical timezone not inferred |
| earnings_time | earnings_calendar.earnings_time | Preserve original categorical provider session label, e.g.BMO/AMC/postmarket; not an instant |
| published_at | news_sentiment.published_ts | Article publication instant; not feed retrieval/freshness |
| fetched_at | earnings_calendar.fetched_at | Recorded provider retrieval clock only |
| ingested_at | row-level economic/earnings/news/SEC inserted_at | DB first insertion, never last refresh |
| updated_at | earnings_calendar.updated_at | DB update, never provider publication/observation |
| data_source | earnings_calendar.data_source | Actual recorded provider identity, independent of the old generic display label |

No observed_at, event_at or event_time_zone is synthesized. Unknown fields stay absent/null according to the existing response-model exclude-unset policy; consumers treat either as unavailable. The new fields are optional-and-nullable in the schema for backward compatibility. Do not replace a missing clock with another clock or a current timestamp. Invalid/NaT/NaN, naive datetime, malformed scalar and nonfinite values do not become strings pretending to be qualified timestamps; the field remains unavailable with a controlled diagnostic/metadata reason. Aware instants are serialized in canonical UTC using the existing helper, preserving meaning. Scheduled date values remain dates. Valid optional financial values and current finite-EPS handling are unchanged.

For economic legacy TIME, the absence of row-level timezone/provenance remains explicit even if the present producer intends Eastern time. Correcting future producer extraction does not identify old rows or authorize a backfill. Earnings categorical labels remain distinct from exact clocks; no BMO→08:30 or postmarket→16:00 conversion.

Projection deltas add economic event_time/inserted_at; earnings earnings_time/data_source/fetched_at/inserted_at/updated_at; news published_ts/inserted_at; SEC inserted_at. Retain existing WHERE/window/ticker/type clauses and all response selection/dedup choices. In particular, this slice does not change the existing news date expression or backward48-hour window; known news-date issue1270 remains separately owned. Insider-cluster ingestion is unavailable because an aggregate has no single original row clock; do not introduce MIN/MAX as a substitute.

## Compact per-source clock descriptors

Add optional top-level timing_sources, a map keyed by known contributing existing source labels. Build it once after the response's existing filters, only for the fixed contributing source families (Benzinga, AV news, FRED/Calendar, AV earnings_calendar, AV insider, SEC EDGAR). Do not generate per-record copies, use ticker/event names as map keys, or add keys for a source that contributed no returned event. Unknown source labels receive no manufactured descriptor; the consumer retains its unavailable default.

Each source value maps temporal field names to a typed descriptor with these exact members:

- basis: provider_publication | provider_retrieval | db_first_insert | db_update | provider_schedule_label | legacy_unqualified | unavailable.
- precision: instant | local_time | session_label | unknown.
- time_zone: UTC or null. UTC describes emitted aware timestamps only; it never qualifies a legacy schedule.
- reason: string or null, using the controlled reasons schedule_timezone_not_recorded, release_instant_not_recorded, not_recorded, aggregate_clock_not_defined, cache_save_clock_not_source_observation.
- missing_reason: the fixed not_recorded_or_unqualified, describing an omitted per-row value. This is a contract description, not an assertion that every row is missing or a completeness counter.

For example, FRED/Calendar.event_time uses basis legacy_unqualified, precision local_time, time_zone null and reason schedule_timezone_not_recorded. Its ingested_at descriptor uses db_first_insert/instant/UTC, reason null. Its absent observed_at/fetched_at/updated_at descriptors use unavailable/unknown/null, reason not_recorded. Earnings earnings_time uses provider_schedule_label/session_label/null and release_instant_not_recorded; actual retrieved/inserted/updated clocks keep their own descriptors. News published_at uses provider_publication; a publication is not an observation of the whole source. Insider aggregate clocks use aggregate_clock_not_defined. Benzinga cache generation is not exposed as a merged source observation; descriptor reason cache_save_clock_not_source_observation preserves that limitation.

Descriptors provide clock meaning and explicit unknown qualification; they do not calculate age, claim currentness or encode a new SLA. Per-row data_source preserves the selected earnings row’s provider identity without changing the existing generic source label or source selection. Existing ticker/date dedup can select one of several provider rows; this metadata must not claim that the chosen fetched_at represents every provider. The future provider-history design may supply stronger observations, but this spec does not reserve or populate them by inference.

## Coverage contract

Add optional top-level coverage with required members when present:

- requested: {from:string,to:string}, exactly the existing response date_range.
- returned: {from:string|null,to:string|null}, min/max dates of actual returned groups, or null/null when none or any group date is unqualified. Do not silently exclude an unqualified group and imply complete returned extent.
- verified: null, always in this implementation.
- reason: source_coverage_not_recorded, always in this implementation.

Returned bounds describe the result, not completeness. They can include existing backward news outside the requested event range; preserve that behavior rather than falsely clipping/certifying it. Total remains the count of all returned events, not the number of date groups or selected UI highlights. Retain #306's complete grouped-source validation and separate available/unknown-freshness semantics. Do not invent an “all events through” frontier from the last stored date, job success, retrieval time, MAX(inserted_at) or selected timeline.

## ForexFactory timestamp normalization

For each actual FF timestamp, require a valid aware instant before extracting market date/time. Use the existing named America/New_York helper, then derive date/time and run the current weekday filter. Preserve original source date/time identity under equivalent offsets and both DST seasons. UTC Saturday00:30 that is Friday20:30ET remains an eligible Friday event; a true Eastern weekend remains excluded under the existing policy.

Naive or invalid inputs are refused with a controlled diagnostic identifying the reason/count, not silently assigned ET/UTC or substituted with now. Do not log secrets or arbitrary response bodies. Preserve all valid siblings, country/impact filters, titles, forecast/previous fields, existing dedup keys and FF-over-FRED selection. FRED canonical schedule lookup, provider call graph, retry/timeout behavior and all acquisition windows remain unchanged. The persisted TIME remains the legacy schema representation; this change does not add historical provenance or update existing rows outside ordinary already-authorized future runs.

## Resource admission and compatibility

Volume: same returned events and same five API SQL calls; no extra joins, per-event queries, provider fetch or row duplication. Optional per-row metadata is O(returned rows); descriptors are bounded by the six existing source families. No new background workload or stored relation.

Velocity: no cadence, polling, scheduler, retry, concurrency or refresh change. FF retains its two existing feed requests; FRED pagination and CLI30-day horizon remain unchanged. The existing request timeout configuration and deployment/runtime limits are not widened. No provider call is required for local verification.

Wall-clock/cost: incremental work is deterministic scalar clock normalization and small response metadata construction; no incremental paid API call or storage. Measure the actual before/after bounded fixture path in implementation; do not claim a live latency SLO from a mock. Existing budgets remain authoritative.

Consumer admission: retain the existing45,000-character complete-source refusal. The final candidate must measure its actual serialized101-event fixture, including the final descriptors, and a deliberately oversized control. The spike's earlier compact sketch measured30,834 characters with60-character titles,44,974 with200-character titles, and60,124 with200-character titles plus three50-character values; these are not final-schema promises. Current string/details sizes are unbounded, so no universal101-row fit claim is possible. Do not trim events or metadata, raise the limit or replace source failure with partial success. Before rollout, use already captured canonical payload evidence if legitimately available to assess admission; an absent packet remains an explicit unknown, not permission for a new provider call.

Old consumers retain all legacy fields. New consumers tolerate optional additions and absence on an old deployment. Neither endpoint/schema presence nor regenerated types establishes deployed source parity. Preserve the quote date-only contract, current playbook market-date qualification and Replay withholding for catalysts without a point-in-time publication/version contract.

## Verification and evidence

Port the spike's failing actual-function controls into owned API/fetcher suites; do not rely solely on JSON model construction or copied implementations. Test real query construction and actual routed response with network/database acquisition forbidden. Add NULL/NaT/invalid/naive/aware clock cases, categorical schedule labels, actual source identity, zero-row response and unchanged unrelated siblings. Assert UTC output and every clock's independent role. Test the producer boundary on equivalent offsets in October/November, Friday/Saturday conversion, a true Eastern weekend and valid siblings beside rejected timestamps. Existing earnings numeric and news-filter suites must remain green.

Use literal cross-repo fixtures for101 complete events, empty bounds and oversized refusal; preserve source totals and exact clock semantics. Generate API/OpenAPI and Solyra types only through supported tools with exact source pin/receipt. Run appropriate unit/types/build/API/consumer contract checks and current-MAIN documentation/gate verification. A fresh required independent review is normal delivery work owned by the parent; this drafting worker requests none.

## Explicit exclusions and separate StageC proposal

No new observation/history table, schema migration, raw response archive, provider identity backfill, complete-through watermark, economic updated_at/fetched_at invention, quote-source substitution, source entitlement change, acquisition horizon extension, new schedule, deployment, production query, source refresh or backfill is authorized by this spec. No financial formula, reaction calculation, score, actual-release status or event dedup redesign. No news UTC-date regrouping, broad calendar cleanup, Research CPI title-based merge, or premarket unknown-time filtering redesign.

StageC needs its own normal narrow spec: capture real future successful provider observations in UTC with provider identity, actual query window, outcome/partial status and source-qualified coverage, link records to those observations, preserve first insertion and keep legacy unknowns unknown. A migration cannot backdate observation from inserted_at or stamp existing rows with now. Success clocks cannot advance on failed/partial acquisition. No such implementation or migration is bundled here.

## Owner closeout and remaining decision

No live/deployed acceptance has been run for this draft. Parent-owned closeout after ordinary source review/merge must identify exact backend/producer and frontend revisions, verify the already authorized served contract and rendered schedule/clock labels, and distinguish API projection qualification from actual future producer qualification. The protected/stopped browser route remains untouched; no alternate route or retry is implied. Missing deployed evidence remains pending.

The remaining decision is written approval of this exact draft contract and scope for the normal spec review/MAIN path. It does not ask the owner to approve an unknown implementation or any operational action. Until that decision and normal spec merge, status remains draft and there is no implementation plan or runtime PR claimed.
