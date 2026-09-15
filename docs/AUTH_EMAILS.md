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

## Template state (live since 2026-09-15)

Everything is applied. A `--show` against the project returns:

| Field | Live value |
|---|---|
| `senderDisplayName` / From | `Solyra <noreply@stocks.insightscollective.org>` |
| `callbackUri` | `https://solyra-stocks.lovable.app/auth/action` |
| `verifyEmailTemplate.subject` | `Confirm your email address for Solyra` |
| `resetPasswordTemplate.subject` | `Reset your Solyra password` |
| `changeEmailTemplate.subject` | `Your Solyra sign-in email was changed` |
| `revertSecondFactorAdditionTemplate.subject` | `Two-step verification was added to your Solyra account` |
| all four `body` / `bodyFormat` | the HTML in `gcp/auth_email_templates/`, byte-for-byte |

Verified by diffing the live config against `render_all(Branding())` with
`verify_applied`, not by eye. The action URL was separately confirmed by
loading a real action link against the deployed SPA: the page reads the
`mode` / `oobCode` parameters, calls Identity Platform, and renders the
error card for a used or invalid code.

**Known cosmetic defect, accepted:** each of the four subjects carries a
trailing newline (`'Reset your Solyra password\n'`), introduced when the
values were transcribed from a support email where each sat on its own line.
Mail systems normally strip it from the header. `--apply` therefore still
reports the four subjects as not-applied and exits 2 even though everything
else matches.

**That "only the subjects" reading expires each New Year.** The footer renders
`{{YEAR}}` from `Branding.year`, which defaults to *today's* year, while the
live bodies stay frozen at the year support applied them (2026). From
2027-01-01 a default `--apply` will report four *body* mismatches as well, and
the whole difference will be the copyright line. Pass `--year 2026` to render
against what is actually live, and treat any body diff that survives that as a
real one. The same flag is what to use when asking support to re-apply, so the
footer does not silently jump a year.

### The lock is still on, and this is the part to remember

The API refuses template *content* changes on this project and **still does**,
even now that the content is customized:

| Field | Result |
|---|---|
| `senderDisplayName`, `replyTo` | accepted and persisted |
| `subject` (any template, any change) | `400 EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED` |
| `callbackUri` | `400 EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED` |
| `body` + `bodyFormat: HTML` | `200 OK`, but the GET afterwards still returns the previous body |
| A `subject` write identical to the live value | `200 OK` (a change gate, not a permissions error) |

So the current content did **not** get there through this script, and the
next change will not either. It was applied by Firebase engineering through
support case **10423967**, in two rounds: the action URL first, then the four
subjects and bodies. The console editor is blocked the same way as the API.

**To change a subject, a body, or the action URL from here:** run
`--render-dir` to produce the HTML, then reply on a Firebase support case
asking engineering to apply the files and the subject lines. Expect to supply
a rough volume estimate for the transactional mail. Do not spend time
debugging `EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED` or re-scoping credentials; the
lock is project-level and is not an auth problem.

### Ways to get self-service back, in order of effort

1. **Ask support to lift the lock.** The same case that applied the content
   is the place to ask whether the project can be unlocked for normal
   console/API edits. Cheapest if it works.
2. **Custom SMTP.** Templates → SMTP settings: point the project at your own
   sending provider (SendGrid, Postmark, Resend, Mailgun, or a Google
   Workspace relay) with `noreply@stocks.insightscollective.org` as the
   sender. Google's reference config for `CUSTOM_SMTP` shows the HTML `body`
   alongside it. Needs a provider account and credentials.
3. **Own the sending entirely** (the "level 3" option): generate action links
   server-side with firebase-admin (`generate_password_reset_link`,
   `generate_email_verification_link`) and send through a transactional
   provider with these same HTML files. The template lock becomes
   irrelevant, at the cost of a vendor and a secret in the API service.

## Apply / update the templates

```bash
# See what is live (sender, subject, body size, callbackUri, DNS state)
python -m gcp.auth_email_templates --show

# Preview the exact phased PATCH requests --apply would send, built against
# the live config (reads it, writes nothing)
python -m gcp.auth_email_templates --dry-run

# Write rendered HTML previews to open in a browser
python -m gcp.auth_email_templates --render-dir /tmp/auth-emails

# Apply in two phases (sender fields, then subject/body/action URL), then
# re-read the config and diff it against what was sent. Exit 0 = everything
# landed; 2 = a content field did not match afterwards (see "Template state").
python -m gcp.auth_email_templates --apply
```

Defaults (all overridable by flag): product name `Solyra`, SPA origin
`https://solyra-stocks.lovable.app`, action path `/auth/action`, sender name
`Solyra`, sender local part `noreply`. Reply-to is carried over from the live
config unless `--reply-to` is given. `--support-email` adds a "Questions?
Write to ..." line to the footer. `--year` pins the footer copyright year,
which otherwise follows today's date and drifts from the frozen live bodies.

When the SPA moves to its own domain, **`--app-url` alone will not move the
emails.** It changes `callbackUri`, which is exactly what the lock refuses, so
the run exits 2 and every emailed link keeps pointing at the old host. The
sequence is: add the new host to authorized domains, run `--render-dir` with
`--app-url https://<host>` to produce the HTML carrying the new links, then ask
Firebase support to apply that action URL and those bodies, quoting the full
URL you want (`https://<host>/auth/action`). Treat the old host as live until
`--show` reports the new `callbackUri`.

