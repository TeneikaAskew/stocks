# FRONTEND ARCHITECTURE

> **Companion to** [`ARCHITECTURE.md`](ARCHITECTURE.md) — that doc covers the GCP/Cloud-Run/Cloud-SQL backbone; this doc covers the React + Vite single-page app that ships inside the `trading-platform` Cloud Run service.
> **Last refreshed:** 2026-05-22.
> **Companion diagram:** [`Frontend.drawio`](Frontend.drawio).

## TL;DR

- **Stack:** React 19 + TypeScript 5.9 + Vite 7 + Tailwind 4, Zustand for client state, TanStack Query for server state, TanStack Table for tables, Recharts + lightweight-charts for visualisations, react-router-dom v7 with a single nested layout route.
- **Layout:** one root `BrowserRouter` with an `AppShell` (sidebar + header) wrapping **12 route-level pages**, each lazy-loaded with `React.lazy` + `Suspense` and isolated by a per-route `RouteErrorBoundary` so a single page crash doesn't take down the chrome.
- **API surface:** ~30 endpoints all under `/api/*`, served by the same FastAPI process that serves the static SPA (single-port Cloud Run service on port 8080 in production; dev uses Vite on 5173 proxied to FastAPI on 8000).
- **Build/deploy:** `npm run build` → `platform/dist/` → bundled into the `trading-platform` Docker image (multi-stage, frontend stage = node:20-slim, runtime = python:3.11-slim) → Cloud Build → Cloud Run service at `stocks.insightscollective.org` (IAP-gated, Google-managed TLS, `--no-cpu-throttling`).
- **Two-stage deploy:** push to `main` triggers `deploy-platform-staging.yml` → revision tagged `staging` at 0% traffic → manual `promote-platform-prod.yml` shifts 100% traffic to the staging tag.

## Directory map

```
platform/
├─ index.html                   # Vite HTML entry (dark mode default)
├─ package.json                 # React 19, Vite 7, Tailwind 4, Zustand, TanStack Query/Table, Recharts
├─ vite.config.ts               # @ → src alias, proxies /api + /dev to FastAPI :8000
├─ tsconfig.json + tsconfig.{app,node}.json
├─ eslint.config.js
├─ playwright.config.ts         # E2E
├─ Dockerfile                   # multi-stage: node builds dist/, python serves it
├─ cloudbuild.yaml              # Cloud Build for trading-platform image
├─ deploy.sh                    # build + deploy (STAGING=1 for staging revision)
├─ screenshot_pages.mjs         # Playwright util for capturing each page
├─ src/
│  ├─ main.tsx                  # ReactDOM.createRoot(...).render(<App />)
│  ├─ App.tsx                   # QueryClientProvider + RouterProvider (12 routes)
│  ├─ routes/                   # 12 lazy-loaded pages — one per sidebar nav item
│  │  ├─ DashboardPage.tsx      # /         — Data pipeline health, watchlist summary
│  │  ├─ LiveMarketPage.tsx     # /live     — real-time quote + indicators
│  │  ├─ ChartsPage.tsx         # /charts   — candlestick / area chart + strategy conditions
│  │  ├─ OptionsFlowPage.tsx    # /options  — Greeks, GEX, options table
│  │  ├─ PlaybookPage.tsx       # /playbook — pre-market playbook evaluator
│  │  ├─ ReportsPage.tsx        # /reports  — analytics + trade stats
│  │  ├─ SignalsPage.tsx        # /signals  — live + historical signal_alerts
│  │  ├─ JournalPage.tsx        # /journal  — trade journal entries
│  │  ├─ InsightsPage.tsx       # /insights — AI insight cards + watchlist + refresh
│  │  ├─ CatalystsPage.tsx      # /catalysts— Benzinga catalysts calendar
│  │  ├─ AdminPage.tsx          # /admin    — admin-only (model_routing, role routes)
│  │  └─ HelpPage.tsx           # /help     — glossary, Strat methodology refs
│  ├─ components/
│  │  ├─ layout/                # AppShell, Header, Sidebar (12 nav items + ticker switcher)
│  │  ├─ shared/                # DataTable, MetricCard, Modal, Tabs, DateSelector,
│  │  │                         # LoadingSpinner, RouteErrorBoundary
│  │  ├─ dashboard/             # DataPipelineStatus
│  │  ├─ insights/              # ReportCards, WatchlistPanel
│  │  ├─ charts/                # CandlestickChart, PriceAreaChart,
│  │  │                         # StrategyConditionsCard, SimilarSetupsCard
│  │  └─ backtest/              # BacktesterSection
│  ├─ hooks/                    # 17 TanStack-Query-backed data hooks (see hook map below)
│  ├─ stores/                   # Zustand client state (5 stores)
│  │  ├─ tickerStore.ts         # activeTicker + availableTickers (IWM/SPY/QQQ)
│  │  ├─ tradeStore.ts          # in-flight trade form state
│  │  ├─ themeStore.ts          # dark/light toggle
│  │  ├─ settingsStore.ts       # sidebar collapsed, etc.
│  │  └─ reviewDateStore.ts     # date selector for weekend review
│  ├─ lib/                      # pure helpers, mirrors lib/ on the backend
│  │  ├─ indicators.ts          # client-side indicator math (mirror of lib/indicators.py)
│  │  ├─ playbookEvaluator.ts   # evaluator used before backend round-trip
│  │  ├─ marketSession.ts       # pre/RTH/post-market clock
│  │  ├─ chartTheme.ts          # Recharts + lightweight-charts colors
│  │  ├─ time.ts                # ET-aware date helpers
│  │  └─ *.test.ts              # Vitest unit tests
│  └─ types/                    # Ticker, Insight, Watchlist type defs
└─ tests/                       # Playwright E2E specs
   └─ helpers/                  # shared E2E utilities
```

