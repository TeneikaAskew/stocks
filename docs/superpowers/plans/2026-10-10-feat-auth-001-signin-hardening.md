---
feat_id: FEAT-AUTH-001
spec: docs/superpowers/specs/2026-10-10-feat-auth-001-signin-hardening-r2.md
branch: feature/feat-auth-001-signin-hardening
pr: 1360
status: ready
---

# Sign-in hardening implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

## Task 1: refuse unverified email
Spec: § Design, "platform/api/auth.py" and "Tests". Advances done_when[0], [1] and [3].
- [ ] Add to `tests/api/test_platform_auth.py`: the `unverified:` stub token, `test_firebase_refuses_unverified_email`, `test_me_reports_unverified_admin_email_as_anonymous`, `test_verify_bearer_email_accepts_verified_email`, `test_verify_bearer_email_refuses_unverified_email` (false, absent, string)
- [ ] Run: `python -m pytest tests/api/test_platform_auth.py -q` (expect FAIL on the new tests)
- [ ] Implement `UnverifiedEmailError`, the claim check in `_verify_bearer_email`, the 403 in `auth_middleware`
- [ ] Run again (expect PASS)

## Task 2: gate /dev by mode
Spec: § Design, "platform/api/main.py /dev" and "Tests". Advances done_when[2] and [3].
- [ ] Write `tests/api/test_dev_page_auth.py`, one test per row of the spec's table
- [ ] Run: `python -m pytest tests/api/test_dev_page_auth.py -q` (expect FAIL for firebase and iap without a header)
- [ ] Implement the mode check in `dev_info` and correct the comment above `_DEV_ALLOWED_EMAIL`
- [ ] Run again (expect PASS); run `tests/api` and `tests/meta` and compare failures with origin/main
- [ ] Commit: `fix(auth): require verified email and gate /dev by auth mode`

## Task 3: close
Spec: § Done when. Closes done_when[4].
- [ ] Update the FEAT-AUTH-001 record in 02-FEATURE-CATALOG (Status, Last reviewed, Tests naming both files)
- [ ] Add this PR to the FEAT-AUTH-001 PR lineage in 12-PR-ISSUE-TRACEABILITY
- [ ] Docs audit reports nothing new over origin/main (`python -m scripts.maintenance.docs_audit`)
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main`
