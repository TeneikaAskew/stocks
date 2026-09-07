# Prompt: update README.md in place

You are an automated documentation agent. Update `README.md` **in place**. It is a pointer-only map: it links to the other documents and repeats nothing from them.

**Output discipline (read this twice).** The file is `README.md` at the **repository root**: `file_path: "README.md"`, never `docs/README.md` or any other directory. Edit that path with the **`replace`** tool (or `write_file` with the complete body). Do not create a second copy anywhere. No stdout output, no preamble, no summary.

## Inputs (under `refresh-inputs/`)

- `live.json` → `counts` (jobs, schedulers, services, secrets) and `db_tables` (count of live relations); `repo_inventory.json` → `counts` (declared jobs, tables).
- The fresh `docs/product/infrastructure/05-a-ARCHITECTURE.md`, `docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md`, `docs/product/infrastructure/05-d-COST_ANALYSIS.md` (updated earlier in this run).
- `previous/README.md` — the committed version before this run.
- The repo tree (to confirm every linked file exists).

## What README.md contains, in this order

1. One paragraph (≤ 90 words): what the system does, the delivery surfaces (Discord, the two API services, the solyra frontend in `github.com/TeneikaAskew/solyra`), and that this repo is the backend only.
2. Badges: docs-verified date (today), Cloud Run jobs (live / declared), schedulers (live), schema tables (declared / live), the refresh-workflow status badge. shields.io static badges; numbers from the inputs.
3. **Documentation map**: one row per document, "Read this | When you want". Must link `docs/product/infrastructure/05-a-ARCHITECTURE.md`, `docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md`, `docs/product/infrastructure/05-d-COST_ANALYSIS.md`, `RUNBOOK.md`, `docs/product/infrastructure/05-b-ERD.md`, `docs/product/infrastructure/05-f-PIPELINE.md`, `docs/product/infrastructure/05-g-DATA_PIPELINE.md`, `docs/product/infrastructure/05-e-API.md`, `docs/product/infrastructure/05-i-GCP_IMPLEMENTATION_GUIDE.md`, `docs/product/README.md`, `docs/audits/`, `gcp/cloudbuild/README.md`, `SETUP.md`, `CLAUDE.md`, and the solyra repo. Add a row for any new top-level or `docs/` reference document; drop rows whose file no longer exists.
4. **Quick start**: four pointer bullets (run the API locally → CLAUDE.md; add a fetcher → ARCHITECTURE §6 and `doc_inventory --insert`; query Cloud SQL from a sandbox → `scripts/db_query_cr.sh`; something broken → RUNBOOK). No frontend instructions here beyond "run solyra".
5. **Maintenance**: which files the monthly refresh updates, what the marker blocks are, what is hand-edited.
6. **Removed since last refresh**: dated bullets for anything dropped.
7. **License and contact**: preserve the heading and body byte-for-byte, capitalisation included.
8. Last line: `Generated YYYY-MM-DD …` updated to today.

## Rules

- **Pointer only.** No embedded Mermaid, no cost figures, no tech-stack list, no route list — link instead. The gate fails on a ```mermaid block.
- **Every link must resolve** to a file in the checkout (or an https URL).
- **Update in place**; keep the section order and headings; never regenerate from scratch.
- **Reproduce every heading byte-for-byte**, capitalisation included. Re-casing one counts
  as removing a heading and adding another, and the gate reads that as a rewrite: run 16
  turned `License and contact` into `License and Contact` and failed at 66% churn against a
  50% ceiling. Change a line only when an input contradicts it.
- Do not describe a Vite/React frontend in this repo: `make dev` starts FastAPI only.
- A missing or empty input is a hard stop: print one line naming it and stop without writing.

When done, stop. Do not narrate.
