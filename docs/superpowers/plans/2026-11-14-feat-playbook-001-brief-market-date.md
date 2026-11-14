---
feat_id: FEAT-PLAYBOOK-001
spec: docs/superpowers/specs/2026-11-14-feat-playbook-001-brief-market-date.md
branch: fix/feat-playbook-001-brief-market-date
pr: 1941
status: ready
---

# The brief's live date is the exchange's date: implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

**Goal:** with `BRIEF_AS_OF` unset, `gcp/premarket_brief.py` dates a run by
`lib.eastern_time.market_today()` instead of the container's UTC date, so the Sunday 21:00
America/New_York run is dated Sunday and Monday's 08:30 run writes Monday's canonical row.

**Approach:** four lines in one file (the import, two reads in `_resolve_analysis_date`, one in
`persist_to_cloud_sql`), driven by frozen-clock tests that run `main([])` against in-memory tables.
Owner's decision (a): the Sunday run writes a Sunday-dated canonical row like any other run, so
`persist_to_cloud_sql` gains no session check.

## Global constraints (from the spec)

- Under `gcp/`, `lib/`, `platform/` and `scripts/` only `gcp/premarket_brief.py` changes. `gcp/deploy.sh`
  and `gcp/schema.sql` do not.
- No new dependency. A test fixes the clock with `_freeze_exchange_clock(monkeypatch, eastern)`, which
  replaces `lib.eastern_time.eastern_now`, the copy `lib.strat` imported, and `gcp.premarket_brief.date`
  (a subclass whose `today()` is the UTC date of the same instant, as in the container).
- No `# tz-ok:` comment is added. The two `tz_localize(None)` sites stay as they are.
- Every edit in `gcp/premarket_brief.py` keeps the file's line count and every later line number: the
  generated inventory blocks of `docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md` cite lines of
  this file, and `tests/scripts/test_check_generated_docs.py` fails when they move.
- No production command in any task. Deploy and the checks after it are the owner's (spec, Close-out).

## Review focus

Conditions the spec implies and where a test pins each:

1. The host date and the exchange date differ in both seasons (01:00 UTC under EDT, 02:00 under EST):
   Task 1, both parameters of `test_sunday_evening_run_is_dated_sunday`.
2. A row dated Sunday must not block Monday's write: Task 1, `test_monday_run_after_sunday_writes_the_monday_row`.
3. A replay for the coming Monday asked for on Sunday evening is "in the future": Task 1,
   `test_future_check_and_fallback_use_the_exchange_date`.
4. A brief handed to `persist_to_cloud_sql` without `analysis_date`: the same test.
5. A weekday morning must not change: Task 1, `test_weekday_morning_run_is_unchanged` (passes before
   and after).

