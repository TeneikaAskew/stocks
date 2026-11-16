---
feat_id: FEAT-CATALYST-001
req_ids: [REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-DATA-004, REQ-MARKET-001, REQ-PLAYBOOK-001, REQ-REL-001, REQ-FRESH-001, REQ-MODEL-001, REQ-MODEL-002, REQ-CAP-003, REQ-CAP-001, REQ-CAP-002, REQ-PERF-002, REQ-REPLAY-001, REQ-REPLAY-002, REQ-VALID-001, REQ-FRESH-002, REQ-PERF-001, REQ-OBS-001, REQ-MODEL-003]
issues: [1135, 1138, 1158, 863, 1301, 1302, 1303, 1091]
site_source_notes: [CATALYSTS-04]
canvases:
  - https://claude.ai/artifact/Fg4VQHB6dFGWF9iXSJUDtg
done_when:
  - "The earnings brief and earnings API use the same versioned scoring, archetype, eligibility, observation-clock and missing-data contracts for matching snapshots"
  - "Historical earnings and conditional reads exclude future reports and unmatured outcomes, use exact declared daily-return windows, and expose metric-specific clean sample counts"
  - "BMO reactions resolve without requiring the next session, AMC reactions use the next exchange session, and partial events are revisited idempotently as forward horizons mature"
  - "A shared earnings decision snapshot includes the complete Strat context, first and latest premarket displacement, timestamped activation and typed invalidation, and missing inputs cannot produce a directional recommendation"
  - "The October 8-9 production-path replay covers ANGO, TLRY, PEP, BYRN, HELE, NG, NRIX, DAL and APLD, preserves pre-observation uncertainty and emits a reproducible movement scorecard"
  - "Static proxy-calibrated confidence and sizing claims are marked unvalidated unless production-input time-safe validation supports them, and high observed displacement remains visible regardless of historical quintile"
  - "Dry-run repair and readiness reports cover all affected earnings readers/writers, with bounded batched I/O and measured job capacity"
  - "The affected model records, FEAT-CATALYST-001 capability record and PR traceability are updated, and focused tests, docs audit and spec gate pass"
status: approved
supersedes: null
---

# Actionable earnings engine using the complete Strat contract

## Problem and intended outcome

The owner authorizes repairing the earnings engine and emphasizes accurate, consistent
coverage of the whole Strat. The success criterion is actionable understanding of
price movement, not dollar returns. The linked shared-engine prerequisite is
`2026-10-12-feat-strat-001-complete-state-contract.md`.

The capability row is: **FEAT-CATALYST-001 — Earnings / catalysts — Events, reactions,
news, filings — `earnings_*`, `lib/earnings_reactions.py`, earnings APIs**.
Issues listed above are touched; closure requires their individual evidence. No news
or filing behavior is widened merely because it shares the capability.

Original October 8-9 output and Alpha Vantage comparisons show divergent app/brief
archetypes and scores, misleading first-print gap context, strong movers hidden under
static Q1 routing, and delayed/missing reaction feedback. Intake also reproduces a
four-row/one-clean-quarter sufficiency error and a completed BMO reaction discarded
solely because the next session is unavailable.

## Approaches considered

1. Repair brief formatting and current SQL fields only: insufficient because the
   underlying clocks, windows, denominators and decision semantics still disagree.
2. **Recommended: shared versioned earnings snapshot built from the canonical Strat
   engine, with a dry-run historical replay and explicit readiness states.** Keep
   ingestion adapters and existing jobs, consolidate duplicated computations.
3. Fit a new earnings predictor to October 8-9: rejected because it would overfit two
   sessions and would not repair the deterministic inconsistencies.

## Design

### 1. Shared scoring and observation contract

`lib/earnings_reactions.py` owns playability inputs, numerical scoring, archetype,
clean-sample sufficiency and evaluation metadata. The brief and
`gcp/refresh_earnings_views.py` call it rather than substituting calendar `score`
(an upstream strategy score) or all-time materialized-view aggregates. Keep strategy
scores separately named. Use the same configured historical window, units, minimum
samples and decision timestamp for parity comparisons.

Source observations retain `(ticker, event date)` identity, while canonical report
selection follows the evidence-backed independent identity in §B below; finite
field precedence applies within supported report/source linkage.
Preserve event/report timing and contradictory-source flags; do not mix MAX values
from different upcoming dates into one event. Null/NaN/infinite values remain explicit
unavailable data, not zero, quiet movement or an empty earnings slate. Store source,
rule/config version, freshness, report/reaction sessions and reconstruction status.

