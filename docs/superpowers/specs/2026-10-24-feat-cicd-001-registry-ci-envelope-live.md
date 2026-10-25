---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-004]
issues: []
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "The registry job uses literal timeout-minutes: 6 through separately reviewed pinned-copy-first and matching-live-workflow PRs, with no other execution, permission, dependency, isolation or runtime-deadline change."
  - "Existing native pin-order and workflow-contract controls reject a live-only or simultaneous pin/live timeout change; all original tests, assertions, native invocations and required checks remain present and pass."
  - "Exact-head hosted receipts for both implementation stages show every required check passing and pytest at most 285 seconds; the activated six-minute job additionally meets every component allocation and finishes within 335 seconds with at least 25 seconds measured headroom."
  - "Observed stage timings, exporter execution mode, cost and verification limits, independent reviews, ordinary source proof and full-default main/proposed no-new audits are recorded before release; any unresolved capacity or evidence failure holds release without retry loops or a gate waiver."
status: approved
supersedes: null
---

# Registry CI envelope: matching live-workflow stage primary

## Authority and final proof preservation

This is the stage-two primary for the same owner-approved `docs/superpowers/specs/2026-10-24-feat-cicd-001-registry-ci-envelope.md` design, merged through #1586 at `ffa5f15fd69be64f897354227692b3365a7586f3`. The bounded finish authority covers the necessary staged-spec correction and conditional normal implementation merges. This delivery-only primary changes no approved behavior, budget or constraint.

Its four frontmatter DoD strings are copied verbatim from the parent. They preserve every global obligation, including both implementation-stage receipts and final hosted exporter/headroom proof. The parent remains unchanged and is not falsely certified by the pin-stage PR. The pin-stage primary binds only its own achievable first-stage obligations. No primary-spec stage filter or exception is added to the gate.

## Prerequisites and exact scope

This branch/ready plan/draft PR opens only after the separately reviewed pinned-copy stage is actually MAIN. Verify its exact source/merge receipt and retained five-minute hosted evidence. Select this primary in a new normally gated ready plan, perform initial and actual-PR-bound PLANONLY commits, then CODE. No stacking on an unmerged pin branch.

Change only `.github/workflows/registry-check.yml`'s `jobs.registry.timeout-minutes` from literal5 to literal6, matching the pin already on BASE. The pin is not edited in this PR. All allowed companion delivery edits, ordinary SHARED-01 proof, review seats and runtime/test/isolation constraints are exactly the parent's; no gate/parser/suite/dependency/runner/runtime or stopped optimization code is included. All original cases, assertions and native calls remain unchanged.

## Unchanged arithmetic and observation criteria

The complete job budget remains **25s pre-suite +15s suite-step overhead +285s pytest +5s exporter +5s cleanup +25s variability =360s**. The allocations and observational-versus-proposed qualifications in the parent are incorporated unchanged. They are not new kill timers or speed claims. The285s suite ceiling and all runtime safety caps stay exact.

Require the actual current-head hosted six-minute registry job to complete with its required exporter and every component allocation met, at most335s whole-job time and at least25s headroom under360s. Record pytest elapsed/case/skip/warning counts, suite-step residual including installation, exporter mode, cleanup, head/base, all required checks and code/security reviews. Retain the pin-stage actual-head receipts as the other half of the parent DoD. A legitimate unchanged-input exporter path is labeled as such; absent full-path timing remains an explicit limit on the5s reserve. Do not fabricate inputs or repeat successful suites to choose a favorable sample.

Source proof, no-new audits, four prepush review seats and normal protected merges remain mandatory. No denial workaround, blind retry, capacity waiver or future-stage proof is permitted. Completion of this live stage with the retained pin evidence is the point at which the parent global design can be reported complete; specification approval alone and pytest success alone are not that outcome.

## Cost, side effects and rollback

Only the stocks CI job's nominal allowance rises300to360s. Existing event volume/velocity, runner CPU/memory, native isolation and execution steps remain exact. The extra60s/20% allowance is not a hard maximum on occupancy or billing; cancellation tails and account rounding remain unproven. No GCP/SQL/schema/provider/deployment change is introduced. Rollback and risk handling remain the parent's normal reviewed pin-first sequence, with no protection or runtime-cap relaxation.
