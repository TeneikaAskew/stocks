---
feat_id: FEAT-DEPLOY-001
spec: docs/superpowers/specs/2026-11-01-feat-deploy-001-retire-ew-evaluator-source-note.md
branch: fix/feat-deploy-001-retire-ew-evaluator
pr: 1658
status: ready
---

# Retire the evaluate-ew-strikes deployment: implementation plan

Spec #1652 merged as 412e1f85996c8ce903e9183035f93fb88fa8240e (squash of 9aad003d; spec blob
6a3453b1, sha256 8a9873ae, approved). This branch forks from that commit. `gcp/deploy.sh` is
byte-identical between a79ac45d and 412e1f85, so every line anchor below is read from the fork
point itself. The news-owned bodies `deploy_fetch_news_sentiment`, `_topics` and `_earnings`
(L3140-3227) are never edited here. P-C in RETIREMENT-DESIGN.md rev 3.9 sections 4, 6 and 7.

Rules carried: commit messages without AI attribution; `scripts/gate/spec_gate.py --commit` run
by hand before the first three commits (no hook was installed in that clone and none was bypassed); from
the merge of main that rebinds this plan, commits are made with the repository hook installed (`make hooks`); no Cloud
Run job, scheduler or secret is read or mutated by this branch; `gcp/fetchers/evaluate_ew_strikes.py`,
`docs/product/05-INFRASTRUCTURE.md` and the MODEL-EWV-001 model row are other specs' work (P-I, P-J).

## Task 1: differential baseline and red tests
Spec: done_when[1] (the new test module), done_when[4] (module untouched); advances done_when[1].
- [ ] Create `tests/gcp/test_deploy_ew_evaluator.py` with a recording `gcloud` stub on `PATH`
      (the `_run` shape of `tests/gcp/test_deploy_image_pinning.py`), function bodies extracted by
      name from a given `deploy.sh` text so the same harness runs the fork-point text and the
      working tree.
- [ ] Differential tests read the baseline from `DEPLOY_BASELINE_REV` (`git show <rev>:gcp/deploy.sh`)
      and skip with that reason when the variable is unset: a comparison against a merge base is
      this pull request's evidence, and a permanent unconditional comparison would refuse every
      later legitimate `deploy.sh` change. The recorded run with
      `DEPLOY_BASELINE_REV=412e1f85996c8ce903e9183035f93fb88fa8240e` goes in the PR body.
      (a) every `run jobs` and `scheduler jobs` argv from `deploy_fetchers` and `deploy_schedulers`
      on the working tree equals the baseline's minus the calls naming `evaluate-ew-strikes` or
      `evaluate-ew-strikes-daily`, plus exactly the one `scheduler jobs describe` and one
      `scheduler jobs delete` the retirement issues; (b) the three news bodies are byte-identical
      to the baseline.
- [ ] Hermetic tests, red on the fork point before any edit: `deploy_fetchers` issues no argv
      naming `evaluate-ew-strikes`; `deploy_schedulers` issues one delete of
      `evaluate-ew-strikes-daily` and no create or update naming it; `bash gcp/deploy.sh
      evaluate-ew-strikes` exits 1, prints `RETIRED`, runs no `gcloud`; `help` names no
      `evaluate-ew-strikes`; `evaluate-ew-strikes` is in the `_NEEDS_DEPLOY_CREDS=0` list; no
      function `deploy_evaluate_ew_strikes` exists. Keep the red run's output for the PR body.

## Task 2: the deploy.sh edits
Spec: done_when[0]; advances done_when[0] and turns Task 1 green.
- [ ] Delete the `# EW strike verdict evaluator` comment and `deploy_evaluate_ew_strikes` (L2847-2874).
- [ ] Delete the `deploy_evaluate_ew_strikes` call in `deploy_fetchers` (L3242).
- [ ] Replace the `_schedule "evaluate-ew-strikes-daily" ...` call and its comment (L4865-4870)
      with the retired-schedule deletion in the existing `_unschedule ... || SCHEDULER_FAILURES=...`
      pattern (L4955-4972 shape); the unrelated comment at L4732 stays.
- [ ] Replace the `evaluate-ew-strikes)` dispatcher arm (L5427) with a stub in the
      `p7b-classifier)` shape (L5415) that echoes a `RETIRED` message and exits 1.
