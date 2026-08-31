# Backend and API Product Plan

**Last reviewed:** 2026-08-30 · **Owner:** TBD

**VERIFIED — CODE.** Extracted from FastAPI decorators in `platform/api` at `d335f2f` by
`scripts` parsing of `@router|@app.<method>("<path>")` plus the enclosing handler, its
docstring, and the SQL identifiers in its body. **87 endpoints** resolved this way.

## How to read the Auth column

Auth is **global ASGI middleware**, not a per-handler dependency — see
[09](09-SECURITY-AUTH.md). The value below is derived mechanically from
`auth.py::_path_requires_auth`, not asserted:

- **Gated in `firebase`; unenforced in `iap`/`open`** — the default for `/api/*`. The
  middleware verifies a bearer token **only** when `AUTH_MODE=firebase`; in `iap` and
  `open` it calls through unconditionally (`auth.py:134-140`).
- **OPEN prefix — never gated** — matches one of the four prefixes at `auth.py:38`.
- **Not gated in any mode** — non-`/api/` path; `_path_requires_auth` returns `False`
  at `auth.py:129-130`. See the `/dev` exposure in [09](09-SECURITY-AUTH.md).
- **`+ _require_admin`** — handler additionally calls `admin.py:59` directly.

| Auth posture | Endpoints |
|---|---|
| Gated in `firebase`; **unenforced in `iap`/`open`** | 75 |
| **OPEN prefix — never gated** | 5 |
| Gated in `firebase`; **unenforced in `iap`/`open`** + `_require_admin` | 5 |
| **Not gated in any mode** (non-`/api/`) | 2 |

## Capability map

