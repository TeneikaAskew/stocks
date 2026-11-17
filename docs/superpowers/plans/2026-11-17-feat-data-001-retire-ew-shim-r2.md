---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-10-31-feat-data-001-retire-ew-module-shim.md
branch: fix/feat-data-001-retire-ew-shim-r2
pr: null
status: ready
---

# EW scorer retirement implementation plan (re-cut of #1914)

> For agentic workers: use superpowers:executing-plans.

**Goal:** Remove the retired scorer while retaining the shared NYSE import contract.
**Architecture:** Keep the existing nyse_sessions wrapper verbatim; move vendor tests verbatim and add independent shim coverage.
**Tech stack:** Python, pandas, pandas_market_calendars, pytest.
**Spec:** docs/superpowers/specs/2026-10-31-feat-data-001-retire-ew-module-shim.md

This plan is a copy of #1914's plan (`docs/superpowers/plans/2026-11-13-feat-data-001-retire-ew-module-shim.md`
on the branch `fix/feat-data-001-retire-ew-module-shim`, head 9aaa28f7), bound to this branch. #1914 reached
the two-round review cap with one open P1 (discussion r4571335566: the committed
`docs/review-evidence/site-source-snapshot.json` held two top-level JSON records). The owner approved the
re-cut on 2026-11-17. The spec, its `done_when` items and the work are unchanged; the steps below are
re-executed on this branch from current main, and a box is ticked only for a step run here.

## Constraints and prerequisites

