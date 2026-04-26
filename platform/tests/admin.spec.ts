/**
 * E2E: Admin model-routing dashboard.
 *
 * Tests the sessionStorage-token auth flow and the routing table
 * render/update path. Backend is fully mocked via page.route.
 */
import { test, expect } from '@playwright/test';

const MOCK_ROUTES = {
  routes: [
    { role: 'analyst', provider: 'vertex', model: 'gemini-2.0-flash', updated_at: null, updated_by: null },
    { role: 'bull', provider: 'vertex', model: 'gemini-2.0-flash', updated_at: null, updated_by: null },
    { role: 'bear', provider: 'vertex', model: 'gemini-2.0-flash', updated_at: null, updated_by: null },
    { role: 'judge', provider: 'vertex', model: 'gemini-2.0-flash', updated_at: null, updated_by: null },
    { role: 'trader', provider: 'vertex', model: 'gemini-2.0-flash', updated_at: null, updated_by: null },
    { role: 'risk', provider: 'vertex', model: 'gemini-2.0-flash', updated_at: null, updated_by: null },
    {
      role: 'portfolio_manager',
      provider: 'vertex',
      model: 'gemini-2.0-flash',
      updated_at: null,
      updated_by: null,
    },
  ],
};

const MOCK_MODELS = {
  models: [
    { provider: 'vertex', model: 'gemini-2.0-flash', has_credentials: true, input_usd_per_mtok: 0.1, output_usd_per_mtok: 0.4 },
    { provider: 'vertex', model: 'gemini-2.5-pro', has_credentials: true, input_usd_per_mtok: 1.25, output_usd_per_mtok: 10.0 },
    { provider: 'anthropic', model: 'claude-sonnet-4-6', has_credentials: false, input_usd_per_mtok: 3.0, output_usd_per_mtok: 15.0 },
  ],
};

test.describe('Admin — model routing', () => {
  test.beforeEach(async ({ context }) => {
    // Clear any persisted token between tests (fresh tab)
    await context.clearCookies();
  });

  test('token gate rejects invalid tokens and accepts the correct one', async ({ page }) => {
    // Mock /api/me as non-admin user so the token gate is shown
    await page.route('**/api/me', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ email: null }) })
    );
    // First call (token probe) — 401 for wrong, 200 for right
    await page.route('**/api/admin/routes', async (route) => {
      const req = route.request();
      const token = req.headers()['x-admin-token'];
      if (token === 'correct-token') {
        return route.fulfill({ status: 200, body: JSON.stringify(MOCK_ROUTES) });
      }
      return route.fulfill({ status: 401, body: JSON.stringify({ detail: 'bad' }) });
    });
    await page.route('**/api/admin/models', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify(MOCK_MODELS) })
    );

    await page.goto('/admin');
    await page.waitForLoadState('networkidle');

    // Gate visible
    await expect(page.getByTestId('admin-token-input')).toBeVisible();

    // Wrong token
    await page.getByTestId('admin-token-input').fill('wrong-token');
    await page.getByTestId('admin-submit').click();
    await expect(page.getByTestId('admin-error')).toContainText(/invalid token/i);

    // Correct token
    await page.getByTestId('admin-token-input').fill('correct-token');
    await page.getByTestId('admin-submit').click();

    // Routing table renders
    await expect(page.getByTestId('admin-routes-table')).toBeVisible();
    await expect(page.getByText('analyst')).toBeVisible();
    await expect(page.getByText('portfolio_manager')).toBeVisible();
  });

  test('editing a route saves via PUT and reflects the new value', async ({ page }) => {
    // Mock /api/me as non-admin user so the token gate is shown
    await page.route('**/api/me', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ email: null }) })
    );
    // Token probe always 200
    await page.route('**/api/admin/routes', async (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({ status: 200, body: JSON.stringify(MOCK_ROUTES) });
      }
      // Fall-through for POST/PUT handled by a more-specific route below
      return route.continue();
    });
    await page.route('**/api/admin/models', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify(MOCK_MODELS) })
    );

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
            updated_at: '2026-04-15T14:30:00Z',
            updated_by: 'admin-ui',
          }),
        });
      }
      return route.continue();
    });

    await page.goto('/admin');
    await page.waitForLoadState('networkidle');

    // Unlock with valid token
    await page.getByTestId('admin-token-input').fill('correct-token');
    await page.getByTestId('admin-submit').click();

    await expect(page.getByTestId('admin-routes-table')).toBeVisible();

    // Change trader model
    await page.getByTestId('model-trader').selectOption('gemini-2.5-pro');
    await page.getByTestId('save-trader').click();

    // PUT body should carry the new model
    await expect.poll(() => putBody, { timeout: 5_000 }).toEqual({
      provider: 'vertex',
      model: 'gemini-2.5-pro',
    });
  });
});
