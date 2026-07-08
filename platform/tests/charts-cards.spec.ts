/**
 * E2E for the Phase D / Phase 4 / Phase 5 additions on the Charts page:
 *   - Strategy Conditions card (always rendered when ≥14 bars are loaded)
 *   - Similar Setups card (placeholder when no setup, populated when fired)
 *   - Sig overlay toggle in the toolbar
 *
 * Mocks the bar/reference APIs so the cards render deterministically
 * independent of the live Cloud SQL state. Task 10 moved both cards'
 * math server-side (POST /api/live/indicators, POST /api/live/signal-series
 * — lib/indicators.py + lib/signals.py); those two endpoints are mocked
 * here too so the spec stays fully hermetic and doesn't depend on a
 * FastAPI backend being reachable during the run.
 */
import { test, expect } from '@playwright/test';
import { mockCommon, M } from './helpers/mocks';

// 30 bars walking up — enough to clear the 14-bar RSI warmup and
// produce CALL fires deterministically.
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

const MOCK_REFERENCE = {
  ticker: 'IWM',
  date: '2026-04-25',
  source: 'mock',
  open: 219.8,
  high: 222.0,
  low: 218.0,
  close: 220.0,
};

const MOCK_SIMILAR_CALL = {
  ticker: 'IWM',
  direction: 'CALL',
  rsi: 35,
  score: 4,
  rsi_band: 5,
  stats: {
    count: 240,
    avg_mfe_pct: 0.094,
    median_mfe_pct: 0.077,
    p25_mfe_pct: 0.012,
    p75_mfe_pct: 0.18,
    avg_return_5min: 0.04,
    avg_return_20min: 0.082,
    pct_profitable: 0.858,
    earliest: '2015-01-15T14:00:00+00:00',
    latest: '2026-04-07T20:00:00+00:00',
  },
  matches: [
    {
      time: '2026-04-07 14:44:00+00:00',
      direction: 'CALL',
      price: 250.41,
      score: 4,
      rsi: 35.8,
      return_pct: 0.012,
      return_5min: 0.012,
      return_20min: 0.012,
    },
  ],
};

// Server-side indicators + 10-condition strength panel (POST
// /api/live/indicators — lib/indicators.py). CALL side deliberately fires
// (strength >= 70) so the badge/fires-path is exercised deterministically;
// PUT side does not.
const MOCK_LIVE_INDICATORS = {
  indicators: {
    ema9: 220.5, ema20: 220.0, ema50: 219.0, rsi: 55,
    stochK: 72, stochD: 65, atr: 1.2, vwap: 220.2, stochKPrev: 70,
  },
  signals: {
    call: {
      direction: 'CALL',
      strength: 80,
      fired: true,
      conditions: [
        { id: 'c_p_ema9', label: 'Price > EMA9', met: true, current: 221.5, threshold: 220.5, operator: '>' },
        { id: 'c_p_ema20', label: 'Price > EMA20', met: true, current: 221.5, threshold: 220.0, operator: '>' },
        { id: 'c_p_ema50', label: 'Price > EMA50', met: true, current: 221.5, threshold: 219.0, operator: '>' },
        { id: 'c_p_vwap', label: 'Price > VWAP', met: true, current: 221.5, threshold: 220.2, operator: '>' },
        { id: 'c_rsi50', label: 'RSI > 50', met: true, current: 55, threshold: 50, operator: '>' },
        { id: 'c_rsi60', label: 'RSI > 60', met: false, current: 55, threshold: 60, operator: '>' },
        { id: 'c_stoch70', label: 'StochRSI > 70', met: true, current: 72, threshold: 70, operator: '>' },
        { id: 'c_rvol', label: 'RVOL > 1.0', met: true, current: 1.4, threshold: 1.0, operator: '>' },
        { id: 'c_cross', label: 'EMA9 > EMA20', met: true, current: 220.5, threshold: 220.0, operator: '>' },
        { id: 'c_atr', label: 'ATR > 2.0', met: false, current: 1.2, threshold: 2.0, operator: '>' },
      ],
    },
    put: {
      direction: 'PUT',
      strength: 20,
      fired: false,
      conditions: [
        { id: 'p_p_ema9', label: 'Price < EMA9', met: false, current: 221.5, threshold: 220.5, operator: '<' },
        { id: 'p_p_ema20', label: 'Price < EMA20', met: false, current: 221.5, threshold: 220.0, operator: '<' },
        { id: 'p_p_ema50', label: 'Price < EMA50', met: false, current: 221.5, threshold: 219.0, operator: '<' },
        { id: 'p_p_vwap', label: 'Price < VWAP', met: false, current: 221.5, threshold: 220.2, operator: '<' },
        { id: 'p_rsi50', label: 'RSI < 50', met: false, current: 55, threshold: 50, operator: '<' },
        { id: 'p_rsi40', label: 'RSI < 40', met: false, current: 55, threshold: 40, operator: '<' },
        { id: 'p_stoch30', label: 'StochRSI < 30', met: false, current: 72, threshold: 30, operator: '<' },
        { id: 'p_rvol', label: 'RVOL > 1.0', met: true, current: 1.4, threshold: 1.0, operator: '>' },
        { id: 'p_cross', label: 'EMA9 < EMA20', met: false, current: 220.5, threshold: 220.0, operator: '<' },
        { id: 'p_atr', label: 'ATR > 2.0', met: false, current: 1.2, threshold: 2.0, operator: '>' },
      ],
    },
  },
};

