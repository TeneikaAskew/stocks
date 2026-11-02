---
feat_id: FEAT-CATALYST-001
spec: docs/superpowers/specs/2026-11-01-feat-catalyst-001-implied-move-invalid-guard-source-note.md
branch: fix/feat-catalyst-001-implied-move-invalid-guard
pr: 1670
status: ready
---

# recommended_structure implied_move_invalid keyword implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

Specification #1650 merged as ca043892f15ce6d0b79b369c30453c22474a2dbe. Its approved successor #1675 (main 6e34cf86) keeps done_when items 1 to 6 byte-identical, adds item 7 (CATALYSTS-04 source identity) and reads item 4 as the code/test file limit; this plan was rebound to the successor in the merge of main that brought it in. this branch starts from main 38ff519301fb25ca15eac146f1b7a9a40a33fd8b, whose `lib/earnings_reactions.py` is byte-identical to d806bfd1 (the spec's reference revision). Scope is reserved to `recommended_structure` and the new test file only (recovery ledger entry 105). Draft stocks#1608 appends after L958 of the same file and keeps its own branch, budget and lines; this plan does not touch them. No caller, premarket, deploy or gate file changes.

The keyword is an explicit invalid-state interface. It is not an upstream data repair and not a deployed fix: no caller passes it until the separately specified FEAT-PLAYBOOK-001 brief change, whose plan is cut only after this lands on main.

## Task 1: current-main controls and failing tests
Spec: § Design (entry check, guard branch) and § Risks. Advances done_when[0], done_when[1], done_when[2].
- [ ] Write `tests/lib/test_earnings_reactions_recommended_structure.py` with the three named tests; the 5x3x3x3x2 (270-row) table is captured by running the d806bfd1 bytes of the function, keyword omitted.
- [ ] Run `python -m pytest tests/lib/test_earnings_reactions_recommended_structure.py -q` on unchanged main (expect the three named tests to FAIL on the unknown keyword; the fixture threshold check passes).

## Task 2: implement the keyword
Spec: § Design. Advances done_when[0], done_when[1], done_when[2], done_when[3].
- [ ] Add keyword-only `implied_move_invalid: bool = False` to `recommended_structure`, the three docstring lines, one ValueError entry check at the top of the body, and one `'SKIP'` return immediately before the `_LO_IMPLIED_HARD_MAX` test.
- [ ] Run the new file again (expect PASS) and confirm by mutation that dropping the SKIP branch, dropping the `*`, widening SKIP to the not-over-priced branch, moving the entry check after the env read, or narrowing it to long-only each fails a test.
- [ ] Confirm `git diff origin/main` touches no line of `lib/earnings_reactions.py` outside `recommended_structure`, and that `gcp/refresh_earnings_views.py`, `gcp/premarket_brief.py` and `gcp/earnings_reactions_brief.py` are unchanged.

## Task 3: existing callers unchanged
Spec: § Risks (default-off compatibility). Advances done_when[4].
- [ ] Run the existing suites that exercise `recommended_structure` and its callers unmodified (`tests/lib/test_lib_earnings_reactions.py`, `tests/lib/test_brief_two_track_redesign.py`, `tests/lib/test_conditional_lean.py`, `tests/gcp/test_premarket_brief.py`, `tests/gcp/test_earnings_reactions_brief.py`, `tests/gcp/test_compute_earnings_reactions.py`, `tests/api/test_earnings_router.py`) on main and on the branch; counts must match.

## Task 4: publication records and gates
Spec: § Rollout and § Files and ownership. Advances done_when[5].
- [x] Prerequisite: an approved same-FEAT successor spec on main that declares the owned SITE Component ID in `site_source_notes` (#1675, merged as 6e34cf86, declares CATALYSTS-04).
- [ ] After that lands: update only the FEAT-CATALYST-001 record (Status, Last reviewed, evidence) and the traceability entry with the real PR number; add the declared SITE implementation-source note; produce and verify the sidecar; compare the docs audit to origin/main.
- [ ] Run `python3 scripts/gate/spec_gate.py --commit` before each commit and `--pr origin/main` with real PR metadata; open as draft and set `pr` in the next commit.
- [ ] Current-head required external code review and CI under the ordinary budget; Ready, merge and deploy only with the owner.

## Task 4a: source identity (CATALYSTS-04)
Spec: § Source identity and close-out. Advances done_when[6].
- [ ] Update only the (FEAT-CATALYST-001, CATALYSTS-04) row of the SITE Implementation-source notes table: prefix `source_identity_sha256=<hash from produce>; `, keep the row's earlier accurate own content, and add implementation and test prose for the keyword and its tests.
- [ ] Run `scripts/maintenance/doc_source_snapshot.py produce` from the committed HEAD, commit the sidecar, then `verify` with the fixed ceilings.
- [ ] Compare the matched main and branch `scripts/maintenance/docs_audit.py` runs (no finding that main lacks); `tests/scripts/test_doc_source_snapshot.py` and `tests/scripts/test_docs_audit.py` pass unchanged; `docs/DOC_REGISTRY.md` equals main's.

## Task 5: close
Spec: § Rollout. Post-merge only.
- [ ] Set this plan's `status: done` on a `docs/<slug>` branch after the merge.
