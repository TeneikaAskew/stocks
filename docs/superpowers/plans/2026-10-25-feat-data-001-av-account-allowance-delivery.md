---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-10-25-feat-data-001-av-account-allowance-source-proof.md
branch: fix/feat-data-001-av-account-allowance-delivery
pr: null
status: ready
---

# Account allowance and local pacing implementation plan

> For agentic workers: use superpowers:executing-plans with root as sole file writer and independent final review. Existing isolated worktree is reused; no second implementer.

**Goal:** Correct purchased account allowance to 600 RPM while preserving explicit conservative local pacing.
**Architecture:** AlphaVantageConfig separates account ceiling from local allocation; the two research CLIs derive pacing from local allocation and reject unsafe overrides before dispatch.
**Tech Stack:** Python dataclasses, pytest, actual CLI parser with mocked I/O.
**Spec:** docs/superpowers/specs/2026-10-25-feat-data-001-av-account-allowance-source-proof.md, merged metadata-only successor #1604 at b5bb0155. Original five runtime criteria unchanged.

## Global constraints

Account rpm600 and account_rpm alias; default local_rpm150,delay0.4,batch150; explicit allocated local600 yields0.1/batch600. No per-worker600 grant, shared-capacity claim, key-loader change, provider or production calls, schema changes, backoff/retry/breaker changes. Preserve task-count partition exactly once. Accepted options component files/evidence remain unchanged.

## Review focus

Boolean/noninteger/nonfinite/zero/negative/over-account allocations reject; unsafe CLI delays reject before I/O; valid slower delays preserve allocation; actual batch loops consume local configuration; existing consumer pacing and retry decisions remain unchanged. Each is tested below.

## Task 1: account/local configuration

Spec: Design and Consumers; done_when[0,1,3].
Files: lib/config.py; tests/lib/test_av_account_allowance.py.
Consumes: existing AlphaVantageConfig construction and delay/batch consumers.
Produces: rpm:int=600, local_rpm:int=150, account_rpm read alias, validated positive integer allocations and locally derived delay/batch.
- [x] Write default/explicit/invalid configuration tests and consumer/task partition controls.
- [x] Run `python3 -m pytest tests/lib/test_av_account_allowance.py -q`; expect behavior failures on current150 baseline before editing runtime source.
- [x] Implement only the config class allowance/validation/derived properties; preserve get_api_keys unchanged.
- [x] Run same suite; expect all pass. Commit with normal commit gate after meaningful green proof.

## Task 2: actual research CLI pacing

Spec: Consumers and Regression; done_when[2,3].
Files: scripts/fetch_alphavantage_intraday.py,scripts/fetch_alphavantage_options.py; tests/scripts/test_av_client_pacing.py.
Consumes: Task1 local batch/delay; existing main parsers, fetch loops and circuit/backoff functions.
Produces: local batch defaults and finite delay override no faster than allocation, enforced before any dispatch.
- [x] Mock dotenv/key loader/HTTP, use temporary local directories and fake clocks; test real parsers and both real batch loops, including invalid0/negative/nan/inf/faster overrides and valid default/slower settings.
- [x] Run `python3 -m pytest tests/scripts/test_av_client_pacing.py -q`; expect current unvalidated override and rpm batch failures.
- [x] Derive both batch constants from batch_size, validate delay with parser.error, update only pacing comments/help. Leave request, retry and breaker functions unchanged.
- [x] Run both new suites plus directly affected `tests/lib/test_config.py`; expect all pass. Record exact source hashes and results; no accepted options suite rerun.

## Task 3: normal publication and release prerequisites

Spec: Regression/delivery,Capacity; done_when[4].
- [ ] Independent whole diff/test review; own FEAT-DATA-001 catalog/traceability records, normal commit/PR gate and branch/main no-new docs audit. Respect actual SITE/verifier gates without editing governance.
- [ ] Open draft implementation PR when lawful, record its number, satisfy current-head Codex reviews/checks. Do not claim local tests as deployed proof.
- [ ] Before runtime source merge inspect actual automatic lib/** API migrate effects; reuse STRAT's existing applied-schema export, require safe relevant schema status/digest/view state, no destructive/surprise migration.
- [ ] Verify intended immutable build/revision and local pacing after scoped release; preserve account/job configuration, rollback exact captured image. No exploratory provider calls, research writes or replay.

## Preserved delivery lineage

This is the non-stacked replacement delivery for draft #1603, required because a plan cannot rebind its spec after creation. It starts from actual MAIN b5bb0155, not the unmerged draft. The five runtime/test blobs are byte-identical to independently reviewed258fb789;224author tests and the independent code review remain component evidence, not a new-head execution claim. The old draft/branches/receipts remain preserved. No accepted A8/A10 source or test is recreated or rerun. Old pre-publication spec review, current-head spec CODE/SEC, independent runtime review and both metadata-spec review heads remain in the same lineage; no effort allowance resets here. Normal current-head required CI/review and actual source-note producer/audit remain.
