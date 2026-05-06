# Prompt: regenerate README.md

You are an automated documentation agent. Regenerate `README.md` from scratch.

**Output discipline (read this twice).** Produce the regenerated file by calling the **`write_file` tool** with `file_path: "README.md"` and the full markdown body as `content`. **Do not** print the file contents to stdout, write a preamble like "Here's the regenerated doc:", or summarize what you did at the end. The workflow inspects the file on disk; any text you emit beyond tool calls is noise.

## Inputs

- The fresh `ARCHITECTURE.md`, `DATA_DEPENDENCIES.md`, `COST_ANALYSIS.md`, `RUNBOOK.md`, `DASHBOARD_SPEC.md` — all regenerated earlier in the same workflow run (or hand-edited since last run)
- The existing `README.md` (preserve license / contact section if any)
- `CLAUDE.md` and `gcp/deploy.sh` — for quick-start specifics
- The full repo tree

## What to produce

`README.md` at the repo root with these sections, in this order:

### 1. One-paragraph project description (≤80 words)

What the system does, who runs it, primary delivery surfaces (Discord + dashboard). Pull the language from `ARCHITECTURE.md`'s system overview but tighten it.

### 2. Status badges

A row of badges showing:
- Last architecture-doc refresh date (today's date when this prompt runs)
- Monthly cost (pull the headline number from `COST_ANALYSIS.md` §1)
- Number of Cloud Run Jobs (pull from `ARCHITECTURE.md` §2 inventory or `gcp_inventory.json` filtered to `assetType=run.googleapis.com/Job`)
- Number of scheduled crons (count `gcloud scheduler jobs list` or grep `_schedule(` in `gcp/deploy.sh`)
- GitHub Actions status badge for the architecture-refresh workflow

Use [shields.io](https://shields.io/) static badges for the date / cost / counts (dynamic data not available without an external service). Use the GitHub Actions native workflow badge for the workflow status.

### 3. Documentation map

A markdown table listing every `*.md` doc in the repo root (and `docs/DATA_PIPELINE.md` + `docs/GCP_IMPLEMENTATION_GUIDE.md` if they still exist). Columns: Document | Purpose | Read this when. Each row is one line. Cover the 6 audit docs (ARCHITECTURE, DATA_DEPENDENCIES, COST_ANALYSIS, RUNBOOK, DASHBOARD_SPEC, SETUP) plus CLAUDE.md plus any other live docs.

### 4. Architecture at a glance

Three sentences summarizing the system's shape (what runs, where, how). Then **embed the Mermaid diagram from `ARCHITECTURE.md` directly** — copy the entire `mermaid` code block. Below the diagram, include a one-line "Full per-table flow is in DATA_DEPENDENCIES.md" link.

### 5. Cost at a glance

Pull these three things from `COST_ANALYSIS.md`:
- Headline monthly run-rate (from §1 or the doc opener)
- The biggest line item (from §2)
- The top recommendation (from §5)

3-5 bullets. Link to `COST_ANALYSIS.md` for full detail.

### 6. Quick start

Three subsections, each 3-5 bullets:

#### "I want to run this locally"
Reference `make dev` / `make install` from `gcp/deploy.sh` + the existing CLAUDE.md notes on `.env` and `.gcp-key.json`. Include the port map (Vite 5173, FastAPI 8000) and the available frontend routes list.

#### "I want to add a new fetcher"
Step-by-step: new module in `gcp/fetchers/`, deploy function in `gcp/deploy.sh`, add to `deploy_fetchers()` + `deploy_schedulers()`, schema in `gcp/schema.sql` if new table, then update ARCHITECTURE.md / DATA_DEPENDENCIES.md (or wait for monthly refresh).

#### "Something is broken"
One-liner pointing at `RUNBOOK.md`. Mention the failure-notifier flow (Cloud Logging sink → Pub/Sub → Cloud Run Service → GitHub issue) — link to ARCHITECTURE.md §3 "Failure notification."

### 7. Maintenance

Explain that documentation auto-refreshes monthly via the GitHub Actions workflow. Link to the workflow file. State that bot PRs should be reviewed and merged within a week. Note which docs are auto-regenerated (ARCHITECTURE, DATA_DEPENDENCIES, COST_ANALYSIS, README) vs operator-edited (RUNBOOK, DASHBOARD_SPEC).

### 8. License and contact

Preserve whatever exists in the previous README. If there's no explicit license (the typical state), note that and treat as "all rights reserved." Include a contact pointer (GitHub repo owner / git log).

## Rules

- **No content duplicated from the other docs.** Link, don't restate.
- **Under 400 lines.** It's a map, not a manual.
- **Direct, terse.** No marketing language. No "Welcome to..." / "This amazing system..." / etc.
- **Every link must be a real file path that exists.** Don't link to docs that haven't been created yet.
- **Date the doc.** Last line: `Generated YYYY-MM-DD by .github/workflows/refresh-architecture-docs.yml`.

When done, write the file and exit. Do not narrate.
