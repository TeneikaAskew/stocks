# UI Screen Inventory

**Last reviewed:** 2026-08-30 · **Owner:** TBD

**VERIFIED — CODE.** 15 routes declared in `platform/src/App.tsx:44-72`. `/` is public;
`/welcome` redirects; the other 13 are children of `<AuthGate><AppShell/></AppShell>`.
All page components are `lazy()`-loaded behind `<Suspense fallback={<PageLoader/>}>` with a
shared `RouteErrorBoundary`. React Query defaults to five-minute staleness and one retry.
**Authentication is an in-route sign-in state (`SignInScreen`), not a `/login` route.**

State columns below are **detected in the page source**, not assumed: `load` = a loading or
skeleton branch, `err` = an error branch, `empty` = an empty-result branch, `stale` = any
freshness/as-of/demo-data affordance. A missing marker is a concrete gap to close, not a
statement that the screen is broken.

## Live URLs

**VERIFIED — DEPLOYMENT** (probed 2026-08-30). Production is IAP-gated: an unauthenticated
request to any path below redirects to Google SSO for audience `bictech.org`. Full environment
inventory, including the staging and Discord services whose URLs are not committed anywhere, is
in [05](05-INFRASTRUCTURE.md#environments-and-urls).

| Screen | Route | Production URL | Local dev |
|---|---|---|---|
| Landing | `/` | `https://trading-platform-5sjtb3yl7a-ue.a.run.app/` | `http://localhost:5173/` |
| Welcome redirect | `/welcome` | `https://trading-platform-5sjtb3yl7a-ue.a.run.app/welcome` | `http://localhost:5173/welcome` |
| Dashboard | `/dashboard` | `https://trading-platform-5sjtb3yl7a-ue.a.run.app/dashboard` | `http://localhost:5173/dashboard` |
| Live Market | `/live` | `https://trading-platform-5sjtb3yl7a-ue.a.run.app/live` | `http://localhost:5173/live` |
| Charts | `/charts` | `https://trading-platform-5sjtb3yl7a-ue.a.run.app/charts` | `http://localhost:5173/charts` |
| Options Flow | `/options` | `https://trading-platform-5sjtb3yl7a-ue.a.run.app/options` | `http://localhost:5173/options` |
| Playbook | `/playbook` | `https://trading-platform-5sjtb3yl7a-ue.a.run.app/playbook` | `http://localhost:5173/playbook` |
| Reports | `/reports` | `https://trading-platform-5sjtb3yl7a-ue.a.run.app/reports` | `http://localhost:5173/reports` |
| Signals | `/signals` | `https://trading-platform-5sjtb3yl7a-ue.a.run.app/signals` | `http://localhost:5173/signals` |
| Journal | `/journal` | `https://trading-platform-5sjtb3yl7a-ue.a.run.app/journal` | `http://localhost:5173/journal` |
| AI Insights | `/insights` | `https://trading-platform-5sjtb3yl7a-ue.a.run.app/insights` | `http://localhost:5173/insights` |
| Catalysts | `/catalysts` | `https://trading-platform-5sjtb3yl7a-ue.a.run.app/catalysts` | `http://localhost:5173/catalysts` |
| Admin | `/admin` | `https://trading-platform-5sjtb3yl7a-ue.a.run.app/admin` | `http://localhost:5173/admin` |
| Help & Glossary | `/help` | `https://trading-platform-5sjtb3yl7a-ue.a.run.app/help` | `http://localhost:5173/help` |
| Settings | `/settings` | `https://trading-platform-5sjtb3yl7a-ue.a.run.app/settings` | `http://localhost:5173/settings` |

Operational endpoints outside the SPA router: `https://trading-platform-5sjtb3yl7a-ue.a.run.app/dev` (the unauthenticated-on-staging
page — see [09](09-SECURITY-AUTH.md)), `https://trading-platform-5sjtb3yl7a-ue.a.run.app/api/health`, `https://trading-platform-5sjtb3yl7a-ue.a.run.app/api/health/freshness`.
In local development the frontend dev server lives in the solyra repo since the #957 split
(its Vite proxies `/api` to `http://localhost:8000`); `platform/` here holds only the API.

## Screen inventory

| Screen | Route | Component | LOC | APIs | Child cmpts | load | err | empty | stale | E2E specs | Status |
|---|---|---|---|---|---|:--:|:--:|:--:|:--:|---|---|
| Landing | `/` | `LandingPage` | 40 | 0 | 8 | — | — | — | — | 2 | Production |
| Navigate | `/welcome` | `Navigate` | 0 | 0 | 0 | — | — | — | — | **0** | Production |
| Dashboard | `/dashboard` | `DashboardPage` | 843 | 7 | 14 | ✓ | ✓ | ✓ | ✓ | 4 | Production but needs remediation |
| LiveMarket | `/live` | `LiveMarketPage` | 411 | 1 | 1 | — | ✓ | ✓ | ✓ | 2 | Production but needs remediation |
| Charts | `/charts` | `ChartsPage` | 967 | 0 | 8 | ✓ | ✓ | ✓ | ✓ | 3 | Production but needs remediation |
| OptionsFlow | `/options` | `OptionsFlowPage` | 68 | 0 | 1 | — | — | — | — | 2 | Production but needs remediation |
| Playbook | `/playbook` | `PlaybookPage` | 355 | 2 | 2 | ✓ | ✓ | ✓ | ✓ | 1 | Broken |
| Reports | `/reports` | `ReportsPage` | 153 | 2 | 0 | ✓ | ✓ | ✓ | ✓ | 2 | Production but needs remediation |
| Signals | `/signals` | `SignalsPage` | 341 | 1 | 3 | ✓ | ✓ | ✓ | ✓ | 1 | Production but needs remediation |
| Journal | `/journal` | `JournalPage` | 945 | 2 | 10 | ✓ | ✓ | ✓ | ✓ | 3 | Production but needs remediation |
| Insights | `/insights` | `InsightsPage` | 587 | 1 | 14 | ✓ | ✓ | ✓ | ✓ | 1 | Experimental |
| Catalysts | `/catalysts` | `CatalystsPage` | 625 | 2 | 0 | ✓ | ✓ | — | ✓ | 1 | Production but needs remediation |
| Admin | `/admin` | `AdminPage` | 369 | 1 | 3 | ✓ | ✓ | — | — | 2 | Production but needs remediation |
| Help | `/help` | `HelpPage` | 296 | 0 | 0 | — | — | ✓ | — | 1 | Production |
| Settings | `/settings` | `SettingsPage` | 131 | 0 | 0 | — | — | ✓ | — | **0** | Incomplete |

### Gaps visible from this table

- **`/settings` has zero E2E coverage and zero API calls.** It reads `useThemeStore` and
  `useSettingsStore`, which persist to **`localStorage`** (`platform/src/stores/settingsStore.ts:48,68`)
  — the page header comment says so at line 8. It is **device-local, not user-owned server state**.
  Any ownership, sync or backend-test work planned against `/api/config` or `watchlists` for this
  screen would target the wrong layer.
- **`/options` is a 68-line wrapper** with no loading, error, empty or stale branch of its own;
  all behavior lives in child components. Its states must be verified there, not here.
- **`/admin` has no empty or stale affordance**, and **`/help` has only an empty branch**.
- `/welcome` is a one-line `<Navigate to="/" replace />` — it is a redirect, not a screen, and
  carries no independent requirements.

### Cross-cutting specs

Of the five specs that covered behavior spanning screens rather than one route:
`auth-gate.spec.ts` and `navigation.spec.ts` live in solyra `tests/` since the #957 split;
`api-smoke.spec.ts` and `dev.spec.ts` were deleted in #957 with no replacement (live API smoke
gap tracked in [#971](https://github.com/TeneikaAskew/stocks/issues/971); the `/dev` surface is
[#943](https://github.com/TeneikaAskew/stocks/issues/943)'s, whose tests must be written fresh);
`data-pipeline-status.spec.ts` was split — its widget guard is ported in
[solyra#29](https://github.com/TeneikaAskew/solyra/pull/29), its live API tests fall under #971.
Plus **27 Vitest component tests**, now under solyra `src/**/*.test.*`. Neither suite runs in CI
([solyra#28](https://github.com/TeneikaAskew/solyra/issues/28), formerly #868; both suites moved to solyra in the #957 split).

## Per-screen records

> **Frontend split (2026-09-03 note):** component paths below (`platform/src/**`) moved to
> solyra `src/**` in the #957 split, and the E2E specs live in solyra `tests/`; `platform/`
> in this repo holds only the API.

### SCREEN-LANDING — `/`

- **Purpose:** Public marketing entry and waitlist capture — the only route reachable signed-out in every auth mode.
- **Status:** Production · **Blocking issue:** — · **Owner:** TBD · **Target phase:** see [13](13-ROADMAP.md) · **Last reviewed:** 2026-08-30
- **Component:** `platform/src/routes/LandingPage.tsx` (40 lines)
- **Child components:** `BentoGrid`, `ChartShowcase`, `DailyRhythm`, `Hero`, `LandingFAQ`, `LandingNav`, `ModuleDives`, `WaitlistSection`
- **API calls (from source):** none found in the page component — issued by child components or hooks
- **States present:** none detected · **absent:** load, err, empty, stale
- **E2E specs:** `solyra tests/demo-banners.spec.ts`, `solyra tests/landing.spec.ts`
- **PR lineage:** [#684](https://github.com/TeneikaAskew/stocks/pull/684) origin · [#686](https://github.com/TeneikaAskew/stocks/pull/686) real walk-forward proof tile · [solyra#26](https://github.com/TeneikaAskew/solyra/issues/26) perf open (was #683; moved 2026-09-03)
- **Target:** meet REQ-UX-001 — explicit stale/unavailable presentation, keyboard operability,
  WCAG 2.1 AA contrast, and acceptance tests for every state listed absent above.

### SCREEN-NAVIGATE — `/welcome`

- **Purpose:** Legacy alias; permanently redirects to `/`.
- **Status:** Production · **Blocking issue:** — · **Owner:** TBD · **Target phase:** see [13](13-ROADMAP.md) · **Last reviewed:** 2026-08-30
- **Component:** `platform/src/App.tsx (inline)` (0 lines)
- **API calls (from source):** none found in the page component — issued by child components or hooks
- **States present:** none detected
- **E2E specs:** **none**
- **PR lineage:** [#684](https://github.com/TeneikaAskew/stocks/pull/684)
- **Target:** meet REQ-UX-001 — explicit stale/unavailable presentation, keyboard operability,
  WCAG 2.1 AA contrast, and acceptance tests for every state listed absent above.

### SCREEN-DASHBOARD — `/dashboard`

- **Purpose:** Daily starting point: market brief, movement read, expected move, most-active marquee, sector rotation.
- **Status:** Production but needs remediation · **Blocking issue:** [#861](https://github.com/TeneikaAskew/stocks/issues/861) · **Owner:** TBD · **Target phase:** see [13](13-ROADMAP.md) · **Last reviewed:** 2026-08-30
- **Component:** `platform/src/routes/DashboardPage.tsx` (843 lines)
- **Child components:** `CandlestickChart`, `Card`, `CardHeader`, `Delta`, `DirTag`, `KpiTile`, `Metric`, `MicroLabel`, `MovementRead`, `Pill`, `PriceAreaChart`, `ScoreStars`, `SetupCardDetails`, `TickerCombobox`
- **API calls (from source):** `/api/catalysts/events`, `/api/dashboard/brief/`, `/api/market/data/`, `/api/market/reference/`, `/api/market/sectors`, `/api/playbook/`, `/api/signals/`
- **Stores:** `useReviewDateStore`, `useTickerStore`
- **States present:** load, err, empty, stale
- **E2E specs:** `solyra tests/dashboard-chart-fit.spec.ts`, `solyra tests/dashboard.spec.ts`, `solyra tests/most-active-bar.spec.ts`, `solyra tests/movement-read.spec.ts`
- **PR lineage:** [#649](https://github.com/TeneikaAskew/stocks/pull/649)/[#650](https://github.com/TeneikaAskew/stocks/pull/650) movement statement · [#729](https://github.com/TeneikaAskew/stocks/pull/729) enable + e2e · [#732](https://github.com/TeneikaAskew/stocks/pull/732) most-active bar · [#733](https://github.com/TeneikaAskew/stocks/pull/733) expected-move card (disabled by [#810](https://github.com/TeneikaAskew/stocks/pull/810))
- **Target:** meet REQ-UX-001 — explicit stale/unavailable presentation, keyboard operability,
  WCAG 2.1 AA contrast, and acceptance tests for every state listed absent above.

### SCREEN-LIVEMARKET — `/live`

- **Purpose:** Intraday monitoring of quotes, indicators and STRAT state for the watchlist.
- **Status:** Production but needs remediation · **Blocking issue:** [#928](https://github.com/TeneikaAskew/stocks/issues/928) · **Owner:** TBD · **Target phase:** see [13](13-ROADMAP.md) · **Last reviewed:** 2026-08-30
- **Component:** `platform/src/routes/LiveMarketPage.tsx` (411 lines)
- **Child components:** `MetricCard`
- **API calls (from source):** `/api/market/data/`
- **Stores:** `useReviewDateStore`, `useTickerStore`
- **States present:** err, empty, stale · **absent:** load
- **E2E specs:** `solyra tests/live-market.spec.ts`, `solyra tests/movement-read.spec.ts`
- **PR lineage:** [#690](https://github.com/TeneikaAskew/stocks/pull/690) market dropdown + truthful session badge · [#700](https://github.com/TeneikaAskew/stocks/pull/700) one-source-of-truth signals
- **Target:** meet REQ-UX-001 — explicit stale/unavailable presentation, keyboard operability,
  WCAG 2.1 AA contrast, and acceptance tests for every state listed absent above.

### SCREEN-CHARTS — `/charts`

- **Purpose:** Instrument and timeframe chart analysis with strategy conditions and level overlays.
- **Status:** Production but needs remediation · **Blocking issue:** [#912](https://github.com/TeneikaAskew/stocks/issues/912) · **Owner:** TBD · **Target phase:** see [13](13-ROADMAP.md) · **Last reviewed:** 2026-08-30
- **Component:** `platform/src/routes/ChartsPage.tsx` (967 lines)
- **Child components:** `LoadingSpinner`, `Modal`, `ReplaySessionControls`, `SimilarSetupsCard`, `StrategyConditionsCard`, `TradeMarkingChart`, `type PriceLineConfig`, `type TradeMarkingChartHandle`
- **API calls (from source):** none found in the page component — issued by child components or hooks
- **Stores:** `useReviewDateStore`, `useSettingsStore`, `useTickerStore`
- **States present:** load, err, empty, stale
- **E2E specs:** `solyra tests/charts-cards.spec.ts`, `solyra tests/ticker-combobox.spec.ts` (`phase1-charts.spec.ts` deleted as stale — #958)
- **PR lineage:** [#715](https://github.com/TeneikaAskew/stocks/pull/715) restore charts UI · [#703](https://github.com/TeneikaAskew/stocks/pull/703) ticker type-ahead · [#700](https://github.com/TeneikaAskew/stocks/pull/700)
- **Target:** meet REQ-UX-001 — explicit stale/unavailable presentation, keyboard operability,
  WCAG 2.1 AA contrast, and acceptance tests for every state listed absent above.

### SCREEN-OPTIONSFLOW — `/options`

- **Purpose:** Options flow, Greeks and the 2-D strike x expiration gamma grid.
- **Status:** Production but needs remediation · **Blocking issue:** [#826](https://github.com/TeneikaAskew/stocks/issues/826) · **Owner:** TBD · **Target phase:** see [13](13-ROADMAP.md) · **Last reviewed:** 2026-08-30
- **Component:** `platform/src/routes/OptionsFlowPage.tsx` (68 lines)
- **Child components:** `TickerCombobox`
- **API calls (from source):** none found in the page component — issued by child components or hooks
- **Stores:** `useTickerStore`
- **States present:** none detected · **absent:** load, err, empty, stale
- **E2E specs:** `solyra tests/gamma-levels.spec.ts`, `solyra tests/options-flow.spec.ts`
- **PR lineage:** [#255](https://github.com/TeneikaAskew/stocks/pull/255) Cloudflare→FastAPI cutover · [#540](https://github.com/TeneikaAskew/stocks/pull/540)/[#541](https://github.com/TeneikaAskew/stocks/pull/541) grid math + endpoints · [#645](https://github.com/TeneikaAskew/stocks/pull/645) wire Swing Mode to real /grid
- **Target:** meet REQ-UX-001 — explicit stale/unavailable presentation, keyboard operability,
  WCAG 2.1 AA contrast, and acceptance tests for every state listed absent above.

### SCREEN-PLAYBOOK — `/playbook`

- **Purpose:** The day’s structured setups — trigger, invalidation, targets — with as-of review mode.
- **Status:** Broken · **Blocking issue:** [#861](https://github.com/TeneikaAskew/stocks/issues/861) · **Owner:** TBD · **Target phase:** see [13](13-ROADMAP.md) · **Last reviewed:** 2026-08-30
- **Component:** `platform/src/routes/PlaybookPage.tsx` (355 lines)
- **Child components:** `SetupCardDetails`, `type SetupHorizon`
- **API calls (from source):** `/api/market/reference/`, `/api/playbook/`
- **Stores:** `useTickerStore`
- **States present:** load, err, empty, stale
- **E2E specs:** `solyra tests/playbook.spec.ts`
- **PR lineage:** [#444](https://github.com/TeneikaAskew/stocks/pull/444) EOD outcome tracking + as-of cutoff · [#620](https://github.com/TeneikaAskew/stocks/pull/620) as-of review mode · [#774](https://github.com/TeneikaAskew/stocks/pull/774) silent resolver outage fix
- **Target:** meet REQ-UX-001 — explicit stale/unavailable presentation, keyboard operability,
  WCAG 2.1 AA contrast, and acceptance tests for every state listed absent above.

### SCREEN-REPORTS — `/reports`

- **Purpose:** Backtest, walk-forward and replay-trainer results; analytics summaries.
- **Status:** Production but needs remediation · **Blocking issue:** [#813](https://github.com/TeneikaAskew/stocks/issues/813) · **Owner:** TBD · **Target phase:** see [13](13-ROADMAP.md) · **Last reviewed:** 2026-08-30
- **Component:** `platform/src/routes/ReportsPage.tsx` (153 lines)
- **API calls (from source):** `/api/reports/`, `/api/reports/list/`
- **Stores:** `useTickerStore`
- **States present:** load, err, empty, stale
- **E2E specs:** `solyra tests/replay-trainer.spec.ts`, `solyra tests/reports.spec.ts`
- **PR lineage:** [#513](https://github.com/TeneikaAskew/stocks/pull/513) backtest→Cloud Run · [#548](https://github.com/TeneikaAskew/stocks/pull/548) walk-forward stage · [#706](https://github.com/TeneikaAskew/stocks/pull/706) backtest my trades · [#710](https://github.com/TeneikaAskew/stocks/pull/710) bar-replay trainer
- **Target:** meet REQ-UX-001 — explicit stale/unavailable presentation, keyboard operability,
  WCAG 2.1 AA contrast, and acceptance tests for every state listed absent above.

### SCREEN-SIGNALS — `/signals`

- **Purpose:** Signal discovery and live alert monitoring.
- **Status:** Production but needs remediation · **Blocking issue:** [#905](https://github.com/TeneikaAskew/stocks/issues/905) · **Owner:** TBD · **Target phase:** see [13](13-ROADMAP.md) · **Last reviewed:** 2026-08-30
- **Component:** `platform/src/routes/SignalsPage.tsx` (341 lines)
- **Child components:** `KpiTile`, `MicroLabel`, `TickerCombobox`
- **API calls (from source):** `/api/signals/`
- **Stores:** `useReviewDateStore`, `useTickerStore`
- **States present:** load, err, empty, stale
- **E2E specs:** `solyra tests/signals.spec.ts`
- **PR lineage:** [#184](https://github.com/TeneikaAskew/stocks/pull/184) lib/strategies origin · [#504](https://github.com/TeneikaAskew/stocks/pull/504) dedicated Discord channel · [#803](https://github.com/TeneikaAskew/stocks/pull/803) RVOL respecification
- **Target:** meet REQ-UX-001 — explicit stale/unavailable presentation, keyboard operability,
  WCAG 2.1 AA contrast, and acceptance tests for every state listed absent above.

### SCREEN-JOURNAL — `/journal`

- **Purpose:** One-stop trade cockpit: interactive chart marking, examples, broker CSV import, per-user trades.
- **Status:** Production but needs remediation · **Blocking issue:** [#717](https://github.com/TeneikaAskew/stocks/issues/717) · **Owner:** TBD · **Target phase:** see [13](13-ROADMAP.md) · **Last reviewed:** 2026-08-30
- **Component:** `platform/src/routes/JournalPage.tsx` (945 lines)
- **Child components:** `Card`, `CardHeader`, `ImportTradesModal`, `KpiTile`, `LoadingSpinner`, `PriceAreaChart`, `TickerCombobox`, `TradeMarkingChart`, `TradeRailCard`, `type TradeMarkingChartHandle`
- **API calls (from source):** `/api/journal/export/`, `/api/journal/trades`
- **Stores:** `useSettingsStore`, `useTickerStore`
- **States present:** load, err, empty, stale
- **E2E specs:** `solyra tests/journal-import.spec.ts`, `solyra tests/journal-onestop.spec.ts`, `solyra tests/journal.spec.ts`
- **PR lineage:** [#626](https://github.com/TeneikaAskew/stocks/pull/626) per-user scoping · [#705](https://github.com/TeneikaAskew/stocks/pull/705) chart trades persist · [#718](https://github.com/TeneikaAskew/stocks/pull/718) one-stop cockpit · [#764](https://github.com/TeneikaAskew/stocks/pull/764) tz guard
- **Target:** meet REQ-UX-001 — explicit stale/unavailable presentation, keyboard operability,
  WCAG 2.1 AA contrast, and acceptance tests for every state listed absent above.

### SCREEN-INSIGHTS — `/insights`

- **Purpose:** AI-generated per-ticker insight reports, history and chat.
- **Status:** Experimental · **Blocking issue:** [#916](https://github.com/TeneikaAskew/stocks/issues/916) · **Owner:** TBD · **Target phase:** see [13](13-ROADMAP.md) · **Last reviewed:** 2026-08-30
- **Component:** `platform/src/routes/InsightsPage.tsx` (587 lines)
- **Child components:** `AgentsPanel`, `BriefVsInsightsCard`, `CatalystsCard`, `DebateCard`, `DegradationBanner`, `HeaderCard`, `KeyLevelsCard`, `MicroLabel`, `PersonaPlansCard`, `RiskFlagsCard`, `SignalsCard`, `SimilarTradesCard`, `StratCard`, `TickerCombobox`
- **API calls (from source):** `/api/insights/chat`
- **Stores:** `useTickerStore`
- **States present:** load, err, empty, stale
- **E2E specs:** `solyra tests/insights.spec.ts`
- **PR lineage:** [#353](https://github.com/TeneikaAskew/stocks/pull/353) divergence card · [#344](https://github.com/TeneikaAskew/stocks/pull/344) reflection memory · [#451](https://github.com/TeneikaAskew/stocks/pull/451) break feedback loop
- **Target:** meet REQ-UX-001 — explicit stale/unavailable presentation, keyboard operability,
  WCAG 2.1 AA contrast, and acceptance tests for every state listed absent above.

### SCREEN-CATALYSTS — `/catalysts`

- **Purpose:** Earnings, economic events, news and SEC filings as trade context.
- **Status:** Production but needs remediation · **Blocking issue:** [#863](https://github.com/TeneikaAskew/stocks/issues/863) · **Owner:** TBD · **Target phase:** see [13](13-ROADMAP.md) · **Last reviewed:** 2026-08-30
- **Component:** `platform/src/routes/CatalystsPage.tsx` (625 lines)
- **API calls (from source):** `/api/catalysts/events`, `/api/catalysts/types`
- **Stores:** `useThemeStore`, `useTickerStore`
- **States present:** load, err, stale · **absent:** empty
- **E2E specs:** `solyra tests/catalysts.spec.ts`
- **PR lineage:** [#624](https://github.com/TeneikaAskew/stocks/pull/624) earnings router origin · [#220](https://github.com/TeneikaAskew/stocks/pull/220) catalyst proximity · [#532](https://github.com/TeneikaAskew/stocks/pull/532) $-attribution
- **Target:** meet REQ-UX-001 — explicit stale/unavailable presentation, keyboard operability,
  WCAG 2.1 AA contrast, and acceptance tests for every state listed absent above.

### SCREEN-ADMIN — `/admin`

- **Purpose:** Operator surface: model routing, strat-engine state, structure brief, route config.
- **Status:** Production but needs remediation · **Blocking issue:** [#838](https://github.com/TeneikaAskew/stocks/issues/838) · **Owner:** TBD · **Target phase:** see [13](13-ROADMAP.md) · **Last reviewed:** 2026-08-30
- **Component:** `platform/src/routes/AdminPage.tsx` (369 lines)
- **Child components:** `ModelStateSnapshot`, `PredictForm`, `StructureBrief`
- **API calls (from source):** `/api/admin/routes`
- **States present:** load, err · **absent:** empty, stale
- **E2E specs:** `solyra tests/admin-auth.spec.ts`, `solyra tests/admin.spec.ts`
- **PR lineage:** [#567](https://github.com/TeneikaAskew/stocks/pull/567)/[#568](https://github.com/TeneikaAskew/stocks/pull/568) strat_engine state dashboard · [#635](https://github.com/TeneikaAskew/stocks/pull/635) platform audit
- **Target:** meet REQ-UX-001 — explicit stale/unavailable presentation, keyboard operability,
  WCAG 2.1 AA contrast, and acceptance tests for every state listed absent above.

### SCREEN-HELP — `/help`

- **Purpose:** Glossary and cross-framework term reference.
- **Status:** Production · **Blocking issue:** — · **Owner:** TBD · **Target phase:** see [13](13-ROADMAP.md) · **Last reviewed:** 2026-08-30
- **Component:** `platform/src/routes/HelpPage.tsx` (296 lines)
- **API calls (from source):** none found in the page component — issued by child components or hooks
- **States present:** empty · **absent:** load, err, stale
- **E2E specs:** `solyra tests/help.spec.ts`
- **PR lineage:** [#539](https://github.com/TeneikaAskew/stocks/pull/539) gamma glossary + endpoint · [#546](https://github.com/TeneikaAskew/stocks/pull/546) TermHover · [#423](https://github.com/TeneikaAskew/stocks/pull/423) 11 Strat entries
- **Target:** meet REQ-UX-001 — explicit stale/unavailable presentation, keyboard operability,
  WCAG 2.1 AA contrast, and acceptance tests for every state listed absent above.

### SCREEN-SETTINGS — `/settings`

- **Purpose:** Device-local appearance and layout preferences.
- **Status:** Incomplete · **Blocking issue:** [solyra#27](https://github.com/TeneikaAskew/solyra/issues/27) (was #685; moved 2026-09-03) · **Owner:** TBD · **Target phase:** see [13](13-ROADMAP.md) · **Last reviewed:** 2026-08-30
- **Component:** `platform/src/routes/SettingsPage.tsx` (131 lines)
- **API calls (from source):** none found in the page component — device-local state only
- **Stores:** `useSettingsStore`, `useThemeStore`
- **States present:** empty · **absent:** load, err, stale
- **E2E specs:** **none**
- **PR lineage:** [#611](https://github.com/TeneikaAskew/stocks/pull/611) platform redesign · [#589](https://github.com/TeneikaAskew/stocks/pull/589) app shell
- **Target:** meet REQ-UX-001 — explicit stale/unavailable presentation, keyboard operability,
  WCAG 2.1 AA contrast, and acceptance tests for every state listed absent above.

