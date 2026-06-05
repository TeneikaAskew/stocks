/**
 * E2E: Signals ("/signals") — alert table with direction/strength filters.
 */
import { test, expect } from '@playwright/test';
import { mockCommon, M } from './helpers/mocks';

const MOCK_SIGNALS = {
  ticker: 'IWM',
  count: 3,
  signals: [
    {
      time: '2026-04-25 18:00:00',
      ticker: 'IWM',
      direction: 'CALL',
      score: 4.5,
      rsi: 62.0,
      ema9: 220.5,
      ema20: 220.0,
      close: 220.4,
      volume: 1_200_000,
    },
    {
      time: '2026-04-25 17:30:00',
      ticker: 'IWM',
      direction: 'PUT',
      score: 3.0,
      rsi: 38.0,
      ema9: 219.7,
      ema20: 220.1,
      close: 219.9,
      volume: 950_000,
    },
    {
      time: '2026-04-25 17:00:00',
      ticker: 'IWM',
      direction: 'CALL',
      score: 2.0,
      rsi: 55.0,
      ema9: 219.6,
      ema20: 219.8,
      close: 219.5,
      volume: 800_000,
    },
  ],
};

test.describe('Signal Explorer', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/signals/IWM*', (r) => r.fulfill(M.ok(MOCK_SIGNALS)));
    // 90-day backtest summary that backs the redesigned Performance P&L card.
    await page.route('**/api/analytics/summary/IWM*', (r) =>
      r.fulfill(M.ok({
        totalTrades: 312, closedTrades: 300, activeTrades: 12,
        winCount: 186, lossCount: 114, winRate: 0.62,
        totalPnL: 41.8, avgPnL: 0.139, maxWin: 3.4, maxLoss: -1.9,
        profitFactor: 1.74, callCount: 168, putCount: 132,
      }))
    );
  });

  test('shows the 90-day Performance P&L card', async ({ page }) => {
    await page.goto('/signals');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/performance · 90-day backtest/i)).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/win rate/i)).toBeVisible();
    await expect(page.getByText(/profit factor/i)).toBeVisible();
    await expect(page.getByText('1.74')).toBeVisible();
  });

  test('renders signal explorer heading', async ({ page }) => {
    await page.goto('/signals');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('h1, h2').filter({ hasText: /signal/i }).first()).toBeVisible();
  });

  test('lists alert rows', async ({ page }) => {
    await page.goto('/signals');
    await page.waitForLoadState('networkidle');
    // Score column should render numeric values from the mock
    await expect(page.getByText(/4\.5|3\.0|2\.0/).first()).toBeVisible();
  });

  test('shows CALL and PUT directions', async ({ page }) => {
    await page.goto('/signals');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/CALL/i).first()).toBeVisible();
    await expect(page.getByText(/PUT/i).first()).toBeVisible();
  });

  test('shows empty state when no alerts', async ({ page }) => {
    await page.route('**/api/signals/IWM*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', count: 0, signals: [] }))
    );
    await page.goto('/signals');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/no.*signal|empty/i).first()).toBeVisible();
  });

  test('renders within 7s perf budget', async ({ page }) => {
    // First-paint of the signals table includes initial bundle download +
    // GCS parquet fetch on cold cache. 7s budget is the post-warm target.
    const start = Date.now();
    await page.goto('/signals');
    await page.waitForLoadState('networkidle');
    expect(Date.now() - start).toBeLessThan(7000);
  });
});
