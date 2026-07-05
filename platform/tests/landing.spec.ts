import { expect, test } from '@playwright/test';

// A well-formed (but fake) Firebase web config — enough for initializeApp() to
// construct without throwing; no network is needed to render the signed-out
// landing page (same fixture as tests/auth-gate.spec.ts).
const FAKE_FIREBASE = {
  apiKey: 'AIzaSyFAKE-key-for-tests-000000000000000',
  authDomain: 'demo-test.firebaseapp.com',
  projectId: 'demo-test',
  appId: '1:1234567890:web:abcdef0123456789',
};

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

  test('landing renders at / even in firebase auth mode (signed out)', async ({ page }) => {
    // Route contract: `/` is the public LandingPage route (not wrapped by
    // AuthGate — see platform/src/App.tsx), so it must render regardless of
    // auth mode. Registered directly (no mockCommon) since `/` never calls
    // /api/me or /api/live/status; only /api/config/firebase is fetched at
    // boot (platform/src/main.tsx).
    await page.route('**/api/config/firebase', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ authMode: 'firebase', firebase: FAKE_FIREBASE }),
      }),
    );
    await page.goto('/');
    await expect(page.getByTestId('landing-page')).toBeVisible();
    await expect(page.getByTestId('signin-screen')).toHaveCount(0);
  });
});
