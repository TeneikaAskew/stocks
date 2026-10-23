# Task4 fix round2 recovery checkpoint

**Scoped independent verification PASS: N1 addressed; no new fix-induced defect found.** This is new reconstruction under approved scope, not recovered original Task4 bytes, whole-feature acceptance, or merge/deployment approval.

## Sensitive implementation evidence

The unchanged fix1 candidate produced **7 failures and16 passing controls**. The fix retains one bounded coarse stop/target witness and reconciles it after a later fine-frame activation while preserving original evidence knowledge and separate reconciliation time. Focused lifecycle verification: **57 passed**. One final affected three-level-module batch: **252 passed in22.66s**, no skips/warnings, explicit `--mode=mock`. Exact commands and logs are in the source archive; no unchanged360/60-case batch was repeated.

Source SHA256: `fff237a96f75a3570bb1cc832ff8b136fbe9fe4b7f0bc766031b13087d5ea6d8`. Level-test SHA256: `81ac17b3e12262f656b3377649cfa9bc562fe74b673f8bf915404e80071caf98`. Only `observe_bar` and one pending field changed in production. Earlier freezes, reviewer evidence, full test prefixes, all11 prior checkpoint paths and legacy tracker ASTs are preserved.

## Durable source-only backup

Archive `task4-fix2-frozen-candidate-delta.tar.xz`: 66,816 bytes, 23 members; SHA256 `e0c4a00f6c1550bbd41708f8fade714dd6773aefe26ee32a1bc6f543b3899222`. All remote bytes and member hashes verified after retrieval. This delta plus the [fix1 archive](2026-10-23-strat-task4-fix1-review.md) reconstructs every one of the15 current frozen paths; the combined proof checks each size/hash in memory without overwriting live source. No provider/native raw captures, private IAM policy or credential values are included.

- [Archive part 1/3](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370281230)
- [Archive part 2/3](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370282057)
- [Archive part 3/3](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370282609)

Decode each part separately, concatenate decoded bytes in order, verify archive SHA256 and `BACKUP-MANIFEST.json`, then overlay the two changed frozen paths on the fix1 frozen tree. The baseline and complete15-path manifest are preserved in this archive. The archive was frozen before independent verification; its pending-review label remains historical even after the separate review completes.

## Remaining boundaries

GCP raw upload remains paused. No organization IAM retry, API enablement, new credentials, policy change or raw public upload occurred. Holdout remains quarantined and unscored. Real merged calendar/DATA basis, source/PIT admission, owner-defined canonical PMG/custom anchors, downstream consumer and M1 propagation, resolver/#908 treatment, actual production replay/resource qualification and final delivery gates remain open. Local synthetic cases do not certify these requirements.

## Original reviewer scoped result

Original report SHA256: `0241d3391b1d65af7e78f907ce2ed0bfafffd81cdefe539b87d8bf2dd0d6351f`. The following is the complete scoped report, preserved separately from the pre-review source archive. No additional suite or probe was run by the reviewer.

# Task4 fix2 — scoped independent re-review

**N1: ADDRESSED.**

**Spec compliance: PASS for the dispatched N1 correction and its fix-induced interactions.**

**Code quality: PASS for this scoped fix.** No new blocking defect was found in the fix1-to-fix2 changes. Bounded Task4 reconstruction approval is granted with the original R1–R5 dispositions retained; this is not whole-feature, upstream-data or production-integration acceptance. Root retains subsequent task and publication authority.

## Scope and identity

Read the fix2 brief, report, complete scoped diff, command log, actual RED/GREEN logs, manifests and preservation records, and the complete fix1 independent review including its original N1 counterexample. Reviewed the complete current `observe_bar` method, its immediate state/confirmation/event-retention helpers, the appended tests and their actual tracker/observation helpers. This is one scoped re-review of N1 and changes introduced by its fix, not a new whole-task audit.

Independently recomputed SHA-256 and checked actual bytes:

- All 15 live files match the fixed frozen tree and manifest; all 15 fix2 baseline files match the baseline manifest.
- Both earlier 15-path frozen trees retain their recorded hashes.
- All 40 recorded fix1 artifacts, including the prior review and literal N1 probe evidence, are unchanged.
- All 11 approved Tasks1–3 checkpoint paths retain their earlier identities.
- Only `lib/strat_levels.py` and `tests/lib/test_strat_levels.py` differ between the baseline and fixed manifests. Regenerating the textual diff in memory exactly matches `fix1-to-fix2.diff`.
- All three prior level-test prefixes are preserved. Independent AST comparison confirms that production changes consist only of `LegStateTracker.observe_bar` and the single `_typed_pending_extrema = None` field. All remaining production AST, including legacy `update` and `state`, is unchanged.
- The prior main report remains an exact prefix of the current main report.

| File | Reviewed baseline SHA-256 | Fixed candidate SHA-256 |
|---|---|---|
| `lib/strat_levels.py` | `ca3ecd8e111c1c1b4f8f27dcb6a1a5503bdb2fe354f74b45483ed830d2220f4b` | `fff237a96f75a3570bb1cc832ff8b136fbe9fe4b7f0bc766031b13087d5ea6d8` |
| `tests/lib/test_strat_levels.py` | `3fdf3d80d2bec533893e1b2f08ea412076f7abe1fa5d8b557fdd421a34b2d25d` | `81ac17b3e12262f656b3377649cfa9bc562fe74b673f8bf915404e80071caf98` |

## N1 correction and sensitivity

