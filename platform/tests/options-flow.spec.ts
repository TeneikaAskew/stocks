/**
 * E2E: Options Flow ("/options") — chain heatmap, toggles, live AV fallback.
 *
 * The page was restructured (OptionsFlowPage.tsx): it now opens on the
 * Heatseeker tab (SwingMode grid cockpit) and the original chain-profile
 * body — D3 GEX heatmap, net/calls/puts toggles, source footer — lives in
 * the Profiles tab (ProfilesTab.tsx), reached via the top-level segmented
 * control. Tests that assert the chain UI click into Profiles first.
 *
 * All backend traffic is intercepted via mockOptionsApi (helpers/mocks.ts):
 * dates, chain, grid, levels, and the greeks POST — the full fan-out of the
 * page. An unmocked request would hit the Vite proxy and 500 without a
 * backend.
 */
import { test, expect } from '@playwright/test';
import {
  mockOptionsApi,
  mockCommon,
  MOCK_OPTIONS_DATES,
  MOCK_OPTIONS_CHAIN,
  MOCK_GRID_POPULATED,
  MOCK_GREEKS,
  M,
} from './helpers/mocks';

/** Open the Profiles tab (the original chain-profile view). */
async function openProfilesTab(page: import('@playwright/test').Page) {
  await page.getByRole('button', { name: 'Profiles' }).click();
}

test.describe('Options Flow', () => {
  test.beforeEach(async ({ page }) => {
    await mockOptionsApi(page);
  });

  test('navigates to /options', async ({ page }) => {
    await page.goto('/options');
    await page.waitForLoadState('networkidle');
    // The restructured page (OptionsFlowPage.tsx) no longer renders the
    // literal word "options" — its landmark is the Symbol combobox plus the
    // Heatseeker / Flowseeker / Profiles view switcher (TABS).
    await expect(page.getByText('Symbol', { exact: true })).toBeVisible();
    for (const tab of ['Heatseeker', 'Flowseeker', 'Profiles']) {
      await expect(page.getByRole('button', { name: tab })).toBeVisible();
    }
  });

  test('renders strike values in chain heatmap (Profiles tab)', async ({ page }) => {
    await page.goto('/options');
    await page.waitForLoadState('networkidle');
    await openProfilesTab(page);
    // Strike 220 should appear at least once (as an axis label in the D3
    // heatmap ProfilesTab renders from the mocked chain)
    await expect(page.getByText(/220/).first()).toBeVisible();
  });

  test('renders chart axes and net/calls/puts toggle (Profiles tab)', async ({ page }) => {
    await page.goto('/options');
    await page.waitForLoadState('networkidle');
    await openProfilesTab(page);
    // ProfilesTab renders a GEX/VEX chart; toggle labels are visible in the toolbar
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

// ── Live fallback: Cloud SQL 404 → AlphaVantage live proxy ────────────────
// Replaces the decommissioned Cloudflare Worker. When the EOD Cloud SQL
// endpoint returns 404 (e.g. today's date before the 9 PM fetcher), the
// Profiles tab must fall through to /api/options/live/{ticker}/{date} and
// render the same heatmap with an "AlphaVantage Live" source badge
// (ProfilesTab.tsx useOptionsData + source footer).

test.describe('Options Flow — live AV fallback', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/options/dates/IWM', (r) => r.fulfill(M.ok(MOCK_OPTIONS_DATES)));
    // Cloud SQL chain endpoint 404s — segment glob is single-level so it does
    // NOT capture /api/options/live/IWM/... (and the grid/levels routes
    // registered after it take precedence for their URLs).
    await page.route('**/api/options/IWM/*', (r) =>
      r.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'No AlphaVantage options data ingested for IWM.' }),
      })
    );
    // The Swing grid and gamma levels are independent of the chain fallback;
    // keep the grid alive and let /levels 404 too (the EOD snapshot that
    // backs /levels is the same one that 404'd above). ProfilesTab then
    // estimates spot from the chain's deltas instead of the server spot.
    await page.route('**/api/options/IWM/grid*', (r) => r.fulfill(M.ok(MOCK_GRID_POPULATED)));
    await page.route('**/api/options/IWM/*/levels*', (r) =>
      r.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'No AlphaVantage options data ingested for IWM.' }),
      })
    );
    await page.route('**/api/options/greeks', (r) => r.fulfill(M.ok(MOCK_GREEKS)));
    // Live endpoint returns the chain with the live source badge.
    await page.route('**/api/options/live/IWM/*', (r) =>
      r.fulfill(
        M.ok({
          ...MOCK_OPTIONS_CHAIN,
          metadata: { source: 'alphavantage_live', data_source: 'alphavantage', row_count: 10 },
        })
      )
    );
  });

  test('falls back to live endpoint and shows AlphaVantage Live badge', async ({ page }) => {
    await page.goto('/options');
    await page.waitForLoadState('networkidle');
    await openProfilesTab(page);
    await expect(page.getByText(/AlphaVantage Live/).first()).toBeVisible();
  });
});
