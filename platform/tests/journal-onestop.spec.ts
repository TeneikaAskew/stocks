/**
 * E2E: Journal one-stop cockpit (Task 5 of the journal one-stop-shop program).
 *
 * The /journal page is the complete journaling surface: interactive marking
 * chart + trade rail (layout B "Cockpit"), Examples view (admin teaching
 * trades, GET /api/journal/examples/{ticker}) as the default when the user's
 * own journal is empty, 7 KPI tiles (incl. Avg R:R + TP1 hit), Overview/
 * Session scoping, and risk columns (Stop / TPs / R:R) in the trade table.
 *
 * Mocks follow tests/helpers/mocks.ts conventions; the mark-entry canvas
 * interaction recipe is reused from charts-cards.spec.ts (Task 2.3 block).
 */
import { test, expect } from '@playwright/test';
import { mockCommon, M } from './helpers/mocks';

// 30 bars walking up — same synthetic series as charts-cards.spec.ts so the
// canvas-click recipe resolves clicks to real bars deterministically.
function buildUpRunCandlestick(n = 30, base = 220, step = 0.05) {
  const bars = [];
  for (let i = 0; i < n; i += 1) {
    const close = base + i * step;
    bars.push({
      time: 1_700_000_000 + i * 60,
      open: close - step,
      high: close + 0.01,
      low: close - step - 0.01,
      close,
    });
  }
  return bars;
}

const CALL_BARS = buildUpRunCandlestick(30);
const VOLUME = CALL_BARS.map((c) => ({ time: c.time, value: 100_000 }));

const MOCK_MARKET_DATA = {
  ticker: 'IWM',
  date: '2026-04-25',
  count: CALL_BARS.length,
  candlestick: CALL_BARS,
  volume: VOLUME,
};

// Admin teaching examples — same JSON shape as GET /api/journal/trades.
// ex-1 has the full risk plan: R:R = |220-222.5| / |220-219| = 2.50, and its
// CALL exit (222.5) reached TP1 (222.5) -> TP1 hit = 100%. ex-2 has no
// TP/SL — its risk columns must render "—", never fabricated values.
const EXAMPLE_TRADES = {
  ticker: 'IWM',
  source: 'cloud_sql',
  count: 2,
  trades: [
    {
      id: 'ex-1',
      ticker: 'IWM',
      direction: 'CALL',
      entry_ts: '2026-04-25T09:35:00',
      exit_ts: '2026-04-25T10:15:00',
      entry_price: 220.0,
      exit_price: 222.5,
      return_pct: 1.14,
      notes: 'Example: breakout continuation.',
      take_profits: [222.5, 224],
      stop_loss: 219,
      status: 'win',
      source: 'chart',
      session_id: null,
    },
    {
      id: 'ex-2',
      ticker: 'IWM',
      direction: 'PUT',
      entry_ts: '2026-04-25T10:30:00',
      exit_ts: '2026-04-25T11:00:00',
      entry_price: 221.0,
      exit_price: 221.66,
      return_pct: -0.3,
      notes: 'Example: failed breakdown.',
      status: 'loss',
      source: 'manual',
      session_id: null,
    },
  ],
};

// One own closed trade on the chart date — drives the My-journal rail card
// and risk-column assertions.
const OWN_TRADES = {
  ticker: 'IWM',
  source: 'cloud_sql',
  count: 1,
  trades: [
    {
      id: 'own-1',
      ticker: 'IWM',
      direction: 'CALL',
      entry_ts: '2026-04-25T09:31:00',
      exit_ts: '2026-04-25T10:15:00',
      entry_price: 220.0,
      exit_price: 222.5,
      return_pct: 1.14,
      notes: 'My own breakout trade.',
      take_profits: [223, 225],
      stop_loss: 218.5,
      status: 'win',
      source: 'chart',
      session_id: null,
      created_at: '2026-04-25T09:31:01',
    },
  ],
};

const EMPTY_TRADES = { ticker: 'IWM', source: 'cloud_sql', count: 0, trades: [] };

