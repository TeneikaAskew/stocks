# Stocks Platform Redesign — Data Evaluation & Implementation Plan

> Companion to the Claude Design handoff (`Stocks Platform Redesign.html` +
> `FRONTEND_STACK.md`). This doc answers the two questions that gate the
> redesign: **what backend data can each new surface actually be wired to**,
> and **in what order do we build**. Surfaces are tagged
> **LIVE** (endpoint + table exist today), **PARTIAL** (data exists but needs a
> small backend addition), or **MOCK** (no data source — requires a new vendor
> or substantial engineering).
>
> Audited 2026-06-05. Branch base: `feature/trading-platform`
> (commit `a2077eb` — Phase-1 shell already merged).

---

## 0. Where the redesign stands

The **app shell is already built** on `feature/trading-platform`
(`a2077eb`): HeroUI v3 + Tailwind v4, the Obsidian Analyst token system in
`src/index.css` (surfaces, density, accent swatches, brand mark, top-tabs,
command palette, settings popover), and the shell components
(`AppShell`, `Sidebar`, `TopTabs`, `CommandPalette`, `SettingsMenu`,
`Brand`, `navConfig`). `settingsStore` persists nav-pattern / density /
accent. ⌘K works.

What's left is **page-level** work: restyling the 12 existing route pages to
the prototype, adding the new sub-tab structures (Options Flow → 4 tabs,
AI Insights → 2 tabs, Strat Engine, Backtests), and the shared primitives
every page reuses.

The existing pages are **already wired to real backend data** (17 hooks,
~50 endpoints). The prototype is mock-only. So the redesign is a
**restyle + restructure of wired pages + a few new surfaces**, not a
from-scratch rebuild. Wherever the prototype shows data we already have,
we wire it; where we don't, we render an explicit "data unavailable" state
(per CLAUDE.md Rule 3.7 — no silent fallbacks), never a fabricated number.

---

## 1. AlphaVantage API — capability audit

**Key:** `ALPHA_VANTAGE_API_KEY` (`.env.example:62`); newer fetchers also
accept `AV_API_KEY`, plus `ALPHA_VANTAGE_API_KEY_2..5` for parallel
rate-limit distribution.

**Tier: PREMIUM — top tier, 1200 req/min entitlement** (confirmed by the
account owner, 2026-06-05).

> ⚠️ **Config drift — backend follow-up.** The repo config understates the
> real limit: `lib/config.py:113` has `rpm: int = 150` and the
> `platform/api/routers/options.py:9` comment says "600 req/min". The actual
> key does **1200 RPM**. Because pacing is centralized in
> `AlphaVantageConfig.seconds_per_call`, bumping the one `rpm` constant to
> 1200 unlocks ~8× fetcher throughput (a 50-ticker backfill that the stale
> 150 value paces at ~minutes could run far faster), with `tenacity` backoff
> still absorbing any 429s. This is a one-line change but touches *every*
> fetcher's wall-clock, so treat it as a deliberate capacity change
> (CLAUDE.md Rule 0): re-check each Cloud Run Job's task-timeout headroom
> before/after. Listed in §4 follow-ups.

**Routing: every external request flows through GCP — verified.** The browser
**only** ever calls the GCP-hosted FastAPI (`/api/*` on Cloud Run); it never
calls AlphaVantage (or any vendor) directly. Every `fetch()` in
`platform/src/**` targets `/api/...` (the lone external URL is a docs `href`
to wallstreethorizon.com, not a data call). The AV key is read server-side
only — `platform/api/main.py:71`, `routers/grid.py:361`, `routers/live.py:44`
(`os.environ["AV_API_KEY"|"ALPHA_VANTAGE_API_KEY"]`, sourced from Secret
Manager in Cloud Run) — so the key is never shipped to the client. The data
path is **browser → Cloud Run FastAPI → AlphaVantage → Cloud SQL**, or
browser → API → Cloud SQL for cached rows. **The redesign must preserve this:
no client-side vendor calls, ever** (see §5).

### Endpoints in use today

| AV function | Fetcher | Writes table | Cadence |
|---|---|---|---|
| `TIME_SERIES_INTRADAY` (1-min, `entitlement=realtime`, extended hours) | `fetch_alphavantage_intraday.py` | `market_data_intraday` | monthly bulk + intraday |
| `TIME_SERIES_DAILY_ADJUSTED` | `fetch_market_data.py` | `market_data_daily` | daily |
| `HISTORICAL_OPTIONS` (EOD chains) | `fetch_av_historical_options.py` | `etf_options_snapshots` (`market_session='EOD'`) | 09 PM ET daily |
| `REALTIME_OPTIONS` (intraday chains, 5-min) | `fetch_av_realtime_options.py` | `etf_options_snapshots` (`REALTIME`) | */5 09–15 ET |
| `NEWS_SENTIMENT` | `fetch_news_sentiment.py` | `news_sentiment` | daily |
| `EARNINGS` | `fetch_earnings_history.py` | `earnings_history` | periodic |
| `INSIDER_TRANSACTIONS` | `fetch_insider_transactions.py` | `insider_transactions` | periodic |
| `TOP_GAINERS_LOSERS` | `fetch_top_movers.py` | `top_movers_daily` | daily |
| `OVERVIEW` (fundamentals) | `lib/ticker_info.py` (cache) | `ticker_info` | on-demand |

