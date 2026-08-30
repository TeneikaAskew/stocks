# UI Screen Inventory

**VERIFIED — CODE:** routes are lazy-loaded in `platform/src/App.tsx`; `/` is public, `/welcome` redirects, and the application children are wrapped by `AuthGate` and `AppShell`. React Query defaults to five-minute staleness and one retry. `RouteErrorBoundary` preserves the shell after route render failure. Authentication is an in-route sign-in state, not a `/login` route.

## Shared screen contract
All protected screens inherit identity gating, shell/navigation, suspense loader, and route error boundary. Each target screen must render identifiable as-of/freshness, permission, dependency error, empty, loading, and stale states; preserve useful state without concealing changed data; and meet responsive/keyboard/accessibility requirements. Current behavior must be verified per component/test rather than inferred from this contract.

| Screen | Route | User | Route component | Backend families | Access | Status |
|---|---|---|---|---|---|---|
| Landing | `/` | Public visitor | `platform/src/routes/LandingPage.tsx` | waitlist | Public; waitlist write | Production |
| Welcome redirect | `/welcome` | Public visitor | `platform/src/App.tsx` | none | Public redirect | Production but needs remediation |
| Dashboard | `/dashboard` | Trader | `platform/src/routes/DashboardPage.tsx` | dashboard, config | Protected | Production but needs remediation |
| Live Market | `/live` | Trader | `platform/src/routes/LiveMarketPage.tsx` | live, signals | Protected | Production but needs remediation |
| Charts | `/charts` | Trader | `platform/src/routes/ChartsPage.tsx` | live/history, grid | Protected | Production but needs remediation |
| Options Flow | `/options` | Trader/analyst | `platform/src/routes/OptionsFlowPage.tsx` | options, grid | Protected | Production but needs remediation |
| Playbook | `/playbook` | Trader | `platform/src/routes/PlaybookPage.tsx` | playbook | Protected | Broken |
| Reports | `/reports` | Trader/researcher | `platform/src/routes/ReportsPage.tsx` | analytics, backtest | Protected | Production but needs remediation |
| Signals | `/signals` | Trader | `platform/src/routes/SignalsPage.tsx` | signals | Protected | Production but needs remediation |
| Journal | `/journal` | Trader | `platform/src/routes/JournalPage.tsx` | journal | Protected; owner scope required | Production but needs remediation |
| AI Insights | `/insights` | Trader/analyst | `platform/src/routes/InsightsPage.tsx` | insights | Protected | Production but needs remediation |
| Catalysts | `/catalysts` | Trader/analyst | `platform/src/routes/CatalystsPage.tsx` | catalysts, earnings | Protected | Production but needs remediation |
| Admin | `/admin` | Operator/admin | `platform/src/routes/AdminPage.tsx` | admin, config | Protected + server admin check | Production but needs remediation |
| Help & Glossary | `/help` | Trader | `platform/src/routes/HelpPage.tsx` | glossary | Protected | Production |
| Settings | `/settings` | Trader | `platform/src/routes/SettingsPage.tsx` | config | Protected | Production but needs remediation |

## SCREEN-LANDING — Landing
- **Purpose/features:** Enable the public visitor to use the landing surface; meaningful controls, tabs, filters, selections, imports or mutations must retain their own test evidence.
- **Current route/status:** `/`; public; status is evidence-qualified in the table.
- **UI/state:** `platform/src/routes/LandingPage.tsx` and its imported components/hooks; React Query plus component/store/local state where imported. Do not infer persistence from presentation state.
- **Backend/data/models:** router families `waitlist`; exact endpoints are in [04](04-BACKEND-API.md), data in [06](06-DATA-ARCHITECTURE.md), models in [07](07-MODEL-REGISTRY.md).
- **Loading/error/empty/mobile:** suspense and route-crash states are verified globally; dependency-specific empty/error and responsive behavior require component/test evidence and otherwise remain **Incomplete**.
- **Tests:** search `platform/src/**/*.test.*`, `platform/tests/*.spec.ts`; absent row-level coverage is a gap.
- **Issues/PRs:** see [12](12-PR-ISSUE-TRACEABILITY.md); origin lineage may be `UNKNOWN / NEEDS HISTORY TRACE`.
- **Target:** meet REQ-UX-001, relevant feature requirements, explicit stale/unavailable presentation, authenticated ownership where applicable, telemetry, responsive design, and acceptance tests.


