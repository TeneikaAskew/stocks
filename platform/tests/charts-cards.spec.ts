/**
 * E2E for the Phase D / Phase 4 / Phase 5 additions on the Charts page:
 *   - Strategy Conditions card (always rendered when ≥14 bars are loaded)
 *   - Similar Setups card (placeholder when no setup, populated when fired)
 *   - Sig overlay toggle in the toolbar
 *
 * Mocks the bar/reference APIs so the cards render deterministically
 * independent of the live Cloud SQL state. Task 10 moved both cards'
 * math server-side (POST /api/live/indicators, POST /api/live/signal-series
 * — lib/indicators.py + lib/signals.py); those two endpoints are mocked
 * here too so the spec stays fully hermetic and doesn't depend on a
 * FastAPI backend being reachable during the run.
 */
import { test, expect } from '@playwright/test';
import { mockCommon, M } from './helpers/mocks';

// 30 bars walking up — enough to clear the 14-bar RSI warmup and
// produce CALL fires deterministically.
function buildUpRunCandlestick(n = 30, base = 220, step = 0.05) {
  const bars = [];
  for (let i = 0; i < n; i += 1) {
    const close = base + i * step;
    bars.push({
      time: 1_700_000_000 + i * 60,
      open: close - step,
      high: close + 0.01,
      low: close - step - 0.01,
      close,
    });
  }
  return bars;
}

const CALL_BARS = buildUpRunCandlestick(30);
const VOLUME = CALL_BARS.map((c) => ({ time: c.time, value: 100_000 }));

const MOCK_MARKET_DATA = {
  ticker: 'IWM',
  date: '2026-04-25',
  count: CALL_BARS.length,
  candlestick: CALL_BARS,
  volume: VOLUME,
};

const MOCK_REFERENCE = {
  ticker: 'IWM',
  date: '2026-04-25',
  source: 'mock',
  open: 219.8,
  high: 222.0,
  low: 218.0,
  close: 220.0,
};

const MOCK_SIMILAR_CALL = {
  ticker: 'IWM',
  direction: 'CALL',
  rsi: 35,
  score: 4,
  rsi_band: 5,
  stats: {
    count: 240,
    avg_mfe_pct: 0.094,
    median_mfe_pct: 0.077,
    p25_mfe_pct: 0.012,
    p75_mfe_pct: 0.18,
    avg_return_5min: 0.04,
    avg_return_20min: 0.082,
    pct_profitable: 0.858,
    earliest: '2015-01-15T14:00:00+00:00',
    latest: '2026-04-07T20:00:00+00:00',
  },
  matches: [
    {
      time: '2026-04-07 14:44:00+00:00',
      direction: 'CALL',
      price: 250.41,
      score: 4,
      rsi: 35.8,
      return_pct: 0.012,
      return_5min: 0.012,
      return_20min: 0.012,
    },
  ],
};

