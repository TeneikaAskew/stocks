# Site Traceability Matrix

**Last reviewed:** unknown · **Owner:** TBD

## How to read this

This document has one section per area, in navigation order. Each area carries a Checklist
table, what gets ticked, and a Chain table, where that element's data comes from. Gates are
defined in this document's Gates section. The element ID is the join to the UI spec.

## Site outline

- **TRADING**
  - [Dashboard](#04--dashboard) · `/dashboard`
- **MARKET**
  - [Live](#05--live-market) · `/live`
  - [Charts](#06--charts) · `/charts`
  - [Options Flow](#07--options-flow) · `/options`
  - [Signals](#08--signals) · `/signals`
- **INTELLIGENCE**
  - [AI Insights](#09--ai-insights) · `/insights`
  - [Catalysts](#10--catalysts) · `/catalysts`
- **LEARN**
  - [Playbook](#11--playbook) · `/playbook`
  - [Reports](#12--reports) · `/reports`
  - [Journal](#13--journal) · `/journal`
- **SUPPORT**
  - [Admin](#14--admin) · `/admin`
  - [Settings](#15--settings) · `/settings`
  - [Help & Glossary](#16--help-and-glossary) · `/help`
  - [FAQ](#01--landing) · `/#faq`
- [Landing](#01--landing) · `/`
- [AuthGate](#02--authgate-and-sign-in) · in-route state on every app route
- [AppShell](#03--appshell) · layout for the 13 app pages
- [SHARED](#00--shared-under-every-page) · all

## Progress

| Area | Rows | S | T | V | Te |
|---|---|---|---|---|---|
| 00 · Shared, under every page | 8 | 0 | 0 | 0 | 0 |
| 01 · Landing | 13 | 0 | 0 | 0 | 0 |
| 02 · AuthGate and sign-in | 10 | 0 | 0 | 0 | 0 |
| 03 · AppShell | 16 | 0 | 0 | 0 | 0 |
| 04 · Dashboard | 21 | 0 | 0 | 0 | 0 |
| 05 · Live Market | 13 | 0 | 0 | 0 | 0 |
| 06 · Charts | 17 | 0 | 0 | 0 | 0 |
| 07 · Options Flow | 13 | 0 | 0 | 0 | 0 |
| 08 · Signals | 12 | 0 | 0 | 0 | 0 |
| 09 · AI Insights | 15 | 0 | 0 | 0 | 0 |
| 10 · Catalysts | 14 | 0 | 0 | 0 | 0 |
| 11 · Playbook | 10 | 0 | 0 | 0 | 0 |
| 12 · Reports | 10 | 0 | 0 | 0 | 0 |
| 13 · Journal | 16 | 0 | 0 | 0 | 0 |
| 14 · Admin | 13 | 0 | 0 | 0 | 0 |
| 15 · Settings | 13 | 0 | 0 | 0 | 0 |
| 16 · Help and Glossary | 8 | 0 | 0 | 0 | 0 |
| Total | 222 | 0 | 0 | 0 | 0 |

```bash
# whole document; run between two "## NN ·" headings for one area
awk -F'|' '$2 ~ /^ *[A-Z]+-[0-9]+ *$/ && $4 ~ /\[[ x]\]/ {
  n++; s+=($4~/x/); t+=($5~/x/); v+=($6~/x/); te+=($7~/x/)
} END { print n, s, t, v, te }' docs/product/03-SITE-TRACEABILITY.md
```

## Gates

**S, Specified.** The element's entry under UI-SCREENS.md exists with acceptance criteria a
test can be written from, its states, and its data contract. Evidence: the entry's anchor.

**T, Traced.** The Chain row is complete and every citation resolves: endpoint in the vendored
OpenAPI snapshot, handler file and line, tables in `gcp/schema.sql`, producer job and
schedule in `gcp/deploy.sh`, test files. `none` is allowed only with a reason. Evidence: the
date and commit of the verification.

**V, Validated.** The element was observed working against real data through a production
path: a recorded request and response on staging, a `scripts/db_query_cr.sh` result showing
the rows the page needs, or a replay flag (`REPLAY_DATE`, `BRIEF_AS_OF`, `INSIGHT_AS_OF`) for
pipeline-produced data. Reading the code never counts (CLAUDE.md §3.11). Evidence: a link to
the PR or issue comment holding the command and its output, with the date.

**Te, Tested.** Automated tests cover the element and each of its states at every layer the
chain crosses, they pass, and the suite they belong to runs on pull requests in its repo.
Today: stocks pytest runs in the Backtest Pipeline workflow on pull requests to `main`;
solyra Vitest runs in solyra CI; solyra Playwright does not run in CI (solyra#28 is open).
A Playwright-only element therefore cannot tick Te until that closes. The gate shows the
blocker instead of hiding it. Evidence: test file links and a CI run link.

Rules:

- V requires T. Te requires S. S and T are independent.
- A tick is a claim with an evidence entry and date in the same commit.
- Nothing un-ticks automatically. The registry drift check queues the document when its
  declared code paths move; the flagged area's V and Te are then re-earned, not carried.

## 00 · Shared, under every page

UI spec: [UI-SCREENS.md § Cross-cutting specs](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md#cross-cutting-specs)
· Capability: [FEAT-AUTH-001](02-FEATURE-CATALOG.md#feat-auth-001), [FEAT-DATA-001](02-FEATURE-CATALOG.md#feat-data-001), [FEAT-DEPLOY-001](02-FEATURE-CATALOG.md#feat-deploy-001), [FEAT-OPS-001](02-FEATURE-CATALOG.md#feat-ops-001), [FEAT-UI-001](02-FEATURE-CATALOG.md#feat-ui-001)
· Requirements: REQ-UX-001, REQ-ACCESS-001 · Route: all · Status: FEAT-AUTH-001 Production but needs remediation · FEAT-DATA-001 Production but needs remediation · FEAT-DEPLOY-001 Production but needs remediation · FEAT-OPS-001 Incomplete · FEAT-UI-001 Production but needs remediation

### Checklist
| ID | Element | S | T | V | Te | Evidence |
|---|---|---|---|---|---|---|
| SHARED-01 | API service and auth middleware (solyra-api-staging, solyra-api-prod, AUTH_MODE) | [ ] | [ ] | [ ] | [ ] | |
| SHARED-02 | Open prefixes kept in sync (api/auth.py and authedFetch OPEN_PREFIXES) | [ ] | [ ] | [ ] | [ ] | |
| SHARED-03 | Data path: authedFetch, apiTargets, Vite proxy, staging fallback | [ ] | [ ] | [ ] | [ ] | |
| SHARED-04 | Mock mode and demo-data banners | [ ] | [ ] | [ ] | [ ] | |
| SHARED-05 | React Query defaults (five-minute staleness, one retry) | [ ] | [ ] | [ ] | [ ] | |
| SHARED-06 | Failure lane: job log, Cloud Logging sink, Pub/Sub, failure-notifier, GitHub issue | [ ] | [ ] | [ ] | [ ] | |
| SHARED-07 | Freshness watchdog and /api/health/freshness | [ ] | [ ] | [ ] | [ ] | |
| SHARED-08 | Liveness: /api/health | [ ] | [ ] | [ ] | [ ] | |

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|
| SHARED-01 | every /api/* route | [auth.py:188](../../platform/api/auth.py#L188) `auth_middleware` → `platform/api/auth.py` | none | Cloud Run services `solyra-api-prod` (IAP, `AUTH_MODE=iap`) · `solyra-api-staging` (public, `AUTH_MODE=firebase`) · service account `trading-platform-svc@` ([platform/deploy.sh](../../platform/deploy.sh)) | Firebase Auth (staging) · Google IAP (prod) | [test_platform_auth.py](../../tests/api/test_platform_auth.py) · [test_route_coverage.py](../../tests/api/test_route_coverage.py) · solyra [auth-gate.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/auth-gate.spec.ts) |
| SHARED-02 | | [auth.py:69](../../platform/api/auth.py#L69) `_OPEN_API_EXACT`/`_OPEN_API_PREFIXES` → `platform/api/auth.py` | none | | | [test_platform_auth.py](../../tests/api/test_platform_auth.py) · solyra [authedFetch.test.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/lib/authedFetch.test.ts) |
| SHARED-03 | every /api/* route | solyra [authedFetch.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/lib/authedFetch.ts), [apiTargets.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/lib/apiTargets.ts), [vite.config.ts](https://github.com/TeneikaAskew/solyra/blob/main/vite.config.ts) (dev-proxy probe) | none | `solyra-api-staging` (the fallback target `STAGING_API` re-points to from a static host) | Lovable (the static host that triggers the fallback) | solyra [authedFetch.test.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/lib/authedFetch.test.ts) |
| SHARED-04 | every /api/* route (short-circuited, never reaches the network) | | none | | | solyra [mockMode.test.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/lib/mockMode.test.ts) · [mock-mode.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/mock-mode.spec.ts) |
| SHARED-05 | | | none | | | solyra [App.tsx](https://github.com/TeneikaAskew/solyra/blob/main/src/App.tsx) (`QueryClient` defaults, no colocated test found) |
| SHARED-06 | | | none | Cloud Logging sink `gcp-job-failures-sink` → Pub/Sub topic `gcp-job-failures` → subscription `gcp-job-failures-push` → Cloud Run service `failure-notifier` ([gcp/deploy.sh](../../gcp/deploy.sh) `deploy_notifier`); secrets `discord-webhook-gcp`, `github-pat`, `github-repo` | Discord (dedicated GCP-failures channel) · GitHub (issue create/update) | [test_failure_notifier.py](../../tests/gcp/test_failure_notifier.py) |
| SHARED-07 | GET /api/health/freshness | [health.py:158](../../platform/api/routers/health.py#L158) → `scripts/audit_data_freshness.py` | every tracked Cloud SQL table (see [05-c](infrastructure/05-c-DATA_DEPENDENCIES.md)) | Cloud SQL `trading-db` · Cloud Run job `freshness-watchdog` · triggers `freshness-watchdog-hourly` (`0 9-19 * * 1-5`), `freshness-watchdog-nightly` (`30 19 * * *`) ([gcp/deploy.sh](../../gcp/deploy.sh)); secret `DB_PASS` | | [test_platform_api.py](../../tests/api/test_platform_api.py) · [test_route_coverage.py](../../tests/api/test_route_coverage.py) · solyra [data-pipeline-widget.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/dashboard/data-pipeline-widget.spec.ts) |
| SHARED-08 | GET /api/health | [main.py:270](../../platform/api/main.py#L270) → none (reports `_CLOUD_SQL`/`_LIB_DIR_EXISTS` booleans, no `lib/` call) | none | Cloud Run services `solyra-api-prod`, `solyra-api-staging` | | [test_platform_api.py](../../tests/api/test_platform_api.py) · [test_platform_auth.py](../../tests/api/test_platform_auth.py) · [test_route_coverage.py](../../tests/api/test_route_coverage.py) |

### Backend notes
- Inherited by every row below (not repeated per row): project `adept-mountain-474619-d4`, region `us-east1`, service account `trading-runner@adept-mountain-474619-d4.iam.gserviceaccount.com` for every Cloud Run job, image `us-east1-docker.pkg.dev/adept-mountain-474619-d4/trading/trading-system` (the `IMAGE_REF` every `deploy_*` function in [gcp/deploy.sh](../../gcp/deploy.sh) references), the Cloud SQL connection path `gcp/database.py:93` `get_engine()` (Cloud SQL Python Connector, `CLOUD_SQL_CONNECTION_NAME` + `DB_USER`/`DB_PASS`/`DB_NAME`), and Lovable as the SPA host serving every solyra route (SHARED-03's data path exists specifically to re-point `/api/*` off Lovable's static hosting). The API service itself runs as a separate account, `trading-platform-svc@`, set by `--service-account` in [platform/deploy.sh](../../platform/deploy.sh); jobs and the API service are not the same identity.
- Auth is global ASGI middleware, not a per-router dependency (`auth_middleware` wraps every request; `_path_requires_auth` decides per-path). It only verifies a bearer token when `AUTH_MODE=firebase`; `iap` and `open` call through unconditionally.
- Freshness has two independent paths that must be read separately: the standalone `freshness-watchdog` Cloud Run job (hourly during RTH, once after close) that exits non-zero into the failure lane on a stale table, and the on-demand `/api/health/freshness` endpoint the Dashboard widget polls, which wraps the same `scripts/audit_data_freshness.py` module behind a 5-minute in-process cache.
- Design drift carried from the pre-#957 architecture diagrams, per spec §4.5: the dashboard was labelled "no per-user auth" and the platform service "FastAPI + React" in the Claude Design docs. Both predate the #957 split (the SPA moved to this solyra repo; `platform/` now serves the API only, and every `/api/*` route is subject to the `AUTH_MODE` posture described in SHARED-01) and are stale as design labels, not as a statement about the current code.

### Gaps
- 05-INFRASTRUCTURE.md's Cloud Run job inventory table marks the Secrets column absent (its em-dash placeholder) for `fetch-market-data`, `backfill-daily-indicators`, `fetch-premarket-refresh`, `premarket-brief` and `fetch-top-movers` (cited from Dashboard's Data column, area 04). Reading the `deploy_*` functions directly shows each references `${DB_SECRET_FLAG}`, which expands (`_build_secret_flag`, [gcp/deploy.sh:1038](../../gcp/deploy.sh)) to `DB_PASS=db-trading-pass:latest,AV_API_KEY=av-api-key:latest,ALPHA_VANTAGE_API_KEY=av-api-key:latest,DISCORD_WEBHOOK_URL=discord-webhook-insights:latest` plus optional Discord/FRED/Benzinga pairs. The generated table's parser evidently does not resolve the `${DB_SECRET_FLAG}` variable reference to a literal `--set-secrets`, so it undercounts secrets for every job that uses the shared helper rather than an inline flag. Not fixed here: 05-INFRASTRUCTURE.md is a generated doc (see its own Maintenance column).
- No `AUDIT-2026-05-13` markers were found in any handler this task's areas cite (`platform/api/auth.py`, `platform/api/main.py`, `platform/api/routers/dashboard.py`, `platform/api/routers/config.py`, `platform/api/routers/health.py`, `platform/api/routers/live.py`, `platform/api/routers/catalysts.py`, `platform/api/routers/signals.py`, `platform/api/routers/playbook.py`, `platform/api/routers/waitlist.py`), and every endpoint cited from these five areas carries a `response_model`. The "66 of 98 validated trivially" untyped-response gap (spec §4.5) does not land on any row in SHARED, Landing, AuthGate, AppShell or Dashboard.

## 01 · Landing

UI spec: [UI-SCREENS.md § SCREEN-LANDING](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md#screen-landing--)
· Capability: [FEAT-WAITLIST-001](02-FEATURE-CATALOG.md#feat-waitlist-001)
· Requirements: REQ-UX-001, REQ-ACCESS-001 · Route: `/` · Status: Production

### Checklist
| ID | Element | S | T | V | Te | Evidence |
|---|---|---|---|---|---|---|
| LANDING-01 | LandingNav | [ ] | [ ] | [ ] | [ ] | |
| LANDING-02 | Hero with the agent terminal | [ ] | [ ] | [ ] | [ ] | |
| LANDING-03 | BentoGrid | [ ] | [ ] | [ ] | [ ] | |
| LANDING-04 | ChartShowcase | [ ] | [ ] | [ ] | [ ] | |
| LANDING-05 | ModuleDives | [ ] | [ ] | [ ] | [ ] | |
| LANDING-06 | DailyRhythm | [ ] | [ ] | [ ] | [ ] | |
| LANDING-07 | WaitlistSection | [ ] | [ ] | [ ] | [ ] | |
| LANDING-08 | FAQ (#faq) | [ ] | [ ] | [ ] | [ ] | |
| LANDING-09 | Sign in (to /dashboard) | [ ] | [ ] | [ ] | [ ] | |
| LANDING-10 | Request access, join the waitlist | [ ] | [ ] | [ ] | [ ] | |
| LANDING-11 | See a live day (scroll to #learn) | [ ] | [ ] | [ ] | [ ] | |
| LANDING-12 | State: loading (waitlist submit in flight) | [ ] | [ ] | [ ] | [ ] | |
| LANDING-13 | State: error (waitlist failure shown inline) | [ ] | [ ] | [ ] | [ ] | |

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|
| LANDING-01 | | | none | | | solyra [landing.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/landing/landing.spec.ts) |
| LANDING-02 | none (static content) | | none | | | solyra [landing.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/landing/landing.spec.ts) |
| LANDING-03 | none (static content) | | none | | | solyra [landing.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/landing/landing.spec.ts) |
| LANDING-04 | none (static content) | | none | | | solyra [landing.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/landing/landing.spec.ts) |
| LANDING-05 | none (static content) | | none | | | solyra [landing.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/landing/landing.spec.ts) |
| LANDING-06 | none (static content) | | none | | | solyra [landing.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/landing/landing.spec.ts) |
| LANDING-07 | POST /api/waitlist | [waitlist.py:84](../../platform/api/routers/waitlist.py#L84) → `gcp/database.py` (`get_engine`, inline SQL, no `lib/` module) | `waitlist_signups` (user write) | `solyra-api-staging`, `solyra-api-prod` · Cloud SQL `trading-db` | | [test_waitlist_router.py](../../tests/api/test_waitlist_router.py) · solyra [waitlist.test.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/components/landing/waitlist.test.ts) · [landing.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/landing/landing.spec.ts) |
| LANDING-08 | none (static content) | | none | | | solyra [landing.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/landing/landing.spec.ts) |
| LANDING-09 | | | none | | | solyra [landing.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/landing/landing.spec.ts) |
| LANDING-10 | POST /api/waitlist | [waitlist.py:84](../../platform/api/routers/waitlist.py#L84) → `gcp/database.py` (`get_engine`, inline SQL, no `lib/` module) | `waitlist_signups` (user write) | `solyra-api-staging`, `solyra-api-prod` · Cloud SQL `trading-db` | | [test_waitlist_router.py](../../tests/api/test_waitlist_router.py) · solyra [waitlist.test.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/components/landing/waitlist.test.ts) |
| LANDING-11 | | | none | | | |
| LANDING-12 | | solyra [WaitlistSection.tsx](https://github.com/TeneikaAskew/solyra/blob/main/src/components/landing/WaitlistSection.tsx) (`status === 'submitting'`) | none | | | |
| LANDING-13 | | solyra [waitlist.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/components/landing/waitlist.ts), [WaitlistSection.tsx](https://github.com/TeneikaAskew/solyra/blob/main/src/components/landing/WaitlistSection.tsx) | none | | | solyra [waitlist.test.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/components/landing/waitlist.test.ts) · [landing.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/landing/landing.spec.ts) |

### Backend notes
- Landing is the one area with no pipeline behind it: every element except the waitlist form is static JSX plus bundled fixtures (`src/components/landing/fixtures.ts` for Hero/ChartShowcase); nothing here reads Cloud SQL or waits on a Cloud Run job.
- The page must render with zero runtime-config or Firebase cost (issue #26): `ConfigGate` only wraps the gated app group and `/auth/action`, so `/` ships none of that code; `landing.spec.ts` pins this with a network-request assertion.
- Freshness budget: none applicable. Nothing on this page is time-sensitive data.

### Gaps
- External per spec §4.4 should name Lovable as the SPA host for this area (the design's stated convention for Landing), but nothing on the page makes a request that surfaces it in a Chain cell. Lovable is the deploy target, not a runtime dependency any element calls, so no row's External cell has anything truthful to hold; recorded here rather than invented onto a row.

## 02 · AuthGate and sign-in

UI spec: [UI-SCREENS.md § SCREEN-AUTH](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md#screen-auth--sign-in-in-route)
· Capability: [FEAT-AUTH-001](02-FEATURE-CATALOG.md#feat-auth-001)
· Requirements: REQ-UX-001, REQ-ACCESS-001 · Route: in-route state on every app route · Status: Production but needs remediation

### Checklist
| ID | Element | S | T | V | Te | Evidence |
|---|---|---|---|---|---|---|
| AUTH-01 | Auth-mode bootstrap (firebase, iap, open) | [ ] | [ ] | [ ] | [ ] | |
| AUTH-02 | State: loading spinner while the session resolves | [ ] | [ ] | [ ] | [ ] | |
| AUTH-03 | Google sign-in, with the new-tab variant when framed | [ ] | [ ] | [ ] | [ ] | |
| AUTH-04 | Email and password sign-in with inline error | [ ] | [ ] | [ ] | [ ] | |
| AUTH-05 | Sign-up mode | [ ] | [ ] | [ ] | [ ] | |
| AUTH-06 | Forgot password: reset email, then /auth/action | [ ] | [ ] | [ ] | [ ] | |
| AUTH-07 | Identity and role read (email, admin, dev) | [ ] | [ ] | [ ] | [ ] | |
| AUTH-08 | State: permission, 401 on a gated call shows "Sign in to load data" | [ ] | [ ] | [ ] | [ ] | |
| AUTH-09 | Sign out | [ ] | [ ] | [ ] | [ ] | |
| AUTH-10 | State: error, config fetch failure shows the config-error screen | [ ] | [ ] | [ ] | [ ] | |

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|
| AUTH-01 | GET /api/config/firebase | [config.py:45](../../platform/api/routers/config.py#L45) → none | none | `solyra-api-staging`, `solyra-api-prod` · env `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_PROJECT_ID`, `FIREBASE_APP_ID` on the service ([platform/deploy.sh](../../platform/deploy.sh)) | Firebase Auth | [test_platform_auth.py](../../tests/api/test_platform_auth.py) · solyra [auth-gate.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/auth-gate.spec.ts) (`open mode → app renders, no login screen`, `gated chunk downloads in parallel with the config fetch`, `firebase mode, signed out → login screen blocks the app`) |
| AUTH-02 | | solyra [useUser.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/hooks/useUser.ts) (`isLoading`), [AuthGate.tsx](https://github.com/TeneikaAskew/solyra/blob/main/src/components/auth/AuthGate.tsx) | none | | | |
| AUTH-03 | none (Firebase SDK) | token verified per call, [auth.py:114](../../platform/api/auth.py#L114) `_verify_bearer_email` | none | Firebase Auth, Google provider, authorized domains | Firebase Auth | solyra [auth-gate.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/auth-gate.spec.ts) |
| AUTH-04 | none (Firebase SDK) | token verified per call, [auth.py:114](../../platform/api/auth.py#L114) `_verify_bearer_email` | none | Firebase Auth | Firebase Auth | solyra [auth-gate.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/auth-gate.spec.ts) (`login screen toggles between sign-in and sign-up`) |
| AUTH-05 | none (Firebase SDK) | [auth.py:169](../../platform/api/auth.py#L169) `_is_allowed` (`AUTH_OPEN_SIGNUP`) | none | Firebase Auth | Firebase Auth | solyra [auth-gate.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/auth-gate.spec.ts) (`login screen toggles between sign-in and sign-up`) |
| AUTH-06 | none (Firebase SDK) | email templates `gcp/auth_email_templates.py`, `docs/AUTH_EMAILS.md` | none | Firebase Auth action links | Firebase Auth | solyra [auth-gate.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/auth-gate.spec.ts) (`Forgot password` and `/auth/action` describe blocks) |
| AUTH-07 | GET /api/me | [main.py:282](../../platform/api/main.py#L282) `get_current_user`, `stored_role_for` at [auth.py:229](../../platform/api/auth.py#L229) → none | `user_roles` | `solyra-api-staging`, `solyra-api-prod` · IAP on prod | | [test_platform_auth.py](../../tests/api/test_platform_auth.py) · [test_route_coverage.py](../../tests/api/test_route_coverage.py) · solyra [admin-auth.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/admin/admin-auth.spec.ts) |
| AUTH-08 | any gated /api/* | [auth.py:188](../../platform/api/auth.py#L188) `auth_middleware`, 401 → solyra [authGate.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/lib/authGate.ts) `markAuthBlocked` | none | | | solyra [authedFetch.test.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/lib/authedFetch.test.ts) · [most-active-bar.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/most-active-bar.spec.ts) |
| AUTH-09 | none (Firebase SDK) | | none | | Firebase Auth | solyra [navigation.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/navigation.spec.ts) |
| AUTH-10 | GET /api/config/firebase | [config.py:45](../../platform/api/routers/config.py#L45) → none | none | `solyra-api-staging`, `solyra-api-prod` | | solyra [auth-gate.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/auth-gate.spec.ts) (`config fetch failure → config-error screen`, `config endpoint answering HTML ... → config-error screen`) |

### Backend notes
- Auth is global ASGI middleware, not a per-router dependency. It verifies a bearer token only when `AUTH_MODE=firebase`; in `iap` and `open` it calls through (see [09-SECURITY-AUTH.md](09-SECURITY-AUTH.md)).
- The open prefixes are `/api/health`, `/api/me`, `/api/config/firebase`, `/api/waitlist` in [auth.py:69](../../platform/api/auth.py#L69) and must stay in sync with `OPEN_PREFIXES` in solyra [src/lib/authedFetch.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/lib/authedFetch.ts) (area 00, SHARED-02).
- Boot order (client-side, no backend job feeds this area): `ConfigGate` fetches `/api/config/firebase` once per page load (module-level `bootPromise`), then in `firebase` mode dynamically imports and awaits the Firebase facade before `AuthGate` reads any auth state. A logged-out visit to `/` never pays this cost (issue #26).
- Freshness budget: none, identity and config are read fresh on every boot; `useUser`'s `/api/me` query has a 30-second `staleTime` so a role granted or revoked mid-session converges on the next mount/focus refetch, not instantly.

### Gaps
- The design's backend diagram labels the dashboard "no per-user auth" and the platform service "FastAPI + React"; both predate the #957 split (see SHARED, area 00).

## 03 · AppShell

UI spec: [UI-SCREENS.md § SCREEN-SHELL](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md#screen-shell--app-shell)
· Capability: [FEAT-UI-001](02-FEATURE-CATALOG.md#feat-ui-001)
· Requirements: REQ-UX-001, REQ-ACCESS-001 · Route: layout for the 13 app pages · Status: Production but needs remediation

### Checklist
| ID | Element | S | T | V | Te | Evidence |
|---|---|---|---|---|---|---|
| SHELL-01 | Sidebar or TopTabs navigation | [ ] | [ ] | [ ] | [ ] | |
| SHELL-02 | Header in sidebar mode (auth status, sign out, replay control, theme toggle) | [ ] | [ ] | [ ] | [ ] | |
| SHELL-03 | MockModeBanner | [ ] | [ ] | [ ] | [ ] | |
| SHELL-04 | AuthStatusBanner and EmailVerificationBanner | [ ] | [ ] | [ ] | [ ] | |
| SHELL-05 | MostActiveBar marquee | [ ] | [ ] | [ ] | [ ] | |
| SHELL-06 | RouteErrorBoundary | [ ] | [ ] | [ ] | [ ] | |
| SHELL-07 | Market session badge (LIVE, PRE, AH, CLOSED) | [ ] | [ ] | [ ] | [ ] | |
| SHELL-08 | Command palette (Cmd-K, Ctrl-K) | [ ] | [ ] | [ ] | [ ] | |
| SHELL-09 | Replay control (historical review) | [ ] | [ ] | [ ] | [ ] | |
| SHELL-10 | Theme toggle | [ ] | [ ] | [ ] | [ ] | |
| SHELL-11 | Sign out | [ ] | [ ] | [ ] | [ ] | |
| SHELL-12 | State: loading (marquee before the first response) | [ ] | [ ] | [ ] | [ ] | |
| SHELL-13 | State: empty (marquee renders nothing on an empty list) | [ ] | [ ] | [ ] | [ ] | |
| SHELL-14 | State: error (marquee absent on 500, page renders) | [ ] | [ ] | [ ] | [ ] | |
| SHELL-15 | State: stale (session badge truthful when closed) | [ ] | [ ] | [ ] | [ ] | |
| SHELL-16 | State: permission (auth status banner when signed out or blocked) | [ ] | [ ] | [ ] | [ ] | |

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|
| SHELL-01 | | | none | | | solyra [navigation.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/navigation.spec.ts) (`top nav renders inline tabs + Market/Learn/Support dropdowns`) |
| SHELL-02 | | | none | | | solyra [navigation.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/navigation.spec.ts) (`auth status lives at the menu bottom, not the bar`) |
| SHELL-03 | | | none | | | solyra [mock-mode.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/mock-mode.spec.ts) |
| SHELL-04 | GET /api/me | [main.py:282](../../platform/api/main.py#L282) → none | `user_roles` | `solyra-api-staging`, `solyra-api-prod` | | |
| SHELL-05 | GET /api/market/most-active | [main.py:1510](../../platform/api/main.py#L1510) → none | `market_data_intraday`, `top_movers_intraday` ← `fetch-top-movers` ([top-movers-daily](../../gcp/deploy.sh), 16:15 ET Mon-Fri) | `solyra-api-staging`, `solyra-api-prod` · Cloud SQL `trading-db` · Cloud Run job `fetch-top-movers` · trigger `top-movers-daily` | AlphaVantage TOP_GAINERS_LOSERS | solyra [MostActiveBar.test.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/components/shared/MostActiveBar.test.ts), [MostActiveBar.test.tsx](https://github.com/TeneikaAskew/solyra/blob/main/src/components/shared/MostActiveBar.test.tsx) · [most-active-bar.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/most-active-bar.spec.ts) |
| SHELL-06 | | solyra [RouteErrorBoundary.tsx](https://github.com/TeneikaAskew/solyra/blob/main/src/components/shared/RouteErrorBoundary.tsx) | none | | | |
| SHELL-07 | GET /api/live/status | [live.py:174](../../platform/api/routers/live.py#L174) → none | none | `solyra-api-staging`, `solyra-api-prod` | | solyra [navigation.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/navigation.spec.ts) (`market session badge is truthful — CLOSED when the market is closed`) |
| SHELL-08 | | | none | | | |
| SHELL-09 | GET /api/config/market-hours | [config.py:131](../../platform/api/routers/config.py#L131) → none | none | `solyra-api-staging`, `solyra-api-prod` | | |
| SHELL-10 | none (localStorage) | solyra [themeStore.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/stores/themeStore.ts) | none | | | |
| SHELL-11 | none (Firebase SDK) | | none | | Firebase Auth | solyra [navigation.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/navigation.spec.ts) |
| SHELL-12 | GET /api/market/most-active | [main.py:1510](../../platform/api/main.py#L1510) → none | `market_data_intraday`, `top_movers_intraday` ← `fetch-top-movers` ([top-movers-daily](../../gcp/deploy.sh), 16:15 ET Mon-Fri) | `solyra-api-staging`, `solyra-api-prod` · Cloud SQL `trading-db` | AlphaVantage TOP_GAINERS_LOSERS | |
| SHELL-13 | GET /api/market/most-active | [main.py:1510](../../platform/api/main.py#L1510) → none | `market_data_intraday`, `top_movers_intraday` ← `fetch-top-movers` ([top-movers-daily](../../gcp/deploy.sh), 16:15 ET Mon-Fri) | `solyra-api-staging`, `solyra-api-prod` · Cloud SQL `trading-db` | AlphaVantage TOP_GAINERS_LOSERS | solyra [most-active-bar.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/most-active-bar.spec.ts) (`renders nothing when the API returns an empty item list`) |
| SHELL-14 | GET /api/market/most-active | [main.py:1510](../../platform/api/main.py#L1510) → none | `market_data_intraday`, `top_movers_intraday` ← `fetch-top-movers` ([top-movers-daily](../../gcp/deploy.sh), 16:15 ET Mon-Fri) | `solyra-api-staging`, `solyra-api-prod` · Cloud SQL `trading-db` | AlphaVantage TOP_GAINERS_LOSERS | solyra [most-active-bar.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/most-active-bar.spec.ts) (`bar is absent and the page otherwise renders fine when the API returns 500`) |
| SHELL-15 | GET /api/live/status | [live.py:174](../../platform/api/routers/live.py#L174) → none | none | `solyra-api-staging`, `solyra-api-prod` | | solyra [navigation.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/navigation.spec.ts) (`market session badge is truthful — CLOSED when the market is closed`) |
| SHELL-16 | GET /api/me | [main.py:282](../../platform/api/main.py#L282) → none | `user_roles` | `solyra-api-staging`, `solyra-api-prod` | | |

### Backend notes
- SHELL-04, 07, 09, 12-16 name the same handful of endpoints repeatedly because AppShell is a thin composition of independently-fetching widgets (`AuthStatusIndicator`/`useUser`, `MarketSessionBadge`/`useLiveStatus`, `MostActiveBar`/`useMostActive`) rather than one shell-level fetch; each widget owns its own loading/empty/error branch in source, not a shared shell-level state machine.
- `MostActiveBar` mounts once in `AppShell.tsx` (not per-page) on `/live`, `/charts`, `/options`, `/signals`, `/journal` only (`MOST_ACTIVE_BAR_ROUTES`), so it persists across navigation within that group instead of unmounting/remounting per route.
- Freshness budget: `useMostActive` has a 10-minute `staleTime` and a 15-minute `refetchInterval`; `useLiveStatus` refetches every 60s with a 30s `staleTime`; `useUser`'s `/api/me` query has a 30s `staleTime`. None of these are pipeline-fed on a cron the way Dashboard is; they are live/near-live reads, not daily-batch outputs.
- `fetch-top-movers` also has two intraday schedules (`top-movers-intraday-hourly` at `30 9-15 * * 1-5` and `top-movers-intraday-close` at `5 16 * * 1-5`) declared via `_schedule_with_args` in [gcp/deploy.sh](../../gcp/deploy.sh), which the brief's canonical `_schedule(_brief)? "` grep does not match (only the plain `_schedule "top-movers-daily" ...` line does). The Data column above cites the one the canonical grep finds; the intraday runs mean the most-active snapshot is fresher during RTH than "once at 16:15" alone would suggest.

### Gaps
- No `AUDIT-2026-05-13` markers were found in `platform/api/routers/live.py` or `platform/api/main.py`'s most-active/health handlers.
- No colocated or Playwright test was found for `RouteErrorBoundary.tsx` (SHELL-06), `CommandPalette.tsx` (SHELL-08), `ReplayControl.tsx` (SHELL-09), `themeStore.ts`/theme toggle (SHELL-10), or the `AuthStatusBanner`/`EmailVerificationBanner` pair (SHELL-04, SHELL-16); their Tests cells are blank, not merely thin.

## 04 · Dashboard

UI spec: [UI-SCREENS.md § SCREEN-DASHBOARD](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md#screen-dashboard--dashboard)
· Capability: [FEAT-MARKET-001](02-FEATURE-CATALOG.md#feat-market-001)
· Requirements: REQ-UX-001, REQ-ACCESS-001 · Route: `/dashboard` · Status: Production but needs remediation

### Checklist
| ID | Element | S | T | V | Te | Evidence |
|---|---|---|---|---|---|---|
| DASHBOARD-01 | Briefing strip | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-02 | Top setup | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-03 | Daily KPIs | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-04 | Intraday chart | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-05 | Live signals table | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-06 | Catalysts list | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-07 | Sector rotation | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-08 | AI take | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-09 | News | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-10 | Switch ticker | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-11 | Refresh | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-12 | Candles or Area toggle | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-13 | 1D or 5D sector period | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-14 | Click a card (signals, catalysts, news, AI take) | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-15 | Review mode | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-16 | State: loading | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-17 | State: empty | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-18 | State: error | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-19 | State: stale | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-20 | State: permission | [ ] | [ ] | [ ] | [ ] | |
| DASHBOARD-21 | Movement Read card (feature-flagged) | [ ] | [ ] | [ ] | [ ] | |

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|
| DASHBOARD-01 | GET /api/dashboard/brief/{ticker} · GET /api/live/status · GET /api/live/quote/{ticker} | [dashboard.py:82](../../platform/api/routers/dashboard.py#L82) → none · [live.py:174](../../platform/api/routers/live.py#L174) → none · [live.py:189](../../platform/api/routers/live.py#L189) → none | `premarket_analysis` ← `premarket-brief` ([premarket-brief-daily](../../gcp/deploy.sh), 08:30 ET Mon-Fri) · `market_data_daily` ← `fetch-market-data` ([fetch-market-data-daily](../../gcp/deploy.sh), 23:00 ET Mon-Fri) | `solyra-api-staging`, `solyra-api-prod` · Cloud SQL `trading-db` · Cloud Run jobs `premarket-brief`, `fetch-market-data` | AlphaVantage GLOBAL_QUOTE (live quote) | [test_platform_api.py](../../tests/api/test_platform_api.py) · [test_route_coverage.py](../../tests/api/test_route_coverage.py) · solyra [dashboard.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/dashboard/dashboard.spec.ts) |
| DASHBOARD-02 | GET /api/playbook/{ticker} | [playbook.py:306](../../platform/api/routers/playbook.py#L306) → none | `playbook_cards` ← `phase6-playbook` ([phase6-playbook-daily](../../gcp/deploy.sh), 04:30 ET Mon-Fri) | `solyra-api-staging`, `solyra-api-prod` · Cloud SQL `trading-db` · Cloud Run job `phase6-playbook` | | [test_platform_api.py](../../tests/api/test_platform_api.py) · solyra [dashboard.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/dashboard/dashboard.spec.ts) · [DashboardPage.avgReturn.test.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/routes/DashboardPage.avgReturn.test.ts) |
| DASHBOARD-03 | GET /api/market/reference/{ticker}/{date} | [main.py:1061](../../platform/api/main.py#L1061) → none | `market_data_daily` ← `fetch-market-data` ([fetch-market-data-daily](../../gcp/deploy.sh), 23:00 ET Mon-Fri) | `solyra-api-staging`, `solyra-api-prod` · Cloud SQL `trading-db` · Cloud Run job `fetch-market-data` | | [test_platform_api.py](../../tests/api/test_platform_api.py) · [test_route_coverage.py](../../tests/api/test_route_coverage.py) · solyra [dashboard.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/dashboard/dashboard.spec.ts) |
| DASHBOARD-04 | GET /api/market/data/{ticker}/{date} | [main.py:905](../../platform/api/main.py#L905) → none | `market_data_intraday` ← `fetch-market-data` ([fetch-market-data-daily](../../gcp/deploy.sh), 23:00 ET Mon-Fri) | `solyra-api-staging`, `solyra-api-prod` · Cloud SQL `trading-db` · Cloud Run job `fetch-market-data` | | solyra [dashboard-chart-fit.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/dashboard/dashboard-chart-fit.spec.ts) · [ticker-combobox.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/dashboard/ticker-combobox.spec.ts) |
| DASHBOARD-05 | GET /api/signals/{ticker} | [signals.py:221](../../platform/api/routers/signals.py#L221) → none | `historical_signals` ← `historical-signals-watchlist` ([historical-signals-watchlist-daily](../../gcp/deploy.sh), 01:00 ET Tue-Sat) | `solyra-api-staging`, `solyra-api-prod` · Cloud SQL `trading-db` · Cloud Run job `historical-signals-watchlist` | | [test_platform_api.py](../../tests/api/test_platform_api.py) · solyra [dashboard.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/dashboard/dashboard.spec.ts), [ticker-combobox.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/dashboard/ticker-combobox.spec.ts) |
| DASHBOARD-06 | GET /api/catalysts/events | [catalysts.py:158](../../platform/api/routers/catalysts.py#L158) → none | `earnings_calendar` ← `fetch-earnings-calendar` ([daily-earnings-refresh-calendar](../../gcp/deploy.sh), 19:00 ET Mon-Fri) · `economic_events` ← `fetch-economic-events` ([economic-events-daily](../../gcp/deploy.sh), 07:00 ET Mon-Fri) · `insider_transactions` ← `fetch-insider-transactions` ([insider-transactions-daily](../../gcp/deploy.sh), 07:00 ET Mon-Fri) · `news_sentiment` ← `fetch-news-sentiment-earnings` ([news-sentiment-earnings-0600](../../gcp/deploy.sh), 06:00 ET Mon-Fri) | `solyra-api-staging`, `solyra-api-prod` · Cloud SQL `trading-db` · Cloud Run jobs `fetch-earnings-calendar`, `fetch-economic-events`, `fetch-insider-transactions`, `fetch-news-sentiment-earnings` | Benzinga (live-refresh path, `refresh=true`) | [test_route_coverage.py](../../tests/api/test_route_coverage.py) · solyra [dashboard.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/dashboard/dashboard.spec.ts) |
| DASHBOARD-07 | GET /api/market/sectors | [main.py:1402](../../platform/api/main.py#L1402) → none | `market_data_daily` ← `fetch-market-data` ([fetch-market-data-daily](../../gcp/deploy.sh), 23:00 ET Mon-Fri) | `solyra-api-staging`, `solyra-api-prod` · Cloud SQL `trading-db` · Cloud Run job `fetch-market-data` | | [test_market_sectors.py](../../tests/api/test_market_sectors.py) · [test_route_coverage.py](../../tests/api/test_route_coverage.py) · solyra [dashboard.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/dashboard/dashboard.spec.ts), [DashboardPage.sectorBarWidthPct.test.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/routes/DashboardPage.sectorBarWidthPct.test.ts) |
| DASHBOARD-08 | GET /api/insights/report/{ticker} | [insights.py:764](../../platform/api/routers/insights.py#L764) → none | `insight_reports` ← `insight-pipeline` ([insight-pipeline-daily](../../gcp/deploy.sh), 08:45 ET Mon-Fri) | `solyra-api-staging`, `solyra-api-prod` · Cloud SQL `trading-db` · Cloud Run job `insight-pipeline` · Cloud Tasks queue `insight-pipeline-queue` | Google Gemini (report generation, inside `insight-pipeline`) | solyra [insights.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/insights/insights.spec.ts), [ticker-combobox.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/dashboard/ticker-combobox.spec.ts) |
| DASHBOARD-09 | GET /api/catalysts/events | [catalysts.py:158](../../platform/api/routers/catalysts.py#L158) → none | `news_sentiment` ← `fetch-news-sentiment-earnings` ([news-sentiment-earnings-0600](../../gcp/deploy.sh), 06:00 ET Mon-Fri) | `solyra-api-staging`, `solyra-api-prod` · Cloud SQL `trading-db` · Cloud Run job `fetch-news-sentiment-earnings` | | solyra [dashboard.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/dashboard/dashboard.spec.ts), [DashboardPage.relativeDayLabel.test.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/routes/DashboardPage.relativeDayLabel.test.ts) |
| DASHBOARD-10 | none (localStorage) | | none | | | solyra [ticker-combobox.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/dashboard/ticker-combobox.spec.ts) |
| DASHBOARD-11 | | | none | | | |
| DASHBOARD-12 | none (localStorage) | | none | | | |
| DASHBOARD-13 | | | none | | | |
| DASHBOARD-14 | | | none | | | solyra [dashboard.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/dashboard/dashboard.spec.ts) |
| DASHBOARD-15 | GET /api/market/data/{ticker}/{date} · GET /api/market/reference/{ticker}/{date} | [main.py:905](../../platform/api/main.py#L905) → none · [main.py:1061](../../platform/api/main.py#L1061) → none | `market_data_intraday`, `market_data_daily` ← `fetch-market-data` ([fetch-market-data-daily](../../gcp/deploy.sh), 23:00 ET Mon-Fri) | `solyra-api-staging`, `solyra-api-prod` · Cloud SQL `trading-db` | | solyra [dashboard.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/dashboard/dashboard.spec.ts) |
| DASHBOARD-16 | | solyra [WidgetState.tsx](https://github.com/TeneikaAskew/solyra/blob/main/src/components/shared/WidgetState.tsx) | none | | | solyra [WidgetState.test.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/components/shared/WidgetState.test.ts) |
| DASHBOARD-17 | | solyra [DashboardPage.tsx](https://github.com/TeneikaAskew/solyra/blob/main/src/routes/DashboardPage.tsx) (`Unavailable`) | none | | | |
| DASHBOARD-18 | | solyra [WidgetState.tsx](https://github.com/TeneikaAskew/solyra/blob/main/src/components/shared/WidgetState.tsx) (`WidgetError`) | none | | | solyra [WidgetState.test.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/components/shared/WidgetState.test.ts) |
| DASHBOARD-19 | | solyra [DashboardPage.tsx](https://github.com/TeneikaAskew/solyra/blob/main/src/routes/DashboardPage.tsx) (`playbookAge`, `snapshotAgeLabel`) | none | | | |
| DASHBOARD-20 | | solyra [WidgetState.tsx](https://github.com/TeneikaAskew/solyra/blob/main/src/components/shared/WidgetState.tsx) (`SignInEmptyState`), [authGate.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/lib/authGate.ts) | none | | | solyra [WidgetState.test.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/components/shared/WidgetState.test.ts) |
| DASHBOARD-21 | GET /api/movement-statement | [dashboard.py:530](../../platform/api/routers/dashboard.py#L530) → `lib/movement_statement.py`, `lib/data_loader.py`, `lib/strat_levels.py` | `market_data_daily` ← `fetch-market-data` ([fetch-market-data-daily](../../gcp/deploy.sh), 23:00 ET Mon-Fri) · `premarket_analysis` ← `premarket-brief` ([premarket-brief-daily](../../gcp/deploy.sh), 08:30 ET Mon-Fri) | `solyra-api-staging`, `solyra-api-prod` · Cloud SQL `trading-db` · Cloud Run jobs `fetch-market-data`, `premarket-brief` · env `MOVEMENT_STATEMENT_ENABLED=true` on the service ([platform/deploy.sh](../../platform/deploy.sh)) | | [test_movement_statement_router.py](../../tests/api/test_movement_statement_router.py) · solyra [movement-read.spec.ts](https://github.com/TeneikaAskew/solyra/blob/main/tests/dashboard/movement-read.spec.ts), [MovementRead.test.tsx](https://github.com/TeneikaAskew/solyra/blob/main/src/components/dashboard/MovementRead.test.tsx) |

### Backend notes
- Pipeline order feeding this page, earliest first (all times America/New_York): `fetch-market-data` 23:00 Mon-Fri (`market_data_daily`, `market_data_intraday`) → `backfill-daily-indicators` 02:30 Mon-Sat (heals NULL derived-indicator columns on `market_data_daily`) → `phase6-playbook` 04:30 Mon-Fri (`playbook_cards`) → `fetch-news-sentiment-earnings` 06:00 Mon-Fri (`news_sentiment`) → `fetch-insider-transactions` / `fetch-economic-events` 07:00 Mon-Fri → `fetch-premarket-refresh` 08:20 Mon-Fri (UPDATEs `gap_pct`/`pre_*` on `market_data_daily` only) → `premarket-brief` 08:30 Mon-Fri (`premarket_analysis`) → `insight-pipeline` 08:45 Mon-Fri (`insight_reports`) → `fetch-earnings-calendar` 19:00 Mon-Fri → `historical-signals-watchlist` 01:00 Tue-Sat (`historical_signals`, next session). Ordering for `market_data_daily` is enforced by the schedule itself (08:20 refresh runs before the 08:30 brief; the 23:00 nightly fetch is canonical and runs after close); see [05-c §4](infrastructure/05-c-DATA_DEPENDENCIES.md#4-multi-writer-tables-coordination-risks).
- `premarket_analysis` is a 3-writer table (`premarket-brief`, `premarket-playbook-resolver` at 21:15 Mon-Fri, `signal-monitor` at 09:25 Mon-Fri); the brief handler's `WHERE run_kind = 'live'` filter picks among them at read time, and which job produced the row read by DASHBOARD-01 on any given request was not traced further than that filter.
- Freshness the page assumes: the brief bullets read as "today's brief", which per the pipeline order above is not present until 08:30 ET on a trading day; before that the briefing strip shows the `Unavailable` fallback rather than yesterday's data relabeled as today's. `useInsightReport`, `useFetch` (brief/playbook/signals/sectors) all carry a 60s `staleTime`; the playbook query additionally re-polls every 15 minutes in live mode so the server's own `max_age_days` 503 surfaces within that window.
- Review mode (DASHBOARD-15) does not introduce new endpoints of its own: `reviewDate`/`reviewTime` add a `?date=`/`end_date=`/`end_time=` query parameter onto the brief, playbook and signals requests already listed under DASHBOARD-01/02/05, and `useReviewQuote` additionally calls the same `/api/market/data/{ticker}/{date}` (1-minute bars) and `/api/market/reference/{ticker}/{date}` endpoints already listed under DASHBOARD-04/03 to reconstruct a synthetic as-of quote; see [useReviewQuote.ts](https://github.com/TeneikaAskew/solyra/blob/main/src/hooks/useReviewQuote.ts).

### Gaps
- **04-BACKEND-API.md says `/api/market/data/{ticker}/{date}` touches `market_data_daily`; the handler reads `market_data_intraday`.** Verified by reading `_load_date_data` ([main.py:1595-1624](../../platform/api/main.py#L1595)): every branch is `SELECT ... FROM market_data_intraday`. This endpoint feeds DASHBOARD-04 and DASHBOARD-15; the Data cells above record what the code does.
- **04-BACKEND-API.md's Tables-touched for `/api/catalysts/events` omits `news_sentiment`.** The handler queries it directly ([catalysts.py:114](../../platform/api/routers/catalysts.py#L114)) and stamps the `"AV news"` source tag ([catalysts.py:405](../../platform/api/routers/catalysts.py#L405)) that DASHBOARD-09's News card filters on; the same endpoint genuinely serves both the Catalysts list and the News card from one fetch. Recorded on DASHBOARD-06 and DASHBOARD-09.
- **04-BACKEND-API.md says `/api/signals/{ticker}` reads data "via lib/"; the handler issues its own inline SQL against `historical_signals`** (`_query_signals_sql`, [signals.py:180-212](../../platform/api/routers/signals.py#L180)). DASHBOARD-05's Data cell names `historical_signals` directly rather than repeating "via lib/".
- **05-INFRASTRUCTURE.md's job table lists `phase6-playbook`'s schedule as "manual"; `gcp/deploy.sh` has a live, uncommented scheduler entry** `_schedule "phase6-playbook-daily" "30 4 * * 1-5" "phase6-playbook"` ([gcp/deploy.sh:4504](../../gcp/deploy.sh)). DASHBOARD-02's Data cell uses the schedule the code declares.
- The page renders a fourth live card, `MovementRead` ([src/components/dashboard/MovementRead.tsx](https://github.com/TeneikaAskew/solyra/blob/main/src/components/dashboard/MovementRead.tsx)), gated behind `MOVEMENT_STATEMENT_ENABLED` and hidden in review mode. This was flagged here as missing a Checklist row in the first draft of this task; the controller ruled to append it as DASHBOARD-21 (IDs never renumber) rather than leave it uncovered, so it now has both a Checklist row and a Chain row above.
- No `AUDIT-2026-05-13` markers were found in `platform/api/routers/dashboard.py`, `platform/api/main.py`'s market/sectors/most-active handlers, `platform/api/routers/signals.py`, `platform/api/routers/catalysts.py`, `platform/api/routers/playbook.py` or `platform/api/routers/insights.py`'s report handler.

## 05 · Live Market

UI spec: [UI-SCREENS.md § SCREEN-LIVEMARKET](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md#screen-livemarket--live)
· Capability: [FEAT-LIVE-001](02-FEATURE-CATALOG.md#feat-live-001), [FEAT-SIGNAL-001](02-FEATURE-CATALOG.md#feat-signal-001), [FEAT-STRAT-001](02-FEATURE-CATALOG.md#feat-strat-001), [FEAT-IND-001](02-FEATURE-CATALOG.md#feat-ind-001)
· Requirements: REQ-UX-001, REQ-ACCESS-001, REQ-MARKET-001 · Route: `/live` · Status: Production but needs remediation

### Checklist
| ID | Element | S | T | V | Te | Evidence |
|---|---|---|---|---|---|---|
| LIVE-01 | Session bar | [ ] | [ ] | [ ] | [ ] | |
| LIVE-02 | Quote card | [ ] | [ ] | [ ] | [ ] | |
| LIVE-03 | Six indicator tiles | [ ] | [ ] | [ ] | [ ] | |
| LIVE-04 | CALL and PUT setup cards | [ ] | [ ] | [ ] | [ ] | |
| LIVE-05 | Live (15s) or Paused toggle | [ ] | [ ] | [ ] | [ ] | |
| LIVE-06 | Sound alert | [ ] | [ ] | [ ] | [ ] | |
| LIVE-07 | Switch ticker | [ ] | [ ] | [ ] | [ ] | |
| LIVE-08 | Review mode | [ ] | [ ] | [ ] | [ ] | |
| LIVE-09 | State: loading | [ ] | [ ] | [ ] | [ ] | |
| LIVE-10 | State: empty | [ ] | [ ] | [ ] | [ ] | |
| LIVE-11 | State: error | [ ] | [ ] | [ ] | [ ] | |
| LIVE-12 | State: stale | [ ] | [ ] | [ ] | [ ] | |
| LIVE-13 | State: permission | [ ] | [ ] | [ ] | [ ] | |

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|

### Backend notes

### Gaps

## 06 · Charts

UI spec: [UI-SCREENS.md § SCREEN-CHARTS](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md#screen-charts--charts)
· Capability: [FEAT-CHART-001](02-FEATURE-CATALOG.md#feat-chart-001), [FEAT-STRAT-001](02-FEATURE-CATALOG.md#feat-strat-001), [FEAT-IND-001](02-FEATURE-CATALOG.md#feat-ind-001)
· Requirements: REQ-UX-001, REQ-ACCESS-001 · Route: `/charts` · Status: Production but needs remediation

### Checklist
| ID | Element | S | T | V | Te | Evidence |
|---|---|---|---|---|---|---|
| CHARTS-01 | Toolbar | [ ] | [ ] | [ ] | [ ] | |
| CHARTS-02 | Candlestick chart | [ ] | [ ] | [ ] | [ ] | |
| CHARTS-03 | Crosshair bar | [ ] | [ ] | [ ] | [ ] | |
| CHARTS-04 | Replay session controls | [ ] | [ ] | [ ] | [ ] | |
| CHARTS-05 | Strategy conditions card | [ ] | [ ] | [ ] | [ ] | |
| CHARTS-06 | Similar setups card | [ ] | [ ] | [ ] | [ ] | |
| CHARTS-07 | Backtester | [ ] | [ ] | [ ] | [ ] | |
| CHARTS-08 | Post-session scorecard | [ ] | [ ] | [ ] | [ ] | |
| CHARTS-09 | Change date or timeframe | [ ] | [ ] | [ ] | [ ] | |
| CHARTS-10 | Toggle overlays | [ ] | [ ] | [ ] | [ ] | |
| CHARTS-11 | Run a replay session | [ ] | [ ] | [ ] | [ ] | |
| CHARTS-12 | Backtest my trades | [ ] | [ ] | [ ] | [ ] | |
| CHARTS-13 | State: loading | [ ] | [ ] | [ ] | [ ] | |
| CHARTS-14 | State: empty | [ ] | [ ] | [ ] | [ ] | |
| CHARTS-15 | State: error | [ ] | [ ] | [ ] | [ ] | |
| CHARTS-16 | State: stale | [ ] | [ ] | [ ] | [ ] | |
| CHARTS-17 | State: permission | [ ] | [ ] | [ ] | [ ] | |

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|

### Backend notes

### Gaps

## 07 · Options Flow

UI spec: [UI-SCREENS.md § SCREEN-OPTIONSFLOW](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md#screen-optionsflow--options)
· Capability: [FEAT-OPTION-001](02-FEATURE-CATALOG.md#feat-option-001)
· Requirements: REQ-UX-001, REQ-ACCESS-001 · Route: `/options` · Status: Retest Required

### Checklist
| ID | Element | S | T | V | Te | Evidence |
|---|---|---|---|---|---|---|
| OPTIONS-01 | Heatseeker: Swing Mode | [ ] | [ ] | [ ] | [ ] | |
| OPTIONS-02 | Heatseeker: Trinity Mode | [ ] | [ ] | [ ] | [ ] | |
| OPTIONS-03 | Flowseeker: Live Feed | [ ] | [ ] | [ ] | [ ] | |
| OPTIONS-04 | Flowseeker: Contract Drilldown | [ ] | [ ] | [ ] | [ ] | |
| OPTIONS-05 | Profiles | [ ] | [ ] | [ ] | [ ] | |
| OPTIONS-06 | Symbol picker | [ ] | [ ] | [ ] | [ ] | |
| OPTIONS-07 | View switcher | [ ] | [ ] | [ ] | [ ] | |
| OPTIONS-08 | Pick an expiration date | [ ] | [ ] | [ ] | [ ] | |
| OPTIONS-09 | State: loading | [ ] | [ ] | [ ] | [ ] | |
| OPTIONS-10 | State: empty | [ ] | [ ] | [ ] | [ ] | |
| OPTIONS-11 | State: error | [ ] | [ ] | [ ] | [ ] | |
| OPTIONS-12 | State: stale | [ ] | [ ] | [ ] | [ ] | |
| OPTIONS-13 | State: permission | [ ] | [ ] | [ ] | [ ] | |

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|

### Backend notes

### Gaps

## 08 · Signals

UI spec: [UI-SCREENS.md § SCREEN-SIGNALS](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md#screen-signals--signals)
· Capability: [FEAT-SIGNAL-001](02-FEATURE-CATALOG.md#feat-signal-001)
· Requirements: REQ-UX-001, REQ-ACCESS-001, REQ-SIGNAL-001 · Route: `/signals` · Status: Production but needs remediation

### Checklist
| ID | Element | S | T | V | Te | Evidence |
|---|---|---|---|---|---|---|
| SIGNALS-01 | Header | [ ] | [ ] | [ ] | [ ] | |
| SIGNALS-02 | Performance KPIs | [ ] | [ ] | [ ] | [ ] | |
| SIGNALS-03 | Filter bar | [ ] | [ ] | [ ] | [ ] | |
| SIGNALS-04 | Signals table | [ ] | [ ] | [ ] | [ ] | |
| SIGNALS-05 | Filter and sort | [ ] | [ ] | [ ] | [ ] | |
| SIGNALS-06 | Clear filters | [ ] | [ ] | [ ] | [ ] | |
| SIGNALS-07 | Review mode | [ ] | [ ] | [ ] | [ ] | |
| SIGNALS-08 | State: loading | [ ] | [ ] | [ ] | [ ] | |
| SIGNALS-09 | State: empty | [ ] | [ ] | [ ] | [ ] | |
| SIGNALS-10 | State: error | [ ] | [ ] | [ ] | [ ] | |
| SIGNALS-11 | State: stale | [ ] | [ ] | [ ] | [ ] | |
| SIGNALS-12 | State: permission | [ ] | [ ] | [ ] | [ ] | |

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|

### Backend notes

### Gaps

## 09 · AI Insights

UI spec: [UI-SCREENS.md § SCREEN-INSIGHTS](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md#screen-insights--insights)
· Capability: [FEAT-INSIGHT-001](02-FEATURE-CATALOG.md#feat-insight-001)
· Requirements: REQ-UX-001, REQ-ACCESS-001 · Route: `/insights` · Status: Experimental

### Checklist
| ID | Element | S | T | V | Te | Evidence |
|---|---|---|---|---|---|---|
| INSIGHTS-01 | Report cards | [ ] | [ ] | [ ] | [ ] | |
| INSIGHTS-02 | Agents tab | [ ] | [ ] | [ ] | [ ] | |
| INSIGHTS-03 | History tab | [ ] | [ ] | [ ] | [ ] | |
| INSIGHTS-04 | Watchlist tab | [ ] | [ ] | [ ] | [ ] | |
| INSIGHTS-05 | Chat tab | [ ] | [ ] | [ ] | [ ] | |
| INSIGHTS-06 | Degradation banner | [ ] | [ ] | [ ] | [ ] | |
| INSIGHTS-07 | Generate or refresh a report | [ ] | [ ] | [ ] | [ ] | |
| INSIGHTS-08 | Set a point-in-time cutoff | [ ] | [ ] | [ ] | [ ] | |
| INSIGHTS-09 | Add or remove watchlist tickers | [ ] | [ ] | [ ] | [ ] | |
| INSIGHTS-10 | Chat | [ ] | [ ] | [ ] | [ ] | |
| INSIGHTS-11 | State: loading | [ ] | [ ] | [ ] | [ ] | |
| INSIGHTS-12 | State: empty | [ ] | [ ] | [ ] | [ ] | |
| INSIGHTS-13 | State: error | [ ] | [ ] | [ ] | [ ] | |
| INSIGHTS-14 | State: stale | [ ] | [ ] | [ ] | [ ] | |
| INSIGHTS-15 | State: permission | [ ] | [ ] | [ ] | [ ] | |

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|

### Backend notes

### Gaps

## 10 · Catalysts

UI spec: [UI-SCREENS.md § SCREEN-CATALYSTS](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md#screen-catalysts--catalysts)
· Capability: [FEAT-CATALYST-001](02-FEATURE-CATALOG.md#feat-catalyst-001)
· Requirements: REQ-UX-001, REQ-ACCESS-001 · Route: `/catalysts` · Status: Production but needs remediation

### Checklist
| ID | Element | S | T | V | Te | Evidence |
|---|---|---|---|---|---|---|
| CATALYSTS-01 | Hot Now | [ ] | [ ] | [ ] | [ ] | |
| CATALYSTS-02 | Impact tier filter | [ ] | [ ] | [ ] | [ ] | |
| CATALYSTS-03 | Type chips | [ ] | [ ] | [ ] | [ ] | |
| CATALYSTS-04 | Event timeline | [ ] | [ ] | [ ] | [ ] | |
| CATALYSTS-05 | WSH upgrade banner | [ ] | [ ] | [ ] | [ ] | |
| CATALYSTS-06 | Change date range | [ ] | [ ] | [ ] | [ ] | |
| CATALYSTS-07 | Filter by impact or type | [ ] | [ ] | [ ] | [ ] | |
| CATALYSTS-08 | Expand an event | [ ] | [ ] | [ ] | [ ] | |
| CATALYSTS-09 | Open insight report | [ ] | [ ] | [ ] | [ ] | |
| CATALYSTS-10 | State: loading | [ ] | [ ] | [ ] | [ ] | |
| CATALYSTS-11 | State: empty | [ ] | [ ] | [ ] | [ ] | |
| CATALYSTS-12 | State: error | [ ] | [ ] | [ ] | [ ] | |
| CATALYSTS-13 | State: stale | [ ] | [ ] | [ ] | [ ] | |
| CATALYSTS-14 | State: permission | [ ] | [ ] | [ ] | [ ] | |

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|

### Backend notes

### Gaps

## 11 · Playbook

UI spec: [UI-SCREENS.md § SCREEN-PLAYBOOK](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md#screen-playbook--playbook)
· Capability: [FEAT-PLAYBOOK-001](02-FEATURE-CATALOG.md#feat-playbook-001)
· Requirements: REQ-UX-001, REQ-ACCESS-001, REQ-PLAYBOOK-001 · Route: `/playbook` · Status: Broken

### Checklist
| ID | Element | S | T | V | Te | Evidence |
|---|---|---|---|---|---|---|
| PLAYBOOK-01 | Header | [ ] | [ ] | [ ] | [ ] | |
| PLAYBOOK-02 | Setup cards | [ ] | [ ] | [ ] | [ ] | |
| PLAYBOOK-03 | Trade levels | [ ] | [ ] | [ ] | [ ] | |
| PLAYBOOK-04 | Switch ticker | [ ] | [ ] | [ ] | [ ] | |
| PLAYBOOK-05 | Watch conditions fill | [ ] | [ ] | [ ] | [ ] | |
| PLAYBOOK-06 | State: loading | [ ] | [ ] | [ ] | [ ] | |
| PLAYBOOK-07 | State: empty | [ ] | [ ] | [ ] | [ ] | |
| PLAYBOOK-08 | State: error | [ ] | [ ] | [ ] | [ ] | |
| PLAYBOOK-09 | State: stale | [ ] | [ ] | [ ] | [ ] | |
| PLAYBOOK-10 | State: permission | [ ] | [ ] | [ ] | [ ] | |

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|

### Backend notes

### Gaps

## 12 · Reports

UI spec: [UI-SCREENS.md § SCREEN-REPORTS](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md#screen-reports--reports)
· Capability: [FEAT-REPORT-001](02-FEATURE-CATALOG.md#feat-report-001), [FEAT-REPLAY-001](02-FEATURE-CATALOG.md#feat-replay-001)
· Requirements: REQ-UX-001, REQ-ACCESS-001 · Route: `/reports` · Status: FEAT-REPORT-001 Production but needs remediation · FEAT-REPLAY-001 Invalidated

### Checklist
| ID | Element | S | T | V | Te | Evidence |
|---|---|---|---|---|---|---|
| REPORTS-01 | Picker bar | [ ] | [ ] | [ ] | [ ] | |
| REPORTS-02 | Report header | [ ] | [ ] | [ ] | [ ] | |
| REPORTS-03 | Report body | [ ] | [ ] | [ ] | [ ] | |
| REPORTS-04 | Select a report | [ ] | [ ] | [ ] | [ ] | |
| REPORTS-05 | Previous or Next | [ ] | [ ] | [ ] | [ ] | |
| REPORTS-06 | State: loading | [ ] | [ ] | [ ] | [ ] | |
| REPORTS-07 | State: empty | [ ] | [ ] | [ ] | [ ] | |
| REPORTS-08 | State: error | [ ] | [ ] | [ ] | [ ] | |
| REPORTS-09 | State: stale | [ ] | [ ] | [ ] | [ ] | |
| REPORTS-10 | State: permission | [ ] | [ ] | [ ] | [ ] | |

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|

### Backend notes

### Gaps

## 13 · Journal

UI spec: [UI-SCREENS.md § SCREEN-JOURNAL](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md#screen-journal--journal)
· Capability: [FEAT-JOURNAL-001](02-FEATURE-CATALOG.md#feat-journal-001)
· Requirements: REQ-UX-001, REQ-ACCESS-001, REQ-JOURNAL-001 · Route: `/journal` · Status: Production but needs remediation

### Checklist
| ID | Element | S | T | V | Te | Evidence |
|---|---|---|---|---|---|---|
| JOURNAL-01 | Header row | [ ] | [ ] | [ ] | [ ] | |
| JOURNAL-02 | Cockpit row | [ ] | [ ] | [ ] | [ ] | |
| JOURNAL-03 | KPI tiles | [ ] | [ ] | [ ] | [ ] | |
| JOURNAL-04 | My style panel | [ ] | [ ] | [ ] | [ ] | |
| JOURNAL-05 | Add-trade form | [ ] | [ ] | [ ] | [ ] | |
| JOURNAL-06 | Trade table | [ ] | [ ] | [ ] | [ ] | |
| JOURNAL-07 | Mark entry on the chart | [ ] | [ ] | [ ] | [ ] | |
| JOURNAL-08 | Add trade manually | [ ] | [ ] | [ ] | [ ] | |
| JOURNAL-09 | Import CSV | [ ] | [ ] | [ ] | [ ] | |
| JOURNAL-10 | Export CSV | [ ] | [ ] | [ ] | [ ] | |
| JOURNAL-11 | Switch view or session | [ ] | [ ] | [ ] | [ ] | |
| JOURNAL-12 | State: loading | [ ] | [ ] | [ ] | [ ] | |
| JOURNAL-13 | State: empty | [ ] | [ ] | [ ] | [ ] | |
| JOURNAL-14 | State: error | [ ] | [ ] | [ ] | [ ] | |
| JOURNAL-15 | State: stale | [ ] | [ ] | [ ] | [ ] | |
| JOURNAL-16 | State: permission | [ ] | [ ] | [ ] | [ ] | |

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|

### Backend notes

### Gaps

## 14 · Admin

UI spec: [UI-SCREENS.md § SCREEN-ADMIN](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md#screen-admin--admin)
· Capability: [FEAT-MODEL-001](02-FEATURE-CATALOG.md#feat-model-001), [FEAT-ADMIN-001](02-FEATURE-CATALOG.md#feat-admin-001), [FEAT-OPS-001](02-FEATURE-CATALOG.md#feat-ops-001)
· Requirements: REQ-UX-001, REQ-ACCESS-001 · Route: `/admin` · Status: FEAT-MODEL-001 Invalidated / Failed (mixed) · FEAT-ADMIN-001 Production but needs remediation · FEAT-OPS-001 Incomplete

### Checklist
| ID | Element | S | T | V | Te | Evidence |
|---|---|---|---|---|---|---|
| ADMIN-01 | Users and roles tab | [ ] | [ ] | [ ] | [ ] | |
| ADMIN-02 | Chart and report data tab | [ ] | [ ] | [ ] | [ ] | |
| ADMIN-03 | Models and routing tab | [ ] | [ ] | [ ] | [ ] | |
| ADMIN-04 | Grant or revoke roles | [ ] | [ ] | [ ] | [ ] | |
| ADMIN-05 | Disable a user | [ ] | [ ] | [ ] | [ ] | |
| ADMIN-06 | Refresh a data source | [ ] | [ ] | [ ] | [ ] | |
| ADMIN-07 | Change provider or model per role and save | [ ] | [ ] | [ ] | [ ] | |
| ADMIN-08 | Run a predict | [ ] | [ ] | [ ] | [ ] | |
| ADMIN-09 | State: loading | [ ] | [ ] | [ ] | [ ] | |
| ADMIN-10 | State: empty | [ ] | [ ] | [ ] | [ ] | |
| ADMIN-11 | State: error | [ ] | [ ] | [ ] | [ ] | |
| ADMIN-12 | State: stale | [ ] | [ ] | [ ] | [ ] | |
| ADMIN-13 | State: permission | [ ] | [ ] | [ ] | [ ] | |

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|

### Backend notes

### Gaps

## 15 · Settings

UI spec: [UI-SCREENS.md § SCREEN-SETTINGS](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md#screen-settings--settings)
· Capability: [FEAT-SETTINGS-001](02-FEATURE-CATALOG.md#feat-settings-001)
· Requirements: REQ-UX-001, REQ-ACCESS-001 · Route: `/settings` · Status: Incomplete

### Checklist
| ID | Element | S | T | V | Te | Evidence |
|---|---|---|---|---|---|---|
| SETTINGS-01 | Profile tab | [ ] | [ ] | [ ] | [ ] | |
| SETTINGS-02 | Appearance tab | [ ] | [ ] | [ ] | [ ] | |
| SETTINGS-03 | Trading tab | [ ] | [ ] | [ ] | [ ] | |
| SETTINGS-04 | Notifications tab | [ ] | [ ] | [ ] | [ ] | |
| SETTINGS-05 | Account tab | [ ] | [ ] | [ ] | [ ] | |
| SETTINGS-06 | Toggle appearance | [ ] | [ ] | [ ] | [ ] | |
| SETTINGS-07 | Save changes or Discard | [ ] | [ ] | [ ] | [ ] | |
| SETTINGS-08 | Sign out | [ ] | [ ] | [ ] | [ ] | |
| SETTINGS-09 | State: loading | [ ] | [ ] | [ ] | [ ] | |
| SETTINGS-10 | State: empty | [ ] | [ ] | [ ] | [ ] | |
| SETTINGS-11 | State: error | [ ] | [ ] | [ ] | [ ] | |
| SETTINGS-12 | State: stale | [ ] | [ ] | [ ] | [ ] | |
| SETTINGS-13 | State: permission | [ ] | [ ] | [ ] | [ ] | |

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|

### Backend notes

### Gaps

## 16 · Help and Glossary

UI spec: [UI-SCREENS.md § SCREEN-HELP](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md#screen-help--help)
· Capability: [FEAT-HELP-001](02-FEATURE-CATALOG.md#feat-help-001)
· Requirements: REQ-UX-001, REQ-ACCESS-001 · Route: `/help` · Status: Production

### Checklist
| ID | Element | S | T | V | Te | Evidence |
|---|---|---|---|---|---|---|
| HELP-01 | Search box | [ ] | [ ] | [ ] | [ ] | |
| HELP-02 | Category pills | [ ] | [ ] | [ ] | [ ] | |
| HELP-03 | Glossary entries | [ ] | [ ] | [ ] | [ ] | |
| HELP-04 | State: empty (no entry matches) | [ ] | [ ] | [ ] | [ ] | |
| HELP-05 | Search | [ ] | [ ] | [ ] | [ ] | |
| HELP-06 | Filter by category | [ ] | [ ] | [ ] | [ ] | |
| HELP-07 | Expand an entry | [ ] | [ ] | [ ] | [ ] | |
| HELP-08 | TermHover links from other pages | [ ] | [ ] | [ ] | [ ] | |

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|

### Backend notes

### Gaps
