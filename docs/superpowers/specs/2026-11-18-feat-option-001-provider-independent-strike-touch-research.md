---
feat_id: FEAT-OPTION-001
req_ids: [REQ-REL-001, REQ-GOV-001]
issues: []
canvases: []
done_when:
  - "A local research input manifest records each candidate artifact hash, origin, license/permission, schema, event identity, instrument, strike, strategy/direction, decision time, availability time, price basis and coverage. It explicitly distinguishes recorded non-EW picks from listed option strikes and retrospectively generated hypothetical rules; no synthetic or retrospective choice is represented as a historical recommendation. Missing trustworthy decision/availability clocks yields ineligible or unknown, not a fabricated sample."
  - "A pre-registered protocol freezes the selection rule, universe, session horizon, inclusivity, strike-distance strata, baseline, chronological train/validation/test split, embargo and reporting metrics before any held-out outcomes are viewed. Its input eligibility excludes EW recommendations and both retired source aliases; exclusion tests fail when that eligibility predicate is removed. No old EW scorer or feed is restored."
  - "Offline synthetic tests exercise the actual proposed evaluation functions for up/down touch, exact equality, initially beyond-strike state, no touch with complete bars, incomplete bars, unknown event timing, after-close Friday, holiday, early close, both DST transitions, late-arriving records, split/basis mismatch, duplicate/revised bars and competing intrabar events. Tests prove the same outputs independent of provider labels when canonical admissible inputs are equal. A price crossing is never reported as a fill, assignment, recommendation success or profit."
  - "A bounded offline feasibility report gives eligible and excluded counts with reasons, event/ticker/date coverage and missingness by stratum, provenance limitations, touch and separate close-side results, time-to-touch intervals and censoring. It compares the frozen rule against matched simple baselines with uncertainty clustered by event/ticker and reports untouched out-of-sample results separately. If no permitted, point-in-time non-EW sample exists, report insufficient evidence and stop; no minimum sample, performance claim or live acquisition is invented."
  - "Calendar source and both runtime consumers remain byte-identical to the research base, including gcp/fetchers/evaluate_ew_strikes.py, lib/eastern_time.py, gcp/fetchers/_av_realtime_collector.py and lib/earnings_reactions.py; existing calendar and 22 vendor-answer cases remain unchanged. The report separates historical scorer repair evidence from new research and identifies the owner decision needed before any migration, general-purpose evaluator implementation, production integration or release."
  - "Any later research implementation has its own fresh plan bound to this approved-main specification, normal scope/source/document checks, required review and CI within existing limits. Report exact input hashes, code revision, commands, elapsed time and peak memory; no offline result is represented as deployed protection or financial efficacy."
status: draft
supersedes: null
---

# Preserve the calendar; evaluate provider-independent strike-touch research

## Decision and disposition of #2097

The owner paused rename/removal to understand the file. After the recommendation to preserve the calendar and separately evaluate provider-independent strike-touch usefulness, the owner replied: “Lets do this and update 2097”. This authorizes this draft update and investigation direction; it is not approval of unseen research acceptance wording, runtime changes, merge or deployment.

This replaces the four unmerged migration proposals in #2097. They remain in Git history at c5b4017f, but are no longer proposed contracts in this PR. No accepted specification is superseded or edited. Preserve the working calendar shim and its imports unchanged. A later rename/deletion needs its own explicit decision and lawful contract amendments. Do not mark the prior migration proposal approved by implication.

## Ownership and boundaries

FEAT-OPTION-001 owns options/strike analysis; its catalog capability is “Flow, Greeks, GEX grid”. This is a research-feasibility contract, not a source ingestion or recommendation feature. No new issue. Existing #2091 security work and #2095 producer attribution are separate. Recheck author ownership before any eventual research branch. No live data access, SQL, vendor/model call, archive transfer, production build/job/deployment, secret access or historical mutation is admitted here. The current PR changes specifications only.

## What the old file did versus what remains

Before #2084 the evaluator selected earnings_calendar rows specifically sourced from earnings_whispers with non-null strikes; it measured independent intraday underlying prices against those picks. Calls/bull spreads used high >= strike, puts/bear spreads low <= strike, and covered calls compared close to strike. This was a retrospective price-path measurement, not option profit or predictive skill. The retained model record documents wrong-session repairs (1,263 after-close verdicts; 328 changed), not validated investment performance. Preserve these historical measurements and labels as history, never reuse them as non-EW recommendations or held-out validation.

Main 666804f9 contains only nyse_sessions delegating to lib.eastern_time.session_schedule. The options collector and earnings_session_schedule still use it. It consumes no EW data and calculates no strikes. Its useful calendar functionality stays intact regardless of research outcome.

## Evidenced input candidates versus unverified availability