## Task 1: Frozen-clock tests, red on main
Spec: § Design; § What the Sunday run does; § Consequences 3 and 6. Advances done_when[0], [1], [2], [3].
- [ ] In `tests/gcp/test_premarket_brief.py` add `_freeze_exchange_clock(monkeypatch, eastern: datetime) -> None`
  and `class TestLiveDateIsTheExchangeDate` with a `_run(monkeypatch, tables, eastern, entry, last_bar,
  premarket_day=None)` helper that runs `pb.main([])` for `BRIEF_TICKERS=SPY,IWM` on synthetic daily
  bars ending `last_bar` (plus the session's premarket row when `premarket_day` is given), with
  `gcp.database` answered from the `tables` dict (`premarket_analysis` keyed by date and ticker,
  `premarket_analysis_history` a list) and sockets refused
- [ ] `test_sunday_evening_run_is_dated_sunday`, parameters `(2026-11-15 21:00, 2026-11-13, 2026-11-16,
  2026-11-20)` and `(2026-07-12 21:00, 2026-07-10, 2026-07-13, 2026-07-17)`: `analysis_date` is the
  Sunday; `load_earnings_for_brief` got `weekly=True` and its query window is Monday to Friday;
  `load_yesterday_amc_reactions` was not called; `load_economic_events` got `days_ahead=7`; every
  history row is dated the Sunday and no row in either table is dated the Monday
- [ ] `test_monday_run_after_sunday_writes_the_monday_row`: the Sunday run, then `2026-11-16 08:30` with
  the premarket row; the canonical table holds a live row dated 2026-11-16 for SPY and IWM whose
  `level_basis['premarket_status']` is `ok` and whose `analysis_ts` is the Monday run's; no
  "row already exists" warning in `caplog`
- [ ] `test_future_check_and_fallback_use_the_exchange_date`: at `2026-11-15 21:00`,
  `BRIEF_AS_OF=2026-11-16` raises `ValueError` matching `future`, `BRIEF_AS_OF=2026-11-15` returns
  2026-11-15, and `persist_to_cloud_sql` of a brief with no `analysis_date` writes rows dated 2026-11-15
  (the three results are compared in one assertion so main shows all of them)
- [ ] `test_weekday_morning_run_is_unchanged`: at `2026-11-10 08:30`, dated 2026-11-10, `weekly=False`,
  canonical rows dated 2026-11-10
- [ ] Run: `python3 -m pytest -q -p no:cacheprovider tests/gcp/test_premarket_brief.py -k TestLiveDateIsTheExchangeDate`
  (expect 4 failed, 1 passed: the weekday control passes on main)
- [ ] Commit with this plan: `test(brief): pin the brief's live date to the exchange clock`

## Task 2: The four lines
Spec: § Design (the table). Advances done_when[0], [1], [2], [5].
- [ ] `gcp/premarket_brief.py`: import `market_today` from `lib.eastern_time`; `_resolve_analysis_date`
  returns `market_today()` and compares `BRIEF_AS_OF` with `market_today()`; `persist_to_cloud_sql`
  falls back to `market_today()`; the docstring of the first and the comment above the last say the
  exchange's date, in the same number of lines
- [ ] Run the Task 1 command (expect 5 passed) and
  `python3 -m pytest -q -p no:cacheprovider tests/scripts/test_check_generated_docs.py` (expect pass)
- [ ] Commit: `fix(brief): date a live run by the exchange's date, not the container's`

## Task 3: The three existing tests that pin the host clock
Spec: § Design (tests). Advances done_when[4].
- [ ] `TestResolveAnalysisDate::test_default_returns_today` and `::test_blank_falls_back_to_today` freeze
  `2026-11-15 21:00` America/New_York and assert `date(2026, 11, 15)`
- [ ] `test_brief_pipeline_never_acquires_ew_recap`, live parameter: freeze `08:30` America/New_York on the
  parameter's date instead of replacing `pb.date` alone
- [ ] Run every test file under `tests/` that names `premarket_brief` (expect all pass)
- [ ] Commit: `test(brief): fix the exchange clock in the tests that read the host date`

## Task 4: The ratchet baseline
Spec: § The file's five ratchet entries. Advances done_when[6].
- [ ] Run: `python -m tests.meta.test_timezone_boundaries --write-baseline`; the diff of
  `tests/fixtures/timezone_boundary_baseline.json` removes the three `host-today` entries of
  `gcp/premarket_brief.py` and nothing else
- [ ] Run: `python3 -m pytest -q -p no:cacheprovider tests/meta/test_timezone_boundaries.py` (expect pass);
  `grep -c 'tz-ok' gcp/premarket_brief.py` prints 0
- [ ] Commit: `test(meta): drop the brief's three host-date sites from the timezone baseline`

## Task 5: Source identity and close
Spec: § Intake (SITE component); § Close-out. Advances done_when[7], closes done_when[8].
- [ ] Add the `(FEAT-PLAYBOOK-001, DASHBOARD-01)` row to the Implementation-source notes table of
  `docs/product/03-SITE-TRACEABILITY.md` with the producer's `source_identity_sha256`, commit, produce
  `docs/review-evidence/site-source-snapshot.json` from the committed body, commit it and run `verify`
  from the committed HEAD
- [ ] Update the 02-FEATURE-CATALOG FEAT-PLAYBOOK-001 record (Status, Last reviewed)
- [ ] Add this PR to 12-PR-ISSUE-TRACEABILITY once it has a number, and set `pr` here
- [ ] Docs audit reports nothing new over origin/main (`python3 scripts/maintenance/docs_audit.py`)
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main`
