/**
 * Regression: demo-data banners on mock options surfaces.
 *
 * Flowseeker (live feed) and SwingMode (heatmap) render data disclaimers
 * to prevent silent drift into illusion of liveness. This suite pins
 * those banners so they can't vanish while the tabs stay mock.
 */
import { test, expect } from '@playwright/test';
import { mockCommon, M, MOCK_GRID, MOCK_LEVELS } from './helpers/mocks';

test.describe('Mock data surfaces stay banner-honest', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);

    // Options page needs grid/levels/dates endpoints to avoid infinite loading
    const MOCK_DATES = { ticker: 'IWM', dates: ['2026-04-25', '2026-04-24'] };

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
