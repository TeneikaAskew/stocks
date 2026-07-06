/**
 * E2E: Admin role-based access control.
 *
 * Tests the IAP-email-based admin bypass, sidebar visibility, and
 * token-gate fallback. Backend is fully mocked via page.route.
 *
 * Scenarios:
 *   1. Admin email (teneika@bictech.org) bypasses the token gate
 *   2. Admin email sees the routing panel without a logout button
 *   3. Non-admin users see the token gate on /admin
 *   4. Sidebar shows Admin link only for the admin email
 *   5. Sidebar hides Admin link for non-admin / anonymous users
 *   6. Non-admin with valid token still sees logout button
 *   7. Admin can edit routes without needing a token header
 */
import { test, expect } from '@playwright/test';

const ADMIN_EMAIL = 'teneika@bictech.org';

const MOCK_ROUTES = {
  routes: [
    { role: 'analyst', provider: 'vertex', model: 'gemini-2.0-flash', updated_at: null, updated_by: null },
    { role: 'bull', provider: 'vertex', model: 'gemini-2.0-flash', updated_at: null, updated_by: null },
    { role: 'bear', provider: 'vertex', model: 'gemini-2.0-flash', updated_at: null, updated_by: null },
    { role: 'judge', provider: 'vertex', model: 'gemini-2.0-flash', updated_at: null, updated_by: null },
    { role: 'trader', provider: 'vertex', model: 'gemini-2.0-flash', updated_at: null, updated_by: null },
    { role: 'risk', provider: 'vertex', model: 'gemini-2.0-flash', updated_at: null, updated_by: null },
    { role: 'portfolio_manager', provider: 'vertex', model: 'gemini-2.0-flash', updated_at: null, updated_by: null },
  ],
};

const MOCK_MODELS = {
  models: [
    { provider: 'vertex', model: 'gemini-2.0-flash', has_credentials: true, input_usd_per_mtok: 0.1, output_usd_per_mtok: 0.4 },
    { provider: 'vertex', model: 'gemini-2.5-pro', has_credentials: true, input_usd_per_mtok: 1.25, output_usd_per_mtok: 10.0 },
    { provider: 'anthropic', model: 'claude-sonnet-4-6', has_credentials: false, input_usd_per_mtok: 3.0, output_usd_per_mtok: 15.0 },
  ],
};

/** Set up common admin API mocks (routes + models always succeed). */
async function mockAdminApi(page: import('@playwright/test').Page) {
  await page.route('**/api/admin/routes', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ status: 200, body: JSON.stringify(MOCK_ROUTES) });
    }
    return route.continue();
  });
  await page.route('**/api/admin/models', (route) =>
    route.fulfill({ status: 200, body: JSON.stringify(MOCK_MODELS) }),
  );
}

// The boot-time runtime-config probe must resolve to a valid config or the app
// renders its "could not load configuration" error screen instead of the app
// (main.tsx fails loud rather than silently defaulting to open mode — see
// CLAUDE.md Rule 3.7). `open` mode keeps the auth gate inert, so these
// admin/sidebar specs exercise the app exactly as before.
test.beforeEach(async ({ page }) => {
  await page.route('**/api/config/firebase', (route) =>
    route.fulfill({ status: 200, body: JSON.stringify({ authMode: 'open', firebase: null }) }),
  );
});

// ---------------------------------------------------------------------------
// Admin email bypass
// ---------------------------------------------------------------------------

test.describe('Admin — IAP email bypass', () => {
  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
  });

  test('admin email skips token gate and sees routing panel directly', async ({ page }) => {
    await page.route('**/api/me', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ email: ADMIN_EMAIL, is_admin: true }) }),
    );
    await mockAdminApi(page);

    await page.goto('/admin');

    // Token gate should NOT appear
    await expect(page.getByTestId('admin-token-input')).not.toBeVisible();

    // Routing table should render directly
    await expect(page.getByTestId('admin-routes-table')).toBeVisible();
    await expect(page.getByText('analyst')).toBeVisible();
    await expect(page.getByText('portfolio_manager')).toBeVisible();
  });

  test('admin email does not see the logout button', async ({ page }) => {
    await page.route('**/api/me', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ email: ADMIN_EMAIL, is_admin: true }) }),
    );
    await mockAdminApi(page);

    await page.goto('/admin');

    await expect(page.getByTestId('admin-routes-table')).toBeVisible();
    // Logout button should be hidden for IAP-authenticated admin
    await expect(page.getByTestId('admin-logout')).not.toBeVisible();
  });

  test('admin email can edit a route without providing a token', async ({ page }) => {
    await page.route('**/api/me', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ email: ADMIN_EMAIL, is_admin: true }) }),
    );
    await mockAdminApi(page);

    let putBody: unknown = null;
    await page.route('**/api/admin/routes/trader', (route) => {
      if (route.request().method() === 'PUT') {
        putBody = JSON.parse(route.request().postData() || '{}');
        return route.fulfill({
          status: 200,
          body: JSON.stringify({
            role: 'trader',
            provider: 'vertex',
            model: 'gemini-2.5-pro',
            updated_at: '2026-04-26T10:00:00Z',
            updated_by: 'admin-ui',
          }),
        });
      }
      return route.continue();
    });

    await page.goto('/admin');
    await expect(page.getByTestId('admin-routes-table')).toBeVisible();

    // Change model for trader
    await page.getByTestId('model-trader').selectOption('gemini-2.5-pro');
    await page.getByTestId('save-trader').click();

    await expect.poll(() => putBody, { timeout: 5_000 }).toEqual({
      provider: 'vertex',
      model: 'gemini-2.5-pro',
    });
  });
});