The calendar's advertised horizon must match its ingestion horizon; a partial source
cannot present the API's second week as earnings-free. Before widening the fetch
window, measure source row count and unique option-enrichment symbols, retain bounded
batches and expose actual coverage/freshness. This supplies #1302's capacity evidence
rather than increasing the window without accounting for its added calls.

Retain the existing options-structure preference modes as distinct outputs. A historical
archetype is context, not a mandate to buy a particular structure before price confirmation.

### 2. Time-safe history and honest denominators

Historical windows use the event's actual publication/reaction clock, never merely
`fiscal_date_ending < today`. Statistics using a 5-day outcome are unavailable until
that horizon has matured; per-metric availability and clean count travel with the result.
When acquisition timestamps are not historically reconstructable, mark evidence
reconstructed and refuse to claim a strict contemporaneous data test.

Parameterize queries; batch per-symbol cutoffs. An exact 60-return denominator needs
61 eligible completed closes, then exactly 60 valid returns. Expose insufficient
coverage rather than shrinking the window silently. Report before/after score and
quintile changes; do not assume old cut-points remain valid after changing the divisor.

Conditional analogs enforce the same timing basis and observation clock and count
clean held/reversed/unknown observations separately. The current event cannot appear
in its own analogs. Sufficiency applies to the metric used by a decision, not to row count.

The reaction setup classifier uses drift into the current report computed from current
pre-event bars. It must not reuse the most recent historical report's drift as current
evidence. Historical archetype and event setup remain distinct concepts with shared
data semantics; consolidate duplicates, not genuinely different questions.

### 3. Reaction completion and recovery

`gcp/fetchers/compute_earnings_reactions.py` remains the canonical pure reaction math.
For BMO, resolve the report-session gap and range once that session is available;
the existence of D+1 must not gate an already observed BMO reaction. For AMC, require
the next exchange session. Unknown release timing is explicit unavailable timing.
Preserve existing sustain horizon definitions with a version; expose reaction-session
movement separately so BMO/AMC comparisons have the same clear anchor.

Track base-session readiness and 3/5/10-session maturity independently. Select recent
unresolved/incomplete event keys for refresh, not tickers that have never had any
reaction. Batch daily windows, flush bounded groups, and make retry/upsert idempotent.
Dry-run by default for historical repairs; preserve live briefing history and emit a
before/after proposal before production backfills or promotions.

### 4. Shared actionable earnings snapshot

Build one snapshot consumed by the earnings briefing, scoped versioned action-list/
details API and replay tooling. Compatible upcoming lists expose explicit live-context
readiness and the action-reader reference, as bounded in §7. It includes the full shared Strat contract: candle/color, priority
combo plus failed/compression facts, strict continuity and weighted alignment,
timeframe coverage, prior/current levels, both PMG forms, premarket/ORB state,
trigger/target/room, and typed invalidation. Unsupported portions carry reason codes;
they must not be presented as computed just because the parent snapshot exists.

Preserve first-premarket-print gap and add latest quote displacement with timestamp,
source and quote age. Separate premarket displacement, RTH opening gap and post-entry
movement. Calculate failed-gap, reclaim and continuation state from observations
available at the clock. Use exchange calendar and finite raw/adjusted-consistent inputs.

Maintain explicit state transitions: watch/await-confirmation, gap-already-crossed,
activated, held, failed, invalidated, unavailable. A directional action requires its
configured fresh/hold/bar-close condition; a mixed historical archetype does not imply
two simultaneous entries. Missing/stale quotes cannot activate anything. New reverse
evidence can change the active branch without rewriting the original premarket output.

Daily/weekly materialized tables supply historical enrichment, not an intraday
action clock. At request time, scoped action-list and detail handlers batch-load event keys
and source observations through one explicit clock, then call the shared action
producer. Quote/activation/failure state is recomputed from observed inputs; no daily
refresh or HTTP cache substitutes for an intraday update. No new scheduler is added.
Resolve a current/upcoming event from the canonical merged calendar even without a
historical reaction row: missing source inputs return the known event with explicit
unavailable action fields/reasons; only an unknown event returns 404. The same event
must advance between premarket and confirmation handler clocks without a refresh,
using only observations available at each clock.

### 5. Historical playability and live movement are separate rankings

The original fixed quintiles were calibrated with a proxy denominator and liquidity.
Do not carry their old hit-rate/sizing claims into a changed production score scale.
Expose validation state and descriptive score; revalidate production-input thresholds
only on a frozen time-safe population with actual normalizer and liquidity coverage.
If that coverage is insufficient, the correct result is unvalidated, not imputed data.

