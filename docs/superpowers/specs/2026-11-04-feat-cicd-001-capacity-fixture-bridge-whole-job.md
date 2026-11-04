---
feat_id: FEAT-CICD-001
req_ids: [REQ-CAP-001, REQ-CAP-003, REQ-GOV-001, REQ-GOV-003]
issues: [1707, 1708]
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "tests/scripts/test_spec_gate.py preserves every baseline/current-main test name, case, meaningful assertion and numeric/blank/deferral/rendered-HTML/fence/n-a/workload verdict; eight existing capacity functions receive only explicit same-value Cost plus historical30 carriers/fixed diagnostics, and the narrow module-scope oracle/fixture guard/new equivalence regression execute every authoritative BASE case and reject dropped, duplicated, reordered or quantity-changed cases and mismatched Cost/30 BEFORE gate dispatch, without reading expected labels/verdicts from HEAD or adding duplicate gate calls."
  - "The actual unchanged BASE gate and the proposed test suite pass the complete mandatory BASE suite and complete affected suites; the complete unchanged hosted registry-check / registry job on the PR's exact head passes every test and the unchanged exporter within its unchanged six-minute (360 second) timeout, with all required actual hook/CLI assertions preserved; every hosted attempt on that head is recorded with its exact head, pytest and whole-job times against main's measured spread (twelve successful hosted registry jobs of the unchanged suite on docs/ branches, 2026-11-03 and 2026-11-04: whole job 235 to 350 seconds, median 309.5; pytest 294.68, 306.46 and 328.62 seconds on the three runs read in full), no retry selects a favourable sample, a timeout on that head blocks completion until #1707 or the ten-minute envelope stage lands, and the earlier 285 second target is recorded as UNMET, not certified; the PR's added tests take at most 15 seconds in total in one local `python3 -m pytest tests/scripts/test_spec_gate.py --durations=0` run on the exact head, recorded with its machine; real Git/fullSHA PR-mode controls show bridge fixtures preserve existing success/refusal behavior, with source gate/template/pins/workflows/hooks bytes unchanged."
  - "tests/scripts/test_spec_gate.py::test_capacity_bridge_case_and_carrier_equivalence proves the executable independently captured BASE case oracle covers every original positive/rejection/missing-label case, compares actual paired carrier text/quantities and baseline verdict/failure class, and fails before real gate subprocess on Cost999 versus legacy0.01/300, both-carriers-changed, missing/duplicate carrier and dropped or replaced negative-case mutations; all original gate cases execute once through the existing real CLI, unchanged gate/template/pins and the timing acceptance of the item above."
  - "python3 scripts/maintenance/doc_source_snapshot.py verify passes identity-matched on the PR head for the approved-spec-bound own SHARED-01 source note and committed eligible sidecar, using the actually merged source-review verifier; all other SITE bytes, historical markers, other capability records and policy/runtime predicates stay unchanged; the matched current-main-versus-branch docs_audit.py run, which reads solyra's issues, is tracked in #1708 and does not gate this PR; that issue names this PR, the solyra issue read access it needs from the owner, and the run once access exists."
  - "Four independent frozen-head gate-review seats execute concrete shell/YAML/exporter-policy/byte controls and report no unresolved load-bearing finding before the single reviewed push; normal current-head authenticated CODE review, required green CI, resolved conversations and this branch's own ready plan/catalog/traceability/PR evidence complete this fixture-only delivery."
status: approved
supersedes: docs/superpowers/specs/2026-10-13-feat-cicd-001-capacity-fixture-bridge.md
---

# Capacity fixture bridge: whole-job timing and a tracked docs audit

## Authority

Proposed on 2026-11-04 by the FEAT-CICD-001 delivery lane. The owner delegated delivery decisions on 2026-11-04 ("Do what you think would best benefit the project") and asked for the lanes to be driven to done; the coordinating session chose this successor route for the 285 second clause and the docs audit. This file is not self-approved: it takes effect only when the owner authorizes the merge of the PR that adds it, and that merge is the approval its `status` records. It is not a finding waiver, a review substitute or a rollout.

## Problem

`docs/superpowers/specs/2026-10-13-feat-cicd-001-capacity-fixture-bridge.md` requires the suite to fit "the existing285second registry ceiling". That target cannot be met by any head today, because the unchanged suite on main already misses it. Read in full, three hosted registry runs of main's unchanged suite on 2026-11-04 took 294.68 s, 306.46 s and 328.62 s of pytest. Across twelve successful hosted registry jobs of the unchanged suite on docs/ branches on 2026-11-03 and 2026-11-04, the whole job took 235 to 350 s (median 309.5 s) under the workflow's unchanged six-minute timeout. On #1706's head 358adad8 the hosted registry job ran 179 tests with pytest at 306.18 s and a whole job of 326 s (job 126892975278), every hosted check passing. The bridge's one new test takes about 6 s locally.

