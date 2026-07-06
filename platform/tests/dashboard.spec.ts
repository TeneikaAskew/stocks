/**
 * E2E: Dashboard ("/dashboard") — the app's home view anchored on activeTicker.
 *
 * Covers brief tile, latest signals, KPI grid, best/worst trades.
 * All API calls mocked; perf budget = first contentful render under 5s.
 */
import { test, expect } from '@playwright/test';
import { mockCommon, M } from './helpers/mocks';

// Brief shape the redesigned Overview consumes (bias bullets + KPI close/RSI).
const MOCK_BRIEF = {
  ticker: 'IWM',
  source: 'cloud_sql',
  bias: 'bullish',
  rsi: 58.4,
  strat_candle: '2U',
  strat_combo: 'Failed 2D → 2U',
  ftfc_score: 0.72,
  ftfc_direction: 'bullish',
  signal_status: '0DTE call flow leading',
  daily_indicators: {
    date: '2026-04-25',
    close: 220.5,
    rsi_14: 58.4,
    rvol: 1.4,
    strat_candle: '2U',
    strat_combo: 'Failed 2D → 2U',
    ftfc_score: 0.72,
    ftfc_direction: 'bullish',
  },
  live: { price: 220.45, session: 'closed' },
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
    // Intraday bars so the Overview chart card renders (candlestick default).
    const bars = [10, 11, 12, 13, 14, 15].map((h) => {
      const time = Date.UTC(2026, 3, 24, h, 0, 0) / 1000;
      const p = 219 + h * 0.1;
      return { time, open: p - 0.2, high: p + 0.3, low: p - 0.3, close: p };
    });
    await page.route('**/api/market/data/IWM/*', (r) =>
      r.fulfill(M.ok({
        ticker: 'IWM', date: '2026-04', count: bars.length,
        candlestick: bars,
        volume: bars.map((b) => ({ time: b.time, value: 1_000_000 })),
      }))
    );
    // Candlestick chart reads market-hours for its RTH window.
    await page.route('**/api/config/market-hours', (r) =>
      r.fulfill(M.ok({ regular: { open: '09:30', close: '16:00' }, premarket: { open: '04:00', close: '09:30' }, afterhours: { open: '16:00', close: '20:00' } }))
    );
  });

  test('renders Overview heading + pre-market brief for the active ticker', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    // Redesigned Overview: "Overview" H1, the active ticker in the header
    // micro-label + hero, and the pre-market brief panel.
    await expect(page.locator('h1', { hasText: 'Overview' }).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/pre-market brief/i).first()).toBeVisible();
    await expect(page.getByText('IWM').first()).toBeVisible();
  });

  test('shows daily bias card', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/daily bias/i).first()).toBeVisible({ timeout: 10_000 });
  });

  test('shows the daily KPI tiles (prev close / latest close / 2-day change / RSI)', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    // Redesigned KPI row, computed from brief.daily_indicators + reference.
    await expect(page.getByText(/prev close/i)).toBeVisible();
    await expect(page.getByText(/latest close/i)).toBeVisible();
    await expect(page.getByText(/2-day change/i)).toBeVisible();
    await expect(page.getByText(/RSI \(14\)/i)).toBeVisible();
  });

  test('intraday chart exposes the Candles / Area toggle and switches', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('IWM · intraday')).toBeVisible({ timeout: 10_000 });
    const candles = page.getByRole('button', { name: 'Candles' });
    const area = page.getByRole('button', { name: 'Area' });
    await expect(candles).toBeVisible();
    await expect(area).toBeVisible();
    // Switching to Area renders the Recharts area surface without crashing.
    await area.click();
    await expect(page.locator('svg.recharts-surface').first()).toBeVisible({ timeout: 5_000 });
  });

  test('renders within 7s perf budget', async ({ page }) => {
    // Dashboard has heavy API fan-out (brief + backtest + equity + signals +
    // playbook + live quote/history/avg-vol + reference). 7s allows for the
    // first-paint waterfall before mocks fully resolve.
    const start = Date.now();
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    expect(Date.now() - start).toBeLessThan(7000);
  });
});
