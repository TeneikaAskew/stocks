# Hardcoded Values Remediation — Implementation Plan & Progress

## Context

The Live dashboard's ATR and StochRSI showed wrong values because the math
was duplicated in TypeScript (`platform/src/lib/indicators.ts`) and drifted
from the canonical Python implementation in `lib/indicators.py`. A full-site
audit identified 21 similar issues — financial math, config thresholds, and
mock data hardcoded into the React app instead of sourced from the API.

**Architectural rule going forward:** the app must never duplicate financial
math or hold divergent config values. Python (`lib/`) and Cloud SQL are the
single source of truth.

---

## Part 1 — HIGH severity (math that drifts)

### 1A. Options Greeks math — ✅ DONE

**Was:** `platform/src/lib/greeksCalculator.ts` had hardcoded
`SPOT_MULTIPLIER`, `GEX_MULTIPLIER`, `VEX_MULTIPLIER`, ATM filter `0.02`,
and `sqrt(252) * 0.01` implied-move annualization in TypeScript.

**Fix:** New endpoint `POST /api/options/greeks` in
`platform/api/routers/options.py` runs all GEX/VEX/zero-gamma/max-pain/
implied-move math server-side. Frontend posts `{options, spot_price}`,
gets back `{aggregated, gex_by_strike, metrics, nodes, config}`.

- [x] Server endpoint created
- [x] Frontend hook `useOptionsGreeks` created in
      `platform/src/hooks/useOptionsGreeks.ts`
- [x] OptionsFlowPage refactored to consume the hook
- [x] `platform/src/lib/greeksCalculator.ts` deleted

### 1A.1. Gamma math consolidation into `lib/gamma.py` — ✅ DONE

**Follow-up to 1A:** the math was server-side, but still inline in
`platform/api/routers/options.py` (functions `_aggregate_by_strike`,
`_total_gex`, `_zero_gamma`, `_detect_nodes`, etc.). That meant the
AI insights pipeline, the CLI, and the Pine companion all couldn't
reuse it — they'd have to reimplement.

Worse: `_total_gex` used `dealer_gamma = -gamma` unconditional while
`_aggregate_by_strike` used calls-add / puts-subtract — opposite signs
on the same data, so the metrics card and the heatmap displayed
contradictory totals.

**Fix:** New module `lib/gamma.py` is the canonical implementation.
`options.py` now imports from it, and total GEX is derived from the
sum of per-strike values (algebraically guaranteed consistent).

- [x] `lib/gamma.py` created with full taxonomy (King/Gate/Spot/Flip,
      regime classification, layered spot estimation)
- [x] Sign-bug fix: per-strike sign convention is the only one used
- [x] `platform/api/routers/options.py` refactored to import from `lib.gamma`
- [x] New endpoint `GET /api/options/{ticker}/{date}/levels` for the
      AI agent / CLI / Pine consumers (chain-source-aware)
- [x] `lib/agents/summarizers.summarize_gamma_levels` + new "gamma"
      analyst role in the AI pipeline
- [x] CLI `scripts/show_gamma_levels.py` refactored to import `lib.gamma`
- [x] `tradingview-pine-scripts/gamma-levels-overlay-v2` Pine companion
- [x] Documentation: `docs/gamma_levels.md`
- [x] Tests: 25 in `tests/test_gamma.py`, 12 in `tests/test_options_router.py`

### 1B. Node detection — ✅ DONE

**Was:** `platform/src/lib/nodeAnalyzer.ts` had hardcoded
`MIN_THRESHOLD = 500`, `TOP_NODES_COUNT = 5`, `MIDPOINT_THRESHOLD = 0.5`.

**Fix:** Folded into `POST /api/options/greeks` — returns
`nodes: { kingNode, gatekeepers, midpoints, allNodes }` alongside metrics.
Thresholds defined once at top of `options.py`.

- [x] Node detection moved to `_detect_nodes()` in `options.py`
- [x] Returned in the same response as Greeks (one round trip)
- [x] OptionsFlowPage uses `greeks.nodes` directly
- [x] `platform/src/lib/nodeAnalyzer.ts` deleted

