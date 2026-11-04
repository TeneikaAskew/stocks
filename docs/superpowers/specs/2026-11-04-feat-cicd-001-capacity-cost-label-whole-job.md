---
feat_id: FEAT-CICD-001
req_ids: [REQ-CAP-001, REQ-CAP-003, REQ-GOV-001, REQ-GOV-003]
issues: [1707, 1708]
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "tests/scripts/test_spec_gate.py::test_capacity_cost_label_contract invokes actual trusted-BASE/fullSHA gate CLI: numeric Cost-only workload bodies and the filled exact canonical PR template pass; absent/blank/unnumbered/deferred Cost, bare unrelated30 or historical30-only formula and valid30 beside invalid Cost refuse, with actual unchanged-main Cost-rejected/30-wrongly-accepted pre-fix RED evidence."
  - "tests/scripts/test_spec_gate.py::test_capacity_cost_rendered_budget_guards and every existing bridged/current-main capacity case preserve numeric-leading quantities/true-zero, blank-own-line, deferral, rendered HTML/comments/fences/headings, checkbox/canvas exclusions, all-fields-n-a with real reason, partial-n-a refusal, workload path/ownership and non-workload behavior without a parser alias or changed gate budget."
  - "The sole production predicate edit is CAPACITY_LABELS fourth literal30 to Cost; the actual .github/pull_request_template.md differs from main by exactly the approved fourth-field one-line oracle, is still a gated CICD process input, and all other template/gate predicates, pins, workflows, hooks, default policies and source/resource/data interfaces remain unchanged."
  - "The independently reviewed fixture-bridge specification AND its actual TEST-only CODE are MAIN before this branch opens; complete affected gate suites and the actual mandatory unchanged bridged-BASE suite pass; the complete unchanged hosted registry-check / registry job on the PR's exact head passes every test and the unchanged exporter within its unchanged six-minute (360 second) timeout, with all required actual hook/CLI assertions preserved; every hosted attempt on that head is recorded with its exact head, pytest and whole-job times against main's measured spread (twelve successful hosted registry jobs of the unchanged suite on docs/ branches, 2026-11-03 and 2026-11-04: whole job 235 to 350 seconds, median 309.5; pytest 294.68, 306.46 and 328.62 seconds on the three runs read in full), no retry selects a favourable sample, a timeout on that head blocks completion until #1707 or the ten-minute envelope stage lands, and the earlier 285 second target is recorded as UNMET, not certified; test_capacity_cost_label_contract and test_capacity_cost_rendered_budget_guards together take at most 30 seconds in total in one local `python3 -m pytest tests/scripts/test_spec_gate.py --durations=0` run on the exact head, recorded with its machine; with four independent frozen-head concrete gate-review seats empty before push and no test/HTML/n-a/numeric/review guard weakening."
  - "python3 scripts/maintenance/doc_source_snapshot.py verify passes identity-matched on the PR head using actual reviewed Gov verifier/compatible Counter CODE MAIN, this approved SHARED-01 ordinary source-note declaration and committed eligible sidecar; the matched current-main-versus-branch docs_audit.py run, which reads solyra's issues, is tracked in #1708 and does not gate this PR; that issue names this PR, the solyra issue read access it needs from the owner, and the run once access exists; own catalog/traceability/ready plan/PR records distinguish the verified Cost predicate from unchanged production rollout, and all other SITE/product/marker bytes remain protected."
  - "Normal authenticated external CODE review for the current head, required green CI, resolved conversations and exact own spec/plan/DoD evidence complete this single Cost correction PR; no bootstrap reuse, unmerged sibling import, self-approved spec mutation or deployment claim is used."
status: approved
supersedes: docs/superpowers/specs/2026-10-13-feat-cicd-001-capacity-cost-label.md
---

# Capacity Cost label: whole-job timing and a tracked docs audit

## Authority

Proposed on 2026-11-04 by the FEAT-CICD-001 delivery lane. The owner delegated delivery decisions on 2026-11-04 ("Do what you think would best benefit the project") and asked for the lanes to be driven to done; the coordinating session chose this successor route for the 285 second clause and the docs audit. This file is not self-approved: it takes effect only when the owner authorizes the merge of the PR that adds it, and that merge is the approval its `status` records. It is not a finding waiver, a review substitute or a rollout.

