/**
 * E2E: Dashboard ("/dashboard") — the app's home view anchored on activeTicker.
 *
 * Covers brief tile, latest signals, KPI grid, best/worst trades.
 * All API calls mocked; perf budget = first contentful render under 5s.
 */
import { test, expect } from '@playwright/test';
import { mockCommon, M } from './helpers/mocks';

// Relative-to-now ISO dates so the News card's day-granularity relative
// label ("yesterday") and forward-event dates are deterministic regardless
// of when the suite runs.
const TODAY_ISO = new Date().toISOString().slice(0, 10);
const YESTERDAY_ISO = (() => {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
})();
const TOMORROW_ISO = (() => {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
})();

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

// Sector rotation: 3 ok rows (ranked distinctly for 1D vs 5D) + 1 unavailable row.
const MOCK_SECTORS = {
  as_of: '2026-04-25',
  status: 'ok',
  sectors: [
    { symbol: 'XLK', name: 'Technology', close: 250.1, chg_1d_pct: 1.25, chg_5d_pct: 3.4, status: 'ok' },
    { symbol: 'XLF', name: 'Financials', close: 45.2, chg_1d_pct: 2.5, chg_5d_pct: -1.1, status: 'ok' },
    { symbol: 'XLE', name: 'Energy', close: 90.3, chg_1d_pct: -0.75, chg_5d_pct: 4.2, status: 'ok' },
    { symbol: 'XLY', name: 'Consumer Discretionary', status: 'unavailable', reason: 'stale data' },
  ],
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

// News is backward-dated (yesterday) alongside 3 forward-dated catalyst
// events — regression coverage for the news-card contract: the fixed
// frontend matches on `source === 'AV news'` against the FULL events array,
// which is robust regardless of dating or slicing. The old frontend matched
// on `sentiment_label || catalyst_type === 'NEWS'`; the backend never emits
// catalyst_type literally 'NEWS' (it maps to NEWS_CATALYST/EARNINGS_NEWS/
// MERGER_ACQUISITION/IPO/ECONOMIC), so these rows — carrying an empty
// sentiment_label, as real low-confidence articles sometimes do — pin the
// exact match condition this fix changed: "0 fresh" on the old filter,
// "2 fresh" once matched by `source` instead.
const MOCK_EVENTS_WITH_NEWS = {
  status: 'ok',
  source: 'mock',
  date_range: { from: YESTERDAY_ISO, to: TOMORROW_ISO },
  total: 5,
  events_by_date: {
    [YESTERDAY_ISO]: [
      {
        date: YESTERDAY_ISO,
        ticker: 'IWM',
        catalyst_type: 'NEWS_CATALYST',
        title: 'Russell 2000 constituents rally on rate-cut optimism',
        impact: 'Medium',
        source: 'AV news',
        sentiment_label: '',
        sentiment_score: 0.31,
      },
      {
        date: YESTERDAY_ISO,
        ticker: 'IWM',
        catalyst_type: 'NEWS_CATALYST',
        title: 'Small-cap earnings season kicks off with mixed guidance',
        impact: 'Low',
        source: 'AV news',
        sentiment_label: '',
        sentiment_score: 0.02,
      },
    ],
    [TODAY_ISO]: [
      {
        date: TODAY_ISO,
        ticker: 'AAPL',
        catalyst_type: 'EARNINGS',
        event: 'Q2 2026 Earnings',
        expected_impact: 'high',
        source: 'mock',
      },
      {
        date: TODAY_ISO,
        ticker: 'MSFT',
        catalyst_type: 'CONFERENCE_CALL',
        event: 'Investor Day',
        expected_impact: 'medium',
        source: 'mock',
      },
    ],
    [TOMORROW_ISO]: [
      {
        date: TOMORROW_ISO,
        ticker: 'MACRO',
        catalyst_type: 'ECONOMIC',
        title: 'CPI release',
        impact: 'High',
        source: 'FRED/Calendar',
      },
    ],
  },
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

  test('sector rotation card ranks sectors, shows an em-dash row, and 1D/5D toggle switches values', async ({ page }) => {
    await page.route('**/api/market/sectors', (r) => r.fulfill(M.ok(MOCK_SECTORS)));
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    const card = page.getByTestId('sector-rotation-card');
    await expect(card).toBeVisible({ timeout: 10_000 });

    // as-of caption in the header meta.
    await expect(card).toContainText('as of 2026-04-25');

    // 1D (default): ranked desc by chg_1d_pct — XLF (2.5) > XLK (1.25) > XLE (-0.75),
    // unavailable XLY sinks to the bottom.
    let rows = await card.getByTestId('sector-row').allTextContents();
    expect(rows).toHaveLength(4);
    expect(rows[0]).toContain('Financials');
    expect(rows[1]).toContain('Technology');
    expect(rows[2]).toContain('Energy');
    expect(rows[3]).toContain('Consumer Discretionary');
    expect(rows[3]).toContain('—');

    // Toggle to 5D — ranked desc by chg_5d_pct — XLE (4.2) > XLK (3.4) > XLF (-1.1).
    await card.getByRole('button', { name: '5D' }).click();
    rows = await card.getByTestId('sector-row').allTextContents();
    expect(rows[0]).toContain('Energy');
    expect(rows[1]).toContain('Technology');
    expect(rows[2]).toContain('Financials');
    expect(rows[3]).toContain('Consumer Discretionary');
  });

  test('News card counts AV-news rows dated in the past and shows both headlines', async ({ page }) => {
    await page.route('**/api/catalysts/events**', (r) => r.fulfill(M.ok(MOCK_EVENTS_WITH_NEWS)));
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    const newsCard = page.getByTestId('news-card');
    await expect(page.getByText('2 fresh')).toBeVisible({ timeout: 10_000 });
    await expect(newsCard.getByText('Russell 2000 constituents rally on rate-cut optimism')).toBeVisible();
    await expect(newsCard.getByText('Small-cap earnings season kicks off with mixed guidance')).toBeVisible();
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
