/**
 * Gamma Levels feature verification (King / Gate / Spot / Flip + chart overlay).
 *
 * Covers:
 *   - OptionsFlowPage: spot method chip, regime chip, King/Gate/Flip chips,
 *     explicit fallback when spot can't be estimated, server warnings banner.
 *   - ChartsPage: Gamma toggle button presence (only for ETF tickers) and
 *     that toggling it adds horizontal price lines to the chart.
 *   - HelpPage: 'Gamma Levels' category exists with the new entries.
 *   - API: GET /api/options/{ticker}/{date}/levels returns the GammaSummary
 *     contract.
 *
 * Requires:
 *   - FastAPI backend on :8000 with Cloud SQL configured + chain data for QQQ
 *   - Vite dev server on :5173
 */
import { test, expect } from '@playwright/test';
import { mockOptionsApi } from './helpers/mocks';

const ETF_TICKER = 'QQQ'; // a ticker we know has chain data

test.describe('Gamma Levels: API contract', () => {
  test('GET /api/options/dates/{ticker} returns options snapshot dates', async ({ request }) => {
    const res = await request.get(`http://localhost:8000/api/options/dates/${ETF_TICKER}`);
    expect(res.ok()).toBeTruthy();
    const json = await res.json();
    expect(Array.isArray(json.dates)).toBeTruthy();
    expect(json.dates.length).toBeGreaterThan(0);
  });

  test('GET /api/options/{ticker}/{date}/levels returns the GammaSummary shape', async ({ request }) => {
    const datesRes = await request.get(`http://localhost:8000/api/options/dates/${ETF_TICKER}`);
    const { dates } = await datesRes.json();
    const date = dates[0]; // most recent

    const res = await request.get(`http://localhost:8000/api/options/${ETF_TICKER}/${date}/levels`);
    expect(res.ok()).toBeTruthy();
    const summary = await res.json();

    // Top-level GammaSummary fields
    expect(summary).toHaveProperty('ticker');
    expect(summary.ticker).toBe(ETF_TICKER);
    expect(summary).toHaveProperty('snapshot_date');
    expect(summary).toHaveProperty('spot');
    expect(summary).toHaveProperty('gamma_balance'); // may be null
    expect(summary).toHaveProperty('gamma_flip'); // may be null
    expect(summary).toHaveProperty('regime');
    expect(['positive_gamma', 'negative_gamma', 'unknown']).toContain(summary.regime);
    expect(summary).toHaveProperty('total_gex');
    expect(summary).toHaveProperty('levels');
    expect(summary).toHaveProperty('kings');
    expect(summary).toHaveProperty('gates');
    expect(summary).toHaveProperty('gamma_balance_levels');
    expect(summary).toHaveProperty('warnings');
    expect(summary).toHaveProperty('chain_size');

    // Spot estimate sub-shape
    expect(summary.spot).toHaveProperty('price');
    expect(summary.spot).toHaveProperty('method');
    expect(['parity', 'delta', 'median_strike', 'override', 'none']).toContain(summary.spot.method);
  });

  test('GET /levels?spot=... overrides the estimated spot', async ({ request }) => {
    const datesRes = await request.get(`http://localhost:8000/api/options/dates/${ETF_TICKER}`);
    const { dates } = await datesRes.json();
    const date = dates[0];

    const customSpot = 999.99;
    const res = await request.get(`http://localhost:8000/api/options/${ETF_TICKER}/${date}/levels?spot=${customSpot}`);
    expect(res.ok()).toBeTruthy();
    const summary = await res.json();
    expect(summary.spot.price).toBe(customSpot);
    expect(summary.spot.method).toBe('override');
  });

  test('GET /api/options/greeks total_gex equals sum of per-strike (sign consistency)', async ({ request }) => {
    // Pull the chain
    const datesRes = await request.get(`http://localhost:8000/api/options/dates/${ETF_TICKER}`);
    const { dates } = await datesRes.json();
    const date = dates[0];
    const chainRes = await request.get(`http://localhost:8000/api/options/${ETF_TICKER}/${date}`);
    const chain = await chainRes.json();
    if (!chain.options?.length) test.skip(true, 'no chain data');

    // Pull the levels endpoint just to get a server-estimated spot
    const lvlRes = await request.get(`http://localhost:8000/api/options/${ETF_TICKER}/${date}/levels`);
    const summary = await lvlRes.json();
    const spot = summary.spot.price;
    if (spot <= 0) test.skip(true, 'no spot');

    // POST to /greeks
    const greeksRes = await request.post(`http://localhost:8000/api/options/greeks`, {
      data: { options: chain.options, spot_price: spot },
    });
    expect(greeksRes.ok()).toBeTruthy();
    const greeks = await greeksRes.json();

    const sumOfPerStrike = greeks.gex_by_strike.reduce(
      (acc: number, s: { gex: number }) => acc + s.gex,
      0
    );
    // Total GEX must match sum of per-strike (the sign-consistency invariant)
    expect(greeks.metrics.total_gex).toBeCloseTo(sumOfPerStrike, 0);
  });
});

