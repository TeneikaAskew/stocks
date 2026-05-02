# Stocks

A private stocks-trading research and signal-delivery platform on GCP. **Discord** is the primary surface (scheduled briefs + slash-command interactions); a secondary internal **React + FastAPI dashboard** lives at the `trading-platform` Cloud Run Service. Single-user / small-team — no public auth, no per-user partitioning. The fetcher fleet runs as Cloud Run Jobs orchestrated by Cloud Scheduler; math is concentrated in `lib/` so Cloud Run, the FastAPI router, and CLI scripts all consume the same code.

![Last refresh](https://img.shields.io/badge/last_doc_refresh-2026--05--02-blue)
![Monthly cost](https://img.shields.io/badge/monthly_cost-~%2413-green)
![Cloud Run Jobs](https://img.shields.io/badge/cloud_run_jobs-27-blue)
![Cloud Scheduler crons](https://img.shields.io/badge/scheduled_crons-40%2B-blue)
![Architecture refresh](https://github.com/TeneikaAskew/stocks/actions/workflows/refresh-architecture-docs.yml/badge.svg)

> Static badges (last refresh / monthly cost / job count) get bumped by the [monthly auto-refresh workflow](.github/workflows/refresh-architecture-docs.yml). Last hand-bump 2026-05-02.

---

## Documentation map

This repo documents itself. Read these in order if you're new — or jump to whichever one matches what you're trying to do.

| Document | Purpose | Read this when |
|---|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Component inventory + GCP resources + data-flow diagrams | You want the 30,000-ft view of how the pieces fit |
| [DATA_DEPENDENCIES.md](DATA_DEPENDENCIES.md) | Per-table write/read graph + multi-writer + orphan analysis + Mermaid graph | You're touching a fetcher / writer and want to know what reads downstream |
| [COST_ANALYSIS.md](COST_ANALYSIS.md) | 90-day GCP billing rollup mapped to components + recommendations | You want to know what costs money and where the leverage is |
| [RUNBOOK.md](RUNBOOK.md) | Failure-scenario playbook (8 scenarios) + RTO/RPO + rebuild-from-scratch | Something is on fire and you need a checklist |
| [DASHBOARD_SPEC.md](DASHBOARD_SPEC.md) | 5-panel signal-quality dashboard spec (not built yet — closes a real gap) | You want to build the missing visibility into signal quality |
| [SETUP.md](SETUP.md) | One-time setup for the auto-doc-refresh workflow (WIF, IAM, secrets) | You're enabling monthly auto-refresh for the first time |
| [CLAUDE.md](CLAUDE.md) | Project rules for AI agents working in this repo | You're collaborating with Claude / Codex on this code |
| [docs/DATA_PIPELINE.md](docs/DATA_PIPELINE.md) | Per-table freshness budgets + reliability TODOs | You're triaging stale data |
| [docs/GCP_IMPLEMENTATION_GUIDE.md](docs/GCP_IMPLEMENTATION_GUIDE.md) | The longer GCP playbook (predates ARCHITECTURE.md) | You want narrative GCP context |

---

## Architecture at a glance

The system runs as a fleet of ~27 Cloud Run Jobs orchestrated by Cloud Scheduler. Most jobs follow the shape *pull external API → upsert Cloud SQL → optionally write parquet to GCS → exit*. A second class of jobs (`premarket-brief`, `signal-monitor`, `insight-pipeline`, `weekend-review`) reads from Cloud SQL, computes derived analytics from `lib/`, and posts results to Discord.

```mermaid
flowchart LR
    subgraph EXT [External APIs]
        AV[AlphaVantage]
        FRED[FRED]
        SEC[EDGAR]
        DISCORD_API[Discord API]
    end

    subgraph FETCH [Cloud Run Jobs - fetchers]
        FMD[fetch-market-data]
        FFR[fetch-fred-rates]
        FEC[earnings-calendar]
        FNS[fetch-news-sentiment]
        FSF[fetch-sec-filings]
    end

    subgraph DB [(Cloud SQL — trading-db)]
        T1[(market_data_*)]
        T2[(earnings_*)]
        T3[(news_sentiment / sec_filings)]
        T4[(signals / insights / trades)]
    end

    subgraph CONSUME [Cloud Run Jobs - consumers]
        PB[premarket-brief]
        SM[signal-monitor]
        IP[insight-pipeline]
    end

    subgraph SURFACE [User surfaces]
        DC[Discord webhook]
        DASH[trading-platform dashboard]
        DI[discord-interactions slash commands]
    end

    AV --> FMD
    FRED --> FFR
    SEC --> FSF
    AV --> FNS

    FMD ==> T1
    FFR ==> T1
    FEC ==> T2
    FNS ==> T3
    FSF ==> T3

    T1 --> PB
    T1 --> SM
    T2 --> PB
    T3 --> IP
    T1 --> IP

    PB ==> T4
    SM ==> T4
    IP ==> T4

    PB --> DC
    SM --> DC
    IP --> DC
    T4 --> DASH
    DISCORD_API <--> DI
    DI --> CONSUME

    classDef ext fill:#F59E0B,stroke:#92400E,color:#fff
    classDef job fill:#3B82F6,stroke:#1E40AF,color:#fff
    classDef tbl fill:#10B981,stroke:#065F46,color:#fff
    class AV,FRED,SEC,DISCORD_API ext
    class FMD,FFR,FEC,FNS,FSF,PB,SM,IP job
```

Full per-table flow with all 27 jobs is in [DATA_DEPENDENCIES.md §7](DATA_DEPENDENCIES.md#7-mermaid-graph). Per-job purpose + scheduler binding is in [ARCHITECTURE.md §2](ARCHITECTURE.md#2-component-inventory).

---

## Cost at a glance

- **~\$13/month run-rate** at March pricing (~\$3/month at April pricing, possibly with a credit applied)
- **Cloud SQL is 92% of spend** — single `trading-db` Postgres small instance + storage
- **Top reduction recommendation:** verify whether April's 72%-vs-March drop is a real credit (Billing Reports → split by Credits) before optimizing further

Full breakdown: [COST_ANALYSIS.md](COST_ANALYSIS.md).

---

## Quick start

### I want to run this locally

```bash
make dev    # FastAPI on :8000 + Vite dev server on :5173
```

Prereqs: Python deps (`make install`), Node deps (`cd platform && npm install`), `.env` at repo root with `GOOGLE_APPLICATION_CREDENTIALS` pointing to `.gcp-key.json`. Full env setup including secrets is in [CLAUDE.md](CLAUDE.md#technology-stack).

Available routes once running:
- `/` Dashboard, `/live` Live Market, `/charts`, `/options` Options Flow, `/playbook`, `/backtest`, `/reports`, `/signals`, `/journal`, `/insights`, `/admin`

### I want to add a new fetcher

1. Add a Python module under [`gcp/fetchers/`](gcp/fetchers/) following the shape of [`fetch_market_data.py`](gcp/fetchers/fetch_market_data.py) — read external API, upsert via `gcp.database.upsert_dataframe`, exit non-zero on missing env vars
2. Add a `deploy_<name>()` function to [`gcp/deploy.sh`](gcp/deploy.sh) (modeled on the existing fetcher deploys around lines 536-911)
3. Add the function to `deploy_fetchers()` and add a Cloud Scheduler entry in `deploy_schedulers()`
4. If the fetcher writes a new table: add the schema to [`gcp/schema.sql`](gcp/schema.sql) and run `./gcp/deploy.sh apply-schema`
5. Add an inventory row to [ARCHITECTURE.md](ARCHITECTURE.md#code-modules) and a write/read entry to [DATA_DEPENDENCIES.md](DATA_DEPENDENCIES.md) (or wait for the next monthly refresh to do it for you)

### Something is broken

→ [RUNBOOK.md](RUNBOOK.md). 8 failure scenarios with detection signal, immediate response, recovery steps, verification.

The failure-notifier auto-creates labeled GitHub issues for any Cloud Run Job ERROR — see [ARCHITECTURE.md §3 "Failure notification"](ARCHITECTURE.md#failure-notification) for how that flow works.

---

## Maintenance

Documentation auto-refreshes monthly via [`.github/workflows/refresh-architecture-docs.yml`](.github/workflows/refresh-architecture-docs.yml):

- Runs on the 1st of every month at 06:00 UTC, plus manual dispatch
- Authenticates to GCP via Workload Identity Federation (no service-account JSON keys checked in)
- Snapshots inventory + IAM + 90-day billing rollup, then invokes Claude Code in headless mode using prompts versioned under [`.github/prompts/`](.github/prompts/)
- Opens a PR titled `Monthly architecture doc refresh: YYYY-MM` if any of `ARCHITECTURE.md` / `DATA_DEPENDENCIES.md` / `COST_ANALYSIS.md` / `README.md` changed meaningfully
- Bot PRs should be reviewed and merged within a week — stale auto-PRs accumulate noise

One-time setup is documented in [SETUP.md](SETUP.md). Cost: ~\$3-5/month in Anthropic API spend.

The `RUNBOOK.md` and `DASHBOARD_SPEC.md` are **not** auto-regenerated — they're operator-edited (incident playbook + forward-looking spec, not state snapshots). Edit them by hand and PR like any other code change.

---

## License and contact

> No explicit license has been added to this repo. Treat as **all rights reserved** until that changes. Contact: see git log / GitHub repo owner.

---

*Repo policies — branching, commit conventions, AI-collaboration rules — live in [CLAUDE.md](CLAUDE.md).*
