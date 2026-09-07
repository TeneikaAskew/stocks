# Stocks Trading Platform

A private stocks and options trading intelligence platform on GCP: Cloud Run Jobs pull market, options, earnings, macro, filings and news data into Cloud SQL, compute Strat, gamma and signal analytics with one shared `lib/` engine, and deliver briefs and alerts to Discord. A FastAPI service (`solyra-api-prod` behind IAP, `solyra-api-staging` public with Firebase login) serves the [solyra](https://github.com/TeneikaAskew/solyra) React UI. This repository is the backend; the frontend moved to solyra in #957.

![Last audit](https://img.shields.io/badge/docs_verified-2026--09--07-blue)
![Cloud Run Jobs](https://img.shields.io/badge/cloud_run_jobs-76_live_%2F_67_declared-blue)
![Cloud Scheduler](https://img.shields.io/badge/schedulers-66_live-blue)
![Cloud SQL tables](https://img.shields.io/badge/schema_tables-66_declared_%2F_94_live-blue)
![Architecture refresh](https://github.com/TeneikaAskew/stocks/actions/workflows/refresh-architecture-docs.yml/badge.svg)

Counts are read live by `python -m scripts.maintenance.doc_inventory --live`; the badges are updated by the monthly refresh.

## Documentation map

| Read this | When you want |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | the whole system: every job, scheduler, service, table, route, deploy path, data flow, failure path, live-vs-repo reconciliation |
| [DATA_DEPENDENCIES.md](DATA_DEPENDENCIES.md) | which module writes and reads each table, multi-writer risks, orphan tables, blast radius per job |
| [COST_ANALYSIS.md](COST_ANALYSIS.md) | the monthly GCP bill by SKU and component |
| [RUNBOOK.md](RUNBOOK.md) | something is on fire: failure scenarios, recovery steps, rebuild sequence |
| [ERD.md](ERD.md) | the schema as entity-relationship diagrams, by cluster |
| [docs/PIPELINE.md](docs/PIPELINE.md) | the two-lane model: live trading vs research, and the one indicator engine both share |
| [docs/DATA_PIPELINE.md](docs/DATA_PIPELINE.md) | per-table freshness budgets and canonical writers |
| [docs/API.md](docs/API.md) | the FastAPI route reference: every router and route, rendered from the code on each refresh |
| [docs/GCP_IMPLEMENTATION_GUIDE.md](docs/GCP_IMPLEMENTATION_GUIDE.md) | the Python engine internals: indicators, signals, Strat, backtest, data layer |
| [docs/product/README.md](docs/product/README.md) | the living product plan: capabilities, requirements, security, roadmap |
| [docs/audits/](docs/audits/) | dated audits, including the 2026-09-07 architecture-doc audit that produced this layout |
| [gcp/cloudbuild/README.md](gcp/cloudbuild/README.md) | the Cloud Build triggers that deploy the API and apply the schema |
| [SETUP.md](SETUP.md) | one-time setup of the monthly documentation refresh (WIF, roles, secrets) |
| [CLAUDE.md](CLAUDE.md) | project rules for AI agents and the operational command cookbook (sandbox network limits, database access, backups) |
| [solyra](https://github.com/TeneikaAskew/solyra) | the React frontend, its screens and its own docs |

## Quick start

- **Run the API locally**: `make install`, then `make dev` starts FastAPI on `:8000` (no frontend here; run solyra's `npm run dev`, whose proxy uses `:8000` when it is up). Environment and credentials: [CLAUDE.md](CLAUDE.md).
- **Add a fetcher**: module under `gcp/fetchers/`, a `deploy_<name>()` function and a scheduler entry in `gcp/deploy.sh`, schema in `gcp/schema.sql` if it writes a new table. The next monthly refresh picks it up in ARCHITECTURE.md and DATA_DEPENDENCIES.md; run `python -m scripts.maintenance.doc_inventory --insert` to update them now.
- **Query Cloud SQL from a sandbox**: `./scripts/db_query_cr.sh -q "SELECT …"` (only port 443 is open there; see [CLAUDE.md → Database access](CLAUDE.md#database-access)).
- **Something is broken**: [RUNBOOK.md](RUNBOOK.md); failed jobs already open a GitHub issue through the failure notifier ([ARCHITECTURE.md §10.10](ARCHITECTURE.md#1010-failure-flow)).

## Maintenance

`ARCHITECTURE.md`, `DATA_DEPENDENCIES.md`, `COST_ANALYSIS.md` and this file are refreshed monthly by [`.github/workflows/refresh-architecture-docs.yml`](.github/workflows/refresh-architecture-docs.yml): it snapshots live GCP, renders the inventory tables inside the `<!-- inventory:* -->` marker blocks deterministically, has Gemini update the surrounding prose in place, gates the result (job, scheduler, table and route coverage, no lost sections, no dead links, docs-vs-live drift), and opens a PR. Prose outside the markers is hand-maintained; content inside them is overwritten. `RUNBOOK.md`, `ERD.md` and `docs/` are hand-edited.

## Removed since last refresh

- 2026-09-07: README became a pointer-only map. "Architecture at a glance" (the embedded diagram) now lives in ARCHITECTURE.md §2; "Cost at a glance" in COST_ANALYSIS.md; "I want to run this locally", "I want to add a new fetcher" and "Something is broken" are the Quick start bullets above; "Tech stack" is ARCHITECTURE.md §16 and the solyra README.

## License and contact

No explicit license has been added to this repo. Treat as **all rights reserved** until that changes. Contact: see git log / GitHub repo owner.

Generated 2026-09-07 by hand from the audit in [`docs/audits/ARCHITECTURE_DOCS_AUDIT_2026-09-07.md`](docs/audits/ARCHITECTURE_DOCS_AUDIT_2026-09-07.md). The monthly refresh updates this line.
