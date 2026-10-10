---
feat_id: FEAT-AUTH-001
req_ids: [REQ-AUTH-001, REQ-AUTH-002, REQ-AUTH-003, REQ-AUTHZ-001]
issues: [943]
canvases: []
done_when:
  - "tests/api/test_platform_auth.py asserts that in firebase mode a gated API request whose token has email_verified false or absent gets 403 with detail 'verify your email to continue', and that the same token resolves to no identity in current_user_email, so /api/me reports email null and is_admin false for it"
  - "tests/api/test_platform_auth.py runs the real bearer-token verifier in platform/api/auth.py against a stub firebase_admin and asserts it returns the email when email_verified is true and raises UnverifiedEmailError when it is false or absent"
  - "tests/api/test_dev_page_auth.py asserts /dev answers 404 in firebase mode with and without an IAP header, 403 in iap mode with no IAP header or a header naming another email, 200 in iap mode for DEV_ALLOWED_EMAIL, and 200 in open mode"
  - "Every new test is shown failing against the platform/api code on origin/main at the time the PR opens, and the Backtest Pipeline Run Tests job is green on the PR head"
  - "The FEAT-AUTH-001 record in 02-FEATURE-CATALOG shows a current Status and Last reviewed and names both test files, 12-PR-ISSUE-TRACEABILITY lists the PR under FEAT-AUTH-001, and the PR body closes #943"
status: approved
supersedes: null
---

# Sign-in hardening: verified email and the /dev page

## Problem

Two gaps in the authentication layer, both found or confirmed by reading the code on main
(`4fe9db5`) during the screen-by-screen walkthrough of the login screen.

1. **The backend never checks that a Firebase email is verified.** `_verify_bearer_email`
   (`platform/api/auth.py:114`) returns the token's `email` claim and ignores `email_verified`.
   Staging runs Firebase with open self-sign-up, admin is granted by email
   (`configured_admin_email()` and the `user_roles` table), and staging shares production's
   database. Anyone who can create a Firebase account with an email they do not own is treated as
   that person by every gated route, including as admin when the email is an admin's. Whether
   Firebase would allow the sign-up depends on whether that email already has an account in the
   project, which cannot be seen from the code. `docs/product/09-SECURITY-AUTH.md` says "any
   verified Firebase identity is admitted", which reads as if this were checked. No issue tracked
   it.