## Routing model

`App.tsx` builds a single `createBrowserRouter` tree with one **layout route** (`AppShell`) wrapping **12 child routes**. Each child:

- is `React.lazy`-loaded, so the initial bundle is only the shell + the active page;
- is wrapped in a `<Suspense fallback={<PageLoader />}>` for the lazy-load handoff;
- carries its own `errorElement={<RouteErrorBoundary />}` — when a page crashes during render, the boundary catches it, keeps sidebar + header rendered, and shows a card with the error + a refresh button. The crash does **not** unmount the chrome.

The 12 routes:

| Path        | Page                 | Purpose | Primary API surface |
|-------------|----------------------|---------|---------------------|
| `/`         | `DashboardPage`      | Data-pipeline freshness + watchlist summary | `/api/dashboard/brief/{ticker}` |
| `/live`     | `LiveMarketPage`     | Real-time quote, intraday indicators | `/api/live/quote`, `/api/live/indicators`, `/api/live/history`, `/api/live/avg-volume`, `/api/live/status` |
| `/charts`   | `ChartsPage`         | Candlestick + area + strategy-conditions card | `/api/market/data/{ticker}/{date}`, `/api/market/dates`, `/api/market/reference` |
| `/options`  | `OptionsFlowPage`    | Greeks, GEX, options chain | `/api/options/greeks` |
| `/playbook` | `PlaybookPage`       | Pre-market playbook trigger/target/stop evaluator | `/api/playbook/evaluate` (+ client-side `playbookEvaluator.ts` mirror) |
| `/reports`  | `ReportsPage`        | Analytics, trade stats, per-ticker summaries | `/api/analytics/summary/{ticker}`, `/api/analytics/trade-stats` |
| `/signals`  | `SignalsPage`        | Live + historical `signal_alerts`, similar-setups search | `/api/signals/{ticker}/similar` |
| `/journal`  | `JournalPage`        | Trade journal CRUD | `/api/journal/*` |
| `/insights` | `InsightsPage`       | AI insight cards, refresh button (Cloud Tasks enqueue) | `/api/insights/report/{ticker}`, `/refresh`, `/history`, `/api/insights/watchlist` |
| `/catalysts`| `CatalystsPage`      | Benzinga catalysts calendar | `/api/catalysts/*` |
| `/admin`    | `AdminPage`          | Admin-only — model routing, role/route grants | `/api/admin/models`, `/api/admin/routes/{role}` |
| `/help`     | `HelpPage`           | Glossary + Strat methodology refs | static |

The `Sidebar` filters `/admin` out for non-admin users (server-resolved via `useUser` → `/api/me`).

## Data flow

Three concentric loops:

1. **Server state — TanStack Query.** All hooks under `src/hooks/use*.ts` use `useQuery`/`useMutation` keyed by `[resource, ...params]`. The `QueryClient` in `App.tsx` sets `staleTime: 5 min` and `retry: 1` — most market data is "fresh enough for 5 minutes," and a single retry catches transient Cloud Run cold-starts without thrashing on real outages.
2. **Client state — Zustand.** Five stores hold UI-only state: active ticker (`tickerStore`), in-flight trade form (`tradeStore`), dark/light (`themeStore`), sidebar collapsed (`settingsStore`), date selector (`reviewDateStore`). No server data leaks into Zustand — that lives in the query cache.
3. **Local computation — `src/lib/*.ts`.** Pure functions: client-side indicator math (`indicators.ts`), market-session clock (`marketSession.ts`), playbook evaluator (`playbookEvaluator.ts`). These mirror the backend `lib/*.py` modules so charts and pre-evaluation can render without a round-trip. **Tested with Vitest** (`*.test.ts` files alongside).

