# Code Traceability

**Last reviewed:** 2026-08-30

All **26** capability IDs from [02](02-FEATURE-CATALOG.md) appear here — the previous
revision listed 16 of 22, so Settings, Help, Waitlist, Model, Alert and Ops resolved to no code
locus despite two of them being P0. Directory presence is not production evidence; the
Status column comes from [02](02-FEATURE-CATALOG.md).

| ID | Implementation | Tests | Status |
|---|---|---|---|
| [FEAT-AUTH-001](02-FEATURE-CATALOG.md#feat-auth-001) | `platform/api/auth.py`, `platform/api/main.py:51`, `platform/src/components/auth` | `platform/tests/auth-gate.spec.ts`, `admin-auth.spec.ts` | Production but needs remediation |
| [FEAT-WAITLIST-001](02-FEATURE-CATALOG.md#feat-waitlist-001) | `platform/src/routes/LandingPage.tsx`, `platform/api/routers/waitlist.py` | `landing.spec.ts`, `waitlist.test.ts` | Production |
| [FEAT-MARKET-001](02-FEATURE-CATALOG.md#feat-market-001) | `platform/src/routes/DashboardPage.tsx`, `platform/api/routers/dashboard.py`, `lib/movement_statement.py` | `dashboard.spec.ts`, `movement-read.spec.ts`, `MovementRead.test.tsx` | Production but needs remediation |
| [FEAT-LIVE-001](02-FEATURE-CATALOG.md#feat-live-001) | `platform/src/routes/LiveMarketPage.tsx`, `platform/api/routers/live.py`, `lib/indicators.py` | `live-market.spec.ts` | Production but needs remediation |
| [FEAT-CHART-001](02-FEATURE-CATALOG.md#feat-chart-001) | `platform/src/routes/ChartsPage.tsx`, `platform/api/routers/live.py`, `grid.py` | `charts-cards.spec.ts`, `phase1-charts.spec.ts` | Production but needs remediation |
| [FEAT-OPTION-001](02-FEATURE-CATALOG.md#feat-option-001) | `platform/src/routes/OptionsFlowPage.tsx`, `platform/api/routers/options.py`, `grid.py`, `lib/gamma.py`, `lib/options_greeks.py` | `options-flow.spec.ts`, `gamma-levels.spec.ts`, `swingGridUtils.test.ts` | Retest Required |
| [FEAT-SIGNAL-001](02-FEATURE-CATALOG.md#feat-signal-001) | `lib/signals.py`, `lib/strategies/`, `gcp/signal_monitor.py`, `platform/api/routers/signals.py` | `signals.spec.ts`, `tests/test_signal*.py` | Production but needs remediation |
| [FEAT-PLAYBOOK-001](02-FEATURE-CATALOG.md#feat-playbook-001) | `platform/src/routes/PlaybookPage.tsx`, `platform/api/routers/playbook.py`, `gcp/premarket_brief.py`, `scripts/analysis/phase6_playbook.py` | `playbook.spec.ts`, `tests/test_phase6_playbook.py` | **Broken** |
| [FEAT-STRAT-001](02-FEATURE-CATALOG.md#feat-strat-001) | `lib/strat.py`, `lib/strat_levels.py`, `lib/exec_backtest/ftfc.py` | `tests/test_strat*.py` | Production but needs remediation |
| [FEAT-IND-001](02-FEATURE-CATALOG.md#feat-ind-001) | `lib/indicators.py`, `lib/signals.py` | `tests/test_indicators*.py` | Production but needs remediation |
| [FEAT-INSIGHT-001](02-FEATURE-CATALOG.md#feat-insight-001) | `lib/agents/`, `platform/api/routers/insights.py`, `gcp/insight_pipeline_job.py` | `insights.spec.ts`, `tests/test_agents_*.py` | Experimental |
| [FEAT-CATALYST-001](02-FEATURE-CATALOG.md#feat-catalyst-001) | `platform/api/routers/catalysts.py`, `earnings.py`, `lib/earnings_reactions.py` | `catalysts.spec.ts` | Production but needs remediation |
| [FEAT-REPORT-001](02-FEATURE-CATALOG.md#feat-report-001) | `platform/src/routes/ReportsPage.tsx`, `platform/api/routers/backtest.py`, `analytics.py` | `reports.spec.ts`, `BacktesterSection.format.test.ts` | Production but needs remediation |
| [FEAT-REPLAY-001](02-FEATURE-CATALOG.md#feat-replay-001) | `lib/backtest.py`, `lib/walk_forward.py`, `lib/exec_backtest/`, `scripts/replay_signal_monitor.py`, `gcp/signal_monitor_eod_resolver.py` | `replay-trainer.spec.ts`, `tests/test_backtest*.py` | **Invalidated** |
| [FEAT-MODEL-001](02-FEATURE-CATALOG.md#feat-model-001) | `gcp/research/`, `lib/walk_forward.py`, `platform/api/routers/magnitude.py` | `tests/test_walk_forward*.py`, `tests/test_magnitude*.py` | **Invalidated / Failed** (mixed) |
| [FEAT-JOURNAL-001](02-FEATURE-CATALOG.md#feat-journal-001) | `platform/src/routes/JournalPage.tsx`, `platform/api/routers/journal.py`, `lib/broker_import.py` | `journal.spec.ts`, `journal-import.spec.ts`, `journal-onestop.spec.ts` | Production but needs remediation |
| [FEAT-ALERT-001](02-FEATURE-CATALOG.md#feat-alert-001) | `gcp/discord_interactions/main.py`, `gcp/notifier*.py` | `tests/test_notifier*.py` | Production but needs remediation |
| [FEAT-ADMIN-001](02-FEATURE-CATALOG.md#feat-admin-001) | `platform/src/routes/AdminPage.tsx`, `platform/api/routers/admin.py` | `admin.spec.ts`, `admin-auth.spec.ts` | Production but needs remediation |
| [FEAT-HELP-001](02-FEATURE-CATALOG.md#feat-help-001) | `platform/src/routes/HelpPage.tsx`, `platform/api/routers/glossary.py` | `help.spec.ts` | Production |
| [FEAT-SETTINGS-001](02-FEATURE-CATALOG.md#feat-settings-001) | `platform/src/routes/SettingsPage.tsx`, `platform/src/stores/settingsStore.ts`, `themeStore.ts` | **none** | Incomplete |
| [FEAT-DATA-001](02-FEATURE-CATALOG.md#feat-data-001) | `gcp/fetchers/`, `gcp/schema.sql`, `lib/data_loader.py`, `gcp/database.py` | `tests/test_data_loader*.py`, integration suite | Production but needs remediation |
| [FEAT-DEPLOY-001](02-FEATURE-CATALOG.md#feat-deploy-001) | `gcp/deploy.sh`, `platform/deploy.sh`, `gcp/cloudbuild/` | static checks only | Production but needs remediation |
| [FEAT-OPS-001](02-FEATURE-CATALOG.md#feat-ops-001) | `gcp/freshness_watchdog.py`, `gcp/notifier*.py`, `platform/api/routers/health.py` | `data-pipeline-status.spec.ts` | Incomplete |
| [FEAT-CICD-001](02-FEATURE-CATALOG.md#feat-cicd-001) | `.github/workflows/`, `gcp/cloudbuild/` | 230 python tests, 29 e2e, 27 vitest | Production but needs remediation |
| [FEAT-UI-001](02-FEATURE-CATALOG.md#feat-ui-001) | `platform/src/App.tsx`, `platform/src/components/shared/` | `navigation.spec.ts` | Production but needs remediation |
| [FEAT-DEBT-001](02-FEATURE-CATALOG.md#feat-debt-001) | `scripts/`, archived apps | — | Retire candidate |

## Repository layers

| Layer | Owns | Rule |
|---|---|---|
| `platform/src/routes` | screen composition (15 routes) | one file per route, lazy-loaded; see [03](03-UI-SCREENS.md) |
| `platform/src/components`, `stores`, `hooks` | interaction and client state | `settingsStore`/`themeStore` persist to `localStorage`, **not** the API |
| `platform/api/routers` | the HTTP contract (87 endpoints) | auth is middleware, not per-router; see [09](09-SECURITY-AUTH.md) |
| `lib/` | **all** reusable financial math | the React app never duplicates it (`docs/HARDCODED_VALUES_REMEDIATION.md`); 33 of 87 endpoints hold inline SQL, the rest go through `lib/` |
| `gcp/` | scheduled ingestion, analysis, notification (67 jobs) | `gcp/research/` is **not** production by location alone |
| `scripts/analysis/` | analysis scripts — **but also feeds `playbook_cards`** | a production user-facing table is written from here; weakest coverage ([#849](https://github.com/TeneikaAskew/stocks/issues/849)) |
| `gcp/schema.sql` | 64 relations | runtime SQL must be reconciled ([#860](https://github.com/TeneikaAskew/stocks/issues/860)) |
| `.github/workflows`, `gcp/deploy.sh` | delivery intent | not necessarily live state ([#859](https://github.com/TeneikaAskew/stocks/issues/859)) |
| `tests/`, `platform/tests/` | 230 python, 29 e2e, 27 vitest | frontend suites do not run in CI ([#868](https://github.com/TeneikaAskew/stocks/issues/868)) |