## SCREEN-WELCOMEREDIRECT — Welcome redirect
- **Purpose/features:** Enable the public visitor to use the welcome redirect surface; meaningful controls, tabs, filters, selections, imports or mutations must retain their own test evidence.
- **Current route/status:** `/welcome`; public; status is evidence-qualified in the table.
- **UI/state:** `platform/src/App.tsx` and its imported components/hooks; React Query plus component/store/local state where imported. Do not infer persistence from presentation state.
- **Backend/data/models:** router families `none`; exact endpoints are in [04](04-BACKEND-API.md), data in [06](06-DATA-ARCHITECTURE.md), models in [07](07-MODEL-REGISTRY.md).
- **Loading/error/empty/mobile:** suspense and route-crash states are verified globally; dependency-specific empty/error and responsive behavior require component/test evidence and otherwise remain **Incomplete**.
- **Tests:** search `platform/src/**/*.test.*`, `platform/tests/*.spec.ts`; absent row-level coverage is a gap.
- **Issues/PRs:** see [12](12-PR-ISSUE-TRACEABILITY.md); origin lineage may be `UNKNOWN / NEEDS HISTORY TRACE`.
- **Target:** meet REQ-UX-001, relevant feature requirements, explicit stale/unavailable presentation, authenticated ownership where applicable, telemetry, responsive design, and acceptance tests.


## SCREEN-DASHBOARD — Dashboard
- **Purpose/features:** Enable the trader to use the dashboard surface; meaningful controls, tabs, filters, selections, imports or mutations must retain their own test evidence.
- **Current route/status:** `/dashboard`; Protected; status is evidence-qualified in the table.
- **UI/state:** `platform/src/routes/DashboardPage.tsx` and its imported components/hooks; React Query plus component/store/local state where imported. Do not infer persistence from presentation state.
- **Backend/data/models:** router families `dashboard, config`; exact endpoints are in [04](04-BACKEND-API.md), data in [06](06-DATA-ARCHITECTURE.md), models in [07](07-MODEL-REGISTRY.md).
- **Loading/error/empty/mobile:** suspense and route-crash states are verified globally; dependency-specific empty/error and responsive behavior require component/test evidence and otherwise remain **Incomplete**.
- **Tests:** search `platform/src/**/*.test.*`, `platform/tests/*.spec.ts`; absent row-level coverage is a gap.
- **Issues/PRs:** see [12](12-PR-ISSUE-TRACEABILITY.md); origin lineage may be `UNKNOWN / NEEDS HISTORY TRACE`.
- **Target:** meet REQ-UX-001, relevant feature requirements, explicit stale/unavailable presentation, authenticated ownership where applicable, telemetry, responsive design, and acceptance tests.


