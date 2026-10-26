---
feat_id: FEAT-CATALYST-001
spec: docs/superpowers/specs/2026-10-24-feat-catalyst-001-event-bound-reaction-integration.md
branch: feature/feat-catalyst-001-event-bound-reactions
pr: null
status: ready
---

# Event-bound earnings integration implementation plan

Approved spec is genuinely on main via PR1593 merge d30c1e4d. Sole author owns the existing earnings worktree; no STRAT/governance file author overlap. Implementation-source trace may update only the declared FEAT-CATALYST-001/CATALYSTS-04 backend note under the existing protocol, without altering the calendar Chain or asserting frontend outcome wiring.

## Task 1 — exact production event timing
Spec: Timing, identity and source admission; advances done_when[0]. Write actual producer/resolver regression controls for same-ticker/different-date timing, selected-date ambiguity and unknown refusal; run RED, repair `fetch_calendar_timing_map`, `normalize_timing` and `populate_for_tickers`, then GREEN. Preserve documented same-event source precedence, valid native financial formulas and ticker-batched SQL.
- [ ] Execute the bounded change and its named checks above; retain actual evidence before claiming this task complete.

## Task 2 — prior-value retention and event identity
Spec: Refresh preservation and revision policy; advances done_when[0,3]. Test refused or immature inputs against qualified previous legacy fields/JSON/clocks, conflicting identities versus compatible atomic replacement. Implement explicit preservation in the actual producer/persistence handoff, never NULL/false/zero replacement or old-payload reattachment to a changed event.
- [ ] Execute the bounded change and its named checks above; retain actual evidence before claiming this task complete.

## Task 3 — shared admission and daily descriptors
Spec: Additive daily_path_v1 and source admission; advances done_when[1,2]. Selectively port the preserved clock/source/maturity helpers; keep strict-PIT behavior, adapt to genuinely merged existing canonical NYSE sessions rather than copy an algorithm or import an unmerged alias. Implement separate completed-close opposite-step and closing-gap-fill fields with explicit source basis, maturity, zero-gap state, sample completeness and censoring. Test future-prefix invariance; do not change native is_reversal_5d or its anchors/thresholds.
- [ ] Execute the bounded change and its named checks above; retain actual evidence before claiming this task complete.

## Task 4 — one additive column and dependent views
Spec: Owned production files and exact integration; advances done_when[3]. Add nullable earnings_reactions.daily_path_v1 JSONB to fresh/additive DDL; retain existing NULL rows as unqualified. Expose it through event view, add separately named lean summary, bind fiscal identity correctly, retain dependent refresh order and validate on isolated temporary PostgreSQL. No production schema application in the development tests.
- [ ] Execute the bounded change and its named checks above; retain actual evidence before claiming this task complete.

## Task 5 — atomic upcoming replacement
Spec: Refresh preservation; advances done_when[3,4]. Extend existing last_3_events JSON without a new upcoming column; perform replacement atomically and inject write failure to prove old rows survive. Do not add per-event remote reads or new tables.
- [ ] Execute the bounded change and its named checks above; retain actual evidence before claiming this task complete.

## Task 6 — actual brief/API consumers
Spec: Data contracts and definition of done; advances done_when[2,4]. Apply admission before native aggregate/classify, preserve threshold four and smaller-sample labels, expose percentages with metric-specific denominators and explicit unknowns. Test actual existing earnings routes and brief/view parity on the same admitted cohort; preserve differing legacy all-history fields explicitly rather than force them equal.
- [ ] Execute the bounded change and its named checks above; retain actual evidence before claiming this task complete.

## Task 7 — executable reproduction preservation
Spec: Executable research preservation; advances done_when[5]. Preserve the finite five original first-party scripts and exact identities; provide separately hashed injected-input adapters for the approved new-seven cohort and owner-supplied private inputs only. Never execute the unused legacy TEN-row main, acquire providers automatically, publish licensed payloads or claim all 663 historical versions integrated. Exercise synthetic controls and permitted derived artifact identities without new scoring criteria.
- [ ] Execute the bounded change and its named checks above; retain actual evidence before claiming this task complete.

## Task 8 — real qualified fixture integration
Spec: Definition of done and rollout boundary; advances done_when[0..5]. Use the already qualified four-quarter ANGO/current-vintage fixtures only: actual no-write producer -> isolated storage -> views -> real router/brief, boundary refusals and retained priors. Do not invent EPS, original PIT receipts, ANGO new path outcomes or frontend traversal. No October holdout access or production backfill; ticker-only --force is not a bounded event manifest.
- [ ] Execute the bounded change and its named checks above; retain actual evidence before claiming this task complete.

## Task 9 — source-proof and ordinary delivery gates
Spec: Backend-only trace binding and definition of done; advances done_when[6]. Update only own capability/traceability records and declared source note; run real producer/verifier at existing default bounds, affected suites, actual branch/main no-new docs audit, gate and current-head normal review/CI. Report exact failures rather than waive budgets or hold all work on an unmerged governance PR. Record capacity from actual full affected paths.
- [ ] Execute the bounded change and its named checks above; retain actual evidence before claiming this task complete.

## Task 10 — reviewed-main deployment and rollback closeout
Spec: Rollout boundary; advances done_when[6] and separately recorded release checks. After eligible normal CODE merge, the authorized release owner verifies actual deployed revisions, targeted additive migration/view refresh and API responses, current source qualification and rollback identities. Keep new nullable evidence column when rolling back application code; no unsafe broad backfill or fabricated screen proof. Mark this plan done only after the implementation PR merges, through ordinary DOC closeout.
- [ ] Execute the bounded change and its named checks above; retain actual evidence before claiming this task complete.
