# Most-Active Ticker Bar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An auto-scrolling most-active ticker bar (ticker · price · change % · volume · intraday sparkline) under the top nav on every Market-section page and the Journal, fed by hourly AlphaVantage TOP_GAINERS_LOSERS snapshots.

**Architecture:** Extend the existing `fetch-top-movers` Cloud Run job with an hourly intraday-snapshot mode writing to a new `top_movers_intraday` table (the existing 16:15 daily job/table stay untouched — the ranker consumes them). One new read endpoint serves the latest snapshot list plus each ticker's snapshot-series for sparklines. A shared `<MostActiveBar/>` renders the marquee; sparklines draw only from ≥2 real snapshot points (Rule 3.7 — never synthesized).

**Tech Stack:** Python/FastAPI + pandas (`gcp/fetchers/fetch_top_movers.py`, `gcp/schema.sql`, `gcp/deploy.sh`, new router or `platform/api/main.py` market surface), React/TS + canvas sparkline, pytest, Playwright.

**User decisions (2026-07-12):** marquee (pause on hover/touch; static fallback under `prefers-reduced-motion`); most-active list only; hourly API refresh accruing sparkline data. Design approved via the mockup artifact ("Most-active ticker bar" section).

## Global Constraints

- Branch `feature/most-active-ticker-bar` off current main. Conventional commits, no AI branding/trailers, stage by explicit path, never stage `platform/playwright.config.ts`, `docs/alphavantage/`, `model_analysis.txt`.
- Existing daily fetch (`top_movers_daily`, 16:15 scheduler) byte-identical in behavior — the ranker reads it. The intraday mode is ADDITIVE.
- Rule 3.7: no fabricated points — a ticker with one snapshot gets no sparkline (chip renders without it); missing change/volume → "—". The bar labels its data honestly ("Most active · <date or 'live'>" from the snapshot timestamps).
- Rule 0 capacity (put in PR): 7 AV calls/day (hourly 09:30–16:00 ET Mon–Fri) + 1 existing daily; job wall-clock <30s, task-timeout 300s, max-retries 0; page cost = one indexed SELECT (+ TanStack staleTime 10 min).
- Naive-ET/UTC discipline: snapshot timestamps stored as TIMESTAMPTZ true-UTC (job runs on Cloud Run UTC clock via `datetime.now(timezone.utc)` — be explicit, don't repeat the naive-`now()` ambiguity documented in the trades forensics); API converts for display labels only.
- Playwright local recipe: vite 4321 + baseURL patch, REVERT + kill before commits; foreground runs.

---

### Task 1: Schema + hourly snapshot mode on the fetcher

**Files:** Modify `gcp/schema.sql` (append), `gcp/fetchers/fetch_top_movers.py`; Test `tests/gcp/test_fetch_top_movers_intraday.py` (hermetic — mock `requests` + upsert; follow the style of existing fetcher tests, find one via `ls tests/ | grep fetch`).

**Schema (append to gcp/schema.sql, after top_movers_daily):**
```sql
CREATE TABLE IF NOT EXISTS top_movers_intraday (
    id            BIGSERIAL PRIMARY KEY,
    snapshot_ts   TIMESTAMPTZ  NOT NULL,           -- true UTC, set once per job run
    snapshot_date DATE         NOT NULL,           -- ET trading date of the snapshot
    rank          SMALLINT     NOT NULL,           -- 1..20 position in the most-active list
    ticker        VARCHAR(10)  NOT NULL,
    price         DOUBLE PRECISION,
    change_amount DOUBLE PRECISION,
    change_pct    DOUBLE PRECISION,
    volume        BIGINT,
    inserted_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_top_movers_intraday UNIQUE (snapshot_ts, ticker)
);
CREATE INDEX IF NOT EXISTS idx_top_movers_intraday_date
    ON top_movers_intraday (snapshot_date DESC, snapshot_ts DESC);
```

**Fetcher:** add `--intraday-snapshot` flag: same AV call, take `most_actively_traded` only, parse `change_percentage` ("+2.31%" → 2.31 float, strip %/sign correctly for negatives), one `snapshot_ts = datetime.now(timezone.utc)` for the batch, `snapshot_date` = that instant converted to ET date, upsert via the existing `upsert_dataframe` with the unique key. Reuse the existing AV-key/env handling and error paths in the file — on AV failure raise (job fails loudly; max-retries 0; scheduler fires again next hour — an hourly gap is acceptable and visible).

- [ ] Failing tests: parse fixture JSON (real AV response shape incl. negative changes) → 20 rows, correct floats/volume ints; single snapshot_ts across batch; ET snapshot_date correct for a 20:30 UTC run (=16:30 ET same day) and a 13:30 UTC run; AV error → raises (no empty-success); `--dry-run` writes nothing.
- [ ] Implement → green: `python -m pytest tests/gcp/test_fetch_top_movers_intraday.py -q`.
- [ ] Commit: `feat(fetchers): hourly most-active snapshots to top_movers_intraday`

---

### Task 2: Read endpoint

**Files:** Modify the market/dashboard router that already serves public market reads (find where `/api/market/dates` lives — add alongside; likely `platform/api/main.py` or a router); Test `tests/api/test_most_active_endpoint.py` (TestClient scaffold from tests/api/test_journal_examples.py).

**Interfaces (Produces):** `GET /api/market/most-active` →
```json
{ "snapshot_ts": "2026-07-13T14:30:00+00:00", "snapshot_date": "2026-07-13", "label": "live",  // "live" if latest snapshot < 90min old during RTH, else the ET date
  "items": [ { "ticker": "NVDA", "rank": 1, "price": 182.40, "change_pct": 2.31, "volume": 312000000,
               "spark": [181.2, 181.9, 182.4] } ] }
```
- One SQL: pull ALL of the latest `snapshot_date`'s rows (indexed), group in memory: items = latest snapshot's 20 ordered by rank; `spark` = that ticker's price across the date's snapshots ordered by snapshot_ts (omit the key entirely when <2 points — Rule 3.7).
- Empty table → `{"items": [], "label": null, ...}` honest empty (frontend hides the bar), NOT an error — the bar is decorative; but DB-unavailable → 503 like siblings.
- Auth: match whatever gate `/api/market/dates` has (verify, don't assume).

- [ ] Failing tests: shape; spark ordering; <2 snapshots → no spark key; empty table → items []; ranks ordered; auth parity with market/dates.
- [ ] Implement → green + run the file alongside `tests/api/test_platform_api.py`.
- [ ] Commit: `feat(api): most-active endpoint with per-ticker snapshot sparklines`

---

### Task 3: MostActiveBar component + placement

**Files:** Create `platform/src/components/shared/MostActiveBar.tsx` (+ `MostActiveBar.test.ts` vitest for the pure helpers); Modify the layout/pages: mount under the top nav on Market-section routes AND `/journal` — find the Market section's shared layout (TopTabs / route layout) and mount ONCE there rather than per-page if a shared wrapper exists (read `platform/src/App.tsx` routing first; report the mount decision); Test `platform/tests/most-active-bar.spec.ts`.

Component: fetch via TanStack (`staleTime` 10 min, `refetchInterval` 15 min); render header cell ("MOST ACTIVE" + label), then items: ticker bold, price, change% (bull/bear color, "—" when null), compact volume ("312M vol" — pure helper `formatCompactVolume`, vitest: 312_000_000→"312M", 44_100_000→"44M", 981_000→"981K", null→"—"), sparkline `<canvas>` 56×18 drawn from `spark` (single stroke, bull/bear by first-vs-last; only when present). Marquee: duplicate the item strip, CSS `@keyframes` translateX loop, speed ~40s/loop, `:hover`/`:focus-within` pauses, `@media (prefers-reduced-motion: reduce)` → static overflow-x-auto. Empty items → component renders nothing (no skeleton flash — mount hidden until data).

- [ ] Failing e2e: bar renders on /journal and one Market page with mocked payload (items + one spark, one no-spark ticker); marquee element has the animation class and it's absent under reduced-motion emulation (`page.emulateMedia({ reducedMotion: 'reduce' })`); no horizontal page overflow at 390×844 (bar is its own overflow container); absent entirely when API returns empty items.
- [ ] Implement → green: new spec + journal-onestop + charts-cards (mount points touched) + `npx tsc -b --force` + `npx vitest run`.
- [ ] Commit: `feat(ui): most-active marquee bar on market pages and journal`

---

### Task 4: Rollout

- [ ] `gcp/deploy.sh`: add the hourly scheduler (cron `30 9-15 * * 1-5` ET timezone + one at 16:05 for the close snapshot — verify how existing schedulers pass `--schedule` + `--time-zone America/New_York`, copy the pattern; job args `--intraday-snapshot`; task-timeout 300, max-retries 0, memory per sibling jobs).
- [ ] Apply schema: run the `apply-schema-migrations` CR job (the repo's canonical path), verify table exists via db_query_cr read.
- [ ] Deploy the updated job image + scheduler; trigger one manual `--intraday-snapshot` run; verify rows landed (read-only query).
- [ ] Full gates + parity screenshot of the bar on Journal + a Market page → send to user; staging deploy; acceptance.

---

## Self-Review
- Coverage: hourly refresh (T1+T4), marquee + reduced-motion (T3), most-active only (T1/T2), sparkline from real accrued data only (T2/T3), placement Market+Journal (T3), honest empty/labels throughout. No gaps.
- No placeholders; exact DDL/shapes/test lists included; T2 defers ONLY discoverable facts (which router file, auth gate) with explicit verify instructions.
- Type consistency: `spark` optional array end-to-end; change_pct float percent (TRUE PERCENT convention).
- Risk: AV hourly quota — 8 calls/day well within any tier; scheduler ET timezone must be explicit or hours drift with DST (constraint noted in T4).