Technical indicators (RSI/EMA/MACD/ATR/Bollinger/VWAP) are **computed in
Python** (`lib/indicators.py`) from OHLCV, **not** pulled from AV indicator
endpoints — keeps one source of math truth.

### Available on the tier but NOT yet used (integration opportunities)

- **`REALTIME_OPTIONS` is already paid for but only sampled every 5 min** —
  the Flowseeker "live tape" still can't be built from it (snapshots, not
  prints), but a near-real-time **gamma/OI delta tape** (what changed since
  the last 5-min snapshot) *is* buildable from data we already store.
- `MARKET_STATUS` — replace the hardcoded session clock in `lib/config.py`.
- `INTRADAY` extended-hours is on; pre/post-market bars are available for the
  hero ticker + brief.
- `BALANCE_SHEET` / `INCOME_STATEMENT` / `CASH_FLOW` — fundamentals for an
  earnings-surprise context card.
- `SECTOR_PERFORMANCE` — a real sector-rotation tile (prototype mobile shows
  one) instead of the finviz scrape.

---

## 2. Cloud SQL data landscape (`gcp/schema.sql`)

| Domain | Tables |
|---|---|
| **Market** | `market_data_daily` (OHLCV + 60 indicators), `market_data_intraday` (1-min, partitioned), `top_movers_daily` |
| **Options / gamma** | `etf_options_snapshots` (chains, EOD+REALTIME), `v_etf_options_node` (VIEW: net gamma/vega per strike×expiry), `earnings_options_snapshots`, `daily_rates` (risk-free + div yield) |
| **Signals / strat** | `signal_alerts` (live fires), `historical_signals` (5-condition voter), `trades` (backtest), `signal_metrics` (HIT/WRONG/NOISE/MIXED), `strat_levels` |
| **Brief** | `premarket_analysis` (+ `_history`), bias/RSI/strat/FTFC/playbook levels |
| **AI insights** | `insight_reports` (+ `_history`), `insight_runs`, `model_routing` |
| **Earnings / catalysts** | `earnings_calendar`, `earnings_history`, `earnings_reactions`, `sec_filings`, `insider_transactions`, `economic_events` |
| **News** | `news_sentiment` (label + score + topics) |
| **Journal** | `journal_entries` (user log + pgvector embedding) |
| **Admin / calibration** | `ticker_calibration`, `exit_config_overrides`, `ranker_runs`, `watchlists`, `ticker_info` |

---

## 3. Redesign surface → data status

This is the table that decides what to wire vs. stub. Endpoints verified in
`platform/api/routers/`.

| Surface | Component | Status | Endpoint / gap |
|---|---|---|---|
| **Overview** | Brief hero, bias, KPIs | **LIVE** | `/api/dashboard/brief/{t}`, `/api/live/quote/{t}`, `/api/market/reference/{t}/{d}` |
| | Hero ticker row (SPY/QQQ/IWM/DIA/VIX) | **LIVE** | `/api/live/quote/{t}` per ticker |
| | Latest signals table | **LIVE** | `/api/signals/{t}` |
| | Top setup | **LIVE** | `/api/playbook/{t}` |
| **Options Flow** | Heatseeker (strike×expiry GEX/VEX heatmap + drill-in) | **LIVE** | `/api/options/{t}/{d}/grid`, `useGammaLevels` |
| | Trinity (SPY/QQQ/SPX GEX ladders) | **LIVE** | `/api/options/{t}/nodes` (union) |
| | Profiles (GEX-by-strike, net-GEX curve, OI) | **LIVE** | `/api/options/{t}/{d}/levels` |
| | Profiles (Charm heatmap, Expected-move cone) | PARTIAL | charm = gamma decay not stored; cone needs IV skew surface |
| | Flowseeker (sweep/block/split print tape) | **MOCK** | AV gives 5-min snapshots, not prints — needs a tick vendor. Ship a **gamma/OI delta tape** from snapshots instead. |
| **Strat Engine** | Calibrated class {1/2U/2D/3} per ticker×TF | **LIVE*** | `/api/admin/strat-engine/predict` (admin-only today) |
| | ECE / reliability per cell | **LIVE*** | `/api/admin/strat-engine/state` |
| | Candle replay w/ prediction overlay | PARTIAL | bars LIVE; per-bar predictions not persisted (backfill or compute) |
| | FTFC continuity (multi-TF) | PARTIAL | `ftfc_direction` exists; cross-TF agreement not tracked |
| | Stage-4 gate verdicts | **MOCK** | logic in `lib/strategies`; not persisted |
| **AI Insights** | Briefing (House Views, Persona Plans, Bull/Bear, Risk, Trade Plan) | **LIVE** | `/api/insights/report/{t}` (7-agent JSONB) |
| | Pre-market context, Similar trades | **LIVE** | `/api/dashboard/brief/{t}`, `/api/signals/{t}/similar` |
| | Agents (model routing) | **LIVE** | `/api/admin/routes` |
| | Agents (per-step reasoning trace) | PARTIAL | run metadata LIVE; chain-of-thought not persisted |
| **Catalysts** | Earnings, SEC filings, Insider, News+sentiment | **LIVE** | `/api/catalysts/events` |
| | Econ / Fed | PARTIAL | FRED + Benzinga subset only |
| **Signals** | Classification, P&L card | **LIVE** | `/api/signals/{t}`, `/api/analytics/summary/{t}` |
| | Walk-forward (rolling decay) | PARTIAL | equity curve LIVE; rolling metrics not computed |
| **Journal** | Trades, P&L curve, KPIs | **LIVE** | `/api/journal/trades/{t}`, `/api/analytics/*` |
| **Admin** | Pipeline freshness, audit history, routing | **LIVE** | `/api/health/freshness`, history tables, `/api/admin/routes` |
| | Ticker calibration, Ranker decisions | PARTIAL | tables exist; **no read endpoint yet** |