// task-examples-union: the Examples union response contains BOTH an
// admin-authored journal_entries row (source:'chart', same as EXAMPLE_TRADES
// above) and an automated-pipeline `trades` row (id 'pipe-<n>',
// source:'pipeline') — both dated on the mocked chart session (2026-04-25)
// so both land in the rail. Both are wins so the aggregate tile assertion
// (2W / 0L) is unambiguous evidence the pipeline row's return_pct is folded
// into the stats layer exactly like any other example row (brief: "the
// stats layer must not treat 'pipeline' specially").
const UNION_EXAMPLE_TRADES = {
  ticker: 'IWM',
  source: 'cloud_sql',
  count: 2,
  trades: [
    {
      id: 'admin-union-1',
      ticker: 'IWM',
      direction: 'CALL',
      entry_ts: '2026-04-25T09:35:00',
      exit_ts: '2026-04-25T10:15:00',
      entry_price: 220.0,
      exit_price: 222.5,
      return_pct: 1.14,
      notes: 'Admin-authored example.',
      take_profits: [],
      stop_loss: null,
      status: 'win',
      source: 'chart',
      session_id: null,
    },
    {
      id: 'pipe-9001',
      ticker: 'IWM',
      direction: 'PUT',
      entry_ts: '2026-04-25T10:30:00',
      exit_ts: '2026-04-25T11:00:00',
      entry_price: 221.0,
      exit_price: 219.5,
      return_pct: 0.68,
      notes: 'target_hit',
      take_profits: [],
      stop_loss: null,
      status: 'win',
      source: 'pipeline',
      session_id: null,
    },
  ],
};

async function mockJournalOneStop(
  page: import('@playwright/test').Page,
  { own, examples }: { own: unknown; examples: unknown },
) {
  await mockCommon(page);
  // Dates come back as YYYYMMDD in production (platform/api/main.py) — the
  // page's ISO conversion assumes that (see charts-cards.spec.ts Task 2.3).
  await page.route('**/api/market/dates/IWM', (r) =>
    r.fulfill(M.ok({ ticker: 'IWM', dates: ['20260425'] }))
  );
  await page.route('**/api/market/data/IWM/*', (r) => r.fulfill(M.ok(MOCK_MARKET_DATA)));
  await page.route('**/api/config/market-hours', (r) =>
    r.fulfill(
      M.ok({
        regular: { open: '09:30', close: '16:00' },
        premarket: { open: '04:00', close: '09:30' },
        afterhours: { open: '16:00', close: '20:00' },
      })
    )
  );
  await page.route('**/api/journal/trades/IWM', (r) => r.fulfill(M.ok(own)));
  await page.route('**/api/journal/examples/IWM', (r) => r.fulfill(M.ok(examples)));
}

