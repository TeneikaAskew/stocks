# Historical SITE presence repair acceptance

The sections up to "Verified live CI integration" are the 2026-10-25 records, kept as written;
their counts and identities belong to the heads they name. The current state is in the last section.

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

## Verified live CI integration

Actual live-six-minute activation #1599 merged `e7e74ccc2a97f31eeefba3e275904ad181743bf0`, with all six required hosted checks and CODE/SECURITY clean (receipt1599#6400278126). Live and pinned workflow bytes are equal, SHA256 `0be013b46061d523ce4cae88859d235313e0e1f530f78742dbe88e71af589434`; its native registry144PASS291.10s/exporter-current whole314s leaves46s reserve. Integrate that actual MAIN at `fa06a175`, preserving both fixture and verifier owned records and the complete #1595/#1597 review history. This source module/test pair is unchanged from reviewed d065a3ef and fully tested066; no algorithm/cap/charging/test change.

Regenerate the ordinary sidecar against actual e7 MAIN; source/body identities remain ba3b55735db8811c10982c8cde45832fc073ba6e587820b59064cfa4aacfc053 /7d89ee2c6390c1c85cfc051874b305e4b2f4be720a9f864b75e1da3403cacac1. The old066 registry cancellation (144PASS290.88s, exporterSKIPPED) remains a failure of that head, not rerun or relabeled. Its main7598PASS71skip115warnings1281.19s and clean CODE/SECURITY remain separate historical evidence. This necessary final integration receives focused current-head verification within the retained actual review history; no new full-review budget or approval hold. Final current-head native CI/reviews still must pass before normal merge.

## Current MAIN integration (2026-11-01)

Main advanced to `27c3c9ecf35d1ce382261d2be4b998196f6ff011` (2026-10-25 head `2221b3e3` was based on `e7e74ccc`).
Local commits on this branch: `505db5c2` merges that main (parents `2221b3e3`, `27c3c9ec`); its only
conflicts were the SITE table and this sidecar, both taken from main. `52ce1e7c` updates main's single
`FEAT-CICD-001 | SHARED-01` note row (added by #1591) in place instead of adding a second row, with the
current source identity and the current fact that the pinned (#1591) and live (#1599) registry timeouts
are both six minutes. `ca3e20f6` regenerates the sidecar against `27c3c9ec`. Source module and tests stay
byte-identical to reviewed `d065a3ef` (blobs `ce02946a247eb6af6a2b98ffc628a3287878ecc9`,
`19e7c6ae6d180f97bbec68ae2424e6b5012adf91`).

Measured 2026-11-01 at `ca3e20f6`, original 5-second / 8388608-byte / 20000-entry limits:
- `doc_source_snapshot.py verify --policy-ref 27c3c9ec --source-ref HEAD`: declared-note identity-matched,
  7520214 bytes, 1482 entries, 0.699 s and 0.750 s on two runs. Source identity
  `56e5cb7a801e90996ff4676300a25b04480cc6158c70e8df4ee5a4be3e779ab9`, body
  `0b94445b8ec436a79107143061f467f741556d880727544b98fd0256616fdc7f`, policy
  `8009cb4dc0e87842d6dc52ad44bd38e576e40a1ec9adbcecdcb2a377efe0b8ef`.
- For comparison, main's unrepaired verifier on `27c3c9ec` refuses its own record: "object exceeds
  remaining input-byte allowance" at 6493746 counted bytes.
- `pytest -q tests/scripts/test_doc_source_snapshot.py`: 199 passed, 1 warning in 313.48 s.
- `docs_audit.py --json` on main `27c3c9ec` and on `ca3e20f6`, both with the same saved issue snapshot
  captured 2026-10-31T11:02:59Z (live issue reads are not available in the authoring environment, so this
  compares the two trees and is not fresh issue evidence): main 292 findings, branch 289, no new finding
  identity with multiplicity; the 3 removed are the SITE changed-since pair and the source-provenance
  byte-allowance refusal.
- Local gate: hook passed on all three commits; `spec_gate.py --pr` in draft mode passes.

Not yet evidenced for this head: hosted current-head checks and current-head CODE/SECURITY review.
The 2026-10-25 records above (4 hosted CODE runs on `fbcd11e7`, `c4c06155`, `066745dd`, `2221b3e3`,
3 SECURITY runs, VP-01 and the 2026-10-25 merge hold) are unchanged, and done_when item 4 stays open.