The original counterexample has trigger100, call target102/stop98 (put target98/stop102), 1m close activation and 5m close invalidation. At the same 09:35 knowledge clock, the 09:30–09:31 fine bar confirms activation, while its enclosing 09:30–09:35 coarse bar touches both target and stop without closing beyond the invalidation threshold. Both delivery orders must retain `stop_target_order_unknown`, with activation true and confirmed invalidation false.

Previously the coarse-first order discarded that unresolved joint range because activation had not yet occurred and the coarse close did not confirm invalidation. At `lib/strat_levels.py:410–417`, the correction stores joint target/stop evidence independently of confirmed invalidation. At `:465–479`, every admitted observation can reconcile that retained witness after activation. The new branch is symmetric for calls and puts through the existing normalized touch predicates. It does not fabricate close invalidation or executable-entry eligibility.

The four exact call/put × delivery-order tests at `tests/lib/test_strat_levels.py:1745–1759` use the original counterexample and assert state, reason, activation, unconfirmed invalidation and unknown executable entry. Actual RED fails the two coarse-first cases with `activated` instead of `ambiguous`; the fine-first controls already pass. The recorded final GREEN includes all four. This is directly sensitive to N1 rather than merely checking the new field.

The 16 hold controls at `:1761–1783` cover calls/puts and both orders. A coarse range ending after hold confirmation remains ambiguous. A range wholly before the hold, adjacent to its start, or ending exactly at hold confirmation remains descriptive and leaves state `held`. The two coarse-first spanning cases fail in RED; all boundary controls pass there and remain in GREEN. Source `:430–432,465–466` preserves the existing touch lower bound and hold/close confirmation endpoint, with strict endpoint comparison, so the original R1 boundaries are not reopened.

## Fix interaction checks

- **Immutable evidence and reconciliation:** The pending record stores the original source frame, start, nominal end, observed endpoint and knowledge time. Reconciliation emits a separate event with original `evidence_known_at`, current `known_at`/`reconciled_at`, and completion derived from original evidence knowledge (`:470–479`). It never rewrites an earlier event. Both-direction tests at `:1785–1804` assert the unchanged earlier event prefix, 09:35 evidence time versus 09:36 reconciliation, and no event changes on 09:37 redelivery. Both fail on baseline and pass after the fix.
- **Cumulative snapshots:** The existing per-frame, per-bar fact identities prevent a repeated cumulative range from moving the first joint-extrema observation endpoint merely as the knowledge clock advances (`:411–414`). If the second required extremum first appears on a later snapshot, its fact is not yet present and the joint witness can be admitted then. New bars clear only their own frame's current identities. This check follows the actual admission and fact-update code; no additional behavioral execution was needed.
- **Bounded state and history independence:** The new state is one record, selected by greatest observed endpoint. For the existing eligibility predicate “any joint range ends after the fixed activation lower bound,” retaining that maximum is sufficient; shorter witnesses cannot change the answer. Reconciliation reads the record, not retained event history. The test at `:1806–1828` evicts the original descriptive event with 130 failed fine bars, then confirms activation inside the retained 4h range and asserts ambiguity, original source evidence, no confirmed invalidation and at most128 retained events. It fails on baseline and passes after the fix.
- **Existing lifecycle interactions:** Confirmed invalidation retains its independent evidence and ordering logic. The new reason is emitted only once; existing sticky ambiguity and unavailable-overlay behavior remain. The separate ambiguity event retains the first `ambiguity_detected` transition without creating repeated pinned events, so the existing128-event cap still applies. Gap state and unknown fill/entry values are not changed. Legacy tracker behavior and unrelated level/gap/cluster/builder logic are AST-identical.

## Recorded execution evidence

Inspected actual log contents and the recorded commands, all explicitly using `--mode=mock`:

| Evidence | Result | Relevance |
|---|---|---|
| `red.txt` | **7 failed,16 passed,191 deselected in0.46s** | Two exact coarse-first directions, two coarse-first spanning-hold directions, two evidence-time cases and the history-truncation case fail on the baseline. |
| `green-focused.txt` | **57 passed,157 deselected in0.33s** | New23 cases plus prior lifecycle and typed confirmation controls. |
| `green-final.txt` | **252 passed in22.66s**, no skips or warnings | Actual levels, playbook and freshness modules; prior R1–R5 tests remain included. |

No suite was rerun by this reviewer. No additional behavioral probe was justified: source inspection and the sensitive recorded counterexamples resolved the scoped concerns. Reviewer execution was limited to static file/hash/diff/AST verification. Shells sourced `/workspace/stocks-setup/shell-env.sh`; verification used `/workspace/stocks-venv/bin/python` with bytecode writes disabled. No source changes, Git, network/cloud/DB/vendor/data/holdout/settings/notifications, nested agents or Task5A work occurred.

## Remaining gates and disposition

**No new fix-induced defect found. N1 is addressed, and this scoped fix passes both spec-compliance and quality review.** Original R1–R5 remain addressed; this conclusion does not inherit historical-source approval or assert exact historical reconstruction.

The actual merged calendar/DATA basis and source/PIT qualification, owner-defined canonical PMG/custom anchors, downstream Task5A integration and Task5E/M1 activation-envelope propagation, resolver/#908 fill-dependent treatment, and production replay/resource proof remain genuine open gates. The current low-level typed state and synthetic tests do not certify those obligations. No new strategy policy, fill-price choice or financial definition is introduced or required by this correction.
