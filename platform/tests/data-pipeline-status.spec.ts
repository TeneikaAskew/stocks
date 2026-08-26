/**
 * Data Pipeline Status — /api/health/freshness endpoint + dashboard contract.
 *
 * The freshness monitoring system has two halves: the active half is the
 * freshness-watchdog workflow, and the reactive half is the
 * /api/health/freshness endpoint (platform/api/routers/health.py). The
 * DataPipelineStatus widget (src/components/dashboard/DataPipelineStatus.tsx)
 * that used to surface the endpoint on the dashboard is no longer mounted by
 * any route since the dashboard redesign — no importer exists anywhere under
 * src/ — so the page-level tests below pin that CURRENT contract, and the
 * endpoint's shape is verified directly against the API.
 */
import { test, expect } from '@playwright/test';
import { mockCommon, M } from './helpers/mocks';

// Fixture mirroring the real /api/health/freshness envelope
// (health.py get_freshness → scripts/audit_data_freshness.py FreshnessRow):
// checked_at, expected_market_close, overall_status, tables[{table, ticker,
// last_row_at, expected_latest, lag_hours, expected_max_hours, status,
// row_count_recent, writer_job}]. Note market_data_daily tracks IWM/SPY/QQQ
// only — SPX was intentionally removed from that check on 2026-05-15
// (audit_data_freshness.py CHECKS comment); SPX freshness is tracked via
// etf_options_snapshots instead.
const freshnessRow = (table: string, ticker: string | null) => ({
  table,
  ticker,
  last_row_at: '2026-04-24',
  expected_latest: '2026-04-24',
  lag_hours: 2.5,
  expected_max_hours: 30,
  status: 'ok',
  row_count_recent: 1,
  writer_job: null,
});

const MOCK_FRESHNESS = {
  checked_at: '2026-04-25T12:00:00Z',
  expected_market_close: '2026-04-24',
  overall_status: 'ok',
  tables: [
    freshnessRow('market_data_daily', 'IWM'),
    freshnessRow('market_data_daily', 'SPY'),
    freshnessRow('market_data_daily', 'QQQ'),
    freshnessRow('etf_options_snapshots', 'IWM'),
    freshnessRow('etf_options_snapshots', 'SPY'),
    freshnessRow('etf_options_snapshots', 'QQQ'),
    freshnessRow('etf_options_snapshots', 'SPX'),
    freshnessRow('signal_alerts', null),
  ],
};

// First uncached /api/health/freshness call may run the full Cloud SQL audit.
// Pre-warm once so every test after sees the cached, fast response.
test.beforeAll(async ({ request }) => {
  await request.get('http://localhost:8000/api/health/freshness', { timeout: 90_000 });
});

test.describe('Data pipeline status widget', () => {
  // The DataPipelineStatus component still exists but is orphaned: nothing
  // imports it (verified — `grep -rn DataPipelineStatus platform/src` matches
  // only the component file itself), so no dashboard route can render it.
  // This test pins that contract with the freshness route mocked, proving
  // the absence is structural rather than a failed fetch (the widget renders
  // null while loading and an "unavailable" card on error). If the widget is
  // ever re-mounted, this test fails and the render/expand/timestamp suite
  // should be restored from git history alongside these mocks.
  test('dashboard renders without the data-pipeline widget', async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/health/freshness', (r) => r.fulfill(M.ok(MOCK_FRESHNESS)));

    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });

    // Dashboard landmark (DashboardPage.tsx renders the Overview h1)
    await expect(page.locator('h1', { hasText: 'Overview' }).first()).toBeVisible({
      timeout: 15_000,
    });

    // The widget's unmistakable label ("Data pipeline",
    // DataPipelineStatus.tsx) must not appear anywhere on the page.
    await expect(page.getByText(/data pipeline/i)).toHaveCount(0);
  });
});

test.describe('/api/health/freshness endpoint', () => {
  test('returns a valid freshness report', async ({ request }) => {
    const res = await request.get('http://localhost:8000/api/health/freshness');
    expect(res.ok()).toBeTruthy();
    const json = await res.json();

    expect(json).toHaveProperty('checked_at');
    expect(json).toHaveProperty('expected_market_close');
    expect(json).toHaveProperty('overall_status');
    expect(json).toHaveProperty('tables');
    expect(['ok', 'warn', 'stale', 'unknown']).toContain(json.overall_status);
    expect(Array.isArray(json.tables)).toBeTruthy();
    expect(json.tables.length).toBeGreaterThan(0);
  });

  test('every table row has the expected shape', async ({ request }) => {
    const res = await request.get('http://localhost:8000/api/health/freshness');
    const { tables } = await res.json();

    for (const row of tables) {
      expect(row).toHaveProperty('table');
      expect(row).toHaveProperty('status');
      expect(row).toHaveProperty('expected_max_hours');
      expect(row).toHaveProperty('row_count_recent');
      expect(['ok', 'warn', 'stale', 'unknown']).toContain(row.status);
    }
  });

  test('excludes SPX from market_data_daily but audits it via etf_options_snapshots', async ({
    request,
  }) => {
    // SPX was intentionally REMOVED from the market_data_daily check on
    // 2026-05-15: SPX is the S&P 500 *index* — AlphaVantage TIME_SERIES_DAILY
    // has no OHLCV feed for it, and the old FRED close-only hack was ripped
    // out (scripts/audit_data_freshness.py CHECKS: market_data_daily tickers
    // are IWM/SPY/QQQ only; the comment there documents the removal). SPX
    // options Greeks derive spot from the chain via put-call parity, so its
    // freshness IS still watched — through etf_options_snapshots, whose
    // ticker list includes SPX. If SPX reappears under market_data_daily the
    // FRED hack got resurrected; if it drops out of etf_options_snapshots it
    // silently left the watchdog.
    const res = await request.get('http://localhost:8000/api/health/freshness');
    const { tables } = await res.json();

    const spxDaily = tables.find(
      (r: { table: string; ticker: string | null }) =>
        r.table === 'market_data_daily' && r.ticker === 'SPX',
    );
    expect(
      spxDaily,
      'SPX must NOT be in market_data_daily checks (removed 2026-05-15 — no real OHLCV feed)',
    ).toBeUndefined();

    const spxOptions = tables.find(
      (r: { table: string; ticker: string | null }) =>
        r.table === 'etf_options_snapshots' && r.ticker === 'SPX',
    );
    expect(
      spxOptions,
      'SPX row missing from etf_options_snapshots freshness check',
    ).toBeTruthy();
  });

  test('second call hits the TTL cache (fast)', async ({ request }) => {
    // First request may run the full audit (several Cloud SQL queries)
    await request.get('http://localhost:8000/api/health/freshness');

    const t0 = Date.now();
    const res = await request.get('http://localhost:8000/api/health/freshness');
    const elapsed = Date.now() - t0;

    expect(res.ok()).toBeTruthy();
    // Cached responses should come back well under 1s
    expect(elapsed, `cached response took ${elapsed}ms`).toBeLessThan(1000);
  });
});