A separate live movement watchlist uses observable displacement relative to ATR,
level/ORB breaks and reversal state. Historical Q1 must not hide a large current move
such as BYRN or HELE. Liquidity eligibility and historical confidence are separate;
report which restriction applies. Do not tune thresholds to reproduce these two dates.

### 6. Replay, API and deterministic model evaluation

Decision evidence executes actual production orchestration: `BRIEF_AS_OF` in
`gcp/premarket_brief.py`, plus explicit as-of/captured-input/no-write modes added first
to `gcp/earnings_reactions_brief.py`, `gcp/refresh_earnings_views.py` and
`gcp/fetchers/compute_earnings_reactions.py` where absent. Production source selection,
clock propagation, readiness, enrichment and consumer formatting are exercised; a
standalone script calling the same helpers is insufficient under REQ-REPLAY-001/002.
A validation script may launch/compare those outputs only. Prove dry-run refuses
persistence and notifications: current BRIEF_AS_OF/--no-discord still writes SQL.
Offline and remote modes use that same production orchestration. Capture decision snapshots at 08:30, RTH open,
confirmation and subsequent meaningful movement. A clock may not read later daily
closes, future intraday highs or unmatured reaction flags.

Acceptance cases: ANGO failed strength, TLRY partial recovery, PEP trend continuation,
BYRN downside-gap reversal, HELE upside-gap fade, NG less directional movement,
NRIX original AMC schedule/next-session price path with its conflicting later AV
report date retained, DAL gap recovery, and APLD readiness/timing gaps.
October 8-9 are regression cases, not a new training set. Include an additional frozen
historical window and adverse/missing-data cases before promoting new empirical rules.

Publish a movement scorecard: observation clock, fresh versus already-crossed breaks,
confirmation time, target progression, directional hold/failure, reversal detection
delay, session range and surfaced/missed movement, with sample/coverage counts. Dollar
or options-PnL claims are outside this phase.

Audit MODEL-EARN-001/002, MODEL-WATCH-001 and MODEL-EWV-001 and deterministic dependencies
(Strat, FTFC, levels, indicators/ORB, options/gamma inputs and briefing state). Reuse
shared computations where appropriate; preserve different model questions explicitly.
Every finding has tested, reproduced, unresolved or unavailable status, rather than
claiming all deterministic models are empirically validated because unit tests pass.

The current app's existing score/archetype fields are corrected without client-breaking
renames. Add the versioned action snapshot to scoped action-list/detail responses and the
brief payload; upcoming lists carry the compatible explicit readiness/reference contract
in §7, never a stale action mislabeled current. Any response containing evolving quote/activation/failure/invalidation
state uses `Cache-Control: no-store`, including upcoming and event detail; the existing
86400-second historical-event cache must not cache live action state. Immutable
historical-only responses can retain their existing policy. Test headers and two
successive observation clocks through actual API handlers.

The affected existing site reader `platform/api/routers/catalysts.py::_db_catalyst_events`
and `/api/catalysts/events` are explicitly included for the already listed #1301–1303:
use the shared per-event finite-value/source merge, omit unavailable EPS rather than
render `est nan`, preserve event identity while deduplicating, and return truthful
requested-horizon/source-age/coverage. For every existing included source, carry
per-source count, newest data timestamp, newest write timestamp, read/status and
error through `CatalystsResponse` serialization; unavailable timestamps/counts remain
null with reasons. A failed read is not zero events. Raw age/read facts do not
substitute for the absent shared PR-0 freshness verdict. Do not imply that adding upcoming/details fields
changes the event timeline's current client rendering or manufactures missing second-week
calendar ingestion. Test the actual catalysts response for these contracts. Confirm actual frontend consumption before declaring the app displays
new action fields; any necessary solyra rendering change requires its own linked
FEAT-CATALYST-001 spec and PR, not a silently widened backend PR.

### 7. Capacity, observability and promotion

