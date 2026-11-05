---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-04-feat-cicd-001-capacity-cost-label-whole-job.md
branch: feature/feat-cicd-001-capacity-cost-label
pr: 1716
status: done
---

# Require the documented Cost capacity field: implementation plan

> For agentic workers: use superpowers:executing-plans. Every task cites a spec section and the done_when item it advances.
> One author: the lane session driving FEAT-CICD-001's capacity work. This branch is pushed only from actual main containing the bridge merged (the re-cut #1713, which replaced #1706); until then it stays local. Work authored before that merge is rebased onto that main, and the four seats re-run on the rebased head, before the one push; seats on an earlier head do not count for it.

**Goal:** the fourth `CAPACITY_LABELS` literal becomes `"Cost"`, the default PR template's one cost line becomes `- Cost: <!-- $/run × runs/day × 30 for new scheduled jobs -->`, and two real-CLI tests prove the strict contract. No alias for `30`, no other predicate change.

**Spec:** `docs/superpowers/specs/2026-11-04-feat-cicd-001-capacity-cost-label-whole-job.md` (approved, main blob 3021fe75, merged by #1710 as a7b49bd9), which supersedes `docs/superpowers/specs/2026-10-13-feat-cicd-001-capacity-cost-label.md` (merged by #1474 as 4fdbb519) and replaces only its 285 s timing clause and its docs-audit obligation. Prerequisites: bridge successor spec (#1710) AND its TEST-only CODE on main (#1713); Gov verifier (#1470) and Counter (#1538) CODE on main.

**Consumers (recorded, not owned):** the deploy EW-binding retirement #1659 (its spec's "Strict Capacity Cost prerequisite" section) and the catalyst EW re-cut under #1703's spec (consolidated CAT spec, "Delivery dependencies": the 30 label "must be corrected by its actual separate CICD owner CODE MAIN"; P1 F1 on #1703, comment 6634577378).

**Base:** actual `origin/main` containing #1713 merged. One branch, one PR, one author.

**Measured on unchanged main 1fb97576 (2026-11-04), re-run on main 178973b0 with the bridge merged (gate and template byte-identical) into `docs/review-evidence/capacity-label-baseline-controls.json` and `docs/review-evidence/capacity-label-template-controls.json`:** Cost-only numeric body refused "leaves 30 blank"; bare `30: 0.01 samples` accepted; legacy formula alone accepted; filled current template accepted; filled template with the approved Cost line refused "leaves 30 blank"; template sha256 496bc1e3… equals the spec's source hash and the one-line result hashes to 201355b3…, the spec's recorded result. On the same line, `30: $0.01 · Cost: TBD` is refused as "defers 30" by the old gate (value text runs to line end), so negative bodies in Task 2 put each carrier on its own line.

## Global constraints

- Production edits: exactly one tuple string in `scripts/gate/spec_gate.py` and exactly one line in `.github/pull_request_template.md`. `check_capacity`'s body, every other template byte, pins, workflows, hooks, verifier, renderer and policy documents equal main.
- The template is read from current main at apply time; the whole-file oracle reverses NEW to OLD and must equal main's bytes, else stop (an unexpected predecessor line is not patched over).
- Only the BASE gate in `spec-gate.yml` reads this PR's body (`registry-check.yml` passes no PR_BODY), and `check_capacity` applies only to workload paths, which this PR does not touch. The body still carries both `$/run × runs/day × 30:` and `Cost:` on separate lines, which both gates accept, so it reads correctly before and after the tuple changes.
- New tests sit beside the capacity functions; module-scope helpers only; real CLI, real Git, full-SHA BASE/HEAD; no mocked `check_capacity`.
- One push after four empty seats; review route per the owner's D2.

## Task 1: verify prerequisites and reproduce the two pre-fix defects (M5)
Spec: § Problem and actual source evidence; § Ownership, acceptance and four-task plan (task 1). Advances done_when[0].
- [ ] Record: PR-A merge commit and the suite blob on main; bridge, Gov and Counter identities; gate blob; template sha256 (must be 496bc1e3… or the diff from it is explained and the oracle re-derived).
- [ ] On unchanged bridged main through the real CLI: Cost-only numeric refused as missing 30; bare unrelated 30 accepted; filled current template accepted; filled template with the Cost line refused. Outputs go in the PR body's Verification section and in the spec's named evidence files, `docs/review-evidence/capacity-label-baseline-controls.json` and `docs/review-evidence/capacity-label-template-controls.json`.
- [ ] Registry time of main's then-current suite recorded.

## Task 2: the tuple, the template line and the strict matrix
Spec: § Exact production design; § Exact default-template oracle and process protection. Advances done_when[0], done_when[1], done_when[2].
- [ ] RED first: write `test_capacity_cost_label_contract` and `test_capacity_cost_rendered_budget_guards`; run against the unchanged gate and record the failures.
- [ ] `CAPACITY_LABELS = ("Volume", "Velocity", "Wall-clock", "Cost")`; apply the template line through the oracle; record before and after sha256.
- [ ] GREEN matrix (each case its own line layout): numeric Cost-only passes; canonical `Cost: $0.01/run x 2 runs/day x 30 = $0.60/month` passes; true zero `$0` passes; filled exact new template passes; absent, blank, unnumbered and deferred Cost refuse with the message naming Cost; bare `30: 0.01 samples` refuses; legacy formula alone refuses; numeric 30 on its own line beside blank/TBD/see-issue Cost refuses; original blank-template and HTML-hidden placeholder refuse.
- [ ] Guards preserved: numeric-leading quantities, blank-own-line, deferral, rendered HTML/comments/fences/headings, checkbox and canvas exclusions, all-fields n/a with reason, partial n/a refusal, workload path detection, non-workload body.
- [ ] Process protection: `is_process_file` still gates the template; `test_capacity_cost_label_contract` shows a docs/ branch and a FEAT-MODEL-001 branch editing it refused by the unchanged classifier.

## Task 3: suites, budget and seats (M6)
Spec: done_when[3]. Advances done_when[3].
- [ ] Full gate suite (bridged BASE cases unchanged) and `tests/scripts/test_export_model_registry.py` pass on the head; every bridged case keeps its verdict with the new tuple (the diagnostic alternatives now resolve to the `Cost` spelling).
- [ ] Four independent frozen-head seats, one correction batch, repeated until empty; one push.
- [ ] Hosted registry time on the exact head recorded with every attempt; `base-suite` (bridged main suite against this gate) green. Timing per the successor spec's done_when[3]: the job passes within the unchanged 360 s timeout, every attempt is recorded with head, pytest and whole-job times against main's measured spread, no retry selects a favourable sample, a timeout blocks completion until #1707 or the ten-minute stage lands, the two Cost tests take at most 30 s together in one local `--durations=0` run on the exact head (with its machine), and 285 s is recorded as UNMET. No cap change.

## Task 4: records, source note, audits, review, close
Spec: § Ownership, acceptance and four-task plan (task 4); done_when[4], done_when[5].
- [ ] Set this plan's `pr:` to the PR number. Catalog Status ("Cost predicate verified in source and CI; production rollout unchanged") and Last reviewed, with no other FEAT IDs on changed lines; traceability lineage entry; PR body names both consumers (#1659, the CAT re-cut) and the open workload PRs whose body has only the legacy cost line (each needs a `Cost:` line once this merges; spec-gate re-runs on `edited`).
- [ ] `(FEAT-CICD-001, SHARED-01)` row rebound with prose for the predicate and template change and its tests, earlier content kept; sidecar produced and committed; `verify` identity-matched.
- [ ] Registry blob, mode and type equal main's. Matched `docs_audit.py`: tracked in #1708 under the successor spec's done_when[4] (needs solyra read access from the owner) and does not gate this PR.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` with the PR body in Draft and Ready modes.
- [ ] Current-head review or the owner-recorded substitute (D2); zero unresolved threads; green CI; merge. Post-merge `status: done` on a `docs/` branch.
