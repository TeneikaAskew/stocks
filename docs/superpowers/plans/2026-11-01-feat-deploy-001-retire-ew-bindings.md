---
feat_id: FEAT-DEPLOY-001
spec: docs/superpowers/specs/2026-10-31-feat-deploy-001-retire-ew-bindings.md
branch: fix/feat-deploy-001-retire-ew-bindings
pr: 1659
status: ready
---

# Retire the EarningsWhispers credential bindings from the calendar job: implementation plan

Spec #1654 merged as d3967fa773fb60409309fa4a00396826ef156e2c (squash of 3deb87a0; spec blob
5d239811, sha256 c976d36b, approved; its predecessor `2026-10-12-feat-deploy-001-av-deployment.md`
is status superseded on main). This branch forks from that commit. `gcp/deploy.sh` is byte-identical
between a79ac45d, 412e1f85 and d3967fa7, so every line anchor below is read from the fork point. The
news-owned bodies `deploy_fetch_news_sentiment`, `_topics` and `_earnings` (L3140-3227) are never
edited here; the evaluator retirement is the sibling branch `fix/feat-deploy-001-retire-ew-evaluator`
(its hunks sit at L1092, L2847-2874, L3242, L4865-4870, L5427 and L5556-5557; whichever lands second
rebases). P-B in RETIREMENT-DESIGN.md rev 3.9 sections 4, 6 and 7; RUNTIME-QUALIFICATION-PLAN.md section 1.

Rules carried: no secret is deleted, disabled, rotated or read by this branch (`ew-user` and `ew-pass`
stay as Secret Manager resources); commit messages without AI attribution; `spec_gate.py --commit` by
hand before each commit (no hook is installed in this clone and none is bypassed); no Cloud Run job,
scheduler or secret is mutated; the carried predecessor done_when items that name the absent
`tests/gcp/test_deploy_av_remediation.py` are not this change's scope (design decision D8).

## Task 1: differential baseline and red tests
Spec: done_when[27], done_when[28], done_when[29]; advances all three.
- [ ] Create `tests/gcp/test_deploy_ew_bindings.py` with a recording `gcloud` stub whose
      `secrets versions access` answers sentinel values for `ew-user` and `ew-pass`, function bodies
      extracted by name from a given `deploy.sh` text (the harness shape of
      `tests/gcp/test_deploy_ew_evaluator.py`).
- [ ] Differential tests read the baseline from `DEPLOY_BASELINE_REV` and skip when it is unset
      (same reasoning as the evaluator branch: a merge-base comparison is this pull request's
      evidence, not a permanent unconditional test): the calendar create and update argv equal the
      baseline's once the baseline's `,EW_USER=…,EW_PASS=…` suffix is removed from `--set-env-vars`;
      the three news bodies are byte-identical to the baseline. Run with
      `DEPLOY_BASELINE_REV=d3967fa773fb60409309fa4a00396826ef156e2c` for the PR body.
- [ ] Hermetic tests, red on the fork point: both `run jobs create|update fetch-earnings-calendar`
      argv carry `--set-env-vars` equal to `ENV_STRING` and name neither `EW_USER` nor `EW_PASS`;
      no argv is `secrets versions access … ew-user|ew-pass`; no sentinel appears in any argv or
      stdout; `_dispatch_arms()["earnings-calendar"]` exists and its closure creates exactly
      `fetch-earnings-calendar`, naming neither `backfill_watchlist` nor `deploy_fetchers`;
      `help` names `earnings-calendar`; the arm is not in the `_NEEDS_DEPLOY_CREDS=0` list and sets
      no `_PIN_AFTER=0`; `fetchers)`, `deploy_fetchers`, `backfill_watchlist` and the exemption list
      are byte-identical to the baseline (differential).

## Task 2: the deploy.sh edits
Spec: done_when[27], done_when[30]; advances both and turns Task 1 green.
- [ ] In `deploy_fetch_earnings_calendar` (L2791-2818) delete `local ew_user ew_pass ew_env`, the two
      `_secret` reads and the `ew_env` composition (L2793-2796); both `--set-env-vars "${ew_env}"`
      become `--set-env-vars "${ENV_STRING}"`. Every other argument stays.
- [ ] Add `    earnings-calendar) _run build_image deploy_fetch_earnings_calendar ;;` after
      `fred-rates)` (L5426) and one help line beside `fred-rates` (L5555) naming `earnings-calendar`.
- [ ] `pytest tests/gcp/test_deploy_ew_bindings.py tests/gcp/test_deploy_reachability.py
      tests/gcp/test_deploy_image_pinning.py -q` green, reachability and pinning unchanged.

## Task 3: RUNBOOK and the implementation-source note
Spec: done_when[31] (RUNBOOK), frontmatter `site_source_notes: [SHARED-07]`; advances done_when[31].
- [ ] `RUNBOOK.md` Step 7 (L433): `ew-user / ew-pass` listed as retained and unused since this change,
      with no job that reads them; no deletion instruction.
- [ ] After the code and tests are committed, `python3 scripts/maintenance/doc_source_snapshot.py
      produce --policy-ref origin/main --source-ref HEAD` to write
      `docs/review-evidence/site-source-snapshot.json`, then append the `| FEAT-DEPLOY-001 | SHARED-07 |
      source_identity_sha256=…; … |` row to the `## Implementation-source notes` table of
      `docs/product/03-SITE-TRACEABILITY.md` (implementation and local tests only; rollout pending).
      Record what the gate's `gate_note_scope` says if it refuses the first shape.

## Task 4: catalog and traceability records, gates, PR
Spec: done_when[33]; advances done_when[33] and done_when[30]'s "no mutation" clause by linking the operator step.
- [ ] `02-FEATURE-CATALOG.md` FEAT-DEPLOY-001: Status notes the binding retirement, Last reviewed is the
      head commit date; `12-PR-ISSUE-TRACEABILITY.md` lineage gains this PR and the spec PR #1654; set
      `pr:` here once the draft PR exists.
- [ ] Full suite as the sandbox allows; `spec_gate.py --pr main HEAD`; `export_model_registry.py
      --check --rev HEAD --base main`; tell the news thread the exact hunks before the push.
- [ ] Draft PR body: the hunks; red and green output; the differential run; capacity (no new job,
      the calendar job's env shrinks by two names); RUNTIME-QUALIFICATION-PLAN.md section 1
      (`./gcp/deploy.sh earnings-calendar` after merge with explicit authorization, then a
      names-only `describe` of the job env, never the whole env object) linked as separately
      authorized close-out; rollback by the previous digest. No hosted review is requested by this branch.