Target existing daily refresh envelope: <=500 reporters, <=20 eligible quarters each,
and <=61 completed closes each: <=40,500 compact records. At 250 bytes/source record,
~10 MB before dataframe overhead; budget 256 MB per batch and process bounded groups.
The current/upcoming compact daily refresh uses <=8 reads plus batched writes,
not one query per reporter or minute. The distinct historical reaction producer uses
its inherited full admission in §F below, not this compact-refresh read arithmetic.
At 2 seconds/read the I/O estimate is <=16 seconds plus measured CPU/write time.
Record actual wall-clock and memory for the populated production-like volume and
compare against the pre-change configured Cloud Run timeout. If completion exceeds
one quarter of that fixed timeout, redesign batching/I/O or reduce the admitted
bounded workload; do not raise the timeout to fit a slow job. Apply REQ-CAP-001/002
and REQ-PERF-002 to the existing jobs, including separately measured multi-year
reaction construction, full Strat context and additional enrichment sources. The
40,500 compact-record arithmetic alone does not cover those extra inputs.

The frozen two-day replay is <=12 symbols × 780 RTH bars plus daily history: <15,000
source rows. Alpha Vantage retrieval is optional, cached, throttled and bounded; report
entitlement/rate-limit/freshness failures separately from unavailable market data.
Interactive API work also meets REQ-PERF-001. Preserve the existing compact,
unpaginated `/api/catalysts/events` calendar contract; do not attach full action
contexts to every timeline entry. Existing upcoming fields remain compatible compact
enrichment; add explicit live-context readiness and a reference to the versioned action
reader rather than silently presenting a daily snapshot as current. Full live action
lists use `/api/earnings/actions` with <=10 event keys/page, deterministic event-date/
ticker/event-key ordering, continuation metadata and a bound observation clock across
page traversal. Detail admits one event. A 500-reporter fixture traverses all 50 pages;
test >500 events across pages and preserve all identities, without requiring existing
calendar clients to discover pagination unexpectedly. Existing upcoming responses for
<=500 events are <=2 MiB; above the admitted bound return explicit capacity/narrowing
information, never silently truncate or claim no earnings. Current-event details and
scoped action-list responses call the same producer as the brief.

Each live action request uses at most two batched SQL source reads: canonical event/
historical/calibration/enrichment selection (<=20 eligible quarters/event), and tagged
indexed slices from `market_data_daily` and `market_data_intraday` (<=600 daily and
<=1920 one-minute observations/event, two extended sessions, filtered by the clock).
Budget <=25,500 compact records for ten events including metadata, <=8 MiB actual
source data and <=64 MiB request working set. Project only admitted source columns,
stream bounded SQL chunks and enforce row/byte limits before materializing the full
result; rejecting an already oversized dataframe does not prove the memory bound. No per-key network or request-time vendor
HTTP calls. Existing indexes support bounded key/time slices; insufficient history,
source budget overflow or missing period-open coverage remains explicit unavailable,
not truncated-as-complete. This interactive source envelope is separate from the
unchanged 400-daily-row historical replay envelope. Source age does not manufacture
a shared PR-0 freshness verdict.

Target final UTF-8 JSON <=256 KiB/action page, <=128 KiB/detail, and <=2 MiB for the
admitted compact upcoming/cached-catalysts list. Target p95 <=2 s end-to-end at four
concurrent warm requests, including pool checkout, SQL/driver, transfer, shared
computation and JSON. Prospective decomposition: 100 ms pool + two 300 ms SQL reads +
250 ms transfer/decode +700 ms compute +100 ms JSON +250 ms reserve. These are design
bounds, not measured proof; benchmark actual full admitted inputs and driver behavior,
including unavailable-source cases separately. Fast error/unavailable responses cannot
satisfy the successful full-context latency check. If the admitted shape misses,
redesign/reduce the explicit live-page bound before rollout and repeat acceptance;
do not infer compliance from the job's 2 s/read worst-case allowance. Enforce a request
deadline with truthful error/unavailable status; never return stale actionable output.

Cached compact catalysts reads have a separate measurement from existing forced-
refresh/cache-miss vendor work: preserve truthful in-flight/pending/error source status
with a <=45 s forced-refresh/cold-response deadline and <=3 s per external
request, counting retries within the total deadline. Stop launching additional source
calls on exhaustion; return truthful partial/pending/error coverage, not complete
calendar status. The normal cached/live-action request deadline is <=2 s. No claim
that SQL-only timing certifies an external Benzinga refresh. Record actual response bytes, per-source rows/reads, memory,
end-to-end p95 and driver/cache/concurrency assumptions. Production monitoring and
availability remain separate rollout evidence, not implied by local warm tests.

No new scheduler is introduced. Measure changed runtime and calculate incremental
Cloud Run cost before deployment; no automatic multi-year backfill runs in production.

