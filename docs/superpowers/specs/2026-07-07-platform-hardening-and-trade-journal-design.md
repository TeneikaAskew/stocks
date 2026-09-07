# Platform Hardening + Trade Journal Program — Design Spec

**Date:** 2026-07-07
**Status:** Approved approach (Approach A — unify on `journal_entries`), pending final spec review
**Scope:** One program, six phases: site-wide remediation, data foundations (ticker
type-ahead / sector rotation / news), unified per-user trade log, labeled-trade
backtest + benchmark, style-learning walk-forward with a playbook seam, and a
bar-by-bar chart replay trainer.

---

## 1. Goals

1. Every number the site shows is correct and honestly labeled (Rule 3.7 end-to-end).
2. Charts stay inside their sections and resize responsively.
3. The dashboard's Sector rotation and News cards show real data.
4. The ticker control is an obvious, extensible type-ahead input backed by the
   internal SYMBOL_SEARCH proxy; picking a new symbol auto-ingests it.
5. /charts becomes a learn-to-trade surface: per-user trade marking that persists,
   admin seed trades as the teaching layer, real backtests of the user's labeled
   style, and a bar-replay trainer — all feeding the playbook loop over time.

## 2. Non-goals (this program)

- User trades appearing in the playbook UI (seam built, flag stays off; playbook
  remains admin-only, fueled by the pipeline `trades` table).
- Intraday ingestion for arbitrary tickers (intraday stays SPY/IWM/QQQ; new
  tickers get daily bars via the watchlist union).
- A `users` table / role system. Identity remains Firebase/IAP email +
  `ADMIN_EMAIL` env; per-user data keys on `user_email`.
- Options-flow live tape (Flowseeker stays mock, but banner-honest).

## 3. Global constraints

- **No silent fallbacks** (CLAUDE.md Rule 3.7): no `?? 0` / `|| 0` / `.get(k, 0)`
  on financial fields; explicit `Unavailable` / "—" states; loud errors.
- **Financial math lives in Python `lib/`** and is served by FastAPI; the React
  app renders. No new client-side indicator/P&L math; existing duplication on
  ChartsPage is removed in Phase 0.
- **Replay parity** (Rule 3.6): indicator snapshots for style learning use the
  production `signal_monitor.calculate_indicators` path, never `add_all_indicators`
  directly, never hand-rolled bar iteration.
- **Schema before traffic**: additive, idempotent migrations (`ADD COLUMN IF NOT
  EXISTS`) applied via the `apply-schema-migrations` job before the service
  revision that reads them takes traffic.
- **Pipeline/user separation**: the pipeline `trades` table stays pure (no user
  rows); user data lives only in `journal_entries` (schema comment at
  gcp/schema.sql:1089-1093 governs).
- **Branch + PR only; conventional commits; no AI branding.** Capacity + cost
  notes in any PR touching fetchers or Cloud Run jobs (Rule 0).
- **TDD**: every task ships its test first (pytest for lib/api, Playwright for UI).

---

## 4. Phase 0 — Remediation wave

Twelve fixes. Each is independently testable; they may batch into 2–3 PRs
(numbers/units · layout/charts · hygiene).