### Hook → endpoint map

| Hook                       | Endpoint(s) hit                                            | Reads                              |
|----------------------------|------------------------------------------------------------|------------------------------------|
| `useUser`                  | `/api/me`                                                  | Identity + admin flag (IAP header) |
| `useTickerSearch`          | (client-side filter over `availableTickers`)               | Zustand `tickerStore`              |
| `useLiveQuote`             | `/api/live/quote/{ticker}`                                 | Latest 1-min bar                   |
| `useLiveIndicators`        | `/api/live/indicators`                                     | Wilder RSI/EMA/ATR/VWAP            |
| `useLiveHistory`           | `/api/live/history/{ticker}`                               | Intraday history window            |
| `useLiveStatus`            | `/api/live/status`                                         | Market session + fetcher freshness |
| `useMarketData`            | `/api/market/data/{ticker}/{date}`, `/dates`, `/reference` | Daily OHLCV for chart              |
| `useGammaLevels`           | `/api/options/greeks` (per-strike GEX)                     | King/Gate/Spot/Flip                |
| `useOptionsGreeks`         | `/api/options/greeks`                                      | BSM delta/gamma/theta/vega         |
| `usePlaybookEvaluation`    | `/api/playbook/evaluate`                                   | trigger/target/stop                |
| `useInsights`              | `/api/insights/report/{ticker}`, `/refresh`, `/history`    | AI insight reports                 |
| `useWatchlist`             | `/api/insights/watchlist`                                  | Watchlist CRUD                     |
| `useSimilarSetups`         | `/api/signals/{ticker}/similar`                            | Historical near-neighbours         |
| `useTradeAnalytics`        | `/api/analytics/summary/{ticker}`, `/trade-stats`          | Per-ticker analytics               |
| `useAdmin`                 | `/api/admin/models`, `/api/admin/routes/{role}`            | Model routing, RBAC                |
| `useConfig`                | `/api/config/indicators`, `/api/config/market-hours`       | Server-resolved config             |
| `useUser` (above)          | `/api/me`                                                  |                                    |

All hooks read `useTickerStore().activeTicker` (or a per-page override) and key the query on it, so flipping the sidebar ticker switcher refetches every ticker-scoped query in one move.

## Refresh semantics — AI insights write path

Most pages are read-only. The one important write path is the **insights refresh button**, which closes a loop through Cloud Tasks:

```
Browser (InsightsPage / ReportCards)
  ↓ POST /api/insights/report/{ticker}/refresh
FastAPI router (platform/api/routers/insights.py)
  ↓ enqueue task on insight-pipeline-queue (Cloud Tasks)
  ↓ task targets the insight-pipeline Cloud Run Job's :run endpoint
  ↓ with env vars INSIGHT_RUN_ID + INSIGHT_TICKER
Cloud Tasks delivers → insight-pipeline Job runs
  ↓ writes one row to insight_reports + insight_runs in Cloud SQL
Browser re-polls /api/insights/report/{ticker} via TanStack Query refetch
  ↓ new row appears
```

This is the only path that mutates production data from the frontend — everything else is a read or a journal CRUD that lands in `journal_entries`.

## Build pipeline

### Local dev

```bash
cd platform && npm install         # one-time
npm run dev                        # vite on :5173, proxies /api → :8000
# In another terminal:
make dev                           # FastAPI on :8000 (from repo root)
```

`vite.config.ts` proxies `/api/*` (and `/dev/*`) to `localhost:8000`, so the browser only talks to `:5173`. Hot-module reload works for `.tsx`/`.css`; FastAPI auto-reloads via `uvicorn --reload`.

### Production build

```bash
npm run build                       # tsc -b && vite build → platform/dist/
```

`tsc -b` runs project-references compilation (`tsconfig.app.json` + `tsconfig.node.json`) — type-checks the whole app before bundling. `vite build` produces tree-shaken, code-split chunks (each lazy route is its own chunk) into `platform/dist/`.

### Docker image

[`platform/Dockerfile`](platform/Dockerfile) is multi-stage:

1. **`frontend` stage** (`node:20-slim`) — runs `npm ci` + `npm run build`, outputs `/build/platform/dist/`.
2. **`runtime` stage** (`python:3.11-slim`) — installs FastAPI deps, copies `lib/` + `gcp/` + `platform/api/`, then `COPY --from=frontend /build/platform/dist /app/platform/dist` so the same Python process serves the SPA + `/api/*`. `main.py` mounts `dist/` as a `StaticFiles` at `/`.

