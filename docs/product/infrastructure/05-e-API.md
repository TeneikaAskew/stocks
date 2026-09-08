# Platform API Reference

The FastAPI app in [`platform/api/main.py`](../../../platform/api/main.py) is deployed twice from one image as `solyra-api-prod` (IAP) and `solyra-api-staging` (public, Firebase login); the services, the auth model and the deploy path are in [ARCHITECTURE.md §7](05-a-ARCHITECTURE.md#7-cloud-run-services-auth-and-the-api). The tables below are rendered from the router files by `scripts/maintenance/doc_inventory.py` on every monthly refresh and must not be edited by hand; run `python -m scripts.maintenance.doc_inventory --insert docs/product/infrastructure/05-e-API.md` to update them now.

Live OpenAPI on a running instance: `/docs` and `/openapi.json`.

Committed OpenAPI snapshot: [`platform/api/openapi.json`](../../../platform/api/openapi.json). Regenerate it with `python scripts/export_openapi.py` after any route or response-model change; `tests/api/test_openapi_snapshot.py` fails when it is stale. The frontend repo (TeneikaAskew/solyra) vendors the file from `main` and validates its response types and mock payloads against it in CI, so the snapshot is the cross-repo API contract, not documentation.

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
| [`main.py`](../../../platform/api/main.py) | 9 | GET | `/api/health`, `/api/market`, `/api/me`, `/dev` |
| [`admin.py`](../../../platform/api/routers/admin.py) | 12 | GET, POST, PUT | `/api/admin` |
| [`analytics.py`](../../../platform/api/routers/analytics.py) | 2 | GET, POST | `/api/analytics` |
| [`backtest.py`](../../../platform/api/routers/backtest.py) | 5 | GET, POST | `/api/backtest`, `/api/style` |
| [`catalysts.py`](../../../platform/api/routers/catalysts.py) | 5 | GET | `/api/catalysts` |
| [`config.py`](../../../platform/api/routers/config.py) | 3 | GET | `/api/config` |
| [`dashboard.py`](../../../platform/api/routers/dashboard.py) | 2 | GET | `/api/dashboard`, `/api/movement-statement` |
| [`earnings.py`](../../../platform/api/routers/earnings.py) | 9 | GET | `/api/earnings` |
| [`glossary.py`](../../../platform/api/routers/glossary.py) | 1 | GET | `/api/glossary` |
| [`grid.py`](../../../platform/api/routers/grid.py) | 5 | GET | `/api/options` |
| [`health.py`](../../../platform/api/routers/health.py) | 1 | GET | `/api/health` |
| [`insights.py`](../../../platform/api/routers/insights.py) | 13 | DELETE, GET, POST | `/api/insights` |
| [`journal.py`](../../../platform/api/routers/journal.py) | 9 | DELETE, GET, PATCH, POST | `/api/journal` |
| [`live.py`](../../../platform/api/routers/live.py) | 6 | GET, POST | `/api/live` |
| [`magnitude.py`](../../../platform/api/routers/magnitude.py) | 2 | GET | `/api/magnitude` |
| [`options.py`](../../../platform/api/routers/options.py) | 5 | GET, POST | `/api/options` |
| [`playbook.py`](../../../platform/api/routers/playbook.py) | 4 | GET, POST | `/api/playbook`, `/api/reports` |
| [`preferences.py`](../../../platform/api/routers/preferences.py) | 2 | GET, PUT | `/api/me` |
| [`profile.py`](../../../platform/api/routers/profile.py) | 2 | GET, PUT | `/api/me` |
| [`signals.py`](../../../platform/api/routers/signals.py) | 2 | GET | `/api/signals` |
| [`waitlist.py`](../../../platform/api/routers/waitlist.py) | 1 | POST | `/api/waitlist` |
| **Total** | 100 |  | 21 routers |
<!-- inventory:routers:end -->

## Routes

<!-- inventory:routes:start -->
| Method | Path | Defined | Purpose |
|---|---|---|---|
| `GET` | `/api/admin/data-sources` | [`platform/api/routers/admin.py:1389`](../../../platform/api/routers/admin.py#L1389) | Per-dataset freshness/coverage, aggregated from the shared audit. |
| `POST` | `/api/admin/data-sources/{source_id}/refresh` | [`platform/api/routers/admin.py:1522`](../../../platform/api/routers/admin.py#L1522) | Queue the dataset's Cloud Run fetcher job. |
| `GET` | `/api/admin/models` | [`platform/api/routers/admin.py:208`](../../../platform/api/routers/admin.py#L208) |  |
| `GET` | `/api/admin/routes` | [`platform/api/routers/admin.py:129`](../../../platform/api/routers/admin.py#L129) |  |
| `PUT` | `/api/admin/routes/{role}` | [`platform/api/routers/admin.py:157`](../../../platform/api/routers/admin.py#L157) |  |
| `POST` | `/api/admin/strat-engine/predict` | [`platform/api/routers/admin.py:592`](../../../platform/api/routers/admin.py#L592) | Run the frozen strat-engine type model for ONE bar. |
| `GET` | `/api/admin/strat-engine/state` | [`platform/api/routers/admin.py:575`](../../../platform/api/routers/admin.py#L575) | Operator snapshot of the on-shelf strat-engine model state. |
| `POST` | `/api/admin/strat-engine/structure-continuation` | [`platform/api/routers/admin.py:733`](../../../platform/api/routers/admin.py#L733) | Read-only, feature-flagged calibrated structure-continuation probability. |
| `GET` | `/api/admin/structure-brief` | [`platform/api/routers/admin.py:342`](../../../platform/api/routers/admin.py#L342) | Dev-only readout of the strat-engine type model's structure predictions. |
| `GET` | `/api/admin/users` | [`platform/api/routers/admin.py:1019`](../../../platform/api/routers/admin.py#L1019) | Every Firebase account + its stored role(s). |
| `PUT` | `/api/admin/users/{uid}/roles` | [`platform/api/routers/admin.py:1063`](../../../platform/api/routers/admin.py#L1063) | Replace an account's stored role. |
| `PUT` | `/api/admin/users/{uid}/status` | [`platform/api/routers/admin.py:1135`](../../../platform/api/routers/admin.py#L1135) | Enable or disable a Firebase account. |
| `GET` | `/api/analytics/summary/{ticker}` | [`platform/api/routers/analytics.py:126`](../../../platform/api/routers/analytics.py#L126) | Summarize rows from the ``trades`` table for a ticker. |
| `POST` | `/api/analytics/trade-stats` | [`platform/api/routers/analytics.py:118`](../../../platform/api/routers/analytics.py#L118) |  |
| `GET` | `/api/backtest/all/{ticker}` | [`platform/api/routers/backtest.py:355`](../../../platform/api/routers/backtest.py#L355) | List all backtest runs for a ticker, sorted by timestamp descending. |
| `GET` | `/api/backtest/equity/{ticker}` | [`platform/api/routers/backtest.py:257`](../../../platform/api/routers/backtest.py#L257) | Return equity curve from the most recent equity CSV for the given ticker, |
| `POST` | `/api/backtest/replay-trades` | [`platform/api/routers/backtest.py:512`](../../../platform/api/routers/backtest.py#L512) | Score the signed-in user's labeled journal trades against actual bars |
| `GET` | `/api/backtest/results/{ticker}` | [`platform/api/routers/backtest.py:188`](../../../platform/api/routers/backtest.py#L188) | Return trades from the most recent backtest CSV for the given ticker, |
| `GET` | `/api/catalysts/asof/{ticker}` | [`platform/api/routers/catalysts.py:612`](../../../platform/api/routers/catalysts.py#L612) | Unified point-in-time catalyst view for a ticker. |
| `GET` | `/api/catalysts/events` | [`platform/api/routers/catalysts.py:158`](../../../platform/api/routers/catalysts.py#L158) | Get catalyst events grouped by date. |
| `GET` | `/api/catalysts/snapshot/{ticker}` | [`platform/api/routers/catalysts.py:613`](../../../platform/api/routers/catalysts.py#L613) | Unified point-in-time catalyst view for a ticker. |
| `GET` | `/api/catalysts/ticker/{ticker}` | [`platform/api/routers/catalysts.py:575`](../../../platform/api/routers/catalysts.py#L575) | Get all catalyst events for a specific ticker. |
| `GET` | `/api/catalysts/types` | [`platform/api/routers/catalysts.py:773`](../../../platform/api/routers/catalysts.py#L773) | Return available catalyst types and WSH upgrade info. |
| `GET` | `/api/config/firebase` | [`platform/api/routers/config.py:44`](../../../platform/api/routers/config.py#L44) | Public runtime auth config for the frontend bootstrap. |
| `GET` | `/api/config/indicators` | [`platform/api/routers/config.py:71`](../../../platform/api/routers/config.py#L71) | Return indicator periods, signal thresholds, and zone labels. |
| `GET` | `/api/config/market-hours` | [`platform/api/routers/config.py:127`](../../../platform/api/routers/config.py#L127) | Return US equity market session windows + 2026 holidays. |
| `GET` | `/api/dashboard/brief/{ticker}` | [`platform/api/routers/dashboard.py:82`](../../../platform/api/routers/dashboard.py#L82) | Return daily bias / strat status for the dashboard. |
| `GET` | `/api/earnings/calibration` | [`platform/api/routers/earnings.py:304`](../../../platform/api/routers/earnings.py#L304) | The live calibration row (PR-A + PR-B headline finding). |
| `GET` | `/api/earnings/event/{ticker}/{event_date}` | [`platform/api/routers/earnings.py:172`](../../../platform/api/routers/earnings.py#L172) | Single-event drill-down. |
| `GET` | `/api/earnings/health/ping` | [`platform/api/routers/earnings.py:324`](../../../platform/api/routers/earnings.py#L324) | Lightweight warm-up probe. NOT called by a scheduler. |
| `GET` | `/api/earnings/history/{ticker}` | [`platform/api/routers/earnings.py:138`](../../../platform/api/routers/earnings.py#L138) | Last N quarters for one ticker — full event timeline. |
| `GET` | `/api/earnings/insights/grid` | [`platform/api/routers/earnings.py:255`](../../../platform/api/routers/earnings.py#L255) | The 144-row Q × bucket × structure insights table (PR-B). |
| `GET` | `/api/earnings/insights/winners` | [`platform/api/routers/earnings.py:278`](../../../platform/api/routers/earnings.py#L278) | Top-N named winners per (structure × quintile). |
| `GET` | `/api/earnings/lean` | [`platform/api/routers/earnings.py:197`](../../../platform/api/routers/earnings.py#L197) | Per-ticker lean leaderboard. |
| `GET` | `/api/earnings/ticker/{ticker}/lean` | [`platform/api/routers/earnings.py:233`](../../../platform/api/routers/earnings.py#L233) | Lean stats for one ticker. |
| `GET` | `/api/earnings/upcoming` | [`platform/api/routers/earnings.py:108`](../../../platform/api/routers/earnings.py#L108) | Next N days of earnings reporters, decorated with full history. |
| `GET` | `/api/glossary/gamma` | [`platform/api/routers/glossary.py:30`](../../../platform/api/routers/glossary.py#L30) | Return the UI-safe gamma term dictionary. |
| `GET` | `/api/health` | [`platform/api/main.py:270`](../../../platform/api/main.py#L270) | Liveness probe: reports the service version and its configured backends. |
| `GET` | `/api/health/freshness` | [`platform/api/routers/health.py:146`](../../../platform/api/routers/health.py#L146) | Return the cached freshness report (see freshness_report_dict). |
| `POST` | `/api/insights/chat` | [`platform/api/routers/insights.py:1074`](../../../platform/api/routers/insights.py#L1074) | Stream a Gemini response for the given mode and message. |
| `GET` | `/api/insights/report/{ticker}` | [`platform/api/routers/insights.py:724`](../../../platform/api/routers/insights.py#L724) | Return the most recent InsightReport for the ticker. |
| `GET` | `/api/insights/report/{ticker}/history` | [`platform/api/routers/insights.py:753`](../../../platform/api/routers/insights.py#L753) | Return a scannable list of recent reports for the ticker. |
| `POST` | `/api/insights/report/{ticker}/refresh` | [`platform/api/routers/insights.py:801`](../../../platform/api/routers/insights.py#L801) | Enqueue a fresh pipeline run for the ticker. |
| `GET` | `/api/insights/reports/{report_id}` | [`platform/api/routers/insights.py:763`](../../../platform/api/routers/insights.py#L763) | Return a single insight report by row id. |
| `GET` | `/api/insights/runs/{run_id}` | [`platform/api/routers/insights.py:925`](../../../platform/api/routers/insights.py#L925) | Poll the status of a refresh run. |
| `GET` | `/api/insights/ticker/search` | [`platform/api/routers/insights.py:504`](../../../platform/api/routers/insights.py#L504) | Search for tickers by keyword (company name, symbol, etc). |
| `GET` | `/api/insights/ticker/{ticker}/info` | [`platform/api/routers/insights.py:519`](../../../platform/api/routers/insights.py#L519) | Return cached ticker details (AV OVERVIEW), fetching if needed. |
| `GET` | `/api/insights/ticker/{ticker}/peers` | [`platform/api/routers/insights.py:550`](../../../platform/api/routers/insights.py#L550) | Return peer tickers from FinViz (cached). |
| `GET` | `/api/insights/ticker/{ticker}/quote` | [`platform/api/routers/insights.py:539`](../../../platform/api/routers/insights.py#L539) | Return latest price/volume from AV GLOBAL_QUOTE. |
| `GET` | `/api/insights/watchlist` | [`platform/api/routers/insights.py:669`](../../../platform/api/routers/insights.py#L669) | Return today's ranked candidate tickers with score breakdowns. |
| `POST` | `/api/insights/watchlist/add` | [`platform/api/routers/insights.py:559`](../../../platform/api/routers/insights.py#L559) | Add a ticker to the watchlist and return its info + quote. |
| `DELETE` | `/api/insights/watchlist/{ticker}` | [`platform/api/routers/insights.py:636`](../../../platform/api/routers/insights.py#L636) | Soft-delete a ticker from the watchlist (sets removed_at=NOW()). |
| `GET` | `/api/journal/examples/{ticker}` | [`platform/api/routers/journal.py:905`](../../../platform/api/routers/journal.py#L905) | Read-only teaching "Examples" — the UNION of the admin's own journal |
| `POST` | `/api/journal/export/{ticker}` | [`platform/api/routers/journal.py:1348`](../../../platform/api/routers/journal.py#L1348) | Write journal trades to {ticker}_trade_tracker.csv in data/signals/. |
| `POST` | `/api/journal/import/commit` | [`platform/api/routers/journal.py:1492`](../../../platform/api/routers/journal.py#L1492) | Insert the caller-selected `PairedTrade`s from a preview. |
| `POST` | `/api/journal/import/preview` | [`platform/api/routers/journal.py:1402`](../../../platform/api/routers/journal.py#L1402) | Parse an uploaded broker CSV export and FIFO-pair round trips. |
| `GET` | `/api/journal/seed/{ticker}` | [`platform/api/routers/journal.py:1282`](../../../platform/api/routers/journal.py#L1282) | Read-only admin seed pull from the automated pipeline `trades` table. |
| `POST` | `/api/journal/trades` | [`platform/api/routers/journal.py:1064`](../../../platform/api/routers/journal.py#L1064) | Insert a journal entry for the signed-in user. Returns it with its id. |
| `GET` | `/api/journal/trades/{ticker}` | [`platform/api/routers/journal.py:865`](../../../platform/api/routers/journal.py#L865) | Return the signed-in user's journal entries for the ticker, newest first. |
| `DELETE` | `/api/journal/trades/{trade_id}` | [`platform/api/routers/journal.py:1227`](../../../platform/api/routers/journal.py#L1227) | Delete one of the signed-in user's journal entries by UUID. |
| `PATCH` | `/api/journal/trades/{trade_id}` | [`platform/api/routers/journal.py:1141`](../../../platform/api/routers/journal.py#L1141) | Close an ACTIVE trade: sets exit_ts/exit_price, computes return_pct |
| `GET` | `/api/live/avg-volume/{ticker}` | [`platform/api/routers/live.py:384`](../../../platform/api/routers/live.py#L384) | Return the 20-day average daily volume for RVOL calculation. |
| `GET` | `/api/live/history/{ticker}` | [`platform/api/routers/live.py:314`](../../../platform/api/routers/live.py#L314) | Fetch last 100 1-min bars from Alpha Vantage TIME_SERIES_INTRADAY. |
| `POST` | `/api/live/indicators` | [`platform/api/routers/live.py:526`](../../../platform/api/routers/live.py#L526) | Compute indicators and CALL/PUT signals from a bar series. |
| `GET` | `/api/live/quote/{ticker}` | [`platform/api/routers/live.py:188`](../../../platform/api/routers/live.py#L188) | Fetch real-time quote from Alpha Vantage GLOBAL_QUOTE. |
| `POST` | `/api/live/signal-series` | [`platform/api/routers/live.py:609`](../../../platform/api/routers/live.py#L609) | Per-bar CALL/PUT signal fires for the Charts page "Sig" overlay. |
| `GET` | `/api/live/status` | [`platform/api/routers/live.py:173`](../../../platform/api/routers/live.py#L173) | Return current market open/closed status based on Eastern Time. |
| `GET` | `/api/magnitude/{ticker}/{tf}/at/{ts}` | [`platform/api/routers/magnitude.py:153`](../../../platform/api/routers/magnitude.py#L153) | Return the prediction for exactly this (ticker, tf, ts). |
| `GET` | `/api/magnitude/{ticker}/{tf}/latest` | [`platform/api/routers/magnitude.py:109`](../../../platform/api/routers/magnitude.py#L109) | Return the most-recent prediction for this (ticker, tf). |
| `GET` | `/api/market/coverage` | [`platform/api/main.py:1239`](../../../platform/api/main.py#L1239) | Data coverage per symbol — drives the type-ahead's full/daily/new badges. |
| `GET` | `/api/market/data/{ticker}/{date}` | [`platform/api/main.py:913`](../../../platform/api/main.py#L913) | Load intraday OHLCV data for a specific ticker and date. |
| `GET` | `/api/market/dates/{ticker}` | [`platform/api/main.py:607`](../../../platform/api/main.py#L607) | List available trading dates for a ticker (Cloud SQL → local fallback). |
| `GET` | `/api/market/most-active` | [`platform/api/main.py:1518`](../../../platform/api/main.py#L1518) | Most-active tickers snapshot, with per-ticker snapshot sparklines. |
| `GET` | `/api/market/reference/{ticker}/{date}` | [`platform/api/main.py:1069`](../../../platform/api/main.py#L1069) | Get previous day OHLC reference levels for support/resistance. |
| `GET` | `/api/market/sectors` | [`platform/api/main.py:1410`](../../../platform/api/main.py#L1410) | Sector rotation snapshot computed from SPDR sector ETF daily closes. |
| `GET` | `/api/me` | [`platform/api/main.py:282`](../../../platform/api/main.py#L282) | Return the authenticated identity + role flags. |
| `GET` | `/api/me/preferences` | [`platform/api/routers/preferences.py:132`](../../../platform/api/routers/preferences.py#L132) |  |
| `PUT` | `/api/me/preferences` | [`platform/api/routers/preferences.py:149`](../../../platform/api/routers/preferences.py#L149) | Upsert the provided subset of fields and return the full stored row. |
| `GET` | `/api/me/profile` | [`platform/api/routers/profile.py:145`](../../../platform/api/routers/profile.py#L145) |  |
| `PUT` | `/api/me/profile` | [`platform/api/routers/profile.py:162`](../../../platform/api/routers/profile.py#L162) | Upsert the provided subset of fields and return the full stored row. |
| `GET` | `/api/movement-statement` | [`platform/api/routers/dashboard.py:528`](../../../platform/api/routers/dashboard.py#L528) | PHASE 3 — read-only, feature-flagged movement statement. |
| `GET` | `/api/options/dates/{ticker}` | [`platform/api/routers/options.py:318`](../../../platform/api/routers/options.py#L318) | Return the `limit` most-recent snapshot dates with AlphaVantage data. |
| `POST` | `/api/options/greeks` | [`platform/api/routers/options.py:753`](../../../platform/api/routers/options.py#L753) | Single source of truth for GEX/VEX/max-pain/implied-move/nodes. |
| `GET` | `/api/options/live/{ticker}/{date_str}` | [`platform/api/routers/options.py:633`](../../../platform/api/routers/options.py#L633) | Fetch the AlphaVantage HISTORICAL_OPTIONS chain live, with the same |
| `GET` | `/api/options/{ticker}/grid` | [`platform/api/routers/grid.py:618`](../../../platform/api/routers/grid.py#L618) | Live 2-D strike × expiration grid. |
| `GET` | `/api/options/{ticker}/grid/timeseries` | [`platform/api/routers/grid.py:1076`](../../../platform/api/routers/grid.py#L1076) | Per-strike GEX time-series for a single expiration over the last |
| `GET` | `/api/options/{ticker}/nodes` | [`platform/api/routers/grid.py:932`](../../../platform/api/routers/grid.py#L932) | Live semantic taxonomy — King / Gates / Midpoints / Hedge Nodes / |
| `GET` | `/api/options/{ticker}/{date_str}` | [`platform/api/routers/options.py:524`](../../../platform/api/routers/options.py#L524) | Return the AlphaVantage option chain for `ticker` on `date_str` |
| `GET` | `/api/options/{ticker}/{date_str}/grid` | [`platform/api/routers/grid.py:738`](../../../platform/api/routers/grid.py#L738) | Historical 2-D grid for a past date — EOD only. |
| `GET` | `/api/options/{ticker}/{date_str}/levels` | [`platform/api/routers/options.py:809`](../../../platform/api/routers/options.py#L809) | Stratalyst-style King/Gate/Spot/Flip taxonomy for a Cloud SQL snapshot. |
| `GET` | `/api/options/{ticker}/{date_str}/nodes` | [`platform/api/routers/grid.py:1000`](../../../platform/api/routers/grid.py#L1000) | Historical semantic taxonomy — EOD only. |
| `POST` | `/api/playbook/evaluate` | [`platform/api/routers/playbook.py:747`](../../../platform/api/routers/playbook.py#L747) | Evaluate playbook condition strings against a live snapshot. |
| `GET` | `/api/playbook/{ticker}` | [`platform/api/routers/playbook.py:306`](../../../platform/api/routers/playbook.py#L306) | Return structured setup cards for a ticker from ``playbook_cards``. |
| `GET` | `/api/reports/list/{ticker}` | [`platform/api/routers/playbook.py:367`](../../../platform/api/routers/playbook.py#L367) | List available phase report files for a given ticker (from GCS). |
| `GET` | `/api/reports/{ticker}/{phase}` | [`platform/api/routers/playbook.py:440`](../../../platform/api/routers/playbook.py#L440) | Return the raw markdown text of a specific phase report for a ticker from GCS. |
| `GET` | `/api/signals/{ticker}` | [`platform/api/routers/signals.py:182`](../../../platform/api/routers/signals.py#L182) | Return historical signals for a ticker. |
| `GET` | `/api/signals/{ticker}/similar` | [`platform/api/routers/signals.py:284`](../../../platform/api/routers/signals.py#L284) | Return historical signals similar to the supplied bar's conditions. |
| `POST` | `/api/style/mine-and-validate` | [`platform/api/routers/backtest.py:690`](../../../platform/api/routers/backtest.py#L690) | Mine the caller's closed journal trades into a condition profile, |
| `POST` | `/api/waitlist` | [`platform/api/routers/waitlist.py:84`](../../../platform/api/routers/waitlist.py#L84) |  |
| `GET` | `/dev` | [`platform/api/main.py:433`](../../../platform/api/main.py#L433) |  |
<!-- inventory:routes:end -->

## Conventions

- Everything lives under `/api/`. `{ticker}` is the upper-cased symbol (`SPY`, `QQQ`, `IWM`, `^SPX`); `{date_str}` is `YYYY-MM-DD`.
- Auth is decided per request by `AUTH_MODE` in [`platform/api/auth.py`](../../../platform/api/auth.py): `iap` trusts the IAP header, `firebase` verifies a bearer ID token, `open` passes through (local only). `/api/me`, `/api/health*`, `/api/config/firebase*` and `/api/waitlist*` are open; everything else is gated. Admin routes require the `admin` role from the `user_roles` table. Details: [ARCHITECTURE.md §7.2](05-a-ARCHITECTURE.md#72-auth-model-platformapiauthpy).
- Data comes from Cloud SQL (`market_data_*`, `etf_options_snapshots`, `journal_entries`, `trades`, `insight_reports`, …), GCS (phase reports, playbook markdown) and Alpha Vantage (live quotes). Which route reads which table: [DATA_DEPENDENCIES.md](05-c-DATA_DEPENDENCIES.md).
- The frontend that calls these routes is the Solyra SPA in `TeneikaAskew/solyra`; it is not served by this app.
