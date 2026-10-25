---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-10-24-feat-cicd-001-review-alignment.md
branch: feature/feat-cicd-001-review-alignment
pr: 1583
status: ready
---

# Agent review alignment implementation plan

> For agentic workers: use superpowers:executing-plans with one writer and read-only acceptance/review cohorts. No worker other than the designated writer publishes shared files.

**Goal:** Make the existing agent instructions consistently apply the approved blocking, disposition, review-effort and owner-escalation rules.

**Architecture:** Policy-only alignment across the six existing instruction surfaces. A writer-maintained evidence record captures actual instruction-compliance exercises and existing executable regression results. This adds no automated review controller and cannot prove live durability.

**Tech Stack:** Markdown policy, Git/GitHub lineage records, existing Python pytest/gate/generator checks.

**Spec:** docs/superpowers/specs/2026-10-24-feat-cicd-001-review-alignment.md

## Execution hold

This plan must be reviewed before policy edits begin, as the writing-plans skill requires. The approved spec must first be present on actual main. A schema status of ready does not waive either prerequisite. All implementation PRs remain drafts; no implementation merge, deployment or production write is authorized.

Budget continuity is preserved without an extra pre-implementation approval gate. The approved spec's Status and authority section says existing instructions govern until the policy changes land. Therefore this delivery continues under current main's review rules, including its two-round per-PR cap; the proposed four-pass lineage policy is the implementation target, not an already-active controller. Record #1577's two external code reviews, its security review and known internal effort in the linked history; do not erase, relabel or reset any prior pass. Preserve the same root across #1577 and #1583 in the evidence ledger. Missing historical identities remain explicitly unknown. Before any later work relies on an allowance under the newly adopted lineage policy, use its owner-adjudication rule rather than asserting a fresh balance. This transition does not grant additional rounds under current policy, waive required reviews or reset replacement/split PR history.

## Global Constraints

- One named writer owns the branch and shared evidence. Other agents are read-only.
- P0/P1 and unmet mandatory acceptance, security, data-integrity, capacity and no-fallback protections block. Do not silently change severity.
- Initial review is complete; later verification covers findings, changed semantics and affected dependencies. Genuine late defects are reported.
- Implementation target: four declared judgment passes per lineage, at most two external code-review rounds, including pre-push judgment work. Cancelled reservations remain spent; replacement and split PRs share the balance. Extensions require explicit owner adjudication and distinct aggregate/external allowances. Until that policy is adopted, current main governs this delivery; retain all history for the transition.
- No automatic merge or re-cut merely because a round ends. Required current-head external CODE review, CI, conversation resolution and existing protections remain mandatory.
- No gate implementation, pinned workflow, timeout, dependency or generated-inventory allowance changes.
- No documentation migration, STRAT/options/fixture changes, external Claude contact or automatic issue closure.
- Solyra needs its own approved and landed specification, reviewed plan and draft implementation PR; this stocks plan cannot bypass those gates.

## Review Focus

1. A P2 that fails mandatory acceptance must block, despite the lower badge (Task 2/C4).
2. Punctuation in a glob or normative requirement must not be classified by a blanket cosmetic whitelist (Task 2/C2).
3. A replacement PR, cancelled pass or partial parallel cohort cannot erase effort or findings (Task 2/C6-C8).
4. An output hash precheck cannot be described as atomic exclusion, and handoff cannot proceed while the prior writer is active (Task 3/C11).
5. A passing local scenario or instruction text check cannot be described as mechanical enforcement or observed production durability (Tasks 3-4/A5).

## Task 1: establish source identity and review accounting

Spec: § Complete initial review, focused verification and stable identity; § Proposed aggregate effort limit. Advances A2 and A5.

Files: create `docs/review-evidence/2026-10-24-agent-review-alignment.md`; no policy edit yet.

- [ ] Confirm the spec's actual main commit/blob, active branch ownership and no competing alignment implementation PR.
- [ ] Record one linked root for #1577 and #1583, the predecessor/spec PR, all actual passes and known/unknown effort. Do not assert a new allowance from a stage change. Preserve current main review rules during delivery and explicitly record the later adoption/adjudication boundary.
- [ ] Declare the full read-only acceptance cohort, immutable reviewed baseline and planned scope before invoking it. Reserve pass IDs before work. Record each reviewer/run separately even when in one cohort.
- [ ] Record repository head/base, spec blob, original finding IDs/URLs, pass reservations/completions/cancellations, owner decisions and remaining aggregate/external allowance. Link the two clean spec code-review receipts and security receipt as predecessor evidence.
- [ ] Commit only the plan/evidence setup after normal commit validation. Do not mark implementation acceptance complete.

## Task 2: align the existing policy surfaces

Spec: § One blocking and disposition rule; § Complete initial review; § Proposed aggregate effort limit; § Required policy surfaces. Advances A1, A2 and A3.

Files: modify `AGENTS.md`, `CLAUDE.md`, `.claude/skills/product-delivery/SKILL.md`, `.claude/commands/resolve-issue.md`, `.claude/agents/code-reviewer.md`, `.github/pull_request_template.md`.