2. **`/dev` on the public staging service needs no sign-in** (stocks#943, open since 2026-08-31).
   The page is outside `/api/`, so the auth middleware skips it, and the handler
   (`platform/api/main.py:433`) allows any request without an IAP header. On staging no request
   carries one, so the page shows the Playwright service account, the IAP audience, the revision,
   the Cloud SQL connection name and the strat-engine model state to anyone. REQ-AUTH-003 requires
   such a page to be gated like `/api/*` or not deployed on a public service.

The owner asked for both to be fixed on 2026-10-10 ("Fix 1, 2, 3" in the project thread).

## Non-goals

- No frontend change. Solyra already shows an unverified-email banner; with this change the
  backend refuses data to that account until it verifies, and the frontend shows that 403
  however it shows any 403 today (not changed here). Making the banner block the app is a solyra change of its own.
- No change to how admin is granted (REQ-AUTHZ-001's constant-time comparison and email-only
  grant are #911-adjacent and stay out). This spec closes the path by which an unowned email
  reaches that check, not the check itself.
- No change to `iap` or `open` mode for `/api/*`. REQ-AUTH-002's application-layer header check for
  `/api/*` and the fail-closed deploy of REQ-AUTH-001 are #911.
- Not `docs/product/09-SECURITY-AUTH.md` or `15-OPEN-DECISIONS.md`: a feature branch may edit only
  this capability's catalog record and traceability entry. Both are corrected on a `docs/` branch
  after merge, with the plan's `status: done`.
- No removal of `/dev`. Production (IAP) and local development keep it.

## Approaches considered

For the verified email:

1. Check `email_verified` inside `_verify_bearer_email` and raise a distinct error the middleware
   maps to 403. Chosen: one place, so the middleware and `current_user_email` (which `/api/me` and
   the admin check use) cannot disagree.
2. Check it only in the middleware. Rejected: `/api/me` resolves identity outside the middleware,
   so an unverified admin email would still be reported `is_admin: true` to the frontend.
3. Disable email/password sign-up and allow Google only. Rejected: removes a working sign-in path
   the staging site offers on purpose.

For `/dev` (#943's three options):

1. Gate it with the Firebase bearer token on staging. Rejected: `/dev` is opened by browser
   navigation, which cannot attach a bearer token, so the page would be unreachable anyway, with
   more code.
2. Do not serve it on the public Firebase service, and require the IAP header in `iap` mode.
   Chosen: satisfies REQ-AUTH-003's second branch, and the missing-header case in `iap` mode is
   exactly REQ-AUTH-002's point that the perimeter is not assumed.
3. Accept the exposure. Rejected: the owner asked for a fix.

## Design

### `platform/api/auth.py`

- New `class UnverifiedEmailError(Exception)` with a docstring naming this spec.
- `_verify_bearer_email`: after `verify_id_token`, if `decoded.get("email_verified") is not True`,
  raise `UnverifiedEmailError`. The identity check is `is not True`, so a missing claim is refused,
  never assumed. Google sign-ins carry `email_verified: true`, so they are unaffected.
- `auth_middleware`: catch `UnverifiedEmailError` before the generic handler and answer
  `403 {"detail": "verify your email to continue"}`. A 403, not a 401: the token is valid and the
  account is known, it is not yet permitted.
- `current_user_email` already maps any exception to `None`; a comment there names the unverified
  case so the next reader does not narrow that `except`.
- The module docstring's access-policy paragraph says verified email is required.

### `platform/api/main.py` `/dev`

Decided by `AUTH_MODE` (imported from `api.auth`), before any field is read:

| Mode | No IAP header | Header, other email | Header, `DEV_ALLOWED_EMAIL` |
|---|---|---|---|
| `firebase` (public staging) | 404 | 404 | 404 |
| `iap` (production) | 403 | 403 | 200 |
| `open` (local) | 200 | 403 | 200 |

`open` keeps the existing other-email 403. 404 rather than 403 on staging so the route reads as
absent, which is what REQ-AUTH-003 asks for. The comment above `_DEV_ALLOWED_EMAIL`, which says the
page is only reachable behind IAP, is corrected.

### Tests

- `tests/api/test_platform_auth.py`: the existing `fake_verify` stub gains a `unverified:<email>`
  token that raises `UnverifiedEmailError`; new tests cover the 403 detail and `/api/me`
  reporting `email: null`, `is_admin: false` for that token on an admin email. The existing
  clock-skew test's stub returns `email_verified: True`; new tests run the real
  `_verify_bearer_email` with `email_verified` false and absent.
- New `tests/api/test_dev_page_auth.py`, one test per row of the table above, with
  `_strat_engine_state` stubbed so no GCS call is made.

### Capacity (CLAUDE.md rule 0)

n/a: no job, query or vendor call is added. Each gated request does one dictionary lookup more on
an already-decoded token; `/dev` does one string comparison more.

## Risks

- **An existing unverified staging account loses data access.** Intended. It regains access by
  verifying. Google accounts are unaffected. Caught by done_when[0].
- **A Firebase provider that omits `email_verified`.** Refused by design (done_when[1] covers the
  absent claim). If a provider is added later that legitimately omits it, it must be handled
  explicitly, not by loosening this check.
- **Someone relies on `/dev` on staging.** Nothing in solyra links to it (`grep` over `src` and
  `tests` finds no `/dev` route reference). Production and local keep it (done_when[2]).
