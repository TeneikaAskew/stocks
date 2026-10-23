---
feat_id: FEAT-CATALYST-001
req_ids: [REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-DATA-004, REQ-MARKET-001, REQ-PLAYBOOK-001, REQ-REL-001, REQ-FRESH-001, REQ-MODEL-001, REQ-MODEL-002, REQ-CAP-003, REQ-CAP-001, REQ-CAP-002, REQ-PERF-002, REQ-REPLAY-001, REQ-REPLAY-002, REQ-VALID-001, REQ-FRESH-002]
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

Source selection merges finite fields deterministically by `(ticker, event date)`.
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

Build one snapshot consumed by the earnings briefing, upcoming/details API and
replay tooling. It includes the full shared Strat contract: candle/color, priority
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
renames. Add the versioned action snapshot to upcoming/details responses and the
brief payload. Any response containing evolving quote/activation/failure/invalidation
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
Use <=8 reads plus batched writes per daily job, not one query per reporter or minute.
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
No new scheduler is introduced. Measure changed runtime and calculate incremental
Cloud Run cost before deployment; no automatic multi-year backfill runs in production.

Emit counts of missing timing, stale quotes, unmatched event keys, partial horizons,
missing metric samples and producer/consumer mismatches. Reads never silently convert
an internal failure into no earnings or quiet price action.

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
| 4 | Add `tests/lib/test_lib_earnings_reactions.py::TestEarningsActionSnapshot`; run it with premarket/Strat integration and actual API header tests | First-print/latest/opening gaps conflate, missing/stale source evidence activates, type/continuity/PMG facts drop, same-minute order is invented, touch passes close confirmation, or no-store is absent on evolving actions. |
| 5 | Add `tests/gcp/test_earnings_production_replay.py`; execute the production entrypoints above on the nine captured regression names and bounded October batches | Selection/orchestration differs from live, later bars/reactions enter earlier decisions, report-timing conflicts are hidden, original outputs are overwritten, or dry-run persists/posts. Check in `docs/research/earnings-engine-october-2026-replay.json`. |
| 6 | Add `tests/gcp/test_earnings_validation_contract.py`; run with movement-watchlist tests | Proxy calibration becomes validated sizing/hit-rate advice, missing validation coverage is imputed, or historical Q1 suppresses an observed BYRN/HELE movement without a visible reason. |
| 7 | Add `tests/gcp/test_earnings_capacity.py::test_changed_jobs_fit_retained_quarter_timeout_with_full_io` and `tests/gcp/test_compute_earnings_reactions.py::TestReactionReadinessContract::test_incomplete_event_recovery_is_bounded_idempotent_and_dry_run`; run them with API SQL integration on the admitted500-reporter/20-quarter/61-close fixture and measured extra context | Per-event remote loops, unbounded accumulation, premature reaction skipping, writes in dry-run, timeout inflation, false readiness or driver/schema mismatch. |
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
