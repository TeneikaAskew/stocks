/**
 * Regression: demo-data banners on mock options surfaces.
 *
 * Flowseeker (live feed) and SwingMode (heatmap) render data disclaimers
 * to prevent silent drift into illusion of liveness. This suite pins
 * those banners so they can't vanish while the tabs stay mock.
 */
import { test, expect } from '@playwright/test';
import { mockCommon, M } from './helpers/mocks';

test.describe('Mock data surfaces stay banner-honest', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);

    // Options page needs grid/levels/dates endpoints to avoid infinite loading
    const MOCK_DATES = { ticker: 'IWM', dates: ['2026-04-25', '2026-04-24'] };
    const MOCK_LEVELS = {
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
    const MOCK_GRID = {
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

    await page.route('**/api/options/dates/IWM', (r) => r.fulfill(M.ok(MOCK_DATES)));
    await page.route('**/api/options/IWM/*/levels', (r) => r.fulfill(M.ok(MOCK_LEVELS)));
    await page.route('**/api/options/**/grid**', (route) => route.fulfill(M.ok(MOCK_GRID)));

    await page.goto('/options');
    await page.waitForLoadState('networkidle');
  });

  test('Heatseeker Swing Mode shows the demo banner', async ({ page }) => {
    // Heatseeker is the default tab; SwingMode is the default inner mode.
    // The SwingMode component renders <div class="hs-demo-banner">
    await expect(page.locator('.hs-demo-banner').first()).toBeVisible();
  });

  test('Flowseeker tab shows the demo banner text', async ({ page }) => {
    // Click the Flowseeker tab (button with "Flowseeker" text)
    await page.getByRole('button', { name: /Flowseeker/i }).click();
    // Wait for the component to render
    await page.waitForLoadState('networkidle');
    // FlowseekerTab renders <DemoDataBanner> with text "Demo data — not live."
    // (The em dash is U+2014, copied from DemoDataBanner.tsx line 23)
    await expect(page.getByText('Demo data — not live.').first()).toBeVisible();
  });
});
