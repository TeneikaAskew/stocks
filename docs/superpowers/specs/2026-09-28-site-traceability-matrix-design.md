# Site Traceability Matrix: design

**Date:** 2026-09-28 · **Status:** design approved in conversation, written spec pending review · **Repos:** `TeneikaAskew/stocks`, `TeneikaAskew/solyra`

This is a dated design record (registry class C). It describes the two documents that
together let one person walk the Solyra site area by area and prove, element by element,
what each area needs, what makes it work, and whether that has been specified, traced,
validated and tested.

Related: [`docs/product/README.md`](../../product/README.md) (the living product plan),
[`docs/product/02-FEATURE-CATALOG.md`](../../product/02-FEATURE-CATALOG.md),
[`docs/product/04-BACKEND-API.md`](../../product/04-BACKEND-API.md),
[`docs/product/05-INFRASTRUCTURE.md`](../../product/05-INFRASTRUCTURE.md),
[`docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md`](../../product/infrastructure/05-c-DATA_DEPENDENCIES.md),
[`docs/product/infrastructure/05-e-API.md`](../../product/infrastructure/05-e-API.md),
solyra [`docs/UI-SCREENS.md`](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md).

---

## 1. Why

The product plan traces 26 capabilities to code, tests, PRs and issues. The screen inventory
records each of the 15 routed screens with its API calls and E2E specs. Both stop at the page
or capability level. Nothing lists the elements on a page, nothing walks an element down to
the table and the job that fills it, and neither is a checklist that shows what has been
covered. Two Claude Design documents (the Solyra site map and the backend architecture) were
drawn from these docs and inherited their drift, for example a dashboard labelled "no
per-user auth" and a platform service labelled "FastAPI + React", both true before the #957
split and false now.

**Outcome.** For every area of the site, one place says what is required, what data it
needs, which API, job, table, schedule, GCP resource and external service supply it, where the
code and tests are, and which of four gates each element has earned. Work proceeds area by
area, and a tick is never a claim without evidence.

**Success criteria.**

- A reader can open one document and see every area of the site with its elements, the
  chain behind each element, and four checkboxes per element.
- Every citation in that document is a link that the existing doc audits check.
- Every element ID resolves to a spec entry on the UI side, so a test can be written from it.
- Nothing is duplicated between the new document and the inventories that already exist.
- Drift like the two examples above is recorded as drift, not silently corrected in the
  design and left in the docs.

---

## 2. Decisions taken during brainstorming

| Decision | Choice |
|---|---|
| Where the checklist lives | A new `stocks/docs/product/03-SITE-TRACEABILITY.md`, filling the empty 03 slot of the numbered product plan. The only place gates are ticked. |
| UI-side detail | The existing `solyra/docs/UI-SCREENS.md`, extended in place. No new folder, no per-area files, nothing moved. |
| What a checkbox certifies | Four gates per row: Specified, Traced, Validated, Tested. |
| Row unit | One row per user-visible element (what is displayed, actions), plus one row per required state (loading, empty, error, stale, permission). |
| IDs | `AREA-NN`, area key from the design in upper case, never renumbered. |
| Infrastructure columns | All-inclusive. Every GCP resource the element touches, named, including the Cloud Run service or job and Cloud SQL, and every external service, in two columns. |
| Generation | Hand-authored first. The Chain table's columns line up with what `scripts/maintenance/doc_inventory.py` computes, so a generated region can replace it later without changing the document's shape. Not part of this design. |
| Phasing | Phase 0 builds the framework with every row present and unticked. Phases 1 to 6 work one navigation group each, in site-map order. |
| The design source files | `solyraPages.js` and `arch-details.js` are seeds, not committed. Every line in them is a claim to verify against code before it enters a cell. The designs get regenerated from the docs afterwards. |

---

## 3. Deliverables

Exhaustive. Nothing else is created.