The predecessor also requires a matched `docs_audit.py` run. That script reads solyra's issues, and the sessions that push to this repository have no solyra access: the audit returned 403, and adding solyra to the delivery session was refused. The obligation cannot be met by the PR's author until the owner grants that access.

`2026-11-04-feat-cicd-001-inventory-whole-job.md` (#1702, open) replaces the same 285 s clause for the complete-inventory capability with a 335 s whole-job ceiling. That bound would fail main's own unchanged suite on its slowest measured job (350 s), so this spec does not copy it.

## Non-goals

- No change to any workflow, timeout, pinned file, gate, template, hook, test, assertion or runtime safety threshold. The registry job keeps `timeout-minutes: 6`.
- No speed claim, and no rerun to find a favourable sample. Making the suite faster is #1707, under the predecessor's own remedy (a separately reviewed, behaviour-equivalent bounded fixture improvement).
- The docs audit is not waived. It moves to #1708 and runs once solyra access exists; any new finding gets its own FEAT-CICD-001 fix.
- No change to any other capability's acceptance or to the 2026-11-02 ten-minute envelope specs.

## Approaches considered

1. Make the suite fit 285 s first (#1707). Main's suite alone runs 10 to 44 s over on pytest, so this is a separate piece of work, and the predecessor already routes it there.
2. A fixed whole-job ceiling like #1702's 335 s. Main's own unchanged suite reached 350 s, so the bound would fail on runner variance alone, not on anything this change does.
3. Chosen: the hosted job must pass within the unchanged six-minute timeout, which CI already enforces; every attempt is recorded against main's measured spread; and the change's own cost is bounded directly by its added tests' measured duration. This judges the change on its own delta, which is the part it controls.

## Design

The done_when list is the predecessor's list, item for item. Items 1 and 5 are byte-identical to the predecessor. Three items change:

- Item 2: the clause "under the existing285second registry ceiling" is replaced by the timing acceptance below. The rest of the item (real Git/full-SHA PR-mode controls, source gate/template/pins/workflows/hooks bytes unchanged) is unchanged.
- Item 3: only its last words change, from "unchanged gate/template/pins and285second budget" to "unchanged gate/template/pins and the timing acceptance of the item above".
- Item 4: the docs-audit obligation moves to #1708. What stays in the item: the committed SHARED-01 sidecar verifies identity-matched on the PR head with the merged source-review verifier, and all other SITE bytes, markers, other capability records and policy/runtime predicates stay unchanged.

The timing acceptance has four parts:
- the complete unchanged hosted `registry-check / registry` job on the exact head passes every test and the unchanged exporter within the unchanged 360 s timeout;
- every hosted attempt on that head is recorded with its head, pytest and whole-job times, against main's measured spread, and no retry selects a favourable sample; a timeout on that head blocks completion until #1707 or the ten-minute envelope stage lands;
- the added tests stay within a fixed budget: 15 s for the PR's added tests (the one new test measured about 6 s), from one local `--durations=0` run on the exact head;
- the 285 s target is recorded as UNMET, not certified.

Every other section of the predecessor ("Exact design", ownership, the BASE oracle, acceptance and delivery boundaries, risks) applies word for word, except its Wall-clock sentence, which is replaced by the timing acceptance above. The predecessor stays on main, unchanged except its status-only move to `superseded` in the same change, the gate's one permitted edit of an approved spec.

## Capacity and cost

- **Volume and velocity:** unchanged from the predecessor; one registry job per existing PR event.
- **Wall-clock:** as in Design. Main's spread is the reference, not a guarantee.
- **Cost:** $0 new GCP workload, schedule or resource; hosted runner minutes unchanged, because no limit changes.

## Risks

- **Runner variance or suite growth** could push a head past six minutes. Main's slowest measured job (350 s) plus the bridge's new test (about 6 s) and the Cost tests (about 8 to 12 s locally) is above 360 s, so once both land a slow runner can time out on any PR. That attempt fails and is recorded; completion waits for #1707 or the ten-minute stage, and the timeout is not raised here.
- **The docs audit could find something** once it runs. #1708 holds it open; a finding gets its own fix, and this spec does not claim the audit passed.

## Validation and rollout

1. This spec-only change, on branch `docs/spec-feat-cicd-001-capacity-timing`, holds this file and the predecessor's status-only change.
2. It passes `python3 scripts/gate/spec_gate.py --pr origin/main` and normal review, and merges only on owner authorization.
3. The implementing PR then re-binds its plan to this spec and updates its PR body's done_when list.
4. No production action.
