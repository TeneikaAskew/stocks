---
feat_id: FEAT-CATALYST-001
req_ids: [REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-DATA-004, REQ-MARKET-001, REQ-PLAYBOOK-001, REQ-REL-001, REQ-FRESH-001, REQ-MODEL-001, REQ-MODEL-002, REQ-CAP-003]
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

Extend existing validation/research entrypoints rather than maintaining independent
classification in a replay script. Offline captured-input mode and read-only GCP/AV
mode run the same production helpers. Capture decision snapshots at 08:30, RTH open,
confirmation and subsequent meaningful movement. A clock may not read later daily
closes, future intraday highs or unmatured reaction flags.

Acceptance cases: ANGO failed strength, TLRY partial recovery, PEP trend continuation,
BYRN downside-gap reversal, HELE upside-gap fade, NG less directional movement,
NRIX AMC next-session reversal, DAL gap recovery, and APLD readiness/timing gaps.
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
brief payload. Confirm actual frontend consumption before declaring the app displays
new action fields; any necessary solyra rendering change requires its own linked
FEAT-CATALYST-001 spec and PR, not a silently widened backend PR.

### 7. Capacity, observability and promotion

Target existing daily refresh envelope: <=500 reporters, <=20 eligible quarters each,
and <=61 completed closes each: <=40,500 compact records. At 250 bytes/source record,
~10 MB before dataframe overhead; budget 256 MB per batch and process bounded groups.
Use <=8 reads plus batched writes per daily job, not one query per reporter or minute.
At 2 seconds/read the I/O estimate is <=16 seconds plus measured CPU/write time.
Record actual wall-clock and memory for the populated production-like volume and keep
the Cloud Run timeout at least four times measured completion time.

The frozen two-day replay is <=12 symbols × 780 RTH bars plus daily history: <15,000
source rows. Alpha Vantage retrieval is optional, cached, throttled and bounded; report
entitlement/rate-limit/freshness failures separately from unavailable market data.
No new scheduler is introduced. Measure changed runtime and calculate incremental
Cloud Run cost before deployment; no automatic multi-year backfill runs in production.

Emit counts of missing timing, stale quotes, unmatched event keys, partial horizons,
missing metric samples and producer/consumer mismatches. Reads never silently convert
an internal failure into no earnings or quiet price action.

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
