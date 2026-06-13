# GCP Data Dictionary — Trading Platform

> Maps every frontend page of the React trading platform (`platform/src/`) to the
> GCP resources that back it: FastAPI endpoints (`platform/api/`), Cloud SQL tables
> (`gcp/schema.sql`), the Cloud Run **Jobs** that populate the data (`gcp/deploy.sh`),
> the external vendor APIs / LLMs, and the Secret Manager secrets each component needs.
>
> **Scope / source of truth.** Page→endpoint wiring is read from `platform/src/hooks/*.ts`
> and the `fetch()` / `useFetch` calls in `platform/src/routes/*.tsx` +
> `platform/src/components/**`. Endpoint→data wiring is read from `platform/api/routers/*.py`
> and `platform/api/main.py`. Secrets/sizing are from `gcp/deploy.sh` + `platform/deploy.sh`,
> cross-checked against **live GCP state** (`gcloud` over 443) captured 2026-06-05.
>
> **GCP project:** `adept-mountain-474619-d4` · **region:** `us-east1` ·
> **Cloud SQL instance:** `trading-db` (db `trading`) ·
> **GCS bucket:** `adept-mountain-474619-d4-trading-data`

---

## 0. The two Cloud Run *services* the UI lives behind (live state)

| Service | Region | What it is | Service account | Secrets mounted (`--set-secrets`) |
|---|---|---|---|---|
| **`trading-platform`** | us-east1 | The React SPA **and** the FastAPI backend, one container (`platform/Dockerfile`: Vite build → `platform/dist`, served by `uvicorn api.main:app` on :8080). This is the only service the browser talks to. | `28960574877-compute@developer.gserviceaccount.com` (**default compute SA**, *not* `trading-runner@`) | **`DB_PASS` ← `trading-db-pass:latest` ONLY** |
| `discord-interactions` | us-east1 | Discord slash-command webhook receiver (`gcp/discord_interactions`). Not part of the React UI. | `trading-runner@…` | DB + AV + Discord + `DISCORD_APP_ID/PUBLIC_KEY/BOT_TOKEN` |
| `failure-notifier` | us-east1 | Pub/Sub-driven GCP-job-failure → GitHub issue/PR sink (`gcp/failure_notifier`). Not part of the UI. | `trading-runner@…` | DB + `GITHUB_PAT`/`GITHUB_REPO` + `discord-webhook-gcp` |

> **Deploy source mismatch (intentional).** The `trading-platform` service is deployed by
> **`platform/deploy.sh`**, NOT by `gcp/deploy.sh` (which deploys the Jobs + the other two
> services). The two share env-var *names* (`CLOUD_SQL_CONNECTION_NAME`, `DB_USER`, `DB_NAME`,
> `GCS_BUCKET`, `GCP_PROJECT_ID`) but the platform service's secret surface is much smaller —
> see §0.1.

### 0.1 ⚠️ Load-bearing finding — what the `trading-platform` service can and can't do

Live `gcloud run services describe trading-platform` shows its env is exactly:
`CLOUD_SQL_CONNECTION_NAME`, `DB_USER=trading_user`, `DB_NAME=trading`, `GCS_BUCKET`,
`GCP_PROJECT_ID`, `PLAYWRIGHT_TESTER_SA`, `IAP_OAUTH_CLIENT_ID`, and **`DB_PASS` (secret)**.

Consequences for the data flows below:

1. **No `AV_API_KEY` / `ALPHA_VANTAGE_API_KEY` is mounted on the UI service.** Every
   endpoint that calls AlphaVantage *on the request path* returns **HTTP 503
   "Alpha Vantage API key not configured"** in production as currently deployed:
   `/api/live/quote`, `/api/live/history`, `/api/live/avg-volume` (AV fallback only),
   `/api/insights/ticker/search|info|quote`, `/api/options/live/...`, `/api/market/reference`
   (recent-date AV branch), and the `/api/options/.../grid` on-demand AV branch. These
   degrade to their **Cloud SQL** path where one exists (avg-volume, market/reference,
   options chain) and hard-fail where AV is the only source (live quote/history, ticker search).
   *This is the single biggest gap between "what the code can do" and "what prod serves."*
