---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-003, REQ-REVIEW-001]
issues: []
canvases: []
done_when:
  - "Commit and PR-mode gate tests accept the exact trusted-main earnings metadata successor through one additive metadata_successor field while retaining the original plan spec, branch, PR and acceptance authority."
  - "Gate tests reject changed original bindings, done-plan reopening, malformed or duplicate links, modified or unmerged specs, wrong feature or lineage, chains, cycles and every unrecognized successor."
  - "Registry tests permit only the existing daily/weekly earnings-reactions exclusion-row clarification retaining MODEL-EARN-001 and Inputs-only semantics, reject other rows, promotions and table reshaping, and retain exact generated-JSON verification."
  - "tests/scripts/test_doc_source_snapshot.py exercises actual CLI preflight, production, committed verification, gate note scope and fresh-clone landed verification with the exact metadata link and unchanged original spec identity; it fails on main's independent supersession refusal and passes only with the narrowly validated pair."
  - "Source-proof integration controls reject absent or malformed metadata links, changed plan bindings or either pinned spec, uncovered successors, wrong source hashes, missing or unchanged notes, source/body/policy drift and raised fixed ceilings; records retain the original spec path and blob identity and cannot author their own exception."
  - "The original superseded-spec, plan-binding and selected-spec regressions and the full spec-gate suite pass; normal source proof, fixed resource ceilings, no-new docs audits, mandatory gate red-team and current-head review/security/CI requirements remain enforced."
  - "The FEAT-CICD-001 catalog and traceability records identify the implementation PR and its verified gate behavior without claiming earnings runtime or deployment acceptance."
status: approved
supersedes: null
---

# Preserve immutable earnings plan binding through exact metadata succession

## Problem and authorization

The October 26 owner instruction authorizes the exact metadata-successor correction
and ordinary specification-before-code publication. It does not authorize changing
an earnings runtime candidate or waiving any review or merge requirement. Main
1675723188af915ea7e4d889ba9dbc28fc32fc9f contains the original approved earnings
specification from #1593 and its metadata-only successor from #1609. The existing
implementation plan cannot replace its frozen `spec`, yet `trace` rejects that
original once the approved successor exists. `check_registry_rows` also reads only
the selected original, which does not name the existing model reference.

No existing matching gate specification was found on current main or in the
matching GitHub PR search. This specification adds a narrow policy contract rather
than reopening, replacing or circumventing any existing PR's review history.

On October 27 the owner explicitly authorized amendment of this same open #1612
specification to address first-review P1 `r4380178105`. Read-only reproduction on
main returned `bound approved spec has been superseded in trusted POLICY` from
`Snapshot.spec_binding`, independently of the gate's trace check. The authorized
scope therefore also includes that verifier and its integration tests, preserving
the first review and the normal remaining review round.

## Approaches and selected design

Replacing the plan's `spec` would weaken immutable binding. Accepting arbitrary
prose-equivalent successors would create a broad authorization surface. Instead,
admit exactly one already-reviewed pair by immutable path and raw-byte identity,
through a separate optional `metadata_successor` field. The original `Traced`
specification remains the financial and acceptance authority.

## Exact trusted pair and plan

- Original: `docs/superpowers/specs/2026-10-24-feat-catalyst-001-event-bound-reaction-integration.md`,
  SHA256 `b5701d90da14d2a372156ad6c130e239e49748533dd631db882a6f70c20157a6`.
- Successor: `docs/superpowers/specs/2026-10-25-feat-catalyst-001-model-trace-metadata.md`,
  SHA256 `14e8f6f7b96fd49b640e860a5e97a3b4453556e9e418c1ab6fac55c631f35408`.
- Plan: `docs/superpowers/plans/2026-10-25-feat-catalyst-001-event-bound-reactions.md`;
  branch `feature/feat-catalyst-001-event-bound-reactions`; PR #1608.

Both specifications must be approved, serve FEAT-CATALYST-001, be regular files
with exactly these bytes on trusted main/base policy and unchanged in the evaluated
tree. The successor must directly supersede the original. Preserve raw `req_ids`,
`done_when` and source-note declarations and the original financial-body prefix;
the pinned metadata suffix is the only addition. A fork or self-approved tree may
not supply the authority. A missing, draft, unmerged, altered, unrelated or further
successor fails closed. Reject a second link, duplicate key, list, chain, self-link,
cycle or unnormalized/out-of-repository path. Absence of the additive field retains
ordinary supersession rejection. Every other feature and specification retains the
existing supersession policy.

## Runtime scope and authorization boundaries

