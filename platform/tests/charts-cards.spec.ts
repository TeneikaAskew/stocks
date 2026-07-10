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

// ─────────────────────────────────────────────────────────────────────────
// Task 2.4: admin seed-trade teaching layer (GET /api/journal/seed/{ticker}).
// Read-only overlay — muted markers, a "Playbook seed" panel section, a
// client-side benchmark line, and a `Show seed trades` toggle that gates
// both. Unavailable/error responses render an honest muted line, never
// fabricated stats (CLAUDE.md Rule 3.7).
// ─────────────────────────────────────────────────────────────────────────
const SEED_TRADES = [
  {
    id: 'seed-1',
    direction: 'CALL',
    entry_time: '2026-04-25 09:35:00+00:00',
    entry_price: 220.1,
    exit_time: '2026-04-25 09:50:00+00:00',
    exit_price: 221.1,
    return_pct: 0.45,
    strat_combo: '2U-2U',
    exit_reason: 'take_profit',
  },
  {
    id: 'seed-2',
    direction: 'PUT',
    entry_time: '2026-04-25 10:05:00+00:00',
    entry_price: 221.5,
    exit_time: '2026-04-25 10:20:00+00:00',
    exit_price: 221.94,
    return_pct: -0.2,
    strat_combo: '3-2D',
    exit_reason: 'stop_loss',
  },
];

test.describe('Charts page — admin seed-trade teaching layer (Task 2.4)', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
    // Dates come back as YYYYMMDD in production — see the Task 2.3 block
    // above for why this format matters (selectedIsoDate conversion).
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
    await page.route('**/api/journal/trades/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', source: 'cloud_sql', count: 0, trades: [] }))
    );
  });

  test('renders Playbook seed section with read-only rows and a benchmark line; toggle hides section + markers', async ({ page }) => {
    await page.route('**/api/journal/seed/IWM*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', date: '2026-04-25', count: 2, trades: SEED_TRADES }))
    );

    await page.goto('/charts');
    await page.waitForLoadState('networkidle');

    // Section + benchmark line (default ON).
    await expect(page.getByText('Playbook seed')).toBeVisible();
    await expect(page.getByText(/2 trades · 50% win/)).toBeVisible();

    // Two read-only rows — direction chips + signed percents, no exit/delete
    // controls (those only exist on TradeCard, the user-trade component).
    await expect(page.getByText('SEED CALL')).toBeVisible();
    await expect(page.getByText('SEED PUT')).toBeVisible();
    await expect(page.getByText('+0.45%')).toBeVisible();
    await expect(page.getByText('-0.20%')).toBeVisible();
    await expect(page.getByText('2U-2U')).toBeVisible();
    await expect(page.getByText('3-2D')).toBeVisible();

    // Toggle off — section (and its markers) disappear.
    const toggle = page.getByTestId('seed-toggle');
    await expect(toggle).toBeVisible();
    await toggle.click();
    await expect(page.getByText('Playbook seed')).not.toBeVisible();

    // Toggle back on — section reappears (proves it's pure client state,
    // not a one-shot unmount).
    await toggle.click();
    await expect(page.getByText('Playbook seed')).toBeVisible();
  });

  test('unavailable seed layer renders an honest muted line, never fabricated stats', async ({ page }) => {
    await page.route('**/api/journal/seed/IWM*', (r) =>
      r.fulfill(M.ok({ status: 'unavailable', reason: 'seed layer requires Cloud SQL' }))
    );

    await page.goto('/charts');
    await page.waitForLoadState('networkidle');

    await expect(page.getByText('Seed layer unavailable')).toBeVisible();
    // No benchmark numbers should render alongside the honest line.
    await expect(page.getByText(/\d+% win/)).not.toBeVisible();
  });

  test('seed query error (503) renders the same honest muted line', async ({ page }) => {
    await page.route('**/api/journal/seed/IWM*', (r) =>
      r.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'seed query failed' }) })
    );

    await page.goto('/charts');
    await page.waitForLoadState('networkidle');

    await expect(page.getByText('Seed layer unavailable')).toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────────────────
