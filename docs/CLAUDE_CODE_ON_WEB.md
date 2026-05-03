# Claude Code on the Web — Setup, Patterns, and Gotchas

A field guide for using **Claude Code on the web** (claude.ai/code) with this repo, especially from a phone-only session where the sandbox can't reach Cloud SQL or run `gh`/`gcloud` natively.

> **Audience.** Anyone (you, future Claude sessions, a teammate) needing to operate this repo from a web sandbox.
>
> **Source of truth.** Patterns here were validated end-to-end during PR #235 (the `db-query.yml` workflow). When something says "we hit X" it means we hit X on a real run, not a hypothetical.

---

## TL;DR

| Need | Path |
|---|---|
| Run a SQL query against Cloud SQL | Dispatch `.github/workflows/db-query.yml` |
| Use `gh` / `gcloud` from the sandbox | Install via SessionStart script (not pre-installed) |
| Authenticate to GCP | `gcloud auth activate-service-account` with `claude-web@` SA key |
| Authenticate to GitHub | PAT pulled from GCP Secret Manager (`gh-stocks-repo-pat`) |
| Make Claude react to PR events | Subscribe to PR webhooks; a `UserPromptSubmit` hook reminds Claude to fetch live state before reasoning |
| Add a "from now on, always X" rule | Add a hook in `.claude/settings.json` — memory alone won't enforce it |
| Run Python against real Cloud SQL one-off (no workflow yet) | Cloud Build escape hatch with the `claude-web@` SA |

---

## Why this guide exists

Claude Code on the web runs in a sandbox that:

- **Blocks all outbound TCP except port 443.** Cloud SQL Postgres (5432) and the Cloud SQL Auth Proxy (3307) are unreachable. Adding the sandbox's egress IP to authorized networks doesn't help — the binding constraint is the sandbox firewall, not the database ACL.
- **Doesn't pre-install `gh` or `gcloud`.** Both must be installed per session via a SessionStart script.
- **Doesn't have native GitHub Actions dispatch tooling.** From the sandbox you can read GitHub state via the MCP tools (`mcp__github__*`) but you cannot trigger workflows, read run logs, or download artifacts via MCP — those need the REST API + a PAT.

This guide captures the patterns that make this workable, distilled from a session that built the `db-query.yml` workflow specifically to work around these constraints.

---

## The sandbox model — what's available

