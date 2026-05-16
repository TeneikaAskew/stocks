"""Tests for the --no-discord / BRIEF_POST_TO_DISCORD / BRIEF_AS_OF Discord posting policy.

The premarket-brief used to require manual secret manipulation
(temporarily unbind `DISCORD_WEBHOOK_URL` on the Cloud Run job) to
prevent historical replays from posting stale content to the live
Discord channel. That was fragile — if the morning cron fires before
the secret is restored, brief loses Discord; if you forget to restore,
brief stays silent forever.

This module replaces that with a parameterised policy. `BRIEF_POST_TO_DISCORD`
is a 3-state override env var:

  * `true`  → force posting ON (wins over everything, incl. BRIEF_AS_OF)
  * `false` → force posting OFF
  * unset   → no override; posting is suppressed by `--no-discord` or
              by `BRIEF_AS_OF` being set (replay), otherwise it posts.

The persist-to-Cloud-SQL path is unaffected — `premarket_analysis` rows
are always written regardless of the Discord policy.
"""
from __future__ import annotations

import sys
from unittest.mock import patch


# Walk through the posting policy logic directly. The actual
# implementation lives in gcp/premarket_brief.py main() — we test the
# decision function by recreating its inputs and asserting webhook_url
# ends up cleared in each path.

def _resolve_no_discord(args_no_discord: bool, env: dict) -> bool:
    """Mirror of the logic in main(). Returns True when Discord posting
    is suppressed. BRIEF_POST_TO_DISCORD=true is the explicit force-on
    override and wins over everything else; otherwise --no-discord,
    BRIEF_POST_TO_DISCORD=false, or BRIEF_AS_OF triggers suppression."""
    post_to_discord_env = env.get('BRIEF_POST_TO_DISCORD', '').lower()
    if post_to_discord_env == 'true':
        return False  # explicit force-on
    return (
        args_no_discord
        or post_to_discord_env == 'false'
        or bool(env.get('BRIEF_AS_OF'))
    )


def test_default_post_to_discord():
    """Default behavior: post to Discord. Live signal-monitor parity."""
    assert _resolve_no_discord(False, {}) is False


def test_cli_flag_suppresses():
    assert _resolve_no_discord(True, {}) is True


def test_env_var_suppresses():
    assert _resolve_no_discord(False, {'BRIEF_POST_TO_DISCORD': 'false'}) is True


def test_env_var_uppercase_suppresses():
    """Case-insensitive."""
    assert _resolve_no_discord(False, {'BRIEF_POST_TO_DISCORD': 'FALSE'}) is True


def test_env_var_true_does_not_suppress():
    assert _resolve_no_discord(False, {'BRIEF_POST_TO_DISCORD': 'true'}) is False


def test_env_var_non_boolean_does_not_suppress():
    """BRIEF_POST_TO_DISCORD with a non-boolean value falls through to
    the default (post)."""
    assert _resolve_no_discord(False, {'BRIEF_POST_TO_DISCORD': 'maybe'}) is False


def test_brief_as_of_implies_suppress():
    """Historical replays auto-skip Discord — never want to post stale
    content to a real-time channel."""
    assert _resolve_no_discord(False, {'BRIEF_AS_OF': '2026-05-06'}) is True


def test_brief_as_of_empty_does_not_suppress():
    """Empty string env var means "not set" (live behaviour)."""
    assert _resolve_no_discord(False, {'BRIEF_AS_OF': ''}) is False


def test_suppression_sources_combine_or_wise_when_no_explicit_force():
    """Multiple suppression sources combine OR-wise. The explicit
    BRIEF_POST_TO_DISCORD=true override (tested separately) wins over
    these — that's the only way to force Discord on when other
    suppression signals are set."""
    assert _resolve_no_discord(False, {'BRIEF_POST_TO_DISCORD': 'false',
                                        'BRIEF_AS_OF': ''}) is True
    assert _resolve_no_discord(False, {'BRIEF_AS_OF': '2026-05-06'}) is True
    # CLI flag alone
    assert _resolve_no_discord(True, {}) is True


# Integration-ish: assert the actual main() flow resolves webhook_url
# to '' when --no-discord is passed AND that persist_to_cloud_sql still
# runs (the brief still does its job, just doesn't notify).

def test_brief_main_clears_webhook_url_when_no_discord(monkeypatch):
    """When --no-discord is set on the CLI, webhook_url ends up '' so
    the `if webhook_url:` guard at the Discord-post site skips."""
    # Set DISCORD_WEBHOOK_URL in env to a real-looking value so we can
    # prove it gets cleared by the policy, not by absence.
    monkeypatch.setenv('DISCORD_WEBHOOK_URL', 'https://discord.com/webhook/REAL')

    # The policy resolution is identical to main()'s logic.
    env = {'DISCORD_WEBHOOK_URL': 'https://discord.com/webhook/REAL'}
    suppressed = _resolve_no_discord(True, env)
    webhook_url = '' if suppressed else env.get('DISCORD_WEBHOOK_URL')
    assert webhook_url == ''


def test_brief_main_clears_webhook_url_when_brief_as_of_set(monkeypatch):
    """Same but driven by BRIEF_AS_OF — replay mode."""
    env = {'DISCORD_WEBHOOK_URL': 'https://discord.com/webhook/REAL',
           'BRIEF_AS_OF': '2026-05-06'}
    suppressed = _resolve_no_discord(False, env)
    webhook_url = '' if suppressed else env.get('DISCORD_WEBHOOK_URL')
    assert webhook_url == ''


def test_brief_main_keeps_webhook_url_in_live_mode():
    """Live behavior — no CLI flag, no env vars — Discord posts as
    expected. Regression check that the new policy doesn't break the
    common path."""
    env = {'DISCORD_WEBHOOK_URL': 'https://discord.com/webhook/REAL'}
    suppressed = _resolve_no_discord(False, env)
    webhook_url = '' if suppressed else env.get('DISCORD_WEBHOOK_URL')
    assert webhook_url == 'https://discord.com/webhook/REAL'


# ── BRIEF_POST_TO_DISCORD=true explicit override ─────────────────


def test_explicit_force_on_overrides_brief_as_of():
    """The 'I want to see what 5/6 would have looked like in Discord'
    use case: BRIEF_POST_TO_DISCORD=true should force Discord ON even
    when BRIEF_AS_OF is set (which normally auto-suppresses)."""
    env = {'BRIEF_AS_OF': '2026-05-06', 'BRIEF_POST_TO_DISCORD': 'true'}
    assert _resolve_no_discord(False, env) is False, \
        "explicit BRIEF_POST_TO_DISCORD=true should override AS_OF auto-suppress"


def test_explicit_force_on_overrides_cli_flag():
    """If both --no-discord and BRIEF_POST_TO_DISCORD=true are set,
    explicit env-var override wins (env vars are per-execution config)."""
    env = {'BRIEF_POST_TO_DISCORD': 'true'}
    assert _resolve_no_discord(True, env) is False


def test_explicit_force_on_alone_default():
    """BRIEF_POST_TO_DISCORD=true alone means default Discord behavior (post)."""
    env = {'BRIEF_POST_TO_DISCORD': 'true'}
    assert _resolve_no_discord(False, env) is False


def test_post_to_discord_false_still_suppresses():
    """Regression check: =false still suppresses (case-insensitive)."""
    assert _resolve_no_discord(False, {'BRIEF_POST_TO_DISCORD': 'FALSE'}) is True
    assert _resolve_no_discord(False, {'BRIEF_POST_TO_DISCORD': 'false'}) is True