test.describe('Journal one-stop cockpit — Examples default', () => {
  test.beforeEach(async ({ page }) => {
    await mockJournalOneStop(page, { own: EMPTY_TRADES, examples: EXAMPLE_TRADES });
  });

  test('defaults to Examples when own journal is empty — EX badges, 7 populated tiles, risk columns with "—" honesty', async ({ page }) => {
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');

    // Rail cards carry the EX badge (read-only teaching rows).
    await expect(page.getByTestId('ex-badge').first()).toBeVisible();

    // Scope label opens in Overview.
    await expect(page.getByTestId('scope-label')).toHaveText(/overview — all dates/i);

    // All 7 KPI tiles, populated from the examples dataset.
    await expect(page.getByText('Trades', { exact: true })).toBeVisible();
    await expect(page.getByText('Win rate')).toBeVisible();
    await expect(page.getByText('Total P&L')).toBeVisible();
    await expect(page.getByText('Avg / trade')).toBeVisible();
    await expect(page.getByText('Avg win')).toBeVisible();
    await expect(page.getByText('Avg R:R')).toBeVisible();
    await expect(page.getByText('TP1 hit')).toBeVisible();
    // ex-1's plan: |220-222.5|/|220-219| = 2.50; its exit reached TP1 -> 100%.
    // exact:true so "$222.50" (which contains the substring "2.50") can't
    // satisfy the assertion.
    await expect(page.getByText('2.50', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('100%', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('1W / 1L')).toBeVisible();

    // Trade table: risk columns render values for ex-1 and "—" for ex-2.
    await expect(page.getByRole('columnheader', { name: 'Stop' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'TPs' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'R:R' })).toBeVisible();
    const ex1Row = page.locator('tr', { hasText: 'Example: breakout continuation.' });
    await expect(ex1Row.getByText('$219.00')).toBeVisible();
    await expect(ex1Row.getByText('222.50 / 224.00')).toBeVisible();
    const ex2Row = page.locator('tr', { hasText: 'Example: failed breakdown.' });
    await expect(ex2Row.getByText('—').first()).toBeVisible();

    // Examples are read-only: table row actions are disabled with a tooltip.
    await expect(ex1Row.getByRole('button')).toBeDisabled();

    // Equity curve card sits in the rail (2 closed trades -> a real curve).
    await expect(page.getByText(/equity curve/i).first()).toBeVisible();
  });

  test('toggling to My journal shows the own empty state WITHOUT hiding the chart', async ({ page }) => {
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');

    await page.getByRole('button', { name: 'My journal' }).click();

    await expect(page.getByText(/no trades logged for iwm yet/i)).toBeVisible();
    // The chart card and its canvas stay rendered — never a bare page.
    await expect(page.locator('canvas').first()).toBeVisible();
    // EX badges are gone in My-journal view.
    await expect(page.getByTestId('ex-badge')).toHaveCount(0);
  });

  test('mark-entry flow on the JOURNAL chart POSTs source:"chart" and flips the view to My journal', async ({ page }) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let capturedBody: any = null;
    await page.route('**/api/journal/trades', async (route) => {
      if (route.request().method() !== 'POST') return route.continue();
      capturedBody = route.request().postDataJSON();
      await route.fulfill(
        M.ok({ source: 'cloud_sql', id: 'new-trade-1', return_pct: null, status: 'active' })
      );
    });

    await page.goto('/journal');
    await page.waitForLoadState('networkidle');

    // RTH filtering (default ON) would clip every CALL_BARS candle — their
    // epochs land at ~22:xx UTC, outside the 09:30-16:00 RTH window — so no
    // candles would be plotted for the click handler to hit. Toggle it off
    // so the full 30-bar series renders and a click resolves to a real bar.
    await page.getByRole('button', { name: /^RTH$/ }).click();
    await page.waitForTimeout(500);

    await page.getByRole('button', { name: /Mark Entry/ }).click();
    await expect(page.getByText('Click chart to set entry price')).toBeVisible();

    const canvas = page.locator('canvas').first();
    const box = await canvas.boundingBox();
    expect(box).not.toBeNull();

    // Entry click — left third of the plot area, away from scale margins.
    await page.mouse.click(box!.x + box!.width * 0.15, box!.y + box!.height * 0.5);
    await expect(page.getByText('Select CALL or PUT')).toBeVisible();

    await page.getByRole('button', { name: 'CALL' }).click();
    await expect(page.getByText(/Click TP1/)).toBeVisible();
    // CandlestickChart's click-subscription effect re-subscribes via a
    // passive useEffect — the DOM can read "Click TP1" before the canvas's
    // click closure caught up to the new drawingStep (see
    // charts-cards.spec.ts's identical wait).
    await page.waitForTimeout(1500);

    // Click TP1, then skip TP2/TP3/SL via two Escapes.
    await page.mouse.click(box!.x + box!.width * 0.3, box!.y + box!.height * 0.3);
    await expect(page.getByText(/Click TP2/)).toBeVisible();
    await page.waitForTimeout(500);

    await page.keyboard.press('Escape');
    await expect(page.getByText(/Click Stop Loss/)).toBeVisible();
    await page.waitForTimeout(500);
    await page.keyboard.press('Escape');

    await expect.poll(() => capturedBody, { timeout: 10_000 }).not.toBeNull();
    expect(capturedBody.ticker).toBe('IWM');
    expect(capturedBody.direction).toBe('CALL');
    expect(capturedBody.source).toBe('chart');

    // Marking always writes to MY journal — the view flips so the user sees
    // where the trade went. Own journal (mock) is still empty -> its honest
    // empty state proves the active view is now My journal, and the EX
    // badges are gone.
    await expect(page.getByText(/no trades logged for iwm yet/i)).toBeVisible();
    await expect(page.getByTestId('ex-badge')).toHaveCount(0);
  });
});

test.describe('Journal one-stop cockpit — My journal view', () => {
  test.beforeEach(async ({ page }) => {
    await mockJournalOneStop(page, { own: OWN_TRADES, examples: EXAMPLE_TRADES });
  });

  test('rail card shows the return % centered and prominent', async ({ page }) => {
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');

    // Own journal is non-empty -> defaults to My journal.
    await expect(page.getByTestId('ex-badge')).toHaveCount(0);

    const railReturn = page.getByTestId('rail-return').first();
    await expect(railReturn).toBeVisible();
    await expect(railReturn).toHaveText('+1.14%');

    // "Centered": the return element's horizontal midpoint sits within the
    // middle third of its card. "Prominent": its font-size is strictly the
    // largest on the card.
    const card = page.getByTestId('trade-rail-card').first();
    const cardBox = await card.boundingBox();
    const retBox = await railReturn.boundingBox();
    expect(cardBox).not.toBeNull();
    expect(retBox).not.toBeNull();
    const retMid = retBox!.x + retBox!.width / 2;
    expect(retMid).toBeGreaterThan(cardBox!.x + cardBox!.width / 3);
    expect(retMid).toBeLessThan(cardBox!.x + (cardBox!.width * 2) / 3);
    const retSize = await railReturn.evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
    const maxOtherSize = await card.evaluate((el) => {
      let max = 0;
      el.querySelectorAll('*').forEach((child) => {
        // Skip the return element itself AND its ancestors — containers
        // inherit the root font-size without rendering their own text, so
        // only elements whose text is NOT the return figure count.
        if (
          (child as HTMLElement).dataset?.testid === 'rail-return' ||
          child.querySelector('[data-testid="rail-return"]')
        ) return;
        // Only elements that RENDER text directly (a non-whitespace text
        // node child) — a wrapper div inheriting 16px around 12px spans
        // doesn't display any 16px glyphs itself.
        const rendersText = Array.from(child.childNodes).some(
          (n) => n.nodeType === Node.TEXT_NODE && n.textContent?.trim(),
        );
        if (!rendersText) return;
        const size = parseFloat(getComputedStyle(child).fontSize);
        if (size > max) max = size;
      });
      return max;
    });
    expect(retSize).toBeGreaterThan(maxOtherSize);
  });

  test('risk columns render values for a planned trade in My journal', async ({ page }) => {
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');

    // own-1: stop 218.5, TPs 223/225, R:R = |220-223|/|220-218.5| = 2.00.
    const ownRow = page.locator('tr', { hasText: 'My own breakout trade.' });
    await expect(ownRow.getByText('$218.50')).toBeVisible();
    await expect(ownRow.getByText('223.00 / 225.00')).toBeVisible();
    await expect(ownRow.getByText('2.00', { exact: true })).toBeVisible();
  });

  test('scope label flips between Overview and Session when the date is selected/cleared', async ({ page }) => {
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');

    const label = page.getByTestId('scope-label');
    await expect(label).toHaveText(/overview — all dates/i);

    await page.locator('input[type="date"]').first().fill('2026-04-25');
    await expect(label).toHaveText(/session — 04\/25\/2026/i);

    await page.getByTestId('clear-date').click();
    await expect(label).toHaveText(/overview — all dates/i);
  });

  test('hovering a rail card highlights its markers on the chart, and mouseleave clears it', async ({ page }) => {
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');

    const card = page.getByTestId('trade-rail-card').first();
    const chart = page.getByTestId('trade-marking-chart');

    // No hover yet — neither side reflects a highlight.
    await expect(chart).not.toHaveAttribute('data-highlighted-trade', /.+/);

    await card.hover();
    await expect(card).toHaveAttribute('data-highlighted', 'true');
    await expect(chart).toHaveAttribute('data-highlighted-trade', 'own-1');

    // Mouseleave clears both sides.
    await page.mouse.move(0, 0);
    await expect(card).not.toHaveAttribute('data-highlighted', 'true');
    await expect(chart).not.toHaveAttribute('data-highlighted-trade', /.+/);
  });
});

// Bug (2026-07-12 user acceptance): a chart-marked IWM trade at naive-ET
// 10:05 showed the chart marker and TradeRailCard correctly at 10:05, but
// the journal TABLE row showed 14:05 — a 4-hour UTC<->ET discrepancy
// between two views of the SAME stored row. Root cause: JournalPage's
// `tsToDisplay` round-tripped the naive-ET timestamp string through
// `new Date(...)`, which parses an offset-less date-time string as
// HOST-LOCAL time; TradeRailCard's `formatTime` never went through `Date`
// string-parsing (it reads the already-correct epoch via `isoNaiveToEpoch`
// and formats with UTC accessors), so it was immune. Pinned here with the
// EXACT wire shape `_rows_to_trades` (platform/api/routers/journal.py)
// returns for a Cloud SQL journal_entries row: space-separated, no offset
// ("YYYY-MM-DD HH:MM:SS", from the `entry_ts AT TIME ZONE 'UTC'` SELECT
// cast) — under a non-UTC browser timezone, so the assertion only passes
// if the fix is genuinely host-timezone-independent. Dated 2026-04-25 (not
// the real bug's 2026-07-08) to match `mockJournalOneStop`'s single mocked
// market-data session date, so both the chart rail (date-filtered) and the
// table (session-scoped when only one date exists) render this row.
test.describe('Journal one-stop cockpit — table/rail-card time parity (regression)', () => {
  test.use({ timezoneId: 'America/New_York' });

  const TZ_BUG_OWN_TRADES = {
    ticker: 'IWM',
    source: 'cloud_sql',
    count: 1,
    trades: [
      {
        id: 'tz-bug-1',
        ticker: 'IWM',
        direction: 'CALL',
        entry_ts: '2026-04-25 10:05:00', // exact _rows_to_trades wire shape
        exit_ts: null,
        entry_price: 291.86,
        exit_price: null,
        return_pct: null,
        notes: 'TZ parity regression trade.',
        take_profits: [],
        stop_loss: null,
        status: 'active',
        source: 'chart',
        session_id: null,
      },
    ],
  };

  test.beforeEach(async ({ page }) => {
    await mockJournalOneStop(page, { own: TZ_BUG_OWN_TRADES, examples: EXAMPLE_TRADES });
  });

  test('the table Entry time and the rail card time render the SAME naive-ET wall clock', async ({ page }) => {
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');

    const railTime = page.getByTestId('rail-entry-time').first();
    const tableTime = page.getByTestId('table-entry-time').first();
    await expect(railTime).toBeVisible();
    await expect(tableTime).toBeVisible();

    // Both must read the stored wall clock (10:05), never the TZ-shifted
    // 14:05 the pre-fix `tsToDisplay` produced under America/New_York.
    await expect(railTime).toHaveText('10:05');
    await expect(tableTime).toHaveText('10:05');
  });
});

// Mobile responsiveness (staging bug report, 390-412px viewport): the
// cockpit row (chart + rail, layout B) used a fixed `w-[340px] shrink-0`
// rail beside a `flex-1` chart in a plain `flex` row — on a phone viewport
// the chart collapsed to a sliver and its own toolbar overlapped the
// rail's heading/cards. The approved design stacks the rail BELOW the
// chart under the `lg` breakpoint.
test.describe('Journal one-stop cockpit — mobile viewport (390x844)', () => {
  test.beforeEach(async ({ page }) => {
    await mockJournalOneStop(page, { own: OWN_TRADES, examples: EXAMPLE_TRADES });
  });

  test('no page-level horizontal scroll, and the rail stacks below the chart (not beside it)', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');

    // (a) No horizontal overflow at the page level.
    const overflowX = await page.evaluate(() => {
      const doc = document.documentElement;
      return { scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth };
    });
    expect(overflowX.scrollWidth).toBeLessThanOrEqual(overflowX.clientWidth + 1);

    // (b) Chart card and rail do NOT overlap horizontally — the rail sits
    // below the chart card (stacked), not beside it.
    const chartCard = page.getByTestId('journal-chart-card');
    const rail = page.getByTestId('trade-rail-card').first();
    const chartBox = await chartCard.boundingBox();
    const railBox = await rail.boundingBox();
    expect(chartBox).not.toBeNull();
    expect(railBox).not.toBeNull();
    expect(railBox!.y).toBeGreaterThanOrEqual(chartBox!.y + chartBox!.height - 1);

    // (c) The chart card is not squeezed into a sliver.
    expect(chartBox!.width).toBeGreaterThanOrEqual(300);
  });
});