- [ ] Capture prior-policy answers for C1-C9 using exact diffs and histories in the evidence record. Ask read-only participants for decisions before showing expected answers. Record contradictory/unknown baseline decisions rather than inventing executable failures.
- [ ] Make AGENTS.md the common blocking/disposition and lineage-accounting reference. Preserve full first-review scope, REQ-GOV-003 classification, browser/API proof and repository-specific rules. Replace the ambiguous reviewer pronoun.
- [ ] Align CLAUDE.md cap, pre-push judgment accounting and Rule 2.5. Preserve authentic current-head CODE review and first-review receipts; replace compulsory recuts with recorded owner escalation at the allowance limit. Tests/checks themselves do not consume judgment passes.
- [ ] Align all related resolve-issue step 2/4/5/6 and downstream close-out references, not only the stale paragraph. Never automatically fix/push/request another review after the limit; never resolve a real blocker by renaming its severity.
- [ ] Preserve product-delivery's existing substantive-spec-reapproval distinction, ordinary plan/code gates, catalog/traceability rules and exact generated-inventory allowance. Amend only contradictory review/exhaustion instructions.
- [ ] Add the CRITICAL=P0, HIGH=P1, MEDIUM=P2, LOW=P3 mapping while retaining original labels and owner-only adjudication of absent/conflicting severity. Update the PR checklist to use the same precedence and escalation rules.
- [ ] Search every occurrence of review cap, repeat-until-empty, split/re-cut and severity language in active policy for contradictions. Historical evidence is not rewritten.
- [ ] Run the same C1-C9 inputs under the proposed instructions in one declared acceptance cohort. Record actual decisions, missed/new SHA provenance, pass consumption and discrepancies. Do not hardcode expected decisions in a simulator and call it behavior.
- [ ] Fix substantive contradictions within the approved spec in one batch, respecting the reserved review allowance. Any changed design decision returns to owner approval.

## Task 3: prove preserved evidence and writer boundaries

Spec: § Generated evidence and shared-file ownership; acceptance C9-C11. Advances A3 and A5.

Files: modify the same policy surfaces and evidence record only; reuse existing executable tests.

- [ ] Document exclusive publication, writer-private outputs, expected branch head/output hashes, refusal on mismatch and owner-acknowledged quiescent handoff. State explicitly that hashes alone are not atomic compare-and-swap.
- [ ] Run `tests/scripts/test_spec_gate.py::test_commit_mode_freezes_a_spec_once_main_holds_it_approved`; report merged-spec immutability only. It does not authenticate approval of an unmerged spec change.
- [ ] Run the exact C10 regression controls below with `/workspace/stocks-venv/bin/python -m pytest -q` (quote parameterized node IDs). Record pinned inputs, commands, exit status and generated output hashes; compare two outputs from identical committed inputs. Preserve exact renderer ownership and resource limits.

  - `tests/scripts/test_spec_gate.py::test_complete_inventory_renders_from_merge_base_prose`
  - `tests/scripts/test_spec_gate.py::test_complete_inventory_refuses_non_renderer_prose`
  - `tests/scripts/test_doc_source_snapshot.py::test_actual_producer_and_gate_refuse_note_boundary_mutations[marker]`
  - `tests/scripts/test_doc_source_snapshot.py::test_actual_producer_and_gate_refuse_note_boundary_mutations[wrong-hash]`
  - `tests/scripts/test_doc_source_snapshot.py::test_actual_tree_policy_and_git_state_mutations_refuse[new-path]`
  - `tests/scripts/test_doc_source_snapshot.py::test_actual_well_formed_forged_identity_refused_by_verifier_and_audit`
- [ ] Use a temporary bare Git repository with two clones to observe actual non-fast-forward refusal and verify the winning remote tip is preserved. Never use the production remote for this exercise.
- [ ] Give participant B read-only ownership instructions and an attempted publication request before and after A's precheck. Record B's actual refusal and unchanged file hashes. Do not substitute a script programmed to refuse.
- [ ] Present stale hash, divergent tip and active-writer handoff variants. Record holds and preservation. Do not execute a successful handoff until the required real owner acknowledgment exists; report that positive control pending if absent.
- [ ] Label each result executable regression, instruction-compliance exercise or live-process observation. Preserve failures/unknowns; do not mark live observation passed.

## Task 4: validate, publish a draft and preserve the cross-repository boundary

Spec: § Implementation sequencing and quality checks; § Observed real-PR acceptance and risks. Advances A4 and A5.

Files: update only FEAT-CICD-001 in `docs/product/02-FEATURE-CATALOG.md` and `docs/product/12-PR-ISSUE-TRACEABILITY.md`, this plan and its evidence record.

- [ ] Run the unchanged BASE and proposed HEAD spec gates. Run complete affected existing suites: `tests/scripts/test_spec_gate.py`, `tests/scripts/test_doc_source_snapshot.py`, and `tests/scripts/test_check_generated_docs.py`. Do not alter fixture coverage or assertions to obtain green results.
- [ ] Run full default documentation audits against actual baseline and proposed committed head. Compare complete finding identities, not counts alone; permit zero new findings. Preserve outputs and exact revisions in evidence.
- [ ] Keep generated evidence source-bound; repeat only checks invalidated by a later change. Inspect ordinary CI on the exact submitted head.
- [ ] Update only the owning capability record/traceability entry. Keep product deployment, mechanical enforcement and durable behavior claims explicitly unproven.
- [ ] Open the single implementation PR as draft with all A1-A5 boxes copied honestly; set this plan's PR number in the next normal commit. Do not claim cross-repository A1/A4 complete from stocks evidence.
- [ ] Prepare a matching Solyra spec through its own workflow, preserving its Lovable header, Rule 4 and hermetic browser proof. Its specification merge and plan review remain separate prerequisites; no unrelated merge is authorized.
- [ ] Record the prospective ten-lineage observation protocol: at least three real lineages per repo, actual replacement and acceptance-blocker coverage, zero lost findings/budget resets/unchecked blockers/overwrites, and measured pass/time counts. Implementation validation is not durability evidence; observation begins only after authorized rollout.
- [ ] Present results and unresolved acceptance to the owner. Do not merge implementation or waive unfinished matching Solyra work.
