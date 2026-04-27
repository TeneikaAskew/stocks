# Trading Application — Briefing Deck

**Compiled:** 2026-04-26 (refreshed post-PR-#99)
**Scope:** Full-system reference covering architecture, data pipeline, infrastructure, plans executed, and operational runbook.
**Audience:** Engineers, stakeholders, and future maintainers.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System At A Glance](#2-system-at-a-glance)
3. [Application Surfaces](#3-application-surfaces)
4. [The Platform (Unified Dashboard)](#4-the-platform-unified-dashboard)
5. [Python Trading Engine (`lib/`)](#5-python-trading-engine-lib)
6. [Data Pipeline & Storage](#6-data-pipeline--storage)
7. [GCP Infrastructure](#7-gcp-infrastructure)
8. [GitHub Actions / CI](#8-github-actions--ci)
9. [Standalone Web Tools](#9-standalone-web-tools)
10. [Google Apps Script](#10-google-apps-script)
11. [AI / Multi-Agent Pipeline](#11-ai--multi-agent-pipeline)
12. [Strategy & Methodology](#12-strategy--methodology)
13. [Testing Strategy](#13-testing-strategy)
14. [Plans Executed (Apr 10–26, 2026)](#14-plans-executed-apr-1026-2026)
15. [Recent Activity (Changelogs & Commits)](#15-recent-activity-changelogs--commits)
16. [Outstanding Work & Known Gaps](#16-outstanding-work--known-gaps)
17. [Operations Runbook](#17-operations-runbook)
18. [Conventions & Glossary](#18-conventions--glossary)

---

## 1. Executive Summary

A full-stack equity trading research and execution platform centered on four primary tickers — **IWM, SPY, QQQ, SPX** — with a curated watchlist extension (e.g. AVGO). The system ingests market data from AlphaVantage and supporting providers, persists to Cloud SQL + GCS, computes 195+ technical features, generates entry signals via a 3-of-5 voter augmented by Strat candle classification and Full Timeframe Continuity (FTFC), backtests with walk-forward validation, and surfaces everything through a unified React + FastAPI dashboard. A multi-agent AI pipeline (analysts → debate → trader/risk/portfolio manager) writes a daily structured insight per ticker, persisted in Cloud SQL and viewable on the `/insights` route.

**At a glance:**

| Metric | Value |
| --- | --- |
| Frontend routes | 12 (Dashboard, Live, Charts, Options, Playbook, Backtest-in-Charts, Reports, Signals, Journal, Insights, Catalysts, Admin, Help) |
| FastAPI routers | 14 (live, options, playbook, backtest, signals, insights, journal, dashboard, catalysts, admin, **analytics**, **config**, **health**, plus `__init__`) |
| Python `lib/` modules | 12 (+ `lib/agents/` package with 11 modules + `ranker/` subpackage). Adds `lib/gamma.py` — canonical Greeks/GEX/VEX/King-Gate-Spot-Flip math |
| GCP fetchers | 11 (composition shifted: `fetch_etf_options.py` deleted, `fetch_fred_rates.py` added) |
| Cloud SQL tables | 31 (adds `daily_rates` for FRED-driven historical Greeks; `ticker_info` for AV/FinViz metadata cache; `earnings_calendar` now 47–48 cols incl. UW liquidity) |
| Cloud Run jobs | 17 (15 scheduled + `apply-schema-migrations` one-shot + `compute-spx-greeks-backfill` on-demand) |
| GitHub Actions workflows | 14 (composition: `fetch_etf_options.yml` removed, `freshness-watchdog.yml` added) |
| Standalone web tools | 4 (heatseeker, success-report, chart-viewer, website) |
| Google Apps Script files | 33 |
| Test files | ~35 Python (`make test` ~703 tests after PR #94's +251), 34+ E2E specs (includes `admin-auth.spec.ts` — 13 IAP auth tests), 18 script regression |
| Plans logged Apr 10–26 | 17 (13 ✅ shipped, 3 🟡 partial, 1 📋 investigation) |
| Production URL | `trading-platform-5sjtb3yl7a-ue.a.run.app` (Cloud Run + IAP SSO, bictech.org) |

**Key architectural achievements (Apr 2026):**
- **Canonical gamma/Greeks math server-side** (`lib/gamma.py` ~568 lines + `lib/options_greeks.py` ~470-line BSM IV solver). Client-side `greeksCalculator.ts` and `nodeAnalyzer.ts` deleted. New endpoints `POST /api/options/greeks` and `GET /api/options/{ticker}/{date}/levels` drive heatmap + King/Gate/Spot/Flip taxonomy.
- **FRED daily-rates pipeline** (`daily_rates` table + `fetch_fred_rates.py` Cloud Run Job) feeds historical BSM Greeks with time-varying risk-free + dividend yield instead of constants.
- **7 Claude Code reliability agents** (debug-local, impact-analyzer, infra-drift-detector, pre-deploy-check, security-scan, test-coverage-analyzer, trading-logic-reviewer) plus 100-point audit-review scorecard.
- Server-side math enforcement (Python ↔ TypeScript drift eliminated for Greeks, indicators, playbook conditions).
- Multi-provider LLM client (Vertex / Anthropic / OpenAI) with per-role routing in `model_routing` table; gamma analyst now part of the pipeline.
- Cloud Run deployment with IAP-managed Google SSO; production `/dev` diagnostic endpoint.
- Comprehensive freshness watchdog (`scripts/audit_data_freshness.py` + `freshness-watchdog.yml` + `/api/health/freshness` + Dashboard `DataPipelineStatus` widget).
- Cloud Run job failure notifier (Pub/Sub → Discord + GitHub issue) — `gcp/failure_notifier.py` + `FAILURE_NOTIFIER_DEPLOYMENT.md` runbook.
- Historical Review Mode (global DateSelector with trading-day snapping, `end_date`/`end_time` API params).
- Catalyst-analog matching backtest (replaces empty-trades backtest for thin-data tickers).
- Phase 3 deterministic ticker ranker (insider buying vs selling split, news-topic match, watchlist scoping).
- **Ticker metadata system** (`lib/ticker_info.py` ~454 lines). Unified access to company info, peers, news from AlphaVantage (SYMBOL_SEARCH, OVERVIEW, GLOBAL_QUOTE) and FinViz. Cloud SQL `ticker_info` table cache + local JSON fallback. Drives the Watchlist "Add Ticker" search flow via 5 new endpoints on the insights router and `useTickerSearch` hook.
- **Admin IAP email bypass** (PR #98). The admin email (`teneika@bictech.org`) authenticates via IAP header without entering a token. New `/api/me` endpoint, `useUser` hook, conditional Admin sidebar link. Token-based auth preserved as fallback.
- **RSS news feed classifier** (`scripts/probe_news_feeds.py`). Probes 19 candidate RSS feeds (Seeking Alpha, Yahoo, CNBC, MarketWatch, Investing.com, NASDAQ) and classifies them as `PER_TICKER` vs `GENERAL` with metadata extraction (cashtags, pub dates, category elements). Investigation tool for future news integration.
- **Deterministic per-persona trade planner** (`lib/agents/trade_planner.py`). Replaced LLM-generated entry/stop/targets/sizing with explicit math recipes: aggressive (2× ATR stop, 2R/3.5R/5R targets), neutral (1× ATR), conservative (structural stop, 0.5× sizing). Same inputs now produce byte-identical plans.
- Historical signals migrated from GCS parquet to Cloud SQL `historical_signals` table; bulk insert ~130× faster via multi-row VALUES; new `/api/signals/{ticker}/similar` endpoint backs the Charts "Similar Setups" card.
- Earnings ticker fan-out capped at top-25 by tier + market cap in both the daily fetcher and the premarket brief, fixing a silent ~2-week stale-bars regression on IWM/SPY/QQQ caused by AV rate-limit budget exhaustion. UW liquidity columns (SP500 flag, stock/options volume, open interest, realized vol, past reactions) now flow into `earnings_calendar` and drive the within-tier sort.

---

## 2. System At A Glance

### Architecture diagram

```
                    ┌────────────────────────────────────────┐
                    │  External Sources                      │
                    │  AlphaVantage  Yahoo  FRED  Benzinga   │
                    │  SEC Edgar     Form 4  AV News         │
                    │  Unusual Whales  Earnings Whispers     │
                    │  ForexFactory                          │
                    └──────────────────┬─────────────────────┘
                                       │
                                       ▼
                    ┌────────────────────────────────────────┐
                    │  GCP Fetchers (gcp/fetchers/)          │
                    │  Run as Cloud Run Jobs on Scheduler    │
                    │  + GH Actions workflows (legacy)       │
                    └──────────┬─────────────────────────┬───┘
                               │                         │
                               ▼                         ▼
                    ┌─────────────────────┐   ┌────────────────────┐
                    │ Cloud SQL           │   │ Google Cloud       │
                    │ (PostgreSQL 15)     │   │ Storage (GCS)      │
                    │ 31 tables           │   │ raw/data/*.parquet │
                    └──────────┬──────────┘   └─────────┬──────────┘
                               │                         │
                               └─────────────┬───────────┘
                                             ▼
                    ┌────────────────────────────────────────┐
                    │  FastAPI Backend (platform/api/)       │
                    │  10 routers, TTL caching               │
                    │  uvicorn — port 8000 (dev) /           │
                    │  Cloud Run (prod, behind IAP)          │
                    └──────────────────┬─────────────────────┘
                                       │ /api/*
                                       ▼
                    ┌────────────────────────────────────────┐
                    │  React 19 + Vite 7 + TS Frontend       │
                    │  12 routes, TanStack Query             │
                    │  Vite dev — port 5173 → /api proxy     │
                    │  Prod — StaticFiles served by FastAPI  │
                    └────────────────────────────────────────┘

                    ┌────────────────────────────────────────┐
                    │ Sidecar systems (off the main path):   │
                    │  • lib/agents/   — multi-agent AI      │
                    │  • Cloud Run notifier — failure alerts │
                    │  • GAS spreadsheet automation          │
                    │  • 4 standalone web tools              │
                    │  • TradingView Pine Scripts            │
                    └────────────────────────────────────────┘
```

### Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19, Vite 7, TypeScript 5, Tailwind CSS 4, TanStack Query, Recharts, lucide-react icons |
| Backend (API) | FastAPI, Uvicorn, Pydantic, Python 3.11 |
| Trading engine | pandas, NumPy, py_vollib_vectorized (BSM Greeks), pandas_market_calendars |
| Database | PostgreSQL 15 (Cloud SQL `db-g1-small`) |
| Object storage | Google Cloud Storage |
| Compute (jobs) | Cloud Run Jobs + Cloud Scheduler (cron) |
| Compute (web) | Cloud Run Service (auto-managed IAP SSO) |
| Secrets | Google Secret Manager (.env locally) |
| LLMs | Vertex AI Gemini, Anthropic Claude, OpenAI (per-role routing) |
| CI/CD | GitHub Actions (14 workflows + shared failure handler) |
| Spreadsheet automation | Google Apps Script (33 .js files) |
| Charting (mobile/Pine) | TradingView Pine Script v6 |
| Testing | pytest (unit/integration), Playwright (E2E), Vitest (frontend unit) |

### Data flow (canonical request)

1. Cloud Scheduler fires a Cloud Run Job (e.g. `fetch-market-data`).
2. Fetcher pulls from AlphaVantage, computes derived fields (indicators, VWAP, Strat fields), and writes to Cloud SQL via `gcp/database.py`. Parquet copy lands in GCS.
3. User opens `/dashboard` in the browser. React fetches `/api/dashboard/brief/{ticker}` via TanStack Query.
4. `dashboard.py` router reads from Cloud SQL, applies the live overlay (synthetic today-bar built from AV live quote during market hours), recomputes RSI/EMA/SMA from `lib.indicators`, and returns JSON with a `live` block and trading-day-aware `stale_days`.
5. React renders the Daily Bias card. During market hours, the brief refetches every 15 s; otherwise on a longer interval.

---

## 3. Application Surfaces

The application has **five distinct surfaces**, all rooted in the same git repo. The Platform is primary; everything else is sidecar or legacy.

| Surface | Path | Primary use | Status |
| --- | --- | --- | --- |
| **Platform** (React + FastAPI) | `platform/` | Day-to-day research, live trading, journaling, AI insights | Primary, active |
| **Standalone web tools** | `options-heatseeker/`, `success-report-site/`, `chart-viewer/`, `website/` | Specialized exploratory views (heatmaps, reports, raw charts) | Active, some legacy |
| **Google Apps Script** | `google-apps-script/` | Spreadsheet-based trade tracking, options premium backfill, web app | Legacy, in maintenance |
| **TradingView Pine Scripts** | `tradingview-pine-scripts/` | Mobile and TV-native indicators (v6 API) | Active (no .pine in git currently — see §16) |
| **Earnings options analytics** | `earnings_options_analytics/` | Standalone earnings strategy backtester | Maintained, separate from platform |

The Platform is the source of truth for live trading workflows. The standalone tools predate the unified dashboard; some are still actively used (heatseeker for IV surface) and others are in maintenance mode (chart-viewer, website).

---

## 4. The Platform (Unified Dashboard)

### 4.1 Frontend routes (12)

Files in `platform/src/routes/`. The route table is wired in `platform/src/App.tsx`. All routes share the AppShell layout (header + sidebar + main).

| Route | File | Purpose |
| --- | --- | --- |
| `/` | `DashboardPage.tsx` | Daily Bias card with live overlay, top setup, KPIs (RSI, ATR, RVOL), best/worst trades, AI insight summary, watchlist mini-table |
| `/live` | `LiveMarketPage.tsx` | Real-time quote, ORB levels, mid-day chart, signal pill, candlestick mapper |
| `/charts` | `ChartsPage.tsx` | Multi-timeframe charts, indicator overlays, **embedded Backtester section**, live strategy conditions card |
| `/options` | `OptionsFlowPage.tsx` | Options chains with Greeks (AV-sourced), IV heatmap, dates picker, strike filter |
| `/playbook` | `PlaybookPage.tsx` | Strategy condition cards (12 per ticker), live evaluation against snapshot |
| `/reports` | `ReportsPage.tsx` | Phase-grouped reports (premarket, midday, weekly review) with filenames + path metadata |
| `/signals` | `SignalsPage.tsx` | Historical signal alerts table, date-range filtering, review-mode aware (`dateTo` overridden by review date) |
| `/journal` | `JournalPage.tsx` | CRUD trade journal: notes, P&L, tags. Cloud SQL primary, local JSON fallback |
| `/insights` | `InsightsPage.tsx` | Multi-agent analyst report (DirectionCard, TradePlanCard, DebateCard, persona plans), Watchlist tab with deterministic ranker, refresh trigger |
| `/catalysts` | `CatalystsPage.tsx` | Unified actionable feed: news + 8-K filings + economic events + earnings + insider transactions, date-range picker, point-in-time snapshots |
| `/admin` | `AdminPage.tsx` | Model routing dashboard (provider/version per analyst role), gated to ADMIN_TOKEN |
| `/help` | `HelpPage.tsx` | User docs, feature guides, keyboard shortcuts |

The standalone `/backtest` route was **merged into Charts** as a Backtester section (per `crystalline-puzzling-clock` plan).

### 4.2 Frontend libs and components

#### `platform/src/lib/`

| File | Role |
| --- | --- |
| `chartTheme.ts` | Recharts theme: colors, fonts, responsive sizing |
| `indicators.ts` | Frontend indicator helpers (EMA, RSI, MACD, Stochastic, BB) for chart overlays + per-bar voter `computeStrategySignalsForSeries()`. Canonical math lives server-side |
| `marketSession.ts` | Premarket/regular/after-hours classification with holiday calendar (`MARKET_HOLIDAYS_2026`) — paired with `marketSession.test.ts` |
| `time.ts` | Timezone + 12 h time formatting (`formatEasternTime12h`, etc.) |
| `playbookEvaluator.ts` | Thin client-side wrapper exposing `buildSnapshot` reused on Dashboard. Condition-eval math moved to `POST /api/playbook/evaluate` (PR #81 / plan #4) |
| `strategySignals.ts` | CALL/PUT scoring + strength labeling — paired with `strategySignals.test.ts` |

**Removed in plan #4 closure (PR #81):** `greeksCalculator.ts` and `nodeAnalyzer.ts` were both deleted — their math lives in `lib/gamma.py` server-side, accessed via `POST /api/options/greeks` and `GET /api/options/{ticker}/{date_str}/levels`.

#### `platform/src/components/`

- `layout/` — `AppShell.tsx`, `Header.tsx` (with global DateSelector for review mode), `Sidebar.tsx`
- `shared/` — `Tabs`, `Modal`, `DateSelector`, `LoadingSpinner`, `MetricCard`, `DataTable`, `RouteErrorBoundary`, `DataPipelineStatus` (freshness widget — PR #85)
- `charts/` — `PriceAreaChart`, `CandlestickChart`, `StrategyConditionsCard`, `SimilarSetupsCard`
- `backtest/` — `BacktesterSection` (extracted from the old standalone BacktestPage)
- `insights/` — `WatchlistPanel`, `ReportCards`, persona plan tables

#### Frontend stores & hooks

- `stores/marketStore.ts` — minimal Zustand store; `isMarketOpen`/`setMarketOpen` removed in `velvety-booping-kazoo` (those fields were never written to)
- `stores/reviewDateStore.ts` — global review-mode date/time, consumed by Dashboard, Charts, Signals
- `hooks/useLiveStatus.ts` — shared TanStack Query hook for `/api/live/status`. Single cache entry across Header + Dashboard + Live pages
- `hooks/useGammaLevels.ts` — fetches `GET /api/options/{ticker}/{date_str}/levels` (PR #81). Replaced client-side `nodeAnalyzer.ts` aggregation
- `hooks/useOptionsGreeks.ts` — POSTs to `/api/options/greeks` (PR #86)
- `hooks/useConfig.ts` — fetches `/api/config/indicators` and `/api/config/market-hours` (closes BRIEFING §16.2 drift)
- `hooks/useLiveIndicators.ts` — server-computed intraday indicators
- `hooks/useSimilarSetups.ts` — fetches `/api/signals/{ticker}/similar` for the Charts page Similar Setups card (PR #80)
- `hooks/useTickerSearch.ts` — debounced AV SYMBOL_SEARCH autocomplete (8 results), `useAddToWatchlist()` / `useRemoveFromWatchlist()` mutations. Drives the WatchlistPanel "Add Ticker" search flow (PR #98)
- `hooks/useUser.ts` — fetches `/api/me` for IAP-authenticated email; exposes `{ email, isAdmin, isLoading }`. Used by Sidebar (conditional Admin link) and AdminPage (token gate bypass) (PR #98)

### 4.3 FastAPI routers and endpoints

Files in `platform/api/routers/`. The 13 active routers (+ `__init__.py`):

| Router | File | Key endpoints | Notes |
| --- | --- | --- | --- |
| Live quote | `live.py` | `GET /api/quote/{ticker}`, `GET /api/live/status`, `POST /api/live/indicators` | Live AV quote, ORB levels (5 m/15 m), market session detection, server-computed indicators |
| Options | `options.py` | `GET /api/options/dates/{ticker}`, `GET /api/options/{ticker}/{date_str}`, **`POST /api/options/greeks`**, **`GET /api/options/{ticker}/{date_str}/levels`** | Cloud SQL reader (`data_source='alphavantage'`), 12 h TTL cache. Greeks + levels endpoints (PR #81) drive the heatmap and King/Gate/Spot/Flip taxonomy via `lib/gamma.py` |
| Playbook | `playbook.py` | `GET /api/playbook/eval`, `POST /api/playbook/evaluate` | Server-side condition evaluation against live/historical |
| Backtest | `backtest.py` | `GET /api/backtest/results/{ticker}`, `GET /api/backtest/all/{ticker}` | Reads CSVs from GCS with TTL cache. Returns `runs[]`, `win_rate` (0-1), `avg_return_pct` |
| Signals | `signals.py` | `GET /api/signals/{ticker}`, `GET /api/signals/{ticker}/similar`, params: `end_date`, `end_time`, `direction`, `min_score` | Cloud SQL `historical_signals` reader (legacy parquet fallback). `/similar` returns prior bars in same direction + score + RSI bucket (PR #80) |
| Insights | `insights.py` | `GET /api/insights/{ticker}`, `POST /api/insights/refresh/{ticker}`, `GET /api/insights/runs/...`, **`GET /api/insights/ticker/search`**, **`GET .../ticker/{t}/info`**, **`GET .../ticker/{t}/quote`**, **`POST .../watchlist/add`**, **`DELETE .../watchlist/{t}`** | Cached agent reports (Cloud SQL `insight_reports`), refresh trigger queues a Cloud Run Job. Ticker search/info/quote endpoints back the WatchlistPanel "Add Ticker" flow via `lib/ticker_info` (PR #98) |
| Journal | `journal.py` | `GET/POST/PATCH/DELETE /api/journal/{ticker}`, `GET /api/journal/{ticker}/{id}` | Cloud SQL `journal_entries` (UUID PK) primary; local JSON fallback for offline/dev |
| Dashboard | `dashboard.py` | `GET /api/dashboard/brief/{ticker}` | Live overlay applied during market hours; trading-day stale calculation; `live: { price, session, updated_at, source }` block |
| Catalysts | `catalysts.py` | `GET /api/catalysts/{ticker}`, `GET /api/catalysts/snapshot/{ticker}?as_of=...` | Unified feed: news, 8-K, insider, economic events, earnings; point-in-time snapshots |
| Admin | `admin.py` | `GET/PUT /api/admin/routes`, `GET /api/admin/models`, **`GET /api/me`** (on `main.py`) | Model provider/version per role. **IAP email bypass** (PR #98): admin email (`teneika@bictech.org`) authenticated via `X-Goog-Authenticated-User-Email` header skips the token gate. `/api/me` returns the current user's email. Token-based `X-Admin-Token` auth preserved as fallback |
| **Analytics** | `analytics.py` | `GET /api/analytics/summary/{ticker}`, `POST /api/analytics/trade-stats` | Server-side trade analytics aggregation (PR #92). Replaces frontend `useTradeAnalytics` math |
| **Config** | `config.py` | `GET /api/config/indicators`, `GET /api/config/market-hours` | Single source of truth for thresholds + market hours. Closes BRIEFING §16.2 plan #4 drift |
| **Health** | `health.py` | `GET /api/health/freshness`, `GET /api/health` | Per-source last-synced timestamps. Backs the Dashboard `DataPipelineStatus` widget + the `freshness-watchdog.yml` workflow (PR #85) |

### 4.4 Build & dev workflow

```bash
# Frontend (port 5173)
cd platform && npm install && npm run dev

# Backend (port 8000) — must source .env first
set -a && source ../.env && set +a
cd platform && uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Or, single command via repo Makefile:
make dev

# Type check
cd platform && npx tsc --noEmit

# Frontend tests (Vitest)
cd platform && npm test

# E2E (local, port 5173+8000)
cd platform && npm run e2e
```

Vite proxies `/api/*` to `:8000`. CORS allows `*.app.github.dev` for Codespace. `vite.config.ts` uses `defineConfig` from `vitest/config` so the `test` field is recognized by `tsc -b`.

### 4.5 Production deployment (Cloud Run + IAP)

Production service: **`trading-platform`** in region `us-east1`. URL: `trading-platform-5sjtb3yl7a-ue.a.run.app`.

**Container build:** multi-stage Dockerfile at `platform/Dockerfile` — Node 20 stage builds the Vite frontend; Python 3.11 stage runs Uvicorn and serves both `/api/*` and the SPA at `/` via FastAPI StaticFiles.

**Build trigger:** `platform/cloudbuild.yaml` (because `gcloud builds submit --tag` only finds Dockerfile at repo root). `.gcloudignore` is anchored so root `/Dockerfile` (Jupyter image) is excluded but `/platform/Dockerfile` flows through. Build context dropped from ~470 MB → ~225 MB after excluding `node_modules/` and `platform/dist/`.

**Cloud SQL connection:** wired via `--add-cloudsql-instances` flag; `gcp/` directory is copied into the runtime image so `gcp/database.py` connector path works.

**Auth:** Auto-managed IAP enabled via `gcloud beta run services update --iap`. Roles granted:
- `roles/iap.httpsResourceAccessor` → `teneika@bictech.org`
- `roles/iap.httpsResourceAccessor` → `playwright-tester` service account (for E2E)

The IAP audience is bictech.org — Google SSO required. Programmatic SA-issued JWT validation is **not possible** under auto-managed IAP because the IAP OAuth Admin API was retired 2026-03-19. Browser-based SSO + Playwright `storageState` is the working path.

**Diagnostic endpoint:** `GET /dev` returns deployed revision, Playwright tester SA email, IAP audience, Cloud SQL status. Gated by `X-Goog-Authenticated-User-Email == teneika@bictech.org`. Local-dev requests (no header) bypass the gate.

**Playwright projects** in `platform/playwright.config.ts`:
- `iap-setup` (headed) — captures Google sign-in cookies via `tests/auth.setup.ts` → `tests/.auth/iap-state.json`
- `cloud` (headless) — reuses cookies against the deployed URL

npm scripts: `e2e`, `e2e:cloud:auth`, `e2e:cloud`.

---

## 5. Python Trading Engine (`lib/`)

Files in `lib/`. Pure-Python, no FastAPI/database imports — testable in isolation.

| Module | Purpose |
| --- | --- |
| `backtest.py` | Event-driven backtester. Sequential bar iteration, risk caps (max trades/day, daily loss limit, concurrent positions), entry signal evaluation, exit rules (time, target, stop, RSI extreme), strat bonus integration |
| `signals.py` | 3-of-5 condition voter for CALL/PUT setups. Conditions: consecutive periods of trend, RSI zone, EMA proximity, Stochastic RSI threshold, MACD confirmation. Optional strat bonus (+0…+3) |
| `indicators.py` | Canonical indicator math. SMA, EMA, RSI (fast/slow), Stochastic RSI, MACD, ATR, Bollinger Bands, VWAP, OBV, RVOL, 20 d / 5 d annualized volatility |
| `strat.py` | FTFC scoring (multi-timeframe alignment); candle pattern classification (1, 2, 2u, 2d, 3); engulfing/doji/inside-bar tagging; combo/setup labeling. PR #81 added Failed_2U / Failed_2D detection + simple 2-bar continuations |
| `walk_forward.py` | Anchored walk-forward validation. Expanding training window + fixed test window; per-fold metric aggregation; stability scoring across folds |
| `data_loader.py` | Unified data loader. Cloud SQL primary; local parquet fallback. Handles `data_source` filtering, resampling rules, missing-data validation. `load_options(data_source=...)`, `get_close_price()` helper (PR #92), `load_data_sources()` helper for tests |
| `config.py` | Typed dataclasses: `IndicatorConfig`, `SignalConfig`, `RiskConfig`, `ExitConfig`, `StratConfig`, `BacktestConfig`, `WalkForwardConfig`, `AlphaVantageConfig(rpm=150)` |
| `insights.py` | Template-driven narrative generation from backtest output. Markdown reports with win rate, Sharpe, drawdown, expectancy |
| **`gamma.py`** | **Canonical Greeks/gamma math (PR #81, ~568 lines).** `aggregate_by_strike`, `gex_by_strike`, `total_vex`, `put_call_ratio`, `estimate_spot` (3-tier: parity → delta-proxy → median-strike), `zero_gamma`, `compute_gamma_flip`, `max_pain`, `implied_move`, `detect_nodes`, `classify_levels`, `build_summary`. `SpotEstimate`, `Level`, `GammaSummary` dataclasses. Single source of truth replacing the deleted `greeksCalculator.ts`/`nodeAnalyzer.ts`. See `docs/gamma_levels.md` |
| `options_greeks.py` | Black-Scholes-Merton Greeks (PR #86, ~470 lines). `py_vollib_vectorized` IV solver from AV mid prices, computes 5 Greeks analytically, writes sidecar `_computed` columns (`delta_computed`, `gamma_computed`, etc.). `get_rate_and_yield()` reads `daily_rates`. `enrich_av_chain_with_greeks()` orchestrator for SPX/NDX/RUT/XSP |
| **`ticker_info.py`** | **Ticker metadata system (PR #98, ~454 lines).** Multi-source: AV SYMBOL_SEARCH (autocomplete), OVERVIEW (company name/sector/industry/market cap/description), GLOBAL_QUOTE (live price/volume); FinViz peers (~10 tickers) + news (~100 headlines). Dual persistence: Cloud SQL `ticker_info` table (30-day TTL) + local `data/ticker_info.json` fallback. Public API: `get_ticker_info()`, `search_tickers()`, `get_quote()`, `get_peers()`, `get_finviz_news()`, `get_aliases()`, `refresh_watchlist_info()` |
| `api_client.py` | HTTP helpers for AlphaVantage, Yahoo, FRED |
| `logging_config.py` | Centralized logging setup for CLI + Cloud Run jobs |

### `lib/agents/` — multi-agent AI pipeline

| File | Role |
| --- | --- |
| `schema.py` | Pydantic models for `InsightReport`, `AnalystReport`, `Debate`, `TradePlan`, `PortfolioRecommendation` |
| `prompts.py` | Per-role prompt templates (analyst, bull, bear, judge, trader, risk, portfolio_manager, sentiment, **gamma**) |
| `summarizers.py` | SQL→narrative summarizers per analyst (market, strat, options, catalyst, sentiment, gamma). Largest file — 38+ KB. `summarize_gamma_levels` reads `lib/gamma.build_summary()` for the gamma analyst (PR #81) |
| `orchestrator.py` | Top-level run: load context → run analysts → debate → judge → trade plan → persist `InsightReport` |
| `llm_client.py` | Provider-agnostic interface (`Adapter` abstract) |
| `vertex_adapter.py` | Vertex AI Gemini implementation |
| `anthropic_adapter.py` | Anthropic Claude implementation |
| `model_routing.py` | Reads `model_routing` Cloud SQL table; resolves `(role, env)` → `(provider, model)` |
| `pricing.py` | Per-provider/model token pricing for cost tracking in reports |
| `embeddings.py` | Vector embeddings for journal entries / similarity search |
| **`trade_planner.py`** | **Deterministic per-persona trade planning (PR #96).** Replaces LLM-generated entry/stop/targets/sizing with explicit math recipes per persona: aggressive (2× ATR stop, 2R/3.5R/5R targets, 1.5× sizing), neutral (1× ATR, 1R/2R/3R, 1.0×), conservative (structural stop via SMA200/swing low, 1R/1.75R, 0.5×, blocks on weak alignment). Same inputs → byte-identical plans. LLM still provides narrative (thesis, bull/bear case, risk flags) |
| `ranker/` | Subpackage — deterministic Phase 3 ticker ranker |

### `lib/agents/ranker/` — deterministic ticker ranker

| File | Role |
| --- | --- |
| `candidates.py` | Pull candidate ticker pool (default: curated watchlist; opt-in: full catalyst universe) |
| `signals.py` | Per-ticker signal extraction (insider buying, insider selling, news topic match, earnings proximity, etc.). Includes `_insider_window()` shared SQL fetch |
| `scoring.py` | `weighted_score()` allows negative weights. `pct_of_max` normalizes via `abs(weight)` so result stays in `[-1, 1]` |
| `rank.py` | Top-level orchestration: candidates → signals → score → sort. Persists audit row to `ranker_runs` |

**Important:** the ranker default is the curated watchlist (IWM, QQQ, SPY, SPX, AVGO). Switching to the full catalyst universe (1871 tickers) causes timeouts. See feedback memory `feedback_ranker_scope.md`.

---

## 6. Data Pipeline & Storage

### 6.1 Data sources

| Source | What it provides | Used by |
| --- | --- | --- |
| **AlphaVantage** | Daily + intraday OHLCV, historical options chains (with Greeks for ETFs), earnings calendar, news sentiment, insider transactions, top movers | Primary market data, primary options data |
| **Yahoo Finance** | Legacy intraday, legacy options (Yahoo data archived; see plan `zippy-forging-bachman`) | Archive only, no new writes |
| **FRED** | DGS3MO (risk-free rate), SP500DIV (dividend yield), economic indicator releases (no times) | SPX Greeks BSM inputs, fallback economic events |
| **Benzinga** | Corporate events, earnings detail | Catalysts feed |
| **SEC EDGAR** | 8-K material event filings, 10-Q/10-K | `sec_filings` table, catalysts feed |
| **Form 4** | Insider transactions (buy/sell, executive, value) | `insider_transactions` table, ranker signal |
| **AV News** | Article-level sentiment scoring with topics | `news_sentiment` table, catalysts feed, ranker |
| **Unusual Whales** | Earnings calendar (fundamentals) | Earnings calendar tier 2/3 |
| **Earnings Whispers** | Earnings calendar with strategy picks (strike, expiration, premium) | Earnings calendar tier 2/3, strategy attachment |
| **ForexFactory** | Economic events with **release times** + forecast/previous values | Primary economic events source (FRED has dates only) |

### 6.2 GCP Fetchers (`gcp/fetchers/`)

| File | Source | Target | Schedule |
| --- | --- | --- | --- |
| `fetch_market_data.py` | AlphaVantage daily + Cloud SQL daily series (for indicators) | `market_data_daily` (OHLCV + 30+ indicators), VWAP from intraday. Earnings-window fan-out **capped at top-25 by `has_options` + `market_cap`** (`MAX_EARNINGS_TICKERS` env, `--max-earnings-tickers` flag) so AV's 150-rpm budget always covers core IWM/SPY/QQQ/SPX | Daily Cloud Run Job |
| `fetch_alphavantage_intraday.py` | AlphaVantage `TIME_SERIES_INTRADAY` 1 min | `market_data_intraday` (partitioned), GCS parquet | Monthly Cloud Run + GH Actions |
| `fetch_av_historical_options.py` | AlphaVantage historical options (back-dated) | `etf_options_snapshots` with `data_source='alphavantage'` | Daily Cloud Run + backfill / catch-up |
| `fetch_earnings_history.py` | AlphaVantage `EARNINGS` | `earnings_history` (quarterly EPS with surprise) | Weekly Cloud Run |
| `fetch_economic_events.py` | ForexFactory + FRED backup | `economic_events` (with release times) | Daily |
| `fetch_fred_rates.py` | FRED `DGS3MO` (3-month Treasury) | `daily_rates` (date PK, dgs3mo, sp500_div_yld, fetched_at). Feeds `lib/options_greeks.get_rate_and_yield()` for historical BSM Greeks (PR #93) | Daily |
| `fetch_news_sentiment.py` | AlphaVantage `NEWS_SENTIMENT` | `news_sentiment` (per-ticker scores, topics, overall sentiment) | Hourly (in-window catalysts) |
| `fetch_sec_filings.py` | SEC EDGAR | `sec_filings` (ticker, cik, form, items array) | Daily |
| `fetch_insider_transactions.py` | AlphaVantage / Form 4 | `insider_transactions` | Daily |
| `fetch_top_movers.py` | AlphaVantage `TOP_GAINERS_LOSERS` | `top_movers_daily` | Daily |
| `_watchlist.py` | (utility) | Shared watchlist loader unioning to ticker pool | (imported by others) |
| `scripts/fetch_earnings_calendar.py` (CLI) | UnusualWhales `upcoming_earnings_v2` + Earnings Whispers + AlphaVantage `EARNINGS_CALENDAR` | `earnings_calendar` (incl. UW liquidity enrichments — `is_s_p_500`, `stock_volume`, `options_volume`, `open_interest`, `rv_1d_last_12q`, `last_1d_reactions`) | Daily Cloud Run via `fetch-earnings-calendar` |

The legacy `gcp/fetchers/fetch_earnings_options.py` was removed (commit `5abfc89`); earnings options now flow through `fetch_av_historical_options.py`. The legacy `gcp/fetchers/fetch_etf_options.py` (intraday yahooquery) was removed in PR #95 (commit `aea5a7c`); historical AV is the sole options writer.

### 6.3 Cloud SQL schema

31 tables total. PostgreSQL 15 on Cloud SQL `db-g1-small` (1.7 GB cache; tier upgrade deferred — see `INFRASTRUCTURE_NOTES.md` at repo root).

| Table | Purpose | Notable columns |
| --- | --- | --- |
| `market_data_daily` | Daily OHLCV + 30+ indicators | `sma_200`, `ema_20`, `macd`/`macd_signal`/`macd_histogram`, `bb_*`, `rsi`, `atr`, `vwap_eod`, `consecutive_up/down`, strat fields |
| `market_data_intraday` | 1 min/5 m/15 m/30 m/1 h OHLCV (LIST-partitioned by ticker) | `interval`, `ts`, OHLCV |
| `market_data_intraday_spy` | Partition |  |
| `market_data_intraday_iwm` | Partition |  |
| `market_data_intraday_qqq` | Partition |  |
| `market_data_intraday_spx` | Partition |  |
| `market_data_intraday_other` | Catch-all partition |  |
| `etf_options_snapshots` | Options chains | `data_source`, `mark`, `bid`/`ask`, Greeks. **Sidecar `_computed` columns** (`delta_computed`, `gamma_computed`, `theta_computed`, `vega_computed`, `rho_computed`, `iv_computed`) for SPX/NDX/RUT/XSP via `lib/options_greeks.enrich_av_chain_with_greeks()` (PR #86) |
| `daily_rates` | FRED daily rates for historical Greeks | `date PK`, `dgs3mo` (3-month Treasury), `sp500_div_yld`, `fetched_at`. Indexed `(date DESC)`. Populated by `fetch_fred_rates.py` (PR #93) |
| `earnings_options_snapshots` | Earnings-week chains (legacy) | (mirrors etf_options_snapshots) |
| `archive_yahoo_market_data_daily` | Yahoo data archive | `LIKE` source INCLUDING ALL |
| `archive_yahoo_market_data_intraday` | Yahoo data archive |  |
| `archive_yahoo_etf_options_snapshots` | Yahoo data archive |  |
| `archive_yahoo_earnings_options_snapshots` | Yahoo data archive |  |
| `earnings_calendar` | Forward earnings + strategy picks | 48 cols incl. tier (AV/UW/EW), strategy, strike, premium, score, hit tracking, **UW liquidity enrichments** (`is_s_p_500`, `stock_volume`, `options_volume`, `open_interest`, `rv_1d_last_12q`, `last_1d_reactions`) |
| `earnings_history` | Backward EPS history | `fiscal_date_ending`, `reported_eps`, `estimated_eps`, `surprise` |
| `sec_filings` | 8-K material events | `cik`, `form`, `filing_date`, `items` array |
| `insider_transactions` | Form 4 buys/sells | `executive`, `transaction_type`, `shares`, `value` |
| `top_movers_daily` | Daily gainers/losers/most-active | `category`, `rank`, `change_pct` |
| `ranker_runs` | Ranker audit trail | `candidate_count`, `weights_used`, `results` JSONB |
| `signal_alerts` | Fired 5-condition signals | `direction`, `base_score`, `strat_bonus`, `conditions_met` |
| `trades` | Executed trades from backtest | `entry_ts`, `exit_ts`, `direction`, `return_pct`, `exit_reason` |
| `journal_entries` | User-authored journal (UUID PK) | `notes`, separate from automated `trades` |
| `premarket_analysis` | Daily premarket setup classification | 32 cols: `rsi`, `strat_daily`, `ftfc_score`, enriched indicators |
| `economic_events` | Economic calendar | `event_date`, `event_name`, `importance`, `actual`/`forecast`/`previous`, **release time** |
| `model_routing` | AI provider/model per role | `role`, `provider`, `model`, `enabled` |
| `insight_reports` | Cached multi-agent output | `ticker`, `as_of`, `report` JSONB, `model_versions`, `cost_usd` |
| `insight_runs` | Async pipeline state | `status` (queued/running/done/failed), `report_id` |
| `news_sentiment` | Article-level sentiment | `ticker`, `published_ts`, `sentiment_score`, `topics` array |
| **`ticker_info`** | **Ticker metadata cache (PR #98)** | `symbol PK`, `name`, `exchange`, `asset_type`, `sector`, `industry`, `market_cap`, `description`, `relationships` JSONB (peers), `updated_at`. Populated by `lib/ticker_info.py` from AV OVERVIEW + FinViz |
| `historical_signals` | Idempotent signal record (for backtests) | `ticker`, `entry_time`, `trade_type`, `signal_strength`, `return_pct`, `entry_rsi/ema/vwap` |

### 6.4 GCS layout

Bucket: `gs://adept-mountain-474619-d4-trading-data` (~7.61 GiB).

```
raw/data/
  spy/
    historical_*.parquet        # daily OHLCV from AV
    options_*.parquet           # historical options chains
    intraday/
      *.parquet                 # 1-min bars (5+ years)
  iwm/   (same structure)
  qqq/   (same structure)
  spx/   (daily only — no AV intraday)
```

GCS is the source of truth for raw parquet data. Cloud SQL is the source of truth for structured queries. Local `data/` is **NOT** in git (removed in commit `f287259b`).

To pull a ticker locally:
```bash
gsutil -m cp -r gs://adept-mountain-474619-d4-trading-data/raw/data/spy/ data/spy/
```

### 6.5 Local `data/` tree (gitignored)

```
data/
  {ticker}/
    historical_*.parquet
    options/*.parquet
    intraday/*.parquet
  journal/
    {ticker}_journal.json    # local fallback for journal entries
backtest_results/
  backtest_{ticker}_{config}.csv
  equity_{ticker}_{config}.csv
  timeframe_sweep_{ticker}.csv
```

CSV schemas (actual):
- `backtest_*.csv`: `entry_time, exit_time, direction, entry_price, exit_price, exit_reason, return_pct, base_score, strat_bonus, ...` (no `pnl`/`ticker` column)
- `timeframe_sweep_*.csv`: `label, trades, win_rate, avg_win, avg_loss, pf, expectancy, max_dd, sharpe, type` (no `ticker`/`entry_tf`/`filter_tf`)

---

## 7. GCP Infrastructure

GCP project: `adept-mountain-474619-d4`. Region: `us-east1`.

### 7.1 Cloud Run Jobs catalog

| Job | What it does | Trigger |
| --- | --- | --- |
| `fetch-market-data` | Daily OHLCV + indicators (SPY/IWM/QQQ + watchlist union) | Cloud Scheduler — daily |
| `fetch-av-historical-options` | AV historical options EOD writer | Cloud Scheduler — daily |
| `fetch-av-options-backfill` | Historical options backfill (AV) | Manual / one-shot |
| `fetch-alphavantage-intraday` | 1-min bars monthly | Cloud Scheduler — monthly + manual |
| `fetch-economic-events` | ForexFactory + FRED → `economic_events` | Cloud Scheduler — daily |
| `fetch-earnings-calendar` | UW + EW + AV → `earnings_calendar` | Cloud Scheduler — daily |
| `fetch-news-sentiment` | AV news + topics → `news_sentiment` | Cloud Scheduler — hourly (in-window catalysts) |
| `fetch-sec-filings` | SEC EDGAR 8-K → `sec_filings` | Cloud Scheduler — daily |
| `fetch-insider-transactions` | Form 4 → `insider_transactions` | Cloud Scheduler — daily |
| `fetch-top-movers` | AV TOP_GAINERS_LOSERS → `top_movers_daily` | Cloud Scheduler — daily |
| `fetch-fred-rates` | FRED `DGS3MO` → `daily_rates` (PR #93) | Cloud Scheduler — daily |
| `premarket-brief` | 3-embed Discord message + persist to `premarket_analysis` (32 cols). Earnings list ranked by `(date, tier, is_s_p_500, options_volume, stock_volume, market_cap)` and **capped at top-25** (`BRIEF_MAX_EARNINGS` env) | Cloud Scheduler — 8:30 AM ET weekdays |
| `signal-monitor` | Real-time signal alerts → `signal_alerts` + `trades` | Cloud Scheduler — every 5 min during market hours |
| `daily-insight-reports` | Multi-agent pipeline for SPY/IWM/QQQ → `insight_reports` | Cloud Scheduler — 8:45 AM ET weekdays (after premarket-brief) |
| `auto-refresh-top-n` | Pre-warm insights for top-N ranker tickers | Cloud Scheduler — daily |
| `weekend-review` | Weekly market review aggregation | Cloud Scheduler — weekly |
| `apply-schema-migrations` | One-shot idempotent `gcp/schema.sql` runner via `gcp/apply_schema.py` (PR #84). Lets schema rollouts happen without a Codespace | Manual |
| `compute-spx-greeks-backfill` | SPX historical Greeks via `scripts/maintenance/compute_spx_greeks.py` (PR #89). Idempotent (skips rows with `gamma_computed IS NOT NULL`) | Manual / on-demand |
| `failure-notifier` | Cloud Logging Sink → Pub/Sub → Cloud Run Service `gcp/failure_notifier.py` (PR #82). Discord embed + GitHub issue with dedup. See `docs/FAILURE_NOTIFIER_DEPLOYMENT.md` | Pub/Sub push |

The original `fetch-earnings-options` job was removed (commit `5abfc89`) and `fetch-etf-options` (intraday yahooquery) was removed in PR #95; both flowed through `fetch-av-historical-options` which is the sole options writer now.

### 7.2 Cloud Scheduler triggers

23+ cron triggers configured by `gcp/deploy.sh`. Times use UTC; ET conversions accounting for EST/EDT.

Most-trafficked triggers:
- ETF options 9× per day
- Earnings options 6× per day
- Premarket brief: 8:30 AM ET (12:30 UTC EST / 13:30 UTC EDT)
- Daily insights: 8:45 AM ET (intentionally after premarket-brief so insights see fresh strat state)
- Market data daily: post-close
- Intraday monthly: 1st of month
- Economic events: pre-market window
- Earnings calendar: post-close
- News sentiment: hourly during market hours

The premarket-brief → daily-insights ordering is enforced by both Cloud Scheduler AND a GitHub Actions duplicate (Cloud SQL `UNIQUE (ticker, as_of)` with `ON CONFLICT UPDATE` makes the second-firing a no-op upsert).

### 7.3 Secret Manager / IAM

Secrets in Google Secret Manager:
- `AV_API_KEY` and `ALPHA_VANTAGE_API_KEY` (both names — different code paths)
- `FRED_API_KEY`
- `DISCORD_WEBHOOK_URL`
- `github-pat`, `github-repo` (failure notifier)
- `ADMIN_TOKEN`
- LLM provider keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`)

`gcp/deploy.sh` `_env_string()` injects the merged env into Cloud Run jobs. Both `AV_API_KEY` and `ALPHA_VANTAGE_API_KEY` are set on every job to eliminate the "fetcher reads `ALPHA_VANTAGE_API_KEY` but only `AV_API_KEY` is set" footgun.

IAM principals:
- `teneika@bictech.org` — admin, IAP access to platform
- `playwright-tester@...` SA — IAP access for E2E
- Cloud Run runtime SA — Cloud SQL Client role, GCS read/write
- Cloud Build SA — Artifact Registry writer

### 7.4 Failure notifier

Per plan `immutable-jumping-muffin`. Architecture:

```
Cloud Run Job fails
  → Cloud Logging captures error
  → Cloud Logging Sink filters job failures
  → Pub/Sub topic
  → Cloud Run Service `failure-notifier` (FastAPI app)
  → Discord embed (red, job name, error snippet, "View logs" link)
  → GitHub issue created/updated (label: gcp-job-failure,{job_name})
```

Implemented in `gcp/failure_notifier.py`. Uses the same image as the main jobs but with an alternate `--command` entrypoint. Secrets `github-pat` + `github-repo` from Secret Manager. Duplicate detection via search on existing open issues.

### 7.5 `gcp/deploy.sh` entry point

Single-script deploy orchestrator. Functions:
- `build` — build container image, push to Artifact Registry
- `migrate` — apply `gcp/schema.sql`
- `fetchers` — deploy all Cloud Run Jobs + scheduler triggers
- `notifier` — deploy failure notifier service + sink
- `platform` — deploy unified web service (with IAP setup)
- `_env_string()` — internal merger of Secret Manager values

Image digest tracked across rebuilds (e.g. `78035eb7…` → `10200d2c…` on the AV migration rebuild). Stale-image incidents are diagnosed via `gcloud run jobs describe ... --format="value(spec.template.spec.containers[0].image)"`.

Pre-deploy verification (per `dreamy-churning-lovelace`): `pre-deploy-check` agent gates against stale `platform/dist/` and uncommitted `gcp/` changes. Post-deploy verification confirms the new revision is serving traffic and `/api/health` returns OK.

---

## 8. GitHub Actions / CI

14 workflows in `.github/workflows/`. All use the shared failure handler.

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `analyze-market-data.yml` | Daily 22:00 UTC + manual | Compute indicators + strat classification on daily series; backfill Cloud SQL |
| `backtest-pipeline.yml` | Manual | Full backtest run (base + strat) for configured tickers; report generation |
| `daily-insight-reports.yml` | Daily 12:45 UTC weekdays + manual | Multi-agent pipeline trigger (alongside Cloud Scheduler) for observable failure surface |
| `deploy-trading-apps.yml` | Push to main | Deploy standalone web tools to GH Pages / Cloudflare |
| `download-google-sheets.yml` | Scheduled | Fetch Google Sheets data (watchlists, manual trades) → GCS |
| `earnings-options-analytics.yml` | Weekly | Earnings options strategy analysis (the standalone `earnings_options_analytics/` package) |
| `fetch-alphavantage-intraday-monthly.yml` | Monthly + manual | 1-min intraday backfill from AV |
| `fetch-alphavantage-options-daily.yml` | Daily 01:00 UTC + manual | ETF options EOD → Cloud SQL + GCS |
| `fetch-news-sentiment.yml` | Daily + manual | AV news sentiment per ticker |
| `freshness-watchdog.yml` | Hourly + nightly | Comprehensive data-pipeline freshness audit (PR #85). Runs `scripts/audit_data_freshness.py`; auto-creates labeled GitHub issues on staleness; backs Dashboard `DataPipelineStatus` widget via `/api/health/freshness` |
| `handle-workflow-failure.yml` | Reusable (called via `uses:`) | Auto-create GitHub issues + draft PRs on workflow failure; extracts last 50 lines of logs |
| `test-failure-handler.yml` | Manual | Smoke-test the failure handler |
| `update_economic_events_calendar.yml` | Daily + manual | Economic calendar refresh |
| `validate-market-data.yml` | Manual + on push | Data quality (gaps, duplicates, staleness) |

Two `.disabled` files exist alongside (intentionally retired):
- `fetch-market-data.yml.disabled` — Cloud Run Job is sole source of truth
- `fetch-economic-events-calendar.yml.disabled` — superseded by Cloud Run

The legacy `fetch_etf_options.yml` (intraday yahooquery options) was deleted entirely in PR #95 (commit `aea5a7c`).

### Reusable failure handler pattern

Every workflow includes:

```yaml
handle-failure:
  needs: main-job
  if: failure()
  uses: ./.github/workflows/handle-workflow-failure.yml
  permissions:
    contents: write
    issues: write
    pull-requests: write
    actions: read
  with:
    workflow_name: "Human-readable name"
    failure_title: "❌ Descriptive failure title"
    issue_labels: "workflow-failure,specific-label,automated"
    workflow_file: "workflow-filename.yml"
    run_id: ${{ github.run_id }}
    run_number: ${{ github.run_number }}
    run_url: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
    create_pr: true
```

Implemented by `scripts/handle_workflow_failure.py` (Python). Behavior:
- Creates a labeled issue with workflow context, last 50 log lines, link to logs.
- Creates a draft PR on `fix/workflow-{name}-{run-number}` branch.
- Duplicate detection: if an issue already exists for the same workflow, comments on it instead of opening a new one.

---

## 9. Standalone Web Tools

Four tools under their own top-level directories. Each predates the Platform but remains in the repo for niche or legacy use.

| Tool | Path | Port | Tech | Purpose |
| --- | --- | --- | --- | --- |
| **Options Heatseeker** | `options-heatseeker/` | 8101 | Cloudflare Worker + HTML5 + JS | IV heatmap, gamma exposure surface, contract flow, implied move calcs. Source of `greeksCalculator.js` and `nodeAnalyzer.js` ported into platform |
| **Success Report** | `success-report-site/` | 8102 | Python + HTML | Earnings options strategy backtests; trade-by-trade P&L, win rates, equity curves |
| **Chart Viewer** | `chart-viewer/` | 8103 | Static HTML5 + Recharts/D3 | Lightweight price + indicator + order block viewer; reads parquet from local or GCS |
| **Trading Dashboard** | `website/trading-dashboard.html` | 8104 | Self-contained HTML + JS | Offline-capable dashboard with live quote, Greeks calculator, earnings calendar, basic alerts |

Heatseeker is the most actively used today (IV surface visualization is its niche). Chart Viewer and Trading Dashboard are in maintenance — superseded by the Platform's `/charts` and `/dashboard` routes.

---

## 10. Google Apps Script

33 JavaScript files in `google-apps-script/src/`. Drives the Google Sheets-based trade tracking workflow.

Grouped by purpose:

| Group | Files | What they do |
| --- | --- | --- |
| **Globals & helpers** | `01_GlobalVars.js`, `02_HelperFunctions.js` | API keys, date parsing, array utilities |
| **Triggers** | `03_Triggers.js` | Scheduled triggers, on-edit handlers |
| **Calculations** | `06_CalculateFavorables.py` (oddly named), `08_TrackingUpdates.js` | Compute favorable/unfavorable move arrays; update tracking columns |
| **Backfill** | `09_HistoricalBackfill.js`, `10_YahooHistorical.js` | Yahoo historical data import (legacy; Cloud SQL is now primary) |
| **Continuation** | `14_ExecutionContinuation.js` | Timeout-safe resumption (handles GAS 6-min execution limit by checkpointing state and re-firing) |
| **Reports** | `15_SuccessReport.js`, `15_AddTrackingColumns.js`, `17_SuccessReportWebApp.js` | Generate success reports, add tracking columns, web-app delivery |
| **Web app** | `16_WebApp.js`, `17_SuccessReportWebApp.js`, `99_WebAppDebug.js` | HTTP handlers for sheet-as-API |
| **Cleanup / fixes** | `20_FixHitDates.js`, `24_FixCacheData.js` | Data correction utilities |
| **UI** | `25_MenuSheet.js` | Custom Sheets menu |
| **Options tracking** | `27_OptionsPremiumTracking.js`, `27_OptionsPremiumBackfill.js` | Options premium history |
| **Alerts** | `06_trading-alerts.js` | (Recently renamed from `iwm_trading_alerts` and de-hardcoded — commit `f73bbb5`) |
| **Legacy** | `07_OldCode.js` | Archived code |

The continuation pattern (file `14`) is the most novel piece: GAS limits scripts to 6 minutes, so long-running operations checkpoint to PropertiesService, exit, and re-trigger themselves until done.

---

## 11. AI / Multi-Agent Pipeline

Per plan `clever-forging-bear` (Apr 15 2026). Replaces the original ad-hoc Gemini chat on the Insights tab with a structured multi-agent analysis pipeline.

### 11.1 Roles

| Role | Job | Input | Output |
| --- | --- | --- | --- |
| **Market analyst** | Indicator + price action read | Cloud SQL daily/intraday data | `AnalystReport` (thesis, metrics, signals) |
| **Strat analyst** | Strat candle + FTFC analysis | Multi-timeframe data | `AnalystReport` |
| **Options analyst** | Options chain + flow + Greeks | `etf_options_snapshots` | `AnalystReport` |
| **Catalyst analyst** | News, earnings, 8-K, insider, economic events | Catalysts feed (news_sentiment, sec_filings, insider_transactions, economic_events, earnings_history) | `AnalystReport` |
| **Sentiment analyst** | News sentiment + topic match | `news_sentiment` with AV topic slugs | `AnalystReport` |
| **Gamma analyst** | King/Gate/Spot/Flip levels + regime read | `lib/gamma.build_summary()` against today's options chain (PR #81) | `AnalystReport` (level magnets, flip distance, vol regime) |
| **Bull researcher** | Bull case from analyst reports | Analyst reports | `Position` |
| **Bear researcher** | Bear case | Analyst reports | `Position` |
| **Research manager (judge)** | Adjudicate debate | Bull + bear positions | `Verdict` |
| **Trader** | Concrete trade plan | Verdict | `TradePlan` (entry, stop, targets, confidence) |
| **Risk** | Position sizing + risk caps | Trade plan | Risk-adjusted plan |
| **Portfolio manager** | Final recommendation | Risk-adjusted plan + portfolio context | `PortfolioRecommendation` |

The full output is a structured `InsightReport` Pydantic model (defined in `lib/agents/schema.py`).

### 11.2 Provider routing

Each role maps to `(provider, model)` via the `model_routing` Cloud SQL table. Switching is runtime (no code deploy):

```sql
-- Example: route trader to Anthropic Claude, market analyst to Gemini
INSERT INTO model_routing (role, provider, model, enabled)
VALUES ('trader', 'anthropic', 'claude-opus-4-7', true),
       ('market_analyst', 'vertex', 'gemini-2.5-pro', true);
```

Adapters in `lib/agents/`:
- `vertex_adapter.py` — Vertex AI Gemini
- `anthropic_adapter.py` — Anthropic Claude
- (OpenAI adapter is a future extension; routing schema supports `provider='openai'`)

`llm_client.py` exposes a unified `Adapter` interface; `model_routing.py` resolves `(role, env)` → `(provider, model)`.

### 11.3 Persistence

| Table | Purpose |
| --- | --- |
| `insight_reports` | Cached output: `report` JSONB, `model_versions`, `cost_usd`. Unique `(ticker, as_of)` |
| `insight_runs` | Async pipeline state: `status` (queued/running/done/failed), `report_id` |
| `model_routing` | Role → provider/model |

Cost tracking: `lib/agents/pricing.py` has per-provider/per-model token pricing; the orchestrator accumulates cost into the report's `cost_usd` field.

### 11.4 Schedules and triggers

- **Daily run:** Cloud Scheduler fires `daily-insight-reports` Cloud Run Job at 8:45 AM ET (after `premarket-brief`). Generates reports for SPY/IWM/QQQ.
- **GH Actions duplicate:** `daily-insight-reports.yml` fires at the same time on weekdays — gives a failure surface (auto-issue + auto-PR) that Cloud Scheduler doesn't natively provide. `UNIQUE (ticker, as_of) ON CONFLICT UPDATE` makes the second firing a no-op.
- **Manual trigger:** `workflow_dispatch` with a ticker input — for debugging a single report.
- **On-demand refresh:** `POST /api/insights/refresh/{ticker}` enqueues a Cloud Run Job execution and returns a `run_id`. Frontend polls `GET /api/insights/runs/{run_id}` until status flips to `done`.
- **Auto-refresh top-N:** `auto_refresh_top_n.py` Cloud Run Job pre-warms reports for the top-N ranker tickers daily (Phase 5 cache-warming).

### 11.5 Admin dashboard

`/admin` route (gated by `ADMIN_TOKEN`):
- View current `model_routing` table state
- Toggle role enabled/disabled
- Swap provider/model per role
- Inspect recent `insight_runs` and their `cost_usd`

Implemented in `platform/src/routes/AdminPage.tsx` + `platform/api/routers/admin.py`.

---

## 12. Strategy & Methodology

### 12.1 Strat candle types & FTFC weights

The Rob Smith "Strat" candle classification system. Each bar is one of:
- **1** (inside bar) — high < prev high, low > prev low. Compression, breakout pending.
- **2u** (directional up) — high > prev high, low ≥ prev low. Trend continuation up.
- **2d** (directional down) — high ≤ prev high, low < prev low. Trend continuation down.
- **3** (outside bar) — high > prev high AND low < prev low. Two-sided sweep.
- **Failed_2U** (PR #81) — bar broke prior high but closed below the breakout level (bearish reversal signal). `lib/strat.detect_failed_2u()`.
- **Failed_2D** (PR #81) — bar broke prior low but closed above the breakdown level (bullish reversal signal). `lib/strat.detect_failed_2d()`.

`lib/strat.detect_combos()` already labels 212/312 reversals, 212 continuations, and 32 reversals. PR #81 added simple 2-bar continuation labels alongside Failed_2 detection.

**FTFC (Full Timeframe Continuity)** scores how aligned multiple timeframes are. Weights:

| Timeframe | Weight |
| --- | --- |
| Weekly | 0.10 |
| Daily | 0.35 |
| 1 h | 0.25 |
| 15 m | 0.20 |
| 5 m | 0.10 |

FTFC score range: `[-1, 1]`. Positive = bullish alignment. Used as part of the strat bonus on the signal voter.

### 12.2 3-of-5 signal voter + strat bonus

Base signal generation in `lib/signals.py`. Five conditions evaluated on each bar:

1. **Consecutive periods** — last N bars trending in entry direction
2. **RSI zone** — RSI within configured range (e.g. CALL: 45–70; PUT: 30–55)
3. **EMA proximity** — price within ATR-multiple of EMA
4. **Stochastic RSI** — fast crosses slow in entry direction
5. **MACD** — histogram confirming entry direction

`base_score = 1 point per condition met` (range 0–5). Entry fires if `base_score >= 3`.

**Strat bonus** (range 0–3, added to base):
- +0…+1 from FTFC score (continuity)
- +0…+1 from candle pattern (engulfing, 2u/2d, etc.)
- +0…+1 from setup tag (combo, key reversal)

**Total scale: 0–8.**

| Score | Strength |
| --- | --- |
| 3–4 | Weak |
| 5 | Medium |
| 6–7 | Strong |
| 8 | Very Strong |

### 12.3 Indicators (195 IWM features)

Per `docs/INVESTMENT_MODELS_SUMMARY.md`. Computed in `lib/indicators.py` and the GCP daily fetcher.

Breakdown:
- Base OHLCV: ~5 cols
- Core indicators: ~30 cols (SMA, EMA, RSI, ATR, VWAP, RVOL, OBV, Stochastic RSI, MACD, BB)
- Historical levels: 80 cols (multi-period highs/lows, ATR-distance bands)
- ORB (Opening Range Breakout): 108 cols (5 m / 15 m / 30 m bands × multiple stats × directional flags)
- Order Blocks: 7 cols
- (overlap accounts for the 195 total, not 230)

### 12.4 Risk rules and exit logic

In `lib/config.py` (`RiskConfig`, `ExitConfig`):

**Risk caps:**
- Max trades per day: 2–3
- Daily loss limit: 2% — stops all trading if hit
- Max concurrent positions: 1–2

**Exit rules (in priority order):**
- Profit target hit: +0.30% (CALL) / +0.38% (PUT)
- Stop hit: -0.15% (CALL) / -0.20% (PUT)
- Time stop: 30 min (CALL) / 35 min (PUT)
- RSI extreme: exit if RSI > 80 (CALL) or < 20 (PUT)

**Position sizing (signal-strength-driven):**
- 3 conditions met: 25% size
- 4 conditions: 50%
- 5+ conditions: 75%
- 7+ (with strat bonus): 100%

### 12.5 Backtest results highlights

Per `BACKTEST_RESULTS.md` (1-min entries, 3-of-5 conditions, 1-day window).

**Base IWM (no strat):**
| Metric | Value |
| --- | --- |
| Trades | 13,946 |
| Win rate | 41.0% |
| Profit factor | 1.01 |
| Sharpe | 0.19 |

**Base + Strat overlay:**
| Metric | Value |
| --- | --- |
| Trades | 12,238 |
| Win rate | 41.4% |
| Profit factor | 1.03 |
| Sharpe | **0.43 (+133%)** |
| Filter rejection rate | ~12% |

**Trade duration:** winners 22 min avg, losers 15 min avg.
**Exit distribution:** 48% stop / 27% time / 24% profit / 1% other.

**Timeframe sweep insight:** the **1m + 30m combo** is the edge — Sharpe **7.70**, win rate **54%**. Beats every single-TF approach.

**Best windows:**
- 9:30–10:00 AM ET: 0.48% avg
- 10:00 AM–2:00 PM: 0.33%
- After 2 PM: 0.30%

**Probability-calibrated highlights** (from morning checklist analysis):
- RSI <30: 100% WR (n is small — sample-size caveat)
- ATR ≥0.15: 100% WR, 0.39% avg
- CALL Bias setup (20 EMA > 50 EMA, Price > VWAP, RSI > 50): 100% WR, 0.31% avg

---

## 13. Testing Strategy

### 13.1 Make targets

```bash
make test            # Unit + integration (~703 tests after PR #94's +251 alignment, ~80s, excludes E2E)
make test-e2e        # Playwright E2E (33+ specs, ~30s)
make test-scripts    # CLI regression for scripts/ (18 tests, ~40s)
```

Chromium for Playwright is installed at `~/.cache/ms-playwright/chromium-1208`. Reinstall only if dir vanishes:
```bash
python -m playwright install chromium
```

### 13.2 Test file inventory (`tests/`)

| File | Coverage |
| --- | --- |
| `test_backtest.py` | Backtesting engine: trade entry/exit, risk rules, position sizing |
| `test_signals.py` | 3-of-5 voter, CALL/PUT scoring |
| `test_indicators.py` | SMA, EMA, RSI, MACD, BB, ATR |
| `test_strat.py` | FTFC scoring, candle patterns, strategy classification |
| `test_data_loader.py` | Cloud SQL / parquet, resampling, validation |
| `test_walk_forward.py` | Fold metrics, stability scoring |
| `test_config.py` | Configuration loading and validation |
| `test_platform_api.py` | FastAPI routers (requires Cloud SQL) |
| `test_routers_insights_admin.py` | Insights and admin routers (model routing) |
| `test_auto_refresh.py` | Auto-refresh ticker caching |
| `test_ranker.py` | Ticker ranking and weighting (insider buying vs selling, news topic match) |
| `test_agent_orchestrator.py` | Multi-agent pipeline orchestration |
| `test_agent_summarizers.py` | Per-analyst summarization (with sentiment analyst + AV topic slugs) |
| `test_agent_schema.py` | Pydantic models for InsightReport, TradePlan |
| `test_agent_model_routing.py` | Model routing resolution |
| `test_agent_pricing.py` | Cost tracking |
| `test_agent_vertex_adapter.py` | Vertex adapter |
| `test_phase2_fetchers.py` | GCP fetcher integration |
| `test_production_readiness.py` | Production environment checks (100-pt scorecard) |
| `test_e2e.py` | Playwright E2E (28 scenarios) |
| `test_scripts.py` | CLI regression for scripts |
| `test_integration.py` | Cross-module integration |
| `test_gamma.py` | `lib/gamma.py` — sign convention, GEX/VEX, King/Gate/Spot/Flip classification (PR #81) |
| `test_options_greeks.py` | `lib/options_greeks.py` — BSM IV solver, sidecar columns, FRED rate lookup (PR #86) |
| `test_options_router.py` | `POST /api/options/greeks` and `GET .../levels` (PR #88) |
| `test_failure_notifier.py` | Pub/Sub envelope parsing, Discord shape, GitHub dedup (PR #82) |
| `test_apply_schema.py` | One-shot schema migration job (PR #84) |
| `test_audit_data_freshness.py` | Per-table freshness watchdog (PR #85) |
| `test_fetch_av_historical_options.py` | AV options backfill fetcher (PR #94) |
| `test_historical_signals.py` | Multi-row VALUES bulk insert path (PR #94) |
| `test_playbook_evaluate.py` | Server-side playbook condition evaluation (PR #94) |
| `test_premarket_brief.py` | Premarket-brief job: tier sort, top-N cap, Discord embed (PR #94) |
| `test_watchlist_helper.py` | Watchlist union utilities (PR #94) |
| `test_agent_anthropic_adapter.py`, `test_agent_embeddings.py` | Multi-agent expansion (PR #94) |
| `test_ticker_info.py` | Ticker metadata: AV search, quote, peers, FinViz news, Cloud SQL + JSON cache (PR #98) |
| `test_trade_planner.py` | Deterministic per-persona trade planning (PR #96) |

Frontend unit tests (Vitest) — colocated with source:
- `platform/src/lib/playbookEvaluator.test.ts`
- `platform/src/lib/strategySignals.test.ts`
- `platform/src/lib/marketSession.test.ts`
- `platform/src/lib/strategySignalsForSeries.test.ts` (PR #80 per-bar voter)

### 13.3 Pre-existing failures on main (NOT regressions)

Per `MEMORY.md` and re-verified on main 2026-04-26:

- `test_pipeline_end_to_end_green` — LLM call count drift 12 → 13 (count expectation stale)
- `test_health_returns_ok` — asserts `data_dir_exists` field, missing in current `/api/health` response
- Most `test_platform_api.py` cases — Cloud SQL not reachable from sandbox
- `test_data_loader.py::TestLoadIntraday::test_returns_empty_when_no_data` — premise invalidated when Cloud SQL gained real IWM data; should be deleted/rewritten, not perpetually waved through

Always switch to main and re-run a failing test before treating it as a branch regression.

### 13.4 Playwright E2E

Local mode (default): `npm run e2e` against `localhost:5173` + `:8000`.
Cloud mode (against deployed): `npm run e2e:cloud:auth` (one-time interactive Google sign-in) then `npm run e2e:cloud`.

Specs added since BRIEFING write:
- `gamma-levels.spec.ts` — gamma overlay + heatmap + admin gamma flow (PR #81)
- `data-pipeline-status.spec.ts` — DataPipelineStatus widget (PR #85)
- `api-smoke.spec.ts` — endpoint smoke (PR #88)
- `navigation.spec.ts` — route navigation smoke (PR #88)
- `charts-cards.spec.ts` — Strategy Conditions + Similar Setups + Sig overlay (PR #80)
- `admin-auth.spec.ts` — IAP email bypass, token gate fallback, sidebar Admin link visibility (13 tests, PR #98/#99)

Coverage includes per-route smoke tests for Dashboard, Charts, Insights, Admin, Catalysts, Signals, Journal — added in commit `8639b63` and `413830b`.

---

## 14. Plans Executed (Apr 10–26, 2026)

Seventeen named plans live in `~/.claude/plans/`. All have been validated against current code. Status legend:
- ✅ **Shipped** — full intent landed in code
- 🟡 **Partial** — some pieces shipped, others staged or deferred
- ⛔ **Not shipped** — plan written but no code deliverable
- 📋 **Investigation** — diagnostic only, no code expected

| # | Plan codename | Title | Date | Status |
| --- | --- | --- | --- | --- |
| 1 | `clever-forging-bear` | AI Insights Tab — Multi-Agent Analyst Pipeline | 2026-04-15 | ✅ Shipped |
| 2 | `crystalline-puzzling-clock` | Dashboard + Charts UI cleanup | 2026-04-13 | ✅ Shipped |
| 3 | `dreamy-churning-lovelace` | Port AWS agents → GCP & harden deploy pipeline | 2026-04-14 | ✅ Shipped |
| 4 | `glistening-munching-willow` | Eliminate Hardcoded Values — Move All Math/Config to GCP | 2026-04-18 | ✅ Shipped |
| 5 | `glowing-popping-thimble` | Options Flow Data Pipeline — Production Fix | 2026-04-13 | 🟡 Partial |
| 6 | `golden-zooming-newell` | Daily Bias Card — Fix & Redesign | 2026-04-14 | ✅ Shipped |
| 7 | `goofy-yawning-rain` | SPX Backfill + Comprehensive Freshness Watchdog | 2026-04-14 | ✅ Shipped |
| 8 | `humming-dreaming-cascade` | Daily Bias: un-stale the dashboard | 2026-04-13 | ✅ Shipped |
| 9 | `immutable-jumping-muffin` | GCP Cloud Run Job Failure Notifier (Discord + GitHub Issue) | 2026-04-14 | ✅ Shipped |
| 10 | `lovely-riding-quiche` | SPX Options Greeks — Implementation Plan | 2026-04-13 | 🟡 Partial |
| 11 | `mutable-churning-map` | Historical Review Mode — Full App Integration | 2026-04-10 | ✅ Shipped |
| 12 | `starry-bubbling-koala` | Investigation Report — Stale Market Data | 2026-04-10 | 📋 Investigation |
| 13 | `velvety-booping-kazoo` | Header "Market Closed" badge fix | 2026-04-10 | ✅ Shipped |
| 14 | `zippy-forging-bachman` | Archive Yahoo Data → `archive_yahoo_*` Tables | 2026-04-12 | 🟡 Partial |
| 15 | (session 4) | Ticker Info API + Watchlist Add | 2026-04-26 | ✅ Shipped |
| 16 | (session 4) | Admin IAP Email Bypass | 2026-04-26 | ✅ Shipped |
| 17 | (session 4) | RSS News Feed Probe (19 feeds) | 2026-04-26 | ✅ Shipped |

### Per-plan detail

#### 1. `clever-forging-bear` — AI Insights Multi-Agent Pipeline ✅

**Problem:** Insights tab was a generic Gemini chat — non-deterministic, no structured output.
**Approach:** Replace with multi-agent pipeline (analysts → debate → trader/risk/PM). Provider-agnostic LLM client with per-role routing.
**Files shipped:** `lib/agents/` (11 modules), `platform/api/routers/insights.py`, `platform/api/routers/admin.py`, `platform/src/routes/InsightsPage.tsx`, `platform/src/routes/AdminPage.tsx`, `.github/workflows/daily-insight-reports.yml`. Schema: `insight_reports`, `model_routing`, `insight_runs`.
**Evidence:** Full `lib/agents/` package present; `InsightsPage.tsx` renders structured DirectionCard / TradePlanCard / DebateCard; AdminPage routing UI live; daily workflow + Cloud Run Job both fire at 12:45 UTC.

#### 2. `crystalline-puzzling-clock` — Dashboard + Charts UI cleanup ✅

**Problem:** Multiple small UX nits — top setup bullets, 24 h time, separate /backtest route.
**Approach:** Replace condition bullets with met/unmet/unknown icons; switch to 12 h time; merge `/backtest` into Charts; document backtest data storage.
**Files shipped:** `DashboardPage.tsx` (TrendingUp/TrendingDown icons, time format), `LiveMarketPage.tsx`, `ChartsPage.tsx` (Backtester section), `components/backtest/BacktesterSection.tsx`, `App.tsx` (route removal), `playbookEvaluator.ts` (extracted `buildSnapshot`).
**Evidence:** No `BacktestPage.tsx` standalone in routes; ChartsPage embeds Backtester; verified commit `5d957d0` "feat(charts): live strategy conditions card on /charts".

#### 3. `dreamy-churning-lovelace` — Port AWS agents → GCP ✅

**Problem:** AWS-specific Claude Code agents (deploy, security-scan, etc.) were missing GCP equivalents; deploy pipeline lacked verification.
**Approach:** Port 7 agents (pre-deploy-check, security-scan, impact-analyzer, infra-drift-detector, test-coverage-analyzer, trading-logic-reviewer, debug-local). Enhance gcp-deploy with pre-check + post-deploy verification. Add NO-SHORTCUTS discipline + Cloud Monitoring alert hooks to workflow-debugger.
**Files shipped:** `.claude/agents/` (7 new), `.claude/agents/workflow-debugger.md` (enhanced), `.claude/commands/gcp-deploy.md`, `.claude/commands/audit-review.md`.
**Evidence:** Agents present in `.claude/agents/` with file dates Apr 18 03:54.

#### 4. `glistening-munching-willow` — Eliminate Hardcoded Values 🟡

**Problem:** 21 hardcoded values across the frontend (Greeks multipliers, node thresholds, RSI zones, market hours). Drift between Python `lib/indicators.py` and TypeScript.
**Approach:** Delete client-side `greeksCalculator.ts` and `nodeAnalyzer.ts`; move math to server endpoints. Add `/api/config/indicators` and `/api/config/market-hours` for thresholds.
**Closed by PR #81 ("Consolidate gamma analytics into lib/gamma.py as single source of truth") and PR #92.** Evidence:
- `platform/src/lib/greeksCalculator.ts` — **DELETED** ✓
- `platform/src/lib/nodeAnalyzer.ts` — **DELETED** ✓
- `lib/gamma.py` — **NEW**, ~568 lines, canonical math (GEX, VEX, King/Gate/Spot/Flip taxonomy, max-pain, implied move) ✓
- `POST /api/options/greeks` endpoint — **LIVE** at [platform/api/routers/options.py:359](platform/api/routers/options.py#L359) ✓
- `GET /api/options/{ticker}/{date_str}/levels` endpoint — **LIVE** at [platform/api/routers/options.py:415](platform/api/routers/options.py#L415) ✓
- `useGammaLevels.ts` hook + `useOptionsGreeks.ts` hook — **LIVE**, OptionsFlowPage rewired ✓
- `analytics.py` router — **LIVE** (PR #92): `/api/analytics/summary/{ticker}`, `/api/analytics/trade-stats` ✓
- `config.py` router — **LIVE** (PR #92): `/api/config/indicators`, `/api/config/market-hours` ✓
- `docs/HARDCODED_VALUES_REMEDIATION.md` declares Parts 1A, 1A.1, 1B, 1C, 1D, 1E, 2A, 2B, 2C all ✅ DONE; only 1F (chart take-profit default) deferred per user preference, and Part 3 (LOW severity cosmetic) deferred ✓
- `docs/gamma_levels.md` provides the canonical King/Gate/Spot/Flip reference ✓
- `tradingview-pine-scripts/gamma-levels-overlay-v2` — Pine companion shipped ✓

#### 5. `glowing-popping-thimble` — Options Flow Pipeline Phase 1 + Phase 2 🟡 (infra ✅, exec pending)

**Phase 1 (✅ shipped):** Reader was a live AV proxy that 404'd on today's date. Rewritten as Cloud SQL reader with 12 h TTL cache. Workflow `fetch-alphavantage-options-daily.yml` writes to Cloud SQL via `gcp/fetchers/fetch_av_historical_options.py`. AV historical backfill (~7,500 calls, 8,389 parquet files) completed Apr 13. SPX 10-year coverage in.
**Phase 2 infra (✅ shipped via PRs #86, #89, #93):** SPX Greeks computation. AV doesn't provide Greeks for cash-settled SPX; compute via `py_vollib_vectorized` (BSM IV solve from mid prices). Sidecar columns (`delta_computed`, `gamma_computed`, etc.) preserve AV provenance. Three-tier spot derivation: FRED SP500 (tier 1), put-call parity (tier 2), SPY×10 (tier 3).
**Files shipped:**
- `lib/options_greeks.py` ✓ (470 lines, PR #86)
- `requirements.txt` += `py_vollib_vectorized` ✓
- `etf_options_snapshots` sidecar columns ✓
- `gcp/fetchers/fetch_fred_rates.py` ✓ (PR #93)
- `daily_rates` Cloud SQL table ✓ (PR #93)
- `scripts/maintenance/compute_spx_greeks.py` ✓ (PR #89)
- `scripts/backfill_spx_from_options.py` ✓ (PR #89)
- Cloud Run Job `compute-spx-greeks-backfill` ✓
**Still pending:** backfill execution. Sequenced after Yahoo options cleanup completes.

#### 6. `golden-zooming-newell` — Daily Bias Card Redesign ✅

**Problem:** Card had Unicode arrows, unexplained "Combo: none" label, "1d stale" badge despite frozen daily close, RSI mismatch (60.7 vs 61.7) on same page, dense but not actionable.
**Approach:** Replace Unicode arrows with lucide `TrendingUp`/`TrendingDown`; clarify combo with tooltip; make RSI sources consistent; restructure with headline thesis + confidence bar + CTA "See top setup →".
**Files shipped:** `DashboardPage.tsx`, `dashboard.py` (live-overlay RSI consistency).
**Evidence:** TrendingUp/TrendingDown icons confirmed in DashboardPage; RSI single-source via `brief.rsi` or live overlay.

#### 7. `goofy-yawning-rain` — SPX Backfill + Freshness Watchdog ✅

**Problem:** SPX had a 4-month gap (2025-12-18 → 2026-04-13). No comprehensive watchdog for staleness across tickers/tables.
**Approach:** Phase 1 SPX backfill via put-call parity (~78 rows, `data_source='derived_put_call_parity'`). Phase 2 add SPX detection to `fetch_market_data.py`. Phase 3 fail-fast guards in `signal_monitor.py`. Phase 4 hourly+nightly freshness watchdog GH workflow.
**Files shipped:** `scripts/backfill_spx_from_options.py`, `gcp/fetchers/fetch_market_data.py` (SPX branch), `gcp/signal_monitor.py`, `scripts/audit_data_freshness.py`, `.github/workflows/freshness-watchdog.yml`, `docs/DATA_PIPELINE.md`.

#### 8. `humming-dreaming-cascade` — Daily Bias Un-Stale ✅

**Problem:** Daily Bias card frozen on last daily close; `/api/dashboard/brief/{ticker}` returned only EOD snapshot.
**Approach:** `_apply_live_overlay(brief, ticker)` helper. During market hours, append synthetic today-bar built from AV live quote, recompute RSI14/EMA9/EMA20/SMA200 via `lib.indicators`. Frontend polls every 15 s during market hours. `_trading_days_between()` for honest staleness.
**Files shipped:** `dashboard.py`, `DashboardPage.tsx`, `gcp/deploy.sh` (image rebuild).
**Side fix:** Cloud Run image was stale (pre-AV migration); rebuilt and redeployed; backfilled 2026-04-06..2026-04-10.

#### 9. `immutable-jumping-muffin` — GCP Job Failure Notifier ✅

**Problem:** 9 Cloud Run Jobs ran on Cloud Scheduler but failures only surfaced in Cloud Logging.
**Approach:** Cloud Logging sink → Pub/Sub topic → Cloud Run Service notifier → Discord embed + GitHub issue (with duplicate detection). Notifier is a FastAPI app deployed alongside main image with alternate `--command` entrypoint.
**Files shipped:** `gcp/failure_notifier.py`, `gcp/deploy.sh` (notifier setup functions), `tests/test_failure_notifier.py`, secrets `github-pat` + `github-repo`.

#### 10. `lovely-riding-quiche` — SPX Options Greeks 🟡 (infra ✅, exec pending)

**Phase 2 distillation of #5.** Architectural decision: sidecar columns. Reader aliases `_computed` Greeks for tickers in `COMPUTE_GREEKS_TICKERS = {SPX, SPXW, NDX, RUT, XSP}`.
**Shipped (PRs #86, #89, #93):** `lib/options_greeks.py` (470 lines), `py_vollib_vectorized` in requirements, `gcp/fetchers/fetch_fred_rates.py`, `daily_rates` Cloud SQL table, `scripts/maintenance/compute_spx_greeks.py`, Cloud Run Job `compute-spx-greeks-backfill`, `daily_rates` table indexed on `(date DESC)`.
**Still pending:** backfill execution and `greeks_source` field on response.
**Blocker:** Yahoo options cleanup completion (running `fetch-av-options-backfill` Cloud Run Job).

#### 11. `mutable-churning-map` — Historical Review Mode ✅

**Problem:** DateSelector set `reviewDate + reviewTime` but only Dashboard/LiveMarketPage consumed it. Other routes ignored review state.
**Approach:** Add `end_date`/`end_time` query params to `/api/signals` and `/api/market/data/{ticker}/{date}`. Dashboard KPIs + Best/Worst Trades filter by cutoff. ChartsPage snaps to nearest trading day in review mode. SignalsPage forces `dateTo = reviewDate`. DateSelector lifted to header.
**Files shipped:** `signals.py`, `main.py`, `DashboardPage.tsx`, `ChartsPage.tsx`, `SignalsPage.tsx`, `Header.tsx`, `LiveMarketPage.tsx`, `reviewDateStore.ts`.

#### 12. `starry-bubbling-koala` — Stale Market Data Investigation 📋

**Diagnosis only:** Dashboard/Live pages showed 2026-04-09 prices while labeled "Market Open" on 2026-04-10. Three root causes: (A) AV entitlement doesn't include today's intraday on the current tier; (B) Cloud SQL `market_data_daily` is T-1 by design (EOD job); (C) frontend didn't surface staleness. Findings drove follow-up plans #6 and #8.

#### 13. `velvety-booping-kazoo` — Header Market Closed Badge ✅

**Problem:** Header showed "Market Closed" during trading hours. Root cause: `marketStore.ts` had `isMarketOpen: false` initial + `setMarketOpen` setter, **but nothing called the setter**. Two pages duplicated `useFetch + /api/live/status`.
**Approach:** Single shared `useLiveStatus` TanStack Query hook. Lift `sessionLabel`/`sessionColor` to `lib/marketSession.ts`. Delete dead store fields.
**Files shipped:** `hooks/useLiveStatus.ts`, `lib/marketSession.ts`, `Header.tsx`, `marketStore.ts`, `DashboardPage.tsx`, `LiveMarketPage.tsx`.

#### 14. `zippy-forging-bachman` — Archive Yahoo Data 🟡

**Problem:** Yahoo data was supposed to be deleted post-AV migration but ~24 M rows remained in `etf_options_snapshots`, ~51 K in `market_data_intraday`.
**Approach:** Create `archive_yahoo_*` tables via `CREATE TABLE ... (LIKE src INCLUDING ALL)`. Chunked copy + delete using primary-key batching (NOT ctid — partition-local ctids would collide on LIST-partitioned tables and delete AV rows).
**Files shipped:** `gcp/schema.sql` (4 archive tables ✓), `scripts/archive_yahoo_data.py` (✓ with dry-run + per-table `--confirm`).
**Status:** intraday cleanup completed (with one ctid bug + AV recovery). Options cleanup pending — must wait for `fetch-av-options-backfill` to finish to avoid I/O contention.
**Update (PR #95, 2026-04-26):** the legacy `fetch_etf_options.yml` workflow + `gcp/fetchers/fetch_etf_options.py` + `scripts/fetch_etf_options_intraday.py` were removed entirely (yahooquery intraday options pipeline retired). One less blocker; the writer surface for options is now AV-only.

---

## 15. Recent Activity (Changelogs & Commits)

### 15.1 Week of 2026-04-07 to 2026-04-13

Summarized from `docs/changelog/CHANGELOG_2026-04-07_to_2026-04-13.md`.

**Data pipeline & Cloud SQL:**
- Daily Bias card overlays live AV quote on Cloud SQL snapshot during market hours.
- Cloud Run image rebuilt — 4-day silent yfinance failure (pandas float into INTEGER columns) fixed.
- Cloud SQL `market_data_daily` backfilled through 2026-04-10 for IWM/SPY/QQQ.
- Stale-days switched from calendar days to trading days.

**Data sources:**
- ForexFactory added as economic events source (real release times).
- AV `EARNINGS_CALENDAR` added as 3rd source (date-of-truth) alongside UW + EW.
- Earnings calendar tier-sorted by source coverage.
- Weekly mode added to premarket brief.

**Infrastructure:**
- `fetch-market-data.yml` GH Actions disabled — Cloud Run Job is sole source.
- Yahoo archive tables + cleanup script deployed.
- Intraday Yahoo data archived/removed (51 K rows). AV intraday switched to upsert mode.

**Platform:**
- Options Flow page rewritten to read Cloud SQL.
- Covering index `(ticker, data_source, snapshot_date DESC)` created.
- Options dates endpoint widening-range scan (60 d → 1 y → 3 y → 10 y → unbounded) with 12 h TTL cache.

### 15.2 Week of 2026-04-20 to 2026-04-26

Summarized from `docs/changelog/CHANGELOG_2026-04-20_to_2026-04-26.md`.

**Cloud Run deployment & IAP:**
- `platform/` deployed to Cloud Run with auto-managed IAP (bictech.org SSO).
- Multi-stage Dockerfile (Node 20 frontend, Python 3.11 backend); build context 4 GB → 225 MB.
- Playwright auth flow with `storageState` for E2E against deployed URL.
- `/dev` diagnostic endpoint (revision, Cloud SQL status, IAP audience) gated to authenticated users.

**WCAG & build fixes:**
- 8 button components fixed (white-on-light-blue → `--on-brand` text token).
- TypeScript errors blocking production build fixed.
- ViteConfig moved to `defineConfig` from `vitest/config`.

**Ranker & sentiment:**
- Insider buying (+1.5) and selling (-1.5) tracked separately.
- `weighted_score()` allows negative weights; `pct_of_max` normalizes via `abs(weight)`.
- Shared `_insider_window()` extraction.

**Historical signals → Cloud SQL:**
- New `historical_signals` table (PK `(ticker, entry_time)`, indexed on score / direction).
- `gcp/historical_signals.py` helper + `scripts/run_historical_signals.py` CLI (`--start-date` / `--end-date` / `--force` / `--backfill-from`); month-by-month bash driver in `scripts/backfill_historical_signals.sh`.
- Bulk INSERT switched from pg8000 executemany to one multi-row `VALUES (...), (...)` per chunk: ~6 rows/sec → ~800 rows/sec (~130×). 11-year IWM/QQQ/SPY backfill now runs in ~10 min/ticker instead of ~9 hr.
- `signals.py` router primary path moved to Cloud SQL with parquet kept as a local-dev fallback. New `GET /api/signals/{ticker}/similar?direction&rsi&score&rsi_band&limit` powers the Charts "Similar Setups" card with server-side aggregation (count, mean/median/p25/p75 MFE pct, mean return at 5/20 min, pct profitable).

**Earnings cap + UW enrichment:**
- `_earnings_tickers_in_window` (daily fetcher) and `load_earnings_for_brief` (premarket Discord) both capped at top-25 ranked by `optionable → SP500 → options_volume → stock_volume → market_cap → ticker`. Configurable via `MAX_EARNINGS_TICKERS` / `--max-earnings-tickers` / `BRIEF_MAX_EARNINGS`.
- Root cause for the cap: AV's 150-rpm budget was being spent on a 200+ ticker fan-out, silently skipping IWM/SPY/QQQ when the loop ran out of quota. The four core tickers were stale for ~2 weeks before anyone noticed.
- Added 6 columns to `earnings_calendar` populated from UW's `upcoming_earnings_v2`: `is_s_p_500`, `stock_volume`, `options_volume` (= `call_vol+put_vol`), `open_interest`, `rv_1d_last_12q`, `last_1d_reactions` (JSONB array). UW's response is 30 fields total — we now capture the 9 we already had plus these 6 ranking signals; the rest (logo URL, country code, etc.) skipped intentionally.
- Heavy earnings days (e.g. Wed 2026-04-29 with 251 calendar rows) now surface 25 SP500 / tier-1 names — MSFT, META, GOOGL, QCOM, ABBV, etc. — instead of falling back to alphabetical AV-only long-tail (ALWIF, BUSEL).

**Session 3 — Post-Merge Cascade (2026-04-26 morning UTC, PRs #81–#95):**

After PR #80 merged into main, 14 follow-on PRs landed in the same morning:

- **Gamma consolidation** (#81) — `lib/gamma.py` (568 lines) becomes single source of truth for GEX/VEX/King-Gate-Spot-Flip math. Deletes `greeksCalculator.ts`, `nodeAnalyzer.ts`. Adds `POST /api/options/greeks` and `GET /api/options/{ticker}/{date_str}/levels` endpoints. New `useGammaLevels.ts` hook. Charts page gamma overlay toggle. Gamma analyst added to AI pipeline. Pine Script `gamma-levels-overlay-v2`. Tests `test_gamma.py` (323 lines) + `gamma-levels.spec.ts` (244 lines).
- **Failure notifier** (#82) — `gcp/failure_notifier.py` (333 lines): Cloud Logging Sink → Pub/Sub → Cloud Run Service → Discord embed + GitHub issue (with dedup). `FAILURE_NOTIFIER_DEPLOYMENT.md` runbook (351 lines).
- **7 reliability agents** (#83) — debug-local, impact-analyzer, infra-drift-detector, pre-deploy-check, security-scan, test-coverage-analyzer, trading-logic-reviewer added to `.claude/agents/`. Closes plan #3 in code (BRIEFING was premature).
- **Schema migrations job** (#84) — `gcp/apply_schema.py` + `apply-schema-migrations` Cloud Run Job. Schema rollouts no longer need a Codespace.
- **Pipeline freshness widget + watchdog** (#85) — `scripts/audit_data_freshness.py` (575 lines), `platform/api/routers/health.py`, `.github/workflows/freshness-watchdog.yml` (121 lines), Dashboard `DataPipelineStatus.tsx` widget.
- **`lib/options_greeks.py` BSM module** (#86) — 470 lines, `py_vollib_vectorized` IV solver, sidecar columns, `enrich_av_chain_with_greeks()` orchestrator.
- **Data pipeline + codespaces auth + April incident docs** (#87) — `docs/DATA_PIPELINE.md` (435 lines), `docs/claude-code-codespaces-auth.md` (70 lines), `docs/incidents/2026-04-14-market-data-daily-gap.md` (76 lines, first postmortem).
- **E2E smoke specs** (#88) — `navigation.spec.ts`, `data-pipeline-status.spec.ts`, `api-smoke.spec.ts`.
- **SPX Greeks backfill scripts** (#89) — `scripts/maintenance/compute_spx_greeks.py` (277 lines), `scripts/backfill_spx_from_options.py` (209 lines, put-call-parity SPX OHLC backfill).
- **Makefile convenience** (#90) — `make setup-notifier`, `make notifier`.
- **100-point audit scorecard + pre-deploy gate** (#91) — `.claude/commands/audit-review.md` upgraded; `.claude/commands/gcp-deploy.md` adds pre-deploy gate (closes plan #3 hardening).
- **Misc fixes** (#92) — `lib/data_loader.get_close_price()` helper, `gcp/signal_monitor.py` fail-fast on missing env, `MetricCard` subtitle color fix. Adds `analytics.py` and `config.py` routers (closes BRIEFING §16.2 plan #4 drift entry).
- **FRED daily rates pipeline** (#93) — `gcp/fetchers/fetch_fred_rates.py` (213 lines), `daily_rates` Cloud SQL table, scheduler trigger. Closes the last infra gap in plans #5 and #10 — only backfill execution pending.
- **Test suite alignment** (#94) — +251 net additions across 18 test files; new test files for failure notifier, schema migrations, freshness audit, AV options backfill, historical_signals, playbook evaluate, premarket brief, watchlist helper, anthropic adapter, embeddings.
- **Remove fetch-etf-options pipeline** (#95) — workflow `.yml` (186 lines), fetcher `.py` (293 lines), CLI script (616 lines) all deleted. Yahooquery intraday options retired. AV-only writer surface.

### 15.3 Session 4 (2026-04-26 evening, PRs #96–#99)

**Deterministic trade planner** (PR #96):
- `lib/agents/trade_planner.py` replaces LLM-generated entry/stop/targets/sizing with explicit per-persona math. Same inputs → byte-identical plans. Aggressive/neutral/conservative recipes with ATR-based stops, R-multiple targets, and sizing multipliers.

**Ticker Info API + Watchlist Add** (PR #98, commit `382993a9`):
- `lib/ticker_info.py` (~454 lines): AV SYMBOL_SEARCH/OVERVIEW/GLOBAL_QUOTE + FinViz peers/news. Cloud SQL `ticker_info` table cache + local JSON fallback.
- 5 new endpoints on insights router: `GET /api/insights/ticker/search`, `.../info`, `.../quote`, `POST .../watchlist/add`, `DELETE .../watchlist/{ticker}`.
- `useTickerSearch` hook (debounced search, add/remove mutations). WatchlistPanel enhanced with search input + add ticker flow.

**Admin IAP email bypass** (PR #98, commit `4d1afda8`):
- `admin.py` accepts IAP-authenticated admin email (`teneika@bictech.org`) without token.
- `/api/me` endpoint returns current user's email from IAP headers.
- `useUser` hook + conditional Admin sidebar link + AdminPage token gate skip.

**RSS news feed probe** (PR #98, commits `396d7b81`, `b86af6f6`):
- `scripts/probe_news_feeds.py` classifies 19 candidate RSS feeds as PER_TICKER vs GENERAL.
- Extracts metadata: cashtags, pub dates, category elements, item counts.
- Investigation tool for future news integration pipeline.

**Test reliability fix** (PR #99):
- `admin-auth.spec.ts` (13 Playwright tests): IAP bypass, token gate fallback, sidebar visibility.
- Replaced `networkidle` waits with element-based waits to prevent timeouts when backend is slow.

### 15.4 Themes from last 50 commits

| Theme | Commits |
| --- | --- |
| **Catalysts feed** | unified actionable feed, point-in-time snapshots, news + 8-K + earnings + insider merge, Benzinga corporate events |
| **Ranker** | Phase 3 deterministic ranker, watchlist scoping, insider direction split, news topic match, audit insert via execute_sql |
| **Insights / agents** | Watchlist tab, persona plans, sentiment analyst, AV topic slugs, drop 7-day earnings expansion |
| **Cloud Run platform deploy** | IAP-gated /dev, Playwright cloud-mode, WCAG button fixes |
| **Fetchers** | SEC EDGAR 8-K, news topics, earnings history, insider transactions, top movers, hourly news cadence |
| **E2E tests** | per-route Playwright coverage, catalyst + insights UI behaviors |
| **Strat fields** | computed in `compute_and_upsert_daily_indicators` |
| **Backtest** | catalyst-analog matching replaces empty-trades backtest, cross-ticker analog matching |
| **Watchlist** | trimmed to IWM/QQQ/SPY/SPX/AVGO; unioned into market_data + options ticker pools |
| **Operations** | Phase 2 Cloud Shell deploy + smoke test runbooks, idempotent watchlist backfill |

---

## 16. Outstanding Work & Known Gaps

### 16.1 Sequencing-blocked items

| Item | Blocker | ETA |
| --- | --- | --- |
| **SPX Greeks backfill execution** (`compute-spx-greeks-backfill` Cloud Run Job) | Yahoo cleanup of `etf_options_snapshots` must finish first; infra is ready | After Yahoo archival completes |
| **Yahoo options archive** (chunked delete from prod) | `fetch-av-options-backfill` Cloud Run Job active executions | After backfill quiesces |
| **`greeks_source` field on options response** | Wait for SPX Greeks backfill to populate `_computed` columns first | After backfill |
| **RSS news integration pipeline** | `scripts/probe_news_feeds.py` classified 19 feeds; next step is building the fetcher (`gcp/fetchers/fetch_rss_news.py`) and schema table | Design phase |

### 16.2 Plan-vs-code drift

| Plan | Drift |
| --- | --- |
| (none) | Plan #4 `glistening-munching-willow` was the only outstanding drift; closed by PRs #81 (gamma consolidation) and #92 (analytics + config routers). All TS deletions confirmed; both server endpoints live. See `docs/HARDCODED_VALUES_REMEDIATION.md` for the per-item closure log. |

### 16.3 README gaps

`README.md` covers backtest, lib, scripts, and end-to-end pipeline well but is **missing**:
- No mention of Cloud Run Jobs catalog
- No mention of Cloud SQL tables / schema
- No mention of Cloud Scheduler triggers
- No mention of Discord webhook alerts
- No mention of Vertex AI / multi-agent pipeline
- No mention of options Greeks computation
- No mention of the deterministic ranker
- No mention of the Catalysts page
- No GCP architecture overview
- No deployment instructions (Cloud Run + IAP)
- No production troubleshooting (Cloud SQL tier decisions, cost monitoring)

Recommended sections to add:
1. **Cloud Infrastructure** — GCP stack overview, jobs schedule, tables.
2. **Platform Features** — expand beyond the 12 routes to explain Insights, Catalysts, Ranker.
3. **Real-Time Monitoring** — Discord alerts, signal_monitor, premarket brief schedule.
4. **Deployment** — Cloud Run, IAP, local dev vs production.
5. **Cost & Performance** — Cloud SQL tier decision tree, scaling guidance.

### 16.4 Pre-existing test failures (NOT regressions)

Always verify against main before treating as branch issues:
- `test_pipeline_end_to_end_green` — LLM call count drift 12 → 13
- `test_health_returns_ok` — asserts `data_dir_exists`, missing in current API response
- `test_data_loader.py::TestLoadIntraday::test_returns_empty_when_no_data` — premise broken once Cloud SQL has real IWM data; should be deleted/rewritten, not perpetually waved through
- `test_platform_api.py` — most cases require Cloud SQL not reachable from sandbox

### 16.5 TradingView Pine Scripts

`tradingview-pine-scripts/` directory now contains the gamma-levels companion landed via PR #81:
- `gamma-levels-overlay-v2` — Pine v6 indicator that consumes `lib/gamma.py` outputs (King/Gate/Spot/Flip levels) for on-chart display
- `gamma-levels-overlay.md` — companion documentation

The original v1/v2 indicator pairs referenced in MEMORY.md still live in TradingView cloud, not in git. If/when re-imported, follow the same compliance rules below.

Compliance rules per memory `pine-script-rules.md`:
- Use `indicator()` not `study()` (v6 API)
- `ta.*`, `math.*`, `str.tostring()` namespaces; no `iff()`, no `transp`
- Line continuation indent must NOT be a multiple of 4 spaces
- No comma-separated statements (`hline(0), hline(30)` invalid)

---

## 17. Operations Runbook

### 17.1 Local development

```bash
# Authenticate (required once per shell)
set -a && source .env && set +a

# Start everything
make dev                              # Frontend + API together

# Or independently:
cd platform && npm run dev            # Vite, port 5173
cd platform && uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Standalone tools
cd options-heatseeker && npm run dev  # port 8101
cd success-report-site && python serve.py  # port 8102
python -m http.server 8103 -d chart-viewer
python -m http.server 8104 -d website
```

### 17.2 Cloud SQL access

```bash
# Connect via cloud-sql-proxy (preferred for ad-hoc)
cloud-sql-proxy adept-mountain-474619-d4:us-east1:trading-db &
psql -h localhost -p 5432 -U trading -d trading

# Or via gcloud
gcloud sql connect trading-db --user=trading

# Apply schema (idempotent — uses CREATE TABLE IF NOT EXISTS)
bash gcp/deploy.sh migrate

# Direct schema reload
psql ... -f gcp/schema.sql
```

Connection string in `.env`: `CLOUD_SQL_INSTANCE=adept-mountain-474619-d4:us-east1:trading-db`.

### 17.3 GCS access

```bash
# Pull all data locally (~7.6 GB)
gsutil -m cp -r gs://adept-mountain-474619-d4-trading-data/raw/data/ data/

# Pull a single ticker
gsutil -m cp -r gs://adept-mountain-474619-d4-trading-data/raw/data/spy/ data/spy/

# List by prefix
gsutil ls gs://adept-mountain-474619-d4-trading-data/raw/data/iwm/options/
```

### 17.4 Codespace specifics

Per memory `MEMORY.md`:
- `vite.config.ts` has `host: true` for Codespace network.
- CORS allows `*.app.github.dev`.
- Bash permissions: `"Bash(*)"` is allowed in `.claude/settings.local.json` and `~/.claude/settings.json`.

### 17.5 Common breakages and fixes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Daily Bias card shows "stale" during market hours | Live overlay failed (AV quote endpoint down) | Check `/api/live/status` response; verify `AV_API_KEY` set; check Cloud Run logs for `fetch-market-data` last run |
| Options dates endpoint returns empty | No rows in `etf_options_snapshots` for ticker on date | Verify `data_source='alphavantage'` rows exist; check `fetch-alphavantage-options-daily` last run; widening-range scan should fall back to oldest |
| `/api/health` reports `cloud_sql: false` | Connector not initialized | Verify `--add-cloudsql-instances` set on Cloud Run service; check IAM has `roles/cloudsql.client` |
| `/admin` returns 401 | `ADMIN_TOKEN` missing or wrong | Set via Secret Manager + Cloud Run env var |
| Cloud Run Job fails silently | Stale image (pre-migration) | `bash gcp/deploy.sh build` to rebuild + redeploy. Check digest with `gcloud run jobs describe` |
| GH Actions workflow fails repeatedly | Real bug or rate limit | Auto-issue created with last 50 log lines; auto-PR on `fix/workflow-{name}-{run}` branch |
| Playwright E2E "Auth required" against deployed URL | IAP cookies expired | Re-run `npm run e2e:cloud:auth` (interactive Google sign-in) |
| `tsc -b` fails with `defineConfig` errors | `vite.config.ts` not using `vitest/config` | Confirm `import { defineConfig } from 'vitest/config'` |
| Backtester returns no trades | Catalyst-analog matching needs catalyst data | Verify `news_sentiment`, `earnings_history`, `sec_filings` populated for the ticker/date |
| Test `test_pipeline_end_to_end_green` fails | LLM call count drift (pre-existing) | Verify against main — not a regression |

### 17.6 Deploys

```bash
# Build + push image
bash gcp/deploy.sh build

# Apply schema
bash gcp/deploy.sh migrate

# Deploy fetchers (Cloud Run Jobs + scheduler triggers)
bash gcp/deploy.sh fetchers

# Deploy failure notifier
bash gcp/deploy.sh notifier

# Deploy unified web service (with IAP)
bash gcp/deploy.sh platform

# Verify post-deploy
curl https://trading-platform-...run.app/api/health
gcloud run services describe trading-platform --region us-east1
```

### 17.7 Ports inventory

| Port | Service |
| --- | --- |
| 5173 | Platform frontend (Vite dev) |
| 8000 | Platform API (FastAPI) |
| 8101 | Options Heatseeker |
| 8102 | Success Report |
| 8103 | Chart Viewer |
| 8104 | Trading Dashboard (legacy website) |

---

## 18. Conventions & Glossary

### 18.1 Strat & FTFC terms

- **Strat candle** — Rob Smith's candle classification (1, 2u, 2d, 3). Encodes whether a bar broke prior bar's high, low, both, or neither.
- **FTFC (Full Timeframe Continuity)** — Multi-timeframe alignment score in `[-1, 1]`. Weighted: Daily 0.35, 1 h 0.25, 15 m 0.20, 5 m 0.10, Weekly 0.10.
- **Combo** — A specific Strat candle sequence that's been historically profitable (e.g. "1-3-2u").
- **Setup** — A multi-condition trade pattern (e.g. "FTFC max conviction", "ORB breakout").

### 18.2 Signal score scale

| Score | Meaning |
| --- | --- |
| 0–2 | No entry |
| 3 | Weak (25% size) |
| 4 | Weak (50% size) |
| 5 | Medium (50–75%) |
| 6–7 | Strong (75–100%) |
| 8 | Very Strong (100%) |

`base_score` (3-of-5 voter): 0–5. `strat_bonus`: 0–3. `total = base + bonus`.

### 18.3 Key data fields

- `data_source` — Provenance tag on options/intraday rows. Values: `alphavantage`, `yfinance`/`yahoo` (legacy), NULL (legacy Yahoo intraday), `derived_put_call_parity` (SPX backfill).
- `mark` — Mid-price between bid and ask on options snapshots.
- `stale_days` — Trading days (NOT calendar days) since the underlying data updated.
- `live` block — `{ price, session, updated_at, source }` returned by dashboard brief during market hours.
- `greeks_source` — Planned field to indicate whether Greeks came from AV (`alphavantage`) or BSM compute (`computed_bsm`). SPX uses computed.

### 18.4 Commit conventions

Per CLAUDE.md and memory:
- **Format:** Conventional commits — `type: description` (e.g. `fix: resolve API timeout issue`)
- **No Claude branding** — no "built by Claude", "generated by Claude", no 🤖 emoji
- Message focuses on the **why**, not the **what**
- Prefer creating new commits over amending
- Stage files explicitly (avoid `git add -A` / `git add .` to skip secrets)

### 18.5 Branch naming

- `feature/short-description` for new features
- `fix/short-description` for bug fixes
- `fix/workflow-{name}-{run-number}` for auto-created failure-handler branches
- Never commit non-trivial changes directly to `main`

### 18.6 File-management philosophy (CLAUDE.md)

1. **Read before writing** — explore existing files first.
2. **Extend, don't duplicate** — add to existing modules.
3. **One place, one purpose** — keep related functionality together.
4. **Last resort** — only create new files when absolutely necessary.

### 18.7 Reference document map

| Doc | Use it for |
| --- | --- |
| `README.md` (repo root) | Quickstart, backtest mechanics, lib/scripts overview |
| `QUICK_REFERENCE.md` (repo root) | Strat candles, FTFC weights, signal scoring, position sizing, gamma quick-reference |
| `BACKTEST_RESULTS.md` (repo root) | Full 10-year backtest table |
| `INFRASTRUCTURE_NOTES.md` (repo root) | Cloud SQL tier decisions, query performance, scaling triggers |
| `CLAUDE.md` (repo root) | Project rules, automation, GH workflow patterns |
| `docs/GCP_IMPLEMENTATION_GUIDE.md` | GCP architecture deep-dive, schema, costs |
| `docs/GCP_IMPLEMENTATION_STATUS.md` | Phase-by-phase migration tracker |
| `docs/INVESTMENT_MODELS_SUMMARY.md` | 5-model system, 195 features breakdown |
| `docs/MODEL_SUMMARY.md` | Concise model overview |
| `docs/DESIGN_SYSTEM.md` | "The Obsidian Analyst" theme, color tokens, typography |
| `docs/API.md` | FastAPI router/endpoint catalog (PR #92) |
| `docs/DATA_PIPELINE.md` | Per-table freshness plan, canonical writers, watchdog (PR #87) |
| `docs/FAILURE_NOTIFIER_DEPLOYMENT.md` | Pub/Sub failure-notifier deployment + smoke test (PR #82) |
| `docs/HARDCODED_VALUES_REMEDIATION.md` | Plan #4 closure log, server-side math architecture (PR #81) |
| `docs/gamma_levels.md` | King/Gate/Spot/Flip canonical reference, sign convention, spot estimation (PR #81) |
| `docs/claude-code-codespaces-auth.md` | Codespaces + Claude Code OAuth setup (PR #87) |
| `docs/incidents/` | Postmortems — currently `2026-04-14-market-data-daily-gap.md` (PR #87) |
| `docs/alpha-vantage-*.md` | AV fetcher quickstart + workflow guides |
| `docs/options_chain_guide.md` | yahooquery vs yfinance, options data format |
| `docs/trading_rules_and_alerts.md` | Time windows, conditions, position sizing |
| `docs/quick_reference_card.md` | Compact decision flow |
| `docs/QUICK_START_OPTIONS.md` | Options analytics quickstart |
| `docs/README_OPTIONS.md` | Options module overview |
| `docs/GOOGLE_SHEETS_SETUP.md` | Google Sheets API credentials |
| `docs/Morning Checklist Updated.md` | Pre-market routine + probability stats |
| `docs/changelog/` | Weekly session notes (commit-anchored) |
| `docs/BRIEFING_DECK.md` | This document — full system reference |

---

**End of briefing deck.**

Compiled from: 17 plans (`~/.claude/plans/`), 2 changelog files, source code as of 2026-04-26 post-PR-#99 (branch `main`, HEAD includes PRs #96–#99), `gcp/schema.sql` (31 tables), all 14 GitHub workflow YAMLs, `MEMORY.md`, `HARDCODED_VALUES_REMEDIATION.md`, `gamma_levels.md`, and the 22 `docs/` reference files.
