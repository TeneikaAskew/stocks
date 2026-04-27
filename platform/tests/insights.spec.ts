/**
 * E2E: Structured AI Insights page.
 *
 * All backend calls are mocked via page.route so this spec doesn't
 * require Cloud SQL or the agent pipeline to be running. The mocks
 * cover three flows:
 *   - existing report loads and renders all the cards
 *   - empty state shows the CTA when /report returns 404
 *   - refresh runs the queued -> running -> done polling loop and
 *     eventually reloads the report
 */
import { test, expect } from '@playwright/test';

const MOCK_REPORT = {
  ticker: 'IWM',
  as_of: '2026-04-15T14:30:00Z',
  report: {
    ticker: 'IWM',
    as_of: '2026-04-15T14:30:00Z',
    direction: 'long',
    conviction: 'high',
    thesis: 'Breakout above prior-day high with FTFC bullish and supportive volume.',
    entry_zone: { low: 220.0, high: 221.5 },
    stop: 218.0,
    targets: [224.0, 228.0],
    invalidation: 'Close below 218 on the 1-hour chart.',
    time_horizon: 'swing',
    key_levels: { support: 218.0, resistance: 224.0, pivot: 220.0 },
    strat_status: {
      last_candle: '2U',
      in_force_combo: '212_bull_reversal',
      ftfc_score: 0.72,
      ftfc_direction: 'bullish',
      trigger_high: 221.0,
      trigger_low: 218.5,
    },
    catalysts: [
      { name: 'CPI', date: '2026-04-22', impact: 'high', kind: 'economic' },
    ],
    bull_case: 'Volume + FTFC + trigger break aligned.',
    bear_case: 'Tight stop, CPI in window.',
    risk_flags: [
      { persona: 'conservative', severity: 'warn', message: 'CPI release within holding period.' },
    ],
    persona_plans: [
      {
        persona: 'aggressive',
        entry_zone: { low: 220.0, high: 222.5 },
        stop: 215.0,
        targets: [228.0, 234.0, 240.0],
        position_size_pct: 1.5,
        rationale: 'Wider stop, extended targets on high-conviction setup.',
      },
      {
        persona: 'neutral',
        entry_zone: { low: 220.0, high: 221.5 },
        stop: 218.0,
        targets: [223.0, 226.0, 229.0],
        position_size_pct: 1.0,
        rationale: '~1 ATR stop with 1R/2R/3R targets.',
      },
      {
        persona: 'conservative',
        entry_zone: { low: 220.5, high: 221.0 },
        stop: 219.0,
        targets: [222.5, 224.0],
        position_size_pct: 0.4,
        rationale: 'Reduced size + tight stop into CPI window.',
      },
    ],
    supporting_signals: [
      { alert_ts: '2026-04-15T14:30:00Z', direction: 'CALL', strength: 'strong', score: 4.5 },
    ],
    similar_past_trades: [],
    confidence_score: 0.78,
    failed_sections: [],
    model_versions: { trader: 'vertex:gemini-2.0-flash' },
    run_cost_usd: 0.0134,
    run_latency_ms: 12500,
  },
  model_versions: { trader: 'vertex:gemini-2.0-flash' },
  cost_usd: 0.0134,
  latency_ms: 12500,
};

