/**
 * E2E for the bar-replay trainer session mode on /charts (Task 5.2).
 *
 * Mocks a full trading day of 1-minute bars (all inside the default RTH
 * window, encoded as naive-ET-as-UTC epochs per this repo's convention —
 * see useJournalChartTrades.ts's isoNaiveToEpoch doc comment) and drives:
 *   Start replay -> warm-start reveal -> Step x2 -> Sig disabled ->
 *   Mark Entry mid-replay POSTs source:'replay' + a real session UUID with
 *   the entry pinned to the LAST REVEALED bar's epoch -> a future-timed
 *   existing trade is hidden from both the side-panel count and the
 *   "N hidden" toolbar readout while the reveal hasn't reached it yet.
 */
import { test, expect } from '@playwright/test';
import { mockCommon, M } from './helpers/mocks';

// 30 one-minute bars starting 09:31 "ET" (naive-ET-as-UTC epoch, matching
// this repo's chart-time convention), so every bar falls inside the default
// 09:30-16:00 RTH window without needing to toggle RTH off.
const START_EPOCH = Math.floor(Date.UTC(2026, 3, 25, 9, 31, 0) / 1000);
function buildDayBars(n = 30, base = 220, step = 0.05) {
  const bars = [];
  for (let i = 0; i < n; i += 1) {
    const close = base + i * step;
    bars.push({
      time: START_EPOCH + i * 60,
      open: close - step,
      high: close + 0.01,
      low: close - step - 0.01,
      close,
    });
  }
  return bars;
}

const DAY_BARS = buildDayBars(30);
const DAY_VOLUME = DAY_BARS.map((c) => ({ time: c.time, value: 100_000, color: '#089981' }));

