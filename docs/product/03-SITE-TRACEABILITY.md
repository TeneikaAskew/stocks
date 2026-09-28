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
| 00 · Shared, under every page | 0 | 0 | 0 | 0 | 0 |
| 01 · Landing | 0 | 0 | 0 | 0 | 0 |
| 02 · AuthGate and sign-in | 0 | 0 | 0 | 0 | 0 |
| 03 · AppShell | 0 | 0 | 0 | 0 | 0 |
| 04 · Dashboard | 0 | 0 | 0 | 0 | 0 |
| 05 · Live Market | 0 | 0 | 0 | 0 | 0 |
| 06 · Charts | 0 | 0 | 0 | 0 | 0 |
| 07 · Options Flow | 0 | 0 | 0 | 0 | 0 |
| 08 · Signals | 0 | 0 | 0 | 0 | 0 |
| 09 · AI Insights | 0 | 0 | 0 | 0 | 0 |
| 10 · Catalysts | 0 | 0 | 0 | 0 | 0 |
| 11 · Playbook | 0 | 0 | 0 | 0 | 0 |
| 12 · Reports | 0 | 0 | 0 | 0 | 0 |
| 13 · Journal | 0 | 0 | 0 | 0 | 0 |
| 14 · Admin | 0 | 0 | 0 | 0 | 0 |
| 15 · Settings | 0 | 0 | 0 | 0 | 0 |
| 16 · Help and Glossary | 0 | 0 | 0 | 0 | 0 |
| Total | 0 | 0 | 0 | 0 | 0 |

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

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|

### Backend notes

### Gaps
