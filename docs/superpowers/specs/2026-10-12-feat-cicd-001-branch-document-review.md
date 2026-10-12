---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-004, REQ-REVIEW-001]
issues: [1121]
canvases: []
done_when:
  - "tests/scripts/test_docs_audit.py exercises a real Git feature branch with changed watched code and a verified source-snapshot record: the exact reviewed code and documentation pass before merge, while changed code, changed documentation, absent evidence and an unverified stamp remain findings."
  - "tests/scripts/test_docs_audit.py exercises an actual squash merge and fresh clone, proves the reviewed source snapshot survives by exact committed source identity, and rejects unknown source identity rather than trusting an unavailable branch SHA."
  - "tests/scripts/test_docs_audit.py rejects narrowed watcher declarations, malformed or oversized records, guessed source identity, unsafe evidence paths, replacement-object ambiguity and stale source snapshots; the existing broad scripts/tests declarations remain unchanged."
  - "tests/scripts/test_spec_gate.py permits only the exact site traceability metadata and backend sections declared by the capability's approved merge-base specification, protects frontend claims and every undeclared section, and continues refusing unrelated product-document changes."
  - "tests/scripts/test_spec_gate.py proves the provenance verifier, its suite and package initialization inputs are protected CICD process files and cannot be changed by an unrelated feature to forge a review."
  - "A four-seat independent real-gate review, the unchanged BASE suite, complete affected suites and branch-versus-main documentation audit pass; no CI timeout, required check or unresolved-review rule is waived."
  - "The portable committed-source verification command records actual input count, bytes, source identity and runtime, enforces a five-second verification deadline and eight-MiB record/listing ceiling, and rejects limit breaches without trusting partial output."
  - "The FEAT-CICD-001 record and PR traceability distinguish verified branch implementation evidence from deployed-state verification, and the delivery skill/spec template describe the approved scoped workflow and mandatory post-merge main/staging close-out."
status: draft
supersedes: null
---

# Verify documentation against the source being merged

## Problem and decision requested

The existing delivery workflow requires no new documentation findings before code merges. The site matrix watches all scripts and tests. Code changes therefore create a changed-since finding, while the audit refuses a verified branch baseline because it is not on trunk. A trunk baseline cannot include those changes. Narrowing the watchers missed real dependencies and was discarded in PR1433.

The concrete source reproduction is main73457c38/site baseline303b66a3 producing no drift, while gate7f2af59e produces a new site finding. A verified branch stamp is refused as baseline-not-on-trunk; a stale trunk stamp is refused as code-drift-since-baseline. Issue1121 explains why branch SHA ancestry alone does not survive a squash merge.

This proposal changes the repository's documentation review workflow. It requires separate owner approval before implementation. It does not approve or merge an incomplete AV implementation.

## Proposed contract

Keep every existing broad watcher and every normal audit check. Add a verified source-snapshot record that binds the exact committed watched code, the exact reviewed document body, the actual source revision, the main baseline, and authenticated review evidence. Derive watched paths from the trusted merge-base registry, including additions under its directory scopes; authored lists cannot shrink coverage.

The record's source identity must survive a squash merge and a fresh clone without assuming the feature commit remains an ancestor or that its Git object remains available. Design an exact committed-source manifest/digest for that purpose and verify it against actual source blobs, including modes and paths. Do not substitute a branch name, arbitrary hash, unavailable commit or operator assertion for verification. Git replacement ambiguity and unsupported state make the proof unavailable.

Use explicit context: implementation-source review, rollout pending. This evidence does not certify the deployed site, frontend screenshots, source data freshness or production health. The post-merge main and staging close-out remains mandatory.

A changed-since finding is cleared only when the new record establishes that those exact changed source bytes and corresponding document body were actually reviewed. Unknown source, stale body, later code edits, malformed records or missing evidence remain findings. Dead references, incorrect descriptions, missing tests and other audit failures are not suppressed.

## Narrow document ownership

The only additional product document is docs/product/03-SITE-TRACEABILITY.md. A capability's separately approved merge-base specification must declare the precise component/backend sections it needs to update. The gate permits only those backend notes/source/test references plus the review metadata required by this protocol. It protects frontend claims and every undeclared section. Existing immutable specs are supplemented separately; they are not widened in place.

No blanket product-document exception is introduced. Requirement changes still land on their own docs branch; generated infrastructure output still requires the exact trusted renderer contract; catalog and issue traceability remain capability scoped.

## Implementation boundary and delivery

FEAT-CICD-001 owns scripts/maintenance/docs_audit.py, a narrow provenance verifier if needed, their existing tests, the product-scope check and its tests, and the exact delivery-skill/spec-template wording. The verifier and its initialization inputs are protected process files. An implementation plan and branch open only after this draft is approved and merged.

Use genuine Git branches, actual squash merges, fresh clones and actual gate/audit commands in tests. Synthetic successful proof dictionaries cannot establish the merge-stability requirement. Four independent gate reviewers must exercise concrete refusal/accepted controls before publication. Existing review caps, current-head reviews, green CI and conversation resolution remain binding.

## Capacity and limits

The current source tree has about1519 entries/186MiB of blobs. Scope verification uses bounded committed-source identity records; it does not buffer all blob contents or add a deployed workload. Admit at most20000 entries and eightMiB of record/listing input within a five-second whole verification deadline. Exceeding a bound is explicit unverified state. Measure cold and ordinary verification and retain actual evidence before acceptance.

New Cloud Run jobs, schedulers and vendor calls: zero. Hosted-runner incremental cost: zero on the existing public-runner allocation; measured wall-clock remains required. The unrelated full-render60second/512MiB and registry285second limits remain binding in their own contract.

## Risks and exclusions

Forged review records, silently reduced watch scope, stale code or documentation, unsafe paths, object replacement, source commits disappearing after squash, and implementation review being mistaken for deployment are the principal risks. The mandatory negative and fresh-clone tests must reject each. This proposal supplies no approval to ignore a P1 finding, fabricate source availability, relax financial causality, or activate an unverified producer.