const MOCK_MARKET_DATA = {
  ticker: 'IWM',
  date: '2026-04-25',
  count: DAY_BARS.length,
  candlestick: DAY_BARS,
  volume: DAY_VOLUME,
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

// Structurally valid but inert (no fires / no strength) — the Strategy
// Conditions panel and the Sig overlay aren't under test here, only that
// the latter is force-disabled during a replay session.
const MOCK_LIVE_INDICATORS = {
  indicators: {
    ema9: null, ema20: null, ema50: null, rsi: null,
    stochK: null, stochD: null, atr: null, vwap: null, stochKPrev: null,
  },
  signals: {
    call: { direction: 'CALL', strength: 0, fired: false, conditions: [] },
    put: { direction: 'PUT', strength: 0, fired: false, conditions: [] },
  },
};
const MOCK_SIGNAL_SERIES = { fires: [] };

// One trade inside the warm-start reveal (bar index 5, 09:36) and one AFTER
// the reveal will ever reach during this test (bar index 25, 09:56) — the
// latter is the information-leakage case the replay cutoff must hide.
const EARLY_TRADE = {
  id: 'early-trade-1',
  ticker: 'IWM',
  direction: 'CALL',
  entry_ts: '2026-04-25T09:36:00',
  exit_ts: null,
  entry_price: 220.25,
  exit_price: null,
  return_pct: null,
  notes: '',
  take_profits: [],
  stop_loss: null,
  status: 'active',
  source: 'chart',
  session_id: null,
  created_at: '2026-04-25T09:36:01',
};
const LATE_TRADE = {
  id: 'late-trade-1',
  ticker: 'IWM',
  direction: 'PUT',
  entry_ts: '2026-04-25T09:56:00',
  exit_ts: null,
  entry_price: 221.5,
  exit_price: null,
  return_pct: null,
  notes: '',
  take_profits: [],
  stop_loss: null,
  status: 'active',
  source: 'chart',
  session_id: null,
  created_at: '2026-04-25T09:56:01',
};

test.describe('Charts page — bar-replay trainer session (Task 5.2)', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
    // Dates come back as YYYYMMDD in production — see charts-cards.spec.ts's
    // Task 2.3 block for why this format matters (selectedIsoDate conversion).
    await page.route('**/api/market/dates/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', dates: ['20260425'] }))
    );
    await page.route('**/api/market/data/IWM/*', (r) => r.fulfill(M.ok(MOCK_MARKET_DATA)));
    await page.route('**/api/market/reference/IWM/*', (r) => r.fulfill(M.ok(MOCK_REFERENCE)));
    await page.route('**/api/signals/IWM/similar*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', direction: 'CALL', rsi: 35, score: 4, rsi_band: 5, stats: null, matches: [] }))
    );
    await page.route('**/api/signals/IWM*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', count: 0, signals: [] }))
    );
    await page.route('**/api/live/indicators', (r) => r.fulfill(M.ok(MOCK_LIVE_INDICATORS)));
    await page.route('**/api/live/signal-series', (r) => r.fulfill(M.ok(MOCK_SIGNAL_SERIES)));
    await page.route('**/api/journal/seed/IWM*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', date: '2026-04-25', count: 0, trades: [] }))
    );
    await page.route('**/api/journal/trades/IWM', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', source: 'cloud_sql', count: 2, trades: [EARLY_TRADE, LATE_TRADE] }))
    );
  });

  test('start -> warm-start reveal -> step x2 -> Sig disabled -> future trade hidden -> Mark Entry POSTs source:replay pinned to the last revealed bar', async ({ page }) => {
    await page.goto('/charts');
    await page.waitForLoadState('networkidle');

    // Pre-replay: both trades visible (no cutoff in effect yet).
    await expect(page.getByText('Trades (2)')).toBeVisible();

    // Start replay -> warm-start reveal (REPLAY_WARM_START_BARS = 15 of 30).
    const startBtn = page.getByTestId('replay-start-btn');
    await expect(startBtn).toBeVisible();
    await startBtn.click();

    const revealedCount = page.getByTestId('replay-revealed-count');
    await expect(revealedCount).toHaveText('15/30');

    // Future-timed trade (09:56, bar 25) is now hidden — reveal cutoff is
    // bar 14 (09:45). Only the early trade (09:36, bar 5) remains visible.
    await expect(page.getByText('Trades (1)')).toBeVisible();
    await expect(page.getByText(/1 trade hidden/)).toBeVisible();

    // Sig overlay is force-disabled for the duration of the session.
    const sigButton = page.getByRole('button', { name: /^Sig$/ });
    await expect(sigButton).toBeDisabled();
    await expect(sigButton).toHaveAttribute('title', 'unavailable during replay');

    // Step twice: 15 -> 16 -> 17.
    const stepBtn = page.getByTestId('replay-step-btn');
    await stepBtn.click();
    await stepBtn.click();
    await expect(revealedCount).toHaveText('17/30');

    // Still hidden — cutoff is now bar 16 (09:47), still before 09:56.
    await expect(page.getByText('Trades (1)')).toBeVisible();
    await expect(page.getByText(/1 trade hidden/)).toBeVisible();

    // Let the appendMode extension's chart-canvas repaint settle before
    // clicking it (the two Step clicks each trigger a React re-render ->
    // series.update() in a passive effect that lags a beat behind the DOM).
    await page.waitForTimeout(500);

    // Mark Entry mid-playback.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let capturedBody: any = null;
    await page.route('**/api/journal/trades', async (route) => {
      if (route.request().method() !== 'POST') return route.continue();
      capturedBody = route.request().postDataJSON();
      await route.fulfill(M.ok({ source: 'cloud_sql', id: 'replay-trade-1', return_pct: null, status: 'active' }));
    });

    await page.getByRole('button', { name: /Mark Entry/ }).click();
    await expect(page.getByText('Click chart to set entry price')).toBeVisible();

    const canvas = page.locator('canvas').first();
    const box = await canvas.boundingBox();
    expect(box).not.toBeNull();

    await page.mouse.click(box!.x + box!.width * 0.5, box!.y + box!.height * 0.5);
    await expect(page.getByText('Select CALL or PUT')).toBeVisible();

    await page.getByRole('button', { name: 'CALL' }).click();
    await expect(page.getByText(/Click TP1/)).toBeVisible();
    // See charts-cards.spec.ts's mark-entry test for why this wait is
    // needed: CandlestickChart's click-subscription effect re-subscribes
    // via a passive useEffect that lags a beat behind the drawingStep text.
    await page.waitForTimeout(1500);

    await page.mouse.click(box!.x + box!.width * 0.6, box!.y + box!.height * 0.3);
    await expect(page.getByText(/Click TP2/)).toBeVisible();
    await page.waitForTimeout(500);

    await page.keyboard.press('Escape');
    await expect(page.getByText(/Click Stop Loss/)).toBeVisible();
    await page.waitForTimeout(500);
    await page.keyboard.press('Escape');

    await expect.poll(() => capturedBody, { timeout: 10_000 }).not.toBeNull();

    expect(capturedBody.ticker).toBe('IWM');
    expect(capturedBody.direction).toBe('CALL');
    expect(capturedBody.source).toBe('replay');
    expect(capturedBody.session_id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
    );
    // Entry epoch pinned to the LAST REVEALED bar (index 16, 09:31 + 16min
    // = 09:47) regardless of where on the canvas the entry click landed.
    expect(capturedBody.entry_date).toBe('2026-04-25');
    expect(capturedBody.entry_time).toBe('09:47');
  });

  test('Stop resets to the idle "Start replay" button and re-fits the full day', async ({ page }) => {
    await page.goto('/charts');
    await page.waitForLoadState('networkidle');

    await page.getByTestId('replay-start-btn').click();
    await expect(page.getByTestId('replay-controls')).toBeVisible();

    await page.getByTestId('replay-stop-btn').click();
    await expect(page.getByTestId('replay-start-btn')).toBeVisible();
    await expect(page.getByTestId('replay-controls')).not.toBeVisible();

    // Both trades visible again — the replay cutoff no longer applies.
    await expect(page.getByText('Trades (2)')).toBeVisible();
    const sigButton = page.getByRole('button', { name: /^Sig$/ });
    await expect(sigButton).toBeEnabled();
  });
});
