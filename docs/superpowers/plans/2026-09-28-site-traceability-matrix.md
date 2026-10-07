# Site Traceability Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the site-organized traceability matrix in stocks and the element-level additions to solyra's screen inventory, with every row present and unticked (Phase 0), then walk the entry path (Landing, AuthGate, AppShell, SHARED) through all four gates as the worked exemplar (Phase 1).

**Architecture:** Two documents. `stocks/docs/product/03-SITE-TRACEABILITY.md` is the checklist: seventeen area sections, each with a Checklist table (ID, element, four gates, evidence) and a seven-column Chain table (API, backend, data, GCP, external, tests). `solyra/docs/UI-SCREENS.md` is extended in place with per-screen Data, Displayed, Actions, States, Journeys and Elements subsections whose headings carry the same IDs. Both repos' doc audits and link checks are the test harness; nothing new is generated.

**Tech Stack:** Markdown, GitHub-flavored tables, bash (`grep`, `awk`, `jq`, `curl`), `python -m scripts.maintenance.docs_audit` (stocks), `node scripts/docs-audit.mjs` (solyra), `scripts/db_query_cr.sh` (stocks), Playwright and Vitest (solyra), pytest (stocks).

**Spec:** `docs/superpowers/specs/2026-09-28-site-traceability-matrix-design.md` (stocks). Read it first; sections are cited below as "spec §N".

## Global Constraints

- Both repos are checked out side by side at `/home/user/stocks` and `/home/user/solyra`, both on branch `claude/inspiring-cori-k9lz5g`. Commit on that branch. Never force-push, rebase or amend a pushed commit (solyra is Lovable-connected). Do not open pull requests unless the user asks.
- Commit messages: conventional format, imperative mood, no AI attribution of any kind (both repos' CLAUDE.md). Stocks uses `type: description`; solyra uses `type(scope): description`.
- Exactly one new file across both repos: `docs/product/03-SITE-TRACEABILITY.md` in stocks. Every other change edits an existing file (spec §3).
- Gate cells hold exactly `[ ]` or `[x]`. Phase 0 ticks nothing. A tick lands in the same commit as its Evidence entry (spec §6).
- No table cell may contain `TBD`, `TODO`, `to confirm` or `?`. A blank cell means not traced (spec §4.4).
- Every citation is a link or a backticked repo path. Backticked paths are repository-root relative (`platform/api/routers/config.py:45`, never `routers/config.py`), because both audits treat a backticked path with a slash and an extension as a repo path and flag a missing one. Relative markdown links may carry `#L45`. Cross-repo links are `https://github.com/TeneikaAskew/<repo>/blob/main/...`.
- Area headings in the matrix are `## NN · Title` exactly as listed in spec §4.8, and no other `##` heading in that file starts with two digits. Element headings in UI-SCREENS.md are `##### AREA-NN · Element name`.
- New prose uses the middle dot `·` as separator, like the existing docs, and no em or en dashes.
- Seeds (spec Appendix A) live outside the repos at `/tmp/claude-0/-home-user/1672b327-2e71-5285-ae08-5c932e37a085/scratchpad/designs/solyraPages.js` and `arch-details.js`. If that directory is gone, ask the user to re-upload the two files. A seed line enters a cell only after it is checked against the code or `gcp/deploy.sh`.
- Every task ends by running the recipes it names (section "Verification recipes") and pasting their output into the commit body or the PR description.

## Review Focus

1. An ID that exists in one document but not the other (a heading renamed, a row added on one side): the join breaks silently. Recipe R8 pins it, owned by Task 10 and re-run by every Phase 1 task.
2. An API cell naming a path the API no longer declares (renamed endpoint, typo in a template like `{ticker}`): the row traces to nothing. Recipe R6 pins it, owned by Tasks 3 to 6.
3. A gate ticked with no Evidence entry, or V ticked before T, or Te before S: the checklist lies. Recipe R10 pins it, owned by Task 11 and re-run by Tasks 12 to 14.
4. The Progress table disagreeing with the rows (a row added, the table not updated): the rollup misleads. Recipe R3 pins it, owned by Task 2 and re-run by every later task.
5. An existing UI-SCREENS.md anchor disappearing while records are extended (a heading edited by hand): links from the stocks product plan 404. Recipe R9 pins it, owned by Tasks 8 to 10.

---

## Verification recipes

Run from the repo root named in each recipe. "Prints nothing" means an empty stdout and exit 0 unless stated.

**R1 · sections (stocks).**
```bash
grep -nE '^## [0-9]{2} · ' docs/product/03-SITE-TRACEABILITY.md
```
Expected: exactly 17 lines, numbers 00 to 16 in order, titles as in spec §4.8.

**R2 · Checklist IDs unique and well-formed (stocks).**
```bash
awk -F'|' '$4 ~ /\[[ x]\]/ {gsub(/ /,"",$2); print $2}' docs/product/03-SITE-TRACEABILITY.md | sort | uniq -d
awk -F'|' '$4 ~ /\[[ x]\]/ {gsub(/ /,"",$2); print $2}' docs/product/03-SITE-TRACEABILITY.md | grep -vcE '^[A-Z]+-[0-9]{2}$'
```
Expected: first command prints nothing; second prints `0`.

**R3 · progress rollup (stocks).**
```bash
awk -F'|' '$2 ~ /^ *[A-Z]+-[0-9]+ *$/ && $4 ~ /\[[ x]\]/ {
  n++; s+=($4~/x/); t+=($5~/x/); v+=($6~/x/); te+=($7~/x/)
} END { print n, s, t, v, te }' docs/product/03-SITE-TRACEABILITY.md
```
Expected: five numbers that equal the Total row of the Progress table. Per area, wrap the file in `sed -n '/^## 02 · /,/^## 03 · /p'` and compare with that area's row.

**R4 · no placeholder words in cells (stocks).**
```bash
grep -nE '^\|.*(TBD|TODO|to confirm|\?)' docs/product/03-SITE-TRACEABILITY.md
```
Expected: prints nothing.

**R5 · every Chain ID has a Checklist row (stocks).**
```bash
F=docs/product/03-SITE-TRACEABILITY.md
comm -13 <(awk -F'|' '$4 ~ /\[[ x]\]/ {gsub(/ /,"",$2); print $2}' $F | sort -u) \
         <(awk -F'|' '$2 ~ /^ *[A-Z]+-[0-9]{2} *$/ && $4 !~ /\[[ x]\]/ {gsub(/ /,"",$2); print $2}' $F | sort -u)
```
Expected: prints nothing.

**R6 · every API path exists in the vendored OpenAPI snapshot (stocks, needs solyra beside it).**
```bash
F=docs/product/03-SITE-TRACEABILITY.md; SNAP=../solyra/tests/fixtures/stocks-openapi.json
grep -oE '\b(GET|POST|PUT|PATCH|DELETE) /api/[^ |`]+' $F | sort -u | while read -r m p; do
  jq -e --arg p "$p" --arg m "$(echo $m | tr A-Z a-z)" '.paths[$p][$m]' $SNAP >/dev/null || echo "MISSING $m $p"
