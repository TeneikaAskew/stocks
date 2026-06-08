import { defineConfig, devices } from '@playwright/test';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const CLOUD_RUN_URL =
  process.env.CLOUD_RUN_URL ?? 'https://trading-platform-5sjtb3yl7a-ue.a.run.app';
const IAP_STATE = path.join(__dirname, 'tests', '.auth', 'iap-state.json');

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  timeout: 30_000,
  // For local-dev specs (project=chromium), Playwright reuses an already-running
  // Vite server. If you don't have one up, set PLAYWRIGHT_START_VITE=1 to have
  // Playwright boot it. The cloud project hits Cloud Run directly so this is a
  // no-op there.
  webServer: process.env.PLAYWRIGHT_START_VITE
    ? {
        command: 'npm run dev',
        url: 'http://localhost:5173',
        reuseExistingServer: true,
        timeout: 60_000,
      }
    : undefined,
  projects: [
    // Default: existing local-dev tests against http://localhost:5173.
    {
      name: 'chromium',
      testIgnore: /\.setup\.ts$/,
      use: {
        ...devices['Desktop Chrome'],
        baseURL: 'http://localhost:5173',
        headless: true,
        // The headless shell lacks system root CAs, so the Montserrat
        // Google-Fonts CDN load throws ERR_CERT and trips the "no console
        // errors" assertions. Accept certs in this mocked local project
        // (does not affect the cloud project, which uses real IAP).
        ignoreHTTPSErrors: true,
      },
    },
    // Interactive: open a real browser, complete Google sign-in, save cookies.
    // Run via `npm run e2e:cloud:auth`. Skipped by the default test command.
    {
      name: 'iap-setup',
      testMatch: /\.setup\.ts$/,
      use: {
        ...devices['Desktop Chrome'],
        baseURL: CLOUD_RUN_URL,
        headless: false,
      },
    },
    // Headless tests against the deployed Cloud Run URL using saved IAP cookies.
    // Run via `npm run e2e:cloud`. Requires `iap-setup` to have run first.
    {
      name: 'cloud',
      testIgnore: /\.setup\.ts$/,
      use: {
        ...devices['Desktop Chrome'],
        baseURL: CLOUD_RUN_URL,
        headless: true,
        storageState: IAP_STATE,
      },
    },
  ],
});
