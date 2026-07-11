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
import { mockDashboard, M } from './helpers/mocks';

test.describe('Dashboard intraday candle chart', () => {
  test.beforeEach(async ({ page }) => {
    await mockDashboard(page);
    // Real /api/backtest/results/{ticker} shape (empty CSV branch): ticker,
    // filename, trade_count, summary, trades — see
    // platform/api/routers/backtest.py get_backtest_results. Previously
    // mocked with the wrong shape ({ ticker, runs: [] }), which doesn't
    // match anything the router actually returns.
    await page.route('**/api/backtest/results/IWM', (r) =>
      r.fulfill(
        M.ok({
          ticker: 'IWM',
          filename: 'backtest_IWM_20260420_150000.csv',
          trade_count: 0,
          summary: {},
          trades: [],
        })
      )
    );
    // Real /api/backtest/equity/{ticker} shape (empty CSV branch): ticker,
    // filename, summary, dates, values — see get_equity_curve. Previously
    // mocked with { ticker, points: [], summary }, which doesn't match the
    // router's dates/values contract BacktesterSection.tsx actually reads.
    await page.route('**/api/backtest/equity/IWM', (r) =>
      r.fulfill(
        M.ok({
          ticker: 'IWM',
          filename: 'equity_IWM_20260420_150000.csv',
          summary: {},
          dates: [],
          values: [],
        })
      )
    );
    // Real /api/backtest/all/{ticker} shape: ticker, total_runs, runs — see
    // list_all_backtests. Previously mocked as bare { runs: [] }.
    await page.route('**/api/backtest/all/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', total_runs: 0, runs: [] }))
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