Repository inspection, not database sampling:

- gcp/schema.sql earnings_options_snapshots declares symbol, snapshot_ts/date, option type, expiration, strike, bid/ask, underlying_price, data_source and inserted_at. These are listed contracts, not proof that someone chose a trade or that a snapshot was actually available at decision time. No current row counts or completeness were queried.
- earnings_calendar strategy/strike/premium fields are explicitly EW-specific in the schema; their presence is not evidence of independent recorded picks. Event date/time/source/fetched_at are potential event metadata only; provenance and revision history still need verification.
- scripts/backtest_playability.py constructs hypothetical strikes from chains (e.g. nearest spot paired strike). Such output can support a frozen hypothetical-rule study, not a claimed historical pick. A calculation_date or historical quote timestamp alone is not a decision/availability receipt.
- Repository market-data code requests as-traded bars, but this does not prove historical stored windows have a consistent split basis or contemporaneous revisions. Require input manifests and basis checks; never join modern adjusted prices to historical raw strikes silently.

No eligible non-EW recorded-pick dataset is established by this inspection. A future study may use only separately authorized local artifacts with provenance. Synthetic fixtures suffice to validate measurement semantics, not predictive usefulness. New data acquisition/transfer needs separate authorization.

## Protocol and measurement definition

Before selecting outcomes, freeze ticker/event universe and a mechanically reproducible strike rule using only information available by the decision cutoff. Keep actual recorded picks in a distinct cohort from hypothetical rules. Record event announcement timestamp, its source and known-at time; unknown announcement timing is excluded or explicitly unknown. Resolve premarket/after-close/holiday/early-close/DST using the existing canonical schedule, without modifying calendar source. Start observation no earlier than the declared decision and event/session boundary; a partial minute that straddles the cutoff cannot prove ordering. An intraday announcement cannot use the full session's earlier extrema.

For a positive finite strike, define upward touch as eligible bar high >= strike and downward touch as low <= strike. Report already-beyond at observation start separately from a later crossing. Close-above/below is a different metric; do not label it actual option assignment. Use actual session opens/closes, not fixed clock offsets. Time-to-touch is bounded by observed bar interval; minute data cannot prove tick ordering or executable fills. Multiple events within one bar remain ambiguous. Missing bars can leave a non-touch censored/unknown, not MISS; observed touch does not establish complete exposure coverage. Use confirmed corporate-action/basis evidence or reject mismatches. Do not impute missing strikes, times, prices or outcomes.

Baseline examples to pre-register: distance-to-spot matched strikes at the same decision time, and a simple fixed-distance rule matched by direction/horizon/event strata. Include already-beyond controls so high touch rates are not mistaken for skill. Avoid fitting and reporting on the same events; split chronologically with event-group isolation/embargo for overlapping horizons, freeze parameters before held-out evaluation, disclose every tested variant and uncertainty. If only one chosen sample or too few independent events exist, label descriptive feasibility only. Coverage/selection bias and provider revisions are reported, not hidden.

## Non-goals and alternatives

Renaming the shim to earnings-strikes would misdescribe a calendar; no rename is selected here. Restoring the EW scorer would restore an EW-dependent selection path and is rejected. Generalizing its historical arithmetic without provenance would not establish usefulness. Selected approach: preserve current production behavior, validate a narrow provider-independent measurement contract with synthetic cases, and assess whether trustworthy non-EW inputs and meaningful baseline-relative evidence exist before proposing a product.

Profitability requires separate premium quotes available at entry, spreads, fills/liquidity, exercise/assignment rules, financing, fees, slippage and exit rules. Touch rate alone establishes none of these and is not a trading recommendation. No return/backtest/profit claim is an acceptance criterion here.

## Research implementation scope and bounded execution

After approval on main, a fresh plan may propose only an offline pure research module and its dedicated synthetic tests plus a report/manifest. Exact paths must be frozen in that plan within FEAT-OPTION-001 ownership; if the gate does not admit them, obtain a scope amendment rather than editing runtime readers. No hooks into existing CLI/jobs/API, no reuse of retired module entrypoints, no library/calendar changes. Before any real-artifact evaluation, record maximum rows/bytes, chronological span, wall-clock and memory budget from manifest inspection and obtain the bounded run decision; reject inputs exceeding it. This spec does not authorize an unbounded historical sweep. Existing repository renderer/verifier/test limits remain unchanged.

## Close-out and next decision

Deliver input feasibility, synthetic RED/GREEN measurement proof, separately labeled held-out evidence if available, and limitations. The owner then decides whether to abandon, gather authorized additional evidence, or approve a separate general-purpose evaluator/migration specification. No automatic publication as a signal, no calendar change and no deployment follows from a positive study. Keep all historical data and original review accounting.