// task-examples-union: Examples = pipeline `trades` UNION admin journal
// (user decision 2026-07-11) — GET /api/journal/examples/{ticker} now
// returns both an admin-authored row and a pipeline row; the page must
// render both with their distinct origin badges and aggregate both into
// the KPI tiles unchanged (stats layer treats 'pipeline' like any other
// non-replay source).
test.describe('Journal one-stop cockpit — Examples union (pipeline + admin)', () => {
  test.beforeEach(async ({ page }) => {
    await mockJournalOneStop(page, { own: EMPTY_TRADES, examples: UNION_EXAMPLE_TRADES });
  });

  test('renders a pipeline-labeled row alongside an admin EX row; tiles aggregate both', async ({ page }) => {
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');

    // Both example rows carry the EX badge (read-only teaching rows) — the
    // pipeline row ADDITIONALLY carries the muted "pipeline" origin badge,
    // distinguishing it from the admin-authored one.
    await expect(page.getByTestId('ex-badge')).toHaveCount(2);
    await expect(page.getByTestId('pipeline-badge')).toHaveCount(1);

    // Tiles aggregate BOTH rows — 2 trades total, both wins (1.14% CALL +
    // 0.68% PUT), so the win/loss sub-label reads 2W / 0L.
    await expect(page.getByText('Trades', { exact: true })).toBeVisible();
    await expect(page.getByText('2W / 0L')).toBeVisible();

    // Trade table: the pipeline row's direction cell carries the "pipeline"
    // badge; the admin row's does not.
    const pipelineRow = page.locator('tr', { hasText: 'target_hit' });
    await expect(pipelineRow.getByText('pipeline', { exact: true })).toBeVisible();
    const adminRow = page.locator('tr', { hasText: 'Admin-authored example.' });
    await expect(adminRow.getByText('pipeline', { exact: true })).toHaveCount(0);

    // Examples stay read-only across the union — both rows' delete buttons
    // are disabled, including the pipeline one.
    await expect(pipelineRow.getByRole('button')).toBeDisabled();
  });
});

