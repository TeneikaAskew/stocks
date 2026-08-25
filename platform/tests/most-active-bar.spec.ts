/**
 * E2E: Most-active ticker bar (Task 3 of the most-active-ticker-bar plan).
 *
 * The `<MostActiveBar/>` marquee mounts under the top nav on Market-section
 * routes (Live/Charts/Options/Signals) and on /journal, fed by
 * GET /api/market/most-active. It renders nothing when the API returns an
 * empty item list (decorative — never a skeleton flash), auto-scrolls via a
 * CSS keyframe animation that's suppressed under `prefers-reduced-motion`,
 * and never causes page-level horizontal overflow (it's its own overflow
 * container).
 */
import { test, expect } from '@playwright/test';
import { mockCommon, mockDashboard, M } from './helpers/mocks';

const MOCK_MOST_ACTIVE = {
  snapshot_ts: '2026-07-12T14:30:00+00:00',
  snapshot_date: '2026-07-12',
  label: 'live',
  items: [
    {
      ticker: 'NVDA',
      rank: 1,
      price: 182.4,
      change_pct: 2.31,
      volume: 312_000_000,
      spark: [181.2, 181.9, 182.4],
    },
    {
      ticker: 'TSLA',
      rank: 2,
      price: 245.1,
      change_pct: -1.42,
      volume: 44_100_000,
      // no `spark` key — under 2 real snapshot points (Rule 3.7: never
      // synthesize a single-point series). Chip must render without one.
    },
  ],
};

const EMPTY_MOST_ACTIVE = { snapshot_ts: null, snapshot_date: null, label: null, items: [] };

async function mockJournalStructure(page: import('@playwright/test').Page) {
  await page.route('**/api/market/dates/IWM', (r) =>
    r.fulfill(M.ok({ ticker: 'IWM', dates: [], months: [] }))
  );
  await page.route('**/api/journal/examples/IWM', (r) =>
    r.fulfill(M.ok({ ticker: 'IWM', source: 'cloud_sql', count: 0, trades: [] }))
  );
  await page.route('**/api/journal/trades/IWM*', (r) =>
    r.fulfill(M.ok({ ticker: 'IWM', count: 0, trades: [] }))
  );
}

async function mockLiveMarketStructure(page: import('@playwright/test').Page) {
  await page.route('**/api/live/quote/IWM*', (r) =>
    r.fulfill(
      M.ok({
        ticker: 'IWM',
        price: 220.45,
        open: 219.8,
        high: 221.2,
        low: 219.5,
        volume: 12_345_678,
        change: 0.65,
        change_pct: 0.296,
        prev_close: 219.8,
        last_updated: '2026-04-25T19:55:00Z',
        market_session: 'closed',
        market_open: false,
      })
    )
  );
  await page.route('**/api/live/history/IWM*', (r) =>
    r.fulfill(M.ok({ ticker: 'IWM', interval: '1min', count: 0, market_session: 'closed', market_open: false, bars: [] }))
  );
  await page.route('**/api/live/avg-volume/IWM*', (r) =>
    r.fulfill(ok_avg_volume())
  );
  await page.route('**/api/playbook/IWM', (r) => r.fulfill(M.ok({ ticker: 'IWM', cards: [] })));
  await page.route('**/api/market/reference/IWM/*', (r) =>
    r.fulfill(
      M.ok({
        ticker: 'IWM',
        date: '2026-04-25',
        source: 'mock',
        open: 219.8,
        high: 222.0,
        low: 218.0,
        close: 220.0,
      })
    )
  );
}

function ok_avg_volume() {
  return M.ok({ ticker: 'IWM', avg_volume_20d: 25_000_000, sample_size: 20, last_date: '2026-04-24', source: 'mock' });
}