### 1C. Trade analytics — ✅ DONE

**Was:** `useTradeAnalytics` computed win rate, profit factor, max loss,
avg win/loss client-side from a trades array.

**Fix:** Two new endpoints in `platform/api/routers/analytics.py`:
- `POST /api/analytics/trade-stats` — accepts ad-hoc trade list (used by
  ChartsPage annotation trades), returns full stats
- `GET /api/analytics/summary/{ticker}?days=N` — reads the real `trades`
  table in Cloud SQL and aggregates (used by Dashboard backtest section)

- [x] Server endpoints created
- [x] `useTradeAnalytics` rewritten to POST trades to the server
- [x] New `useTradeSummary` hook for DB-backed summary
- [x] Verified IWM: 144 trades, 80.6% win rate, profit factor 1.81

### 1D. Playbook condition parser — ✅ DONE

**Was:** `playbookEvaluator.ts` had ~200 lines of regex-based condition
parsing client-side, with hardcoded thresholds (StochRSI 20/80,
proximity 0.5%, ORB 30 min).

**Fix:** New endpoint `POST /api/playbook/evaluate` in
`platform/api/routers/playbook.py` accepts a snapshot + either flat
`conditions` or batched per-card `batches`, returns parallel results.
Thresholds (`PRICE_PROXIMITY_PCT`, `STOCH_OVERSOLD_DEFAULT`, etc.)
defined once at module top.

- [x] Server endpoint created with both flat + batch modes
- [x] `usePlaybookEvaluation` and `usePlaybookBatch` hooks created
- [x] `playbookEvaluator.ts` reduced to snapshot-builder helpers only
- [x] DashboardPage and PlaybookPage wired to server evaluation

### 1E. Options display range — ✅ DONE

**Was:** Hardcoded `±15%` strike range filter on OptionsFlowPage.

**Fix:** Server returns `config.strike_range_pct` (default 0.15) in the
Greeks response. Frontend reads it directly: `greeks.config.strike_range_pct`.

- [x] Display range tied to server config
- [x] Heatmap label shows `±{Math.round(rangePct * 100)}%` dynamically

### 1F. Chart take-profit default — ⏳ DEFERRED

**Was:** `ChartsPage.tsx:230` defaults TP size to `0.33` (three equal
tranches).

**Fix planned:** Read from a new `/api/user/preferences` endpoint or
user settings store. Deferred — chart annotation trades are ephemeral
and the default is a UX choice, not a correctness issue.

- [ ] Future work — log as follow-up issue

---

## Part 2 — MEDIUM severity (config that should be versioned)

### 2A. `/api/config/indicators` — ✅ DONE

**Was:** RSI zone labels (30/45/55/70) and other indicator thresholds
hardcoded in `DashboardPage.tsx`, `LiveMarketPage.tsx`, etc.

**Fix:** New endpoint in `platform/api/routers/config.py` returns
periods, thresholds, and zones from `lib/config.py`.

- [x] Server endpoint created
- [x] `useIndicatorConfig` + `classifyRsiZone` helper in
      `platform/src/hooks/useConfig.ts`
- [x] DashboardPage RSI zone labels now data-driven
- [x] HelpPage glossary now substitutes RSI/EMA/StochRSI/RVOL/min-conditions
      values from the live config (with `lib/config.py` defaults as fallback)

### 2B. `/api/config/market-hours` — ✅ DONE

**Was:** `CandlestickChart.tsx:45-46` hardcoded `RTH_START = 9*60+30`
and `RTH_END = 16*60`. Same constants duplicated in `live.py`.

**Fix:** New endpoint returns the canonical session boundaries plus
2026 holiday list. CandlestickChart now consumes via `useMarketHours`.

- [x] Server endpoint created
- [x] `useMarketHours` hook in `platform/src/hooks/useConfig.ts`
- [x] CandlestickChart wired with fallback to standard NYSE hours

