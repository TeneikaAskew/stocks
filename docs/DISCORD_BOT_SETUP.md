# Discord Bot Setup Guide

End-to-end runbook for wiring a Discord bot + slash-command interactions endpoint to this repo's `discord-interactions` Cloud Run service. Follow top-to-bottom on a fresh app; jump to specific sections when re-bootstrapping.

The slash commands this enables: `/replay`, `/watchlist`, `/validate`, `/backtest` — see [docs/plans/DISCORD_INTERACTIONS_PLAN.md](plans/DISCORD_INTERACTIONS_PLAN.md) for the design + per-command behaviour.

---

## Prerequisites

- Owner/admin of the Discord server you want the bot in.
- `gcloud` CLI authenticated against the project that hosts this repo's Cloud Run jobs (`adept-mountain-474619-d4` for our case).
- Local Python 3.11 with the repo cloned and `pip install -r requirements-gcp.txt` already done — needed for the one-shot command-registration script.

If any of those are missing, fix them first. Everything below assumes they're in place.

---

## Step 1 — Create the Discord application

1. Go to https://discord.com/developers/applications.
2. Click **New Application**, give it a name (e.g. "Trading Brief Bot"), agree, **Create**.
3. You're now on the **General Information** tab. **Copy these three values into a scratch buffer** — you'll feed them to GCP Secret Manager in Step 2:

| Field | Where on the page | Looks like |
|---|---|---|
| **Application ID** | top of General Information | a 19-digit number |
| **Public Key** | a few sections down on the same page | 64-character hex string |
| **Bot Token** | go to the **Bot** tab in the left sidebar → **Reset Token** → confirm → copy *immediately*, you can't view it again | base64-ish, ~70 chars |

⚠️ The bot token is shown **once**. If you lose it, you have to reset and re-add to Secret Manager.

---

## Step 2 — Store the three values in GCP Secret Manager

The Cloud Run service reads these at startup. From your shell:

```bash
GCLOUD="/c/Program Files (x86)/Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd"
PROJECT=adept-mountain-474619-d4

# For each of the three secrets — gcloud will prompt for the value via stdin.
# Paste the value, press Enter, then Ctrl-D (or Ctrl-Z then Enter on Windows).
"$GCLOUD" secrets create discord-app-id      --project=$PROJECT --data-file=-
"$GCLOUD" secrets create discord-public-key  --project=$PROJECT --data-file=-
"$GCLOUD" secrets create discord-bot-token   --project=$PROJECT --data-file=-
```

Verify all three landed:

```bash
"$GCLOUD" secrets list --project=$PROJECT --filter='name~discord' --format='value(name)'
```

Expected output: `discord-app-id`, `discord-public-key`, `discord-bot-token`.

If any value was wrong, replace it with `gcloud secrets versions add <name> --data-file=-` (don't `secrets create` again — it'll error on duplicate).

---

## Step 3 — Grant the runtime SA permission to dispatch Cloud Run Jobs

The interactions service kicks off `premarket-brief` / `insight-pipeline` / etc. as Cloud Run Jobs. Its runtime service account needs `roles/run.developer`:

```bash
"$GCLOUD" projects add-iam-policy-binding $PROJECT \
    --member=serviceAccount:trading-runner@$PROJECT.iam.gserviceaccount.com \
    --role=roles/run.developer
```