// Task 3.3: "Backtest my trades" scorecard (POST /api/backtest/replay-trades
// — platform/api/routers/backtest.py / lib/backtest.py replay_labeled_trades).
// Button lives in the side panel Trades tab, enabled only when >=1 CLOSED
// (non-active) trade is present for the current ticker/date; clicking it
// opens a modal scoring the closed trades against the production benchmark.
// ─────────────────────────────────────────────────────────────────────────
test.describe('Charts page — backtest-my-trades scorecard (Task 3.3)', () => {
  const CLOSED_ROW_1 = {
    id: 'closed-1',
    ticker: 'IWM',
    direction: 'CALL',
    entry_ts: '2026-04-25T09:31:00',
    exit_ts: '2026-04-25T10:15:00',
    entry_price: 220.0,
    exit_price: 222.5,
    return_pct: 1.5,
    notes: '',
    take_profits: [223],
    stop_loss: 218.5,
    status: 'win',
    source: 'chart',
    session_id: null,
    created_at: '2026-04-25T09:31:01',
  };
  const CLOSED_ROW_2 = {
    id: 'closed-2',
    ticker: 'IWM',
    direction: 'PUT',
    entry_ts: '2026-04-25T10:30:00',
    exit_ts: '2026-04-25T11:00:00',
    entry_price: 221.0,
    exit_price: 220.0,
    return_pct: 0.45,
    notes: '',
    take_profits: [],
    stop_loss: null,
    status: 'win',
    source: 'chart',
    session_id: null,
    created_at: '2026-04-25T10:30:01',
  };
  const ACTIVE_ROW = {
    id: 'active-1',
    ticker: 'IWM',
    direction: 'CALL',
    entry_ts: '2026-04-25T11:15:00',
    exit_ts: null,
    entry_price: 222.0,
    exit_price: null,
    return_pct: null,
    notes: '',
    take_profits: [],
    stop_loss: null,
    status: 'active',
    source: 'chart',
    session_id: null,
    created_at: '2026-04-25T11:15:01',
  };

  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
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
    await page.route('**/api/journal/seed/IWM*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', date: '2026-04-25', count: 0, trades: [] }))
    );
    await page.route('**/api/journal/trades/IWM', (r) =>
      r.fulfill(
        M.ok({
          ticker: 'IWM',
          source: 'cloud_sql',
          count: 3,
          trades: [CLOSED_ROW_1, CLOSED_ROW_2, ACTIVE_ROW],
        })
      )
    );
  });

  test('button is enabled with closed trades present and POSTs only the closed trade ids', async ({ page }) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let capturedBody: any = null;
    await page.route('**/api/backtest/replay-trades', async (route) => {
      capturedBody = route.request().postDataJSON();
      await route.fulfill(
        M.ok({
          trades: [
            {
              id: 'closed-1',
              status: 'ok',
              actual_return_pct: 1.5,
              fill_check: 'ok',
              system_signal_at_entry: { direction: 'CALL', score: 4 },
              system_exit: { exit_reason: 'time_stop', return_pct: 0.3, exit_time: '2026-04-25 10:00:00' },
              exit_edge_bps: 120.0,
            },
            { id: 'closed-2', status: 'unavailable', reason: 'trade still open' },
          ],
          aggregate: {
            n: 2,
            scored_n: 1,
            win_rate: 1.0,
            avg_return_pct: 1.5,
            system_resolved_n: 1,
            system_no_signal_n: 0,
            system_agreement_rate: 1.0,
            avg_exit_edge_bps: 120.0,
          },
        })
      );
    });

    await page.goto('/charts');
    await page.waitForLoadState('networkidle');

    const btn = page.getByTestId('backtest-trades-btn');
    await expect(btn).toBeVisible();
    await expect(btn).toBeEnabled();

    await btn.click();
    await expect.poll(() => capturedBody, { timeout: 10_000 }).not.toBeNull();
    expect(capturedBody.ticker).toBe('IWM');
    expect(new Set(capturedBody.trade_ids)).toEqual(new Set(['closed-1', 'closed-2']));
  });

  test('modal renders per-trade rows (ok + unavailable) and an honest aggregate footer', async ({ page }) => {
    await page.route('**/api/backtest/replay-trades', (r) =>
      r.fulfill(
        M.ok({
          trades: [
            {
              id: 'closed-1',
              status: 'ok',
              actual_return_pct: 1.5,
              fill_check: 'ok',
              system_signal_at_entry: { direction: 'CALL', score: 4 },
              system_exit: { exit_reason: 'time_stop', return_pct: 0.3, exit_time: '2026-04-25 10:00:00' },
              exit_edge_bps: 120.0,
            },
            { id: 'closed-2', status: 'unavailable', reason: 'trade still open' },
          ],
          aggregate: {
            n: 2,
            scored_n: 1,
            win_rate: 1.0,
            avg_return_pct: 1.5,
            system_resolved_n: 1,
            system_no_signal_n: 0,
            system_agreement_rate: 1.0,
            avg_exit_edge_bps: 120.0,
          },
        })
      )
    );

    await page.goto('/charts');
    await page.waitForLoadState('networkidle');
    await page.getByTestId('backtest-trades-btn').click();

    const modal = page.getByTestId('replay-scorecard');
    await expect(modal).toBeVisible();

    const okRow = page.getByTestId('scorecard-row-closed-1');
    await expect(okRow).toBeVisible();
    await expect(okRow.getByText('+1.50%')).toBeVisible();
    await expect(okRow.getByText(/time_stop/)).toBeVisible();
    await expect(okRow.getByText(/match/i)).toBeVisible();
    await expect(okRow.getByText(/\+120\.00\s*bps/)).toBeVisible();

    const unavailableRow = page.getByTestId('scorecard-row-closed-2');
    await expect(unavailableRow).toBeVisible();
    await expect(unavailableRow.getByText(/trade still open/i)).toBeVisible();
    // Unavailable rows never render numbers.
    await expect(unavailableRow.getByText(/%/)).not.toBeVisible();

    await expect(modal.getByText(/1\s*\/\s*2\s*scored.*100%/i)).toBeVisible();
    await expect(modal.getByText(/Agreement:\s*100%/i)).toBeVisible();
    await expect(modal.getByText(/system had a setup on 1 of 1 entries/i)).toBeVisible();
  });

  test('all-unavailable replay shows em dashes in the footer, never a fabricated 0%', async ({ page }) => {
    // #702 follow-ups Task 2 item 1: scored_n === 0 -> win_rate /
    // avg_return_pct / avg_exit_edge_bps come back null from the server;
    // the footer must render '—' for each, not a fabricated "0%"/"0.00%".
    await page.route('**/api/backtest/replay-trades', (r) =>
      r.fulfill(
        M.ok({
          trades: [
            { id: 'closed-1', status: 'unavailable', reason: 'no bars for this date' },
            { id: 'closed-2', status: 'unavailable', reason: 'trade still open' },
          ],
          aggregate: {
            n: 2,
            scored_n: 0,
            win_rate: null,
            avg_return_pct: null,
            system_resolved_n: 0,
            system_no_signal_n: 0,
            system_agreement_rate: null,
            avg_exit_edge_bps: null,
          },
        })
      )
    );

    await page.goto('/charts');
    await page.waitForLoadState('networkidle');
    await page.getByTestId('backtest-trades-btn').click();

    const modal = page.getByTestId('replay-scorecard');
    await expect(modal).toBeVisible();

    // The "0/N scored" context line stays, but every numeric field is a
    // dash: Win rate, Avg return, Avg edge, Agreement.
    await expect(modal.getByText(/0\s*\/\s*2\s*scored/i)).toBeVisible();
    await expect(modal.getByText(/Win rate\s*—/)).toBeVisible();
    await expect(modal.getByText(/Avg return:\s*—/)).toBeVisible();
    await expect(modal.getByText(/Avg edge:\s*—/)).toBeVisible();
    await expect(modal.getByText(/Agreement:\s*—/)).toBeVisible();
    // Never a fabricated zero anywhere in the footer.
    await expect(modal.getByText(/0%|0\.00%|NaN/)).not.toBeVisible();
  });

  test('footer surfaces system_no_signal_n as "no setup on Y" when the system had no setup on some entries', async ({
    page,
  }) => {
    // #702 follow-ups Task 2 item 2: when system_no_signal_n > 0, the
    // agreement clause gains a "· no setup on Y" suffix.
    await page.route('**/api/backtest/replay-trades', (r) =>
      r.fulfill(
        M.ok({
          trades: [
            {
              id: 'closed-1',
              status: 'ok',
              actual_return_pct: 0.8,
              fill_check: 'ok',
              system_signal_at_entry: { direction: null, score: 0 },
              system_exit: { exit_reason: 'time_stop', return_pct: 0.2, exit_time: '2026-04-25 10:00:00' },
              exit_edge_bps: 60.0,
            },
            {
              id: 'closed-2',
              status: 'ok',
              actual_return_pct: -0.5,
              fill_check: 'ok',
              system_signal_at_entry: { direction: 'CALL', score: 4 },
              system_exit: { exit_reason: 'stop_loss', return_pct: -0.3, exit_time: '2026-04-25 11:00:00' },
              exit_edge_bps: -20.0,
            },
          ],
          aggregate: {
            n: 2,
            scored_n: 2,
            win_rate: 0.5,
            avg_return_pct: 0.15,
            system_resolved_n: 1,
            system_no_signal_n: 1,
            system_agreement_rate: 0.0,
            avg_exit_edge_bps: 20.0,
          },
        })
      )
    );

    await page.goto('/charts');
    await page.waitForLoadState('networkidle');
    await page.getByTestId('backtest-trades-btn').click();

    const modal = page.getByTestId('replay-scorecard');
    await expect(modal).toBeVisible();
    await expect(modal.getByText(/system had a setup on 1 of 2 entries.*no setup on 1/i)).toBeVisible();
  });

  test('a 503 from the replay endpoint renders a loud inline error, never a silent failure', async ({ page }) => {
    await page.route('**/api/backtest/replay-trades', (r) =>
      r.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'journal database not configured' }),
      })
    );

    await page.goto('/charts');
    await page.waitForLoadState('networkidle');
    await page.getByTestId('backtest-trades-btn').click();

    const modal = page.getByTestId('replay-scorecard');
    await expect(modal).toBeVisible();
    await expect(modal.getByText(/journal database not configured/i)).toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────────────────
