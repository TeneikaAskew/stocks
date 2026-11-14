---
feat_id: FEAT-DEPLOY-001
spec: docs/superpowers/specs/2026-10-29-feat-deploy-001-news-retry-coupling.md
branch: fix/feat-deploy-001-news-retry-coupling
pr: 1671
status: ready
---

# News retry coupling implementation plan

> For agentic workers: use superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

**Goal:** Every create and update of the three NEWS jobs carries `--max-retries 0`.
**Architecture:** Three existing `gcp/deploy.sh` function bodies only; a hermetic
behavioral test executes the actual bodies with a shell-local gcloud stub.
**Tech stack:** bash, pytest.
**Spec:** docs/superpowers/specs/2026-10-29-feat-deploy-001-news-retry-coupling.md
(approved, main d806bfd1, blob 216424cb).

## Global constraints

- Edit only `deploy_fetch_news_sentiment`, `deploy_fetch_news_sentiment_earnings`
  and `deploy_fetch_news_sentiment_topics`. Preserve every other argument and the
  command ordering. Add no lines, so no later `deploy.sh` line moves.
- No gcloud, provider, SQL, image build or deployment during preparation. Source
  tests never attest a live setting or image.
- The typed-news producer (FEAT-DATA-001, #1643) stays a separate change; it is
  not copied, rebased onto or edited here.
- `gcp/deploy.sh` is shared with the EarningsWhispers retirement work: this branch
  owns only the three function bodies and lands first; that work integrates it by
  base sync.
- Review lineage is not reset (spec, Status and derivation). No review is claimed
  that has not run.

## Review focus

- A create-only fix leaves existing jobs retrying; an update-only fix leaves new
  jobs unsafe. Both branches and both env-only updates are covered.
- Only the three named jobs are addressed, and every other argument equals the
  pinned baseline call for call: main 53bc13ff since the 2026-11-13 base sync,
  b483989e before it.
- The embedded baseline is byte-pinned and re-derived from git where available.

## Task 1: Behavioral retry tests, RED on the baseline

Spec: Design, "Focused test"; advances done_when[0] and done_when[1].
Files: tests/gcp/test_news_retry_coupling.py.

- [x] Extract the actual three definitions from `gcp/deploy.sh` and execute them
  under bash with a NUL-delimited argv-recording gcloud stub; scenarios
  all-create-success (5 calls) and all-existing (8 calls).
- [x] Embed the pinned baseline bodies (b483989e lines 3140-3227) with a sha256 pin
  and a git re-derivation check; the retry controls must reject the baseline.
  Re-pinned on the 2026-11-13 base sync, as the spec's adaptation clause allows, to
  main 53bc13ff lines 3119-3205: main's #1813 removed `--remove-env-vars NEWS_TICKERS`
  from the fetch-news-sentiment update, so b483989e no longer describes main. The
  assertions are unchanged; unpatched main fails the same three retry controls.
- [x] Run `pytest tests/gcp/test_news_retry_coupling.py` on unpatched source
  (expect the three retry controls to FAIL, the shape/baseline checks to pass).

## Task 2: Zero retries on every NEWS create and update

Spec: Design, first paragraph; advances done_when[0], done_when[1], done_when[3].
Files: gcp/deploy.sh.

- [x] Change each create's `--max-retries 1` to `--max-retries 0`; append
  `--max-retries 0` to each update's existing `--region` line, including the
  earnings and topics env-only updates.
- [x] `bash -n gcp/deploy.sh`; run the focused test again (expect all PASS).
- [x] 2026-11-13 base sync: main's #1813 pins the exact news argv in
  tests/gcp/test_deploy_flag_syntax.py (`MERGE_BASE_CALLS`) with retries 1 on create and
  none on update. Its three news entries now carry `--max-retries 0` on every call, as
  the spec's adaptation clause allows; the pin stays exact and rejects unpatched main.
- [ ] Run affected deploy/inventory/news suites and the full suite.
- [ ] Commit: `fix(deploy): zero whole-job retries on the three news jobs`.

## Task 3: Rollout record

Spec: Design, "Operational release"; advances done_when[2].
Files: this plan, section "Rollout record".

- [x] Record the three-job capture, drift/active-execution refusal, retry-first,
  image-second activation and image-first rollback sequence below. It is a
  pre-merge record only; live readbacks remain post-merge.

## Task 4: Own delivery records and review

Spec: Delivery and post-merge close-out; advances done_when[3] and done_when[4].
Files: this plan; docs/product/02-FEATURE-CATALOG.md (FEAT-DEPLOY-001 record only);
docs/product/12-PR-ISSUE-TRACEABILITY.md (FEAT-DEPLOY-001 entry only);
docs/product/03-SITE-TRACEABILITY.md (one `FEAT-DEPLOY-001 | SHARED-07`
implementation-source note); docs/review-evidence/site-source-snapshot.json;
renderer-owned inventory rows that `scripts/maintenance/doc_inventory.py` derives
from the changed retry values, if the docs audit requires them.

- [ ] Open one draft PR; set `pr` here in the next commit.
- [ ] Produce the SHARED-07 note from producer preflight's source identity, commit,
  produce and verify the sidecar from the committed HEAD.
- [ ] Docs audit on this branch and on origin/main: no new finding.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main`.
- [ ] Record exact historical and current review lineage on the PR; an authorized
  independent final review, current-head CODE/SEC review and CI before release.

## Rollout record

Source tests alone never attest any live setting or image. This sequence runs only
after the source merges and only under separately authorized release execution by
the existing GCP operator. It is not a blanket `./gcp/deploy.sh` target and never
replays a provider call or a job by hand.

1. Capture, for exactly `fetch-news-sentiment`, `fetch-news-sentiment-earnings` and
   `fetch-news-sentiment-topics`: the current immutable image digest, which must be
   the logger-hardened image that becomes the rollback target; current
   `maxRetries`; command, args, service account, region, memory, CPU, task timeout,
   environment and secret references.
2. Refuse on any unknown job, unexpected image identity, configuration drift from
   the captured expectation, or an execution of any of the three that is still
   running.
3. Apply `maxRetries 0` to all three without changing the image, and read it back
   for all three before any typed image activation.
4. Activate the reviewed typed-news (FEAT-DATA-001) immutable image, then verify
   the intended digest and that every other captured field is unchanged.
5. Rollback restores the captured logger-hardened image first and verifies it on
   all three, and only then restores any prior retry value.
6. Natural schedules and existing allowed exports are the verification
   mechanism; persisted coverage is not inferred from task success.