2. **No `ADMIN_TOKEN` is mounted.** The `/api/admin/*` routes fall back to IAP-email auth
   (`X-Goog-Authenticated-User-Email` == `teneika@bictech.org`). With no `ADMIN_TOKEN` set,
   a request lacking that IAP header gets **503 "ADMIN_TOKEN not configured"** (not 401).
3. **Vertex Gemini auth is via ADC**, i.e. the attached **default compute SA**'s identity —
   there is no Gemini API key. The insights pipeline that actually calls Vertex runs in the
   **`insight-pipeline` Job** (SA `trading-runner@`), not in this service; the only Vertex call
   the *service* itself makes is the `/api/insights/chat` streaming endpoint.
4. **Auth posture:** the service is IAM-gated (`--no-allow-unauthenticated`) with an
   `IAP_OAUTH_CLIENT_ID` wired for IAP. Secrets live server-side only; **the browser bundle
   contains no secrets** (confirmed — see §2).

---

## 1. Per-page mapping

12 pages, routed in `platform/src/App.tsx`. "Job(s) that populate the data" = the Cloud Run
Job(s) that write the Cloud SQL tables / GCS objects the page reads (the page itself never
writes them, except Journal).

| Page (route) | API endpoint(s) | Cloud SQL table(s) | GCP Job(s) that populate the data | Other GCP / external services | Secrets the data flow depends on |
|---|---|---|---|---|---|
| **Dashboard / Overview** (`/`) `DashboardPage.tsx` | `/api/dashboard/brief/{t}`, `/api/playbook/{t}`, `/api/signals/{t}`, `/api/catalysts/events`, `/api/market/reference/{t}/{d}`, `/api/market/data/{t}/{m}`, `/api/health/freshness`, `/api/me` | `premarket_analysis`, `market_data_daily`, `historical_signals`, `news_sentiment`/`earnings_calendar`/`sec_filings`/`insider_transactions`/`economic_events` (catalysts), `market_data_intraday` | `premarket-brief`, `fetch-market-data`, `backfill-daily-indicators`, `historical-signals-watchlist`, `fetch-news-sentiment*`, `fetch-earnings-calendar`, `fetch-sec-filings`, `fetch-insider-transactions`, `fetch-economic-events` | Cloud SQL; GCS (playbook md); **AlphaVantage** for the live-quote overlay (open-market only) | `db-trading-pass`; `av-api-key` (live overlay only — *unmounted on UI svc → overlay silently skipped*); `benzinga-api-key` (catalysts, optional) |
| **Live Market** (`/live`) `LiveMarketPage.tsx` | `/api/live/quote/{t}`, `/api/live/history/{t}`, `/api/live/avg-volume/{t}`, `/api/live/status`, `/api/live/indicators` (POST), `/api/market/data/{t}/{d}` | `market_data_daily` (avg-volume fallback), `market_data_intraday` (historical bars) | `fetch-market-data`, `backfill-daily-indicators`, `fetch-alphavantage-intraday` | **AlphaVantage** GLOBAL_QUOTE + TIME_SERIES_INTRADAY + TIME_SERIES_DAILY (request-path); `lib/indicators.py` for server-side indicators | `av-api-key` ⚠️ (*unmounted on UI svc → quote/history return 503 in prod*); `db-trading-pass` |
| **Charts** (`/charts`) `ChartsPage.tsx` | `/api/market/data/{t}/{d}`, `/api/market/dates/{t}`, `/api/market/reference/{t}/{d}`, `/api/options/{t}/{d}/levels`, `/api/options/greeks` (POST), `/api/signals/{t}/similar`, `/api/analytics/trade-stats` (POST), `/api/backtest/{all,results,equity}/{t}` (BacktesterSection), `/api/config/*`, `/api/glossary/gamma` | `market_data_intraday`, `market_data_daily`, `etf_options_snapshots`, `historical_signals`; backtest CSVs in **GCS** `raw/data/backtest_results/` | `fetch-market-data`, `fetch-alphavantage-intraday`, `fetch-av-options-backfill`/`fetch-av-options-realtime`, `historical-signals-watchlist`, `backtest` (writes the GCS CSVs) | Cloud SQL; **GCS** (backtest CSVs); `lib/gamma.py` (GEX/levels), `lib/indicators.py`; AV reference fallback | `db-trading-pass`; `av-api-key` (recent-date reference only) |
| **Options Flow** (`/options`) `OptionsFlowPage.tsx` | `/api/options/dates/{t}`, `/api/options/{t}/{d}`, `/api/options/live/{t}/{d}`, `/api/options/{t}/{d}/levels`, `/api/options/greeks` (POST) | `etf_options_snapshots` (`data_source='alphavantage'`, ~107M rows) | `fetch-av-options-backfill` (EOD, `av-options-daily` 21:00 ET), `fetch-av-options-realtime` (intraday, `av-options-realtime`) | Cloud SQL; **AlphaVantage** HISTORICAL_OPTIONS live proxy (fallback); `lib/gamma.py` | `db-trading-pass`; `av-api-key` (live proxy + on-demand grid — *unmounted on UI svc*) |
| **Signals** (`/signals`) `SignalsPage.tsx` | `/api/signals/{t}`, `/api/signals/{t}/similar` | `historical_signals` (~1.48M rows); GCS parquet fallback `raw/data/signals/` | `historical-signals-watchlist` (`scripts/run_historical_signals.py`) | Cloud SQL | `db-trading-pass` |
| **AI Insights** (`/insights`) `InsightsPage.tsx` | `/api/insights/report/{t}`, `/api/insights/reports/{id}`, `/api/insights/report/{t}/history`, `/api/insights/report/{t}/refresh` (POST→Tasks), `/api/insights/runs/{id}`, `/api/insights/chat` (POST stream), `/api/dashboard/brief/{t}` | `insight_reports` (568 rows), `insight_runs`, `insight_reports_history`, `model_routing`; reads of `market_data_daily`/`etf_options_snapshots`/`signal_alerts`/`news_sentiment`/`earnings_calendar`/`sec_filings`/`economic_events` inside the pipeline | **`insight-pipeline`** Job (refresh → Cloud Tasks → Job; daily `insight-pipeline-daily` 08:45 ET) | **Vertex AI Gemini** `gemini-3.1-flash-lite` (all 7 roles, live `model_routing`); **Cloud Tasks** (`insight-pipeline-queue`); Cloud Run Job; Cloud SQL; AV (ticker-info inside pipeline) | **Vertex via ADC SA** (no key); `db-trading-pass`; `av-api-key` (pipeline data); `admin-token` (only for /admin routing UI) |
| **Catalysts** (`/catalysts`) `CatalystsPage.tsx` | `/api/catalysts/events`, `/api/catalysts/types`, `/api/catalysts/ticker/{t}`, `/api/catalysts/asof/{t}` | `news_sentiment`, `economic_events`, `earnings_calendar`, `earnings_history`, `insider_transactions`, `sec_filings`, `market_data_daily` (+ local `data/catalysts/catalyst_calendar.json` cache) | `fetch-news-sentiment*`, `fetch-economic-events`, `fetch-earnings-calendar`, `fetch-earnings-history`, `fetch-insider-transactions`, `fetch-sec-filings` | **Benzinga** Calendar API (primary, optional); Cloud SQL; **FRED** (economic events upstream) | `db-trading-pass`; `benzinga-api-key` (optional); `fred-api-key` (economic upstream) |
| **Playbook** (`/playbook`) `PlaybookPage.tsx` | `/api/playbook/{t}`, `/api/playbook/evaluate` (POST), `/api/market/reference/{t}/{d}` | *none directly* — reads markdown from GCS | `premarket-brief` / research jobs write `phase6_playbook_{t}.md`; condition eval is pure `lib` math (`platform/api/routers/playbook.py`) | **GCS** `raw/reports/` (playbook markdown); Cloud SQL (reference fallback) | `db-trading-pass` (reference only); GCS via SA |
| **Reports** (`/reports`) `ReportsPage.tsx` | `/api/reports/list/{t}`, `/api/reports/{t}/{phase}` | *none* | research/phase jobs write phase report `*.md` to GCS | **GCS** `raw/reports/` (phase markdown) | (none beyond GCS SA) |
| **Journal** (`/journal`) `JournalPage.tsx` | `/api/journal/trades/{t}` (GET), `/api/journal/trades` (POST), `/api/journal/trades/{id}` (DELETE), `/api/journal/export/{t}` (POST) | **`journal_entries`** — *user-written via the UI* (not a Job). **Live count = 0 rows.** Local JSON fallback when Cloud SQL off. | *none* (the page is the writer) | Cloud SQL | `db-trading-pass` |
| **Admin** (`/admin`) `AdminPage.tsx` | `/api/admin/routes` (GET/PUT), `/api/admin/models`, `/api/admin/structure-brief`, `/api/admin/strat-engine/state`, `/api/admin/strat-engine/predict` (POST), `/api/me` | `model_routing` (routes); strat-engine reads `strat_features_*` on predict | `insight-pipeline` consumes `model_routing`; strat-engine artifacts written by the `strat-engine` research Job to GCS | Cloud SQL; **GCS** `research/strat_engine/` (model.pkl + metrics + structure_brief); `lib/agents/pricing.py` catalog | `admin-token` ⚠️ (*unmounted on UI svc → 503 unless IAP email matches*); `db-trading-pass` |
| **Help** (`/help`) `HelpPage.tsx` | `/api/glossary/gamma` (+ `<TermHover>` shared) | *none* | *none* — served from `lib/gamma_glossary.py` module constant | (static, in-process) | (none) |