| Capability | Entry points | Trigger | Data | Target gap |
|---|---|---|---|---|
| Platform API | `platform/api/main.py` + 18 routers | HTTPS | Cloud SQL via `lib/data_loader`, GCS | consistent contracts, ownership, telemetry |
| Ingestion / analysis jobs | 67 Cloud Run jobs, `gcp/**` | Cloud Scheduler (58) / manual | vendors → SQL/artifacts | idempotency, freshness, provenance — see [05](05-INFRASTRUCTURE.md) |
| Discord interactions | `gcp/discord_interactions/main.py` | Discord HTTPS | interaction validation | secrets via env not Secret Manager ([#830](https://github.com/TeneikaAskew/stocks/issues/830)) |

## Endpoint inventory

### `platform/api/main.py` — 10 endpoints

| Method | Route | Purpose | Auth | Tables touched | UI |
|---|---|---|---|---|---|
| GET | `/api/health` | health check | **OPEN prefix — never gated** | via `lib/` | ✓ |
| GET | `/api/me` | Return the authenticated identity + admin flag. | **OPEN prefix — never gated** | via `lib/` | ✓ |
| GET | `/dev` | dev info | **Not gated in any mode** (non-`/api/`) | via `lib/` | — |
| GET | `/api/market/dates/{ticker}` | List available trading dates for a ticker (Cloud SQL → local fallback). | Gated in `firebase`; **unenforced in `iap`/`open`** | `market_data_intraday` | ✓ |
| GET | `/api/market/data/{ticker}/{date}` | Load intraday OHLCV data for a specific ticker and date. | Gated in `firebase`; **unenforced in `iap`/`open`** | `market_data_daily` | ✓ |
| GET | `/api/market/reference/{ticker}/{date}` | Get previous day OHLC reference levels for support/resistance. | Gated in `firebase`; **unenforced in `iap`/`open`** | `market_data_daily` | ✓ |
| GET | `/api/market/coverage` | Data coverage per symbol — drives the type-ahead's full/daily/new badges. | Gated in `firebase`; **unenforced in `iap`/`open`** | `market_data_daily`, `market_data_intraday` | ✓ |
| GET | `/api/market/sectors` | Sector rotation snapshot computed from SPDR sector ETF daily closes. | Gated in `firebase`; **unenforced in `iap`/`open`** | `market_data_daily` | ✓ |
| GET | `/api/market/most-active` | Most-active tickers snapshot, with per-ticker snapshot sparklines. | Gated in `firebase`; **unenforced in `iap`/`open`** | `market_data_intraday`, `top_movers_intraday` | ✓ |
| GET | `/{full_path:path}` | SPA fallback — serve index.html for any non-API, non-asset route. | **Not gated in any mode** (non-`/api/`) | via `lib/` | — |

### `platform/api/routers/admin.py` — 5 endpoints

| Method | Route | Purpose | Auth | Tables touched | UI |
|---|---|---|---|---|---|
| GET | `/api/admin/routes` | admin list routes | Gated in `firebase`; **unenforced in `iap`/`open`** + `_require_admin` | via `lib/` | ✓ |
| PUT | `/api/admin/routes/{role}` | admin update route | Gated in `firebase`; **unenforced in `iap`/`open`** + `_require_admin` | via `lib/` | ✓ |
| GET | `/api/admin/models` | Load the most recent structure-brief snapshot from GCS. | Gated in `firebase`; **unenforced in `iap`/`open`** + `_require_admin` | via `lib/` | ✓ |
| GET | `/api/admin/structure-brief` | Dev-only readout of the strat-engine type model's structure predictions. | Gated in `firebase`; **unenforced in `iap`/`open`** + `_require_admin` | via `lib/` | ✓ |
| GET | `/api/admin/strat-engine/state` | Operator snapshot of the on-shelf strat-engine model state. | Gated in `firebase`; **unenforced in `iap`/`open`** + `_require_admin` | via `lib/` | ✓ |

### `platform/api/routers/analytics.py` — 2 endpoints

| Method | Route | Purpose | Auth | Tables touched | UI |
|---|---|---|---|---|---|
| POST | `/api/analytics/trade-stats` | compute trade stats | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/analytics/summary/{ticker}` | Summarize rows from the ``trades`` table for a ticker. | Gated in `firebase`; **unenforced in `iap`/`open`** | `trades` | ✓ |

### `platform/api/routers/backtest.py` — 5 endpoints

| Method | Route | Purpose | Auth | Tables touched | UI |
|---|---|---|---|---|---|
| GET | `/api/backtest/results/{ticker}` | Return trades from the most recent backtest CSV for the given ticker, | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/backtest/equity/{ticker}` | Return equity curve from the most recent equity CSV for the given ticker, | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/backtest/all/{ticker}` | List all backtest runs for a ticker, sorted by timestamp descending. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| POST | `/api/backtest/replay-trades` | Score the signed-in user's labeled journal trades against actual bars | Gated in `firebase`; **unenforced in `iap`/`open`** | `journal_entries` | ✓ |
| POST | `/api/style/mine-and-validate` | Mine the caller's closed journal trades into a condition profile, | Gated in `firebase`; **unenforced in `iap`/`open`** | `journal_entries`, `playbook_cards_staging`, `user_style_results` | ✓ |

### `platform/api/routers/catalysts.py` — 5 endpoints

| Method | Route | Purpose | Auth | Tables touched | UI |
|---|---|---|---|---|---|
| GET | `/api/catalysts/events` | Get catalyst events grouped by date. | Gated in `firebase`; **unenforced in `iap`/`open`** | `earnings_calendar`, `economic_events`, `insider_transactions` | ✓ |
| GET | `/api/catalysts/ticker/{ticker}` | Get all catalyst events for a specific ticker. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | — |
| GET | `/api/catalysts/asof/{ticker}` | Unified point-in-time catalyst view for a ticker. | Gated in `firebase`; **unenforced in `iap`/`open`** | `earnings_calendar`, `earnings_history`, `insider_transactions`, `market_data_daily`, `news_sentiment` | — |
| GET | `/api/catalysts/snapshot/{ticker}` | Unified point-in-time catalyst view for a ticker. | Gated in `firebase`; **unenforced in `iap`/`open`** | `earnings_calendar`, `earnings_history`, `insider_transactions`, `market_data_daily`, `news_sentiment` | — |
| GET | `/api/catalysts/types` | Return available catalyst types and WSH upgrade info. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |

### `platform/api/routers/config.py` — 3 endpoints

| Method | Route | Purpose | Auth | Tables touched | UI |
|---|---|---|---|---|---|
| GET | `/api/config/firebase` | Public runtime auth config for the frontend bootstrap. | **OPEN prefix — never gated** | via `lib/` | ✓ |
| GET | `/api/config/indicators` | Return indicator periods, signal thresholds, and zone labels. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/config/market-hours` | Return US equity market session windows + 2026 holidays. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |

### `platform/api/routers/dashboard.py` — 2 endpoints

| Method | Route | Purpose | Auth | Tables touched | UI |
|---|---|---|---|---|---|
| GET | `/api/dashboard/brief/{ticker}` | Return daily bias / strat status for the dashboard. | Gated in `firebase`; **unenforced in `iap`/`open`** | `market_data_daily`, `premarket_analysis` | ✓ |
| GET | `/api/movement-statement` | PHASE 3 — read-only, feature-flagged movement statement. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |

### `platform/api/routers/earnings.py` — 9 endpoints

| Method | Route | Purpose | Auth | Tables touched | UI |
|---|---|---|---|---|---|
| GET | `/api/earnings/upcoming` | Next N days of earnings reporters, decorated with full history. | Gated in `firebase`; **unenforced in `iap`/`open`** | `earnings_upcoming_with_history` | — |
| GET | `/api/earnings/history/{ticker}` | Last N quarters for one ticker — full event timeline. | Gated in `firebase`; **unenforced in `iap`/`open`** | `earnings_event_outcomes` | — |
| GET | `/api/earnings/event/{ticker}/{event_date}` | Single-event drill-down. | Gated in `firebase`; **unenforced in `iap`/`open`** | `earnings_event_outcomes` | — |
| GET | `/api/earnings/lean` | Per-ticker lean leaderboard. | Gated in `firebase`; **unenforced in `iap`/`open`** | `earnings_ticker_lean` | — |
| GET | `/api/earnings/ticker/{ticker}/lean` | Lean stats for one ticker. | Gated in `firebase`; **unenforced in `iap`/`open`** | `earnings_ticker_lean` | — |
| GET | `/api/earnings/insights/grid` | The 144-row Q × bucket × structure insights table (PR-B). | Gated in `firebase`; **unenforced in `iap`/`open`** | `earnings_options_strategy_insights` | — |
| GET | `/api/earnings/insights/winners` | Top-N named winners per (structure × quintile). | Gated in `firebase`; **unenforced in `iap`/`open`** | `earnings_options_strategy_winners` | — |
| GET | `/api/earnings/calibration` | The live calibration row (PR-A + PR-B headline finding). | Gated in `firebase`; **unenforced in `iap`/`open`** | `earnings_calibration` | — |
| GET | `/api/earnings/health/ping` | Lightweight warm-up endpoint hit by the keep-warm Cloud Scheduler. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | — |

### `platform/api/routers/glossary.py` — 1 endpoints

| Method | Route | Purpose | Auth | Tables touched | UI |
|---|---|---|---|---|---|
| GET | `/api/glossary/gamma` | Return the UI-safe gamma term dictionary. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |

### `platform/api/routers/grid.py` — 5 endpoints

| Method | Route | Purpose | Auth | Tables touched | UI |
|---|---|---|---|---|---|
| GET | `/api/options/{ticker}/grid` | Live 2-D strike × expiration grid. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/options/{ticker}/{date_str}/grid` | Historical 2-D grid for a past date — EOD only. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/options/{ticker}/nodes` | Live semantic taxonomy — King / Gates / Midpoints / Hedge Nodes / | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/options/{ticker}/{date_str}/nodes` | Historical semantic taxonomy — EOD only. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/options/{ticker}/grid/timeseries` | Per-strike GEX time-series for a single expiration over the last | Gated in `firebase`; **unenforced in `iap`/`open`** | `etf_options_snapshots` | ✓ |

### `platform/api/routers/health.py` — 1 endpoints

| Method | Route | Purpose | Auth | Tables touched | UI |
|---|---|---|---|---|---|
| GET | `/api/health/freshness` | Return a freshness report for every tracked Cloud SQL data table. | **OPEN prefix — never gated** | via `lib/` | ✓ |

### `platform/api/routers/insights.py` — 12 endpoints

| Method | Route | Purpose | Auth | Tables touched | UI |
|---|---|---|---|---|---|
| GET | `/api/insights/ticker/search` | Search for tickers by keyword (company name, symbol, etc). | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/insights/ticker/{ticker}/info` | Return cached ticker details (AV OVERVIEW), fetching if needed. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/insights/ticker/{ticker}/quote` | Return latest price/volume from AV GLOBAL_QUOTE. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/insights/ticker/{ticker}/peers` | Return peer tickers from FinViz (cached). | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| POST | `/api/insights/watchlist/add` | Add a ticker to the watchlist and return its info + quote. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| DELETE | `/api/insights/watchlist/{ticker}` | Soft-delete a ticker from the watchlist (sets removed_at=NOW()). | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/insights/watchlist` | Return today's ranked candidate tickers with score breakdowns. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/insights/report/{ticker}` | Return the most recent InsightReport for the ticker. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/insights/report/{ticker}/history` | Return a scannable list of recent reports for the ticker. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/insights/reports/{report_id}` | Return a single insight report by row id. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/insights/runs/{run_id}` | Poll the status of a refresh run. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| POST | `/api/insights/chat` | Stream a Gemini response for the given mode and message. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |

### `platform/api/routers/journal.py` — 9 endpoints

| Method | Route | Purpose | Auth | Tables touched | UI |
|---|---|---|---|---|---|
| GET | `/api/journal/trades/{ticker}` | Return the signed-in user's journal entries for the ticker, newest first. | Gated in `firebase`; **unenforced in `iap`/`open`** | `journal_entries` | ✓ |
| GET | `/api/journal/examples/{ticker}` | Read-only teaching "Examples" — the UNION of the admin's own journal | Gated in `firebase`; **unenforced in `iap`/`open`** | `journal_entries`, `signal_alerts`, `trades` | ✓ |
| POST | `/api/journal/trades` | Insert a journal entry for the signed-in user. Returns it with its id. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| PATCH | `/api/journal/trades/{trade_id}` | Close an ACTIVE trade: sets exit_ts/exit_price, computes return_pct | Gated in `firebase`; **unenforced in `iap`/`open`** | `journal_entries` | ✓ |
| DELETE | `/api/journal/trades/{trade_id}` | Delete one of the signed-in user's journal entries by UUID. | Gated in `firebase`; **unenforced in `iap`/`open`** | `journal_entries` | ✓ |
| GET | `/api/journal/seed/{ticker}` | Read-only admin seed pull from the automated pipeline `trades` table. | Gated in `firebase`; **unenforced in `iap`/`open`** | `trades` | ✓ |
| POST | `/api/journal/export/{ticker}` | Write journal trades to {ticker}_trade_tracker.csv in data/signals/. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| POST | `/api/journal/import/preview` | Parse an uploaded broker CSV export and FIFO-pair round trips. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| POST | `/api/journal/import/commit` | Insert the caller-selected `PairedTrade`s from a preview. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |

### `platform/api/routers/live.py` — 6 endpoints

| Method | Route | Purpose | Auth | Tables touched | UI |
|---|---|---|---|---|---|
| GET | `/api/live/status` | Return current market open/closed status based on Eastern Time. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/live/quote/{ticker}` | Fetch real-time quote from Alpha Vantage GLOBAL_QUOTE. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/live/history/{ticker}` | Fetch last 100 1-min bars from Alpha Vantage TIME_SERIES_INTRADAY. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/live/avg-volume/{ticker}` | Return the 20-day average daily volume for RVOL calculation. | Gated in `firebase`; **unenforced in `iap`/`open`** | `market_data_daily` | ✓ |
| POST | `/api/live/indicators` | Compute indicators and CALL/PUT signals from a bar series. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| POST | `/api/live/signal-series` | Per-bar CALL/PUT signal fires for the Charts page "Sig" overlay. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |

### `platform/api/routers/options.py` — 5 endpoints

| Method | Route | Purpose | Auth | Tables touched | UI |
|---|---|---|---|---|---|
| GET | `/api/options/dates/{ticker}` | Return up to 1000 most-recent snapshot dates that have AlphaVantage data | Gated in `firebase`; **unenforced in `iap`/`open`** | `etf_options_snapshots` | ✓ |
| GET | `/api/options/{ticker}/{date_str}` | Return the AlphaVantage option chain for `ticker` on `date_str` | Gated in `firebase`; **unenforced in `iap`/`open`** | `etf_options_snapshots` | ✓ |
| GET | `/api/options/live/{ticker}/{date_str}` | Fetch the AlphaVantage HISTORICAL_OPTIONS chain live, with the same | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| POST | `/api/options/greeks` | Single source of truth for GEX/VEX/max-pain/implied-move/nodes. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/options/{ticker}/{date_str}/levels` | Stratalyst-style King/Gate/Spot/Flip taxonomy for a Cloud SQL snapshot. | Gated in `firebase`; **unenforced in `iap`/`open`** | `etf_options_snapshots` | ✓ |

### `platform/api/routers/playbook.py` — 4 endpoints

| Method | Route | Purpose | Auth | Tables touched | UI |
|---|---|---|---|---|---|
| GET | `/api/playbook/{ticker}` | Return structured setup cards for a ticker. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/reports/list/{ticker}` | List available phase report files for a given ticker (from GCS). | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/reports/{ticker}/{phase}` | Return the raw markdown text of a specific phase report for a ticker from GCS. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| POST | `/api/playbook/evaluate` | Evaluate playbook condition strings against a live snapshot. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |

### `platform/api/routers/signals.py` — 2 endpoints

| Method | Route | Purpose | Auth | Tables touched | UI |
|---|---|---|---|---|---|
| GET | `/api/signals/{ticker}` | Return historical signals for a ticker. | Gated in `firebase`; **unenforced in `iap`/`open`** | via `lib/` | ✓ |
| GET | `/api/signals/{ticker}/similar` | Return historical signals similar to the supplied bar's conditions. | Gated in `firebase`; **unenforced in `iap`/`open`** | `historical_signals` | ✓ |

### `platform/api/routers/waitlist.py` — 1 endpoints

| Method | Route | Purpose | Auth | Tables touched | UI |
|---|---|---|---|---|---|
| POST | `/api/waitlist` | INSERT INTO waitlist_signups (email, source, user_agent) | **OPEN prefix — never gated** | `waitlist_signups` | ✓ |

Table column: names are **validated against the 69 relations declared in `gcp/schema.sql`**;
unmatched identifiers are discarded rather than reported. `via lib/` means the handler issues
no inline SQL and reaches data through `lib/data_loader.py` or another `lib/` module — the
intended architecture (one source of truth for math; see [11](11-CODE-TRACEABILITY.md)).

UI column: `✓` = the route string appears in `platform/src`; `—` = no frontend caller found
(external consumer, dead endpoint, or dynamically constructed). Dead-endpoint cleanup is
tracked by [#921](https://github.com/TeneikaAskew/stocks/issues/921).

## Known defects

| Issue | Effect on this surface |
|---|---|
| [#847](https://github.com/TeneikaAskew/stocks/issues/847) | `dashboard.py` / `analytics.py` routers: PARTIAL test coverage, implicated in a real incident |
| [#925](https://github.com/TeneikaAskew/stocks/issues/925) | Legacy database query failures become empty data (P0) |
| [#926](https://github.com/TeneikaAskew/stocks/issues/926) | Second silent empty-data swallow in the data loader (P0) |
| [#837](https://github.com/TeneikaAskew/stocks/issues/837) | Pervasive `SELECT *` — data minimization |
| [#868](https://github.com/TeneikaAskew/stocks/issues/868) | Frontend Vitest and Playwright suites do not run in CI |
| [#921](https://github.com/TeneikaAskew/stocks/issues/921) | Dead API endpoints not yet identified or removed |
| [#917](https://github.com/TeneikaAskew/stocks/issues/917) | Oversized compute/persistence/rendering control points |

## Traceability

| Aspect | Reference |
|---|---|
| Origin PRs | [#255](https://github.com/TeneikaAskew/stocks/pull/255) options-heatseeker Cloudflare→FastAPI cutover · [#502](https://github.com/TeneikaAskew/stocks/pull/502) two-stage platform deploy · [#541](https://github.com/TeneikaAskew/stocks/pull/541) `/grid` + `/nodes` · [#624](https://github.com/TeneikaAskew/stocks/pull/624) earnings 8-endpoint router · [#684](https://github.com/TeneikaAskew/stocks/pull/684) waitlist API |
| Test coverage | [#503](https://github.com/TeneikaAskew/stocks/pull/503) 12 hermetic API test classes · [#505](https://github.com/TeneikaAskew/stocks/pull/505) real-SQL integration tests on ephemeral Postgres · [#509](https://github.com/TeneikaAskew/stocks/pull/509) |
| Remediation | [#518](https://github.com/TeneikaAskew/stocks/pull/518) INT-column coercion (22P02 bug class) · [#483](https://github.com/TeneikaAskew/stocks/pull/483) `pool_pre_ping` for Cloud SQL TLS drops · [#507](https://github.com/TeneikaAskew/stocks/pull/507) CPU throttling |
| Code | `platform/api/main.py`, `platform/api/routers/*.py`, `platform/api/auth.py`, `lib/data_loader.py` |
| Tests | `tests/test_api_*.py`, `platform/tests/api-smoke.spec.ts` |