| # | Defect | Fix | Test |
|---|---|---|---|
| 0.1 | Dashboard Top-setup "Avg return" 100× inflated (`DashboardPage.tsx:467` multiplies percent units by 100; playbook API returns percents — `playbook.py:312`) | Render `topCard.avg_return` un-multiplied via the shared percent formatter | Unit test on the formatter usage; Playwright asserts the dashboard and /playbook show the same value for the same card |
| 0.2 | Backtester Avg Return / Avg Win / Avg Loss show "+0.00%" — backend passes raw fractions (`platform/api/routers/backtest.py` `_summarize_returns`, ~0.003-scale values from `lib/backtest.py:531-533`) and `BacktesterSection.tsx:355,360,365,230` formats with `toFixed(2)` and no ×100 | `_summarize_returns` emits true percents (×100) for `avg_return_pct`, `avg_win_pct`, `avg_loss_pct`, `total_return_pct`; `win_rate` stays a 0–1 fraction and remains ×100'd only in the UI (document the convention in the router docstring); per-trade `Return %` column converted server-side too | pytest asserting `_summarize_returns` output units on a fixture CSV; Playwright asserts non-zero rendered values |
| 0.3 | Journal counts null `return_pct` as 0% trades (`JournalPage.tsx:169,180,436` `?? 0`) | Null-returns excluded from win-rate/avg/total/equity math and rendered "—"; stats footer shows "N of M trades have returns" | Playwright with a fixture entry lacking `return_pct` |
| 0.4 | `PriceAreaChart` hardcodes `$` + `toFixed(0)` axis (repeated "$1/$0" ticks) and is used for a percent series on /journal (`PriceAreaChart.tsx:69,154`, `JournalPage.tsx:304`) | Add `valueFormatter?: (v: number) => string` + `tooltipFormatter?` props (default: current dollar format with adaptive decimals so ticks never repeat); /journal passes percent formatters | Vitest/unit on tick uniqueness for a 0.9–1.1 range; Playwright axis-label assertion |
| 0.5 | Dashboard candle chart overflows its 260px card (`CandlestickChart.tsx:306-312` forces `minHeight: 400`; `DashboardPage.tsx:547-555` slot has no clip) | `minHeight` becomes an optional prop (default none); `/charts` passes `minHeight={400}`; dashboard slot adds `overflow-hidden`. Existing ResizeObserver then reports true height — responsiveness restored | Playwright: dashboard candle canvas height ≤ card height; /charts unchanged |
| 0.6 | Backtester axes + run selection: y-axis `$…toFixed(0)` on ~1.0 normalized equity; x-axis strips year (`BacktesterSection.tsx:170,175`); header says "12 runs" but only `blobs[0]` is viewable | Y-axis adaptive-decimal normalized format; x-axis `YYYY-MM-DD` → `MM/DD/YY` keeping year; add a run `Select` fed by `/api/backtest/all/{ticker}` and thread `run` param through `/api/backtest/results|equity` | pytest for the run-param plumbing; Playwright picks an older run |
| 0.7 | Reports XSS: `marked.parse` into `dangerouslySetInnerHTML` unsanitized (`ReportsPage.tsx:83`) | Sanitize with `dompurify` (new dep) before injection | Unit test: script tag in fixture markdown is stripped |
| 0.8 | Fabricated data without clear banners: Flowseeker tab + ContractDrilldown fully mock; Heatseeker TacticalCard mock with a small banner | Prominent `DemoDataBanner` (amber, top of panel, non-dismissable) on all mock surfaces | Playwright asserts banner visible on each mock tab |
| 0.9 | Dead controls / render-phase side effects: SwingMode Refresh + Glossary no-op (`SwingMode.tsx:273-278`); AdminPage logout during render (`AdminPage.tsx:179`); ChartsPage render-phase `setLocalSelectedDate` (`ChartsPage.tsx:114`) | Wire Refresh to the grid query invalidation, Glossary to `/help`; move logout into `useEffect`; keep render-time adjustment only where it follows the render-adjustment pattern (document) | Playwright: Refresh triggers refetch; unit lint pass |
| 0.10 | UTC "today" bugs: `todayISO()` uses `toISOString()` (Dashboard `:147-149`, Playbook `:59-60`, Catalysts local-date math) | Shared `platform/src/lib/dates.ts` with `todayET()` / `toETDateString()`; all "today" computations use ET | Vitest with mocked clock at 23:30 ET |
| 0.11 | Live review-mode "change" baseline differs from live (open→last vs prior-close→last, `LiveMarketPage.tsx:186-200`) | Review-mode change computed vs prior session close from `/api/market/reference`; label the field "vs prior close" in both modes | Playwright review-mode assertion with fixture data |
| 0.12 | ChartsPage duplicates Python indicator/voter math in TS (`lib/indicators.ts` + `ChartsPage.tsx:183-196,226,785`) | Charts consumes `POST /api/live/indicators` (already exists, used by /live and /playbook); TS `computeIndicators`/`computeStrategySignals` deleted with their call sites | pytest parity fixture already covers server; Playwright asserts Live Strategy Conditions still render |

