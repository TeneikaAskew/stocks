/**
 * E2E: Reports ("/reports") — phase analysis reports list and viewer.
 */
import { test, expect } from '@playwright/test';
import { mockCommon, M } from './helpers/mocks';

const MOCK_REPORT_LIST = {
  ticker: 'IWM',
  reports: [
    { phase: 'phase1', filename: 'phase1_iwm.md', path: 'reports/phase1_iwm.md' },
    { phase: 'phase6_playbook', filename: 'phase6_playbook_iwm.md', path: 'reports/phase6_playbook_iwm.md' },
  ],
};

const MOCK_REPORT_BODY = `# Phase 1: IWM Backtest

## Summary
Sharpe 11.05 on 1m+30m timeframe combo over 2015-2026.

## Trades
- Total: 1,234
- Win rate: 62%
- Avg return: 0.85%
`;

test.describe('Reports', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/reports/list/IWM', (r) => r.fulfill(M.ok(MOCK_REPORT_LIST)));
    await page.route('**/api/reports/IWM/*', (r) =>
      r.fulfill({ status: 200, contentType: 'text/plain', body: MOCK_REPORT_BODY })
    );
  });

  test('renders reports heading', async ({ page }) => {
    await page.goto('/reports');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/reports/i).first()).toBeVisible();
  });

  test('lists available phase reports', async ({ page }) => {
    await page.goto('/reports');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/phase1|phase 1/i).first()).toBeVisible();
  });

  test('renders within 5s perf budget', async ({ page }) => {
    const start = Date.now();
    await page.goto('/reports');
    await page.waitForLoadState('networkidle');
    expect(Date.now() - start).toBeLessThan(5000);
  });
});
