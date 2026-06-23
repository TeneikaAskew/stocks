# FRONTEND ARCHITECTURE

> **Companion to** [`ARCHITECTURE.md`](ARCHITECTURE.md) — that doc covers the GCP/Cloud-Run/Cloud-SQL backbone; this doc covers the React + Vite single-page app that ships inside the `trading-platform` Cloud Run service.
> **Last refreshed:** 2026-06-23.
> **Companion diagram:** [`Frontend.drawio`](Frontend.drawio).
> **Canonical route-by-route inventory:** [`docs/PLATFORM_AUDIT_2026-06-19.md`](docs/PLATFORM_AUDIT_2026-06-19.md).

## TL;DR

- **Stack:** React 19 + TypeScript + Vite + Tailwind v4 + HeroUI, Zustand for client state, TanStack Query for server state, TanStack Table for tables, lightweight-charts (candles/volume) + Recharts (area/line/equity) + d3 for visualisations, react-router-dom v6 with a single nested layout route.
- **Layout:** one root `createBrowserRouter` with an `AppShell` (selectable top-tabs **or** sidebar nav + header) wrapping **13 route-level pages**, each lazy-loaded with `React.lazy` + `Suspense` and isolated by a per-route `RouteErrorBoundary` so a single page crash doesn't take down the chrome. A global ⌘K / Ctrl-K command palette jumps to any page/ticker/action.
- **Authentication:** new `AUTH_MODE` layer (`firebase` / `iap` / `open`). The whole app is wrapped in an `AuthGate`; in `firebase` mode an unauthenticated user gets a `SignInScreen`, and every gated `/api/*` call carries a Firebase bearer token injected by a global `fetch` wrapper. **Production runs on IAP today; staging runs on Firebase** (the in-app login). 401 → sign in, 403 → not allowed — fail-closed, no anonymous render (CLAUDE.md Rule 3.7).
- **API surface:** `/api/*` served by the same FastAPI process that serves the static SPA, across **17 routers** under `platform/api/routers/`, importing the shared `lib/` math spine. Single-port Cloud Run service in production; dev uses Vite on 5173 proxied to FastAPI on 8000.
- **Build/deploy:** `npm run build` → `platform/dist/` → bundled into the `trading-platform` Docker image (multi-stage: frontend = node, runtime = python serving FastAPI + the React dist) → Cloud Build → Cloud Run service at `stocks.insightscollective.org` (IAP-gated, Google-managed TLS, `--no-cpu-throttling`). `platform/deploy.sh` drives both prod and a public `STAGING=1` revision (the platform-deploy GHA workflows were retired in favour of `platform/deploy.sh`).

## Authentication layer

The former staging passcode bypass (`auth_bypass.py`) is gone. One middleware in [`platform/api/auth.py`](platform/api/auth.py) serves three modes off the `AUTH_MODE` env var, so a single built image works in every environment:

| `AUTH_MODE` | Where | How identity is resolved | Enforcement |
|-------------|-------|--------------------------|-------------|
| `firebase`  | staging service (public, no IAP) | verify a Firebase ID token (`Authorization: Bearer …`) on every gated `/api/*` request; identity = the verified email | middleware enforces — invalid/expired token → **401**, disallowed account → **403** |
| `iap`       | **production today** | identity from the IAP-injected `X-Goog-Authenticated-User-Email` header at the edge | edge already gated; middleware is pass-through |
| `open`      | local dev (`make dev`) | no-op | none |

