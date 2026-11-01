---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-10-25-feat-cicd-001-verifier-presence.md
branch: feature/feat-cicd-001-verifier-presence-bound
pr: 1597
status: ready
---

# Avoid redundant historical SITE content inspection

**Spec:** `docs/superpowers/specs/2026-10-25-feat-cicd-001-verifier-presence.md`.

Parent-authorized narrow corrective repair, October 25: preserve all validation,
logical-byte accounting, source identities and fixed resource ceilings. Sole writer: root.

1. Reproduce #1575 and #1593 immutable published heads against trusted main.
2. Replace the historical SITE existence-only content read in terminal detection
   with an equivalent regular-blob tree check. Full bodies remain mandatory and
   charged for actual body comparison. Missing/malformed entries still refuse.
3. Add focused changed-source, duplicate-read and oversized-body regression controls.
4. Run affected tests and reproduce actual failing heads with the candidate module.
5. Publish a draft with normal scoped review and hand off exact source/test revisions.

No cap increase, read discount, source exemption or review reset. The fixed ceiling
may still legitimately refuse larger inputs. #1583 integration is separate.

## Task 1: Remove redundant historical presence content read

Spec: `docs/superpowers/specs/2026-10-25-feat-cicd-001-verifier-presence.md` — resource admission and committed-source verification.

- [ ] Replace the existence-only historical body read with regular-blob metadata validation.
- [ ] Preserve full charged body reads when comparing bodies and all resource caps.
- [ ] Run focused duplicate-read/changed-source/oversized-body tests and complete verifier suite.
- [ ] Verify both actual failing published heads retain exact source/body identities.
- [ ] Obtain normal scoped review and publish exact source/test handoff.

## Retained delivery and review lineage

Required immutable-binding replacement of #1595, not a new review allowance.
Original CODE first review fbcd11e7 had VP-01 P2 missing historical blob;
d065a3ef fixes it with metadata size/type/availability and original size admission.
Original thread4369466246 and fix reply4369486725, receipt6392781464 remain binding.
197 initial /199 corrected local tests passed; independent focused fix verification
addressed VP-01. One external CODE round spent; reserve remaining final CODE round
plus required first SECURITY as one declared current-head cohort. All predecessor
#1470/#1595/#1596 effort stays recorded; no reset or uncounted run.
Owner approved only1596 three explicit old-verifier findings, receipt6397257797;
normal final proof, no-new audit, checks/reviews and protections apply here.