## 5. Phase 1 — Data foundations

### 5.1 Ticker type-ahead (`TickerCombobox`)

- **Backend**: reuse `GET /api/insights/ticker/search?keywords=&limit=` (SYMBOL_SEARCH
  proxy via `lib/ticker_info.py`). Response: `{keywords, results: [{symbol, name,
  type, region, currency, match_score}]}`.
- **Data badge**: new `GET /api/market/coverage?symbols=A,B,C` returns per-symbol
  `{intraday: bool, daily: bool}` from one batched query over
  `market_data_intraday` presence + `market_data_daily`. Suggestion rows render
  `full` (intraday+daily) / `daily` / `new` badges.
- **Frontend**: `platform/src/components/shared/TickerCombobox.tsx` replaces
  `TickerSelect` at every call site. Input with chevron + border (obvious
  affordance), 300ms debounce (`useDebouncedValue` hook — new), keyboard nav,
  quick-pick row pinning IWM/SPY/QQQ. Store: `Ticker` type widens to `string`
  (`types/index.ts:1`); `tickerStore` gains `recentTickers: string[]` (persisted,
  max 8).
- **Auto-ingest**: choosing a `new` symbol calls the existing watchlist-add
  endpoint (backed by `gcp/fetchers/_watchlist.py add_to_watchlist`), then shows
  a toast + page-level notice: "Tracking AAPL — daily data lands after tonight's
  fetch." Pages keep their existing honest empty/unavailable states meanwhile.
  No synchronous backfill in the request path.
- **Infra pre-req**: verify `av-api-key` is mounted on the `trading-platform`
  and `trading-platform-staging` Cloud Run services (`platform/deploy.sh:84`
  lists it; `platform/GCP_DATA_DICTIONARY.md:42,119` says the deployed service
  lacks it — resolve the drift, mount if missing). SYMBOL_SEARCH fails loudly
  (503 with reason) if the key is absent — no fabricated suggestions.

### 5.2 Sector rotation

- Add the 11 SPDR ETFs `XLK XLF XLE XLV XLI XLY XLP XLU XLB XLRE XLC` to the
  daily fetch universe (`gcp/fetchers/fetch_market_data.py:33` `TICKERS`, or the
  watchlist if less invasive — decide in plan; fetch path already handles ETFs).
  One-time backfill of ≥ 30 trading days via the fetcher's `--tickers`/`--date`
  flags. Capacity: +11 symbols on an existing batched daily job — negligible;
  note in PR per Rule 0.
- New `GET /api/market/sectors` (router: `platform/api/routers/market_meta.py`
  or nearest existing market router): returns per-ETF `{symbol, sector_name,
  close, chg_1d_pct, chg_5d_pct, as_of}` computed in SQL/pandas from
  `market_data_daily`. If any ETF has no rows → that row is `status:
  "unavailable"`, never zeros. If ALL are missing → 200 with
  `{status: "unavailable", reason}` and the card keeps an honest empty state.
- Dashboard card: ranked horizontal bars (green/red) by `chg_1d_pct`, 1D/5D
  toggle, "as of {date}" caption. Replaces the hardcoded `Unavailable` at
  `DashboardPage.tsx:633-636`.

### 5.3 News

- **Diagnosis first** (dispatch via `./scripts/db_query_cr.sh`, queries drafted in
  the investigation): confirm freshness of `news_sentiment` and the topic
  distribution before tuning constants. (Local dispatch currently hangs on this
  Windows shell — run from CI/Cloud Shell or fix the dispatcher first; do not
  skip.)
