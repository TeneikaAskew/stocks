# Plan Consolidation and Preservation Audit

**Verified:** 2026-08-31 · **Owner:** TBD · **Merged canonical baseline:** [#931](https://github.com/TeneikaAskew/stocks/pull/931) · **Open follow-up:** [#945](https://github.com/TeneikaAskew/stocks/pull/945)

## Direct answer

The Claude rebuild was folded into the canonical plan without dropping a product record. PR #924
was **not copied byte-for-byte into `docs/product/`**: it remains the upstream, single-owner
workstream manifest. Its identifiers and relationships were cross-checked and retained here, while
its full narrative now lives on `main` in `docs/audit/2026-08-27/issue-reconciliation.md` after PR #924 merged. Therefore:

- **Claude rebuild:** byte-compared and semantic differences reviewed.
- **PR #924:** every issue reference is represented, including the ten closed duplicates; the
  469-line merged source file itself is linked rather than duplicated.
- **Review feedback incorporated:** each substantive PR #924 review finding was revalidated against issue contracts, current code, tests, PR state and GitHub timelines, then converted into canonical requirements, roadmap gates, WBS prerequisites and candidate inventory.

## Immutable source snapshots

| Source | Snapshot | Scope | Byte evidence |
|---|---|---|---|
| Claude rebuild | `826ca943dafb5b6ca2062b8575e90ab86bea05eb` | 17 `docs/product/*.md` files | `git diff --no-renames <sha> -- docs/product/` plus per-file SHA-256 |
| PR #924 merged manifest | `a8e307586e86c0cf1658061e04511ebe972a44f5` | `docs/audit/2026-08-27/issue-reconciliation.md` on `main` | 469 lines, 75,580 bytes, SHA-256 `b51ab16564a72d07a02c80578b108960158424c46bbfc14488209efbe45911ff` |
| Merged canonical baseline | PR #931 merge `c93197e` | `docs/product/` on `main` | merged baseline identity |
| Byte-comparison tree | `a518585` | the 17 original requested product files after Claude consolidation corrections | exact canonical side used for the 8-identical/9-different result |
| Current follow-up | PR #945 | updates to the merged #931 baseline | open; not on `main` until merged |

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

The 469 lines of the merged PR #924 manifest are not pasted into a second `docs/product` file. In particular, its
per-finding Claude/Codex source citations, `Claude review requested?` cells, conversation template,
and full withdrawn-statement prose remain in the manifest. This avoids two editable copies. They
are **not lost**: the manifest is linked, pinned above by commit and hash, and its issue/link set is
checked. PR #924 has now merged, so that exact authoritative file lives beside the product plan on the default branch.

## PR #924 review findings — validation and incorporation

The seven substantive review findings were not accepted from prose alone. Each was checked against
current code, issue acceptance criteria, PR state and targeted tests. All seven are now incorporated:

| Finding | Evidence run/reviewed | Validity result | Canonical incorporation |
|---|---|---|---|
| PR-C must follow repaired inputs and replay/data | #825/#826, #822–#824, #905/#909 bodies; current zero-fill, `date <= cutoff`, unbounded full-frame/latest-row level load and duplicated backfill code | **VALID** — a frozen baseline before repair would canonize known-invalid inputs/cohorts | REQ-VALID-001; [13 delivery gates](13-ROADMAP.md#validated-delivery-stream-gates); EPIC 0 |
| PR-E risk controls need working replay | #818 DoD and production verification; `tests/gcp/test_signal_monitor_caps.py` | **VALID; cap-engagement gate satisfied, identity parity outstanding** — #818 closed after 15=15 counts and 969 suppressions, but those capped counts do not prove the live/replay fire sets match; #816 calibration and activation remain blocked by fire-identity comparison and #940 | REQ-RISK-001; PR-E gate records satisfied and open halves |
| #833/#863/#922 share freshness primitive | all three issue bodies and current watchdog scope | **VALID** — same stopped-writer/still-reading class; consumer policy remains separate | REQ-FRESH-002; shared PR-0 WBS prerequisite |
| Candidate/recoverability inventory before scheduling | GraphQL `CrossReferencedEvent` scan across all 105 canonical issues; PR state, files and DoD review | **VALID** — five issues have actionable/partial candidates; 100 do not; dependency mentions excluded | REQ-GOV-002; [12 candidate inventory](12-PR-ISSUE-TRACEABILITY.md#candidate-and-recoverability-inventory--verified--github) |
| Do not require unavailable automated Claude responder | #932 is closed and unmerged; no replacement workflow verified | **VALID** | REQ-REVIEW-001; manual/authenticated disposition gate |
| PR-B validation must follow #825/#826 semantics | issue contracts plus current `open_interest or 0`/gamma zero-fill paths | **VALID** — coverage/zero-fill changes the quantity being validated | REQ-VALID-001; PR-A → PR-B validation gate |
| Replay-dependent PR-D work must follow PR-F; #815 can proceed | #814/#815 and replay issue contracts | **VALID WITH SPLIT** — cross-system parity blocked; within-live stop counterfactual independent | split PR-D gate in [13](13-ROADMAP.md#validated-delivery-stream-gates) |

### Defect-validity probes

The validation suite intentionally distinguishes “tests pass” from “defect disproved.” At repository
source commit `bacc9be`, the targeted suite passed **132 tests** with this exact invocation:

```bash
pytest -q \
  tests/gcp/test_signal_monitor_caps.py \
  tests/agents/test_agent_summarizers.py \
  tests/gcp/test_signal_monitor_level_refresh.py \
  tests/lib/test_gamma.py \
  tests/lib/test_gamma_never_null.py
```

No external artifact or environment override was supplied. Pytest reported 132 passed and four
non-failing warnings (two `datetime.utcnow()` deprecations and two pandas fragmentation warnings).
This proves the selected current contracts remain stable; it does not disprove an untested boundary.
Static probes then confirmed the open boundary defects are still reachable or untested:

- `summarize_backtest_metrics` queries `date <= cutoff`, the exact #822 boundary under dispute;
- `refresh_level_map` loads the full daily frame and takes its latest row before supplying
  `analysis_date`, preserving #823's as-of concern;
- `scripts/backfill_and_replay.py` still calls `add_all_indicators` instead of the production
  fetcher, preserving #824's duplicated-pipeline concern;
- missing open interest is still converted with `or 0` in gamma/grid paths, preserving #826's
  validation dependency;
- #932 remains closed and unmerged; and #940 remains open.

These probes validate **the need for the gates**, not completion of the underlying fixes. No open
issue is marked fixed by this documentation change.

## Section-by-section validation

| Canonical section | Evidence compared | Validation method | Outcome |
|---|---|---|---|
| README / master matrix | feature IDs, routes, endpoints, jobs, relations, model/node and issue totals | cross-document counts and link targets | Primary index synchronized |
| 00 Product overview | route graph, API/job/data/model inventories | architecture nodes checked against 03–08 | No inventory category omitted |
| 01 Requirements | repository incident rules and acceptance gates | unique `REQ-*` scan; Rule 0/2.5/3.6/3.7 presence | Gates retained |
| 02 Feature catalog | full issue map and code traceability | feature-ID set and per-capability issue-count comparison | 26 capabilities synchronized |
| 03 UI screens | `platform/src/App.tsx`, route components, Playwright/Vitest files | route-set and named-test comparison | 15 routed surfaces retained |
| 04 Backend/API | all FastAPI and Discord decorators | Python AST, including multiline decorators; route/method set comparison | 92 platform + 2 Discord endpoints |
| 05 Infrastructure | uncommented Cloud Run job commands and Scheduler commands | name-set extraction; create/update/scheduler review | 76 jobs and 65 schedulers documented |
| 06 Data architecture | comment-stripped schema plus runtime `CREATE TABLE`/writers | relation-set, producer and consumer scans | 64 declared relations; runtime magnitude table called out |
| 07 Model registry | deterministic/ML/LLM implementation paths and audit findings | path existence, lifecycle/status and recommendation review | Negative/invalid models retained |
| 08 AI architecture | `lib/agents/orchestrator.py` | analyst/risk/node roster and edge review | six analysts, three risk personas, full current graph retained |
| 09 Security/auth | middleware, deploy defaults, handlers and UI auth | mode/default/open-prefix/perimeter comparison | auth layers and #943 exposure retained |
| 10 Operations | watchdog/jobs/issues/incidents | evidence/status review; proposed SLOs kept distinct | Current versus target remains explicit |
| 11 Code traceability | feature catalog IDs and referenced paths/tests | feature-set equality and filesystem existence | Every capability has a locus |
| 12 PR/issue traceability | live open issues, PR API, PR #924 | live set equality and PR #924 reference-set comparison | 121 open issues plus closed duplicates retained at snapshot |
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
6. PR review findings are reproduced and either incorporated with evidence or explicitly rejected with evidence; thread state alone is not a validity result.
7. Candidate/recoverability state is regenerated from GitHub timelines before scheduling any stream.
