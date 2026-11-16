---
feat_id: FEAT-SIGNAL-001
spec: docs/superpowers/specs/2026-10-31-feat-signal-001-retire-ew-reader.md
branch: fix/feat-signal-001-retire-ew-reader
pr: 1801
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
- [x] Run unchanged tests/scripts/test_doc_source_snapshot.py and tests/scripts/test_docs_audit.py (expect PASS).

## Task 3: Normal Draft publication
Spec: done_when[3], Source identity and close-out pre-merge step 4.
- [x] Coordinate current-main sequencing before publication; regenerate identity after watched source/body/policy changes.
- [x] Update only owned capability record and PR traceability, preserving earlier prose; open one Draft PR under normal gates.
- [x] Record PR number in this plan, actual review budget and retained findings; do not request a third round.
- [ ] Run PR-mode gate and record source tests separately from hosted current-head checks and review.

## Task 4: Post-merge owner close-out (not performed by this task)
Spec: Source identity and close-out post-merge obligations.
- [ ] Independently verify actual main source/body identity in a fresh clone after squash.
- [ ] Obtain real job/service deployment evidence named by the spec; do not infer it from source tests or sidecar.
- [ ] Retire sidecar only through ordinary trunk --stamp --verify or fixed trunk-closeout-pending protocol.
- [ ] Set this plan status to done on a separate docs branch after merge.

## Local evidence checkpoint

Source/test review: fresh local reviewer, first source review, no findings. This is not hosted current-head review. Focused reader tests passed (75). Committed identity verifier passed with the fixed ceilings; matched main/head audit has zero new findings. Unchanged source/docs suite: 804 passed on this branch. Exact main initially returned 803 passed / 1 failed (exit 1): the slow-True timeout control asserted a nonempty reaped-grandchild list; no escaped or remaining children were reported. Its unchanged isolated rerun passed (exit 0). Original traceback retained; no governance code/tests changed. Fresh whole-candidate local review found no introduced defects. This is not hosted current-head review. Initial concurrent identity verification timed out; sequential retries passed without changing the ceiling or source. No merge or production action.

Draft PR: #1801. Before publication, the exact branch had no prior PR or review history; first hosted read after opening showed no submitted reviews. No hosted review requested; two-round cap remains intact. Main sequencing coordinated under the parent task; no merge authorized.

## Authorized required-check repair (2026-11-11)

Exact new permission retained, without resetting the three local passes:

> Assistant: “To finish these readers and the remaining fetcher spec #1685, may I allow the necessary additional current-head reviews for those three PRs, while retaining all prior review history and requiring their normal checks before merge?”
> User: “Yes and Fix the required check”

Spec: done_when[0..3], normal current-head review/checks and AGENTS.md API-response proof.
- [ ] Reproduce required-check failures, preserve baseline evidence, and repair only scoped source/test/generated evidence.
- [ ] P-G: prove actual earnings readers through watchlist and generated-report API responses; retain existing timezone debt with its new SQL fingerprint, without a timezone exemption or query semantics change.
- [ ] P-H and P-G: render affected inventories from committed source with the existing renderer; preserve foreign prose.
- [ ] Correct owned PR lineage syntax; regenerate only declared SITE notes and sidecar against coordinated main.
- [ ] Run source, timezone, generated-docs and API regressions, ordinary gates and matched audits.
- [ ] Complete repair candidate before necessary hosted current-head review; no new local judgment pass.
- [ ] Preserve all prior local/hosted reviews and findings; no merge/deploy until explicit sequencing handoff.

Temporary publication hold: both PRs had externally been made Ready and auto-merge enabled. Auto-merge was disabled and both were converted to Draft at 14:07:30 / 14:07:34 UTC, before the subsequent no-Draft-conversion instruction arrived. Do not blindly reverse status. Restore only through coordinated sequencing; #1685 precedes #1800, then #1801 final mechanical sync.
