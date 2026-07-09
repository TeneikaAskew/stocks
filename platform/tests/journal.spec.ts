/**
 * E2E: Trade Journal ("/journal") — list trades, add/delete, export CSV.
 */
import { test, expect } from '@playwright/test';
import { mockCommon, M } from './helpers/mocks';

const MOCK_TRADES = {
  ticker: 'IWM',
  count: 1,
  trades: [
    {
      trade_id: '00000000-0000-0000-0000-000000000001',
      ticker: 'IWM',
      direction: 'long',
      entry_ts: '2026-04-24T14:00:00Z',
      exit_ts: '2026-04-24T15:30:00Z',
      entry_price: 220.0,
      exit_price: 222.5,
      shares: 100,
      pnl: 250.0,
      notes: 'Breakout above PD high.',
    },
  ],
};

// One closed trade + one ACTIVE (null-exit, chart-marked) trade — the
// shared GET /api/journal/trades/{ticker} endpoint returns these for
// open positions and JournalPage must render both without crashing.
const MOCK_TRADES_WITH_ACTIVE = {
  ticker: 'IWM',
  count: 2,
  trades: [
    {
      id: '00000000-0000-0000-0000-000000000001',
      ticker: 'IWM',
      direction: 'CALL',
      entry_ts: '2026-04-24T14:00:00Z',
      exit_ts: '2026-04-24T15:30:00Z',
      entry_price: 220.0,
      exit_price: 222.5,
      return_pct: 1.14,
      notes: 'Breakout above PD high.',
      status: 'win',
      source: 'manual',
    },
    {
      id: '00000000-0000-0000-0000-000000000002',
      ticker: 'IWM',
      direction: 'PUT',
      entry_ts: '2026-04-25T09:31:00Z',
      exit_ts: null,
      entry_price: 218.0,
      exit_price: null,
      return_pct: null,
      notes: 'Still open — chart-marked.',
      status: 'active',
      source: 'chart',
      take_profits: [216, 214],
      stop_loss: 220,
      session_id: null,
    },
  ],
};

test.describe('Trade Journal', () => {
  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/journal/trades/IWM*', (r) => r.fulfill(M.ok(MOCK_TRADES)));
  });

  test('renders journal heading', async ({ page }) => {
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('h1, h2').filter({ hasText: /journal/i }).first()).toBeVisible();
  });

  test('lists existing trades', async ({ page }) => {
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/breakout above pd high/i)).toBeVisible();
  });

  test('shows empty state when no trades', async ({ page }) => {
    await page.route('**/api/journal/trades/IWM*', (r) =>
      r.fulfill(M.ok({ ticker: 'IWM', count: 0, trades: [] }))
    );
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/no.*trade|empty|add.*trade/i).first()).toBeVisible();
  });

  test('renders within 5s perf budget', async ({ page }) => {
    const start = Date.now();
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');
    expect(Date.now() - start).toBeLessThan(5000);
  });

  test('renders an active (null-exit) trade alongside a closed one without crashing', async ({ page }) => {
    await page.route('**/api/journal/trades/IWM*', (r) => r.fulfill(M.ok(MOCK_TRADES_WITH_ACTIVE)));
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');

    // Both trades render — the closed one and the active (null-exit) one.
    await expect(page.getByText(/breakout above pd high/i)).toBeVisible();
    await expect(page.getByText(/still open — chart-marked/i)).toBeVisible();

    // The active row shows a status chip explaining the dashes.
    await expect(page.getByText('active', { exact: true })).toBeVisible();
  });
});

// ── Task 5.3: practice-trade (bar-replay-trainer) analytics hygiene ──────
// Mixed manual + replay rows: source:'replay' entries are excluded from
// every stats aggregate by default, foldable back in via the "Include
// practice sessions" toggle.
test.describe('Trade Journal — practice-trade analytics hygiene (Task 5.3)', () => {
  const MANUAL_TRADE = {
    id: '00000000-0000-0000-0000-0000000000a1',
    ticker: 'IWM',
    direction: 'CALL',
    entry_ts: '2026-04-24T14:00:00Z',
    exit_ts: '2026-04-24T15:30:00Z',
    entry_price: 220.0,
    exit_price: 242.0,
    return_pct: 10.0,
    notes: 'Manual win trade.',
    status: 'win',
    source: 'manual',
    session_id: null,
  };
  const REPLAY_TRADE = {
    id: '00000000-0000-0000-0000-0000000000a2',
    ticker: 'IWM',
    direction: 'PUT',
    entry_ts: '2026-04-25T09:36:00',
    exit_ts: '2026-04-25T09:40:00',
    entry_price: 220.25,
    exit_price: 330.375,
    return_pct: -50.0,
    notes: 'Practice replay trade.',
    status: 'loss',
    source: 'replay',
    session_id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
  };
  const MIXED_TRADES = { ticker: 'IWM', source: 'cloud_sql', count: 2, trades: [MANUAL_TRADE, REPLAY_TRADE] };

  test.beforeEach(async ({ page }) => {
    await mockCommon(page);
    await page.route('**/api/journal/trades/IWM*', (r) => r.fulfill(M.ok(MIXED_TRADES)));
  });

  test('excludes replay trades from stats by default; toggle folds them in; exclusion note mentions practice trades', async ({ page }) => {
    await page.goto('/journal');
    await page.waitForLoadState('networkidle');

    // Default: only the manual trade counts. avg == total == its own return
    // (a single trade), and the Trades tile sub-label reads 1W/0L.
    await expect(page.getByText('+10.00%').first()).toBeVisible();
    await expect(page.getByText('1W / 0L')).toBeVisible();
    const note = page.getByTestId('replay-exclusion-note');
    await expect(note).toBeVisible();
    await expect(note).toHaveText(/practice trade/i);

    // Toggle on -> both trades count. avg return flips to a DIFFERENT
    // specific number: (10 + -50) / 2 = -20.00%; total P&L = -40.00%;
    // Trades tile sub-label becomes 1W/1L.
    await page.getByTestId('include-replay-toggle').check();
    await expect(page.getByText('-20.00%').first()).toBeVisible();
    await expect(page.getByText('-40.00%')).toBeVisible();
    await expect(page.getByText('1W / 1L')).toBeVisible();
    await expect(note).not.toBeVisible();
  });
});