**Cross-cutting calls present on most pages** (via shared components): `/api/glossary/gamma`
(`TermHover.tsx`), `/api/config/market-hours` (`CandlestickChart.tsx`),
`/api/health/freshness` (`DataPipelineStatus.tsx`), `/api/me` (`useUser`).

### 1.1 Mock / not-yet-wired surfaces (explicitly NOT backed by a live Job)

Grounded in in-code comments and the `platform/src/data/*Mock.ts` files:

| Surface | Page | Status | Evidence |
|---|---|---|---|
| **Flowseeker → Live Feed** (flow tape) | Options Flow | **MOCK** — "There is NO backend endpoint" | `components/options/FlowseekerTab.tsx:16`, `data/optionsFlowMock.ts` |
| **Flowseeker → Contract Drilldown** | Options Flow | **MOCK** | `components/options/ContractDrilldown.tsx:26`, `data/contractDrilldownMock.ts` |
| **Heatseeker → Swing Mode** (2-D strikes×expirations grid) | Options Flow | **MOCK** grid; real-data *overlay* via `/levels` when available for the focus symbol | `components/options/SwingMode.tsx:30-36`, `data/heatseekerMock.ts` |
| **Heatseeker → Trinity Mode** | Options Flow | **REAL** (`useGammaLevels` → `/api/options/{t}/{d}/levels`) | `components/options/TrinityTab.tsx`, `HeatseekerSection.tsx` |
| **Profiles** tab | Options Flow | **REAL** (Cloud SQL chain via `/api/options/...`) | `components/options/ProfilesTab.tsx` |
| **Admin structure-brief / strat-engine predict** | Admin | **DEV-ONLY, deploy-gated.** Not wired into any user route or scheduler; `available=false` until the Track B/C gate lifts (no scheduler writes `research/strat_engine/structure_brief_latest.json`) | `routers/admin.py:173-181`, `main.py:344-350` |
| **Journal** | Journal | **Functionally empty in prod** — `journal_entries` has 0 rows; data only appears once a user manually logs trades | live count = 0 |
| **Sector rotation** | (not a page) | Not present as a live endpoint | — |

