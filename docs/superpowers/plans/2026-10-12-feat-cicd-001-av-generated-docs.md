---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-10-11-feat-cicd-001-generated-docs-render.md
branch: fix/feat-cicd-001-av-generated-docs
pr: null
status: ready
---

# Make generated inventory changes pass the delivery gate

Approved authority is the merged generated-docs-render specification. This prerequisite permits AV schema/route changes to carry exact rendered inventory bodies without weakening product-record boundaries. Sole implementation author works from merged main; no stacking, unmerged cherry-pick, other-author branch push or pinned/workflow/timeout edit.

## Task 1: Implement and verify generated-block and byte-scope checks

Spec: § Design, § Capacity, § Non-goals. Advances done_when[0] through done_when[5] and done_when[7].

- [ ] Read approved merged specification, current main gate/test callers and attributed candidate source PR1383@f552ec59f6418bfe091154f9d2737501f83a81b0. Port only approved gate/tests/skill behavior as explicit code attribution and reconcile main changes, no unmerged commit history.
- [ ] Reproduce meaningful new assertions failing against actual main gate; preserve all concrete marker/body/bytes/head-tree/render-input/refused-control coverage.
- [ ] Optimize fixture/materialization I/O only within the approved contract, measure full registry-equivalent gate suite comfortably below285seconds without raising timeout/pinned/workflow change.
- [ ] Run full gate, neighbors and actual base suite against new gate; preserve render trust/isolation and failure behavior.
- [ ] Update owned FEAT-CICD-001 catalog Status/Last reviewed; root supplies draft PR number for owned traceability before final delivery.
- [ ] Commit self-reviewed code after commit gate, keep branch unpushed pending root's FOUR independent concrete-snippet red-team seats.

## Task 2: Resolve independent findings and finish concrete delivery

Spec: § Design, § Risks, § Done when. Advances done_when[6], done_when[8] and done_when[9].

- [ ] Root arranges shell, YAML/Actions, exporter/policy and diff/byte/render reviewers with executed concrete snippets. Batch all confirmed fixes; repeat independent pass until empty before single push. No author self-review substitutes for independent seats.
- [ ] Run final tests after changed code, docs audit comparison with no new finding keys and PR-mode gate against main.
- [ ] Add actual PR number to plan/catalog owned traceability; record all acceptance evidence/runtime/material risks in report and PR body. Root reviews/merges; no product deployments by author.
