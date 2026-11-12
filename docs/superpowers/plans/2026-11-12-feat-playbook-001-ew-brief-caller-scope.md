---
feat_id: FEAT-PLAYBOOK-001
spec: docs/superpowers/specs/2026-11-11-feat-playbook-001-retire-ew-brief-caller-scope.md
branch: fix/feat-playbook-001-ew-brief-caller-scope
pr: null
status: ready
---

# Retire EW from the premarket brief implementation plan

> For agentic workers: use superpowers:executing-plans; this lane has one source writer.

**Goal:** Exclude retired EW sources before earnings calculations and remove their brief presentation and acquisition.
**Architecture:** Use the landed shared SQL predicate at both existing loader boundaries. Remove only EW-specific presentation and recap acquisition; keep non-EW routing, numeric helpers and compatibility shape.
**Tech Stack:** Python, pandas, SQL, pytest, existing documentation identity tooling.
**Spec:** docs/superpowers/specs/2026-11-11-feat-playbook-001-retire-ew-brief-caller-scope.md

## Global constraints

Base: 75493a4753ec4dbcfbaa8663477c3943710a2069. Preserve all thirteen finite-values successor obligations and #1687 history. No finite-value repair in this lane. No schema, shared calendar, evaluator, deployment, secret or historical-data edits. Source/test scope is gcp/premarket_brief.py and tests/gcp/test_premarket_brief.py, plus obsolete recap-stub removal only in tests/gcp/test_strat_snapshot_parity.py , tests/api/test_brief_level_break_response.py and tests/lib/strat_2026_11_06.py. Preserve newer session-level tests. Use existing two-round review cap and normal Draft publication; no production actions.

## Review focus

- NULL and unknown sources alongside supported sources must survive the SQL boundary without a Python ordering error.
- Hydrated retired rows must not win aggregates before filtering.
- Replay and Sunday callers must never acquire recap data, including empty-calendar days.
- Legacy payloads with NaN recap metrics must not resurrect presentation; this is not numeric-repair proof.
- Busy supported-source output must preserve the existing 4090-character bound and non-EW sections.

## Task 1: Query-boundary exclusion and loader compatibility
Spec: Design and done_when 1–3.
Interfaces: consume earnings_not_retired_sql('ec'); retain both existing loader signatures and dictionaries.
- [ ] Collect actual base brief/caller nodes and run baseline tests.
- [ ] Add actual-query SQLite adapter cases for both aliases, mixed maxima, NULL/unknown/near-alias and supported sources, daily/weekly/replay/unconfirmed routes. Assert removal of the predicate admits retired aliases and changes expected_move/volume 5/20000 to 9/30000.
- [ ] Run new tests on the original source and record failures.
- [ ] Filter both SQL boundaries before grouping, remove retired calendar columns and priorities, preserve tiers 2/4/6 and empty compatibility keys.
- [ ] Adapt only enumerated retired ranking fixtures; preserve non-EW assertions and exact per-kept conditional-lean calls.
- [ ] Run brief tests and commit through the real gate/hook.

## Task 2: Retire acquisition and presentation
Spec: Design and done_when 4–6.
Interfaces: actual generate_premarket_brief and _build_earnings_embed; existing mocked non-EW boundaries.
- [ ] Add weekday/Sunday/BRIEF_AS_OF pipeline tests forbidding EW acquisition/imports and external I/O; legacy-payload absence and supported golden/busy output tests.
- [ ] Record baseline failures of retirement tests and passing unchanged controls.
- [ ] Remove recap definitions/wiring, verdict/Whispers rendering and retired badges/truncation priority; preserve _valid_num and unrelated helpers byte-for-byte.
- [ ] Replace every enumerated retired test with its mapped absence test; remove only the three obsolete caller stubs.
- [ ] Run full scoped brief/caller tests and reconcile every base collected node and assertion, including new nodes since the admitted historical inventory.
- [ ] Record query counts, fixture row/byte envelope, elapsed time and peak memory; commit through gate/hook.

## Task 3: Delivery records and qualification
Spec: Files and ownership, Capacity and done_when 6–8.
Interfaces: committed source, approved PLAYBOOK-09 note and normal source identity producer/verifier.
- [ ] Update own catalog/lineage and MODEL-BRIEF pointers; amend only approved MODEL-EWV brief-consumer/recap prose while retaining evaluator/audit history.
- [ ] Regenerate supported generated inventories, preserve every unrelated SITE byte, update own PLAYBOOK-09 note and produce/verify sidecar with fixed ceilings (5 seconds, 12582912 bytes, 20000 entries).
- [ ] Run caller, shared-calendar, vendor, model, source-snapshot, docs-audit and registry/governance checks; compare actual main/head audit findings.
- [ ] Run trusted BASE/PR-mode gate; prepare first complete review with exact node dispositions and truthful evidence, leaving review/CI acceptance incomplete until observed.
- [ ] Coordinate shared records, publish Draft, bind its number, follow normal limited review and CI. No merge/deployment without release sequencing coordination.

## Resumption ledger — November 12

The prior unpublished implementation remains preserved at 9e855b68 in /workspace/ew-pd-implementation; its qualified five-file patch is historical input, not evidence for this base. No implementation review has been requested for this resumption. Preserve all earlier review history; no budget reset is claimed. The approved caller-scope successor is now on main. Current-main RSI calibration, holiday freshness, STRAT levels and all newly added tests must survive. A patch-check found only two caller-stub hunks with changed surrounding setup; remove the obsolete line only, preserving that setup. P-I specification #1686 is merged, but its implementation waits for this consumer retirement. No production action is part of this work.

## Qualification and review ledger

2026-11-12: baseline 271/scoped candidate 282 tests passed; all 54 caller nodes preserved. Eight selected base-source controls fail while all ten candidate controls pass. Existing calendar/vendor/model/source-proof/audit/timezone suites pass 1003 with one unchanged collector durability integration-only skip; no new skip/xfail. Matched audits show no new finding. First complete local implementation review at 8e5b36e3 finished09:29:01 with one P2 busy-output coverage finding; its single correction preserves nodes and adds an oversized supported-source watchlist. Cap-removal mutant fails three cases; corrected fixture passes four. No runtime correction. One review round remains for the final published head; do not spend it before plan PR-number binding and final source records. Open #1832 overlaps brief/model/shared records; coordinator owns merge sequencing and no foreign branch is modified.