---

## 2. Secrets inventory (GCP Secret Manager)

All 21 secrets in the project (live `gcloud secrets list`). "Browser-reachable?" answers the
audit question — **none are**: the React bundle ships no secrets; every secret is mounted into a
Cloud Run container at start via `--set-secrets` (resolved from Secret Manager, never in the JS
bundle and never in revision metadata). The browser only ever talks to the FastAPI, which holds
secrets server-side.

| Secret | What it's for | Consumed by (Cloud Run svc/job) | Browser-reachable? | Backs a page's data flow? |
|---|---|---|---|---|
| **`trading-db-pass`** | Cloud SQL password for `trading_user` — **the one secret the `trading-platform` UI service mounts** (`DB_PASS`) | `trading-platform` (UI) | **No** | **Yes — every Cloud-SQL-backed page** (Dashboard, Charts, Options, Signals, Insights, Catalysts, Journal, Admin) |
| `db-trading-pass` | Same DB password, different secret name; mounted as `DB_PASS` into all the **Jobs** + the other two services (`gcp/deploy.sh` `DB_SECRET_FLAG`) | all Jobs, `discord-interactions`, `failure-notifier` | No | Yes — indirectly (the Jobs that populate the tables) |
| `db-trading-user` / `cloud-sql-connection-name` | Non-secret DB username + instance conn-name, kept in SM for central rotation; injected as plain env on Jobs | all Jobs | No | Yes (DB connectivity) |
| **`av-api-key`** | **AlphaVantage** API key (realtime-options tier). Mapped to BOTH `AV_API_KEY` + `ALPHA_VANTAGE_API_KEY` | Jobs (fetch-market-data, fetch-av-options-*, fetch-alphavantage-intraday, insight-pipeline, …), `discord-interactions`. **⚠️ NOT mounted on `trading-platform`** | No | **Yes** — Live Market (quote/history), Options Flow (live proxy), Charts/Dashboard (reference, ticker search). *Request-path AV fails on the UI svc; Cloud-SQL-backed reads still work.* |
| **`admin-token`** | `ADMIN_TOKEN` for `/api/admin/*` model-routing UI. Mounted into `insight-pipeline` Job; **NOT on `trading-platform`** | `insight-pipeline` Job | No (browser sends it as `X-Admin-Token` from sessionStorage; the value lives server-side) | Admin page (⚠️ unmounted on UI svc → IAP-email auth is the only working path in prod) |
| `benzinga-api-key` | **Benzinga** catalyst calendar | catalyst fetchers / `BENZINGA_API_KEY` (optional) | No | Catalysts (optional/primary) |
| `fred-api-key` | **FRED** economic data | `fetch-fred-rates`, `fetch-economic-events` (optional) | No | Catalysts (economic events), Greeks risk-free rate |
| `ew-user` / `ew-pass` | Earnings Whispers login (paid) | earnings fetchers | No | Indirect (earnings calendar enrichment) |
| `sec-user-agent` | SEC EDGAR `User-Agent` header (required by SEC) | `fetch-sec-filings` | No | Catalysts (8-K filings) |
| `discord-webhook-insights` | Default `DISCORD_WEBHOOK_URL` (briefs/insights channel) | Jobs (premarket-brief, insight-discord-push, …) | No | No (push notifications, not page data) |
| `discord-webhook-signals` | Signals channel (`signal-monitor`, EOD resolver, QA) | signal jobs | No | No |
| `discord-webhook-earnings` | Earnings embed channel | earnings brief jobs | No | No |
| `discord-webhook-gcp` | GCP-job-failure channel | `failure-notifier` | No | No |
| `discord-app-id` / `discord-public-key` / `discord-bot-token` | Discord slash-command app identity / Ed25519 verify / bot token | `discord-interactions` service | No | No |
| `github-pat` / `github-repo` | Failure-notifier → GitHub issue/PR | `failure-notifier` | No | No |
| `gh-stocks-repo-pat` | Repo PAT used by the sandbox to dispatch workflows/`db-query` (ops only) | (sandbox tooling) | No | No |

