---
feat_id: FEAT-CATALYST-001
spec: docs/superpowers/specs/2026-11-19-feat-catalyst-001-retired-provenance-output.md
branch: fix/feat-catalyst-001-retired-provenance-recut
pr: 2116
status: ready
---

# Retired catalyst provenance Implementation Plan

> For agentic workers: use superpowers:executing-plans, retaining the existing sole author and two-round review cap.

**Goal:** Exclude positively identified retired EW provenance from both current catalyst event responses without deleting cached or historical data.
**Architecture:** One iterative, pure provenance predicate in the existing router. Apply it to acquired/cache/DB events before response counts/grouping, and before ticker fallback eligibility; qualify fallback results too. Keep SQL exclusions, acquisition control flow and unknown sources intact.
**Tech Stack:** Python, FastAPI TestClient, pytest, SQLite synthetic selection fixture.
**Spec:** docs/superpowers/specs/2026-11-19-feat-catalyst-001-retired-provenance-output.md
**Binding:** Actual main e678601acc2e52d0cede19578eb141eb52ef9446, approved #2101. This plan is committed before runtime edits. No runtime remediation or deployment is claimed by plan admission.

## Global constraints
- Runtime scope: platform/api/routers/catalysts.py only. New tests: tests/api/test_catalyst_retired_provenance.py; only the named negative control in tests/api/test_catalyst_source_labels.py may otherwise change.
- Retired exact trimmed tokens: earnings_whispers, EarningsWhispers, Earnings Whispers. Retain Earnings_Whispers, unknown/missing/null/numeric provenance and arbitrary prose mentions.
- Recognize source/data_source/provider/sources/provenance and descriptor name inside provenance containers; parse complete earnings_calendar (...) wrappers, not substring matches.
- Exclude mixed-origin events whole. Retain independent same-ticker/date siblings. Do not rewrite labels, caches, database rows or archives.
- Fixed source proof ceilings: 5 seconds, 16777216 combined bytes, 20000 entries. Renderer 60 seconds/512 MiB; no raised limits.
- No real provider, database, subprocess job, production operation, new issue or deployment. Real Solyra/API readback remains a separate release milestone.

## Review focus
- Deep nested provenance must not exhaust recursion: task 1 nested iterative control.
- Retired-only ticker cache must permit exactly the existing one fallback: task 2 call-count control.
- Mixed labels must not contaminate an independent sibling or wash provenance: task 1 exact-response controls.
- Declining or timing-out flight must not acquire a second vendor batch: task 2 flight controls.
- SQL mutation must remain discriminating despite final rejection: task 3 independent selection/HTTP assertions.

## Task 1: response provenance predicate and HTTP controls
Spec: Alternatives and selected design; done_when[0,1,4].
Files: create tests/api/test_catalyst_retired_provenance.py; modify platform/api/routers/catalysts.py.
Interface: `_has_retired_provenance(event: dict) -> bool`, pure and nonmutating; iterative traversal of recognized provenance fields only.
- [ ] Inspect existing test harness, establish fail-on-call guards for requests, database engines and subprocess execution; use fixed Eastern date, temporary cache and mocked acquisition/DB records only.
- [ ] Add parameterized `test_retired_provenance_absent_from_http` for both endpoints and every exact alias, wrapper, mixed token list and nested descriptor. Assert no event, count or group contains the excluded record; reproduce failure on recorded main.
- [ ] Add `test_supported_and_unknown_provenance_preserved` with AV/UW/Yahoo/Benzinga, null/missing/numeric/unknown, Earnings_Whispers, malformed wrappers and title-only mentions. Assert exact surviving event dictionaries and independent same-ticker/date sibling.
- [ ] Add `test_deep_provenance_is_iterative_and_nonmutating`; cover nested lists/dicts and unrelated payload strings.
- [ ] Implement the predicate and apply it to the merged general feed before grouping/counting; use qualified DB events for the DB contribution count.
- [ ] Run `python3 -m pytest -q tests/api/test_catalyst_retired_provenance.py`; retain red and green receipts.

## Task 2: acquisition, cache and fallback boundaries
Spec: Alternatives and selected design; done_when[2].
Files: same router and new regression file. Interface: preserve get_catalyst_events and get_catalysts_for_ticker signatures and response schemas.
- [ ] Add `test_acquisition_paths_qualify_provenance` for cached, fresh, no-data/cache fallback, peer-generation change, finished decliner and timed-out decliner; mock flight claim/wait deterministically and assert vendor call bounds, response source/status and no cache-byte mutation.
- [ ] Add `test_retired_only_ticker_cache_uses_one_qualified_fallback`; prove one call, supported live result survives, retired live result absent, no recursive fallback.
- [ ] Add `test_filters_sorting_counts_and_siblings` with date/type/ticker filters and unrelated event types; preserve existing filter semantics rather than repairing unrelated behavior.
- [ ] Qualify ticker cache before deciding fallback and qualify live results. Keep acquisition/single-flight state and wait limits unchanged.
- [ ] Run the new regression file plus existing flight/cache tests discovered by `rg -l 'CATALYST_FLIGHT|peer_refreshed|catalysts/events' tests`; inspect each selected harness before execution.

