# Platform API Reference

The FastAPI app in [`platform/api/main.py`](../platform/api/main.py) is deployed twice from one image as `solyra-api-prod` (IAP) and `solyra-api-staging` (public, Firebase login); the services, the auth model and the deploy path are in [ARCHITECTURE.md §7](../ARCHITECTURE.md#7-cloud-run-services-auth-and-the-api). The tables below are rendered from the router files by `scripts/maintenance/doc_inventory.py` on every monthly refresh and must not be edited by hand; run `python -m scripts.maintenance.doc_inventory --insert docs/API.md` to update them now.

Live OpenAPI on a running instance: `/docs` and `/openapi.json`.

## Start the API locally

```bash
cd platform
set -a && source ../.env && set +a
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload   # AUTH_MODE defaults to open
```

## Routers

Every router mounts at the root (`prefix=""`) and carries its own `/api/...` paths.

<!-- inventory:routers:start -->
| Router | Routes | Methods | Path families |
|---|---|---|---|
| [`main.py`](../platform/api/main.py) | 10 | GET | `/api/health`, `/api/market`, `/api/me`, `/dev` … |
| [`admin.py`](../platform/api/routers/admin.py) | 12 | GET, POST, PUT | `/api/admin` |
| [`analytics.py`](../platform/api/routers/analytics.py) | 2 | GET, POST | `/api/analytics` |
| [`backtest.py`](../platform/api/routers/backtest.py) | 5 | GET, POST | `/api/backtest`, `/api/style` |
| [`catalysts.py`](../platform/api/routers/catalysts.py) | 5 | GET | `/api/catalysts` |
| [`config.py`](../platform/api/routers/config.py) | 3 | GET | `/api/config` |
| [`dashboard.py`](../platform/api/routers/dashboard.py) | 2 | GET | `/api/dashboard`, `/api/movement-statement` |
| [`earnings.py`](../platform/api/routers/earnings.py) | 9 | GET | `/api/earnings` |
| [`glossary.py`](../platform/api/routers/glossary.py) | 1 | GET | `/api/glossary` |
| [`grid.py`](../platform/api/routers/grid.py) | 5 | GET | `/api/options` |
| [`health.py`](../platform/api/routers/health.py) | 1 | GET | `/api/health` |
| [`insights.py`](../platform/api/routers/insights.py) | 13 | DELETE, GET, POST | `/api/insights` |
| [`journal.py`](../platform/api/routers/journal.py) | 9 | DELETE, GET, PATCH, POST | `/api/journal` |
| [`live.py`](../platform/api/routers/live.py) | 6 | GET, POST | `/api/live` |
| [`magnitude.py`](../platform/api/routers/magnitude.py) | 2 | GET | `/api/magnitude` |
| [`options.py`](../platform/api/routers/options.py) | 5 | GET, POST | `/api/options` |
| [`playbook.py`](../platform/api/routers/playbook.py) | 4 | GET, POST | `/api/playbook`, `/api/reports` |
| [`preferences.py`](../platform/api/routers/preferences.py) | 2 | GET, PUT | `/api/me` |
| [`profile.py`](../platform/api/routers/profile.py) | 2 | GET, PUT | `/api/me` |
| [`signals.py`](../platform/api/routers/signals.py) | 2 | GET | `/api/signals` |
| [`waitlist.py`](../platform/api/routers/waitlist.py) | 1 | POST | `/api/waitlist` |
| **Total** | 101 |  | 21 routers |
<!-- inventory:routers:end -->

## Routes

<!-- inventory:routes:start -->
| Method | Path | Defined | Purpose |
|---|---|---|---|
| `GET` | `/api/admin/data-sources` | [`platform/api/routers/admin.py:1204`](../platform/api/routers/admin.py#L1204) | Per-dataset freshness/coverage, aggregated from the shared audit. |
| `POST` | `/api/admin/data-sources/{source_id}/refresh` | [`platform/api/routers/admin.py:1330`](../platform/api/routers/admin.py#L1330) | Queue the dataset's Cloud Run fetcher job. |
| `GET` | `/api/admin/models` | [`platform/api/routers/admin.py:155`](../platform/api/routers/admin.py#L155) |  |
| `GET` | `/api/admin/routes` | [`platform/api/routers/admin.py:128`](../platform/api/routers/admin.py#L128) |  |
| `PUT` | `/api/admin/routes/{role}` | [`platform/api/routers/admin.py:135`](../platform/api/routers/admin.py#L135) |  |
| `POST` | `/api/admin/strat-engine/predict` | [`platform/api/routers/admin.py:498`](../platform/api/routers/admin.py#L498) | Run the frozen strat-engine type model for ONE bar. |
| `GET` | `/api/admin/strat-engine/state` | [`platform/api/routers/admin.py:481`](../platform/api/routers/admin.py#L481) | Operator snapshot of the on-shelf strat-engine model state. |
| `POST` | `/api/admin/strat-engine/structure-continuation` | [`platform/api/routers/admin.py:606`](../platform/api/routers/admin.py#L606) | Read-only, feature-flagged calibrated structure-continuation probability. |
| `GET` | `/api/admin/structure-brief` | [`platform/api/routers/admin.py:289`](../platform/api/routers/admin.py#L289) | Dev-only readout of the strat-engine type model's structure predictions. |
| `GET` | `/api/admin/users` | [`platform/api/routers/admin.py:842`](../platform/api/routers/admin.py#L842) | Every Firebase account + its stored role(s). |
| `PUT` | `/api/admin/users/{uid}/roles` | [`platform/api/routers/admin.py:886`](../platform/api/routers/admin.py#L886) | Replace an account's stored role. |
| `PUT` | `/api/admin/users/{uid}/status` | [`platform/api/routers/admin.py:958`](../platform/api/routers/admin.py#L958) | Enable or disable a Firebase account. |
| `GET` | `/api/analytics/summary/{ticker}` | [`platform/api/routers/analytics.py:126`](../platform/api/routers/analytics.py#L126) | Summarize rows from the ``trades`` table for a ticker. |
| `POST` | `/api/analytics/trade-stats` | [`platform/api/routers/analytics.py:118`](../platform/api/routers/analytics.py#L118) |  |
| `GET` | `/api/backtest/all/{ticker}` | [`platform/api/routers/backtest.py:298`](../platform/api/routers/backtest.py#L298) | List all backtest runs for a ticker, sorted by timestamp descending. |
| `GET` | `/api/backtest/equity/{ticker}` | [`platform/api/routers/backtest.py:219`](../platform/api/routers/backtest.py#L219) | Return equity curve from the most recent equity CSV for the given ticker, |
| `POST` | `/api/backtest/replay-trades` | [`platform/api/routers/backtest.py:419`](../platform/api/routers/backtest.py#L419) | Score the signed-in user's labeled journal trades against actual bars |
| `GET` | `/api/backtest/results/{ticker}` | [`platform/api/routers/backtest.py:169`](../platform/api/routers/backtest.py#L169) | Return trades from the most recent backtest CSV for the given ticker, |
| `GET` | `/api/catalysts/asof/{ticker}` | [`platform/api/routers/catalysts.py:498`](../platform/api/routers/catalysts.py#L498) | Unified point-in-time catalyst view for a ticker. |
| `GET` | `/api/catalysts/events` | [`platform/api/routers/catalysts.py:142`](../platform/api/routers/catalysts.py#L142) | Get catalyst events grouped by date. |
| `GET` | `/api/catalysts/snapshot/{ticker}` | [`platform/api/routers/catalysts.py:499`](../platform/api/routers/catalysts.py#L499) | Unified point-in-time catalyst view for a ticker. |
| `GET` | `/api/catalysts/ticker/{ticker}` | [`platform/api/routers/catalysts.py:461`](../platform/api/routers/catalysts.py#L461) | Get all catalyst events for a specific ticker. |
| `GET` | `/api/catalysts/types` | [`platform/api/routers/catalysts.py:659`](../platform/api/routers/catalysts.py#L659) | Return available catalyst types and WSH upgrade info. |
| `GET` | `/api/config/firebase` | [`platform/api/routers/config.py:39`](../platform/api/routers/config.py#L39) | Public runtime auth config for the frontend bootstrap. |
| `GET` | `/api/config/indicators` | [`platform/api/routers/config.py:66`](../platform/api/routers/config.py#L66) | Return indicator periods, signal thresholds, and zone labels. |
| `GET` | `/api/config/market-hours` | [`platform/api/routers/config.py:122`](../platform/api/routers/config.py#L122) | Return US equity market session windows + 2026 holidays. |
| `GET` | `/api/dashboard/brief/{ticker}` | [`platform/api/routers/dashboard.py:76`](../platform/api/routers/dashboard.py#L76) | Return daily bias / strat status for the dashboard. |
| `GET` | `/api/earnings/calibration` | [`platform/api/routers/earnings.py:304`](../platform/api/routers/earnings.py#L304) | The live calibration row (PR-A + PR-B headline finding). |
| `GET` | `/api/earnings/event/{ticker}/{event_date}` | [`platform/api/routers/earnings.py:172`](../platform/api/routers/earnings.py#L172) | Single-event drill-down. |
| `GET` | `/api/earnings/health/ping` | [`platform/api/routers/earnings.py:324`](../platform/api/routers/earnings.py#L324) | Lightweight warm-up endpoint hit by the keep-warm Cloud Scheduler. |
| `GET` | `/api/earnings/history/{ticker}` | [`platform/api/routers/earnings.py:138`](../platform/api/routers/earnings.py#L138) | Last N quarters for one ticker — full event timeline. |
| `GET` | `/api/earnings/insights/grid` | [`platform/api/routers/earnings.py:255`](../platform/api/routers/earnings.py#L255) | The 144-row Q × bucket × structure insights table (PR-B). |
| `GET` | `/api/earnings/insights/winners` | [`platform/api/routers/earnings.py:278`](../platform/api/routers/earnings.py#L278) | Top-N named winners per (structure × quintile). |
| `GET` | `/api/earnings/lean` | [`platform/api/routers/earnings.py:197`](../platform/api/routers/earnings.py#L197) | Per-ticker lean leaderboard. |
| `GET` | `/api/earnings/ticker/{ticker}/lean` | [`platform/api/routers/earnings.py:233`](../platform/api/routers/earnings.py#L233) | Lean stats for one ticker. |
| `GET` | `/api/earnings/upcoming` | [`platform/api/routers/earnings.py:108`](../platform/api/routers/earnings.py#L108) | Next N days of earnings reporters, decorated with full history. |
| `GET` | `/api/glossary/gamma` | [`platform/api/routers/glossary.py:30`](../platform/api/routers/glossary.py#L30) | Return the UI-safe gamma term dictionary. |
| `GET` | `/api/health` | [`platform/api/main.py:223`](../platform/api/main.py#L223) |  |
| `GET` | `/api/health/freshness` | [`platform/api/routers/health.py:70`](../platform/api/routers/health.py#L70) | Return the cached freshness report (see freshness_report_dict). |
| `POST` | `/api/insights/chat` | [`platform/api/routers/insights.py:992`](../platform/api/routers/insights.py#L992) | Stream a Gemini response for the given mode and message. |
| `GET` | `/api/insights/report/{ticker}` | [`platform/api/routers/insights.py:672`](../platform/api/routers/insights.py#L672) | Return the most recent InsightReport for the ticker. |
| `GET` | `/api/insights/report/{ticker}/history` | [`platform/api/routers/insights.py:701`](../platform/api/routers/insights.py#L701) | Return a scannable list of recent reports for the ticker. |
| `POST` | `/api/insights/report/{ticker}/refresh` | [`platform/api/routers/insights.py:736`](../platform/api/routers/insights.py#L736) | Enqueue a fresh pipeline run for the ticker. |
| `GET` | `/api/insights/reports/{report_id}` | [`platform/api/routers/insights.py:710`](../platform/api/routers/insights.py#L710) | Return a single insight report by row id. |
| `GET` | `/api/insights/runs/{run_id}` | [`platform/api/routers/insights.py:860`](../platform/api/routers/insights.py#L860) | Poll the status of a refresh run. |
| `GET` | `/api/insights/ticker/search` | [`platform/api/routers/insights.py:452`](../platform/api/routers/insights.py#L452) | Search for tickers by keyword (company name, symbol, etc). |
| `GET` | `/api/insights/ticker/{ticker}/info` | [`platform/api/routers/insights.py:467`](../platform/api/routers/insights.py#L467) | Return cached ticker details (AV OVERVIEW), fetching if needed. |
| `GET` | `/api/insights/ticker/{ticker}/peers` | [`platform/api/routers/insights.py:498`](../platform/api/routers/insights.py#L498) | Return peer tickers from FinViz (cached). |
| `GET` | `/api/insights/ticker/{ticker}/quote` | [`platform/api/routers/insights.py:487`](../platform/api/routers/insights.py#L487) | Return latest price/volume from AV GLOBAL_QUOTE. |
| `GET` | `/api/insights/watchlist` | [`platform/api/routers/insights.py:617`](../platform/api/routers/insights.py#L617) | Return today's ranked candidate tickers with score breakdowns. |
| `POST` | `/api/insights/watchlist/add` | [`platform/api/routers/insights.py:507`](../platform/api/routers/insights.py#L507) | Add a ticker to the watchlist and return its info + quote. |
| `DELETE` | `/api/insights/watchlist/{ticker}` | [`platform/api/routers/insights.py:584`](../platform/api/routers/insights.py#L584) | Soft-delete a ticker from the watchlist (sets removed_at=NOW()). |
| `GET` | `/api/journal/examples/{ticker}` | [`platform/api/routers/journal.py:664`](../platform/api/routers/journal.py#L664) | Read-only teaching "Examples" — the UNION of the admin's own journal |
| `POST` | `/api/journal/export/{ticker}` | [`platform/api/routers/journal.py:1080`](../platform/api/routers/journal.py#L1080) | Write journal trades to {ticker}_trade_tracker.csv in data/signals/. |
| `POST` | `/api/journal/import/commit` | [`platform/api/routers/journal.py:1202`](../platform/api/routers/journal.py#L1202) | Insert the caller-selected `PairedTrade`s from a preview. |
| `POST` | `/api/journal/import/preview` | [`platform/api/routers/journal.py:1112`](../platform/api/routers/journal.py#L1112) | Parse an uploaded broker CSV export and FIFO-pair round trips. |
| `GET` | `/api/journal/seed/{ticker}` | [`platform/api/routers/journal.py:1014`](../platform/api/routers/journal.py#L1014) | Read-only admin seed pull from the automated pipeline `trades` table. |
| `POST` | `/api/journal/trades` | [`platform/api/routers/journal.py:823`](../platform/api/routers/journal.py#L823) | Insert a journal entry for the signed-in user. Returns it with its id. |
| `GET` | `/api/journal/trades/{ticker}` | [`platform/api/routers/journal.py:624`](../platform/api/routers/journal.py#L624) | Return the signed-in user's journal entries for the ticker, newest first. |
| `DELETE` | `/api/journal/trades/{trade_id}` | [`platform/api/routers/journal.py:979`](../platform/api/routers/journal.py#L979) | Delete one of the signed-in user's journal entries by UUID. |
| `PATCH` | `/api/journal/trades/{trade_id}` | [`platform/api/routers/journal.py:897`](../platform/api/routers/journal.py#L897) | Close an ACTIVE trade: sets exit_ts/exit_price, computes return_pct |
| `GET` | `/api/live/avg-volume/{ticker}` | [`platform/api/routers/live.py:317`](../platform/api/routers/live.py#L317) | Return the 20-day average daily volume for RVOL calculation. |
| `GET` | `/api/live/history/{ticker}` | [`platform/api/routers/live.py:247`](../platform/api/routers/live.py#L247) | Fetch last 100 1-min bars from Alpha Vantage TIME_SERIES_INTRADAY. |
| `POST` | `/api/live/indicators` | [`platform/api/routers/live.py:451`](../platform/api/routers/live.py#L451) | Compute indicators and CALL/PUT signals from a bar series. |
| `GET` | `/api/live/quote/{ticker}` | [`platform/api/routers/live.py:177`](../platform/api/routers/live.py#L177) | Fetch real-time quote from Alpha Vantage GLOBAL_QUOTE. |
| `POST` | `/api/live/signal-series` | [`platform/api/routers/live.py:534`](../platform/api/routers/live.py#L534) | Per-bar CALL/PUT signal fires for the Charts page "Sig" overlay. |
| `GET` | `/api/live/status` | [`platform/api/routers/live.py:162`](../platform/api/routers/live.py#L162) | Return current market open/closed status based on Eastern Time. |
| `GET` | `/api/magnitude/{ticker}/{tf}/at/{ts}` | [`platform/api/routers/magnitude.py:153`](../platform/api/routers/magnitude.py#L153) | Return the prediction for exactly this (ticker, tf, ts). |
| `GET` | `/api/magnitude/{ticker}/{tf}/latest` | [`platform/api/routers/magnitude.py:109`](../platform/api/routers/magnitude.py#L109) | Return the most-recent prediction for this (ticker, tf). |
| `GET` | `/api/market/coverage` | [`platform/api/main.py:887`](../platform/api/main.py#L887) | Data coverage per symbol — drives the type-ahead's full/daily/new badges. |
| `GET` | `/api/market/data/{ticker}/{date}` | [`platform/api/main.py:561`](../platform/api/main.py#L561) | Load intraday OHLCV data for a specific ticker and date. |
| `GET` | `/api/market/dates/{ticker}` | [`platform/api/main.py:494`](../platform/api/main.py#L494) | List available trading dates for a ticker (Cloud SQL → local fallback). |
| `GET` | `/api/market/most-active` | [`platform/api/main.py:1134`](../platform/api/main.py#L1134) | Most-active tickers snapshot, with per-ticker snapshot sparklines. |
| `GET` | `/api/market/reference/{ticker}/{date}` | [`platform/api/main.py:717`](../platform/api/main.py#L717) | Get previous day OHLC reference levels for support/resistance. |
| `GET` | `/api/market/sectors` | [`platform/api/main.py:1026`](../platform/api/main.py#L1026) | Sector rotation snapshot computed from SPDR sector ETF daily closes. |
| `GET` | `/api/me` | [`platform/api/main.py:234`](../platform/api/main.py#L234) | Return the authenticated identity + role flags. |
| `GET` | `/api/me/preferences` | [`platform/api/routers/preferences.py:129`](../platform/api/routers/preferences.py#L129) |  |
| `PUT` | `/api/me/preferences` | [`platform/api/routers/preferences.py:146`](../platform/api/routers/preferences.py#L146) | Upsert the provided subset of fields and return the full stored row. |
| `GET` | `/api/me/profile` | [`platform/api/routers/profile.py:142`](../platform/api/routers/profile.py#L142) |  |
| `PUT` | `/api/me/profile` | [`platform/api/routers/profile.py:159`](../platform/api/routers/profile.py#L159) | Upsert the provided subset of fields and return the full stored row. |
| `GET` | `/api/movement-statement` | [`platform/api/routers/dashboard.py:444`](../platform/api/routers/dashboard.py#L444) | PHASE 3 — read-only, feature-flagged movement statement. |
| `GET` | `/api/options/dates/{ticker}` | [`platform/api/routers/options.py:272`](../platform/api/routers/options.py#L272) | Return up to 1000 most-recent snapshot dates that have AlphaVantage data |
| `POST` | `/api/options/greeks` | [`platform/api/routers/options.py:555`](../platform/api/routers/options.py#L555) | Single source of truth for GEX/VEX/max-pain/implied-move/nodes. |
| `GET` | `/api/options/live/{ticker}/{date_str}` | [`platform/api/routers/options.py:435`](../platform/api/routers/options.py#L435) | Fetch the AlphaVantage HISTORICAL_OPTIONS chain live, with the same |
| `GET` | `/api/options/{ticker}/grid` | [`platform/api/routers/grid.py:529`](../platform/api/routers/grid.py#L529) | Live 2-D strike × expiration grid. |
| `GET` | `/api/options/{ticker}/grid/timeseries` | [`platform/api/routers/grid.py:903`](../platform/api/routers/grid.py#L903) | Per-strike GEX time-series for a single expiration over the last |
| `GET` | `/api/options/{ticker}/nodes` | [`platform/api/routers/grid.py:794`](../platform/api/routers/grid.py#L794) | Live semantic taxonomy — King / Gates / Midpoints / Hedge Nodes / |
| `GET` | `/api/options/{ticker}/{date_str}` | [`platform/api/routers/options.py:343`](../platform/api/routers/options.py#L343) | Return the AlphaVantage option chain for `ticker` on `date_str` |
| `GET` | `/api/options/{ticker}/{date_str}/grid` | [`platform/api/routers/grid.py:618`](../platform/api/routers/grid.py#L618) | Historical 2-D grid for a past date — EOD only. |
| `GET` | `/api/options/{ticker}/{date_str}/levels` | [`platform/api/routers/options.py:611`](../platform/api/routers/options.py#L611) | Stratalyst-style King/Gate/Spot/Flip taxonomy for a Cloud SQL snapshot. |
| `GET` | `/api/options/{ticker}/{date_str}/nodes` | [`platform/api/routers/grid.py:844`](../platform/api/routers/grid.py#L844) | Historical semantic taxonomy — EOD only. |
| `POST` | `/api/playbook/evaluate` | [`platform/api/routers/playbook.py:695`](../platform/api/routers/playbook.py#L695) | Evaluate playbook condition strings against a live snapshot. |
| `GET` | `/api/playbook/{ticker}` | [`platform/api/routers/playbook.py:288`](../platform/api/routers/playbook.py#L288) | Return structured setup cards for a ticker from ``playbook_cards``. |
| `GET` | `/api/reports/list/{ticker}` | [`platform/api/routers/playbook.py:349`](../platform/api/routers/playbook.py#L349) | List available phase report files for a given ticker (from GCS). |
| `GET` | `/api/reports/{ticker}/{phase}` | [`platform/api/routers/playbook.py:405`](../platform/api/routers/playbook.py#L405) | Return the raw markdown text of a specific phase report for a ticker from GCS. |
| `GET` | `/api/signals/{ticker}` | [`platform/api/routers/signals.py:155`](../platform/api/routers/signals.py#L155) | Return historical signals for a ticker. |
| `GET` | `/api/signals/{ticker}/similar` | [`platform/api/routers/signals.py:257`](../platform/api/routers/signals.py#L257) | Return historical signals similar to the supplied bar's conditions. |
| `POST` | `/api/style/mine-and-validate` | [`platform/api/routers/backtest.py:597`](../platform/api/routers/backtest.py#L597) | Mine the caller's closed journal trades into a condition profile, |
| `POST` | `/api/waitlist` | [`platform/api/routers/waitlist.py:81`](../platform/api/routers/waitlist.py#L81) |  |
| `GET` | `/dev` | [`platform/api/main.py:385`](../platform/api/main.py#L385) |  |
| `GET` | `/{full_path:path}` | [`platform/api/main.py:1334`](../platform/api/main.py#L1334) | SPA fallback — serve index.html for any non-API, non-asset route. |
<!-- inventory:routes:end -->

## Conventions

- Everything lives under `/api/`. `{ticker}` is the upper-cased symbol (`SPY`, `QQQ`, `IWM`, `^SPX`); `{date_str}` is `YYYY-MM-DD`.
- Auth is decided per request by `AUTH_MODE` in [`platform/api/auth.py`](../platform/api/auth.py): `iap` trusts the IAP header, `firebase` verifies a bearer ID token, `open` passes through (local only). `/api/me`, `/api/health*`, `/api/config/firebase*` and `/api/waitlist*` are open; everything else is gated. Admin routes require the `admin` role from the `user_roles` table. Details: [ARCHITECTURE.md §7.2](../ARCHITECTURE.md#72-auth-model-platformapiauthpy).
- Data comes from Cloud SQL (`market_data_*`, `etf_options_snapshots`, `journal_entries`, `trades`, `insight_reports`, …), GCS (phase reports, playbook markdown) and Alpha Vantage (live quotes). Which route reads which table: [DATA_DEPENDENCIES.md](../DATA_DEPENDENCIES.md).
- The frontend that calls these routes is the Solyra SPA in `TeneikaAskew/solyra`; it is not served by this app.