## SCREEN-LIVEMARKET — Live Market
- **Purpose/features:** Enable the trader to use the live market surface; meaningful controls, tabs, filters, selections, imports or mutations must retain their own test evidence.
- **Current route/status:** `/live`; Protected; status is evidence-qualified in the table.
- **UI/state:** `platform/src/routes/LiveMarketPage.tsx` and its imported components/hooks; React Query plus component/store/local state where imported. Do not infer persistence from presentation state.
- **Backend/data/models:** router families `live, signals`; exact endpoints are in [04](04-BACKEND-API.md), data in [06](06-DATA-ARCHITECTURE.md), models in [07](07-MODEL-REGISTRY.md).
- **Loading/error/empty/mobile:** suspense and route-crash states are verified globally; dependency-specific empty/error and responsive behavior require component/test evidence and otherwise remain **Incomplete**.
- **Tests:** search `platform/src/**/*.test.*`, `platform/tests/*.spec.ts`; absent row-level coverage is a gap.
- **Issues/PRs:** see [12](12-PR-ISSUE-TRACEABILITY.md); origin lineage may be `UNKNOWN / NEEDS HISTORY TRACE`.
- **Target:** meet REQ-UX-001, relevant feature requirements, explicit stale/unavailable presentation, authenticated ownership where applicable, telemetry, responsive design, and acceptance tests.


## SCREEN-CHARTS — Charts
- **Purpose/features:** Enable the trader to use the charts surface; meaningful controls, tabs, filters, selections, imports or mutations must retain their own test evidence.
- **Current route/status:** `/charts`; Protected; status is evidence-qualified in the table.
- **UI/state:** `platform/src/routes/ChartsPage.tsx` and its imported components/hooks; React Query plus component/store/local state where imported. Do not infer persistence from presentation state.
- **Backend/data/models:** router families `live/history, grid`; exact endpoints are in [04](04-BACKEND-API.md), data in [06](06-DATA-ARCHITECTURE.md), models in [07](07-MODEL-REGISTRY.md).
- **Loading/error/empty/mobile:** suspense and route-crash states are verified globally; dependency-specific empty/error and responsive behavior require component/test evidence and otherwise remain **Incomplete**.
- **Tests:** search `platform/src/**/*.test.*`, `platform/tests/*.spec.ts`; absent row-level coverage is a gap.
- **Issues/PRs:** see [12](12-PR-ISSUE-TRACEABILITY.md); origin lineage may be `UNKNOWN / NEEDS HISTORY TRACE`.
- **Target:** meet REQ-UX-001, relevant feature requirements, explicit stale/unavailable presentation, authenticated ownership where applicable, telemetry, responsive design, and acceptance tests.


## SCREEN-OPTIONSFLOW — Options Flow
- **Purpose/features:** Enable the trader/analyst to use the options flow surface; meaningful controls, tabs, filters, selections, imports or mutations must retain their own test evidence.
- **Current route/status:** `/options`; Protected; status is evidence-qualified in the table.
- **UI/state:** `platform/src/routes/OptionsFlowPage.tsx` and its imported components/hooks; React Query plus component/store/local state where imported. Do not infer persistence from presentation state.
- **Backend/data/models:** router families `options, grid`; exact endpoints are in [04](04-BACKEND-API.md), data in [06](06-DATA-ARCHITECTURE.md), models in [07](07-MODEL-REGISTRY.md).
- **Loading/error/empty/mobile:** suspense and route-crash states are verified globally; dependency-specific empty/error and responsive behavior require component/test evidence and otherwise remain **Incomplete**.
- **Tests:** search `platform/src/**/*.test.*`, `platform/tests/*.spec.ts`; absent row-level coverage is a gap.
- **Issues/PRs:** see [12](12-PR-ISSUE-TRACEABILITY.md); origin lineage may be `UNKNOWN / NEEDS HISTORY TRACE`.
- **Target:** meet REQ-UX-001, relevant feature requirements, explicit stale/unavailable presentation, authenticated ownership where applicable, telemetry, responsive design, and acceptance tests.