// Server-side indicators + 10-condition strength panel (POST
// /api/live/indicators — lib/indicators.py). CALL side deliberately fires
// (strength >= 70) so the badge/fires-path is exercised deterministically;
// PUT side does not.
//
// chart_voter is the July-6 5-condition "teaching voter" restored server-side
// (POST /api/live/indicators -> chart_voter, lib/chart_voter.py) that drives
// the Charts page's Strategy Conditions card (Task 3 of the July-6
// restoration). CALL fires (met_count 3/5, PUT doesn't) so the card's
// fires-path/badge is exercised deterministically. Labels/details verbatim
// from lib/chart_voter.py's Global Constraints.
const MOCK_LIVE_INDICATORS = {
  indicators: {
    ema9: 220.5, ema20: 220.0, ema50: 219.0, rsi: 55,
    stochK: 72, stochD: 65, atr: 1.2, vwap: 220.2, stochKPrev: 70,
  },
  signals: {
    call: {
      direction: 'CALL',
      strength: 80,
      fired: true,
      conditions: [
        { id: 'c_p_ema9', label: 'Price > EMA9', met: true, current: 221.5, threshold: 220.5, operator: '>' },
        { id: 'c_p_ema20', label: 'Price > EMA20', met: true, current: 221.5, threshold: 220.0, operator: '>' },
        { id: 'c_p_ema50', label: 'Price > EMA50', met: true, current: 221.5, threshold: 219.0, operator: '>' },
        { id: 'c_p_vwap', label: 'Price > VWAP', met: true, current: 221.5, threshold: 220.2, operator: '>' },
        { id: 'c_rsi50', label: 'RSI > 50', met: true, current: 55, threshold: 50, operator: '>' },
        { id: 'c_rsi60', label: 'RSI > 60', met: false, current: 55, threshold: 60, operator: '>' },
        { id: 'c_stoch70', label: 'StochRSI > 70', met: true, current: 72, threshold: 70, operator: '>' },
        { id: 'c_rvol', label: 'RVOL > 1.0', met: true, current: 1.4, threshold: 1.0, operator: '>' },
        { id: 'c_cross', label: 'EMA9 > EMA20', met: true, current: 220.5, threshold: 220.0, operator: '>' },
        { id: 'c_atr', label: 'ATR > 2.0', met: false, current: 1.2, threshold: 2.0, operator: '>' },
      ],
    },
    put: {
      direction: 'PUT',
      strength: 20,
      fired: false,
      conditions: [
        { id: 'p_p_ema9', label: 'Price < EMA9', met: false, current: 221.5, threshold: 220.5, operator: '<' },
        { id: 'p_p_ema20', label: 'Price < EMA20', met: false, current: 221.5, threshold: 220.0, operator: '<' },
        { id: 'p_p_ema50', label: 'Price < EMA50', met: false, current: 221.5, threshold: 219.0, operator: '<' },
        { id: 'p_p_vwap', label: 'Price < VWAP', met: false, current: 221.5, threshold: 220.2, operator: '<' },
        { id: 'p_rsi50', label: 'RSI < 50', met: false, current: 55, threshold: 50, operator: '<' },
        { id: 'p_rsi40', label: 'RSI < 40', met: false, current: 55, threshold: 40, operator: '<' },
        { id: 'p_stoch30', label: 'StochRSI < 30', met: false, current: 72, threshold: 30, operator: '<' },
        { id: 'p_rvol', label: 'RVOL > 1.0', met: true, current: 1.4, threshold: 1.0, operator: '>' },
        { id: 'p_cross', label: 'EMA9 < EMA20', met: false, current: 220.5, threshold: 220.0, operator: '<' },
        { id: 'p_atr', label: 'ATR > 2.0', met: false, current: 1.2, threshold: 2.0, operator: '>' },
      ],
    },
  },
  chart_voter: {
    call: {
      direction: 'CALL',
      met_count: 3,
      total_count: 5,
      fires: true,
      conditions: [
        { id: 'call_consec_up', label: '3 consecutive up moves', met: true, detail: '3/3 last bars up' },
        { id: 'call_rsi_band', label: 'RSI 25–50 (bullish band)', met: false, detail: 'RSI 55.0' },
        { id: 'call_stoch_room', label: 'StochRSI K < 80 (room to run)', met: true, detail: 'K 72.0' },
        { id: 'call_above_vwap', label: 'Price > VWAP', met: true, detail: '221.50 > VWAP 220.20' },
        { id: 'call_above_ema9', label: 'Price > EMA9', met: false, detail: '220.50 < EMA9 221.50' },
      ],
    },
    put: {
      direction: 'PUT',
      met_count: 1,
      total_count: 5,
      fires: false,
      conditions: [
        { id: 'put_consec_down', label: '3 consecutive down moves', met: false, detail: '0/3 last bars down' },
        { id: 'put_rsi_band', label: 'RSI 50–75 (bearish band)', met: true, detail: 'RSI 55.0' },
        { id: 'put_stoch_room', label: 'StochRSI K > 20 (room to fall)', met: false, detail: 'K 72.0' },
        { id: 'put_below_vwap', label: 'Price < VWAP', met: false, detail: '221.50 < VWAP 220.20' },
        { id: 'put_below_ema9', label: 'Price < EMA9', met: false, detail: '221.50 > EMA9 220.50' },
      ],
    },
    firing: 'CALL',
  },
};

// Server-side per-bar fires (POST /api/live/signal-series — lib/signals.py).
// One CALL fire on the LAST bar so SimilarSetupsCard's "populated" branch is
// exercised deterministically (time must match the last CALL_BARS bar's
// String(time) exactly — see chartBars construction in ChartsPage.tsx).
const LAST_BAR_TIME = String(CALL_BARS[CALL_BARS.length - 1].time);
const MOCK_SIGNAL_SERIES = {
  fires: [
    { time: LAST_BAR_TIME, direction: 'CALL', score: 4, bar_index: CALL_BARS.length - 1 },
  ],
};

