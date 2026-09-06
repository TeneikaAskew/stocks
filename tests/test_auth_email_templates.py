"""Hermetic tests for gcp/auth_email_templates.py — rendering, PATCH shape,
post-apply verification, and the sandbox token dance. No network."""
from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from gcp import auth_email_templates as aet

BRAND = aet.Branding(
    app_name="Solyra",
    app_url="https://solyra-stocks.lovable.app",
    support_email="support@example.test",
    year=2026,
)


# ── Rendering ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("key", sorted(aet.TEMPLATES))
def test_every_template_renders_with_required_firebase_placeholders(key):
    body = aet.render_body(key, BRAND)
    for placeholder in aet.REQUIRED_PLACEHOLDERS[key]:
        assert placeholder in body
    for placeholder in aet.FORBIDDEN_PLACEHOLDERS:
        assert placeholder not in body
    assert "{{" not in body and "}}" not in body
    # Layout landed: brand wordmark, the SPA link, copyright year, and the
    # button href carries Firebase's %LINK% so the email is never linkless.
    assert "SOLYRA" in body
    assert 'href="https://solyra-stocks.lovable.app"' in body
    assert "&copy; 2026 Solyra" in body
    assert 'href="%LINK%"' in body


def test_subjects_use_product_name_not_firebase_app_name():
    for key in aet.TEMPLATES:
        subject = aet.render_subject(key, BRAND)
        assert "Solyra" in subject
        assert "%" not in subject


def test_support_line_is_omitted_when_no_support_email():
    body = aet.render_body("verifyEmailTemplate", aet.Branding(support_email=None, year=2026))
    assert "Questions?" not in body
    with_support = aet.render_body("verifyEmailTemplate", BRAND)
    assert "mailto:support@example.test" in with_support


def test_app_name_is_html_escaped():
    body = aet.render_body("verifyEmailTemplate", aet.Branding(app_name="A&B <Co>", year=2026))
    assert "A&amp;B &lt;Co&gt;" in body
    assert "<Co>" not in body


def test_validate_body_rejects_unfilled_token_and_missing_link():
    with pytest.raises(ValueError, match="unfilled template token"):
        aet.validate_body("verifyEmailTemplate", "<p>{{APP_NAME}}</p> %LINK%")
    with pytest.raises(ValueError, match="missing Firebase placeholder"):
        aet.validate_body("resetPasswordTemplate", "<p>no link, no email</p>")
    with pytest.raises(ValueError, match="must not use"):
        aet.validate_body("verifyEmailTemplate", "<p>Hello %DISPLAY_NAME%</p> %LINK%")


# ── PATCH construction ───────────────────────────────────────────────────────
def test_build_patch_covers_all_templates_and_callback_uri():
    body, mask = aet.build_patch(BRAND)
    send = body["notification"]["sendEmail"]
    assert send["callbackUri"] == "https://solyra-stocks.lovable.app/auth/action"
    for key in aet.TEMPLATES:
        tpl = send[key]
        assert tpl["bodyFormat"] == "HTML"
        assert tpl["senderDisplayName"] == "Solyra"
        assert tpl["senderLocalPart"] == "noreply"
        assert "%LINK%" in tpl["body"]
        assert f"notification.sendEmail.{key}" in mask.split(",")
        assert "replyTo" not in tpl  # nothing live to carry over, nothing given
    assert "notification.sendEmail.callbackUri" in mask.split(",")


def test_build_patch_carries_over_live_reply_to_unless_overridden():
    existing = {
        "notification": {"sendEmail": {"verifyEmailTemplate": {"replyTo": "help@live.test"}}}
    }
    body, _ = aet.build_patch(BRAND, existing)
    send = body["notification"]["sendEmail"]
    assert send["verifyEmailTemplate"]["replyTo"] == "help@live.test"
    assert "replyTo" not in send["resetPasswordTemplate"]

    body, _ = aet.build_patch(aet.Branding(reply_to="support@new.test", year=2026), existing)
    assert body["notification"]["sendEmail"]["verifyEmailTemplate"]["replyTo"] == "support@new.test"


def test_verify_applied_reports_each_drift():
    body, _ = aet.build_patch(BRAND)
    # Echo of what we sent → clean.
    assert aet.verify_applied(body, body) == []
    # Callback and one subject drifted.
    drifted = {
        "notification": {
            "sendEmail": {
                **{k: dict(v) for k, v in body["notification"]["sendEmail"].items() if k != "callbackUri"},
                "callbackUri": "https://adept-mountain-474619-d4.firebaseapp.com/__/auth/action",
            }
        }
    }
    drifted["notification"]["sendEmail"]["resetPasswordTemplate"]["subject"] = "old"
    problems = aet.verify_applied(drifted, body)
    assert any(p.startswith("callbackUri") for p in problems)
    assert any(p.startswith("resetPasswordTemplate.subject") for p in problems)
    assert len(problems) == 2


# ── Token acquisition ────────────────────────────────────────────────────────
def test_get_access_token_prefers_explicit_env():
    assert aet.get_access_token({"GOOGLE_OAUTH_ACCESS_TOKEN": "x" * 50}) == "x" * 50


