// Screenshot-evidence variant of the local e2e suite: identical to
// playwright.config.ts's chromium project but captures a screenshot for
// EVERY test (not just failures). Used for visual verification runs:
//   PLAYWRIGHT_START_VITE=1 npx playwright test --config=playwright.screens.config.ts
// Not referenced by CI; the default `npx playwright test` is unaffected.
import baseConfig from './playwright.config';
import { defineConfig } from '@playwright/test';

export default defineConfig({
  ...baseConfig,
  projects: (baseConfig.projects ?? [])
    .filter((p) => p.name === 'chromium')
    .map((p) => ({ ...p, use: { ...p.use, screenshot: 'on' as const } })),
});
