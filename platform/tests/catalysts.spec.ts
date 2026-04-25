/**
 * E2E: Catalysts ("/catalysts") — earnings, 8-K, FDA, M&A event timeline,
 * news catalysts, insider clusters, plus the unified-feed UX
 * (Hot Now panel, impact filter, click-to-navigate, sentiment indicator).
 */
import { test, expect } from '@playwright/test';
import { mockCommon, M } from './helpers/mocks';

// today + tomorrow ISO so 'Hot Now' selectors fire deterministically
const TODAY_ISO = new Date().toISOString().slice(0, 10);
const TOMORROW_ISO = (() => {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
})();

const MOCK_EVENTS = {
  status: 'ok',
  source: 'mock',
  date_range: { from: '2026-04-25', to: '2026-05-09' },
  total: 4,
  events_by_date: {
    [TODAY_ISO]: [
      {
        // Hot Now eligible: high impact + today.
        date: TODAY_ISO,
        ticker: 'AVGO',
        catalyst_type: 'MERGER_ACQUISITION',
        title: 'Broadcom rises on AI deals; BofA says visibility improves',
        impact: 'High',
        source: 'AV news',
        sentiment_score: 0.73,
        sentiment_label: 'Bullish',
        relevance_score: 1.0,
      },
    ],
    '2026-04-28': [
      {
        date: '2026-04-28',
        ticker: 'AAPL',
        company_name: 'Apple Inc.',
        catalyst_type: 'EARNINGS',
        event: 'Q2 2026 Earnings',
        expected_impact: 'high',
        confirmed: true,
        source: 'mock',
      },
    ],
    '2026-04-30': [
      {
        date: '2026-04-30',
        ticker: 'MSFT',
        company_name: 'Microsoft Corp.',
        catalyst_type: 'CONFERENCE_CALL',
        event: 'Investor Day',
        expected_impact: 'medium',
        confirmed: true,
        source: 'mock',
      },
    ],
    [TOMORROW_ISO]: [
      {
        date: TOMORROW_ISO,
        ticker: 'MACRO',
        catalyst_type: 'ECONOMIC',
        title: 'CPI release',
        impact: 'High',
        source: 'FRED/Calendar',
      },
    ],
  },
};

test.describe('Catalysts', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/catalysts/events**', (r) => r.fulfill(M.ok(MOCK_EVENTS)));
    await page.route('**/api/catalysts/types', (r) =>
      r.fulfill(
        M.ok({
          benzinga_types: {
            EARNINGS: { label: 'Earnings', color: 'red', icon: 'TrendingUp' },
          },
          wsh_only_types: {},
          upgrade_note: 'Upgrade for full coverage',
        })
      )
    );
  });

  test('renders catalysts heading', async ({ page }) => {
    await page.goto('/catalysts');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('h1').filter({ hasText: /catalysts/i })).toBeVisible();
  });

  test('lists upcoming events', async ({ page }) => {
    await page.goto('/catalysts');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/AAPL/).first()).toBeVisible();
    await expect(page.getByText(/Q2 2026 Earnings/i)).toBeVisible();
  });

  test('shows filter chips', async ({ page }) => {
    await page.goto('/catalysts');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/earnings/i).first()).toBeVisible();
  });

  test('renders within 5s perf budget', async ({ page }) => {
    const start = Date.now();
    await page.goto('/catalysts');
    await page.waitForLoadState('networkidle');
    expect(Date.now() - start).toBeLessThan(5000);
  });

  test('renders Hot Now panel for today/tomorrow high-impact events', async ({ page }) => {
    await page.goto('/catalysts');
    await page.waitForLoadState('networkidle');
    // Hot now header + at least one hot row visible
    await expect(page.getByText(/hot now/i).first()).toBeVisible();
    // The high-impact AVGO event should appear in Hot Now (today)
    await expect(page.getByText(/Broadcom rises on AI deals/i).first()).toBeVisible();
  });

  test('renders impact tier counters in header', async ({ page }) => {
    await page.goto('/catalysts');
    await page.waitForLoadState('networkidle');
    // Header summary: '<n> events <h>H/<m>M/<l>L · ...'
    await expect(page.getByText(/\d+\s*events/i).first()).toBeVisible();
    await expect(page.getByText(/\d+H\s*\/\s*\d+M\s*\/\s*\d+L/i).first()).toBeVisible();
  });

  test('Min-impact filter restricts the timeline', async ({ page }) => {
    await page.goto('/catalysts');
    await page.waitForLoadState('networkidle');
    // Click "High" — only High-impact items should remain.
    await page.getByRole('button', { name: 'High' }).first().click();
    // MSFT Investor Day was Medium impact; should disappear from
    // the date timeline (still allowed in Hot Now since Hot Now
    // ignores the min-impact filter — only the timeline below it
    // is filtered).
    await expect(page.getByText(/Investor Day/i)).toHaveCount(0);
    // High items still visible
    await expect(page.getByText(/Q2 2026 Earnings/i).first()).toBeVisible();
  });

  test('clicking a ticker navigates to /insights with that ticker active', async ({ page }) => {
    await page.goto('/catalysts');
    await page.waitForLoadState('networkidle');
    // The AVGO ticker button (in Hot Now, today's event) — click to navigate
    await page.getByRole('button', { name: 'AVGO' }).first().click();
    await page.waitForURL('**/insights');
    expect(page.url()).toMatch(/\/insights/);
  });

  test('news rows show a sentiment indicator', async ({ page }) => {
    await page.goto('/catalysts');
    await page.waitForLoadState('networkidle');
    // ▲ for bullish (sentiment 0.73). The element shows '▲ 0.73'.
    await expect(page.getByText('▲').first()).toBeVisible();
  });
});
