# Capability, Data-Flow & Gap Matrix

**Purpose:** A single, scannable map of *what the system has today*, *how data flows in and out*, *what's required to run it*, *where the surfaces align*, and *where the gaps are* — intended as the input scaffold for a PRD.

**Scope:** The whole ecosystem, with every surface treated as a peer: the React/FastAPI web platform, the shared `lib/` backend, the GCP Cloud Run jobs + fetchers, the AI insight pipeline, the Discord bot, the TradingView Pine scripts, and the Google Apps Script sheets.

**Generated:** 2026-06-19 from a fresh read-only code inventory. Synthesizes (does not duplicate) the existing docs — see [§9](#9-existing-documentation--what-this-replaces-vs-references).

**Validated:** Code claims (routes, endpoints, `lib/` modules, fetchers, auth) were read from **live source on `main`** (2026-06-19), not from the docs. GCP/DB claims were validated against **live state** on 2026-06-19 via `gcloud run jobs list` (69), `gcloud run services list` (4), `gcloud scheduler jobs list` (78), and a live `information_schema` query (83 base tables). Where live state exceeds a figure in `ARCHITECTURE.md`, the live number is used here and the stale doc is flagged in §9. Per-job *schedules/timeouts* below are read from `deploy.sh` (intended state); the authoritative live job list is `ARCHITECTURE.md`, which needs regeneration (G14).

**Legend:** ✅ present / live · ◐ partial or indirect · ❌ absent · — N/A

---

## 1. Surfaces map

Seven surfaces consume the shared `lib/` spine. They differ wildly in how much of `lib/` they expose to a human.

| # | Surface | Type | Tech | Auth | Status |
|---|---|---|---|---|---|
| S1 | **Web platform** | Unified analytics UI + control plane | React (Vite) + FastAPI, Cloud Run service `trading-platform` | Prod: Google IAP · Staging: passcode bypass · Local: open | ✅ live (prod 100% on rev `00049`; merged `main` staged on rev `00058`) |
| S2 | **`lib/` backend** | Shared math/logic spine | Python package | — (imported) | ✅ the single source of truth for all financial math |
| S3 | **GCP jobs + fetchers** | Batch data + analytics | **69 Cloud Run Jobs, 78 schedulers** (live 2026-06-19) | Service account | ✅ live (1 scheduler PAUSED — G16) |
| S4 | **AI insight pipeline** | Multi-agent advisory | 11-node async orchestrator (`lib/agents`) | via job / API | ✅ live (daily 08:45 + on-demand) |
| S5 | **Discord bot** | Conversational + alerting | Cloud Run service `discord-interactions` + webhooks | Ed25519 signature | ✅ live (5 slash commands, 3 channels) |
| S6 | **TradingView Pine** | Chart overlays / scanners | Pine v6 (standalone) | TradingView account | ✅ live (4 scripts, user-maintained) |
| S7 | **Google Apps Script** | Sheet automation | Apps Script (clasp) | Google account | ✅ live (siloed — EarningsWhispers tracking) |

**Key structural fact:** S2 (`lib/`) is where the capability *exists*; S1/S3/S4/S5 *re-expose* it. S6 and S7 are **not** wired to `lib/` at all — they re-implement or operate independently. This is the root of most alignment gaps in [§7](#7-alignment-matrix-capability--surface).

---

## 2. Capability inventory — the web platform (S1), page by page

| Route | Page | Capability | Calls (API) | Backing data |
|---|---|---|---|---|
| `/` | Dashboard | Premarket brief, live signals, top playbook setup, daily KPIs, intraday candles, catalysts, AI take, news | `dashboard/brief`, `playbook`, `signals`, `market/*`, `catalysts/events`, `insights/report`, `live/*` | `premarket_analysis`, `market_data_*`, `signal_alerts`, `insight_reports` |
| `/live` | Live Market | Live conditions, indicator scorecards, pre/after-hours, strategy condition checks | `live/status|quote|history|avg-volume`, `live/indicators` (POST) | AlphaVantage proxy + `lib.indicators` |
| `/charts` | Charts | Intraday OHLC + volume, indicators, **gamma levels**, similar setups, backtest equity, manual journal drawing | `market/*`, `options/{t}/{d}/levels`, `backtest/results|equity` | `market_data_intraday`, `etf_options_snapshots`, GCS backtest |
| `/options` | Options Flow | Heatseeker (swing/trinity), Flowseeker (live drilldown), Profiles (chain ladder) | `options/{t}/grid|nodes|dates`, `options/{t}/{d}/grid|nodes` | `etf_options_snapshots`, `v_etf_options_node` |
| `/playbook` | Playbook | Live setup cards, condition eval, win-rate/avg-return by hold-window, trade levels | `playbook/{t}`, `playbook/evaluate` (POST), `live/*` | `playbook_cards` / GCS `phase6_playbook_*.md` |
| `/signals` | Signals | Historical signals table + filters, 90-day P&L summary | `signals/{t}`, `analytics/summary/{t}` | `historical_signals` |
| `/journal` | Journal | Manual trade log, P&L, CSV export | `journal/trades/*`, `journal/export` | `journal_entries` (+ local fallback) |
| `/insights` | Insights | AI multi-agent reports, watchlist, history, refresh/re-analyze, divergence vs brief | `insights/report|reports|history|refresh|runs`, `insights/watchlist*`, `insights/ticker/*` | `insight_reports`, `insight_runs`, `model_routing` |
| `/catalysts` | Catalysts | Earnings, econ events, news, SEC filings, insider calendar, impact ranking | `catalysts/events|ticker|types|snapshot` | `earnings_calendar`, `economic_events`, `sec_filings`, `insider_transactions` + Benzinga live |
| `/reports` | Reports | Phase 1–7 analysis markdown viewer | `reports/list`, `reports/{t}/{phase}` | GCS `reports/phase*_{t}_*.md` |
| `/admin` | Admin | Model-routing dashboard, on-demand strat-engine predict, structure-brief | `admin/routes|models|structure-brief|strat-engine/*` | `model_routing` + GCS strat-engine snapshots |
| `/help` | Help | Glossary (indicators, candles, FTFC, PMG, performance) | `config/indicators|market-hours` | `lib.config` |
| `/settings` | Settings | Theme, nav, density, accent (client-only) | — (localStorage) | — |

**Routers (13):** `live`, `dashboard`, `playbook`, `signals`, `options`, `grid`, `catalysts`, `insights`, `journal`, `backtest`, `config`, `admin`, `analytics`, plus `health`, `glossary`, `magnitude` and `market`/`me`/`auth` in `main.py`. ~50 endpoints total.

---

## 3. Data flow IN — external source → table

The system is **AlphaVantage-primary** (premium tier; realtime-options on the $199.99/mo tier), with FRED, ForexFactory, SEC EDGAR, Benzinga, EarningsWhispers, and Unusual Whales as specialized feeds.

| External source | Fetcher | Cadence | Table(s) written |
|---|---|---|---|
| AlphaVantage TIME_SERIES_DAILY/INTRADAY | `fetch_market_data`, `fetch_alphavantage_intraday`, `fetch_premarket_refresh` | nightly + intraday | `market_data_daily`, `market_data_intraday` |
| AlphaVantage HISTORICAL_OPTIONS | `fetch_av_historical_options` | daily 21:00 UTC | `etf_options_snapshots` (EOD) |
| AlphaVantage REALTIME_OPTIONS | `fetch_av_realtime_options` | every 5 min, RTH | `etf_options_snapshots` (REALTIME) |
| AlphaVantage EARNINGS / INSIDER / TOP_MOVERS / NEWS_SENTIMENT | `fetch_earnings_*`, `fetch_insider_transactions`, `fetch_top_movers`, `fetch_news_sentiment` (ticker/earnings/topic modes) | daily / hourly | `earnings_*`, `insider_transactions`, `top_movers_daily`, `news_sentiment` |
| FRED DGS3MO | `fetch_fred_rates` | daily 06:30 UTC | `daily_rates` (risk-free rate for Greeks) |
| ForexFactory + FRED releases | `fetch_economic_events` | daily 07:00 ET | `economic_events` |
| SEC EDGAR | `fetch_sec_filings` | 4× daily | `sec_filings` |
| EarningsWhispers + Unusual Whales | `fetch_earnings_calendar` | daily/weekly | `earnings_calendar` |
| **Derived/materialized** (no external call) | `backfill_daily_indicators`, `compute_earnings_reactions`, `build_options_daily_greeks|features`, `build_realtime_gex`, `build_intraday_gex|flow` | daily/research | indicator cols, `earnings_reactions`, `etf_options_daily_greeks`, `options_daily_features`, `*_gex_15m`, `intraday_flow_15m` |

**Volume markers:** `etf_options_snapshots` ≈ 14M rows/yr (~52 GB at scale; REALTIME pruned to 30 d); `market_data_intraday` ≈ 8M rows (~50 GB); `market_data_daily` ≈ 750k rows.

---

## 4. Data flow OUT — what the system emits

| Channel | Producer(s) | Payload |
|---|---|---|
| **Discord — insights** (`DISCORD_WEBHOOK_URL`) | premarket-brief, earnings-reactions-brief, earnings-long-watchlist, insight-discord-push, weekend-review, validate-brief, failure-notifier | Market brief, earnings digest, AI insights, recaps, failure alerts |
| **Discord — signals** (`..._SIGNALS_URL`) | signal-monitor, eod-resolver, signal-quality-alarm, signal-replay | Entry/exit alerts, ORB, EOD close, quality regressions |
| **Discord — earnings** (`..._EARNINGS_URL`) | premarket-brief (earnings embed) | Earnings reporters digest |
| **GCS** `gs://{PROJECT}-trading-data/` | audits (`reports/`), backtests (`backtest/`), models (`magnitude-models/`), query results (`query-results/`), backups (`sql-dumps/`) | Artifacts, trained models, ad-hoc query output, weekly pg_dump |
| **GitHub issue comments** | audit-walkforward, audit-brief-bias | Per-factor IC/Sharpe tables, bias tallies |
| **Cloud SQL** | all fetchers + pipeline jobs | UPSERT into 30+ tables (primary persistent state) |
| **HTTP/JSON** | `trading-platform` FastAPI | All `/api/*` responses to the web UI |

---

## 5. URL / endpoint map

| Layer | URL |
|---|---|
| Prod web (IAP) | `https://trading-platform-5sjtb3yl7a-ue.a.run.app` (custom: `stocks.insightscollective.org`) |
| Staging revision (IAP, 0% traffic, merged `main`) | `https://staging---trading-platform-5sjtb3yl7a-ue.a.run.app` |
| Public staging service (passcode — **currently mis-configured**, see Gap G1) | `https://trading-platform-staging-5sjtb3yl7a-ue.a.run.app` |
| Discord interactions | Cloud Run service `discord-interactions` (`/discord/interactions`) |
| Cloud Run services (4, live) | `trading-platform`, `trading-platform-staging`, `discord-interactions`, `failure-notifier` |
| Frontend routes | 13 (see [§2](#2-capability-inventory--the-web-platform-s1-page-by-page)) |
| API endpoints | ~50 across 16 routers (`/api/*`) |

---

## 6. What's required to run it

| Category | Requirement |
|---|---|
| **Database** | Cloud SQL `trading-db` (Postgres 15, us-east1), DB `trading`, `pgvector` ext, schema seeded from `gcp/schema.sql`; **83 base tables live** (validated 2026-06-19; `DATA_DICTIONARY.md` listed 81 as of 06-09). Access via Cloud SQL Connector (Unix socket). |
| **Service account** | `trading-runner@` with `cloudsql.client`/`editor`, `run.developer`, `storage.objectAdmin`, `logging.logWriter`, `cloudscheduler.jobRunner`, `artifactregistry.writer`. **Platform deploy also needs `iam.serviceAccountUser` on `trading-platform-svc@`** (see Gap G1). |
| **Secrets** | `db-trading-pass/user`, `av-api-key` (+ `alpha-vantage-api-key` alias), `discord-webhook-*`, `discord-app-id/public-key/bot-token`, `fred-api-key`, `benzinga-api-key`, `staging-passcode` (**missing — Gap G1**). |
| **Env vars** | `CLOUD_SQL_CONNECTION_NAME`, `DB_USER/NAME`, `GCS_BUCKET`, `GCP_PROJECT_ID`, `IAP_OAUTH_CLIENT_ID`, plus per-job tuning (`INSIGHT_AUTO_REFRESH_TOP_N`, `RETENTION_DAYS`, etc.). |
| **External APIs** | AlphaVantage (premium + realtime-options tier), FRED, ForexFactory, SEC EDGAR, Discord, Vertex AI (default LLM). EarningsWhispers / Unusual Whales / Benzinga optional. |
| **Images** | `trading-system:latest` (jobs) and `trading-system:research` (adds lightgbm/sklearn/scipy/shap); `trading-platform` (web). |
| **Infra** | Artifact Registry, ~50 Cloud Scheduler entries, Cloud Tasks `insight-pipeline-queue`. |

---

## 7. Alignment matrix — Capability × Surface

Rows = capabilities (mostly living in `lib/`). Columns = surfaces. This is the heart of the gap analysis: it shows where a capability is *computed* but **not exposed** to a given audience.

| Capability (lib module) | Web API (S1) | GCP jobs (S3) | AI insights (S4) | Discord (S5) | Pine (S6) | Sheets (S7) |
|---|---|---|---|---|---|---|
| Indicators — RSI/EMA/ATR/VWAP/StochRSI/RVOL (`indicators`) | ✅ `/live/indicators`, `/config` | ✅ | ◐ (analyst context) | ◐ (via brief) | ◐ re-implemented | ❌ |
| Gamma GEX/VEX nodes, flip (`gamma`) | ◐ `/options/{}/levels` only | ✅ | ◐ (options analyst) | ◐ | ◐ flip overlay only | ❌ |
| Strat candles + combos + FTFC (`strat`) | ❌ | ✅ | ✅ (strat analyst) | ◐ (in brief) | ❌ no Strat | ❌ |
| Signal scoring — momentum + mean-reversion (`signals`, `strategies/*`) | ❌ | ✅ signal-monitor | ◐ | ✅ live alerts + `/replay-signals` | ◐ lane scanner (own thresholds) | ❌ |
| Strat levels / PMG / room-to-run (`strat_levels`) | ❌ | ✅ | ◐ | ◐ | ◐ session levels (own) | ❌ |
| Backtest + walk-forward (`backtest`, `walk_forward`) | ◐ `/backtest/results` (static only) | ✅ | ❌ | ✅ `/backtest` cmd | ❌ | ❌ |
| Options Greeks + intraday repricing (`options_greeks`, `options_intraday`) | ◐ `/options/greeks` (on-demand calc) | ◐ | ◐ | ❌ | ❌ | ❌ |
| Earnings reactions / playability (`earnings_reactions`) | ❌ | ✅ | ◐ (catalyst analyst) | ✅ earnings briefs | ❌ | ◐ EW tracking (own) |
| Playbook cards (`phase6_playbook`) | ✅ `/playbook` | ✅ builder + resolver | ❌ | ❌ | ❌ | ❌ |
| AI insight report (`agents/*`) | ✅ `/insights/*` | ✅ pipeline job | ✅ (is the pipeline) | ✅ daily push | ❌ | ❌ |
| Candidate ranking (`agents/ranker`) | ❌ | ✅ auto-refresh | ◐ | ❌ | ❌ | ❌ |
| Combo mining (`combo_mining`) | ❌ | ✅ research | ❌ | ❌ | ❌ | ❌ |
| Gamma-proximity alerts (`strategies/gamma_proximity`) | ❌ | ✅ signal-monitor | ❌ | ◐ | ❌ | ❌ |
| Premarket bias / ORB (`strategies/brief_bias`) | ◐ (in brief payload) | ✅ | ◐ | ✅ brief | ◐ ORB scanner (own) | ❌ |
| Exec backtest / options-exec (`exec_backtest`, `options_exec_backtest`) | ❌ | ◐ on-demand | ❌ | ◐ | ❌ | ❌ |
| Intraday features — GEX/flow/fracdiff (`features/*`) | ❌ | ✅ materialized | ◐ | ❌ | ❌ | ❌ |
| Magnitude ML (`strat_engine`, `magnitude_engine`) | ◐ `/magnitude/*`, `/admin/strat-engine` | ✅ | ❌ | ❌ | ❌ | ❌ |

**Reading the matrix:** the web UI (S1) column is the sparsest among the "should-be-rich" rows — a large fraction of `lib/` capability is computed in jobs (S3) and consumed by AI insights (S4) but has **no web endpoint**. That's the PRD opportunity space, enumerated next.

---

## 8. Gap register (PRD candidates)

Each gap: current state → target → effort (S/M/L) → why it matters.

### Tier 0 — Broken / blocking

- **G1 · Auth is half-configured; no working sign-in or logout.**
  *Current:* No Firebase code exists anywhere in the repo (the `AuthGate`/`SignInScreen` on `main` are the **passcode** screen). The public staging service has leftover `AUTH_MODE=firebase` + `AUTH_OPEN_SIGNUP=1` env with **no code behind it**, is **missing `ALLOW_AUTH_BYPASS=1`**, and the **`staging-passcode` secret was deleted** — so neither auth path activates, the gate falls through, and users land in the app with no sign-in and no logout. The `deploy-platform-staging` trigger also lacked `iam.serviceAccountUser` on `trading-platform-svc@` (fixed 2026-06-19).
  *Target:* Decide the real auth model (IAP-only for prod vs. a true app-level login). If a user-facing login is wanted, it must be built end-to-end (frontend screen **+** backend identity endpoint **+** session/logout). Restore `staging-passcode` + `ALLOW_AUTH_BYPASS=1` to make staging verifiable in the meantime.
  *Effort:* M (config restore) / L (real login). *Matters:* you currently cannot validate sign-in at all.

### Tier 1 — High-value capability exposure (compute exists, UI doesn't)

These are `lib/` capabilities that run in jobs/insights but have **no web endpoint** — the densest PRD vein.

- **G2 · Strat candles + FTFC API.** `lib/strat` is fully built and used by jobs/insights but unqueryable from the UI. → `GET /api/strat-candles?ticker&from&to&include_ftfc`. *Effort: M.*
- **G3 · Gamma nodes (full).** Only `/options/{}/levels` exists; raw `Level` structs (score, kind, tags, regime, flip) aren't exposed. → `GET /api/gamma-nodes`. *Effort: S.*
- **G4 · Historical signals with condition breakdown.** `/signals` returns rows but not *which* of the 5–7 conditions fired or the strategy-agreement detail. → extend `/signals` or add `/historical-signals?include_conditions`. *Effort: S–M.*
- **G5 · On-demand backtest.** `/backtest/results` is static GCS only; the engine can't be invoked from the UI (only Discord `/backtest`). → async `POST /api/run-backtest` + job polling (mirror the insights run pattern). *Effort: M.*
- **G6 · Strat levels / room-to-run API.** Computed in signal-monitor, invisible to UI. → `GET /api/strat-levels?ticker&as_of`. *Effort: M.*
- **G7 · Earnings playability/archetype API.** Powers briefs but not queryable. → `GET /api/earnings-playability?ticker&date`. *Effort: S.*
- **G8 · Candidate ranking API.** `agents/ranker` runs off-path in a cron; no way to re-rank or inspect score breakdowns. → `GET /api/rank-candidates?include_breakdown`. *Effort: M.*
- **G9 · Gamma-proximity alerts API.** King-approach / gate-break / flip-cross detection exists but isn't surfaced for review/backtest. → `GET /api/gamma-alerts`. *Effort: S.*
- **G10 · Intraday features API.** `features/intraday_gex|flow` materialized to tables but no feature-query endpoint. → `GET /api/features?ticker&date&features=`. *Effort: M.*

### Tier 2 — Cross-surface consistency

- **G11 · Pine scripts (S6) duplicate `lib/` logic with no single source of truth.** ORB, session levels, RSI/EMA thresholds are hard-coded in Pine and drift from `lib/strategies` configs; Pine has **no Strat** classification. *Target:* either generate Pine constants from `lib/config`, or document them as intentionally-independent. *Effort: M.* *Matters:* signal thresholds can silently diverge between chart and engine.
- **G12 · Google Apps Script (S7) is fully siloed.** EarningsWhispers tracking lives in Sheets, never reaching Cloud SQL or feeding the ranker/brief — duplicate of `earnings_calendar`/`earnings_reactions`. *Target:* decide keep-siloed vs. ingest EW-sheet outcomes into `earnings_calendar`. *Effort: M.*
- **G13 · No live-chat / streaming on AI insights (S4).** Async batch only. *Target:* if interactive Q&A over a report is desired, that's a streaming endpoint + UI. *Effort: L.*

### Tier 3 — Hygiene / docs

- **G14 · Stale docs.** `BRIEFING_DECK.md` (Apr 26) and `GCP_IMPLEMENTATION_STATUS.md` (Apr 29) predate the May expansion; `DATA_PIPELINE.md` (May 1) is 49 d old. The auto-regen `refresh-architecture-docs.yml` is reportedly not running. *Target:* regenerate or retire. *Effort: S.*
- **G15 · GuestBadge dead-render.** Renders only for the guest sentinel; with G1 unresolved it never shows. Tie its lifecycle to whatever auth model G1 settles on. *Effort: S.*
- **G16 · `signal-quality-report-hourly` scheduler is PAUSED (live).** The hourly signal-quality classification is **not currently running** (validated 2026-06-19); only the nightly mode (if its scheduler is enabled) would fire. The matrix's "signal quality" capability is therefore degraded in production. *Target:* decide resume vs. retire; if retire, remove the scheduler so it isn't mistaken for live. *Effort: S.* *Matters:* `signal-quality-alarm` depends on fresh `signal_metrics`; a paused producer can make the alarm silently no-op.

---

## 9. Existing documentation — what this replaces vs references

This matrix is a **synthesis layer**, not a replacement. Authoritative sources:

| Doc | Status | Relationship |
|---|---|---|
| `ARCHITECTURE.md` (2026-05-22) | **partially stale** | Inventory narrative still useful, but its counts (42 jobs / 49 schedulers) are **out of date** — live is 69 jobs / 78 schedulers (validated 2026-06-19). Needs regen (G14). |
| `docs/GCP_ARCHITECTURE.md` (2026-05-16) | current | Narrative topology companion. |
| `docs/API.md` | current | Endpoint reference — the per-endpoint contract source. |
| `docs/DATA_DICTIONARY.md` (2026-06-09) | current | 81 tables / 2,745 columns — the column-level source of truth. |
| `docs/PIPELINE.md` (2026-05-31) | current | Two-lane (live vs research) data/signal flow. |
| `docs/DATA_PIPELINE.md` (2026-05-01) | **stale** | Table-ownership/freshness; needs refresh (G14). |
| `docs/GCP_IMPLEMENTATION_STATUS.md` (2026-04-29) | **stale** | Superseded by ARCHITECTURE.md (G14). |
| `docs/BRIEFING_DECK.md` (2026-04-26) | **stale** | Narrative subset; consolidate or retire (G14). |

---

*This document is a point-in-time snapshot (2026-06-19). The alignment matrix (§7) and gap register (§8) are the PRD-input core; everything above them is the evidence base.*