Auth: `GOOGLE_OAUTH_ACCESS_TOKEN` if set (used as-is), else
`CLOUDSDK_AUTH_ACCESS_TOKEN`, else `gcloud auth print-access-token`, else
Application Default Credentials. `CLOUDSDK_AUTH_ACCESS_TOKEN` gets the same
treatment as in `scripts/db_query_cr.sh`: the script asks the API whether the
value is usable (a read-only GET of the config) instead of inspecting it. In
a Claude Code Remote session that variable is a 14-character placeholder the
API rejects as `ACCESS_TOKEN_TYPE_UNSUPPORTED`; only that answer combined
with a sub-40-character value is treated as "never a credential", and the
script falls through to gcloud's configured service account. Any other
rejection stops the run rather than silently writing the config as a
different principal; set `AUTH_EMAIL_ALLOW_IDENTITY_FALLBACK=1` to accept the
identity switch. The caller needs `roles/identityplatform.admin` or
`roles/editor` on the project.

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

## Custom sending domain (one-time, console + Squarespace DNS)

Out of the box the From address is `noreply@adept-mountain-474619-d4.firebaseapp.com`.
Target: `noreply@stocks.insightscollective.org`.

**Why the API had to move first.** Until 2026-09-06 `stocks.insightscollective.org`
was a CNAME to `ghs.googlehosted.com` (the Cloud Run domain mapping for
`solyra-api-staging`). DNS forbids any other record at a name that carries
a CNAME, so Firebase's two TXT records could never be served there. The
API mapping was therefore re-created as `api.stocks.insightscollective.org`
(same service, same CNAME target) and the `stocks` CNAME is deleted, which
frees `stocks.insightscollective.org` for mail now and for the SPA later
(Lovable maps subdomains with A records, which coexist with TXT).

The zone is hosted by Squarespace Domains (nameservers
`ns-cloud-e1..e4.googledomains.com`; Cloud DNS is not enabled in the
project), so DNS edits happen in Squarespace → Domains →
insightscollective.org → DNS settings. Nothing in GCP can write them.

Records at Squarespace (host is relative to `insightscollective.org`):

| Host | Type | Value | Purpose |
|---|---|---|---|
| `api.stocks` | CNAME | `ghs.googlehosted.com.` | API (Cloud Run mapping → `solyra-api-staging`) |
| `stocks` | TXT | `v=spf1 include:_spf.firebasemail.com ~all` | Firebase SPF |
| `stocks` | TXT | `firebase=adept-mountain-474619-d4` | Firebase ownership |
| `firebase1._domainkey.stocks` | CNAME | `mail-stocks-insightscollective-org.dkim1._domainkey.firebasemail.com.` | DKIM 1 |
| `firebase2._domainkey.stocks` | CNAME | `mail-stocks-insightscollective-org.dkim2._domainkey.firebasemail.com.` | DKIM 2 |
| `_dmarc.stocks` | TXT | `v=DMARC1; p=none; rua=mailto:<a mailbox you read>` | optional, reporting only |
| ~~`stocks`~~ | ~~CNAME~~ | ~~`ghs.googlehosted.com.`~~ | **delete** (blocks the TXT records) |

Copy the Firebase values from the console dialog (Templates → pencil →
Customize domain), not from here, in case they change.

Order of operations:

1. Add the `api.stocks` CNAME. Wait until
   `curl -s 'https://dns.google/resolve?name=api.stocks.insightscollective.org&type=CNAME'`
   shows it, then until `https://api.stocks.insightscollective.org/api/health`
   answers 200 (Google issues the certificate after the record is visible;
   usually minutes, can be longer).
2. Delete the `stocks` CNAME. The old hostname stops answering at that
   point; nothing in the repos calls it (Solyra calls the `run.app` URL).
3. Add the four Firebase records from the table above in Squarespace (the
   two `stocks` TXT rows and the two `firebase*._domainkey.stocks` CNAME
   rows), plus the optional `_dmarc.stocks` TXT. Enter the **short** host
   names exactly as in the table: Squarespace appends
   `.insightscollective.org` itself, and a full hostname in the Name column
   silently lands the record at `stocks.insightscollective.org.insightscollective.org`
   (seen on 2026-09-06). Confirm with
   `curl -s 'https://dns.google/resolve?name=stocks.insightscollective.org&type=TXT'`
   (both values) and the same query for each `_domainkey` name (type=CNAME).
   Public resolvers can hold the deleted CNAME for its TTL (4 h) first.
4. Firebase console → Templates → Customize domain → Verify. Propagation
   can take up to 48 hours; until `python -m gcp.auth_email_templates --show`
   reports `customDomainState: SUCCEEDED`, Firebase keeps sending from the
   `firebaseapp.com` address, so nothing breaks in the meantime. Once it
   passes, click **Apply custom domain** in the green banner; `--show` then
   reports `customDomain` set and `useCustomDomain: true`.
5. Delete the old Cloud Run mapping so it does not linger:
   `gcloud beta run domain-mappings delete --domain=stocks.insightscollective.org --region=us-east1`.

This is deliberately not scripted: the admin/v2 REST API marks every
`DnsInfo` field output-only and has no domain-verification method (verified
against the v2 discovery document on 2026-09-06), and the DNS side lives
outside GCP anyway.

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
