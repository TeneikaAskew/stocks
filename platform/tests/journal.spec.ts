/**
 * E2E: Trade Journal ("/journal") — list trades, add/delete, export CSV.
 */
import { test, expect } from '@playwright/test';
import { mockCommon, M } from './helpers/mocks';

const MOCK_TRADES = {
  ticker: 'IWM',
  count: 1,
  trades: [
    {
      trade_id: '00000000-0000-0000-0000-000000000001',
      ticker: 'IWM',
      direction: 'long',
      entry_ts: '2026-04-24T14:00:00Z',
      exit_ts: '2026-04-24T15:30:00Z',
      entry_price: 220.0,
      exit_price: 222.5,
      shares: 100,
      pnl: 250.0,
      notes: 'Breakout above PD high.',
    },
  ],
};

test.describe('Trade Journal', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/journal/trades/IWM*', (r) => r.fulfill(M.ok(MOCK_TRADES)));
  });

  test('renders journal heading', async ({ page }) => {
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('h1, h2').filter({ hasText: /journal/i }).first()).toBeVisible();
  });

  test('lists existing trades', async ({ page }) => {
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/breakout above pd high/i)).toBeVisible();
  });

  test('shows empty state when no trades', async ({ page }) => {
    await page.route('**/api/journal/trades/IWM*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', count: 0, trades: [] }))
    );
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/no.*trade|empty|add.*trade/i).first()).toBeVisible();
  });

  test('renders within 5s perf budget', async ({ page }) => {
    const start = Date.now();
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');
    expect(Date.now() - start).toBeLessThan(5000);
  });
});
