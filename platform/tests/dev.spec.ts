/**
 * E2E: /dev info page.
 *
 * Verifies the dev/test-account info page renders and exposes the
 * Playwright tester service-account email. Used as a sanity check that
 * the test-account contract is wired through env → API → page.
 */
import { test, expect } from '@playwright/test';

test('/dev page exposes Playwright tester SA email', async ({ page }) => {
  await page.goto('/dev');

  await expect(page.locator('h1')).toContainText('test accounts');

  // The tester SA email should be rendered. Default is set in the API layer
  // when PLAYWRIGHT_TESTER_SA env var is unset, so this works locally too.
  const body = await page.textContent('body');
  expect(body).toMatch(/playwright-tester@.*\.iam\.gserviceaccount\.com/);
});

test('/dev page documents the browser sign-in path', async ({ page }) => {
  await page.goto('/dev');
  const body = await page.textContent('body');
  expect(body).toContain('Browser access');
  expect(body).toContain('gcloud run services proxy');
});
