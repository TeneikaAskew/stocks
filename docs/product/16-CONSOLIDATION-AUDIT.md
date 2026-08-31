# Plan Consolidation and Preservation Audit

**Verified:** 2026-08-31 · **Owner:** TBD · **Canonical PR:** [#931](https://github.com/TeneikaAskew/stocks/pull/931)

## Direct answer

The Claude rebuild was folded into the canonical plan without dropping a product record. PR #924
was **not copied byte-for-byte into `docs/product/`**: it remains the upstream, single-owner
workstream manifest. Its identifiers and relationships were cross-checked and retained here, while
its full narrative remains in `docs/audit/2026-08-27/issue-reconciliation.md` on PR #924. Therefore:

- **Claude rebuild:** byte-compared and semantic differences reviewed.
- **PR #924:** every issue reference is represented, including the ten closed duplicates; the
  447-line source file itself is linked rather than duplicated.
- **Not yet final upstream:** PR #924 has unresolved review feedback. Those proposed corrections
  are recorded below as pending and must not be presented as accepted workstream policy.

## Immutable source snapshots

| Source | Snapshot | Scope | Byte evidence |
|---|---|---|---|
| Claude rebuild | `826ca943dafb5b6ca2062b8575e90ab86bea05eb` | 17 `docs/product/*.md` files | `git diff --no-renames <sha> -- docs/product/` plus per-file SHA-256 |
| PR #924 | `33dc3ccbb14a576295c0dcc42b8a2aa3734f7321` | `docs/audit/2026-08-27/issue-reconciliation.md` | 447 lines, 73,447 bytes, SHA-256 `11ce7a95683f29925aeaed0bdfb21442865235639c1e4444217e5fd3321ebe45` |
| Canonical plan | PR #931 head | `docs/product/` | validated by the checks below |

At this snapshot, 8 Claude files are byte-for-byte identical. Nine differ because the canonical
copy contains reviewed corrections or newer state. Every changed hunk was inspected; the allowed
change classes are: endpoint completeness, issue/count synchronization, derived-table producers,
canonical ownership, #943 tracking, current baseline metadata, PR #924 duplicate preservation,
and removal of the resolved canonical-plan question. A byte difference is not treated as proof of
semantic preservation; the section checks below provide that second layer.

## PR #924 preservation crosswalk

| PR #924 section | Canonical retention | Validation | Result / exception |
|---|---|---|---|
| Method and classification | [12 § Coverage and method](12-PR-ISSUE-TRACEABILITY.md#coverage-and-method) | reviewed narrative and source precedence | Retained by reference; not duplicated |
| Totals | [12 § Reconciliation](12-PR-ISSUE-TRACEABILITY.md#reconciliation-with-the-audit-remediation-workstream) | recomputed open/canonical/pre-audit/post-audit counts | Reconciled; counts intentionally differ by scope |
| Complete canonical mapping | [12 § Full open-issue map](12-PR-ISSUE-TRACEABILITY.md#full-open-issue-map-by-capability) | set comparison of GitHub issue URLs | Every PR #924 issue reference present |
| Duplicate records | [12 § Closed duplicate records](12-PR-ISSUE-TRACEABILITY.md#closed-duplicate-records-retained-from-pr-924) | exact duplicate→canonical pair comparison | 10 of 10 retained |
| Formal issue relationships | [12](12-PR-ISSUE-TRACEABILITY.md) and live GitHub links | issue-link set comparison | Identifiers retained; GitHub remains authoritative |
| Withdrawn/superseded/unticketed findings | [07](07-MODEL-REGISTRY.md), [12](12-PR-ISSUE-TRACEABILITY.md) | reviewed against corrected #812/gamma record | Material correction retained; full prose remains upstream |
| Material disagreements | feature/model trust fields | manual semantic review | Retained where they change trust; upstream prose linked |
| PR delivery strategy and rules | [13](13-ROADMAP.md), [14](14-WORK-BREAKDOWN.md) | stream/phase/dependency comparison | Retained as plan sequencing; #924 owns stream membership |
| Remediation/deployment state | [12 § Remediation status](12-PR-ISSUE-TRACEABILITY.md#remediation-status-2026-08-30-1755) | PR/issue state checked via GitHub | #818/#816/#812/#940 state retained |
| Findings outside canonical 105 | [12](12-PR-ISSUE-TRACEABILITY.md) | open-issue set comparison | #940 and #943 retained |
| Review queue/governance notes | [12](12-PR-ISSUE-TRACEABILITY.md) | manual review | Linked, not duplicated; upstream review state remains authoritative |

### What is deliberately not duplicated

The 447 lines of PR #924 are not pasted into a second `docs/product` file. In particular, its
per-finding Claude/Codex source citations, `Claude review requested?` cells, conversation template,
and full withdrawn-statement prose remain in the manifest. This avoids two editable copies. They
are **not lost**: the manifest is linked, pinned above by commit and hash, and its issue/link set is
checked. Once PR #924 merges, that exact file should live beside the product plan on the default
branch.

## Pending PR #924 review findings

PR #924 is currently blocked by unresolved review feedback. These findings are preserved here so
consolidation cannot make them disappear, but they are not accepted policy until #924 addresses
and resolves them:

1. Gate PR-C research validation on repaired PR-A data semantics and PR-F/PR-G replay paths.
2. Gate PR-E risk-control validation on a replay path that demonstrably engages the cap.
3. Unify or explicitly depend the shared freshness primitive spanning #833, #863 and #922.
4. Inventory candidate commits and recoverability before scheduling remediation work.
5. Use an available manual review process rather than promising the unavailable #932 responder.
6. Gate PR-B gamma validation on repaired #825/#826 input semantics.
7. Gate replay-dependent portions of PR-D execution parity on PR-F while leaving an independently
   measurable #815 counterfactual unblocked.

## Section-by-section validation

| Canonical section | Evidence compared | Validation method | Outcome |
|---|---|---|---|
| README / master matrix | feature IDs, routes, endpoints, jobs, relations, model/node and issue totals | cross-document counts and link targets | Primary index synchronized |
| 00 Product overview | route graph, API/job/data/model inventories | architecture nodes checked against 03–08 | No inventory category omitted |
| 01 Requirements | repository incident rules and acceptance gates | unique `REQ-*` scan; Rule 0/2.5/3.6/3.7 presence | Gates retained |
| 02 Feature catalog | full issue map and code traceability | feature-ID set and per-capability issue-count comparison | 26 capabilities synchronized |
| 03 UI screens | `platform/src/App.tsx`, route components, Playwright/Vitest files | route-set and named-test comparison | 15 routed surfaces retained |
| 04 Backend/API | all FastAPI and Discord decorators | Python AST, including multiline decorators; route/method set comparison | 92 platform + 2 Discord endpoints |
| 05 Infrastructure | uncommented Cloud Run job commands and Scheduler commands | name-set extraction; create/update/scheduler review | 67 jobs and 58 schedulers documented |
| 06 Data architecture | comment-stripped schema plus runtime `CREATE TABLE`/writers | relation-set, producer and consumer scans | 64 declared relations; runtime magnitude table called out |
| 07 Model registry | deterministic/ML/LLM implementation paths and audit findings | path existence, lifecycle/status and recommendation review | Negative/invalid models retained |
| 08 AI architecture | `lib/agents/orchestrator.py` | analyst/risk/node roster and edge review | six analysts, three risk personas, full current graph retained |
| 09 Security/auth | middleware, deploy defaults, handlers and UI auth | mode/default/open-prefix/perimeter comparison | auth layers and #943 exposure retained |
| 10 Operations | watchdog/jobs/issues/incidents | evidence/status review; proposed SLOs kept distinct | Current versus target remains explicit |
| 11 Code traceability | feature catalog IDs and referenced paths/tests | feature-set equality and filesystem existence | Every capability has a locus |
| 12 PR/issue traceability | live open issues, PR API, PR #924 | live set equality and PR #924 reference-set comparison | 120 open issues plus closed duplicates retained at snapshot |
| 13 Roadmap | feature IDs, issue dependencies, audit trust gates | phase/gate/dependency review | Phases 0–7 retained |
| 14 Work breakdown | epics, features, requirements, issues, PRs, code, tests | required-chain field review | Delivery chains retained |
| 15 Open decisions | Claude rebuild and unresolved owner choices | row comparison | Canonical-plan question removed only because resolved; product decisions retained |

## Repeatable acceptance checks

A future consolidation is acceptable only when:

1. `git diff` against each pinned source is reviewed hunk by hunk; a count comparison alone fails.
2. Every PR #924 issue URL is present in the canonical traceability corpus or explicitly classified
   as a closed duplicate, withdrawn statement, or documentation-only finding.
3. The live open-issue set equals the canonical full open-issue map.
4. AST-extracted endpoint method/route pairs equal the API inventory.
5. Route, schema, feature, model/node, job and scheduler sets have no unexplained difference.
6. PR review findings are either resolved or recorded as pending; they are never silently treated
   as incorporated.
