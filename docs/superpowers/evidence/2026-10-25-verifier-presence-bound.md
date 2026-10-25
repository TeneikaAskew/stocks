# Historical SITE presence repair acceptance

Root owns publication. Required immutable-plan continuation: #1595 → #1596 → #1597.
Original first CODE fbcd11e7 found VP-01 P2 missing historical blob availability
(thread4369466246, receipt6392781464). Correction d065a3ef retains mode/type,
bounded sizes() availability and original size admission before skipping the
existence-only content read. Independent focused verification addresses VP-01;
the original independent no-findings review missed that case and is not rewritten.

Full corrected verifier suite:199passed,1warning173.01s. Four targeted controls
passed2.41s, including actual bound-note SHA1/SHA256 repositories where deletion
of only the marker-referenced historical blob must refuse despite a valid newer
record. Source drift duplicate-read and oversized-current-body refusal remain.
Source and tests here are byte-identical to corrected d065a3ef.

Normal publication proof: source_identity_sha256=ba3b55735db8811c10982c8cde45832fc073ba6e587820b59064cfa4aacfc053;
body_sha256=7d89ee2c6390c1c85cfc051874b305e4b2f4be720a9f864b75e1da3403cacac1.
Committed sidecar verify at cac2ec8e:1446entries,6932241bytes,0.5862seconds,
declared-note identity-matched. Full default main911d30a7/head audits288/288,
zero new finding identities including multiplicity; only relocated line numbers
normalized. Remaining debt is retained, not claimed absent.

The original historical failing #1575/#1593 revisions were reproduced with the old
verifier before the1875218-byte41-spec batch; corrected module preserves exact
source/body identities under original8388608-byte/5-second/20000-entry limits.
Current owner revisions must be rechecked separately; a newer owner provenance
close-out is not presumed to share the historical failure.

Owner explicitly approved only #1596's three old-verifier local findings,
recorded6397257797; spec merged normally911d30a7. That exception is not reused here.
All caps/negative tests/source scopes/charging remain unchanged. No automatic
controller, production deployment, live data freshness or durable review-process
claim follows from local source identity or document CI.

One original external CODE round spent on1595; reserve final current-head CODE
and first SECURITY on1597 as the final declared cohort, retaining every prior
review/PR/finding identity. Replacement first review remains complete. No fresh
budget, abandoned finding, duplicate provider request or automatic issue closure.
Final exact-head CI/review receipts belong on1597 to avoid receipt-only pushes.

## Required current MAIN integration

Integrated actual merged acceptance specification MAIN `35671dbba024efa6700e29febdf7ee6b8cea41c2` in `c4478d92`. The source module and tests remain byte-identical to reviewed `d065a3ef`; no algorithm, cap or test change. The only merge conflict was MAIN deleting the former sidecar while this implementation needs an ordinary declared-note record; retain and regenerate that record against actual MAIN. MAIN's independently verified SITE marker is retained, not reverted. Existing source/body identities remain `ba3b55735db8811c10982c8cde45832fc073ba6e587820b59064cfa4aacfc053` / `7d89ee2c6390c1c85cfc051874b305e4b2f4be720a9f864b75e1da3403cacac1`.

This final integration is required after the approved dependency landed, not an unchanged timeout retry or review reset. Current-head hosted CI/review must independently complete; earlier cancelled registry and clean reviews remain evidence of their own commits only. No failed acceptance is marked passed.