test.describe('Charts page — Phase D/4/5 cards', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/market/dates/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', dates: ['2026-04-25'] }))
    );
    await page.route('**/api/market/data/IWM/*', (r) => r.fulfill(M.ok(MOCK_MARKET_DATA)));
    await page.route('**/api/market/reference/IWM/*', (r) => r.fulfill(M.ok(MOCK_REFERENCE)));
    // Similar-setups: any direction returns the canned response above
    await page.route('**/api/signals/IWM/similar*', (r) => r.fulfill(M.ok(MOCK_SIMILAR_CALL)));
    // Existing /api/signals/IWM still gets called by other ChartsPage hooks
    await page.route('**/api/signals/IWM*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', count: 0, signals: [] }))
    );
    // Server-computed indicators/signals (Live Strategy Conditions panel)
    // and per-bar fires (Sig overlay + Similar Setups direction/score).
    await page.route('**/api/live/indicators', (r) => r.fulfill(M.ok(MOCK_LIVE_INDICATORS)));
    await page.route('**/api/live/signal-series', (r) => r.fulfill(M.ok(MOCK_SIGNAL_SERIES)));
    // Task 2.3: chart trades now persist through the journal API
    // (useJournalChartTrades) instead of an in-memory store — every render
    // of /charts fetches GET /api/journal/trades/{ticker}, so it needs a
    // default mock even for specs that don't otherwise touch trades.
    await page.route('**/api/journal/trades/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', source: 'cloud_sql', count: 0, trades: [] }))
    );
  });

  test('Strategy Conditions card renders both CALL and PUT columns', async ({ page }) => {
    await page.goto('/charts');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('Live Strategy Conditions')).toBeVisible();
    // July-6 labels, verbatim from lib/chart_voter.py / MOCK_LIVE_INDICATORS.chart_voter.
    await expect(page.getByText('3 consecutive up moves').first()).toBeVisible();
    await expect(page.getByText('RSI 25–50 (bullish band)').first()).toBeVisible();
    await expect(page.getByText('3 consecutive down moves').first()).toBeVisible();
    await expect(page.getByText('RSI 50–75 (bearish band)').first()).toBeVisible();
    // Card badge — CALL fires with met_count 3/5.
    await expect(page.getByText(/CALL · 3\/5/).first()).toBeVisible();
    // Column header — CALL's "3/5 ✓ fires" suffix.
    await expect(page.getByText(/3\/5 ✓ fires/).first()).toBeVisible();
  });

  test('Similar Setups card renders heading and either matches or placeholder', async ({ page }) => {
    await page.goto('/charts');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('Similar Past Setups')).toBeVisible();
    // Either the populated stats grid OR the "Waits for the voter to fire"
    // placeholder must be present — we don't pin behaviour to the exact
    // RSI/score the voter computes from synthetic bars.
    const populated = page.getByText('Matches').first();
    const placeholder = page.getByText(/waits for the voter to fire/i).first();
    await expect(populated.or(placeholder)).toBeVisible();
  });

  test('Sig overlay toggle is in the toolbar and is clickable', async ({ page }) => {
    await page.goto('/charts');
    await page.waitForLoadState('networkidle');
    const sigButton = page.getByRole('button', { name: /^Sig$/ });
    await expect(sigButton).toBeVisible();
    await sigButton.click();
    // Click again to toggle off (no assertion on visual state — just that
    // the button doesn't throw).
    await sigButton.click();
  });

  // Task 4 of the July-6 restoration: the chart wrapper lost its viewport-
  // based height to a wrapping toolbar + an effective fixed ~400px chart.
  // This pins the fix (viewport-clamped wrapper height + single-row
  // toolbar) without reintroducing the #700 overflow bug.
  test('chart fills the viewport height without horizontal overflow', async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.goto('/charts');
    await page.waitForLoadState('networkidle');
    const canvas = page.locator('canvas').first();
    const box = await canvas.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.height).toBeGreaterThan(450); // was ~400 flat before
    // overflow guard: the #700 fix must hold — canvas never wider than its card
    const card = page.locator('[data-testid="chart-card"]');
    const cardBox = await card.boundingBox();
    expect(box!.width).toBeLessThanOrEqual(cardBox!.width + 1);
    // no page-level horizontal scrollbar
    const scrollW = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientW = await page.evaluate(() => document.documentElement.clientWidth);
    expect(scrollW).toBeLessThanOrEqual(clientW + 1);
  });
});

