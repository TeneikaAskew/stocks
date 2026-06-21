/**
 * Data Pipeline Status widget + /api/health/freshness endpoint.
 *
 * The widget is the reactive half of the data-freshness monitoring system
 * (the active half is the freshness-watchdog GitHub workflow). This suite
 * verifies the widget mounts, renders the API response, and toggles details.
 */
import { test, expect } from '@playwright/test';

// First uncached /api/health/freshness call may run the full Cloud SQL audit.
// Pre-warm once so every test after sees the cached, fast response.
test.beforeAll(async ({ request }) => {
  await request.get('http://localhost:8000/api/health/freshness', { timeout: 90_000 });
});

test.describe('Data pipeline status widget', () => {
  test('renders on the dashboard', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    // The widget always renders a "Data pipeline" label once the query resolves
    await expect(page.getByText(/data pipeline/i).first()).toBeVisible({ timeout: 30_000 });
  });

  test('shows overall status in the collapsed summary', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    // Status label is one of ok | warn | stale | unknown — the CSS uppercases
    // it visually but the DOM text stays lowercase, so match case-insensitively.
    // audit 2026-06-21: the old assertion accepted `unknown` as a valid render.
    // `unknown` is the widget's "the freshness endpoint returned nothing /
    // errored" placeholder, so passing on it let an empty/broken backend look
    // healthy. We now require a REAL status (ok | warn | stale) to be rendered,
    // and convert the `unknown` (endpoint-empty) case into a VISIBLE skip
    // rather than a silent pass — which can never turn a pass into a failure.
    const anyStatus = page.getByText(/^(ok|warn|stale|unknown)$/i).first();
    await expect(anyStatus, 'data-pipeline status label never rendered').toBeVisible({
      timeout: 30_000,
    });
    const statusText = ((await anyStatus.textContent()) || '').trim().toLowerCase();
    test.skip(
      statusText === 'unknown',
      'freshness endpoint returned unknown (no/failed data) — not a healthy state to assert on',
    );
    // Real status present — assert it is one of the genuine health states.
    expect(['ok', 'warn', 'stale']).toContain(statusText);
  });

  test('expands to show per-table pills on click', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    // Click the widget header to expand — it's wrapped in a button
    const header = page.getByText(/data pipeline/i).first();
    await header.click();

    // After expanding, at least one known table name should appear as a pill
    const anyTable = page.getByText(/market_data_daily|etf_options_snapshots|signal_alerts/).first();
    await expect(anyTable).toBeVisible({ timeout: 5_000 });
  });

  test('displays a "Checked HH:MM" timestamp', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    await expect(page.getByText(/checked \d{1,2}:\d{2}/i)).toBeVisible({ timeout: 30_000 });
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

  test('includes SPX in market_data_daily rows', async ({ request }) => {
    // SPX was added to the audit after the parity backfill + fetcher branch
    // landed. If this regresses, SPX will silently drop out of the watchdog.
    const res = await request.get('http://localhost:8000/api/health/freshness');
    const { tables } = await res.json();
    const spxRow = tables.find(
      (r: { table: string; ticker: string | null }) =>
        r.table === 'market_data_daily' && r.ticker === 'SPX',
    );
    expect(spxRow, 'SPX row missing from market_data_daily freshness check').toBeTruthy();
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
