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
    // First uncached call may run the full Cloud SQL audit — raise timeout
    test.setTimeout(90_000);
    const res = await request.get(API + '/api/health/freshness', { timeout: 80_000 });
    expect(res.ok(), `/api/health/freshness returned ${res.status()}`).toBeTruthy();
    const json = await res.json();
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

    // Previous session fields landed during the April 10 gap fix. They live
    // under the `week` sub-object, not the top level.
    expect(ref).toHaveProperty('week');
    expect(ref.week).toHaveProperty('prev_session_close');
    expect(ref.week).toHaveProperty('prev_session_date');
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
    expect(json).toHaveProperty('is_open');
    expect(json).toHaveProperty('session');
  });

  test('GET /api/signals/IWM responds without a server error', async ({ request }) => {
    const res = await request.get(API + '/api/signals/IWM?limit=5');
    expect(res.status(), `/api/signals/IWM returned ${res.status()}`).toBeLessThan(500);
  });

  test('GET /api/playbook/rules responds without a server error', async ({ request }) => {
    const res = await request.get(API + '/api/playbook/rules');
    expect(res.status()).toBeLessThan(500);
  });

  test('GET /api/options/IWM responds without a server error', async ({ request }) => {
    const res = await request.get(API + '/api/options/IWM?limit=5');
    expect(res.status()).toBeLessThan(500);
  });

  test('GET /api/backtest/all/IWM responds without a server error', async ({ request }) => {
    // Real endpoint (no /runs route — that was a memory-based misconception)
    const res = await request.get(API + '/api/backtest/all/IWM');
    expect(res.status()).toBeLessThan(500);
  });
});

test.describe('AI Insights — point-in-time replay validation', () => {
  // These tests exercise the as_of query-string parser without burning
  // an LLM run: both the malformed and the future-dated cases must be
  // rejected before any pipeline work happens, so a 400 is the proof
  // the validator is wired in. We intentionally don't post a valid
  // cutoff here — that would actually enqueue a Cloud Tasks message.

  test('POST /api/insights/report/IWM/refresh?as_of=garbage rejects with 400', async ({
    request,
  }) => {
    const res = await request.post(
      API + '/api/insights/report/IWM/refresh?as_of=not-a-date'
    );
    expect(res.status()).toBe(400);
    const body = await res.json();
    expect(JSON.stringify(body)).toMatch(/as_of/i);
  });

  test('POST /api/insights/report/IWM/refresh?as_of=2099-01-01 rejects future cutoff', async ({
    request,
  }) => {
    const res = await request.post(
      API + '/api/insights/report/IWM/refresh?as_of=2099-01-01'
    );
    expect(res.status()).toBe(400);
    const body = await res.json();
    expect(JSON.stringify(body)).toMatch(/future/i);
  });
});