- **Server fix** (`platform/api/routers/catalysts.py:_db_catalyst_events`): news
  stops sharing the forward event window. News clause becomes
  `published_ts >= NOW() - INTERVAL '48 hours'` (independent of `date_from`),
  keeps `relevance_score >= 0.7`, and the topic filter expands to the union the
  fetcher actually writes: `mergers_and_acquisitions, earnings, ipo,
  economy_monetary, technology, financial_markets, life_sciences`. Add
  `catalyst_type = 'NEWS'` passthrough so the frontend's existing branch works.
- **Frontend**: News card renders source + relative published time; "0 fresh"
  only when the (now backward-looking) query is truly empty.

## 6. Phase 2 — One trade log

### 6.1 Schema (additive, idempotent — `gcp/schema.sql`)

```sql
-- direction ('CALL'|'PUT') already exists and is the option type; no duplicate column.
ALTER TABLE journal_entries
    ADD COLUMN IF NOT EXISTS stop_loss    DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS tp1          DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS tp2          DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS tp3          DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS status       VARCHAR(10) NOT NULL DEFAULT 'closed',  -- 'active'|'win'|'loss'|'breakeven'|'closed'
    ADD COLUMN IF NOT EXISTS source       VARCHAR(10) NOT NULL DEFAULT 'manual',  -- 'chart'|'manual'|'replay'
    ADD COLUMN IF NOT EXISTS session_id   UUID;
ALTER TABLE journal_entries ALTER COLUMN exit_ts    DROP NOT NULL;
ALTER TABLE journal_entries ALTER COLUMN exit_price DROP NOT NULL;
CREATE INDEX IF NOT EXISTS idx_journal_entries_user_source
    ON journal_entries (user_email, source, entry_ts DESC);
```

`return_pct` stays NULL until a trade closes; analytics exclude NULLs (0.3).

### 6.2 API (`platform/api/routers/journal.py`, extend)

- Existing CRUD grows the new fields (Pydantic model additive; old clients fine).
- `PATCH /api/journal/trades/{id}` — close an active trade (exit_ts/price;
  server computes `return_pct` — Python, not TS).
- `GET /api/journal/seed/{ticker}?date=` — read-only admin seed layer from the
  pipeline `trades` table (id, direction, entry/exit time+price, return_pct,
  strat_combo, conditions_met). No auth beyond sign-in; never writable.

### 6.3 Frontend

- `tradeStore` (in-memory) is replaced by TanStack Query against the journal API;
  Mark-Entry flow (`ChartsPage.tsx` `completeTrade`/exit click) POSTs/PATCHes.
  Optimistic updates; trades survive refresh; keyed by signed-in `user_email`
  (open mode: a fixed `local@dev` owner).
- Admin seed trades render as muted/dashed markers + a "Playbook seed" tag in
  the side panel, read-only, toggleable (`Show seed trades`, default ON).
- Analytics tab: user's trades only (server `/api/analytics/trade-stats`), plus
  a benchmark row computed from the seed layer for the same ticker/date range.
- /journal gains nothing visually except the new fields rendering when present —
  it now shows chart-marked trades too (`source` chip).

## 7. Phase 3 — Backtest v1: replay + benchmark

- `lib/backtest.py` gains `replay_labeled_trades(trades: list[LabeledTrade],
  bars: pd.DataFrame) -> ReplayReport` — pure, deterministic:
  - Recomputes each trade's P&L from actual bars (validates chart-click prices
    against bar range; flags impossible fills).
  - Benchmarks each entry bar against the production voter (via
    `signal_monitor.calculate_indicators` + `_evaluate_strategies_for_bar` glue —
    production path, Rule 3.6) → "system agreed / disagreed".
  - Simulates the strategy's own exit config (TP/SL/time-stop) from the same
    entry → "your exit vs system exit" delta in bps.
- `POST /api/backtest/replay-trades` `{ticker, trade_ids[] | session_id}` →
  per-trade scorecard + aggregates `{n, win_rate, avg_return_pct (percent units),
  system_agreement_rate, exit_edge_bps}`. Missing bars for a trade → that trade
  is `status: "unavailable"` with reason; never zero-filled.
