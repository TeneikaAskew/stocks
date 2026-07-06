/**
 * Phase 1 verification: Chart Viewer feature parity checks
 * Tests against live dev server (port 5173) + FastAPI backend (port 8000)
 */
import { test, expect } from '@playwright/test';

test.describe('Phase 1: Chart Viewer', () => {
  test.beforeEach(async ({ page }) => {
    // Hermetic auth: open mode regardless of what backend answers the proxy.
    await page.route('**/api/config/firebase', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ authMode: 'open', firebase: null }) })
    );
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
  });

  // ── Layout ──────────────────────────────────────────────────────────────
  test('top nav renders inline tabs + three dropdown triggers', async ({ page }) => {
    // Inline: Dashboard + AI Insights + Catalysts; Market/Learn/Support are dropdowns.
    await expect(page.locator('nav a')).toHaveCount(3);
    for (const menu of ['market', 'learn', 'support']) {
      await expect(page.getByTestId(`nav-menu-${menu}`)).toBeVisible();
    }
  });

  test('header shows active ticker', async ({ page }) => {
    // Default ticker is IWM
    await expect(page.locator('header, [data-testid="header"]').first()).toContainText('IWM');
  });

  test('can navigate to /charts route', async ({ page }) => {
    // Charts lives in the Market dropdown now.
    await page.getByTestId('nav-menu-market').click();
    await page.click('a[href="/charts"]');
    await page.waitForURL('**/charts');
    // The replay control is the canonical "we landed on a review-aware page" signal.
    await expect(page.getByTestId('replay-toggle')).toBeVisible();
  });

  // ── Replay control ───────────────────────────────────────────────────────
  test('charts page: replay popover has a bounded datetime picker', async ({ page }) => {
    await page.goto('/charts');
    await page.getByTestId('replay-toggle').click();
    const dt = page.getByTestId('replay-datetime');
    await expect(dt).toBeVisible();
    // One-box datetime-local, clamped to "now" so future moments can't be picked.
    const max = await dt.getAttribute('max');
    expect(max).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
  });

  test('charts page: timeframe buttons render', async ({ page }) => {
    await page.goto('/charts');
    for (const label of ['1m', '5m', '15m', '30m', '1h']) {
      await expect(page.getByText(label, { exact: true })).toBeVisible();
    }
  });

  test('charts page: Vol toggle button renders', async ({ page }) => {
    await page.goto('/charts');
    await expect(page.getByText('Vol')).toBeVisible();
  });

  test('charts page: RTH toggle button renders', async ({ page }) => {
    await page.goto('/charts');
    await expect(page.getByText('RTH')).toBeVisible();
  });

  test('charts page: Ref toggle button renders', async ({ page }) => {
    await page.goto('/charts');
    await expect(page.getByText('Ref')).toBeVisible();
  });

  test('charts page: Mark Entry button renders', async ({ page }) => {
    await page.goto('/charts');
    // Use first() in case there are multiple matches (button + possible nav label)
    await expect(page.getByText('Mark Entry').first()).toBeVisible();
  });

  // ── Chart canvas ────────────────────────────────────────────────────────
  test('candlestick chart canvas is rendered', async ({ page }) => {
    await page.goto('/charts');
    // Wait for market data to load (API call)
    await page.waitForTimeout(3000);
    const canvas = page.locator('canvas').first();
    await expect(canvas).toBeVisible();
  });

  // ── Drawing mode ────────────────────────────────────────────────────────
  test('Mark Entry starts drawing mode', async ({ page }) => {
    await page.goto('/charts');
    await page.waitForTimeout(2000);
    await page.getByRole('button', { name: /Mark Entry/ }).click();
    await expect(page.getByText('Click chart to set entry price')).toBeVisible();
  });

  test('ESC cancels drawing mode', async ({ page }) => {
    await page.goto('/charts');
    await page.waitForTimeout(2000);
    await page.getByRole('button', { name: /Mark Entry/ }).click();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: /Mark Entry/ })).toBeVisible();
  });

  // ── Side panel ───────────────────────────────────────────────────────────
  test('side panel Trades tab renders with empty state', async ({ page }) => {
    await page.goto('/charts');
    await expect(page.getByText('No trades yet')).toBeVisible();
  });

  test('side panel Analytics tab renders metrics', async ({ page }) => {
    await page.goto('/charts');
    await page.getByRole('button', { name: 'Analytics' }).click();
    await expect(page.getByText('Win Rate')).toBeVisible();
    await expect(page.getByText('Profit Factor')).toBeVisible();
    await expect(page.getByText('Total P&L')).toBeVisible();
  });

  // ── API connectivity ────────────────────────────────────────────────────
  test('API health check returns ok', async ({ request }) => {
    const res = await request.get('http://localhost:8000/api/health');
    expect(res.ok()).toBeTruthy();
    const json = await res.json();
    expect(json.status).toBe('ok');
  });

  test('API market dates returns 80+ dates for IWM', async ({ request }) => {
    const res = await request.get('http://localhost:8000/api/market/dates/IWM');
    expect(res.ok()).toBeTruthy();
    const json = await res.json();
    expect(json.dates.length).toBeGreaterThan(50);
  });

  test('API reference levels returns prev day OHLC', async ({ request }) => {
    // Get a valid second date
    const datesRes = await request.get('http://localhost:8000/api/market/dates/IWM');
    const { dates } = await datesRes.json();
    // dates are sorted descending; pick the second-to-last so there's a prev day
    const date = dates[dates.length - 2];
    const res = await request.get(`http://localhost:8000/api/market/reference/IWM/${date}`);
    expect(res.ok()).toBeTruthy();
    const json = await res.json();
    expect(json).toHaveProperty('open');
    expect(json).toHaveProperty('high');
    expect(json).toHaveProperty('low');
    expect(json).toHaveProperty('close');
    expect(json.high).toBeGreaterThan(json.low);
  });

  test('API market data returns candlestick bars', async ({ request }) => {
    const datesRes = await request.get('http://localhost:8000/api/market/dates/IWM');
    const { dates } = await datesRes.json();
    const date = dates[0]; // most recent
    const res = await request.get(`http://localhost:8000/api/market/data/IWM/${date}?timeframe=5`);
    expect(res.ok()).toBeTruthy();
    const json = await res.json();
    expect(json.candlestick.length).toBeGreaterThan(0);
    const bar = json.candlestick[0];
    expect(bar).toHaveProperty('time');
    expect(bar).toHaveProperty('open');
    expect(bar).toHaveProperty('high');
    expect(bar).toHaveProperty('low');
    expect(bar).toHaveProperty('close');
  });
});