// ---------------------------------------------------------------------------
// Non-admin users
// ---------------------------------------------------------------------------

test.describe('Admin — non-admin users', () => {
  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
  });

  test('anonymous user sees token gate', async ({ page }) => {
    await page.route('**/api/me', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ email: null, is_admin: false }) }),
    );

    await page.goto('/admin');
    await page.waitForLoadState('networkidle');

    await expect(page.getByTestId('admin-token-input')).toBeVisible();
    await expect(page.getByTestId('admin-routes-table')).not.toBeVisible();
  });

  test('non-admin email sees token gate', async ({ page }) => {
    await page.route('**/api/me', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ email: 'someone@example.com', is_admin: false }) }),
    );

    await page.goto('/admin');
    await page.waitForLoadState('networkidle');

    await expect(page.getByTestId('admin-token-input')).toBeVisible();
    await expect(page.getByTestId('admin-routes-table')).not.toBeVisible();
  });

  test('non-admin with valid token sees logout button', async ({ page }) => {
    await page.route('**/api/me', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ email: 'someone@example.com', is_admin: false }) }),
    );
    await page.route('**/api/admin/routes', (route) => {
      const token = route.request().headers()['x-admin-token'];
      if (token === 'valid-token') {
        return route.fulfill({ status: 200, body: JSON.stringify(MOCK_ROUTES) });
      }
      return route.fulfill({ status: 401, body: JSON.stringify({ detail: 'bad' }) });
    });
    await page.route('**/api/admin/models', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify(MOCK_MODELS) }),
    );

    await page.goto('/admin');
    await page.waitForLoadState('networkidle');

    // Unlock via token
    await page.getByTestId('admin-token-input').fill('valid-token');
    await page.getByTestId('admin-submit').click();

    await expect(page.getByTestId('admin-routes-table')).toBeVisible();
    // Non-admin token users SHOULD see the logout button
    await expect(page.getByTestId('admin-logout')).toBeVisible();
  });

  test('/api/me failure gracefully falls back to non-admin', async ({ page }) => {
    await page.route('**/api/me', (route) =>
      route.fulfill({ status: 500, body: 'Internal Server Error' }),
    );

    await page.goto('/admin');
    await page.waitForLoadState('networkidle');

    // Should fall back to the token gate
    await expect(page.getByTestId('admin-token-input')).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Sidebar visibility
// ---------------------------------------------------------------------------

test.describe('Sidebar — Admin link visibility', () => {
  test('admin email sees Admin link in sidebar', async ({ page }) => {
    await page.route('**/api/me', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ email: ADMIN_EMAIL, is_admin: true }) }),
    );

    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });

    const adminLink = page.locator('nav a[href="/admin"]');
    await expect(adminLink).toBeVisible();
  });

  test('anonymous user does not see Admin link in sidebar', async ({ page }) => {
    await page.route('**/api/me', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ email: null, is_admin: false }) }),
    );

    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });

    // Wait for the nav to render (Help link is always visible)
    await expect(page.locator('nav a[href="/help"]')).toBeVisible();
    const adminLink = page.locator('nav a[href="/admin"]');
    await expect(adminLink).not.toBeVisible();
  });

  test('non-admin email does not see Admin link in sidebar', async ({ page }) => {
    await page.route('**/api/me', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ email: 'user@other.org', is_admin: false }) }),
    );

    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });

    await expect(page.locator('nav a[href="/help"]')).toBeVisible();
    const adminLink = page.locator('nav a[href="/admin"]');
    await expect(adminLink).not.toBeVisible();
  });

  test('admin email can navigate to admin page via sidebar link', async ({ page }) => {
    await page.route('**/api/me', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ email: ADMIN_EMAIL, is_admin: true }) }),
    );
    await mockAdminApi(page);

    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });

    const adminLink = page.locator('nav a[href="/admin"]');
    await expect(adminLink).toBeVisible();
    await adminLink.click();
    await page.waitForURL('**/admin');

    // Should go straight to the routing panel, no token gate
    await expect(page.getByTestId('admin-routes-table')).toBeVisible();
  });

  test('sidebar nav count is 11 for non-admin (no Admin link)', async ({ page }) => {
    await page.route('**/api/me', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ email: null, is_admin: false }) }),
    );

    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });

    // Wait for nav to fully render before counting
    await expect(page.locator('nav a[href="/help"]')).toBeVisible();
    const nav = page.locator('nav a');
    await expect(nav).toHaveCount(11);
  });

  test('sidebar nav count is 12 for admin (includes Admin link)', async ({ page }) => {
    await page.route('**/api/me', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ email: ADMIN_EMAIL, is_admin: true }) }),
    );

    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });

    // Wait for admin link to appear before counting
    await expect(page.locator('nav a[href="/admin"]')).toBeVisible();
    const nav = page.locator('nav a');
    await expect(nav).toHaveCount(12);
  });
});