| Capability | State |
|---|---|
| Outbound TCP 443 (HTTPS) | ✅ allowed |
| Outbound TCP 5432 (Postgres) | ❌ blocked |
| Outbound TCP 3307 (Cloud SQL Auth Proxy backend) | ❌ blocked |
| `gcloud`, `gh` CLIs pre-installed | ❌ install per session |
| Python with stdlib + project requirements.txt | ✅ via `pip install -r requirements.txt` |
| `git` (against the sandbox's local proxy) | ✅ |
| GCS, Cloud Build, Cloud SQL Admin API (over 443) | ✅ |
| GitHub REST API (over 443) | ✅ with a PAT |
| MCP GitHub tools (read state) | ✅ — `pull_request_read`, `list_issues`, etc. |
| MCP GitHub tools (workflow dispatch / artifact download) | ❌ — these endpoints are not exposed via MCP, use REST |

Anything that resolves to a non-443 port — direct DB connections, SSH, custom protocols — has to be reached **via something the sandbox can talk to over 443**: the GitHub REST API (workflow dispatch) or a GCP service (Cloud Build, GCS, Cloud Run jobs).

---

## One-time setup: the SessionStart script

The harness runs a SessionStart hook each time a new web session begins. The script below installs `gcloud` and `gh`, activates GCP with the `claude-web@` service-account key, and authenticates `gh` with the PAT from the sandbox's environment variable. It self-tests every step so a missing dep, expired key, or revoked PAT fails loudly at session start instead of mid-task.

> **Where to put this.** This script lives in your Claude Code on the web project settings as the SessionStart command. Use the [`session-start-hook` skill](https://docs.claude.com/) to wire it in if you're configuring it from a fresh session. The script is idempotent — re-running it on an already-set-up session is a no-op except for the smoke tests.

```bash
#!/bin/bash
set -euo pipefail

# ---------------------------------------------------------------------
# 0. Install gcloud SDK and GitHub CLI (neither is pre-installed)
# ---------------------------------------------------------------------
apt-get update -qq || true
apt-get install -y -qq apt-transport-https ca-certificates gnupg curl

# gcloud repo
curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
  | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
  > /etc/apt/sources.list.d/google-cloud-sdk.list

# gh repo
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  | tee /usr/share/keyrings/githubcli-archive-keyring.gpg > /dev/null
chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
  > /etc/apt/sources.list.d/github-cli.list

apt-get update -qq || true
apt-get install -y -qq google-cloud-cli gh

# Smoke test 0
gcloud --version | head -1
gh --version | head -1

# ---------------------------------------------------------------------
# 1. Write the GCP service account key to disk
# ---------------------------------------------------------------------
KEY_PATH="/home/user/.gcp-key.json"
mkdir -p "$(dirname "$KEY_PATH")"
cat > "$KEY_PATH" <<'EOF'
{
  "type": "service_account",
  "project_id": "adept-mountain-474619-d4",
  "private_key_id": "<redacted>",
  "private_key": "-----BEGIN PRIVATE KEY-----\n<redacted>\n-----END PRIVATE KEY-----\n",
  "client_email": "claude-web@adept-mountain-474619-d4.iam.gserviceaccount.com",
  "client_id": "<redacted>",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/claude-web%40adept-mountain-474619-d4.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}
EOF
chmod 600 "$KEY_PATH"

# Smoke test 1
[ -s "$KEY_PATH" ] || { echo "ERROR: key file empty or missing"; exit 1; }
python3 -c "import json; json.load(open('$KEY_PATH'))"

# ---------------------------------------------------------------------
# 2. Activate gcloud with the service account
# ---------------------------------------------------------------------
gcloud auth activate-service-account --key-file="$KEY_PATH" --quiet
gcloud config set project adept-mountain-474619-d4 --quiet
gcloud config set compute/region us-central1 --quiet
gcloud config set compute/zone us-central1-a --quiet

# Smoke test 2
ACTIVE_ACCT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)")
[ -n "$ACTIVE_ACCT" ] || { echo "ERROR: no active gcloud account"; exit 1; }

# ---------------------------------------------------------------------
# 3. Authenticate gh
# ---------------------------------------------------------------------
if [ -z "${CLAUDE_CODE_STOCKS_PAT:-}" ]; then
  echo "ERROR: CLAUDE_CODE_STOCKS_PAT not set in environment variables."
  exit 1
fi
echo "$CLAUDE_CODE_STOCKS_PAT" | gh auth login --with-token

# Smoke test 3
gh auth status

# ---------------------------------------------------------------------
# 4. Python deps
# ---------------------------------------------------------------------
if [ -f requirements.txt ]; then
  pip install --quiet -r requirements.txt
  pip check || echo "WARN: pip check reported issues (non-fatal)"
fi

# ---------------------------------------------------------------------
# 5. Frontend deps
# ---------------------------------------------------------------------
if [ -f platform/package.json ]; then
  (cd platform && npm ci --silent)
  [ -d platform/node_modules ] || { echo "ERROR: node_modules not created"; exit 1; }
fi

echo "==================================="
echo "All setup steps passed"
echo "  gcloud account: $ACTIVE_ACCT"
echo "  gcloud project: $(gcloud config get-value project)"
echo "  gh user:        $(gh api user -q .login)"
echo "==================================="
```

### Lessons baked into this script

- **`set -euo pipefail`** at the top. Without `-u` an unset env var silently becomes an empty string and the failure surfaces 50 lines later as a confusing API error.
- **Smoke test after every section.** Step 0 and step 3 caught real failures during development (missing apt key, expired PAT). The cost of the test is milliseconds; the cost of debugging a half-set-up session is much higher.
- **`apt-get update -qq || true`** — apt updates can fail transiently in the sandbox image; we tolerate the failure but require the install step to succeed.
- **`chmod 600 "$KEY_PATH"`** — the key is sensitive; restrict perms even though only one user runs in the sandbox.

### Migrating away from the env-var PAT

The script reads the PAT from `CLAUDE_CODE_STOCKS_PAT` (a Claude Code on the web env var). **The longer-term pattern is to fetch it from GCP Secret Manager** (`gh-stocks-repo-pat`) so there's one source of truth and rotation is a single `gcloud secrets versions add` call. To switch:

```bash
# Replace step 3 with:
GH_TOKEN=$(gcloud secrets versions access latest \
  --secret=gh-stocks-repo-pat \
  --project=adept-mountain-474619-d4)
echo "$GH_TOKEN" | gh auth login --with-token
unset GH_TOKEN
```

Why bother:
- The env var lives in two places (GitHub PAT settings + Claude Code on the web env vars). Rotation = update both.
- Secret Manager has a GCP audit log; env vars don't.
- Anyone with `roles/secretmanager.secretAccessor` (which `claude-web@` already has via project-level `roles/editor`) can fetch the latest version without further setup.

---

## Pattern 1: PAT management via GCP Secret Manager

The PAT is the highest-value credential in this workflow — it can dispatch any GitHub Action, write to any file, merge any PR. Treat it accordingly.

### Storage

```
GCP project: adept-mountain-474619-d4
Secret name: gh-stocks-repo-pat
SA with read access: claude-web@... (via project-level roles/editor)
```

### Required scopes for the PAT itself

Use a **fine-grained PAT** scoped to only `TeneikaAskew/stocks`, with:

- `Actions: Read & Write` — required to dispatch `db-query.yml` and read run state
- `Contents: Read` — required to push to feature branches via API (PR creation)
- `Issues: Read & Write` — required to post comments and create tracking issues
- `Pull requests: Read & Write` — required to open / comment on PRs
- `Metadata: Read` — required for almost every API call (always on)

That's the minimum. Don't grant scopes you won't use.

### Rotation

```bash
read -s NEW && echo -n "$NEW" \
  | gcloud secrets versions add gh-stocks-repo-pat \
      --data-file=- \
      --project=adept-mountain-474619-d4 \
  && unset NEW
```

Consumers fetch `latest`, so a new version is picked up transparently. Old versions stay accessible (audit trail) until you explicitly destroy them.

### Anti-patterns

| Don't | Why |
|---|---|
| Paste the PAT value in chat | Logged in conversation transcripts; visible to anyone with access to the session |
| Pass it inline in `curl` argv (`-H "Authorization: Bearer ghp_..."`) | Visible in `/proc/<pid>/cmdline` to other processes on the sandbox |
| Store it in `~/.netrc` permanently | Leaks across `git push` operations; harder to rotate |
| Grant it `repo` (classic) scope | Far broader than needed — fine-grained tokens are scoped to one repo + minimum permissions |

### Correct usage pattern

```bash
# Fetch once per session into a shell variable, never echo it
GH_TOKEN=$(gcloud secrets versions access latest \
  --secret=gh-stocks-repo-pat \
  --project=adept-mountain-474619-d4)

curl -sS -H "Authorization: Bearer $GH_TOKEN" \
  "https://api.github.com/repos/TeneikaAskew/stocks/..."

unset GH_TOKEN  # at end of session if you're paranoid
```

---

## Pattern 2: Cloud SQL access via `db-query.yml`

The keystone pattern of this guide. Built specifically because the sandbox can't reach Cloud SQL.

### How it works

```
Claude on web (sandbox)
       │
       │ HTTPS (443) only
       ▼
  GitHub REST API
       │ workflow_dispatch
       ▼
  GitHub Actions runner ── unrestricted egress ──► Cloud SQL
       │
       │ uploads results.json + summary.md as artifact
       │ optionally posts a comment on a tracking issue
       ▼
  Claude downloads artifact / reads issue comment
```

The runner has full network access; the sandbox doesn't. We borrow the runner's connectivity for the duration of one query.

### Dispatch from a session

```bash
# Read query
GH_TOKEN=$(gcloud secrets versions access latest \
  --secret=gh-stocks-repo-pat --project=adept-mountain-474619-d4)

curl -sS -X POST \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/TeneikaAskew/stocks/actions/workflows/db-query.yml/dispatches \
  -d '{
    "ref":"main",
    "inputs":{"sql":"SELECT count(*) FROM trades WHERE date > current_date - 7"}
  }'

# Poll the most recent run
RUN_ID=$(curl -sS -H "Authorization: Bearer $GH_TOKEN" \
  "https://api.github.com/repos/TeneikaAskew/stocks/actions/workflows/db-query.yml/runs?per_page=1" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['workflow_runs'][0]['id'])")

# Wait for completion (poll every 5s)
while true; do
  STATUS=$(curl -sS -H "Authorization: Bearer $GH_TOKEN" \
    "https://api.github.com/repos/TeneikaAskew/stocks/actions/runs/$RUN_ID" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'], d.get('conclusion','-'))")
  echo "$STATUS"
  [[ "$STATUS" == completed* ]] && break
  sleep 5
done

# Download the artifact
ARTIFACT_ID=$(curl -sS -H "Authorization: Bearer $GH_TOKEN" \
  "https://api.github.com/repos/TeneikaAskew/stocks/actions/runs/$RUN_ID/artifacts" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['artifacts'][0]['id'])")
curl -sS -L -H "Authorization: Bearer $GH_TOKEN" \
  -o /tmp/results.zip \
  "https://api.github.com/repos/TeneikaAskew/stocks/actions/artifacts/$ARTIFACT_ID/zip"
unzip -o /tmp/results.zip -d /tmp/qresults
cat /tmp/qresults/summary.md
```

### Safety model

- **Default is `commit=false`** — every transaction rolls back at the end. A read query gets the same treatment (rollback is a no-op for SELECT). A typo'd UPDATE/DELETE without `commit=true` is a deliberate no-op; the summary shows `↩️ rolled back` so you know.
- **Per-statement transactions** — multi-statement input runs each statement in its own transaction. A user error (syntax, constraint) in statement 2 doesn't kill statements 1 and 3.
- **User-error vs system-error classification** — Postgres SQLSTATE classes 22/23/25/42 + 57014 (timeout) are USER errors (workflow exits 0, no failure handler). Class 08* (connection) is a SYSTEM error (workflow exits 1, `handle-failure` triggers).

### Memory safety: the three row-cap strategies

For a SELECT that returns potentially huge results, pg8000 (the driver) buffers the full result client-side before `fetchmany` returns. Without intervention, a `SELECT * FROM huge_table` would OOM the runner. Three strategies, picked automatically:

| Strategy | When it's used | How it caps |
|---|---|---|
| `server_limit` | Single SELECT, no `FOR UPDATE`/`FOR SHARE`/`INTO` | Wraps as `SELECT * FROM (<user_sql>) _q LIMIT 50001` — Postgres caps server-side |
| `server_cursor` | Non-wrappable SELECT (e.g. `FOR UPDATE`) | `DECLARE _claude_cur NO SCROLL CURSOR FOR <stmt>` + `FETCH FORWARD 50001` — Postgres still caps server-side |
| `client_fetchmany` | Statement Postgres won't cursor (utility, certain DDL) | `fetchmany(50001)` — pg8000 buffers everything, OOM risk for >7 GB results, `statement_timeout` bounds wall-time |

The `summary.md` reports which was used per statement so you know whether truncation is exact or best-effort.

### Multi-statement vs file-based input

- **Inline `sql`** with `;` separators: `sqlparse.split` parses them. **Don't use this for `DO $$...$$` blocks or `CREATE FUNCTION ... LANGUAGE plpgsql`** — the splitter is naive about embedded semicolons.
- **`sql_file`** with a path to a committed `.sql` file: file content is sent as **one** statement, no splitting. Use this for any DDL with embedded semicolons.

### Tracking issue ergonomics

Set the repo variable once:

```bash
gh variable set DB_QUERY_TRACKING_ISSUE -b <issue-number>
```

Now every dispatch posts the summary there by default — you don't pass `-f issue_number=` each time. Phone-friendly: read the issue comments via the GitHub mobile app or `gh issue view ...`.

---

## Pattern 3: Webhook reconciliation hook

When you subscribe a session to PR webhook events (the `<github-webhook-activity>` blocks), they arrive **queued**. By the time Claude sees one, the underlying state may have changed:

- The PR comment was edited
- The CI run finished
- The review was dismissed
- The PR was merged

Acting on the webhook payload alone produces stale conclusions. We literally hit this on PR #235 — a "branding footer is present" notification arrived seconds after the PATCH that stripped it.

### The fix: a UserPromptSubmit hook

`.claude/settings.json` (committed, team-wide):

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "jq 'if (.prompt // \"\" | contains(\"<github-webhook-activity>\")) then {hookSpecificOutput: {hookEventName: \"UserPromptSubmit\", additionalContext: \"Before acting on this webhook event: fetch the current state of the referenced GitHub object (PR comment, review, issue, run, commit) via the GitHub REST API before reasoning. Webhooks lag — the underlying state may have already changed (comment edited, CI run finished, review dismissed, PR merged). Reconcile against live state, then decide.\"}} else empty end'"
          }
        ]
      }
    ]
  }
}
```

The matcher uses `contains("<github-webhook-activity>")` — the literal angle-bracketed tag, not the casual phrase. Verified four cases:

1. Real webhook → emits the reminder ✅
2. Casual mention without angle brackets → no output ✅
3. Unrelated prompt → no output ✅
4. Missing `prompt` field → defensive `// ""` → no output, no error ✅

