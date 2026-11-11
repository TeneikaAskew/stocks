---
feat_id: FEAT-SIGNAL-001
spec: docs/superpowers/specs/2026-10-31-feat-signal-001-retire-ew-reader.md
branch: fix/feat-signal-001-retire-ew-reader
pr: null
status: ready
---

# Retire EW signal readers implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Exclude retired EarningsWhispers rows at the owned read sites.
**Architecture:** Import the existing shared SQL predicate and add it inside each existing WHERE. Keep all other query and downstream behavior unchanged.
**Tech Stack:** Python, pandas, pytest, SQLite query-layer fixture.
**Spec:** docs/superpowers/specs/2026-10-31-feat-signal-001-retire-ew-reader.md

## Global Constraints

- Base: current main 3991c628ff2a614ce5f74a1aa9ca1843d1faca80; P-A/P-B and both approved specs are merged.
- Own only `lib/strategies/catalyst_proximity.py::_nearest_earnings` and `tests/lib/test_catalyst_proximity.py`; never edit the shared helper or fixture.
- No fallback, relabelling, replacement source, deployment, schema, renderer or historical audit changes.
- Use the shared fixture builders, fake only the query layer, and execute actual reader SQL.
- Preserve all foreign SITE bytes and registry blob/mode/type; keep earlier own note prose.
- Normal hooks/gates and the two-round review cap apply; no merge or production action in this implementation task.

## Review Focus

- Both retired aliases need independent removal controls.
- NULL, unknown and Earnings_Whispers remain eligible.
- EW-only tickers disappear, including historical timestamps where applicable.
- Accepted AV/UW/Yahoo serialized reader outputs remain byte-identical to main-shaped controls.
- Ordering, grouping, bounds and limits must remain unchanged, including newly merged summarizer behavior.

## Task 1: Reader predicate and adversarial tests
Spec: done_when[0], done_when[1], done_when[2] and Separation of evidence.
Files: `lib/strategies/catalyst_proximity.py::_nearest_earnings`; tests: `tests/lib/test_catalyst_proximity.py`.
Interfaces: consume lib.earnings_reactions.EARNINGS_NOT_RETIRED_SQL and tests.fixtures.earnings_calendar_sources; preserve reader signatures and outputs.
- [x] Run existing focused test files on the clean baseline (expect PASS).
- [x] Add actual-reader tests with explicit main-shaped negative controls and shared fixture rows. At 10:00 ET, AV premarket plus EW postmarket gives main (390, earnings_post, 120, earnings_pre), then predicated (None, None, 120, earnings_pre). Historical EW-only yields four None values.
- [x] Assert aliases removed, NULL/unknown/nonalias kept, EW-only absent, and byte-identical accepted-source serialized results.
- [x] Run added tests before source edits (expect FAIL on retired values).
- [x] Import shared EARNINGS_NOT_RETIRED_SQL and add it inside existing WHERE, with no other query change.
- [x] Run complete focused test files (expect PASS).
- [x] Run python3 scripts/gate/spec_gate.py --commit, then commit with normal hook.

## Task 2: Bound source identity and unchanged governance tests
Spec: done_when[3], Source identity and close-out pre-merge steps 1-4.
- [x] Read producer preflight source hash and update only approved own SITE implementation-source rows, retaining earlier own prose.
- [x] Commit final SITE body; produce and commit docs/review-evidence/site-source-snapshot.json from committed HEAD.
- [x] Verify with --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000.
- [x] Prove registry blob/mode/type equals current main and all foreign SITE bytes unchanged.
- [x] Run matched main/head docs_audit.py; require no new findings.
- [ ] Run unchanged tests/scripts/test_doc_source_snapshot.py and tests/scripts/test_docs_audit.py (expect PASS).

## Task 3: Normal Draft publication
Spec: done_when[3], Source identity and close-out pre-merge step 4.
- [ ] Coordinate current-main sequencing before publication; regenerate identity after watched source/body/policy changes.
- [ ] Update only owned capability record and PR traceability, preserving earlier prose; open one Draft PR under normal gates.
- [ ] Record PR number in this plan, actual review budget and retained findings; do not request a third round.
- [ ] Run PR-mode gate and record source tests separately from hosted current-head checks and review.

## Task 4: Post-merge owner close-out (not performed by this task)
Spec: Source identity and close-out post-merge obligations.
- [ ] Independently verify actual main source/body identity in a fresh clone after squash.
- [ ] Obtain real job/service deployment evidence named by the spec; do not infer it from source tests or sidecar.
- [ ] Retire sidecar only through ordinary trunk --stamp --verify or fixed trunk-closeout-pending protocol.
- [ ] Set this plan status to done on a separate docs branch after merge.

## Local evidence checkpoint

Source/test review: fresh local reviewer, first source review, no findings. This is not hosted current-head review. Focused reader tests passed (75). Committed identity verifier passed with the fixed ceilings; matched main/head audit has zero new findings. Unchanged governance suites are still being qualified against exact main. Initial concurrent identity verification timed out; sequential retries passed without changing the ceiling or source. No merge or production action.