## Problem

`docs/superpowers/specs/2026-10-13-feat-cicd-001-capacity-cost-label.md` requires the suite to fit "the existing285second registry ceiling". That target cannot be met by any head today, because the unchanged suite on main already misses it. Read in full, three hosted registry runs of main's unchanged suite on 2026-11-04 took 294.68 s, 306.46 s and 328.62 s of pytest. Across twelve successful hosted registry jobs of the unchanged suite on docs/ branches on 2026-11-03 and 2026-11-04, the whole job took 235 to 350 s (median 309.5 s) under the workflow's unchanged six-minute timeout. The Cost correction is built and its tests pass locally; it has no hosted run yet, because it cannot open until the bridge is on main.

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

The done_when list is the predecessor's list, item for item. Items 1, 2, 3 and 6 are byte-identical to the predecessor. Two items change:

- Item 4: "pass within285seconds" is replaced by the timing acceptance below. The rest of the item (the bridge spec and its TEST-only code on main before the branch opens, four frozen-head gate-review seats empty before push, no guard weakening) is unchanged.
- Item 5: the docs-audit obligation moves to #1708. What stays: the committed SHARED-01 sidecar verifies identity-matched on the PR head with the merged Gov verifier and Counter code, the own records distinguish the verified Cost predicate from unchanged production rollout, and all other SITE/product/marker bytes stay protected.

The timing acceptance has four parts:
- the complete unchanged hosted `registry-check / registry` job on the exact head passes every test and the unchanged exporter within the unchanged 360 s timeout;
- every hosted attempt on that head is recorded with its head, pytest and whole-job times, against main's measured spread, and no retry selects a favourable sample; a timeout on that head blocks completion until #1707 or the ten-minute envelope stage lands;
- the added tests stay within a fixed budget: 30 s for test_capacity_cost_label_contract and test_capacity_cost_rendered_budget_guards together (the pair measured 9.7 s locally, collection included), from one local `--durations=0` run on the exact head;
- the 285 s target is recorded as UNMET, not certified.

Every other section of the predecessor ("Exact design", ownership, the BASE oracle, acceptance and delivery boundaries, risks) applies word for word, except its Wall-clock sentence, which is replaced by the timing acceptance above. The predecessor stays on main, unchanged except its status-only move to `superseded` in the same change, the gate's one permitted edit of an approved spec.

## Capacity and cost

- **Volume and velocity:** unchanged from the predecessor; one registry job per existing PR event.
- **Wall-clock:** as in Design. Main's spread is the reference, not a guarantee.
- **Cost:** $0 new GCP workload, schedule or resource; hosted runner minutes unchanged, because no limit changes.

## Risks

- **Runner variance or suite growth** could push a head past six minutes. Main's slowest measured job (350 s) plus the bridge's new test (about 6 s) and the Cost tests (about 8 to 12 s locally) is above 360 s, so once both land a slow runner can time out on any PR. That attempt fails and is recorded; completion waits for #1707 or the ten-minute stage, and the timeout is not raised here.
- **Open workload PRs whose body carries only the legacy `$/run × runs/day × 30:` line** (#1546, #1608, #1643, #1671 and #1681 when this was written) are refused by the base gate on their next event once the Cost correction merges. Each recovers by adding a `Cost:` line to its body; spec-gate re-runs on `edited`, so no push is needed. The implementing PR names them.
- **The docs audit could find something** once it runs. #1708 holds it open; a finding gets its own fix, and this spec does not claim the audit passed.

## Validation and rollout

1. This spec-only change, on branch `docs/spec-feat-cicd-001-capacity-timing`, holds this file and the predecessor's status-only change.
2. It passes `python3 scripts/gate/spec_gate.py --pr origin/main` and normal review, and merges only on owner authorization.
3. The implementing PR then re-binds its plan to this spec and updates its PR body's done_when list.
4. No production action.