- UI: "Backtest my trades" button on the Charts side panel + a scorecard modal;
  results also persist to `backtest_reports`-style storage only if trivially
  compatible, else displayed-only (decide in plan; no new table required for v1).

## 8. Phase 4 — Style learning → playbook seam

- `lib/style_miner.py` (new): given a user's closed trades, snapshot indicator/
  strat state at each entry bar (production indicator path), mine recurring
  condition sets (frequency-threshold rules over the same condition vocabulary
  the playbook uses), emit a `StyleProfile` (JSON: conditions, direction,
  support count).
- Walk-forward: `WalkForwardValidator` runs the `StyleProfile` as a signal
  source (new adapter — engine unchanged) over available history →
  `user_style_results` table (new, shaped like `walk_forward_results` + 
  `user_email`, `profile JSONB`, `created_at`).
- Playbook seam: miner writes candidate cards to `playbook_cards_staging` (new
  table, same shape as `playbook_cards` + `user_email`, `status 'candidate'`).
  The playbook UI does NOT read it in this program (flag `PLAYBOOK_USER_CARDS`
  hardcoded off) — admin-only playbook preserved, flip is a later program.
- UI: "My style" panel on /charts Analytics tab: mined conditions, walk-forward
  win rate/expectancy with sample sizes, honest "not enough closed trades"
  state below 10 closed trades.

## 9. Phase 5 — Replay trainer

- /charts gains a **Replay session** mode: pick any past session (existing date
  picker) → Play/Pause/Step, speeds 1×/5×/20×. Bars reveal client-side from the
  already-fetched `/api/market/data` day (no new endpoint, no future-bar
  leakage: the un-revealed remainder is never rendered and indicator overlays
  are re-requested per revealed prefix or hidden during playback — decide in
  plan; leakage is a hard fail).
- Mark Entry / exits work mid-playback at the revealed bar's timestamp.
- Session end → scorecard via `POST /api/backtest/replay-trades` and trades
  saved with `source='replay'`, shared `session_id` (client-generated UUID).
- Analytics can filter by source, so practice sessions don't pollute "real"
  journal stats by default (default filter: `source != 'replay'`, with a
  visible toggle).

## 10. Error handling & honesty (program-wide)

- Every new endpoint: explicit 4xx/5xx with reason; `UNAVAILABLE` envelopes for
  vendor-dependent data (SYMBOL_SEARCH without key → 503 + reason).
- Every new card/panel: loading, error, and empty states designed in, with
  copy; no spinner-forever, no fabricated zeros.
- Fetcher changes keep failure-loud behavior (no `continue-on-error`).

## 11. Testing strategy

- **pytest**: `_summarize_returns` units; `replay_labeled_trades` on fixture
  bars (wins/losses/impossible fills/missing bars); style miner determinism;
  sectors endpoint SQL (I/O-shape test: N symbols → 1 query); news window filter;
  coverage endpoint batching.
- **Playwright** (hermetic `/api/config/firebase` mock + fixture routes):
  combobox search/badge/auto-ingest flows; journal persistence across reload;
  seed-layer toggle; backtest scorecard; replay trainer play/step/no-future-bars;
  each Phase 0 fix's assertion.
- **Reviewer gates**: fallback-guard, trading-logic-reviewer,
  replay-integrity-reviewer on the relevant PRs; capacity notes on fetcher PRs.
- **Deploy order per phase**: schema migration job → staging → prod (pinned
  revision promoted by name) → post-deploy verification.

## 12. Open items tracked into the plan

1. Confirm `av-api-key` presence on both platform Cloud Run services (drift
   check) — Phase 1 pre-req task.
2. Run the news diagnostic SQL from a working dispatcher before finalizing the
   48h window + topic set constants.
3. Decide SPDRs-in-`TICKERS` vs watchlist-union placement at plan time.
4. Decide indicator-overlay behavior during replay playback (hide vs prefix
   recompute) at plan time — leakage-free is the constraint.