test.describe('AI Insights (structured)', () => {
  test('renders a full report with all cards', async ({ page }) => {
    await page.route('**/api/insights/report/IWM', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify(MOCK_REPORT) })
    );
    await page.route('**/api/insights/report/IWM/history**', (route) =>
      route.fulfill({
        status: 200,
        body: JSON.stringify({ ticker: 'IWM', count: 0, reports: [] }),
      })
    );
    await page.goto('/insights');
    await page.waitForLoadState('networkidle');

    // Header: ticker + direction badge
    await expect(page.locator('h2').filter({ hasText: 'IWM' })).toBeVisible();
    await expect(page.getByText(/long · high/i)).toBeVisible();

    // Thesis
    await expect(page.getByText(/breakout above prior-day high/i)).toBeVisible();

    // Entry zone
    await expect(page.getByText('220.00 – 221.50')).toBeVisible();

    // Bull / bear cards
    await expect(page.getByText('Bull Case')).toBeVisible();
    await expect(page.getByText('Bear Case')).toBeVisible();
    await expect(page.getByText('Volume + FTFC + trigger break aligned.')).toBeVisible();

    // Strat
    await expect(page.getByText('212_bull_reversal')).toBeVisible();

    // Risk flag
    await expect(page.getByText(/CPI release within holding period/)).toBeVisible();

    // Persona plans card with all three personas
    await expect(page.getByText('Persona Plans')).toBeVisible();
    await expect(page.getByText('Aggressive')).toBeVisible();
    await expect(page.getByText('Neutral')).toBeVisible();
    await expect(page.getByText(/^Conservative$/)).toBeVisible();
    // Aggressive plan numbers
    await expect(page.getByText('$220.00 – $222.50')).toBeVisible();
    await expect(page.getByText('1.50× normal')).toBeVisible();
    await expect(page.getByText(/Wider stop, extended targets/)).toBeVisible();

    // Footer model versions line
    await expect(page.getByText(/trader: vertex:gemini-2.0-flash/)).toBeVisible();
  });

  test('shows empty-state CTA when no report exists', async ({ page }) => {
    await page.route('**/api/insights/report/IWM', (route) =>
      route.fulfill({ status: 404, body: JSON.stringify({ detail: 'not found' }) })
    );
    await page.route('**/api/insights/report/IWM/history**', (route) =>
      route.fulfill({
        status: 200,
        body: JSON.stringify({ ticker: 'IWM', count: 0, reports: [] }),
      })
    );
    await page.goto('/insights');
    await page.waitForLoadState('networkidle');

    await expect(page.getByText(/no report yet/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /generate report/i })).toBeVisible();
  });

  test('refresh runs the queued -> running -> done polling loop', async ({ page }) => {
    let pollCount = 0;
    // First call returns 404, after refresh returns real report
    let reportFetches = 0;
    await page.route('**/api/insights/report/IWM', (route) => {
      reportFetches += 1;
      if (reportFetches === 1) {
        return route.fulfill({ status: 404, body: JSON.stringify({ detail: 'nf' }) });
      }
      return route.fulfill({ status: 200, body: JSON.stringify(MOCK_REPORT) });
    });
    await page.route('**/api/insights/report/IWM/history**', (route) =>
      route.fulfill({
        status: 200,
        body: JSON.stringify({ ticker: 'IWM', count: 0, reports: [] }),
      })
    );
    await page.route('**/api/insights/report/IWM/refresh', (route) =>
      route.fulfill({
        status: 200,
        body: JSON.stringify({
          run_id: '00000000-0000-0000-0000-000000000001',
          ticker: 'IWM',
          status: 'queued',
        }),
      })
    );
    await page.route('**/api/insights/runs/**', (route) => {
      pollCount += 1;
      const status = pollCount >= 2 ? 'done' : 'running';
      return route.fulfill({
        status: 200,
        body: JSON.stringify({
          id: '00000000-0000-0000-0000-000000000001',
          ticker: 'IWM',
          status,
          trigger: 'local_dev',
          started_at: '2026-04-15T14:30:05Z',
          finished_at: status === 'done' ? '2026-04-15T14:30:17Z' : null,
          error: null,
          report_id: status === 'done' ? 'abc' : null,
        }),
      });
    });

    await page.goto('/insights');
    await page.waitForLoadState('networkidle');

    // Click Generate Report
    await page.getByRole('button', { name: /generate report/i }).click();

    // Report eventually appears (polling will run to done state)
    await expect(page.locator('h2').filter({ hasText: 'IWM' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/breakout above prior-day high/i)).toBeVisible();
  });
});
