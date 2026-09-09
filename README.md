# Stocks Trading Platform

A private stocks and options trading intelligence platform on GCP: Cloud Run Jobs pull market, options, earnings, macro, filings and news data into Cloud SQL, compute Strat, gamma and signal analytics with one shared `lib/` engine, and deliver briefs and alerts to Discord. A FastAPI service (`solyra-api-prod` behind IAP, `solyra-api-staging` public with Firebase login) serves the [solyra](https://github.com/TeneikaAskew/solyra) React UI. This repository is the backend; the frontend moved to solyra in #957.

![Last audit](https://img.shields.io/badge/docs_verified-2026--09--07-blue)
![Cloud Run Jobs](https://img.shields.io/badge/cloud_run_jobs-76_live_%2F_67_declared-blue)
![Cloud Scheduler](https://img.shields.io/badge/schedulers-65_live-blue)
![Cloud SQL tables](https://img.shields.io/badge/schema_tables-66_declared_%2F_94_live-blue)
![Architecture refresh](https://github.com/TeneikaAskew/stocks/actions/workflows/refresh-architecture-docs.yml/badge.svg)

Counts are read live by `python -m scripts.maintenance.doc_inventory --live`; the badges are updated by the monthly refresh.

## Documentation map

| Read this | When you want |
|---|---|
| [05-a-ARCHITECTURE.md](docs/product/infrastructure/05-a-ARCHITECTURE.md) | the whole system: every job, scheduler, service, table, route, deploy path, data flow, failure path, live-vs-repo reconciliation |
| [05-c-DATA_DEPENDENCIES.md](docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md) | which module writes and reads each table, multi-writer risks, orphan tables, blast radius per job |
| [05-d-COST_ANALYSIS.md](docs/product/infrastructure/05-d-COST_ANALYSIS.md) | the monthly GCP bill by SKU and component |
| [RUNBOOK.md](RUNBOOK.md) | something is on fire: failure scenarios, recovery steps, rebuild sequence |
| [05-b-ERD.md](docs/product/infrastructure/05-b-ERD.md) | the schema as entity-relationship diagrams, by cluster |
| [05-f-PIPELINE.md](docs/product/infrastructure/05-f-PIPELINE.md) | the two-lane model: live trading vs research, and the one indicator engine both share |
| [05-g-DATA_PIPELINE.md](docs/product/infrastructure/05-g-DATA_PIPELINE.md) | per-table freshness budgets and canonical writers |
| [05-e-API.md](docs/product/infrastructure/05-e-API.md) | the FastAPI route reference: every router and route, rendered from the code on each refresh |
| [05-i-GCP_IMPLEMENTATION_GUIDE.md](docs/product/infrastructure/05-i-GCP_IMPLEMENTATION_GUIDE.md) | the Python engine internals: indicators, signals, Strat, backtest, data layer |
| [docs/product/README.md](docs/product/README.md) | the living product plan: capabilities, requirements, security, roadmap |
| [docs/audits/](docs/audits/) | dated audits, including the 2026-09-07 architecture-doc audit that produced this layout |
| [gcp/cloudbuild/README.md](gcp/cloudbuild/README.md) | the Cloud Build triggers that deploy the API and apply the schema |
| [SETUP.md](SETUP.md) | one-time setup of the monthly documentation refresh (WIF, roles, secrets) |
| [CLAUDE.md](CLAUDE.md) | project rules for AI agents and the operational command cookbook (sandbox network limits, database access, backups) |
| [solyra](https://github.com/TeneikaAskew/solyra) | the React frontend, its screens and its own docs |

## Quick start

- **Run the API locally**: `make install`, then `make dev` starts FastAPI on `:8000` (no frontend here; run solyra's `npm run dev`, whose proxy uses `:8000` when it is up). Environment and credentials: [CLAUDE.md](CLAUDE.md).
- **Add a fetcher**: module under `gcp/fetchers/`, a `deploy_<name>()` function and a scheduler entry in `gcp/deploy.sh`, schema in `gcp/schema.sql` if it writes a new table. The next monthly refresh picks it up in `05-a-ARCHITECTURE.md` and `05-c-DATA_DEPENDENCIES.md` under `docs/product/infrastructure/`; run `python -m scripts.maintenance.doc_inventory --insert` to update them now.
- **Query Cloud SQL from a sandbox**: `./scripts/db_query_cr.sh -q "SELECT …"` (only port 443 is open there; see [CLAUDE.md → Database access](CLAUDE.md#database-access)).
- **Something is broken**: [RUNBOOK.md](RUNBOOK.md); failed jobs already open a GitHub issue through the failure notifier ([05-a-ARCHITECTURE.md §10.10](docs/product/infrastructure/05-a-ARCHITECTURE.md#1010-failure-flow)).

## Maintenance

Nine files are written by [`.github/workflows/refresh-architecture-docs.yml`](.github/workflows/refresh-architecture-docs.yml) on the 1st of each month and must not be hand-edited outside the rules below. The `05-*` files live under `docs/product/infrastructure/`:

| Generated file | What the workflow does to it |
|---|---|
| `05-a-ARCHITECTURE.md`, `05-c-DATA_DEPENDENCIES.md` | inventory tables re-rendered inside the `<!-- inventory:* -->` markers from a live GCP snapshot; the prose around them updated in place by Gemini |
| `05-e-API.md` | entirely rendered from the router files — every line inside its two marker blocks is overwritten |
| `05-d-COST_ANALYSIS.md` | rewritten in place by Gemini from the billing digests and the other docs |
| `README.md` | badges and the closing date rendered from the live inventory; the prose and the documentation map are hand-written and no model touches them |
| `Architecture.drawio`, `Architecture-icons.drawio` | counts, scheduler labels, the add-on job grid and the icon reconciliation notes regenerated from the same snapshot |
| `docs/INVESTMENT_MODELS_SUMMARY.md` | resolved-values table re-rendered from `ticker_calibration` |

Prose outside a marker block survives the refresh and is yours to edit; anything inside one is overwritten on the 1st. Every run publishes an added/removed accounting (lines, bytes, churn, headings and blocks gained or lost per file) to its job summary and PR body, and a run that replaced a document rather than updating it fails the churn gate rather than opening a PR. `RUNBOOK.md`, `05-b-ERD.md`, `SETUP.md` and the rest of `docs/` are hand-edited.

## Removed since last refresh

- 2026-09-07: the twelve infrastructure references moved from the repo root and `docs/` into `docs/product/infrastructure/`, renamed `05-a-…` through `05-l-…` so they slot under [docs/product/05-INFRASTRUCTURE.md](docs/product/05-INFRASTRUCTURE.md#reference-documents). No redirect stubs were left behind; every inbound reference in the repo was repointed, and `docs/GCP_ARCHITECTURE.md` (already a stub) was deleted.
- 2026-09-07: README became a pointer-only map. "Architecture at a glance" (the embedded diagram) now lives in ARCHITECTURE.md §2; "Cost at a glance" in COST_ANALYSIS.md; "I want to run this locally", "I want to add a new fetcher" and "Something is broken" are the Quick start bullets above; "Tech stack" is ARCHITECTURE.md §16 and the solyra README.

## License and contact

No explicit license has been added to this repo. Treat as **all rights reserved** until that changes. Contact: see git log / GitHub repo owner.

Generated 2026-09-07 by the monthly documentation refresh. The audits behind these documents are in [`docs/audits/`](docs/audits). The monthly refresh updates this line.
