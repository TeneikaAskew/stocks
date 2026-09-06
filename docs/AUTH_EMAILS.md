# Auth emails (Identity Platform / Firebase Auth)

Firebase sends four transactional emails for the Solyra login: email
verification, password reset, "your sign-in email was changed", and "two-step
verification was added". This doc is the runbook for the branded versions.

| Piece | Where | Owner |
|---|---|---|
| Email HTML (shell + four bodies) | `gcp/auth_email_templates/` | stocks |
| Apply script (renders + PATCHes the project config over HTTPS) | `gcp/auth_email_templates.py` | stocks |
| Tests (render validity, PATCH shape, token handling) | `tests/test_auth_email_templates.py` | stocks |
| The page the emailed buttons land on (`/auth/action`) | solyra `src/routes/AuthActionPage.tsx` | solyra |
| Forgot-password + verify-on-signup flows, in-app "confirm your email" banner | solyra `SignInScreen.tsx`, `AuthStatusIndicator.tsx` | solyra |
| Custom sending domain (DNS) | GCP console, one-time | manual |

## How it fits together

1. The app calls the Firebase SDK (`sendPasswordResetEmail`,
   `sendEmailVerification`, ...). Firebase renders the project's template,
   substituting `%LINK%`, `%EMAIL%`, `%NEW_EMAIL%`, `%SECOND_FACTOR%`.
2. `%LINK%` points at the project's **action URL** (`callbackUri`) with
   `mode=<action>&oobCode=<one-time code>`. The script sets that to the SPA's
   `/auth/action` route, so the user lands in Solyra rather than on Google's
   generic `firebaseapp.com/__/auth/action` page.
3. `/auth/action` (solyra) verifies the code with the SDK and renders the
   reset form / success / error states in the app's own design.

The action URL host must be in the project's Identity Platform
**authorized domains** list (the script prints it with `--show`).

## What Google blocks (state on 2026-09-06)

The Identity Platform config PATCH was probed field by field against this
project with the `claude-web@` service account:

| Field | Result |
|---|---|
| `senderDisplayName`, `replyTo` | accepted and persisted |
| `subject` (any template, any change) | `400 EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED` |
| `callbackUri` (even the same `firebaseapp.com` host with an extra query param) | `400 EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED` |
| `body` + `bodyFormat: HTML` | `200 OK`, but the GET afterwards still returns the stock body |
| A `subject` write identical to the live value | `200 OK` (so it is a change gate, not a permissions error) |

So Google is refusing template *content* customization on this project
(the `customized` flag on every template is unset). The sender name
"Solyra" is live; the stock subjects, stock body, and Google's
`firebaseapp.com/__/auth/action` handler page are still in effect.
`--apply` prints exactly this split and exits 2 while it holds.

Ways to unlock, in order of effort:

1. **Console editor.** Identity Platform → Templates → pencil icon. If the
   console lets you change the subject and "Customize action URL" to
   `https://solyra-stocks.lovable.app/auth/action`, the lock is on the API
   surface only, and a console edit of the four subjects + the action URL is
   a five-minute job. Re-run `--apply` afterwards to confirm (`--show`
   should then report `callbackUri` as the SPA and the phase-content
   PATCH may start passing too).
2. **Custom SMTP.** Templates → SMTP settings: point the project at your own
   sending provider (SendGrid, Postmark, Resend, Mailgun, or a Google
   Workspace relay) with `noreply@stocks.insightscollective.org` as the
   sender. Google's own reference config for `CUSTOM_SMTP` shows the HTML
   `body` alongside it, and it also solves the From-domain question with the
   provider's DKIM/SPF instead of Firebase's. Needs a provider account and
   credentials; then re-run `--apply`.
3. **Own the sending entirely** (the "level 3" option): generate action
   links server-side with firebase-admin (`generate_password_reset_link`,
   `generate_email_verification_link`) and send through a transactional
   provider with these same HTML files. Google's template lock becomes
   irrelevant, at the cost of a vendor and a secret in the API service.