**Secrets a *page's data* depends on (flagged):** `trading-db-pass` (all DB pages),
`av-api-key` (Live Market, Options Flow live, Charts/Dashboard reference + ticker search),
the **Vertex SA / ADC** (AI Insights generation — not a Secret-Manager key but the
default-compute-SA identity), `admin-token` (Admin), `benzinga-api-key` + `fred-api-key`
+ `sec-user-agent` (Catalysts, optional).

**Confirmation the UI never sees a secret:** the browser→server boundary is the FastAPI;
the admin token is the only secret-shaped value the browser handles and it is **entered by a
human into `sessionStorage`** (`useAdmin.ts`) — it is not in the build, not in `.env` baked
into the bundle, and is sent only as a request header.

---

## 3. "Search a stock → end-to-end" trace

Naming each GCP hop for the three flows the user called out. (⚠️ flags where the
currently-deployed `trading-platform` service is missing `AV_API_KEY` — see §0.1.)

### 3a. Search a stock (ticker autocomplete)
```
Browser  ──GET /api/insights/ticker/search?keywords=…&limit=8──▶  trading-platform (Cloud Run svc, FastAPI)
  hook: useTickerSearch (platform/src/hooks/useTickerSearch.ts)
  router: routers/insights.py::search_tickers → lib.ticker_info.search_tickers
  ──HTTPS──▶  AlphaVantage  SYMBOL_SEARCH        (needs AV_API_KEY)
  ◀── matches[] {symbol,name,type,region,currency,match_score}
```
GCP hops: **Cloud Run service (FastAPI)** → **AlphaVantage** (external). No Cloud SQL.
⚠️ On the deployed UI service `AV_API_KEY` is unmounted, so this 503s in prod today;
`av-api-key` must be added to `platform/deploy.sh` for autocomplete to work.

