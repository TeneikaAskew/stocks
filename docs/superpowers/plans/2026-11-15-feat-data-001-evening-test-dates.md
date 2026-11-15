---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-11-14-feat-data-001-deployed-dates-exchange-clock.md
branch: fix/feat-data-001-evening-test-dates
pr: null
status: ready
---

# Tests expect the exchange's date where the code reads it: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are numbered from 0 in the spec's order, [0] to [8].

**Goal:** `make test` and the integration suite pass at every hour, including 19:00 to midnight Eastern, on the code stage 1 (#1948) and the brief's date fix (#1941) put on `main`.

**Architecture:** The code under test now takes "today" from `lib.eastern_time.market_today()`. Four test files still build their expected dates from `date.today()`, the container's UTC date, which is the next day from 19:00 Eastern in winter (20:00 in summer) until midnight Eastern. Each changes to `market_today()`, as `tests/gcp/test_refresh_earnings_views_sources.py:27` and `tests/gcp/test_earnings_long_watchlist_sources.py:26` already do. No code under `gcp/`, `lib/`, `scripts/` or `platform/` changes.

**Tech Stack:** pytest, the local Postgres fixture of `tests/integration/test_catalyst_earnings_estimate_numbers_pg.py`.

**Spec:** `docs/superpowers/specs/2026-11-14-feat-data-001-deployed-dates-exchange-clock.md` (done_when [7]: `make test` passes on the PR head; the PR body lists every existing test whose expectation changed, with the reason).

## Global Constraints

- No code outside `tests/` changes; `tests/fixtures/timezone_boundary_baseline.json` and `tests/meta/test_timezone_boundaries.py` are unchanged (the ratchet does not scan `tests/`).
- No `# tz-ok:` line is added.
- Every changed expectation reads `lib.eastern_time.market_today()`, the helper the code under test reads; none hands the code a fixed date.

## Review Focus

- A test that builds its expected date at import time and the code that reads it at call time straddle midnight Eastern: the same window as the sibling files, which accept it.
- `tests/integration/test_watchlist_history.py` also calls `date.today()`, against `resolve_membership_at` and a Postgres trigger stamping `now()`; neither reads `market_today()`, so it stays (checked: it is not among the failures on `main` in the evening).
- The earnings router's own window (`platform/api/routers/earnings.py:129`, `CURRENT_DATE`) is still the database session's date; the seeded event dates (two days ahead) sit inside it in both readings.

---

### Task 1: expected dates from the exchange's clock

Spec: § Design 3 (frozen-clock tests; the code reads `market_today()`), § Done when. Advances done_when[7].

**Files:**
- Modify: `tests/gcp/test_refresh_earnings_views_retired_score.py:28` (`TODAY`, also imported by `tests/api/test_earnings_upcoming_retired_score.py`)
- Modify: `tests/gcp/test_canonical_provenance.py:37` (`_resolve_analysis_date`, which reads `market_today()` since #1941)
- Modify: `tests/integration/test_earnings_upcoming_retirement_snapshot_pg.py` (five `date.today()` reads: the seed default and the three tests' event and snapshot dates)

- [ ] Record the failure on `main` inside the evening window: the three hermetic files give 9 failed, 15 passed at 2026-11-15T00:46Z; the Postgres file fails `test_empty_retirement_refresh_cannot_resurrect_prior_ew_snapshot` with `[('TODAYEW', 90.0)] == [('EWO', 90.0), ('EWR', 90.0)]`
- [ ] Replace each expectation with `market_today()` from `lib.eastern_time`
- [ ] Run: `python3 -m pytest -q tests/gcp/test_canonical_provenance.py tests/gcp/test_refresh_earnings_views_retired_score.py tests/api/test_earnings_upcoming_retired_score.py` (expect 24 passed in the evening window)
- [ ] Run the Postgres file against a local cluster (`GITHUB_ACTIONS=true DB_HOST=localhost`, user `trading_user`) (expect 3 passed)
- [ ] Run the whole hermetic suite (`python3 -m pytest tests/ -q --ignore=tests/integration`) inside the evening window; no failure that `main` does not also have
- [ ] Commit: `test: expect the exchange's date where the code reads it`

### Task 2: close

Spec: § Done when. Closes done_when[8] for this change.

- [ ] Update the FEAT-DATA-001 record in `docs/product/02-FEATURE-CATALOG.md` (Status, Last reviewed)
- [ ] Add this PR to `docs/product/12-PR-ISSUE-TRACEABILITY.md`
- [ ] Extend the (FEAT-DATA-001, DASHBOARD-01) implementation-source note with the new source hash (`doc_source_snapshot.py produce` as preflight), commit, produce the sidecar, commit, `verify`
- [ ] Docs audit reports nothing new over origin/main (`python3 scripts/maintenance/docs_audit.py`)
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main`