### Activation caveat

The Claude Code settings watcher only watches `.claude/` directories that **had a settings file at session start**. Sessions older than the commit that introduced `.claude/settings.json` won't pick it up automatically — they need to either run `/hooks` once (reloads config) or restart. New sessions auto-load.

### Generalization

The same pattern (`UserPromptSubmit` + `additionalContext` injection) is the right tool for any "from now on, always X" rule that needs harness-level enforcement. Memory and preferences alone don't reliably enforce automated behaviours — only the harness can.

---

## Pattern 4: Cloud Build as a one-off escape hatch

Sometimes you need to run Python against real Cloud SQL **before** the workflow you want exists. Cloud Build is the bridge.

When we built `db-query.yml`, the runner script (`gcp/queries/run_query.py`) couldn't be tested via the workflow itself (chicken/egg). Instead:

```yaml
# /tmp/cb-test/cloudbuild.yaml
steps:
  - name: python:3.11-slim
    entrypoint: bash
    secretEnv: ['DB_USER_SECRET', 'DB_PASS_SECRET', 'DB_CONN_SECRET']
    args:
      - -c
      - |
        set -e
        export DB_USER="$$DB_USER_SECRET"
        export DB_PASS="$$DB_PASS_SECRET"
        export CLOUD_SQL_CONNECTION_NAME="$$DB_CONN_SECRET"
        export DB_NAME=trading
        pip install --quiet -r requirements-gcp.txt sqlparse tabulate
        python gcp/queries/run_query.py --sql 'SELECT current_database(), current_user, version()' --output-dir /tmp/out
        cat /tmp/out/summary.md
availableSecrets:
  secretManager:
    - versionName: projects/adept-mountain-474619-d4/secrets/db-trading-user/versions/latest
      env: DB_USER_SECRET
    - versionName: projects/adept-mountain-474619-d4/secrets/db-trading-pass/versions/latest
      env: DB_PASS_SECRET
    - versionName: projects/adept-mountain-474619-d4/secrets/cloud-sql-connection-name/versions/latest
      env: DB_CONN_SECRET
options:
  logging: CLOUD_LOGGING_ONLY
```

