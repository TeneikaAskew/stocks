/**
 * Interactive IAP authentication setup.
 *
 * Run once (or whenever IAP cookies expire) to populate
 * tests/.auth/iap-state.json. Subsequent `npm run e2e:cloud` runs reuse
 * those cookies headlessly.
 *
 *   npm run e2e:cloud:auth      # opens a real browser; sign into bictech.org
 *   npm run e2e:cloud           # headless tests against the Cloud Run URL
 */
import { test as setup } from '@playwright/test';
import * as fs from 'node:fs';
import * as path from 'node:path';

const authFile = path.join(__dirname, '.auth', 'iap-state.json');

setup('authenticate to IAP', async ({ page }) => {
  fs.mkdirSync(path.dirname(authFile), { recursive: true });

  // Visiting any path triggers the IAP → Google OAuth redirect chain.
  await page.goto('/');

  // Sign-in is interactive; wait until we land back on the deployed app
  // (i.e. the URL is no longer on accounts.google.com or iap.googleapis.com).
  await page.waitForURL(
    (url) => url.host.endsWith('.run.app') && !url.pathname.startsWith('/oauth'),
    { timeout: 5 * 60 * 1000 }
  );

  await page.context().storageState({ path: authFile });
  // eslint-disable-next-line no-console
  console.log(`[iap-setup] saved cookies → ${authFile}`);
});
