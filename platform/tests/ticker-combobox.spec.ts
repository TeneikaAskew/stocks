/**
 * E2E: Ticker type-ahead combobox (Phase 1, Task 2).
 *
 * Replaces the old fixed IWM/SPY/QQQ <TickerSelect> dropdown. Covers: the
 * popover opens from the trigger, typing surfaces search results merged with
 * data-coverage badges, and Enter picks the highlighted result and updates
 * the page's active ticker (the trigger's own label). All API calls mocked —
 * hermetic, no live backend required.
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

test.describe('TickerCombobox', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);

    // Ticker search — returns a single AAPL match for any "aa"-ish query.
    await page.route('**/api/insights/ticker/search**', (r) =>
      r.fulfill(
        M.ok({
          keywords: 'aa',
          results: [
            {
              symbol: 'AAPL',
              name: 'Apple Inc',
              type: 'Equity',
              region: 'United States',
              currency: 'USD',
              match_score: 0.92,
            },
          ],
        })
      )
    );

    // Data coverage — AAPL has daily only (no intraday) → "daily" badge.
    await page.route('**/api/market/coverage**', (r) =>
      r.fulfill(M.ok({ coverage: { AAPL: { intraday: false, daily: true } } }))
    );

    // Rest of the dashboard's fan-out, same shape as dashboard.spec.ts.
    await page.route('**/api/dashboard/brief/IWM*', (r) => r.fulfill(M.ok(MOCK_BRIEF)));
    await page.route('**/api/backtest/results/*', (r) => r.fulfill(M.ok({ ticker: 'IWM', runs: [] })));
    await page.route('**/api/backtest/equity/*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', points: [], summary: { total_return_pct: 0, max_drawdown_pct: 0 } }))
    );
    await page.route('**/api/backtest/all/*', (r) => r.fulfill(M.ok({ runs: [] })));
    await page.route('**/api/signals/*', (r) => r.fulfill(M.ok({ ticker: 'IWM', count: 0, signals: [] })));
    await page.route('**/api/playbook/*', (r) => r.fulfill(M.ok({ ticker: 'IWM', cards: [] })));
    await page.route('**/api/live/quote/*', (r) =>
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
    await page.route('**/api/live/history/*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', interval: '1min', count: 0, bars: [] }))
    );
    await page.route('**/api/live/avg-volume/*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', avg_volume_20d: 25_000_000, sample_size: 20, last_date: '2026-04-24', source: 'mock' }))
    );
    await page.route('**/api/market/reference/*', (r) =>
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
          week: { high: 224.0, low: 216.0, avg_close: 220.0, avg_rsi_14: 55.0, start_date: '2026-04-21', end_date: '2026-04-25', sessions: 5 },
        })
      )
    );
    await page.route('**/api/market/data/*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', date: '2026-04', count: 0, candlestick: [], volume: [] }))
    );
    await page.route('**/api/config/market-hours', (r) =>
      r.fulfill(M.ok({ regular: { open: '09:30', close: '16:00' }, premarket: { open: '04:00', close: '09:30' }, afterhours: { open: '16:00', close: '20:00' } }))
    );

    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
  });

  test('trigger shows the active ticker and opens the popover', async ({ page }) => {
    const trigger = page.getByTestId('ticker-combobox');
    await expect(trigger).toBeVisible();
    await expect(trigger).toContainText('IWM');
    await expect(page.getByTestId('ticker-combobox-panel')).not.toBeVisible();

    await trigger.click();
    await expect(page.getByTestId('ticker-combobox-panel')).toBeVisible();
    await expect(page.getByTestId('ticker-combobox-input')).toBeFocused();
  });

  test('quick picks (IWM/SPY/QQQ) render in the popover', async ({ page }) => {
    await page.getByTestId('ticker-combobox').click();
    await expect(page.getByTestId('ticker-option-IWM')).toBeVisible();
    await expect(page.getByTestId('ticker-option-SPY')).toBeVisible();
    await expect(page.getByTestId('ticker-option-QQQ')).toBeVisible();
  });

  test('typing "aa" surfaces AAPL with a "daily" coverage badge', async ({ page }) => {
    await page.getByTestId('ticker-combobox').click();
    await page.getByTestId('ticker-combobox-input').fill('aa');

    const option = page.getByTestId('ticker-option-AAPL');
    await expect(option).toBeVisible({ timeout: 5000 });
    await expect(option).toContainText('AAPL');
    await expect(option).toContainText('Apple Inc');
    await expect(option).toContainText('daily');
  });

  test('Enter picks the highlighted result and sets the header ticker', async ({ page }) => {
    const trigger = page.getByTestId('ticker-combobox');
    await trigger.click();
    const input = page.getByTestId('ticker-combobox-input');
    await input.fill('aa');
    await expect(page.getByTestId('ticker-option-AAPL')).toBeVisible({ timeout: 5000 });

    // Quick picks (3) + recents (0) precede the single search result, so
    // three ArrowDown presses lands on AAPL before Enter picks it.
    await input.press('ArrowDown');
    await input.press('ArrowDown');
    await input.press('ArrowDown');
    await input.press('Enter');

    await expect(page.getByTestId('ticker-combobox-panel')).not.toBeVisible();
    await expect(trigger).toContainText('AAPL');
  });

  test('clicking the AAPL result directly sets the header ticker', async ({ page }) => {
    const trigger = page.getByTestId('ticker-combobox');
    await trigger.click();
    await page.getByTestId('ticker-combobox-input').fill('aa');
    await page.getByTestId('ticker-option-AAPL').click();

    await expect(page.getByTestId('ticker-combobox-panel')).not.toBeVisible();
    await expect(trigger).toContainText('AAPL');
  });

  test('Escape closes the popover without changing the ticker', async ({ page }) => {
    const trigger = page.getByTestId('ticker-combobox');
    await trigger.click();
    await expect(page.getByTestId('ticker-combobox-panel')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('ticker-combobox-panel')).not.toBeVisible();
    await expect(trigger).toContainText('IWM');
  });

  test('search failure renders an inline error, never an empty "no matches" lie', async ({ page }) => {
    await page.route('**/api/insights/ticker/search**', (r) =>
      r.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'upstream unavailable' }) })
    );
    await page.getByTestId('ticker-combobox').click();
    await page.getByTestId('ticker-combobox-input').fill('zz');
    await expect(page.getByTestId('ticker-search-error')).toBeVisible({ timeout: 5000 });
  });

  test('coverage failure still renders suggestions plus an inline hint that badges may be inaccurate', async ({ page }) => {
    await page.route('**/api/market/coverage**', (r) =>
      r.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'coverage upstream unavailable' }) })
    );
    await page.getByTestId('ticker-combobox').click();
    await page.getByTestId('ticker-combobox-input').fill('aa');

    // Suggestions still render — coverage failing must not blank the list.
    const option = page.getByTestId('ticker-option-AAPL');
    await expect(option).toBeVisible({ timeout: 5000 });
    // Badge falls back to the honest "new" default (coverage unknown)…
    await expect(option).toContainText('new');
    // …and the inline hint tells the user why the badge may be wrong.
    await expect(page.getByTestId('ticker-coverage-error')).toBeVisible();
    await expect(page.getByTestId('ticker-coverage-error')).toContainText('coverage lookup unavailable');
  });

  test('picking a "new"-badged suggestion auto-adds it to the watchlist with an honest ingest notice', async ({ page }) => {
    // AAPL has no coverage entry at all → badge is the honest "new" default.
    await page.route('**/api/market/coverage**', (r) => r.fulfill(M.ok({ coverage: {} })));

    let addRequestBody: unknown = null;
    await page.route('**/api/insights/watchlist/add', (r) => {
      addRequestBody = JSON.parse(r.request().postData() ?? '{}');
      return r.fulfill(
        M.ok({ ticker: 'AAPL', added: true, info: null, quote: null, peers: null, watchlist: ['AAPL'] })
      );
    });

    await page.getByTestId('ticker-combobox').click();
    await page.getByTestId('ticker-combobox-input').fill('aa');
    const option = page.getByTestId('ticker-option-AAPL');
    await expect(option).toContainText('new', { timeout: 5000 });
    await option.click();

    await expect(page.getByTestId('ticker-ingest-notice')).toBeVisible();
    await expect(page.getByTestId('ticker-ingest-notice')).toContainText(
      "Tracking AAPL — daily data lands after tonight's fetch"
    );
    expect(addRequestBody).toEqual({ ticker: 'AAPL' });
  });

  test('picking a "full"-badged suggestion does NOT auto-add to the watchlist', async ({ page }) => {
    await page.route('**/api/market/coverage**', (r) =>
      r.fulfill(M.ok({ coverage: { AAPL: { intraday: true, daily: true } } }))
    );

    let addCalled = false;
    await page.route('**/api/insights/watchlist/add', (r) => {
      addCalled = true;
      return r.fulfill(
        M.ok({ ticker: 'AAPL', added: true, info: null, quote: null, peers: null, watchlist: ['AAPL'] })
      );
    });

    await page.getByTestId('ticker-combobox').click();
    await page.getByTestId('ticker-combobox-input').fill('aa');
    const option = page.getByTestId('ticker-option-AAPL');
    await expect(option).toContainText('full', { timeout: 5000 });
    await option.click();

    await expect(page.getByTestId('ticker-combobox-panel')).not.toBeVisible();
    await expect(page.getByTestId('ticker-combobox')).toContainText('AAPL');
    await expect(page.getByTestId('ticker-ingest-notice')).not.toBeVisible();
    expect(addCalled).toBe(false);
  });

  test('watchlist-add failure shows a loud inline error but still sets the active ticker', async ({ page }) => {
    await page.route('**/api/market/coverage**', (r) => r.fulfill(M.ok({ coverage: {} })));
    await page.route('**/api/insights/watchlist/add', (r) =>
      r.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'watchlist write to Cloud SQL failed: connection refused' }),
      })
    );

    await page.getByTestId('ticker-combobox').click();
    await page.getByTestId('ticker-combobox-input').fill('aa');
    await page.getByTestId('ticker-option-AAPL').click();

    const notice = page.getByTestId('ticker-ingest-notice');
    await expect(notice).toBeVisible();
    await expect(notice).toContainText('503');
    await expect(notice).toContainText('connection refused');
    // Browsing is allowed even when ingest fails — the active ticker still updates.
    await expect(page.getByTestId('ticker-combobox')).toContainText('AAPL');
  });

  test('a search result duplicating a quick pick is deduped — IWM renders exactly once', async ({ page }) => {
    // Search returns IWM (already a quick pick) plus a novel symbol.
    await page.route('**/api/insights/ticker/search**', (r) =>
      r.fulfill(
        M.ok({
          keywords: 'iw',
          results: [
            { symbol: 'IWM', name: 'iShares Russell 2000 ETF', type: 'ETF', region: 'United States', currency: 'USD', match_score: 0.95 },
            { symbol: 'IWN', name: 'iShares Russell 2000 Value ETF', type: 'ETF', region: 'United States', currency: 'USD', match_score: 0.8 },
          ],
        })
      )
    );
    await page.route('**/api/market/coverage**', (r) =>
      r.fulfill(M.ok({ coverage: { IWM: { intraday: true, daily: true }, IWN: { intraday: false, daily: false } } }))
    );

    await page.getByTestId('ticker-combobox').click();
    await page.getByTestId('ticker-combobox-input').fill('iw');

    // The non-duplicate search result renders…
    await expect(page.getByTestId('ticker-option-IWN')).toBeVisible({ timeout: 5000 });
    // …and IWM appears exactly once (the quick-pick chip; the duplicate
    // search row was dropped, so no highlight/testid collision).
    await expect(page.getByTestId('ticker-option-IWM')).toHaveCount(1);
  });

  test('coverage error → NO auto-add, ticker still set', async ({ page }) => {
    // Simulate coverage lookup failure (503).
    // The implementation gate is `!coverage.isError` in TickerCombobox.tsx:205,
    // so auto-ingest must NOT fire when coverage fails, even if the search row
    // badge falls back to "new".
    await page.unroute('**/api/market/coverage**');
    await page.route('**/api/market/coverage**', (r) =>
      r.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'coverage upstream unavailable' }) })
    );

    let addCalled = false;
    await page.route('**/api/insights/watchlist/add', (r) => {
      addCalled = true;
      return r.fulfill(
        M.ok({ ticker: 'AAPL', added: true, info: null, quote: null, peers: null, watchlist: ['AAPL'] })
      );
    });

    await page.getByTestId('ticker-combobox').click();
    await page.getByTestId('ticker-combobox-input').fill('aa');

    // AAPL renders with fallback "new" badge because coverage failed.
    const option = page.getByTestId('ticker-option-AAPL');
    await expect(option).toBeVisible({ timeout: 5000 });
    await expect(option).toContainText('new');

    // Wait for the coverage error hint to appear, confirming the hook has
    // detected the coverage error and set isError to true.
    await expect(page.getByTestId('ticker-coverage-error')).toBeVisible({ timeout: 5000 });

    // Now click the "new"-badged option. Since coverage errored (isError=true),
    // the gate `!coverage.isError` will be false, so auto-ingest should NOT fire.
    await option.click();

    // Assertions: no auto-add occurred, ticker still updated, no ingest notice.
    await expect(page.getByTestId('ticker-combobox-panel')).not.toBeVisible();
    await expect(page.getByTestId('ticker-combobox')).toContainText('AAPL');
    await expect(page.getByTestId('ticker-ingest-notice')).not.toBeVisible();
    expect(addCalled).toBe(false);
  });

  test('keyboard path: type, arrow-down, enter triggers watchlist auto-add', async ({ page }) => {
    // AAPL has no coverage entry → badge is "new" → auto-ingest should fire on selection.
    await page.route('**/api/market/coverage**', (r) => r.fulfill(M.ok({ coverage: {} })));

    let addRequestBody: unknown = null;
    await page.route('**/api/insights/watchlist/add', (r) => {
      addRequestBody = JSON.parse(r.request().postData() ?? '{}');
      return r.fulfill(
        M.ok({ ticker: 'AAPL', added: true, info: null, quote: null, peers: null, watchlist: ['AAPL'] })
      );
    });

    await page.getByTestId('ticker-combobox').click();
    const input = page.getByTestId('ticker-combobox-input');
    await input.fill('aa');
    await expect(page.getByTestId('ticker-option-AAPL')).toBeVisible({ timeout: 5000 });

    // Navigate: 3 quick picks (IWM, SPY, QQQ) + 0 recents precede the search row.
    // ArrowDown 3 times lands on AAPL search row (index 3).
    await input.press('ArrowDown');
    await input.press('ArrowDown');
    await input.press('ArrowDown');
    await input.press('Enter');

    // The selection → auto-ingest flow fires the watchlist POST.
    await expect(page.getByTestId('ticker-ingest-notice')).toBeVisible();
    await expect(page.getByTestId('ticker-ingest-notice')).toContainText(
      "Tracking AAPL — daily data lands after tonight's fetch"
    );
    expect(addRequestBody).toEqual({ ticker: 'AAPL' });
    await expect(page.getByTestId('ticker-combobox')).toContainText('AAPL');
  });
});
