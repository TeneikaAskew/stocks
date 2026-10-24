---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-10-24-feat-cicd-001-registry-read-batching.md
branch: fix/feat-cicd-001-registry-read-batching
pr: null
status: ready
---

# Registry committed read batching implementation plan

> For agentic workers: use superpowers:subagent-driven-development. Steps use checkboxes.

**Goal:** Reduce native Git dispatches without changing gate verdicts or freshness.

**Architecture:** Acquire independent committed entry content/modes in one bounded fresh helper. Only the initial changed-entry inspection and complete HEAD plan scan consume it. Any unsupported or failed acquisition discards all partial results and executes the original ordered native reads.

**Tech Stack:** Python standard library, existing pytest/PyYAML, native Git.

**Spec:** docs/superpowers/specs/2026-10-24-feat-cicd-001-registry-read-batching.md

## Global Constraints

- At most64 queries and8MiB retained payload per optimized acquisition.
- Only scripts/gate/spec_gate.py and tests/scripts/test_spec_gate.py are runtime source/test changes.
- No global cache, cross-acquisition reuse, policy_blob_bytes/check_close_out change, worker flags, dependency, workflow, pin, hook, timeout or gate weakening.
- Preserve every original case, parameter, assertion and native hook/CLI call, the unchanged serial command, registry285s, whole job300s, BASE600s, renderer60s/512MiB and verifier5s/8MiB/20000-entry limits.
- Require four frozen independent prepush reviews, authenticated external current-head review and exact-head CI; no implementation merge authority is included.

## Review Focus

- Replacement refs or repository changes must be visible in each acquisition.
- CRLF/non-UTF8 content retains native text/raw distinctions.
- Missing files, symlinks and gitlinks retain mode/refusal/short-circuit behavior.
- Index, worktree, symbolic refs and unsupported framing use original fresh reads.
- Incomplete, oversized or malformed batches discard partial results before fallback.

## Task 1: Preserve baseline and bind the draft delivery
Spec: § Delivery and authority gate and § Focused regression and acceptance contract. Advances done_when[1] and done_when[3].
- [ ] Preserve exact main gate/suite bytes and failing hosted capacity evidence privately.
- [ ] Commit this PLANONLY change through the manual gate and hook, publish one draft PR through root, then bind its real number in a second gated PLANONLY commit before CODE.
- [ ] Time the full original native serial suite without a compiled harness; retain wall/CPU and collection identities.

## Task 2: Fresh bounded acquisition, native semantics and capacity
Spec: § Design and boundaries and § Focused regression and acceptance contract. Advances done_when[0], done_when[1] and done_when[2].
Files: scripts/gate/spec_gate.py; tests/scripts/test_spec_gate.py.
Interfaces: a narrowly named helper fresh_gate_acquisition(tree: Tree, paths: list[str], *, include_modes: bool) returns a fresh ordered list of (text, mode) pairs or None to require original reads; no state persists.
- [ ] Add test_fresh_gate_acquisition_preserves_git_semantics with real SHA1/SHA256 repositories, replacement refs changed between calls, identical IDs across repos, index/worktree/symbolic targets, CRLF/non-UTF8, symlink/gitlink and missing/error cases; mocked framing faults only supplement real success proof.
- [ ] Run the focused test against pre-fix source and preserve genuine RED evidence.
- [ ] Implement the bounded helper and only the two approved callers; validate size/type/mode/framing/EOF before accepting any result, otherwise retain original ordered read path.
- [ ] Run focused GREEN and commit only after the normal manual gate and hook pass.

- [ ] Add test_gate_batching_preserves_verdict_and_dispatch_economy using the unchanged ready actionlint accepted scenario and explicit follow-up refusal, comparing baseline/proposed actual CLI verdicts and native Git dispatches.
- [ ] Preserve all original test ASTs and parameters; run focused RED/GREEN and relevant neighboring exporter/source suites.
- [ ] Run the complete unchanged native serial suite with every original case and paired baseline/proposed wall/CPU and dispatch measurements; if savings are inadequate, report the shortfall without changing limits or selecting fewer tests.

## Task 3: Owned delivery proof and independent release review
Spec: § Delivery and authority gate. Advances done_when[3] and hosted part of done_when[2].
- [ ] Update only own FEAT-CICD-001 catalog/traceability records and existing SHARED-01 implementation-source note; preserve other note context.
- [ ] Produce and independently verify fresh ordinary declared-note source proof, trusted renderer limits where applicable, full-default main/proposed no-new audit and both BASE/proposed PR gates.
- [ ] Give root frozen brief/report/diff evidence for four independent shell, YAML/Actions, exporter/policy and byte/identity/freshness review seats; fix confirmed findings in one batch, then re-review before one authorized CODE push.
- [ ] Root publishes the CODE head only after the empty prepush pass; follow actual exact-head external CODE/security review and required CI, including exporter completion, without blind retries.
- [ ] Keep this PR draft and all unproved done_when items unticked; no merge, provider or deployment action is authorized.