### 3b. Retrieve info (company info + quote)
```
/api/insights/ticker/{t}/info   → lib.ticker_info.get_ticker_info → AlphaVantage OVERVIEW   (cached in ticker_info table)
/api/insights/ticker/{t}/quote  → lib.ticker_info.get_quote       → AlphaVantage GLOBAL_QUOTE
/api/insights/ticker/{t}/peers  → lib.ticker_info.get_peers        → FinViz (cached)
/api/live/quote/{t}             → routers/live.py                  → AlphaVantage GLOBAL_QUOTE
/api/live/history/{t}           → routers/live.py                  → AlphaVantage TIME_SERIES_INTRADAY (1min ×100)
/api/market/data/{t}/{d}        → main.py::_load_date_data         → Cloud SQL market_data_intraday  (GCS parquet fallback)
/api/market/reference/{t}/{d}   → main.py::get_reference_levels    → AV TIME_SERIES_DAILY (≤30d) ELSE Cloud SQL market_data_daily
```
GCP hops: **Cloud Run svc** → **AlphaVantage / FinViz** (external) and/or **Cloud SQL**
(`market_data_intraday`, `market_data_daily`, `ticker_info`). Populating Jobs behind the
Cloud-SQL paths: **`fetch-market-data`** (daily, `fetch-market-data-daily` 23:00 ET),
**`fetch-alphavantage-intraday`** (`av-intraday-nightly`), **`backfill-daily-indicators`**
(`backfill-indicators-daily`). ⚠️ AV-path endpoints 503 on the UI svc without `av-api-key`.