Emit counts of missing timing, stale quotes, unmatched event keys, partial horizons,
missing metric samples and producer/consumer mismatches. Reads never silently convert
an internal failure into no earnings or quiet price action. Changed job entrypoints
emit run identity, input/output/domain counts, source watermark, duration, error class,
retry state and terminal status. Source/read, computation or persistence failures
terminate nonzero; unavailable ticker resolution is an error. A successful authoritative
empty selection or not-yet-mature cohort has a distinct no-work/pending status, not a
false failure. Dry-run suppresses writes/notifications, not errors. Exercise the real
process/main boundary; logging an error while exiting successfully is insufficient.
Failed source selection, computation, short writes or persistence must preserve the
last committed visible snapshot and must not advance freshness/success state. Publish
validated replacements atomically or through staged generation activation, with
failure after selection and before commit plus retry tests. A DELETE followed by an
independent upsert transaction is not an atomic replacement.

## Executable acceptance mapping and inherited dependencies

The implementation must add/extend these named checks against production functions,
queries and handlers. Future named tests are requirements, not already passing evidence.
Keep each done_when criterion above; a generic focused-suite pass cannot replace its
sensitive check.

| done_when (1-based) | Required command/check | Broken behavior the check must reject |
|---|---|---|
| 1 | Add `tests/gcp/test_earnings_snapshot_parity.py`; run with `tests/api/test_earnings_router.py` and `tests/api/test_catalysts_earnings_contract.py` (new) | Brief/refresh/API score or archetype diverges for identical event/clock, calendar strategy score substitutes for playability, source dates mix, or catalysts response retains est-nan/dedup/coverage defects. |
| 2 | Add `tests/lib/test_lib_earnings_reactions.py::TestHistoricalClockAndSamples`; run it plus reaction-brief history query tests | Current/later report or immature horizon leaks, fiscal end substitutes for publication, 60 requested returns uses 64, or one clean sample passes a four-clean-observation gate. Use seeded real-SQL checks for query behavior. |
| 3 | Add `tests/gcp/test_compute_earnings_reactions.py::TestReactionReadinessContract`; run the production reaction suite | Completed BMO requires D+1, AMC maps to a weekend/holiday, unknown timing becomes AMC, or an existing ticker prevents incomplete-event recovery/idempotent rerun. |
| 4 | Add `tests/lib/test_lib_earnings_reactions.py::TestEarningsActionSnapshot`; run it with premarket/Strat integration and `tests/api/test_earnings_router.py::TestLiveEventActionClocks` (new) | First-print/latest/opening gaps conflate, missing/stale source evidence activates, type/continuity/PMG facts drop, same-minute order is invented, touch passes close confirmation, no-store is absent, a known current/upcoming event without reaction history returns 404, or successive premarket/confirmation action-list/detail handler calls retain daily/weekly action state. Seed the event, call actual scoped action-list/detail handlers and the compatible upcoming readiness/reference fields at both clocks without a refresh, and assert identity/state progression/no future observations. |
| 5 | Add `tests/gcp/test_earnings_production_replay.py`; execute the production entrypoints above on the nine captured regression names and bounded October batches | Selection/orchestration differs from live, later bars/reactions enter earlier decisions, report-timing conflicts are hidden, original outputs are overwritten, or dry-run persists/posts. Check in `docs/research/earnings-engine-october-2026-replay.json`. |
| 6 | Add `tests/gcp/test_earnings_validation_contract.py`; run with movement-watchlist tests | Proxy calibration becomes validated sizing/hit-rate advice, missing validation coverage is imputed, or historical Q1 suppresses an observed BYRN/HELE movement without a visible reason. |
| 7 | Add `tests/gcp/test_earnings_capacity.py::test_changed_jobs_fit_retained_quarter_timeout_with_full_io` and `tests/gcp/test_compute_earnings_reactions.py::TestReactionReadinessContract::test_incomplete_event_recovery_is_bounded_idempotent_and_dry_run`; run them with API SQL integration on the admitted500-reporter/20-quarter/61-close fixture and measured extra context; add `tests/api/test_earnings_router.py::TestInteractiveActionBudget`, `tests/api/test_catalysts_earnings_contract.py::test_interactive_delivery_budget`, and `tests/gcp/test_earnings_job_exit_contract.py` | Per-event remote loops, unbounded accumulation, premature reaction skipping, writes in dry-run, timeout inflation, false readiness, driver/schema mismatch, oversized/slow API responses, hidden >500-row truncation/page loss, or failure logging with a success exit. Measure actual handler UTF-8 bytes/p95 under explicit driver assumptions, test all 50 action pages for 500 events plus >500 stable cursor/clock traversal and unchanged compact calendar consumption, and assert nonzero read/compute/write errors with terminal telemetry plus truthful successful empty/pending states. Inject partial/short writes and before-commit failure; assert rollback/staged publication preserves last-good rows and watermark, then idempotent complete retry. Prove row/byte refusal before oversized materialization and both cached2s/forced45s deadline paths. |
| 8 | Run focused suites, branch/main docs audits, registry export and `python scripts/gate/spec_gate.py --pr origin/main`; verify criterion-by-criterion linked evidence | Missing provenance/model/capability records, untested behavior above or an unresolved delivery gate. |

