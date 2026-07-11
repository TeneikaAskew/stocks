/**
 * Shared API mock helpers for E2E tests.
 *
 * Every page hits a few cross-cutting endpoints (live status pill, health
 * check). Each spec also tends to call the dashboard brief on first paint
 * because the header/sidebar reads it. Centralizing the boilerplate keeps
 * specs short and the mock surface explicit.
 */
import type { Page } from '@playwright/test';

const ok = (body: unknown) => ({
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify(body),
});

const notFound = () => ({
  status: 404,
  contentType: 'application/json',
  body: JSON.stringify({ detail: 'not found' }),
});

/** Apply mocks for endpoints every page hits — call from beforeEach. */
export async function mockCommon(page: Page) {
  await page.route('**/api/health', (r) => r.fulfill(ok({ status: 'ok', cloud_sql: false })));
  // Auth config probe — `open` mode keeps the gate inert (renders the app
  // directly), matching iap/local behaviour. The login page only appears in
  // `firebase` mode.
  await page.route('**/api/config/firebase', (r) =>
    r.fulfill(ok({ authMode: 'open', firebase: null }))
  );
  await page.route('**/api/me', (r) => r.fulfill(ok({ email: null, is_admin: false })));
  await page.route('**/api/live/status', (r) =>
    r.fulfill(ok({ session: 'closed', is_open: false, ts: '2026-04-25T20:00:00Z' }))
  );
  await page.route('**/api/dashboard/brief/*', (r) => r.fulfill(notFound()));
  await page.route('**/api/insights/watchlist*', (r) =>
    r.fulfill(ok({ tickers: ['IWM'], generated_at: '2026-04-25T20:00:00Z' }))
  );
}

// Brief shape the redesigned Overview consumes (bias bullets + KPI close/RSI).
// Byte-identical fixture previously duplicated in dashboard.spec.ts and
// dashboard-chart-fit.spec.ts's beforeEach blocks.
const MOCK_DASHBOARD_BRIEF = {
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

/**
 * Apply the dashboard route set shared by dashboard.spec.ts and
 * dashboard-chart-fit.spec.ts's beforeEach blocks — brief, signals,
 * playbook, live quote/history/avg-volume, market reference, and the
 * market-hours config, all scoped to IWM (the app's default ticker).
 * Includes `mockCommon`, so callers don't need to call it separately.
 *
 * Backtest routes (`/api/backtest/*`) and the intraday `/api/market/data`
 * candle bars differ meaningfully between the two specs (real trade data
 * vs. layout-focused bar counts/shapes) and stay local to each spec's
 * beforeEach per-call overrides.
 */
export async function mockDashboard(page: Page) {
  await mockCommon(page);
  await page.route('**/api/dashboard/brief/IWM*', (r) => r.fulfill(ok(MOCK_DASHBOARD_BRIEF)));
  await page.route('**/api/signals/IWM*', (r) =>
    r.fulfill(ok({ ticker: 'IWM', count: 0, signals: [] }))
  );
  await page.route('**/api/playbook/IWM', (r) => r.fulfill(ok({ ticker: 'IWM', cards: [] })));
  await page.route('**/api/live/quote/IWM', (r) =>
    r.fulfill(
      ok({
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
    r.fulfill(ok({ ticker: 'IWM', interval: '1min', count: 0, bars: [] }))
  );
  await page.route('**/api/live/avg-volume/IWM', (r) =>
    r.fulfill(
      ok({ ticker: 'IWM', avg_volume_20d: 25_000_000, sample_size: 20, last_date: '2026-04-24', source: 'mock' })
    )
  );
  await page.route('**/api/market/reference/IWM/*', (r) =>
    r.fulfill(
      ok({
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
  // Candlestick chart reads market-hours for its RTH window.
  await page.route('**/api/config/market-hours', (r) =>
    r.fulfill(
      ok({
        regular: { open: '09:30', close: '16:00' },
        premarket: { open: '04:00', close: '09:30' },
        afterhours: { open: '16:00', close: '20:00' },
      })
    )
  );
}

// Options grid/levels fixtures shared by navigation.spec.ts's "SwingMode
// toolbar" describe block and demo-banners.spec.ts (byte-identical, IWM,
// snapshot 2026-04-25).
export const MOCK_LEVELS = {
  ticker: 'IWM',
  snapshot_date: '2026-04-25',
  spot: { price: 220, method: 'parity', note: '' },
  gamma_balance: 220,
  gamma_flip: 220,
  regime: 'positive_gamma',
  total_gex: 1_000_000,
  levels: [],
  kings: [],
  gates: [],
  gamma_balance_levels: [],
  window_pct: 6,
  warnings: [],
  chain_size: 0,
};

export const MOCK_GRID = {
  ticker: 'IWM',
  snapshot_date: '2026-04-25',
  snapshot_ts: null,
  data_source: 'realtime',
  spot: { price: 220, method: 'parity', note: '' },
  gamma_balance: 220,
  gamma_flip: 220,
  regime: 'positive_gamma',
  total_gex: 1_000_000,
  total_vex: 0,
  cells: [],
  expirations: [],
  strikes: [],
  window_pct: 6,
  warnings: [],
};

export const M = { ok, notFound };
