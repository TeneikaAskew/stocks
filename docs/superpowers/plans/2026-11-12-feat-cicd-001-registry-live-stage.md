---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-02-feat-cicd-001-registry-ten-minute-envelope.md
branch: fix/feat-cicd-001-registry-live-stage
pr: 1838
status: ready
---

# Registry ten-minute envelope: live stage implementation plan

> For agentic workers: use superpowers:executing-plans. Every task cites a spec section and the done_when item it advances.

**Goal:** the live stage of the approved ten-minute registry envelope. `.github/workflows/registry-check.yml` becomes byte-equal to the pinned copy `scripts/gate/pinned/registry-check.yml`, which #1696 moved to `timeout-minutes: 10` on 2026-11-07. The one changed line is `    timeout-minutes: 6` to `    timeout-minutes: 10` at the `registry` job level.

**Spec:** `docs/superpowers/specs/2026-11-02-feat-cicd-001-registry-ten-minute-envelope.md` (approved parent, #1683), § Sequence step 3 and § Decision. The pin stage's primary (`2026-11-02-feat-cicd-001-registry-ten-minute-pin.md`, #1693) is delivered and not bound here.

**Why now.** From 2026-11-11 14:41Z to 2026-11-12 12:36Z, twelve registry jobs on pull-request runs ended cancelled after about six minutes (started-to-completed 6m01s to 6m15s, read from GitHub's job records): jobs 130591843070, 130645895725, 130650549940, 130652693026, 130654775451, 130738783712, 130796811112, 130868819366, 130946242736, 130986977991, 131013150515 and 131183486446. This stage is the approved remedy; it claims no speedup.

**Base:** main 75493a47. One branch, one PR, one author.

## Global constraints

- Among gate files, only `.github/workflows/registry-check.yml` changes, and only to equal the landed pin. No pinned copy, gate validator, hook, test, exporter, trigger, permission, dependency, runner, check name or other deadline changes (#1695 live-stage constraint).
- The suite stays serial and unchanged: `python3 -m pytest tests/scripts/test_spec_gate.py -q -p no:cacheprovider --noconftest`.
- No hook bypass, no history rewrite. The gate-file red-team pass runs on the frozen head before the one push.

## Task 1: the live workflow
Spec: § Sequence step 3. Advances done_when 1.
- [ ] `.github/workflows/registry-check.yml` line 25: `    timeout-minutes: 6` becomes `    timeout-minutes: 10`; `cmp` against the pinned copy reports no difference.

## Task 2: value assertions with negative controls
Spec: done_when 1.
- [ ] Record a YAML load asserting `jobs.registry.timeout-minutes` is the integer 10 at job level in both the live and the pinned copy, with negative controls failing for the key missing, the value only on a step and the value quoted as "10".

## Task 3: native pin-order and contract controls
Spec: § Sequence. Advances done_when 2.
- [ ] The real gate in PR mode passes this live change equal to the landed pin, and refuses both a live-only timeout change that differs from the pin and a simultaneous pin and live timeout change, each run as a concrete snippet.
- [ ] `tests/scripts/test_spec_gate.py` passes unchanged and serial.

## Task 4: gate-file red-team pass
Spec: § Sequence. Advances done_when 4.
- [ ] One reviewer per attack surface (shell; YAML/Actions; exporter and policy documents), each bypass proven by running the gate against a concrete snippet, on the exact frozen head; findings fixed in one batch; then one push.

## Task 5: hosted registry job
Spec: § Decision, New acceptance. Advances done_when 3.
- [ ] The exact-head registry job, now bounded at ten minutes, passes every test and the unchanged exporter with at least 120 seconds of reserve under 600 seconds; record head, base, setup, gate-step, pytest, exporter and whole-job times for every attempt, with no retry chosen for a favourable sample.

## Task 6: source identity, records and close
Spec: done_when 4.
- [ ] Update only the `(FEAT-CICD-001, SHARED-01)` SITE note row with the current source hash and prose for this stage, keeping its earlier content after "Earlier:"; produce and commit the sidecar from the final committed body; verify from the committed HEAD.
- [ ] Full-default `docs_audit.py` on main and on the head: nothing new on the head.
- [ ] Catalog and PR-traceability records; `python3 scripts/gate/spec_gate.py --pr` with the PR body.
- [ ] Current-head review as CLAUDE.md section 2.5 counts it, every required check, zero unresolved threads.