test.describe('MostActiveBar', () => {
  test('renders on /journal and on a Market page with a spark ticker and a no-spark ticker', async ({ page }) => {
    await mockCommon(page);
    await mockJournalStructure(page);
    await page.route('**/api/market/most-active', (r) => r.fulfill(M.ok(MOCK_MOST_ACTIVE)));

    await page.goto('/journal');
    await page.waitForLoadState('networkidle');
    const journalBar = page.getByTestId('most-active-bar');
    await expect(journalBar).toBeVisible();
    await expect(journalBar.getByText('NVDA').first()).toBeVisible();
    await expect(journalBar.getByText('TSLA').first()).toBeVisible();
    await expect(journalBar.getByText('312M vol').first()).toBeVisible();
    await expect(journalBar.getByText('44M vol').first()).toBeVisible();

    await mockLiveMarketStructure(page);
    await page.goto('/live');
    await page.waitForLoadState('networkidle');
    const liveBar = page.getByTestId('most-active-bar');
    await expect(liveBar).toBeVisible();
    await expect(liveBar.getByText('NVDA').first()).toBeVisible();
  });

  test('does not mount on non-Market, non-Journal pages', async ({ page }) => {
    await mockDashboard(page);
    await page.route('**/api/market/most-active', (r) => r.fulfill(M.ok(MOCK_MOST_ACTIVE)));

    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('most-active-bar')).toHaveCount(0);
  });

  test('marquee track has the animation class normally, and it is absent under prefers-reduced-motion', async ({ page }) => {
    await mockCommon(page);
    await mockJournalStructure(page);
    await page.route('**/api/market/most-active', (r) => r.fulfill(M.ok(MOCK_MOST_ACTIVE)));

    await page.goto('/journal');
    await page.waitForLoadState('networkidle');
    const track = page.getByTestId('most-active-track');
    await expect(track).toHaveClass(/mab-track--animate/);

    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');
    const reducedTrack = page.getByTestId('most-active-track');
    await expect(reducedTrack).not.toHaveClass(/mab-track--animate/);
  });

  test('renders nothing when the API returns an empty item list', async ({ page }) => {
    await mockCommon(page);
    await mockJournalStructure(page);
    await page.route('**/api/market/most-active', (r) => r.fulfill(M.ok(EMPTY_MOST_ACTIVE)));

    await page.goto('/journal');
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('most-active-bar')).toHaveCount(0);
  });

  test('bar is absent and the page otherwise renders fine when the API returns 500', async ({ page }) => {
    // Error-path pin (T3 review, Minor): useMostActive() uses react-query's
    // default error handling — a non-ok fetch throws inside queryFn, which
    // react-query catches into its `error` state rather than propagating to
    // the component tree. MostActiveBar only reads `data`, so on error
    // `data` stays undefined, `items` defaults to `[]`, and the component
    // returns null (same "null-render" path as the empty-list case above).
    // This is expected to pass immediately given that design — it's a
    // regression pin, not a bugfix, and is kept as one per the review.
    await mockCommon(page);
    await mockJournalStructure(page);
    await page.route('**/api/market/most-active', (r) =>
      r.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'internal server error' }) })
    );

    await page.goto('/journal');
    await page.waitForLoadState('networkidle');

    await expect(page.getByTestId('most-active-bar')).toHaveCount(0);
    // Page otherwise fine: the journal's own content (unrelated to the
    // marquee) still renders normally -- no crash, no error boundary.
    await expect(page.getByRole('heading', { name: 'IWM Trade Journal' })).toBeVisible();
    await expect(page.getByText(/no example trades for iwm yet/i)).toBeVisible();
  });

  test('no page-level horizontal overflow at 390x844 with the bar mounted', async ({ page }) => {
    await mockCommon(page);
    await mockJournalStructure(page);
    await page.route('**/api/market/most-active', (r) =>
      r.fulfill(
        M.ok({
          snapshot_ts: '2026-07-12T14:30:00+00:00',
          snapshot_date: '2026-07-12',
          label: 'live',
          items: Array.from({ length: 20 }, (_, i) => ({
            ticker: `TICK${i}`,
            rank: i + 1,
            price: 100 + i,
            change_pct: i % 2 === 0 ? 1.23 : -1.23,
            volume: 10_000_000 + i * 1_000_000,
            spark: [100 + i, 101 + i, 100 + i],
          })),
        })
      )
    );

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('most-active-bar')).toBeVisible();

    const overflowX = await page.evaluate(() => {
      const doc = document.documentElement;
      return { scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth };
    });
    expect(overflowX.scrollWidth).toBeLessThanOrEqual(overflowX.clientWidth + 1);
  });
});
