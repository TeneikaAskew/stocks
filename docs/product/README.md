# Living Product Plan

**Repository:** `TeneikaAskew/stocks`
**Evidence snapshot / Last reviewed:** 2026-08-30
**Purpose:** the maintained index from product intent through implementation, evidence, risk, and delivery.

## Navigation

| Document | Question answered |
|---|---|
| [00 Product overview](00-PRODUCT-OVERVIEW.md) | What is the product and where is it going? |
| [01 Requirements](01-PRODUCT-REQUIREMENTS.md) | What shall it do and how is done defined? |
| [02 Feature catalog](02-FEATURE-CATALOG.md) | What capabilities exist and what is their trust state? |
| [03 UI screens](03-UI-SCREENS.md) | What does each user surface do? |
| [04 Backend/API](04-BACKEND-API.md) | Which endpoints and services support it? |
| [05 Infrastructure](05-INFRASTRUCTURE.md) | What runs and deploys it? |
| [06 Data architecture](06-DATA-ARCHITECTURE.md) | What data exists and how does it flow? |
| [07 Model registry](07-MODEL-REGISTRY.md) | Which rules/models exist and are they trustworthy? |
| [08 AI agents](08-AI-AGENT-ARCHITECTURE.md) | What is the actual and target LLM graph? |
| [09 Security/auth](09-SECURITY-AUTH.md) | How are identity, access, tenancy, and perimeter separated? |
| [10 Operations/reliability](10-OPERATIONS-RELIABILITY.md) | How is production trust measured/recovered? |
| [11 Code traceability](11-CODE-TRACEABILITY.md) | Where is each capability implemented? |
| [12 PR/issue traceability](12-PR-ISSUE-TRACEABILITY.md) | Which changes, issues, and audits affect trust? |
| [13 Roadmap](13-ROADMAP.md) | What should be sequenced next? |
| [14 Work breakdown](14-WORK-BREAKDOWN.md) | How does work decompose into evidence? |
| [15 Open decisions](15-OPEN-DECISIONS.md) | Which product choices remain unresolved? |

## Governance contract

**Evidence tags:** `VERIFIED — CODE`, `VERIFIED — TEST`, `VERIFIED — DEPLOYMENT`, `VERIFIED — GITHUB`, `CLAIMED — DOCUMENTATION`, `PROPOSED — TARGET`, and `UNKNOWN / NEEDS HISTORY TRACE`. Current code and deployed configuration outrank narrative documentation; tests establish covered behavior, not production health; audit evidence qualifies trust.

**Capability status:** Production; Production but needs remediation; Shadow; Experimental; Research; Incomplete; Planned; Deprecated; Dormant; Broken; Retire candidate. **Model status:** Production; Shadow; Experimental; Research; Failed; Retest Required; Invalidated; Archived; Retired.

Every feature uses a stable ID and must retain: Owner, Status, Priority, Target Phase/Release, Last Reviewed, Production/Reliability/Evidence status, Blocking Issues, Relevant PR, Next Action. Unknown values remain `TBD`; proposals never masquerade as current behavior. A PR changing behavior shall update the catalog, traceability row, evidence/status, review date, and acceptance criteria.

## Master traceability matrix

This is the primary navigation view; detailed evidence and monitoring fields are in the linked feature record.