```bash
gcloud builds submit . --config=cloudbuild.yaml --region=global \
  --service-account=projects/adept-mountain-474619-d4/serviceAccounts/claude-web@adept-mountain-474619-d4.iam.gserviceaccount.com
```

### When to use Cloud Build vs `db-query.yml`

| Scenario | Use |
|---|---|
| You need to run an existing reusable script against Cloud SQL | **`db-query.yml`** |
| You're developing the script that reads the DB; the workflow doesn't exist yet | Cloud Build (one-off) |
| You need to test changes to `gcp/database.py` itself | Cloud Build (the workflow uses it; testing it via the workflow is circular) |
| You need network-level access to a non-Cloud-SQL service over a non-443 port | Cloud Build |

After this PR merges, **Cloud Build is dead for ad-hoc DB queries.** Use the workflow.

### `$$` escaping in Cloud Build YAML

Cloud Build performs its own substitution before the shell runs. To get a literal `$` in the executed shell, write `$$` in the YAML. So `$$DB_USER_SECRET` (in YAML) → `$DB_USER_SECRET` (shell sees) → expanded by bash. We hit this — using a single `$` in the Cloud Build YAML caused the build to fail with empty env vars.

---

## GitHub Actions gotchas

### `workflow_dispatch` requires the workflow file on the default branch