## Task 3: preserve discriminating SQL and existing coverage
Spec: done_when[3,4].
Files: only named test in tests/api/test_catalyst_source_labels.py plus new regression file.
- [ ] Adapt `test_main_shaped_events_query_keeps_ew` to inspect actual `_db_catalyst_events` selection through the existing SQLite fixture, before response qualification. With predicate removed retain E/R ticker, T title and mixed-source assertions; with predicate intact assert exclusion. Preserve all unrelated tests/assertions.
- [ ] Independently exercise the real HTTP endpoint with that SQL mutation and assert retired events remain absent; do not treat a prefiltered mock as selection evidence.
- [ ] Collect exact base/head nodes and reconcile additions and the sole adapted control; no retired nodes/skips.
- [ ] Run `python3 -m pytest -q tests/api/test_catalyst_retired_provenance.py tests/api/test_catalyst_source_labels.py tests/api/test_catalyst_earnings_estimate_numbers.py tests/api/test_catalysts_news_filter.py` and the discovered flight/cache tests. Record actual results, no borrowed green receipts.

## Task 4: capacity, records and final-head gates
Spec: Capacity and limits; done_when[5]; Coordinated consumer readback.
- [ ] Measure duration, peak memory and traversed nodes for 1000 synthetic events; retain payload shape and environment. No production latency claim.
- [ ] Update own FEAT-CATALYST-001 catalog/lineage and declared CATALYSTS-04 note only; preserve foreign SITE and registry bytes, generated historical blocks and all unrelated runtime files.
- [ ] Use supported renderer and bounded snapshot producer/verifier from committed source. Compare matched actual main/head offline audits with identical retained issue inputs; require no new findings.
- [ ] Run real commit hooks, PR gate and applicable trusted BASE/registry/governance checks. Publish only a fully prepared Draft; bind pr number before Ready.
- [ ] Preserve #2101 specification review ledger separately from this implementation. Schedule complete first implementation review only after final base/head and truthful acceptance preparation, within two rounds; no unapproved extra events or unchecked completion claims.
- [ ] Record main/staging and Solyra CatalystsPage/Dashboard negative/positive readback as pending post-merge release work; do not merge or deploy in this assignment.

## Preparation receipt
- [x] Approved main spec and actual main identity verified; worktree/open-PR inventory found no competing cache implementation. Unpublished external ownership cannot be proved by PR absence.
- [x] All six acceptance items map to tasks above. No runtime, test, calendar or registry change is included in this plan-only preparation.

## Re-cut lineage and admission boundary
This local successor starts directly from actual main e678601a, preserving the six landed #2103 documentation corrections. It carries only #2107's reviewed functional change; stale generated identity is not reused. #2107 remains at e9167a11b951aeba213270ae64c4db9e5c5a08fb and is not amended. Its first CODE review completed clean at 2026-11-19 17:54:57 UTC; its second CODE review completed clean at 18:24:30 UTC. SECURITY completed at 18:26:39 UTC with null findings flags, not an explicit clean verdict. Both events remain spent on #2107. No review or deployment of this new head is claimed.

The owner directed a minimal clean replacement through normal repository admission. CLAUDE's post-round-two rule requires a split/re-cut/discard for work needing a further push; this is the spec-bound re-cut route, not a third push or review on #2107. A successor's review admission must retain that ledger and be confirmed before any review event; creating this local plan does not reset historical review accounting.

Prior 47-case offline HTTP receipt applies to the exact imported functional bytes; final candidate proof, matched audits, full applicable checks and exact-head review remain outstanding. Fresh producer/verifier must bind this actual named branch and committed plan under unchanged limits. Release coordination remains separate because platform paths match automatic schema/API triggers.

## First-head review and final bookkeeping
PR #2116 first head 4511cb40a4c8bebf493828d2fa6a69927b92d9be passed all six required hosted checks. CODE completed with no findings at 2026-11-20T21:53:21.194888Z (receipt 7052003975); SECURITY explicitly reported no issues at 22:24:39.989547Z (receipt 7052539915). These receipts apply only to that head. This bookkeeping binds the actual PR and preserves both historical #2107 rounds; the final committed head still requires its own CI and review. Live API/Solyra readback, deployment and sidecar close-out remain pending.