// ─────────────────────────────────────────────────────────────────────────
// Task 6: Charts page strip-down — journal activity removed. Trade marking,
// the Trades/Analytics side panel (TradeRailCard list, Backtest-my-trades,
// "My style" tab), trade JSON/CSV export, and the admin seed-trade teaching
// layer (Playbook seed) all moved to the Journal page (/journal) — see
// docs/superpowers/specs/2026-07-11-journal-one-stop-shop-design.md
// §"Charts page (/charts) — journal activity removed". The describes that
// used to exercise those features (Task 2.3 persistence, Task 2.4 seed
// layer, Task 3.3 backtest-my-trades, Task 4.4 My style) are DELETED here,
// not adapted — the underlying UI they drove no longer exists outside an
// active bar-replay-trainer session (see replay-trainer.spec.ts, which
// keeps the trainer's own create/reveal/score path green — the ONE seam
// where Mark Entry survives, gated to `replay.active`, per the design
// spec's "the replay trainer writes source='replay' practice rows via its
// own path — that stays").
//
// This negative-assertion test is the RED->GREEN gate for the strip-down:
// it fails against the pre-strip page (Mark Entry button + "Trades (N)"
// side-panel tab are always rendered) and passes once ChartsPage.tsx no
// longer renders either outside a replay session.
// ─────────────────────────────────────────────────────────────────────────
test.describe('Charts page — no journal activity (Task 6)', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/market/dates/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', dates: ['2026-04-25'] }))
    );
    await page.route('**/api/market/data/IWM/*', (r) => r.fulfill(M.ok(MOCK_MARKET_DATA)));
    await page.route('**/api/market/reference/IWM/*', (r) => r.fulfill(M.ok(MOCK_REFERENCE)));
    await page.route('**/api/signals/IWM/similar*', (r) => r.fulfill(M.ok(MOCK_SIMILAR_CALL)));
    await page.route('**/api/signals/IWM*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', count: 0, signals: [] }))
    );
    await page.route('**/api/live/indicators', (r) => r.fulfill(M.ok(MOCK_LIVE_INDICATORS)));
    await page.route('**/api/live/signal-series', (r) => r.fulfill(M.ok(MOCK_SIGNAL_SERIES)));
    // Journal-trades fetch still happens on /charts (feeds the replay
    // trainer's leakage-cutoff filtering + Task 5.3 scorecard bookkeeping —
    // see ChartsPage.tsx), so it still needs a default mock even though the
    // trade list is no longer rendered as a browsable panel. A closed trade
    // is included on purpose, to prove the panel is genuinely gone (not just
    // hidden because there's nothing to show).
    await page.route('**/api/journal/trades/IWM', (r) =>
      r.fulfill(
        M.ok({
          ticker: 'IWM',
          source: 'cloud_sql',
          count: 1,
          trades: [
            {
              id: 'closed-trade-1',
              ticker: 'IWM',
              direction: 'CALL',
              entry_ts: '2026-04-25T09:31:00',
              exit_ts: '2026-04-25T10:15:00',
              entry_price: 220.0,
              exit_price: 222.5,
              return_pct: 1.1364,
              notes: '',
              take_profits: [223, 225],
              stop_loss: 218.5,
              status: 'win',
              source: 'chart',
              session_id: null,
              created_at: '2026-04-25T09:31:01',
            },
          ],
        })
      )
    );
  });

  test('no Mark Entry button and no Trades (N) side panel outside an active replay session', async ({ page }) => {
    await page.goto('/charts');
    await page.waitForLoadState('networkidle');

    // Mark Entry flow, the Trades/Analytics side panel, JSON/CSV export, and
    // the seed-trade Playbook panel are all gone from the default (non-replay)
    // page — even with a closed trade present for the ticker/date (proves
    // this isn't just "no trades to show").
    await expect(page.getByRole('button', { name: 'Mark Entry' })).not.toBeVisible();
    await expect(page.getByText(/^Trades \(/)).not.toBeVisible();
    await expect(page.getByText('Playbook seed')).not.toBeVisible();
    await expect(page.getByRole('button', { name: 'Backtest my trades' })).not.toBeVisible();
    await expect(page.getByText('My style')).not.toBeVisible();
  });
});
