# Prompt: regenerate COST_ANALYSIS.md

You are an automated documentation agent. Regenerate `COST_ANALYSIS.md` from the billing digests.

**Output discipline (read this twice).** Produce the file with the **`write_file`** tool (`file_path: "COST_ANALYSIS.md"`, full markdown body). No stdout output, no preamble, no summary.

## Inputs (under `refresh-inputs/`)

- `billing_by_month.csv` — `month, cost_usd` for the trailing 90 days (read this first; it is the headline).
- `billing_by_sku.csv` — `service, sku, cost_usd_90d`, sorted descending (read this second).
- `billing.json` — the raw `[{service, sku, cost_usd, month}]` rows, only if you need a per-month split for one SKU. Read it with `offset`/`limit`; **never conclude a month or SKU is absent because a read was truncated** — the CSVs above are complete.
- `live.json` — `counts.jobs`, `counts.schedulers`, `counts.services`, `sql` (tier, disk), `image_tags`; use these for the per-component allocation.
- `repo_inventory.json` → `schedulers` (cron per job) for runs-per-month estimates.
- The fresh `ARCHITECTURE.md` §3/§6 for the component map.
- The previous `COST_ANALYSIS.md` (style reference only).

## What to produce

### 1. Total spend by month
Table from `billing_by_month.csv`: Month | Spend (USD) | Notes. Flag partial months (the oldest month in a 90-day window, and the current month).

### 2. Top 10 cost line items by SKU
From `billing_by_sku.csv`: Rank | Service | SKU | 90-day cost | Maps to (ARCHITECTURE.md component). If a SKU cannot be mapped, write "not attributable from billing export alone".

### 3. Per-component cost estimate
Cloud SQL, Cloud Run Jobs (one SKU across all N jobs — allocate best-effort by runs-per-month × typical duration, from the schedulers), Cloud Run Services (per service where the SKU permits), Cloud Scheduler (N entries, 3 free), Artifact Registry, GCS, Vertex AI, Secret Manager, Pub/Sub, Logging, Cloud Build. State the allocation method. Include "Not attributable from billing export alone".

### 4. Anomalies
Month-over-month change > 50% in any line item; $0.00 for SKUs that should be non-zero (Vertex AI when the insight pipeline runs daily); anything trending to double within 90 days. For each: probable cause, how to confirm (a gcloud or Console step), urgency.

### 5. Cost-reduction recommendations
Three, ranked by $/month, each with the resource, the exact change (gcloud command or config edit), the estimate, the risk and a validation step. Reference `docs/audits/COST_AUDIT_2026-09-06.md` if present rather than repeating it.

## Rules

- Numbers must be honest: write what the CSV says, never round for prose.
- Total spend in the first sentence.
- No projections beyond the data.
- Use the live counts for N jobs / N schedulers; never hardcode a number from an older version.
- A missing or empty input is a hard stop: print one line naming it and stop without writing.
- Last line: `Generated YYYY-MM-DD by .github/workflows/refresh-architecture-docs.yml`.

When done, stop. Do not narrate.
