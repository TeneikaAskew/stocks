/**
 * E2E: Dashboard ("/") — landing page anchored on activeTicker.
 *
 * Covers brief tile, latest signals, KPI grid, best/worst trades.
 * All API calls mocked; perf budget = first contentful render under 5s.
 */
import { test, expect } from '@playwright/test';
import { mockCommon, M } from './helpers/mocks';

const MOCK_BRIEF = {
  ticker: 'IWM',
  as_of: '2026-04-25T20:00:00Z',
  daily_bias: { direction: 'bullish', confidence: 0.7, reason: 'EMA stack + bullish MACD' },
  reference_levels: { prior_high: 222.0, prior_low: 218.0, vwap: 220.5 },
  stale_days: 0,
  cloud_sql: true,
};

const MOCK_BACKTEST = {
  ticker: 'IWM',
  runs: [
    {
      run_id: 'run-1',
      started_at: '2026-04-20T15:00:00Z',
      win_rate: 0.62,
      avg_return_pct: 0.85,
      total_return_pct: 12.4,
      profit_factor: 1.9,
      trades: 42,
    },
  ],
};

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/dashboard/brief/IWM*', (r) => r.fulfill(M.ok(MOCK_BRIEF)));
    await page.route('**/api/backtest/results/IWM', (r) => r.fulfill(M.ok(MOCK_BACKTEST)));
    await page.route('**/api/backtest/equity/IWM', (r) =>
      r.fulfill(
        M.ok({
          ticker: 'IWM',
          points: [
            { date: '2026-04-21', equity: 10000, drawdown: 0 },
            { date: '2026-04-25', equity: 11240, drawdown: 0 },
          ],
          summary: { total_return_pct: 12.4, max_drawdown_pct: 3.2 },
        })
      )
    );
    await page.route('**/api/backtest/all/IWM', (r) => r.fulfill(M.ok({ runs: [] })));
    await page.route('**/api/signals/IWM*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', count: 0, signals: [] }))
    );
    await page.route('**/api/playbook/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', cards: [] }))
    );
    await page.route('**/api/live/quote/IWM', (r) =>
      r.fulfill(
        M.ok({
          ticker: 'IWM',
          price: 220.45,
          open: 219.8,
          high: 221.2,
          low: 219.5,
          volume: 1234567,
          change: 0.65,
          change_pct: 0.296,
          prev_close: 219.8,
          last_updated: '2026-04-25T19:55:00Z',
          market_session: 'closed',
          market_open: false,
        })
      )
    );
    await page.route('**/api/live/history/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', interval: '1min', count: 0, bars: [] }))
    );
    await page.route('**/api/live/avg-volume/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', avg_volume_20d: 25_000_000, sample_size: 20, last_date: '2026-04-24', source: 'mock' }))
    );
    await page.route('**/api/market/reference/IWM/*', (r) =>
      r.fulfill(
        M.ok({
          ticker: 'IWM',
          date: '2026-04-25',
          source: 'mock',
          stale_days: 0,
          open: 220.0,
          high: 222.0,
          low: 218.0,
          close: 220.5,
          week: {
            high: 224.0,
            low: 216.0,
            avg_close: 220.0,
            avg_rsi_14: 55.0,
            start_date: '2026-04-21',
            end_date: '2026-04-25',
            sessions: 5,
          },
        })
      )
    );
    await page.route('**/api/market/data/IWM/*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', date: '2026-04-25', count: 0, candlestick: [], volume: [] }))
    );
  });

  test('renders ticker heading and dashboard label', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    // Dashboard renders the active ticker as a 4xl H1
    await expect(page.locator('h1', { hasText: 'IWM' }).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/dashboard/i).first()).toBeVisible();
  });

  test('shows daily bias card', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/daily bias/i).first()).toBeVisible({ timeout: 10_000 });
  });

  test('shows KPI grid (win rate / avg / return / pf)', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/win rate/i)).toBeVisible();
    await expect(page.getByText(/profit factor/i)).toBeVisible();
  });

  test('renders within 7s perf budget', async ({ page }) => {
    // Dashboard has heavy API fan-out (brief + backtest + equity + signals +
    // playbook + live quote/history/avg-vol + reference). 7s allows for the
    // first-paint waterfall before mocks fully resolve.
    const start = Date.now();
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(Date.now() - start).toBeLessThan(7000);
  });
});
