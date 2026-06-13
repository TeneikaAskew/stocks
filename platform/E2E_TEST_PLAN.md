# End-to-End Test Plan — Stocks Trading Platform

> Canonical test strategy for the Obsidian Analyst redesign. Three layers —
> **frontend E2E (Playwright)**, **backend (pytest)**, and **GCP data/pipeline
> validation** — each runnable independently. Mirrors the actual harness in
> `platform/` and the repo root, so every command below is copy-pasteable.

---

## 0. Layers at a glance

| Layer | What it proves | Tooling | Where | Run command |
|---|---|---|---|---|
| **Frontend E2E** | Every route renders, the redesigned surfaces show the right data, no console errors, responsive | Playwright (chromium) + network mocks | `platform/tests/*.spec.ts` | `cd platform && npm run e2e` |
| **Frontend E2E (live)** | The deployed Cloud Run app behind IAP serves real data | Playwright (`cloud` project) | same specs, `baseURL` = Cloud Run URL | `npm run e2e:cloud:auth` then `npm run e2e:cloud` |
| **Backend unit** | `lib/` math (indicators, strat, gamma, backtest), API contracts | pytest | `tests/test_*.py` | `make test` |
| **Backend E2E / scripts** | Pipeline scripts, fetchers, signal monitor | pytest | `tests/test_e2e.py`, `tests/test_scripts_*.py` | `make test-e2e` · `make test-scripts` |
| **GCP data/pipeline** | Real Cloud SQL data exists + is fresh; jobs/services healthy | `db_query_cr.sh`, `gcloud`, `/api/health/freshness` | `scripts/`, GCP | see §4 |

---

## 1. Frontend E2E (Playwright) — primary

**Config:** `platform/playwright.config.ts` — `testDir: ./tests`, 3 projects:
- **`chromium`** (default): `baseURL=http://localhost:5173`, all `/api/**` **mocked** per-spec → no backend needed, hermetic, fast (~3 min full run).
- **`iap-setup`** / **`cloud`**: run against the live Cloud Run URL behind IAP — skipped by the default command. For the **no-IAP staging service** you can skip the interactive Google sign-in entirely — see §6.

**Mock strategy:** `tests/helpers/mocks.ts` `mockCommon(page)` stubs the cross-cutting endpoints (`/api/health`, `/api/live/status`, brief, watchlist); each spec adds its own `page.route('**/api/<endpoint>', …)` with realistic fixtures. **Fixtures must match the production response shape** (CLAUDE.md Rule 0.3) — e.g. the dashboard brief mock carries `daily_indicators.close`, the signals mock carries `analytics/summary`.

### Coverage matrix (one spec per route + cross-cutting)

| Spec | Route / surface | Asserts |
|---|---|---|
| `dashboard.spec.ts` | `/` Overview | "Overview" heading · pre-market brief · KPI tiles (prev/latest close, 2-day, RSI) · **Candles\|Area chart toggle** · perf budget |
| `signals.spec.ts` | `/signals` | **90-day Performance P&L card** (win rate / profit factor) · explorer rows · CALL/PUT · empty state |
| `insights.spec.ts` (+ Agents) | `/insights` | Briefing dossier · **Agents tab** (run cost/latency · per-role pipeline · model-routing roster · recent runs) |
| `journal.spec.ts` | `/journal` | **KPI tiles + equity curve** · add/delete trade · CSV export |
| `catalysts.spec.ts` | `/catalysts` | feed grouped by date · impact/type filter chips · sentiment |
| `options-flow.spec.ts` · `gamma-levels.spec.ts` | `/options` | Heatseeker grid · GEX/VEX · King/Gate fallback · live-AV badge |
| `live-market.spec.ts` · `charts-cards.spec.ts` · `phase1-charts.spec.ts` | `/live` `/charts` | hero tiles · candlestick canvas · reference levels |
| `playbook.spec.ts` · `reports.spec.ts` · `help.spec.ts` · `admin.spec.ts` · `admin-auth.spec.ts` | `/playbook` `/reports` `/help` `/admin` | cards · glossary · admin auth gate |
| `navigation.spec.ts` | all 12 routes | each route loads without a fatal error |
| `api-smoke.spec.ts` | API contracts | health/freshness, market dates, signals, options, backtest, insights as-of-replay rejects bad cutoffs |

### Run
```bash
cd platform
PLAYWRIGHT_START_VITE=1 npm run e2e            # auto-starts vite, runs chromium
# or, against an already-running dev server:
npm run e2e
npx playwright test --project=chromium tests/journal.spec.ts   # a single spec
```

---

## 2. Backend (pytest)