(The exact SA name may differ if you're using a different runtime SA — check `gcp/deploy.sh` for the canonical value.)

---

## Step 4 — Deploy the `discord-interactions` Cloud Run service

The repo has a one-line dispatch in `gcp/deploy.sh`:

```bash
cd /path/to/repo
bash gcp/deploy.sh discord
```

This:
1. Builds the existing `trading-system` image (or reuses the cached layer if unchanged).
2. Creates/updates a Cloud Run **service** (not a Job — the interactions endpoint must be HTTP-reachable) named `discord-interactions`.
3. Configures it with `--allow-unauthenticated` (Discord doesn't auth via IAM; the Ed25519 signature *is* the auth), `--min-instances=0` (free when idle), `--max-instances=5`.
4. Mounts the three secrets as env vars: `DISCORD_APP_ID`, `DISCORD_PUBLIC_KEY`, `DISCORD_BOT_TOKEN`.

After deploy, **copy the printed service URL** — you'll paste it into Discord in the next step. Looks like:

```
https://discord-interactions-XXXXXXXXXX-ue.a.run.app
```

You can also retrieve the URL after the fact:

```bash
"$GCLOUD" run services describe discord-interactions \
    --region=us-east1 --project=$PROJECT \
    --format='value(status.url)'
```

### Quick health probe (optional but useful)

Before pasting into Discord, confirm the service is healthy:

```python
# python -c "..."  one-liner
import requests
URL = "https://discord-interactions-XXXXXXXXXX-ue.a.run.app"
print(requests.get(f"{URL}/health", timeout=10).json())
# expect: {"status":"ok","discord_public_key":true,"discord_app_id":true,"discord_bot_token":true}
```

If `/health` returns `200` and all three secret flags are `true`, the service is ready for Discord to validate.

---

## Step 5 — Tell Discord where to send interactions

Go back to https://discord.com/developers/applications → your app → **General Information** tab.

Scroll to **Interactions Endpoint URL** and paste the **service URL with `/discord/interactions` appended**:

```
https://discord-interactions-XXXXXXXXXX-ue.a.run.app/discord/interactions
```

⚠️ The path matters. Without `/discord/interactions` Discord hits the service root and gets a 404. The validation will fail with a red error message right under the field.

Click **Save Changes**. Discord sends a signed `PING` (interaction type 1) to the URL. The service:

1. Verifies the Ed25519 signature using `DISCORD_PUBLIC_KEY`.
2. Replies `{"type": 1}` (PONG) within 50ms.
3. Discord accepts and saves the URL.

Success indicator: a **"All your edits have been carefully recorded"** banner. If validation fails Discord shows a red inline error and the URL is rejected — most common causes:

| Error message | Likely cause | Fix |
|---|---|---|
| "Invalid interactions endpoint URL" | URL responds slowly (>3 sec), returns 5xx, or doesn't match the signature contract | Run the `/health` probe; check Cloud Run logs; confirm `discord-public-key` matches the value on the General Info page |
| "Invalid Public Key" / signature mismatch | The value in Secret Manager doesn't match the key Discord shows on the app's General Info page | `gcloud secrets versions add discord-public-key --data-file=-` to upload the right value, then redeploy the service so the new value gets mounted |
| URL not green / no banner | Sometimes the UI is laggy — refresh the page, look for the banner. If still no save, click Save Changes again. |

---

## Step 6 — Register the four slash commands

Until you do this, Discord doesn't know `/replay`, `/watchlist`, etc. exist. From your shell at the repo root:

```bash
PY="/c/Users/tenei/.pyenv/pyenv-win/versions/3.11.9/python.exe"
GCLOUD="/c/Program Files (x86)/Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd"
PROJECT=adept-mountain-474619-d4

APP_ID=$("$GCLOUD" secrets versions access latest --secret=discord-app-id      --project=$PROJECT)
BOT=$(   "$GCLOUD" secrets versions access latest --secret=discord-bot-token   --project=$PROJECT)

DISCORD_APP_ID="$APP_ID" DISCORD_BOT_TOKEN="$BOT" \
    "$PY" -m scripts.discord.register_commands
```

Expected output:

```
Registering 4 commands at global scope...
OK: registered 4 commands
  /replay     (id=...)
  /validate   (id=...)
  /backtest   (id=...)
  /watchlist  (id=...)
```

The script does an idempotent `PUT` — re-running replaces the registration cleanly.

### Global vs guild registration — pick one

| Mode | Command to run | Propagation | Visibility |
|---|---|---|---|
| **Global** (default, no flag) | `python -m scripts.discord.register_commands` | up to **1 hour** | every server the bot is in |
| **Guild** (instant) | `python -m scripts.discord.register_commands --guild <GUILD_ID>` | seconds | only the named guild |

For first-time testing or iteration on the command shape, **use guild mode** — you'll see the commands within seconds of running the script.

To get your guild ID: enable Discord Developer Mode (User Settings → Advanced → Developer Mode), right-click your server icon in the sidebar → **Copy Server ID**.

Once you're happy with the command surface, re-run without `--guild` to push the same definitions globally so they appear in any future server you add the bot to.

---

## Step 7 — Invite the bot to your server

This is the OAuth2 flow. Without it, slash commands don't appear in your server even after registration.

1. Discord Dev Portal → your app → **OAuth2** tab in the left sidebar → **URL Generator** sub-tab.
2. Under **Scopes**, tick exactly two boxes:
   - ☑ **`bot`**
   - ☑ **`applications.commands`**
3. As soon as `bot` is ticked, a **Bot Permissions** section appears below. Tick the minimum:
   - ☑ **Send Messages**
   - ☑ **Embed Links**
   - ☑ **Use Slash Commands** (sometimes labeled "Send Slash Commands")
   - ☑ Read Message History (optional, useful for debugging)
4. Skip everything else — admin, manage server, kick/ban, etc. are not needed.
5. The **Generated URL** field at the bottom will populate. Looks like:

   ```
   https://discord.com/oauth2/authorize?client_id=...&permissions=...&scope=bot+applications.commands
   ```

6. Copy the URL, **open it in a new browser tab**, pick your server from the dropdown, click **Authorize**, solve the captcha if prompted.
7. Discord shows a green-checkmark **"Success!"** screen with the message *"<YourBotName> has been authorized and added to <YourServerName>."* You can close that tab.
8. The bot should now appear in your server's member list (right sidebar in Discord). Slash commands show up in the autocomplete picker within ~5 seconds (or up to 1 hour for global commands; instant for guild-registered).

If you don't see the **Success!** screen, the most common causes are:

| Symptom | Cause | Fix |
|---|---|---|
| "Bots cannot have a manage server permission" | You ticked **Administrator** or **Manage Server** in Bot Permissions | Untick those — the bot only needs Send Messages / Embed Links / Use Slash Commands. Re-copy the URL. |
| Server not in the dropdown | You don't have **Manage Server** permission on that guild | Ask the server owner to do the invite, or get the role granted. |
| "Invalid OAuth2 redirect URI" | App was set up with a custom redirect; OAuth2 URL Generator picks the implicit flow | Discord Dev Portal → OAuth2 → Redirects → confirm there's no stale entry blocking the implicit flow. |

---

## Step 8 — Test it

In any channel where the bot can post, type `/replay` and check that:

1. Discord's autocomplete shows `/replay` with two options: `ticker` and `date`.
2. `ticker:` is dynamically autocompleted as you type — values come from the `watchlists` table in Cloud SQL via the service's autocomplete handler.
3. Submitting `/replay ticker:IWM date:-1` produces a "🔄 Replaying IWM as of YYYY-MM-DD..." deferred message within 3 seconds.
4. ~90 seconds later, two embeds land in the channel: the brief and the AI insight.
5. Discord's deferred message updates to "✅ Done — see embeds above" (or an error message if any job failed).

---

## Troubleshooting

### `/replay` doesn't appear when I type `/`
- Wait 60 seconds (global commands are client-cached). Then `Ctrl+R` to hard-reload Discord.
- If still nothing: re-run the registration script with `--guild <GUILD_ID>` for instant propagation.
- Confirm the bot is actually in the server (right sidebar member list).
- Confirm the bot has the `applications.commands` scope by re-running the OAuth2 invite URL.

### `/replay` appears but does nothing on submit
- The Interactions URL probably isn't validated. Go back to General Information and click Save Changes — Discord re-PINGs.
- Tail the service logs while you click Save:
  ```bash
  "$GCLOUD" run services logs read discord-interactions \
      --region=us-east1 --project=$PROJECT --limit=20
  ```
  You should see one POST `/discord/interactions` with `type:1` returning 200.
- If the service log shows `401 invalid signature` on the PING, the `discord-public-key` secret value is wrong. Update it (`gcloud secrets versions add ...`), redeploy the service to mount the new secret value, save the URL in Discord again.

### "Application did not respond" red error message in Discord
- The service took longer than 3 seconds to acknowledge. Two possible fixes:
  - Set `--min-instances=1` on the Cloud Run service (~$5/mo always-warm) — eliminates cold-start.
  - Or wait and retry — subsequent calls within ~15 min hit a warm container and ack in <500ms.

### Cloud Run service deploys but `/health` returns 500
- Most likely a missing or malformed secret. Check `/health` JSON response — if any of `discord_public_key` / `discord_app_id` / `discord_bot_token` are `false`, that secret either doesn't exist or didn't mount.
- Check the service's env-var configuration:
  ```bash
  "$GCLOUD" run services describe discord-interactions \
      --region=us-east1 --project=$PROJECT \
      --format='value(spec.template.spec.containers[0].env[].name)'
  ```
  Should list all three.

### Bot token leaked / committed accidentally
1. Discord Dev Portal → Bot tab → **Reset Token** immediately.
2. `gcloud secrets versions add discord-bot-token --project=$PROJECT --data-file=-` with the new value.
3. Redeploy the service so the new version gets mounted: `bash gcp/deploy.sh discord`.

### Need to add a new slash command later
1. Edit `scripts/discord/register_commands.py` — add the new command spec to the `COMMANDS` list.
2. Re-run the registration script. Idempotent `PUT` replaces the registration; no Discord state to clean up.
3. Add the command's handler dispatch case in `gcp/discord_interactions/main.py`.
4. Redeploy: `bash gcp/deploy.sh discord`.

---

## Reference — what the secrets are used for

| Secret | Where it's used | Why |
|---|---|---|
| `discord-app-id` | Discord API base URLs (`/applications/{app_id}/commands`) | Identifies the app when registering commands and for followup webhooks |
| `discord-public-key` | `gcp/discord_interactions/main.py:_verify_signature` | Verifies that incoming requests really come from Discord (Ed25519 signature) |
| `discord-bot-token` | `scripts/discord/register_commands.py` + the service's followup-webhook calls | Authenticates the bot when posting commands or editing followup messages |

The first two are public-ish (the app ID is in every interaction URL; the public key is shown openly in the Dev Portal). The bot token is the one that absolutely must stay in Secret Manager — anyone with it can impersonate the bot.

---

## Re-bootstrapping after a long gap

If you come back to this in a few months and forget where you left off, here's the quick-check sequence:

```bash
# 1. Service still healthy?
URL=$("$GCLOUD" run services describe discord-interactions --region=us-east1 \
      --project=$PROJECT --format='value(status.url)')
"$PY" -c "import requests; print(requests.get('$URL/health', timeout=10).json())"

# 2. Commands still registered? (lists global commands)
APP_ID=$("$GCLOUD" secrets versions access latest --secret=discord-app-id --project=$PROJECT)
BOT=$(   "$GCLOUD" secrets versions access latest --secret=discord-bot-token --project=$PROJECT)
"$PY" -c "
import requests
r = requests.get(f'https://discord.com/api/v10/applications/$APP_ID/commands',
                 headers={'Authorization': f'Bot $BOT'}, timeout=10)
print([c['name'] for c in r.json()])
"
# expect: ['replay', 'validate', 'backtest', 'watchlist']

# 3. Bot still in the server? — eyeball the member list in Discord. If missing,
#    re-run the OAuth2 invite URL (Step 7).
```

If all three pass, type `/replay` in a channel and you're good. If any fail, jump to the relevant step above.
