import { expect, test } from '@playwright/test';

// Landing page smoke — runs against the dev server (open auth mode), where
// the landing page is the default page at / in every auth mode.
test.describe('Solyra landing page', () => {
  test('renders all key sections at /', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByTestId('landing-page')).toBeVisible();
    await expect(page.getByRole('heading', { name: /know why the market moves/i })).toBeVisible();
    await expect(page.getByText('Everything that moves the market. One surface.')).toBeVisible();
    await expect(page.getByText(/charts that show the/i)).toBeVisible();
    await expect(page.getByText('One market day with Solyra.')).toBeVisible();
    await expect(page.getByText('Be there at first light.')).toBeVisible();
    // Public module names only — competitor names must never appear.
    await expect(page.getByText(/heatseeker|flowseeker|skylit/i)).toHaveCount(0);
  });

  test('waitlist form rejects an invalid email with a visible error', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('waitlist-email').fill('not-an-email');
    await page.getByTestId('waitlist-submit').click();
    await expect(page.getByTestId('waitlist-error')).toContainText(/valid email/i);
  });
});