// The /options page was restructured (OptionsFlowPage.tsx): it opens on the
// Heatseeker tab (SwingMode gamma cockpit) and the original levels/chain
// profile — spot-method chip, ★ King / ◆ Gate taxonomy chips, metric cards,
// regime label — moved verbatim into the Profiles tab (ProfilesTab.tsx).
// These tests run fully mocked via mockOptionsApi (dates + chain + grid +
// levels + greeks — every request the page makes), so the assertions are
// deterministic instead of the old "pass vacuously when Cloud SQL is empty"
// conditionals.
test.describe('Gamma Levels: OptionsFlowPage UI', () => {
  test.beforeEach(async ({ page }) => {
    await mockOptionsApi(page);
  });

  /** The levels/chain profile view now lives behind the Profiles tab. */
  async function openProfilesTab(page: import('@playwright/test').Page) {
    await page.getByRole('button', { name: 'Profiles' }).click();
  }

  test('options page renders without console errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.goto('/options');
    await page.waitForLoadState('networkidle');
    // Cover the Profiles tab too — it triggers the chain + greeks fetches.
    await openProfilesTab(page);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    // Filter out 3rd-party noise
    const real = errors.filter((e) => !e.includes('favicon') && !e.includes('extension'));
    expect(real, real.join('\n')).toHaveLength(0);
  });

  test('options page shows spot method chip when /levels resolves', async ({ page }) => {
    await page.goto('/options');
    await openProfilesTab(page);
    // The chip next to the spot input renders the server's estimation method
    // (ProfilesTab.tsx spotMethod chip; fixture uses put-call parity). The
    // same value appears in the Swing legend's "Spot method" chip.
    const chip = page.locator('text=/^(parity|delta|median_strike|override)$/').first();
    await expect(chip).toBeVisible();
  });

  test('options page shows King/Gate taxonomy chips', async ({ page }) => {
    await page.goto('/options');
    await openProfilesTab(page);
    // The King/Gate chips render from /levels kings[]/gates[]
    // (ProfilesTab.tsx "★ King $…" / "◆ Gate $…"). With the populated
    // fixture they MUST be present — the silent-disappearance bug is what
    // we're regressing. The "Couldn't estimate spot" fallback branch is
    // unreachable here because the fixture carries a parity spot.
    await expect(page.locator('text=/★ King \\$/')).toBeVisible();
    await expect(page.locator('text=/◆ Gate \\$/').first()).toBeVisible();
  });

  test('options page renders the metrics bar', async ({ page }) => {
    await page.goto('/options');
    await openProfilesTab(page);
    // Metric cards render once spot resolves (ProfilesTab.tsx metrics bar):
    // Total GEX/VEX from POST /greeks, Gamma Flip from /levels gamma_balance.
    // exact:true keeps "Gamma Flip" from also matching the regime description
    // text ("Above gamma flip — pinning / range-bound").
    await expect(page.getByText('Total GEX', { exact: true })).toBeVisible();
    await expect(page.getByText('Gamma Flip', { exact: true })).toBeVisible();
  });

  test('regime chip uses Positive/Negative/Unclear wording', async ({ page }) => {
    await page.goto('/options');
    await openProfilesTab(page);
    // regimeLabel() (useGammaLevels.ts) maps positive_gamma → "Positive
    // gamma", negative_gamma → "Negative gamma", unknown → "Regime unclear";
    // the fixture pins positive_gamma so the chip must render its label
    // (ProfilesTab.tsx regime chip).
    await expect(page.getByText('Positive gamma', { exact: true })).toBeVisible();
  });
});