This means **one Cloud Run service, one port, one TLS cert** — no separate CDN, no separate static host. Cold-start budget is dominated by the Python import graph (`lib/`, `gcp/database.py` Cloud-SQL connector), not by the frontend assets, which are pre-built at image-build time.

### Cloud Run deploy — staging → production

`platform/deploy.sh` drives both modes:

| Mode               | Cmd                                  | Behaviour                                                                 |
|--------------------|--------------------------------------|---------------------------------------------------------------------------|
| Production         | `./platform/deploy.sh`               | builds image, deploys revision tagged `latest` with 100% traffic           |
| Staging            | `STAGING=1 ./platform/deploy.sh`     | builds image, deploys revision tagged `staging` with `--no-traffic` (0%) — reachable at `https://staging---trading-platform-…run.app`, prod untouched |
| Promote staging → prod | `gcloud run services update-traffic trading-platform --to-tags=staging=100` | shifts 100% to the staging-tagged revision                              |

CI wiring:

- [`.github/workflows/deploy-platform-staging.yml`](.github/workflows/deploy-platform-staging.yml) — triggers on push to `main` touching `platform/**`, `lib/**`, `requirements.txt`, or `gcp/database.py`. Runs `STAGING=1 ./platform/deploy.sh`.
- [`.github/workflows/promote-platform-prod.yml`](.github/workflows/promote-platform-prod.yml) — manual `workflow_dispatch`, promotes the staging revision. Shares the staging workflow's concurrency group so deploy + promote can't interleave.

Both authenticate via the `CLAUDE_CODE_WEB_GCP_SA_KEY` repo secret (the same `claude-web@` SA used by every other GCP-touching workflow).

## Testing

- **Unit (`npm test` → Vitest):** pure helpers in `src/lib/*.ts` have co-located `*.test.ts`. Currently covers `playbookEvaluator`, `strategySignals`, `strategySignalsForSeries`, `marketSession`.
- **Component:** none currently — Vitest is config'd for component tests via `@testing-library/react`, but the suite is empty. Filed as a coverage gap.
- **E2E (`npm run e2e` → Playwright):** `tests/*.spec.ts` runs the full app under `chromium`. Two project profiles:
  - `chromium` (default) — local dev against `npm run dev`;
  - `cloud` — runs against the production Cloud Run URL behind IAP. Requires a one-time `e2e:cloud:auth` to capture an IAP cookie, then `e2e:cloud` re-uses it.
- **Lint:** `npm run lint` → ESLint 9 with `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`.

## Production runtime

- **URL:** `https://stocks.insightscollective.org` (Cloud Run domain mapping, Google-managed TLS).
- **Auth:** Identity-Aware Proxy gates the service. The browser handshakes with Google's IAP IdP, IAP injects the `X-Goog-Iap-Jwt-Assertion` header into the FastAPI request, `/api/me` validates it and returns `{ email, isAdmin }`. The `useUser` hook reads this once per session and gates the `/admin` route.
- **Cloud Run config:** `min-instances=1` (to avoid cold-start hitting Discord's 3-sec interaction-ack budget when the same image happens to be invoked for back-channel work), `--no-cpu-throttling` (PR #507 — FastAPI BackgroundTasks need full CPU after the response is sent), 1 vCPU / 1 GiB.
- **Logging:** stdout → Cloud Logging; the failure-notifier sink does NOT cover the service (its filter is `resource.type=cloud_run_job`), so service errors don't auto-create GitHub issues. Pager-style monitoring is via Cloud Logging alert policies (not yet wired — open todo).

## Known limitations

- **No service worker / offline mode.** A reload during a network hiccup shows the browser's network-error page.
- **No code-coverage gate in CI.** Vitest runs but coverage isn't enforced; coverage gaps in `hooks/` and `components/` are not visible until they cause a runtime regression.
- **No component-test layer.** Vitest is only running pure-helper unit tests; the `@testing-library/react` install is dead weight until someone writes the first component test.
- **No Storybook / design-system doc.** Components are documented only by usage. Adding Storybook would help the Tailwind 4 + custom tokens story stay coherent.
- **`/api/me` not cached.** Every page-mount refetches identity. Cheap (single Cloud SQL row) but unnecessary churn.

## Open work

1. **Component test bed.** Set up `@testing-library/react` and write tests for at least `DataTable`, `MetricCard`, `Sidebar` route gating, `RouteErrorBoundary`.
2. **Coverage gate.** Wire Vitest `--coverage` into the staging-deploy workflow as an advisory check.
3. **Cloud Logging alert policy** for the `trading-platform` service (5xx rate, p95 latency).
4. **Component documentation surface** (Storybook or Ladle) — the Tailwind 4 token system is undocumented outside of `chartTheme.ts`.