### 3c. Pull AI insights (refresh → Vertex Gemini → read)
```
Browser ──POST /api/insights/report/{t}/refresh[?as_of=…]──▶  trading-platform (FastAPI)
  hook: useRefreshInsight
  router: routers/insights.py::refresh_insight_report
     1. INSERT insight_runs (status='queued')                       ── Cloud SQL
     2. _enqueue_cloud_task() ──▶ Cloud Tasks queue `insight-pipeline-queue`
          task = OAuth-authed POST to Cloud Run Jobs API:
          run insight-pipeline with env INSIGHT_RUN_ID, INSIGHT_TICKER[, INSIGHT_AS_OF]
     (returns {run_id, status:"queued"})
  Browser polls ──GET /api/insights/runs/{run_id}── every 3s (useRunStatus)

Cloud Tasks ──▶ Cloud Run Job `insight-pipeline` (gcp/insight_pipeline_job.py, SA trading-runner@)
  _run_on_demand → _run_one:
     • load_routes_snapshot()                                       ── Cloud SQL model_routing (7 roles)
     • run_insight_pipeline(ticker, as_of, snapshot)                ── lib/agents/orchestrator.py
         summarizers read market_data_daily / etf_options_snapshots /
         signal_alerts / news_sentiment / earnings_calendar /
         sec_filings / economic_events                              ── Cloud SQL
         each agent role (analyst/bull/bear/judge/trader/risk/portfolio_manager)
         ──▶ Vertex AI Gemini  gemini-3.1-flash-lite  (vertex_adapter, global endpoint, ADC SA)
     • _insert_report_history(...)                                  ── Cloud SQL insight_reports_history (append-only)
     • _upsert_report(...) ON CONFLICT(ticker,as_of)                ── Cloud SQL insight_reports
     • UPDATE insight_runs status='done', report_id=…               ── Cloud SQL

Browser (poll sees status='done') ──GET /api/insights/report/{t}──▶ FastAPI
  router: _fetch_latest_report → SELECT … FROM insight_reports ORDER BY as_of DESC LIMIT 1
  ◀── {ticker, as_of, report(JSONB), model_versions, cost_usd, latency_ms}
```
GCP hops in order: **Cloud Run svc (FastAPI)** → **Cloud SQL** (`insight_runs`) →
**Cloud Tasks** (`insight-pipeline-queue`) → **Cloud Run Job** (`insight-pipeline`) →
**Cloud SQL** (`model_routing` + source tables) → **Vertex AI Gemini** (`gemini-3.1-flash-lite`)
→ **Cloud SQL** (`insight_reports` + `_history`) → read back via **Cloud Run svc** → **Cloud SQL**.
Secrets/identity: **Vertex via the SA's ADC** (no API key), `db-trading-pass`/`av-api-key`
on the Job. Local-dev shortcut: if `google-cloud-tasks` import or enqueue fails, the FastAPI
runs the pipeline inline via `BackgroundTasks` (same code path).

> The separate **`/api/insights/chat`** endpoint (Insights page chat box) streams directly
> from the **FastAPI service** to **Vertex Gemini `gemini-3.1-flash-lite`** (`google-genai`,
> `vertexai=True`, ADC) — it does NOT go through Cloud Tasks or `insight_reports`.

---

## 4. GCP services summary

| GCP service | Used for |
|---|---|
| **Cloud Run — services** | `trading-platform` (React SPA + FastAPI, the only thing the browser hits); `discord-interactions` (slash-command webhook); `failure-notifier` (job-failure → GitHub). |
| **Cloud Run — jobs** (~50 live) | All data ingestion + analytics writers. Page-relevant: `insight-pipeline` (AI Insights), `fetch-market-data` + `fetch-alphavantage-intraday` + `backfill-daily-indicators` (price data → Dashboard/Charts/Live), `fetch-av-options-backfill` + `fetch-av-options-realtime` (Options Flow), `historical-signals-watchlist` (Signals), `premarket-brief` (Dashboard brief + Playbook md), `fetch-news-sentiment*`/`fetch-earnings-calendar`/`fetch-earnings-history`/`fetch-sec-filings`/`fetch-insider-transactions`/`fetch-economic-events`/`fetch-fred-rates` (Catalysts), `backtest` (Insights backtest panel), `auto-refresh-top-n` (pre-warms insight cache), `db-query` (ops SQL), `strat-engine` (research artifacts → Admin). |
| **Cloud SQL (Postgres `trading-db`)** | System of record for nearly every page. ~50 tables; page-critical: `market_data_daily`/`market_data_intraday`, `etf_options_snapshots`, `historical_signals`, `insight_reports`/`insight_runs`/`insight_reports_history`/`model_routing`, `premarket_analysis`, `news_sentiment`/`earnings_calendar`/`earnings_history`/`sec_filings`/`insider_transactions`/`economic_events`, `journal_entries`, `trades`, `watchlists`, `ticker_info`, `signal_alerts`. |
| **Vertex AI (Gemini)** | The LLM for AI Insights. Model `gemini-3.1-flash-lite` for all 7 agent roles (live `model_routing`), via `google-genai` in Vertex mode on the **`global`** endpoint. Adapter registry also supports Anthropic + OpenAI (`lib/agents/pricing.py` price table), but **only the Vertex adapter is registered** by the insights router/job, and the live routing table targets Vertex exclusively. |
| **Cloud Tasks** | `insight-pipeline-queue` — decouples the synchronous refresh request from the long-running `insight-pipeline` Job (max-attempts 2, max-concurrent 5). |
| **GCS (`…-trading-data`)** | Playbook + phase-report **markdown** (`raw/reports/`) for Playbook & Reports pages; backtest CSVs (`raw/data/backtest_results/`) for the Insights backtest panel; signals/market **parquet fallbacks** (`raw/data/…`); strat-engine **model artifacts** (`research/strat_engine/`) for Admin; `db-query` results + weekly `pg_dump` (`sql-dumps/`). Bucket prefix for app reads = `raw/` (`platform/api/gcs_reader.py`). |
| **Secret Manager** | All 21 secrets in §2, mounted into containers at start via `--set-secrets`. |
| **Cloud Scheduler** | ~55 cron triggers driving the Jobs above. Page-relevant cadences: `insight-pipeline-daily` 08:45 ET; `fetch-market-data-daily` 23:00 ET; `av-options-daily` 21:00 ET + `av-options-realtime` */5 9-15 ET; `backfill-indicators-daily` 02:30 ET; `premarket-refresh-daily`/`premarket-brief-daily`; `sec-filings-0700/1000/1300/1700`; `news-sentiment-*` hourly; `auto-refresh-top-n` 08:10 ET; `freshness-watchdog-hourly`. |
| **Artifact Registry** | Hosts `us-east1-docker.pkg.dev/.../trading/trading-system` (Jobs image) + `gcr.io/.../trading-platform` (UI image). |
| **Cloud Build** | Builds both images (`gcloud builds submit` via `platform/cloudbuild.yaml` and `gcp/deploy.sh build`). |
| **IAM / IAP** | `trading-platform` is IAM-gated; an `IAP_OAUTH_CLIENT_ID` is wired and the admin/`/me`/`/dev` routes read the `X-Goog-Authenticated-User-Email` IAP header. SAs: UI svc = default compute SA (Vertex ADC); Jobs = `trading-runner@`; sandbox dispatch = `claude-web@`. |