| # | What | Where | New or edit |
|---|---|---|---|
| 1 | The matrix | `stocks/docs/product/03-SITE-TRACEABILITY.md` | new |
| 2 | Per-screen additions (data, elements, states, journeys, acceptance criteria) and two new records (AuthGate, AppShell) | `solyra/docs/UI-SCREENS.md` | edit |
| 3 | Registry row for the matrix, class D, declared code paths `platform/api`, `gcp/deploy.sh`, `gcp/schema.sql`, `lib` | `stocks/docs/DOC_REGISTRY.md` | edit |
| 4 | Registry row for UI-SCREENS.md gains `src/hooks`, `src/lib/authedFetch.ts`, `tests` as declared code paths | `solyra/docs/DOC_REGISTRY.md` | edit |
| 5 | One navigation row for 03 and one snapshot metric ("site elements traced / total") | `stocks/docs/product/README.md` | edit |
| 6 | One line in each PR template: matrix rows touched and gates changed | `stocks/.github/pull_request_template.md`, `solyra/.github/pull_request_template.md` (both exist) | edit |

---

## 4. The matrix document

### 4.1 Layout, in order

1. H1 and the stocks review marker (`Last reviewed`, `Depth`, `Against`, `Owner`).
2. **How to read this.** One paragraph: one section per area in navigation order; each area has a
   Checklist table (what you tick) and a Chain table (where each element's data comes from);
   gates are defined in the document's Gates section; the element ID is the join to the UI spec.
3. **Site outline.** The navigation groups and pages exactly as `src/components/layout/navConfig.ts`
   declares them, plus the three surfaces outside the nav (Landing, AuthGate, AppShell) and the
   SHARED area. Each entry links to its section.
4. **Progress.** One row per area: rows, S, T, V, Te counts, with the derivation recipe beside it
   (section 4.7).
5. **Gates.** The definitions in section 6 of this spec, verbatim, so the document is self-contained.
6. **Areas.** Seventeen sections in the order of section 4.8.

### 4.2 Area section template

```markdown
## NN · <Area title>

UI spec: [UI-SCREENS.md § SCREEN-<KEY>](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md#screen-<key>)
· Capability: [FEAT-XXX-001](02-FEATURE-CATALOG.md#feat-xxx-001)
· Requirements: REQ-UX-001, ... · Route: `/path` · Status: <ladder value from 02>

### Checklist
| ID | Element | S | T | V | Te | Evidence |
|---|---|---|---|---|---|---|
| AREA-01 | ... | [ ] | [ ] | [ ] | [ ] | |

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|
| AREA-01 | ... | ... | ... | ... | ... | ... |

### Backend notes
- pipeline order and times that feed this area
- freshness budget the page assumes
- known gaps in the path

### Gaps
- open issues by row ID, drift between design and code
```

### 4.3 Checklist table

Columns: ID, Element, S, T, V, Te, Evidence.

- Gate cells hold exactly `[ ]` or `[x]`. Nothing else, so the recipe in 4.7 can count them.
- Evidence holds one entry per earned gate, gate letter then date then link, separated by
  ` · `: `S 2026-10-02 [spec](...) · T 2026-10-02 abc1234 · V 2026-10-03 [#1210 (comment)](...) · Te 2026-10-04 [run](...)`.
- The Element cell is a short name. Detail lives in the UI spec entry the ID points at.

### 4.4 Chain table

Seven columns. Every cell is a link or a blank, never free text and never a placeholder word.

| Column | Holds | Source |
|---|---|---|
| API | Method and path, or `none` with the reason: Firebase SDK, localStorage, static content | The app's call sites (`src/hooks`, `src/routes`, `src/components`) and the vendored OpenAPI snapshot `tests/fixtures/stocks-openapi.json` in solyra |
| Backend | Handler file and line, then the `lib/` module that does the math | The generated route table in 05-e (file and line per route); `lib/` by reading the handler |
| Data | Tables the handler reads, each with the job that writes it and its schedule, written `table ← job (time, days)` | 04's tables-touched column, checked against the generated write and read graph in 05-c, and the scheduler declarations in `gcp/deploy.sh` |
| GCP | Every Google Cloud resource in the element's path, named: the Cloud Run service or job, the Cloud Scheduler trigger, Cloud SQL `trading-db`, Secret Manager secret names (never values), the Cloud Tasks queue, Pub/Sub topic, Cloud Logging sink, GCS bucket and prefix, the Vertex AI model, Firebase Auth and its provider, IAP, the service account when it differs from the default | `gcp/deploy.sh` and `platform/deploy.sh` flags, the job inventory in 05 |
| External | Every non-Google dependency: AlphaVantage with the function used, FRED, SEC EDGAR, ForexFactory, Earnings Whispers, Unusual Whales, FinViz, Benzinga, Discord webhook or channel, GitHub, Lovable as the SPA host | The fetcher modules under `gcp/fetchers`, `lib/`, the routers |
| Tests | stocks pytest for the endpoint and for the producing job, then solyra Vitest and Playwright | `tests/api`, `tests/gcp` in stocks; `tests/<page>` and `src/**/*.test.*` in solyra |

Rules:

- Where a fact lives in a generated region (05-c, 05-e), the cell links to that anchor
  instead of restating a line number that will drift.
- Where no inventory exists, such as a secret or a Cloud Tasks queue, the cell names the
  `deploy_*` function in `gcp/deploy.sh`, which the drift check on that path covers.
- What every element inherits (project, region, `trading-runner@` for jobs, the image, the DB
  connection path through `gcp/database.py`) is written once in the SHARED area. Rows list
  only what is specific to them.
- A blank cell means not traced. That is what the T gate records, so blanks are honest and
  words like "to confirm" are forbidden in cells.

### 4.5 Backend notes and gaps

Backend notes hold what a table cannot: the pipeline order that feeds the area with its
times (for Dashboard: fetch-market-data 23:00, backfill-daily-indicators 02:30,
fetch-premarket-refresh 08:20, premarket-brief 08:30, then the brief endpoint), the
freshness budget the page assumes, and known gaps in the path: silent fallbacks carrying an
AUDIT marker, endpoints with no response model (66 of 98 validated trivially on
2026-09-07), scheduler triggers whose job no code deploys, and design drift such as the
"no per-user auth" label.

Gaps list open issues by row ID and any disagreement between the design seeds and the code.
The row records the code as it is; the gap records the design as the target or as stale.

### 4.6 The SHARED area

The design's "Under every page" section becomes area 00. Rows cover what no single page owns:

- the API service (`solyra-api-prod`, `solyra-api-staging`) and the auth middleware
  (`platform/api/auth.py`), its modes and open prefixes
- the data path: `authedFetch`, `apiTargets`, the Vite proxy, the staging fallback
- mock mode and the demo-data banners
- React Query caching defaults
- the failure lane: job log, Cloud Logging sink, Pub/Sub, `failure-notifier`, GitHub issue
- the freshness watchdog and `/api/health/freshness`
- the inherited infrastructure listed once: project, region, service accounts, image, DB path

This keeps the DATA, DEPLOY and OPS capabilities visible from the site view.

### 4.7 Progress rollup and its recipe

The rollup is updated by hand in the same commit as any tick. The recipe that derives it is
written beside the table so the numbers can be re-checked:

```bash
# whole document; run between two "## NN ·" headings for one area
awk -F'|' '$2 ~ /^ *[A-Z]+-[0-9]+ *$/ && $4 ~ /\[[ x]\]/ {
  n++; s+=($4~/x/); t+=($5~/x/); v+=($6~/x/); te+=($7~/x/)
} END { print n, s, t, v, te }' docs/product/03-SITE-TRACEABILITY.md
```

The `$4 ~ /\[[ x]\]/` test selects Checklist rows only; Chain rows share the ID column but
carry text in column four.

### 4.8 The seventeen areas

| Order | Area | ID prefix | Route | UI spec anchor |
|---|---|---|---|---|
| 00 | Shared, under every page | `SHARED` | all | cross-cutting specs section |
| 01 | Landing | `LANDING` | `/` | `SCREEN-LANDING` |
| 02 | AuthGate and sign-in | `AUTH` | in-route state on every app route | `SCREEN-AUTH` (new) |
| 03 | AppShell | `SHELL` | layout for the 13 app pages | `SCREEN-SHELL` (new) |
| 04 | Dashboard | `DASHBOARD` | `/dashboard` | `SCREEN-DASHBOARD` |
| 05 | Live Market | `LIVE` | `/live` | `SCREEN-LIVEMARKET` |
| 06 | Charts | `CHARTS` | `/charts` | `SCREEN-CHARTS` |
| 07 | Options Flow | `OPTIONS` | `/options` | `SCREEN-OPTIONSFLOW` |
| 08 | Signals | `SIGNALS` | `/signals` | `SCREEN-SIGNALS` |
| 09 | AI Insights | `INSIGHTS` | `/insights` | `SCREEN-INSIGHTS` |
| 10 | Catalysts | `CATALYSTS` | `/catalysts` | `SCREEN-CATALYSTS` |
| 11 | Playbook | `PLAYBOOK` | `/playbook` | `SCREEN-PLAYBOOK` |
| 12 | Reports | `REPORTS` | `/reports` | `SCREEN-REPORTS` |
| 13 | Journal | `JOURNAL` | `/journal` | `SCREEN-JOURNAL` |
| 14 | Admin | `ADMIN` | `/admin` | `SCREEN-ADMIN` |
| 15 | Settings | `SETTINGS` | `/settings` | `SCREEN-SETTINGS` |
| 16 | Help and Glossary | `HELP` | `/help` | `SCREEN-HELP` |

The `/welcome` redirect keeps its existing record and gets no rows. The FAQ anchor `/#faq`
is part of Landing.

---

## 5. Rows and IDs

- One row per user-visible element, drawn from the design's "what's displayed" and "actions"
  lists and checked against the page source.
- One row per required state on every page that renders data: loading, empty, error, stale,
  permission (the auth-blocked "Sign in to load data" presentation). This is REQ-UX-001 made
  checkable per page. Expect about 200 rows across the site.
- Feeds are not rows. An endpoint is the API cell of the element that needs it.
- IDs are `AREA-NN`, two digits, assigned in Phase 0 in the order the design lists elements
  and states. They never get renumbered. A retired element keeps its ID with "retired" in the
  Element cell, so an issue or a test title that cites it still resolves.
- IDs sit beside the existing `FEAT-`, `SCREEN-`, `REQ-` and `MODEL-` families and replace none.

---

## 6. Gates

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
solyra Vitest runs in solyra CI; solyra Playwright runs in solyra CI too, in the `e2e
(chromium, mocked)` job (green on run 36361217691). A Playwright-only element ticks Te by
citing a CI run that executed its test; a row whose test was added on a branch waits for a
run that includes it. The gate shows the blocker instead of hiding it. Evidence: test file
links and a CI run link.

Rules:

- V requires T. Te requires S. S and T are independent.
- A tick is a claim with an evidence entry and date in the same commit.
- Nothing un-ticks automatically. The registry drift check queues the document when its
  declared code paths move; the flagged area's V and Te are then re-earned, not carried.

---

## 7. UI-SCREENS.md additions

Every existing per-screen record keeps every field it has today (purpose, status, blocking
issue, owner, component, child components, API calls, stores, states, E2E specs, PR lineage,
target) and gains these subsections, in this order:

```markdown
#### Data it needs
| Endpoint | Fields read | Produced by | Freshness assumed | Consumer |
|---|---|---|---|---|
| GET /api/dashboard/brief/{ticker} | bias, ftfc, strat candle and combo, rsi, signal status | premarket-brief 08:30 ET weekdays → premarket_analysis | today's brief by 08:30, else "unavailable" | useInsights → briefing strip |
| store: ticker, review date | | Zustand, per session | | every card |

#### Displayed
| ID | Element | Component |
|---|---|---|

#### Actions
| ID | Action | What happens |
|---|---|---|

#### States
| ID | State | Present in source | Presentation |
|---|---|---|---|

#### Journeys
1. <name>: step (IDs touched) → step → step

#### Elements
##### AREA-NN · <Element>
Shows or does · Needs · States · Acceptance criteria (Given / When / Then) · Tests · Code (component, test ids)
```

- The "Data it needs" table is the contract. Non-API inputs get rows too: stores, localStorage,
  static content, mock fixtures. The type in `src/types/` and the typed fixture in
  `tests/helpers/fixtures/` are cited as the sample payload, since the contract test already
  validates both against the OpenAPI snapshot.
- Each journey is the outline of one Playwright test.
- The Elements subsection is what the S gate points at. Its heading carries the ID so the anchor
  is stable: `#area-nn--element`.
- Two records are added: `SCREEN-AUTH` (AuthGate and SignInScreen, an in-route state, no
  `/login` route) and `SCREEN-SHELL` (AppShell: nav, header, banners, most-active marquee,
  command palette, route error boundary). The existing "States present/absent" line becomes
  the States table.
- Every existing heading anchor is preserved. Nothing linking in from the stocks docs breaks.
- Expected size: from about 26 KB to roughly 100 to 120 KB. The model registry in stocks is
  145 KB, so this is within the repos' norms.

---

## 8. Cross-repo linking

- Inside a repo, links are relative. Across repos, links are `blob/main` GitHub URLs, the
  pattern both repos already use.
- The matrix links each area to its UI-SCREENS.md record and each Elements entry by anchor.
  Each record links back to its matrix section. Anchors are GitHub's heading slugs; the
  implementation plan pins each one.
- What is machine-checked: relative links and registry drift in each repo by its own audit
  (`node scripts/docs-audit.mjs --check` in solyra, `python -m scripts.maintenance.docs_audit --check`
  in stocks; the two share a CLI). What is not machine-checked: that a cross-repo anchor
  exists. That check is a manual step in every phase (section 10), and a candidate for a
  small script later.

---

## 9. Phases

### Phase 0, the framework

One PR per repo.

Stocks PR:

- the matrix with layout 4.1, all seventeen area sections in the order of 4.8, every element
  and state row present with an ID, all gates `[ ]`, Evidence empty
- Chain cells filled only where an existing inventory answers them (route file and line from
  05-e, tables from 04 checked against 05-c, producer job and schedule from 05 and
  `deploy.sh`); every other cell blank
- Backend notes seeded from the pipeline order and the design's lineage, each line verified
  against `deploy.sh` before it is written
- registry row, README navigation row and snapshot metric, PR template line

Solyra PR:

- `SCREEN-AUTH` and `SCREEN-SHELL` records
- Displayed and Actions tables with IDs for every screen, seeded from the design data and
  checked against the page source as they are written
- States tables converted from the existing lines
- Data it needs tables where the API calls and hooks already answer them
- Elements entries as headings with the ID, body empty except what the seed provides
- registry row change, PR template line

After Phase 0 the whole site is visible in one place with an honest, mostly empty scorecard.
Phase 0 ticks nothing.

### Phases 1 to 6, one navigation group each

| Phase | Areas |
|---|---|
| 1 | Entry path: Landing, AuthGate, AppShell, SHARED |
| 2 | Dashboard |
| 3 | Market: Live, Charts, Options Flow, Signals |
| 4 | Intelligence: AI Insights, Catalysts |
| 5 | Learn: Playbook, Reports, Journal |
| 6 | Support: Admin, Settings, Help |

Each phase is a PR per repo, or one per area for the large pages (Dashboard, Charts, Journal).

The implementation plan that follows this spec covers Phase 0 in full and Phase 1 as the
worked exemplar. Later phases reuse the Phase 1 procedure without a new spec.

### Working a row

1. Write the element's entry in UI-SCREENS.md with acceptance criteria. Tick S.
2. Complete the Chain row and verify every link resolves. Tick T.
3. Run the production check, paste the command and its output into the PR or issue, link it.
   Tick V.
4. Write or locate the tests, link the CI run. Tick Te.
5. Update the progress rollup. Each tick lands in the same commit as its evidence.

An area is done when every row has four ticks and no blocker issue is open. Only then is its
capability status in 02 reconsidered.

---

## 10. Day-to-day conventions

- Every new issue names the row IDs it affects in its title or body. The matrix's Evidence or
  Gaps cell links the issue back.
- Each PR template carries one line, "Matrix rows touched and gates changed", so a PR that
  moves code behind a row has to say so.
- The capability-level PR and issue traceability document (12) keeps its job. The matrix works
  one level down.
- Both doc audits run as today. When they flag the matrix or UI-SCREENS.md for drift, the
  flagged area's V and Te are re-earned.
- Cross-repo anchor check, every phase: for each ID in the matrix, confirm the heading exists
  in UI-SCREENS.md, and for each ID heading in UI-SCREENS.md, confirm the Checklist row exists.
- The two Claude Design documents are regenerated from the docs after Phase 1, not before.

---

## 11. Failure handling

- A validation that fails leaves V unticked and files an issue with the row ID.
- A producer job that cannot be identified leaves the Data cell blank and adds a Gaps line.
- An endpoint with no test leaves the Tests cell partly blank and Te unticked.
- Where code and design disagree, the row records the code and the Gaps line records the design
  as the target or as stale.
- Bugs found while validating are filed with the row ID and fixed in their own PRs. A phase PR
  changes documentation, tests and the matrix, not product behaviour, unless the fix is a
  one-line correction the reviewer can see whole.

---

## 12. Verification of Phase 0

Phase 0 is right when all of these hold and their output is in the PR:

1. `03-SITE-TRACEABILITY.md` has seventeen `## NN ·` sections in the order of 4.8.
2. Every Checklist ID matches `^[A-Z]+-[0-9]{2}$` and is unique across the document:
   Checklist rows are the ones whose fourth cell is a gate box, which keeps the Chain rows
   (same IDs) out of the count:
   `awk -F'|' '$4 ~ /\[[ x]\]/ {gsub(/ /,"",$2); print $2}' docs/product/03-SITE-TRACEABILITY.md | sort | uniq -d`
   prints nothing.
3. The recipe in 4.7 prints `N 0 0 0 0` with N the row total, and N matches the Progress table.
4. No table cell contains `TBD`, `TODO`, `to confirm` or `?`:
   `grep -nE '^\|.*(TBD|TODO|to confirm|\?)' docs/product/03-SITE-TRACEABILITY.md` prints nothing.
5. Every API cell's path exists in the vendored OpenAPI snapshot in solyra, checked with a
   one-line script in the PR, and `npm run contract:check` is green.
6. `python -m scripts.maintenance.docs_audit --check` passes in stocks;
   `node scripts/docs-audit.mjs --check` passes in solyra.
7. Every ID in the matrix has a heading in UI-SCREENS.md and every ID heading in UI-SCREENS.md
   has a Checklist row (the cross-repo check, run by hand with both repos checked out).
8. Every existing UI-SCREENS.md heading anchor still exists.
9. The README navigation row, the snapshot metric, both registry rows and both PR template
   lines are present.

---

## 13. Out of scope, and later

- Generating the Chain table from `doc_inventory.py`. Later ratchet once the hand-written
  version shows which columns matter.
- A mirrored copy of the matrix in solyra. Links first; the contract-sync pattern can mirror
  it later if a physical copy is wanted.
- Restating any inventory (04, 05, 05-c, 05-e, 06) or any capability record (02, 11, 12).
- Changing the UI-SCREENS.md inventory tables or the "Live URLs" section.
- Fixing the bugs the validation finds, beyond one-line corrections.
- Renumbering existing product documents.

---

## 14. Risks and open items

- **Te for Playwright-only rows cites a CI run that executed the test.** solyra CI
  (`.github/workflows/ci.yml`) runs the `checks` and `e2e (chromium, mocked)` jobs on pull
  requests and pushes to `main` (green on run 36361217691). A row whose test was added on this
  branch still waits for a run that includes it.
- **Cross-repo anchors are not machine-checked.** Item 7 in section 12 is manual until a script
  exists.
- **UI-SCREENS.md grows four to five times.** Anchors keep it navigable; if it becomes
  unworkable that is a decision to revisit, not a reason to split it now.
- **Seeds drift.** The design data already disagrees with UI-SCREENS.md in at least one place
  (Settings: the inventory says zero API calls and localStorage only; the design and the
  current hooks show `/api/me/preferences` and `/api/me/profile`). Every seed line is verified
  against code before it enters a cell, and each disagreement becomes a Gaps line.
- **Phase 0 volume.** About 200 rows across seventeen areas. The seeds carry the element lists
  and the lineage, so the work is verification, not invention.

---

## Appendix A. Seeds and how far to trust them

| Seed | Gives | Trust |
|---|---|---|
| `solyraPages.js` (design data, per page: feeds, displayed, actions, journeys, issues) | element lists and journeys for 16 areas | claims; derived from `src/routes`, `src/hooks`, `src/components/layout` and UI-SCREENS.md on `main` at an unknown date |
| `arch-details.js` (design data: jobs with reads, writes, module, surface; crons; lineage) | producer jobs, schedules, upstream and downstream per node | claims; crons say "as declared in `gcp/deploy.sh` at HEAD, 2026-09-07" |
| UI-SCREENS.md records | states detected in source, E2E specs, PR lineage | verified 2026-08-30, scanned 2026-09-16 |
| 04, 05, 05-c, 05-e, 06 | endpoints, tables touched, jobs, schedules, write and read graph | 05-c and 05-e are generated; 04 and 05 are living docs reviewed 2026-08-31 |
| 02, 11, 12 | capability status, code locus, PRs and issues | living docs reviewed 2026-08-31 |

A seed line enters a cell only after it is checked against the code or `deploy.sh` at the
commit named in the review marker.

## Appendix B. Example area, AuthGate

Illustrative. Cells left blank are exactly the cells Phase 0 would leave blank.

```markdown
## 02 · AuthGate and sign-in

UI spec: [UI-SCREENS.md § SCREEN-AUTH](https://github.com/TeneikaAskew/solyra/blob/main/docs/UI-SCREENS.md#screen-auth)
· Capability: [FEAT-AUTH-001](02-FEATURE-CATALOG.md#feat-auth-001)
· Requirements: REQ-UX-001, REQ-ACCESS-001 · Security: [09](09-SECURITY-AUTH.md)

### Checklist
| ID | Element | S | T | V | Te | Evidence |
|---|---|---|---|---|---|---|
| AUTH-01 | Auth-mode bootstrap (firebase, iap, open) | [ ] | [ ] | [ ] | [ ] | |
| AUTH-02 | Loading spinner while the session resolves | [ ] | [ ] | [ ] | [ ] | |
| AUTH-03 | Google sign-in, with the new-tab variant when framed | [ ] | [ ] | [ ] | [ ] | |
| AUTH-04 | Email and password sign-in with inline error | [ ] | [ ] | [ ] | [ ] | |
| AUTH-05 | Sign-up mode | [ ] | [ ] | [ ] | [ ] | |
| AUTH-06 | Forgot password: reset email, then /auth/action | [ ] | [ ] | [ ] | [ ] | |
| AUTH-07 | Identity and role read (email, admin, dev) | [ ] | [ ] | [ ] | [ ] | |
| AUTH-08 | 401 on a gated call shows "Sign in to load data" | [ ] | [ ] | [ ] | [ ] | |
| AUTH-09 | Sign out | [ ] | [ ] | [ ] | [ ] | |

### Chain
| ID | API | Backend | Data | GCP | External | Tests |
|---|---|---|---|---|---|---|
| AUTH-01 | GET /api/config/firebase | routers/config.py:45 | none | solyra-api-staging, solyra-api-prod; env FIREBASE_API_KEY, FIREBASE_AUTH_DOMAIN, FIREBASE_PROJECT_ID, FIREBASE_APP_ID on the service (platform/deploy.sh) | | solyra src/lib/authGate.test.ts, tests/shared/auth-gate.spec.ts |
| AUTH-03 | none (Firebase SDK) | token verified per call, api/auth.py:136 | none | Firebase Auth, Google provider, authorized domains | | solyra tests/shared/auth-gate.spec.ts |
| AUTH-06 | none (Firebase SDK) | email templates gcp/auth_email_templates.py, docs/AUTH_EMAILS.md | none | Firebase Auth action links | | solyra src/lib/authAction.test.ts |
| AUTH-07 | GET /api/me | platform/api/main.py:282, stored_role_for in api/auth.py:250 | user_roles | solyra-api-staging, solyra-api-prod; IAP on prod | | |
| AUTH-08 | any gated /api/* | api/auth.py middleware, 401 | none | | | solyra src/lib/authedFetch.test.ts |

### Backend notes
- Auth is global ASGI middleware, not a per-router dependency. It verifies a bearer token
  only when AUTH_MODE=firebase; in iap and open it calls through (09).
- The open prefixes are /api/health, /api/config/firebase, /api/waitlist in api/auth.py and must
  stay in sync with OPEN_PREFIXES in solyra src/lib/authedFetch.ts.

### Gaps
- The design's backend diagram labels the dashboard "no per-user auth" and the platform
  service "FastAPI + React"; both predate the #957 split.
```

## Status, 2026-10-08

Appended under the registry's rule for dated records (class C): the design above is the one the
owner approved and is not rewritten.

- **Approved and built.** The owner reviewed this written spec on 2026-09-28 and asked for the
  implementation plan, so the header's "written spec pending review" describes the day it was
  written. The matrix and the screen inventory were built to it in stocks#1338, with the
  follow-ups stocks#1347 and stocks#1348.
- **Te and state rows.** Where a state has its own Checklist row, as this design lays it out
  ("every element and state row present with an ID"), the state's coverage is that row's own
  Te. An element row's Te covers the element and any state that has no row of its own. Settled
  under stocks#1345 (item 6, closed on 2026-10-08): holding an element's tick until its state
  rows are covered would make the tick a roll-up of other rows and hide coverage the element
  has, while the progress table, which counts rows, already shows each uncovered state as its
  own unticked Te.
- **V and permission states.** V validates the production path's answer. A recorded request and
  response on staging, the evidence the V definition names, validates a permission state: the
  recorded 401 is the answer the page renders, and how the page renders it is client behaviour
  that Te covers. Settled under stocks#1345 (item 5, closed on 2026-10-08): every V tick in the
  matrix rests on a recorded staging response, so asking only the permission rows for a browser
  observation would hold them to a different standard.
- **The deployment layer.** A row whose chain cites configuration that `platform/deploy.sh` sets
  is ticked at Te only with a test of that configuration. That test is
  `tests/gcp/test_platform_deploy_service_config.py` (stocks#1350), which runs the script
  against a stub `gcloud` and asserts what each service is deployed with.
