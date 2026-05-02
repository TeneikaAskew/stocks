# Prompt: regenerate COST_ANALYSIS.md

You are Claude. Regenerate `COST_ANALYSIS.md` from scratch using the inputs available.

## Inputs

- `billing_90d.json` — output of a BigQuery query against `adept-mountain-474619-d4.billing_export.gcp_billing_export_v1_*`. Schema: `[{service, sku, cost_usd, month}]`. Window: trailing 90 days from run time.
- `ARCHITECTURE.md` — fresh component inventory (regenerated in the same workflow run, before this prompt fires)
- The previous `COST_ANALYSIS.md` if one exists (style reference only)

## What to produce

`COST_ANALYSIS.md` at the repo root with these sections:

### 1. Total spend by month

A table covering the trailing 90-day window. Columns: Month | Spend (USD) | Notes. Flag partial months explicitly (the 90-day window often catches only the trailing few days of the oldest month).

### 2. Top 10 cost line items by SKU

A table sorted by 90-day cost descending. Columns: Rank | Service | SKU | 90-day cost | F/M/A breakdown | Maps to (ARCHITECTURE.md). For each SKU, identify which component from the inventory it represents. **If you can't confidently map a SKU to a component, say "not attributable from billing export alone" rather than guessing.**

### 3. Per-component cost estimate

For each major component (Cloud SQL, Cloud Run Jobs aggregate, Cloud Scheduler, Cloud Run Services, GCS, Artifact Registry, Vertex AI, etc.):

- The total 90-day cost for that component
- Per-job/per-resource breakdown where the SKU permits it
- **Flag fuzzy allocations.** If the SKU is "Cloud Run Jobs CPU in us-east1" — that's one number across all 27 jobs. State the allocation method explicitly: "best-effort proportional to runs-per-week × CPU-sec/run."
- Specifically section "Not attributable from billing export alone" — list things billing can't tell us (per-job costs, per-table SQL costs, Discord egress).

### 4. Anomalies

Investigate any of:
- **Month-over-month change > 50%** in any line item — could be usage change, credit application, or backfill spike
- **$0.00 cost for SKUs that should have nonzero spend** — Vertex AI Gemini at $0 for 90 days is suspicious if the insight pipeline is supposed to be running
- **Trending up month over month** — anything growing at a rate that would 2x within 90 days

For each, note: probable cause, how to confirm, urgency.

### 5. Cost-reduction recommendations

Three concrete recommendations, ranked by estimated monthly savings. For each:
- The specific resource to change
- The exact change (gcloud command or config edit)
- Estimated $/month saving
- Risk + validation step before pulling the trigger

**Do not propose recommendations without a $/month estimate.** Vague advice ("consider optimizing") is worse than nothing.

## Rules

- **Numbers must be honest.** If the data says $9.16, write $9.16 — don't round to $10 for prose.
- **Total spend at top.** First sentence of the doc should answer "what does this cost me per month."
- **No projections beyond what billing data supports.** Don't extrapolate trend lines from 2 months of data.
- **Date the doc.** Last line: `Generated YYYY-MM-DD by .github/workflows/refresh-architecture-docs.yml`.

When done, write the file and exit. Do not narrate.
