---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-DEPLOY-001]
issues: [2124, 2030]
canvases: []
done_when:
  - "Only test_the_workflow_apply_lock_wait_shrinks_by_what_the_scan_spent in tests/gcp/test_apply_schema_trigger.py changes executable test behavior: retain one slow run with scan_sleep=3, assert successful execution, parse SCAN budget and APPLY lock from that same run and require lock <= scan - 3. No assertion is skipped or relaxed to a smaller debit."
  - "A deterministic offline diagnostic executes the unchanged workflow apply shell with inert pip/git/python/wait boundaries and a per-run synthetic clock: quick=1399 and slow=1397 reproduces the old cross-run failure while scan=1400 and lock=1397 satisfies the new assertion. Same-run zero, three and four-second elapsed controls preserve exact debit; a local mutation that reuses scan_remaining for lock_remaining fails the new assertion. No mutation is committed."
  - "Zero and negative remaining-budget controls before the scan and after it refuse without starting apply; the original exhausted-budget and shared-deadline tests remain unchanged and pass. Production workflow, shared deadline, reserve and actual elapsed-time arithmetic are byte-identical to main."
  - "The affected test file passes through the normal hermetic repository runner; required commit/PR gates, matched documentation audits, applicable existing review requirements and exact-head CI pass. No blind hosted rerun, new timeout, quarantine, xfail or permission change substitutes for the repair."
status: draft
supersedes: null
---

# Measure schema scan debit inside one test run

## Admission and ownership

The owner requested repair of the known failing CI test tracked by #2124 (also #2030). This is a proposed narrow test-maintenance contract, not approval to change schema application. Normal specification approval and landing precede a fresh ready implementation plan. Keep the independent EW verifier specification #2121 unchanged. Public open-PR and local branch inspection on November 26 found no overlapping repair; unpublished external work remains unverified and must be reconciled before implementation publication.

## Problem and design

The current test compares two separate processes whose whole-second clocks can cross different startup boundaries. Legitimate quick=1399 and slow=1397 budgets fail its three-second cross-run difference. The actual workflow correctly subtracts elapsed time from one shared deadline.

Use #2124's within-run repair: remove the quick invocation, retain the slow invocation, assert its return code is zero with stdout/stderr diagnostics, and compare its lock budget with its own pre-scan budget minus three seconds. Preserve the test name. The existing sibling already checks lock <= scan and reserve bounds. No permanent synthetic clock or helper change is needed: a diagnostic clock supplies deterministic proof without expanding the maintained harness.

## Scope and exclusions

Implementation source scope is exactly the named test function in tests/gcp/test_apply_schema_trigger.py and any directly stale comment in that function. Normal fresh plan and feature-owned catalog/traceability records accompany delivery as required. No shared fixture, conftest, production workflow/script/runtime, gate, pinned copy, CI permission, deadline, reserve, schema, data, deployment, provider or external-service change. Preserve the existing hermetic gcloud guard and every other test assertion. The approved hermetic-guard contract remains unchanged; this additive specification supersedes nothing.

## Qualification and capacity

Run deterministic clock controls against the actual workflow shell with an empty environment and an allowlisted local PATH; replace all external operations with inert doubles. The diagnostic's synthetic clocks model boundary conditions, not measured production performance. Then run the actual affected file with the repository's normal hermetic test setup in offline mode. Inspect that runner before use; no production connection or credential lookup is permitted. If full qualification needs an unavailable capability, retain the failure and report it rather than weakening guards.

One fewer workflow simulation and no new deployed workload, database query or vendor call. Existing test timeout and review limits remain. No new infrastructure cost beyond ordinary CI. The eventual implementation must bind this approved specification on actual main and carry real test receipts; this draft does not claim the fix has shipped.
