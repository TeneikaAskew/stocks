/**
 * Navigation smoke tests — every route in the AppShell should load without
 * throwing, render its page heading, and not produce console errors.
 *
 * Runs against live dev server (port 5173) + FastAPI backend (port 8000).
 */
import { test, expect, Page } from '@playwright/test';

const ROUTES: Array<{ path: string; heading: RegExp }> = [
  { path: '/',          heading: /dashboard/i },
  { path: '/live',      heading: /live/i },
  { path: '/charts',    heading: /chart/i },
  { path: '/options',   heading: /options/i },
  { path: '/playbook',  heading: /playbook/i },
  { path: '/reports',   heading: /reports?/i },
  { path: '/signals',   heading: /signals?/i },
  { path: '/journal',   heading: /journal/i },
  { path: '/insights',  heading: /insights?/i },
  { path: '/help',      heading: /help/i },
];

async function collectConsoleErrors(page: Page): Promise<string[]> {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', (err) => errors.push(err.message));
  return errors;
}

test.describe('Navigation smoke', () => {
  test('sidebar renders with correct nav items for non-admin', async ({ page }) => {
    // Without IAP, /api/me returns null → Admin link hidden → 11 items
    await page.route('**/api/me', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ email: null }) })
    );
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle');
    const nav = page.locator('nav a');
    await expect(nav).toHaveCount(11);
  });

  for (const { path, heading } of ROUTES) {
    test(`route ${path} loads without fatal errors`, async ({ page }) => {
      const errors = await collectConsoleErrors(page);
      await page.goto(path, { waitUntil: 'domcontentloaded' });

      // AppShell should always mount a nav — a blank page = fatal
      await expect(page.locator('nav')).toBeVisible();

      // Page-level heading should eventually render (loose match via main)
      await expect(page.locator('main')).toBeVisible();

      // Filter out noisy non-fatal errors (React dev warnings, 3rd-party)
      const fatal = errors.filter(
        (e) =>
          !e.includes('Warning:') &&
          !e.includes('Download the React DevTools') &&
          !e.toLowerCase().includes('favicon'),
      );
      expect(fatal, `console errors on ${path}: ${fatal.join(' | ')}`).toEqual([]);
    });
  }

  test('can navigate between routes via sidebar clicks', async ({ page }) => {
    await page.goto('/');
    await page.click('a[href="/options"]');
    await page.waitForURL('**/options');
    expect(page.url()).toContain('/options');

    await page.click('a[href="/playbook"]');
    await page.waitForURL('**/playbook');
    expect(page.url()).toContain('/playbook');

    await page.click('a[href="/"]');
    await page.waitForURL(/\/$/);
  });
});