done
```
Expected: prints nothing. A path the app calls with a concrete value (`/api/market/data/IWM/20260424`) is written in the cell with the snapshot's template (`/api/market/data/{ticker}/{date}`).

**R7 · doc audits show no P1 or P2 finding on the touched document.**
Both audits read GitHub issue state through `gh`, which returns 403 in a Claude Remote session. Provide an issues snapshot instead. Shape, identical for both tools:
```json
{ "capturedAt": "2026-09-28T15:00:00Z",
  "stocks": { "28": {"state": "open", "kind": "ISSUE"}, "1204": {"state": "closed", "kind": "PR"} },
  "solyra": { "28": {"state": "open", "kind": "ISSUE"} } }
```
Every issue and PR number cited in the touched documents must appear, both repo maps must be non-empty, and the capture must be at most one day old. On a machine where `gh` works, write it with `--write-issues-snapshot snap.json` (either tool). In a Remote session, build it from the GitHub MCP tools: `list_issues` and `list_pull_requests` with `state` unset (both states), all pages, for both repos, mapping each number to `state` and `kind` (`ISSUE` or `PR`). Keep `snap.json` outside the repos.
```bash
# stocks
python -m scripts.maintenance.docs_audit --issues-snapshot /path/snap.json --json \
  | jq '[.findings[] | select(.doc=="docs/product/03-SITE-TRACEABILITY.md" and (.severity=="P1" or .severity=="P2"))]'
# solyra
node scripts/docs-audit.mjs --issues-snapshot /path/snap.json --json \
  | jq '[.findings[] | select(.doc=="docs/UI-SCREENS.md" and (.severity=="P1" or .severity=="P2"))]'
```
Expected: `[]` from each. If the top-level key is not `findings`, print `jq 'keys'` first and adjust; the finding objects carry `check`, `doc`, `severity`.

**R8 · IDs match across repos (run from /home/user).**
```bash
comm -3 <(awk -F'|' '$4 ~ /\[[ x]\]/ {gsub(/ /,"",$2); print $2}' stocks/docs/product/03-SITE-TRACEABILITY.md | sort -u) \
        <(grep -oE '^##### [A-Z]+-[0-9]{2} ' solyra/docs/UI-SCREENS.md | awk '{print $2}' | sort -u)
```
Expected: prints nothing.

**R9 · existing UI-SCREENS.md anchors preserved (solyra).** Before the first edit of a task:
```bash
git show HEAD:docs/UI-SCREENS.md | grep -E '^#{1,4} ' | sort -u > /tmp/anchors-before.txt
```
After editing:
```bash
comm -23 /tmp/anchors-before.txt <(grep -E '^#{1,4} ' docs/UI-SCREENS.md | sort -u)
```
Expected: prints nothing.

**R10 · gate and evidence consistency (stocks).**
```bash
awk -F'|' '$4 ~ /\[[ x]\]/ {
  id=$2; gsub(/ /,"",id); s=($4~/x/); t=($5~/x/); v=($6~/x/); te=($7~/x/); e=$8
  if (v && !t) print id " V without T"; if (te && !s) print id " Te without S"
  if (s && e !~ /S 20[0-9][0-9]-/) print id " S without evidence"; if (t && e !~ /T 20[0-9][0-9]-/) print id " T without evidence"
  if (v && e !~ /V 20[0-9][0-9]-/) print id " V without evidence"; if (te && e !~ /Te 20[0-9][0-9]-/) print id " Te without evidence"
}' docs/product/03-SITE-TRACEABILITY.md
```
Expected: prints nothing.

**Staging and token recipe (Phase 1 V gates).** `STAGING=https://solyra-api-staging-5sjtb3yl7a-ue.a.run.app`. It runs `AUTH_MODE=firebase` with open sign-up (probed 2026-09-28: `/api/config/firebase` returns `authMode: firebase`; `/api/market/most-active` without a token returns 401). For gated calls, mint a Firebase ID token with a test account the user supplies through environment variables, never written to any file:
```bash
API_KEY=$(curl -sS $STAGING/api/config/firebase | jq -r .firebase.apiKey)
TOKEN=$(curl -sS "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=$API_KEY" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$SOLYRA_E2E_EMAIL\",\"password\":\"$SOLYRA_E2E_PASSWORD\",\"returnSecureToken\":true}" | jq -r .idToken)
curl -sS -H "Authorization: Bearer $TOKEN" $STAGING/api/me
```
Evidence pasted into a PR or issue comment shows the command, the HTTP status and the body with `apiKey`, `idToken` and any bearer value replaced by `<redacted>`.

---

## Phase 0, stocks

### Task 1: Matrix skeleton

**Files:**
- Create: `docs/product/03-SITE-TRACEABILITY.md`

**Interfaces:**
- Produces: the file, its seventeen `## NN · Title` headings (spec §4.8), the Checklist and Chain table headers every later task appends rows to, the Progress table with a `Total` row.

- [ ] **Step 1: Run R1.** Expected: prints nothing (file absent). This is the failing check.

- [ ] **Step 2: Write the skeleton** with, in order (spec §4.1): the H1 `# Site Traceability Matrix`; the marker line `**Last reviewed:** unknown · **Owner:** TBD` (no `Depth` or `Against` beside `unknown`, which the audit reports as P2); `## How to read this` (one paragraph from spec §4.1 item 2); `## Site outline` (the five nav groups and pages from `../../solyra` `src/components/layout/navConfig.ts`, plus Landing, AuthGate, AppShell, SHARED, each linking to its section); `## Progress` with columns `Area | Rows | S | T | V | Te`, one row per area with zeros and a `Total` row, and recipe R3 in a fenced block beneath it; `## Gates` (spec §6 verbatim); then the seventeen area sections from spec §4.2, each with the links line, an empty Checklist table (header only), an empty Chain table (header only), `### Backend notes` and `### Gaps` as empty bullet lists.

- [ ] **Step 3: Run R1, R3, R4.** Expected: R1 lists 17 headings in order; R3 prints `0 0 0 0 0`; R4 prints nothing.

- [ ] **Step 4: Commit.**
```bash
git add docs/product/03-SITE-TRACEABILITY.md
git commit -m "docs: add the site traceability matrix skeleton"
```

### Task 2: Every Checklist row, all seventeen areas

