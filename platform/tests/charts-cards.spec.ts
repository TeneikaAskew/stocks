/**
 * E2E for the Phase D / Phase 4 / Phase 5 additions on the Charts page:
 *   - Strategy Conditions card (always rendered when ≥14 bars are loaded)
 *   - Similar Setups card (placeholder when no setup, populated when fired)
 *   - Sig overlay toggle in the toolbar
 *
 * Mocks the bar/reference APIs so the cards render deterministically
 * independent of the live Cloud SQL state.
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
  });

  test('Strategy Conditions card renders both CALL and PUT columns', async ({ page }) => {
    await page.goto('/charts');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('Live Strategy Conditions')).toBeVisible();
    await expect(page.getByText(/3 consecutive up moves/i).first()).toBeVisible();
    await expect(page.getByText(/3 consecutive down moves/i).first()).toBeVisible();
    // The voter result badge should exist (CALL / PUT / "No setup")
    const badge = page.getByText(/CALL · \d\/5|PUT · \d\/5|No setup/i).first();
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