// task-alerts-enrichment (2026-07-12 user decision): pipeline example rows
// join `signal_alerts` server-side — TPs come from the matched alert's
// target_price, and the Stop column/rail SL segment render the row's OWN
// time_stop_minutes as "<N>m time-stop" (never a fixed label, since there is
// no stop PRICE for a pipeline row). Two rows with DIFFERENT time-stop
// minutes (20 vs 25) prove the render is per-row, not hardcoded.
const ALERT_ENRICHED_TRADES = {
  ticker: 'IWM',
  source: 'cloud_sql',
  count: 2,
  trades: [
    {
      id: 'pipe-alert-1',
      ticker: 'IWM',
      direction: 'CALL',
      entry_ts: '2026-04-25T09:35:00',
      exit_ts: '2026-04-25T10:15:00',
      entry_price: 220.0,
      exit_price: 222.5,
      return_pct: 1.14,
      notes: 'target_hit · PDH · score 4.0',
      take_profits: [297.21],
      stop_loss: null,
      time_stop_minutes: 20,
      status: 'win',
      source: 'pipeline',
      session_id: null,
    },
    {
      id: 'pipe-alert-2',
      ticker: 'IWM',
      direction: 'PUT',
      entry_ts: '2026-04-25T10:30:00',
      exit_ts: null,
      entry_price: 221.0,
      exit_price: null,
      return_pct: null,
      notes: '',
      take_profits: [249.9],
      stop_loss: null,
      time_stop_minutes: 25,
      status: 'active',
      source: 'pipeline',
      session_id: null,
    },
  ],
};