GitHub registers `workflow_dispatch` workflows only after their YAML file lands on `main` (or whatever default branch the repo uses). Until that point:

- `gh workflow run db-query.yml` returns 404
- `curl -X POST .../actions/workflows/db-query.yml/dispatches` returns 404
- The GitHub UI's "Run workflow" button **does not appear** for the workflow

This means **you cannot smoke-test a new `workflow_dispatch` workflow on a feature branch.** The smoke test happens after merge. Plan accordingly:

1. Validate the substantive logic via Cloud Build (Pattern 4) on the feature branch
2. Merge to main
3. Smoke-test the workflow YAML wiring on `main`

Do NOT add a temporary `push:` trigger on the feature branch as a workaround for this — the workflow runs arbitrary user-supplied SQL, and a `push:` trigger means every push to the branch dispatches it with hardcoded inputs, which is its own problem.

### Workflow registration is **per-file-on-default-branch**, not per-repo

Each workflow's first appearance on the default branch is what registers it. Renaming a file is treated as deleting the old one and registering the new one. Plan rename PRs accordingly.

### `handle-failure` job permissions

The reusable `.github/workflows/handle-workflow-failure.yml` requires `pull-requests: write` and `actions: read` on the calling job. If you forget these, the failure handler runs but can't actually create the issue/PR — and you find out hours later when scheduled jobs start silently failing.