## SCREEN-PLAYBOOK — Playbook
- **Purpose/features:** Enable the trader to use the playbook surface; meaningful controls, tabs, filters, selections, imports or mutations must retain their own test evidence.
- **Current route/status:** `/playbook`; Protected; status is evidence-qualified in the table.
- **UI/state:** `platform/src/routes/PlaybookPage.tsx` and its imported components/hooks; React Query plus component/store/local state where imported. Do not infer persistence from presentation state.
- **Backend/data/models:** router families `playbook`; exact endpoints are in [04](04-BACKEND-API.md), data in [06](06-DATA-ARCHITECTURE.md), models in [07](07-MODEL-REGISTRY.md).
- **Loading/error/empty/mobile:** suspense and route-crash states are verified globally; dependency-specific empty/error and responsive behavior require component/test evidence and otherwise remain **Incomplete**.
- **Tests:** search `platform/src/**/*.test.*`, `platform/tests/*.spec.ts`; absent row-level coverage is a gap.
- **Issues/PRs:** see [12](12-PR-ISSUE-TRACEABILITY.md); origin lineage may be `UNKNOWN / NEEDS HISTORY TRACE`.
- **Target:** meet REQ-UX-001, relevant feature requirements, explicit stale/unavailable presentation, authenticated ownership where applicable, telemetry, responsive design, and acceptance tests.


## SCREEN-REPORTS — Reports
- **Purpose/features:** Enable the trader/researcher to use the reports surface; meaningful controls, tabs, filters, selections, imports or mutations must retain their own test evidence.
- **Current route/status:** `/reports`; Protected; status is evidence-qualified in the table.
- **UI/state:** `platform/src/routes/ReportsPage.tsx` and its imported components/hooks; React Query plus component/store/local state where imported. Do not infer persistence from presentation state.
- **Backend/data/models:** router families `analytics, backtest`; exact endpoints are in [04](04-BACKEND-API.md), data in [06](06-DATA-ARCHITECTURE.md), models in [07](07-MODEL-REGISTRY.md).
- **Loading/error/empty/mobile:** suspense and route-crash states are verified globally; dependency-specific empty/error and responsive behavior require component/test evidence and otherwise remain **Incomplete**.
- **Tests:** search `platform/src/**/*.test.*`, `platform/tests/*.spec.ts`; absent row-level coverage is a gap.
- **Issues/PRs:** see [12](12-PR-ISSUE-TRACEABILITY.md); origin lineage may be `UNKNOWN / NEEDS HISTORY TRACE`.
- **Target:** meet REQ-UX-001, relevant feature requirements, explicit stale/unavailable presentation, authenticated ownership where applicable, telemetry, responsive design, and acceptance tests.


## SCREEN-SIGNALS — Signals
- **Purpose/features:** Enable the trader to use the signals surface; meaningful controls, tabs, filters, selections, imports or mutations must retain their own test evidence.
- **Current route/status:** `/signals`; Protected; status is evidence-qualified in the table.
- **UI/state:** `platform/src/routes/SignalsPage.tsx` and its imported components/hooks; React Query plus component/store/local state where imported. Do not infer persistence from presentation state.
- **Backend/data/models:** router families `signals`; exact endpoints are in [04](04-BACKEND-API.md), data in [06](06-DATA-ARCHITECTURE.md), models in [07](07-MODEL-REGISTRY.md).
- **Loading/error/empty/mobile:** suspense and route-crash states are verified globally; dependency-specific empty/error and responsive behavior require component/test evidence and otherwise remain **Incomplete**.
- **Tests:** search `platform/src/**/*.test.*`, `platform/tests/*.spec.ts`; absent row-level coverage is a gap.
- **Issues/PRs:** see [12](12-PR-ISSUE-TRACEABILITY.md); origin lineage may be `UNKNOWN / NEEDS HISTORY TRACE`.
- **Target:** meet REQ-UX-001, relevant feature requirements, explicit stale/unavailable presentation, authenticated ownership where applicable, telemetry, responsive design, and acceptance tests.


