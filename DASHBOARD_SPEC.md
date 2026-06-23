# Dashboard Spec — Signal Quality & Backtest

**Generated 2026-05-02. Last updated 2026-06-23.** Closing the visibility gap on the central operator question: *"Is my signal quality good and stable?"*

This is a **spec, not an implementation plan**. Every proposed query is grounded in a table that already exists per [DATA_DEPENDENCIES.md](DATA_DEPENDENCIES.md). The work is sequenced so each panel ships independently — no rip-and-replace.

§0 below captures the **current shipped dashboard state** (routes, auth, per-user scoping, cross-cutting features) as of 2026-06-23. §1–§5 are the original signal-quality panel spec.

---

## 0. Current shipped dashboard (state as of 2026-06-23)

The dashboard is the React + FastAPI single-page app served by the `trading-platform` Cloud Run service. Dev runs Vite on 5173 proxying `/api` → 8000; prod serves `/api/*` + the built React dist from one FastAPI port. Stack: React 19, React Router v6, TanStack Query, Zustand, Tailwind v4, HeroUI. See [docs/PLATFORM_AUDIT_2026-06-19.md](docs/PLATFORM_AUDIT_2026-06-19.md).

### 0.1 Authentication gate

`platform/api/auth.py` exposes an `AUTH_MODE` middleware with three modes:

| Mode | Identity source | Where used |
|---|---|---|
| `firebase` | Firebase ID token (`Authorization: Bearer …`) verified per gated `/api/*` request | staging service (live); prod target |
| `iap` | IAP `X-Goog-Authenticated-User-Email` header | **prod today** |
| `open` | no-op | local dev |

Pre-auth (always reachable) prefixes: `/api/health`, `/api/me`, `/api/config/firebase`. Invalid token → **401**; disallowed account → **403** (fail-closed, CLAUDE.md Rule 3.7). Allow policy is either open self-signup (`AUTH_OPEN_SIGNUP=1`) or an allow-list (`AUTH_ALLOWED_EMAILS`).

Frontend bootstrap (`main.tsx`): `GET /api/config/firebase` → init Firebase → install an authed-fetch wrapper (injects the Bearer token on same-origin `/api/*` calls) → render inside `<AuthGate>`. Components: `src/components/auth/{SignInScreen,AuthGate,SignOutButton}.tsx`, `src/lib/{firebase,authedFetch,runtimeConfig}.ts`, `src/hooks/useUser.ts`. **Status:** Firebase is live on the staging service; **prod is still on IAP** (GCIP `authorizedDomains` for the prod domain + prod `AUTH_MODE=firebase` are not flipped yet — intentional).

### 0.2 Route inventory — 13 lazy routes

All routes are lazy-loaded children of `<AppShell />` in `platform/src/App.tsx`, each wrapped in a per-route `RouteErrorBoundary` so one page's render crash leaves the shell intact.

| # | Path | Page | Notes |
|---|---|---|---|
| 1 | `/` | Dashboard | Premarket-brief strip, hero ticker, intraday Candles↔Area toggle, live signals, catalysts, news-sentiment, sector rotation, review-date picker. **Movement Read card (flag-OFF — see §0.4).** |
| 2 | `/live` | Live Market | Quote tile, 6 indicator tiles (EMA9/20/50, RSI14, StochRSI, ATR14), dual CALL/PUT 5-condition voter cards, session badge, review mode. |
| 3 | `/charts` | Charts | Candlestick+volume w/ overlays (TP1/2/3+SL, prev-day refs, gamma King/Gate/Flip/Balance, entry/exit markers, 5-cond signals), Trades\|Analytics panel, TF buttons, JSON/CSV export, Mark-Entry mode. |
| 4 | `/options` | Options Flow | Heatseeker (Swing/Trinity), Flowseeker (Live/Drilldown), Profiles (OI). ⚠️ **Heatseeker-Swing + Flowseeker render MOCK data; Profiles is REAL.** #600 fixed ~84× GEX inflation. |
| 5 | `/playbook` | Playbook | Strategy cards w/ live conditions + win-rate/avg-return; #613 real target/stop win-rate via typed `playbook_cards`. |
| 6 | `/reports` | Reports | Phase-report list + markdown viewer (GCS-backed). |
| 7 | `/signals` | Signals | Sortable table (Time/Dir/Score/Price/RSI/EMA9/Volume), filters, 90d P&L KPIs. |
| 8 | `/journal` | Journal | **Per-user** trade CRUD + equity curve + CSV export (see §0.3). |
| 9 | `/insights` | AI Insights | Tabs Briefing/Agents/History/Watchlist/Chat; multi-card report; replay-as-of; streaming chat. Watchlist tab not yet per-user (gap). |
| 10 | `/catalysts` | Catalysts | Date-grouped events + earnings + news timeline, Hot-Now, filters. |
| 11 | `/admin` | Admin | Model-routing dashboard, on-demand predict; gated by admin token / IAP email. |
| 12 | `/help` | Help | ~189-entry glossary + indicator config. |
| 13 | `/settings` | **Settings (NEW)** | Theme / nav / density / accent. Zustand + localStorage only — **no API calls**. |