### Secret naming for blast-radius isolation

`db-query.yml` uses `CLAUDE_CODE_WEB_GCP_SA_KEY`, distinct from the `GCP_SA_KEY` that data-pipeline workflows use. Why: the db-query workflow runs arbitrary user-supplied SQL, which is a different trust profile than scheduled fetchers. A key compromise on the db-query SA shouldn't take out the data pipeline.

Same logic for the `PR_WORKFLOW_TOKEN` (used by `handle-workflow-failure.yml` to create PRs from the bot account). Different blast radius, different key.

---

## MCP caveats

The `mcp__github__*` tools are useful for **reading** repo state — `pull_request_read`, `list_issues`, `list_branches`, `get_file_contents`. Use them freely.

Be careful with the **writing** tools:

### `add_reply_to_pull_request_comment` auto-appends Claude branding

When you reply to a PR review comment via this tool, the body that lands on GitHub is **your text + a `_Generated by [Claude Code](https://claude.ai/code)_` footer that the tool injects**. This violates this repo's CLAUDE.md rule #2 (no Claude branding in commits — extends in spirit to PR comments).

**Workaround:** for any PR comment you intend to leave, use a direct REST API call instead:

```bash
GH_TOKEN=$(gcloud secrets versions access latest --secret=gh-stocks-repo-pat --project=adept-mountain-474619-d4)

curl -sS -X POST \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/TeneikaAskew/stocks/pulls/235/comments/<id>/replies" \
  -d '{"body": "your reply"}'
```

Or, after using the MCP tool, immediately PATCH the resulting comment to strip the footer:

```bash
curl -sS -X PATCH \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/TeneikaAskew/stocks/pulls/comments/<id>" \
  -d '{"body": "your reply without the footer"}'
```

### MCP doesn't expose Actions endpoints

There's no `mcp__github__dispatch_workflow` or `mcp__github__download_artifact`. For anything Actions-related, drop to the REST API with the PAT. (See Pattern 2.)

---

## Settings file hierarchy

| File | Scope | Git | Use for |
|---|---|---|---|
| `~/.claude/settings.json` | Global (your account) | n/a | Personal preferences across all projects |
| `.claude/settings.json` | Project | **Commit** | Team-wide hooks, permissions, plugin config |
| `.claude/settings.local.json` | Project | **Gitignore** | Personal overrides for this project |

Load order: user → project → local (later overrides earlier).

For "this rule applies to anyone working on this repo from a web sandbox," put it in `.claude/settings.json` and commit it. Examples already in the repo:

- `permissions.allow` for repeated tool patterns (Bash globs)
- `hooks.UserPromptSubmit` for the webhook-reconciliation rule (Pattern 3)

---

## Stop hooks: the git-status guardrail

`~/.claude/stop-hook-git-check.sh` (a personal hook in your global settings, not committed here) emits feedback if you stop a session with uncommitted changes:

