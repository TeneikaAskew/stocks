---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-04-feat-cicd-001-capacity-fixture-bridge-whole-job.md
branch: feature/feat-cicd-001-capacity-bridge-whole-job
pr: 1713
status: ready
---

# Capacity fixture bridge (test only) implementation plan, re-cut under the whole-job spec

> For agentic workers: use superpowers:executing-plans. Every task cites a spec section and the done_when item it advances.

**Goal:** make `tests/scripts/test_spec_gate.py` carry an explicit same-value `Cost` carrier beside every historical `30` carrier in the eight capacity-bearing functions, with a frozen BASE case oracle and a pre-dispatch pair guard, so the later strict Cost parser can pass main's unchanged suite. The gate, template, pins, workflows and hooks stay byte-identical. This PR says "fixture compatibility delivered; Cost parser correction pending", never "capacity defect fixed".

**Spec:** `docs/superpowers/specs/2026-11-04-feat-cicd-001-capacity-fixture-bridge-whole-job.md` (approved, merged by #1710 as a7b49bd9). It supersedes `docs/superpowers/specs/2026-10-13-feat-cicd-001-capacity-fixture-bridge.md` (#1473, 1aa3e474), whose 285 s clause unchanged main cannot meet (#1707) and whose matched docs audit needs solyra access (#1708); every other obligation is inherited word for word. Predecessors on main: Gov verifier CODE (#1470, 7e5cb49e) and compatible Counter CODE (#1538, a5749d4c).

**Lineage.** Re-cut of #1706 (branch `feature/feat-cicd-001-capacity-fixture-bridge`, head 358adad8), whose plan bound the Oct 13 spec and cannot be re-pointed (the gate: a plan on the base binds one spec). The test file here is byte-identical to #1706's reviewed candidate (sha256 fd6d4e32…, suite blob 9387d37c): two four-seat red-team passes, Codex code and security reviews with no findings on 358adad8, and the hosted attempts recorded there all describe these exact bytes.

**Base:** main a7b49bd9 (suite blob d486f304 and gate blob ffb1ada8 unchanged since the capture on 1fb97576). One branch, one PR, one author.

**Intake evidence (2026-11-04, main 1fb97576, this clone; the suite and gate blobs are unchanged on a7b49bd9):** 155 real gate invocations across the eight functions, 8 passed, 41.63 s local; 17 carrier-bearing cases from 14 fixture literals (the blank carrier on L1307, 12 filled or deferred inline literals, and one composed by the nested-heading fixture's replace on L1320); pre-fix controls show the old gate accepts `Cost: $999` beside `30: $0.01` and refuses a Cost-only body as "leaves 30 blank". Files: `intake/M1-oracle-capture.jsonl`, `intake/RED-controls.jsonl`, `intake/INTAKE-RECEIPT.md`. The author re-captures on the actual fork commit; this intake is a reference, not the oracle.

## Global constraints

- Only `tests/scripts/test_spec_gate.py` changes among source and test files (14 legacy literals: the blank L1307, 12 inline and the nested-heading replace on L1320); `scripts/gate/`, `.github/`, `.githooks/`, every other test and every other SITE/product byte equal main (asserted by `git diff --stat origin/main -- scripts/gate .github .githooks` being empty).
- No new file, workflow, harness, gate call, skip, decorator, regex-accepts-anything assertion, HEAD-derived expected value, import of `CAPACITY_LABELS`, monkeypatch of the production gate or test-aware environment.
- Every original case executes once through the existing real CLI; the oracle and pair comparison piggyback those executions.
- New code sits beside the eight functions (between L1297 and L3830 on 1fb97576), not at end of file, to stay clear of #1700's hunks.
- The dual carrier is appended AFTER the legacy carrier on the same line (measured: a `Cost: TBD` placed before `Wall-clock`'s end changes that case's class to "defers Wall-clock" on the unchanged gate).
- One push, after four empty red-team seats. No `@codex review` is posted by the author; the review route is the owner's D2 decision.

## Task 1: authoritative BASE case capture (M0, M1)
Spec: § Executable authoritative BASE case and paired-carrier comparison. Advances done_when[0], done_when[2].
- [ ] Record fork commit SHA, `git rev-parse HEAD:tests/scripts/test_spec_gate.py` and `HEAD:scripts/gate/spec_gate.py`.
- [ ] Run the eight functions through the real CLI once with the capture plugin (`intake/capture_plugin.py`, logging only); record per function: case order and count, `--pr` operands, `PR_HEAD_REF`, `PR_TITLE`, `PR_DRAFT`, changed files, `PR_BODY`, returncode, exact Capacity message or `spec gate ok`.
- [ ] Record the newest hosted registry time of main's unchanged suite for this base (today: 272.43 s on 1fb97576, job 126624403603), or "no hosted sample for this main".
- [ ] Stop and report if any case no longer reproduces today's verdict.

## Task 2: oracle, guard and the first function (slice 1)
Spec: § Executable authoritative BASE case; § Exact design and allowed literal changes. Advances done_when[0], done_when[2].
- [ ] Embed the frozen literal oracle (bounded; normalises only the two BASE/HEAD operand SHAs and the suite's generated catalog-review date, replaced by `{TODAY}` in fixture files, bodies and reason lines, with the body count recorded and the file counts folded into each case's files identity; no temp path occurs in any case).
- [ ] Add the module-scope pre-dispatch pair guard and per-function finalizer; wire into `test_a_workload_change_carries_its_capacity_numbers` only.
- [ ] RED: with the guard wired and the carrier absent, the guard refuses before any gate subprocess (zero subprocesses, asserted).
- [ ] GREEN: L1307 gains ` · Cost:` (blank beside blank), L1312 and the nested-heading replace on L1320 gain ` · Cost: $0.01` after the legacy carrier; L1309 asserts the original string OR the identical string ending `, Cost blank`; the function passes with every original returncode and message.
- [ ] Commit locally (no push): `test(gate): bridge capacity fixture for the first workload function`.

## Task 3: the remaining seven functions (slices 2 and 3)
Spec: § Exact design and allowed literal changes. Advances done_when[0].
- [ ] Wire the finalizer into the other seven functions; add same-value carriers at L1557, L2220 (`Cost: TBD`), L2223, L2226, L2326, L2329, L3625 (`Cost: $0`), L3656, L3658, L3695, L3821 (`Cost: see issue 42`); keep `×` escapes where the line uses them and the UTF-8 `×` where it does.
- [ ] Diagnostic alternatives at L2222 and L3823 only (`..., 30` OR `..., Cost`), both strings literal.
- [ ] Leave untouched: the `### $/run × runs/day × 30` heading case in function 1, every `n/a: x` fixture, L2214's docstring, and every unrelated numeral 30.
- [ ] Full gate suite passes with the same case count; every original case executed once (155, the capture's count); the suite's TODAY is normalised to `{TODAY}` in fixture files, bodies and reason lines so the oracle holds on every day (a generated catalog-review date, the one normalisation the spec allows besides the two SHA operands).

## Task 4: the equivalence regression (slice 4)
Spec: § `test_capacity_bridge_case_and_carrier_equivalence`. Advances done_when[2].
- [ ] Vectors: Cost999 vs legacy 0.01 and vs 300; both carriers changed to 999; missing, duplicate and reordered carrier (a Cost carrier on the next line or before the legacy one is refused as unpaired); removed, replaced and duplicated original rejection or missing-label case; matching valid, blank, invalid and zero controls.
- [ ] Assert zero gate subprocesses on every pre-dispatch failure and the exact old verdict/failure class on every valid vector through the unchanged real gate; assert the oracle's keys are exactly the eight module-level functions with no marks and that it holds the 155 BASE cases (a renamed, removed or marked function would otherwise switch its guard off silently). Helpers stay module scope: the gate refuses `return` or `raise` nested inside a test.
- [ ] Full suite and `tests/scripts/test_export_model_registry.py` pass; local wall time and per-test durations recorded (reference only).

## Task 5: controls, bytes and budget (M2, M3)
Spec: done_when[1]. Advances done_when[1].
- [ ] Real full-SHA `--pr BASE HEAD` controls on an actual repository with bridged fixtures: existing success and refusal behaviour preserved.
- [ ] `git diff --stat origin/main -- scripts/gate .github .githooks` empty; template sha256 unchanged (496bc1e3… on 1fb97576).
- [ ] Frozen head: four independent gate-review seats (shell; YAML/Actions; exporter and policy documents; byte controls), each bypass proven against the real gate, one correction batch, repeated until empty.
- [ ] One push. Every hosted registry attempt on the exact head recorded with head, pytest and whole-job times against main's measured spread; the job must pass within its unchanged 360 s timeout; the added test within 15 s in one local `--durations=0` run on the exact head; 285 s recorded as UNMET.

## Task 6: records, source note, audits, review, close
Spec: § Acceptance, delivery and four-task boundary; done_when[3], done_when[4].
- [ ] FEAT-CICD-001 catalog record: Status clause ("fixture compatibility delivered; Cost parser correction pending") and Last reviewed; traceability lineage entry.
- [ ] `(FEAT-CICD-001, SHARED-01)` row: `source_identity_sha256=<current>` prefix, prose for this change and its tests, earlier content kept after "Earlier:"; sidecar produced from the final committed body and committed; `verify` identity-matched from the committed HEAD.
- [ ] Sidecar `verify` identity-matched on the head; the matched `docs_audit.py` run is tracked in #1708 (solyra access) and does not gate this PR; registry blob, mode and type equal main's.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` with the PR body, Draft and Ready modes.
- [ ] Current-head review as CLAUDE.md 2.5 counts it, or the owner-recorded substitute (D2); zero unresolved threads; green CI; merge. Post-merge `status: done` on a `docs/` branch.
