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
      in_force_combo: '2D-1-2U_reversal',
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
    await expect(page.getByText('2D-1-2U_reversal')).toBeVisible();

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

// ---------------------------------------------------------------------------
// Point-in-time replay — datetime picker + ?as_of= query string
// ---------------------------------------------------------------------------

test.describe('AI Insights — point-in-time replay', () => {
  /**
   * Stand up the minimal mock surface every replay test needs:
   *   - GET report          (initial render)
   *   - GET history         (empty)
   *   - POST refresh        (records the URL so we can assert on
   *                          whether ?as_of= rode through)
   *   - GET runs/{id}       (immediately reports done so polling
   *                          terminates fast)
   *
   * Returns the array of refresh-URLs the page hit, so each test
   * can assert exactly which query strings the UI sent.
   */
  async function installRoutes(page: import('@playwright/test').Page): Promise<string[]> {
    const refreshUrls: string[] = [];

    await page.route('**/api/insights/report/IWM', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify(MOCK_REPORT) })
    );
    await page.route('**/api/insights/report/IWM/history**', (route) =>
      route.fulfill({
        status: 200,
        body: JSON.stringify({ ticker: 'IWM', count: 0, reports: [] }),
      })
    );
    await page.route('**/api/insights/report/IWM/refresh**', (route) => {
      refreshUrls.push(route.request().url());
      return route.fulfill({
        status: 200,
        body: JSON.stringify({
          run_id: '00000000-0000-0000-0000-000000000001',
          ticker: 'IWM',
          status: 'queued',
        }),
      });
    });
    await page.route('**/api/insights/runs/**', (route) =>
      route.fulfill({
        status: 200,
        body: JSON.stringify({
          id: '00000000-0000-0000-0000-000000000001',
          ticker: 'IWM',
          status: 'done',
          trigger: 'local_dev',
          started_at: '2026-04-15T14:30:05Z',
          finished_at: '2026-04-15T14:30:17Z',
          error: null,
          report_id: 'abc',
        }),
      })
    );
    // The watchlist panel reads insights_watchlist; mock it as empty so
    // the panel shows its empty state rather than blocking on a fetch.
    await page.route('**/api/insights/watchlist**', (route) =>
      route.fulfill({
        status: 200,
        body: JSON.stringify({ tickers: [] }),
      })
    );

    return refreshUrls;
  }

  test('picker is rendered with a max-now cap on the input', async ({ page }) => {
    await installRoutes(page);
    await page.goto('/insights');
    await page.waitForLoadState('networkidle');

    const picker = page.getByLabel('Point-in-time cutoff');
    await expect(picker).toBeVisible();

    // The `max` attribute prevents users from picking a future moment
    // in the date-picker UI. We assert two things, deliberately:
    //   1. A parseable ISO datetime is set (proves the binding works).
    //   2. The value is within ~1 day of now (proves it's tracking the
    //      clock, not a hardcoded fallback). We can't be tighter than
    //      that because <input type="datetime-local"> takes a *local*-
    //      time string but the JS we hand it via toISOString() is UTC,
    //      so re-parsing through `new Date()` re-applies the TZ offset
    //      and the value drifts by up to 12-14 h depending on locale.
    //      The 1-day window covers every real-world TZ.
    const max = await picker.getAttribute('max');
    expect(max).toBeTruthy();
    const maxMs = new Date(max as string).getTime();
    expect(Number.isFinite(maxMs)).toBeTruthy();
    expect(Math.abs(maxMs - Date.now())).toBeLessThanOrEqual(24 * 60 * 60 * 1000);
  });

  test('button label flips between Re-analyze and Replay based on picker state', async ({
    page,
  }) => {
    await installRoutes(page);
    await page.goto('/insights');
    await page.waitForLoadState('networkidle');

    // Default state — no cutoff set → live re-analysis label.
    const button = page.locator('button', { hasText: /^Re-analyze$|^Replay$/ });
    await expect(button).toHaveText(/Re-analyze/);

    // Setting a cutoff flips the label.
    await page.getByLabel('Point-in-time cutoff').fill('2026-04-26T13:15');
    await expect(button).toHaveText(/Replay/);

    // Clearing the cutoff via the × control reverts.
    await page.getByLabel('Clear cutoff').click();
    await expect(button).toHaveText(/Re-analyze/);
  });

  test('clicking Replay sends ?as_of= encoded in the refresh URL', async ({ page }) => {
    const refreshUrls = await installRoutes(page);
    await page.goto('/insights');
    await page.waitForLoadState('networkidle');

    await page.getByLabel('Point-in-time cutoff').fill('2026-04-26T13:15');
    await page.locator('button', { hasText: 'Replay' }).click();

    // Wait for the refresh request to land — polling kicks in after.
    await expect.poll(() => refreshUrls.length).toBeGreaterThanOrEqual(1);

    const url = new URL(refreshUrls[0]);
    expect(url.pathname).toBe('/api/insights/report/IWM/refresh');
    // Browser datetime-local doesn't append a tz; the value goes through
    // the API as-is and the server treats naive input as UTC.
    expect(url.searchParams.get('as_of')).toBe('2026-04-26T13:15');
  });

  test('clicking Re-analyze with no cutoff sends a query-string-free URL', async ({
    page,
  }) => {
    const refreshUrls = await installRoutes(page);
    await page.goto('/insights');
    await page.waitForLoadState('networkidle');

    await page.locator('button', { hasText: 'Re-analyze' }).click();
    await expect.poll(() => refreshUrls.length).toBeGreaterThanOrEqual(1);

    const url = new URL(refreshUrls[0]);
    expect(url.pathname).toBe('/api/insights/report/IWM/refresh');
    expect(url.search).toBe('');
  });

  test('clearing the cutoff after setting it sends a live (no-as_of) refresh', async ({
    page,
  }) => {
    const refreshUrls = await installRoutes(page);
    await page.goto('/insights');
    await page.waitForLoadState('networkidle');

    // Set a cutoff so the button reads Replay …
    await page.getByLabel('Point-in-time cutoff').fill('2026-04-26T13:15');
    await expect(page.locator('button', { hasText: 'Replay' })).toBeVisible();
    // … then clear it.
    await page.getByLabel('Clear cutoff').click();
    await expect(page.locator('button', { hasText: 'Re-analyze' })).toBeVisible();

    await page.locator('button', { hasText: 'Re-analyze' }).click();
    await expect.poll(() => refreshUrls.length).toBeGreaterThanOrEqual(1);

    expect(new URL(refreshUrls[0]).search).toBe('');
  });
});
