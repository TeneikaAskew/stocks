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

// ── Freshness badge: REALTIME / EOD / Stale (Track 4) ──────────────────────
// The badge sits next to the date selector in the toolbar. Tone derives
// purely from the chain response's market_session + snapshot_timestamp,
// so we drive these three states by varying just those two fields.

const FRESHNESS_BASE = {
  ticker: 'IWM',
  date: '2026-04-25',
  options: MOCK_CHAIN.options,
  metadata: { source: 'cloud_sql', data_source: 'alphavantage', row_count: 10 },
};

test.describe('Options Flow — freshness badge', () => {
  test('REALTIME chain shows green Live · HH:MM ET badge', async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/options/dates/IWM', (r) => r.fulfill(M.ok(MOCK_DATES)));
    await page.route('**/api/options/IWM/*', (r) =>
      r.fulfill(
        M.ok({
          ...FRESHNESS_BASE,
          // Use an explicit UTC time so the rendered ET time is deterministic.
          // 18:32 UTC on 2026-04-25 = 14:32 ET (EDT, UTC-4).
          snapshot_timestamp: '2026-04-25T18:32:00Z',
          market_session: 'REALTIME',
        })
      )
    );
    await page.goto('/options');
    await page.waitForLoadState('networkidle');
    const badge = page.getByTestId('options-freshness-badge');
    await expect(badge).toBeVisible();
    await expect(badge).toHaveAttribute('data-tone', 'live');
    await expect(badge).toContainText(/^Live · \d{2}:\d{2} ET$/);
  });

  test('EOD chain shows amber EOD · DOW HH:MM badge', async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/options/dates/IWM', (r) => r.fulfill(M.ok(MOCK_DATES)));
    // Build an EOD timestamp within the ≤2-trading-day fresh window relative
    // to the wall clock the test is running at — otherwise the test silently
    // becomes a stale-badge test as time marches on.
    const recentEod = new Date(Date.now() - 16 * 3600 * 1000).toISOString();
    await page.route('**/api/options/IWM/*', (r) =>
      r.fulfill(
        M.ok({
          ...FRESHNESS_BASE,
          snapshot_timestamp: recentEod,
          market_session: 'EOD',
        })
      )
    );
    await page.goto('/options');
    await page.waitForLoadState('networkidle');
    const badge = page.getByTestId('options-freshness-badge');
    await expect(badge).toBeVisible();
    await expect(badge).toHaveAttribute('data-tone', 'eod');
    await expect(badge).toContainText(/^EOD · [A-Z][a-z]{2} \d{2}:\d{2} ET$/);
  });

  test('stale chain (>2 trading days old EOD) shows red Stale · Nd old badge', async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/options/dates/IWM', (r) => r.fulfill(M.ok(MOCK_DATES)));
    await page.route('**/api/options/IWM/*', (r) =>
      r.fulfill(
        M.ok({
          ...FRESHNESS_BASE,
          // 30 days old — definitely outside the 2-trading-day window.
          snapshot_timestamp: '2026-01-15T21:00:00Z',
          market_session: 'EOD',
        })
      )
    );
    await page.goto('/options');
    await page.waitForLoadState('networkidle');
    const badge = page.getByTestId('options-freshness-badge');
    await expect(badge).toBeVisible();
    await expect(badge).toHaveAttribute('data-tone', 'stale');
    await expect(badge).toContainText(/^Stale · \d+d old$/);
  });

  test('legacy chain (null market_session) shows Stale badge', async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/options/dates/IWM', (r) => r.fulfill(M.ok(MOCK_DATES)));
    await page.route('**/api/options/IWM/*', (r) =>
      r.fulfill(
        M.ok({
          ...FRESHNESS_BASE,
          snapshot_timestamp: '2026-04-25T21:00:00Z',
          market_session: null,
        })
      )
    );
    await page.goto('/options');
    await page.waitForLoadState('networkidle');
    const badge = page.getByTestId('options-freshness-badge');
    await expect(badge).toBeVisible();
    await expect(badge).toHaveAttribute('data-tone', 'stale');
  });
});

// ── Live fallback: Cloud SQL 404 → AlphaVantage live proxy ────────────────
// Replaces the decommissioned Cloudflare Worker. When the EOD Cloud SQL
// endpoint returns 404 (e.g. today's date before the 9 PM fetcher), the page
// must fall through to /api/options/live/{ticker}/{date} and render the same
// heatmap with an "AlphaVantage Live" source badge.

test.describe('Options Flow — live AV fallback', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/options/dates/IWM', (r) => r.fulfill(M.ok(MOCK_DATES)));
    // Cloud SQL endpoint 404s — segment glob is single-level so it does NOT
    // capture /api/options/live/IWM/...
    await page.route('**/api/options/IWM/*', (r) =>
      r.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'No AlphaVantage options data ingested for IWM.' }),
      })
    );
    // Live endpoint returns the chain with the live source badge.
    await page.route('**/api/options/live/IWM/*', (r) =>
      r.fulfill(
        M.ok({
          ...MOCK_CHAIN,
          metadata: { source: 'alphavantage_live', data_source: 'alphavantage', row_count: 10 },
        })
      )
    );
  });

  test('falls back to live endpoint and shows AlphaVantage Live badge', async ({ page }) => {
    await page.goto('/options');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/AlphaVantage Live/).first()).toBeVisible();
  });
});
