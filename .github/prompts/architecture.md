# Prompt: regenerate ARCHITECTURE.md

You are Claude. The user has dropped you into the GitHub repo `TeneikaAskew/stocks` (a private stocks/trading platform deployed to GCP project `adept-mountain-474619-d4`). Your job is to regenerate `ARCHITECTURE.md` from scratch using the inputs available in the workspace.

## Inputs you have

- The full repo tree (clone it, treat it as ground truth for code)
- `gcp_inventory.json` — output of `gcloud asset search-all-resources --scope=projects/adept-mountain-474619-d4`. Lists every Cloud Run Job, Service, Scheduler, Secret, Bucket, Pub/Sub topic, BigQuery dataset, IAM service account, etc. that exists right now.
- `gcp_iam.json` — output of `gcloud projects get-iam-policy adept-mountain-474619-d4 --format=json`. Maps every member to the roles they have.
- The previous `ARCHITECTURE.md` if one exists (use it for style + section ordering, but verify every claim against current state — don't blind-copy)

## What to produce

A single `ARCHITECTURE.md` at the repo root with these sections, in this order:

### 1. System overview (one paragraph, ~80-120 words)

What this system does, who runs it, what the primary delivery surfaces are (Discord webhooks for scheduled briefs + slash-command Cloud Run service; secondary internal React + FastAPI dashboard at the `trading-platform` Cloud Run Service). Single-user / small-team — no public auth, no per-user data partitioning. Mention the rough job count derived from `gcp_inventory.json` (filter `assetType=run.googleapis.com/Job`) and the project ID.

### 2. Component inventory (table form)

Two subsections:

#### 2a. Code modules
A table with columns: Component | Type | Purpose | Depends on | Used by. List every Python module under `gcp/`, `gcp/fetchers/`, key `lib/` modules (the shared math), and the FastAPI entry. Cite each as a markdown link to the file path. The "Used by" column should reference the Cloud Run Job or Cloud Scheduler trigger that invokes it (cross-reference `gcp_inventory.json` job names).

#### 2b. GCP resources
A table with columns: Resource | Type | Purpose | Notes. List every:
- Cloud Run Job (filter `assetType=run.googleapis.com/Job` from `gcp_inventory.json`)
- Cloud Run Service (`run.googleapis.com/Service`)
- Cloud Scheduler job (you may need a separate `gcloud scheduler jobs list` if not in inventory)
- Cloud SQL instance (`sqladmin.googleapis.com/Instance`)
- GCS bucket (`storage.googleapis.com/Bucket`)
- Secret Manager secret (`secretmanager.googleapis.com/Secret`)
- Pub/Sub topic
- Cloud Logging sink
- Cloud Tasks queue
- Service account (with the roles each holds, derived from `gcp_iam.json`)

### 3. Data flow (5 named subsections)

Walk the operator through the daily lifecycle:

- **Daily nightly write path (post-close 11 PM ET)** — what jobs run, what tables they write, in what order
- **Daily morning read path (pre-market 7-9 AM ET)** — pre-market refresh → brief → signal monitor
- **On-demand AI insight refresh (Cloud Tasks)** — FastAPI endpoint enqueues, worker picks up, writes `insight_reports`
- **Failure notification** — log sink → Pub/Sub → failure-notifier Cloud Run Service → GitHub issue
- **Discord slash-command path** — `/replay`, `/watch`, `/backtest`, `/validate` commands; how they hit `discord-interactions` Cloud Run Service and trigger Cloud Run Jobs

### 4. Architecture diagram

A Mermaid diagram (`flowchart LR` or `flowchart TD`) showing:
- The 4 primary external inputs (AlphaVantage, FRED, Discord, EDGAR)
- The fetcher → table → consumer flow
- The Cloud Run Services (FastAPI / discord-interactions / failure-notifier)
- The user-facing surfaces (Discord webhook + dashboard)

Group into subgraphs: `External APIs`, `Fetchers (Cloud Run Jobs)`, `Cloud SQL Tables`, `Consumers`, `User Surfaces`.

### 5. Reconciliation flags (review section)

Two subsections — these are **gaps for the operator to investigate**:

- **Inventory resources with no clear repo reference** — anything in `gcp_inventory.json` that isn't named anywhere in the codebase. Could be orphans (need cleanup) or could be missing from docs.
- **Resources the code references that are NOT in the inventory** — `gcp/deploy.sh` mentions a job/scheduler/secret that doesn't exist in live GCP. Could be a deploy that's never been run, or a name drift.

### 6. Open questions

Bulleted list of "things I noticed I couldn't verify with the data given." Be specific — e.g., "Cloud Run Job `fetch-earnings-options` is in inventory but the module `gcp/fetchers/fetch_earnings_options.py` is missing — verify if it's a config-only shell vs broken."

## Rules

- **Cite file paths and `gcp_inventory.json` records** wherever possible. Markdown links to files. Asset names quoted from inventory.
- **Verify against current state.** If the previous ARCHITECTURE.md said job X exists but inventory disagrees, flag the disagreement in §5.
- **Be terse.** Tables, not paragraphs. The doc should fit in <600 lines including the Mermaid.
- **No marketing language.** This is operator documentation, not pitch deck.
- **No secrets in the output.** Names of secrets are fine. Values, never.
- **Date the doc.** Last line: `Generated YYYY-MM-DD by .github/workflows/refresh-architecture-docs.yml`.

When done, write the file and exit. Do not narrate.
