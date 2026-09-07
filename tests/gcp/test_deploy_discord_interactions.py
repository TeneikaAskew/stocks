"""Regression pins for gcp/deploy.sh::deploy_discord_interactions — #830 (audit K2).

The Discord bot token was read out of Secret Manager in the deploy shell
and pasted into `--set-env-vars` on a public (`--allow-unauthenticated`)
Cloud Run service, so it sat in plaintext in the revision spec, in
`gcloud run services describe`, and in every deploy log — while every
other credential on the same service (DB_PASS, AV_API_KEY, the webhooks,
FRED, Benzinga) is bound with `--set-secrets`. Verified live 2026-09-06:
`DISCORD_BOT_TOKEN` had an empty `secretKeyRef` on `discord-interactions`.

`DISCORD_PUBLIC_KEY` is Discord's Ed25519 *verification* key (public by
definition) and `DISCORD_APP_ID` is a public identifier; both may stay as
plain env vars.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEPLOY_SH = (REPO / "gcp/deploy.sh").read_text()


def _discord_deploy_body() -> str:
    m = re.search(r"deploy_discord_interactions\(\)\s*\{(.*?)\n\}", DEPLOY_SH, re.DOTALL)
    assert m, "deploy_discord_interactions not found in gcp/deploy.sh"
    return m.group(1)


def test_bot_token_is_bound_as_a_secret_not_an_env_var():
    body = _discord_deploy_body()
    # Never materialised into the shell / env string.
    assert "DISCORD_BOT_TOKEN=${discord_bot_token}" not in body
    assert not re.search(r'_secret discord-bot-token', body), \
        "the deploy must not read the bot token's VALUE into the shell"
    # Bound by reference, resolved by Cloud Run at container start.
    assert re.search(r"DISCORD_BOT_TOKEN=discord-bot-token:latest", body), \
        "DISCORD_BOT_TOKEN must be bound via --set-secrets"


def test_bot_token_secret_binding_is_on_a_set_secrets_flag():
    body = _discord_deploy_body()
    # The binding must ride on a --set-secrets flag (either appended to the
    # shared DB_SECRET_FLAG string or its own flag), not --set-env-vars.
    env_flags = re.findall(r'--set-env-vars\s+"([^"]*)"', body)
    assert env_flags and all("DISCORD_BOT_TOKEN" not in e for e in env_flags)
    assert re.search(r"--set-secrets[= ]\S*DISCORD_BOT_TOKEN=discord-bot-token:latest|"
                     r"DB_SECRET_FLAG\}[^\n]*DISCORD_BOT_TOKEN=discord-bot-token:latest", body)


def test_public_identifiers_may_stay_env_vars():
    """Guard against over-correcting: the public key and app id are not
    credentials and the service reads them from the environment."""
    body = _discord_deploy_body()
    assert "DISCORD_PUBLIC_KEY=${discord_public_key}" in body
    assert "DISCORD_APP_ID=${discord_app_id}" in body
