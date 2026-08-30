# Code Traceability

Paths explain responsibility; directory presence is not production evidence. Use feature-specific tests and history before status changes.

| Feature | UI/API/domain/job/data implementation | Test evidence locus | Why it matters |
|---|---|---|---|
| FEAT-AUTH-001 | `platform/src/components/auth; platform/src/lib; platform/api/auth.py` | `platform/tests/auth-gate.spec.ts; platform tests` | primary implementation and regression boundary |
| FEAT-MARKET-001 | `platform/src/routes/DashboardPage.tsx; platform/api/routers/dashboard.py; lib/movement_statement.py` | `platform/api tests; tests` | primary implementation and regression boundary |
| FEAT-LIVE-001 | `platform/src/routes/LiveMarketPage.tsx; platform/api/routers/live.py; lib/indicators.py` | `platform tests; tests` | primary implementation and regression boundary |
| FEAT-CHART-001 | `platform/src/routes/ChartsPage.tsx; platform/api/routers/live.py; platform/api/routers/grid.py` | `platform tests` | primary implementation and regression boundary |
| FEAT-OPTION-001 | `platform/src/routes/OptionsFlowPage.tsx; platform/api/routers/options.py; lib/gamma.py; lib/options_greeks.py` | `options/gamma tests` | primary implementation and regression boundary |
| FEAT-SIGNAL-001 | `platform/src/routes/SignalsPage.tsx; platform/api/routers/signals.py; lib/signals.py; lib/strategies` | `signal/strategy tests` | primary implementation and regression boundary |
| FEAT-PLAYBOOK-001 | `platform/src/routes/PlaybookPage.tsx; platform/api/routers/playbook.py; gcp` | `platform/API/job tests` | primary implementation and regression boundary |
| FEAT-REPORT-001 | `platform/src/routes/ReportsPage.tsx; platform/api/routers/analytics.py; platform/api/routers/backtest.py; lib/backtest.py` | `backtest/walk-forward tests` | primary implementation and regression boundary |
| FEAT-JOURNAL-001 | `platform/src/routes/JournalPage.tsx; platform/api/routers/journal.py; lib/broker_import.py` | `journal/auth tests` | primary implementation and regression boundary |
| FEAT-INSIGHT-001 | `platform/src/routes/InsightsPage.tsx; platform/api/routers/insights.py; lib/agents` | `agent/insight tests` | primary implementation and regression boundary |
| FEAT-CATALYST-001 | `platform/src/routes/CatalystsPage.tsx; platform/api/routers/catalysts.py; platform/api/routers/earnings.py; lib/earnings_reactions.py` | `earnings/catalyst tests` | primary implementation and regression boundary |
| FEAT-ADMIN-001 | `platform/src/routes/AdminPage.tsx; platform/api/routers/admin.py; platform/api/routers/config.py` | `platform/tests/admin-auth.spec.ts; API tests` | primary implementation and regression boundary |
| FEAT-STRAT-001 | `lib/strat.py; lib/strat_levels.py; gcp/research/strat_engine` | `STRAT/level tests` | primary implementation and regression boundary |
| FEAT-REPLAY-001 | `lib/backtest.py; lib/exec_backtest; lib/options_exec_backtest; lib/walk_forward.py` | `replay/backtest tests` | primary implementation and regression boundary |
| FEAT-DATA-001 | `gcp/schema.sql; gcp ingestion jobs; lib/data_loader.py` | `schema/ingestion/data tests` | primary implementation and regression boundary |
| FEAT-DEPLOY-001 | `gcp/deploy.sh; platform/deploy.sh; .github/workflows; gcp/cloudbuild` | `CI/static deployment checks` | primary implementation and regression boundary |

## Repository layers
- `platform/src/routes` composes screens; `components`, hooks/stores and API utilities implement interactions/state.
- `platform/api/routers` is the HTTP contract; `auth.py` establishes principals; route SQL/domain calls identify data/model dependencies.
- `lib` owns reusable calculations, strategies, replay engines and agents; callers must not duplicate semantics.
- `gcp` owns scheduled ingestion/analysis/notification and operational scripts; `gcp/research` is not production by location alone.
- `gcp/schema.sql` plus migrations/queries define persistence intent; runtime SQL must be reconciled.
- `.github/workflows`, Cloud Build files and deploy scripts define delivery intent, not necessarily live state.
- `tests` and `platform` test files establish covered behavior; absence or mocks-only evidence is recorded as a gap.
