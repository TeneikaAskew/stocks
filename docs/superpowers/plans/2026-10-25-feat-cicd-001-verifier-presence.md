---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-10-13-feat-cicd-001-source-review-verifier.md
branch: feature/feat-cicd-001-verifier-presence
pr: 1595
status: ready
---

# Avoid redundant historical SITE content inspection

**Spec:** `docs/superpowers/specs/2026-10-13-feat-cicd-001-source-review-verifier.md`.

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
