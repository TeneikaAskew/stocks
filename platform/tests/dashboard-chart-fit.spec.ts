/**
 * E2E: Dashboard intraday candle chart must stay clipped inside its 260px
 * card slot (`data-testid="intraday-chart-slot"`). Regression guard for the
 * CandlestickChart `minHeight` prop becoming caller-owned — the dashboard
 * caller doesn't pass `minHeight`, so its 260px `overflow-hidden` wrapper
 * clips the chart instead of the chart forcing a 400px floor.
 *
 * All API calls are mocked (mockCommon + local overrides) so the test is
 * hermetic and doesn't depend on a live authenticated backend.
 */
import { test, expect } from '@playwright/test';
import { mockCommon, M } from './helpers/mocks';

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

test.describe('Dashboard intraday candle chart', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/config/firebase', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ authMode: 'open', firebase: null }) })
    );
    await page.route('**/api/dashboard/brief/IWM*', (r) => r.fulfill(M.ok(MOCK_BRIEF)));
    await page.route('**/api/backtest/results/IWM', (r) => r.fulfill(M.ok({ ticker: 'IWM', runs: [] })));
    await page.route('**/api/backtest/equity/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', points: [], summary: { total_return_pct: 0, max_drawdown_pct: 0 } }))
    );
    await page.route('**/api/backtest/all/IWM', (r) => r.fulfill(M.ok({ runs: [] })));
    await page.route('**/api/signals/IWM*', (r) => r.fulfill(M.ok({ ticker: 'IWM', count: 0, signals: [] })));
    await page.route('**/api/playbook/IWM', (r) => r.fulfill(M.ok({ ticker: 'IWM', cards: [] })));
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
    await page.route('**/api/live/history/IWM', (r) => r.fulfill(M.ok({ ticker: 'IWM', interval: '1min', count: 0, bars: [] })));
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
    // Intraday bars (32 hourly bars) so the candle chart has enough data to
    // create a canvas and lay out a realistic candle count.
    const bars = Array.from({ length: 32 }, (_, i) => {
      const time = Date.UTC(2026, 3, 24, 9 + Math.floor(i / 4), (i % 4) * 15, 0) / 1000;
      const p = 219 + i * 0.05;
      return { time, open: p - 0.2, high: p + 0.3, low: p - 0.3, close: p };
    });
    await page.route('**/api/market/data/IWM/*', (r) =>
      r.fulfill(
        M.ok({
          ticker: 'IWM',
          date: '2026-04',
          count: bars.length,
          candlestick: bars,
          volume: bars.map((b) => ({ time: b.time, value: 1_000_000 })),
        })
      )
    );
    // Candlestick chart reads market-hours for its RTH window.
    await page.route('**/api/config/market-hours', (r) =>
      r.fulfill(
        M.ok({ regular: { open: '09:30', close: '16:00' }, premarket: { open: '04:00', close: '09:30' }, afterhours: { open: '16:00', close: '20:00' } })
      )
    );
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
  });

  test('candle chart stays inside its 260px card slot', async ({ page }) => {
    // Switch to Candles if not default
    const candlesBtn = page.getByRole('button', { name: 'Candles', exact: true });
    if (await candlesBtn.isVisible()) await candlesBtn.click();
    await page.waitForTimeout(1500); // chart create
    const slot = page.locator('[data-testid="intraday-chart-slot"]');
    await expect(slot).toBeVisible();
    const slotBox = await slot.boundingBox();
    const canvas = slot.locator('canvas').first();
    const canvasBox = await canvas.boundingBox();
    expect(slotBox).not.toBeNull();
    expect(canvasBox).not.toBeNull();
    // Canvas must not extend below the slot.
    expect(canvasBox!.y + canvasBox!.height).toBeLessThanOrEqual(slotBox!.y + slotBox!.height + 2);
    expect(canvasBox!.height).toBeLessThanOrEqual(262);
  });
});