---

## 5. Live verification snapshot (captured 2026-06-05 over 443)

- `model_routing` (live): all 7 roles `analyst, bull, bear, judge, trader, risk,
  portfolio_manager` → **`vertex` / `gemini-3.1-flash-lite`**. Matches the `gcp/schema.sql`
  seed (lines 1112-1120).
- Row estimates (`pg_class.reltuples`): `etf_options_snapshots` ≈ **107.5M**,
  `market_data_daily` ≈ **3.46M**, `historical_signals` ≈ **1.48M**, `trades` = **1965**,
  `insight_reports` = **568**, `premarket_analysis` = **164**.
- Exact small-table counts: **`journal_entries` = 0** (Journal page empty in prod),
  **active `watchlists` = 16 tickers**.
- Freshness: `insight_reports` latest `as_of` = **2026-06-04 12:46 UTC**;
  `premarket_analysis` latest = **2026-06-04**; `market_data_daily` (SPY) latest =
  **2026-06-04** — all current to the prior trading day.
- Live `gcloud`: 3 Cloud Run services, ~50 Jobs, ~55 schedulers, 21 secrets (all enumerated above).

### Pages whose data is NOT actually populated by a live Job (call-outs)
1. **Journal** — `journal_entries` = 0 rows; data exists only after a user manually logs trades (no Job writes it).
2. **Options Flow → Flowseeker** (Live Feed + Contract Drilldown) — pure mock; no backend endpoint exists.
3. **Options Flow → Heatseeker → Swing Mode grid** — mock 2-D grid (real-data overlay only when `/levels` resolves for the focus symbol).
4. **Admin → structure-brief / strat-engine predict** — dev-only, deploy-gated; no scheduler writes the structure-brief snapshot, so cells render `available=false`.
5. **Reports / Playbook** — depend on phase/playbook **markdown in GCS**; populated by research/brief jobs, not a dedicated scheduled fetcher — if those md files are absent the pages 404.
6. **Everything AlphaVantage-on-request** (Live Market quote/history, ticker autocomplete, Options live proxy) — backed by a live external API, but **non-functional on the currently-deployed `trading-platform` service because `av-api-key` is not mounted there.**