**Pre-auth (un-gated) prefixes** — must stay reachable so the SPA shell + login can boot and probe: `/api/health`, `/api/me`, `/api/config/firebase` (mirrored on the client in `authedFetch.ts`'s `OPEN_PREFIXES`).

**Access policy (firebase mode):** open self-signup by default (`AUTH_OPEN_SIGNUP=1`); flip to an allow-list with `AUTH_OPEN_SIGNUP=0` + `AUTH_ALLOWED_EMAILS=a@x.com,b@y.com`. One env change, no code edit.

**Status:** Firebase login is live on the staging service. **Production is still on IAP** — GCIP `authorizedDomains` doesn't yet carry the prod domain and prod `AUTH_MODE` hasn't been flipped to `firebase` (intentional until the login + domain are wired).

### Boot sequence (`main.tsx`)

`installAuthFetch()` must run **before** the app renders, so the very first `/api/*` data call already carries the token:

```
main.tsx bootstrap()
  ↓ GET /api/config/firebase            (un-gated; INTERNAL — fail LOUD per Rule 3.7)
  ↓ setRuntimeConfig({ authMode, firebase })
  ↓ if firebase mode: initFirebase(config.firebase)
  ↓ installAuthFetch()                  (global window.fetch monkeypatch)
  ↓ ReactDOM.createRoot(...).render(<App />)
```

`/api/config/firebase` is served by **our own** backend (same origin, same deployment) — it is INTERNAL, so a network error, non-OK status, or unparseable body surfaces an explicit "Could not load application configuration" error screen (`data-testid="config-error"`) instead of silently defaulting to `open` and rendering the full app to an anonymous user.

### Frontend auth modules

| File | Role |
|------|------|
| [`src/lib/runtimeConfig.ts`](platform/src/lib/runtimeConfig.ts) | Holds the boot-fetched `{ authMode, firebase }`; `getAuthMode()` accessor. |
| [`src/lib/firebase.ts`](platform/src/lib/firebase.ts) | Lazy Firebase init, `getIdToken()`, `subscribeAuth()`. |
| [`src/lib/authedFetch.ts`](platform/src/lib/authedFetch.ts) | Global `window.fetch` wrapper. In `firebase` mode, injects `Authorization: Bearer <idToken>` on same-origin gated `/api/*` calls (no-op for iap/open). Merges onto existing headers (preserves `X-Admin-Token`, `Content-Type`). A 401 invokes the registered `setOnUnauthorized` callback. Wraps the one network primitive so every call site — ~60 bare `fetch('/api/...')` across ~30 files — is covered with zero per-file edits. |
| [`src/components/auth/AuthGate.tsx`](platform/src/components/auth/AuthGate.tsx) | Top-level gate. Only `firebase` mode shows a login; iap/open render the app directly. Shows `SignInScreen` when not signed in, a spinner while Firebase auth state loads. |
| [`src/components/auth/SignInScreen.tsx`](platform/src/components/auth/SignInScreen.tsx) | The login UI (firebase mode only). |
| [`src/components/auth/SignOutButton.tsx`](platform/src/components/auth/SignOutButton.tsx) | Sign-out action in the chrome. |
| [`src/hooks/useUser.ts`](platform/src/hooks/useUser.ts) | Single identity hook. firebase mode: tracks Firebase auth state, then reads the **server-verified** `/api/me` (`{ email, is_admin }`) once signed in so `is_admin` can't be spoofed. iap/open: polls `/api/me` directly. Returns `{ email, isAdmin, isSignedIn, isLoading, authMode }`. |

## Directory map

```
platform/
├─ index.html                   # Vite HTML entry (dark mode default)
├─ package.json                 # React 19, Vite, Tailwind v4, HeroUI, Zustand, TanStack Query/Table, lightweight-charts, Recharts, firebase
├─ vite.config.ts               # @ → src alias, proxies /api + /dev to FastAPI :8000
├─ tsconfig.json + tsconfig.{app,node}.json
├─ eslint.config.js
├─ playwright.config.ts         # E2E
├─ Dockerfile                   # multi-stage: node builds dist/, python serves it
├─ cloudbuild.yaml              # Cloud Build for trading-platform image
├─ deploy.sh                    # build + deploy (STAGING=1 for the public staging revision)
├─ screenshot_pages.mjs         # Playwright util for capturing each page
├─ src/
│  ├─ main.tsx                  # boot: fetch /api/config/firebase → init Firebase → installAuthFetch → render
│  ├─ App.tsx                   # QueryClientProvider + AuthGate + RouterProvider (13 routes)
│  ├─ routes/                   # 13 lazy-loaded pages — one per nav item
│  │  ├─ DashboardPage.tsx      # /          — premarket brief, hero ticker, live signals, catalysts, news, Movement Read (flag-OFF)
│  │  ├─ LiveMarketPage.tsx     # /live      — real-time quote + indicator tiles + CALL/PUT voter cards
│  │  ├─ ChartsPage.tsx         # /charts    — candlestick + volume + overlays + Trades|Analytics panel
│  │  ├─ OptionsFlowPage.tsx    # /options   — Heatseeker / Flowseeker / Profiles
│  │  ├─ PlaybookPage.tsx       # /playbook  — strategy cards with live conditions + win-rate
│  │  ├─ ReportsPage.tsx        # /reports   — phase report list + markdown viewer
│  │  ├─ SignalsPage.tsx        # /signals   — sortable signal_alerts table + P&L KPIs
│  │  ├─ JournalPage.tsx        # /journal   — PER-USER trade CRUD + equity curve
│  │  ├─ InsightsPage.tsx       # /insights  — AI report tabs + watchlist + chat
│  │  ├─ CatalystsPage.tsx      # /catalysts — event/earnings/news timeline
│  │  ├─ AdminPage.tsx          # /admin     — model-routing dashboard (admin-gated)
│  │  ├─ HelpPage.tsx           # /help      — glossary + indicator config
│  │  └─ SettingsPage.tsx       # /settings  — theme/nav/density/accent (NEW)
│  ├─ components/
│  │  ├─ auth/                  # AuthGate, SignInScreen, SignOutButton
│  │  ├─ layout/                # AppShell, TopTabs, Sidebar, Header, CommandPalette
│  │  ├─ shared/                # DataTable, MetricCard, Modal, Tabs, DateSelector, LoadingSpinner, RouteErrorBoundary
│  │  ├─ dashboard/             # DataPipelineStatus, MovementRead (flag-gated)
│  │  ├─ insights/              # ReportCards, WatchlistPanel
│  │  ├─ charts/                # CandlestickChart, PriceAreaChart, StrategyConditionsCard, SimilarSetupsCard
│  │  └─ backtest/              # BacktesterSection
│  ├─ hooks/                    # TanStack-Query-backed data hooks + useUser (see hook map)
│  ├─ stores/                   # Zustand client state (5 stores)
│  │  ├─ tickerStore.ts         # activeTicker + availableTickers (IWM/SPY/QQQ)
│  │  ├─ tradeStore.ts          # in-flight trade form state
│  │  ├─ themeStore.ts          # dark/light toggle
│  │  ├─ settingsStore.ts       # navPattern + density + accent (persisted to localStorage)
│  │  └─ reviewDateStore.ts     # as-of review-date selector
│  ├─ lib/                      # pure helpers + auth glue
│  │  ├─ firebase.ts            # Firebase init / token / auth-state subscription
│  │  ├─ authedFetch.ts         # global fetch wrapper (bearer injection)
│  │  ├─ runtimeConfig.ts       # boot-fetched auth config
│  │  ├─ indicators.ts          # client-side indicator math (mirror of lib/indicators.py)
│  │  ├─ playbookEvaluator.ts   # evaluator used before backend round-trip
│  │  ├─ marketSession.ts       # pre/RTH/post-market clock
│  │  ├─ chartTheme.ts          # lightweight-charts + Recharts colors
│  │  ├─ format.ts / time.ts    # formatting + ET-aware date helpers
│  │  └─ *.test.ts              # Vitest unit tests
│  └─ types/                    # Ticker, Insight, Watchlist type defs
└─ tests/                       # Playwright E2E specs
   └─ helpers/                  # shared E2E utilities
```

## Routing model

`App.tsx` wraps the tree in `QueryClientProvider` → `AuthGate` → `RouterProvider`, with a single `createBrowserRouter` **layout route** (`AppShell`) wrapping **13 child routes**. Each child:

- is `React.lazy`-loaded, so the initial bundle is only the shell + the active page;
- is wrapped in a `<Suspense fallback={<PageLoader />}>` for the lazy-load handoff;
- carries its own `errorElement={<RouteErrorBoundary />}` — when a page crashes during render, the boundary catches it, keeps the nav + header rendered, and shows a card with the error + a refresh button. The crash does **not** unmount the chrome.

The 13 routes:

| Path        | Page                 | Purpose | Primary API surface |
|-------------|----------------------|---------|---------------------|
| `/`         | `DashboardPage`      | Premarket brief strip, hero ticker, intraday Candles↔Area toggle, live signals, catalysts, news-sentiment, sector rotation, review-date picker, **Movement Read card (flag-OFF)** | `/api/dashboard/brief/{ticker}`, `/api/playbook/{ticker}`, `/api/signals/{ticker}`, `/api/catalysts/events`, `/api/market/reference`, `/api/movement-statement` |
| `/live`     | `LiveMarketPage`     | Quote tile, 6 indicator tiles (EMA9/20/50, RSI14, StochRSI, ATR14), dual CALL/PUT 5-condition voter cards, session badge, review mode | `/api/live/quote`, `/api/live/indicators`, `/api/live/history`, `/api/live/status` |
| `/charts`   | `ChartsPage`         | Candlestick + volume with overlays (TP1/2/3 + SL, prev-day refs, gamma King/Gate/Flip/Balance, entry/exit markers, 5-cond signals), Trades\|Analytics panel, TF buttons, toggles, JSON/CSV export, Mark-Entry mode | `/api/market/data`, `/api/market/reference-levels`, `/api/options/gamma-levels` |
| `/options`  | `OptionsFlowPage`    | Heatseeker (Swing/Trinity), Flowseeker (Live/Drilldown), Profiles (OI by strike). ⚠️ Heatseeker-Swing + Flowseeker render **MOCK** data; **Profiles is real**. #600 fixed the ~84× GEX inflation | `/api/grid/*`, `/api/options/*` |
| `/playbook` | `PlaybookPage`       | Strategy cards with live conditions, win-rate + avg-return; #613 added real target/stop win-rate via the typed `playbook_cards` table | `/api/playbook`, `/api/playbook-batch`, `/api/live/*` |
| `/reports`  | `ReportsPage`        | Phase report list + markdown viewer (GCS-backed) | `/api/reports/list/{ticker}`, `/api/reports/{ticker}/{phase}` |
| `/signals`  | `SignalsPage`        | Sortable signals table (Time/Dir/Score/Price/RSI/EMA9/Volume), filters, 90-day P&L KPIs | `/api/signals/{ticker}`, `/api/analytics/trade-summary` |
| `/journal`  | `JournalPage`        | **Per-user** trade CRUD + equity curve + CSV export | `/api/journal/trades` |
| `/insights` | `InsightsPage`       | Tabs Briefing/Agents/History/Watchlist/Chat; multi-card AI report; replay-as-of; streaming chat | `/api/insights/*` |
| `/catalysts`| `CatalystsPage`      | Date-grouped events + earnings + news timeline, Hot-Now, filters | `/api/catalysts/events`, `/api/catalysts/types` |
| `/admin`    | `AdminPage`          | Model-routing dashboard, on-demand predict — gated by server-side admin (token / IAP email) | `/api/admin/routes`, `/api/admin/models` |
| `/help`     | `HelpPage`           | ~189-entry searchable glossary + indicator config | `/api/glossary`, `/api/config/indicators` |
| `/settings` | `SettingsPage` (NEW) | Theme (dark/light), nav pattern (top-tabs/sidebar), density, accent swatches — Zustand + localStorage only, **no API** | none |

**Nav & cross-cutting chrome:**
- **Selectable nav pattern.** `AppShell` renders `TopTabs` (HeroUI top-tabs, the product default) or `Sidebar`, chosen by `settingsStore.navPattern`. On narrow viewports `TopTabs` collapses the 13 tabs into a **mobile hamburger** pop-up menu.
- **⌘K / Ctrl-K command palette** (`CommandPalette`) jumps to any page, ticker, or action; wired globally in `AppShell`.
- **As-of review-date mode.** `reviewDateStore` holds a selected historical date; review-aware routes (Dashboard, Live, Charts, Signals, Insights) refetch their data as-of that date instead of "now". The Movement Read card is mounted **only in live (non-review) mode**, behind both that guard and the feature flag.
- `Sidebar`/`TopTabs` filter `/admin` out for non-admin users (server-resolved via `useUser` → `/api/me` → `is_admin`).

## Data flow

Three concentric loops:

1. **Server state — TanStack Query.** All hooks under `src/hooks/use*.ts` use `useQuery`/`useMutation` keyed by `[resource, ...params]`. The `QueryClient` in `App.tsx` sets `staleTime: 5 min` and `retry: 1` — most market data is "fresh enough for 5 minutes," and a single retry catches transient Cloud Run cold-starts without thrashing on real outages.
2. **Client state — Zustand.** Five stores hold UI-only state: active ticker (`tickerStore`), in-flight trade form (`tradeStore`), dark/light (`themeStore`), nav/density/accent (`settingsStore`, persisted to localStorage), as-of date (`reviewDateStore`). No server data leaks into Zustand — that lives in the query cache.
3. **Local computation — `src/lib/*.ts`.** Pure functions: client-side indicator math (`indicators.ts`), market-session clock (`marketSession.ts`), playbook evaluator (`playbookEvaluator.ts`). These mirror the backend `lib/*.py` modules so charts and pre-evaluation render without a round-trip. **Tested with Vitest** (`*.test.ts` files alongside).

### Hook → endpoint map

| Hook                       | Endpoint(s) hit                                            | Reads                                |
|----------------------------|------------------------------------------------------------|--------------------------------------|
| `useUser`                  | `/api/me`                                                  | Identity + admin flag (verified)     |
| `useTickerSearch`          | (client-side filter over `availableTickers`)               | Zustand `tickerStore`                |
| `useLiveQuote`             | `/api/live/quote`                                          | Latest 1-min bar                     |
| `useLiveIndicators`        | `/api/live/indicators`                                     | Wilder RSI/EMA/ATR/StochRSI          |
| `useLiveHistory`           | `/api/live/history`                                        | Intraday history window              |
| `useLiveStatus`            | `/api/live/status`                                         | Market session + fetcher freshness   |
| `useReviewQuote`           | `/api/live/*` (as-of review date)                          | Historical-review quote/indicators   |
| `useMarketData`            | `/api/market/data`, `/dates`, `/reference`                 | Daily/intraday OHLCV for chart       |
| `useGammaLevels`           | `/api/options/gamma-levels`                                | King/Gate/Spot/Flip                  |
| `useGammaGlossary`         | `/api/glossary` (gamma terms)                              | Gamma taxonomy labels                |
| `useOptionsGreeks`         | `/api/options/greeks`, `/api/grid/*`                       | Dealer GEX/DEX, BSM Greeks           |
| `usePlaybookEvaluation`    | `/api/playbook`, `/api/playbook-batch`                     | trigger/target/stop, win-rate        |
| `useInsights`              | `/api/insights/report/{ticker}`, `/refresh`, `/history`    | AI insight reports                   |
| `useWatchlist`             | `/api/insights/watchlist`                                  | Watchlist CRUD                       |
| `useMovementStatement`     | `/api/movement-statement`                                  | Structure-continuation read (flag)   |
| `useSimilarSetups`         | `/api/signals/{ticker}/similar`                            | Historical near-neighbours           |
| `useTradeAnalytics`        | `/api/analytics/summary`, `/trade-stats`                   | Per-ticker analytics                 |
| `useAdmin`                 | `/api/admin/models`, `/api/admin/routes/{role}`            | Model routing, RBAC                  |
| `useConfig`                | `/api/config/indicators`, `/api/config/market-hours`       | Server-resolved config               |

All ticker-scoped hooks read `useTickerStore().activeTicker` (or a per-page override) and key the query on it, so flipping the nav ticker switcher refetches every ticker-scoped query in one move.

## API routers (17)

All under [`platform/api/routers/`](platform/api/routers/), imported by `main.py` and served on the same port as the SPA. Every router uses **Pydantic request models** — a shape mismatch returns **422**, not a silent coercion. Missing data is rendered as `null` / "—" with a "data unavailable" badge, never a fabricated `0` (CLAUDE.md Rule 3.7).

| Router | Surface | Notes |
|--------|---------|-------|
| `live`      | `/api/live/*` | Quote, indicators, history, status |
| `dashboard` | `/api/dashboard/*`, `/api/movement-statement` | Brief assembler; `/api/movement-statement` is **flag-gated** (`MOVEMENT_STATEMENT_ENABLED`, default OFF → 503/unavailable; ticker ∈ {IWM,SPY,QQQ}, tf ∈ {5m,15m}) |
| `playbook`  | `/api/playbook`, `/api/playbook-batch` | Live-evaluated strategy cards |
| `signals`   | `/api/signals/*` | signal_alerts + similar-setups |
| `options`   | `/api/options/*` | Greeks, gamma-levels (real `etf_options_snapshots` / `etf_options_daily_greeks`) |
| `grid`      | `/api/grid/*` | **Mounted before `options`** so its routes win; backs Heatseeker/Flowseeker |
| `insights`  | `/api/insights/*` | AI reports, history, watchlist, chat |
| `journal`   | `/api/journal/*` | **Per-user** trade CRUD |
| `admin`     | `/api/admin/*` | Model routing — gated by `X-Admin-Token` / IAP email |
| `catalysts` | `/api/catalysts/*` | Events, earnings, news timeline |
| `backtest`  | `/api/backtest/*` | Backtest reads |
| `analytics` | `/api/analytics/*` | Trade summary / stats |
| `config`    | `/api/config/{firebase,indicators,market-hours}` | **`firebase` is the un-gated boot endpoint**; indicators/market-hours mirror `lib/config.py` |
| `health`    | `/api/health` (+`/freshness`) | Liveness + pipeline freshness (un-gated) |
| `glossary`  | `/api/glossary` | ~189-entry glossary |
| `magnitude` (NEW) | `/api/magnitude/predictions` | Per-bar magnitude-engine predictions (productionized via the `magnitude-inference` Cloud Run Job) |
| `earnings`  (NEW) | `/api/earnings/*` | Earnings calendar / outcomes / lean, backed by the earnings mat-views |

## Refresh semantics — AI insights write path

Most pages are read-only. The two write paths are journal CRUD (`journal_entries`) and the **insights refresh button**, which closes a loop through Cloud Tasks:

```
Browser (InsightsPage / ReportCards)
  ↓ POST /api/insights/report/{ticker}/refresh
FastAPI router (platform/api/routers/insights.py)
  ↓ enqueue task on insight-pipeline-queue (Cloud Tasks)
  ↓ task targets the insight-pipeline Cloud Run Job
Cloud Tasks delivers → insight-pipeline Job runs
  ↓ writes one row to insight_reports + insight_runs in Cloud SQL
Browser re-polls /api/insights/report/{ticker} via TanStack Query refetch
  ↓ new row appears
```

## Per-user data

| Surface | State | Detail |
|---------|-------|--------|
| **Journal** | ✅ shipped (#626) | `journal_entries.user_email`; `_journal_owner(request) = current_user_email() or "local"`; index `(user_email, ticker, entry_ts DESC)`. Fail-closed **503** if a prod owner is required but Cloud SQL is unreachable. |
| **Watchlist** | ⚠️ endpoint-wired, pipeline still shared | The `insights` router now threads `_watchlist_owner(request) = current_user_email() or "default"` into add/remove/load (#635), backed by `watchlists.user_id`. **But the insights generation pipeline still reads the shared `insight_reports` / default watchlist** — so the AI report itself is not yet per-user. **Documented residual gap.** |

## Build pipeline

### Local dev

```bash
cd platform && npm install         # one-time
npm run dev                        # vite on :5173, proxies /api + /dev → :8000
# In another terminal:
make dev                           # FastAPI on :8000 (from repo root)
```

`vite.config.ts` proxies `/api/*` and `/dev/*` to `localhost:8000`, so the browser only talks to `:5173`. In dev, `make dev` serves `{ authMode: 'open' }` from `/api/config/firebase`, so `AuthGate` renders the app directly (open mode reached via a real server response, never a swallowed failure). Hot-module reload works for `.tsx`/`.css`; FastAPI auto-reloads via `uvicorn --reload`.

### Production build

```bash
npm run build                       # tsc -b && vite build → platform/dist/
```

`tsc -b` runs project-references compilation (`tsconfig.app.json` + `tsconfig.node.json`) — type-checks the whole app before bundling. `vite build` produces tree-shaken, code-split chunks (each lazy route is its own chunk) into `platform/dist/`.

### Docker image — one port, one process

[`platform/Dockerfile`](platform/Dockerfile) is multi-stage:

1. **`frontend` stage** (node) — runs `npm ci` + `npm run build`, outputs `platform/dist/`.
2. **`runtime` stage** (python) — installs FastAPI deps, copies `lib/` + `gcp/` + `platform/api/`, then copies the built `dist/` so the **same Python process serves the SPA + `/api/*`**. `main.py` mounts `dist/` as `StaticFiles` at `/`, so any non-`/api` path returns the SPA shell (which then boots, fetches `/api/config/firebase`, and renders).

This means **one Cloud Run service, one port, one TLS cert** — no separate CDN, no separate static host. Cold-start budget is dominated by the Python import graph (`lib/`, `gcp/database.py` Cloud-SQL connector), not the pre-built frontend assets.

### Cloud Run deploy — staging → production

`platform/deploy.sh` drives both modes (the platform-deploy GHA workflows were retired in the 2026-05-30 GHA→Cloud-Run migration):

| Mode | Cmd | Behaviour |
|------|-----|-----------|
| Production | `./platform/deploy.sh` | builds image, deploys `trading-platform` (IAP-gated, `AUTH_MODE=iap`) |
| Staging | `STAGING=1 ./platform/deploy.sh` | builds image, deploys the public `trading-platform-staging` service (no IAP, `AUTH_MODE=firebase`) for the in-app-login surface |

## Testing

- **Unit (`npm test` → Vitest):** pure helpers in `src/lib/*.ts` and a few component-source invariants have co-located `*.test.ts(x)`. Covers `playbookEvaluator`, `strategySignals`, `strategySignalsForSeries`, `marketSession`, `useReviewQuote`, and a source-level guard test (`MovementRead.test.tsx`) asserting `<MovementRead>` is only mounted behind the review-mode guard.
- **Component:** thin — Vitest is configured for `@testing-library/react` but the component suite is mostly source-invariant tests, not rendered-DOM tests. Filed as a coverage gap.
- **E2E (`npm run e2e` → Playwright):** `tests/*.spec.ts` runs the full app under `chromium`. Profiles: `chromium` (local dev against `npm run dev`, open mode) and `cloud` (against the production Cloud Run URL behind IAP — requires a one-time IAP cookie capture).
- **Lint:** `npm run lint` → ESLint 9 with `typescript-eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`.

## Production runtime

- **URL:** `https://stocks.insightscollective.org` (Cloud Run domain mapping, Google-managed TLS).
- **Auth:** **IAP** today (`AUTH_MODE=iap`). The browser handshakes with Google's IAP IdP; IAP injects `X-Goog-Authenticated-User-Email`; `/api/me` returns `{ email, is_admin }`; `useUser` reads it and gates `/admin`. The `firebase` mode (in-app login) is live on the **staging** service and is the path production will move to once GCIP authorized domains + the prod `AUTH_MODE` flip land.
- **Cloud Run config:** `min-instances=1` (avoids cold-start blowing Discord's 3-sec interaction-ack budget when the same image is invoked for back-channel work), `--no-cpu-throttling` (FastAPI BackgroundTasks need full CPU after the response is sent), 1 vCPU / 1 GiB.
- **Logging:** stdout → Cloud Logging. The failure-notifier sink filters `resource.type=cloud_run_job`, so it does **not** cover this service — service errors don't auto-create GitHub issues.

## Known limitations

- **Watchlist insights pipeline not per-user** (above) — endpoints scope by user, the report generator doesn't.
- **Options Flow Heatseeker-Swing + Flowseeker render mock data** — primary roadmap target; Profiles is real.
- **No service worker / offline mode.** A reload during a network hiccup shows the browser's network-error page.
- **No code-coverage gate in CI.** Vitest runs but coverage isn't enforced.
- **Thin component-test layer.** Mostly pure-helper + source-invariant tests; `@testing-library/react` is under-used.
- **No Storybook / design-system doc** — Tailwind v4 + custom-token + accent-swatch story is documented only by usage.
- **No Cloud Logging alert policy** for the `trading-platform` service (5xx rate, p95 latency) — open todo.

## Open work

1. **Thread `current_user_email(request)` into the insights watchlist generation pipeline** so AI reports become per-user (mirrors the journal pattern; endpoints already scope, the pipeline doesn't).
2. **Flip production to Firebase** — add the prod domain to GCIP `authorizedDomains`, set prod `AUTH_MODE=firebase`, retire IAP.
3. **Component test bed** — render-level tests for `DataTable`, `MetricCard`, nav route gating, `RouteErrorBoundary`, `AuthGate`.
4. **Coverage gate** — wire Vitest `--coverage` into the staging-deploy path as an advisory check.
5. **Cloud Logging alert policy** for the `trading-platform` service.
