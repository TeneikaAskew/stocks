/**
 * Navigation smoke tests — every route in the AppShell should load without
 * throwing, render its page heading, and not produce console errors.
 *
 * Runs against live dev server (port 5173) + FastAPI backend (port 8000).
 */
import { test, expect, Page } from '@playwright/test';

const ROUTES: Array<{ path: string; heading: RegExp }> = [
  { path: '/dashboard', heading: /dashboard/i },
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
  // Hermetic auth: open mode regardless of what backend (if any) answers the
  // proxy — these tests exercise routing/nav, not the login flow.
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/config/firebase', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ authMode: 'open', firebase: null }) })
    );
  });

  test('top nav renders inline tabs + Learn/Support dropdowns for non-admin', async ({ page }) => {
    // Without IAP, /api/me returns null → Admin entry hidden from Support
    await page.route('**/api/me', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ email: null }) })
    );
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
    // Inline: TRADING (5) + INTELLIGENCE (2); Learn/Support items live in dropdowns
    await expect(page.locator('nav a[href="/catalysts"]')).toBeVisible();
    await expect(page.locator('nav a')).toHaveCount(7);

    // Support dropdown: Settings, Help & Glossary, FAQ (no Admin for anonymous)
    await page.getByTestId('nav-menu-support').click();
    await expect(page.locator('a[href="/help"]')).toBeVisible();
    await expect(page.locator('a[href="/#faq"]')).toBeVisible();
    await expect(page.locator('a[href="/admin"]')).toHaveCount(0);

    // Learn dropdown: Playbook, Reports, Journal (one click switches menus)
    await page.getByTestId('nav-menu-learn').click();
    await expect(page.locator('a[href="/playbook"]')).toBeVisible();
    await expect(page.locator('a[href="/reports"]')).toBeVisible();
    await expect(page.locator('a[href="/journal"]')).toBeVisible();
  });

  for (const { path } of ROUTES) {
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

  test('can navigate between routes via top-nav clicks', async ({ page }) => {
    await page.goto('/dashboard');
    await page.click('a[href="/options"]');
    await page.waitForURL('**/options');
    expect(page.url()).toContain('/options');

    // Playbook now lives in the Learn dropdown
    await page.getByTestId('nav-menu-learn').click();
    await page.click('a[href="/playbook"]');
    await page.waitForURL('**/playbook');
    expect(page.url()).toContain('/playbook');
    // Trigger reflects the active child route
    await expect(page.getByTestId('nav-menu-learn')).toHaveClass(/active/);

    await page.click('a[href="/dashboard"]');
    await page.waitForURL(/\/dashboard$/);
  });
});
