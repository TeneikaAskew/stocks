---
feat_id: FEAT-STRAT-001
req_ids: [REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-DATA-004, REQ-MARKET-001, REQ-PLAYBOOK-001, REQ-REL-001, REQ-REPLAY-001, REQ-REPLAY-002, REQ-VALID-001, REQ-CAP-001, REQ-CAP-002, REQ-PERF-002]
issues: [884, 866, 907, 908, 1720]
site_source_notes: [DASHBOARD-01, INSIGHTS-08]
canvases:
  - https://claude.ai/artifact/Fg4VQHB6dFGWF9iXSJUDtg
done_when:
  - "The production candle and pattern classifiers pass the bounded existing-version truth table and invalid/gapped-input controls, with unapproved equality and pattern-glossary choices explicitly excluded"
  - "Confirmed setups use only completed coherent bars on 5m, 15m, 30m, 1h, 4h and 1w with validated session clocks; developing, missing or unresolved-anchor cases remain unconfirmed with reasons"
  - "Price versus current-period-open continuity and legacy weighted candle alignment remain separate; actual default FTFC passes append and future-perturbation invariance and the 34 exact legacy final-as-of controls without changing weights"
  - "Existing shared status/history and selected consumer adapters preserve the same as-of clock, completed/developing state, source and price-basis qualification, and explicit unavailable states without external I/O in isolated acceptance"
  - "A separately versioned captured-data foundation diagnostic and retained visual evidence demonstrate actual candle, continuity and consumer arithmetic with exact code/input hashes and explicit retrospective-vintage limitations"
  - "The affected FEAT-STRAT-001 capability and PR traceability records, focused tests and spec gate pass; the matched current-main-versus-branch docs_audit.py run, which reads solyra's issues, is tracked in #1720 and does not gate this release; that issue names the release PR, the solyra issue read access it needs from the owner, and the run once access exists; actual merge and deployed verification are separately recorded after normal release gates"
status: approved
supersedes: docs/superpowers/specs/2026-10-12-feat-strat-001-complete-state-contract.md
---

# STRAT foundation release: a tracked docs audit

## Authority

Proposed on 2026-11-05 by the FEAT-STRAT-001 delivery lane. The owner delegated delivery decisions on 2026-11-04 ("Do what you think would best benefit the project") and, asked on 2026-11-05 whether to run the docs audit themselves or track it in an issue, told the delivery lane to handle it. This file is not self-approved: it takes effect only when the owner authorizes the merge of the PR that adds it, and that merge is the approval its `status` records. It is not a finding waiver, a review substitute or a rollout.

## Problem

`docs/superpowers/specs/2026-10-12-feat-strat-001-complete-state-contract.md` (approved in #1575) makes item 6 of the foundation done_when require that the "docs audit ... pass", and its acceptance table row 6 requires "branch/main docs audits". `scripts/maintenance/docs_audit.py` reads solyra's issue states unconditionally. The sessions that push to this repository have no solyra access: adding solyra to the delivery session was refused. So the release PR (#1714) cannot meet that clause, and the gate refuses to mark it ready for review while item 6 is unticked. #1714 is otherwise complete: items 1 to 5 have evidence and every hosted check is green on its head.

#1708 records the same blocker for FEAT-CICD-001, whose successor specs (#1710) moved the audit into that issue.

## Non-goals

- No change to items 1 to 5, to any test, gate, workflow, template, hook or runtime threshold, or to the later-level obligations the predecessor preserves.
- The docs audit is not waived. It moves to #1720 and runs once solyra access exists; any new finding gets its own FEAT-STRAT-001 fix.
- No claim that the audit passed.

## Approaches considered

1. Keep #1714 in draft until the owner runs the audit or grants solyra access. That holds a finished, green release for an obligation its author cannot meet.
2. Read solyra's issues by another route. Access was refused; going around that refusal is not an option.
3. Chosen: the same route as #1710. Track the matched audit in #1720 so it no longer gates the release, and keep every other item and check.

## Design

The done_when list is the predecessor's list, item for item. Items 1 to 5 are byte-identical to the predecessor. Item 6 changes only in its audit clause: "focused tests, docs audit and spec gate pass" becomes "focused tests and spec gate pass", followed by the #1720 tracking clause. Its last clause, "actual merge and deployed verification are separately recorded after normal release gates", is unchanged.

Every other section of the predecessor applies word for word, except this clause, which this spec overrides:

| Predecessor line | Clause | Replaced by |
|---|---|---|
| 330 (acceptance row 6) | "Run affected focused suites, registry exporter, branch/main docs audits and `python scripts/gate/spec_gate.py --pr origin/main`" | "Run affected focused suites, registry exporter and `python scripts/gate/spec_gate.py --pr origin/main`"; the branch/main docs audit is tracked in #1720 |

Line 574 sits in the predecessor's "Preserved earlier full-contract acceptance, NOT COMPLETED" section. It is a preserved record, not an active foundation checkbox, and stays as it is. The predecessor's `site_source_notes` (DASHBOARD-01, INSIGHTS-08), canvases and requirement IDs carry over unchanged. The predecessor stays on main, unchanged except its status-only move to `superseded` in the same change, the gate's one permitted edit of an approved spec.

## Capacity and cost

- **Volume and velocity:** unchanged from the predecessor.
- **Wall-clock:** unchanged from the predecessor.
- **Cost:** $0 new GCP workload, schedule or resource.

## Risks

- **The docs audit could find something** once it runs. #1720 holds it open; a finding gets its own fix, and this spec does not claim the audit passed.

## Validation and rollout

1. This spec-only change, on branch `docs/spec-feat-strat-001-tracked-docs-audit`, holds this file and the predecessor's status-only change.
2. It passes `python3 scripts/gate/spec_gate.py --pr origin/main` and normal review, and merges only on owner authorization.
3. #1714 then re-binds its plan and SITE notes to this spec and updates its PR body's done_when list.
4. No production action.