| ID | Product area | Capability/feature | UI | Backend | Data | Model | Infrastructure | Code | Tests | Issue | PR | Status | Priority |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| [FEAT-AUTH-001](02-FEATURE-CATALOG.md#feat-auth-001) | Authentication | Protected application access | Sign-in state | /api/me | identity/config | Firebase or IAP | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | [#911](https://github.com/TeneikaAskew/stocks/issues/911) | [history](12-PR-ISSUE-TRACEABILITY.md) | Production but needs remediation | P0 |
| [FEAT-MARKET-001](02-FEATURE-CATALOG.md#feat-market-001) | Market dashboard | Current market brief | Dashboard | /api/dashboard | market_data_daily; premarket_analysis | brief bias; movement statement | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | [#861](https://github.com/TeneikaAskew/stocks/issues/861) | [history](12-PR-ISSUE-TRACEABILITY.md) | Production but needs remediation | P0 |
| [FEAT-LIVE-001](02-FEATURE-CATALOG.md#feat-live-001) | Intraday monitoring | Live quotes, indicators, and state | Live | /api/live | market_data_intraday | indicators; STRAT | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | [#873](https://github.com/TeneikaAskew/stocks/issues/873) | [history](12-PR-ISSUE-TRACEABILITY.md) | Production but needs remediation | P0 |
| [FEAT-CHART-001](02-FEATURE-CATALOG.md#feat-chart-001) | Charting | Instrument/timeframe chart analysis | Charts | /api/live/history | market_data_daily; market_data_intraday | STRAT; levels | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | TBD | [history](12-PR-ISSUE-TRACEABILITY.md) | Incomplete | P1 |
| [FEAT-OPTION-001](02-FEATURE-CATALOG.md#feat-option-001) | Options/Gamma | Options flow, Greeks, GEX | Options Flow | /api/options; /api/grid | options/greeks/gex domains | gamma; flow direction | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | [#884](https://github.com/TeneikaAskew/stocks/issues/884) | [history](12-PR-ISSUE-TRACEABILITY.md) | Production but needs remediation | P0 |
| [FEAT-SIGNAL-001](02-FEATURE-CATALOG.md#feat-signal-001) | Signals | Signal discovery and monitoring | Signals; Live | /api/signals | signal_alerts; historical_signals | momentum; mean reversion; agreement | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | [#874](https://github.com/TeneikaAskew/stocks/issues/874) | [history](12-PR-ISSUE-TRACEABILITY.md) | Production but needs remediation | P0 |
| [FEAT-PLAYBOOK-001](02-FEATURE-CATALOG.md#feat-playbook-001) | Trade planning | Premarket playbook cards | Playbook | /api/playbook | playbook_cards; premarket_analysis | brief bias; levels | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | [#861](https://github.com/TeneikaAskew/stocks/issues/861) | [history](12-PR-ISSUE-TRACEABILITY.md) | Broken | P0 |
| [FEAT-REPORT-001](02-FEATURE-CATALOG.md#feat-report-001) | Reporting | Historical and generated reports | Reports | /api/analytics; /api/backtest | backtest_reports; signal_metrics | evaluation metrics | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | [#906](https://github.com/TeneikaAskew/stocks/issues/906) | [history](12-PR-ISSUE-TRACEABILITY.md) | Experimental | P1 |
| [FEAT-JOURNAL-001](02-FEATURE-CATALOG.md#feat-journal-001) | Journal | Record/import/review trades | Journal | /api/journal | journal_entries; trades | broker import | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | TBD | [history](12-PR-ISSUE-TRACEABILITY.md) | Incomplete | P1 |
| [FEAT-INSIGHT-001](02-FEATURE-CATALOG.md#feat-insight-001) | AI insights | Multi-agent market insight | AI Insights | /api/insights | insight_runs; insight_reports; model_routing | LLM agent graph | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | [#916](https://github.com/TeneikaAskew/stocks/issues/916) | [history](12-PR-ISSUE-TRACEABILITY.md) | Experimental | P0 |
| [FEAT-CATALYST-001](02-FEATURE-CATALOG.md#feat-catalyst-001) | Catalysts | Earnings and event context | Catalysts | /api/catalysts; /api/earnings | earnings; events; SEC; news | earnings reactions | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | TBD | [history](12-PR-ISSUE-TRACEABILITY.md) | Incomplete | P1 |
| [FEAT-ADMIN-001](02-FEATURE-CATALOG.md#feat-admin-001) | Administration | Model/config/STRAT operations | Admin | /api/admin; /api/config | routing; calibration; config | model routing | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | [#911](https://github.com/TeneikaAskew/stocks/issues/911) | [history](12-PR-ISSUE-TRACEABILITY.md) | Production but needs remediation | P0 |
| [FEAT-SETTINGS-001](02-FEATURE-CATALOG.md#feat-settings-001) | Configuration | User display/preferences | Settings | /api/config | watchlists; config | None | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | TBD | [history](12-PR-ISSUE-TRACEABILITY.md) | Incomplete | P2 |
| [FEAT-HELP-001](02-FEATURE-CATALOG.md#feat-help-001) | Help | Glossary and product explanation | Help | /api/glossary | static glossary | None | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | TBD | [history](12-PR-ISSUE-TRACEABILITY.md) | Production | P2 |
| [FEAT-WAITLIST-001](02-FEATURE-CATALOG.md#feat-waitlist-001) | Public site | Landing and waitlist | Landing | /api/waitlist | waitlist_signups | None | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | TBD | [history](12-PR-ISSUE-TRACEABILITY.md) | Production but needs remediation | P2 |
| [FEAT-STRAT-001](02-FEATURE-CATALOG.md#feat-strat-001) | Structural analysis | STRAT/FTFC and levels | Live; Charts; Playbook | shared domain logic | market bars; strat_levels | STRAT; FTFC; level state | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | [#875](https://github.com/TeneikaAskew/stocks/issues/875) | [history](12-PR-ISSUE-TRACEABILITY.md) | Production but needs remediation | P0 |
| [FEAT-REPLAY-001](02-FEATURE-CATALOG.md#feat-replay-001) | Replay | Point-in-time replay | Reports/Admin | /api/backtest | historical_signals; backtest tables | strategies; execution simulation | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | [#813](https://github.com/TeneikaAskew/stocks/issues/813) | [history](12-PR-ISSUE-TRACEABILITY.md) | Invalidated | P0 |
| [FEAT-MODEL-001](02-FEATURE-CATALOG.md#feat-model-001) | Predictive models | Magnitude/direction/meta models | Insights/Admin | /api/magnitude | predictions/artifacts | magnitude; direction; breakout | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | [#910](https://github.com/TeneikaAskew/stocks/issues/910) | [history](12-PR-ISSUE-TRACEABILITY.md) | Retest Required | P0 |
| [FEAT-ALERT-001](02-FEATURE-CATALOG.md#feat-alert-001) | Notifications | Discord signal/insight delivery | External Discord | Discord interactions/jobs | signal_alerts; insight_reports | signal rules | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | TBD | [history](12-PR-ISSUE-TRACEABILITY.md) | Production but needs remediation | P1 |
| [FEAT-DATA-001](02-FEATURE-CATALOG.md#feat-data-001) | Data platform | Market/options/event ingestion | All data surfaces | Cloud Run jobs | all analytical domains | validation/freshness rules | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | [#860](https://github.com/TeneikaAskew/stocks/issues/860) | [history](12-PR-ISSUE-TRACEABILITY.md) | Production but needs remediation | P0 |
| [FEAT-OPS-001](02-FEATURE-CATALOG.md#feat-ops-001) | Operations | Freshness, job and failure monitoring | Admin | /api/health | job_runs; domain timestamps | freshness policy | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | [#862](https://github.com/TeneikaAskew/stocks/issues/862) | [history](12-PR-ISSUE-TRACEABILITY.md) | Incomplete | P0 |
| [FEAT-DEPLOY-001](02-FEATURE-CATALOG.md#feat-deploy-001) | Delivery | Build/deploy/schedule services | None | Cloud Build/Run | Cloud SQL/GCS/Secret Manager | None | Cloud Run/API/SQL as applicable | [map](11-CODE-TRACEABILITY.md) | [evidence](11-CODE-TRACEABILITY.md) | [#829](https://github.com/TeneikaAskew/stocks/issues/829) | [history](12-PR-ISSUE-TRACEABILITY.md) | Production but needs remediation | P0 |
