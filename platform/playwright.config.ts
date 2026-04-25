import { defineConfig, devices } from '@playwright/test';
import * as path from 'node:path';

const CLOUD_RUN_URL =
  process.env.CLOUD_RUN_URL ?? 'https://trading-platform-5sjtb3yl7a-ue.a.run.app';
const IAP_STATE = path.join(__dirname, 'tests', '.auth', 'iap-state.json');

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  timeout: 30_000,
  projects: [
    // Default: existing local-dev tests against http://localhost:5173.
    {
      name: 'chromium',
      testIgnore: /\.setup\.ts$/,
      use: {
        ...devices['Desktop Chrome'],
        baseURL: 'http://localhost:5173',
        headless: true,
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