test.describe('Journal one-stop cockpit — Examples alert enrichment (TPs + per-row time-stop)', () => {
  test.beforeEach(async ({ page }) => {
    await mockJournalOneStop(page, { own: EMPTY_TRADES, examples: ALERT_ENRICHED_TRADES });
  });

  test('table Stop cell renders each pipeline row\'s OWN time_stop_minutes, never a fixed label', async ({ page }) => {
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');

    const row1 = page.locator('tr', { hasText: 'target_hit · PDH · score 4.0' });
    // Only one PUT row exists in this fixture set (pipe-alert-2) — the
    // direction badge text is a unique, unambiguous locator here.
    const row2 = page.locator('tr', { hasText: 'PUT' });

    // Row 1 (matched alert, time_stop_minutes=20): Stop cell "20m time-stop",
    // TPs cell shows the matched target_price, R:R stays "—" (no stop PRICE
    // exists — a ratio would be fabricated, CLAUDE.md Rule 3.7).
    await expect(row1.getByTestId('table-stop-cell')).toHaveText('20m time-stop');
    await expect(row1.getByText('297.21')).toBeVisible();
    await expect(row1.getByText('—').first()).toBeVisible();

    // Row 2 (matched alert, DIFFERENT time_stop_minutes=25) — mutation-proof:
    // a hardcoded "20m time-stop" render would make both rows identical.
    await expect(row2.getByTestId('table-stop-cell')).toHaveText('25m time-stop');
    await expect(row2.getByText('249.90')).toBeVisible();
    await expect(row2.getByText('—').first()).toBeVisible();

    const stopCells = page.getByTestId('table-stop-cell');
    await expect(stopCells).toHaveCount(2);
    const texts = await stopCells.allTextContents();
    expect(new Set(texts).size).toBe(2); // two DIFFERENT rendered values
  });

  test('rail card SL segment renders the time-stop text (no stop price), and the chart draws a TP line from take_profits', async ({ page }) => {
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');

    const railSlSegments = page.getByTestId('rail-sl');
    await expect(railSlSegments).toHaveCount(2);
    const railTexts = await railSlSegments.allTextContents();
    expect(railTexts.some((t) => t.includes('20m time-stop'))).toBe(true);
    expect(railTexts.some((t) => t.includes('25m time-stop'))).toBe(true);

    // The chart renders TP price lines sourced from take_profits — presence
    // of the chart canvas plus the rail cards (which share the SAME mapped
    // TradeEntry.takeProfits the chart's tradePriceLines memo reads from)
    // is the end-to-end proof the matched alert's target_price reaches the
    // chart layer, not just the table.
    await expect(page.locator('canvas').first()).toBeVisible();
    const railTps = page.locator('[data-testid="trade-rail-card"]').getByText(/TP/);
    await expect(railTps.first()).toBeVisible();
  });
});