```bash
make test          # tests/test_*.py — hermetic lib/ unit tests (indicators, strat, gamma, backtest, playbook eval)
make test-scripts  # tests/test_scripts_*.py — pipeline script smoke tests
make test-e2e      # tests/test_e2e.py — heavier integration (needs deps)
```
Most `lib/` tests are hermetic (synthetic DataFrames, no network). Tests that
touch Cloud SQL are skipped/marked when `CLOUD_SQL_CONNECTION_NAME` is unset
(see CLAUDE.md Rule 0.3 — hermetic tests are necessary but not sufficient;
production smoke tests are documented in §4).

---

## 3. Cross-cutting checks (every redesigned page)

1. **No console errors** on load (several specs assert this via a `pageerror`/`console` listener).
2. **Responsive** — no horizontal overflow at 375 / 768 / 1280px (global net in `index.css`; spot-checked with the headless-overflow harness).
3. **No fabricated values** — missing data renders the `—` placeholder / "unavailable" badge, never `0` (Rule 3.7). Specs assert empty states explicitly.
4. **Theme** — dark is the default; light toggles via `data-theme`.

---

## 4. GCP data / pipeline validation

Run before trusting the live app (the deployed UI behind IAP):

```bash
# Data freshness for the tables behind each page (over 443, CR-native):
bash scripts/db_query_cr.sh -q "SELECT 'intraday' t, COUNT(*) n, MAX(ts)::text FROM market_data_intraday;
  SELECT 'insights', COUNT(*), MAX(as_of)::text FROM insight_reports;
  SELECT 'options', COUNT(*), MAX(snapshot_ts)::text FROM etf_options_snapshots;
  SELECT 'news', COUNT(*), MAX(published_ts)::text FROM news_sentiment"

# Service + freshness endpoint:
gcloud run services list --project=adept-mountain-474619-d4 --format='table(metadata.name,status.url)'
curl -s https://trading-platform-…run.app/api/health/freshness   # (behind IAP)
```
Per-page table/job/service/secret mapping: **`platform/GCP_DATA_DICTIONARY.md`**.
Known prod caveats validated there: AV-on-request endpoints require the
`av-api-key` mount (fixed via the dedicated `trading-platform-svc@` SA); Journal
`journal_entries` starts empty until a user logs trades.

---

## 5. CI gating (recommended)
- **PR to `main`**: `npm run lint` + `npm run build` + `npm run e2e` (chromium, mocked) + `make test` must pass.
- **Pre-deploy**: add the `cloud` Playwright project against a staging revision before promoting traffic.

---

## 6. Staging without IAP (passcode gate)

Prod is locked behind IAP, so live E2E against it needs the interactive Google
sign-in (`npm run e2e:cloud:auth`). To test against a deployed app **without**
that, deploy the separate public staging service and use the shared passcode.

**Architecture:** IAP on Cloud Run is service-level and can't be dropped per
revision, so staging is its own service (`trading-platform-staging`) deployed
`--allow-unauthenticated`. An app-level passcode gate re-protects the API:
- `api/auth_bypass.py` — middleware + `POST /api/auth/bypass` + `/api/auth/logout`. Inert unless `ALLOW_AUTH_BYPASS=1` (set only on the staging service), so prod/local are untouched.
- `/api/me` returns `auth_bypass_allowed: true` on staging → the React `<AuthGate>` shows the sign-in screen (`src/components/auth/`). A correct passcode sets an HttpOnly cookie and the app renders as a guest.

**Deploy it (operator, run.admin):**
```bash
# 1. Create the passcode secret + let the runtime SA read it (one-time)
printf '%s' 'YOUR_PASSCODE' | gcloud secrets create staging-passcode \
  --data-file=- --project=adept-mountain-474619-d4
gcloud secrets add-iam-policy-binding staging-passcode \
  --member="serviceAccount:trading-platform-svc@adept-mountain-474619-d4.iam.gserviceaccount.com" \
  --role=roles/secretmanager.secretAccessor --project=adept-mountain-474619-d4
# 2. Deploy the public, passcode-gated staging service (prod untouched)
DB_USER=trading_user DB_NAME=trading STAGING_SERVICE=1 ./platform/deploy.sh
```

**Test against it (no Google sign-in):** point Playwright's `cloud` project at
the staging URL and mint the bypass cookie via the passcode instead of IAP:
```bash
STAGING_URL="https://trading-platform-staging-….run.app"
# Grab the HttpOnly bypass cookie with one POST, save it as Playwright storage state:
curl -sS -c - -X POST "$STAGING_URL/api/auth/bypass" \
  -H 'Content-Type: application/json' -d '{"passcode":"YOUR_PASSCODE"}' >/dev/null
CLOUD_RUN_URL="$STAGING_URL" npm run e2e:cloud   # specs run as the staging guest
```
(or just open `$STAGING_URL` in a browser and type the passcode once.)
