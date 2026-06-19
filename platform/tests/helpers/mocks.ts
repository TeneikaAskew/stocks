/**
 * Shared API mock helpers for E2E tests.
 *
 * Every page hits a few cross-cutting endpoints (live status pill, health
 * check). Each spec also tends to call the dashboard brief on first paint
 * because the header/sidebar reads it. Centralizing the boilerplate keeps
 * specs short and the mock surface explicit.
 */
import type { Page } from '@playwright/test';

const ok = (body: unknown) => ({
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify(body),
});

const notFound = () => ({
  status: 404,
  contentType: 'application/json',
  body: JSON.stringify({ detail: 'not found' }),
});

/** Apply mocks for endpoints every page hits — call from beforeEach. */
export async function mockCommon(page: Page) {
  await page.route('**/api/health', (r) => r.fulfill(ok({ status: 'ok', cloud_sql: false })));
  // Auth config probe — `open` mode keeps the gate inert (renders the app
  // directly), matching iap/local behaviour. The login page only appears in
  // `firebase` mode.
  await page.route('**/api/config/firebase', (r) =>
    r.fulfill(ok({ authMode: 'open', firebase: null }))
  );
  await page.route('**/api/me', (r) => r.fulfill(ok({ email: null, is_admin: false })));
  await page.route('**/api/live/status', (r) =>
    r.fulfill(ok({ session: 'closed', is_open: false, ts: '2026-04-25T20:00:00Z' }))
  );
  await page.route('**/api/dashboard/brief/*', (r) => r.fulfill(notFound()));
  await page.route('**/api/insights/watchlist*', (r) =>
    r.fulfill(ok({ tickers: ['IWM'], generated_at: '2026-04-25T20:00:00Z' }))
  );
}

export const M = { ok, notFound };
