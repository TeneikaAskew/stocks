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
| 04 · Dashboard | 20 | 0 | 0 | 0 | 0 |
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
| Total | 221 | 0 | 0 | 0 | 0 |

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

### Backend notes

### Gaps

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

### Backend notes

### Gaps

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

### Backend notes

### Gaps

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

### Backend notes

### Gaps

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

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|

### Backend notes

### Gaps

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
