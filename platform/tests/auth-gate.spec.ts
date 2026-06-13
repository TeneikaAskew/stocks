/**
 * E2E: staging auth gate (the passcode sign-in screen).
 *
 * The gate only engages when the server reports `auth_bypass_allowed: true`
 * (the public, no-IAP staging service). Everywhere else it's inert and the
 * app renders straight through — which is why every other spec is unaffected.
 *
 * Scenarios:
 *   1. bypass NOT allowed → app renders, no sign-in screen (prod/local).
 *   2. authenticated email → app renders, no sign-in screen.
 *   3. bypass allowed, no session → sign-in screen, app NOT rendered.
 *   4. wrong passcode → explicit error, still gated.
 *   5. correct passcode → cookie set, /api/me flips to guest, app renders.
 */
import { test, expect } from '@playwright/test';
import { mockCommon } from './helpers/mocks';

test.describe('Auth gate — staging passcode', () => {
  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
  });

  test('bypass not allowed → app renders, no sign-in screen', async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/me', (r) =>
      r.fulfill({ status: 200, body: JSON.stringify({ email: null, auth_bypass_allowed: false }) }),
    );

    await page.goto('/', { waitUntil: 'domcontentloaded' });

    await expect(page.locator('nav a[href="/help"]')).toBeVisible();
    await expect(page.getByTestId('signin-screen')).toHaveCount(0);
  });

  test('authenticated email → app renders, no sign-in screen', async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/me', (r) =>
      r.fulfill({
        status: 200,
        body: JSON.stringify({ email: 'guest@staging.local', auth_bypass_allowed: true }),
      }),
    );

    await page.goto('/', { waitUntil: 'domcontentloaded' });

    await expect(page.locator('nav a[href="/help"]')).toBeVisible();
    await expect(page.getByTestId('signin-screen')).toHaveCount(0);
  });

  test('bypass allowed, no session → sign-in screen blocks the app', async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/me', (r) =>
      r.fulfill({ status: 200, body: JSON.stringify({ email: null, auth_bypass_allowed: true }) }),
    );

    await page.goto('/', { waitUntil: 'domcontentloaded' });

    await expect(page.getByTestId('signin-screen')).toBeVisible();
    await expect(page.getByTestId('staging-passcode-input')).toBeVisible();
    // The app shell must NOT be reachable behind the gate.
    await expect(page.locator('nav a[href="/help"]')).toHaveCount(0);
  });

  test('wrong passcode → explicit error, still gated', async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/me', (r) =>
      r.fulfill({ status: 200, body: JSON.stringify({ email: null, auth_bypass_allowed: true }) }),
    );
    await page.route('**/api/auth/bypass', (r) =>
      r.fulfill({ status: 401, body: JSON.stringify({ detail: 'invalid staging passcode' }) }),
    );

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.getByTestId('staging-passcode-input').fill('wrong');
    await page.getByTestId('staging-submit').click();

    await expect(page.getByTestId('staging-error')).toHaveText('Invalid passcode.');
    await expect(page.getByTestId('signin-screen')).toBeVisible();
  });

  test('correct passcode → app renders', async ({ page }) => {
    await mockCommon(page);

    // /api/me flips to an authenticated guest after the bypass POST succeeds.
    let passed = false;
    await page.route('**/api/me', (r) =>
      r.fulfill({
        status: 200,
        body: JSON.stringify({
          email: passed ? 'guest@staging.local' : null,
          auth_bypass_allowed: true,
        }),
      }),
    );
    await page.route('**/api/auth/bypass', (r) => {
      const body = JSON.parse(r.request().postData() || '{}');
      if (body.passcode === 'correct-code') {
        passed = true;
        return r.fulfill({ status: 200, body: JSON.stringify({ ok: true, email: 'guest@staging.local' }) });
      }
      return r.fulfill({ status: 401, body: JSON.stringify({ detail: 'invalid staging passcode' }) });
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await expect(page.getByTestId('signin-screen')).toBeVisible();

    await page.getByTestId('staging-passcode-input').fill('correct-code');
    await page.getByTestId('staging-submit').click();

    // Gate flips: sign-in screen gone, app shell rendered.
    await expect(page.getByTestId('signin-screen')).toHaveCount(0);
    await expect(page.locator('nav a[href="/help"]')).toBeVisible();
  });

  test('guest badge exits back to the sign-in screen', async ({ page }) => {
    await mockCommon(page);

    let loggedIn = true; // start as guest (already passed the passcode)
    await page.route('**/api/me', (r) =>
      r.fulfill({
        status: 200,
        body: JSON.stringify({
          email: loggedIn ? 'guest@staging.local' : null,
          auth_bypass_allowed: true,
        }),
      }),
    );
    await page.route('**/api/auth/logout', (r) => {
      loggedIn = false;
      return r.fulfill({ status: 200, body: JSON.stringify({ ok: true }) });
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });

    // Guest badge is visible; exit clears the session and re-gates.
    await expect(page.getByTestId('guest-badge')).toBeVisible();
    await page.getByTestId('guest-exit').click();

    await expect(page.getByTestId('signin-screen')).toBeVisible();
  });
});
