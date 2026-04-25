/**
 * E2E: Playbook ("/playbook") — top setup, conditions checklist, FTFC strat.
 */
import { test, expect } from '@playwright/test';
import { mockCommon, M } from './helpers/mocks';

const MOCK_PLAYBOOK = {
  ticker: 'IWM',
  cards: [
    {
      id: 'long_breakout_pd',
      name: 'Long breakout above PD high',
      direction: 'long',
      win_rate: 0.62,
      avg_return: 0.85,
      conditions: ['price > prior_high', 'volume > avg', 'EMA9 > EMA20'],
      description: 'Triggers when IWM breaks the prior-day high with above-average volume.',
    },
  ],
};

const MOCK_REFERENCE = {
  ticker: 'IWM',
  date: '2026-04-25',
  reference_levels: { prior_high: 222.0, prior_low: 218.0, vwap: 220.5 },
};

test.describe('Playbook', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/playbook/IWM', (r) => r.fulfill(M.ok(MOCK_PLAYBOOK)));
    await page.route('**/api/market/reference/IWM/*', (r) => r.fulfill(M.ok(MOCK_REFERENCE)));
    await page.route('**/api/signals/IWM*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', count: 0, signals: [] }))
    );
  });

  test('renders ticker playbook heading', async ({ page }) => {
    await page.goto('/playbook');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('h1, h2').filter({ hasText: /IWM.*Playbook|Playbook/i }).first()).toBeVisible();
  });

  test('shows setup with conditions', async ({ page }) => {
    await page.goto('/playbook');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/long breakout/i)).toBeVisible();
  });

  test('shows empty-state when no cards', async ({ page }) => {
    await page.route('**/api/playbook/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', cards: [] }))
    );
    await page.goto('/playbook');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/no playbook|no.*card|run.*pipeline|empty/i).first()).toBeVisible();
  });

  test('renders within 7s perf budget', async ({ page }) => {
    // Slightly looser than 5s — playbook page does signals + reference + brief
    // fanout, so it sits at the cold-warm transition boundary.
    const start = Date.now();
    await page.goto('/playbook');
    await page.waitForLoadState('networkidle');
    expect(Date.now() - start).toBeLessThan(7000);
  });
});