// Task 4.4: "My style" panel (POST /api/style/mine-and-validate —
// platform/api/routers/backtest.py / lib/style_miner.py + lib/walk_forward.py).
// Lives in the side panel's Analytics tab. Always a 200 from the endpoint —
// the "not enough signal yet" cases come back as `{status: "unavailable",
// reason}` and must render the reason verbatim in muted text, never as an
// error; a genuine backend failure (503/500) is a loud inline error.
// ─────────────────────────────────────────────────────────────────────────
test.describe('Charts page — "My style" panel (Task 4.4)', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
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
    await page.route('**/api/journal/seed/IWM*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', date: '2026-04-25', count: 0, trades: [] }))
    );
    await page.route('**/api/journal/trades/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', source: 'cloud_sql', count: 0, trades: [] }))
    );
  });

  async function openAnalyticsTab(page: import('@playwright/test').Page) {
    await page.goto('/charts');
    await page.waitForLoadState('networkidle');
    await page.getByRole('button', { name: /^Analytics$/ }).click();
  }

  test('unavailable response renders the reason verbatim in muted text, never as an error', async ({ page }) => {
    await page.route('**/api/style/mine-and-validate', (r) =>
      r.fulfill(M.ok({ status: 'unavailable', reason: 'need >= 10 closed trades, have 3' }))
    );

    await openAnalyticsTab(page);
    await page.getByTestId('mine-my-style-btn').click();

    const unavailable = page.getByTestId('mine-my-style-unavailable');
    await expect(unavailable).toBeVisible();
    await expect(unavailable).toHaveText('need >= 10 closed trades, have 3');
    // Never rendered as an error banner.
    await expect(page.getByTestId('mine-my-style-error')).not.toBeVisible();
  });

  test('success response renders direction + condition chips and the validated stats line with correctly-converted units', async ({ page }) => {
    await page.route('**/api/style/mine-and-validate', (r) =>
      r.fulfill(
        M.ok({
          profile: {
            direction: 'CALL',
            conditions: ['above_vwap', 'rsi_25_50'],
            support: 4,
            total: 5,
          },
          aggregate_metrics: {
            avg_expectancy_pct: 0.42,
            avg_win_rate: 0.6,
            total_trades_all_folds: 23,
            total_folds: 4,
          },
          stability_score: 0.75,
          staged: true,
        })
      )
    );

    await openAnalyticsTab(page);
    await page.getByTestId('mine-my-style-btn').click();

    const result = page.getByTestId('mine-my-style-result');
    await expect(result).toBeVisible();
    // Scroll-into-view on success: the result sits at the bottom of the
    // scrollable side panel and must be brought into the viewport.
    await expect(result).toBeInViewport();
    await expect(result.getByText('CALL', { exact: true })).toBeVisible();
    await expect(result.getByText('RSI 25-50')).toBeVisible();
    await expect(result.getByText('Above VWAP')).toBeVisible();
    await expect(result.getByText('Based on 4/5 of your entries')).toBeVisible();

    // win_rate 0.6 -> "60%", avg_expectancy_pct 0.42 -> "+0.42%",
    // stability 0.75 -> "75%", plus sample sizes (23 trades, 4 folds).
    await expect(
      result.getByText(/Win rate 60%.*expectancy \+0\.42%.*across 23 trades, 4 folds.*stability 75%/)
    ).toBeVisible();
  });

  test('a stats-endpoint failure dashes every analytics tile with a loud note (no fabricated zeros)', async ({ page }) => {
    await page.route('**/api/analytics/trade-stats', (r) =>
      r.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'stats service down' }),
      })
    );

    await openAnalyticsTab(page);

    await expect(page.getByTestId('analytics-unavailable')).toBeVisible();
    // The Trades count must dash out, not read "0" — a failed fetch is
    // indistinguishable from an empty journal otherwise (Rule 3.7).
    const tradesTile = page.getByText('Trades', { exact: true }).locator('..').locator('.metric-value');
    await expect(tradesTile).toHaveText('--');
    const callTile = page.getByText('CALL', { exact: true }).locator('..').locator('.metric-value');
    await expect(callTile).toHaveText('--');
  });

  test('a 503 from the endpoint renders a loud inline error, never a silent failure', async ({ page }) => {
    await page.route('**/api/style/mine-and-validate', (r) =>
      r.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'journal database not configured' }),
      })
    );

    await openAnalyticsTab(page);
    await page.getByTestId('mine-my-style-btn').click();

    const error = page.getByTestId('mine-my-style-error');
    await expect(error).toBeVisible();
    await expect(error).toHaveText(/journal database not configured/i);
    await expect(page.getByTestId('mine-my-style-unavailable')).not.toBeVisible();
  });

  test('button shows "Mining…" while the mutation is pending', async ({ page }) => {
    await page.route('**/api/style/mine-and-validate', async (r) => {
      await new Promise((resolve) => setTimeout(resolve, 300));
      await r.fulfill(M.ok({ status: 'unavailable', reason: 'need >= 10 closed trades, have 0' }));
    });

    await openAnalyticsTab(page);
    const btn = page.getByTestId('mine-my-style-btn');
    await btn.click();
    await expect(btn).toHaveText(/Mining…/);
    await expect(page.getByTestId('mine-my-style-unavailable')).toBeVisible();
  });
});
