# STRAT and earnings execution recovery — October 23, 2026

This records recovery state, not implementation acceptance or market validation.

## Objective and unchanged scope

Finish accurate, consistent STRAT and earnings behavior through actual production entrypoints. Evaluate price movement, activation, invalidation, target progression and timing, not dollar returns. Baseline: October 1–9, 2026. Retrospective holdout: October 10–16; outcomes remain unscored until both repaired engines and settings freeze. Reacquired inputs must have a new manifest and explicit acquisition vintage; they cannot inherit missing capture hashes or contemporaneous-input claims.

Approved specifications remain in [STRAT PR1566](https://github.com/TeneikaAskew/stocks/pull/1566) and [earnings PR1567](https://github.com/TeneikaAskew/stocks/pull/1567). Their full execution plans remain visible in [the STRAT plan comment](https://github.com/TeneikaAskew/stocks/pull/1566#issuecomment-6356505617) and [the earnings plan comment](https://github.com/TeneikaAskew/stocks/pull/1567#issuecomment-6356506152). Status history is in [issue1563](https://github.com/TeneikaAskew/stocks/issues/1563#issuecomment-6356955819).

## Verified recovery state

The started runtime executes commands, but initially contains an older setup checkout at eca17a65. The previous strat-engine worktree, evaluation directory, replay containers and Docker volumes are absent. Read-only recovery searches found no alternate local archive; the interrupted reviewer has no complete alternative copy. Underlying provider-storage deletion is not established.

GitHub still contains the exact specification heads 0f67903f6ca0b09730f84500f283146e13f4bc20 and 4072f12585d97ee2f8814e481c43c80ba0935a3e, with green CI and pending current-head code reviews. Current fetched main is a5749d4c0b9395582181e8884d2b33af889f5f91; its changes since the prior 2e67a19f base concern generated-inventory governance, not the missing STRAT implementation. Authorized GCP credential refresh and bucket listing succeed. No original implementation archive was found among relevant GitHub artifacts. Storage source discovery continues read-only.

## Prior checkpoint: historical record only

Task1–4 and5A had local reviews; Task5B had a frozen20-file candidate with287 affected and97 persistence tests reported passing, including4 existing pandas warnings. Its interrupted reviewer independently checked hashes and the OpenAPI generator, but returned no final approval. These results cannot certify freshly reconstructed files.

Recovery identifiers: candidate manifest SHA256 e718b33f011850426b68a048e3285d1a41f75cc9ebaadc721d0a47b08afb1e41; report a4cf24ae696e6267083070a1c6d415b86676297f4d60f2523883bd502d7b1d2d; patch 1cef3b2b60816e5127ba945cb75e4b43cb7d633bf32e37fa4fe7d9983160f3e0. Hashes identify missing artifacts; they are not recoverable copies. No patch will be reconstructed from a conversational summary and represented as the original.

## Recovery execution

1. Preserve the current checkout; recover published specifications/plans and inspect actual source at trusted main.
2. Exhaust intact artifact recovery. If unavailable, reimplement from the approved specification and actual source, with fresh failing/passing regression tests and independent reviews. Replay exact previously recorded patch commands only where complete commands are available; verify any claimed recovered file against its original hash.
3. Reacquire baseline source observations through authorized read-only GCP/Alpha Vantage access as needed, preserving original system outputs separately. Record source identity, timestamps, uncertainty and new hashes. Do not score held-out outcomes while rebuilding.
4. Complete the existing sequential STRAT plan, then the nonstacked earnings plan, retaining genuine calendar/basis/receipt integration requirements. Unsupported custom anchors/temporal PMG remain explicit until defined; no new trading policy is selected here.
5. Replay actual brief/insight/earnings entrypoints in a mode refusing all production persistence and notifications. Compare frozen decisions with later price movement; preserve gap-already-crossed, unavailable cases, ambiguous bar order and source coverage in denominators.
6. Push each reviewable checkpoint to its PR under repository gates. This documentation checkpoint is published immediately. Code commits/PR publication remain subject to the approved-spec merge-base gate; no bypass, deployment, production write or new merge permission is implied. Do not accumulate another long unexported implementation.

## Decision record

Ruling: treat inaccessible implementation as unverified until exact files are recovered, otherwise rebuild from executable requirements with fresh tests — prior approvals certify specific missing bytes, not approximate replacements — cost if wrong: repeated implementation/review work, but no false provenance or inherited market-proof claim.

Ruling: publish this documentation checkpoint immediately and use PR-backed implementation checkpoints under the normal gate — user explicitly requested durable PR publication after runtime loss — cost if wrong: additional documentation/review overhead; no code-gate waiver.

## Verified recovery checkpoint

Recovered72 generation-pinned GCP query-result JSON artifacts,74,322,249 bytes;232 statement metadata records. This is a remote archival subset, not the missing467-file evaluation set. The original five-table archive contains2,167 native rows, matching prior recorded totals:42brief history,37insight reports,137alerts,1,946calendar,5reactions. Baseline-only selection produces24brief rows,22insights,89alerts,1,149calendar,3reactions; no deduplication or movement scoring. Holdout outcomes remain unscored. The original AV daily/minute captures and their complete467-file manifest remain missing.

Task1's19 literal original edit commands were recovered and replayed with only worktree-path translation. First17 reproduce allthree original pre-review hashes. After the two recorded review fixes, allthree finalhashes match the original reviewer's independently retained approved hashes. Fresh tests reproduce initialRED30failed/76passed, reviewRED7failed/32passed, finalGREEN158passed. This is exact-byte source restoration, not approximate reconstruction. Independent recovery verification is being finalized.

Task1 final source SHA256:b33fa6e0b047a1f07288a82298f4e2a537bfd95243e255bc56a40f301c905d6d; tests/lib/test_strat.py:a32be6dddc1244e3f2d0ba526f5ac97285e5bf63fb50a42e76f54f4bbd12824e; tests/lib/test_strat_history.py:9433003e6e2bafbd8fffbbb8de3bb37798c38a92af760eec13c20c1d8e4980c4. Other task-command exports are being assessed. Task2 is confirmed incomplete, so new implementation will require fresh tests/review rather than inherit its prior approval.

The unfinished second spec-review round was requested again at the same unchanged head, with explicit recovery context and no extra completed-feedback round. GitHub markers now show fresh manual runs starting11:19AM Eastern onOctober23. There is no current-head completion yet; no merge performed.

Ruling: retry the stalled unfinished second review at unchanged commits after the owner's explicit request to refresh threads — no completed second-round result existed and no new spec change was pushed — cost if wrong: duplicated review effort if an earlier worker also completes; combine same-revision findings and do not request a third feedback round.