## SCREEN-JOURNAL — Journal
- **Purpose/features:** Enable the trader to use the journal surface; meaningful controls, tabs, filters, selections, imports or mutations must retain their own test evidence.
- **Current route/status:** `/journal`; Protected; owner scope required; status is evidence-qualified in the table.
- **UI/state:** `platform/src/routes/JournalPage.tsx` and its imported components/hooks; React Query plus component/store/local state where imported. Do not infer persistence from presentation state.
- **Backend/data/models:** router families `journal`; exact endpoints are in [04](04-BACKEND-API.md), data in [06](06-DATA-ARCHITECTURE.md), models in [07](07-MODEL-REGISTRY.md).
- **Loading/error/empty/mobile:** suspense and route-crash states are verified globally; dependency-specific empty/error and responsive behavior require component/test evidence and otherwise remain **Incomplete**.
- **Tests:** search `platform/src/**/*.test.*`, `platform/tests/*.spec.ts`; absent row-level coverage is a gap.
- **Issues/PRs:** see [12](12-PR-ISSUE-TRACEABILITY.md); origin lineage may be `UNKNOWN / NEEDS HISTORY TRACE`.
- **Target:** meet REQ-UX-001, relevant feature requirements, explicit stale/unavailable presentation, authenticated ownership where applicable, telemetry, responsive design, and acceptance tests.


## SCREEN-AIINSIGHTS — AI Insights
- **Purpose/features:** Enable the trader/analyst to use the ai insights surface; meaningful controls, tabs, filters, selections, imports or mutations must retain their own test evidence.
- **Current route/status:** `/insights`; Protected; status is evidence-qualified in the table.
- **UI/state:** `platform/src/routes/InsightsPage.tsx` and its imported components/hooks; React Query plus component/store/local state where imported. Do not infer persistence from presentation state.
- **Backend/data/models:** router families `insights`; exact endpoints are in [04](04-BACKEND-API.md), data in [06](06-DATA-ARCHITECTURE.md), models in [07](07-MODEL-REGISTRY.md).
- **Loading/error/empty/mobile:** suspense and route-crash states are verified globally; dependency-specific empty/error and responsive behavior require component/test evidence and otherwise remain **Incomplete**.
- **Tests:** search `platform/src/**/*.test.*`, `platform/tests/*.spec.ts`; absent row-level coverage is a gap.
- **Issues/PRs:** see [12](12-PR-ISSUE-TRACEABILITY.md); origin lineage may be `UNKNOWN / NEEDS HISTORY TRACE`.
- **Target:** meet REQ-UX-001, relevant feature requirements, explicit stale/unavailable presentation, authenticated ownership where applicable, telemetry, responsive design, and acceptance tests.


## SCREEN-CATALYSTS — Catalysts
- **Purpose/features:** Enable the trader/analyst to use the catalysts surface; meaningful controls, tabs, filters, selections, imports or mutations must retain their own test evidence.
- **Current route/status:** `/catalysts`; Protected; status is evidence-qualified in the table.
- **UI/state:** `platform/src/routes/CatalystsPage.tsx` and its imported components/hooks; React Query plus component/store/local state where imported. Do not infer persistence from presentation state.
- **Backend/data/models:** router families `catalysts, earnings`; exact endpoints are in [04](04-BACKEND-API.md), data in [06](06-DATA-ARCHITECTURE.md), models in [07](07-MODEL-REGISTRY.md).
- **Loading/error/empty/mobile:** suspense and route-crash states are verified globally; dependency-specific empty/error and responsive behavior require component/test evidence and otherwise remain **Incomplete**.
- **Tests:** search `platform/src/**/*.test.*`, `platform/tests/*.spec.ts`; absent row-level coverage is a gap.
- **Issues/PRs:** see [12](12-PR-ISSUE-TRACEABILITY.md); origin lineage may be `UNKNOWN / NEEDS HISTORY TRACE`.
- **Target:** meet REQ-UX-001, relevant feature requirements, explicit stale/unavailable presentation, authenticated ownership where applicable, telemetry, responsive design, and acceptance tests.