**Files:**
- Modify: `docs/product/03-SITE-TRACEABILITY.md` (each area's Checklist table and the Progress table)

**Interfaces:**
- Consumes: Task 1's headers.
- Produces: the 222 IDs in Appendix A of this plan. Every later task and every UI-SCREENS.md heading uses these IDs and never renumbers them.

- [ ] **Step 1: Run R2 and R3.** Expected: R2 prints nothing and `0`; R3 prints `0 0 0 0 0`.

- [ ] **Step 2: Add the rows** from Appendix A, one per line, in ID order, with `[ ]` in all four gate cells and an empty Evidence cell. Element text is the Appendix A label; a state row's label is `State: loading` and so on.

- [ ] **Step 3: Update the Progress table** so each area's `Rows` equals its Appendix A count and `Total` equals 222.

- [ ] **Step 4: Run R2, R3, R4.** Expected: R2 prints nothing and `0`; R3 prints `222 0 0 0 0`; R4 prints nothing. Compare each area with the per-area form of R3.

- [ ] **Step 5: Commit.** `git commit -am "docs: add every element row to the site traceability matrix"`

### Task 3: Chain rows from inventories, areas 00 to 04

**Files:**
- Modify: `docs/product/03-SITE-TRACEABILITY.md` (Chain, Backend notes, Gaps for SHARED, Landing, AuthGate, AppShell, Dashboard)
- Read: `docs/product/04-BACKEND-API.md`, `docs/product/05-INFRASTRUCTURE.md`, `docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md`, `docs/product/infrastructure/05-e-API.md`, `gcp/deploy.sh`, `../solyra/src/routes/*.tsx`, `../solyra/src/hooks/*.ts`, `../solyra/src/components/**`

**Interfaces:**
- Consumes: Task 2's IDs.
- Produces: one Chain row per Checklist ID in these areas, cells filled only where a source below answers, blank otherwise.

- [ ] **Step 1: Run R5 and R6.** Expected: R5 prints every ID of these areas (no Chain rows yet); R6 prints nothing.

- [ ] **Step 2: API column.** For each area, list the page's calls: `grep -ohE "['\"\`]/api/[-a-zA-Z0-9_/{}]+" ../solyra/src/routes/<Page>.tsx` plus the hooks and child components that page imports (follow the imports one level). Write `METHOD /api/path` using the snapshot's template form. Assign each call to the element that renders it; a call no element owns goes to the area's Backend notes, not a row. Static content, localStorage and the Firebase SDK are written `none (reason)`.

- [ ] **Step 3: Backend column.** For each API path, copy the `Defined` link target from `docs/product/infrastructure/05-e-API.md` as a relative link `[config.py:45](../../platform/api/routers/config.py#L45)`, then read that handler and name the `lib/` module it calls, if any, as a backticked root-relative path.

- [ ] **Step 4: Data column.** Tables from the `Tables touched` cell of the same route in `docs/product/04-BACKEND-API.md`, checked against the table's reader list in 05-c (`### \`table\`` heading under `inventory:reads`). Writer job from the same table's `inventory:writes` list mapped to its job in `docs/product/05-INFRASTRUCTURE.md`; schedule from `grep -nE '^\s*_schedule(_brief)? "' gcp/deploy.sh` (trigger name, cron, job). Write `table ← job (HH:MM ET, days)` with the trigger name linked: `[fetch-market-data-daily](../../gcp/deploy.sh)`. `via lib/` in 04 means read the handler.

- [ ] **Step 5: GCP and External columns.** From `platform/deploy.sh` (the API service: service names, env, secrets, IAP) and the job's `deploy_*` function in `gcp/deploy.sh` (`--set-secrets`, queue, bucket, model, Discord webhook secret). Name resources; never a value. AuthGate rows name `Firebase Auth` and the provider; Landing names `Lovable` under External.

- [ ] **Step 6: Tests column.** `grep -lE '<api path regex>' tests/api/*.py tests/gcp/*.py` here and `grep -rlE '<path>' ../solyra/tests ../solyra/src --include='*.spec.ts' --include='*.test.ts*'` there. Cite files as links: stocks relative, solyra as GitHub URLs.

- [ ] **Step 7: Backend notes and Gaps.** For each area: the pipeline order feeding it (jobs and times from Step 4, in time order), the freshness the page assumes (from the page's copy, such as the brief's "by 08:30"), and gaps: silent fallbacks with an `AUDIT-2026-05-13` marker in the handlers read (`grep -n AUDIT-2026-05-13 <handler>`), untyped responses (routes without `response_model`), the two design-drift lines from spec §4.5 for SHARED. SHARED's Backend notes also carry, once, what every row inherits: project `adept-mountain-474619-d4`, region `us-east1`, the `trading-runner@` service account for jobs, the image the `deploy_*` functions reference, and the Cloud SQL connection path through `gcp/database.py` (spec §4.4).

- [ ] **Step 8: Run R4, R5, R6, R7 (stocks).** Expected: R4 nothing; R5 nothing for these areas; R6 nothing; R7 `[]`.

- [ ] **Step 9: Commit.** `git commit -am "docs: trace the entry path and dashboard chains from the inventories"`

### Task 4: Chain rows from inventories, areas 05 to 08 (Live, Charts, Options Flow, Signals)

Same files, steps and recipes as Task 3 for these four areas.

- [ ] **Steps 1 to 8 as Task 3.**
- [ ] **Step 9: Commit.** `git commit -am "docs: trace the market group chains from the inventories"`

### Task 5: Chain rows from inventories, areas 09 to 12 (AI Insights, Catalysts, Playbook, Reports)

- [ ] **Steps 1 to 8 as Task 3.** Insights rows name `Vertex AI` and the `model_routing` table under GCP and Data; the Cloud Tasks queue `insight-pipeline-queue` belongs to the refresh action row.
- [ ] **Step 9: Commit.** `git commit -am "docs: trace the intelligence and learn chains from the inventories"`

### Task 6: Chain rows from inventories, areas 13 to 16 (Journal, Admin, Settings, Help)

- [ ] **Steps 1 to 8 as Task 3.** Settings rows record the code as it is today: `GET/PUT /api/me/preferences` and `GET/PUT /api/me/profile` through `src/hooks/usePreferences.ts` and `src/hooks/useProfile.ts`, and the Gaps list records that UI-SCREENS.md still says the screen is localStorage-only (spec §14).
- [ ] **Step 9: Run R3, R4, R5, R6, R7.** Expected: R3 `222 0 0 0 0`; the rest as before.
- [ ] **Step 10: Commit.** `git commit -am "docs: trace the support group chains from the inventories"`

### Task 7: Register, index and gate the matrix

**Files:**
- Modify: `docs/DOC_REGISTRY.md` (after the row for `docs/product/02-FEATURE-CATALOG.md`, line 202)
- Modify: `docs/product/README.md` (navigation table after line 16; Snapshot table after line 172)
- Modify: `.github/pull_request_template.md` (a new checklist line in the Summary section)

- [ ] **Step 1: Run R7.** Expected: a `registry` or unclassified finding for the new document, or `[]` if the audit does not flag unregistered paths. Record which.

- [ ] **Step 2: Registry row.** Insert `| D | docs/product/03-SITE-TRACEABILITY.md | platform/api, gcp/deploy.sh, gcp/schema.sql, lib |  |`.

- [ ] **Step 3: README rows.** Navigation: `| [03 Site Traceability](03-SITE-TRACEABILITY.md) | Which elements of each screen are specified, traced, validated and tested, and what runs each one? |`. Snapshot: `| Site elements traced | 0 of 222 ([03](03-SITE-TRACEABILITY.md)) |`.

- [ ] **Step 4: PR template line.** Under `## Summary`, after the existing comment, add `- Matrix rows touched and gates changed: <!-- IDs from docs/product/03-SITE-TRACEABILITY.md, or "none" -->`.

- [ ] **Step 5: Run R7 for `docs/product/03-SITE-TRACEABILITY.md`, `docs/product/README.md` and `docs/DOC_REGISTRY.md`.** Expected: `[]` for each.

- [ ] **Step 6: Commit and push.**
```bash
git add docs/DOC_REGISTRY.md docs/product/README.md .github/pull_request_template.md
git commit -m "docs: register and index the site traceability matrix"
git push -u origin claude/inspiring-cori-k9lz5g
```

## Phase 0, solyra

### Task 8: SCREEN-AUTH and SCREEN-SHELL records, registry row, PR template line

**Files:**
- Modify: `docs/UI-SCREENS.md` (two records inserted after `SCREEN-NAVIGATE`, before `SCREEN-DASHBOARD`; one paragraph in `### Cross-cutting specs`)
- Modify: `docs/DOC_REGISTRY.md:113`
- Modify: `.github/pull_request_template.md`

**Interfaces:**
- Produces: headings `### SCREEN-AUTH` and `### SCREEN-SHELL` in the same heading form as the existing records (ID, a spaced dash, then the route text), anchors `#screen-auth-...` and `#screen-shell-...` that the matrix links to.

- [ ] **Step 1: Save anchors (R9, before).** Then run R7 (solyra) for `docs/UI-SCREENS.md` and record the baseline finding list.

- [ ] **Step 2: Write the two records** with every field the existing records carry: Purpose; Status `Infrastructure`; Blocking issue; Owner `TBD`; Target phase; Last reviewed `2026-09-28`; Component (`src/components/auth/AuthGate.tsx`, `ConfigGate.tsx`, `SignInScreen.tsx`, `SignOutButton.tsx` and `src/routes/AuthActionPage.tsx` for AUTH; `src/components/layout/AppShell.tsx` for SHELL); Child components (AUTH: `LoadingSpinner`, `SignInScreen`; SHELL: `Sidebar`, `TopTabs`, `Header`, `CommandPalette`, `MostActiveBar`, `AuthStatusBanner`, `EmailVerificationBanner`, `MockModeBanner`, `Outlet`); API calls (AUTH: `/api/config/firebase`, `/api/me`; SHELL: `/api/market/most-active`, `/api/live/status`, `/api/me/preferences`, `/api/config/market-hours`); Stores (SHELL: `useSettingsStore`); States present (AUTH: load, err; SHELL: none in the shell itself); E2E specs (AUTH: `tests/shared/auth-gate.spec.ts`, `tests/admin/admin-auth.spec.ts`; SHELL: `tests/shared/navigation.spec.ts`, `tests/shared/most-active-bar.spec.ts`, `tests/shared/mock-mode.spec.ts`); PR lineage `UNKNOWN / NEEDS HISTORY TRACE`; Target REQ-UX-001.

- [ ] **Step 3: Cross-cutting paragraph.** After the existing paragraph in `### Cross-cutting specs`, add one sentence pointing at the matrix's SHARED area (GitHub URL to `stocks/docs/product/03-SITE-TRACEABILITY.md#00--shared-under-every-page`) and a `#### Elements` heading with nothing under it yet.

- [ ] **Step 4: Registry and template.** Change line 113 to `| D | docs/UI-SCREENS.md | src/routes, src/components, src/hooks, src/lib/authedFetch.ts, src/App.tsx, tests | |`. In the PR template, under `## Summary`, add `- Matrix rows touched and gates changed: <!-- IDs from stocks docs/product/03-SITE-TRACEABILITY.md, or "none" -->`.

- [ ] **Step 5: Run R9 (after) and R7.** Expected: R9 prints nothing; R7 shows no new P1 or P2 against the baseline.

- [ ] **Step 6: Commit.**
```bash
git add docs/UI-SCREENS.md docs/DOC_REGISTRY.md .github/pull_request_template.md
git commit -m "docs(screens): add AuthGate and AppShell records and register the matrix join"
```

### Task 9: Per-screen subsections with IDs, records Landing through Signals

**Files:**
- Modify: `docs/UI-SCREENS.md` (records SCREEN-LANDING, SCREEN-AUTH, SCREEN-SHELL, SCREEN-DASHBOARD, SCREEN-LIVEMARKET, SCREEN-CHARTS, SCREEN-OPTIONSFLOW, SCREEN-SIGNALS)

**Interfaces:**
- Consumes: Appendix A IDs.
- Produces: under each record the subsections of spec §7 in order, and one `##### AREA-NN · Element` heading per Appendix A row of that area, body empty except what Step 3 fills.

- [ ] **Step 1: Save anchors (R9, before). Run R8.** Expected: R8 prints every ID (no headings yet).

- [ ] **Step 2: Add the subsections** to each record, after its existing bullet list: `#### Data it needs` (table: Endpoint, Fields read, Produced by, Freshness assumed, Consumer), `#### Displayed` (ID, Element, Component), `#### Actions` (ID, Action, What happens), `#### States` (ID, State, Present in source, Presentation), `#### Journeys` (numbered list), `#### Elements` (the `#####` headings).

- [ ] **Step 3: Fill what the code answers now.** Displayed and Actions rows: label from Appendix A, component from the page's imports. States: `Present in source` from the record's existing "States present" line, which this table replaces. Data it needs: one row per API call the record lists, `Consumer` as the hook or component that issues it, `Produced by` left blank unless the matrix Chain row from Tasks 3 to 6 names the job (copy it). Journeys: the seed's journeys for that page, each step followed by the IDs it touches in parentheses. Element bodies stay empty in Phase 0; the S gate is earned by writing them in Phases 1 to 6.

- [ ] **Step 4: Run R9 (after), R8, R7.** Expected: R9 nothing; R8 prints only IDs of areas 09 to 16 and SHARED; R7 no new P1 or P2.

- [ ] **Step 5: Commit.** `git commit -am "docs(screens): add element, state and journey subsections for the market screens"`

### Task 10: Per-screen subsections with IDs, records Insights through Help, and SHARED

**Files:**
- Modify: `docs/UI-SCREENS.md` (records SCREEN-INSIGHTS, SCREEN-CATALYSTS, SCREEN-PLAYBOOK, SCREEN-REPORTS, SCREEN-JOURNAL, SCREEN-ADMIN, SCREEN-SETTINGS, SCREEN-HELP; the `#### Elements` under Cross-cutting specs for SHARED)

- [ ] **Steps 1 to 3 as Task 9** for these records. SHARED gets only the `#####` headings under Cross-cutting specs. Settings' Data table lists `/api/me/preferences` and `/api/me/profile` from the hooks, and its Gaps line in the matrix already records the inventory's stale claim.
- [ ] **Step 4: Run R9, R8, R7.** Expected: all print nothing or `[]`.
- [ ] **Step 5: Commit and push.**
```bash
git commit -am "docs(screens): add element, state and journey subsections for the remaining screens"
git push -u origin claude/inspiring-cori-k9lz5g
```

## Phase 1, the entry path

Each task below works one area through S, T, V, Te (spec §9 "Working a row") in both repos. Ticks and Evidence entries land in the stocks matrix; specs land in solyra. Order inside a task: solyra commit (S entries and any tests), then stocks commit (Chain completion, ticks, Progress).

### Task 11: SHARED, area 00

**Files:**
- Modify: `../solyra/docs/UI-SCREENS.md` (the eight `##### SHARED-NN` bodies)
- Modify: `docs/product/03-SITE-TRACEABILITY.md` (SHARED Chain, Checklist ticks, Evidence, Backend notes, Progress)

- [ ] **Step 1: Run R10.** Expected: prints nothing (no ticks yet).

- [ ] **Step 2: S.** Write each SHARED element body: shows or does, needs, states, acceptance criteria as Given/When/Then, tests, code. Facts to encode: `platform/api/auth.py:41-70` (modes `open`, `firebase`, `iap`; `_OPEN_API_PREFIXES` is `/api/health`, `/api/config/firebase`, `/api/waitlist`); `src/lib/authedFetch.ts:45` (`OPEN_PREFIXES` adds `/api/me`, so the two lists differ by design: `/api/me` is open on the API side by exact match, see `test_firebase_open_me_is_exact_match_and_subpaths_are_gated`); `src/lib/authedFetch.ts:156-158` (a 401 on a gated path calls `markAuthBlocked`); `src/lib/apiTargets.ts` and `vite.config.ts` (proxy target, staging fallback); `src/lib/mockMode.ts`; React Query defaults in `src/App.tsx`; the failure lane from `gcp/failure_notifier.py` and `docs/product/05-INFRASTRUCTURE.md` deployment diagram; `platform/api/routers/health.py:158` and `gcp/deploy.sh` `deploy_freshness_watchdog`. Tick S with `S <date> [spec](<GitHub URL to the heading>)`.

- [ ] **Step 3: T.** Complete the eight Chain rows; run R6 and click every link. Tick T with `T <date> <commit>`.

- [ ] **Step 4: V.** Run and record: `curl -sS $STAGING/api/health` (200), `curl -sS $STAGING/api/health/freshness | head -c 800` (200, a report per table), `curl -sS $STAGING/api/config/firebase` (200, `authMode: firebase`), `curl -sS -o /dev/null -w '%{http_code}' $STAGING/api/market/most-active` (401). For the failure lane: `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud logging sinks list --project=adept-mountain-474619-d4 --format='value(name,destination)'` shows a sink whose destination is the `gcp-job-failures` Pub/Sub topic (record its name; the design seed calls it `gcp-job-failures-sink`, unverified), and `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud run services describe failure-notifier --region=us-east1 --format='value(status.url)'`. Paste each command and output into a PR or issue comment; tick V with the link.

- [ ] **Step 5: Te.** Cite `tests/api/test_platform_auth.py` (`test_open_mode_is_noop`, `test_firebase_requires_valid_token`, `test_firebase_open_me_is_exact_match_and_subpaths_are_gated`), `tests/api/test_platform_api.py` (`test_health_returns_ok`), solyra `src/lib/authedFetch.test.ts` (`a 401 from an OPEN path does not fire onUnauthorized`, `attaches the bearer token to gated paths`), `src/lib/mockMode.test.ts`, `tests/shared/mock-mode.spec.ts`. Run `python -m pytest tests/api/test_platform_auth.py tests/api/test_platform_api.py -q` here and `npm test -- src/lib/authedFetch.test.ts src/lib/mockMode.test.ts` there; expected: all pass. Tick Te only for rows whose covering suite runs in CI (pytest and Vitest do; Playwright does not until Task 15), with `Te <date> [run](<CI run URL>)`.

- [ ] **Step 6: Run R3, R4, R7, R8, R10; update Progress.** Expected: all clean; R3 shows the SHARED counts.

- [ ] **Step 7: Commit both repos.** solyra: `git commit -am "docs(screens): specify the shared elements under every page"`. stocks: `git commit -am "docs: trace, validate and test the shared area of the matrix"`.

### Task 12: Landing, area 01

**Files:**
- Modify: `../solyra/docs/UI-SCREENS.md` (`##### LANDING-01` to `LANDING-13` bodies)
- Modify: `docs/product/03-SITE-TRACEABILITY.md` (area 01)

- [ ] **Step 1: S.** Facts: components under `src/components/landing/` (`LandingNav`, `Hero` with `useTypingLines`, `BentoGrid`, `ChartShowcase`, `ModuleDives`, `DailyRhythm`, `WaitlistSection`, `LandingFAQ`); `waitlist.ts` posts `email`, `source` and a honeypot to `POST /api/waitlist` and throws the server detail on non-2xx; `/welcome` redirects to `/`; Support menu FAQ links to `/#faq`. State rows: LANDING-12 (submit in flight) has no presentation in the source today and LANDING-13 (waitlist error) renders inline; write the criteria and mark the gap. Tick S.

- [ ] **Step 2: T.** `POST /api/waitlist` to `[waitlist.py:84](../../platform/api/routers/waitlist.py#L84)`, table `waitlist_signups` (user write), External `Lovable` for the host, tests `tests/api/test_waitlist_router.py`. Tick T.

- [ ] **Step 3: V.** `curl -sS -o /dev/null -w '%{http_code}' https://solyra-stocks.lovable.app/` (200); `curl -sS -X POST $STAGING/api/waitlist -H 'Content-Type: application/json' -d '{"email":"not-an-email","source":"matrix-v"}' -w '\n%{http_code}'` (400 with a detail, no row written per `test_invalid_email_is_400_and_no_db_call`); `./scripts/db_query_cr.sh -q "SELECT count(*) FROM waitlist_signups"` (a count). Tick V for LANDING-07 and LANDING-10; the static sections are validated by the 200 on the host.

- [ ] **Step 4: Te.** `tests/landing/landing.spec.ts` (`renders all key sections at /` covers LANDING-01 to 08, `waitlist form rejects an invalid email with a visible error` covers LANDING-13, `landing renders at / even in firebase auth mode (signed out)`); `src/components/landing/waitlist.test.ts`; `tests/api/test_waitlist_router.py`. Run `npm test -- src/components/landing/waitlist.test.ts` and `python -m pytest tests/api/test_waitlist_router.py -q`. Tick Te for rows covered by Vitest or pytest; Playwright-only rows wait for Task 15. LANDING-12 gets no Te and a Gaps line.

- [ ] **Step 5: Run R3, R4, R7, R8, R10; update Progress. Commit both repos.** solyra: `docs(screens): specify the landing page elements`; stocks: `docs: trace, validate and test the landing area of the matrix`.

### Task 13: AuthGate, area 02

**Files:**
- Modify: `../solyra/docs/UI-SCREENS.md` (`##### AUTH-01` to `AUTH-10`)
- Modify: `../solyra/tests/shared/auth-gate.spec.ts` (three new tests)
- Modify: `docs/product/03-SITE-TRACEABILITY.md` (area 02)

- [ ] **Step 1: S.** Facts: `ConfigGate.tsx:42` accepts only `open`, `firebase`, `iap` and shows a config-error screen otherwise; `AuthGate.tsx:17-27` (non-firebase modes render children; loading spinner while `isLoading`; `SignInScreen` when signed out); `SignInScreen.tsx` test ids `signin-screen`, `google-signin`, `google-signin-newtab` (framed, `target="_blank"`, line 182-191), `login-email`, `login-password`, `login-submit`, `login-toggle`, `login-error`, `login-forgot`, `reset-email`, `reset-submit`, `reset-sent`, `reset-back`; modes `signin`, `signup`, `reset`; `src/routes/AuthActionPage.tsx` handles the emailed action link; `platform/api/main.py:282` returns `email`, `is_admin`, `is_dev` with the role from `user_roles` via `stored_role_for` (`api/auth.py:250`); `SignOutButton.tsx`. Write criteria per row; tick S.

- [ ] **Step 2: T.** Chain rows as spec Appendix B, links resolved, `gcp/auth_email_templates.py` and `docs/AUTH_EMAILS.md` for AUTH-06. Tick T.

- [ ] **Step 3: V.** With the staging and token recipe: `/api/config/firebase` (200), `/api/me` without a token (200, anonymous body), `/api/me` with the token (200, the test account's email and flags), `/api/market/most-active` without a token (401) and with it (200). Google sign-in, sign-up and password reset need a browser: ask the user to run them once on `https://solyra-stocks.lovable.app/` and paste the outcome into the PR (which button, what happened, the `reset-sent` confirmation); until that arrives AUTH-03, AUTH-05 and AUTH-06 keep V unticked. Tick V for AUTH-01, 04 (token minted by password proves the credential path), 07, 08 with the comment link.

- [ ] **Step 4: Te, write the failing tests first.** In `tests/shared/auth-gate.spec.ts`, following the file's existing mocking pattern for `/api/config/firebase` and the identitytoolkit routes used by the Forgot password tests:
```ts
test('framed preview: the Google button opens a new tab instead of a popup', ...)
// mount /dashboard inside an iframe from page.setContent, expect frame.getByTestId('google-signin-newtab') visible with target="_blank" and getByTestId('google-signin') absent
test('email sign-in shows the inline error when the identity call fails', ...)
// route the signInWithPassword call to a 400 INVALID_PASSWORD body, submit login-email + login-password, expect getByTestId('login-error') to contain text
test('sign out returns to the sign-in screen', ...)
// signed-in state via the existing helper, click the sign-out control, expect getByTestId('signin-screen') visible
```
  Run `npm run e2e -- tests/shared/auth-gate.spec.ts`; expected: the three new tests fail (no such behaviour mocked yet or selectors missing), the existing ones pass. Then make them pass by fixing the tests' routing and selectors, never the product code. Run again; expected: all pass.

- [ ] **Step 5: Te ticks.** Map rows to tests: AUTH-01 `open mode → app renders`, `firebase mode, signed out → login screen blocks the app`, `config fetch failure → config-error screen` (AUTH-10), `login screen toggles between sign-in and sign-up` (AUTH-05), Forgot password tests (AUTH-06), `/auth/action` tests (AUTH-06), the three new tests (AUTH-03, 04, 09), `tests/api/test_platform_auth.py` (AUTH-07, 08), `src/lib/authedFetch.test.ts` (AUTH-08). Tick Te only where a CI suite covers the row (pytest, Vitest); Playwright-covered rows wait for Task 15.

- [ ] **Step 6: Run R3, R4, R7, R8, R10; update Progress. Commit both repos.** solyra: `test(auth): cover framed Google sign-in, email sign-in errors and sign-out` then `docs(screens): specify the AuthGate elements`; stocks: `docs: trace, validate and test the AuthGate area of the matrix`.

### Task 14: AppShell, area 03

**Files:**
- Modify: `../solyra/docs/UI-SCREENS.md` (`##### SHELL-01` to `SHELL-16`)
- Modify: `../solyra/tests/shared/navigation.spec.ts` (two new tests)
- Modify: `docs/product/03-SITE-TRACEABILITY.md` (area 03)

- [ ] **Step 1: S.** Facts: `AppShell.tsx:61-77` (Sidebar or TopTabs by `useSettingsStore`, Header only in sidebar mode, `MockModeBanner`, `AuthStatusBanner`, `MostActiveBar` only where `showMostActiveBar(pathname)`, `Outlet`, `CommandPalette`); `navConfig.ts` groups and `adminOnly`; `MarketSessionBadge.tsx` and `useLiveStatus` (`/api/live/status`); `ReplayControl.tsx` (`/api/config/market-hours`); `usePreferencesSync` (`/api/me/preferences`, written through); `MostActiveBar.tsx` renders nothing on an empty list and is absent on a 500 (the spec's own tests); `RouteErrorBoundary.tsx`. Tick S.

- [ ] **Step 2: T.** `/api/market/most-active` to `[main.py:1510](../../platform/api/main.py#L1510)`, tables `market_data_intraday`, `top_movers_intraday` ← `fetch-top-movers` (`top-movers-intraday-hourly` 09:30 to 15:30 weekdays, `top-movers-intraday-close` 16:05, `top-movers-daily` 16:15); `/api/live/status` to `[live.py:174](../../platform/api/routers/live.py#L174)`; `/api/config/market-hours` to `[config.py:131](../../platform/api/routers/config.py#L131)`; `/api/me/preferences` to `[preferences.py:132](../../platform/api/routers/preferences.py#L132)` and `#L149`, table `user_preferences`. Tick T.

- [ ] **Step 3: V.** With the token: `/api/market/most-active` (200, items with ranks), `/api/live/status` (200), `/api/config/market-hours` (200), `/api/me/preferences` (200 or 404 when nothing is stored, both honest). `./scripts/db_query_cr.sh -q "SELECT max(<timestamp column named in gcp/schema.sql for top_movers_intraday>) FROM top_movers_intraday"` shows a recent snapshot. Tick V.

- [ ] **Step 4: Te, failing tests first.** In `tests/shared/navigation.spec.ts`:
```ts
test('command palette opens with the keyboard shortcut and navigates to a page', ...)
// press Control+K (and Meta+K on mac), type "Journal", press Enter, expect URL /journal
test('theme toggle flips the document theme attribute', ...)
// sidebar nav pattern seeded, click the toggle in the Header, expect html[data-theme] to change
```
  Run `npm run e2e -- tests/shared/navigation.spec.ts`; expected: two failures, then pass after fixing the tests' selectors against the components. Existing coverage: `most-active-bar.spec.ts` (SHELL-05, 13, 14), `navigation.spec.ts` (SHELL-01, 07 `market session badge is truthful`), `mock-mode.spec.ts` (SHELL-03), `src/hooks/usePreferences.test.ts`, stocks `tests/api/test_most_active_endpoint.py`, `test_preferences_router.py`, `test_platform_api.py::test_live_status`.

- [ ] **Step 5: Run R3, R4, R7, R8, R10; update Progress. Commit both repos.** solyra: `test(shell): cover the command palette and theme toggle` then `docs(screens): specify the AppShell elements`; stocks: `docs: trace, validate and test the AppShell area of the matrix`.

### Task 15: Playwright in solyra CI (solyra#28), so Te can be earned for browser rows

**Files:**
- Modify: `../solyra/.github/workflows/ci.yml`

- [ ] **Step 1: Baseline.** In solyra run `npm run e2e` once and keep the summary line (passed, failed, flaky). Expected today: unknown; record it.

- [ ] **Step 2: Add a job** `e2e` to `ci.yml` after the existing job: checkout, Node setup identical to the existing job, `npm ci`, `npx playwright install --with-deps chromium`, `npm run e2e`, and `actions/upload-artifact` of `playwright-report/` on failure. Do not add `continue-on-error`.

- [ ] **Step 3: Push and read the run.** If the job is red because of failures already present in Step 1, file one solyra issue per failing spec naming the matrix row IDs it covers, link them from the matrix Gaps, and tell the user the job exists but should not be a required check until those close. If green, tell the user it can be made required (a repository setting they own).

- [ ] **Step 4: Te ticks.** Once the job is green on the current head, tick Te for the Playwright-covered rows of Tasks 12 to 14 with `Te <date> [run](<run URL>)`, re-run R10, update Progress, commit in stocks: `docs: earn the Te gate for browser-covered entry-path rows`.

- [ ] **Step 5: Commit and push solyra.** `git commit -am "ci: run the hermetic Playwright suite on pull requests"` and `git push -u origin claude/inspiring-cori-k9lz5g`.

### Task 16: Close out Phase 1

- [ ] **Step 1: Run every recipe R1 to R10 in both repos**, plus `npm test` and `npm run contract:check` in solyra and `python -m pytest tests/api -q` in stocks (spec §12 item 5), and paste the outputs into the stocks PR description or the branch's final commit body.
- [ ] **Step 2: Update the README snapshot metric** to the R3 totals (`<traced> of 222`, where traced counts rows with T ticked) and commit: `docs: update the site traceability snapshot after phase 1`.
- [ ] **Step 3: Push both repos** and report to the user: the two branches, the recipe outputs, the rows still blocked on a manual browser check (AUTH-03, 05, 06) and on Task 15's job. Remind the user that the two Claude Design documents can now be regenerated from the docs (spec §10).

---

## Appendix A. The rows, by area and ID

Displayed elements first, then actions, then states. Labels are the Element cell text. 222 rows. DASHBOARD-21 was appended after Task 3 found the Movement Read card wired to `/api/movement-statement` with no row (ledger ruling); IDs never renumber, so it takes the next number.

**00 SHARED (8)**
SHARED-01 API service and auth middleware (solyra-api-staging, solyra-api-prod, AUTH_MODE) · SHARED-02 Open prefixes kept in sync (api/auth.py and authedFetch OPEN_PREFIXES) · SHARED-03 Data path: authedFetch, apiTargets, Vite proxy, staging fallback · SHARED-04 Mock mode and demo-data banners · SHARED-05 React Query defaults (five-minute staleness, one retry) · SHARED-06 Failure lane: job log, Cloud Logging sink, Pub/Sub, failure-notifier, GitHub issue · SHARED-07 Freshness watchdog and /api/health/freshness · SHARED-08 Liveness: /api/health

**01 LANDING (13)**
LANDING-01 LandingNav · LANDING-02 Hero with the agent terminal · LANDING-03 BentoGrid · LANDING-04 ChartShowcase · LANDING-05 ModuleDives · LANDING-06 DailyRhythm · LANDING-07 WaitlistSection · LANDING-08 FAQ (#faq) · LANDING-09 Sign in (to /dashboard) · LANDING-10 Request access, join the waitlist · LANDING-11 See a live day (scroll to #learn) · LANDING-12 State: loading (waitlist submit in flight) · LANDING-13 State: error (waitlist failure shown inline)

**02 AUTH (10)**
AUTH-01 Auth-mode bootstrap (firebase, iap, open) · AUTH-02 State: loading spinner while the session resolves · AUTH-03 Google sign-in, with the new-tab variant when framed · AUTH-04 Email and password sign-in with inline error · AUTH-05 Sign-up mode · AUTH-06 Forgot password: reset email, then /auth/action · AUTH-07 Identity and role read (email, admin, dev) · AUTH-08 State: permission, 401 on a gated call shows "Sign in to load data" · AUTH-09 Sign out · AUTH-10 State: error, config fetch failure shows the config-error screen

**03 SHELL (16)**
SHELL-01 Sidebar or TopTabs navigation · SHELL-02 Header in sidebar mode (auth status, sign out, replay control, theme toggle) · SHELL-03 MockModeBanner · SHELL-04 AuthStatusBanner and EmailVerificationBanner · SHELL-05 MostActiveBar marquee · SHELL-06 RouteErrorBoundary · SHELL-07 Market session badge (LIVE, PRE, AH, CLOSED) · SHELL-08 Command palette (Cmd-K, Ctrl-K) · SHELL-09 Replay control (historical review) · SHELL-10 Theme toggle · SHELL-11 Sign out · SHELL-12 State: loading (marquee before the first response) · SHELL-13 State: empty (marquee renders nothing on an empty list) · SHELL-14 State: error (marquee absent on 500, page renders) · SHELL-15 State: stale (session badge truthful when closed) · SHELL-16 State: permission (auth status banner when signed out or blocked)

**04 DASHBOARD (21)**
DASHBOARD-01 Briefing strip · DASHBOARD-02 Top setup · DASHBOARD-03 Daily KPIs · DASHBOARD-04 Intraday chart · DASHBOARD-05 Live signals table · DASHBOARD-06 Catalysts list · DASHBOARD-07 Sector rotation · DASHBOARD-08 AI take · DASHBOARD-09 News · DASHBOARD-10 Switch ticker · DASHBOARD-11 Refresh · DASHBOARD-12 Candles or Area toggle · DASHBOARD-13 1D or 5D sector period · DASHBOARD-14 Click a card (signals, catalysts, news, AI take) · DASHBOARD-15 Review mode · DASHBOARD-16 State: loading · DASHBOARD-17 State: empty · DASHBOARD-18 State: error · DASHBOARD-19 State: stale · DASHBOARD-20 State: permission · DASHBOARD-21 Movement Read card (feature-flagged)

**05 LIVE (13)**
LIVE-01 Session bar · LIVE-02 Quote card · LIVE-03 Six indicator tiles · LIVE-04 CALL and PUT setup cards · LIVE-05 Live (15s) or Paused toggle · LIVE-06 Sound alert · LIVE-07 Switch ticker · LIVE-08 Review mode · LIVE-09 State: loading · LIVE-10 State: empty · LIVE-11 State: error · LIVE-12 State: stale · LIVE-13 State: permission

**06 CHARTS (17)**
CHARTS-01 Toolbar · CHARTS-02 Candlestick chart · CHARTS-03 Crosshair bar · CHARTS-04 Replay session controls · CHARTS-05 Strategy conditions card · CHARTS-06 Similar setups card · CHARTS-07 Backtester · CHARTS-08 Post-session scorecard · CHARTS-09 Change date or timeframe · CHARTS-10 Toggle overlays · CHARTS-11 Run a replay session · CHARTS-12 Backtest my trades · CHARTS-13 State: loading · CHARTS-14 State: empty · CHARTS-15 State: error · CHARTS-16 State: stale · CHARTS-17 State: permission

**07 OPTIONS (13)**
OPTIONS-01 Heatseeker: Swing Mode · OPTIONS-02 Heatseeker: Trinity Mode · OPTIONS-03 Flowseeker: Live Feed · OPTIONS-04 Flowseeker: Contract Drilldown · OPTIONS-05 Profiles · OPTIONS-06 Symbol picker · OPTIONS-07 View switcher · OPTIONS-08 Pick an expiration date · OPTIONS-09 State: loading · OPTIONS-10 State: empty · OPTIONS-11 State: error · OPTIONS-12 State: stale · OPTIONS-13 State: permission

**08 SIGNALS (12)**
SIGNALS-01 Header · SIGNALS-02 Performance KPIs · SIGNALS-03 Filter bar · SIGNALS-04 Signals table · SIGNALS-05 Filter and sort · SIGNALS-06 Clear filters · SIGNALS-07 Review mode · SIGNALS-08 State: loading · SIGNALS-09 State: empty · SIGNALS-10 State: error · SIGNALS-11 State: stale · SIGNALS-12 State: permission

**09 INSIGHTS (15)**
INSIGHTS-01 Report cards · INSIGHTS-02 Agents tab · INSIGHTS-03 History tab · INSIGHTS-04 Watchlist tab · INSIGHTS-05 Chat tab · INSIGHTS-06 Degradation banner · INSIGHTS-07 Generate or refresh a report · INSIGHTS-08 Set a point-in-time cutoff · INSIGHTS-09 Add or remove watchlist tickers · INSIGHTS-10 Chat · INSIGHTS-11 State: loading · INSIGHTS-12 State: empty · INSIGHTS-13 State: error · INSIGHTS-14 State: stale · INSIGHTS-15 State: permission

**10 CATALYSTS (14)**
CATALYSTS-01 Hot Now · CATALYSTS-02 Impact tier filter · CATALYSTS-03 Type chips · CATALYSTS-04 Event timeline · CATALYSTS-05 WSH upgrade banner · CATALYSTS-06 Change date range · CATALYSTS-07 Filter by impact or type · CATALYSTS-08 Expand an event · CATALYSTS-09 Open insight report · CATALYSTS-10 State: loading · CATALYSTS-11 State: empty · CATALYSTS-12 State: error · CATALYSTS-13 State: stale · CATALYSTS-14 State: permission

**11 PLAYBOOK (10)**
PLAYBOOK-01 Header · PLAYBOOK-02 Setup cards · PLAYBOOK-03 Trade levels · PLAYBOOK-04 Switch ticker · PLAYBOOK-05 Watch conditions fill · PLAYBOOK-06 State: loading · PLAYBOOK-07 State: empty · PLAYBOOK-08 State: error · PLAYBOOK-09 State: stale · PLAYBOOK-10 State: permission

**12 REPORTS (10)**
REPORTS-01 Picker bar · REPORTS-02 Report header · REPORTS-03 Report body · REPORTS-04 Select a report · REPORTS-05 Previous or Next · REPORTS-06 State: loading · REPORTS-07 State: empty · REPORTS-08 State: error · REPORTS-09 State: stale · REPORTS-10 State: permission

**13 JOURNAL (16)**
JOURNAL-01 Header row · JOURNAL-02 Cockpit row · JOURNAL-03 KPI tiles · JOURNAL-04 My style panel · JOURNAL-05 Add-trade form · JOURNAL-06 Trade table · JOURNAL-07 Mark entry on the chart · JOURNAL-08 Add trade manually · JOURNAL-09 Import CSV · JOURNAL-10 Export CSV · JOURNAL-11 Switch view or session · JOURNAL-12 State: loading · JOURNAL-13 State: empty · JOURNAL-14 State: error · JOURNAL-15 State: stale · JOURNAL-16 State: permission

**14 ADMIN (13)**
ADMIN-01 Users and roles tab · ADMIN-02 Chart and report data tab · ADMIN-03 Models and routing tab · ADMIN-04 Grant or revoke roles · ADMIN-05 Disable a user · ADMIN-06 Refresh a data source · ADMIN-07 Change provider or model per role and save · ADMIN-08 Run a predict · ADMIN-09 State: loading · ADMIN-10 State: empty · ADMIN-11 State: error · ADMIN-12 State: stale · ADMIN-13 State: permission

**15 SETTINGS (13)**
SETTINGS-01 Profile tab · SETTINGS-02 Appearance tab · SETTINGS-03 Trading tab · SETTINGS-04 Notifications tab · SETTINGS-05 Account tab · SETTINGS-06 Toggle appearance · SETTINGS-07 Save changes or Discard · SETTINGS-08 Sign out · SETTINGS-09 State: loading · SETTINGS-10 State: empty · SETTINGS-11 State: error · SETTINGS-12 State: stale · SETTINGS-13 State: permission

**16 HELP (8)**
HELP-01 Search box · HELP-02 Category pills · HELP-03 Glossary entries · HELP-04 State: empty (no entry matches) · HELP-05 Search · HELP-06 Filter by category · HELP-07 Expand an entry · HELP-08 TermHover links from other pages