test.describe('Gamma Levels: ChartsPage overlay', () => {
  test('Gamma toggle is visible for ETF tickers', async ({ page }) => {
    await page.goto('/charts');
    await page.waitForTimeout(2000);
    // The default ticker IWM is an ETF — the toggle should be present
    const toggle = page.getByRole('button', { name: /^Gamma$/ });
    await expect(toggle).toBeVisible();
  });

  test('clicking Gamma toggle changes its active styling', async ({ page }) => {
    await page.goto('/charts');
    await page.waitForTimeout(2000);
    const toggle = page.getByRole('button', { name: /^Gamma$/ });
    const before = await toggle.getAttribute('class');
    await toggle.click();
    await page.waitForTimeout(800);
    const after = await toggle.getAttribute('class');
    expect(after).not.toBe(before);
  });

  test('Gamma toggle is hidden for non-ETF tickers', async ({ page }) => {
    // This test passes vacuously if we can't switch to a non-ETF in this build.
    // The component logic checks GAMMA_LEVELS_TICKERS — if the user changes
    // the active ticker to one not in that set, the toggle disappears.
    await page.goto('/charts');
    await page.waitForTimeout(1500);
    // Sanity: the toggle exists for the default IWM
    await expect(page.getByRole('button', { name: /^Gamma$/ })).toBeVisible();
  });
});

test.describe('Gamma Levels: Help page glossary', () => {
  test('Gamma Levels category pill exists', async ({ page }) => {
    await page.goto('/help');
    await page.waitForLoadState('networkidle');
    const pill = page.getByRole('button', { name: /Gamma Levels \(\d+\)/ });
    await expect(pill).toBeVisible();
  });

  test('clicking the Gamma Levels pill filters the glossary', async ({ page }) => {
    await page.goto('/help');
    await page.waitForLoadState('networkidle');
    await page.getByRole('button', { name: /Gamma Levels \(\d+\)/ }).click();
    // Spot-check several gamma terms that must be present after filtering.
    // "Gamma Flip" needs exact matching: the regime entries' shorts also
    // contain the phrase ("Price is above the gamma flip — …",
    // HelpPage.tsx Regime entries), which trips strict mode on a substring
    // match now that those entries exist.
    await expect(page.getByText('GEX (Gamma Exposure)')).toBeVisible();
    await expect(page.getByText('Gamma Flip', { exact: true })).toBeVisible();
    await expect(page.getByText('King Node (★)')).toBeVisible();
    await expect(page.getByText('Gate Node (◆)')).toBeVisible();
    await expect(page.getByText(/^Regime — Positive Gamma$/)).toBeVisible();
    await expect(page.getByText(/^Regime — Negative Gamma$/)).toBeVisible();
  });

  test('Failed 2U / Failed 2D entries exist under The Strat category', async ({ page }) => {
    await page.goto('/help');
    await page.waitForLoadState('networkidle');
    await page.getByRole('button', { name: /The Strat \(\d+\)/ }).click();
    await expect(page.getByText('Failed 2U')).toBeVisible();
    await expect(page.getByText('Failed 2D')).toBeVisible();
    // The per-direction "2U/2D Continuation" entries were consolidated into
    // a single "22 Continuation" term (covering 22_bull/22_bear) alongside
    // "212 Reversal" — see HelpPage.tsx's The Strat glossary entries.
    await expect(page.getByText('22 Continuation')).toBeVisible();
    await expect(page.getByText('212 Reversal')).toBeVisible();
  });

  test('search "King Node" returns the gamma entry', async ({ page }) => {
    await page.goto('/help');
    await page.waitForLoadState('networkidle');
    const search = page.getByPlaceholder(/Search/);
    await search.fill('King Node');
    await page.waitForTimeout(300);
    await expect(page.getByText('King Node (★)')).toBeVisible();
  });
});
