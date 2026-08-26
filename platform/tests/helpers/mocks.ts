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
  // index.css @imports Montserrat from the Google Fonts CDN. On a runner
  // without outbound internet that request stalls for >10s before failing —
  // blowing 5s perf budgets and logging a "Failed to load resource" console
  // error. Fulfill it with an empty stylesheet: the UI falls back to the
  // system font stack and no spec asserts rendered glyphs.
  await page.route('https://fonts.googleapis.com/**', (r) =>
    r.fulfill({ status: 200, contentType: 'text/css', body: '' })
  );
  await page.route('https://fonts.gstatic.com/**', (r) =>
    r.fulfill({ status: 200, contentType: 'font/woff2', body: '' })
  );
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
  // Most-active ticker bar (mounted on Market pages + /journal via AppShell).
  // Default is an honest empty response so the bar hides itself — specs that
  // don't care about the marquee stay unaffected; most-active-bar.spec.ts
  // overrides this route per-test with real payloads.
  await page.route('**/api/market/most-active', (r) =>
    r.fulfill(ok({ snapshot_ts: null, snapshot_date: null, label: null, items: [] }))
  );
  // ReplayControl (mounted on every page via the TopTabs shell) reads the
  // RTH window from /api/config/market-hours on mount, so this is a
  // cross-cutting request just like /api/live/status. Specs that need a
  // different window (e.g. mockDashboard) re-register and win via
  // Playwright's last-registered-first matching.
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

// ── Options Flow (/options) fixture set ─────────────────────────────────────
// Shared by options-flow.spec.ts and gamma-levels.spec.ts. The /options page
// (OptionsFlowPage.tsx) fans out to FIVE options endpoints, all of which must
// be intercepted for hermetic runs (an unmocked /api request hits the Vite
// proxy and 500s with ECONNREFUSED when no backend is up):
//   Heatseeker/Swing (default tab, SwingMode.tsx):
//     GET  /api/options/dates/{ticker}                (latest snapshot date)
//     GET  /api/options/{ticker}/grid?...             (useGammaGrid, live mode)
//     GET  /api/options/{ticker}/{date}/levels        (useGammaLevels)
//   Profiles tab (ProfilesTab.tsx):
//     GET  /api/options/{ticker}/{date}               (chain; 404 → /live fallback)
//     POST /api/options/greeks                        (useOptionsGreeks)

export const MOCK_OPTIONS_DATES = {
  ticker: 'IWM',
  dates: ['2026-04-25', '2026-04-24'],
};

