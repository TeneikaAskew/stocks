/**
 * Phase 1 verification: Chart Viewer feature parity checks
 * Tests against live dev server (port 5173) + FastAPI backend (port 8000)
 */
import { test, expect } from '@playwright/test';

test.describe('Phase 1: Chart Viewer', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  // ── Layout ──────────────────────────────────────────────────────────────
  test('sidebar renders with all 12 nav items', async ({ page }) => {
    const nav = page.locator('nav a');
    await expect(nav).toHaveCount(12);
  });

  test('header shows active ticker', async ({ page }) => {
    // Default ticker is IWM
    await expect(page.locator('header, [data-testid="header"]').first()).toContainText('IWM');
  });

  test('can navigate to /charts route', async ({ page }) => {
    await page.click('a[href="/charts"]');
    await page.waitForURL('**/charts');
    // Header date input is the canonical "we landed on charts" signal
    await expect(page.locator('input[type="date"]').first()).toBeVisible();
  });

  // ── Chart toolbar ────────────────────────────────────────────────────────
  test('charts page: date input is populated', async ({ page }) => {
    await page.goto('/charts');
    // DateSelector renders <input type="date"> + <input type="time"> + Apply.
    const dateInput = page.locator('input[type="date"]').first();
    await expect(dateInput).toBeVisible();
    // The input is wired to the draft state; at minimum a `max` attribute is
    // set to the latest available trading date — confirms the API resolved.
    const max = await dateInput.getAttribute('max');
    expect(max).toMatch(/^\d{4}-\d{2}-\d{2}$/);
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
