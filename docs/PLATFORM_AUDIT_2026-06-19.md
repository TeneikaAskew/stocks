# Platform Audit — "Stock Insights" (working name, TBD)

**Date:** 2026-06-19 · **Scope:** the repo `platform/` app (React/TS SPA + FastAPI backend).
**Note:** lab.learnthestrat.com / "Stratalyst", "Skylit", and the "@Glitch" social app are
**inspiration platforms**, not this product. Feature adoption from them is tracked separately in
[`FEATURE_ADOPTION_ROADMAP.md`](FEATURE_ADOPTION_ROADMAP.md).

## Stack
- **Frontend:** React 19 + TypeScript, React Router (13 lazy routes), `@tanstack/react-query`,
  Zustand stores, Tailwind v4, HeroUI shell (top-tabs nav + ⌘K command palette).
- **Charts:** `lightweight-charts` (candles/volume), `recharts` (area/line/equity), `d3`.
- **Backend:** FastAPI, 17 routers under `platform/api/routers/`, importing the shared `lib/`
  math spine; data in Cloud SQL (~55 tables) populated by `gcp/fetchers/`.
- **Auth:** `platform/api/auth.py` `AUTH_MODE` middleware (`firebase`/`iap`/`open`); `/api/me`
  returns server-verified `{email, is_admin}`. Per-user journal scoping via `current_user_email()`.

## Route-by-route inventory

### `/` Dashboard (`routes/DashboardPage.tsx`)
- **Features:** pre-market briefing strip; hero ticker; intraday chart with **Candles↔Area toggle**
  (`CandlestickChart` lightweight-charts / `PriceAreaChart` recharts); Live-signals card; Catalysts
  card; News-sentiment card; sector-rotation / AI-take / news 3-col grid; global ticker selector;
  review-date picker.
- **Charts:** intraday candlestick or area (60-min bars, last 2 RTH sessions, volume overlay).
- **Tables/cards:** live signals (Time/Dir/Score/Return), catalysts (Date/Title/Ticker/Impact),
  news (Title/Ticker/Sentiment).
- **Data:** `dashboard/brief/{ticker}`, `playbook/{ticker}`, `signals/{ticker}`,
  `catalysts/events`, `market/reference`, `market/data` → `premarket_analysis`, `signal_alerts`,
  `economic_events`, `news_sentiment`, `market_data_*`.

### `/live` Live Market (`routes/LiveMarketPage.tsx`)
- **Features:** live quote card (Open/High/Low/Prev/Volume); 6 indicator tiles (EMA9/20/50,
  RSI14, StochRSI, ATR14); dual CALL/PUT **5-condition voter** cards with pass/fail dots;
  Live/Pause + Sound toggles; session badge; historical-review mode.
- **Charts:** none (metric-tile + voter layout).
- **Data:** `live/quote`, `live/history`, `live/indicators`, `live/status` → `market_data_intraday`,
  computed via `lib/indicators.py`.

### `/charts` Charts (`routes/ChartsPage.tsx`)
- **Features:** central **candlestick + volume** chart with overlays — TP1/2/3 + SL price lines,
  prev-day reference levels, **gamma King/Gate/Flip/Balance** lines, entry/exit trade markers,
  5-condition signal markers; side panel **Trades | Analytics**; date picker; TF buttons
  (1m/5m/15m/30m/1h); Vol/RTH/Ref/Gamma/Sig toggles; JSON/CSV export; "Mark Entry" drawing mode.
- **Charts:** candlestick (lightweight-charts) with multi-overlay price lines + markers; analytics
  KPI cards (win rate, P&L, profit factor, max win/loss).
- **Data:** `market/data`, `reference-levels`, `gamma-levels` → `market_data_intraday`,
  `strat_levels`, gamma via `lib/gamma.py` + `etf_options_daily_greeks`.

### `/options` Options Flow (`routes/OptionsFlowPage.tsx`)
- **Features:** segmented views — **Heatseeker** (Swing heatmap / Trinity ladder), **Flowseeker**
  (Live Feed / Contract Drilldown), **Profiles** (OI by strike).
- ⚠️ **Status:** Heatseeker-Swing + Flowseeker render **MOCK** data; **Profiles is real**.
- **Data:** `grid` router → `etf_options_daily_greeks`; `options` router → `etf_options_snapshots`.
  **#600 fixed the ~84× GEX inflation** (`max(snapshot_ts)` dedup) on the levels path.
- **Gap vs inspiration:** this is the primary target for the GEX-terminal / Heatseeker / Flowseeker
  adoption work (roadmap top-3).

### `/playbook` Playbook (`routes/PlaybookPage.tsx`)
- **Features:** strategy cards with live-evaluated conditions (pass/fail), win-rate & avg-return,
  progress bars; tinted by conditions-met. **#613** added **real target/stop win-rate** + trade
  levels via the typed `playbook_cards` table.
- **Data:** `playbook`, `playbook-batch`, `live/*` → `playbook_cards` + `lib/indicators.py`.

