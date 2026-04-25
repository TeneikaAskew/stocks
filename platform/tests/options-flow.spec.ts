/**
 * E2E: Options Flow ("/options") — chain table, expiry/strike filters, flow rows.
 */
import { test, expect } from '@playwright/test';
import { mockCommon, M } from './helpers/mocks';

const MOCK_DATES = {
  ticker: 'IWM',
  dates: ['2026-04-25', '2026-04-24'],
};

const MOCK_CHAIN = {
  ticker: 'IWM',
  date: '2026-04-25',
  options: [
    { type: 'call', strike: 218, open_interest: 4000, gamma: 0.03, vega: 0.04, delta: 0.7, volume: 800 },
    { type: 'call', strike: 219, open_interest: 5000, gamma: 0.04, vega: 0.05, delta: 0.6, volume: 900 },
    { type: 'call', strike: 220, open_interest: 6000, gamma: 0.04, vega: 0.05, delta: 0.5, volume: 1200 },
    { type: 'call', strike: 221, open_interest: 5000, gamma: 0.04, vega: 0.05, delta: 0.4, volume: 950 },
    { type: 'call', strike: 222, open_interest: 4000, gamma: 0.03, vega: 0.04, delta: 0.3, volume: 700 },
    { type: 'put',  strike: 218, open_interest: 4500, gamma: 0.03, vega: 0.04, delta: -0.3, volume: 850 },
    { type: 'put',  strike: 219, open_interest: 5200, gamma: 0.04, vega: 0.05, delta: -0.4, volume: 1000 },
    { type: 'put',  strike: 220, open_interest: 6200, gamma: 0.04, vega: 0.05, delta: -0.5, volume: 1300 },
    { type: 'put',  strike: 221, open_interest: 5100, gamma: 0.04, vega: 0.05, delta: -0.6, volume: 1100 },
    { type: 'put',  strike: 222, open_interest: 4400, gamma: 0.03, vega: 0.04, delta: -0.7, volume: 900 },
  ],
  metadata: { source: 'mock', data_source: 'mock', row_count: 10 },
};

test.describe('Options Flow', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/options/dates/IWM', (r) => r.fulfill(M.ok(MOCK_DATES)));
    await page.route('**/api/options/IWM/*', (r) => r.fulfill(M.ok(MOCK_CHAIN)));
  });

  test('navigates to /options', async ({ page }) => {
    await page.goto('/options');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('body')).toContainText(/options/i);
  });

  test('renders strike values in chart', async ({ page }) => {
    await page.goto('/options');
    await page.waitForLoadState('networkidle');
    // Strike 220 should appear at least once (as an axis label)
    await expect(page.getByText(/220/).first()).toBeVisible();
  });

  test('renders chart axes and net/calls/puts toggle', async ({ page }) => {
    await page.goto('/options');
    await page.waitForLoadState('networkidle');
    // Page renders a GEX/VEX chart; toggle labels are visible in the header
    await expect(page.getByText(/calls/i).first()).toBeVisible();
    await expect(page.getByText(/puts/i).first()).toBeVisible();
  });

  test('renders within 5s perf budget', async ({ page }) => {
    const start = Date.now();
    await page.goto('/options');
    await page.waitForLoadState('networkidle');
    expect(Date.now() - start).toBeLessThan(5000);
  });
});