#863 is related audit context, not a promised closure or permission for a new
earnings-only stopped-writer/read-side freshness implementation. Its whole-class
remediation/validation depends on the actual shared PR-0 primitive under
REQ-FRESH-002 and the roadmap; no such shared implementation is presently established.
Consume the actual shared freshness verdict when available, otherwise propagate
`dependency_unavailable` for that claim. Controlled captured-input fixtures can test
state mechanics, but must not certify production freshness or model promotion from
an invented healthy value. Record this dependency explicitly; do not import an
unmerged proposal or silently fall back to a separate generic health check.

Under REQ-VALID-001, captured October inputs remain immutable regression evidence;
repair actual upstream input-semantics/replay blockers and regenerate affected derived
data before claiming an admissible system/model baseline, validation or promotion.
Current-vintage reconstructed/code-correctness diagnostics remain labeled as such.
The October1–9 baseline and October10–16 holdout are processed in bounded batches;
no holdout outcome scoring precedes the repaired revision/settings freeze. Historical
publication-vintage absence cannot be repaired by retrieving the vendor again today.

## Canonical prerequisites, identities and sensitive acceptance

These checks are mandatory additions to the matrix, not evidence they already pass.
All approved thresholds, sustain definitions and two structure-preference policies
remain unchanged. Safe coherent-input math and isolated contract tests can proceed;
actual production integration waits for genuine merged dependencies and is not
certified by mocks, an enabled flag, a registry row or this specification.

### A. Price basis and shared calendar

Adopt approved `2026-10-12-feat-data-001-av-market-data.md` and its actual merged
`lib.price_basis.prepare_daily_basis`/`restore_daily_units`, basis version
av-adjusted-daily-v1. Continuous daily returns, normalizer, ATR and Strat use coherent
all-OHLC split-and-dividend adjustment; share/volume factors remain independently
split-only. Restore every price-dimensional level/ATR/target into the target raw
execution basis before comparing with verified raw minute quotes. First-print,
latest and RTH gap/displacement references and quotes must ALL be in the same known
target share/execution units, including each numerator and denominator. A pre-split
raw prior close cannot be compared directly with a post-split raw quote merely
because both are labeled raw; use the approved clock-qualified mapping or return
gap/action unavailable. Raw gap categories remain separately labeled; carry dividend/ex-date context
without claiming a raw price move is a total return. Never mix raw OHL/adjusted Close
or adjusted minutes/raw quotes. Missing/future factors, unknown minute basis or
unverifiable vintage means unavailable/explicit current-revision diagnostics, not
factor1 or a retrospective strict-as-of claim. No independent adjustment formula or
unmerged helper is introduced here.

The actual merged shared-calendar implementation under approved
`2026-10-19-feat-data-001-shared-market-calendar.md` is a production dependency.
Migrate earnings-owned consumers to its session_schedule/session helpers and run
its guard/pin/parity checks; timezone conversion alone does not establish sessions.
Provider/import/schedule/empty-cache failures remain errors/unavailable. Include
future-year holidays, DST, half-days and delayed opens through actual earnings
consumers, not only one weekend fixture. Do not copy draft PR1546/1489 code.

Required checks: `TestEarningsActionSnapshot::test_split_dividend_basis_and_raw_execution_units`
uses the real merged helper on split/reverse-split/dividend/no-action controls,
missing/future factors and mixed minute inputs, through actual brief/detail adapters, including a split-boundary prior-close/quote
control with no phantom actionable gap and a dividend-only raw ex-date displacement
that remains observable separately from adjusted total-return analytics;
`TestReactionReadinessContract::test_shared_calendar_consumer_parity_and_failure`
runs with `tests/lib/test_market_sessions.py` and the shared guard/pin/consumer tests.
Absence is a blocked integration dependency, not successful positive acceptance.

### B. Canonical report identity, finite merge and lineage