### `/signals` Signals (`routes/SignalsPage.tsx`)
- **Features:** sortable signals table (Time/Dir/Score/Price/RSI/EMA9/Volume); filters — min-score,
  direction (ALL/CALL/PUT), date range; 90-day P&L KPI tiles.
- **Data:** `signals/{ticker}`, `analytics trade-summary` → `signal_alerts`, `historical_signals`,
  `backtest_*`.

### `/journal` Journal (`routes/JournalPage.tsx`)
- **Features:** trade-entry form (dir, entry/exit date-time + price); entries table; **equity curve**
  (recharts, cumulative P&L%); CSV export. **Per-user** (scoped by `current_user_email()` after auth).
- **Data:** `journal/trades` CRUD → `journal_entries`.

### `/insights` AI Insights (`routes/InsightsPage.tsx`)
- **Features:** tabs **Briefing / Agents / History / Watchlist / Chat**; multi-card AI report
  (trade plan, key levels, strat, debate, persona plans, risk flags, similar trades); replay-as-of;
  streaming chat (chat/market/strategy/trade modes).
- **Data:** `insights/*` → `insight_reports`, `insight_runs`, `model_routing`, `watchlists`;
  `lib/agents/*`.
- ⚠️ **Gap:** the Watchlist tab is **not per-user** — see Findings.

### `/catalysts` Catalysts (`routes/CatalystsPage.tsx`)
- **Features:** date-grouped event timeline; Hot-Now section; filters — date range, min-impact,
  catalyst-type chips; sentiment indicators.
- **Data:** `catalysts/events`, `catalysts/types` → `economic_events`, `earnings_calendar`,
  `sec_filings`, `news_sentiment`, Benzinga.

### `/reports` Reports (`routes/ReportsPage.tsx`)
- **Features:** phase report list (sidebar) + markdown viewer.
- **Data:** `reports/list/{ticker}`, `reports/{ticker}/{phase}` (GCS markdown).

### `/admin` Admin (`routes/AdminPage.tsx`)
- **Features:** model-routing table (per agent-role provider+model dropdowns, save), structure
  brief, on-demand predict, model-state snapshot. Gated by server-side admin (token / IAP email).
- **Data:** `admin/routes`, `admin/models` → `model_routing`.

### `/help` Help (`routes/HelpPage.tsx`)
- **Features:** ~189-entry searchable glossary, category pills.
- **Data:** `glossary`, `config/indicators`.

### `/settings` Settings (`routes/SettingsPage.tsx`)
- **Features:** theme (dark/light), nav pattern (tabs/sidebar), density, accent swatches.
- **Data:** none — Zustand/localStorage only.

## Backend data spine (summary)
- **Market:** `market_data_daily` (+30 indicators incl. the `atr_20`/`rsi_30`/`volatility_5d`/
  `high_low_spread` cols restored by #578), `market_data_intraday[_spy/_iwm/_qqq/_spx/_other]`,
  `daily_rates` ← `fetch_market_data`, AlphaVantage, FRED.
- **Options/GEX:** `etf_options_snapshots`, `options_daily_features`, `etf_options_daily_greeks`,
  `intraday_gex_15m`, `realtime_gex_15m`, `intraday_flow_15m` ← AlphaVantage; `lib/gamma.py`.
- **Strat/signals:** `signal_alerts`, `historical_signals`, `signal_metrics`, `strat_levels`,
  `strat_features_{5m,15m,30m}` (scheduler restored by #622), `playbook_cards` (#613).
- **Earnings:** `earnings_calendar/history/reactions`, `earnings_options_*`, and the 3 mat-views
  from #624 (`earnings_event_outcomes`, `earnings_ticker_lean`, `earnings_upcoming_with_history`).
- **Catalysts/news:** `economic_events`, `news_sentiment`, `sec_filings`, `insider_transactions`,
  `top_movers_daily`.
- **AI:** `insight_reports(_history)`, `insight_runs`, `model_routing`.
- **User data:** `watchlists` (has `user_id`, default `'default'`), `journal_entries` (per-user),
  `trades`.
- **Backtest:** `backtest_*`, `walk_forward_results`, `regime_combo_results`, `strat_combo_results`.

## Findings / gaps
1. **Watchlist is not per-user (residual auth gap).** `journal_entries` is scoped via
   `current_user_email()` (#626), but the insights-router watchlist endpoints
   (`insights.py:492/568/600`) never pass a user id, so `_watchlist.py` falls through to
   `DEFAULT_USER_ID = "default"` — all users share one watchlist. **Fix:** thread
   `current_user_email(request)` into `wl_add`/`wl_remove`/`wl_load` (small, mirrors the journal
   pattern). *Flagged, not yet fixed.*
2. **Options Flow Heatseeker-Swing + Flowseeker are mock** — primary roadmap target.
3. **Operator rollout pending** for the merged data PRs — see roadmap / PR notes (#622 strat-engine
   scheduler + `strat_features` backfill; #624 earnings mat-views refresh + seed; #625
   magnitude-inference).
4. **Prod Firebase not live** — GCIP `authorizedDomains` lacks the prod domain and prod `AUTH_MODE`
   is not `firebase` yet (intentional until the frontend login + domain are set).
