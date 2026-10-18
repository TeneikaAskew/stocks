---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-10-18-feat-cicd-001-hermetic-gcloud-guard.md
branch: fix/feat-cicd-001-hermetic-gcloud
pr: 1536
status: ready
---

# Hermetic gcloud guard implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

## Task 1: regression tests, red first
Spec: § Design, "tests/meta/test_hermetic_gcloud.py". Advances done_when[0], [1], [2].
- [ ] Write `tests/meta/test_hermetic_gcloud.py`: each CLI resolves to the tripwire and exits 97; a non-executable fake falls through to the tripwire; `CLOUDSDK_CONFIG` is empty and the token variables are unset
- [ ] Run it behind a logging sentinel `gcloud` (expect 5 FAIL)

## Task 2: the guard
Spec: § Design. Advances done_when[0], [1], [2].
- [ ] Add executable `tests/fixtures/gcloud_tripwire/{gcloud,gsutil,bq}`
- [ ] In `tests/conftest.py`, at import: empty `CLOUDSDK_CONFIG`, drop `CLOUDSDK_AUTH_ACCESS_TOKEN` and `CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE`, prepend the tripwire to PATH; leave `CLOUDSDK_CORE_PROJECT` unset
- [ ] Run task 1's tests again (expect PASS)

## Task 3: the reproduction
Spec: § Problem. Advances done_when[3].
- [ ] Run the six fake-gcloud files behind the sentinel with pytest's temp directory on a `noexec` mount; record 0 sentinel calls against 50 before

## Task 4: full suite
Spec: § Risks. Advances done_when[4].
- [ ] Run `make test`'s scope with and without the guard, behind the sentinel; no test fails only with the guard

## Task 5: close
Spec: § Done when. Closes the last done_when item.
- [ ] Update the 02-FEATURE-CATALOG FEAT-CICD-001 record (Status, Last reviewed)
- [ ] Add this PR to 12-PR-ISSUE-TRACEABILITY
- [ ] Docs audit reports nothing new over origin/main (`python3 scripts/maintenance/docs_audit.py`)
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main`