Until one of these lands, the Solyra `/auth/action` page is deployed but
unreachable from the emails (they still link to Google's page), and the
forgot-password / verification flows work with Google's stock emails.

## Apply / update the templates

```bash
# See what is live (sender, subject, body size, callbackUri, DNS state)
python -m gcp.auth_email_templates --show

# Preview the exact PATCH body (no network)
python -m gcp.auth_email_templates --dry-run

# Write rendered HTML previews to open in a browser
python -m gcp.auth_email_templates --render-dir /tmp/auth-emails

# Apply in two phases (sender fields, then subject/body/action URL), then
# re-read the config and diff it against what was sent. Exit 0 = everything
# landed; 2 = Google refused the content phase (see "What Google blocks").
python -m gcp.auth_email_templates --apply
```

Defaults (all overridable by flag): product name `Solyra`, SPA origin
`https://solyra-stocks.lovable.app`, action path `/auth/action`, sender name
`Solyra`, sender local part `noreply`. Reply-to is carried over from the live
config unless `--reply-to` is given. `--support-email` adds a "Questions?
Write to ..." line to the footer.

When the SPA moves to its own domain, re-run with `--app-url https://<host>`
after adding that host to authorized domains. Nothing else changes.

Auth: the script uses `GOOGLE_OAUTH_ACCESS_TOKEN` if set, else
`gcloud auth print-access-token`, else Application Default Credentials. In a
Claude Code Remote session `CLOUDSDK_AUTH_ACCESS_TOKEN` is a 14-character
placeholder that shadows the real service-account credential; the script
drops it (same rule as `scripts/db_query_cr.sh`). The caller needs
`roles/identityplatform.admin` or `roles/editor` on the project.

Every template is replaced whole: the update mask names the template message,
so a field omitted from the PATCH is cleared. That is why the script builds
the full template object every time.

## Editing the design

* `_layout.html` is the shell: brand mark (the ascending bar-row from
  `Brand.tsx` in solyra, rendered as table cells), white card, footer.
  Tokens: `{{APP_NAME}}`, `{{APP_NAME_UPPER}}`, `{{APP_URL}}`, `{{APP_HOST}}`,
  `{{SUPPORT_LINE}}`, `{{YEAR}}`, `{{SUBJECT}}`, `{{PREHEADER}}`, `{{CONTENT}}`.
* The four `<name>.html` files are the card content only. Keep them
  table-based with inline styles; email clients strip `<style>` blocks and
  ignore web fonts. Light palette on purpose (Gmail and Outlook force it),
  using the app's light-mode tokens: brand `#0072c6`, text `#1a1c20`,
  secondary `#485661`, muted `#6e7781`, borders `#e4e7ee`.
* Do not use `%DISPLAY_NAME%` (blank for email/password sign-ups, renders
  "Hello ,") or `%APP_NAME%` (the Firebase project display name, not the
  product). `render_body` raises on either.
* Every body must keep `%LINK%`, and the templates that reference an account
  must keep `%EMAIL%` / `%NEW_EMAIL%` / `%SECOND_FACTOR%`. Also enforced.

## Custom sending domain (one-time, console)

Out of the box the From address is `noreply@adept-mountain-474619-d4.firebaseapp.com`.
To send from `noreply@stocks.insightscollective.org`:

1. GCP console → Identity Platform → Templates → pencil icon next to
   **From** → "Customize domain" → enter `stocks.insightscollective.org`.
2. The console shows the DNS records to add at the registrar for
   `insightscollective.org`: a TXT record proving ownership, an SPF TXT
   record (`v=spf1 include:_spf.firebasemail.com ~all`), and two
   `firebase1._domainkey` / `firebase2._domainkey` CNAME records for DKIM.
   Copy the values from the console, not from here.
3. Click Verify. Propagation can take up to 48 hours; until
   `--show` reports `customDomainState: SUCCEEDED` Firebase keeps sending
   from the `firebaseapp.com` address, so nothing breaks in the meantime.

This is deliberately not scripted: the admin/v2 REST API marks every
`DnsInfo` field output-only and has no domain-verification method (verified
against the v2 discovery document on 2026-09-06), and the DNS side is manual
anyway. There is no IAM-only path.

## Verifying end to end

1. Sign up with a throwaway email on the SPA → a "Confirm your email
   address for Solyra" email arrives from `Solyra <noreply@...>`.
2. Click the button → lands on `<app>/auth/action?mode=verifyEmail&oobCode=...`
   → "Email confirmed" card, and the in-app banner disappears after
   "I've confirmed".
3. Sign out → "Forgot password?" → reset email → button → new-password form
   → sign in with the new password.
4. `python -m gcp.auth_email_templates --show` prints the live config for
   an audit of what is actually deployed.
