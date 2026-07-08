/**
 * Navigation smoke tests — every route in the AppShell should load without
 * throwing, render its page heading, and not produce console errors.
 *
 * Runs against live dev server (port 5173) + FastAPI backend (port 8000).
 */
import { test, expect, Page } from '@playwright/test';
import { mockCommon, M } from './helpers/mocks';

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

  test('top nav renders inline tabs + Market/Learn/Support dropdowns for non-admin', async ({ page }) => {
    // Without IAP, /api/me returns null → Admin entry hidden from Support
    await page.route('**/api/me', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ email: null }) })
    );
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
    // Inline: Dashboard + INTELLIGENCE (2); Market/Learn/Support are dropdowns
    await expect(page.locator('nav a[href="/catalysts"]')).toBeVisible();
    await expect(page.locator('nav a')).toHaveCount(3);

    // Market dropdown: Live, Charts, Options Flow, Signals
    await page.getByTestId('nav-menu-market').click();
    await expect(page.locator('a[href="/live"]')).toBeVisible();
    await expect(page.locator('a[href="/charts"]')).toBeVisible();
    await expect(page.locator('a[href="/options"]')).toBeVisible();
    await expect(page.locator('a[href="/signals"]')).toBeVisible();

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

  test('market session badge is truthful — CLOSED when the market is closed', async ({ page }) => {
    await page.route('**/api/live/status', (route) =>
      route.fulfill({
        status: 200,
        body: JSON.stringify({
          is_open: false,
          session: 'closed',
          next_open: '2026-07-07T09:30:00-04:00',
          current_time_et: '2026-07-06T12:00:00-04:00',
        }),
      })
    );
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
    const badge = page.getByTestId('nav-menu-market').getByTestId('market-session-badge');
    await expect(badge).toHaveText('CLOSED');
    await expect(badge).not.toHaveClass(/live/);
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

    // Options Flow lives in the Market dropdown
    await page.getByTestId('nav-menu-market').click();
    await page.click('a[href="/options"]');
    await page.waitForURL('**/options');
    expect(page.url()).toContain('/options');
    await expect(page.getByTestId('nav-menu-market')).toHaveClass(/active/);

    // Playbook lives in the Learn dropdown
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

// ── SwingMode toolbar (options page) — Refresh must refetch the live grid,
// Glossary must navigate to /help. The default ticker (IWM, from tickerStore)
// and default Heatseeker/Swing mode drive the /api/options/IWM/grid live path.
test.describe('SwingMode toolbar', () => {
  const MOCK_DATES = { ticker: 'IWM', dates: ['2026-04-25', '2026-04-24'] };
  const MOCK_LEVELS = {
    ticker: 'IWM',
    snapshot_date: '2026-04-25',
    spot: { price: 220, method: 'parity', note: '' },
    gamma_balance: 220,
    gamma_flip: 220,
    regime: 'positive_gamma',
    total_gex: 1_000_000,
    levels: [],
    kings: [],
    gates: [],
    gamma_balance_levels: [],
    window_pct: 6,
    warnings: [],
    chain_size: 0,
  };
  const MOCK_GRID = {
    ticker: 'IWM',
    snapshot_date: '2026-04-25',
    snapshot_ts: null,
    data_source: 'realtime',
    spot: { price: 220, method: 'parity', note: '' },
    gamma_balance: 220,
    gamma_flip: 220,
    regime: 'positive_gamma',
    total_gex: 1_000_000,
    total_vex: 0,
    cells: [],
    expirations: [],
    strikes: [],
    window_pct: 6,
    warnings: [],
  };

  test('Refresh refetches the grid and Glossary navigates to /help', async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/options/dates/IWM', (r) => r.fulfill(M.ok(MOCK_DATES)));
    await page.route('**/api/options/IWM/*/levels', (r) => r.fulfill(M.ok(MOCK_LEVELS)));

    // Intercept BEFORE the first navigation so the counter sees both the
    // initial mount fetch and the Refresh-triggered refetch.
    let gridCalls = 0;
    await page.route('**/api/options/**/grid**', (route) => {
      gridCalls += 1;
      route.fulfill(M.ok(MOCK_GRID));
    });

    await page.goto('/options');
    await page.waitForLoadState('networkidle');

    const before = gridCalls;
    expect(before).toBeGreaterThan(0);

    await page.getByRole('button', { name: 'Refresh' }).click();
    await page.waitForTimeout(500);
    expect(gridCalls).toBeGreaterThan(before);

    await page.getByRole('button', { name: 'Glossary' }).click();
    await page.waitForURL('**/help');
  });
});