// Server-side per-bar fires (POST /api/live/signal-series — lib/signals.py).
// One CALL fire on the LAST bar so SimilarSetupsCard's "populated" branch is
// exercised deterministically (time must match the last CALL_BARS bar's
// String(time) exactly — see chartBars construction in ChartsPage.tsx).
const LAST_BAR_TIME = String(CALL_BARS[CALL_BARS.length - 1].time);
const MOCK_SIGNAL_SERIES = {
  fires: [
    { time: LAST_BAR_TIME, direction: 'CALL', score: 4, bar_index: CALL_BARS.length - 1 },
  ],
};

test.describe('Charts page — Phase D/4/5 cards', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/market/dates/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', dates: ['2026-04-25'] }))
    );
    await page.route('**/api/market/data/IWM/*', (r) => r.fulfill(M.ok(MOCK_MARKET_DATA)));
    await page.route('**/api/market/reference/IWM/*', (r) => r.fulfill(M.ok(MOCK_REFERENCE)));
    // Similar-setups: any direction returns the canned response above
    await page.route('**/api/signals/IWM/similar*', (r) => r.fulfill(M.ok(MOCK_SIMILAR_CALL)));
    // Existing /api/signals/IWM still gets called by other ChartsPage hooks
    await page.route('**/api/signals/IWM*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', count: 0, signals: [] }))
    );
    // Server-computed indicators/signals (Live Strategy Conditions panel)
    // and per-bar fires (Sig overlay + Similar Setups direction/score).
    await page.route('**/api/live/indicators', (r) => r.fulfill(M.ok(MOCK_LIVE_INDICATORS)));
    await page.route('**/api/live/signal-series', (r) => r.fulfill(M.ok(MOCK_SIGNAL_SERIES)));
    // Task 2.3: chart trades now persist through the journal API
    // (useJournalChartTrades) instead of an in-memory store — every render
    // of /charts fetches GET /api/journal/trades/{ticker}, so it needs a
    // default mock even for specs that don't otherwise touch trades.
    await page.route('**/api/journal/trades/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', source: 'cloud_sql', count: 0, trades: [] }))
    );
  });

  test('Strategy Conditions card renders both CALL and PUT columns', async ({ page }) => {
    await page.goto('/charts');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('Live Strategy Conditions')).toBeVisible();
    await expect(page.getByText(/Price > EMA9/i).first()).toBeVisible();
    await expect(page.getByText(/Price < EMA9/i).first()).toBeVisible();
    // The voter result badge should exist (CALL / PUT / "No setup") — the
    // condition count isn't pinned so the assertion survives future
    // additions/removals from the server-side condition set.
    const badge = page.getByText(/CALL · \d+\/\d+|PUT · \d+\/\d+|No setup/i).first();
    await expect(badge).toBeVisible();
  });

  test('Similar Setups card renders heading and either matches or placeholder', async ({ page }) => {
    await page.goto('/charts');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('Similar Past Setups')).toBeVisible();
    // Either the populated stats grid OR the "Waits for the voter to fire"
    // placeholder must be present — we don't pin behaviour to the exact
    // RSI/score the voter computes from synthetic bars.
    const populated = page.getByText('Matches').first();
    const placeholder = page.getByText(/waits for the voter to fire/i).first();
    await expect(populated.or(placeholder)).toBeVisible();
  });

  test('Sig overlay toggle is in the toolbar and is clickable', async ({ page }) => {
    await page.goto('/charts');
    await page.waitForLoadState('networkidle');
    const sigButton = page.getByRole('button', { name: /^Sig$/ });
    await expect(sigButton).toBeVisible();
    await sigButton.click();
    // Click again to toggle off (no assertion on visual state — just that
    // the button doesn't throw).
    await sigButton.click();
  });
});