```
Stop hook feedback:
[~/.claude/stop-hook-git-check.sh]: There are uncommitted changes
in the repository. Please commit and push these changes to the
remote branch.
```

This is a load-bearing safety check for sessions that build features over many edits — it prevents stopping mid-feature with uncommitted state. Keep this hook (or an equivalent) on for any project where a half-finished session is worse than a fully-committed in-progress one.

---

## Lessons learned (compressed)

These are the things we learned by hitting them, not by reading docs:

1. **The web sandbox is a one-port box.** Plan all access through HTTPS-reachable services (GH API, GCS, Cloud Build, Cloud SQL Admin API, Secret Manager API). Anything that needs a different port has to be brokered.

2. **`workflow_dispatch` is blind to feature branches.** GitHub registers it only via default branch. Validate substantive logic out-of-band (Cloud Build); accept that workflow YAML wiring is post-merge testing.

3. **Webhook events lag.** Every webhook-driven action should fetch live state first and reconcile.

4. **Memory cannot enforce "always X" rules.** That's what hooks are for. If you want a behaviour every session, write a hook.

5. **MCP tools are read-friendly, write-cautious.** Reads are clean; writes can have surprises (auto-appended branding, missing endpoints). Drop to REST when in doubt.

6. **Secrets centralize in GCP Secret Manager.** Env vars are convenient but become two-source-of-truth problems. Secret Manager + a SA with `secretAccessor` is one source, audit-logged, rotation-friendly.

7. **Smoke-test every step of setup.** A SessionStart script that fails halfway leaves a worse state than no setup at all. Test after every `apt-get install`, every `auth activate`, every `pip install`.

8. **Cap memory at the database, not at the client.** pg8000 buffers full results. Server-side LIMIT (subquery wrap) or server-side cursor (`DECLARE`/`FETCH FORWARD`) are the only safe caps for huge results. `fetchmany` after-the-fact is too late.

9. **Per-statement transactions are the ad-hoc default.** Cross-statement atomicity is a separate flag you add when needed. Don't pretend a multi-statement batch is one transaction unless you mean it.

10. **Production-grade architecture means capacity planning at design time.** See [`CLAUDE.md` rule 0](../CLAUDE.md). Three numbers in every PR description: volume, velocity, wall-clock. If wall-clock exceeds Cloud Run task-timeout, the architecture is wrong, not the timeout.

---

## Quick reference

| Task | Command |
|---|---|
| Fetch the GH PAT from Secret Manager | `gcloud secrets versions access latest --secret=gh-stocks-repo-pat --project=adept-mountain-474619-d4` |
| Dispatch a read query | `curl -X POST -H "Authorization: Bearer $GH_TOKEN" .../actions/workflows/db-query.yml/dispatches -d '{"ref":"main","inputs":{"sql":"..."}}'` |
| Dispatch a write query | same, with `"commit": "true"` in inputs |
| List recent runs | `curl -H "Authorization: Bearer $GH_TOKEN" .../actions/workflows/db-query.yml/runs?per_page=5` |
| Download artifact for run | `curl -L -H "Authorization: Bearer $GH_TOKEN" -o /tmp/r.zip .../actions/runs/$RUN_ID/artifacts/<id>/zip` |
| Reload hooks in current session | `/hooks` (TUI menu) |
| Add a "from now on" rule | Use the `update-config` skill to add a hook to `.claude/settings.json` |
| Verify SA has Cloud SQL access | `gcloud projects get-iam-policy adept-mountain-474619-d4 --flatten="bindings[].members" --filter="bindings.members:claude-web@*" --format="value(bindings.role)"` |

---

## See also

- [`CLAUDE.md`](../CLAUDE.md) — full project rules, including the production-grade architecture rule (rule 0) and the database access patterns
- [`docs/GCP_ARCHITECTURE.md`](GCP_ARCHITECTURE.md) — the broader GCP setup
- [`gcp/queries/README.md`](../gcp/queries/README.md) — the SQL files directory convention
- [`.github/workflows/db-query.yml`](../.github/workflows/db-query.yml) — the workflow itself
- [`gcp/queries/run_query.py`](../gcp/queries/run_query.py) — the runner script with full inline documentation