Change only `scripts/gate/spec_gate.py`, `tests/scripts/test_spec_gate.py`,
`scripts/maintenance/doc_source_snapshot.py` and
`tests/scripts/test_doc_source_snapshot.py`, plus ordinary required implementation
plan and product close-out records.
`plan_stays_bound` remains unchanged. The original plan's `spec`, `branch`, `pr`
and done/ready protections remain immutable. No replacement earnings plan, branch
or PR is authorized. `validate_plan` validates the optional field; `trace` separately
verifies the exact pair and marks only that specific successor as covered. `Traced`
carries the separately validated metadata scope without replacing `spec_path` or
the original frontmatter.

## Independent source-proof binding

`Snapshot.spec_binding` must independently validate the same exact pinned pair and
the actual committed original plan's additive link before accepting that one
successor. Both gate-note scope and ordinary snapshot production/verification must
reach this check. Keep `selected_binding` and record eligibility bound to the
original specification path and blob, FEAT, original plan, branch and PR; preserve
the existing record schema. An authored record, caller flag, substituted spec,
monkeypatch or skipped verifier cannot supply authority. Production reads the
committed original plan; landed verification independently reads it from SOURCE
and checks the historical baseline and trusted POLICY, without assuming the
feature commit or its branch survives a squash.

The original spec remains byte-identical across baseline/POLICY/SOURCE. The
metadata successor must have the pinned regular-file bytes on trusted POLICY and
SOURCE and on any baseline that supplies its authority; do not infer an approved
specification from the proposed tree. Reject every additional uncovered successor.
All additional manifest, plan and blob reads pass through the existing bounded Git
reader and debit the unchanged logical-byte and whole-verification deadline
budgets. A pure shared exact-pair validator in the gate may be reused with values
read by the verifier; it may not bypass its independent reads or ceilings.

The only changed source-proof refusal is the exact validated metadata-only
supersession described here. Original financial acceptance, declared CATALYSTS-04
note ownership, exact source/body/policy identities, unchanged trusted registry,
ancestral-main availability and eligibility remain enforced. Missing, unchanged,
wrong-hash or foreign notes, CODE disguised as DOC/bootstrap, dirty SITE, oversized
input, deadline exhaustion and record tampering retain their normal refusals.

`check_registry_rows` uses the verified scope only for the existing
`daily-earnings-refresh-reactions` / `weekly-earnings-refresh-reactions` exclusion
row of `docs/product/07-MODEL-REGISTRY.md`. Retain its scheduler identities, job,
MODEL-EARN-001 reference and descriptive post-event input role. The clarification
must explicitly retain `Inputs only` exclusion and no position decision. No model
promotion, other row, header, delimiter, disposition, prose or renderer exemption
is authorized by this field. Existing registry scope for an ordinarily selected
spec remains unchanged. Normal generated JSON must equal the unchanged exporter's
output; no additional generated-file allowance is introduced.

## Verification and risks

Use synthetic hermetic commit and PR fixtures and a fresh-clone/current-main
fixture with the exact reviewed specification bytes. Positive controls retain the
same plan/branch/PR; negative controls mutate each binding, raw acceptance and
financial content, approval/trust/lineage and row boundary independently. Preserve
`test_a_superseded_spec_authorizes_nothing`,
`test_a_plan_on_the_base_stays_bound_to_its_branch_and_pr` and
`test_the_plan_names_the_spec_that_is_enforced`. Prove ordinary source-proof and
export validation still reject invalid evidence and JSON. Run the full affected
suite and `tests/scripts/test_doc_source_snapshot.py`, and base/proposed no-new
documentation audits. Source-proof positive controls run the actual CLI producer,
commit its generated sidecar and verify it without hand-authored proof; verify
again after a real squash into synthetic main and in a fresh clone. Assert the
record's original `eligibility.spec_path` and `spec_blob_oid`, and original
component IDs. Exercise gate-note scope with the same accepted source and negative
controls so accepting only `trace` cannot satisfy the tests. Required shell, YAML/Actions
and exporter/policy red-team reviewers execute concrete bypass probes before any
gate-code push. Normal capped review, security, CI and protected merge apply.

## Capacity and non-goals

Volume: two existing local specification blobs and the existing changed registry
document; no data workload. Velocity: zero provider/API/SQL calls per input row;
only existing gate-local Git/file inspection. Wall-clock: bounded by unchanged gate
ceilings and verified by the affected suite. Cost: no new scheduled or cloud work,
$0 incremental scheduled cost. No deployment, SQL, provider call, credentials,
permissions, workflow, hook, financial behavior or review-budget changes.