// ─────────────────────────────────────────────────────────────────────────
// Task 2.3: chart-marked trades persist through the journal API instead of
// the throwaway zustand store (platform/src/hooks/useJournalChartTrades.ts).
// ─────────────────────────────────────────────────────────────────────────
test.describe('Charts page — journal-backed trade persistence (Task 2.3)', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
    // Dates come back as YYYYMMDD in production (platform/api/main.py's
    // get_available_dates: `d.strftime("%Y%m%d")`) — ChartsPage's
    // selectedIsoDate conversion (slice(0,4)/(4,6)/(6,8)) assumes that, so
    // the mock must match or the journal date filter silently mismatches.
    await page.route('**/api/market/dates/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', dates: ['20260425'] }))
    );
    await page.route('**/api/market/data/IWM/*', (r) => r.fulfill(M.ok(MOCK_MARKET_DATA)));
    await page.route('**/api/market/reference/IWM/*', (r) => r.fulfill(M.ok(MOCK_REFERENCE)));
    await page.route('**/api/signals/IWM/similar*', (r) => r.fulfill(M.ok(MOCK_SIMILAR_CALL)));
    await page.route('**/api/signals/IWM*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', count: 0, signals: [] }))
    );
    await page.route('**/api/live/indicators', (r) => r.fulfill(M.ok(MOCK_LIVE_INDICATORS)));
    await page.route('**/api/live/signal-series', (r) => r.fulfill(M.ok(MOCK_SIGNAL_SERIES)));
  });

  test('renders a trade loaded from the journal GET — covers reload-persistence', async ({ page }) => {
    // A page reload just re-runs this same GET; there's no client-side
    // persistence layer left to lose the trade, so mocking the GET response
    // with a pre-existing closed trade IS the reload-persistence case.
    const closedRow = {
      id: 'closed-trade-1',
      ticker: 'IWM',
      direction: 'CALL',
      entry_ts: '2026-04-25T09:31:00',
      exit_ts: '2026-04-25T10:15:00',
      entry_price: 220.0,
      exit_price: 222.5,
      return_pct: 1.1364,
      notes: '',
      take_profits: [223, 225],
      stop_loss: 218.5,
      status: 'win',
      source: 'chart',
      session_id: null,
      created_at: '2026-04-25T09:31:01',
    };
    await page.route('**/api/journal/trades/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', source: 'cloud_sql', count: 1, trades: [closedRow] }))
    );

    await page.goto('/charts');
    await page.waitForLoadState('networkidle');

    await expect(page.getByText('Trades (1)')).toBeVisible();
    await expect(page.getByText('CALL', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('$220.00')).toBeVisible();
    await expect(page.getByText('$222.50')).toBeVisible();
  });

  test('mark-entry flow POSTs source:"chart", a take_profits array, and a valid epoch->date/time mapping', async ({ page }) => {
    await page.route('**/api/journal/trades/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', source: 'cloud_sql', count: 0, trades: [] }))
    );

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let capturedBody: any = null;
    await page.route('**/api/journal/trades', async (route) => {
      if (route.request().method() !== 'POST') return route.continue();
      capturedBody = route.request().postDataJSON();
      await route.fulfill(M.ok({ source: 'cloud_sql', id: 'new-trade-1', return_pct: null, status: 'active' }));
    });

    await page.goto('/charts');
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

    // Entry click — somewhere in the left third of the plot area, comfortably
    // inside the data range and away from the price-scale/time-scale margins.
    await page.mouse.click(box!.x + box!.width * 0.15, box!.y + box!.height * 0.5);
    await expect(page.getByText('Select CALL or PUT')).toBeVisible();

    await page.getByRole('button', { name: 'CALL' }).click();
    await expect(page.getByText(/Click TP1/)).toBeVisible();
    // CandlestickChart's click-subscription effect (deps: [onChartClick])
    // re-subscribes via a passive useEffect that React flushes some time
    // after paint — the DOM can already read "Click TP1" before the canvas's
    // click handler closure has caught up to the new drawingStep. Empirically
    // (see debug run notes) a couple hundred ms isn't reliably enough in this
    // headless/CI environment; 1.5s consistently clears it without flaking.
    await page.waitForTimeout(1500);

    // Click TP1, then skip TP2/TP3/SL via two Escapes (any tp step -> straight
    // to 'sl' via skipToSL; 'sl' -> skipSL -> completeTrade fires the POST).
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
    expect(Array.isArray(capturedBody.take_profits)).toBe(true);
    expect(capturedBody.take_profits).toHaveLength(1);
    expect(capturedBody.stop_loss).toBeUndefined();

    // entry_date/entry_time must be the naive-ET wall-clock mapping
    // (epochToJournalDateTime, reimplemented here rather than imported so
    // this spec stays independent of the app's module graph/aliases) of
    // SOME bar in CALL_BARS — proves the click's epoch survived the
    // entry->POST-body transform intact.
    const expectedPairs = new Set(
      CALL_BARS.map((b) => {
        const d = new Date(b.time * 1000);
        const p = (n: number) => String(n).padStart(2, '0');
        return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}|${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
      })
    );
    expect(expectedPairs.has(`${capturedBody.entry_date}|${capturedBody.entry_time}`)).toBe(true);
  });
});
