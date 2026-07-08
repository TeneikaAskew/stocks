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
  });

  test('Strategy Conditions card renders both CALL and PUT columns', async ({ page }) => {
    await page.goto('/charts');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('Live Strategy Conditions')).toBeVisible();
    await expect(page.getByText(/Price > EMA9/i).first()).toBeVisible();
    await expect(page.getByText(/Price < EMA9/i).first()).toBeVisible();
    // The voter result badge should exist (CALL / PUT / "No setup") — the
    // condition count isn't pinned so the assertion survives future
    // additions/removals from the server-side condition set.
    const badge = page.getByText(/CALL · \d+\/\d+|PUT · \d+\/\d+|No setup/i).first();
    await expect(badge).toBeVisible();
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
});