### 2C. Unify ATM tolerance — ✅ DONE

**Was:** `greeksCalculator.ts` used 0.02; `OptionsFlowPage.tsx:165` used
0.005 — different "ATM" definitions in different places.

**Fix:** Server returns `config.atm_tolerance` (0.02). The OptionsFlowPage
heatmap reads it via `greeks.config.atm_tolerance` and passes it to the
heatmap component.

- [x] Single source of truth in Python
- [x] Heatmap uses server-supplied tolerance

---

## Part 3 — LOW severity (UI defaults — deferred)

These are cosmetic / UX preferences that don't affect correctness. Logged
as follow-up; do not block on them:

- [ ] Timeframe options array → `/api/config/available-timeframes`
- [ ] Chat modes → returned in insights response schema
- [ ] Default chart timeframe → user settings
- [ ] Reference date default → server-sourced trading calendar
- [ ] Default review time → user settings

---

## Earlier related fix (already shipped before this audit)

### 0. Indicator math (ATR / StochRSI / RSI) — ✅ DONE

The bug that triggered this whole audit. Replaced client-side
`computeIndicators` / `computeSignals` in `LiveMarketPage` with
`POST /api/live/indicators`. Server uses `lib/indicators.py` and returns
both indicators (EMA/RSI/StochRSI/ATR/VWAP + `stochKPrev` for crossover
checks) and dashboard CALL/PUT signal conditions.

- [x] Server endpoint created
- [x] `useLiveIndicators` hook
- [x] LiveMarketPage, DashboardPage, PlaybookPage all wired
- [x] `platform/src/lib/indicators.ts` reduced to types only
- [x] Verified RSI/StochRSI/ATR match Python to 4 decimal places

---

## Files Modified / Created

### Created
- `platform/api/routers/analytics.py` — trade stats endpoints
- `platform/api/routers/config.py` — indicators + market-hours config
- `platform/src/hooks/useConfig.ts` — config hooks + RSI zone classifier
- `platform/src/hooks/useLiveIndicators.ts` — server-side indicator hook
- `platform/src/hooks/useOptionsGreeks.ts` — server-side Greeks hook
- `platform/src/hooks/usePlaybookEvaluation.ts` — server-side evaluator hook

### Modified
- `platform/api/main.py` — wired in 2 new routers
- `platform/api/routers/live.py` — added `POST /api/live/indicators`
- `platform/api/routers/options.py` — added `POST /api/options/greeks`
- `platform/api/routers/playbook.py` — added `POST /api/playbook/evaluate`
- `platform/src/components/charts/CandlestickChart.tsx` — uses market-hours config
- `platform/src/hooks/useTradeAnalytics.ts` — POSTs to server, adds `useTradeSummary`
- `platform/src/routes/HelpPage.tsx` — glossary fetches indicator config
- `platform/src/lib/indicators.ts` — types only
- `platform/src/lib/playbookEvaluator.ts` — snapshot-builder helpers only
- `platform/src/routes/DashboardPage.tsx` — server-side eval + RSI zones
- `platform/src/routes/LiveMarketPage.tsx` — server-side indicators + signals
- `platform/src/routes/OptionsFlowPage.tsx` — server-side Greeks + nodes
- `platform/src/routes/PlaybookPage.tsx` — server-side eval

### Deleted
- `platform/src/lib/greeksCalculator.ts`
- `platform/src/lib/nodeAnalyzer.ts`

---

## Verification

- TypeScript compiles with zero errors
- All 12 routes return HTTP 200 in Playwright smoke test
- Zero console errors across all pages
- Server-computed values match Python to <0.02 absolute difference
- Screenshots captured for every page + Insights tabs (`/tmp/page-screenshots/`)

## Outstanding follow-ups

| Item | Priority | Notes |
|---|---|---|
| Chart TP default size (0.33) | LOW | User preference, not correctness |
| Timeframe options array | LOW | Should come from API |
| Chat modes list | LOW | Should come with insights schema |