- [ ] Add `evaluate-ew-strikes` to the `_NEEDS_DEPLOY_CREDS=0` alternatives (L1090-1094).
- [ ] Delete the two help lines (L5556-5557).
- [ ] `pytest tests/gcp/test_deploy_ew_evaluator.py tests/gcp/test_deploy_reachability.py -q` green,
      reachability unchanged.

## Task 3: the image-pinning sample function
Spec: done_when[2]; advances done_when[2].
- [ ] In `tests/gcp/test_deploy_image_pinning.py` swap the sample function of
      `test_a_deploy_names_the_built_digest` and `test_a_deploy_without_a_build_mutates_nothing`
      from `deploy_evaluate_ew_strikes` to `deploy_fetch_fred_rates`, assertions unchanged.
- [ ] `pytest --collect-only -q tests/gcp/test_deploy_image_pinning.py` count equals the fork point's.

## Task 4: registry row and inventory re-render
Spec: done_when[3]; advances done_when[3].
- [ ] Remove the `evaluate-ew-strikes-daily` scheduler row from `docs/product/07-MODEL-REGISTRY.md`
      (L370); leave the MODEL-EWV-001 model row (L47) and `05-INFRASTRUCTURE.md` untouched.
- [ ] `python3 scripts/gate/export_model_registry.py` so `docs/product/generated/model-registry.json`
      matches, then `--check`.
- [ ] `python3 -m scripts.maintenance.doc_inventory --snapshot
      tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore
      docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md`;
      `pytest tests/scripts/test_check_generated_docs.py tests/meta/test_model_registry_consistency.py -q`.

## Task 5: catalog and traceability records, gates, PR
Spec: done_when[5] (close-out linked, no live mutation), done_when[6]; advances done_when[6].
- [ ] `02-FEATURE-CATALOG.md` FEAT-DEPLOY-001: Status notes the evaluator retirement, Last reviewed
      is the head commit date; `12-PR-ISSUE-TRACEABILITY.md` FEAT-DEPLOY-001 PR lineage gains this PR
      and the spec PR #1652; set `pr:` here once the draft PR exists.
- [ ] `make test`; `python3 -I scripts/gate/spec_gate.py --pr main HEAD` with PR_HEAD_REF and
      PR_BASE_REF; `python3 scripts/gate/export_model_registry.py --check --rev HEAD --base main`.
- [ ] Draft PR body: the six hunks; red and green test output; the differential run; capacity
      (nothing scheduled, a 23:00 ET job is removed); RUNTIME-QUALIFICATION-PLAN.md section 2
      (pause, delete scheduler, delete job) linked as separately authorized close-out, to be
      complete before the FEAT-DATA-001 module-shim image ships; the 05-a reconcile block and
      the daily verifier will report the live job and scheduler until that close-out runs.
      No hosted review is requested by this branch.

## Task 6: source identity (SHARED-07)
Spec: done_when[7]; advances done_when[7]. Rebinding: spec #1666 (merged as 751a6c13, blob 77ebcc18,
approved) supersedes the 2026-10-31 spec and declares `site_source_notes: [SHARED-07]`; this plan is
re-pointed to it in the same commit that merges main.
- [ ] Add or update the `FEAT-DEPLOY-001` / `SHARED-07` row of the SITE Implementation-source notes
      table with the prefix `source_identity_sha256=<current source hash>; ` and prose describing only
      this PR's `gcp/deploy.sh` retirement and its tests; no other SITE byte changes.
- [ ] From the committed HEAD, `python3 -m scripts.maintenance.doc_source_snapshot produce`, then
      `verify` with the fixed ceilings; commit the sidecar produced from the final committed SITE body,
      replacing the sidecar record the merge of main carries.
- [ ] Matched main and branch `scripts/maintenance/docs_audit.py` runs report no finding main does not;
      `pytest tests/scripts/test_doc_source_snapshot.py tests/scripts/test_docs_audit.py -q` unchanged and
      green; `docs/DOC_REGISTRY.md` blob, mode and type equal main's.
- [ ] Repeat after every further merge of main. The renderer (#1660 stage 3) and runtime close-out
      (RUNTIME-QUALIFICATION-PLAN.md section 2) stay separate gates; nothing here deploys.