\* LIVE but gated behind `/api/admin/*` — a user-facing read route is a small add.

**Headline:** the overwhelming majority of the redesign is **LIVE** today.
The only true MOCK is the Flowseeker print-tape (no tick vendor) and Stage-4
gates. Everything tagged PARTIAL is a small, well-scoped backend follow-up,
not a blocker.

---

## 4. Phased implementation plan

Each phase is a shippable PR onto `feature/trading-platform`. Ordering
favors (a) the user's stated #1 goal — an actionable Overview — and
(b) the "headline" Heatseeker view, while front-loading the shared
primitives every later phase reuses.

- **Phase 2 — Foundation primitives** *(this PR)*
  `lib/format.ts` (fmtMoney/fmtGex/fmtSigned/pct) + `components/primitives/`
  (`Pill`, `KpiTile`, `Metric`, `Delta`, `ScoreStars`, `RangeBar`, `DirTag`,
  `Card`) + their CSS in `index.css`. Redesign the **Overview** (landing
  page) on real data to prove the language end-to-end.

- **Phase 3 — Options Flow (the headline).** 4-tab shell (Heatseeker /
  Trinity / Profiles / Flowseeker). Wire Heatseeker grid + drill-in,
  Trinity ladders, GEX/OI profiles to LIVE endpoints. Flowseeker ships as a
  snapshot-delta tape with an honest "5-min snapshot, not prints" badge.

- **Phase 4 — AI Insights.** Briefing + Agents tabs on the LIVE 7-agent
  `insight_reports` payload + model routing.

- **Phase 5 — Catalysts + Signals.** 5-tab catalysts on `/api/catalysts/events`;
  Signals classification table + P&L card.

- **Phase 6 — Strat Engine + Backtests.** Replay (candles + overlay) and
  Structure Brief. Add the user-facing read route for predictions/ECE.
  Backtests = Runs / Walk-forward / Exit-overrides / Playbook / Journal tabs.

- **Phase 7 — Admin, Reports, Help, Mobile responsiveness.** Calibration +
  ranker read endpoints; responsive pass across all pages.

### Small backend follow-ups (sequence alongside the phase that needs them)
0. **Bump `lib/config.py` `rpm` 150 → 1200** to match the real key entitlement
   (re-check Cloud Run Job task-timeouts per CLAUDE.md Rule 0). Update the
   stale "600 req/min" comment in `routers/options.py`.
1. User-facing read route for strat-engine predictions/ECE (un-gate `/api/admin/strat-engine/*`).
2. `GET /api/admin/calibration/{ticker}` + `GET /api/admin/ranker/runs` (tables exist).
3. Persist per-bar strat predictions (backfill job) for the replay tape.
4. Rolling walk-forward metrics column/endpoint on `trades`.

---

## 5. Guardrails

- **All requests route through GCP** (verified §1): the browser only ever
  calls `/api/*` (Cloud Run FastAPI); it never calls AlphaVantage or any other
  vendor directly, and the API key never reaches the client. Every redesigned
  hook fetches `/api/...`; new vendor integrations are added as FastAPI routes
  (or Cloud Run fetchers → Cloud SQL), not client-side calls.
- **No silent fallbacks** (CLAUDE.md 3.7): missing price/Greek/score renders
  `—` + an "unavailable" badge, never `0`/`fillna`.
- **One source of math** (CLAUDE.md): all financial math stays in `lib/`
  (Python) behind FastAPI; the frontend only renders.
- **HeroUI + Tailwind v4** primitives per `FRONTEND_STACK.md`; no new chart
  deps — Recharts/D3/lightweight-charts are already installed.
