---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-10-31-feat-data-001-retire-ew-module-shim.md
branch: fix/feat-data-001-retire-ew-module-shim
pr: null
status: ready
---

# EW scorer retirement implementation plan

> For agentic workers: use superpowers:executing-plans.

**Goal:** Remove the retired scorer while retaining the shared NYSE import contract.
**Architecture:** Keep the existing nyse_sessions wrapper verbatim; move vendor tests verbatim and add independent shim coverage.
**Tech stack:** Python, pandas, pandas_market_calendars, pytest.
**Spec:** docs/superpowers/specs/2026-10-31-feat-data-001-retire-ew-module-shim.md

## Constraints and prerequisites

Base: 6e04eb5311522e214d874d1ee373de3c714e5c19, actual #1837 squash merge at 2026-11-13T14:57:42Z. The brief consumer removal is landed. The coordinator recorded evaluator Scheduler and Cloud Run job removal at 09:08 UTC in the prior coordinator handoff; this task does not repeat live operations or claim its own live verification. Preserve the shared wrapper and its two runtime consumers, historical rows, numeric behavior, other owners' branches and all prior spec reviews. No deployment, schema or secret mutation. Shared SHARED-07/catalog/lineage publication must coordinate with #1824; whichever lands later reconciles main and regenerates proof.

## Review focus

Holiday and early-close schedules must remain real NYSE sessions; DST opens must remain UTC-correct; missing calendar dependency must raise rather than guess; AV collector and earnings-session imports must continue resolving; moved vendor assertions and parametrized node suffixes must be byte-identical.

## Task 1 — shim and test split (done_when 1–3, 5–6)

Spec: done_when items 1–3, 5–6; Sequencing with #1546.

- [x] Collect actual base repository nodes and evaluator nodes; retain their exact inventory outside the checkout before edits.
- [x] Add tests/gcp/test_nyse_sessions_shim.py: holiday week excluding 2026-11-26, 2026-11-27 close 18:00Z, 2027-03-15 open 13:30Z, ImportError without the library, exact original wrapper source and absent scorer surface. Run against original module and record the expected surface failure.
- [x] Replace gcp/fetchers/evaluate_ew_strikes.py with the preserved wrapper, required imports and binding-spec docstring. Move the seven vendor functions and helpers verbatim to tests/gcp/test_fetch_market_data_vendor_answers.py; remove only the 49 scorer cases and original test container. Remove this module from tests/lib/test_av_account_allowance.py CONSUMERS.
- [x] Run the new shim/vendor, unchanged collector/session and account suites. Verify exact base/head node relation: minus49 plus new shim nodes; no other suite loses nodes. Regenerate timezone baseline with its supported command and prove only the two scorer violations disappear.

## Task 2 — model and delivery records (done_when 4–5, 7–8)

Spec: done_when items 4–5, 7–8; Source identity and close-out.

- [x] Mark MODEL-EWV-001 Retired / REMOVE with date, retain history; add retirement header, exact historical counts and preserved-test pointers to its model document. Regenerate model export and run model-pointer/vocabulary checks.
- [ ] Refresh only FEAT-DATA catalog, own lineage after Draft number exists, and declared SHARED-07 note; preserve previous own prose and all foreign SITE bytes. Use supported generated-inventory renderer and fixed-bound source producer/verifier.
- [ ] Run matched main/head documentation audits, unchanged source/audit suites, normal commit and PR gates. Record full counts, failures and boundaries. Name P-J docs/ew-retirement-product-docs as separate follow-up, never alter 06-DATA-ARCHITECTURE here.
- [ ] Publish Draft only after prerequisite receipts and shared-file coordination, bind the number, then spend the first complete review on the final qualified head. Preserve the two-round limit; no reset from spec history.

## Close-out

- [ ] Actual main source verification after merge; plan remains ready until a separate docs close-out.
- [ ] Deployed-image and real-output verification remains separate owner-coordinated release evidence.

## Qualification checkpoint — November 13

Source preparation is committed and locally tested: 111 focused cases passed with the pre-existing collector durability integration-only skip; 27 shim/vendor cases pass without skips, 6 timezone cases pass, 109 model/export cases pass, and 804 unchanged source/audit cases pass. Generated-doc CLI check: 1 passed. Base/head collection: 9629/9585, minus49 scorer plus5 shim. The node receipt identifies the two unchanged gzip-mtime-derived parameter IDs rather than pretending their raw spelling is stable. Matched audits: 311/311, no new finding.

Source identity d53ea207338e80a7f0973df6ca8ef0cd76b6a10a2265951dc7ee195df41dff66 verifies within the fixed ceilings. The model's original unknown provenance marker remains until post-squash verification; the stamp tool refused the branch SHA and wrote nothing.

Publication prerequisite: the actual PR gate refuses the registry-wide Last reviewed header on this feature branch, while the model tests require that header to cover the new dated retirement row. The one-line documentation branch docs/ew-model-registry-review-date carries that prerequisite through normal review; no scope or gate changes are made. The implementation waits for it to land, then reconciles main and regenerates proof. No implementation review event has been spent.