A disputed scheduled/reported date is an observation, not the complete report
identity. Link canonical reports using actual issuer/fiscal-period/report-kind or
source release identity evidence, preserving each source's date/timing/known-at and
identity. Supported cross-source matches produce one canonical report with explicit
conflicts and date aliases; genuinely different reports remain distinct. Without
link evidence, keep identity_unresolved observations nonactionable; never merge by
ticker/date proximity or force NRIX into a confirmed October9 reaction. Retain the
existing per-date source identity as observation lineage rather than fabricate
fiscal/release IDs or two independent directional recommendations.

Every new reaction/aggregate/action output carries exact source/as-of, pipeline,
configuration, rule/model, basis, input-artifact and code identities through actual
writes/views/readers. Immutable lineage references must resolve to real full input
content; no metadata-only fake hash. Preserve DATA UUID and CAT SHA256 namespaces
from their approved contracts. Legacy/mixed retry rows stay unverified, never stamped
repaired by a new reader. Finite source merge preserves legitimate zero EPS,
displacement and counts, while null/NaN/infinities remain unavailable; positive
price/factor domain constraints remain separate.

Required checks: `tests/api/test_catalysts_earnings_contract.py::test_conflicting_report_dates_share_supported_identity_or_refuse_action`
uses supported shared-period evidence, unresolved NRIX-like observations and truly
distinct reports; shared/serialized `test_source_merge_preserves_zero_and_rejects_nonfinite_values`
covers zero/negative-zero/finite/null/NaN/both infinities and precedence conflicts;
`tests/gcp/test_earnings_snapshot_parity.py::test_persisted_and_served_lineage_distinguishes_revisions_and_retries`
executes real writer/read boundaries on partial retries and mixed legacy/current
identities, including actual input-artifact retrieval.

### C. Required capabilities, history and maturity

Declare the required-input capability for each actionable output; no catch-all
optional field can bypass a required quote/level/Strat/continuity/unit/freshness input.
Missing required evidence clears EVERY current directional recommendation field,
actionable side, entry and CALL/PUT suggestion, including watch/await-confirmation
states and rendered brief/API text. Preventing activation alone is insufficient.
Descriptive candle direction, historical archetype and historical structure preference
remain explicitly context, not a current recommendation. Unrelated optional gamma
absence does not fabricate or erase an otherwise supported structural observation.
Preserve positive qualified controls so always-null/unavailable implementations fail.

Conditional analogs exclude the canonical current report and all its date/source
aliases BEFORE ranking/window limits. Assert exact eligible cohort and per-metric
clean numerator/denominator and unknown count. Held/reversed are distinct existing
questions and may overlap; do not invent mutual exclusivity. Null flags cannot become
false outcomes or inflate clean-sample sufficiency. A true zero differs from absent
history. Base,3,5,10-session readiness advances independently at each declared actual
session/source availability, while later horizons stay pending and refresh-eligible;
no D+10 gate or first-horizon completion shortcut. Preserve sustain-anchor semantics.

Required checks: `TestEarningsActionSnapshot::test_required_missing_inputs_clear_every_directional_output`
parameterizes every declared required input/state and production brief/HTTP outputs;
`TestHistoricalClockAndSamples::test_conditional_current_report_exclusion_and_clean_metric_counts`
uses seeded actual SQL with current aliases, future revisions, null/false/overlapping
outcomes, partially mature and out-of-band observations;
`TestReactionReadinessContract::test_base_3_5_10_session_transitions_and_retry_selection`
executes actual compute/write/reselect at just before/at each maturity, including
BMO/AMC, holiday, half-day, unavailable source, unknown timing and duplicate retry.

### D. Calibration and both structure modes

Calibration candidate/report generation defaults to NO live writes, including
`--options-insights`/winner side outputs and legacy `--no-apply` combinations.
Keep numerical selection formulas; only an explicit admitted promotion may mutate
live settings. Require qualified immutable source/cohort/cutoff, frozen unseen
validation, shadow evidence, exact candidate/code/config identities, explicit
promotion decision and real prior-version rollback target. CAS-check the expected
active version and publish atomically with lineage; failure preserves last-good
configuration. Current-revision/proxy diagnostics cannot promote or erase rollback
history through same-day overwrite. This repair does not automatically tune settings.

