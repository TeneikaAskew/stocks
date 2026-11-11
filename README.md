# Stocks Trading Platform

**Last reviewed:** unknown · **Last scanned:** 2026-11-03 · **Owner:** TBD

A private stocks and options trading intelligence platform on GCP: Cloud Run Jobs pull market, options, earnings, macro, filings and news data into Cloud SQL, compute Strat, gamma and signal analytics with one shared `lib/` engine, and deliver briefs and alerts to Discord. A FastAPI service (`solyra-api-staging`, public with Firebase login; `solyra-api-prod` behind IAP was retired on 2026-10-10, [stocks#1366](https://github.com/TeneikaAskew/stocks/pull/1366)) serves the [solyra](https://github.com/TeneikaAskew/solyra) React UI. This repository is the backend; the frontend moved to solyra in #957.

![Last audit](https://img.shields.io/badge/docs_verified-2026--09--07-blue)
![Cloud Run Jobs](https://img.shields.io/badge/cloud_run_jobs-76_live_%2F_67_declared-blue)
![Cloud Scheduler](https://img.shields.io/badge/schedulers-65_live-blue)
![Cloud SQL tables](https://img.shields.io/badge/schema_tables-66_declared_%2F_94_live-blue)

Counts are read live by `python -m scripts.maintenance.doc_inventory --live`; the badges show the 2026-09-07 snapshot and are not refreshed on a schedule.

## Documentation map

| Read this | When you want |
|---|---|
| [05-a-ARCHITECTURE.md](docs/product/infrastructure/05-a-ARCHITECTURE.md) | the whole system: every job, scheduler, service, table, route, deploy path, data flow, failure path, live-vs-repo reconciliation |
| [05-c-DATA_DEPENDENCIES.md](docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md) | which module writes and reads each table, multi-writer risks, orphan tables, blast radius per job |
| [05-d-COST_ANALYSIS.md](docs/product/infrastructure/05-d-COST_ANALYSIS.md) | a dated record of the 2026-09-02 billing data by SKU and component |
| [RUNBOOK.md](RUNBOOK.md) | something is on fire: failure scenarios, recovery steps, rebuild sequence |
| [05-b-ERD.md](docs/product/infrastructure/05-b-ERD.md) | the schema as entity-relationship diagrams, by cluster |
| [05-f-PIPELINE.md](docs/product/infrastructure/05-f-PIPELINE.md) | the two-lane model: live trading vs research, and the one indicator engine both share |
| [05-g-DATA_PIPELINE.md](docs/product/infrastructure/05-g-DATA_PIPELINE.md) | per-table freshness budgets and canonical writers |
| [05-e-API.md](docs/product/infrastructure/05-e-API.md) | the FastAPI route reference: every router and route, rendered from the router files on each PR that changes them |
| [05-i-GCP_IMPLEMENTATION_GUIDE.md](docs/product/infrastructure/05-i-GCP_IMPLEMENTATION_GUIDE.md) | the Python engine internals: indicators, signals, Strat, backtest, data layer |
| [docs/product/README.md](docs/product/README.md) | the living product plan: capabilities, requirements, security, roadmap |
| [docs/audits/](docs/audits/) | dated audits, including the 2026-09-07 architecture-doc audit that produced this layout |
| [gcp/cloudbuild/README.md](gcp/cloudbuild/README.md) | the Cloud Build triggers that deploy the API and apply the schema |
| [SETUP.md](SETUP.md) | one-time Workload Identity Federation setup for `deploy-staging.yml` and `verify-docs-against-live.yml` |
| [CLAUDE.md](CLAUDE.md) | project rules for AI agents and the operational command cookbook (sandbox network limits, database access, backups) |
| [solyra](https://github.com/TeneikaAskew/solyra) | the React frontend, its screens and its own docs |

## Quick start

- **Run the API locally**: `make install`, then `make dev` starts FastAPI on `:8000` (no frontend here; run solyra's `npm run dev`, whose proxy uses `:8000` when it is up). Environment and credentials: [CLAUDE.md](CLAUDE.md).
- **Add a fetcher**: module under `gcp/fetchers/`, a `deploy_<name>()` function and a scheduler entry in `gcp/deploy.sh`, schema in `gcp/schema.sql` if it writes a new table. To list it in `05-a-ARCHITECTURE.md` and `05-c-DATA_DEPENDENCIES.md` under `docs/product/infrastructure/`, run Maintenance step 1 below.
- **Query Cloud SQL from a sandbox**: `./scripts/db_query_cr.sh -q "SELECT …"` (only port 443 is open there; see [CLAUDE.md → Database access](CLAUDE.md#database-access)).
- **Something is broken**: [RUNBOOK.md](RUNBOOK.md); failed jobs already open a GitHub issue through the failure notifier ([05-a-ARCHITECTURE.md §10.10](docs/product/infrastructure/05-a-ARCHITECTURE.md#1010-failure-flow)).

## Maintenance

The monthly refresh of the generated documents was retired on 2026-11-10, and nothing regenerates these files on a schedule. Every step below is optional and run by hand; step 1 is also enforced on each PR by the spec gate and the docs test. The `05-*` files live under `docs/product/infrastructure/`.

1. Re-render the inventory and route blocks of `05-a-ARCHITECTURE.md`, `05-c-DATA_DEPENDENCIES.md` and `05-e-API.md` from the snapshot the spec gate pins as its `RENDER_SNAPSHOT`:

   `python -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --insert docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`

2. Run the tests that compare the committed diagrams and generated blocks, each against the snapshot its test names:

   `python -m pytest tests/scripts/test_check_generated_docs.py tests/scripts/test_refresh_architecture_drawio.py -k committed`

3. Re-render the resolved-values table in `docs/INVESTMENT_MODELS_SUMMARY.md`, from a machine with Cloud SQL access (not a 443-only sandbox), or add `--check` to compare only:

   `python -m scripts.refresh_calibration_table`

The badges and the live-derived blocks show the 2026-09-07 snapshot, the diagram counts the snapshot their test reads, and no tool on main refreshes them from live state. The prose around the marker blocks, `RUNBOOK.md`, `05-b-ERD.md`, `SETUP.md` and the rest of `docs/` are hand-edited.

## Moved and removed documents

- 2026-09-07: the twelve infrastructure references moved from the repo root and `docs/` into `docs/product/infrastructure/`, renamed `05-a-…` through `05-l-…` so they slot under [docs/product/05-INFRASTRUCTURE.md](docs/product/05-INFRASTRUCTURE.md#reference-documents). No redirect stubs were left behind; every inbound reference in the repo was repointed, and `docs/GCP_ARCHITECTURE.md` (already a stub) was deleted.
- 2026-09-07: README became a pointer-only map. "Architecture at a glance" (the embedded diagram) now lives in ARCHITECTURE.md §2; "Cost at a glance" in COST_ANALYSIS.md; "I want to run this locally", "I want to add a new fetcher" and "Something is broken" are the Quick start bullets above; "Tech stack" is ARCHITECTURE.md §16 and the solyra README.

## License and contact

No explicit license has been added to this repo. Treat as **all rights reserved** until that changes. Contact: see git log / GitHub repo owner.

Generated 2026-09-07 from the 2026-09-07 live snapshot. The audits behind these documents are in [`docs/audits/`](docs/audits).