## SCREEN-ADMIN — Admin
- **Purpose/features:** Enable the operator/admin to use the admin surface; meaningful controls, tabs, filters, selections, imports or mutations must retain their own test evidence.
- **Current route/status:** `/admin`; Protected + server admin check; status is evidence-qualified in the table.
- **UI/state:** `platform/src/routes/AdminPage.tsx` and its imported components/hooks; React Query plus component/store/local state where imported. Do not infer persistence from presentation state.
- **Backend/data/models:** router families `admin, config`; exact endpoints are in [04](04-BACKEND-API.md), data in [06](06-DATA-ARCHITECTURE.md), models in [07](07-MODEL-REGISTRY.md).
- **Loading/error/empty/mobile:** suspense and route-crash states are verified globally; dependency-specific empty/error and responsive behavior require component/test evidence and otherwise remain **Incomplete**.
- **Tests:** search `platform/src/**/*.test.*`, `platform/tests/*.spec.ts`; absent row-level coverage is a gap.
- **Issues/PRs:** see [12](12-PR-ISSUE-TRACEABILITY.md); origin lineage may be `UNKNOWN / NEEDS HISTORY TRACE`.
- **Target:** meet REQ-UX-001, relevant feature requirements, explicit stale/unavailable presentation, authenticated ownership where applicable, telemetry, responsive design, and acceptance tests.


## SCREEN-HELPGLOSSARY — Help & Glossary
- **Purpose/features:** Enable the trader to use the help & glossary surface; meaningful controls, tabs, filters, selections, imports or mutations must retain their own test evidence.
- **Current route/status:** `/help`; Protected; status is evidence-qualified in the table.
- **UI/state:** `platform/src/routes/HelpPage.tsx` and its imported components/hooks; React Query plus component/store/local state where imported. Do not infer persistence from presentation state.
- **Backend/data/models:** router families `glossary`; exact endpoints are in [04](04-BACKEND-API.md), data in [06](06-DATA-ARCHITECTURE.md), models in [07](07-MODEL-REGISTRY.md).
- **Loading/error/empty/mobile:** suspense and route-crash states are verified globally; dependency-specific empty/error and responsive behavior require component/test evidence and otherwise remain **Incomplete**.
- **Tests:** search `platform/src/**/*.test.*`, `platform/tests/*.spec.ts`; absent row-level coverage is a gap.
- **Issues/PRs:** see [12](12-PR-ISSUE-TRACEABILITY.md); origin lineage may be `UNKNOWN / NEEDS HISTORY TRACE`.
- **Target:** meet REQ-UX-001, relevant feature requirements, explicit stale/unavailable presentation, authenticated ownership where applicable, telemetry, responsive design, and acceptance tests.


## SCREEN-SETTINGS — Settings
- **Purpose/features:** Enable the trader to use the settings surface; meaningful controls, tabs, filters, selections, imports or mutations must retain their own test evidence.
- **Current route/status:** `/settings`; Protected; status is evidence-qualified in the table.
- **UI/state:** `platform/src/routes/SettingsPage.tsx` and its imported components/hooks; React Query plus component/store/local state where imported. Do not infer persistence from presentation state.
- **Backend/data/models:** router families `config`; exact endpoints are in [04](04-BACKEND-API.md), data in [06](06-DATA-ARCHITECTURE.md), models in [07](07-MODEL-REGISTRY.md).
- **Loading/error/empty/mobile:** suspense and route-crash states are verified globally; dependency-specific empty/error and responsive behavior require component/test evidence and otherwise remain **Incomplete**.
- **Tests:** search `platform/src/**/*.test.*`, `platform/tests/*.spec.ts`; absent row-level coverage is a gap.
- **Issues/PRs:** see [12](12-PR-ISSUE-TRACEABILITY.md); origin lineage may be `UNKNOWN / NEEDS HISTORY TRACE`.
- **Target:** meet REQ-UX-001, relevant feature requirements, explicit stale/unavailable presentation, authenticated ownership where applicable, telemetry, responsive design, and acceptance tests.
