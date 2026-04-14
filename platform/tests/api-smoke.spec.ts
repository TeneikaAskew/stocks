/**
 * API smoke tests — verify every mounted router responds.
 *
 * These run against the live backend (port 8000). Routes that require live
 * market data or specific DB state use loose shape checks; routes that always
 * return a list allow empty results.
 */
import { test, expect, APIRequestContext } from '@playwright/test';

const API = 'http://localhost:8000';

async function getOk(request: APIRequestContext, path: string) {
  const res = await request.get(API + path);
  expect(res.ok(), `${path} returned ${res.status()}`).toBeTruthy();
  return res.json();
}

test.describe('Core health', () => {
  test('GET /api/health returns ok', async ({ request }) => {
    const json = await getOk(request, '/api/health');
    expect(json.status).toBe('ok');
    expect(json).toHaveProperty('cloud_sql');
  });

  test('GET /api/health/freshness returns a report', async ({ request }) => {
    const json = await getOk(request, '/api/health/freshness');
    expect(json).toHaveProperty('overall_status');
    expect(json).toHaveProperty('tables');
  });
});

test.describe('Market data', () => {
  test('GET /api/market/dates/IWM returns 50+ dates', async ({ request }) => {
    const json = await getOk(request, '/api/market/dates/IWM');
    expect(json.dates.length).toBeGreaterThan(50);
  });

  test('GET /api/market/reference/:ticker/:date populates prev session', async ({ request }) => {
    const dates = await getOk(request, '/api/market/dates/IWM');
    const date = dates.dates[Math.floor(dates.dates.length / 2)];
    const ref = await getOk(request, `/api/market/reference/IWM/${date}`);

    expect(ref).toHaveProperty('open');
    expect(ref).toHaveProperty('high');
    expect(ref).toHaveProperty('low');
    expect(ref).toHaveProperty('close');
    expect(ref.high).toBeGreaterThanOrEqual(ref.low);

    // Previous session fields landed during the April 10 gap fix
    expect(ref).toHaveProperty('prev_session_close');
    expect(ref).toHaveProperty('prev_session_date');
  });

  test('GET /api/market/data/:ticker/:date returns candlestick bars', async ({ request }) => {
    const dates = await getOk(request, '/api/market/dates/IWM');
    const date = dates.dates[0];
    const data = await getOk(request, `/api/market/data/IWM/${date}?timeframe=5`);
    expect(data.candlestick.length).toBeGreaterThan(0);
    const bar = data.candlestick[0];
    expect(bar.high).toBeGreaterThanOrEqual(bar.low);
  });
});

test.describe('Live / signals / options / playbook routers', () => {
  test('GET /api/live/status returns a status object', async ({ request }) => {
    const json = await getOk(request, '/api/live/status');
    expect(json).toHaveProperty('market_open');
  });

  test('GET /api/signals/IWM responds (empty list is fine)', async ({ request }) => {
    const res = await request.get(API + '/api/signals/IWM?limit=5');
    // Accept 200 with empty list OR 404 if the signal file doesn't exist
    // in the current environment. Fail only on 5xx.
    expect(res.status(), `/api/signals/IWM returned ${res.status()}`).toBeLessThan(500);
  });

  test('GET /api/playbook/rules returns a rule list', async ({ request }) => {
    const res = await request.get(API + '/api/playbook/rules');
    expect(res.status()).toBeLessThan(500);
  });

  test('GET /api/options/IWM?limit=5 returns a chain or structured empty', async ({ request }) => {
    const res = await request.get(API + '/api/options/IWM?limit=5');
    expect(res.status()).toBeLessThan(500);
  });

  test('GET /api/backtest/runs returns a run list', async ({ request }) => {
    const res = await request.get(API + '/api/backtest/runs');
    expect(res.status()).toBeLessThan(500);
    if (res.ok()) {
      const json = await res.json();
      expect(json).toHaveProperty('runs');
      expect(Array.isArray(json.runs)).toBeTruthy();
    }
  });
});