def test_get_access_token_drops_short_placeholder_before_gcloud():
    seen = {}

    def fake_run(cmd, env, **kw):
        seen["env"] = env
        return subprocess.CompletedProcess(cmd, 0, stdout="ya29." + "a" * 60 + "\n", stderr="")

    with patch.object(aet.subprocess, "run", side_effect=fake_run):
        tok = aet.get_access_token({"CLOUDSDK_AUTH_ACCESS_TOKEN": "placeholder14c", "PATH": "/usr/bin"})
    assert tok.startswith("ya29.")
    assert "CLOUDSDK_AUTH_ACCESS_TOKEN" not in seen["env"]


def test_get_access_token_keeps_real_env_token_for_gcloud():
    seen = {}

    def fake_run(cmd, env, **kw):
        seen["env"] = env
        return subprocess.CompletedProcess(cmd, 0, stdout="ya29." + "b" * 60 + "\n", stderr="")

    real = "ya29." + "r" * 80
    with patch.object(aet.subprocess, "run", side_effect=fake_run):
        aet.get_access_token({"CLOUDSDK_AUTH_ACCESS_TOKEN": real})
    assert seen["env"]["CLOUDSDK_AUTH_ACCESS_TOKEN"] == real


def test_summarize_lists_every_template():
    body, _ = aet.build_patch(BRAND)
    text = aet.summarize(body)
    for key in aet.TEMPLATES:
        assert key in text
    assert "callbackUri:     https://solyra-stocks.lovable.app/auth/action" in text


# ── Two-phase apply ──────────────────────────────────────────────────────────
def test_split_patch_separates_sender_fields_from_locked_content():
    body, _ = aet.build_patch(aet.Branding(reply_to="help@x.test", year=2026))
    phases = aet.split_patch(body, existing={"notification": {"sendEmail": {
        k: {"senderLocalPart": "noreply"} for k in aet.TEMPLATES}}})
    labels = [p[0] for p in phases]
    assert labels == ["sender", "content"]

    _, sender_body, sender_mask = phases[0]
    _, content_body, content_mask = phases[1]
    for key in aet.TEMPLATES:
        assert set(sender_body["notification"]["sendEmail"][key]) == {"senderDisplayName", "replyTo"}
        assert set(content_body["notification"]["sendEmail"][key]) == {"subject", "body", "bodyFormat"}
        assert f"notification.sendEmail.{key}.senderDisplayName" in sender_mask.split(",")
        assert f"notification.sendEmail.{key}.subject" in content_mask.split(",")
        # local part matches live → not written, so it cannot trip the lock
        assert "senderLocalPart" not in sender_mask
    assert "notification.sendEmail.callbackUri" in content_mask.split(",")
    assert "callbackUri" not in sender_mask


def test_split_patch_writes_sender_local_part_only_when_it_changes():
    body, _ = aet.build_patch(aet.Branding(sender_local_part="hello", year=2026))
    phases = aet.split_patch(body, existing={"notification": {"sendEmail": {
        "verifyEmailTemplate": {"senderLocalPart": "noreply"}}}})
    _, sender_body, sender_mask = phases[0]
    assert sender_body["notification"]["sendEmail"]["verifyEmailTemplate"]["senderLocalPart"] == "hello"
    assert "notification.sendEmail.verifyEmailTemplate.senderLocalPart" in sender_mask


def test_apply_reports_locked_content_phase_and_exits_2(capsys):
    """Google's current behaviour: sender fields land, content is refused."""
    live = {"notification": {"sendEmail": {
        **{k: {"senderLocalPart": "noreply", "replyTo": "noreply", "subject": "old", "body": "old", "bodyFormat": "HTML"}
           for k in aet.TEMPLATES},
        "callbackUri": "https://old.example/__/auth/action"}}}

    def fake_apply(project, token, body, mask):
        if ".subject" in mask or "callbackUri" in mask:
            raise RuntimeError(f"PATCH config failed: HTTP 400: {aet.TEMPLATE_LOCKED}")
        for key, tpl in body["notification"]["sendEmail"].items():
            live["notification"]["sendEmail"][key].update(tpl)
        return live

    with patch.object(aet, "get_access_token", return_value="tok"), \
         patch.object(aet, "fetch_config", side_effect=lambda p, t: live), \
         patch.object(aet, "apply_config", side_effect=fake_apply):
        rc = aet.main(["--apply"])

    out = capsys.readouterr()
    assert rc == 2
    assert "phase sender: accepted" in out.out
    assert "phase content: refused" in out.out
    assert "LOCKED on this project" in out.err
    assert live["notification"]["sendEmail"]["verifyEmailTemplate"]["senderDisplayName"] == "Solyra"
    assert live["notification"]["sendEmail"]["verifyEmailTemplate"]["subject"] == "old"


def test_apply_exits_0_when_every_phase_lands():
    live = {"notification": {"sendEmail": {"callbackUri": "x", **{k: {} for k in aet.TEMPLATES}}}}

    def fake_apply(project, token, body, mask):
        for key, tpl in body["notification"]["sendEmail"].items():
            if key == "callbackUri":
                live["notification"]["sendEmail"]["callbackUri"] = tpl
            else:
                live["notification"]["sendEmail"][key].update(tpl)
        return live

    with patch.object(aet, "get_access_token", return_value="tok"), \
         patch.object(aet, "fetch_config", side_effect=lambda p, t: live), \
         patch.object(aet, "apply_config", side_effect=fake_apply):
        assert aet.main(["--apply"]) == 0
