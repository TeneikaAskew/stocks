# Prompt: regenerate docs/product/infrastructure/05-d-COST_ANALYSIS.md

You are an automated documentation agent. Regenerate `docs/product/infrastructure/05-d-COST_ANALYSIS.md` from the billing digests.

**Output discipline (read this twice).** Produce the file with the **`write_file`** tool (`file_path: "docs/product/infrastructure/05-d-COST_ANALYSIS.md"`, given from the repository root, full markdown body). Never a bare `COST_ANALYSIS.md` at the root, never any other directory, and never a second copy. No stdout output, no preamble, no summary.

## Live fleet counts — authoritative, already substituted below

- Cloud Run Jobs: **{{LIVE_JOBS}}**
- Cloud Scheduler jobs: **{{LIVE_SCHEDULERS}}**
- Cloud Run Services: **{{LIVE_SERVICES}}** — {{LIVE_SERVICE_NAMES}}
- Secret Manager secrets: **{{LIVE_SECRETS}}**
- Cloud SQL relations: **{{LIVE_DB_TABLES}}** live, **{{DECLARED_RELATIONS}}** declared, **{{RUNTIME_RELATIONS}}** runtime-created

These counts and the service names beside them were read from `live.json` and
written into this prompt by `scripts/maintenance/render_doc_prompts.py` before
you were called. They are correct as of this run. **Use them verbatim wherever
the document states a count or names a service.** Do not recount them from an
input file, do not derive a count by counting entries you can see in a
truncated read, and do not carry one forward from the previous version of this
document. A 2026-09-07 run wrote a scheduler count under half the live figure
and went red on that single line.

## Inputs (under `refresh-inputs/`)

- `billing_by_month.csv` — `month, cost_usd` for the trailing 90 days (read this first; it is the headline).
- `billing_by_sku.csv` — `service, sku, cost_usd_90d`, sorted descending (read this second).
- `billing.json` — the raw `[{service, sku, cost_usd, month}]` rows, only if you need a per-month split for one SKU. Read it with `offset`/`limit`; **never conclude a month or SKU is absent because a read was truncated** — the CSVs above are complete.
- `live.json` — `counts.jobs`, `counts.schedulers`, `counts.services`, `sql` (tier, disk), `image_tags`; use these for the per-component allocation.
- `repo_inventory.json` → `schedulers` (cron per job) for runs-per-month estimates.
- The fresh `docs/product/infrastructure/05-a-ARCHITECTURE.md` §3/§6 for the component map.
- The previous `docs/product/infrastructure/05-d-COST_ANALYSIS.md` (style reference only).

## What to produce

**Copy the five `### N. ...` headings below into the document word for word**
and use them as the document's `## N. ...` section headings: change the `###`
to `##` and nothing else. Do not add, remove or reword anything in them.
Capitalisation is the one thing not checked — GitHub lowercases heading
anchors, so Title Case breaks no link — but copying them exactly is the
simplest way to satisfy the rule.

They are the spec, not a summary of one: a gate compares each whole heading
against the list below. Run 29 rewrote all five with its own qualifiers ("2.
Top 10 Cost Line Items (90-Day Trailing)" for "2. Top 10 cost line items by
SKU"). Put this month's qualifier in the sentence under the heading, never in
the heading.

### 1. Total spend by month
Table from `billing_by_month.csv`: Month | Spend (USD) | Notes. Flag partial months (the oldest month in a 90-day window, and the current month).

### 2. Top 10 cost line items by SKU
From `billing_by_sku.csv`: Rank | Service | SKU | 90-day cost | Maps to (05-a-ARCHITECTURE.md component). If a SKU cannot be mapped, write "not attributable from billing export alone".

### 3. Per-component cost estimate
Cloud SQL, Cloud Run Jobs (one SKU across all {{LIVE_JOBS}} jobs — allocate best-effort by runs-per-month × typical duration, from the schedulers), Cloud Run Services (per service where the SKU permits), Cloud Scheduler ({{LIVE_SCHEDULERS}} entries, 3 free), Artifact Registry, GCS, Vertex AI, Secret Manager, Pub/Sub, Logging, Cloud Build. State the allocation method. Include "Not attributable from billing export alone".

### 4. Anomalies
Month-over-month change > 50% in any line item; $0.00 for SKUs that should be non-zero (Vertex AI when the insight pipeline runs daily); anything trending to double within 90 days. For each: probable cause, how to confirm (a gcloud or Console step), urgency.

### 5. Cost-reduction recommendations
Three, ranked by $/month, each with the resource, the exact change (gcloud command or config edit), the estimate, the risk and a validation step. Reference `docs/audits/COST_AUDIT_2026-09-06.md` if present rather than repeating it.

## Rules

- Never read or write anything under `docs/product/infrastructure/manual/`: it holds the hand-maintained copies of these documents and is outside the write policy; a change there fails the run.
- **Copy every infrastructure name character for character from wherever you
  read it.** The Cloud Run **service** names are listed above and must be
  copied from there. Every other resource this document names — jobs, the
  Cloud SQL instance, Artifact Registry repositories, schedulers, buckets —
  is not in that list, so take each one from the input file you found it in
  (`live.json`, `repo_inventory.json`, `billing_by_sku.csv`) and copy it
  exactly. Never shorten, singularise or reconstruct a name from memory.
  Run 28 wrote `solyra-api` twice in this document, dropping the environment
  suffix from a service listed above, and the run failed on a service that
  does not exist. A truncated name is the same failure as an invented
  one: `verify_docs_against_live.py` checks every name in this file against
  live GCP and fails the refresh on any that has no match.
- **Every command you write must survive being pasted into a shell.** A
  `gcloud logging read` filter contains spaces and its own quotes, so it needs
  ONE pair of outer quotes and a different quote character inside:
  `gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="X"' --project=adept-mountain-474619-d4 --limit=100`.
  The project id is written out in full there on purpose: a `...` placeholder
  in an example is a thing a model copies verbatim, and the result is both
  unpastable and in breach of the rule below.
  Run 28 wrote the filter with double quotes inside double quotes, which the
  shell splits into four arguments and `gcloud` rejects. A command that errors
  on the first paste costs the reader more than no command at all.
- **The project is `adept-mountain-474619-d4`, region `us-east1`.** Every
  `gcloud` command you write must use that project id. A 2026-09-07 dry run of
  this prompt invented `solyra-trader` in a confirmation command, which makes
  the whole recommendation untrustworthy: a reader who pastes it gets an error
  and stops believing the rest of the document.
- **Check what is already applied before recommending it.** The same dry run
  proposed adding an Artifact Registry cleanup policy that #1004 had already
  deployed. Before writing a recommendation, look for it in `docs/product/infrastructure/05-a-ARCHITECTURE.md`
  §3 (GCP services in use), `docs/audits/COST_AUDIT_2026-09-06.md` and
  `live.json`; if the mitigation exists, say so and quantify what it has
  already saved instead of proposing it again.
- Numbers must be honest: write what the CSV says, never round for prose.
- Total spend in the first sentence.
- No projections beyond the data.
- Every count comes from the **Live fleet counts** block above, verbatim. `repo_inventory.json` → `schedulers` is for per-job cron and runs-per-month only; the number of entries you manage to read out of it is not the fleet count.
- A missing or empty input is a hard stop: print one line naming it and stop without writing.
- Last line: `Generated YYYY-MM-DD by .github/workflows/refresh-architecture-docs.yml`.

When done, stop. Do not narrate.