export const MOCK_OPTIONS_CHAIN = {
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

// Byte-for-byte capture of POST /api/options/greeks (options.py:555) for
// MOCK_OPTIONS_CHAIN at spot 220 — recorded against the live router so the
// fixture can't drift from the GreeksResponse contract (aggregated,
// gex_by_strike, metrics, nodes, config — see useOptionsGreeks.ts).
export const MOCK_GREEKS = {
  aggregated: [
    { strike: 218, net_gamma: -15, call_gamma: 120, put_gamma: 135, net_vega: -20, call_vega: 160, put_vega: 180, call_oi: 4000, put_oi: 4500, call_volume: 800, put_volume: 850 },
    { strike: 219, net_gamma: -8, call_gamma: 200, put_gamma: 208, net_vega: -10, call_vega: 250, put_vega: 260, call_oi: 5000, put_oi: 5200, call_volume: 900, put_volume: 1000 },
    { strike: 220, net_gamma: -8, call_gamma: 240, put_gamma: 248, net_vega: -10, call_vega: 300, put_vega: 310, call_oi: 6000, put_oi: 6200, call_volume: 1200, put_volume: 1300 },
    { strike: 221, net_gamma: -4, call_gamma: 200, put_gamma: 204, net_vega: -5, call_vega: 250, put_vega: 255, call_oi: 5000, put_oi: 5100, call_volume: 950, put_volume: 1100 },
    { strike: 222, net_gamma: -12, call_gamma: 120, put_gamma: 132, net_vega: -16, call_vega: 160, put_vega: 176, call_oi: 4000, put_oi: 4400, call_volume: 700, put_volume: 900 },
  ],
  gex_by_strike: [
    { strike: 218, gex: -7260, call_gex: 58080, put_gex: -65340 },
    { strike: 219, gex: -3872, call_gex: 96800, put_gex: -100672 },
    { strike: 220, gex: -3872, call_gex: 116160, put_gex: -120032 },
    { strike: 221, gex: -1936, call_gex: 96800, put_gex: -98736 },
    { strike: 222, gex: -5808, call_gex: 58080, put_gex: -63888 },
  ],
  metrics: {
    total_gex: -22748,
    total_vex: -506220,
    zero_gamma: null,
    max_pain: 220,
    implied_move: 1.6065001960784193,
    put_call_ratio: 1.0583333333333333,
  },
  nodes: { kingNode: null, gatekeepers: [], midpoints: [], allNodes: [] },
  config: { strike_range_pct: 0.15, atm_tolerance: 0.02, node_min_gamma: 500 },
};

// GammaSummary contract from GET /api/options/{ticker}/{date}/levels
// (options.py:611 → lib.gamma.build_summary): ticker, snapshot_date,
// spot{price,method,note}, gamma_balance, gamma_flip, regime, total_gex,
// levels[], kings[], gates[], gamma_balance_levels[], window_pct, warnings,
// snapshot_timestamp, chain_size. Unlike MOCK_LEVELS (the empty variant used
// by navigation/demo-banner specs), this one carries a populated taxonomy so
// the King/Gate/regime UI renders.
const level = (
  strike: number,
  gex: number,
  kind: 'king' | 'gate' | 'spot' | 'gamma_balance' | 'none',
  tags: string[],
) => ({
  strike,
  gex,
  net_gamma: gex / 48_400, // spot² × 100 multiplier inverted — plausible, unused by UI
  call_oi: 5000,
  put_oi: 5200,
  distance_pct: ((strike - 220) / 220) * 100,
  score: Math.abs(gex) / 2_000_000,
  kind,
  tags,
});

export const MOCK_LEVELS_POPULATED = {
  ticker: 'IWM',
  snapshot_date: '2026-04-25',
  spot: { price: 220, method: 'parity', note: 'K=220.0 C=1.20 P=1.15 exp=2026-04-25' },
  gamma_balance: 219.5,
  gamma_flip: 219.75,
  regime: 'positive_gamma',
  total_gex: 1_250_000,
  levels: [
    level(218, 620_000, 'gate', ['gate']),
    level(219, -180_000, 'gamma_balance', ['gamma_balance']),
    level(220, 1_950_000, 'king', ['king', 'spot']),
    level(221, 710_000, 'gate', ['gate']),
    level(222, 240_000, 'none', []),
  ],
  kings: [level(220, 1_950_000, 'king', ['king', 'spot'])],
  gates: [level(218, 620_000, 'gate', ['gate']), level(221, 710_000, 'gate', ['gate'])],
  gamma_balance_levels: [level(219, -180_000, 'gamma_balance', ['gamma_balance'])],
  window_pct: 6,
  warnings: [],
  snapshot_timestamp: '2026-04-25T20:00:00+00:00',
  chain_size: 10,
};

// GammaGridSummary contract from GET /api/options/{ticker}/grid (grid.py:529
// → lib.gamma.build_grid_summary): per-(strike, expiration) cells with the
// full GEX/VEX field set — see useGammaGrid.ts GammaGridCell.
const gridCell = (strike: number, expiration: string, dte: number, gex: number, vex: number) => ({
  strike,
  expiration,
  dte,
  net_gamma: gex / 48_400,
  call_gamma: Math.abs(gex) / 96_800,
  put_gamma: Math.abs(gex) / 96_800,
  net_vega: vex / 48_400,
  call_vega: Math.abs(vex) / 96_800,
  put_vega: Math.abs(vex) / 96_800,
  gex,
  call_gex: gex > 0 ? gex * 1.5 : gex * -0.5,
  put_gex: gex > 0 ? gex * -0.5 : gex * 1.5,
  vex,
  call_vex: vex > 0 ? vex * 1.5 : vex * -0.5,
  put_vex: vex > 0 ? vex * -0.5 : vex * 1.5,
  call_oi: 5000,
  put_oi: 5200,
  call_volume: 900,
  put_volume: 1000,
  distance_pct: ((strike - 220) / 220) * 100,
  pct_change: null,
  abs_change: null,
});

export const MOCK_GRID_POPULATED = {
  ticker: 'IWM',
  snapshot_date: '2026-04-25',
  snapshot_ts: '2026-04-25T20:00:00+00:00',
  data_source: 'eod_fallback',
  spot: { price: 220, method: 'parity', note: 'K=220.0 C=1.20 P=1.15 exp=2026-04-25' },
  gamma_balance: 219.5,
  gamma_flip: 219.75,
  regime: 'positive_gamma',
  total_gex: 1_250_000,
  total_vex: -350_000,
  cells: [
    gridCell(218, '2026-04-25', 0, 420_000, -60_000),
    gridCell(219, '2026-04-25', 0, -120_000, -40_000),
    gridCell(220, '2026-04-25', 0, 1_310_000, -90_000), // King cell (largest |net GEX|)
    gridCell(221, '2026-04-25', 0, 480_000, -55_000),
    gridCell(222, '2026-04-25', 0, 160_000, -30_000),
    gridCell(218, '2026-05-16', 21, 200_000, -25_000),
    gridCell(219, '2026-05-16', 21, -60_000, -15_000),
    gridCell(220, '2026-05-16', 21, 640_000, -45_000),
    gridCell(221, '2026-05-16', 21, 230_000, -20_000),
    gridCell(222, '2026-05-16', 21, 80_000, -10_000),
  ],
  expirations: ['2026-04-25', '2026-05-16'],
  strikes: [218, 219, 220, 221, 222],
  window_pct: 6,
  warnings: [],
};

/**
 * Intercept every options endpoint the /options page can hit (both the
 * default Heatseeker/Swing view and the Profiles tab), scoped to IWM (the
 * app's default ticker). Registration order matters: Playwright matches
 * routes newest-first, so the single-segment chain glob goes FIRST and the
 * more specific /grid and /levels patterns after it take precedence.
 * Includes `mockCommon`, so callers don't need to call it separately.
 */
export async function mockOptionsApi(page: Page) {
  await mockCommon(page);
  await page.route('**/api/options/dates/IWM', (r) => r.fulfill(ok(MOCK_OPTIONS_DATES)));
  // Chain (single-segment glob: does NOT match /grid?…, /…/levels or
  // /api/options/live/IWM/… — those are handled below / by the caller).
  await page.route('**/api/options/IWM/*', (r) => r.fulfill(ok(MOCK_OPTIONS_CHAIN)));
  await page.route('**/api/options/IWM/grid*', (r) => r.fulfill(ok(MOCK_GRID_POPULATED)));
  await page.route('**/api/options/IWM/*/levels*', (r) => r.fulfill(ok(MOCK_LEVELS_POPULATED)));
  await page.route('**/api/options/greeks', (r) => r.fulfill(ok(MOCK_GREEKS)));
}

export const M = { ok, notFound };