Backing API routers (17, `platform/api/routers/`): live, dashboard, playbook, signals, options, grid (mounted before options), insights, journal, admin, catalysts, backtest, analytics, config, health, glossary, **magnitude (NEW — `/api/magnitude/predictions`)**, **earnings (NEW)**. Plus `/api/movement-statement` on the dashboard router (flag-OFF → 404).

### 0.3 Per-user data scoping

- **Journal** is per-user (#626). `journal.py:_journal_owner(request) = current_user_email(request) or "local"`; every read/write filters `WHERE user_email = :owner`. Index `(user_email, ticker, entry_ts DESC)`. Fail-closed 503 if a prod owner is resolved but Cloud SQL is unreachable.
- **Watchlist** endpoint wiring uses `_watchlist_owner` (#635), writing via `/api/insights/watchlist`. The table's `user_id VARCHAR(320)` defaults to `'default'` (shared admin-curated list); per-surface flags `in_brief` / `in_insight` / `signals` (read by fetchers via `gcp/fetchers/_watchlist.py load_watchlist(user_id, surface)`); soft-delete `removed_at`. **Residual gap:** the insights pipeline itself is still shared (`insight_reports`), so the Insights → Watchlist tab is not yet per-user.

### 0.4 Cross-cutting features

- **As-of review-date mode** — review-aware routes (`REVIEW_AWARE_ROUTES`) accept a review date so the operator can replay any historical session; the Dashboard/Live/Insights pages expose a review-date picker. Pipelines are fully replayable (CLAUDE.md Rule 3.5/3.6).
- **Movement Read card (flag-OFF)** — the Dashboard renders `MovementRead.tsx`, fed by `/api/movement-statement` → `lib/movement_statement.py` (single source of truth: `continuation_prob` headline; levels/expected_move/regime are context). Gated by `MOVEMENT_STATEMENT_ENABLED` + `STRUCTURE_CONTINUATION_MODEL_ENABLED` (**both default OFF**, so the endpoint returns 404 and the card is dormant). Allowed cells IWM/SPY/QQQ, 5m/15m only (30m never).
- **Mobile hamburger nav** — the `AppShell` sidebar collapses to a hamburger menu on small viewports.
- **⌘K command palette** for quick navigation.

---

## 1. What already exists

### Existing routers

| Router | Endpoints | What it answers | Source |
|---|---|---|---|
| **[`signals.py`](platform/api/routers/signals.py)** | `GET /api/signals/{ticker}` (recent signals with score/RSI/etc.); `GET /api/signals/{ticker}/similar?direction&rsi&score&rsi_band` (returns aggregate stats: count, mean/median/p25/p75 MFE, win rate, sample range) | "What does the signal table look like" + "What did historically-similar bars do" | `historical_signals` table |
| **[`analytics.py`](platform/api/routers/analytics.py)** | `POST /api/analytics/trade-stats` (ad-hoc trades from ChartsPage); `GET /api/analytics/summary/{ticker}?days=N` (win rate, profit factor, max win/loss from real `trades` table) | "What's my track record on this ticker over the last N days" | `trades` table |
| **[`backtest.py`](platform/api/routers/backtest.py)** | `GET /api/backtest/results/{ticker}`, `/equity/{ticker}`, `/all/{ticker}` | "What did the backtest produce" | GCS CSVs at `data/backtest_results/` |
| **[`dashboard.py`](platform/api/routers/dashboard.py)** | `GET /api/dashboard/brief/{ticker}` | "Today's brief KPIs for one ticker" | `premarket_analysis` + `market_data_daily` |
| **[`live.py`](platform/api/routers/live.py)** | Live indicator recompute | "What does today's bar look like in real time" | `market_data_intraday` |

### Existing React surfaces

| Page | Components shown | Strengths | Gaps for signal-quality question |
|---|---|---|---|
| **[`SignalsPage.tsx`](platform/src/routes/SignalsPage.tsx)** | Sortable signal table, score/direction/end-date filters | Good for "what just fired" inspection | **No aggregation, no time-trend, no comparison.** A row-by-row table can't answer "is the system regressing." |
| **[`DashboardPage.tsx`](platform/src/routes/DashboardPage.tsx)** | KPI cards (RSI, gap, MA-distance), `PriceAreaChart` | Best per-ticker snapshot | All point-in-time; nothing about signal *behaviour over time*. |
| **[`BacktesterSection.tsx`](platform/src/components/backtest/BacktesterSection.tsx)** | On-demand backtest run | Good for one-off `/backtest` runs | Backtest != live signal quality; backtests use the same code but without the regime drift live signals see. |
| **[`ReportsPage.tsx`](platform/src/routes/ReportsPage.tsx)**, **[`InsightsPage.tsx`](platform/src/routes/InsightsPage.tsx)** | AI insight digest + reports | Good for narrative analysis | No quantitative signal-quality trend. |

### What partially answers "is my signal quality good and stable"

Three fragments exist, none stitched together:

1. **`/api/signals/{ticker}/similar`** → returns historical-bar percentiles for a *single* (RSI, score) match. Useful per-bar; **not aggregate**.
2. **`/api/analytics/summary/{ticker}?days=N`** → win rate / profit factor for a *single ticker*. **No per-strategy breakdown, no time series**.
3. **[`gcp/signal_quality_alarm.py`](gcp/signal_quality_alarm.py)** computes trailing-7d-vs-prior-7d clean-rate from `signal_metrics`, posts to Discord on regression. **Output is a Discord alarm only — never reaches a UI panel.**

The `signal_metrics` table — populated by `scripts/signal_quality_report.py`, holding per-row `cls_5m`/`cls_15m`/`.../cls_240m` classification and per-timeframe `return_*m` MFE — is the **richest signal-quality dataset in the entire stack**, and the operator can't see any of it without running psql.

---

## 2. Gap analysis

Five questions about signal performance the operator cannot currently answer from the dashboard:

| # | Question | Data needed | Where it already lives |
|---|---|---|---|
| **G1** | "Is my clean-rate trending up, flat, or regressing over the last 90 days?" | Daily roll-up of `cls_60m == 'CLEAN_HIT'` rate | [`signal_metrics`](DATA_DEPENDENCIES.md#signal_metrics) — `cls_60m` column, indexed on `(ticker, entry_time)` |
| **G2** | "Which of my strategies has the best edge right now?" | Per-strategy clean-rate + sample size + mean return | `signal_metrics.strategy` + `cls_60m` + `return_60m` |
| **G3** | "How does my signal's edge decay across timeframes (does 60m work but 240m doesn't)?" | Per-timeframe clean-rate aggregate | `signal_metrics.cls_5m..cls_240m` + `return_5m..return_240m` |
| **G4** | "When does my signal work — high-RSI vs low-RSI, CALL vs PUT?" | Win-rate split by RSI bucket × direction | `historical_signals.entry_rsi` + `trade_type` + `return_pct` |
| **G5** | "What hours of the trading day produce the cleanest signals?" | Win-rate by hour-of-day | `historical_signals.entry_time` + `return_pct` |

All five questions are answerable with single SQL queries against tables that already exist and are already being populated daily. **No fetcher work, no schema changes, no new ML.** The work is purely: SQL → API endpoint → React panel.

---

## 3. Proposed panels

Five panels, each independently shippable. Listed in implementation order — earlier panels reuse the router scaffolding the later ones extend.

### Panel 1: 📈 Signal Quality Trend

**Question answered:** *G1 — Is my clean-rate stable, improving, or regressing?*

**SQL** (the `signal_quality_alarm` already computes this for two windows; this panel runs it for N weeks):
```sql
SELECT
  DATE_TRUNC('week', entry_time)::date AS week,
  COUNT(*) FILTER (WHERE cls_60m IS NOT NULL AND cls_60m != 'INSUFFICIENT_DATA')      AS n_total,
  COUNT(*) FILTER (WHERE cls_60m = 'CLEAN_HIT')                                       AS n_clean,
  100.0 * COUNT(*) FILTER (WHERE cls_60m = 'CLEAN_HIT')
        / NULLIF(COUNT(*) FILTER (WHERE cls_60m IS NOT NULL AND cls_60m != 'INSUFFICIENT_DATA'), 0)
                                                                                       AS clean_rate_pct
FROM signal_metrics
WHERE entry_time >= NOW() - make_interval(days => :days)
  AND (:strategy IS NULL OR strategy = :strategy)
  AND (:ticker   IS NULL OR ticker = :ticker)
GROUP BY 1
ORDER BY 1 ASC;
```

**Endpoint:** `GET /api/signal-quality/trend?days=90&tf=cls_60m&strategy=momentum&ticker=`

**React shape:**
- Component: `SignalQualityTrendPanel.tsx`
- Chart: line chart (recharts `LineChart`), x = week (date), y = `clean_rate_pct`
- Overlay: a dashed horizontal line at the `prior_window_avg - 3pp` level (the regression threshold from `signal_quality_alarm.REGRESSION_THRESHOLD_PP`). Crossing below = the alarm fires.
- Tooltip: shows `n_total / n_clean / clean_rate_pct` per week. Sample-size badge if `n_total < 50` (the `MIN_SAMPLE_SIZE` from the alarm).
- Filters at top of panel: timeframe (5m/15m/30m/60m/90m/120m/240m), strategy (dropdown from `SELECT DISTINCT strategy FROM signal_metrics`), ticker (optional).
- Refresh: 1 hour (matches `signal-quality-report` cadence).

---

### Panel 2: 🎯 Per-Strategy Edge Comparison

**Question answered:** *G2 — Which strategy has the best edge?*

**SQL:**
```sql
SELECT
  strategy,
  COUNT(*) FILTER (WHERE cls_60m IS NOT NULL AND cls_60m != 'INSUFFICIENT_DATA')      AS n_total,
  COUNT(*) FILTER (WHERE cls_60m = 'CLEAN_HIT')                                       AS n_clean,
  100.0 * COUNT(*) FILTER (WHERE cls_60m = 'CLEAN_HIT')
        / NULLIF(COUNT(*) FILTER (WHERE cls_60m IS NOT NULL AND cls_60m != 'INSUFFICIENT_DATA'), 0)
                                                                                       AS clean_rate_pct,
  AVG(return_60m) FILTER (WHERE cls_60m = 'CLEAN_HIT')                                AS avg_clean_return,
  AVG(return_60m)                                                                     AS avg_return_overall
FROM signal_metrics
WHERE entry_time >= NOW() - make_interval(days => :days)
GROUP BY strategy
ORDER BY clean_rate_pct DESC NULLS LAST;
```

**Endpoint:** `GET /api/signal-quality/by-strategy?days=30&tf=cls_60m`

**React shape:**
- Component: `StrategyComparisonPanel.tsx`
- Chart: horizontal bar chart, y = strategy name, x = `clean_rate_pct`. Bar opacity = `log(n_total)` so noisy small-sample strategies are visually de-weighted.
- Annotation per bar: `{n_total} signals, +{avg_clean_return:.2%} avg return on hits`.
- Refresh: daily (post-report run).

---

### Panel 3: ⏱ Per-Timeframe Decay Curve

**Question answered:** *G3 — Does my signal's edge decay with time horizon?*

**SQL:**
```sql
WITH stats AS (
  SELECT
    SUM(CASE WHEN cls_5m   = 'CLEAN_HIT' THEN 1 ELSE 0 END)::float / NULLIF(SUM(CASE WHEN cls_5m   IS NOT NULL AND cls_5m   != 'INSUFFICIENT_DATA' THEN 1 ELSE 0 END), 0) * 100 AS cr_5m,
    SUM(CASE WHEN cls_15m  = 'CLEAN_HIT' THEN 1 ELSE 0 END)::float / NULLIF(SUM(CASE WHEN cls_15m  IS NOT NULL AND cls_15m  != 'INSUFFICIENT_DATA' THEN 1 ELSE 0 END), 0) * 100 AS cr_15m,
    SUM(CASE WHEN cls_30m  = 'CLEAN_HIT' THEN 1 ELSE 0 END)::float / NULLIF(SUM(CASE WHEN cls_30m  IS NOT NULL AND cls_30m  != 'INSUFFICIENT_DATA' THEN 1 ELSE 0 END), 0) * 100 AS cr_30m,
    SUM(CASE WHEN cls_60m  = 'CLEAN_HIT' THEN 1 ELSE 0 END)::float / NULLIF(SUM(CASE WHEN cls_60m  IS NOT NULL AND cls_60m  != 'INSUFFICIENT_DATA' THEN 1 ELSE 0 END), 0) * 100 AS cr_60m,
    SUM(CASE WHEN cls_90m  = 'CLEAN_HIT' THEN 1 ELSE 0 END)::float / NULLIF(SUM(CASE WHEN cls_90m  IS NOT NULL AND cls_90m  != 'INSUFFICIENT_DATA' THEN 1 ELSE 0 END), 0) * 100 AS cr_90m,
    SUM(CASE WHEN cls_120m = 'CLEAN_HIT' THEN 1 ELSE 0 END)::float / NULLIF(SUM(CASE WHEN cls_120m IS NOT NULL AND cls_120m != 'INSUFFICIENT_DATA' THEN 1 ELSE 0 END), 0) * 100 AS cr_120m,
    SUM(CASE WHEN cls_240m = 'CLEAN_HIT' THEN 1 ELSE 0 END)::float / NULLIF(SUM(CASE WHEN cls_240m IS NOT NULL AND cls_240m != 'INSUFFICIENT_DATA' THEN 1 ELSE 0 END), 0) * 100 AS cr_240m
  FROM signal_metrics
  WHERE entry_time >= NOW() - make_interval(days => :days)
    AND (:strategy IS NULL OR strategy = :strategy)
)
SELECT * FROM stats;
```

**Endpoint:** `GET /api/signal-quality/decay-curve?days=30&strategy=momentum`

**React shape:**
- Component: `DecayCurvePanel.tsx`
- Chart: line chart, x = timeframe (`5m, 15m, 30m, 60m, 90m, 120m, 240m`), y = `clean_rate_pct`. Best when the curve is monotonically decreasing — that's the "edge decays with time" pattern. A flat or rising curve = the system is good at slow signals but bad at fast ones (or vice versa).
- Refresh: daily.

---

### Panel 4: 🌡 Regime-Conditioned Win Rate

**Question answered:** *G4 — When does my signal work — high-RSI vs low-RSI, CALL vs PUT?*

**SQL:**
```sql
SELECT
  width_bucket(entry_rsi, 0, 100, 10) AS rsi_bucket,
  UPPER(trade_type)                   AS direction,
  COUNT(*)                            AS n_signals,
  100.0 * SUM(CASE WHEN return_pct > 0 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0) AS win_rate_pct,
  AVG(return_pct)                     AS avg_return_pct,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY return_pct) AS median_return_pct
FROM historical_signals
WHERE ticker = :ticker
  AND entry_time >= NOW() - make_interval(days => :days)
GROUP BY 1, 2
ORDER BY 1, 2;
```

**Endpoint:** `GET /api/signal-quality/by-regime?ticker=SPY&dimension=rsi&days=90`

**React shape:**
- Component: `RegimeHeatmapPanel.tsx`
- Chart: heatmap (custom or via `recharts` ScatterChart with sized cells), rows = RSI buckets (0-10, 10-20, ..., 90-100), columns = `CALL` / `PUT`, cell value = `win_rate_pct`, cell color = green→red gradient. Tooltip: `n_signals, avg_return_pct, median_return_pct`.
- Phase 2: extend `dimension` to `gap_pct_bucket` / `volatility_regime` (those live in `historical_signals.extra` JSONB).
- Refresh: daily.

---

### Panel 5: 🕒 Time-of-Day Distribution

**Question answered:** *G5 — What hours of the trading day produce the cleanest signals?*

**SQL:**
```sql
SELECT
  EXTRACT(HOUR FROM entry_time AT TIME ZONE 'America/New_York') AS hour_et,
  COUNT(*)                            AS n_signals,
  100.0 * SUM(CASE WHEN return_pct > 0 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0) AS win_rate_pct,
  AVG(return_pct)                     AS avg_return_pct
FROM historical_signals
WHERE ticker = :ticker
  AND entry_time >= NOW() - make_interval(days => :days)
GROUP BY 1
HAVING COUNT(*) >= 10
ORDER BY 1;
```

**Endpoint:** `GET /api/signal-quality/by-hour?ticker=SPY&days=90`

**React shape:**
- Component: `TimeOfDayPanel.tsx`
- Chart: bar chart, x = hour-ET (`9, 10, 11, 12, 13, 14, 15` — the trading hours), y = `win_rate_pct`. Bar height secondary annotation: `n_signals` printed inside the bar.
- Phase 2: split CALL vs PUT as grouped bars.
- Refresh: weekly (slow-changing).

---

## 4. Implementation plan

### File-level changes

**New router:** `platform/api/routers/signal_quality.py` (~300 LOC)
- 5 endpoints (one per panel above).
- Each endpoint imports `gcp.database.query_to_dataframe` (existing pattern, see `analytics.py:33`).
- Reuse `gcp.signal_quality_alarm.compute_clean_rate` (already a pure helper) to keep clean-rate semantics consistent between the alarm and the dashboard.
- Mount in `platform/api/main.py` alongside existing routers.

**New React route:** `platform/src/routes/SignalQualityPage.tsx`
- Top-level page that imports the 5 panel components.
- Filters at the page level (timeframe, strategy, ticker, days window) — passed as props to panels.
- Uses `react-query` for fetch + cache (existing pattern, see SignalsPage).
- Add nav-bar entry pointing to `/signal-quality`.

**5 new panel components** under `platform/src/components/signal-quality/`:
- `SignalQualityTrendPanel.tsx` — Panel 1
- `StrategyComparisonPanel.tsx` — Panel 2
- `DecayCurvePanel.tsx` — Panel 3
- `RegimeHeatmapPanel.tsx` — Panel 4
- `TimeOfDayPanel.tsx` — Panel 5

Each component is self-contained — own `useQuery` hook, own loading / error / empty states, own chart.

**Reused libs** (no changes):
- `gcp.signal_quality_alarm.compute_clean_rate` and `RegressionResult` (Python)
- `gcp.database.query_to_dataframe` (Python)
- `recharts` (already in `package.json` per existing dashboard panels)
- `@tanstack/react-query` (existing)
- Color tokens from `var(--bull)` / `var(--bear)` / `var(--warn)` (existing CSS vars per SignalsPage)

### Independent shipping order

| Step | Ships | Hours | Independently usable? |
|---|---|---:|:---:|
| **1** | New router scaffolding + `/signal-quality/trend` endpoint + `SignalQualityTrendPanel` (Panel 1) | 5-7h | ✅ — single-panel page is the highest-leverage drop |
| **2** | `/by-strategy` endpoint + `StrategyComparisonPanel` (Panel 2) | 4-6h | ✅ |
| **3** | `/decay-curve` endpoint + `DecayCurvePanel` (Panel 3) | 4-6h | ✅ |
| **4** | `/by-regime` endpoint + `RegimeHeatmapPanel` (Panel 4) | 6-8h | ✅ — heatmap is the heaviest UI component (custom cells) |
| **5** | `/by-hour` endpoint + `TimeOfDayPanel` (Panel 5) | 3-5h | ✅ |
| **+ buffer** | Tests, docs, polish, mobile-responsive checks | 4-6h | n/a |

Each step adds one endpoint + one panel + one nav addition. Steps 2-5 can ship in any order after step 1 — they share the router file and the page chrome.

### What's deliberately NOT in scope

- **No new tables.** Every query reads from `signal_metrics` and `historical_signals` — both already populated.
- **No fetcher changes.** No backfill needed. The `signal-quality-report` Cloud Run Job already populates the data.
- **No ML.** Pure SQL roll-ups, no model training.
- **No alerting.** That's the `signal_quality_alarm`'s job. This is read-only visibility.
- **Backtest dashboard polish is excluded** — `BacktesterSection.tsx` and the `/api/backtest/*` endpoints already cover the backtest case. This spec is about **live signal quality**, not backtest replay.

---

## 5. One-week implementation estimate

| Day | Work | Cumulative output |
|---|---|---|
| **Mon** | Router scaffolding (new file, mount, types, error paths). Panel 1 endpoint + UI. End-of-day: trend chart visible on staging. | 1 panel live |
| **Tue** | Panel 2 (strategy comparison). End-of-day: bar chart shipped. | 2 panels live |
| **Wed** | Panel 3 (decay curve). End-of-day: line chart shipped. | 3 panels live |
| **Thu** | Panel 4 (regime heatmap — heaviest UI component). End-of-day: heatmap visible but maybe rough. | 4 panels live |
| **Fri** | Panel 5 (time-of-day) + polish + tests + nav-bar integration + responsive checks. | All 5 panels live |

**Total: 5 working days, 30-35 hours.** Buffer of 4-6h for the heatmap component (it's custom — `recharts` doesn't ship a great heatmap; you'll either build a CSS-grid heatmap or wrap a `ScatterChart`). If the heatmap turns into a 2-day job, swap Friday's polish for Day 5 of heatmap finish and ship the time-of-day panel the following Monday.

---

## Implementation tips

- **Cache aggressively.** All five queries are aggregations over `signal_metrics` / `historical_signals` — they don't change minute-to-minute. Use `TTLCache` at the router level (60-300 sec) and `staleTime` at the React-query level (60-600 sec). The exact cache busts can be triggered by the `signal-quality-report` finishing — but since that's a daily job, hourly cache is fine.
- **Sample-size badges everywhere.** The `signal_quality_alarm.MIN_SAMPLE_SIZE = 50` rule should propagate — any panel cell with `n_total < 50` should visually fade (50% opacity) so you don't read noise as signal. The alarm already enforces this; the UI should match.
- **Strategy filter is the secret weapon.** All the panels accept an optional `strategy` filter. Comparing "momentum" vs "mean_reversion" on the same ticker over the same 30 days — that's where the dashboard's leverage compounds.
- **Don't mix `historical_signals` and `signal_metrics` in the same panel.** They tag rows with overlapping but not identical predicates. Pick one source per panel:
  - Panels 1-3 use `signal_metrics` (cls_*  → CLEAN_HIT semantics).
  - Panels 4-5 use `historical_signals` (return_pct → win-rate semantics).

---

## Tables referenced

Per [DATA_DEPENDENCIES.md](DATA_DEPENDENCIES.md):

| Table | Read by this spec | Writer | Status |
|---|---|---|---|
| [`signal_metrics`](DATA_DEPENDENCIES.md#signal_metrics) | Panels 1, 2, 3 | `scripts/signal_quality_report.py` (Cloud Run Job `signal-quality-report`) | ✅ Live |
| [`historical_signals`](DATA_DEPENDENCIES.md#historical_signals) | Panels 4, 5 | `gcp/historical_signals.py` (replay harness, also written by `backfill_ticker` for `/replay`) | ✅ Live |
| [`trades`](DATA_DEPENDENCIES.md#trades) | Already covered by existing `/api/analytics/summary/{ticker}` (no new panels for this) | `gcp/trade_logger.py` | ✅ Live |
