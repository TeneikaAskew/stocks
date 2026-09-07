#!/usr/bin/env python3
"""
Branded Identity Platform (Firebase Auth) email templates.

Firebase sends four transactional emails on the project's behalf — email
verification, password reset, sign-in-email-changed, and the "two-step
verification was added" notice. Out of the box they are plain "Hello
%DISPLAY_NAME%, follow this link" messages sent from
noreply@<project>.firebaseapp.com with the link pointing at Google's generic
/__/auth/action page. This module owns the replacement:

  * gcp/auth_email_templates/_layout.html   — shared email shell (brand mark,
    card, footer). Table-based, inline-styled, email-client safe.
  * gcp/auth_email_templates/<name>.html     — the per-email card content.
  * this script — renders layout + content, then PATCHes the project's
    Identity Platform config over the admin/v2 REST API (port 443, so it
    works from the Claude Code sandbox, a desktop, or Cloud Build).

The rendered bodies keep Firebase's own substitution placeholders (%LINK%,
%EMAIL%, %NEW_EMAIL%, %SECOND_FACTOR%) — Firebase fills those at send time.
Product-level values ({{APP_NAME}}, {{APP_URL}}, ...) are filled here.

Usage
-----
    python -m gcp.auth_email_templates --show                # print live config
    python -m gcp.auth_email_templates --dry-run             # print the PATCH body
    python -m gcp.auth_email_templates --apply               # PATCH + verify
    python -m gcp.auth_email_templates --render-dir /tmp/x   # write HTML previews

What Google currently allows on this project (probed 2026-09-06, see
docs/AUTH_EMAILS.md "What Google blocks"): the sender display name and
reply-to are accepted; subject and the action URL are refused with
EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED; an HTML body PATCH returns 200 but is not
persisted. So --apply runs in two phases — sender fields first (always
applied), then subject/body/action URL — and reports exactly which phase
landed. Phase two is expected to start passing once the project is allowed
to customize templates (custom SMTP, or a console-side unlock); nothing in
this script needs to change for that.

Not covered here: the custom SENDING domain (From: noreply@stocks.insights
collective.org instead of @<project>.firebaseapp.com). The admin/v2 API
exposes every DnsInfo field as output-only and has no verify-domain method
(checked against the v2 discovery document), so that is a one-time console
step — see docs/AUTH_EMAILS.md.

Every option has a default that matches the live deployment; see DEFAULTS.
The action URL (where the emailed button lands) MUST be a page that renders
the Solyra SPA's /auth/action route and MUST be on a domain listed in the
project's Identity Platform authorized domains.

See docs/AUTH_EMAILS.md for the runbook.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import html
import json
import logging
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

logger = logging.getLogger("auth_email_templates")

TEMPLATE_DIR = Path(__file__).resolve().parent / "auth_email_templates"
LAYOUT_FILE = "_layout.html"

IDENTITY_API = "https://identitytoolkit.googleapis.com/admin/v2"
CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

DEFAULT_PROJECT = "adept-mountain-474619-d4"

# Template key in the Identity Platform config -> (content file, subject, preheader).
# Subjects deliberately avoid %APP_NAME% (Firebase's project display name is
# "Investing and Trading", not the product name) and %DISPLAY_NAME% (empty for
# email/password sign-ups, which renders as "Hello ,").
TEMPLATES: dict[str, tuple[str, str, str]] = {
    "verifyEmailTemplate": (
        "verify_email.html",
        "Confirm your email address for {{APP_NAME}}",
        "One click confirms this address for your {{APP_NAME}} account.",
    ),
    "resetPasswordTemplate": (
        "reset_password.html",
        "Reset your {{APP_NAME}} password",
        "Use the link inside to choose a new password. It can be used once.",
    ),
    "changeEmailTemplate": (
        "change_email.html",
        "Your {{APP_NAME}} sign-in email was changed",
        "If this was not you, restore your previous email address now.",
    ),
    "revertSecondFactorAdditionTemplate": (
        "revert_second_factor.html",
        "Two-step verification was added to your {{APP_NAME}} account",
        "If this was not you, remove the method now.",
    ),
}

# Firebase placeholders each rendered body must still carry, otherwise the
# email goes out without its link (or with a blank account reference).
REQUIRED_PLACEHOLDERS: dict[str, set[str]] = {
    "verifyEmailTemplate": {"%LINK%"},
    "resetPasswordTemplate": {"%LINK%", "%EMAIL%"},
    "changeEmailTemplate": {"%LINK%", "%NEW_EMAIL%"},
    "revertSecondFactorAdditionTemplate": {"%LINK%", "%SECOND_FACTOR%"},
}

# Firebase placeholders that must NOT appear: the product name comes from
# branding, and the display name is unset for most accounts.
FORBIDDEN_PLACEHOLDERS = {"%APP_NAME%", "%DISPLAY_NAME%"}


@dataclass(frozen=True)
class Branding:
    """Product-level values substituted into the templates and sender fields."""

    app_name: str = "Solyra"
    # Where the emailed buttons land. Must render the SPA (the /auth/action
    # route lives in the solyra repo) and be an Identity Platform authorized
    # domain. The API lives at api.stocks.insightscollective.org;
    # stocks.insightscollective.org is reserved for the Firebase sending
    # domain and, later, the SPA. Until the SPA moves there, the published
    # Lovable host is the default.
    app_url: str = "https://solyra-stocks.lovable.app"
    action_path: str = "/auth/action"
    sender_name: str = "Solyra"
    sender_local_part: str = "noreply"
    # Reply-to is carried over from the live config unless given explicitly;
    # None means "do not touch".
    reply_to: str | None = None
    support_email: str | None = None
    year: int = field(default_factory=lambda: _dt.date.today().year)

    @property
    def action_url(self) -> str:
        return self.app_url.rstrip("/") + self.action_path

    @property
    def app_host(self) -> str:
        return urlsplit(self.app_url).netloc


DEFAULTS = Branding()


# ── Rendering ────────────────────────────────────────────────────────────────
def _read_template(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def _substitutions(branding: Branding, subject: str, preheader: str) -> dict[str, str]:
    support_line = ""
    if branding.support_email:
        support_line = (
            f' Questions? Write to <a href="mailto:{html.escape(branding.support_email)}"'
            f' style="color:#0072c6;text-decoration:none;">{html.escape(branding.support_email)}</a>.'
        )
    return {
        "{{APP_NAME}}": html.escape(branding.app_name),
        "{{APP_NAME_UPPER}}": html.escape(branding.app_name.upper()),
        "{{APP_URL}}": html.escape(branding.app_url, quote=True),
        "{{APP_HOST}}": html.escape(branding.app_host),
        "{{SUPPORT_LINE}}": support_line,
        "{{YEAR}}": str(branding.year),
        "{{SUBJECT}}": html.escape(subject),
        "{{PREHEADER}}": html.escape(preheader),
    }


def _fill(text: str, subs: dict[str, str]) -> str:
    for token, value in subs.items():
        text = text.replace(token, value)
    return text


def render_subject(key: str, branding: Branding = DEFAULTS) -> str:
    _, subject, _ = TEMPLATES[key]
    return subject.replace("{{APP_NAME}}", branding.app_name)


def render_body(key: str, branding: Branding = DEFAULTS) -> str:
    """Layout + content for one template, fully substituted and validated."""
    content_file, subject, preheader = TEMPLATES[key]
    subs = _substitutions(
        branding,
        subject.replace("{{APP_NAME}}", branding.app_name),
        preheader.replace("{{APP_NAME}}", branding.app_name),
    )
    content = _fill(_read_template(content_file), subs)
    body = _fill(_read_template(LAYOUT_FILE), {**subs, "{{CONTENT}}": content})
    validate_body(key, body)
    return body


def validate_body(key: str, body: str) -> None:
    """Raise ValueError on an unfilled token or a missing/forbidden Firebase placeholder."""
    if "{{" in body or "}}" in body:
        start = body.index("{{") if "{{" in body else body.index("}}")
        raise ValueError(f"{key}: unfilled template token near: {body[start:start + 40]!r}")
    missing = sorted(p for p in REQUIRED_PLACEHOLDERS[key] if p not in body)
    if missing:
        raise ValueError(f"{key}: rendered body is missing Firebase placeholder(s) {missing}")
    present = sorted(p for p in FORBIDDEN_PLACEHOLDERS if p in body)
    if present:
        raise ValueError(f"{key}: rendered body must not use Firebase placeholder(s) {present}")


def render_all(branding: Branding = DEFAULTS) -> dict[str, dict[str, str]]:
    return {key: {"subject": render_subject(key, branding), "body": render_body(key, branding)} for key in TEMPLATES}


# ── PATCH construction ───────────────────────────────────────────────────────
def build_patch(branding: Branding, existing: dict | None = None) -> tuple[dict, str]:
    """Return (request body, updateMask) for the Identity Platform config PATCH.

    Each template is replaced whole (the mask names the template message, so
    any sub-field left out would be cleared) — which is why reply-to is
    carried over from `existing` when the branding does not set it.
    """
    existing_send = ((existing or {}).get("notification") or {}).get("sendEmail") or {}
    templates: dict[str, dict] = {}
    for key, rendered in render_all(branding).items():
        reply_to = branding.reply_to
        if reply_to is None:
            reply_to = (existing_send.get(key) or {}).get("replyTo")
        tpl = {
            "senderLocalPart": branding.sender_local_part,
            "senderDisplayName": branding.sender_name,
            "subject": rendered["subject"],
            "body": rendered["body"],
            "bodyFormat": "HTML",
        }
        if reply_to:
            tpl["replyTo"] = reply_to
        templates[key] = tpl

    body = {"notification": {"sendEmail": {**templates, "callbackUri": branding.action_url}}}
    mask_fields = [f"notification.sendEmail.{key}" for key in TEMPLATES] + ["notification.sendEmail.callbackUri"]
    return body, ",".join(mask_fields)


TEMPLATE_LOCKED = "EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED"

# Template fields Google accepts on a locked project vs. the ones it refuses.
SENDER_FIELDS = ("senderDisplayName", "replyTo")
CONTENT_FIELDS = ("subject", "body", "bodyFormat")


def split_patch(body: dict, existing: dict | None = None) -> list[tuple[str, dict, str]]:
    """Split the full desired state into (label, body, updateMask) phases.

    Phase "sender": display name + reply-to per template, plus the sender
    local part when it differs from the live value (it is left out of the
    mask otherwise so an unneeded write cannot trip the lock).
    Phase "content": subject, body, bodyFormat per template + callbackUri —
    everything Google refuses while the project's templates are locked.
    """
    send = body["notification"]["sendEmail"]
    live = ((existing or {}).get("notification") or {}).get("sendEmail") or {}
    phases: list[tuple[str, dict, str]] = []

    sender_body: dict = {}
    sender_mask: list[str] = []
    content_body: dict = {}
    content_mask: list[str] = []
    for key in TEMPLATES:
        tpl = send[key]
        sender_body[key] = {f: tpl[f] for f in SENDER_FIELDS if f in tpl}
        sender_mask += [f"notification.sendEmail.{key}.{f}" for f in SENDER_FIELDS if f in tpl]
        if tpl.get("senderLocalPart") != (live.get(key) or {}).get("senderLocalPart"):
            sender_body[key]["senderLocalPart"] = tpl["senderLocalPart"]
            sender_mask.append(f"notification.sendEmail.{key}.senderLocalPart")
        content_body[key] = {f: tpl[f] for f in CONTENT_FIELDS}
        content_mask += [f"notification.sendEmail.{key}.{f}" for f in CONTENT_FIELDS]
    content_body["callbackUri"] = send["callbackUri"]
    content_mask.append("notification.sendEmail.callbackUri")

    phases.append(("sender", {"notification": {"sendEmail": sender_body}}, ",".join(sender_mask)))
    phases.append(("content", {"notification": {"sendEmail": content_body}}, ",".join(content_mask)))
    return phases


def is_template_locked(err: BaseException) -> bool:
    return TEMPLATE_LOCKED in str(err)


def is_content_problem(problem: str) -> bool:
    """True when a verify_applied() line names a field Google refuses/drops on
    a locked project (subject, body, bodyFormat, callbackUri) rather than a
    sender field."""
    field_path = problem.split(":", 1)[0]
    return field_path == "callbackUri" or field_path.rsplit(".", 1)[-1] in CONTENT_FIELDS


def verify_applied(config: dict, patch_body: dict) -> list[str]:
    """Compare a freshly-fetched config against what was sent; return mismatches."""
    want = patch_body["notification"]["sendEmail"]
    got = ((config.get("notification") or {}).get("sendEmail") or {})
    problems: list[str] = []
    for key, tpl in want.items():
        if key == "callbackUri":
            if got.get("callbackUri") != tpl:
                problems.append(f"callbackUri: want {tpl!r}, got {got.get('callbackUri')!r}")
            continue
        live = got.get(key) or {}
        for fld, val in tpl.items():
            if live.get(fld) != val:
                shown = (str(live.get(fld))[:60] + "…") if fld == "body" else live.get(fld)
                problems.append(f"{key}.{fld}: not applied (live={shown!r})")
    return problems


def summarize(config: dict) -> str:
    """Human-readable view of the email-relevant parts of the live config."""
    send = ((config.get("notification") or {}).get("sendEmail") or {})
    lines = [
        f"method:          {send.get('method')}",
        f"callbackUri:     {send.get('callbackUri')}",
        f"dnsInfo:         {json.dumps(send.get('dnsInfo'))}",
        f"authorizedDomains: {json.dumps(config.get('authorizedDomains'))}",
    ]
    for key in TEMPLATES:
        tpl = send.get(key) or {}
        sender = f"{tpl.get('senderDisplayName') or '(no name)'} <{tpl.get('senderLocalPart')}@…>"
        lines.append(
            f"{key}:\n    from={sender} replyTo={tpl.get('replyTo')} format={tpl.get('bodyFormat')}"
            f"\n    subject={tpl.get('subject')!r}\n    body={len(tpl.get('body') or '')} chars"
        )
    return "\n".join(lines)


# ── Google API access (443 only) ─────────────────────────────────────────────
IDENTITY_FALLBACK_ENV = "AUTH_EMAIL_ALLOW_IDENTITY_FALLBACK"


def probe_token(project: str, token: str) -> str:
    """Ask the API whether `token` is usable for this project (read-only GET).

    Returns one of:
      "ok"             — accepted (2xx)
      "unsupported"    — 401 with reason ACCESS_TOKEN_TYPE_UNSUPPORTED: not a
                         credential at all (the Claude Code Remote placeholder)
      "unauthenticated"— any other 401: a real credential that expired or was
                         revoked
      "denied"         — 403: valid identity, missing role
      "other:<status>" — anything else
    Same discipline as scripts/db_query_cr.sh: usability is decided by asking
    the API, not by inspecting the token.
    """
    import requests  # lazy

    resp = requests.get(
        f"{IDENTITY_API}/projects/{project}/config",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    if resp.status_code < 300:
        return "ok"
    if resp.status_code == 401:
        return "unsupported" if "ACCESS_TOKEN_TYPE_UNSUPPORTED" in resp.text else "unauthenticated"
    if resp.status_code == 403:
        return "denied"
    return f"other:{resp.status_code}"


def get_access_token(
    env: dict[str, str] | None = None,
    project: str = DEFAULT_PROJECT,
    probe: Callable[[str, str], str] = probe_token,
) -> str:
    """An OAuth2 access token for the Identity Toolkit admin API.

    Order: GOOGLE_OAUTH_ACCESS_TOKEN (explicit, used as-is) →
    CLOUDSDK_AUTH_ACCESS_TOKEN (the caller's chosen identity, kept unless the
    API proves it was never a credential) → `gcloud auth print-access-token`
    → Application Default Credentials.

    CLOUDSDK_AUTH_ACCESS_TOKEN handling mirrors scripts/db_query_cr.sh. Claude
    Code Remote sessions export a short placeholder there; whether it is
    usable is decided by asking the API, not by looking at it:

      * accepted → use it. It is the identity the caller selected.
      * ACCESS_TOKEN_TYPE_UNSUPPORTED and shorter than 40 chars → it was never
        a credential, so nothing the caller chose is being discarded; fall
        through to gcloud's configured credentials.
      * any other rejection → stop. Dropping a real-but-expired token would
        run the PATCH as a different, possibly more privileged principal.
        Set AUTH_EMAIL_ALLOW_IDENTITY_FALLBACK=1 to accept that switch.
      * 403 → use it and let the real call fail loudly; substituting another
        identity would hide the missing role the operator needs to see.
    """
    env = dict(os.environ if env is None else env)
    explicit = env.get("GOOGLE_OAUTH_ACCESS_TOKEN", "").strip()
    if explicit:
        return explicit

    selected = env.get("CLOUDSDK_AUTH_ACCESS_TOKEN")
    if selected:
        verdict = probe(project, selected)
        if verdict in ("ok", "denied") or verdict.startswith("other:"):
            return selected
        if verdict == "unsupported" and len(selected) < 40:
            logger.info(
                "CLOUDSDK_AUTH_ACCESS_TOKEN is %d chars and the API rejected it as "
                "ACCESS_TOKEN_TYPE_UNSUPPORTED — a harness placeholder, not a credential; "
                "using gcloud's configured credentials instead", len(selected),
            )
            env.pop("CLOUDSDK_AUTH_ACCESS_TOKEN")
        elif env.get(IDENTITY_FALLBACK_ENV) == "1":
            logger.warning(
                "CLOUDSDK_AUTH_ACCESS_TOKEN was rejected (%s); %s=1 is set, so continuing "
                "under gcloud's configured identity", verdict, IDENTITY_FALLBACK_ENV,
            )
            env.pop("CLOUDSDK_AUTH_ACCESS_TOKEN")
        else:
            raise RuntimeError(
                f"CLOUDSDK_AUTH_ACCESS_TOKEN was rejected by the API ({verdict}) and is "
                f"{len(selected)} characters — long enough to be a real credential that has "
                "expired or been revoked. Refusing to silently run as a different principal: "
                "refresh the token, unset it yourself, or set "
                f"{IDENTITY_FALLBACK_ENV}=1 to accept the identity switch."
            )

    try:
        out = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            env=env, capture_output=True, text=True, check=True, timeout=60,
        )
        token = out.stdout.strip()
        if token:
            return token
        logger.info("gcloud returned an empty token; falling back to ADC")
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        logger.info("gcloud token unavailable (%s); falling back to ADC", exc)
    from google.auth import default as google_auth_default  # lazy: only needed on this path
    from google.auth.transport.requests import Request as GoogleRequest

    creds, _ = google_auth_default(scopes=[CLOUD_PLATFORM_SCOPE])
    creds.refresh(GoogleRequest())
    if not creds.token:
        raise RuntimeError("could not obtain a Google access token (gcloud and ADC both failed)")
    return creds.token


def _session(token: str):
    import requests  # lazy so the pure helpers stay import-light for tests

    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


def _raise_for(resp, what: str) -> dict:
    if resp.status_code >= 300:
        raise RuntimeError(f"{what} failed: HTTP {resp.status_code}: {resp.text[:2000]}")
    return resp.json()


def fetch_config(project: str, token: str) -> dict:
    with _session(token) as s:
        return _raise_for(s.get(f"{IDENTITY_API}/projects/{project}/config", timeout=60), "GET config")


def apply_config(project: str, token: str, body: dict, update_mask: str) -> dict:
    with _session(token) as s:
        resp = s.patch(
            f"{IDENTITY_API}/projects/{project}/config",
            params={"updateMask": update_mask},
            data=json.dumps(body),
            timeout=60,
        )
        return _raise_for(resp, "PATCH config")



# ── CLI ──────────────────────────────────────────────────────────────────────
def _branding_from_args(args: argparse.Namespace) -> Branding:
    return Branding(
        app_name=args.app_name,
        app_url=args.app_url,
        action_path=args.action_path,
        sender_name=args.sender_name,
        sender_local_part=args.sender_local_part,
        reply_to=args.reply_to,
        support_email=args.support_email,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", default=os.environ.get("GCP_PROJECT_ID", DEFAULT_PROJECT))
    p.add_argument("--app-name", default=DEFAULTS.app_name)
    p.add_argument("--app-url", default=DEFAULTS.app_url, help="SPA origin; buttons land on APP_URL + --action-path")
    p.add_argument("--action-path", default=DEFAULTS.action_path)
    p.add_argument("--sender-name", default=DEFAULTS.sender_name)
    p.add_argument("--sender-local-part", default=DEFAULTS.sender_local_part)
    p.add_argument("--reply-to", default=None, help="reply-to address; omitted = keep the live value")
    p.add_argument("--support-email", default=None, help="adds a 'Questions? Write to …' line to the footer")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--show", action="store_true", help="print the live email config and exit")
    mode.add_argument("--dry-run", action="store_true", help="print the exact phased PATCH requests --apply would send, no write")
    mode.add_argument("--apply", action="store_true", help="PATCH the live config, then re-fetch and verify")
    mode.add_argument("--render-dir", help="write rendered HTML previews to this directory and exit")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")

    branding = _branding_from_args(args)

    if args.render_dir:
        out = Path(args.render_dir)
        out.mkdir(parents=True, exist_ok=True)
        for key, rendered in render_all(branding).items():
            (out / f"{key}.html").write_text(rendered["body"], encoding="utf-8")
            print(f"{key}: {rendered['subject']!r} -> {out / (key + '.html')}")
        return 0

    token = get_access_token(project=args.project)
    existing = fetch_config(args.project, token)

    if args.dry_run:
        # Exactly the requests --apply would send, in order, built against the
        # live config (reply-to carry-over and the sender-local-part diff both
        # depend on it), so what is reviewed is what will be issued.
        body, _ = build_patch(branding, existing)
        for label, phase_body, mask in split_patch(body, existing):
            print(f"── phase {label} ──\nPATCH {IDENTITY_API}/projects/{args.project}/config?updateMask={mask}")
            print(json.dumps(phase_body, indent=2))
        print("\n(dry run: nothing was written)")
        return 0

    if args.show or not args.apply:
        print(summarize(existing))
        if not args.show:
            print("\n(no changes made; pass --apply to write, --dry-run to preview)")
        return 0

    body, _ = build_patch(branding, existing)
    locked = False
    accepted: list[str] = []
    for label, phase_body, mask in split_patch(body, existing):
        try:
            apply_config(args.project, token, phase_body, mask)
            accepted.append(label)
            print(f"phase {label}: accepted by the API (verifying below)")
        except RuntimeError as exc:
            if not is_template_locked(exc):
                raise
            locked = True
            print(f"phase {label}: refused by Google ({TEMPLATE_LOCKED})")

    fresh = fetch_config(args.project, token)
    problems = verify_applied(fresh, body)
    # A 200 on the content phase is not proof it landed: Google drops HTML
    # bodies silently on a locked project. Drift in any content field after
    # an accepted content phase is the same lock, just quieter.
    silently_dropped = [prob for prob in problems if is_content_problem(prob)] if "content" in accepted else []
    if silently_dropped:
        locked = True
        print(f"phase content: accepted by the API but {len(silently_dropped)} content field(s) were not persisted")
    print(summarize(fresh))
    if locked:
        print(
            "\nTemplate content is LOCKED on this project: Google refuses subject / action URL"
            "\nchanges and drops HTML bodies. Sender name and reply-to were applied. To unlock,"
            "\nsee docs/AUTH_EMAILS.md 'What Google blocks' (console edit, or custom SMTP).",
            file=sys.stderr,
        )
    if problems:
        print("\nNOT APPLIED:", file=sys.stderr)
        for prob in problems:
            print(f"  - {prob}", file=sys.stderr)
        return 2 if locked else 1
    print(f"\nApplied and verified {len(TEMPLATES)} templates; callbackUri={branding.action_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
