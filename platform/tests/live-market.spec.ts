/**
 * E2E: Live Market ("/live") — live quote, intraday bars, playbook overlay.
 */
import { test, expect } from '@playwright/test';
import { mockCommon, M } from './helpers/mocks';

const MOCK_QUOTE = {
  ticker: 'IWM',
  price: 220.45,
  open: 219.8,
  high: 221.2,
  low: 219.5,
  volume: 12_345_678,
  change: 0.65,
  change_pct: 0.296,
  prev_close: 219.8,
  last_updated: '2026-04-25T19:55:00Z',
  market_session: 'regular',
  market_open: true,
};

const MOCK_HISTORY = {
  ticker: 'IWM',
  interval: '1min',
  count: 30,
  market_session: 'regular',
  market_open: true,
  bars: Array.from({ length: 30 }, (_, i) => ({
    time: `2026-04-25 ${String(13 + Math.floor(i / 60)).padStart(2, '0')}:${String(i % 60).padStart(2, '0')}:00`,
    open: 220 + i * 0.05,
    high: 220.2 + i * 0.05,
    low: 219.9 + i * 0.05,
    close: 220.1 + i * 0.05,
    volume: 100_000,
  })),
};

const MOCK_AVG_VOL = {
  ticker: 'IWM',
  avg_volume_20d: 25_000_000,
  sample_size: 20,
  last_date: '2026-04-24',
  source: 'mock',
};

test.describe('Live Market', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/live/quote/IWM*', (r) => r.fulfill(M.ok(MOCK_QUOTE)));
    await page.route('**/api/live/history/IWM*', (r) => r.fulfill(M.ok(MOCK_HISTORY)));
    await page.route('**/api/live/avg-volume/IWM*', (r) => r.fulfill(M.ok(MOCK_AVG_VOL)));
    await page.route('**/api/playbook/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', cards: [] }))
    );
    await page.route('**/api/market/reference/IWM/*', (r) =>
      r.fulfill(
        M.ok({
          ticker: 'IWM',
          date: '2026-04-25',
          source: 'mock',
          open: 220.0,
          high: 222.0,
          low: 218.0,
          close: 220.5,
        })
      )
    );
    await page.route('**/api/playbook/IWM', (r) => r.fulfill(M.notFound()));
    await page.route('**/api/market/dates/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', dates: ['2026-04-25'] }))
    );
    await page.route('**/api/market/data/IWM/*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', date: '2026-04-25', candlestick: [], volume: [] }))
    );
  });

  test('navigates to /live and renders ticker context', async ({ page }) => {
    await page.goto('/live');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('body')).toContainText(/IWM/);
  });

  test('renders live price quote', async ({ page }) => {
    await page.goto('/live');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/220\.45/).first()).toBeVisible();
  });

  test('shows session pill', async ({ page }) => {
    await page.goto('/live');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/market open|market closed|pre-market|after hours/i).first()).toBeVisible();
  });

  test('renders within 5s perf budget', async ({ page }) => {
    const start = Date.now();
    await page.goto('/live');
    await page.waitForLoadState('networkidle');
    expect(Date.now() - start).toBeLessThan(5000);
  });
});
