/**
 * E2E: the app-level auth gate.
 *
 * The gate only engages in `firebase` auth mode (the public app-login service).
 * In `open`/`iap` mode it's inert and the app renders directly — which is why
 * every other spec (open mode) is unaffected.
 *
 * Real Google/email sign-in needs a live Firebase project, so that path is
 * covered by the staging manual verification, not here. These specs assert the
 * gate's render decision + that the login UI is present in firebase mode.
 */
import { test, expect } from '@playwright/test';
import { mockCommon } from './helpers/mocks';

// A well-formed (but fake) Firebase web config — enough for initializeApp() to
// construct without throwing; no network is needed to render the signed-out UI.
const FAKE_FIREBASE = {
  apiKey: 'AIzaSyFAKE-key-for-tests-000000000000000',
  authDomain: 'demo-test.firebaseapp.com',
  projectId: 'demo-test',
  appId: '1:1234567890:web:abcdef0123456789',
};

test.describe('Auth gate', () => {
  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
  });

  test('open mode → app renders, no login screen', async ({ page }) => {
    await mockCommon(page); // config → { authMode: 'open' }
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });

    await expect(page.locator('nav a[href="/help"]')).toBeVisible();
    await expect(page.getByTestId('signin-screen')).toHaveCount(0);
  });

  test('firebase mode, signed out → login screen blocks the app', async ({ page }) => {
    await mockCommon(page);
    // Registered after mockCommon so it wins (Playwright: last route matches first).
    await page.route('**/api/config/firebase', (r) =>
      r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ authMode: 'firebase', firebase: FAKE_FIREBASE }),
      }),
    );

    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });

    await expect(page.getByTestId('signin-screen')).toBeVisible();
    await expect(page.getByTestId('google-signin')).toBeVisible();
    await expect(page.getByTestId('login-email')).toBeVisible();
    await expect(page.getByTestId('login-password')).toBeVisible();
    // The app shell must NOT be reachable behind the gate.
    await expect(page.locator('nav a[href="/help"]')).toHaveCount(0);
  });

  test('login screen toggles between sign-in and sign-up', async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/config/firebase', (r) =>
      r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ authMode: 'firebase', firebase: FAKE_FIREBASE }),
      }),
    );

    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
    await expect(page.getByTestId('login-submit')).toHaveText(/sign in/i);

    await page.getByTestId('login-toggle').click();
    await expect(page.getByTestId('login-submit')).toHaveText(/create account/i);
  });
});
