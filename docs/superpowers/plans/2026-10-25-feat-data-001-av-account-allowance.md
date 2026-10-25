---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-10-24-feat-data-001-av-account-allowance.md
branch: fix/feat-data-001-av-account-allowance
pr: null
status: ready
---

# Account allowance and local pacing implementation plan

> For agentic workers: use superpowers:executing-plans with root as sole file writer and independent final review. Existing isolated worktree is reused; no second implementer.

**Goal:** Correct purchased account allowance to 600 RPM while preserving explicit conservative local pacing.
**Architecture:** AlphaVantageConfig separates account ceiling from local allocation; the two research CLIs derive pacing from local allocation and reject unsafe overrides before dispatch.
**Tech Stack:** Python dataclasses, pytest, actual CLI parser with mocked I/O.
**Spec:** docs/superpowers/specs/2026-10-24-feat-data-001-av-account-allowance.md, merged in #1587 at 9a3248bdb63a9b15cd0256126ac0e2ce99629796.

## Global constraints

Account rpm600 and account_rpm alias; default local_rpm150,delay0.4,batch150; explicit allocated local600 yields0.1/batch600. No per-worker600 grant, shared-capacity claim, key-loader change, provider or production calls, schema changes, backoff/retry/breaker changes. Preserve task-count partition exactly once. Accepted options component files/evidence remain unchanged.

## Review focus

Boolean/noninteger/nonfinite/zero/negative/over-account allocations reject; unsafe CLI delays reject before I/O; valid slower delays preserve allocation; actual batch loops consume local configuration; existing consumer pacing and retry decisions remain unchanged. Each is tested below.

## Task 1: account/local configuration

Spec: Design and Consumers; done_when[0,1,3].
Files: lib/config.py; tests/lib/test_av_account_allowance.py.
Consumes: existing AlphaVantageConfig construction and delay/batch consumers.
Produces: rpm:int=600, local_rpm:int=150, account_rpm read alias, validated positive integer allocations and locally derived delay/batch.
- [ ] Write default/explicit/invalid configuration tests and consumer/task partition controls.
- [ ] Run `python3 -m pytest tests/lib/test_av_account_allowance.py -q`; expect behavior failures on current150 baseline before editing runtime source.
- [ ] Implement only the config class allowance/validation/derived properties; preserve get_api_keys unchanged.
- [ ] Run same suite; expect all pass. Commit with normal commit gate after meaningful green proof.

## Task 2: actual research CLI pacing

Spec: Consumers and Regression; done_when[2,3].
Files: scripts/fetch_alphavantage_intraday.py,scripts/fetch_alphavantage_options.py; tests/scripts/test_av_client_pacing.py.
Consumes: Task1 local batch/delay; existing main parsers, fetch loops and circuit/backoff functions.
Produces: local batch defaults and finite delay override no faster than allocation, enforced before any dispatch.
- [ ] Mock dotenv/key loader/HTTP, use temporary local directories and fake clocks; test real parsers and both real batch loops, including invalid0/negative/nan/inf/faster overrides and valid default/slower settings.
- [ ] Run `python3 -m pytest tests/scripts/test_av_client_pacing.py -q`; expect current unvalidated override and rpm batch failures.
- [ ] Derive both batch constants from batch_size, validate delay with parser.error, update only pacing comments/help. Leave request, retry and breaker functions unchanged.
- [ ] Run both new suites plus directly affected `tests/lib/test_config.py`; expect all pass. Record exact source hashes and results; no accepted options suite rerun.

## Task 3: normal publication and release prerequisites

Spec: Regression/delivery,Capacity; done_when[4].
- [ ] Independent whole diff/test review; own FEAT-DATA-001 catalog/traceability records, normal commit/PR gate and branch/main no-new docs audit. Respect actual SITE/verifier gates without editing governance.
- [ ] Open draft implementation PR when lawful, record its number, satisfy current-head Codex reviews/checks. Do not claim local tests as deployed proof.
- [ ] Before runtime source merge inspect actual automatic lib/** API migrate effects; reuse STRAT's existing applied-schema export, require safe relevant schema status/digest/view state, no destructive/surprise migration.
- [ ] Verify intended immutable build/revision and local pacing after scoped release; preserve account/job configuration, rollback exact captured image. No exploratory provider calls, research writes or replay.