Required checks in `tests/scripts/test_calibrate_earnings.py`:
`test_default_and_no_apply_flags_write_no_live_targets`,
`test_unqualified_current_revision_or_missing_shadow_refuses_promotion`, and
`test_admitted_promotion_is_atomic_versioned_and_rollbackable` exercise actual main
and writers, default/options-insights flags, malformed/changed candidates and a
qualified positive control. A dummy allowed boolean cannot replace admission proof.
`tests/gcp/test_earnings_snapshot_parity.py::test_both_structure_preferences_survive_all_consumers`
uses a fixture whose existing long-only and income/credit outputs differ, plus
non-overpricing/SKIP controls. Assert both through producer/SQL/brief/compact upcoming/
action page/detail; historical preference cannot resurrect a missing-input action.

### E. Consistent continuation and deterministic movement proof

Action continuation binds observation clock AND actual event-cohort/source revision,
history/calibration/configuration, contributing prices and timing generations.
Serve the exact immutable generation or explicitly refuse/restart when it changes.
MAX(updated_at) and cutoff filters over mutable rows do not reconstruct deleted or
overwritten history. Use actual merged publication/revision evidence when available;
missing stable evidence remains dependency_unavailable. Any cohort manifest has
explicit bounded storage/lifetime and fits the two-read/row/byte/concurrency budget;
no unbounded held session or full-history rescan is hidden behind pagination.
`TestInteractiveActionBudget::test_concurrent_source_change_preserves_or_refuses_continuation`
changes insertion/deletion/backdate/calibration/price/timing between actual pages,
asserting coherent results or explicit restart, never silently mixed generations.

`tests/gcp/test_earnings_production_replay.py::test_movement_scorecard_schema_case_values_and_repeatability`
asserts all nine identities and checkpoints, meaningful per-case values for break
freshness/already-crossed, confirmation time, target progression, hold/failure,
reversal delay, range, surfaced/missed movement and metric-specific coverage counts.
Include reconstruction/conflict/unavailable reasons and NRIX uncertainty. Reject empty
or partial artifacts, future observations, impossible delays and invented unavailable
outcomes. Run identical input hashes/code/config twice; canonical semantic output is
byte-identical and matches the checked-in artifact. Volatile run/emission identity
lives in a separately compared envelope; never normalize financial differences away.

### F. Full historical reaction admission

The500×20/61 daily refresh envelope does not cover the canonical historical reaction
job. Reuse the actual merged producer/receipt interface under approved
`2026-10-12-feat-catalyst-001-av-producer-receipts.md`: <=100 tickers×100 reports
(10,000), ten bounded <=10-ticker price batches with <=26,000 bars/16MiB each,
<=100 atomic artifact/derived groups, <=1MiB artifact plus <=1MiB derived JSON/group,
119 total network round trips and <=450s against retained1,800s timeout. Existing
420s planning decomposition is238sI/O+100s transform+30s setup+20s serialization+
32s reserve; these remain unmeasured bounds. Additional engine context must fit the
complete retained budget or reduce admission, never inflate timeouts or hide cost.

Resolve immutable event-key work with explicit pending scope/cursor/fair continuation;
100/100 admission cannot mean full-history complete. Long-history price windows that
exceed row/byte limits are split into admitted event windows or stay capacity-pending,
never silently truncated or loaded unboundedly. An all-history CLI default cannot
bypass admission and no automatic multi-year production rebuild is introduced.
`tests/gcp/test_earnings_capacity.py::test_historical_reaction_maximum_admission_and_pending_universe`
executes actual main at maximum source/artifact/serialization shape, >100 ticker/report
scope, sparse/dense multi-year windows, deadline/byte overflow, intermediate commit/
retry/fair continuation and complete selected-versus-pending reconciliation. Run
`test_reaction_maximum_batched_io_fits_admission` with actual merged receipt integration.
No per-report remote call or unbounded ticker/report accumulation is accepted. Missing
producer/basis/receipt prerequisites remain explicit; pure local math is not a
substitute for integrated maximum-shape evidence or a source-backed baseline.

## Risks and compatibility

Scores and archetypes change because the old surfaces used different inputs. Snapshot
the original values and publish a per-event before/after diff. No revised historical
output becomes an original live report. No historical calibration is silently promoted
on current liquidity or revised earnings data. Keep compatibility fields and rule
versions inspectable during API migration.

## Scope boundary

The shared Strat repair lands first under its own approved spec and PR; this PR begins
from the merged base, never stacked on an unmerged change. Signal-monitor alert quotas,
AI direction-gate policy and options execution profitability remain separately owned
controls. This spec exposes truthful actionable earnings states but does not claim to
have fixed those separate controls through earnings changes alone.