Base: current main d35d9ce2 (2026-11-17). The brief consumer removal is landed (#1837, 6e04eb53) and the
operational retirement record is merged (#1869, afd476b6); the evaluator job and schedule are retired in
deploy source (#1834). Preserve the shared wrapper and its two runtime consumers, historical rows,
numeric behavior, other owners' branches and all prior spec and implementation reviews, #1914's included.
No deployment, schema or secret mutation.

Main gained #2047 (f5a9fd01) after #1914 was cut. It edited `evaluate_range` (its minute fetch no longer
passes `adjusted=False`), the scorer test that pinned that keyword, and the vendor helper `_daily` (a
TIME_SERIES_DAILY reply with no adjusted fields). The first two leave with the scorer. `_daily` moves
as main holds it, so the vendor block moves verbatim from current main, not from #1914's branch.

## Review focus

Holiday and early-close schedules must remain real NYSE sessions; DST opens must remain UTC-correct; missing calendar dependency must raise rather than guess; AV collector and earnings-session imports must continue resolving; moved vendor assertions and parametrized node suffixes must be byte-identical to current main.

## Task 1: shim and test split (done_when 1 to 3, 5 to 6)

Spec: done_when items 1 to 3, 5 to 6; Sequencing with #1546.

- [x] Collect actual base repository nodes and evaluator nodes; retain their exact inventory outside the checkout before edits.
- [x] Add tests/gcp/test_nyse_sessions_shim.py: holiday week excluding 2026-11-26, 2026-11-27 close 18:00Z, 2027-03-15 open 13:30Z, ImportError without the library, exact original wrapper source and absent scorer surface. Run against original module and record the expected surface failure.
- [x] Replace gcp/fetchers/evaluate_ew_strikes.py with the preserved wrapper, required imports and binding-spec docstring. Move the seven vendor functions and helpers verbatim from current main to tests/gcp/test_fetch_market_data_vendor_answers.py; remove only the 49 scorer cases and original test container. Remove this module from tests/lib/test_av_account_allowance.py CONSUMERS.
- [x] Run the new shim/vendor, unchanged collector/session and account suites. Verify exact base/head node relation: minus 49 plus new shim nodes; no other suite loses nodes. Regenerate timezone baseline with its supported command and prove only the two scorer violations disappear.

## Task 2: model and delivery records (done_when 4 to 5, 7 to 8)

Spec: done_when items 4 to 5, 7 to 8; Source identity and close-out.

- [x] Mark MODEL-EWV-001 Retired / REMOVE with date, retain history; add retirement header, exact historical counts and preserved-test pointers to its model document. Regenerate model export and run model-pointer/vocabulary checks.
- [x] Refresh only FEAT-DATA catalog, own lineage, and declared SHARED-07 note; preserve previous own prose and all foreign SITE bytes. Use supported generated-inventory renderer and fixed-bound source producer/verifier, with the sidecar written whole by the producer as one record.
- [x] Run matched main/head documentation audits, unchanged source/audit suites, normal commit and PR gates. Record full counts, failures and boundaries. Name P-J docs/ew-retirement-product-docs as separate follow-up, never alter 06-DATA-ARCHITECTURE here.
- [ ] Publish Draft only after prerequisite receipts and shared-file coordination, bind the number, then spend the first complete review on the final qualified head. Preserve the two-round limit and #1914's review history; no reset is claimed.

## Close-out

- [ ] Actual main source verification after merge; plan remains ready until a separate docs close-out.
- [ ] Deployed-image and real-output verification remains separate owner-coordinated release evidence.

## History carried from #1914 (not re-executed here)

#1914's plan recorded these receipts on its own bases. They are kept as its history and are not
evidence for this branch.

- November 13, base 6e04eb53: 111 focused cases passed with the pre-existing collector durability
  integration-only skip; 27 shim/vendor cases, 6 timezone cases, 109 model/export cases and 804
  unchanged source/audit cases passed; base/head collection 9629/9585, minus 49 scorer plus 5 shim;
  matched audits 311/311; source identity d53ea207338e80a7f0973df6ca8ef0cd76b6a10a2265951dc7ee195df41dff66.
  The model's unknown provenance marker was retained; the registry-wide Last reviewed prerequisite
  landed separately through docs/ew-model-registry-review-date.
- November 13, main 12633c83: 152 vendor/calendar-consumer/as-traded/API cases passed with one existing
  skip; collection 9643/9599; matched audits 312/312; source identity
  261c0e4e6e44d07893f2f0d9bc569bbd1adf50c70a7f8993f8b67c254fa2bbc8.
- November 14, base fdb005df: #1869 merged at 00:28:59 UTC as afd476b6; collection 9646/9602 (minus 71
  old evaluator nodes, plus 22 moved vendor nodes and 5 new shim nodes).
- November 14, Draft #1914 on base db0e4ba3: 290 focused unique cases passed with 1 existing skip;
  804 source/audit cases passed; matched audits 311/311; source identity
  714e2180698a103b147359145dd92c7a7725fc9f51950697354d0544f9c7af3e.
- Review: first CODE review clean on fbe6b80c; second CODE review on 9aaa28f7 (a merge of main) posted
  the P1 above; SECURITY review completed on fbe6b80c with null finding flags.

## Re-cut execution, November 17

Receipts for this branch are recorded here as each step runs.

Task 1, on base d35d9ce2:

- Base inventory: `python3 -m pytest tests/ --collect-only -q` collected 11,717 cases (sorted node list
  sha256 091b3985c8efa6772b648c01928df832ada01005bae1a53bbfed6b4f61db8591, kept outside the checkout);
  `tests/gcp/test_evaluate_ew_strikes.py` collected 71 cases over 35 functions.
- The new shim test against the original module: 4 passed, 1 failed
  (`test_scorer_surface_is_removed`: `hasattr(ew, 'scoring_session')`), as expected; the wrapper-source
  case passed, so the pinned wrapper equals main's L196-204 byte for byte.
- After the strip: the kept wrapper equals main's L196-204 (L205 is the blank line after it); the module
  exports `nyse_sessions` and imports only `date`, `pd` and `session_schedule`. The vendor block (`_Resp`
  through `test_every_price_call_sends_the_listed_share_class`) is current main's block byte for byte,
  #2047's `_daily` included; it differs from #1914's moved copy only in `_daily`.
- Shim, vendor, collector entry and allowance suites: 88 passed, 1 skipped (the existing
  `tests/gcp/test_av_options_collector_entry.py:188` integration-only skip).
- Head inventory: 11,673 cases. Per file, only `tests/gcp/test_evaluate_ew_strikes.py` (71 to 0),
  `tests/gcp/test_fetch_market_data_vendor_answers.py` (0 to 22) and `tests/gcp/test_nyse_sessions_shim.py`
  (0 to 5) change: 11,673 minus 11,717 is minus 44, which is minus 49 plus 5. The 22 moved node ids equal
  the base ids; the 49 retired ids equal #1914's receipt. The only other node-id difference is the two
  gzip-mtime parameter ids of `tests/gcp/test_av_realtime_transport_cli.py`, whose count is unchanged.
- `python -m tests.meta.test_timezone_boundaries --write-baseline` removed exactly the two
  `scoring_session` entries; `tests/meta/test_timezone_boundaries.py`: 6 passed.

Task 2, model records:

- `docs/product/07-MODEL-REGISTRY.md`: only the MODEL-EWV-001 row changes (1 line; Status Retired, Rec
  REMOVE, operational retirement date 2026-11-13 kept); no history row or blockquote is touched. The row
  and `docs/models/MODEL-EWV-001.md` were unchanged on main since #1914's base, so #1914's edits applied
  cleanly; the model document's counts now state this branch's collection.
- `python3 scripts/gate/export_model_registry.py` regenerated `docs/product/generated/model-registry.json`;
  `--check` printed `model-registry.json is current` and exited 0.
- `tests/meta/test_model_registry_consistency.py`: 68 passed, after the carried receipt
  `docs/review-evidence/ew-module-shim/node-disposition.json` was added (before it, the dead-path check
  failed on that citation, as it should).
- `docs/review-evidence/ew-module-shim/node-disposition.json` and `preservation.json` are #1914's files,
  carried unchanged (blobs 5d1e1429 and c833f2a3, equal to #1914's): no tool in the repository generates
  them, so they are not regenerated. They describe #1914's bases; this branch's receipts are in this plan.

Task 2, records, identity and checks:

- `python3 scripts/maintenance/doc_inventory.py --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json
  --insert` over 05-a, 05-c and 05-e updated 05-a and 05-c (the module's summary line, and the module
  leaving the `earnings_calendar` writer, reader and multi-writer lists) and left 05-e unchanged.
- FEAT-DATA-001 catalog Status names this re-cut; Last reviewed reads 2026-11-17. The FEAT-DATA-001
  lineage records #1914 and its re-cut; this branch's PR number is added once it exists.
- Producer preflight reported source identity
  f719860b10696121d8badcb38c1c7cd034d8598be84d41617fff75bb1d74cece with "each declared own note must be
  added or updated". The `(FEAT-DATA-001, SHARED-07)` row was rebound to it, its earlier content kept after
  "Earlier:", and committed (30b7505b); the SITE diff is that one row. `produce` then wrote the sidecar
  whole (6b6c5446): `json.load` and the tool's `json_record` each read one record. `verify --policy-ref
  origin/main --source-ref HEAD --max-seconds 5 --max-input-bytes 16777216 --max-entries 20000` reported
  `identity-matched` on the `declared-note` route, 1,895 entries, 14,658,398 counted bytes, SITE body
  6dcd9717a82b1c1d49a067bcfb699fa528854ee5a867b5792fd6498b1ed63c86. `docs/DOC_REGISTRY.md` is blob
  c101b844, mode 100644, as on main.
- Matched docs audit (`LC_ALL=C python3 scripts/maintenance/docs_audit.py`, normalized and sorted): main
  d35d9ce2 316 findings, branch 313; `comm -23 branch main` is empty. The three main-only findings are
  SITE's two changed-since findings and its source-provenance finding.
- `python3 scripts/gate/spec_gate.py --pr origin/main`: `spec gate ok` over 18 changed files; every commit
  passed `--commit` and the pre-commit hook.
- Suites: `tests/gcp` (without `tests/gcp/test_av_realtime_transport_cli.py`) with the importer, earnings,
  allowance, eastern-time, model-registry and timezone suites, `-n auto`: 5,119 passed, 8 skipped (the
  collector integration-only case and seven deploy differential cases that need `DEPLOY_BASELINE_REV`), in
  548 s; `tests/gcp/test_av_realtime_transport_cli.py` alone: 33 passed;
  `tests/scripts/test_check_generated_docs.py`, `tests/scripts/test_doc_source_snapshot.py` and
  `tests/scripts/test_docs_audit.py`, unchanged: 964 passed, 1 skipped (a root-only case), in 195 s.
- Read on 2026-11-17 at 20:24:56Z: `gcloud run jobs describe evaluate-ew-strikes` answered
  `Cannot find job` and the `evaluate-ew-strikes-daily` scheduler answered `NOT_FOUND` in us-east1.
- P-J (`docs/ew-retirement-product-docs`) is named in the PR body; `06-DATA-ARCHITECTURE.md` is unchanged.
